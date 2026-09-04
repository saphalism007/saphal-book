"""
The schedules that sit behind a set of accounts.

An audit file is not a balance sheet and a profit and loss. It is those two
with a working behind every figure that matters, and the ones that get asked
for first are always the same:

    the movement in fixed assets, cost and depreciation, both years
    the fixed asset register, asset by asset
    the depreciation working under Schedule 2 of the Income Tax Act, 2058
    the deferred tax working, book value against tax value
    the financial instruments note under NFRS 7

Everything here reads. Nothing here posts.
"""

import datetime

from ..core import money, nepali_date as nd
from . import masters, reports


# Schedule 2 of the Income Tax Act, 2058
#
# The classes and their rates. Depreciation is worked out on the pool, not on
# each asset, which is why the tax figure and the book figure hardly ever agree
# and why the deferred tax working exists at all.

TAX_CLASSES = [
    ("A", "Buildings, structures and similar works of a permanent nature", 500),
    ("B", "Computers, data handling equipment, fixtures, office furniture and "
          "office equipment", 2500),
    ("C", "Automobiles, buses and minibuses", 2000),
    ("D", "Construction and earth moving equipment, and any depreciable asset "
          "not falling in another class", 1500),
    ("E", "Intangible assets other than depreciable assets, written off over "
          "the useful life", 0),
]

TAX_CLASS_LOOKUP = {code: (description, rate) for code, description, rate in TAX_CLASSES}

# How much of an addition is taken into the pool in the year it is bought.
# First four months of the income year in full, the middle four at two thirds,
# the last four at one third.
ABSORPTION = [
    ((4, 5, 6, 7), 3, 3, "Bought in the first four months, taken in full"),
    ((8, 9, 10, 11), 2, 3, "Bought in the middle four months, two thirds taken"),
    ((12, 1, 2, 3), 1, 3, "Bought in the last four months, one third taken"),
]

# A pool this small is simply written off. Schedule 2, section 2.
SMALL_POOL_LIMIT = money.to_paisa("2000")


def absorption_for(date_ad):
    """What fraction of a purchase enters the pool in the year it was bought."""
    _, month, _ = nd.ad_to_bs(date_ad)
    for months, numerator, denominator, label in ABSORPTION:
        if month in months:
            return numerator, denominator, label
    return 3, 3, ""


# Movement in fixed assets


def movement_schedule(conn, group_code, from_ad, to_ad, compare=None):
    """
    The movement in a group of assets: cost brought forward, bought, sold,
    carried forward, and the same for the depreciation against it.

    Works for property, plant and equipment, for intangibles, for investment
    property, for anything held at cost less depreciation.
    """
    group = masters.group_by_code(conn, group_code)
    if group is None:
        return None

    opening_moves = reports.account_movements(conn, upto_ad=reports._day_before(from_ad))
    period = reports.account_movements(conn, from_ad=from_ad, upto_ad=to_ad)

    cost_rows, depreciation_rows = [], []
    for account in reports._account_rows(conn):
        if account["group_id"] != group["id"]:
            continue
        odr, ocr = opening_moves.get(account["id"], (0, 0))
        opening = account["opening_paisa"] + odr - ocr
        pdr, pcr = period.get(account["id"], (0, 0))
        closing = opening + pdr - pcr
        if opening == 0 and pdr == 0 and pcr == 0:
            continue
        if account["account_kind"] == "contra_asset":
            depreciation_rows.append({
                "account_id": account["id"], "code": account["code"], "name": account["name"],
                "opening": -opening, "charge": pcr, "on_disposal": pdr, "closing": -closing,
            })
        else:
            cost_rows.append({
                "account_id": account["id"], "code": account["code"], "name": account["name"],
                "opening": opening, "additions": pdr, "disposals": pcr, "closing": closing,
            })

    def total(rows, key):
        return sum(row[key] for row in rows)

    result = {
        "group_code": group_code, "group_name": group["name"],
        "from_ad": from_ad, "to_ad": to_ad,
        "cost": cost_rows,
        "depreciation": depreciation_rows,
        "cost_totals": {k: total(cost_rows, k)
                        for k in ("opening", "additions", "disposals", "closing")},
        "depreciation_totals": {k: total(depreciation_rows, k)
                                for k in ("opening", "charge", "on_disposal", "closing")},
        "previous": None,
    }
    result["carrying_opening"] = result["cost_totals"]["opening"] - result["depreciation_totals"]["opening"]
    result["carrying_closing"] = result["cost_totals"]["closing"] - result["depreciation_totals"]["closing"]

    if compare:
        result["previous"] = movement_schedule(conn, group_code,
                                               compare["from_ad"], compare["to_ad"])
    return result


# The register itself


def _bs_month_index(date_ad):
    """A single number for a Bikram Sambat month, so two can be subtracted."""
    year, month, _ = nd.ad_to_bs(date_ad)
    return year * 12 + (month - 1)


def _months_held(acquired_ad, from_ad, to_ad, disposed_ad=""):
    """
    How many months of the period an asset was in use.

    Counted in Nepali months, because that is the calendar the accounts are
    kept in. An asset bought part way through Mangsir is charged from Mangsir,
    which is how a monthly charge is normally applied in Nepal.
    """
    start = max(acquired_ad, from_ad)
    finish = min(to_ad, disposed_ad) if disposed_ad else to_ad
    if finish < start:
        return 0
    months = _bs_month_index(finish) - _bs_month_index(start) + 1
    return max(0, min(12, months))


def asset_register(conn, from_ad, to_ad, include_disposed=True):
    """
    Every asset the business owns, with what it cost, what has been written off
    it, and what it is carried at. This is the schedule an auditor ticks the
    physical verification against.
    """
    rows = []
    for asset in conn.execute("""SELECT f.*, a.name AS account_name, a.code AS account_code
                                 FROM fixed_assets f
                                 JOIN accounts a ON a.id = f.asset_account_id
                                 ORDER BY f.tax_class, f.acquired_ad, f.code"""):
        disposed = bool(asset["disposed_ad"]) and asset["disposed_ad"] <= to_ad
        if disposed and not include_disposed:
            continue
        if asset["acquired_ad"] > to_ad:
            continue

        bought_in_period = from_ad <= asset["acquired_ad"] <= to_ad
        cost = asset["cost_paisa"] or asset["opening_cost_paisa"]

        opening_accumulated = asset["opening_accumulated_paisa"]
        # Depreciation charged in earlier years, worked out the same way.
        prior_charge = 0
        if not bought_in_period and asset["acquired_ad"] < from_ad:
            prior_charge = _book_depreciation(asset, asset["acquired_ad"],
                                              reports._day_before(from_ad), cost,
                                              opening_accumulated)
        accumulated_before = opening_accumulated + prior_charge
        charge = 0 if disposed and asset["disposed_ad"] < from_ad else _book_depreciation(
            asset, from_ad, to_ad, cost, accumulated_before)
        accumulated_after = accumulated_before + charge
        if accumulated_after > cost - asset["residual_paisa"]:
            accumulated_after = max(0, cost - asset["residual_paisa"])
            charge = accumulated_after - accumulated_before

        carrying = cost - accumulated_after
        gain = None
        if disposed:
            gain = asset["disposal_proceeds_paisa"] - carrying

        description, rate = TAX_CLASS_LOOKUP.get(asset["tax_class"], ("", 0))
        rows.append({
            "id": asset["id"], "code": asset["code"], "name": asset["name"],
            "description": asset["description"],
            "account_code": asset["account_code"], "account_name": asset["account_name"],
            "tax_class": asset["tax_class"], "tax_rate_bp": rate,
            "acquired_ad": asset["acquired_ad"],
            "acquired_bs": asset["acquired_bs"] or nd.format_bs(nd.ad_to_bs(asset["acquired_ad"]), "numeric"),
            "cost": cost,
            "book_method": asset["book_method"], "book_rate_bp": asset["book_rate_bp"],
            "useful_life_years": asset["useful_life_years"],
            "residual": asset["residual_paisa"],
            "opening_accumulated": accumulated_before,
            "charge": charge,
            "closing_accumulated": accumulated_after,
            "carrying": carrying,
            "bought_in_period": bought_in_period,
            "disposed": disposed,
            "disposed_ad": asset["disposed_ad"],
            "disposal_proceeds": asset["disposal_proceeds_paisa"],
            "gain_on_disposal": gain,
            "location": asset["location"], "serial_no": asset["serial_no"],
            "supplier": asset["supplier"], "invoice_no": asset["invoice_no"],
            "months_held": _months_held(asset["acquired_ad"], from_ad, to_ad,
                                        asset["disposed_ad"]),
        })

    live = [r for r in rows if not r["disposed"]]
    return {
        "from_ad": from_ad, "to_ad": to_ad,
        "rows": rows,
        "totals": {
            "cost": sum(r["cost"] for r in live),
            "opening_accumulated": sum(r["opening_accumulated"] for r in live),
            "charge": sum(r["charge"] for r in rows),
            "closing_accumulated": sum(r["closing_accumulated"] for r in live),
            "carrying": sum(r["carrying"] for r in live),
            "additions": sum(r["cost"] for r in rows if r["bought_in_period"]),
            "disposal_proceeds": sum(r["disposal_proceeds"] for r in rows if r["disposed"]),
        },
        "count": len(live),
        "disposed_count": sum(1 for r in rows if r["disposed"]),
    }


def _book_depreciation(asset, from_ad, to_ad, cost, accumulated):
    """
    What the books charge, which is a separate question from what the tax
    working allows. Straight line or reducing balance, apportioned for the part
    of the period the asset was actually held.
    """
    method = asset["book_method"]
    if method == "none":
        return 0
    months = _months_held(asset["acquired_ad"], from_ad, to_ad, asset["disposed_ad"])
    if months <= 0:
        return 0
    depreciable = cost - asset["residual_paisa"]
    if depreciable <= accumulated:
        return 0
    if method == "slm":
        life = asset["useful_life_years"] or 0
        if life > 0:
            yearly = money.round_half_up(depreciable, life)
        else:
            yearly = money.apply_rate(depreciable, asset["book_rate_bp"])
    else:
        written_down = cost - accumulated
        yearly = money.apply_rate(written_down, asset["book_rate_bp"])
    charge = money.round_half_up(yearly * months, 12)
    return min(charge, depreciable - accumulated)


# Depreciation under the Income Tax Act


def tax_depreciation(conn, start_bs_year, special_industry=False):
    """
    The depreciation working under Schedule 2 of the Income Tax Act, 2058.

    Pool by pool: what was brought forward, what was bought and how much of it
    the year absorbs, what was sold, the depreciation base, the rate, and what
    is carried forward.

    The pools are built from the beginning so a year can never be worked out
    from a figure somebody typed in by mistake.
    """
    fiscal = nd.fiscal_year(start_bs_year)

    openings = {row["tax_class"]: row["opening_wdv"]
                for row in conn.execute("SELECT tax_class, opening_wdv FROM tax_pool_opening")}
    assets = conn.execute("SELECT * FROM fixed_assets ORDER BY acquired_ad, id").fetchall()

    first_year = _earliest_year(conn, assets)
    if first_year is None:
        first_year = start_bs_year

    pools = {code: dict(opening=openings.get(code, 0)) for code, _d, _r in TAX_CLASSES}
    carried = {code: openings.get(code, 0) for code, _d, _r in TAX_CLASSES}
    working = None

    # If the register starts later than the year being asked for, there is
    # simply nothing in the pools yet, and the working for that year is empty
    # rather than missing.
    year = min(first_year, start_bs_year)
    while year <= start_bs_year:
        working = _tax_year(conn, assets, nd.fiscal_year(year), carried, special_industry)
        carried = {code: pool["closing"] for code, pool in working["pools"].items()}
        year += 1

    working["fiscal_year"] = fiscal
    working["from_first_year"] = first_year
    return working


def _earliest_year(conn, assets):
    years = []
    for asset in assets:
        try:
            years.append(nd.fiscal_year_of(asset["acquired_ad"])["start_bs"][0])
        except nd.DateRangeError:
            continue
    row = conn.execute("SELECT books_begin_ad FROM company WHERE id = 1").fetchone()
    if row:
        try:
            years.append(nd.fiscal_year_of(row["books_begin_ad"])["start_bs"][0])
        except nd.DateRangeError:
            pass
    return min(years) if years else None


def _tax_year(conn, assets, fiscal, opening, special_industry):
    """One income year of the pool working."""
    pools = {}
    for code, description, rate in TAX_CLASSES:
        applied = rate
        if special_industry and rate:
            # A special industry may add one third to the rate. Schedule 2.
            applied = rate + money.round_half_up(rate, 3)
        pools[code] = {
            "code": code, "description": description, "rate_bp": applied,
            "opening": opening.get(code, 0),
            "additions": 0, "absorbed": 0, "unabsorbed": 0,
            "disposals": 0, "base": 0, "depreciation": 0, "closing": 0,
            "items": [], "small_pool": False,
        }

    for asset in assets:
        pool = pools.get(asset["tax_class"])
        if pool is None:
            continue
        if fiscal["start_ad"] <= asset["acquired_ad"] <= fiscal["end_ad"]:
            cost = asset["cost_paisa"] or asset["opening_cost_paisa"]
            numerator, denominator, label = absorption_for(asset["acquired_ad"])
            absorbed = money.round_half_up(cost * numerator, denominator)
            pool["additions"] += cost
            pool["absorbed"] += absorbed
            pool["unabsorbed"] += cost - absorbed
            pool["items"].append({
                "code": asset["code"], "name": asset["name"],
                "acquired_ad": asset["acquired_ad"],
                "acquired_bs": nd.format_bs(nd.ad_to_bs(asset["acquired_ad"]), "numeric"),
                "cost": cost, "absorbed": absorbed, "fraction": "%d/%d" % (numerator, denominator),
                "reason": label, "kind": "addition",
            })
        if asset["disposed_ad"] and fiscal["start_ad"] <= asset["disposed_ad"] <= fiscal["end_ad"]:
            pool["disposals"] += asset["disposal_proceeds_paisa"]
            pool["items"].append({
                "code": asset["code"], "name": asset["name"],
                "acquired_ad": asset["disposed_ad"],
                "acquired_bs": nd.format_bs(nd.ad_to_bs(asset["disposed_ad"]), "numeric"),
                "cost": asset["disposal_proceeds_paisa"], "absorbed": 0,
                "fraction": "", "reason": "Sold during the year", "kind": "disposal",
            })

    for pool in pools.values():
        base = pool["opening"] + pool["absorbed"] - pool["disposals"]
        pool["base"] = base
        if base <= 0:
            pool["depreciation"] = 0
            pool["closing"] = base + pool["unabsorbed"]
            continue
        if base < SMALL_POOL_LIMIT:
            # A pool below the limit is written off in full rather than carried
            # on for years at a few rupees a time.
            pool["depreciation"] = base
            pool["small_pool"] = True
        else:
            pool["depreciation"] = money.apply_rate(base, pool["rate_bp"])
        pool["closing"] = base - pool["depreciation"] + pool["unabsorbed"]

    totals = {key: sum(pool[key] for pool in pools.values())
              for key in ("opening", "additions", "absorbed", "unabsorbed",
                          "disposals", "base", "depreciation", "closing")}
    return {"fiscal_year": fiscal, "pools": pools, "totals": totals,
            "special_industry": special_industry}


# Deferred tax


# Provisions the Income Tax Act does not allow until the money is actually paid.
# The difference reverses when it is, which is what makes it a deferred tax
# asset rather than a permanent difference.
DEDUCTIBLE_ON_PAYMENT = ["1224", "2131", "2132", "2265", "2283"]


def income_tax_rate(conn):
    """The rate the company is assessed at, kept as a setting."""
    row = conn.execute("SELECT value FROM settings WHERE key = 'income_tax_rate'").fetchone()
    if row and row["value"]:
        return money.rate_to_bp(row["value"])
    return 2500  # 25 percent, the general rate for a company in Nepal


def deferred_tax(conn, start_bs_year, compare_bs_year=None):
    """
    The deferred tax working.

    What the books carry an asset at against what the tax working carries it at.
    The difference is temporary: it will reverse, and the tax effect of that
    reversal is recognised now under NAS 12.

    A taxable temporary difference, where the books carry more than tax does,
    gives a liability. A deductible one gives an asset.
    """
    fiscal = nd.fiscal_year(start_bs_year)
    rate = income_tax_rate(conn)
    to_ad = fiscal["end_ad"]

    register = asset_register(conn, fiscal["start_ad"], to_ad, include_disposed=False)
    book_value = register["totals"]["carrying"]
    tax_working = tax_depreciation(conn, start_bs_year)
    tax_value = tax_working["totals"]["closing"]

    balances = reports.balances_as_at(conn, to_ad)
    lines = [{
        "particular": "Property, plant and equipment",
        "book": book_value, "tax": tax_value,
        "difference": book_value - tax_value,
        "note": "Written down for the books against the pool written down value "
                "under Schedule 2 of the Income Tax Act, 2058.",
    }]

    for code in DEDUCTIBLE_ON_PAYMENT:
        account = masters.account_by_code(conn, code)
        if account is None:
            continue
        balance = balances.get(account["id"], 0)
        if balance == 0:
            continue
        # Balances are held debit positive, so a provision shows as a credit.
        # Its carrying amount in the books is the positive figure.
        carrying = -balance if balance < 0 else balance
        # Under NAS 12 the tax base of such a liability is nil, because the whole
        # of it will be deducted when it is paid. That is a deductible temporary
        # difference, which gives a deferred tax asset, so it carries the
        # opposite sign to the one property, plant and equipment gives.
        lines.append({
            "particular": account["name"],
            "book": carrying,
            "tax": 0,
            "difference": -carrying,
            "note": "Carried in the books but nil for tax until it is actually paid, "
                    "so it gives a deferred tax asset.",
        })

    total_difference = sum(line["difference"] for line in lines)
    deferred = money.apply_rate(total_difference, rate)

    result = {
        "fiscal_year": fiscal,
        "rate_bp": rate,
        "lines": lines,
        "total_difference": total_difference,
        "deferred_amount": deferred,
        "is_liability": deferred > 0,
        "book_value": book_value,
        "tax_value": tax_value,
        "previous": None,
        "movement": None,
    }

    if compare_bs_year is not None:
        earlier = deferred_tax(conn, compare_bs_year)
        result["previous"] = earlier
        result["movement"] = deferred - earlier["deferred_amount"]
    return result


# Financial instruments, NFRS 7


INSTRUMENT_MAP = {
    "1220": ("financial_asset_amortised", "Trade receivables"),
    "1250": ("financial_asset_amortised", "Cash in hand"),
    "1260": ("financial_asset_amortised", "Balances with banks"),
    "1270": ("financial_asset_amortised", "Short term deposits"),
    "1170": ("financial_asset_amortised", "Deposits and loans given"),
    "1150": ("financial_asset_fvoci", "Investments in equity instruments"),
    "2210": ("financial_liability_amortised", "Trade payables"),
    "2110": ("financial_liability_amortised", "Borrowings"),
    "2220": ("financial_liability_amortised", "Short term borrowings and overdraft"),
    "2140": ("financial_liability_amortised", "Lease liabilities"),
    "2270": ("financial_liability_amortised", "Accrued expenses"),
    "2290": ("financial_liability_amortised", "Other payables"),
}

INSTRUMENT_SECTIONS = [
    ("financial_asset_amortised", "Financial assets measured at amortised cost"),
    ("financial_asset_fvoci", "Financial assets at fair value through other comprehensive income"),
    ("financial_asset_fvtpl", "Financial assets at fair value through profit or loss"),
    ("financial_liability_amortised", "Financial liabilities measured at amortised cost"),
    ("financial_liability_fvtpl", "Financial liabilities at fair value through profit or loss"),
]

# What is deliberately not a financial instrument, listed so the note can say so
# rather than leaving the reader to wonder where the stock went.
NOT_FINANCIAL = {
    "1210": "Inventories, which are goods rather than a contractual right to cash",
    "1230": "Advances and prepayments, which will be settled in goods or services",
    "1240": "Tax balances, which arise by statute rather than by contract",
    "1110": "Property, plant and equipment",
    "1140": "Intangible assets",
    "2230": "Advances from customers, settled by delivering goods",
    "2240": "Value added tax and duties",
    "2250": "Tax deducted at source",
    "2260": "Employee related dues",
    "2280": "Provisions for employee benefits",
}


def financial_instruments(conn, as_at_ad, compare_as_at=None):
    """
    The financial instruments note under NFRS 7, by the category each balance is
    measured in, with what is not a financial instrument set out underneath.
    """
    def gather(at_ad):
        balances = reports.balances_as_at(conn, at_ad)
        sections = {key: {"key": key, "title": title, "lines": [], "total": 0}
                    for key, title in INSTRUMENT_SECTIONS}
        excluded = []
        for account in reports._account_rows(conn):
            if account["statement"] != "BS":
                continue
            balance = balances.get(account["id"], 0)
            if balance == 0:
                continue
            amount = -balance if account["nature"] in reports.CREDIT_NATURES else balance
            mapped = INSTRUMENT_MAP.get(account["group_code"])
            if mapped is None:
                reason = NOT_FINANCIAL.get(account["group_code"])
                if reason:
                    excluded.append({"code": account["code"], "name": account["name"],
                                     "amount": amount, "reason": reason})
                continue
            key, caption = mapped
            bucket = sections[key]
            bucket["lines"].append({
                "account_id": account["id"], "code": account["code"],
                "name": account["name"], "caption": caption, "amount": amount})
            bucket["total"] += amount
        return sections, excluded

    sections, excluded = gather(as_at_ad)
    previous_sections = gather(compare_as_at)[0] if compare_as_at else None

    if previous_sections:
        for key, bucket in sections.items():
            old = previous_sections[key]
            by_account = {line["account_id"]: line["amount"] for line in old["lines"]}
            for line in bucket["lines"]:
                line["previous"] = by_account.get(line["account_id"], 0)
            seen = {line["account_id"] for line in bucket["lines"]}
            for line in old["lines"]:
                if line["account_id"] not in seen:
                    bucket["lines"].append(dict(line, amount=0, previous=line["amount"]))
            bucket["previous_total"] = old["total"]

    total_assets = sum(sections[key]["total"] for key, _t in INSTRUMENT_SECTIONS
                       if key.startswith("financial_asset"))
    total_liabilities = sum(sections[key]["total"] for key, _t in INSTRUMENT_SECTIONS
                            if key.startswith("financial_liability"))

    # A maturity profile of what is owed, which NFRS 7 asks for.
    payable_ageing = reports.ageing(conn, "payable", as_at_ad)
    receivable_ageing = reports.ageing(conn, "receivable", as_at_ad)
    concentration = []
    if receivable_ageing["grand_total"]:
        for row in receivable_ageing["rows"][:5]:
            concentration.append({
                "name": row["name"], "amount": row["total"],
                "share_bp": money.round_half_up(row["total"] * 10000,
                                                receivable_ageing["grand_total"]),
            })

    return {
        "as_at_ad": as_at_ad, "compare_as_at": compare_as_at,
        "sections": [sections[key] for key, _t in INSTRUMENT_SECTIONS
                     if sections[key]["lines"]],
        "excluded": excluded,
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "maturity": {"labels": payable_ageing["labels"], "amounts": payable_ageing["totals"],
                     "total": payable_ageing["grand_total"]},
        "credit_concentration": concentration,
        "largest_share_bp": concentration[0]["share_bp"] if concentration else 0,
    }

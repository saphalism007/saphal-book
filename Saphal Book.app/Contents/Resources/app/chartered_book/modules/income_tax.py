"""
The income tax computation, under the Income Tax Act, 2058.

Profit in the books and income under the Act are two different numbers, and the
statement that gets one from the other is what an assessing officer reads first.
This produces that statement, line by line, from the books rather than from
anything typed twice.

    Net profit as shown by the books
      add   depreciation the books charged
      add   expenses the Act does not allow
      less  depreciation under Schedule 2, worked out from the pools
    Assessable income from business, section 7
      less  donations allowed under section 12
      less  losses brought forward, section 20
    Taxable income, section 3
      tax at the rates for the year
      less  tax already deducted at source
      less  advance tax paid
    What is left to pay

Two things this deliberately does not do.

It does not carry the tax rates inside it. Nepal sets them afresh in the Finance
Act each Jestha, so rates written into a program are confidently wrong every
year from the day it ships. They live in the books, against the year they belong
to, and can be corrected the morning the Finance Act is published.

It does not decide what is disallowable on somebody's behalf. It applies what
has been marked against each ledger and shows every line it added back, so the
person signing the return can see exactly what was done and change it.
"""

from ..core import money
from . import reports, schedules

# What the Act treats differently, and where to read about it.
TREATMENTS = {
    "allowed": "Deducted in full",
    "disallowed": "Added back in full",
    "partial": "Added back in part",
    "depreciation": "Replaced by the pool figure under Schedule 2",
    "donation": "Added back, then let out again up to the section 12 limit",
}

# Where the rates go when a year has none set yet. Written down as what they
# were, not as what they will be, and shown on screen as needing checking
# against the Finance Act for the year in question.
SEED_RATES = {
    # A natural person who has remuneration. The first band carries the one
    # percent social security tax.
    "individual": [
        (0, 50000000, 100, "First 5,00,000 at 1 percent, social security tax"),
        (50000000, 70000000, 1000, "Next 2,00,000 at 10 percent"),
        (70000000, 100000000, 2000, "Next 3,00,000 at 20 percent"),
        (100000000, 200000000, 3000, "Next 10,00,000 at 30 percent"),
        (200000000, None, 3600, "Above 20,00,000 at 36 percent"),
    ],
    "couple": [
        (0, 60000000, 100, "First 6,00,000 at 1 percent, social security tax"),
        (60000000, 80000000, 1000, "Next 2,00,000 at 10 percent"),
        (80000000, 110000000, 2000, "Next 3,00,000 at 20 percent"),
        (110000000, 200000000, 3000, "Next 9,00,000 at 30 percent"),
        (200000000, None, 3600, "Above 20,00,000 at 36 percent"),
    ],
    # A proprietor taxed on the profit of the firm. The one percent is a social
    # security tax on remuneration, so it does not touch business income, and
    # the first band is nil.
    "business_individual": [
        (0, 50000000, 0, "First 5,00,000 nil, the 1 percent is on remuneration only"),
        (50000000, 70000000, 1000, "Next 2,00,000 at 10 percent"),
        (70000000, 100000000, 2000, "Next 3,00,000 at 20 percent"),
        (100000000, 200000000, 3000, "Next 10,00,000 at 30 percent"),
        (200000000, None, 3600, "Above 20,00,000 at 36 percent"),
    ],
    "business_couple": [
        (0, 60000000, 0, "First 6,00,000 nil, the 1 percent is on remuneration only"),
        (60000000, 80000000, 1000, "Next 2,00,000 at 10 percent"),
        (80000000, 110000000, 2000, "Next 3,00,000 at 20 percent"),
        (110000000, 200000000, 3000, "Next 9,00,000 at 30 percent"),
        (200000000, None, 3600, "Above 20,00,000 at 36 percent"),
    ],
    "entity": [
        (0, None, 2500, "Companies generally, 25 percent"),
    ],
    # Section 11. A special industry, and several others besides, pays twenty
    # percent rather than twenty five.
    "entity_special": [
        (0, None, 2000, "Special industry under section 11, 20 percent"),
    ],
}

# What each set is called on screen.
RATE_SETS = {
    "individual": "A person, single",
    "couple": "A person, couple",
    "business_individual": "A proprietor, single",
    "business_couple": "A proprietor, couple",
    "entity": "A company or a firm",
    "entity_special": "A company, special industry",
}


ENTITY_ASSESSED_AS = {
    "proprietorship": "business_individual",
    "partnership": "entity",
    "private_limited": "entity",
    "public_limited": "entity",
    "cooperative": "entity",
    "ngo": "entity",
    "other": "entity",
}


class TaxError(Exception):
    """Raised when the computation cannot be made."""


def assessed_as(conn, start_bs_year):
    """Whether this year is taxed on the slabs for a person or a flat rate."""
    row = conn.execute("SELECT assessed_as FROM tax_year_settings WHERE start_bs_year = ?",
                       (start_bs_year,)).fetchone()
    if row and row["assessed_as"]:
        return row["assessed_as"]
    company = conn.execute("SELECT entity_type FROM company WHERE id = 1").fetchone()
    return ENTITY_ASSESSED_AS.get(company["entity_type"] if company else "other", "entity")


def rate_set_for(conn, start_bs_year):
    """
    Which set of bands this year is charged on.

    Section 11. A special industry is not only allowed a third more
    depreciation, it is charged at twenty percent rather than twenty five, so
    ticking that box has to move both or the return is wrong on one of them.
    """
    who = assessed_as(conn, start_bs_year)
    row = conn.execute("SELECT special_industry FROM tax_year_settings WHERE start_bs_year = ?",
                       (start_bs_year,)).fetchone()
    if row and row["special_industry"] and who == "entity":
        return "entity_special"
    return who


def rates(conn, start_bs_year, applies_to):
    """
    The bands for one year, in order, and whether anybody has confirmed them.

    Where a year has none set, the seed is handed back so there is a statement
    to look at rather than an error, but nothing is written to the books. The
    second return value says so, and the screen says so too, until somebody has
    checked the figures against the Finance Act for that year and saved them.
    """
    rows = conn.execute(
        """SELECT band_from, band_to, rate_bp, note FROM tax_rates
           WHERE start_bs_year = ? AND applies_to = ?
           ORDER BY band_from""", (start_bs_year, applies_to)).fetchall()
    if rows:
        return [dict(row) for row in rows], False
    return [{"band_from": a, "band_to": b, "rate_bp": r, "note": n}
            for a, b, r, n in SEED_RATES.get(applies_to, [])], True


def save_rates(conn, username, start_bs_year, applies_to, bands):
    """
    Write the bands for one year, replacing whatever was there.

    Bands are given lowest first as (from, to, rate, note), amounts in rupees
    and the rate as a percentage. The top band is given no ceiling.
    """
    from ..core import audit
    cleaned, floor = [], 0
    for band in bands:
        band_from = money.to_paisa(band.get("band_from", 0) or 0)
        raw_to = band.get("band_to")
        band_to = None if raw_to in (None, "", "-") else money.to_paisa(raw_to)
        if band_to is not None and band_to <= band_from:
            raise TaxError("A band has to end above where it starts.")
        if band_from != floor:
            raise TaxError("Each band has to start where the one below it ended.")
        floor = band_to if band_to is not None else band_from
        cleaned.append((band_from, band_to, money.rate_to_bp(band.get("rate_bp", 0) or 0),
                        (band.get("note") or "").strip()))
        if band_to is None:
            break
    if not cleaned:
        raise TaxError("A year needs at least one band.")
    if cleaned[-1][1] is not None:
        raise TaxError("The top band has to be left open at the upper end.")
    conn.execute("DELETE FROM tax_rates WHERE start_bs_year = ? AND applies_to = ?",
                 (start_bs_year, applies_to))
    conn.executemany(
        """INSERT INTO tax_rates
           (start_bs_year, applies_to, band_from, band_to, rate_bp, note)
           VALUES (?, ?, ?, ?, ?, ?)""",
        [(start_bs_year, applies_to) + row for row in cleaned])
    audit.log(conn, username, "tax.rates", "tax_rates", start_bs_year,
              "%d %s" % (start_bs_year, applies_to),
              "Tax rates for %d set, %d band%s" % (start_bs_year, len(cleaned),
                                                   "" if len(cleaned) == 1 else "s"),
              None, None)
    return cleaned


def tax_on(taxable, bands):
    """
    Work the tax out band by band, and show the working.

    Every band is shown, including the ones the income did not reach, because a
    computation that only shows the bands that bit is harder to check than one
    that shows them all.
    """
    lines = []
    total = 0
    for band in bands:
        floor = band["band_from"]
        ceiling = band["band_to"]
        if ceiling is None:
            slice_amount = max(0, taxable - floor)
        else:
            slice_amount = max(0, min(taxable, ceiling) - floor)
        charge = money.apply_rate(slice_amount, band["rate_bp"])
        total += charge
        lines.append({
            "from": floor, "to": ceiling, "rate_bp": band["rate_bp"],
            "amount": slice_amount, "tax": charge, "note": band["note"],
        })
    return total, lines


def _adjustments(conn, from_ad, to_ad):
    """
    Every ledger the Act treats differently, with what it does to the profit.

    Read off what has been marked against each account, so the statement can say
    which ledger each addition came from rather than presenting one lump.

    Three things come back: the ledgers added back, the depreciation the books
    charged, and what was given away in donations. Donations are separated
    because they are added back here and then let out again further down, up to
    the section 12 limit, which cannot be worked out until the assessable income
    is known.
    """
    period = reports.account_movements(conn, from_ad=from_ad, upto_ad=to_ad)
    added_back = []
    book_depreciation = 0
    donations = 0
    for account in reports._account_rows(conn):
        if account["statement"] != "PL":
            continue
        keys = account.keys()
        treatment = account["tax_treatment"] if "tax_treatment" in keys else "allowed"
        if treatment == "allowed":
            continue
        dr, cr = period.get(account["id"], (0, 0))
        spent = dr - cr
        if spent <= 0:
            continue
        if treatment == "depreciation":
            book_depreciation += spent
            continue
        if treatment == "donation":
            donations += spent
        allowed_bp = account["tax_allowed_bp"] if "tax_allowed_bp" in keys else 10000
        if treatment == "partial":
            back = spent - money.apply_rate(spent, allowed_bp)
        else:
            back = spent
        if back:
            added_back.append({
                "account_id": account["id"], "code": account["code"],
                "name": account["name"], "spent": spent, "added_back": back,
                "treatment": treatment,
                "why": TREATMENTS[treatment],
                "note": account["tax_note"] if "tax_note" in keys else "",
            })
    added_back.sort(key=lambda row: -row["added_back"])
    return added_back, book_depreciation, donations


def computation(conn, start_bs_year):
    """
    The whole statement, from the profit in the books to what is left to pay.

    Every figure comes from the books. Nothing is typed twice, so nothing can
    disagree with the accounts it was supposed to have come from.
    """
    from ..core import nepali_date as nd
    fiscal = nd.fiscal_year(start_bs_year)
    from_ad, to_ad = fiscal["start_ad"], fiscal["end_ad"]

    settings = conn.execute("SELECT * FROM tax_year_settings WHERE start_bs_year = ?",
                            (start_bs_year,)).fetchone()
    special = bool(settings["special_industry"]) if settings else False
    typed_advance = settings["advance_tax_paid"] if settings else 0
    brought_forward = settings["brought_forward_loss"] if settings else 0

    pl = reports.profit_and_loss(conn, from_ad, to_ad)
    net_profit = pl["profit_before_tax"]

    added_back, book_depreciation, donation_given = _adjustments(conn, from_ad, to_ad)
    additions = sum(row["added_back"] for row in added_back)

    pools = schedules.tax_depreciation(conn, start_bs_year, special)
    tax_depreciation = pools["totals"]["depreciation"] if pools else 0

    assessable = net_profit + book_depreciation + additions - tax_depreciation

    # Section 12. A donation is deductible up to the lowest of five percent of
    # assessable income, one hundred thousand rupees, and what was actually
    # given. Every rupee of it was added back above, so only the allowed part
    # comes off here. Where the year is a loss there is no assessable income to
    # take five percent of, so nothing is allowed.
    donation_cap = min(money.apply_rate(max(assessable, 0), 500),
                       money.to_paisa("100000"))
    donation_allowed = min(donation_given, donation_cap) if assessable > 0 else 0

    after_donation = assessable - donation_allowed

    # Section 20. A loss brought in can only be set against a profit, and
    # whatever is not used, together with this year's own loss, goes forward.
    loss_used = min(max(brought_forward, 0), max(after_donation, 0))
    taxable = max(after_donation - loss_used, 0)
    carried_forward = max(brought_forward - loss_used, 0) + max(-after_donation, 0)

    who = rate_set_for(conn, start_bs_year)
    bands, seeded = rates(conn, start_bs_year, who)
    tax, band_lines = tax_on(taxable, bands)

    tds = _ledger_movement(conn, "1244", from_ad, to_ad)
    # What was paid in advance is read off the ledger where it was posted. The
    # figure on the settings screen is only for a payment that has not reached
    # the books yet, so it is used where the ledger is silent and ignored where
    # it is not, and never added twice.
    posted_advance = _ledger_movement(conn, "1243", from_ad, to_ad)
    advance = posted_advance or typed_advance
    advance_from = "the Advance Income Tax ledger" if posted_advance else "typed in"
    paid = tds + advance
    outstanding = tax - paid

    rows = [
        {"label": "Net profit as shown by the books", "amount": net_profit,
         "kind": "start"},
        {"label": "Add: depreciation charged in the books", "amount": book_depreciation,
         "note": "Replaced below by the figure under Schedule 2"},
        {"label": "Add: expenses the Act does not allow", "amount": additions,
         "note": "%d ledger%s, listed below" % (len(added_back),
                                                "" if len(added_back) == 1 else "s")},
        {"label": "Less: depreciation under Schedule 2", "amount": -tax_depreciation,
         "note": "Worked out on the pools, not asset by asset"},
        {"label": "Assessable income from business, section 7", "amount": assessable,
         "kind": "total"},
        {"label": "Less: donation allowed, section 12", "amount": -donation_allowed,
         "note": "Lowest of what was given, 5 percent of assessable income, "
                 "and Rs 1,00,000"},
        {"label": "Less: loss brought forward, section 20", "amount": -loss_used,
         "note": "" if not brought_forward else
                 "%s was carried in" % money.format_money(brought_forward)},
        {"label": "Taxable income, section 3", "amount": taxable, "kind": "total"},
        {"label": "Tax on that", "amount": tax, "kind": "tax"},
        {"label": "Less: tax deducted at source", "amount": -tds,
         "note": "From the TDS receivable ledger"},
        {"label": "Less: advance tax paid", "amount": -advance,
         "note": "Section 94, three instalments, %s" % advance_from},
        {"label": "Left to pay" if outstanding >= 0 else "Refundable",
         "amount": abs(outstanding), "kind": "grand"},
    ]

    turnover = pl["revenue"]
    notices = []
    if seeded:
        notices.append(
            "The rates shown have not been confirmed for %s. Check them against "
            "the Finance Act for the year and save them." % fiscal["label"])
    if carried_forward:
        notices.append(
            "%s of loss goes forward. Section 20 gives seven income years to use "
            "it, so it has to be carried into %d as well."
            % (money.format_money(carried_forward), start_bs_year + 1))
    if donation_given > donation_allowed:
        notices.append(
            "%s was given and only %s is deductible. Section 12 caps it, and it "
            "only counts at all if the body it went to is an approved one."
            % (money.format_money(donation_given), money.format_money(donation_allowed)))
    if not added_back and not book_depreciation:
        notices.append(
            "No ledger is marked as disallowed. Fines, donations, provisions and "
            "prior period items belong on this list, so set them under Treatments.")
    if who.startswith("business") and 0 < turnover <= money.to_paisa("10000000"):
        notices.append(
            "Turnover is %s. A natural person below one crore may pay turnover "
            "tax under section 4(4a) instead of tax on profit. Worth comparing."
            % money.format_money(turnover))
    if not advance:
        notices.append(
            "No advance tax is recorded for the year. Section 94 wants it in "
            "three instalments, by Poush, Chaitra and Ashadh.")

    return {
        "start_bs_year": start_bs_year,
        "label": fiscal["label"],
        "from_ad": from_ad, "to_ad": to_ad,
        "assessed_as": who,
        "assessed_as_label": RATE_SETS.get(who, who),
        "special_industry": special,
        "rates_were_seeded": seeded,
        "rows": rows,
        "added_back": added_back,
        "bands": band_lines,
        "pools": pools,
        "notices": notices,
        "turnover": turnover,
        "net_profit": net_profit,
        "book_depreciation": book_depreciation,
        "additions": additions,
        "tax_depreciation": tax_depreciation,
        "assessable": assessable,
        "taxable": taxable,
        "tax": tax,
        "tds": tds,
        "advance_tax": advance,
        "advance_tax_from": advance_from,
        "outstanding": outstanding,
        "brought_forward_loss": brought_forward,
        "loss_used": loss_used,
        "loss_carried_forward": carried_forward,
        "donation_given": donation_given,
        "donation_cap": donation_cap,
        "donation_allowed": donation_allowed,
    }


def _ledger_movement(conn, code, from_ad, to_ad):
    """What one ledger took in over the year, nil where there is no such ledger."""
    from . import masters
    account = masters.account_by_code(conn, code)
    if account is None:
        return 0
    dr, cr = reports.account_movements(conn, from_ad=from_ad, upto_ad=to_ad).get(
        account["id"], (0, 0))
    return max(dr - cr, 0)


def set_year(conn, username, start_bs_year, **fields):
    """Record what has been paid and how the year is assessed."""
    from ..core import audit
    conn.execute("INSERT OR IGNORE INTO tax_year_settings (start_bs_year) VALUES (?)",
                 (start_bs_year,))
    allowed = ("assessed_as", "special_industry", "advance_tax_paid",
               "brought_forward_loss", "note")
    sets, args = [], []
    for key in allowed:
        if key in fields:
            value = fields[key]
            if key in ("advance_tax_paid", "brought_forward_loss"):
                value = money.to_paisa(value or 0)
            if key == "special_industry":
                value = 1 if value else 0
            sets.append("%s = ?" % key)
            args.append(value)
    if not sets:
        return
    args.append(start_bs_year)
    conn.execute("UPDATE tax_year_settings SET %s WHERE start_bs_year = ?"
                 % ", ".join(sets), args)
    audit.log(conn, username, "tax.year", "tax_year_settings", start_bs_year,
              str(start_bs_year), "Income tax settings for %d changed" % start_bs_year,
              None, fields)


def set_treatment(conn, username, account_id, treatment, allowed_bp=10000, note=""):
    """Say how one ledger is treated when the profit is turned into income."""
    if treatment not in TREATMENTS:
        raise TaxError("A ledger is allowed, disallowed, partial or depreciation.")
    conn.execute(
        "UPDATE accounts SET tax_treatment = ?, tax_allowed_bp = ?, tax_note = ? WHERE id = ?",
        (treatment, int(allowed_bp), note, account_id))
    from ..core import audit
    audit.log(conn, username, "tax.treatment", "accounts", account_id, treatment,
              "Tax treatment set to %s" % TREATMENTS[treatment], None, None)

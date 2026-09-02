"""
The formal financial statements.

What an audit in Nepal expects to be handed is a set, not a single page:

    Statement of Financial Position
    Statement of Profit or Loss and Other Comprehensive Income
    Statement of Changes in Equity
    Statement of Cash Flows
    Notes, with a schedule behind every line on the face of the statements

The presentation follows the Nepal Financial Reporting Standards, which take
NAS 01 for presentation and NAS 07 for cash flows. Comparative figures for the
previous year sit beside every figure, because NAS 01 requires them and because
a statement without last year beside it tells you very little.

Nothing here writes to the books.
"""

from ..core import money, nepali_date as nd
from . import reports


# Which part of the cash flow statement a movement belongs to. Keyed by the
# code of the group the ledger sits in.
CASH_GROUPS = ("1250", "1260")

CASH_FLOW_SECTION = {
    # Operating: what the trade itself ties up or releases
    "1210": "operating",   # inventories
    "1220": "operating",   # trade receivables
    "1230": "operating",   # advances and prepayments
    "1240": "operating",   # tax assets
    "1280": "operating",   # other current assets
    "1160": "operating",   # deferred tax asset
    "2210": "operating",   # trade payables
    "2230": "operating",   # advance from customers
    "2240": "operating",   # value added tax and duties
    "2250": "operating",   # tax deducted at source
    "2260": "operating",   # employee related payables
    "2270": "operating",   # accruals
    "2280": "operating",   # provisions
    "2290": "operating",   # other current liabilities
    "2120": "operating",   # deferred tax liability
    "2130": "operating",   # long term provisions

    # Investing: what is spent on or recovered from long lived things
    "1110": "investing",   # property, plant and equipment at cost
    "1130": "investing",   # capital work in progress
    "1140": "investing",   # intangible assets
    "1150": "investing",   # long term investments
    "1170": "investing",   # deposits and long term advances
    "1180": "investing",   # investment property
    "1190": "investing",   # right of use assets
    "1270": "investing",   # short term investments

    # Financing: money put in, taken out, borrowed or repaid
    "2110": "financing",   # long term borrowings
    "2140": "financing",   # lease liabilities
    "2220": "financing",   # short term borrowings and overdraft
    "3100": "financing",   # capital
    "3200": "financing",   # reserves
    "3300": "financing",   # drawings
}


def _classify(account):
    """Where a balance sheet ledger belongs in the cash flow statement."""
    group = account["group_code"]
    if group in CASH_GROUPS:
        return "cash"
    # Accumulated depreciation is not a cash movement. It is matched by the
    # depreciation added back in the operating section, so it is left out here.
    if account["account_kind"] == "contra_asset":
        return "non_cash"
    return CASH_FLOW_SECTION.get(group, "operating")


def previous_period(from_ad, to_ad):
    """The same period one fiscal year earlier, for the comparative column."""
    try:
        fy = nd.fiscal_year_of(from_ad)
        start_year = fy["start_bs"][0] - 1
        if start_year < nd.BS_START_YEAR:
            return None
        earlier = nd.fiscal_year(start_year)
        return {"from_ad": earlier["start_ad"], "to_ad": earlier["end_ad"],
                "label": earlier["label"]}
    except nd.DateRangeError:
        return None


def _balances(conn, at_ad):
    return reports.balances_as_at(conn, at_ad)


def _account_index(conn):
    index = {}
    for account in reports._account_rows(conn):
        index[account["id"]] = account
    return index


# Statement of financial position


def position(conn, as_at_ad, fy_start_ad, compare_as_at=None, compare_start=None):
    """
    Statement of Financial Position in the vertical form NAS 01 sets out:
    non current assets, current assets, equity, non current liabilities,
    current liabilities, with a note number against every line.
    """
    current = _side_totals(conn, as_at_ad, fy_start_ad)
    prior = _side_totals(conn, compare_as_at, compare_start) if compare_as_at else None

    def block(title, group_codes, source):
        lines = []
        total = 0
        for code in group_codes:
            amount = source["groups"].get(code, {}).get("total", 0)
            if amount == 0 and (prior is None
                                or prior["groups"].get(code, {}).get("total", 0) == 0):
                continue
            lines.append({
                "code": code,
                "name": source["groups"].get(code, {}).get("name")
                        or (prior and prior["groups"].get(code, {}).get("name")) or code,
                "name_np": source["groups"].get(code, {}).get("name_np", ""),
                "group_id": source["groups"].get(code, {}).get("group_id"),
                "amount": amount,
                "previous": prior["groups"].get(code, {}).get("total", 0) if prior else None,
            })
            total += amount
        previous_total = sum(
            prior["groups"].get(code, {}).get("total", 0) for code in group_codes) if prior else None
        return {"title": title, "lines": lines, "total": total, "previous": previous_total}

    non_current_assets = ["1110", "1130", "1140", "1180", "1190", "1150", "1160", "1170"]
    current_assets = ["1210", "1220", "1230", "1240", "1250", "1260", "1270", "1280"]
    equity_groups = ["3100", "3200", "3300"]
    non_current_liabilities = ["2110", "2120", "2130", "2140"]
    current_liabilities = ["2210", "2220", "2230", "2240", "2250", "2260",
                           "2270", "2280", "2290"]

    sections = {
        "non_current_assets": block("Non current assets", non_current_assets, current),
        "current_assets": block("Current assets", current_assets, current),
        "equity": block("Equity", equity_groups, current),
        "non_current_liabilities": block("Non current liabilities", non_current_liabilities, current),
        "current_liabilities": block("Current liabilities", current_liabilities, current),
    }

    # Profit for the period belongs inside equity and is what makes the
    # statement balance without a closing entry having to be passed first.
    profit = reports.profit_and_loss(conn, fy_start_ad, as_at_ad)["profit_after_tax"]
    previous_profit = None
    if compare_as_at:
        previous_profit = reports.profit_and_loss(
            conn, compare_start, compare_as_at)["profit_after_tax"]
    sections["equity"]["lines"].append({
        "code": "PL", "name": "Profit or loss for the period",
        "name_np": "अवधिको नाफा नोक्सान", "group_id": None,
        "amount": profit, "previous": previous_profit,
    })
    sections["equity"]["total"] += profit
    if sections["equity"]["previous"] is not None and previous_profit is not None:
        sections["equity"]["previous"] += previous_profit

    total_assets = sections["non_current_assets"]["total"] + sections["current_assets"]["total"]
    total_equity = sections["equity"]["total"]
    total_liabilities = (sections["non_current_liabilities"]["total"]
                         + sections["current_liabilities"]["total"])

    previous_assets = previous_equity = previous_liabilities = None
    if prior:
        previous_assets = ((sections["non_current_assets"]["previous"] or 0)
                           + (sections["current_assets"]["previous"] or 0))
        previous_equity = sections["equity"]["previous"] or 0
        previous_liabilities = ((sections["non_current_liabilities"]["previous"] or 0)
                                + (sections["current_liabilities"]["previous"] or 0))

    return {
        "as_at_ad": as_at_ad,
        "as_at_bs": nd.format_bs(nd.ad_to_bs(as_at_ad), "long"),
        "sections": sections,
        "total_assets": total_assets,
        "total_equity": total_equity,
        "total_liabilities": total_liabilities,
        "total_equity_and_liabilities": total_equity + total_liabilities,
        "difference": total_assets - (total_equity + total_liabilities),
        "balanced": total_assets == total_equity + total_liabilities,
        "previous": {
            "as_at_ad": compare_as_at,
            "total_assets": previous_assets,
            "total_equity": previous_equity,
            "total_liabilities": previous_liabilities,
            "total_equity_and_liabilities": (previous_equity + previous_liabilities)
                                            if prior else None,
        } if prior else None,
    }


def _side_totals(conn, as_at_ad, fy_start_ad):
    """Balance sheet groups with their totals, presented as positive figures."""
    balances = _balances(conn, as_at_ad)
    groups = {}
    for account in reports._account_rows(conn):
        if account["statement"] != "BS":
            continue
        balance = balances.get(account["id"], 0)
        amount = -balance if account["nature"] in reports.CREDIT_NATURES else balance
        bucket = groups.setdefault(account["group_code"], {
            "group_id": account["group_id"], "name": account["group_name"],
            "name_np": account["group_name_np"], "total": 0, "lines": []})
        if balance != 0:
            bucket["lines"].append({
                "account_id": account["id"], "code": account["code"],
                "name": account["name"], "name_np": account["name_np"], "amount": amount})
        bucket["total"] += amount
    return {"groups": groups, "as_at_ad": as_at_ad}


# Statement of profit or loss


def profit_or_loss(conn, from_ad, to_ad, compare=None):
    """
    Statement of Profit or Loss by nature of expense, which is the form NAS 01
    permits and the one a trading house in Nepal is normally presented in.
    """
    current = reports.profit_and_loss(conn, from_ad, to_ad)
    prior = reports.profit_and_loss(conn, compare["from_ad"], compare["to_ad"]) if compare else None

    def line(label, key, note=None, negate=False):
        amount = current.get(key, 0)
        previous = prior.get(key, 0) if prior else None
        if negate:
            amount = -amount
            previous = -previous if previous is not None else None
        return {"label": label, "key": key, "amount": amount,
                "previous": previous, "note": note}

    rows = [
        line("Revenue from operations", "revenue", "1"),
        line("Cost of sales", "cost_of_sales", "2", negate=True),
        {"label": "Gross profit", "key": "gross_profit", "total": True,
         "amount": current["gross_profit"],
         "previous": prior["gross_profit"] if prior else None},
        line("Other income", "other_income", "3"),
        line("Employee benefit expenses", "employee", "4", negate=True),
        line("Administrative expenses", "administrative", "5", negate=True),
        line("Selling and distribution expenses", "selling", "6", negate=True),
        {"label": "Operating profit", "key": "operating_profit", "total": True,
         "amount": current["operating_profit"],
         "previous": prior["operating_profit"] if prior else None},
        line("Finance costs", "finance", "7", negate=True),
        line("Depreciation and amortisation", "depreciation", "8", negate=True),
        line("Other expenses", "other_expense", "9", negate=True),
        {"label": "Profit before tax", "key": "profit_before_tax", "total": True,
         "amount": current["profit_before_tax"],
         "previous": prior["profit_before_tax"] if prior else None},
        line("Income tax expense", "tax", "10", negate=True),
        {"label": "Profit for the period", "key": "profit_after_tax", "total": True,
         "strong": True, "amount": current["profit_after_tax"],
         "previous": prior["profit_after_tax"] if prior else None},
        line("Other comprehensive income", "other_comprehensive_income", "11"),
        {"label": "Total comprehensive income for the period",
         "key": "total_comprehensive_income", "total": True, "strong": True,
         "amount": current["total_comprehensive_income"],
         "previous": prior["total_comprehensive_income"] if prior else None},
    ]

    return {
        "from_ad": from_ad, "to_ad": to_ad,
        "period_bs": "%s to %s" % (nd.format_bs(nd.ad_to_bs(from_ad), "long"),
                                   nd.format_bs(nd.ad_to_bs(to_ad), "long")),
        "rows": [row for row in rows if row.get("total") or row["amount"] != 0
                 or (row.get("previous") or 0) != 0],
        "detail": current,
        "previous_detail": prior,
        "compare": compare,
    }


def trading_account(conn, from_ad, to_ad):
    """
    The traditional Trading Account, opening stock through to gross profit.

    Many proprietors and auditors in Nepal still read this form first, so it is
    offered alongside the standard presentation. The figures are the same ones.
    """
    period = reports.account_movements(conn, from_ad=from_ad, upto_ad=to_ad)
    debit, credit = [], []
    for account in reports._account_rows(conn):
        if account["section"] != "cost_of_sales" and account["section"] != "revenue":
            continue
        dr, cr = period.get(account["id"], (0, 0))
        movement = dr - cr
        if movement == 0:
            continue
        entry = {"account_id": account["id"], "code": account["code"],
                 "name": account["name"], "name_np": account["name_np"],
                 "amount": abs(movement)}
        if account["nature"] == "expense":
            (debit if movement > 0 else credit).append(entry)
        else:
            (credit if movement < 0 else debit).append(entry)

    total_debit = sum(e["amount"] for e in debit)
    total_credit = sum(e["amount"] for e in credit)
    gross = total_credit - total_debit
    return {
        "from_ad": from_ad, "to_ad": to_ad,
        "debit": debit, "credit": credit,
        "total_debit": total_debit, "total_credit": total_credit,
        "gross_profit": gross,
    }


# Statement of changes in equity


def changes_in_equity(conn, from_ad, to_ad, compare=None):
    """
    How equity moved over the period, ledger by ledger.

    Opening balance, what the owner put in or took out, the profit for the
    period, and the closing balance. NAS 01 asks for this as a statement in its
    own right rather than a note.
    """
    opening_balances = _balances(conn, reports._day_before(from_ad))
    closing_balances = _balances(conn, to_ad)
    period = reports.account_movements(conn, from_ad=from_ad, upto_ad=to_ad)

    rows = []
    for account in reports._account_rows(conn):
        if account["section"] != "equity":
            continue
        opening = -opening_balances.get(account["id"], 0)
        closing = -closing_balances.get(account["id"], 0)
        dr, cr = period.get(account["id"], (0, 0))
        if opening == 0 and closing == 0 and dr == 0 and cr == 0:
            continue
        rows.append({
            "account_id": account["id"], "code": account["code"],
            "name": account["name"], "name_np": account["name_np"],
            "group_name": account["group_name"],
            "opening": opening,
            "introduced": cr,
            "withdrawn": dr,
            "closing": closing,
        })

    result_pl = reports.profit_and_loss(conn, from_ad, to_ad)
    profit = result_pl["profit_after_tax"]
    other_comprehensive = result_pl["other_comprehensive_income"]
    totals = {
        "opening": sum(r["opening"] for r in rows),
        "introduced": sum(r["introduced"] for r in rows),
        "withdrawn": sum(r["withdrawn"] for r in rows),
        "closing": sum(r["closing"] for r in rows),
    }
    out = {
        "from_ad": from_ad, "to_ad": to_ad,
        "rows": rows,
        "profit": profit,
        "other_comprehensive": other_comprehensive,
        "totals": totals,
        "closing_with_profit": totals["closing"] + profit + other_comprehensive,
        "previous": None,
    }

    if compare:
        earlier = changes_in_equity(conn, compare["from_ad"], compare["to_ad"])
        out["previous"] = earlier
        by_account = {row["account_id"]: row for row in earlier["rows"]}
        for row in out["rows"]:
            old_row = by_account.get(row["account_id"])
            row["previous_opening"] = old_row["opening"] if old_row else 0
            row["previous_closing"] = old_row["closing"] if old_row else 0
        seen = {row["account_id"] for row in out["rows"]}
        for old_row in earlier["rows"]:
            if old_row["account_id"] in seen:
                continue
            out["rows"].append(dict(old_row, opening=0, introduced=0, withdrawn=0, closing=0,
                                    previous_opening=old_row["opening"],
                                    previous_closing=old_row["closing"]))
    return out


# Statement of cash flows


def cash_flows(conn, from_ad, to_ad, compare=None):
    """
    Statement of Cash Flows by the indirect method, as NAS 07 permits.

    Profit before tax is adjusted for what did not move cash, then for what the
    working capital tied up or released, and the result is compared against the
    movement the cash and bank ledgers actually show. The two are reported side
    by side so a difference can never hide.
    """
    start_before = reports._day_before(from_ad)
    opening = _balances(conn, start_before)
    closing = _balances(conn, to_ad)
    accounts = _account_index(conn)

    buckets = {"operating": [], "investing": [], "financing": [], "non_cash": []}
    cash_opening = cash_closing = 0

    for account_id, account in accounts.items():
        if account["statement"] != "BS":
            continue
        before = opening.get(account_id, 0)
        after = closing.get(account_id, 0)
        movement = after - before
        section = _classify(account)
        if section == "cash":
            cash_opening += before
            cash_closing += after
            continue
        if movement == 0:
            continue
        # An asset going up uses cash. A liability going up releases it.
        effect = -movement
        # Balances are held debit positive, so a liability or a capital account
        # grows as its balance falls. The statement has to say increase or
        # decrease the way a reader means it, not the way the sign runs.
        grew = movement > 0 if account["nature"] == "asset" else movement < 0
        buckets[section].append({
            "account_id": account_id, "code": account["code"], "name": account["name"],
            "group_name": account["group_name"], "nature": account["nature"],
            "movement": movement, "effect": effect, "increased": grew,
        })

    pl = reports.profit_and_loss(conn, from_ad, to_ad)
    depreciation = pl["depreciation"]
    finance_cost = pl["finance"]
    tax = pl["tax"]

    operating_effect = sum(item["effect"] for item in buckets["operating"])
    investing = sum(item["effect"] for item in buckets["investing"])
    financing = sum(item["effect"] for item in buckets["financing"])

    # Profit is already inside the movement of the equity balances only once the
    # year is closed, so it is brought in here explicitly instead.
    profit_before_tax = pl["profit_before_tax"]

    operating = (profit_before_tax + depreciation + finance_cost
                 + operating_effect - tax)
    investing_total = investing
    financing_total = financing - finance_cost

    net = operating + investing_total + financing_total
    actual = cash_closing - cash_opening
    unexplained = actual - net

    result = {
        "from_ad": from_ad, "to_ad": to_ad,
        "profit_before_tax": profit_before_tax,
        "depreciation": depreciation,
        "finance_cost": finance_cost,
        "tax_paid": tax,
        "working_capital": buckets["operating"],
        "working_capital_total": operating_effect,
        "operating": operating,
        "investing_items": buckets["investing"],
        "investing": investing_total,
        "financing_items": buckets["financing"],
        "financing": financing_total,
        "net_change": net,
        "cash_opening": cash_opening,
        "cash_closing": cash_closing,
        "actual_change": actual,
        "unexplained": unexplained,
        "ties": unexplained == 0,
        "previous": None,
    }

    if compare:
        # The same statement one year earlier, so every line has last year
        # beside it as NAS 01 requires of a complete set.
        earlier = cash_flows(conn, compare["from_ad"], compare["to_ad"])
        result["previous"] = earlier
        by_account = {}
        for section in ("working_capital", "investing_items", "financing_items"):
            for item in earlier[section]:
                by_account[item["account_id"]] = item["effect"]
        for section in ("working_capital", "investing_items", "financing_items"):
            for item in result[section]:
                item["previous"] = by_account.get(item["account_id"], 0)
        # An account that moved last year but not this year still belongs on the
        # statement, otherwise the comparative column has a hole in it.
        seen = {item["account_id"] for section in
                ("working_capital", "investing_items", "financing_items")
                for item in result[section]}
        for section in ("working_capital", "investing_items", "financing_items"):
            for item in earlier[section]:
                if item["account_id"] in seen:
                    continue
                result[section].append(dict(item, movement=0, effect=0,
                                            increased=item.get("increased", False),
                                            previous=item["effect"]))
                seen.add(item["account_id"])
    return result


# Notes and schedules


def schedules(conn, from_ad, to_ad, compare=None):
    """
    A schedule behind every group on the face of the statements, with last year
    beside it. This is what turns a one page balance sheet into something an
    auditor can actually check.
    """
    current = _side_totals(conn, to_ad, from_ad)
    prior = _side_totals(conn, compare["to_ad"], compare["from_ad"]) if compare else None
    period = reports.profit_and_loss(conn, from_ad, to_ad)
    prior_period = reports.profit_and_loss(
        conn, compare["from_ad"], compare["to_ad"]) if compare else None

    notes = []
    number = 0

    def prior_line(code, account_id):
        if not prior:
            return None
        bucket = prior["groups"].get(code)
        if not bucket:
            return 0
        for line in bucket["lines"]:
            if line["account_id"] == account_id:
                return line["amount"]
        return 0

    for code in sorted(current["groups"]):
        bucket = current["groups"][code]
        if not bucket["lines"] and not (prior and prior["groups"].get(code, {}).get("lines")):
            continue
        number += 1
        lines = [{
            "account_id": line["account_id"], "code": line["code"], "name": line["name"],
            "name_np": line["name_np"], "amount": line["amount"],
            "previous": prior_line(code, line["account_id"]),
        } for line in bucket["lines"]]
        notes.append({
            "number": number, "group_code": code, "group_id": bucket["group_id"],
            "title": bucket["name"], "title_np": bucket["name_np"],
            "statement": "BS", "lines": lines,
            "total": bucket["total"],
            "previous_total": prior["groups"].get(code, {}).get("total", 0) if prior else None,
        })

    for section_key, section in sorted(period["sections"].items()):
        for group_code in sorted(section["groups"]):
            group = section["groups"][group_code]
            number += 1
            prior_group = None
            if prior_period:
                prior_section = prior_period["sections"].get(section_key, {})
                prior_group = prior_section.get("groups", {}).get(group_code)
            lines = []
            for line in sorted(group["lines"], key=lambda x: x["code"]):
                previous = 0
                if prior_group:
                    for old in prior_group["lines"]:
                        if old["account_id"] == line["account_id"]:
                            previous = old["amount"]
                            break
                lines.append({
                    "account_id": line["account_id"], "code": line["code"],
                    "name": line["name"], "name_np": line["name_np"],
                    "amount": line["amount"], "previous": previous if prior_period else None,
                })
            notes.append({
                "number": number, "group_code": group_code, "group_id": None,
                "title": group["name"], "title_np": group.get("name_np", ""),
                "statement": "PL", "lines": lines, "total": group["total"],
                "previous_total": prior_group["total"] if prior_group else None,
            })

    return {"notes": notes, "from_ad": from_ad, "to_ad": to_ad, "compare": compare}


def full_set(conn, from_ad, to_ad, compare=True):
    """Everything an audit file needs, in one call."""
    earlier = previous_period(from_ad, to_ad) if compare else None
    return {
        "from_ad": from_ad, "to_ad": to_ad,
        "period_label": "%s to %s" % (nd.format_bs(nd.ad_to_bs(from_ad), "long"),
                                      nd.format_bs(nd.ad_to_bs(to_ad), "long")),
        "compare": earlier,
        "position": position(conn, to_ad, from_ad,
                             earlier["to_ad"] if earlier else None,
                             earlier["from_ad"] if earlier else None),
        "profit_or_loss": profit_or_loss(conn, from_ad, to_ad, earlier),
        "trading": trading_account(conn, from_ad, to_ad),
        "equity": changes_in_equity(conn, from_ad, to_ad, earlier),
        "cash_flows": cash_flows(conn, from_ad, to_ad, earlier),
        "schedules": schedules(conn, from_ad, to_ad, earlier),
    }

"""
Analytical review, the way it is done on a job.

This is not a substitute for an audit. It is the first pass an assistant makes
before the partner looks at anything: run through the books, list what does not
look right, and put a reference against each one so it can be followed up
rather than argued about.

Every finding carries where it came from, how much it is worth, and what rule
or standard it touches. Nothing here changes a figure.
"""

import datetime

from ..core import money, nepali_date as nd
from . import masters, reports

HIGH, MEDIUM, LOW, INFO = "high", "medium", "low", "info"

# Thresholds that come from the law. They move with each Finance Act, so they
# are gathered here in one place rather than buried in the checks.
CASH_PAYMENT_LIMIT = money.to_paisa("50000")      # section 21, Income Tax Act, 2058
CONTRACT_TDS_THRESHOLD = money.to_paisa("50000")  # section 89
DONATION_CEILING = money.to_paisa("100000")       # section 12
ROUND_SUM_MINIMUM = money.to_paisa("10000")


class Finding(dict):
    pass


def _finding(severity, area, title, detail, reference="", amount=0, count=0, items=None):
    return Finding(severity=severity, area=area, title=title, detail=detail,
                   reference=reference, amount=amount, count=count, items=items or [])


def review(conn, from_ad, to_ad, compare=None):
    """Run every check over one period and return what came back."""
    findings = []
    context = {
        "from_ad": from_ad, "to_ad": to_ad,
        "balances": reports.balances_as_at(conn, to_ad),
        "period": reports.account_movements(conn, from_ad=from_ad, upto_ad=to_ad),
        "accounts": {a["id"]: a for a in reports._account_rows(conn)},
        "profit": reports.profit_and_loss(conn, from_ad, to_ad),
        "company": conn.execute("SELECT * FROM company WHERE id = 1").fetchone(),
    }
    if compare:
        context["previous_profit"] = reports.profit_and_loss(
            conn, compare["from_ad"], compare["to_ad"])

    for check in (_check_integrity, _check_classification, _check_completeness,
                  _check_tax, _check_parties, _check_stock,
                  _check_behaviour, _check_analytics):
        try:
            findings.extend(check(conn, context) or [])
        except Exception as exc:
            findings.append(_finding(INFO, "Review", "A check could not be run",
                                     "%s: %s" % (check.__name__, exc)))

    order = {HIGH: 0, MEDIUM: 1, LOW: 2, INFO: 3}
    findings.sort(key=lambda f: (order.get(f["severity"], 9), -abs(f["amount"])))
    counts = {level: sum(1 for f in findings if f["severity"] == level)
              for level in (HIGH, MEDIUM, LOW, INFO)}
    return {
        "from_ad": from_ad, "to_ad": to_ad,
        "findings": findings, "counts": counts, "total": len(findings),
        "ratios": _ratios(conn, context),
        "clean": counts[HIGH] == 0 and counts[MEDIUM] == 0,
    }


# Does it hold together at all


def _check_integrity(conn, ctx):
    out = []
    trial = reports.trial_balance(conn, ctx["from_ad"], ctx["to_ad"])
    if not trial["balanced"]:
        difference = trial["totals"]["closing_dr"] - trial["totals"]["closing_cr"]
        out.append(_finding(HIGH, "Integrity", "The trial balance does not tie",
                            "Debit and credit differ by %s. Nothing else in this review can be "
                            "relied on until that is found." % money.format_money(abs(difference)),
                            "NAS 01", abs(difference)))

    sheet = reports.balance_sheet(conn, ctx["to_ad"], ctx["from_ad"])
    if not sheet["balanced"]:
        out.append(_finding(HIGH, "Integrity", "The balance sheet does not balance",
                            "Assets differ from equity and liabilities by %s."
                            % money.format_money(abs(sheet["difference"])),
                            "NAS 01", abs(sheet["difference"])))

    suspense = masters.account_by_code(conn, "1281")
    if suspense:
        balance = ctx["balances"].get(suspense["id"], 0)
        if balance:
            out.append(_finding(HIGH, "Integrity", "The suspense account still has a balance",
                                "%s is sitting in suspense. Nothing should be left there when "
                                "the books are closed, because by definition nobody knows what "
                                "it is." % money.format_money(abs(balance)),
                                "", abs(balance)))

    for account in ctx["accounts"].values():
        if account["account_kind"] != "cash":
            continue
        balance = ctx["balances"].get(account["id"], 0)
        if balance < 0:
            out.append(_finding(HIGH, "Integrity", "Cash has gone below zero",
                                "%s shows a credit balance of %s. A cash box cannot hold less "
                                "than nothing, so either a receipt is missing or a payment has "
                                "been entered twice."
                                % (account["name"], money.format_money(-balance)),
                                "", -balance))
    return out


# Is anything sitting on the wrong side


def _check_classification(conn, ctx):
    out = []
    wrong_side = []
    for account in ctx["accounts"].values():
        balance = ctx["balances"].get(account["id"], 0)
        if balance == 0:
            continue
        nature = account["nature"]
        kind = account["account_kind"]
        if kind in ("contra_asset", "contra_income", "contra_expense"):
            continue
        if nature == "asset" and balance < 0:
            wrong_side.append((account, -balance, "asset with a credit balance"))
        elif nature in ("liability", "equity") and balance > 0:
            wrong_side.append((account, balance, "liability or equity with a debit balance"))

    if wrong_side:
        out.append(_finding(
            MEDIUM, "Classification", "Ledgers sitting on the wrong side",
            "%d ledger%s carry a balance on the side they should not. Some are genuine, an "
            "advance from a customer landing in debtors for instance, but each one needs "
            "either reclassifying or explaining."
            % (len(wrong_side), "" if len(wrong_side) == 1 else "s"),
            "NAS 01", sum(amount for _a, amount, _r in wrong_side), len(wrong_side),
            [{"account_id": a["id"], "code": a["code"], "name": a["name"],
              "amount": amount, "note": reason} for a, amount, reason in wrong_side]))
    return out


# Has everything been done that should have been


def _check_completeness(conn, ctx):
    out = []

    # Gaps in a numbered series are the first thing a tax officer looks for.
    for row in conn.execute(
            """SELECT voucher_type, COUNT(*) AS n FROM vouchers
               WHERE date_ad >= ? AND date_ad <= ? GROUP BY voucher_type""",
            (ctx["from_ad"], ctx["to_ad"])):
        numbers = [r["number"] for r in conn.execute(
            """SELECT number FROM vouchers WHERE voucher_type = ?
               AND date_ad >= ? AND date_ad <= ? ORDER BY number""",
            (row["voucher_type"], ctx["from_ad"], ctx["to_ad"]))]
        digits = []
        prefix = None
        for number in numbers:
            tail = "".join(ch for ch in number if ch.isdigit())
            head = "".join(ch for ch in number if not ch.isdigit())
            if not tail:
                continue
            if prefix is None:
                prefix = head
            if head != prefix:
                continue
            digits.append(int(tail))
        if len(digits) < 3:
            continue
        digits.sort()
        missing = [n for n in range(digits[0], digits[-1] + 1) if n not in set(digits)]
        if missing:
            out.append(_finding(
                MEDIUM, "Completeness", "Gaps in the %s numbering" % row["voucher_type"],
                "%d number%s missing between %s%d and %s%d. A gap in an invoice series has to "
                "be explainable, so find the cancelled or spoiled documents."
                % (len(missing), "" if len(missing) == 1 else "s",
                   prefix or "", digits[0], prefix or "", digits[-1]),
                "Value Added Tax Rules, 2053", 0, len(missing),
                [{"note": "%s%d" % (prefix or "", n)} for n in missing[:40]]))

    cancelled = conn.execute(
        """SELECT COUNT(*) AS n FROM vouchers WHERE status = 'cancelled'
           AND date_ad >= ? AND date_ad <= ?""", (ctx["from_ad"], ctx["to_ad"])).fetchone()["n"]
    posted = conn.execute(
        """SELECT COUNT(*) AS n FROM vouchers WHERE status = 'posted'
           AND date_ad >= ? AND date_ad <= ?""", (ctx["from_ad"], ctx["to_ad"])).fetchone()["n"]
    if posted and cancelled and cancelled * 100 > posted * 5:
        out.append(_finding(
            MEDIUM, "Completeness", "A lot of vouchers have been cancelled",
            "%d cancelled against %d posted. Read the reasons given. A pattern of cancellations "
            "around a particular customer or period is worth understanding."
            % (cancelled, posted), "", 0, cancelled))

    if ctx["profit"]["depreciation"] == 0:
        assets = conn.execute("SELECT COUNT(*) AS n FROM fixed_assets WHERE active = 1"
                              ).fetchone()["n"]
        owns = any(ctx["balances"].get(a["id"], 0) > 0
                   for a in ctx["accounts"].values() if a["account_kind"] == "fixed_asset")
        if assets or owns:
            out.append(_finding(
                HIGH, "Completeness", "No depreciation has been charged",
                "The business owns fixed assets but nothing has been written off them this "
                "period. Both the profit and the carrying amount are overstated.",
                "NAS 16"))

    company = ctx["company"]
    if company and company["has_goods"]:
        stock_account = masters.account_by_code(conn, "1211")
        if stock_account:
            booked = ctx["balances"].get(stock_account["id"], 0)
            counted = reports.stock_summary(conn, ctx["to_ad"])["total_value"]
            if abs(counted - booked) > money.to_paisa("1"):
                out.append(_finding(
                    HIGH, "Completeness", "Closing stock is not in the accounts",
                    "The stock records show %s but the ledger carries %s. Until the closing "
                    "stock entry is passed, cost of sales and the profit are both wrong by "
                    "%s." % (money.format_money(counted), money.format_money(booked),
                             money.format_money(abs(counted - booked))),
                    "NAS 02", abs(counted - booked)))
    return out


# Tax


def _check_tax(conn, ctx):
    out = []
    company = ctx["company"]

    if company and company["vat_registered"]:
        rate = company["vat_rate_bp"] or 1300
        sales = conn.execute(
            """SELECT COALESCE(SUM(taxable_paisa), 0) AS taxable,
                      COALESCE(SUM(vat_paisa), 0) AS vat
               FROM vouchers WHERE status = 'posted' AND voucher_type = 'sales'
                 AND date_ad >= ? AND date_ad <= ?""",
            (ctx["from_ad"], ctx["to_ad"])).fetchone()
        if sales["taxable"]:
            expected = money.apply_rate(sales["taxable"], rate)
            gap = sales["vat"] - expected
            if abs(gap) > money.to_paisa("10"):
                out.append(_finding(
                    HIGH, "Value added tax", "Output tax does not agree with taxable sales",
                    "Taxable sales of %s should carry tax of %s, but %s has been charged, a "
                    "difference of %s."
                    % (money.format_money(sales["taxable"]), money.format_money(expected),
                       money.format_money(sales["vat"]), money.format_money(abs(gap))),
                    "Value Added Tax Act, 2052", abs(gap)))

        no_pan = conn.execute(
            """SELECT COUNT(*) AS n, COALESCE(SUM(v.total_paisa), 0) AS amount
               FROM vouchers v LEFT JOIN parties p ON p.id = v.party_id
               WHERE v.status = 'posted' AND v.voucher_type = 'sales'
                 AND v.is_vat_invoice = 1 AND v.date_ad >= ? AND v.date_ad <= ?
                 AND (p.pan IS NULL OR p.pan = '')""",
            (ctx["from_ad"], ctx["to_ad"])).fetchone()
        if no_pan["n"]:
            out.append(_finding(
                MEDIUM, "Value added tax", "Tax invoices raised without the buyer's PAN",
                "%d tax invoice%s totalling %s carry no PAN for the buyer. A tax invoice to a "
                "registered person has to show it."
                % (no_pan["n"], "" if no_pan["n"] == 1 else "s",
                   money.format_money(no_pan["amount"])),
                "Value Added Tax Rules, 2053", no_pan["amount"], no_pan["n"]))

    # Expenses that need tax deducted at source.
    for code, label, rate_note in (("6201", "Office Rent", "10 percent under section 88"),
                                   ("6215", "Legal and Professional Fee",
                                    "15 percent under section 88"),
                                   ("6216", "Audit Fee", "15 percent under section 88"),
                                   ("6217", "Consultancy Fee", "15 percent under section 88"),
                                   ("6303", "Commission on Sales",
                                    "15 percent under section 88")):
        account = masters.account_by_code(conn, code)
        if account is None:
            continue
        debit, _credit = ctx["period"].get(account["id"], (0, 0))
        if debit <= 0:
            continue
        deducted = conn.execute(
            """SELECT COALESCE(SUM(e.cr_paisa), 0) AS amount
               FROM voucher_entries e
               JOIN vouchers v ON v.id = e.voucher_id
               JOIN accounts a ON a.id = e.account_id
               JOIN account_groups g ON g.id = a.group_id
               WHERE g.code = '2250' AND v.status = 'posted'
                 AND v.date_ad >= ? AND v.date_ad <= ?
                 AND EXISTS (SELECT 1 FROM voucher_entries e2
                             WHERE e2.voucher_id = v.id AND e2.account_id = ?)""",
            (ctx["from_ad"], ctx["to_ad"], account["id"])).fetchone()["amount"]
        if deducted == 0:
            out.append(_finding(
                HIGH, "Tax deducted at source", "No tax deducted on %s" % account["name"],
                "%s has gone through %s this period with nothing deducted at source. The rate "
                "is %s. An expense on which tax should have been withheld and was not is "
                "disallowed."
                % (money.format_money(debit), account["name"], rate_note),
                "Income Tax Act, 2058, sections 88 and 21", debit))

    # Expenses the Act does not allow at all.
    penalty = masters.account_by_code(conn, "7303")
    if penalty:
        debit, _c = ctx["period"].get(penalty["id"], (0, 0))
        if debit:
            out.append(_finding(
                MEDIUM, "Income tax", "Penalties and fines have been charged",
                "%s of penalty, fine or interest on tax. None of it is deductible, so it has "
                "to be added back when the return is prepared." % money.format_money(debit),
                "Income Tax Act, 2058, section 21", debit))

    donation = masters.account_by_code(conn, "6226")
    if donation:
        debit, _c = ctx["period"].get(donation["id"], (0, 0))
        if debit > DONATION_CEILING:
            out.append(_finding(
                MEDIUM, "Income tax", "Donations above the ceiling",
                "%s given away. The deduction is capped at the lower of five percent of "
                "adjusted taxable income or one hundred thousand rupees, so the excess is "
                "added back." % money.format_money(debit),
                "Income Tax Act, 2058, section 12", debit))

    # Cash payments over the limit are disallowed.
    cash_accounts = [a["id"] for a in ctx["accounts"].values() if a["account_kind"] == "cash"]
    if cash_accounts:
        marks = ", ".join("?" for _ in cash_accounts)
        big = conn.execute(
            """SELECT v.id, v.number, v.date_bs, v.narration, e.cr_paisa AS amount,
                      p.name AS party_name
               FROM voucher_entries e JOIN vouchers v ON v.id = e.voucher_id
               LEFT JOIN parties p ON p.id = v.party_id
               WHERE e.account_id IN (%s) AND e.cr_paisa > ?
                 AND v.status = 'posted' AND v.date_ad >= ? AND v.date_ad <= ?
               ORDER BY e.cr_paisa DESC LIMIT 60""" % marks,
            cash_accounts + [CASH_PAYMENT_LIMIT, ctx["from_ad"], ctx["to_ad"]]).fetchall()
        if big:
            total = sum(row["amount"] for row in big)
            out.append(_finding(
                HIGH, "Income tax", "Cash payments above fifty thousand rupees",
                "%d payment%s totalling %s went out in cash above the limit. Expenditure paid "
                "in cash over fifty thousand rupees to one person in one transaction is not "
                "allowed as a deduction, apart from the exceptions the Act lists."
                % (len(big), "" if len(big) == 1 else "s", money.format_money(total)),
                "Income Tax Act, 2058, section 21", total, len(big),
                [{"voucher_id": r["id"], "note": "%s  %s  %s"
                  % (r["number"], r["date_bs"], r["party_name"] or r["narration"] or ""),
                  "amount": r["amount"]} for r in big[:25]]))
    return out


# Customers and suppliers


def _check_parties(conn, ctx):
    out = []
    for side, label in (("receivable", "customer"), ("payable", "supplier")):
        ageing = reports.ageing(conn, side, ctx["to_ad"])
        overdue = [r for r in ageing["rows"] if sum(r["buckets"][2:]) > 0]
        if overdue and side == "receivable":
            amount = sum(sum(r["buckets"][2:]) for r in overdue)
            out.append(_finding(
                MEDIUM, "Receivables", "Money owed for more than sixty days",
                "%s is owed by %d customer%s beyond sixty days. Consider whether it is still "
                "collectable, and whether a provision is needed."
                % (money.format_money(amount), len(overdue), "" if len(overdue) == 1 else "s"),
                "NFRS 9", amount, len(overdue),
                [{"account_id": r["account_id"], "code": r["code"], "name": r["name"],
                  "amount": sum(r["buckets"][2:])} for r in overdue[:25]]))

        over_limit = [r for r in ageing["rows"]
                      if r["credit_limit"] and r["total"] > r["credit_limit"]]
        if over_limit and side == "receivable":
            out.append(_finding(
                LOW, "Receivables", "Customers over their credit limit",
                "%d customer%s owe more than the limit set for them."
                % (len(over_limit), "" if len(over_limit) == 1 else "s"),
                "", sum(r["total"] for r in over_limit), len(over_limit),
                [{"account_id": r["account_id"], "name": r["name"], "amount": r["total"],
                  "note": "limit " + money.format_money(r["credit_limit"])}
                 for r in over_limit[:25]]))

    no_pan = conn.execute(
        """SELECT COUNT(*) AS n FROM parties
           WHERE active = 1 AND (pan IS NULL OR pan = '') AND party_type IN ('supplier','both')"""
    ).fetchone()["n"]
    if no_pan:
        out.append(_finding(
            LOW, "Suppliers", "Suppliers with no PAN recorded",
            "%d supplier%s have no PAN on file. Buying from an unregistered person limits what "
            "can be claimed and what can be deducted."
            % (no_pan, "" if no_pan == 1 else "s"), "Income Tax Act, 2058", 0, no_pan))
    return out


# Stock


def _check_stock(conn, ctx):
    out = []
    company = ctx["company"]
    if not company or not company["has_goods"]:
        return out

    summary = reports.stock_summary(conn, ctx["to_ad"])
    negative = [r for r in summary["rows"] if r["qty"] < 0]
    if negative:
        out.append(_finding(
            HIGH, "Stock", "Stock has gone below zero",
            "%d item%s show a negative quantity. Something has been sold that was never "
            "recorded as bought, so either a purchase is missing or a sale is wrong."
            % (len(negative), "" if len(negative) == 1 else "s"),
            "NAS 02", 0, len(negative),
            [{"item_id": r["item_id"], "name": r["name"],
              "note": money.format_qty(r["qty"])} for r in negative[:25]]))

    ageing = reports.stock_ageing(conn, ctx["to_ad"])
    if ageing["old_value"]:
        out.append(_finding(
            MEDIUM, "Stock", "Stock that has been sitting a long time",
            "%s of stock has been on the shelf more than a hundred and eighty days. Stock is "
            "carried at the lower of cost and net realisable value, so consider whether it is "
            "still worth what it cost." % money.format_money(ageing["old_value"]),
            "NAS 02", ageing["old_value"], 0,
            [{"item_id": r["item_id"], "name": r["name"], "amount": r["bucket_value"][-1]}
             for r in ageing["rows"] if r["bucket_value"][-1]][:25]))

    never = [r for r in ageing["rows"] if r["never_sold"]]
    if never:
        out.append(_finding(
            LOW, "Stock", "Items bought but never sold",
            "%d item%s have stock on hand and no sale against them at all."
            % (len(never), "" if len(never) == 1 else "s"), "NAS 02",
            sum(r["value"] for r in never), len(never),
            [{"item_id": r["item_id"], "name": r["name"], "amount": r["value"]}
             for r in never[:25]]))

    below_cost = []
    for item in conn.execute("""SELECT id, name, sale_rate_paisa FROM items
                                WHERE active = 1 AND maintain_stock = 1"""):
        if not item["sale_rate_paisa"]:
            continue
        state = reports.item_stock(conn, item["id"], ctx["to_ad"])
        if state["qty"] > 0 and state["average_rate"] > item["sale_rate_paisa"]:
            below_cost.append({"item_id": item["id"], "name": item["name"],
                               "amount": state["value"],
                               "note": "cost %s, selling price %s"
                                       % (money.format_money(state["average_rate"]),
                                          money.format_money(item["sale_rate_paisa"]))})
    if below_cost:
        out.append(_finding(
            MEDIUM, "Stock", "Stock carried above its selling price",
            "%d item%s cost more than they are priced to sell for. Under NAS 02 they should be "
            "written down to what they will actually fetch."
            % (len(below_cost), "" if len(below_cost) == 1 else "s"),
            "NAS 02", sum(b["amount"] for b in below_cost), len(below_cost), below_cost[:25]))
    return out


# How the entries were made


def _check_behaviour(conn, ctx):
    out = []

    rounds = conn.execute(
        """SELECT COUNT(*) AS n, COALESCE(SUM(total_paisa), 0) AS amount FROM vouchers
           WHERE status = 'posted' AND date_ad >= ? AND date_ad <= ?
             AND total_paisa >= ? AND total_paisa % 100000 = 0""",
        (ctx["from_ad"], ctx["to_ad"], ROUND_SUM_MINIMUM)).fetchone()
    total_vouchers = conn.execute(
        """SELECT COUNT(*) AS n FROM vouchers WHERE status = 'posted'
           AND date_ad >= ? AND date_ad <= ?""",
        (ctx["from_ad"], ctx["to_ad"])).fetchone()["n"]
    if total_vouchers and rounds["n"] * 100 > total_vouchers * 25:
        out.append(_finding(
            LOW, "Entries", "A lot of perfectly round amounts",
            "%d of %d vouchers are in exact thousands. Round sums are normal for rent and "
            "salary, less so for trade, so it is worth a glance."
            % (rounds["n"], total_vouchers), "", rounds["amount"], rounds["n"]))

    late = conn.execute(
        """SELECT id, number, date_bs, date_ad, created_at, total_paisa, narration
           FROM vouchers
           WHERE status = 'posted' AND date_ad >= ? AND date_ad <= ?
             AND julianday(substr(created_at, 1, 10)) - julianday(date_ad) > 30
           ORDER BY julianday(substr(created_at, 1, 10)) - julianday(date_ad) DESC LIMIT 40""",
        (ctx["from_ad"], ctx["to_ad"])).fetchall()
    if late:
        out.append(_finding(
            MEDIUM, "Entries", "Vouchers entered long after their date",
            "%d voucher%s were keyed more than a month after the date written on them. Books "
            "written up well after the event are worth more scrutiny."
            % (len(late), "" if len(late) == 1 else "s"), "", 0, len(late),
            [{"voucher_id": r["id"], "note": "%s dated %s, entered %s"
              % (r["number"], r["date_bs"], r["created_at"][:10]),
              "amount": r["total_paisa"]} for r in late[:25]]))

    duplicates = conn.execute(
        """SELECT date_ad, party_id, total_paisa, COUNT(*) AS n,
                  GROUP_CONCAT(number, ', ') AS numbers
           FROM vouchers
           WHERE status = 'posted' AND date_ad >= ? AND date_ad <= ?
             AND party_id IS NOT NULL AND total_paisa > 0
           GROUP BY date_ad, party_id, total_paisa, voucher_type
           HAVING COUNT(*) > 1 ORDER BY total_paisa DESC LIMIT 30""",
        (ctx["from_ad"], ctx["to_ad"])).fetchall()
    if duplicates:
        out.append(_finding(
            MEDIUM, "Entries", "Possible duplicates",
            "%d set%s of vouchers share the same party, date and amount. Some will be genuine "
            "repeat business, but each should be looked at."
            % (len(duplicates), "" if len(duplicates) == 1 else "s"), "", 0, len(duplicates),
            [{"note": r["numbers"], "amount": r["total_paisa"]} for r in duplicates[:25]]))

    users = conn.execute(
        """SELECT COUNT(DISTINCT created_by) AS n FROM vouchers
           WHERE date_ad >= ? AND date_ad <= ?""",
        (ctx["from_ad"], ctx["to_ad"])).fetchone()["n"]
    if users <= 1 and total_vouchers > 50:
        out.append(_finding(
            LOW, "Control", "Everything was entered by one person",
            "All %d vouchers were keyed by the same user. In a small business that is normal, "
            "but it means there is no separation between making an entry and checking it, so "
            "the owner's own review matters more." % total_vouchers, "", 0, 0))
    return out


# Does the shape of the numbers make sense


def _check_analytics(conn, ctx):
    out = []
    profit = ctx["profit"]
    previous = ctx.get("previous_profit")

    if profit["revenue"] and profit["gross_profit"] < 0:
        out.append(_finding(
            HIGH, "Analytical", "Gross profit is negative",
            "Cost of sales of %s against revenue of %s. Either stock is valued wrongly, the "
            "closing stock entry has not been passed, or goods are being sold below cost."
            % (money.format_money(profit["cost_of_sales"]),
               money.format_money(profit["revenue"])), "", -profit["gross_profit"]))

    if previous and previous["revenue"] and profit["revenue"]:
        this_margin = money.round_half_up(profit["gross_profit"] * 10000, profit["revenue"])
        last_margin = money.round_half_up(previous["gross_profit"] * 10000, previous["revenue"])
        swing = abs(this_margin - last_margin)
        if swing > 500:
            out.append(_finding(
                MEDIUM, "Analytical", "Gross margin has moved sharply",
                "The margin has gone from %.1f percent to %.1f percent. A swing of that size "
                "needs an explanation: a change in the mix, in pricing, or an error in stock."
                % (last_margin / 100.0, this_margin / 100.0), "", 0))

    return out


def _ratios(conn, ctx):
    """The handful of ratios that get looked at first."""
    balances = ctx["balances"]
    accounts = ctx["accounts"]
    profit = ctx["profit"]

    def total_for(section):
        amount = 0
        for account in accounts.values():
            if account["section"] != section or account["statement"] != "BS":
                continue
            balance = balances.get(account["id"], 0)
            amount += -balance if account["nature"] in reports.CREDIT_NATURES else balance
        return amount

    def group_total(codes):
        amount = 0
        for account in accounts.values():
            if account["group_code"] not in codes:
                continue
            balance = balances.get(account["id"], 0)
            amount += -balance if account["nature"] in reports.CREDIT_NATURES else balance
        return amount

    current_assets = group_total({"1210", "1220", "1230", "1240", "1250", "1260", "1270", "1280"})
    current_liabilities = group_total({"2210", "2220", "2230", "2240", "2250", "2260",
                                       "2270", "2280", "2290"})
    inventory = group_total({"1210"})
    receivables = group_total({"1220"})
    payables = group_total({"2210"})
    borrowings = group_total({"2110", "2220", "2140"})
    equity = total_for("equity") + profit["profit_after_tax"]

    def ratio(numerator, denominator, places=2):
        if not denominator:
            return None
        return round(numerator / float(denominator), places)

    def days(balance, flow):
        if not flow:
            return None
        return int(round(balance * 365.0 / flow))

    return {
        "current_ratio": ratio(current_assets, current_liabilities),
        "quick_ratio": ratio(current_assets - inventory, current_liabilities),
        "debt_to_equity": ratio(borrowings, equity),
        "gross_margin_pct": (round(profit["gross_profit"] * 100.0 / profit["revenue"], 1)
                             if profit["revenue"] else None),
        "net_margin_pct": (round(profit["profit_after_tax"] * 100.0 / profit["revenue"], 1)
                           if profit["revenue"] else None),
        "receivable_days": days(receivables, profit["revenue"]),
        "payable_days": days(payables, profit["cost_of_sales"]),
        "inventory_days": days(inventory, profit["cost_of_sales"]),
        "working_capital": current_assets - current_liabilities,
        "current_assets": current_assets,
        "current_liabilities": current_liabilities,
    }

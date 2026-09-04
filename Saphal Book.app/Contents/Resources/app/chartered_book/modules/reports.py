"""
Reports read from the books. They never write to them.

A single rule governs every figure here: only vouchers with status 'posted'
are counted. Drafts and cancelled vouchers are invisible to the accounts.

Sign convention: a balance is held as a signed integer in paisa where a
positive number means a debit balance and a negative number means a credit
balance. Each report turns that into the column an accountant expects to read.
"""

from ..core import money, nepali_date as nd

POSTED = "status = 'posted'"

# Which side a group's natural balance sits on, used for presenting figures
# without a minus sign in front of them.
CREDIT_NATURES = ("liability", "equity", "income")


def _account_rows(conn, only_active=False):
    sql = """SELECT a.*, g.code AS group_code, g.name AS group_name, g.name_np AS group_name_np,
                    g.nature, g.statement, g.section, g.sort_order AS group_sort,
                    g.parent_id AS group_parent_id
             FROM accounts a JOIN account_groups g ON g.id = a.group_id"""
    if only_active:
        sql += " WHERE a.active = 1"
    sql += " ORDER BY g.sort_order, a.code"
    return conn.execute(sql).fetchall()


def account_movements(conn, upto_ad=None, from_ad=None):
    """Total debit and credit per account, optionally limited to a date window."""
    sql = """SELECT e.account_id, SUM(e.dr_paisa) AS dr, SUM(e.cr_paisa) AS cr
             FROM voucher_entries e JOIN vouchers v ON v.id = e.voucher_id
             WHERE v.%s""" % POSTED
    args = []
    if from_ad:
        sql += " AND v.date_ad >= ?"
        args.append(from_ad)
    if upto_ad:
        sql += " AND v.date_ad <= ?"
        args.append(upto_ad)
    sql += " GROUP BY e.account_id"
    return {r["account_id"]: (r["dr"] or 0, r["cr"] or 0) for r in conn.execute(sql, args)}


def balances_as_at(conn, upto_ad):
    """Signed closing balance of every account as at a date. Debit positive."""
    moves = account_movements(conn, upto_ad=upto_ad)
    out = {}
    for row in _account_rows(conn):
        dr, cr = moves.get(row["id"], (0, 0))
        out[row["id"]] = row["opening_paisa"] + dr - cr
    return out


def trial_balance(conn, from_ad, to_ad, include_zero=False):
    """
    Opening, movement and closing for every account between two dates.

    The report proves the books: total debit must equal total credit in each
    pair of columns. If it does not, something has bypassed the posting engine.
    """
    opening_moves = account_movements(conn, upto_ad=_day_before(from_ad))
    period_moves = account_movements(conn, from_ad=from_ad, upto_ad=to_ad)
    rows = []
    totals = {"opening_dr": 0, "opening_cr": 0, "period_dr": 0, "period_cr": 0,
              "closing_dr": 0, "closing_cr": 0}
    for account in _account_rows(conn):
        odr, ocr = opening_moves.get(account["id"], (0, 0))
        opening = account["opening_paisa"] + odr - ocr
        pdr, pcr = period_moves.get(account["id"], (0, 0))
        closing = opening + pdr - pcr
        if not include_zero and opening == 0 and pdr == 0 and pcr == 0 and closing == 0:
            continue
        row = {
            "account_id": account["id"],
            "code": account["code"],
            "name": account["name"],
            "name_np": account["name_np"],
            "group_name": account["group_name"],
            "group_code": account["group_code"],
            "nature": account["nature"],
            "statement": account["statement"],
            "opening_dr": opening if opening > 0 else 0,
            "opening_cr": -opening if opening < 0 else 0,
            "period_dr": pdr,
            "period_cr": pcr,
            "closing_dr": closing if closing > 0 else 0,
            "closing_cr": -closing if closing < 0 else 0,
        }
        for key in totals:
            totals[key] += row[key]
        rows.append(row)
    return {"rows": rows, "totals": totals,
            "balanced": totals["closing_dr"] == totals["closing_cr"]
                        and totals["opening_dr"] == totals["opening_cr"]
                        and totals["period_dr"] == totals["period_cr"],
            "from_ad": from_ad, "to_ad": to_ad}


def _day_before(date_ad):
    import datetime
    return (datetime.date.fromisoformat(date_ad) - datetime.timedelta(days=1)).isoformat()


def ledger_statement(conn, account_id, from_ad, to_ad):
    """Every posting in one account for a period, with a running balance."""
    account = conn.execute(
        """SELECT a.*, g.name AS group_name, g.nature
           FROM accounts a JOIN account_groups g ON g.id = a.group_id
           WHERE a.id = ?""", (account_id,)).fetchone()
    if account is None:
        return None
    prior = conn.execute(
        """SELECT COALESCE(SUM(e.dr_paisa), 0) AS dr, COALESCE(SUM(e.cr_paisa), 0) AS cr
           FROM voucher_entries e JOIN vouchers v ON v.id = e.voucher_id
           WHERE e.account_id = ? AND v.%s AND v.date_ad < ?""" % POSTED,
        (account_id, from_ad)).fetchone()
    opening = account["opening_paisa"] + prior["dr"] - prior["cr"]

    lines = conn.execute(
        """SELECT v.id AS voucher_id, v.number, v.date_ad, v.date_bs, v.voucher_type,
                  v.narration AS voucher_narration, v.reference_no,
                  e.dr_paisa, e.cr_paisa, e.narration, e.line_no,
                  p.name AS party_name,
                  (SELECT GROUP_CONCAT(a2.name, ', ')
                     FROM voucher_entries e2 JOIN accounts a2 ON a2.id = e2.account_id
                    WHERE e2.voucher_id = v.id AND e2.account_id <> ?) AS contra
           FROM voucher_entries e JOIN vouchers v ON v.id = e.voucher_id
           LEFT JOIN parties p ON p.id = v.party_id
           WHERE e.account_id = ? AND v.%s AND v.date_ad >= ? AND v.date_ad <= ?
           ORDER BY v.date_ad, v.id, e.line_no""" % POSTED,
        (account_id, account_id, from_ad, to_ad)).fetchall()

    running = opening
    out = []
    total_dr = total_cr = 0
    for line in lines:
        running += line["dr_paisa"] - line["cr_paisa"]
        total_dr += line["dr_paisa"]
        total_cr += line["cr_paisa"]
        out.append({
            "voucher_id": line["voucher_id"],
            "number": line["number"],
            "date_ad": line["date_ad"],
            "date_bs": line["date_bs"],
            "voucher_type": line["voucher_type"],
            "party_name": line["party_name"] or "",
            "particulars": line["contra"] or (line["narration"] or line["voucher_narration"]),
            "narration": line["narration"] or line["voucher_narration"] or "",
            "reference_no": line["reference_no"] or "",
            "dr": line["dr_paisa"],
            "cr": line["cr_paisa"],
            "balance": running,
        })
    return {
        "account": account,
        "opening": opening,
        "lines": out,
        "total_dr": total_dr,
        "total_cr": total_cr,
        "closing": running,
        "from_ad": from_ad,
        "to_ad": to_ad,
    }


def day_book(conn, from_ad, to_ad, voucher_type=None, include_cancelled=False):
    sql = """SELECT v.*, p.name AS party_name, vt.name AS type_name
             FROM vouchers v
             LEFT JOIN parties p ON p.id = v.party_id
             JOIN voucher_types vt ON vt.code = v.voucher_type
             WHERE v.date_ad >= ? AND v.date_ad <= ?"""
    args = [from_ad, to_ad]
    if not include_cancelled:
        sql += " AND v.status <> 'cancelled'"
    if voucher_type:
        sql += " AND v.voucher_type = ?"
        args.append(voucher_type)
    sql += " ORDER BY v.date_ad, v.id"
    return conn.execute(sql, args).fetchall()


def profit_and_loss(conn, from_ad, to_ad):
    """
    Statement of profit or loss for a period, laid out the way NFRS presents it.

    Income is shown as a positive figure, expense as a positive figure, and the
    result is revenue less every expense line.
    """
    period = account_movements(conn, from_ad=from_ad, upto_ad=to_ad)
    sections = {}
    for account in _account_rows(conn):
        if account["statement"] != "PL":
            continue
        dr, cr = period.get(account["id"], (0, 0))
        movement = dr - cr
        if movement == 0:
            continue
        # Income sits on the credit side, so flip it to read as a positive amount.
        amount = -movement if account["nature"] == "income" else movement
        bucket = sections.setdefault(account["section"], {
            "section": account["section"], "groups": {}, "total": 0})
        group = bucket["groups"].setdefault(account["group_code"], {
            "code": account["group_code"], "name": account["group_name"],
            "name_np": account["group_name_np"], "sort": account["group_sort"],
            "lines": [], "total": 0})
        group["lines"].append({
            "account_id": account["id"], "code": account["code"],
            "name": account["name"], "name_np": account["name_np"], "amount": amount})
        group["total"] += amount
        bucket["total"] += amount

    def section_total(name):
        return sections.get(name, {}).get("total", 0)

    revenue = section_total("revenue")
    other_income = section_total("other_income")
    cost_of_sales = section_total("cost_of_sales")
    employee = section_total("employee")
    administrative = section_total("administrative")
    selling = section_total("selling")
    finance = section_total("finance")
    depreciation = section_total("depreciation")
    other_expense = section_total("other_expense")
    tax = section_total("tax")

    other_comprehensive = section_total("oci")

    gross_profit = revenue - cost_of_sales
    operating_expense = employee + administrative + selling
    operating_profit = gross_profit + other_income - operating_expense
    profit_before_tax = operating_profit - finance - depreciation - other_expense
    profit_after_tax = profit_before_tax - tax
    # Items of other comprehensive income never pass through profit or loss.
    # NAS 01 shows them below it and adds the two to total comprehensive income.
    total_comprehensive_income = profit_after_tax + other_comprehensive

    return {
        "from_ad": from_ad, "to_ad": to_ad,
        "sections": sections,
        "revenue": revenue,
        "other_income": other_income,
        "cost_of_sales": cost_of_sales,
        "gross_profit": gross_profit,
        "employee": employee,
        "administrative": administrative,
        "selling": selling,
        "operating_expense": operating_expense,
        "operating_profit": operating_profit,
        "finance": finance,
        "depreciation": depreciation,
        "other_expense": other_expense,
        "profit_before_tax": profit_before_tax,
        "tax": tax,
        "profit_after_tax": profit_after_tax,
        "other_comprehensive_income": other_comprehensive,
        "total_comprehensive_income": total_comprehensive_income,
    }


def balance_sheet(conn, as_at_ad, fy_start_ad=None):
    """
    Statement of financial position as at a date.

    Profit for the year is computed from the profit and loss accounts and shown
    inside equity, which is what makes the statement balance without anyone
    having to pass a closing entry first.
    """
    balances = balances_as_at(conn, as_at_ad)
    sides = {"assets": {"groups": {}, "total": 0},
             "liabilities": {"groups": {}, "total": 0},
             "equity": {"groups": {}, "total": 0}}
    for account in _account_rows(conn):
        if account["statement"] != "BS":
            continue
        balance = balances.get(account["id"], 0)
        if balance == 0:
            continue
        amount = -balance if account["nature"] in CREDIT_NATURES else balance
        side = sides[account["section"]]
        group = side["groups"].setdefault(account["group_code"], {
            "code": account["group_code"], "name": account["group_name"],
            "name_np": account["group_name_np"], "sort": account["group_sort"],
            "parent_id": account["group_parent_id"], "lines": [], "total": 0})
        group["lines"].append({
            "account_id": account["id"], "code": account["code"],
            "name": account["name"], "name_np": account["name_np"], "amount": amount})
        group["total"] += amount
        side["total"] += amount

    if fy_start_ad is None:
        fy_start_ad = nd.fiscal_year_of(as_at_ad)["start_ad"]
    result = profit_and_loss(conn, fy_start_ad, as_at_ad)
    profit = result["profit_after_tax"] + result["other_comprehensive_income"]

    sides["equity"]["groups"]["3200P"] = {
        "code": "3200P", "name": "Profit for the Period", "name_np": "अवधिको नाफा",
        "sort": 321, "parent_id": None,
        "lines": [{"account_id": None, "code": "", "name": "Profit for the Period",
                   "name_np": "अवधिको नाफा", "amount": profit}],
        "total": profit,
    }
    sides["equity"]["total"] += profit

    assets = sides["assets"]["total"]
    liabilities = sides["liabilities"]["total"]
    equity = sides["equity"]["total"]
    return {
        "as_at_ad": as_at_ad,
        "assets": sides["assets"],
        "liabilities": sides["liabilities"],
        "equity": sides["equity"],
        "total_assets": assets,
        "total_liabilities": liabilities,
        "total_equity": equity,
        "total_liabilities_and_equity": liabilities + equity,
        "difference": assets - (liabilities + equity),
        "balanced": assets == liabilities + equity,
        "profit_for_period": profit,
    }


# Stock


def stock_movements(conn, item_id, upto_ad=None):
    sql = """SELECT s.*, v.number, v.voucher_type, v.date_bs, p.name AS party_name
             FROM stock_ledger s JOIN vouchers v ON v.id = s.voucher_id
             LEFT JOIN parties p ON p.id = v.party_id
             WHERE s.item_id = ? AND v.status = 'posted'"""
    args = [item_id]
    if upto_ad:
        sql += " AND s.date_ad <= ?"
        args.append(upto_ad)
    sql += " ORDER BY s.date_ad, s.id"
    return conn.execute(sql, args).fetchall()


def item_stock(conn, item_id, upto_ad=None):
    """
    Replay an item's movements to get quantity on hand and its value under the
    weighted average method. Replaying rather than storing a running figure means
    a backdated entry corrects the valuation automatically.
    """
    item = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if item is None:
        return None
    qty = item["opening_qty"]
    value = item["opening_value_paisa"]
    history = []
    for move in stock_movements(conn, item_id, upto_ad):
        if move["direction"] > 0:
            qty += move["qty"]
            value += move["value_paisa"]
            cost = move["value_paisa"]
        else:
            if move["qty"] >= qty or qty <= 0:
                cost = value
                qty = qty - move["qty"]
                value = 0
            else:
                cost = money.round_half_up(value * move["qty"], qty)
                qty -= move["qty"]
                value -= cost
        history.append({
            "date_ad": move["date_ad"], "date_bs": move["date_bs"],
            "number": move["number"], "voucher_type": move["voucher_type"],
            "party_name": move["party_name"] or "",
            "direction": move["direction"], "qty": move["qty"],
            "rate": move["rate_paisa"], "value": move["value_paisa"],
            "cost": cost, "balance_qty": qty, "balance_value": value,
        })
    average = money.round_half_up(value * money.QTY_SCALE, qty) if qty > 0 else 0
    return {"item": item, "qty": qty, "value": value, "average_rate": average,
            "history": history}


def stock_summary(conn, upto_ad=None, group_id=None, only_active=True):
    """Quantity and value of every stock item, with the total that goes into the accounts."""
    sql = """SELECT i.*, g.name AS group_name, u.symbol AS unit_symbol
             FROM items i LEFT JOIN item_groups g ON g.id = i.group_id
             LEFT JOIN units u ON u.id = i.unit_id
             WHERE i.maintain_stock = 1 AND i.item_type = 'goods'"""
    args = []
    if only_active:
        sql += " AND i.active = 1"
    if group_id:
        sql += " AND i.group_id = ?"
        args.append(group_id)
    sql += " ORDER BY g.name, i.name"
    rows = []
    total_value = 0
    for item in conn.execute(sql, args):
        state = item_stock(conn, item["id"], upto_ad)
        total_value += state["value"]
        rows.append({
            "item_id": item["id"], "code": item["code"], "name": item["name"],
            "name_np": item["name_np"], "group_name": item["group_name"] or "",
            "unit": item["unit_symbol"] or "", "qty": state["qty"],
            "value": state["value"], "average_rate": state["average_rate"],
            "reorder_qty": item["reorder_qty"],
            "below_reorder": item["reorder_qty"] > 0 and state["qty"] <= item["reorder_qty"],
        })
    return {"rows": rows, "total_value": total_value, "upto_ad": upto_ad}


# Receivables and payables


def outstanding(conn, side, as_at_ad=None):
    """
    Party wise balances. side is 'receivable' for customers or 'payable' for
    suppliers. Ageing is measured from the invoice date.
    """
    kind = "party_customer" if side == "receivable" else "party_supplier"
    sql = """SELECT a.id, a.code, a.name, a.opening_paisa,
                    p.id AS party_id, p.phone, p.mobile, p.credit_days, p.credit_limit_paisa,
                    p.pan
             FROM accounts a
             LEFT JOIN parties p ON p.account_id = a.id
             JOIN account_groups g ON g.id = a.group_id
             WHERE a.account_kind = ? OR g.code = ?"""
    group_code = "1220" if side == "receivable" else "2210"
    accounts = conn.execute(sql, (kind, group_code)).fetchall()
    moves = account_movements(conn, upto_ad=as_at_ad)
    rows = []
    total = 0
    for account in accounts:
        dr, cr = moves.get(account["id"], (0, 0))
        balance = account["opening_paisa"] + dr - cr
        amount = balance if side == "receivable" else -balance
        if amount == 0:
            continue
        rows.append({
            "account_id": account["id"], "party_id": account["party_id"],
            "code": account["code"], "name": account["name"],
            "pan": account["pan"] or "", "phone": account["mobile"] or account["phone"] or "",
            "credit_days": account["credit_days"] or 0,
            "credit_limit": account["credit_limit_paisa"] or 0,
            "amount": amount,
        })
        total += amount
    rows.sort(key=lambda r: -r["amount"])
    return {"rows": rows, "total": total, "side": side, "as_at_ad": as_at_ad}


# Value added tax


SALES_TYPES = ("sales", "credit_note")
PURCHASE_TYPES = ("purchase", "debit_note")


def vat_register(conn, side, from_ad, to_ad):
    """
    The sales or purchase register in the layout the Inland Revenue Department
    asks for. A credit note reduces the sales register and a debit note reduces
    the purchase register, which is why both appear here with a negative sign.
    """
    types = SALES_TYPES if side == "sales" else PURCHASE_TYPES
    reversal = "credit_note" if side == "sales" else "debit_note"
    placeholders = ", ".join("?" for _ in types)
    rows = conn.execute(
        """SELECT v.*, p.name AS party_name, p.pan AS party_pan
           FROM vouchers v LEFT JOIN parties p ON p.id = v.party_id
           WHERE v.status = 'posted' AND v.voucher_type IN (%s)
             AND v.date_ad >= ? AND v.date_ad <= ?
           ORDER BY v.date_ad, v.id""" % placeholders,
        list(types) + [from_ad, to_ad]).fetchall()

    entries = []
    totals = {"total": 0, "taxable": 0, "vat": 0, "exempt": 0}
    for row in rows:
        sign = -1 if row["voucher_type"] == reversal else 1
        # A sales return or purchase return also reduces the register.
        if row["voucher_type"] in ("sales_return", "purchase_return"):
            sign = -1
        entry = {
            "voucher_id": row["id"],
            "date_ad": row["date_ad"],
            "date_bs": row["date_bs"],
            "number": row["number"],
            "voucher_type": row["voucher_type"],
            "party_name": row["party_name"] or "Cash",
            "party_pan": row["party_pan"] or "",
            "total": sign * row["total_paisa"],
            "taxable": sign * row["taxable_paisa"],
            "vat": sign * row["vat_paisa"],
            "exempt": sign * row["exempt_paisa"],
        }
        for key in totals:
            totals[key] += entry[key]
        entries.append(entry)

    # Returns are stored under their own voucher types, so pick them up too.
    return_type = "sales_return" if side == "sales" else "purchase_return"
    for row in conn.execute(
            """SELECT v.*, p.name AS party_name, p.pan AS party_pan
               FROM vouchers v LEFT JOIN parties p ON p.id = v.party_id
               WHERE v.status = 'posted' AND v.voucher_type = ?
                 AND v.date_ad >= ? AND v.date_ad <= ?
               ORDER BY v.date_ad, v.id""", (return_type, from_ad, to_ad)):
        entry = {
            "voucher_id": row["id"], "date_ad": row["date_ad"], "date_bs": row["date_bs"],
            "number": row["number"], "voucher_type": row["voucher_type"],
            "party_name": row["party_name"] or "Cash", "party_pan": row["party_pan"] or "",
            "total": -row["total_paisa"], "taxable": -row["taxable_paisa"],
            "vat": -row["vat_paisa"], "exempt": -row["exempt_paisa"],
        }
        for key in totals:
            totals[key] += entry[key]
        entries.append(entry)

    entries.sort(key=lambda e: (e["date_ad"], e["number"]))
    return {"side": side, "from_ad": from_ad, "to_ad": to_ad,
            "rows": entries, "totals": totals}


def vat_return(conn, bs_year, bs_month):
    """
    The monthly VAT position for a Bikram Sambat month.

    Output tax less input tax gives either an amount payable to the Inland
    Revenue Department or a credit carried into the following month.
    """
    from_ad, to_ad = nd.bs_month_range(bs_year, bs_month)
    sales = vat_register(conn, "sales", from_ad, to_ad)
    purchases = vat_register(conn, "purchase", from_ad, to_ad)
    output_tax = sales["totals"]["vat"]
    input_tax = purchases["totals"]["vat"]
    net = output_tax - input_tax
    return {
        "bs_year": bs_year,
        "bs_month": bs_month,
        "month_name": nd.MONTH_NAMES_EN[bs_month - 1],
        "month_name_np": nd.MONTH_NAMES_NP[bs_month - 1],
        "from_ad": from_ad,
        "to_ad": to_ad,
        "sales": sales["totals"],
        "purchases": purchases["totals"],
        "output_tax": output_tax,
        "input_tax": input_tax,
        "net": net,
        "payable": net if net > 0 else 0,
        "credit_carried": -net if net < 0 else 0,
        "sales_rows": sales["rows"],
        "purchase_rows": purchases["rows"],
        # The return is due on the 25th of the following Nepali month.
        "due_date_bs": _vat_due_date(bs_year, bs_month),
    }


def _vat_due_date(bs_year, bs_month):
    year, month = (bs_year + 1, 1) if bs_month == 12 else (bs_year, bs_month + 1)
    try:
        day = min(25, nd.days_in_bs_month(year, month))
    except nd.DateRangeError:
        return ""
    return nd.format_bs((year, month, day), "long")


def cash_and_bank_summary(conn, upto_ad):
    """Balance of every cash and bank ledger, for the dashboard."""
    balances = balances_as_at(conn, upto_ad)
    rows = []
    total = 0
    for account in _account_rows(conn, only_active=True):
        if account["account_kind"] not in ("cash", "bank"):
            continue
        balance = balances.get(account["id"], 0)
        if balance == 0 and account["opening_paisa"] == 0:
            continue
        rows.append({"account_id": account["id"], "name": account["name"],
                     "kind": account["account_kind"], "balance": balance})
        total += balance
    return {"rows": rows, "total": total}


# Drilling down
#
# Every figure in a statement should be answerable. Click a total and it opens
# the groups inside it, click a group and it opens the ledgers, click a ledger
# and it opens month by month, click a month and it opens the vouchers, click a
# voucher and the voucher itself appears. Nothing in a report is a dead end.


def _day_before_iso(date_ad):
    import datetime
    return (datetime.date.fromisoformat(date_ad) - datetime.timedelta(days=1)).isoformat()


def _groups(conn):
    return conn.execute("SELECT * FROM account_groups ORDER BY sort_order, code").fetchall()


def group_tree(conn, from_ad, to_ad, statement=None, section=None):
    """
    The whole group hierarchy with a total against every node.

    A parent shows the total of everything beneath it, so the tree can be opened
    one level at a time without the figures ever disagreeing.
    """
    opening_moves = account_movements(conn, upto_ad=_day_before_iso(from_ad))
    period_moves = account_movements(conn, from_ad=from_ad, upto_ad=to_ad)

    nodes = {}
    for group in _groups(conn):
        nodes[group["id"]] = {
            "id": group["id"], "code": group["code"], "name": group["name"],
            "name_np": group["name_np"], "parent_id": group["parent_id"],
            "nature": group["nature"], "statement": group["statement"],
            "section": group["section"], "sort": group["sort_order"],
            "own_opening": 0, "own_debit": 0, "own_credit": 0, "own_closing": 0,
            "opening": 0, "debit": 0, "credit": 0, "closing": 0,
            "ledger_count": 0, "children": [],
        }

    for account in _account_rows(conn):
        node = nodes.get(account["group_id"])
        if node is None:
            continue
        odr, ocr = opening_moves.get(account["id"], (0, 0))
        opening = account["opening_paisa"] + odr - ocr
        pdr, pcr = period_moves.get(account["id"], (0, 0))
        node["own_opening"] += opening
        node["own_debit"] += pdr
        node["own_credit"] += pcr
        node["own_closing"] += opening + pdr - pcr
        node["ledger_count"] += 1

    # Roll every figure up through the parents.
    for node in nodes.values():
        for key in ("opening", "debit", "credit", "closing"):
            node[key] = node["own_" + key]
    for node in list(nodes.values()):
        parent = nodes.get(node["parent_id"])
        while parent is not None:
            for key in ("opening", "debit", "credit", "closing"):
                parent[key] += node["own_" + key]
            parent = nodes.get(parent["parent_id"])

    for node in nodes.values():
        if node["parent_id"] and node["parent_id"] in nodes:
            nodes[node["parent_id"]]["children"].append(node["id"])

    roots = []
    for node in sorted(nodes.values(), key=lambda n: (n["sort"], n["code"])):
        if node["parent_id"]:
            continue
        if statement and node["statement"] != statement:
            continue
        if section and node["section"] != section:
            continue
        roots.append(node["id"])

    return {"nodes": nodes, "roots": roots, "from_ad": from_ad, "to_ad": to_ad}


def group_detail(conn, group_id, from_ad, to_ad):
    """What sits directly inside one group: the child groups and the ledgers."""
    group = conn.execute("SELECT * FROM account_groups WHERE id = ?", (group_id,)).fetchone()
    if group is None:
        return None
    tree = group_tree(conn, from_ad, to_ad)
    node = tree["nodes"].get(group_id)

    children = []
    for child_id in (node["children"] if node else []):
        child = tree["nodes"][child_id]
        if child["closing"] == 0 and child["debit"] == 0 and child["credit"] == 0:
            continue
        children.append({
            "kind": "group", "id": child["id"], "code": child["code"],
            "name": child["name"], "name_np": child["name_np"],
            "opening": child["opening"], "debit": child["debit"],
            "credit": child["credit"], "closing": child["closing"],
            "has_more": bool(child["children"]) or child["ledger_count"] > 0,
        })

    opening_moves = account_movements(conn, upto_ad=_day_before_iso(from_ad))
    period_moves = account_movements(conn, from_ad=from_ad, upto_ad=to_ad)
    ledgers = []
    for account in _account_rows(conn):
        if account["group_id"] != group_id:
            continue
        odr, ocr = opening_moves.get(account["id"], (0, 0))
        opening = account["opening_paisa"] + odr - ocr
        pdr, pcr = period_moves.get(account["id"], (0, 0))
        closing = opening + pdr - pcr
        if opening == 0 and pdr == 0 and pcr == 0:
            continue
        ledgers.append({
            "kind": "ledger", "id": account["id"], "code": account["code"],
            "name": account["name"], "name_np": account["name_np"],
            "opening": opening, "debit": pdr, "credit": pcr, "closing": closing,
            "has_more": True,
        })

    return {
        "group": dict(group),
        "path": group_path(conn, group_id),
        "nature": group["nature"],
        "children": children,
        "ledgers": ledgers,
        "totals": {
            "opening": node["opening"] if node else 0,
            "debit": node["debit"] if node else 0,
            "credit": node["credit"] if node else 0,
            "closing": node["closing"] if node else 0,
        },
        "from_ad": from_ad, "to_ad": to_ad,
    }


def group_path(conn, group_id):
    """The chain of groups from the top down to this one, for the breadcrumb."""
    path = []
    current = conn.execute("SELECT * FROM account_groups WHERE id = ?", (group_id,)).fetchone()
    guard = 0
    while current is not None and guard < 20:
        path.insert(0, {"id": current["id"], "code": current["code"], "name": current["name"]})
        if not current["parent_id"]:
            break
        current = conn.execute("SELECT * FROM account_groups WHERE id = ?",
                               (current["parent_id"],)).fetchone()
        guard += 1
    return path


def ledger_monthly(conn, account_id, from_ad, to_ad):
    """
    One ledger summarised into Nepali months, which is how a proprietor reads a
    year. Each month opens into the vouchers that made it.
    """
    account = conn.execute(
        """SELECT a.*, g.name AS group_name, g.id AS group_id, g.nature
           FROM accounts a JOIN account_groups g ON g.id = a.group_id WHERE a.id = ?""",
        (account_id,)).fetchone()
    if account is None:
        return None

    prior = conn.execute(
        """SELECT COALESCE(SUM(e.dr_paisa), 0) AS dr, COALESCE(SUM(e.cr_paisa), 0) AS cr
           FROM voucher_entries e JOIN vouchers v ON v.id = e.voucher_id
           WHERE e.account_id = ? AND v.%s AND v.date_ad < ?""" % POSTED,
        (account_id, from_ad)).fetchone()
    opening = account["opening_paisa"] + prior["dr"] - prior["cr"]

    rows = conn.execute(
        """SELECT v.date_ad, e.dr_paisa, e.cr_paisa
           FROM voucher_entries e JOIN vouchers v ON v.id = e.voucher_id
           WHERE e.account_id = ? AND v.%s AND v.date_ad >= ? AND v.date_ad <= ?""" % POSTED,
        (account_id, from_ad, to_ad)).fetchall()

    buckets = {}
    for row in rows:
        year, month, _ = nd.ad_to_bs(row["date_ad"])
        key = (year, month)
        bucket = buckets.setdefault(key, {"debit": 0, "credit": 0, "count": 0})
        bucket["debit"] += row["dr_paisa"]
        bucket["credit"] += row["cr_paisa"]
        bucket["count"] += 1

    months = []
    running = opening
    for key in sorted(buckets):
        year, month = key
        bucket = buckets[key]
        start_ad, end_ad = nd.bs_month_range(year, month)
        running += bucket["debit"] - bucket["credit"]
        months.append({
            "bs_year": year, "bs_month": month,
            "label": "%s %d" % (nd.MONTH_NAMES_EN[month - 1], year),
            "label_np": "%s %s" % (nd.MONTH_NAMES_NP[month - 1], nd.to_devanagari(year)),
            "from_ad": max(start_ad, from_ad), "to_ad": min(end_ad, to_ad),
            "debit": bucket["debit"], "credit": bucket["credit"],
            "count": bucket["count"], "closing": running,
        })

    return {
        "account": dict(account),
        "path": group_path(conn, account["group_id"]),
        "opening": opening,
        "months": months,
        "total_debit": sum(m["debit"] for m in months),
        "total_credit": sum(m["credit"] for m in months),
        "closing": running,
        "from_ad": from_ad, "to_ad": to_ad,
    }


def _age_in_days(item, as_at_ad):
    """
    How overdue an item is on the reporting date.

    If the invoice carries a due date, the age is counted from that, so an
    invoice inside its credit period is not shown as overdue. Otherwise it is
    counted from the invoice date. A negative answer means it is not due yet.
    """
    import datetime
    reference = item.get("due_date_ad") or item.get("date_ad")
    if not reference:
        return None
    days = (datetime.date.fromisoformat(as_at_ad)
            - datetime.date.fromisoformat(reference)).days
    if item.get("due_date_ad") and days <= 0:
        return -1
    return days


def _bucket_index(age, edges):
    """
    Which column an item falls in.

    Column 0 is not yet due. Then one column for each edge, and a last column
    for anything older than the final edge.
    """
    if age is None or age <= 0:
        return 0
    for position, edge in enumerate(edges):
        if age <= edge:
            return position + 1
    return len(edges) + 1


def ageing(conn, side, as_at_ad, buckets=(30, 60, 90, 180)):
    """
    How old the money owed is, invoice by invoice.

    An invoice is treated as settled by receipts against that party in the order
    the invoices were raised, which is the first in first out assumption most
    Nepali traders work on when nothing has been allocated against a specific
    bill. Anything not matched to an invoice is shown separately as on account.
    """
    is_receivable = side == "receivable"
    invoice_types = ("sales", "debit_note") if is_receivable else ("purchase", "credit_note")
    return_types = ("sales_return", "credit_note") if is_receivable else \
                   ("purchase_return", "debit_note")
    group_code = "1220" if is_receivable else "2210"

    accounts = conn.execute(
        """SELECT a.id, a.code, a.name, a.opening_paisa, p.id AS party_id,
                  p.name AS party_name, p.pan, p.mobile, p.phone, p.credit_days,
                  p.credit_limit_paisa
           FROM accounts a
           LEFT JOIN parties p ON p.account_id = a.id
           JOIN account_groups g ON g.id = a.group_id
           WHERE g.code = ? AND a.active = 1""", (group_code,)).fetchall()

    labels = []
    edges = list(buckets)
    labels.append("Not yet due")
    previous = 0
    for edge in edges:
        labels.append("%d to %d days" % (previous + 1, edge))
        previous = edge
    labels.append("Over %d days" % previous)

    rows = []
    totals = [0] * len(labels)
    grand = 0

    for account in accounts:
        moves = conn.execute(
            """SELECT v.id, v.number, v.date_ad, v.date_bs, v.voucher_type, v.due_date_ad,
                      e.dr_paisa, e.cr_paisa
               FROM voucher_entries e JOIN vouchers v ON v.id = e.voucher_id
               WHERE e.account_id = ? AND v.status = 'posted' AND v.date_ad <= ?
               ORDER BY v.date_ad, v.id""", (account["id"], as_at_ad)).fetchall()

        outstanding = []
        settlement = 0
        opening = account["opening_paisa"]
        if is_receivable and opening > 0:
            outstanding.append({"number": "Opening", "date_ad": None, "amount": opening,
                                "due_date_ad": None})
        elif not is_receivable and opening < 0:
            outstanding.append({"number": "Opening", "date_ad": None, "amount": -opening,
                                "due_date_ad": None})

        for move in moves:
            raised = move["dr_paisa"] if is_receivable else move["cr_paisa"]
            settled = move["cr_paisa"] if is_receivable else move["dr_paisa"]
            if raised:
                outstanding.append({
                    "number": move["number"], "date_ad": move["date_ad"],
                    "date_bs": move["date_bs"], "amount": raised,
                    "due_date_ad": move["due_date_ad"] or None,
                    "voucher_id": move["id"],
                })
            if settled:
                settlement += settled

        # Knock the settlements off the oldest invoices first.
        for item in outstanding:
            if settlement <= 0:
                break
            taken = min(settlement, item["amount"])
            item["amount"] -= taken
            settlement -= taken
        outstanding = [item for item in outstanding if item["amount"] > 0]
        if settlement > 0:
            outstanding.append({"number": "On account", "date_ad": None,
                                "amount": -settlement, "due_date_ad": None})

        balance = sum(item["amount"] for item in outstanding)
        if balance == 0:
            continue

        line_buckets = [0] * len(labels)
        details = []
        for item in outstanding:
            age = _age_in_days(item, as_at_ad)
            index = _bucket_index(age, edges)
            line_buckets[index] += item["amount"]
            details.append({
                "number": item["number"], "date_bs": item.get("date_bs", ""),
                "date_ad": item.get("date_ad"), "voucher_id": item.get("voucher_id"),
                "amount": item["amount"], "age_days": age,
            })

        for position, amount in enumerate(line_buckets):
            totals[position] += amount
        grand += balance
        rows.append({
            "account_id": account["id"], "party_id": account["party_id"],
            "code": account["code"], "name": account["party_name"] or account["name"],
            "pan": account["pan"] or "", "phone": account["mobile"] or account["phone"] or "",
            "credit_days": account["credit_days"] or 0,
            "credit_limit": account["credit_limit_paisa"] or 0,
            "buckets": line_buckets, "total": balance, "details": details,
        })

    rows.sort(key=lambda r: -r["total"])
    return {"side": side, "as_at_ad": as_at_ad, "labels": labels,
            "rows": rows, "totals": totals, "grand_total": grand}


def stock_ageing(conn, as_at_ad, buckets=(30, 60, 90, 180), only_active=True):
    """
    How long the stock on the shelf has been sitting there.

    Quantity is aged on a first in first out basis, because the oldest bag of
    cement is the one that has been there longest whatever the accounts value it
    at. Value is then put against each age band at the weighted average rate, so
    the total agrees to the paisa with the stock figure in the balance sheet.

    Stock that has not moved for months is the first thing an auditor asks about
    and the last thing a shopkeeper notices, so it is flagged here.
    """
    import datetime

    labels = []
    previous = 0
    for edge in buckets:
        labels.append("%d to %d days" % (previous + 1, edge))
        previous = edge
    labels.append("Over %d days" % previous)

    sql = """SELECT i.*, g.name AS group_name, u.symbol AS unit_symbol
             FROM items i LEFT JOIN item_groups g ON g.id = i.group_id
             LEFT JOIN units u ON u.id = i.unit_id
             WHERE i.maintain_stock = 1 AND i.item_type = 'goods'"""
    if only_active:
        sql += " AND i.active = 1"
    sql += " ORDER BY g.name, i.name"

    as_at = datetime.date.fromisoformat(as_at_ad)
    rows = []
    totals_qty = [0] * len(labels)
    totals_value = [0] * len(labels)
    grand_value = 0

    for item in conn.execute(sql):
        state = item_stock(conn, item["id"], as_at_ad)
        if state["qty"] <= 0 and state["value"] == 0:
            continue

        # Rebuild the layers that make up what is on hand, oldest first.
        layers = []
        if item["opening_qty"] > 0:
            begins = conn.execute("SELECT books_begin_ad FROM company WHERE id = 1").fetchone()
            layers.append({"date_ad": begins["books_begin_ad"] if begins else as_at_ad,
                           "qty": item["opening_qty"]})
        for move in stock_movements(conn, item["id"], as_at_ad):
            if move["direction"] > 0:
                layers.append({"date_ad": move["date_ad"], "qty": move["qty"]})
            else:
                remaining = move["qty"]
                while remaining > 0 and layers:
                    taken = min(remaining, layers[0]["qty"])
                    layers[0]["qty"] -= taken
                    remaining -= taken
                    if layers[0]["qty"] <= 0:
                        layers.pop(0)

        line_qty = [0] * len(labels)
        oldest = None
        for layer in layers:
            if layer["qty"] <= 0:
                continue
            try:
                age = (as_at - datetime.date.fromisoformat(layer["date_ad"])).days
            except (TypeError, ValueError):
                age = 0
            if oldest is None or age > oldest:
                oldest = age
            index = len(buckets)
            for position, edge in enumerate(buckets):
                if age <= edge:
                    index = position
                    break
            line_qty[index] += layer["qty"]

        held = sum(line_qty)
        # Put the value against the bands in the same proportion as the quantity,
        # so the row adds back to the balance sheet figure exactly.
        line_value = money.allocate(state["value"], line_qty) if held else [0] * len(labels)

        last_out = conn.execute(
            """SELECT MAX(s.date_ad) AS d FROM stock_ledger s
               JOIN vouchers v ON v.id = s.voucher_id
               WHERE s.item_id = ? AND s.direction = -1 AND v.status = 'posted'
                 AND s.date_ad <= ?""", (item["id"], as_at_ad)).fetchone()
        days_since_sale = None
        if last_out and last_out["d"]:
            days_since_sale = (as_at - datetime.date.fromisoformat(last_out["d"])).days

        for position in range(len(labels)):
            totals_qty[position] += line_qty[position]
            totals_value[position] += line_value[position]
        grand_value += state["value"]

        rows.append({
            "item_id": item["id"], "code": item["code"], "name": item["name"],
            "group_name": item["group_name"] or "", "unit": item["unit_symbol"] or "",
            "qty": state["qty"], "value": state["value"],
            "average_rate": state["average_rate"],
            "bucket_qty": line_qty, "bucket_value": line_value,
            "oldest_days": oldest,
            "days_since_last_sale": days_since_sale,
            "slow_moving": days_since_sale is not None and days_since_sale > buckets[-1],
            "never_sold": days_since_sale is None and state["qty"] > 0,
        })

    rows.sort(key=lambda r: -(r["bucket_value"][-1] or 0))
    return {
        "as_at_ad": as_at_ad, "labels": labels, "rows": rows,
        "totals_qty": totals_qty, "totals_value": totals_value,
        "grand_value": grand_value,
        "slow_count": sum(1 for r in rows if r["slow_moving"]),
        "never_sold_count": sum(1 for r in rows if r["never_sold"]),
        "old_value": totals_value[-1] if totals_value else 0,
    }

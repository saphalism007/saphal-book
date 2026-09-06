"""
Who bought what, from whom, and whether it was worth selling.

The trial balance and the statements say what happened to the business. These
say where it came from: which customers, which items, which months, and what
each item actually made after what it cost to buy.

Everything here reads the invoice lines rather than the ledger, because the
ledger knows the amount and not the item. Cancelled vouchers are left out
throughout, and returns are netted off rather than listed apart, because a
customer who bought a lakh and sent half of it back did not buy a lakh.
"""

from ..core import money

# Which voucher types make up each side, and which way each pushes the total.
# Taken from the list the software itself uses rather than typed here again.
# A credit note reduces what a customer bought and a debit note reduces what
# was bought from a supplier, so both belong on their side.
SIDES = {
    "sales": {"out": ("sales",), "back": ("sales_return", "credit_note"),
              "party": "customer", "label": "Sales", "counterparty": "Customer"},
    "purchase": {"out": ("purchase",), "back": ("purchase_return", "debit_note"),
                 "party": "supplier", "label": "Purchase", "counterparty": "Supplier"},
}

POSTED = "status = 'posted'"


def _kinds(side):
    spec = SIDES[side]
    return spec["out"] + spec["back"], spec


def _sign_case(spec):
    """A return counts against the side it belongs to, not as its own figure."""
    back = ", ".join("'%s'" % kind for kind in spec["back"])
    return "CASE WHEN v.voucher_type IN (%s) THEN -1 ELSE 1 END" % back


def by_party(conn, side, from_ad, to_ad, monthly=False):
    """
    What each customer bought, or what was bought from each supplier.

    Net of returns. The count is of invoices rather than of lines, so a bill
    with eleven items on it is one bill.
    """
    if side not in SIDES:
        raise ValueError("side is sales or purchase")
    kinds, spec = _kinds(side)
    sign = _sign_case(spec)
    period = "substr(v.date_bs, 1, 7)" if monthly else "''"

    rows = conn.execute(
        """SELECT COALESCE(p.name, 'Cash and walk in') AS party,
                  p.id AS party_id,
                  %s AS period,
                  COUNT(DISTINCT v.id) AS bills,
                  SUM(%s * i.taxable_paisa) AS taxable,
                  SUM(%s * i.vat_paisa) AS vat,
                  SUM(%s * i.amount_paisa) AS amount,
                  SUM(%s * i.discount_paisa) AS discount
           FROM voucher_items i
           JOIN vouchers v ON v.id = i.voucher_id
           LEFT JOIN parties p ON p.id = v.party_id
           WHERE v.%s AND v.voucher_type IN (%s)
             AND v.date_ad >= ? AND v.date_ad <= ?
           GROUP BY p.id, period
           ORDER BY amount DESC""" % (
            period, sign, sign, sign, sign, POSTED,
            ", ".join("'%s'" % k for k in kinds)),
        (from_ad, to_ad)).fetchall()

    out = [dict(row) for row in rows]
    return {"side": side, "monthly": monthly, "rows": out,
            "counterparty": spec["counterparty"],
            "totals": _totals(out), "from_ad": from_ad, "to_ad": to_ad}


def by_item(conn, side, from_ad, to_ad, monthly=False):
    """
    What was sold or bought, item by item, in quantity and in money.

    Quantity is netted the same way as money, so a return takes the units back
    off as well. A line with no item on it, which is how a service or a one off
    charge is entered, is gathered under one heading rather than dropped.
    """
    if side not in SIDES:
        raise ValueError("side is sales or purchase")
    kinds, spec = _kinds(side)
    sign = _sign_case(spec)
    period = "substr(v.date_bs, 1, 7)" if monthly else "''"

    rows = conn.execute(
        """SELECT COALESCE(it.name, 'Not an item') AS item,
                  it.id AS item_id, it.code AS code, u.name AS unit,
                  %s AS period,
                  COUNT(DISTINCT v.id) AS bills,
                  SUM(%s * i.qty) AS qty,
                  SUM(%s * i.taxable_paisa) AS taxable,
                  SUM(%s * i.amount_paisa) AS amount,
                  SUM(%s * i.discount_paisa) AS discount
           FROM voucher_items i
           JOIN vouchers v ON v.id = i.voucher_id
           LEFT JOIN items it ON it.id = i.item_id
           LEFT JOIN units u ON u.id = COALESCE(i.unit_id, it.unit_id)
           WHERE v.%s AND v.voucher_type IN (%s)
             AND v.date_ad >= ? AND v.date_ad <= ?
           GROUP BY it.id, period
           ORDER BY amount DESC""" % (
            period, sign, sign, sign, sign, POSTED,
            ", ".join("'%s'" % k for k in kinds)),
        (from_ad, to_ad)).fetchall()

    out = []
    for row in rows:
        entry = dict(row)
        # A rate that comes out of dividing money by quantity is the only
        # honest average here: it is what was actually charged across the whole
        # period, not the rate on the item master.
        entry["average_rate"] = (money.round_half_up(entry["taxable"] * 1000, entry["qty"])
                                 if entry["qty"] else 0)
        out.append(entry)
    return {"side": side, "monthly": monthly, "rows": out,
            "totals": _totals(out), "from_ad": from_ad, "to_ad": to_ad}


def item_profitability(conn, from_ad, to_ad):
    """
    What each item earned, against what it cost to put on the shelf.

    The cost is the one carried on the sale itself, worked out at weighted
    average when the sale was made, rather than today's purchase price. Using
    today's price would move last year's profit every time something was
    bought, which is exactly what NAS 02 does not permit.

    An item with no cost on its lines is shown with the margin left blank
    rather than shown as pure profit, because a hundred percent margin on a
    missing figure is a lie a report should not tell.
    """
    rows = conn.execute(
        """SELECT COALESCE(it.name, 'Not an item') AS item,
                  it.id AS item_id, it.code AS code,
                  SUM(CASE WHEN v.voucher_type IN ('sales_return', 'credit_note')
                           THEN -1 ELSE 1 END * i.qty) AS qty,
                  SUM(CASE WHEN v.voucher_type IN ('sales_return', 'credit_note')
                           THEN -1 ELSE 1 END * i.taxable_paisa) AS revenue,
                  SUM(CASE WHEN v.voucher_type IN ('sales_return', 'credit_note')
                           THEN -1 ELSE 1 END * COALESCE(i.cost_paisa, 0)) AS cost,
                  SUM(CASE WHEN COALESCE(i.cost_paisa, 0) = 0 THEN 1 ELSE 0 END) AS no_cost
           FROM voucher_items i
           JOIN vouchers v ON v.id = i.voucher_id
           LEFT JOIN items it ON it.id = i.item_id
           WHERE v.%s AND v.voucher_type IN ('sales', 'sales_return', 'credit_note')
             AND v.date_ad >= ? AND v.date_ad <= ?
           GROUP BY it.id
           ORDER BY revenue DESC""" % POSTED,
        (from_ad, to_ad)).fetchall()

    out = []
    revenue_total = cost_total = 0
    missing_cost = False
    for row in rows:
        entry = dict(row)
        entry["profit"] = entry["revenue"] - entry["cost"]
        entry["known_cost"] = not entry["no_cost"]
        if not entry["known_cost"]:
            missing_cost = True
        entry["margin_bp"] = (money.round_half_up(entry["profit"] * 10000, entry["revenue"])
                              if entry["revenue"] and entry["known_cost"] else None)
        revenue_total += entry["revenue"]
        cost_total += entry["cost"]
        out.append(entry)

    profit = revenue_total - cost_total
    # The same rule as each line, and it has to be. Showing a hundred percent
    # at the foot because no cost was recorded is exactly the lie the lines
    # above are careful not to tell.
    margin = (money.round_half_up(profit * 10000, revenue_total)
              if revenue_total and not missing_cost else None)

    # Why this will not equal the profit and loss, said here rather than left
    # to be discovered. This report reads invoice lines, so it knows what was
    # billed. A discount allowed at the time of settlement is a decision taken
    # after the invoice and never touches a line, but it does reduce revenue.
    from . import reports
    settlement = _ledger_movement(conn, "4132", from_ad, to_ad)

    return {
        "rows": out, "from_ad": from_ad, "to_ad": to_ad,
        "totals": {"revenue": revenue_total, "cost": cost_total, "profit": profit,
                   "margin_bp": margin},
        "any_missing_cost": missing_cost,
        "settlement_discount": settlement,
        "revenue_after_settlement": revenue_total - settlement,
    }


def _ledger_movement(conn, code, from_ad, to_ad):
    """What one ledger took in over the period, nil where there is no such ledger."""
    from . import masters, reports
    account = masters.account_by_code(conn, code)
    if account is None:
        return 0
    dr, cr = reports.account_movements(conn, from_ad=from_ad, upto_ad=to_ad).get(
        account["id"], (0, 0))
    return dr - cr


def _totals(rows):
    """
    The bottom line of the report, with every column present.

    Always every column, even where there are no rows at all. A total that is
    simply absent because nothing was found makes the screen above it fall
    over, and a period with no sales in it is an ordinary thing to ask about.
    """
    keys = ("bills", "qty", "taxable", "vat", "amount", "discount")
    return {key: sum(row.get(key) or 0 for row in rows) for key in keys}

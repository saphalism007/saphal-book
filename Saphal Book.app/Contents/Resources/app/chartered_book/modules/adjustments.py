"""
Stock adjustments.

A physical count rarely agrees with the book to the last piece. Breakage,
pilferage, goods taken for the owner's own use, a miscount at the counter, all
of it has to be recorded rather than quietly absorbed, because a shortage that
disappears into cost of sales is exactly what an auditor is looking for.

Each adjustment moves the quantity in the stock ledger and posts the value at
weighted average cost, so the loss or the gain appears on its own line in the
profit and loss rather than inside the cost of goods sold.
"""

from ..core import money
from . import ledger, masters, reports

STOCK_ACCOUNT = "1211"
DEFAULT_LOSS = "7304"     # Stock Written Off and Shortage
DEFAULT_GAIN = "4209"     # Miscellaneous Income

REASONS = [
    ("shortage", "Shortage found on counting", -1, DEFAULT_LOSS),
    ("damage", "Damaged or broken", -1, DEFAULT_LOSS),
    ("expiry", "Expired or unsaleable", -1, DEFAULT_LOSS),
    ("own_use", "Taken for own use", -1, "3301"),
    ("sample", "Given as a sample or free issue", -1, "6302"),
    ("excess", "Excess found on counting", 1, DEFAULT_GAIN),
    ("opening", "Correcting an opening quantity", 1, DEFAULT_GAIN),
]

REASON_LOOKUP = {code: (label, direction, account) for code, label, direction, account in REASONS}


class AdjustmentError(Exception):
    """Raised when a stock adjustment cannot be made."""


def _account_id(conn, code, label):
    row = masters.account_by_code(conn, code)
    if row is None:
        raise AdjustmentError("The %s account (code %s) is missing." % (label, code))
    return row["id"]


def price_lines(conn, raw_lines, date_ad):
    """
    Work out what each adjustment line is worth.

    A decrease is valued at the weighted average the item is carried at on that
    date, because that is what is actually leaving. An increase is valued at the
    same rate where there is stock to average, and at the purchase rate where
    the item has none.
    """
    lines = []
    for index, raw in enumerate(raw_lines or [], start=1):
        item_id = raw.get("item_id")
        if not item_id:
            continue
        item = masters.get_item(conn, item_id)
        if item is None:
            raise AdjustmentError("Line %d refers to an item that no longer exists." % index)
        if not item["maintain_stock"] or item["item_type"] != "goods":
            raise AdjustmentError("%s is not something stock is kept for." % item["name"])

        qty = money.to_qty(raw.get("qty") or 0)
        if qty <= 0:
            raise AdjustmentError("Line %d needs a quantity greater than zero." % index)

        reason = raw.get("reason") or "shortage"
        if reason not in REASON_LOOKUP:
            raise AdjustmentError("Line %d has a reason that is not on the list." % index)
        label, direction, account_code = REASON_LOOKUP[reason]

        state = reports.item_stock(conn, item_id, date_ad)
        rate = state["average_rate"] or item["purchase_rate_paisa"]
        if raw.get("rate") not in (None, ""):
            rate = money.to_paisa(raw.get("rate"))
        value = money.round_half_up(qty * rate, money.QTY_SCALE)

        if direction < 0 and qty > state["qty"]:
            raise AdjustmentError(
                "Line %d takes %s of %s out, but only %s is on hand."
                % (index, money.format_qty(qty), item["name"], money.format_qty(state["qty"])))

        lines.append({
            "item_id": item_id, "item_code": item["code"], "item_name": item["name"],
            "unit_symbol": item["unit_symbol"] or "",
            "qty": qty, "direction": direction, "rate": rate, "value": value,
            "reason": reason, "reason_label": label,
            "account_code": raw.get("account_code") or account_code,
            "on_hand_before": state["qty"], "warehouse_id": raw.get("warehouse_id"),
            "note": (raw.get("note") or "").strip(),
        })
    if not lines:
        raise AdjustmentError("Add at least one line to the adjustment.")
    return lines


def build(conn, payload):
    """Turn the counted differences into a voucher the posting engine accepts."""
    date_ad = payload.get("date_ad")
    lines = price_lines(conn, payload.get("items"), date_ad)
    stock_account = _account_id(conn, STOCK_ACCOUNT, "stock in trade")

    by_account = {}
    stock_movement = 0
    for line in lines:
        signed = line["value"] * line["direction"]
        stock_movement += signed
        account_id = _account_id(conn, line["account_code"], "the adjustment account")
        by_account[account_id] = by_account.get(account_id, 0) - signed

    entries = []
    if stock_movement > 0:
        entries.append({"account_id": stock_account, "dr": money.to_rupees(stock_movement),
                        "cr": 0, "narration": "Stock found on counting"})
    elif stock_movement < 0:
        entries.append({"account_id": stock_account, "dr": 0,
                        "cr": money.to_rupees(-stock_movement),
                        "narration": "Stock written down on counting"})

    for account_id, amount in by_account.items():
        if amount > 0:
            entries.append({"account_id": account_id, "dr": money.to_rupees(amount), "cr": 0,
                            "narration": ""})
        elif amount < 0:
            entries.append({"account_id": account_id, "dr": 0, "cr": money.to_rupees(-amount),
                            "narration": ""})

    if len(entries) < 2:
        raise AdjustmentError("The adjustment comes to nothing, so there is nothing to post.")

    return {
        "voucher_type": "stock_adjust",
        "date_ad": date_ad,
        "number": payload.get("number"),
        "reference_no": payload.get("reference_no", ""),
        "narration": payload.get("narration") or "Stock adjustment on counting",
        "status": payload.get("status", "posted"),
        "total_paisa": abs(stock_movement),
        "entries": entries,
        "items": [{
            "item_id": line["item_id"],
            "description": line["reason_label"] + (("  " + line["note"]) if line["note"] else ""),
            "warehouse_id": line["warehouse_id"],
            "qty": money.qty_value(line["qty"]),
            "rate": money.to_rupees(line["rate"]),
            "direction": line["direction"],
            "vat_bp": 0,
        } for line in lines],
        "computed": {"lines": lines, "stock_movement": stock_movement},
    }


def post(conn, username, payload):
    return ledger.post_voucher(conn, username, build(conn, payload))

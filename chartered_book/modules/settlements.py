"""
Receiving and paying against bills, with the discount that goes with it.

A customer who settles early is usually allowed something off. A supplier paid
early usually allows something back. That is a settlement discount, and it is
not the same thing as the trade discount taken off an invoice line: it arises
after the invoice, it depends on when the money moves, and it belongs on the
receipt or the payment rather than on the invoice.

    Receipt   debit the bank with what came in
              debit Discount Allowed with what was given up
              credit the customer with the whole bill that is now settled

    Payment   debit the supplier with the whole bill now settled
              credit the bank with what went out
              credit Discount on Purchase with what was allowed back

Which bill each amount is set against is recorded, so a statement of account
shows what is still open rather than one running balance.
"""

from ..core import money
from . import ledger, masters, reports

# Neither of these is an expense or an income in its own right. Discount
# Allowed sits under Revenue as a deduction, which is where NFRS 15 puts a
# reduction in the consideration a customer pays. Discount on Purchase sits
# under Purchases as a deduction, because NAS 02 measures the cost of purchase
# after trade discounts and rebates. Putting a supplier discount into other
# income instead would lift both gross profit and closing stock above cost.
DISCOUNT_ALLOWED = "4132"     # taken off what customers owe
DISCOUNT_RECEIVED = "5105"    # allowed back by suppliers


class SettlementError(Exception):
    """Raised when a receipt or a payment cannot be built."""


def _account_id(conn, code, label):
    row = masters.account_by_code(conn, code)
    if row is None:
        raise SettlementError("The %s account (code %s) is missing." % (label, code))
    return row["id"]


def open_bills(conn, party_id, side, as_at_ad):
    """
    The bills still open for one party, oldest first.

    Built the same way the ageing report builds them, so the two can never
    disagree: invoices in date order, with receipts already set against them
    knocked off the oldest first.
    """
    party = masters.get_party(conn, party_id)
    if party is None or not party["account_id"]:
        raise SettlementError("That party has no ledger account.")
    ageing = reports.ageing(conn, side, as_at_ad)
    for row in ageing["rows"]:
        if row["account_id"] == party["account_id"]:
            bills = [dict(item) for item in row["details"] if item["amount"] > 0]
            return {"party": dict(party), "account_id": party["account_id"],
                    "bills": bills, "total": row["total"],
                    "credit_days": row["credit_days"]}
    return {"party": dict(party), "account_id": party["account_id"],
            "bills": [], "total": 0, "credit_days": party["credit_days"]}


def build(conn, payload, kind):
    """
    Turn what was collected on the screen into a voucher.

    kind is 'receipt' for money coming in or 'payment' for money going out.
    """
    if kind not in ("receipt", "payment"):
        raise SettlementError("This is either a receipt or a payment.")
    is_receipt = kind == "receipt"

    party_id = payload.get("party_id")
    if not party_id:
        raise SettlementError("Choose the %s."
                              % ("customer" if is_receipt else "supplier"))
    party = masters.get_party(conn, party_id)
    if party is None or not party["account_id"]:
        raise SettlementError("That party has no ledger account.")

    bank_account = payload.get("bank_account_id")
    if not bank_account:
        raise SettlementError("Choose the cash box or bank account the money moves through.")

    allocations = []
    settled = 0
    discount = 0
    for index, row in enumerate(payload.get("allocations") or [], start=1):
        amount = money.to_paisa(row.get("amount") or 0)
        line_discount = money.to_paisa(row.get("discount") or 0)
        if amount == 0 and line_discount == 0:
            continue
        if amount < 0 or line_discount < 0:
            raise SettlementError("Line %d cannot be a negative amount." % index)
        allocations.append({
            "against_voucher_id": row.get("voucher_id") or None,
            "bill_reference": (row.get("number") or "").strip(),
            "amount": amount, "discount": line_discount,
        })
        settled += amount
        discount += line_discount

    on_account = money.to_paisa(payload.get("on_account") or 0)
    if on_account < 0:
        raise SettlementError("An amount on account cannot be negative.")

    received = settled + on_account
    if received == 0 and discount == 0:
        raise SettlementError("Nothing has been entered to receive or pay.")

    party_total = received + discount

    discount_account = payload.get("discount_account_id")
    if discount and not discount_account:
        discount_account = _account_id(
            conn, DISCOUNT_ALLOWED if is_receipt else DISCOUNT_RECEIVED,
            "discount allowed" if is_receipt else "discount received")

    entries = []
    if is_receipt:
        if received:
            entries.append({"account_id": bank_account, "dr": money.to_rupees(received),
                            "cr": 0, "narration": ""})
        if discount:
            entries.append({"account_id": discount_account, "dr": money.to_rupees(discount),
                            "cr": 0, "narration": "Discount allowed on early settlement"})
        entries.append({"account_id": party["account_id"], "dr": 0,
                        "cr": money.to_rupees(party_total), "narration": ""})
    else:
        entries.append({"account_id": party["account_id"],
                        "dr": money.to_rupees(party_total), "cr": 0, "narration": ""})
        if received:
            entries.append({"account_id": bank_account, "dr": 0,
                            "cr": money.to_rupees(received), "narration": ""})
        if discount:
            entries.append({"account_id": discount_account, "dr": 0,
                            "cr": money.to_rupees(discount),
                            "narration": "Discount received on early settlement"})

    voucher_allocations = []
    for row in allocations:
        voucher_allocations.append({
            "account_id": party["account_id"],
            "against_voucher_id": row["against_voucher_id"],
            "bill_reference": row["bill_reference"],
            "allocation_type": "against",
            "amount": money.to_rupees(row["amount"] + row["discount"]),
        })
    if on_account:
        voucher_allocations.append({
            "account_id": party["account_id"], "against_voucher_id": None,
            "bill_reference": "", "allocation_type": "on_account",
            "amount": money.to_rupees(on_account),
        })

    return {
        "voucher_type": kind,
        "date_ad": payload.get("date_ad"),
        "number": payload.get("number"),
        "party_id": party_id,
        "reference_no": (payload.get("reference_no") or "").strip(),
        "payment_mode": payload.get("payment_mode", ""),
        "narration": payload.get("narration", ""),
        "status": payload.get("status", "posted"),
        "discount_paisa": discount,
        "total_paisa": party_total,
        "entries": entries,
        "allocations": voucher_allocations,
        "summary": {"received": received, "discount": discount,
                    "settled": settled, "on_account": on_account,
                    "party_total": party_total},
    }


def post(conn, username, payload, kind):
    return ledger.post_voucher(conn, username, build(conn, payload, kind))


def statement_of_account(conn, party_id, from_ad, to_ad):
    """
    A statement to send a customer, or to check against a supplier's.

    Every invoice, receipt, note and adjustment in date order with a running
    balance, and what is still open at the end broken down by bill.
    """
    party = masters.get_party(conn, party_id)
    if party is None or not party["account_id"]:
        raise SettlementError("That party has no ledger account.")
    ledger_view = reports.ledger_statement(conn, party["account_id"], from_ad, to_ad)
    side = "payable" if party["party_type"] == "supplier" else "receivable"
    outstanding = open_bills(conn, party_id, side, to_ad)
    return {
        "party": dict(party),
        "side": side,
        "opening": ledger_view["opening"],
        "lines": ledger_view["lines"],
        "total_dr": ledger_view["total_dr"],
        "total_cr": ledger_view["total_cr"],
        "closing": ledger_view["closing"],
        "open_bills": outstanding["bills"],
        "from_ad": from_ad, "to_ad": to_ad,
    }

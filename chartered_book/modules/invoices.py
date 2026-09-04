"""
Sales and purchase invoices.

The screen collects item lines. This module turns those lines into a set of
double entries that balances to the paisa, applies VAT the way the Value Added
Tax Act, 2052 requires it to appear, and hands the result to the posting engine.

Nepal uses a periodic inventory system in most trading houses and that is what
is followed here. A sales invoice does not post cost of goods sold. Stock is
tracked in quantity and value in the stock ledger, and the closing stock entry
at period end brings the value into the accounts. This is what an audit in
Nepal expects to see and it stays correct when a backdated invoice is entered.
"""

from ..core import money
from . import ledger, masters

DEFAULT_ACCOUNTS = {
    "sales_taxable": "4111",
    "sales_exempt": "4112",
    "sales_return": "4131",
    "purchase_taxable": "5101",
    "purchase_exempt": "5102",
    "purchase_return": "5104",
    "vat_output": "2241",
    "vat_input": "1241",
    "cash": "1251",
    "round_off": "7305",
    "discount_allowed": "4132",
    "service_income": "4121",
}


class InvoiceError(Exception):
    """Raised when an invoice cannot be built."""


def _account_id(conn, code, label):
    row = masters.account_by_code(conn, code)
    if row is None:
        raise InvoiceError(
            "The %s account (code %s) is missing from the chart of accounts." % (label, code))
    return row["id"]


def compute_lines(conn, raw_items, price_includes_vat=False, bill_discount=0,
                  bill_discount_bp=0):
    """
    Work out every figure on an invoice line.

    Returns the priced lines plus the totals the header needs. Rounding happens
    once per line, so the sum of the lines always equals the invoice total and
    the customer copy agrees with the ledger to the paisa.

    A discount given on the bill as a whole is spread back over the lines in
    proportion to what each line is worth. It has to be, for three reasons that
    all matter. Value added tax is charged on the discounted consideration, so
    the tax cannot be worked out until each line knows its share. Goods come
    into stock at what they cost after the discount, so the weighted average is
    wrong unless the share reaches the line. And where a bill carries both
    taxable and exempt goods, only the taxable share may reduce the tax.
    """
    lines = []
    for index, raw in enumerate(raw_items or [], start=1):
        item_id = raw.get("item_id")
        if not item_id:
            continue
        item = masters.get_item(conn, item_id)
        if item is None:
            raise InvoiceError("Line %d refers to an item that no longer exists." % index)
        qty = money.to_qty(raw.get("qty") or 0)
        if qty <= 0:
            raise InvoiceError("Line %d needs a quantity greater than zero." % index)
        rate = money.to_paisa(raw.get("rate") if raw.get("rate") not in (None, "")
                              else item["sale_rate_paisa"])
        vat_bp = int(raw.get("vat_bp") if raw.get("vat_bp") is not None else item["vat_rate_bp"])
        if not item["vat_applicable"]:
            vat_bp = 0

        if price_includes_vat and vat_bp:
            # The counter quoted a price with tax in it. Work backwards.
            gross_incl = money.round_half_up(qty * rate, money.QTY_SCALE)
            gross, _ = money.extract_from_inclusive(gross_incl, vat_bp)
        else:
            gross = money.round_half_up(qty * rate, money.QTY_SCALE)

        line_discount_bp = int(raw.get("discount_bp") or 0)
        if raw.get("discount") not in (None, ""):
            discount = money.to_paisa(raw.get("discount"))
        else:
            discount = money.apply_rate(gross, line_discount_bp)
        if discount > gross:
            raise InvoiceError("Line %d has a discount larger than the line amount." % index)

        lines.append({
            "item_id": item_id,
            "item_code": item["code"],
            "item_name": item["name"],
            "item_type": item["item_type"],
            "description": raw.get("description") or "",
            "warehouse_id": raw.get("warehouse_id"),
            "unit_id": raw.get("unit_id") or item["unit_id"],
            "unit_symbol": item["unit_symbol"] or "",
            "qty": qty,
            "free_qty": money.to_qty(raw.get("free_qty") or 0),
            "rate": rate,
            "gross": gross,
            "discount_bp": line_discount_bp,
            "discount": discount,
            "bill_discount": 0,
            "taxable": gross - discount,
            "vat_bp": vat_bp,
            "vat": 0,
            "amount": 0,
            "batch": raw.get("batch") or "",
            "expiry_ad": raw.get("expiry_ad") or "",
            "sales_account_id": item["sales_account_id"],
            "purchase_account_id": item["purchase_account_id"],
        })

    if not lines:
        raise InvoiceError("Add at least one line to the invoice.")

    after_line_discount = sum(line["taxable"] for line in lines)
    if bill_discount in (None, ""):
        bill_discount = 0
    bill_total = int(bill_discount) if bill_discount else money.apply_rate(
        after_line_discount, int(bill_discount_bp or 0))
    if bill_total < 0:
        raise InvoiceError("A discount on the bill cannot be a negative figure.")
    if bill_total > after_line_discount:
        raise InvoiceError(
            "The discount on the bill is %s, which is more than the %s the lines come to."
            % (money.format_money(bill_total), money.format_money(after_line_discount)))

    if bill_total:
        shares = money.allocate(bill_total, [line["taxable"] for line in lines])
        for line, share in zip(lines, shares):
            line["bill_discount"] = share
            line["taxable"] -= share

    subtotal = discount_total = taxable_total = exempt_total = vat_total = 0
    for line in lines:
        line["vat"] = money.apply_rate(line["taxable"], line["vat_bp"])
        line["amount"] = line["taxable"] + line["vat"]
        subtotal += line["gross"]
        discount_total += line["discount"] + line["bill_discount"]
        if line["vat_bp"]:
            taxable_total += line["taxable"]
        else:
            exempt_total += line["taxable"]
        vat_total += line["vat"]

    return {
        "lines": lines,
        "subtotal": subtotal,
        "line_discount": discount_total - bill_total,
        "bill_discount": bill_total,
        "discount": discount_total,
        "taxable": taxable_total,
        "exempt": exempt_total,
        "vat": vat_total,
        "net": taxable_total + exempt_total + vat_total,
    }


def price_voucher(conn, payload):
    """Price the lines of a voucher, including any discount on the whole bill."""
    return compute_lines(
        conn, payload.get("items"), bool(payload.get("price_includes_vat")),
        money.to_paisa(payload.get("bill_discount")) if payload.get("bill_discount")
        not in (None, "") else 0,
        int(payload.get("bill_discount_bp") or 0))


def _round_off(amount, enabled):
    """Round an invoice to the nearest rupee and report the adjustment."""
    if not enabled:
        return amount, 0
    remainder = amount % 100
    if remainder == 0:
        return amount, 0
    rounded = amount - remainder + (100 if remainder >= 50 else 0)
    return rounded, rounded - amount


def build_sales(conn, payload):
    """Assemble a sales invoice ready for the posting engine."""
    totals = price_voucher(conn, payload)
    other_charges = money.to_paisa(payload.get("other_charges") or 0)
    tds = money.to_paisa(payload.get("tds") or 0)
    gross_total = totals["net"] + other_charges
    total, round_off = _round_off(gross_total, payload.get("round_invoice", True))
    receivable = total - tds

    is_cash = str(payload.get("payment_mode") or "").lower() in ("cash", "counter")
    if is_cash:
        debit_account = payload.get("cash_account_id") or _account_id(conn, DEFAULT_ACCOUNTS["cash"], "cash")
    else:
        party_id = payload.get("party_id")
        if not party_id:
            raise InvoiceError("Choose a customer, or mark the invoice as a cash sale.")
        party = masters.get_party(conn, party_id)
        if party is None or not party["account_id"]:
            raise InvoiceError("That customer has no ledger account.")
        debit_account = party["account_id"]

    entries = [{"account_id": debit_account, "dr": money.to_rupees(receivable), "cr": 0,
                "narration": ""}]
    if tds:
        entries.append({"account_id": payload.get("tds_account_id")
                        or _account_id(conn, "1244", "TDS receivable"),
                        "dr": money.to_rupees(tds), "cr": 0,
                        "narration": "Tax deducted at source by the customer"})

    # Credit each line to its own income account so the profit and loss shows
    # goods and services separately without any extra work.
    by_account = {}
    for line in totals["lines"]:
        account_id = line["sales_account_id"]
        if not account_id:
            code = DEFAULT_ACCOUNTS["sales_taxable"] if line["vat_bp"] else DEFAULT_ACCOUNTS["sales_exempt"]
            if line["item_type"] == "service":
                code = DEFAULT_ACCOUNTS["service_income"]
            account_id = _account_id(conn, code, "sales")
        by_account[account_id] = by_account.get(account_id, 0) + line["taxable"]
    for account_id, amount in by_account.items():
        if amount:
            entries.append({"account_id": account_id, "dr": 0, "cr": money.to_rupees(amount),
                            "narration": ""})

    if totals["vat"]:
        entries.append({"account_id": _account_id(conn, DEFAULT_ACCOUNTS["vat_output"], "VAT output"),
                        "dr": 0, "cr": money.to_rupees(totals["vat"]),
                        "narration": "Value added tax on sales"})
    if other_charges:
        entries.append({"account_id": payload.get("other_charges_account_id")
                        or _account_id(conn, "4209", "other income"),
                        "dr": 0, "cr": money.to_rupees(other_charges), "narration": "Other charges"})
    if round_off:
        account = _account_id(conn, DEFAULT_ACCOUNTS["round_off"], "rounding")
        if round_off > 0:
            entries.append({"account_id": account, "dr": 0, "cr": money.to_rupees(round_off),
                            "narration": "Rounding"})
        else:
            entries.append({"account_id": account, "dr": money.to_rupees(-round_off), "cr": 0,
                            "narration": "Rounding"})

    return {
        "voucher_type": payload.get("voucher_type", "sales"),
        "date_ad": payload.get("date_ad"),
        "number": payload.get("number"),
        "party_id": None if is_cash else payload.get("party_id"),
        "reference_no": payload.get("reference_no", ""),
        "due_date_ad": payload.get("due_date_ad", ""),
        "payment_mode": payload.get("payment_mode", ""),
        "narration": payload.get("narration", ""),
        "status": payload.get("status", "posted"),
        "subtotal": money.to_rupees(totals["subtotal"]),
        "discount": money.to_rupees(totals["discount"]),
        "bill_discount": money.to_rupees(totals["bill_discount"]),
        "taxable": money.to_rupees(totals["taxable"]),
        "exempt": money.to_rupees(totals["exempt"]),
        "vat": money.to_rupees(totals["vat"]),
        "other_charges": money.to_rupees(other_charges),
        "tds": money.to_rupees(tds),
        "round_off": money.to_rupees(round_off),
        "total_paisa": total,
        "is_vat_invoice": 1 if totals["vat"] else 0,
        "entries": entries,
        "items": [_item_row(line) for line in totals["lines"]],
        "computed": totals,
    }


def build_purchase(conn, payload):
    """Assemble a purchase invoice ready for the posting engine."""
    totals = price_voucher(conn, payload)
    other_charges = money.to_paisa(payload.get("other_charges") or 0)
    tds = money.to_paisa(payload.get("tds") or 0)
    gross_total = totals["net"] + other_charges
    total, round_off = _round_off(gross_total, payload.get("round_invoice", True))
    payable = total - tds

    is_cash = str(payload.get("payment_mode") or "").lower() in ("cash", "counter")
    if is_cash:
        credit_account = payload.get("cash_account_id") or _account_id(conn, DEFAULT_ACCOUNTS["cash"], "cash")
    else:
        party_id = payload.get("party_id")
        if not party_id:
            raise InvoiceError("Choose a supplier, or mark the purchase as a cash purchase.")
        party = masters.get_party(conn, party_id)
        if party is None or not party["account_id"]:
            raise InvoiceError("That supplier has no ledger account.")
        credit_account = party["account_id"]

    entries = []
    by_account = {}
    for line in totals["lines"]:
        account_id = line["purchase_account_id"]
        if not account_id:
            code = DEFAULT_ACCOUNTS["purchase_taxable"] if line["vat_bp"] else DEFAULT_ACCOUNTS["purchase_exempt"]
            account_id = _account_id(conn, code, "purchase")
        by_account[account_id] = by_account.get(account_id, 0) + line["taxable"]
    for account_id, amount in by_account.items():
        if amount:
            entries.append({"account_id": account_id, "dr": money.to_rupees(amount), "cr": 0,
                            "narration": ""})

    if totals["vat"]:
        entries.append({"account_id": _account_id(conn, DEFAULT_ACCOUNTS["vat_input"], "VAT input"),
                        "dr": money.to_rupees(totals["vat"]), "cr": 0,
                        "narration": "Value added tax on purchases"})
    if other_charges:
        entries.append({"account_id": payload.get("other_charges_account_id")
                        or _account_id(conn, "5202", "freight"),
                        "dr": money.to_rupees(other_charges), "cr": 0, "narration": "Other charges"})
    if round_off:
        account = _account_id(conn, DEFAULT_ACCOUNTS["round_off"], "rounding")
        if round_off > 0:
            entries.append({"account_id": account, "dr": money.to_rupees(round_off), "cr": 0,
                            "narration": "Rounding"})
        else:
            entries.append({"account_id": account, "dr": 0, "cr": money.to_rupees(-round_off),
                            "narration": "Rounding"})

    entries.append({"account_id": credit_account, "dr": 0, "cr": money.to_rupees(payable),
                    "narration": ""})
    if tds:
        entries.append({"account_id": payload.get("tds_account_id")
                        or _account_id(conn, "2253", "TDS payable"),
                        "dr": 0, "cr": money.to_rupees(tds),
                        "narration": "Tax deducted at source on this payment"})

    return {
        "voucher_type": payload.get("voucher_type", "purchase"),
        "date_ad": payload.get("date_ad"),
        "number": payload.get("number"),
        "party_id": None if is_cash else payload.get("party_id"),
        "reference_no": payload.get("reference_no", ""),
        "reference_date_ad": payload.get("reference_date_ad", ""),
        "due_date_ad": payload.get("due_date_ad", ""),
        "payment_mode": payload.get("payment_mode", ""),
        "narration": payload.get("narration", ""),
        "status": payload.get("status", "posted"),
        "subtotal": money.to_rupees(totals["subtotal"]),
        "discount": money.to_rupees(totals["discount"]),
        "bill_discount": money.to_rupees(totals["bill_discount"]),
        "taxable": money.to_rupees(totals["taxable"]),
        "exempt": money.to_rupees(totals["exempt"]),
        "vat": money.to_rupees(totals["vat"]),
        "other_charges": money.to_rupees(other_charges),
        "tds": money.to_rupees(tds),
        "round_off": money.to_rupees(round_off),
        "total_paisa": total,
        "is_vat_invoice": 1 if totals["vat"] else 0,
        "entries": entries,
        "items": [_item_row(line) for line in totals["lines"]],
        "computed": totals,
    }


def _item_row(line):
    return {
        "item_id": line["item_id"],
        "description": line["description"],
        "warehouse_id": line["warehouse_id"],
        "unit_id": line["unit_id"],
        "qty": money.qty_value(line["qty"]),
        "free_qty": money.qty_value(line["free_qty"]),
        "rate": money.to_rupees(line["rate"]),
        "discount_bp": line["discount_bp"],
        "discount": money.to_rupees(line["discount"]),
        "bill_discount": money.to_rupees(line["bill_discount"]),
        "vat_bp": line["vat_bp"],
        "batch": line["batch"],
        "expiry_ad": line["expiry_ad"],
    }


def post_sales(conn, username, payload):
    return ledger.post_voucher(conn, username, build_sales(conn, payload))


def post_purchase(conn, username, payload):
    return ledger.post_voucher(conn, username, build_purchase(conn, payload))


# Returns and notes
#
# A return sends goods back and reverses the tax that went with them. A note
# changes the price without any goods moving, which is what a rate difference,
# a shortage in delivery or an allowance after the event amounts to.
#
# Under the Value Added Tax Act, 2052 the tax on a return or an allowance is
# adjusted in the month the credit or debit note is issued, so each of these is
# a voucher in its own right with its own number, not an edit of the original.


def build_sales_return(conn, payload):
    """
    Goods coming back from a customer.

    Debit Sales Return, debit the output tax back out of the VAT account, and
    credit the customer. The goods go back into stock.
    """
    totals = price_voucher(conn, payload)
    total = totals["net"]
    party_id = payload.get("party_id")
    is_cash = str(payload.get("payment_mode") or "").lower() in ("cash", "counter")
    if is_cash:
        credit_account = payload.get("cash_account_id") or _account_id(
            conn, DEFAULT_ACCOUNTS["cash"], "cash")
    else:
        if not party_id:
            raise InvoiceError("Choose the customer the goods came back from.")
        party = masters.get_party(conn, party_id)
        if party is None or not party["account_id"]:
            raise InvoiceError("That customer has no ledger account.")
        credit_account = party["account_id"]

    entries = [{"account_id": payload.get("return_account_id")
                or _account_id(conn, DEFAULT_ACCOUNTS["sales_return"], "sales return"),
                "dr": money.to_rupees(totals["taxable"] + totals["exempt"]), "cr": 0,
                "narration": "Goods returned by the customer"}]
    if totals["vat"]:
        entries.append({"account_id": _account_id(conn, DEFAULT_ACCOUNTS["vat_output"],
                                                  "VAT output"),
                        "dr": money.to_rupees(totals["vat"]), "cr": 0,
                        "narration": "Output tax reversed on the return"})
    entries.append({"account_id": credit_account, "dr": 0, "cr": money.to_rupees(total),
                    "narration": ""})

    return _wrap(payload, "sales_return", totals, total, entries, is_cash)


def build_purchase_return(conn, payload):
    """
    Goods going back to a supplier.

    Debit the supplier, credit Purchase Return, and take the input tax back out.
    The goods leave stock.
    """
    totals = price_voucher(conn, payload)
    total = totals["net"]
    party_id = payload.get("party_id")
    is_cash = str(payload.get("payment_mode") or "").lower() in ("cash", "counter")
    if is_cash:
        debit_account = payload.get("cash_account_id") or _account_id(
            conn, DEFAULT_ACCOUNTS["cash"], "cash")
    else:
        if not party_id:
            raise InvoiceError("Choose the supplier the goods went back to.")
        party = masters.get_party(conn, party_id)
        if party is None or not party["account_id"]:
            raise InvoiceError("That supplier has no ledger account.")
        debit_account = party["account_id"]

    entries = [{"account_id": debit_account, "dr": money.to_rupees(total), "cr": 0,
                "narration": ""}]
    entries.append({"account_id": payload.get("return_account_id")
                    or _account_id(conn, DEFAULT_ACCOUNTS["purchase_return"], "purchase return"),
                    "dr": 0, "cr": money.to_rupees(totals["taxable"] + totals["exempt"]),
                    "narration": "Goods returned to the supplier"})
    if totals["vat"]:
        entries.append({"account_id": _account_id(conn, DEFAULT_ACCOUNTS["vat_input"],
                                                  "VAT input"),
                        "dr": 0, "cr": money.to_rupees(totals["vat"]),
                        "narration": "Input tax reversed on the return"})

    return _wrap(payload, "purchase_return", totals, total, entries, is_cash)


def _wrap(payload, voucher_type, totals, total, entries, is_cash):
    return {
        "voucher_type": voucher_type,
        "date_ad": payload.get("date_ad"),
        "number": payload.get("number"),
        "party_id": None if is_cash else payload.get("party_id"),
        "reference_no": payload.get("reference_no", ""),
        "reference_date_ad": payload.get("reference_date_ad", ""),
        "payment_mode": payload.get("payment_mode", ""),
        "narration": payload.get("narration", ""),
        "status": payload.get("status", "posted"),
        "subtotal": money.to_rupees(totals["subtotal"]),
        "discount": money.to_rupees(totals["discount"]),
        "bill_discount": money.to_rupees(totals["bill_discount"]),
        "taxable": money.to_rupees(totals["taxable"]),
        "exempt": money.to_rupees(totals["exempt"]),
        "vat": money.to_rupees(totals["vat"]),
        "total_paisa": total,
        "is_vat_invoice": 1 if totals["vat"] else 0,
        "entries": entries,
        "items": [_item_row(line) for line in totals["lines"]],
        "computed": totals,
    }


def build_note(conn, payload, kind):
    """
    A credit note to a customer, or a debit note to a supplier, where no goods
    move. Used for a rate difference, a discount agreed after the invoice, a
    shortage in a delivery, or a claim.

    The amount and the tax on it are entered directly, because there is nothing
    to price from a stock list.
    """
    if kind not in ("credit_note", "debit_note"):
        raise InvoiceError("A note is either a credit note or a debit note.")
    is_credit = kind == "credit_note"

    amount = money.to_paisa(payload.get("amount") or 0)
    if amount <= 0:
        raise InvoiceError("Enter the amount of the note.")
    vat_bp = int(payload.get("vat_bp") if payload.get("vat_bp") is not None else 0)
    vat = money.apply_rate(amount, vat_bp)
    total = amount + vat

    party_id = payload.get("party_id")
    if not party_id:
        raise InvoiceError("Choose the %s the note is for."
                           % ("customer" if is_credit else "supplier"))
    party = masters.get_party(conn, party_id)
    if party is None or not party["account_id"]:
        raise InvoiceError("That party has no ledger account.")

    other_account = payload.get("account_id")
    if not other_account:
        other_account = _account_id(
            conn, DEFAULT_ACCOUNTS["discount_allowed"] if is_credit else "5105",
            "the account the note goes to")

    if is_credit:
        # Less is owed by the customer.
        entries = [{"account_id": other_account, "dr": money.to_rupees(amount), "cr": 0,
                    "narration": payload.get("reason", "")}]
        if vat:
            entries.append({"account_id": _account_id(conn, DEFAULT_ACCOUNTS["vat_output"],
                                                      "VAT output"),
                            "dr": money.to_rupees(vat), "cr": 0,
                            "narration": "Output tax adjusted"})
        entries.append({"account_id": party["account_id"], "dr": 0,
                        "cr": money.to_rupees(total), "narration": ""})
    else:
        # Less is owed to the supplier.
        entries = [{"account_id": party["account_id"], "dr": money.to_rupees(total), "cr": 0,
                    "narration": ""}]
        entries.append({"account_id": other_account, "dr": 0, "cr": money.to_rupees(amount),
                        "narration": payload.get("reason", "")})
        if vat:
            entries.append({"account_id": _account_id(conn, DEFAULT_ACCOUNTS["vat_input"],
                                                      "VAT input"),
                            "dr": 0, "cr": money.to_rupees(vat),
                            "narration": "Input tax adjusted"})

    return {
        "voucher_type": kind,
        "date_ad": payload.get("date_ad"),
        "number": payload.get("number"),
        "party_id": party_id,
        "reference_no": payload.get("reference_no", ""),
        "reference_date_ad": payload.get("reference_date_ad", ""),
        "narration": payload.get("narration") or payload.get("reason", ""),
        "status": payload.get("status", "posted"),
        "taxable": money.to_rupees(amount if vat_bp else 0),
        "exempt": money.to_rupees(0 if vat_bp else amount),
        "vat": money.to_rupees(vat),
        "total_paisa": total,
        "is_vat_invoice": 1 if vat else 0,
        "entries": entries,
        "items": [],
    }


def post_sales_return(conn, username, payload):
    return ledger.post_voucher(conn, username, build_sales_return(conn, payload))


def post_purchase_return(conn, username, payload):
    return ledger.post_voucher(conn, username, build_purchase_return(conn, payload))


def post_note(conn, username, payload, kind):
    return ledger.post_voucher(conn, username, build_note(conn, payload, kind))

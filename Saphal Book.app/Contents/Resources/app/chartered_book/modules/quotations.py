"""
What was offered, before anybody agreed to it.

A quotation is a promise about a price. Nothing has been sold, no tax is due
and no stock has moved, so it is not an entry in the books and does not go near
them. It becomes an invoice, and an entry, only when the customer says yes.

The one thing it must not do is price differently from the invoice it turns
into. A quotation saying one figure and an invoice saying another is worse than
having no quotations at all, so both go through the same pricing: the same
discount rules, the same tax, the same rounding. The figures are kept here as
well, but only so that an old quotation still reads as it did on the day it was
sent, rather than quietly re-pricing itself when somebody changes an item's
rate six months later.

Turning one into an invoice happens once. A quotation already invoiced is
refused rather than allowed to make a second one, because two invoices for the
same job is a conversation nobody wants to have with a customer.
"""

import datetime

from ..core import audit, money, nepali_date as nd
from . import invoices, masters

OPEN = "open"
ACCEPTED = "accepted"
DECLINED = "declined"
INVOICED = "invoiced"

STATUS = {
    OPEN: "Open",
    ACCEPTED: "Accepted",
    DECLINED: "Declined",
    INVOICED: "Turned into an invoice",
}


class QuotationError(Exception):
    """Raised when a quotation cannot be made or used."""


def _now():
    from ..core import db
    return db.now_stamp()


def next_number(conn):
    """The next quotation number, following the same shape as a voucher's."""
    row = conn.execute(
        "SELECT number FROM quotations ORDER BY id DESC LIMIT 1").fetchone()
    if row is None:
        return "QT0001"
    digits = "".join(ch for ch in row["number"] if ch.isdigit())
    try:
        return "QT%04d" % (int(digits) + 1)
    except ValueError:
        return "QT%04d" % (conn.execute(
            "SELECT COUNT(*) n FROM quotations").fetchone()["n"] + 1)


def price(conn, payload):
    """
    What this quotation comes to, priced exactly as the invoice would be.

    The same call the invoice screen makes, so the two cannot drift.
    """
    totals = invoices.price_voucher(conn, payload)
    other = money.to_paisa(payload.get("other_charges") or 0)
    gross = totals["net"] + other
    total = gross
    if payload.get("round_invoice", True):
        remainder = gross % 100
        if remainder:
            total = gross - remainder + (100 if remainder >= 50 else 0)
    totals = dict(totals)
    totals["other_charges"] = other
    totals["round_off"] = total - gross
    totals["total"] = total
    return totals


def create(conn, username, payload):
    """Write one quotation. Nothing reaches the books."""
    party_id = payload.get("party_id")
    party_name = (payload.get("party_name") or "").strip()
    if party_id:
        party = masters.get_party(conn, party_id)
        if party is None:
            raise QuotationError("That customer is not on the list.")
        party_name = party["name"]
    if not party_name:
        raise QuotationError("Say who it is for.")

    if not (payload.get("items") or []):
        raise QuotationError("A quotation needs at least one line.")

    totals = price(conn, payload)
    date_ad = payload.get("date_ad") or datetime.date.today().isoformat()
    try:
        date_bs = nd.format_bs(nd.ad_to_bs(date_ad), "numeric")
    except Exception:                                               # noqa: BLE001
        date_bs = ""

    number = (payload.get("number") or "").strip() or next_number(conn)
    if conn.execute("SELECT id FROM quotations WHERE number = ?", (number,)).fetchone():
        raise QuotationError("There is already a quotation numbered %s." % number)

    cursor = conn.execute(
        """INSERT INTO quotations
           (number, date_ad, date_bs, valid_until_ad, party_id, party_name,
            narration, terms, price_includes_vat, bill_discount_paisa,
            other_charges_paisa, subtotal_paisa, discount_paisa, taxable_paisa,
            exempt_paisa, vat_paisa, total_paisa, status, created_by,
            created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (number, date_ad, date_bs, payload.get("valid_until_ad") or "",
         party_id or None, party_name,
         (payload.get("narration") or "").strip()[:300],
         (payload.get("terms") or "").strip()[:600],
         1 if payload.get("price_includes_vat") else 0,
         totals["bill_discount"], totals["other_charges"],
         totals["subtotal"], totals["discount"], totals["taxable"],
         totals["exempt"], totals["vat"], totals["total"],
         OPEN, username, _now(), _now()))
    quotation_id = cursor.lastrowid

    conn.executemany(
        """INSERT INTO quotation_items
           (quotation_id, line_no, item_id, description, qty, unit_id, rate_paisa,
            discount_bp, discount_paisa, taxable_paisa, vat_bp, vat_paisa, amount_paisa)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [(quotation_id, n, line.get("item_id"), line.get("description", ""),
          line.get("qty", 0), line.get("unit_id"), line.get("rate", 0),
          line.get("discount_bp", 0), line.get("discount", 0),
          line.get("taxable", 0), line.get("vat_bp", 0), line.get("vat", 0),
          line.get("amount", 0))
         for n, line in enumerate(totals["lines"], start=1)])

    audit.log(conn, username, "quotation.create", "quotations", quotation_id, number,
              "Quoted %s to %s" % (money.format_money(totals["total"]), party_name),
              None, None)
    return quotation_id


def listing(conn, status=None):
    """Every quotation, newest first, with what became of it."""
    where, args = "", []
    if status:
        where = "WHERE q.status = ?"
        args.append(status)
    rows = conn.execute(
        """SELECT q.*, v.number AS voucher_number
           FROM quotations q LEFT JOIN vouchers v ON v.id = q.voucher_id
           %s ORDER BY q.date_ad DESC, q.id DESC""" % where, args).fetchall()
    out = []
    today = datetime.date.today().isoformat()
    for row in rows:
        entry = dict(row)
        entry["status_label"] = STATUS.get(row["status"], row["status"])
        entry["expired"] = bool(
            row["valid_until_ad"] and row["valid_until_ad"] < today
            and row["status"] in (OPEN, ACCEPTED))
        out.append(entry)
    return {"rows": out,
            "open_total": sum(row["total_paisa"] for row in out
                              if row["status"] in (OPEN, ACCEPTED))}


def one(conn, quotation_id):
    row = conn.execute(
        """SELECT q.*, v.number AS voucher_number
           FROM quotations q LEFT JOIN vouchers v ON v.id = q.voucher_id
           WHERE q.id = ?""", (quotation_id,)).fetchone()
    if row is None:
        raise QuotationError("There is no such quotation.")
    lines = conn.execute(
        """SELECT qi.*, i.name AS item_name, i.code AS item_code, u.name AS unit_name
           FROM quotation_items qi
           LEFT JOIN items i ON i.id = qi.item_id
           LEFT JOIN units u ON u.id = COALESCE(qi.unit_id, i.unit_id)
           WHERE qi.quotation_id = ? ORDER BY qi.line_no""", (quotation_id,)).fetchall()
    found = dict(row)
    found["lines"] = [dict(line) for line in lines]
    found["status_label"] = STATUS.get(row["status"], row["status"])
    return found


def set_status(conn, username, quotation_id, status):
    """Say what the customer did with it."""
    if status not in (OPEN, ACCEPTED, DECLINED):
        raise QuotationError("A quotation is open, accepted or declined.")
    row = conn.execute("SELECT number, status FROM quotations WHERE id = ?",
                       (quotation_id,)).fetchone()
    if row is None:
        raise QuotationError("There is no such quotation.")
    if row["status"] == INVOICED:
        raise QuotationError("That one has already become an invoice.")
    conn.execute("UPDATE quotations SET status = ?, updated_at = ? WHERE id = ?",
                 (status, _now(), quotation_id))
    audit.log(conn, username, "quotation.status", "quotations", quotation_id,
              row["number"], "%s marked %s" % (row["number"], STATUS[status]),
              None, None)
    return True


def to_invoice(conn, username, quotation_id, date_ad=None):
    """
    Turn one into a sales invoice.

    Priced again from the lines rather than copied from the stored totals, so
    an invoice is always right by today's rules. Where that changes the figure,
    the person is looking at both and can see it.

    Once only. Two invoices for the same job is a conversation nobody wants to
    have with a customer.
    """
    found = one(conn, quotation_id)
    if found["status"] == INVOICED:
        raise QuotationError(
            "That quotation already became invoice %s." % (found["voucher_number"] or ""))
    if found["status"] == DECLINED:
        raise QuotationError("That quotation was declined. Mark it open first.")

    payload = {
        "date_ad": date_ad or datetime.date.today().isoformat(),
        "party_id": found["party_id"],
        "narration": found["narration"] or ("Against quotation %s" % found["number"]),
        "reference_no": found["number"],
        "price_includes_vat": bool(found["price_includes_vat"]),
        "bill_discount": money.to_rupees(found["bill_discount_paisa"]),
        "other_charges": money.to_rupees(found["other_charges_paisa"]),
        "items": [{
            "item_id": line["item_id"],
            "description": line["description"],
            "qty": money.qty_value(line["qty"]),
            "rate": money.to_rupees(line["rate_paisa"]),
            "discount_bp": line["discount_bp"],
        } for line in found["lines"]],
    }
    voucher_id = invoices.post_sales(conn, username, payload)
    conn.execute(
        "UPDATE quotations SET status = ?, voucher_id = ?, updated_at = ? WHERE id = ?",
        (INVOICED, voucher_id, _now(), quotation_id))
    audit.log(conn, username, "quotation.invoice", "quotations", quotation_id,
              found["number"], "%s became an invoice" % found["number"], None, None)
    return voucher_id


def remove(conn, username, quotation_id):
    """
    Throw one away.

    One that has become an invoice stays, because the invoice refers to it and
    a reference pointing at nothing is worse than a quotation nobody needs.
    """
    row = conn.execute("SELECT number, status FROM quotations WHERE id = ?",
                       (quotation_id,)).fetchone()
    if row is None:
        raise QuotationError("There is no such quotation.")
    if row["status"] == INVOICED:
        raise QuotationError(
            "That one became an invoice, and the invoice refers to it. Cancel the "
            "invoice instead if it was wrong.")
    conn.execute("DELETE FROM quotations WHERE id = ?", (quotation_id,))
    audit.log(conn, username, "quotation.remove", "quotations", quotation_id,
              row["number"], "Threw away %s" % row["number"], None, None)
    return True

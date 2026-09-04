"""
The posting engine.

This is where the books are actually written. Every rule that protects the
integrity of the accounts lives here:

  A voucher must balance. Total debit equals total credit, to the paisa.
  A voucher must fall inside a fiscal year that is still open.
  A posted voucher is never silently removed. It is cancelled, and the
  cancellation is recorded with a reason and a user name.
  Every insert, amendment and cancellation is written to the audit log.

Amounts arriving from a screen are text. They are converted to integer paisa at
the door and stay integers from then on.
"""

import datetime

from ..core import audit, db, money, nepali_date as nd


class PostingError(Exception):
    """Raised when a voucher cannot be accepted into the books."""


def fiscal_year_for_date(conn, date_ad):
    row = conn.execute("""SELECT * FROM fiscal_years
                          WHERE start_ad <= ? AND end_ad >= ?""", (date_ad, date_ad)).fetchone()
    if row is None:
        raise PostingError(
            "No fiscal year covers %s. Open that year under Company before posting." % date_ad)
    return row


def next_voucher_number(conn, voucher_type, fiscal_year_id, reserve=True):
    """
    Give out the next number in the series for a voucher type and year.

    The number is taken inside the caller's transaction, so two vouchers can
    never receive the same number even if they are saved at the same moment.
    """
    row = conn.execute("""SELECT * FROM number_series
                          WHERE voucher_type = ? AND fiscal_year_id = ?""",
                       (voucher_type, fiscal_year_id)).fetchone()
    if row is None:
        vt = conn.execute("SELECT prefix FROM voucher_types WHERE code = ?",
                          (voucher_type,)).fetchone()
        prefix = vt["prefix"] if vt else voucher_type[:2].upper()
        conn.execute("""INSERT INTO number_series (voucher_type, fiscal_year_id, prefix,
                                                   next_number, width) VALUES (?, ?, ?, 1, 4)""",
                     (voucher_type, fiscal_year_id, prefix))
        row = conn.execute("""SELECT * FROM number_series
                              WHERE voucher_type = ? AND fiscal_year_id = ?""",
                           (voucher_type, fiscal_year_id)).fetchone()
    number = "%s%0*d" % (row["prefix"], row["width"], row["next_number"])
    # Skip a number that a user typed in by hand earlier.
    while conn.execute("""SELECT 1 FROM vouchers
                          WHERE voucher_type = ? AND fiscal_year_id = ? AND number = ?""",
                       (voucher_type, fiscal_year_id, number)).fetchone():
        conn.execute("""UPDATE number_series SET next_number = next_number + 1
                        WHERE voucher_type = ? AND fiscal_year_id = ?""",
                     (voucher_type, fiscal_year_id))
        row = conn.execute("""SELECT * FROM number_series
                              WHERE voucher_type = ? AND fiscal_year_id = ?""",
                           (voucher_type, fiscal_year_id)).fetchone()
        number = "%s%0*d" % (row["prefix"], row["width"], row["next_number"])
    if reserve:
        conn.execute("""UPDATE number_series SET next_number = next_number + 1
                        WHERE voucher_type = ? AND fiscal_year_id = ?""",
                     (voucher_type, fiscal_year_id))
    return number


def _clean_entries(conn, raw_entries):
    """Turn screen rows into validated debit and credit lines."""
    entries = []
    for index, row in enumerate(raw_entries or [], start=1):
        account_id = row.get("account_id")
        if not account_id:
            continue
        dr = money.to_paisa(row.get("dr") or 0)
        cr = money.to_paisa(row.get("cr") or 0)
        if dr == 0 and cr == 0:
            continue
        if dr < 0:
            cr, dr = -dr, 0
        if cr < 0:
            dr, cr = -cr, 0
        if dr and cr:
            raise PostingError("Line %d has both a debit and a credit. Use one or the other."
                               % index)
        account = conn.execute("SELECT id, name, active FROM accounts WHERE id = ?",
                               (account_id,)).fetchone()
        if account is None:
            raise PostingError("Line %d refers to an account that does not exist." % index)
        if not account["active"]:
            raise PostingError("Line %d uses %s, which is switched off." % (index, account["name"]))
        entries.append({
            "account_id": int(account_id),
            "dr": dr,
            "cr": cr,
            "narration": (row.get("narration") or "").strip(),
            "cost_center_id": row.get("cost_center_id") or None,
        })
    return entries


def _check_balance(entries):
    if len(entries) < 2:
        raise PostingError("A voucher needs at least one debit and one credit.")
    total_dr = sum(e["dr"] for e in entries)
    total_cr = sum(e["cr"] for e in entries)
    if total_dr == 0:
        raise PostingError("The voucher has no amount.")
    if total_dr != total_cr:
        raise PostingError(
            "Debit and credit do not agree. Debit %s, credit %s, difference %s."
            % (money.format_money(total_dr), money.format_money(total_cr),
               money.format_money(abs(total_dr - total_cr))))
    return total_dr


def _check_date(conn, date_ad, allow_closed=False):
    try:
        parsed = datetime.date.fromisoformat(date_ad)
    except (TypeError, ValueError):
        raise PostingError("The date %r is not a valid date." % date_ad)
    fy = fiscal_year_for_date(conn, date_ad)
    if fy["status"] == "closed" and not allow_closed:
        raise PostingError("Fiscal year %s is closed. Reopen it before posting into it."
                           % fy["label"])
    begins = conn.execute("SELECT books_begin_ad FROM company WHERE id = 1").fetchone()
    if begins and date_ad < begins["books_begin_ad"]:
        raise PostingError("The books begin on %s. Nothing can be posted before that date."
                           % begins["books_begin_ad"])
    return parsed, fy


def post_voucher(conn, username, payload, allow_closed=False):
    """
    Write a voucher into the books.

    payload keys:
      voucher_type, date_ad, entries [required]
      number, party_id, reference_no, reference_date_ad, due_date_ad,
      payment_mode, narration, items, status, and the amount summary fields
      that an invoice screen fills in.

    Returns the voucher id.
    """
    voucher_type = payload.get("voucher_type")
    vt = conn.execute("SELECT * FROM voucher_types WHERE code = ? AND active = 1",
                      (voucher_type,)).fetchone()
    if vt is None:
        raise PostingError("Unknown voucher type %r." % voucher_type)

    date_ad = payload.get("date_ad")
    _, fy = _check_date(conn, date_ad, allow_closed)
    date_bs = nd.format_bs(nd.ad_to_bs(date_ad), "numeric")

    entries = _clean_entries(conn, payload.get("entries"))
    total = _check_balance(entries)

    status = payload.get("status") or "posted"
    if status not in ("draft", "posted"):
        raise PostingError("A new voucher must be saved as a draft or posted.")

    number = (payload.get("number") or "").strip()
    if number:
        clash = conn.execute("""SELECT id FROM vouchers
                                WHERE voucher_type = ? AND fiscal_year_id = ? AND number = ?""",
                             (voucher_type, fy["id"], number)).fetchone()
        if clash:
            raise PostingError("Voucher number %s is already used in %s." % (number, fy["label"]))
    else:
        number = next_voucher_number(conn, voucher_type, fy["id"])

    party_id = payload.get("party_id") or None
    party_account_id = payload.get("party_account_id") or None
    if party_id and not party_account_id:
        row = conn.execute("SELECT account_id FROM parties WHERE id = ?", (party_id,)).fetchone()
        party_account_id = row["account_id"] if row else None

    now = db.now_stamp()
    cur = conn.execute(
        """INSERT INTO vouchers (fiscal_year_id, voucher_type, number, date_ad, date_bs,
                                 party_id, party_account_id, reference_no, reference_date_ad,
                                 due_date_ad, payment_mode, narration,
                                 subtotal_paisa, discount_paisa, bill_discount_paisa,
                                 taxable_paisa, exempt_paisa,
                                 vat_paisa, other_charges_paisa, tds_paisa, round_off_paisa,
                                 total_paisa, is_vat_invoice, status,
                                 created_by, created_at, updated_by, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (fy["id"], voucher_type, number, date_ad, date_bs, party_id, party_account_id,
         (payload.get("reference_no") or "").strip(),
         payload.get("reference_date_ad") or "",
         payload.get("due_date_ad") or "",
         (payload.get("payment_mode") or "").strip(),
         (payload.get("narration") or "").strip(),
         money.to_paisa(payload.get("subtotal") or 0),
         money.to_paisa(payload.get("discount") or 0),
         money.to_paisa(payload.get("bill_discount") or 0),
         money.to_paisa(payload.get("taxable") or 0),
         money.to_paisa(payload.get("exempt") or 0),
         money.to_paisa(payload.get("vat") or 0),
         money.to_paisa(payload.get("other_charges") or 0),
         money.to_paisa(payload.get("tds") or 0),
         money.to_paisa(payload.get("round_off") or 0),
         payload.get("total_paisa") if payload.get("total_paisa") is not None else total,
         1 if payload.get("is_vat_invoice") else 0,
         status, username, now, username, now))
    voucher_id = cur.lastrowid

    for line_no, entry in enumerate(entries, start=1):
        conn.execute(
            """INSERT INTO voucher_entries (voucher_id, line_no, account_id, dr_paisa,
                                            cr_paisa, narration, cost_center_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (voucher_id, line_no, entry["account_id"], entry["dr"], entry["cr"],
             entry["narration"], entry["cost_center_id"]))

    _write_items(conn, voucher_id, payload.get("items"), date_ad, vt, status)
    _write_allocations(conn, voucher_id, payload.get("allocations"))

    audit.log(conn, username, "voucher.post", "vouchers", voucher_id,
              "%s %s" % (voucher_type, number),
              "%s %s dated %s for %s" % (vt["name"], number, date_bs, money.format_money(total)),
              None, {"number": number, "date_ad": date_ad, "total": total, "status": status})
    return voucher_id


def _write_items(conn, voucher_id, raw_items, date_ad, vt, status):
    """Save the goods or service lines, and the stock movement they cause."""
    if not raw_items:
        return
    direction = 0
    if vt["affects_stock"]:
        direction = {"sales": -1, "sales_return": 1, "purchase": 1,
                     "purchase_return": -1}.get(vt["code"], 0)
    # A stock adjustment can add on one line and take away on the next, so each
    # line carries its own direction rather than the voucher setting one.
    per_line = vt["code"] == "stock_adjust"
    for line_no, row in enumerate(raw_items, start=1):
        item_id = row.get("item_id")
        if not item_id:
            continue
        item = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        if item is None:
            raise PostingError("Line %d refers to an item that does not exist." % line_no)
        qty = money.to_qty(row.get("qty") or 0)
        rate = money.to_paisa(row.get("rate") or 0)
        gross = money.round_half_up(qty * rate, money.QTY_SCALE)
        discount_bp = int(row.get("discount_bp") or 0)
        if row.get("discount") not in (None, ""):
            discount = money.to_paisa(row.get("discount"))
        else:
            discount = money.apply_rate(gross, discount_bp)
        # The share of a discount given on the bill as a whole. The pricing
        # module works it out and hands it down, because only it can see the
        # other lines it has to be shared with.
        bill_discount = money.to_paisa(row.get("bill_discount") or 0)
        taxable = gross - discount - bill_discount
        vat_bp = int(row.get("vat_bp") if row.get("vat_bp") is not None else item["vat_rate_bp"])
        if not item["vat_applicable"]:
            vat_bp = 0
        vat = money.apply_rate(taxable, vat_bp)
        amount = taxable + vat
        cur = conn.execute(
            """INSERT INTO voucher_items (voucher_id, line_no, item_id, description, warehouse_id,
                                          qty, free_qty, unit_id, rate_paisa, gross_paisa,
                                          discount_bp, discount_paisa, bill_discount_paisa,
                                          taxable_paisa, vat_bp,
                                          vat_paisa, amount_paisa, cost_paisa, batch, expiry_ad)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (voucher_id, line_no, item_id, (row.get("description") or "").strip(),
             row.get("warehouse_id") or None, qty, money.to_qty(row.get("free_qty") or 0),
             row.get("unit_id") or item["unit_id"], rate, gross, discount_bp, discount,
             bill_discount, taxable, vat_bp, vat, amount, money.to_paisa(row.get("cost") or 0),
             (row.get("batch") or "").strip(), row.get("expiry_ad") or ""))
        item_line_id = cur.lastrowid

        line_direction = int(row.get("direction") or 0) if per_line else direction
        if line_direction and item["maintain_stock"] and item["item_type"] == "goods" \
                and status == "posted":
            total_qty = qty + money.to_qty(row.get("free_qty") or 0)
            stock_rate = rate
            stock_value = None
            if line_direction > 0 and vt["code"] == "purchase" and total_qty:
                # Cost of purchase under NAS 02 is what was actually paid for
                # the goods. Trade discounts and rebates come off it, whether
                # they were agreed line by line or on the bill as a whole, and
                # free goods are part of the quantity the money bought. Bringing
                # stock in at the list rate instead would carry the closing
                # stock above cost and take the discount straight to profit.
                stock_rate = money.round_half_up(taxable * money.QTY_SCALE, total_qty)
                # The value carried is the taxable amount itself, not the rate
                # multiplied back out, so nothing is lost to rounding twice and
                # the stock ledger ties to the purchase ledger to the paisa.
                stock_value = taxable
            if line_direction > 0 and vt["code"] == "sales_return":
                # Goods a customer sends back come into stock at what they cost
                # us, not at what we sold them for. Bringing them back at the
                # selling price would lift the weighted average on every return
                # and quietly overstate the closing stock.
                stock_rate = _cost_rate(conn, item, date_ad)
            if total_qty:
                conn.execute(
                    """INSERT INTO stock_ledger (voucher_id, voucher_item_id, item_id, warehouse_id,
                                                 date_ad, direction, qty, rate_paisa, value_paisa, note)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '')""",
                    (voucher_id, item_line_id, item_id, row.get("warehouse_id") or None,
                     date_ad, line_direction, total_qty, stock_rate,
                     stock_value if stock_value is not None
                     else money.round_half_up(total_qty * stock_rate, money.QTY_SCALE)))


def _cost_rate(conn, item, date_ad):
    """
    What one unit of an item is being carried at on a date.

    The weighted average of what is on hand. If there is none on hand, the last
    known purchase rate, and failing that the rate on the item record.
    """
    from . import reports
    state = reports.item_stock(conn, item["id"], date_ad)
    if state and state["qty"] > 0 and state["average_rate"]:
        return state["average_rate"]
    last = conn.execute(
        """SELECT vi.rate_paisa FROM voucher_items vi
           JOIN vouchers v ON v.id = vi.voucher_id
           WHERE vi.item_id = ? AND v.status = 'posted' AND v.voucher_type = 'purchase'
             AND v.date_ad <= ?
           ORDER BY v.date_ad DESC, v.id DESC LIMIT 1""", (item["id"], date_ad)).fetchone()
    if last and last["rate_paisa"]:
        return last["rate_paisa"]
    return item["purchase_rate_paisa"]


def _write_allocations(conn, voucher_id, allocations):
    for row in allocations or []:
        amount = money.to_paisa(row.get("amount") or 0)
        if not amount:
            continue
        conn.execute(
            """INSERT INTO bill_allocations (voucher_id, account_id, against_voucher_id,
                                             bill_reference, allocation_type, amount_paisa)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (voucher_id, row.get("account_id"), row.get("against_voucher_id") or None,
             (row.get("bill_reference") or "").strip(),
             row.get("allocation_type") or "against", amount))


def get_voucher(conn, voucher_id):
    voucher = conn.execute(
        """SELECT v.*, p.name AS party_name, p.name_np AS party_name_np, p.pan AS party_pan,
                  p.address AS party_address, p.city AS party_city, p.district AS party_district,
                  p.phone AS party_phone, p.mobile AS party_mobile,
                  vt.name AS type_name, vt.name_np AS type_name_np
           FROM vouchers v
           LEFT JOIN parties p ON p.id = v.party_id
           LEFT JOIN voucher_types vt ON vt.code = v.voucher_type
           WHERE v.id = ?""", (voucher_id,)).fetchone()
    if voucher is None:
        return None
    entries = conn.execute(
        """SELECT e.*, a.code AS account_code, a.name AS account_name, a.name_np AS account_name_np
           FROM voucher_entries e JOIN accounts a ON a.id = e.account_id
           WHERE e.voucher_id = ? ORDER BY e.line_no""", (voucher_id,)).fetchall()
    items = conn.execute(
        """SELECT vi.*, i.code AS item_code, i.name AS item_name, i.name_np AS item_name_np,
                  u.symbol AS unit_symbol
           FROM voucher_items vi JOIN items i ON i.id = vi.item_id
           LEFT JOIN units u ON u.id = vi.unit_id
           WHERE vi.voucher_id = ? ORDER BY vi.line_no""", (voucher_id,)).fetchall()
    allocations = conn.execute("SELECT * FROM bill_allocations WHERE voucher_id = ?",
                               (voucher_id,)).fetchall()
    return {"voucher": voucher, "entries": entries, "items": items, "allocations": allocations}


def amend_voucher(conn, username, voucher_id, payload, allow_closed=False):
    """
    Replace the contents of an existing voucher.

    The voucher keeps its number and its identity so that any document already
    printed still refers to the same record. The previous contents go to the
    audit log, so an auditor can see exactly what changed and when.
    """
    existing = get_voucher(conn, voucher_id)
    if existing is None:
        raise PostingError("That voucher no longer exists.")
    voucher = existing["voucher"]
    if voucher["status"] == "cancelled":
        raise PostingError("A cancelled voucher cannot be edited. Enter a fresh one.")

    date_ad = payload.get("date_ad") or voucher["date_ad"]
    _, fy = _check_date(conn, date_ad, allow_closed)
    old_fy = conn.execute("SELECT * FROM fiscal_years WHERE id = ?",
                          (voucher["fiscal_year_id"],)).fetchone()
    if old_fy["status"] == "closed" and not allow_closed:
        raise PostingError("This voucher belongs to closed year %s." % old_fy["label"])

    entries = _clean_entries(conn, payload.get("entries"))
    total = _check_balance(entries)
    date_bs = nd.format_bs(nd.ad_to_bs(date_ad), "numeric")

    before = {
        "voucher": {k: voucher[k] for k in voucher.keys()},
        "entries": [{k: e[k] for k in e.keys()} for e in existing["entries"]],
        "items": [{k: i[k] for k in i.keys()} for i in existing["items"]],
    }

    number = (payload.get("number") or voucher["number"]).strip()
    if number != voucher["number"] or fy["id"] != voucher["fiscal_year_id"]:
        clash = conn.execute("""SELECT id FROM vouchers WHERE voucher_type = ?
                                AND fiscal_year_id = ? AND number = ? AND id <> ?""",
                             (voucher["voucher_type"], fy["id"], number, voucher_id)).fetchone()
        if clash:
            raise PostingError("Voucher number %s is already used in %s." % (number, fy["label"]))

    conn.execute("DELETE FROM voucher_entries WHERE voucher_id = ?", (voucher_id,))
    conn.execute("DELETE FROM stock_ledger WHERE voucher_id = ?", (voucher_id,))
    conn.execute("DELETE FROM voucher_items WHERE voucher_id = ?", (voucher_id,))
    conn.execute("DELETE FROM bill_allocations WHERE voucher_id = ?", (voucher_id,))

    party_id = payload.get("party_id") if "party_id" in payload else voucher["party_id"]
    party_account_id = payload.get("party_account_id") or None
    if party_id and not party_account_id:
        row = conn.execute("SELECT account_id FROM parties WHERE id = ?", (party_id,)).fetchone()
        party_account_id = row["account_id"] if row else None

    status = payload.get("status") or voucher["status"]
    conn.execute(
        """UPDATE vouchers SET fiscal_year_id = ?, number = ?, date_ad = ?, date_bs = ?,
                               party_id = ?, party_account_id = ?, reference_no = ?,
                               reference_date_ad = ?, due_date_ad = ?, payment_mode = ?,
                               narration = ?, subtotal_paisa = ?, discount_paisa = ?,
                               taxable_paisa = ?, exempt_paisa = ?, vat_paisa = ?,
                               other_charges_paisa = ?, tds_paisa = ?, round_off_paisa = ?,
                               total_paisa = ?, is_vat_invoice = ?, status = ?,
                               updated_by = ?, updated_at = ?
           WHERE id = ?""",
        (fy["id"], number, date_ad, date_bs, party_id, party_account_id,
         (payload.get("reference_no") or "").strip(),
         payload.get("reference_date_ad") or "",
         payload.get("due_date_ad") or "",
         (payload.get("payment_mode") or "").strip(),
         (payload.get("narration") or "").strip(),
         money.to_paisa(payload.get("subtotal") or 0),
         money.to_paisa(payload.get("discount") or 0),
         money.to_paisa(payload.get("taxable") or 0),
         money.to_paisa(payload.get("exempt") or 0),
         money.to_paisa(payload.get("vat") or 0),
         money.to_paisa(payload.get("other_charges") or 0),
         money.to_paisa(payload.get("tds") or 0),
         money.to_paisa(payload.get("round_off") or 0),
         payload.get("total_paisa") if payload.get("total_paisa") is not None else total,
         1 if payload.get("is_vat_invoice") else 0,
         status, username, db.now_stamp(), voucher_id))

    for line_no, entry in enumerate(entries, start=1):
        conn.execute(
            """INSERT INTO voucher_entries (voucher_id, line_no, account_id, dr_paisa,
                                            cr_paisa, narration, cost_center_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (voucher_id, line_no, entry["account_id"], entry["dr"], entry["cr"],
             entry["narration"], entry["cost_center_id"]))

    vt = conn.execute("SELECT * FROM voucher_types WHERE code = ?",
                      (voucher["voucher_type"],)).fetchone()
    _write_items(conn, voucher_id, payload.get("items"), date_ad, vt, status)
    _write_allocations(conn, voucher_id, payload.get("allocations"))

    audit.log(conn, username, "voucher.amend", "vouchers", voucher_id,
              "%s %s" % (voucher["voucher_type"], number),
              "Voucher amended. New total %s." % money.format_money(total),
              before, {"number": number, "date_ad": date_ad, "total": total})
    return voucher_id


def cancel_voucher(conn, username, voucher_id, reason):
    """
    Mark a voucher as cancelled.

    The row and its lines stay in the database. Every report ignores a cancelled
    voucher, but the number remains used so a gap in the invoice series is
    always explainable to a tax officer.
    """
    voucher = conn.execute("SELECT * FROM vouchers WHERE id = ?", (voucher_id,)).fetchone()
    if voucher is None:
        raise PostingError("That voucher no longer exists.")
    if voucher["status"] == "cancelled":
        raise PostingError("That voucher is already cancelled.")
    reason = (reason or "").strip()
    if not reason:
        raise PostingError("Give a reason for cancelling. It becomes part of the record.")
    fy = conn.execute("SELECT * FROM fiscal_years WHERE id = ?",
                      (voucher["fiscal_year_id"],)).fetchone()
    if fy["status"] == "closed":
        raise PostingError("Fiscal year %s is closed." % fy["label"])
    now = db.now_stamp()
    conn.execute("""UPDATE vouchers SET status = 'cancelled', cancelled_by = ?,
                                        cancelled_at = ?, cancel_reason = ?, updated_at = ?
                    WHERE id = ?""", (username, now, reason, now, voucher_id))
    conn.execute("DELETE FROM stock_ledger WHERE voucher_id = ?", (voucher_id,))
    audit.log(conn, username, "voucher.cancel", "vouchers", voucher_id,
              "%s %s" % (voucher["voucher_type"], voucher["number"]),
              "Cancelled. Reason: %s" % reason,
              {k: voucher[k] for k in voucher.keys()}, {"status": "cancelled", "reason": reason})


def delete_draft(conn, username, voucher_id):
    """Only a draft may be removed outright. A posted voucher is cancelled instead."""
    voucher = conn.execute("SELECT * FROM vouchers WHERE id = ?", (voucher_id,)).fetchone()
    if voucher is None:
        raise PostingError("That voucher no longer exists.")
    if voucher["status"] != "draft":
        raise PostingError("Only a draft can be deleted. Cancel the voucher instead.")
    audit.log(conn, username, "voucher.delete_draft", "vouchers", voucher_id,
              "%s %s" % (voucher["voucher_type"], voucher["number"]),
              "Draft deleted.", {k: voucher[k] for k in voucher.keys()}, None)
    conn.execute("DELETE FROM vouchers WHERE id = ?", (voucher_id,))

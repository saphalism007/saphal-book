"""
What was offered, before anybody agreed to it.

A quotation is a promise about a price. Nothing has been sold, no tax is due,
no stock has moved. So the first thing this insists on is that writing one
changes nothing at all in the books, and the second is that when it does become
an invoice it comes to the same figure it promised.

A quotation saying one figure and an invoice saying another is worse than
having no quotations at all, so both go through the same pricing and this
checks that they agree to the paisa on an awkward bill: a line discount, a
discount on the whole bill, tax, and rounding.

Run with:  python3 -m tests.test_quotations
"""

import glob
import os
import sys

from chartered_book.core import db, money, nepali_date as nd
from chartered_book.modules import (company, invoices, masters, quotations,
                                    reports)

FAILURES = []
USER = "quotetest"


def check(label, got, expected):
    if got != expected:
        FAILURES.append("%s: got %s, expected %s"
                        % (label,
                           money.format_money(got) if isinstance(got, int) else got,
                           money.format_money(expected) if isinstance(expected, int) else expected))


def clean_up():
    system = db.open_system()
    system.execute("DELETE FROM companies WHERE slug LIKE 'quote_test%'")
    system.commit()
    for path in glob.glob(os.path.join(db.BOOKS_DIR, "quote_test*")):
        try:
            os.remove(path)
        except OSError:
            pass


def main():
    clean_up()
    system = db.open_system()
    year = nd.today_bs()[0]
    made = company.create_company(system, "Quote Test Shop", "trading", USER,
                                  books_begin_ad=nd.fiscal_year(year)["start_ad"])
    conn = made["conn"]
    day = nd.bs_to_ad(year, 4, 10).isoformat()

    customer = masters.create_party(conn, USER, "Buddha Builders", "customer")
    unit = conn.execute("SELECT id FROM units LIMIT 1").fetchone()["id"]
    cement = masters.create_item(conn, USER, "OPC Cement 50 kg", unit_id=unit,
                                 vat_applicable=1, sale_rate="900",
                                 purchase_rate="800", maintain_stock=1)
    rod = masters.create_item(conn, USER, "TMT Rod 12 mm", unit_id=unit,
                              vat_applicable=1, sale_rate="120",
                              purchase_rate="100", maintain_stock=1)
    conn.commit()

    # An awkward bill on purpose: two lines, a discount on one of them, a
    # discount on the whole bill, tax on top, and a delivery charge.
    offer = {
        "date_ad": day, "party_id": customer,
        "narration": "Tilottama site, first phase",
        "valid_until_ad": nd.bs_to_ad(year, 5, 10).isoformat(),
        "terms": "Delivery within seven days of order.",
        "other_charges": "500",
        "bill_discount": "1000",
        "items": [
            {"item_id": cement, "qty": "100", "rate": "900", "discount_bp": 500},
            {"item_id": rod, "qty": "500", "rate": "120"},
        ],
    }

    before = conn.execute("SELECT COUNT(*) n FROM vouchers").fetchone()["n"]
    quotation_id = quotations.create(conn, USER, offer)
    conn.commit()

    # Nothing whatsoever reaches the books.
    check("writing a quotation makes no entry",
          conn.execute("SELECT COUNT(*) n FROM vouchers").fetchone()["n"], before)
    check("and no ledger moves",
          sum(reports.balances_as_at(conn, day).values()), 0)

    found = quotations.one(conn, quotation_id)
    check("it is numbered", found["number"], "QT0001")
    check("it is open", found["status"], "open")
    check("for the right customer", found["party_name"], "Buddha Builders")
    check("with both lines", len(found["lines"]), 2)
    quoted = found["total_paisa"]

    # The figure has to be right, not merely consistent. Worked by hand:
    #   cement  100 at 900 = 90,000 less 5%  = 85,500
    #   rod     500 at 120                    = 60,000
    #   subtotal                              = 1,45,500
    #   less discount on the whole bill       =   (1,000)
    #   taxable                               = 1,44,500
    #   VAT at 13%                            =   18,785
    #   plus delivery                         =      500
    #   total                                 = 1,63,785
    check("the quotation comes to the figure worked by hand",
          quoted, money.to_paisa("163785"))

    # Now the thing that matters most: the invoice must agree.
    voucher_id = quotations.to_invoice(conn, USER, quotation_id, day)
    conn.commit()
    invoice = conn.execute("SELECT number, total_paisa, reference_no FROM vouchers "
                           "WHERE id = ?", (voucher_id,)).fetchone()
    check("the invoice comes to the same as the quotation",
          invoice["total_paisa"], quoted)
    check("and refers back to it", invoice["reference_no"], "QT0001")

    # And now it is a real entry: the customer owes it.
    customer_account = masters.get_party(conn, customer)["account_id"]
    check("the customer owes the invoice",
          reports.balances_as_at(conn, day).get(customer_account), quoted)

    found = quotations.one(conn, quotation_id)
    check("the quotation is marked as invoiced", found["status"], "invoiced")
    check("and names the invoice", found["voucher_number"], invoice["number"])

    # Once only. Two invoices for one job is a conversation nobody wants.
    try:
        quotations.to_invoice(conn, USER, quotation_id, day)
        FAILURES.append("a quotation was invoiced twice")
    except quotations.QuotationError:
        pass

    # And it cannot be thrown away once an invoice points at it.
    try:
        quotations.remove(conn, USER, quotation_id)
        FAILURES.append("an invoiced quotation was thrown away")
    except quotations.QuotationError:
        pass

    # A second one, to check the ordinary refusals.
    try:
        quotations.create(conn, USER, {"date_ad": day, "items": [
            {"item_id": cement, "qty": "1", "rate": "900"}]})
        FAILURES.append("a quotation with nobody to send it to was accepted")
    except quotations.QuotationError:
        pass

    try:
        quotations.create(conn, USER, {"date_ad": day, "party_id": customer,
                                       "items": []})
        FAILURES.append("an empty quotation was accepted")
    except quotations.QuotationError:
        pass

    # One that goes nowhere can be thrown away, and takes its lines with it.
    spare = quotations.create(conn, USER, {
        "date_ad": day, "party_id": customer,
        "items": [{"item_id": rod, "qty": "10", "rate": "120"}]})
    conn.commit()
    check("the next one is numbered on",
          quotations.one(conn, spare)["number"], "QT0002")
    quotations.set_status(conn, USER, spare, "declined")
    conn.commit()
    check("it can be marked declined",
          quotations.one(conn, spare)["status"], "declined")
    quotations.remove(conn, USER, spare)
    conn.commit()
    check("and thrown away with its lines",
          conn.execute("SELECT COUNT(*) n FROM quotation_items WHERE quotation_id = ?",
                       (spare,)).fetchone()["n"], 0)

    conn.commit()
    conn.close()
    clean_up()

    if FAILURES:
        print("Quotations: %d problem%s"
              % (len(FAILURES), "" if len(FAILURES) == 1 else "s"))
        for line in FAILURES:
            print("  " + line)
        return 1
    print("Quotations: what was quoted is what gets invoiced.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

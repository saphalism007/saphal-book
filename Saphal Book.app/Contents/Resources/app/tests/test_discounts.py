"""
Discounts.

A discount is agreed in three different ways and each one is treated
differently, so each one is checked here.

  On the invoice line.       A trade discount. It comes off revenue on a sale
                             and off the cost of purchase on a bill. It never
                             reaches a ledger of its own.
  On the bill as a whole.    The same thing, shared back over the lines it was
                             given on, because value added tax is charged on
                             what the customer actually pays and goods come
                             into stock at what they actually cost.
  On the payment.            A settlement discount. It is not known when the
                             invoice is raised, so it is recorded when it is
                             taken, against Discount Allowed on a receipt and
                             Discount on Purchase on a payment.

Run with:  python3 -m tests.test_discounts
"""

import glob
import os
import sys

from chartered_book.core import db, money, nepali_date as nd
from chartered_book.modules import (company, invoices, masters, reports,
                                    settlements, statements)

FAILURES = []
USER = "discounttest"
SLUG = "discount_test_company"


def check(label, got, expected):
    if got != expected:
        FAILURES.append("%s: got %s, expected %s" % (label, got, expected))


def rs(paisa):
    return money.format_money(paisa)


def clean_up():
    system = db.open_system()
    system.execute("DELETE FROM companies WHERE slug LIKE 'discount_test%'")
    for path in glob.glob(os.path.join(db.BOOKS_DIR, SLUG + ".db*")):
        try:
            os.remove(path)
        except OSError:
            pass


def main():
    clean_up()
    system = db.open_system()
    fy = nd.fiscal_year(2083)
    result = company.create_company(system, "Discount Test Company", "trading", USER,
                                    pan="301777888", vat_registered=1,
                                    books_begin_ad=fy["start_ad"])
    conn = result["conn"]
    start, end = fy["start_ad"], fy["end_ad"]
    code = lambda c: masters.account_by_code(conn, c)["id"]

    def day(month, dayno):
        year = fy["start_bs"][0] if month >= 4 else fy["start_bs"][0] + 1
        return nd.bs_to_ad(year, month, dayno).isoformat()

    def balances(at=None):
        return reports.balances_as_at(conn, at or end)

    masters.update_account(conn, USER, code("1251"), opening="500000", opening_side="dr")
    masters.update_account(conn, USER, code("3101"), opening="500000", opening_side="cr")

    supplier = masters.create_party(conn, USER, "Discount Test Supplier", "supplier",
                                    pan="609333444")
    customer = masters.create_party(conn, USER, "Discount Test Customer", "customer",
                                    pan="302333444")
    supplier_account = masters.get_party(conn, supplier)["account_id"]
    customer_account = masters.get_party(conn, customer)["account_id"]
    unit = masters.unit_by_symbol(conn, "pcs")
    rod = masters.create_item(conn, USER, "Discount Test Rod", unit_id=unit["id"],
                              purchase_rate="1000", sale_rate="1400", vat_rate_bp=1300)
    wire = masters.create_item(conn, USER, "Discount Test Wire", unit_id=unit["id"],
                               purchase_rate="500", sale_rate="700", vat_rate_bp=1300)

    # --- A purchase with a discount on one line only -----------------------
    #
    # 100 rods at 1,000 is 1,00,000, less 10 percent is 90,000.
    # Value added tax at 13 percent on 90,000 is 11,700.
    before = balances()
    invoices.post_purchase(conn, USER, {
        "date_ad": day(4, 5), "party_id": supplier,
        "items": [{"item_id": rod, "qty": "100", "rate": "1000", "discount_bp": 1000}]})
    after = balances()

    # New books keep stock on the perpetual system, so what a supplier bills
    # for goods lands in Stock in Trade and never touches Purchases.
    check("goods taken into stock net of the line discount",
          after[code("1211")] - before[code("1211")], money.to_paisa("90000"))
    check("input tax on the discounted value",
          after[code("1241")] - before[code("1241")], money.to_paisa("11700"))
    check("supplier owed the discounted total",
          before[supplier_account] - after[supplier_account], money.to_paisa("101700"))
    check("no discount ledger was touched on a trade discount",
          after.get(code("5105"), 0), before.get(code("5105"), 0))

    stock = reports.item_stock(conn, rod, end)
    check("rods came into stock at cost, not at list",
          stock["value"], money.to_paisa("90000"))
    check("weighted average rod is 900", rs(stock["average_rate"]), "900.00")

    # --- A purchase with a discount on the bill as a whole -----------------
    #
    # 100 rods at 1,000 and 100 wire at 500 is 1,50,000. Ten percent off the
    # bill is 15,000, shared 10,000 to the rods and 5,000 to the wire.
    before = balances()
    invoices.post_purchase(conn, USER, {
        "date_ad": day(4, 9), "party_id": supplier,
        "bill_discount_bp": 1000,
        "items": [{"item_id": rod, "qty": "100", "rate": "1000"},
                  {"item_id": wire, "qty": "100", "rate": "500"}]})
    after = balances()

    check("goods taken into stock net of the bill discount",
          after[code("1211")] - before[code("1211")], money.to_paisa("135000"))
    check("input tax on the value after the bill discount",
          after[code("1241")] - before[code("1241")], money.to_paisa("17550"))

    wire_stock = reports.item_stock(conn, wire, end)
    check("wire took its share of the bill discount",
          wire_stock["value"], money.to_paisa("45000"))
    check("weighted average wire is 450", rs(wire_stock["average_rate"]), "450.00")

    rod_stock = reports.item_stock(conn, rod, end)
    check("rods carry 90,000 plus 90,000", rod_stock["value"], money.to_paisa("180000"))
    check("200 rods on hand", money.format_qty(rod_stock["qty"]), "200")

    # --- A bill discount split across taxable and exempt goods -------------
    #
    # Only the taxable share may reduce the tax. 1,000 of taxable goods and
    # 1,000 of exempt goods, 200 off the bill, is 100 off each, so the tax is
    # 13 percent of 900 and not 13 percent of 800 or of 1,000.
    exempt_item = masters.create_item(conn, USER, "Discount Test Exempt Bag",
                                      unit_id=unit["id"], purchase_rate="100",
                                      sale_rate="120", vat_rate_bp=0, vat_applicable=0)
    before = balances()
    invoices.post_purchase(conn, USER, {
        "date_ad": day(4, 12), "party_id": supplier, "bill_discount": "200",
        "items": [{"item_id": wire, "qty": "2", "rate": "500"},
                  {"item_id": exempt_item, "qty": "10", "rate": "100"}]})
    after = balances()
    check("only the taxable share of a bill discount reduces the tax",
          after[code("1241")] - before[code("1241")], money.to_paisa("117"))

    # --- A sale with both kinds of discount --------------------------------
    #
    # 50 rods at 1,400 is 70,000, less 5 percent on the line is 66,500,
    # less 1,500 off the bill is 65,000. Tax is 8,450.
    before = balances()
    invoices.post_sales(conn, USER, {
        "date_ad": day(4, 20), "party_id": customer, "bill_discount": "1500",
        "round_invoice": False,
        "items": [{"item_id": rod, "qty": "50", "rate": "1400", "discount_bp": 500}]})
    after = balances()

    check("revenue is the transaction price, net of both discounts",
          before[code("4111")] - after[code("4111")], money.to_paisa("65000"))
    check("output tax on the transaction price",
          before[code("2241")] - after[code("2241")], money.to_paisa("8450"))
    check("customer owes the discounted total",
          after[customer_account] - before[customer_account], money.to_paisa("73450"))
    check("no discount ledger was touched on a sale",
          after.get(code("4132"), 0), before.get(code("4132"), 0))

    # A sale takes stock out at the weighted average, not at what it sold for.
    check("stock down to 150 rods",
          money.format_qty(reports.item_stock(conn, rod, end)["qty"]), "150")

    # --- Not a paisa is lost when a bill discount will not divide ----------
    #
    # Three lines of 1,000 each, 100 off the bill. A third of 100 is 33.33, so
    # the shares have to be 33.34, 33.33 and 33.33 or the invoice will not add.
    priced = invoices.price_voucher(conn, {
        "bill_discount": "100",
        "items": [{"item_id": wire, "qty": "1", "rate": "1000"},
                  {"item_id": wire, "qty": "1", "rate": "1000"},
                  {"item_id": wire, "qty": "1", "rate": "1000"}]})
    shares = [line["bill_discount"] for line in priced["lines"]]
    check("the shares add back to the discount", sum(shares), money.to_paisa("100"))
    check("no share is out by more than a paisa",
          max(shares) - min(shares) <= 1, True)
    check("taxable value is the lines less the discount",
          priced["taxable"], money.to_paisa("2900"))

    # --- A discount larger than the bill is refused ------------------------
    refused = ""
    try:
        invoices.price_voucher(conn, {
            "bill_discount": "5000",
            "items": [{"item_id": wire, "qty": "1", "rate": "1000"}]})
    except invoices.InvoiceError as exc:
        refused = str(exc)
    check("a discount bigger than the bill is refused",
          refused.startswith("The discount on the bill is"), True)

    # --- A settlement discount is a different thing entirely ---------------
    #
    # The customer settles the invoice and is allowed 450 off for paying early.
    before = balances()
    settlements.post(conn, USER, {
        "date_ad": day(5, 2), "party_id": customer,
        "bank_account_id": code("1251"),
        "allocations": [{"amount": "73000", "discount": "450"}]}, "receipt")
    after = balances()
    check("discount allowed carries the settlement discount",
          after[code("4132")] - before[code("4132")], money.to_paisa("450"))
    check("the customer is relieved of the whole 73,450",
          before[customer_account] - after[customer_account], money.to_paisa("73450"))

    # The supplier allows 700 back for early payment.
    before = balances()
    settlements.post(conn, USER, {
        "date_ad": day(5, 4), "party_id": supplier,
        "bank_account_id": code("1251"),
        "allocations": [{"amount": "100000", "discount": "700"}]}, "payment")
    after = balances()
    check("a supplier settlement discount reduces the cost of purchase",
          before[code("5105")] - after[code("5105")], money.to_paisa("700"))
    check("it does not go to other income",
          after.get(code("4203"), 0), before.get(code("4203"), 0))

    # --- Where each one lands in the profit and loss ------------------------
    pl = reports.profit_and_loss(conn, start, end)
    check("discount allowed sits inside revenue",
          any(group["code"] == "4130"
              for group in pl["sections"]["revenue"]["groups"].values()), True)
    check("discount on purchase sits inside cost of sales",
          any(line["code"] == "5105"
              for group in pl["sections"]["cost_of_sales"]["groups"].values()
              for line in group["lines"]), True)

    # Revenue on the face is the invoiced value less every discount.
    # 65,000 invoiced, less the 450 settlement discount, is 64,550.
    check("revenue on the face of the statement", pl["revenue"], money.to_paisa("64550"))

    # --- The note ties back to the ledger ----------------------------------
    note = statements.discount_note(conn, start, end)
    sales_rows = {row["label"]: row["amount"] for row in note["sales"]}
    check("the note starts at the gross value invoiced",
          sales_rows["Goods and services invoiced, before any discount"],
          money.to_paisa("70000"))
    check("the note shows the line discount",
          sales_rows["Less discount given on the invoice lines"], money.to_paisa("-3500"))
    check("the note shows the bill discount",
          sales_rows["Less discount given on the bill as a whole"], money.to_paisa("-1500"))
    check("the note ends at revenue on the face",
          sales_rows["Revenue from operations"], pl["revenue"])
    check("the note needs no plug",
          any(row["label"].startswith("Other entries") for row in note["sales"]), False)

    purchase_rows = {row["label"]: row["amount"] for row in note["purchases"]}
    check("the purchase note ends at what the suppliers charged",
          purchase_rows["Cost of what suppliers billed, net of every discount"],
          money.to_paisa("226100"))
    check("the purchase note needs no plug",
          any(row["label"].startswith("Other entries") for row in note["purchases"]), False)

    # --- Nothing is out of balance after any of it -------------------------
    tb = reports.trial_balance(conn, start, end)
    check("trial balance ties", tb["balanced"], True)
    bs = reports.balance_sheet(conn, end, start)
    check("balance sheet balances", bs["balanced"], True)

    conn.close()
    clean_up()

    if FAILURES:
        print("FAILED (%d)" % len(FAILURES))
        for line in FAILURES:
            print("  " + line)
        return 1
    print("All discount tests passed.")
    print("  Trade discount    off revenue and off the cost of purchase")
    print("  Bill discount     shared over the lines before tax and before stock")
    print("  Settlement        Discount Allowed and Discount on Purchase")
    print("  Trial balance     ties")
    return 0


if __name__ == "__main__":
    sys.exit(main())

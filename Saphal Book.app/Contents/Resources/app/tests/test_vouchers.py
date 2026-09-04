"""
Returns, notes and stock adjustments.

These are the vouchers that correct something already posted, so they are the
ones most likely to be got wrong. Each is checked for what it does to stock, to
the tax accounts and to the party, and the books are checked for balance after
every one.

Run with:  python3 -m tests.test_vouchers
"""

import glob
import os
import sys

from chartered_book.core import db, money, nepali_date as nd
from chartered_book.modules import (adjustments, company, inventory, invoices, ledger,
                                    masters, period_end, reports)

FAILURES = []
USER = "vouchertest"
SLUG = "voucher_test_company"


def check(label, got, expected):
    if got != expected:
        FAILURES.append("%s: got %s, expected %s" % (label, got, expected))


def rs(paisa):
    return money.format_money(paisa)


def clean_up():
    system = db.open_system()
    system.execute("DELETE FROM companies WHERE slug LIKE 'voucher_test%'")
    for path in glob.glob(os.path.join(db.BOOKS_DIR, SLUG + ".db*")):
        try:
            os.remove(path)
        except OSError:
            pass


def balances(conn, at):
    return reports.balances_as_at(conn, at)


def main():
    clean_up()
    system = db.open_system()
    fy = nd.fiscal_year(2083)
    result = company.create_company(system, "Voucher Test Company", "trading", USER,
                                    pan="301234599", vat_registered=1,
                                    books_begin_ad=fy["start_ad"])
    conn = result["conn"]

    # This suite is about the periodic system: purchases go to Purchases and the
    # closing stock entry brings the value in at the year end. The perpetual
    # system, which is what new books use, is covered in test_inventory.
    inventory.set_method(conn, "periodic", USER)
    start, end = fy["start_ad"], fy["end_ad"]
    code = lambda c: masters.account_by_code(conn, c)["id"]

    def day(month, dayno):
        year = fy["start_bs"][0] if month >= 4 else fy["start_bs"][0] + 1
        return nd.bs_to_ad(year, month, dayno).isoformat()

    masters.update_account(conn, USER, code("1251"), opening="200000", opening_side="dr")
    masters.update_account(conn, USER, code("3101"), opening="200000", opening_side="cr")

    supplier = masters.create_party(conn, USER, "Return Test Supplier", "supplier", pan="609111222")
    customer = masters.create_party(conn, USER, "Return Test Customer", "customer", pan="302111222")
    supplier_account = masters.get_party(conn, supplier)["account_id"]
    customer_account = masters.get_party(conn, customer)["account_id"]
    unit = masters.unit_by_symbol(conn, "bag")
    item = masters.create_item(conn, USER, "Return Test Cement", unit_id=unit["id"],
                               purchase_rate="800", sale_rate="1000", vat_rate_bp=1300)

    # Buy 200, sell 50.
    invoices.post_purchase(conn, USER, {
        "date_ad": day(4, 4), "party_id": supplier,
        "items": [{"item_id": item, "qty": "200", "rate": "800"}]})
    invoices.post_sales(conn, USER, {
        "date_ad": day(4, 10), "party_id": customer,
        "items": [{"item_id": item, "qty": "50", "rate": "1000"}]})

    check("stock after buying and selling",
          money.format_qty(reports.item_stock(conn, item, end)["qty"]), "150")

    # The customer sends 10 back.
    before = balances(conn, end)
    invoices.post_sales_return(conn, USER, {
        "date_ad": day(4, 18), "party_id": customer,
        "items": [{"item_id": item, "qty": "10", "rate": "1000"}],
        "narration": "Ten bags returned, wrong grade"})
    after = balances(conn, end)

    check("stock back up after the sales return",
          money.format_qty(reports.item_stock(conn, item, end)["qty"]), "160")
    check("customer owes 11,300 less",
          before[customer_account] - after[customer_account], money.to_paisa("11300"))
    check("sales return debited 10,000",
          after[code("4131")] - before[code("4131")], money.to_paisa("10000"))
    check("output tax reversed by 1,300",
          after[code("2241")] - before[code("2241")], money.to_paisa("1300"))

    # 20 go back to the supplier.
    before = balances(conn, end)
    invoices.post_purchase_return(conn, USER, {
        "date_ad": day(4, 20), "party_id": supplier,
        "items": [{"item_id": item, "qty": "20", "rate": "800"}],
        "narration": "Twenty bags returned, damaged in transit"})
    after = balances(conn, end)

    check("stock down after the purchase return",
          money.format_qty(reports.item_stock(conn, item, end)["qty"]), "140")
    check("supplier owed 18,080 less",
          after[supplier_account] - before[supplier_account], money.to_paisa("18080"))
    check("purchase return credited 16,000",
          before[code("5104")] - after[code("5104")], money.to_paisa("16000"))
    check("input tax reversed by 2,080",
          before[code("1241")] - after[code("1241")], money.to_paisa("2080"))

    # A credit note for a rate difference, no goods moving.
    before = balances(conn, end)
    stock_before = reports.item_stock(conn, item, end)["qty"]
    invoices.post_note(conn, USER, {
        "date_ad": day(5, 3), "party_id": customer, "amount": "4000", "vat_bp": 1300,
        "reason": "Rate agreed at 920 after the invoice was raised"}, "credit_note")
    after = balances(conn, end)
    check("a credit note moves no stock",
          reports.item_stock(conn, item, end)["qty"], stock_before)
    check("customer owes 4,520 less",
          before[customer_account] - after[customer_account], money.to_paisa("4520"))
    check("output tax adjusted by 520",
          after[code("2241")] - before[code("2241")], money.to_paisa("520"))

    # A debit note claimed against the supplier.
    before = balances(conn, end)
    invoices.post_note(conn, USER, {
        "date_ad": day(5, 5), "party_id": supplier, "amount": "2500", "vat_bp": 1300,
        "reason": "Short delivery claimed"}, "debit_note")
    after = balances(conn, end)
    check("supplier owed 2,825 less",
          after[supplier_account] - before[supplier_account], money.to_paisa("2825"))
    check("input tax adjusted by 325",
          before[code("1241")] - after[code("1241")], money.to_paisa("325"))

    # A physical count finds five bags short.
    before = balances(conn, end)
    adjustments.post(conn, USER, {
        "date_ad": day(5, 12),
        "items": [{"item_id": item, "qty": "5", "reason": "damage",
                   "note": "Torn bags in the back store"}],
        "narration": "Physical count on 12 Bhadra"})
    after = balances(conn, end)

    check("stock down after the adjustment",
          money.format_qty(reports.item_stock(conn, item, end)["qty"]), "135")
    check("the loss is 4,000 at cost",
          after[code("7304")] - before[code("7304")], money.to_paisa("4000"))
    check("stock in trade credited 4,000",
          before[code("1211")] - after[code("1211")], money.to_paisa("4000"))

    # Taking stock for the owner's own use is drawings, not an expense.
    before = balances(conn, end)
    adjustments.post(conn, USER, {
        "date_ad": day(5, 14),
        "items": [{"item_id": item, "qty": "2", "reason": "own_use"}],
        "narration": "Two bags taken for the house"})
    after = balances(conn, end)
    check("own use goes to drawings, not to expenses",
          after[code("3301")] - before[code("3301")], money.to_paisa("1600"))

    # A shortage bigger than what is on hand must be refused.
    try:
        adjustments.post(conn, USER, {
            "date_ad": day(5, 15),
            "items": [{"item_id": item, "qty": "9999", "reason": "shortage"}]})
        FAILURES.append("an adjustment larger than the stock on hand was accepted")
    except adjustments.AdjustmentError:
        pass

    # Everything must still tie, and closing stock must still come out right.
    tb = reports.trial_balance(conn, start, end)
    check("trial balance ties after every correction", tb["balanced"], True)

    period_end.post_closing_stock(conn, USER, end)
    stock = reports.stock_summary(conn, end)
    check("closing stock equals 133 bags at 800",
          stock["total_value"], money.to_paisa("106400"))
    check("stock in trade agrees with the stock report",
          balances(conn, end)[code("1211")], stock["total_value"])
    check("trial balance still ties after closing stock",
          reports.trial_balance(conn, start, end)["balanced"], True)

    bs = reports.balance_sheet(conn, end, start)
    check("balance sheet balances", bs["balanced"], True)

    # The VAT return must pick the returns and notes up.
    vat = reports.vat_return(conn, 2083, 4)
    check("sales register carries the return", vat["sales"]["vat"] < money.to_paisa("6500"), True)

    conn.close()
    clean_up()

    if FAILURES:
        print("FAILED (%d)" % len(FAILURES))
        for line in FAILURES:
            print("  " + line)
        return 1
    print("All return, note and adjustment tests passed.")
    print("  Closing stock   %s" % rs(stock["total_value"]))
    print("  Trial balance   ties")
    print("  Balance sheet   balances")
    return 0


if __name__ == "__main__":
    sys.exit(main())

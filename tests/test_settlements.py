"""
Receipts and payments against bills, and the discount that goes with them.

A settlement discount is easy to post the wrong way round, and getting it wrong
leaves a customer's account showing a balance that will never be collected. So
each one is checked against the ledger it moved.

Run with:  python3 -m tests.test_settlements
"""

import glob
import os
import sys

from chartered_book.core import db, money, nepali_date as nd
from chartered_book.modules import (company, invoices, masters, reports, settlements)

FAILURES = []
USER = "settlementtest"
SLUG = "settlement_test_company"


def check(label, got, expected):
    if got != expected:
        FAILURES.append("%s: got %s, expected %s"
                        % (label,
                           money.format_money(got) if isinstance(got, int) else got,
                           money.format_money(expected) if isinstance(expected, int) else expected))


def clean_up():
    system = db.open_system()
    system.execute("DELETE FROM companies WHERE slug LIKE 'settlement_test%'")
    for path in glob.glob(os.path.join(db.BOOKS_DIR, SLUG + ".db*")):
        try:
            os.remove(path)
        except OSError:
            pass


def main():
    clean_up()
    system = db.open_system()
    fy = nd.fiscal_year(2083)
    conn = company.create_company(system, "Settlement Test Company", "trading", USER,
                                  vat_registered=1, books_begin_ad=fy["start_ad"])["conn"]
    start, end = fy["start_ad"], fy["end_ad"]
    code = lambda c: masters.account_by_code(conn, c)["id"]

    def day(month, dayno):
        year = fy["start_bs"][0] if month >= 4 else fy["start_bs"][0] + 1
        return nd.bs_to_ad(year, month, dayno).isoformat()

    masters.update_account(conn, USER, code("1251"), opening="500000", opening_side="dr")
    masters.update_account(conn, USER, code("3101"), opening="500000", opening_side="cr")

    customer = masters.create_party(conn, USER, "Discount Customer", "customer", credit_days=15)
    supplier = masters.create_party(conn, USER, "Discount Supplier", "supplier", credit_days=30)
    customer_account = masters.get_party(conn, customer)["account_id"]
    supplier_account = masters.get_party(conn, supplier)["account_id"]
    unit = masters.unit_by_symbol(conn, "pcs")
    item = masters.create_item(conn, USER, "Discount Item", unit_id=unit["id"],
                               purchase_rate="1000", sale_rate="1500", vat_rate_bp=0)

    # Two sales, so there is a choice of bill to settle.
    first = invoices.post_sales(conn, USER, {
        "date_ad": day(4, 5), "party_id": customer,
        "items": [{"item_id": item, "qty": "10", "rate": "1500"}]})     # 15,000
    invoices.post_sales(conn, USER, {
        "date_ad": day(4, 20), "party_id": customer,
        "items": [{"item_id": item, "qty": "6", "rate": "1500"}]})      # 9,000

    bills = settlements.open_bills(conn, customer, "receivable", end)
    check("two bills open", len(bills["bills"]), 2)
    check("owed in total", bills["total"], money.to_paisa("24000"))

    # The customer settles the first bill early: 14,500 in cash, 500 allowed off.
    before = reports.balances_as_at(conn, end)
    settlements.post(conn, USER, {
        "date_ad": day(4, 12), "party_id": customer,
        "bank_account_id": code("1251"), "payment_mode": "cash",
        "narration": "Settled early, two percent allowed",
        "allocations": [{"voucher_id": first, "number": "SI0001",
                         "amount": "14500", "discount": "500"}],
    }, "receipt")
    after = reports.balances_as_at(conn, end)

    check("cash up by what came in",
          after[code("1251")] - before[code("1251")], money.to_paisa("14500"))
    check("discount allowed debited",
          after[code("4132")] - before[code("4132")], money.to_paisa("500"))
    check("customer credited with the whole bill",
          before[customer_account] - after[customer_account], money.to_paisa("15000"))

    bills = settlements.open_bills(conn, customer, "receivable", end)
    check("first bill is closed", len(bills["bills"]), 1)
    check("only the second is left", bills["total"], money.to_paisa("9000"))

    # Money on account, not set against any bill.
    settlements.post(conn, USER, {
        "date_ad": day(5, 2), "party_id": customer,
        "bank_account_id": code("1251"), "on_account": "2000",
        "narration": "Advance against future supply",
    }, "receipt")
    check("what is owed drops by the advance",
          settlements.open_bills(conn, customer, "receivable", end)["total"],
          money.to_paisa("7000"))

    # Now the other way round: a supplier allows a discount for early payment.
    purchase = invoices.post_purchase(conn, USER, {
        "date_ad": day(4, 8), "party_id": supplier,
        "items": [{"item_id": item, "qty": "20", "rate": "1000"}]})     # 20,000

    before = reports.balances_as_at(conn, end)
    settlements.post(conn, USER, {
        "date_ad": day(4, 15), "party_id": supplier,
        "bank_account_id": code("1251"), "payment_mode": "cash",
        "narration": "Paid inside the discount period",
        "allocations": [{"voucher_id": purchase, "number": "PI0001",
                         "amount": "19400", "discount": "600"}],
    }, "payment")
    after = reports.balances_as_at(conn, end)

    check("cash down by what went out",
          before[code("1251")] - after[code("1251")], money.to_paisa("19400"))
    check("discount received credited",
          before[code("4203")] - after[code("4203")], money.to_paisa("600"))
    check("supplier debited with the whole bill",
          after[supplier_account] - before[supplier_account], money.to_paisa("20000"))
    check("nothing left owing to the supplier",
          settlements.open_bills(conn, supplier, "payable", end)["total"], 0)

    # A negative amount must be refused rather than quietly flipped.
    try:
        settlements.post(conn, USER, {
            "date_ad": day(5, 3), "party_id": customer,
            "bank_account_id": code("1251"),
            "allocations": [{"voucher_id": first, "amount": "-100"}]}, "receipt")
        FAILURES.append("a negative settlement was accepted")
    except settlements.SettlementError:
        pass

    # A receipt with nothing on it must be refused.
    try:
        settlements.post(conn, USER, {
            "date_ad": day(5, 3), "party_id": customer,
            "bank_account_id": code("1251"), "allocations": []}, "receipt")
        FAILURES.append("an empty receipt was accepted")
    except settlements.SettlementError:
        pass

    tb = reports.trial_balance(conn, start, end)
    check("trial balance ties", tb["balanced"], True)

    statement = settlements.statement_of_account(conn, customer, start, end)
    check("the statement shows what is still open",
          sum(bill["amount"] for bill in statement["open_bills"]), money.to_paisa("7000"))
    check("the statement closing agrees with the ledger",
          statement["closing"], money.to_paisa("7000"))

    conn.close()
    clean_up()

    if FAILURES:
        print("FAILED (%d)" % len(FAILURES))
        for line in FAILURES:
            print("  " + line)
        return 1
    print("All settlement and discount tests passed.")
    print("  Discount allowed  %s" % money.format_money(money.to_paisa("500")))
    print("  Discount received %s" % money.format_money(money.to_paisa("600")))
    print("  Trial balance     ties")
    return 0


if __name__ == "__main__":
    sys.exit(main())

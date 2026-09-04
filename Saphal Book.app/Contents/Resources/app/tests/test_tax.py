"""
Value added tax and tax deducted at source.

The registers have to agree with the ledgers, because the return filed with the
Inland Revenue Department and the balance sheet given to the owner are supposed
to be two views of the same month.

Settling a month is the part that was missing. Output tax and input tax both go
on accumulating in their own ledgers until somebody closes the month off, and
until then the balance sheet shows a large tax asset and a large tax liability
side by side when only the difference is really owed.

Run with:  python3 -m tests.test_tax
"""

import glob
import os
import sys

from chartered_book.core import db, money, nepali_date as nd
from chartered_book.modules import (company, invoices, masters, period_end, reports)

FAILURES = []
USER = "taxtest"
SLUG = "tax_test_company"


def check(label, got, expected):
    if got != expected:
        FAILURES.append("%s: got %s, expected %s" % (label, got, expected))


def clean_up():
    system = db.open_system()
    system.execute("DELETE FROM companies WHERE slug LIKE 'tax_test%'")
    for path in glob.glob(os.path.join(db.BOOKS_DIR, SLUG + ".db*")):
        try:
            os.remove(path)
        except OSError:
            pass


def main():
    clean_up()
    system = db.open_system()
    fy = nd.fiscal_year(2083)
    result = company.create_company(system, "Tax Test Company", "trading", USER,
                                    pan="301888999", vat_registered=1,
                                    books_begin_ad=fy["start_ad"])
    conn = result["conn"]
    start, end = fy["start_ad"], fy["end_ad"]
    code = lambda c: masters.account_by_code(conn, c)["id"]

    def day(month, dayno):
        year = fy["start_bs"][0] if month >= 4 else fy["start_bs"][0] + 1
        return nd.bs_to_ad(year, month, dayno).isoformat()

    def balances():
        return reports.balances_as_at(conn, end)

    masters.update_account(conn, USER, code("1251"), opening="2000000", opening_side="dr")
    masters.update_account(conn, USER, code("3101"), opening="2000000", opening_side="cr")
    unit = masters.unit_by_symbol(conn, "pcs")
    item = masters.create_item(conn, USER, "Tax Test Item", unit_id=unit["id"],
                               purchase_rate="1000", sale_rate="1500", vat_rate_bp=1300)
    supplier = masters.create_party(conn, USER, "Tax Test Supplier", "supplier", pan="609888999")
    customer = masters.create_party(conn, USER, "Tax Test Customer", "customer", pan="302888999")

    # Shrawan: buy a lot, sell a little. Input tax is the larger.
    invoices.post_purchase(conn, USER, {
        "date_ad": day(4, 6), "party_id": supplier,
        "items": [{"item_id": item, "qty": "100", "rate": "1000"}]})
    invoices.post_sales(conn, USER, {
        "date_ad": day(4, 20), "party_id": customer, "round_invoice": False,
        "items": [{"item_id": item, "qty": "20", "rate": "1500"}]})

    # Bhadra: sell the rest. Output tax is the larger.
    invoices.post_sales(conn, USER, {
        "date_ad": day(5, 12), "party_id": customer, "round_invoice": False,
        "items": [{"item_id": item, "qty": "50", "rate": "1500"}]})

    # --- The return has to agree with the ledgers --------------------------
    shrawan = reports.vat_return(conn, 2083, 4)
    check("input tax on a 1,00,000 purchase", shrawan["input_tax"], money.to_paisa("13000"))
    check("output tax on a 30,000 sale", shrawan["output_tax"], money.to_paisa("3900"))
    check("Shrawan leaves a credit", shrawan["credit_carried"], money.to_paisa("9100"))
    check("the return is due on the 25th of the next month",
          shrawan["due_date_bs"], "25 Bhadra 2083")

    bhadra = reports.vat_return(conn, 2083, 5)
    check("output tax on a 75,000 sale", bhadra["output_tax"], money.to_paisa("9750"))
    check("Bhadra leaves an amount payable", bhadra["payable"], money.to_paisa("9750"))

    held = balances()
    check("the register agrees with the input tax ledger",
          held[code("1241")], shrawan["input_tax"] + bhadra["input_tax"])
    check("the register agrees with the output tax ledger",
          -held[code("2241")], shrawan["output_tax"] + bhadra["output_tax"])

    # --- Settling the month ------------------------------------------------
    period_end.post_vat_settlement(conn, USER, 2083, 4)
    period_end.post_vat_settlement(conn, USER, 2083, 5)
    held = balances()

    check("input tax is cleared out once the months are settled",
          held.get(code("1241"), 0), 0)
    check("output tax is cleared out too", held.get(code("2241"), 0), 0)
    check("what is left to pay stands on its own",
          -held[code("2242")], money.to_paisa("9750"))
    check("the credit from Shrawan is carried forward",
          held[code("1242")], money.to_paisa("9100"))

    # A month cannot be settled twice by accident.
    refused = ""
    try:
        period_end.post_vat_settlement(conn, USER, 2083, 4)
    except period_end.PeriodEndError as exc:
        refused = str(exc)
    check("settling the same month again is refused",
          refused.startswith("The value added tax for Shrawan"), True)

    # --- Tax deducted at source --------------------------------------------
    #
    # A customer who deducts tax at source pays less than the invoice, and the
    # difference is an asset until it is set against the year's own tax.
    before = balances()
    invoices.post_sales(conn, USER, {
        "date_ad": day(6, 4), "party_id": customer, "round_invoice": False,
        "tds": "1500", "items": [{"item_id": item, "qty": "10", "rate": "1500"}]})
    after = balances()
    check("tax deducted by a customer is carried as receivable",
          after[code("1244")] - before.get(code("1244"), 0), money.to_paisa("1500"))
    check("and the customer owes that much less",
          after[masters.get_party(conn, customer)["account_id"]]
          - before[masters.get_party(conn, customer)["account_id"]],
          money.to_paisa("15450"))

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
    print("All tax tests passed.")
    print("  VAT register       agrees with both tax ledgers")
    print("  Settling a month   leaves only what is owed, or only what is recoverable")
    print("  TDS deducted       carried as receivable, customer owes that much less")
    return 0


if __name__ == "__main__":
    sys.exit(main())

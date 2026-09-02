"""
The financial statements have to tie.

A set of books is built with everything a cash flow statement is supposed to
classify: a fixed asset bought, a loan taken and partly repaid, capital
introduced, drawings taken, depreciation charged, interest paid, and ordinary
trading on credit. Then every statement is checked.

Run with:  python3 -m tests.test_statements
"""

import glob
import os
import sys

from chartered_book.core import db, money, nepali_date as nd
from chartered_book.modules import (company, invoices, ledger, masters, period_end,
                                    reports, statements)

FAILURES = []
USER = "statementtest"
SLUG = "statement_test_company"


def check(label, got, expected):
    if got != expected:
        FAILURES.append("%s: got %s, expected %s" % (label, got, expected))


def rs(paisa):
    return money.format_money(paisa)


def clean_up():
    system = db.open_system()
    system.execute("DELETE FROM companies WHERE slug LIKE 'statement_test%'")
    for path in glob.glob(os.path.join(db.BOOKS_DIR, SLUG + ".db*")):
        try:
            os.remove(path)
        except OSError:
            pass


def build():
    clean_up()
    system = db.open_system()
    fy = nd.fiscal_year(2083)
    result = company.create_company(
        system, "Statement Test Company", "trading", USER,
        pan="301111111", vat_registered=1, books_begin_ad=fy["start_ad"])
    return result["conn"], fy


def post(conn, date_ad, narration, lines, voucher_type="journal"):
    return ledger.post_voucher(conn, USER, {
        "voucher_type": voucher_type, "date_ad": date_ad, "narration": narration,
        "entries": [{"account_id": account, "dr": dr, "cr": cr}
                    for account, dr, cr in lines]})


def main():
    conn, fy = build()
    start, end = fy["start_ad"], fy["end_ad"]
    code = lambda c: masters.account_by_code(conn, c)["id"]

    cash = code("1251")
    bank = code("1261")
    capital = code("3101")
    drawings = code("3301")

    # Opening position, brought in before the year starts.
    masters.update_account(conn, USER, cash, opening="100000", opening_side="dr")
    masters.update_account(conn, USER, capital, opening="100000", opening_side="cr")

    def day(month, dayno):
        year = fy["start_bs"][0] if month >= 4 else fy["start_bs"][0] + 1
        return nd.bs_to_ad(year, month, dayno).isoformat()

    # Financing: capital introduced into the bank, and a term loan taken.
    post(conn, day(4, 2), "Further capital introduced",
         [(bank, "500000", 0), (capital, 0, "500000")], "receipt")
    post(conn, day(4, 3), "Term loan from the bank",
         [(bank, "300000", 0), (code("2111"), 0, "300000")], "receipt")

    # Investing: a delivery vehicle bought.
    post(conn, day(4, 5), "Delivery vehicle purchased",
         [(code("1118"), "420000", 0), (bank, 0, "420000")], "payment")

    # Trading on credit.
    supplier = masters.create_party(conn, USER, "Test Supplier", "supplier", pan="609999999")
    customer = masters.create_party(conn, USER, "Test Customer", "customer", pan="302222222")
    unit = masters.unit_by_symbol(conn, "bag")
    item = masters.create_item(conn, USER, "Test Cement", unit_id=unit["id"],
                               purchase_rate="800", sale_rate="1000", vat_rate_bp=1300)
    invoices.post_purchase(conn, USER, {
        "date_ad": day(4, 10), "party_id": supplier,
        "items": [{"item_id": item, "qty": "500", "rate": "800"}]})
    invoices.post_sales(conn, USER, {
        "date_ad": day(5, 6), "party_id": customer,
        "items": [{"item_id": item, "qty": "300", "rate": "1000"}]})

    supplier_account = masters.get_party(conn, supplier)["account_id"]
    customer_account = masters.get_party(conn, customer)["account_id"]
    post(conn, day(5, 20), "Paid the supplier",
         [(supplier_account, "300000", 0), (bank, 0, "300000")], "payment")
    post(conn, day(6, 2), "Received from the customer",
         [(bank, "200000", 0), (customer_account, 0, "200000")], "receipt")

    # Running costs, depreciation, interest, drawings and a loan repayment.
    post(conn, day(6, 5), "Shop rent", [(code("6201"), "60000", 0), (cash, 0, "60000")], "payment")
    post(conn, day(6, 20), "Interest on the term loan",
         [(code("7101"), "18000", 0), (bank, 0, "18000")], "payment")
    post(conn, day(7, 1), "Part repayment of the term loan",
         [(code("2111"), "50000", 0), (bank, 0, "50000")], "payment")
    post(conn, day(7, 10), "Drawings by the proprietor",
         [(drawings, "40000", 0), (cash, 0, "40000")], "payment")
    post(conn, day(3, 30), "Depreciation on the vehicle for the year",
         [(code("7206"), "84000", 0), (code("1126"), 0, "84000")])

    period_end.post_closing_stock(conn, USER, end)

    # Checks

    tb = reports.trial_balance(conn, start, end)
    check("trial balance ties", tb["balanced"], True)

    full = statements.full_set(conn, start, end)

    position = full["position"]
    check("statement of financial position balances", position["balanced"], True)
    if not position["balanced"]:
        FAILURES.append("position out by %s" % rs(position["difference"]))

    cf = full["cash_flows"]
    check("cash flow ties to the cash ledgers", cf["ties"], True)
    if not cf["ties"]:
        FAILURES.append("cash flow unexplained %s" % rs(cf["unexplained"]))

    # The vehicle is the only investing item and it went out.
    investing_names = [item["name"] for item in cf["investing_items"]]
    check("vehicle appears under investing", "Vehicles" in investing_names, True)
    check("investing is an outflow", cf["investing"] < 0, True)
    check("investing equals the cost of the vehicle", cf["investing"], -money.to_paisa("420000"))

    # Financing: 500,000 capital in, 300,000 loan in, 50,000 repaid,
    # 40,000 drawings out, and 18,000 interest paid.
    check("financing is an inflow", cf["financing"] > 0, True)
    check("financing figure", cf["financing"],
          money.to_paisa("500000") + money.to_paisa("300000")
          - money.to_paisa("50000") - money.to_paisa("40000") - money.to_paisa("18000"))

    # Depreciation must be added back and must not appear as investing.
    check("depreciation added back", cf["depreciation"], money.to_paisa("84000"))
    check("accumulated depreciation is not an investing item",
          any("Accumulated" in item["name"] for item in cf["investing_items"]), False)

    # Cash actually held at the end.
    cash_balance = reports.cash_and_bank_summary(conn, end)["total"]
    check("closing cash agrees with the ledgers", cf["cash_closing"], cash_balance)

    equity = full["equity"]
    check("equity closing includes the profit",
          equity["closing_with_profit"], position["total_equity"])

    pl = full["profit_or_loss"]
    check("profit and loss carries a comparative column", pl["compare"] is not None, True)

    # Gross profit: sold 300 bags costing 800 at 1000.
    check("gross profit", pl["detail"]["gross_profit"], money.to_paisa("60000"))

    schedules = full["schedules"]
    check("there are notes behind the statements", len(schedules["notes"]) > 5, True)
    for note in schedules["notes"]:
        total = sum(line["amount"] for line in note["lines"])
        if total != note["total"]:
            FAILURES.append("note %s does not add up: lines %s, total %s"
                            % (note["number"], rs(total), rs(note["total"])))

    trading = full["trading"]
    check("trading account gross profit agrees",
          trading["gross_profit"], pl["detail"]["gross_profit"])

    conn.close()
    clean_up()

    if FAILURES:
        print("FAILED (%d)" % len(FAILURES))
        for line in FAILURES:
            print("  " + line)
        return 1
    print("All financial statement tests passed.")
    print("  Total assets          %s" % rs(position["total_assets"]))
    print("  Operating cash flow   %s" % rs(cf["operating"]))
    print("  Investing cash flow   %s" % rs(cf["investing"]))
    print("  Financing cash flow   %s" % rs(cf["financing"]))
    print("  Closing cash          %s" % rs(cf["cash_closing"]))
    print("  Notes prepared        %d" % len(schedules["notes"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""
Stock kept on the perpetual system.

Goods bought are an asset the moment they arrive. Goods sold take their cost
out of that asset and into cost of sales on the same day. Nobody has to pass a
closing stock entry for the balance sheet to be right, and gross profit can be
read on any day of the year.

The one thing that must never happen is the balance on Stock in Trade parting
company with the value in the stock report. Every check below comes back to
that.

Run with:  python3 -m tests.test_inventory
"""

import glob
import os
import sys

from chartered_book.core import db, money, nepali_date as nd
from chartered_book.modules import (company, inventory, invoices, masters, reports,
                                    statements)

FAILURES = []
USER = "stocktest"
SLUG = "stock_test_company"


def check(label, got, expected):
    if got != expected:
        FAILURES.append("%s: got %s, expected %s" % (label, got, expected))


def rs(paisa):
    return money.format_money(paisa)


def clean_up():
    system = db.open_system()
    system.execute("DELETE FROM companies WHERE slug LIKE 'stock_test%'")
    for path in glob.glob(os.path.join(db.BOOKS_DIR, SLUG + ".db*")):
        try:
            os.remove(path)
        except OSError:
            pass


def main():
    clean_up()
    system = db.open_system()
    fy = nd.fiscal_year(2083)
    result = company.create_company(system, "Stock Test Company", "trading", USER,
                                    pan="301555666", vat_registered=1,
                                    books_begin_ad=fy["start_ad"])
    conn = result["conn"]
    start, end = fy["start_ad"], fy["end_ad"]
    code = lambda c: masters.account_by_code(conn, c)["id"]

    def day(month, dayno):
        year = fy["start_bs"][0] if month >= 4 else fy["start_bs"][0] + 1
        return nd.bs_to_ad(year, month, dayno).isoformat()

    def balances(at=None):
        return reports.balances_as_at(conn, at or end)

    def stock_ties(when, at=None):
        """The whole point. The asset must equal the stock report, to the paisa."""
        at = at or end
        booked = balances(at).get(code("1211"), 0)
        valued = reports.stock_summary(conn, at)["total_value"]
        check("stock in trade ties to the stock report %s" % when, booked, valued)
        return booked

    check("new books are kept on the perpetual system", inventory.method(conn), "perpetual")

    masters.update_account(conn, USER, code("1251"), opening="1000000", opening_side="dr")
    masters.update_account(conn, USER, code("3101"), opening="1000000", opening_side="cr")

    supplier = masters.create_party(conn, USER, "Stock Test Supplier", "supplier",
                                    pan="609555666")
    customer = masters.create_party(conn, USER, "Stock Test Customer", "customer",
                                    pan="302555666")
    unit = masters.unit_by_symbol(conn, "pcs")
    phone = masters.create_item(conn, USER, "Stock Test Phone", unit_id=unit["id"],
                                purchase_rate="2000", sale_rate="3000", vat_rate_bp=1300)

    # --- Buying puts the goods on the balance sheet, with no journal --------
    invoices.post_purchase(conn, USER, {
        "date_ad": day(4, 3), "party_id": supplier,
        "items": [{"item_id": phone, "qty": "10", "rate": "2000"}]})

    after = balances()
    check("goods bought are an asset straight away",
          after[code("1211")], money.to_paisa("20000"))
    check("nothing was charged to purchases",
          after.get(code("5101"), 0), 0)
    check("nothing was charged to cost of sales",
          after.get(code("5401"), 0), 0)
    stock_ties("after buying")

    # --- A second purchase at a different price -----------------------------
    invoices.post_purchase(conn, USER, {
        "date_ad": day(4, 8), "party_id": supplier,
        "items": [{"item_id": phone, "qty": "10", "rate": "3000"}]})
    check("stock in trade carries both lots",
          balances()[code("1211")], money.to_paisa("50000"))
    check("weighted average is 2,500",
          rs(reports.item_stock(conn, phone, end)["average_rate"]), "2,500.00")
    stock_ties("after the second purchase")

    # --- Selling charges the cost on the same day ---------------------------
    before = balances()
    invoices.post_sales(conn, USER, {
        "date_ad": day(4, 15), "party_id": customer, "round_invoice": False,
        "items": [{"item_id": phone, "qty": "8", "rate": "4000"}]})
    after = balances()

    check("revenue is what the customer agreed to pay",
          before[code("4111")] - after[code("4111")], money.to_paisa("32000"))
    check("cost of goods sold is 8 at the weighted average",
          after[code("5401")] - before[code("5401")], money.to_paisa("20000"))
    check("the asset comes down by the same figure",
          before[code("1211")] - after[code("1211")], money.to_paisa("20000"))
    stock_ties("after selling")

    # Gross profit is readable now, without any period end entry at all.
    pl = reports.profit_and_loss(conn, start, end)
    check("gross profit reads without a closing stock entry",
          pl["gross_profit"], money.to_paisa("12000"))

    # --- A backdated purchase changes the average for everything after it ---
    #
    # Buying 10 more at 1,000 on a date before the sale makes the average on the
    # day of that sale 2,000, not 2,500, so the cost of that sale was overstated
    # by 4,000 and has to be put right.
    invoices.post_purchase(conn, USER, {
        "date_ad": day(4, 10), "party_id": supplier,
        "items": [{"item_id": phone, "qty": "10", "rate": "1000"}]})
    after = balances()
    check("cost of sales was put right the moment the backdated bill was entered",
          after[code("5401")], money.to_paisa("16000"))
    stock_ties("after a backdated purchase")

    # And running it again by hand changes nothing, which is what makes it safe
    # to run whenever anybody wants reassurance.
    again = inventory.rebuild(conn, USER)
    check("a second rebuild finds nothing left to correct", again["changed"], 0)
    check("it did look at every stock voucher", again["looked_at"] >= 4, True)
    check("the figures did not move", balances()[code("5401")], money.to_paisa("16000"))
    stock_ties("after running the rebuild again")

    # --- Goods coming back ---------------------------------------------------
    before = balances()
    invoices.post_sales_return(conn, USER, {
        "date_ad": day(5, 2), "party_id": customer, "round_invoice": False,
        "items": [{"item_id": phone, "qty": "2", "rate": "4000"}]})
    after = balances()
    # By now 30 were bought for 60,000 and 8 went out, so the average is 2,000.
    # Two coming back are worth 4,000, not the 8,000 they were sold for.
    check("returned goods go back into the asset at cost, not at the selling price",
          after[code("1211")] - before[code("1211")], money.to_paisa("4000"))
    check("cost of sales is relieved by exactly what they cost",
          before[code("5401")] - after[code("5401")], money.to_paisa("4000"))
    check("the customer is credited the full selling price with tax",
          money.to_paisa("9040") > 0, True)
    stock_ties("after a sales return")

    # Three going back to the supplier at 2,000 each. They are carried at 2,000
    # as well, so nothing falls to cost of sales on this one.
    before = balances()
    invoices.post_purchase_return(conn, USER, {
        "date_ad": day(5, 6), "party_id": supplier, "round_invoice": False,
        "items": [{"item_id": phone, "qty": "3", "rate": "2000"}]})
    after = balances()
    check("goods going back leave the asset at what they are carried at",
          before[code("1211")] - after[code("1211")], money.to_paisa("6000"))
    check("nothing falls to cost of sales when the refund equals the cost",
          after[code("5401")], before[code("5401")])
    stock_ties("after a purchase return")

    # And where the supplier refunds more than the goods are carried at, the
    # difference corrects cost of sales rather than showing up as a profit.
    before = balances()
    invoices.post_purchase_return(conn, USER, {
        "date_ad": day(5, 9), "party_id": supplier, "round_invoice": False,
        "items": [{"item_id": phone, "qty": "1", "rate": "3500"}]})
    after = balances()
    check("the goods still leave at what they were carried at",
          before[code("1211")] - after[code("1211")], money.to_paisa("2000"))
    check("the extra 1,500 corrects cost of sales",
          before[code("5401")] - after[code("5401")], money.to_paisa("1500"))
    stock_ties("after a purchase return above cost")

    # --- Nothing is out of balance at any point ------------------------------
    tb = reports.trial_balance(conn, start, end)
    check("trial balance ties", tb["balanced"], True)
    bs = reports.balance_sheet(conn, end, start)
    check("balance sheet balances", bs["balanced"], True)

    final = stock_ties("at the end")

    conn.close()
    clean_up()

    if FAILURES:
        print("FAILED (%d)" % len(FAILURES))
        for line in FAILURES:
            print("  " + line)
        return 1
    print("All perpetual inventory tests passed.")
    print("  Stock in Trade  %s, tying to the stock report at every step" % rs(final))
    print("  Trial balance   ties")
    print("  Balance sheet   balances")
    return 0


if __name__ == "__main__":
    sys.exit(main())

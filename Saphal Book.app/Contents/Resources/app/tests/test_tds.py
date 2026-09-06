"""
Tax deducted at source, both ways.

Two different questions that are easy to run together. What this business
withheld from people it paid and owes to the department, and what its own
customers withheld from it, which is money already paid towards its own tax.

The figure that matters on the first is what is still owed at the end of a
month, because section 90 wants it deposited within twenty five days of the
month end and a wrong figure there is a penalty. So this checks the arithmetic
of opening, withheld, deposited and closing, and that the due date lands where
the Act puts it rather than where a Gregorian calendar would.

Run with:  python3 -m tests.test_tds
"""

import glob
import os
import sys

from chartered_book.core import db, money, nepali_date as nd
from chartered_book.modules import company, ledger, masters, tds

FAILURES = []
USER = "tdstest"


def check(label, got, expected):
    if got != expected:
        FAILURES.append("%s: got %s, expected %s"
                        % (label,
                           money.format_money(got) if isinstance(got, int) else got,
                           money.format_money(expected) if isinstance(expected, int) else expected))


def clean_up():
    system = db.open_system()
    system.execute("DELETE FROM companies WHERE slug LIKE 'tds_test%'")
    system.commit()
    for path in glob.glob(os.path.join(db.BOOKS_DIR, "tds_test*")):
        try:
            os.remove(path)
        except OSError:
            pass


def main():
    clean_up()
    system = db.open_system()
    year = 2083
    made = company.create_company(system, "TDS Test Firm", "service", USER,
                                  books_begin_ad=nd.fiscal_year(year)["start_ad"])
    conn = made["conn"]

    def day(month, dayno):
        return nd.bs_to_ad(year, month, dayno).isoformat()

    rent = masters.account_by_code(conn, "6201")["id"]
    cash = masters.account_by_code(conn, "1251")["id"]
    tds_rent = masters.account_by_code(conn, "2252")["id"]
    tds_svc = masters.account_by_code(conn, "2253")["id"]
    suffered = masters.account_by_code(conn, "1244")["id"]
    fees = masters.account_by_code(conn, "4121")
    fees = fees["id"] if fees else masters.account_by_code(conn, "4111")["id"]

    # Rent of fifty thousand in Shrawan, ten percent withheld under 88(1).
    ledger.post_voucher(conn, USER, {
        "voucher_type": "payment", "date_ad": day(4, 10), "narration": "Shop rent, Shrawan",
        "entries": [{"account_id": rent, "dr": "50000", "cr": 0},
                    {"account_id": tds_rent, "dr": 0, "cr": "5000"},
                    {"account_id": cash, "dr": 0, "cr": "45000"}]})

    # A consultant's fee in the same month, fifteen percent withheld.
    ledger.post_voucher(conn, USER, {
        "voucher_type": "payment", "date_ad": day(4, 20), "narration": "Consultant",
        "entries": [{"account_id": rent, "dr": "20000", "cr": 0},
                    {"account_id": tds_svc, "dr": 0, "cr": "3000"},
                    {"account_id": cash, "dr": 0, "cr": "17000"}]})

    # And a customer withholding from this firm's own bill.
    ledger.post_voucher(conn, USER, {
        "voucher_type": "journal", "date_ad": day(4, 25), "narration": "Client withheld",
        "entries": [{"account_id": suffered, "dr": "1500", "cr": 0},
                    {"account_id": fees, "dr": 0, "cr": "1500"}]})
    conn.commit()

    shrawan = tds.monthly(conn, year, 4)
    check("two sections moved in Shrawan", len(shrawan["sections"]), 2)
    check("the whole month's withholding", shrawan["totals"]["withheld"],
          money.to_paisa("8000"))
    check("nothing was deposited yet", shrawan["totals"]["deposited"], 0)
    check("so the whole lot is owed", shrawan["owing"], money.to_paisa("8000"))
    check("and it is due on 25 Bhadra", shrawan["due_bs"], "%04d-05-25" % year)
    check("which is a real date", shrawan["due_ad"],
          nd.bs_to_ad(year, 5, 25).isoformat())

    rows = {section["code"]: section for section in shrawan["sections"]}
    check("rent is under the right section", rows["2252"]["section"], "88-rent")
    check("at ten percent", rows["2252"]["rate_bp"], 1000)
    check("and the amount withheld is right", rows["2252"]["withheld"],
          money.to_paisa("5000"))
    check("the service fee is under its own section", rows["2253"]["section"], "88-svc")
    check("at fifteen percent", rows["2253"]["rate_bp"], 1500)

    # Each one names who it was withheld from, which is what the return needs.
    check("the entry behind it is listed", len(rows["2252"]["rows"]), 1)
    check("with the voucher it came from",
          rows["2252"]["rows"][0]["narration"], "Shop rent, Shrawan")

    # Tax withheld from this firm is a different figure and must not be mixed in.
    check("what customers withheld is counted apart",
          shrawan["suffered"]["added"], money.to_paisa("1500"))
    check("and is not in what is owed",
          shrawan["owing"], money.to_paisa("8000"))

    # Deposit it in Bhadra and Shrawan's liability is settled, but the deposit
    # belongs to Bhadra.
    ledger.post_voucher(conn, USER, {
        "voucher_type": "payment", "date_ad": day(5, 20), "narration": "Deposited to IRD",
        "entries": [{"account_id": tds_rent, "dr": "5000", "cr": 0},
                    {"account_id": tds_svc, "dr": "3000", "cr": 0},
                    {"account_id": cash, "dr": 0, "cr": "8000"}]})
    conn.commit()

    bhadra = tds.monthly(conn, year, 5)
    check("Bhadra opens owing what Shrawan left", bhadra["totals"]["opening"],
          money.to_paisa("8000"))
    check("Bhadra deposited it", bhadra["totals"]["deposited"], money.to_paisa("8000"))
    check("and nothing is left owing", bhadra["owing"], 0)

    # Shrawan on its own has not changed. A month already closed must not move
    # because a later month was paid.
    again = tds.monthly(conn, year, 4)
    check("Shrawan still shows what it withheld", again["totals"]["withheld"],
          money.to_paisa("8000"))
    check("and still shows nothing deposited in it", again["totals"]["deposited"], 0)

    # The whole year ties to the ledgers.
    fiscal = nd.fiscal_year(year)
    whole = tds.register(conn, fiscal["start_ad"], fiscal["end_ad"])
    check("the year withheld the same total", whole["totals"]["withheld"],
          money.to_paisa("8000"))
    check("and deposited all of it", whole["totals"]["deposited"], money.to_paisa("8000"))
    check("leaving nothing owed at the year end", whole["totals"]["closing"], 0)

    from chartered_book.modules import reports
    balances = reports.balances_as_at(conn, fiscal["end_ad"])
    check("which agrees with the rent ledger", -balances.get(tds_rent, 0), 0)
    check("and with the service fee ledger", -balances.get(tds_svc, 0), 0)
    check("and tax suffered still stands in the books",
          balances.get(suffered, 0), money.to_paisa("1500"))

    conn.commit()
    conn.close()
    clean_up()

    if FAILURES:
        print("TDS: %d problem%s" % (len(FAILURES), "" if len(FAILURES) == 1 else "s"))
        for line in FAILURES:
            print("  " + line)
        return 1
    print("TDS: what was withheld, what was paid over, and when it was due.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

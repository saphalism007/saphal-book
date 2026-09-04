"""
The schedules an audit file is built on.

Depreciation under Schedule 2 of the Income Tax Act, 2058 is worked out on
pools, with an addition absorbed in full, two thirds or one third depending on
when in the year it was bought. Getting that wrong understates or overstates
the charge for every year that follows, so every figure here is checked against
one worked by hand.

Run with:  python3 -m tests.test_schedules
"""

import glob
import os
import sys

from chartered_book.core import db, money, nepali_date as nd
from chartered_book.modules import company, masters, schedules

FAILURES = []
USER = "scheduletest"
SLUG = "schedule_test_company"


def check(label, got, expected):
    if got != expected:
        FAILURES.append("%s: got %s, expected %s"
                        % (label, money.format_money(got) if isinstance(got, int) else got,
                           money.format_money(expected) if isinstance(expected, int) else expected))


def rs(paisa):
    return money.format_money(paisa)


def clean_up():
    system = db.open_system()
    system.execute("DELETE FROM companies WHERE slug LIKE 'schedule_test%'")
    for path in glob.glob(os.path.join(db.BOOKS_DIR, SLUG + ".db*")):
        try:
            os.remove(path)
        except OSError:
            pass


def add_asset(conn, code, name, account_code, tax_class, acquired_ad, cost,
              method="wdv", rate_bp=0, life=0):
    account = masters.account_by_code(conn, account_code)
    now = db.now_stamp()
    conn.execute(
        """INSERT INTO fixed_assets (code, name, asset_account_id, tax_class, acquired_ad,
                                     acquired_bs, cost_paisa, book_method, book_rate_bp,
                                     useful_life_years, active, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
        (code, name, account["id"], tax_class, acquired_ad,
         nd.format_bs(nd.ad_to_bs(acquired_ad), "numeric"), money.to_paisa(cost),
         method, rate_bp, life, now, now))


def main():
    clean_up()
    system = db.open_system()
    fy = nd.fiscal_year(2083)
    result = company.create_company(system, "Schedule Test Company", "trading", USER,
                                    books_begin_ad=fy["start_ad"])
    conn = result["conn"]
    company.ensure_fiscal_year(conn, 2084, USER)

    def day(bs_year, month, dayno):
        return nd.bs_to_ad(bs_year, month, dayno).isoformat()

    # One asset in each of the three absorption windows.
    add_asset(conn, "FA001", "Shop building", "1112", "A",
              day(2083, 4, 1), "2000000", "slm", 0, 40)          # Shrawan, first four months
    add_asset(conn, "FA002", "Office computers", "1117", "B",
              day(2083, 8, 10), "300000", "wdv", 2500)           # Mangsir, middle four
    add_asset(conn, "FA003", "Delivery vehicle", "1118", "C",
              day(2083, 12, 5), "1200000", "wdv", 2000)          # Chaitra, last four

    # Year one, worked by hand.
    year1 = schedules.tax_depreciation(conn, 2083)
    a, b, c = year1["pools"]["A"], year1["pools"]["B"], year1["pools"]["C"]

    check("class A absorbed in full", a["absorbed"], money.to_paisa("2000000"))
    check("class A depreciation base", a["base"], money.to_paisa("2000000"))
    check("class A depreciation at 5 percent", a["depreciation"], money.to_paisa("100000"))
    check("class A carried forward", a["closing"], money.to_paisa("1900000"))

    check("class B absorbed two thirds", b["absorbed"], money.to_paisa("200000"))
    check("class B unabsorbed one third", b["unabsorbed"], money.to_paisa("100000"))
    check("class B depreciation at 25 percent", b["depreciation"], money.to_paisa("50000"))
    check("class B carried forward", b["closing"], money.to_paisa("250000"))

    check("class C absorbed one third", c["absorbed"], money.to_paisa("400000"))
    check("class C unabsorbed two thirds", c["unabsorbed"], money.to_paisa("800000"))
    check("class C depreciation at 20 percent", c["depreciation"], money.to_paisa("80000"))
    check("class C carried forward", c["closing"], money.to_paisa("1120000"))

    check("total depreciation for the year", year1["totals"]["depreciation"],
          money.to_paisa("230000"))
    check("total carried forward", year1["totals"]["closing"], money.to_paisa("3270000"))

    # Year two. Nothing bought, so the whole opening balance is the base.
    year2 = schedules.tax_depreciation(conn, 2084)
    check("year two opens where year one closed",
          year2["totals"]["opening"], money.to_paisa("3270000"))
    check("year two class A depreciation", year2["pools"]["A"]["depreciation"],
          money.to_paisa("95000"))
    check("year two class B depreciation", year2["pools"]["B"]["depreciation"],
          money.to_paisa("62500"))
    check("year two class C depreciation", year2["pools"]["C"]["depreciation"],
          money.to_paisa("224000"))
    check("year two total depreciation", year2["totals"]["depreciation"],
          money.to_paisa("381500"))

    # Selling the vehicle takes the proceeds out of the pool, not the cost.
    conn.execute("""UPDATE fixed_assets SET disposed_ad = ?, disposal_proceeds_paisa = ?
                    WHERE code = 'FA003'""",
                 (day(2084, 6, 15), money.to_paisa("900000")))
    year2b = schedules.tax_depreciation(conn, 2084)
    pool_c = year2b["pools"]["C"]
    check("disposal proceeds leave the pool", pool_c["disposals"], money.to_paisa("900000"))
    check("base after the disposal", pool_c["base"], money.to_paisa("220000"))
    check("depreciation after the disposal", pool_c["depreciation"], money.to_paisa("44000"))

    # A pool below two thousand rupees is written off in full.
    conn.execute("""UPDATE fixed_assets SET disposed_ad = ?, disposal_proceeds_paisa = ?
                    WHERE code = 'FA003'""",
                 (day(2084, 6, 15), money.to_paisa("1119000")))
    small = schedules.tax_depreciation(conn, 2084)["pools"]["C"]
    check("a pool under two thousand is written off", small["small_pool"], True)
    check("and the whole base is allowed", small["depreciation"], small["base"])
    conn.execute("UPDATE fixed_assets SET disposed_ad = '', disposal_proceeds_paisa = 0 "
                 "WHERE code = 'FA003'")

    # The register keeps the books separate from the tax working.
    register = schedules.asset_register(conn, fy["start_ad"], fy["end_ad"])
    check("three assets on the register", register["count"], 3)
    building = [r for r in register["rows"] if r["code"] == "FA001"][0]
    # Straight line over forty years, held for the whole twelve months.
    check("building written off over forty years", building["charge"], money.to_paisa("50000"))
    computers = [r for r in register["rows"] if r["code"] == "FA002"][0]
    # Bought in Mangsir, so eight months of the year at 25 percent reducing balance.
    check("computers depreciated for eight months", computers["months_held"], 8)
    check("computers charge for the books", computers["charge"], money.to_paisa("50000"))

    # Deferred tax is the difference between the two, at the company's rate.
    deferred = schedules.deferred_tax(conn, 2083)
    expected = money.apply_rate(deferred["book_value"] - deferred["tax_value"],
                                deferred["rate_bp"])
    check("deferred tax follows the difference", deferred["deferred_amount"], expected)
    check("the rate is twenty five percent", deferred["rate_bp"], 2500)

    # The movement schedule reads from the ledgers, which have nothing in them
    # here, so it should come back empty rather than guessing.
    movement = schedules.movement_schedule(conn, "1110", fy["start_ad"], fy["end_ad"])
    check("movement schedule reads the ledgers", movement["carrying_closing"], 0)

    conn.close()
    clean_up()

    if FAILURES:
        print("FAILED (%d)" % len(FAILURES))
        for line in FAILURES:
            print("  " + line)
        return 1
    print("All schedule tests passed.")
    print("  Year one tax depreciation   %s" % rs(year1["totals"]["depreciation"]))
    print("  Year two tax depreciation   %s" % rs(year2["totals"]["depreciation"]))
    print("  Pools carried forward       %s" % rs(year1["totals"]["closing"]))
    print("  Deferred tax at 25 percent  %s" % rs(deferred["deferred_amount"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())

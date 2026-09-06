"""
The entries that come round again.

Rent, salary, a loan instalment. The month one gets forgotten is the month the
accounts are wrong, so what is due is shown rather than remembered.

Three things have to hold, and none of them is the easy case.

Every month that is owed has to be listed, not only the next one. A pattern set
up in Shrawan and looked at in Mangsir owes five months, and offering one of
them would leave four quietly missing, which is the failure this exists to end.

A month must not be postable twice, because two people looking at the same
screen is ordinary and a rent charged twice is not.

And the Nepali months are of different lengths, so a pattern due on the
thirty second has to survive the months that have thirty, without being dragged
down to thirty for ever by one short month.

Run with:  python3 -m tests.test_recurring
"""

import glob
import os
import sys

from chartered_book.core import db, money, nepali_date as nd
from chartered_book.modules import company, masters, recurring, reports

FAILURES = []
USER = "recurtest"


def check(label, got, expected):
    if got != expected:
        FAILURES.append("%s: got %r, expected %r" % (label, got, expected))


def clean_up():
    system = db.open_system()
    system.execute("DELETE FROM companies WHERE slug LIKE 'recur_test%'")
    system.commit()
    for path in glob.glob(os.path.join(db.BOOKS_DIR, "recur_test*")):
        try:
            os.remove(path)
        except OSError:
            pass


def main():
    clean_up()
    system = db.open_system()
    year = nd.today_bs()[0]
    made = company.create_company(system, "Recur Test Shop", "trading", USER,
                                  books_begin_ad=nd.fiscal_year(year)["start_ad"])
    conn = made["conn"]
    company.ensure_fiscal_year(conn, year + 1, USER)

    rent = masters.account_by_code(conn, "6201")["id"]
    cash = masters.account_by_code(conn, "1251")["id"]

    # A monthly rent starting in Shrawan, looked at from the middle of Mangsir.
    # Shrawan, Bhadra, Ashwin, Kartik and Mangsir have all had a first of the
    # month, so five are owed.
    pattern = recurring.create(conn, USER, {
        "name": "Shop rent", "every": "month", "starts_bs": "%d-04-01" % year,
        "narration": "Monthly shop rent",
        "lines": [{"account_id": rent, "dr": "25000", "cr": 0},
                  {"account_id": cash, "dr": 0, "cr": "25000"}]})
    conn.commit()

    due = recurring.due_list(conn, pattern, "%d-08-15" % year)
    check("five months are owed by Mangsir", len(due), 5)
    check("oldest first", due[0]["due_bs"], "%d-04-01" % year)
    check("and the newest is Mangsir", due[-1]["due_bs"], "%d-08-01" % year)

    # Posting one makes a real, balanced entry.
    voucher_id = recurring.post_due(conn, USER, pattern, due[0]["due_bs"])
    conn.commit()
    entries = conn.execute(
        "SELECT SUM(dr_paisa) dr, SUM(cr_paisa) cr FROM voucher_entries WHERE voucher_id = ?",
        (voucher_id,)).fetchone()
    check("the entry is for the right amount", entries["dr"], money.to_paisa("25000"))
    check("and it balances", entries["dr"], entries["cr"])

    check("one fewer is owed afterwards",
          len(recurring.due_list(conn, pattern, "%d-08-15" % year)), 4)

    # Twice is the thing that must not happen.
    try:
        recurring.post_due(conn, USER, pattern, due[0]["due_bs"])
        FAILURES.append("the same month was posted twice")
    except recurring.RecurringError:
        pass

    # It has to reach the ledger, not just the voucher table.
    balances = reports.balances_as_at(conn, nd.fiscal_year(year)["end_ad"])
    check("the rent ledger has the charge", balances.get(rent), money.to_paisa("25000"))
    check("and the cash box is down by it", balances.get(cash), -money.to_paisa("25000"))

    # An entry that does not balance is refused when the pattern is made, not
    # the twelfth time it runs.
    try:
        recurring.create(conn, USER, {
            "name": "Wrong", "starts_bs": "%d-04-01" % year,
            "lines": [{"account_id": rent, "dr": "100", "cr": 0},
                      {"account_id": cash, "dr": 0, "cr": "90"}]})
        FAILURES.append("an unbalanced pattern was accepted")
    except recurring.RecurringError:
        pass

    try:
        recurring.create(conn, USER, {
            "name": "One legged", "starts_bs": "%d-04-01" % year,
            "lines": [{"account_id": rent, "dr": "100", "cr": 0}]})
        FAILURES.append("a one sided pattern was accepted")
    except recurring.RecurringError:
        pass

    # The months are different lengths. A pattern due on the thirty second has
    # to land on the last real day and then recover, not be dragged down.
    landed = []
    when = "%d-01-32" % year
    for _ in range(4):
        y, m, d = recurring._parse_bs(when)
        landed.append(recurring._format_bs(y, m, recurring._land_on(y, m, d)))
        when = recurring.step_on(when, "month")
    check("it lands on the last day of a thirty one day month",
          landed[0], "%d-01-31" % year)
    check("and recovers to the thirty second where the month has one",
          landed[2], "%d-03-32" % year)

    # Quarterly and yearly step properly.
    check("a quarter is three months on",
          recurring.step_on("%d-04-01" % year, "quarter"), "%d-07-01" % year)
    check("a year rolls the year over",
          recurring.step_on("%d-11-01" % year, "year"), "%d-11-01" % (year + 1))

    # A pattern that has ended stops owing.
    ended = recurring.create(conn, USER, {
        "name": "Finished", "every": "month",
        "starts_bs": "%d-04-01" % year, "ends_bs": "%d-05-01" % year,
        "lines": [{"account_id": rent, "dr": "100", "cr": 0},
                  {"account_id": cash, "dr": 0, "cr": "100"}]})
    conn.commit()
    check("a pattern with an end owes only up to it",
          len(recurring.due_list(conn, ended, "%d-08-15" % year)), 2)

    # Switching one off stops it owing anything.
    recurring.update(conn, USER, ended, {"active": 0,
        "lines": [{"account_id": rent, "dr": "100", "cr": 0},
                  {"account_id": cash, "dr": 0, "cr": "100"}]})
    conn.commit()
    check("a pattern switched off owes nothing",
          len(recurring.due_list(conn, ended, "%d-08-15" % year)), 0)

    # Removing a pattern leaves the entries it already made alone. Those are
    # real entries in the books.
    before = conn.execute("SELECT COUNT(*) n FROM vouchers").fetchone()["n"]
    recurring.remove(conn, USER, pattern)
    conn.commit()
    after = conn.execute("SELECT COUNT(*) n FROM vouchers").fetchone()["n"]
    check("the entries it made stay in the books", after, before)
    check("but the pattern is gone",
          conn.execute("SELECT COUNT(*) n FROM recurring WHERE id = ?",
                       (pattern,)).fetchone()["n"], 0)

    conn.commit()
    conn.close()
    clean_up()

    if FAILURES:
        print("Recurring: %d problem%s" % (len(FAILURES), "" if len(FAILURES) == 1 else "s"))
        for line in FAILURES:
            print("  " + line)
        return 1
    print("Recurring: every month that is owed is offered, and none of them twice.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

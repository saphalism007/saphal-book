"""
The Companies Act, 2063 read against the books.

Reference material tells somebody what the law says. This checks whether a
particular set of books complies with it, which is the part that is actually
work, and the part that has to be right: telling a company it has breached
section 105 when it has not is worse than saying nothing at all.

Which rules apply depends on what the entity is. Everything here is checked
twice, once on a private limited company where it should fire and once on a
sole proprietorship where the Act does not reach and it must stay silent.

Run with:  python3 -m tests.test_statute
"""

import glob
import os
import sys

from chartered_book.core import db, money, nepali_date as nd
from chartered_book.modules import audit_review, company, ledger, masters

FAILURES = []
USER = "statutetest"


def check(label, got, expected):
    if got != expected:
        FAILURES.append("%s: got %r, expected %r" % (label, got, expected))


def clean_up():
    system = db.open_system()
    system.execute("DELETE FROM companies WHERE slug LIKE 'statute_test%'")
    system.commit()
    for path in glob.glob(os.path.join(db.BOOKS_DIR, "statute_test*")):
        try:
            os.remove(path)
        except OSError:
            pass


def titles(conn, from_ad, to_ad):
    found = audit_review.review(conn, from_ad, to_ad)
    return {row["title"]: row for row in found["findings"]}


def post(conn, date_ad, pairs, narration):
    """One journal, given as (code, dr, cr) so the intent reads plainly."""
    entries = []
    for code, dr, cr in pairs:
        account = masters.account_by_code(conn, code)
        entries.append({"account_id": account["id"], "dr": dr, "cr": cr})
    ledger.post_voucher(conn, USER, {
        "voucher_type": "journal", "date_ad": date_ad,
        "narration": narration, "entries": entries})


def build(slug, name, entity_type, year):
    system = db.open_system()
    fiscal = nd.fiscal_year(year)
    made = company.create_company(system, name, "trading", USER,
                                  books_begin_ad=fiscal["start_ad"])
    conn = made["conn"]
    conn.execute("UPDATE company SET entity_type = ? WHERE id = 1", (entity_type,))
    conn.commit()
    return conn, fiscal


def main():
    clean_up()

    # A year far enough back that the six month deadline has certainly gone by,
    # so the lateness check has something real to bite on.
    old = nd.today_bs()[0] - 2

    conn, fiscal = build("statute_test_ltd", "Statute Test Company", "private_limited", old)
    day = lambda m, d: nd.bs_to_ad(old, m, d).isoformat()

    # Share capital in, then a loss that eats most of it, then money out to a
    # director. Three separate breaches in one small set of books.
    post(conn, day(4, 1), [("1251", "1000000", 0), ("3103", 0, "1000000")],
         "Share capital introduced")
    post(conn, day(5, 1), [("6201", "700000", 0), ("1251", 0, "700000")],
         "A year of rent with almost no trade")
    post(conn, day(6, 1), [("3201", "700000", 0), ("6201", 0, "700000")],
         "Loss taken to retained earnings")
    post(conn, day(7, 1), [("2113", "250000", 0), ("1251", 0, "250000")],
         "Paid out to a director")
    conn.commit()

    found = titles(conn, fiscal["start_ad"], fiscal["end_ad"])

    check("a company two years late is told so",
          "The statements for this year are late" in found, True)
    check("and it is treated as serious",
          found.get("The statements for this year are late", {}).get("severity"), "high")
    check("the section is named",
          "109" in found.get("The statements for this year are late", {}).get("reference", ""),
          True)

    check("a debit on the director account is caught",
          "The company appears to have lent to a director" in found, True)
    check("with the amount",
          found.get("The company appears to have lent to a director", {}).get("amount"),
          money.to_paisa("250000"))
    check("and section 105 named",
          "105" in found.get("The company appears to have lent to a director", {})
          .get("reference", ""), True)

    check("accumulated losses are reported",
          "Accumulated losses are being carried" in found, True)
    check("and half the capital gone is its own finding",
          "Half the share capital or more has been lost" in found, True)

    # The same books, as a sole proprietorship. The Companies Act does not reach
    # a proprietor, so every one of those has to fall silent.
    conn.execute("UPDATE company SET entity_type = 'proprietorship' WHERE id = 1")
    conn.commit()
    quiet = titles(conn, fiscal["start_ad"], fiscal["end_ad"])

    for heading in ("The statements for this year are late",
                    "The company appears to have lent to a director",
                    "Accumulated losses are being carried",
                    "Half the share capital or more has been lost"):
        check("a proprietor is not told about: " + heading, heading in quiet, False)

    conn.commit()
    conn.close()

    # A proprietor who has drawn more than was ever put in.
    conn2, fiscal2 = build("statute_test_prop", "Statute Test Trader", "proprietorship", old)
    day2 = lambda m, d: nd.bs_to_ad(old, m, d).isoformat()
    post(conn2, day2(4, 1), [("1251", "200000", 0), ("3101", 0, "200000")],
         "Capital introduced")
    post(conn2, day2(8, 1), [("3301", "350000", 0), ("1251", 0, "350000")],
         "Drawings through the year")
    conn2.commit()

    drawn = titles(conn2, fiscal2["start_ad"], fiscal2["end_ad"])
    check("drawings beyond capital are raised",
          "Drawings exceed the capital introduced" in drawn, True)
    check("with the drawings figure",
          drawn.get("Drawings exceed the capital introduced", {}).get("amount"),
          money.to_paisa("350000"))

    # And a company is not told about drawings, because it does not have any.
    conn2.execute("UPDATE company SET entity_type = 'private_limited' WHERE id = 1")
    conn2.commit()
    check("a company is not told about drawings",
          "Drawings exceed the capital introduced"
          in titles(conn2, fiscal2["start_ad"], fiscal2["end_ad"]), False)

    conn2.commit()
    conn2.close()
    clean_up()

    if FAILURES:
        print("Statute: %d problem%s" % (len(FAILURES), "" if len(FAILURES) == 1 else "s"))
        for line in FAILURES:
            print("  " + line)
        return 1
    print("Statute: the Act is applied where it reaches and nowhere else.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

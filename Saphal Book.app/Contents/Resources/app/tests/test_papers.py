"""
The paper behind the entry.

A voucher is an assertion; the bill behind it is the evidence. Kept in the
books, so a backup, a copy sent to the account and a tablet all carry it.

The things that matter here are not the happy case. A file has to come back
byte for byte, because a bill that comes back slightly wrong is worse than one
that did not come back at all. What cannot be held has to be refused before it
is written rather than after. And a paper has to leave when the entry it
belongs to leaves, or the books fill up with evidence for things that no longer
exist.

Run with:  python3 -m tests.test_papers
"""

import base64
import glob
import os
import sys

from chartered_book.core import db, nepali_date as nd
from chartered_book.modules import company, ledger, masters, papers

FAILURES = []
USER = "papertest"


def check(label, got, expected):
    if got != expected:
        FAILURES.append("%s: got %r, expected %r"
                        % (label, str(got)[:70], str(expected)[:70]))


def clean_up():
    system = db.open_system()
    system.execute("DELETE FROM companies WHERE slug LIKE 'paper_test%'")
    system.commit()
    for path in glob.glob(os.path.join(db.BOOKS_DIR, "paper_test*")):
        try:
            os.remove(path)
        except OSError:
            pass


def main():
    clean_up()
    system = db.open_system()
    fiscal = nd.fiscal_year(nd.today_bs()[0])
    made = company.create_company(system, "Paper Test Shop", "trading", USER,
                                  books_begin_ad=fiscal["start_ad"])
    conn = made["conn"]
    day = nd.bs_to_ad(nd.today_bs()[0], 4, 10).isoformat()

    cash = masters.account_by_code(conn, "1251")["id"]
    rent = masters.account_by_code(conn, "6201")["id"]
    voucher_id = ledger.post_voucher(conn, USER, {
        "voucher_type": "payment", "date_ad": day, "narration": "Shop rent",
        "entries": [{"account_id": rent, "dr": "25000", "cr": 0},
                    {"account_id": cash, "dr": 0, "cr": "25000"}]})
    conn.commit()

    # Bytes that are awkward on purpose: a zero, a high byte, and something
    # that is not valid text in any encoding. A bill scanned to a JPEG is full
    # of all three, and anything that treats the content as text mangles them.
    awkward = bytes(range(256)) * 40
    paper_id = papers.attach(conn, USER, voucher_id, "supplier bill.png",
                             "image/png", base64.b64encode(awkward).decode(),
                             note="The rent receipt")
    conn.commit()

    kept = papers.listing(conn, voucher_id)
    check("one paper is kept", len(kept), 1)
    check("under its own name", kept[0]["filename"], "supplier bill.png")
    check("with its size", kept[0]["size_bytes"], len(awkward))
    check("and it is one a browser can show", kept[0]["shows_in_place"], True)

    got = papers.fetch(conn, paper_id)
    check("it comes back byte for byte", base64.b64decode(got["content"]), awkward)
    check("with the note it was given", got["note"], "The rent receipt")

    # Stored as bytes, not as text. A megabyte kept as base64 would be four
    # thirds of one on the disk, and the books are backed up whole.
    stored = conn.execute("SELECT content FROM attachments WHERE id = ?",
                          (paper_id,)).fetchone()["content"]
    check("held as bytes rather than as text", isinstance(stored, bytes), True)
    check("and takes no more room than the file did", len(stored), len(awkward))

    # What cannot be held is refused before it is written.
    try:
        papers.attach(conn, USER, voucher_id, "setup.exe",
                      "application/x-msdownload", base64.b64encode(b"MZ").decode())
        FAILURES.append("a program was accepted into the books")
    except papers.PaperError:
        pass

    try:
        papers.attach(conn, USER, voucher_id, "huge.png", "image/png",
                      base64.b64encode(b"x" * (papers.MOST_PER_FILE + 1)).decode())
        FAILURES.append("a file over the limit was accepted")
    except papers.PaperError:
        pass

    try:
        papers.attach(conn, USER, voucher_id, "empty.png", "image/png", "")
        FAILURES.append("an empty file was accepted")
    except papers.PaperError:
        pass

    try:
        papers.attach(conn, USER, 999999, "orphan.png", "image/png",
                      base64.b64encode(b"x").decode())
        FAILURES.append("a paper was kept against an entry that does not exist")
    except papers.PaperError:
        pass

    check("nothing that was refused got in", len(papers.listing(conn, voucher_id)), 1)

    # What the books have grown to, said before somebody notices their backup
    # has got slow.
    weight = papers.how_much(conn)
    check("the total is counted", weight["count"], 1)
    check("and measured", weight["bytes"], len(awkward))
    check("and is not called heavy when it is not", weight["heavy"], False)

    # Asked for a whole list at once, so a day book does not make one enquiry
    # per row.
    counts = papers.vouchers_with_papers(conn, [voucher_id, 999999])
    check("the count comes back for the voucher that has one", counts.get(voucher_id), 1)
    check("and not for one that does not", 999999 in counts, False)

    # Removing the entry has to take its evidence with it, or the books fill up
    # with proof of things that no longer exist.
    conn.execute("DELETE FROM voucher_entries WHERE voucher_id = ?", (voucher_id,))
    conn.execute("DELETE FROM vouchers WHERE id = ?", (voucher_id,))
    conn.commit()
    check("the paper goes when the entry goes",
          conn.execute("SELECT COUNT(*) n FROM attachments").fetchone()["n"], 0)

    conn.commit()
    conn.close()
    clean_up()

    if FAILURES:
        print("Papers: %d problem%s" % (len(FAILURES), "" if len(FAILURES) == 1 else "s"))
        for line in FAILURES:
            print("  " + line)
        return 1
    print("Papers: the bill comes back exactly as it went in.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""
The paper behind the entry.

A voucher on its own is an assertion. The bill, the delivery note, the bank
advice, the cheque: those are the evidence, and on an audit the two living in
different places is most of the work. Kept here they travel with the books, so
a backup, a copy sent to the account and a tablet all carry them.

That is a deliberate choice with a cost. Papers make the books bigger, and the
books are backed up whole and sent whole, so there are limits: how large one
paper may be, and how large the whole lot may grow before somebody is told.
Both are said plainly on the screen rather than discovered when a backup starts
taking a minute.

Nothing here decides what is worth keeping. It refuses what it cannot hold and
takes everything else.
"""

import base64
import datetime

from ..core import audit

# One paper. Big enough for a photographed bill or a scanned page, small enough
# that a hundred of them do not make the books unwieldy.
MOST_PER_FILE = 5 * 1024 * 1024

# All of them together, past which the screen says so. Not a refusal: somebody
# with a real reason to keep three hundred bills should be told what it costs,
# not stopped.
WORTH_MENTIONING = 200 * 1024 * 1024

# What a browser can actually show back without downloading it first.
SHOWS_IN_PLACE = ("image/jpeg", "image/png", "image/gif", "image/webp",
                  "application/pdf")

# What is worth keeping against an entry. A spreadsheet or a document is
# ordinary supporting evidence; a program is not, and an accounting file is no
# place to carry one.
ALLOWED = SHOWS_IN_PLACE + (
    "image/heic", "image/heif", "image/tiff", "image/bmp",
    "text/plain", "text/csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel", "application/msword",
)


class PaperError(Exception):
    """Raised when a paper cannot be kept."""


def _now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def human_size(count):
    for unit in ("bytes", "KB", "MB", "GB"):
        if count < 1024 or unit == "GB":
            return "%d %s" % (count, unit) if unit == "bytes" else "%.1f %s" % (count, unit)
        count /= 1024.0
    return "%d bytes" % count


def attach(conn, username, voucher_id, filename, mime, encoded, note=""):
    """
    Keep one paper against one voucher.

    The content arrives as base64 because it has come through a screen, and a
    browser has no other way to hand over bytes. It is decoded here and stored
    as bytes, not as text, so a megabyte on the disk is a megabyte and not four
    thirds of one.
    """
    voucher = conn.execute("SELECT id, number FROM vouchers WHERE id = ?",
                           (voucher_id,)).fetchone()
    if voucher is None:
        raise PaperError("There is no such entry to keep this against.")

    filename = (filename or "").strip() or "paper"
    mime = (mime or "").strip().lower()
    if mime and mime not in ALLOWED:
        raise PaperError(
            "A %s is not something to keep in a set of books. Bills, photographs, "
            "PDFs, spreadsheets and documents are." % mime)

    try:
        content = base64.b64decode(encoded or "", validate=False)
    except Exception:                                               # noqa: BLE001
        raise PaperError("That file did not arrive in one piece. Try it again.")
    if not content:
        raise PaperError("That file is empty.")
    if len(content) > MOST_PER_FILE:
        raise PaperError(
            "That file is %s. The most one paper can be is %s. A photograph taken "
            "on a phone is usually smaller if it is taken as a document rather "
            "than at full size."
            % (human_size(len(content)), human_size(MOST_PER_FILE)))

    cursor = conn.execute(
        """INSERT INTO attachments
           (voucher_id, filename, mime, size_bytes, content, note, added_by, added_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (voucher_id, filename[:200], mime[:120], len(content), content,
         (note or "").strip()[:300], username, _now()))
    audit.log(conn, username, "paper.attach", "attachments", cursor.lastrowid,
              filename, "Kept %s against %s" % (filename, voucher["number"]), None, None)
    return cursor.lastrowid


def listing(conn, voucher_id):
    """What is kept against one voucher, without reading any of it back."""
    rows = conn.execute(
        """SELECT id, filename, mime, size_bytes, note, added_by, added_at
           FROM attachments WHERE voucher_id = ? ORDER BY id""",
        (voucher_id,)).fetchall()
    return [dict(row, size_text=human_size(row["size_bytes"]),
                 shows_in_place=row["mime"] in SHOWS_IN_PLACE) for row in rows]


def fetch(conn, paper_id):
    """One paper, content and all, ready to be handed back to the screen."""
    row = conn.execute(
        """SELECT id, voucher_id, filename, mime, size_bytes, content, note
           FROM attachments WHERE id = ?""", (paper_id,)).fetchone()
    if row is None:
        raise PaperError("That paper is not here.")
    return {"id": row["id"], "voucher_id": row["voucher_id"],
            "filename": row["filename"], "mime": row["mime"],
            "size_bytes": row["size_bytes"], "note": row["note"],
            "content": base64.b64encode(row["content"]).decode("ascii")}


def remove(conn, username, paper_id):
    """
    Take one paper away.

    The entry it belonged to is untouched. Removing evidence is worth recording,
    so it goes in the audit trail with the name of whoever did it.
    """
    row = conn.execute("SELECT id, filename, voucher_id FROM attachments WHERE id = ?",
                       (paper_id,)).fetchone()
    if row is None:
        raise PaperError("That paper is not here.")
    conn.execute("DELETE FROM attachments WHERE id = ?", (paper_id,))
    audit.log(conn, username, "paper.remove", "attachments", paper_id,
              row["filename"], "Removed %s" % row["filename"], None, None)
    return True


def how_much(conn):
    """
    What the papers have grown to, and whether that is worth mentioning.

    Said before somebody notices their backup has got slow, rather than after.
    """
    row = conn.execute(
        "SELECT COUNT(*) AS n, COALESCE(SUM(size_bytes), 0) AS bytes FROM attachments"
    ).fetchone()
    return {"count": row["n"], "bytes": row["bytes"],
            "size_text": human_size(row["bytes"]),
            "heavy": row["bytes"] > WORTH_MENTIONING,
            "limit_per_file": MOST_PER_FILE,
            "limit_per_file_text": human_size(MOST_PER_FILE)}


def vouchers_with_papers(conn, voucher_ids):
    """
    How many papers each of these vouchers has.

    Asked for a whole list at once so a day book does not make one enquiry per
    row, which is the difference between a screen that opens and one that
    crawls once there are a few hundred entries.
    """
    if not voucher_ids:
        return {}
    marks = ", ".join("?" for _ in voucher_ids)
    rows = conn.execute(
        "SELECT voucher_id, COUNT(*) AS n FROM attachments "
        "WHERE voucher_id IN (%s) GROUP BY voucher_id" % marks,
        list(voucher_ids)).fetchall()
    return {row["voucher_id"]: row["n"] for row in rows}

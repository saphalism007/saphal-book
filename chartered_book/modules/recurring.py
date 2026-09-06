"""
The entries that come round again.

Rent, salary, the electricity standing charge, a loan instalment, the monthly
depreciation charge. The same entry every month, typed again every month, and
the month it gets forgotten is the month the accounts are wrong.

Kept here as a pattern with the double entry it makes, so what is due can be
shown and posted rather than remembered.

Nothing posts itself, and that is deliberate. A voucher that appeared in the
books without anybody agreeing to it is worse than one that was forgotten,
because a forgotten one gets noticed and an invented one does not. What this
removes is the remembering, not the deciding.

Dates are Bikram Sambat throughout, because the months these things follow are
Nepali months. A rent due on the first of every month is due on the first of
Shrawan, not on the sixteenth of July.
"""

from ..core import audit, money, nepali_date as nd
from . import ledger

EVERY = {"month": 1, "quarter": 3, "year": 12}


class RecurringError(Exception):
    """Raised when a pattern cannot be made or run."""


def _now():
    from ..core import db
    return db.now_stamp()


def _parse_bs(text):
    """A Bikram Sambat date written 2083-04-01, as three numbers."""
    try:
        year, month, day = [int(part) for part in str(text).split("-")]
    except (ValueError, AttributeError):
        raise RecurringError("A date has to be written like 2083-04-01.")
    return year, month, day


def _format_bs(year, month, day):
    return "%04d-%02d-%02d" % (year, month, day)


def step_on(due_bs, every):
    """
    The next time after this one.

    A pattern due on the thirty second of a month has to survive the months
    that have thirty. It is pulled back to the last day of the month it lands
    in, and the day it was asked for is kept, so a run of months goes 32, 30,
    32 rather than being dragged down to 30 for ever by one short month.
    """
    months = EVERY.get(every)
    if not months:
        raise RecurringError("A pattern runs monthly, quarterly or yearly.")
    year, month, day = _parse_bs(due_bs)
    month += months
    while month > 12:
        month -= 12
        year += 1
    return _format_bs(year, month, day)


def _land_on(year, month, day):
    """Pull a day back to the last one the month actually has."""
    try:
        longest = nd.daysInMonth(year, month) if hasattr(nd, "daysInMonth") else None
    except Exception:                                               # noqa: BLE001
        longest = None
    if longest is None:
        longest = _days_in_month(year, month)
    return min(day, longest)


def _days_in_month(year, month):
    """How many days a Bikram Sambat month has, asked of the calendar itself."""
    for day in (32, 31, 30, 29):
        try:
            nd.bs_to_ad(year, month, day)
            return day
        except Exception:                                           # noqa: BLE001
            continue
    return 30


def to_ad(due_bs):
    """The ordinary date a Bikram Sambat due date falls on."""
    year, month, day = _parse_bs(due_bs)
    return nd.bs_to_ad(year, month, _land_on(year, month, day)).isoformat()


def create(conn, username, payload):
    """
    Set up one pattern.

    The double entry is checked here rather than when it runs, because a
    pattern that will not post is worse the twelfth time than the first.
    """
    name = (payload.get("name") or "").strip()
    if not name:
        raise RecurringError("Give it a name you will recognise in a list.")
    every = payload.get("every") or "month"
    if every not in EVERY:
        raise RecurringError("A pattern runs monthly, quarterly or yearly.")

    starts = (payload.get("starts_bs") or "").strip()
    if not starts:
        raise RecurringError("Say when it starts.")
    _parse_bs(starts)
    ends = (payload.get("ends_bs") or "").strip()
    if ends:
        _parse_bs(ends)
        if ends < starts:
            raise RecurringError("It cannot end before it starts.")

    lines = _clean_lines(conn, payload.get("lines") or [])

    cursor = conn.execute(
        """INSERT INTO recurring
           (name, voucher_type, every, day_of_month, starts_bs, ends_bs, next_due_bs,
            party_id, narration, note, active, created_by, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)""",
        (name[:120], payload.get("voucher_type") or "journal", every,
         _parse_bs(starts)[2], starts, ends, starts,
         payload.get("party_id") or None,
         (payload.get("narration") or "").strip()[:300],
         (payload.get("note") or "").strip()[:300],
         username, _now(), _now()))
    pattern_id = cursor.lastrowid
    _write_lines(conn, pattern_id, lines)
    audit.log(conn, username, "recurring.create", "recurring", pattern_id, name,
              "Set up %s, %s from %s" % (name, every, starts), None, None)
    return pattern_id


def update(conn, username, pattern_id, payload):
    """Change a pattern. What it has already posted is left alone."""
    row = conn.execute("SELECT * FROM recurring WHERE id = ?", (pattern_id,)).fetchone()
    if row is None:
        raise RecurringError("There is no such pattern.")
    lines = _clean_lines(conn, payload.get("lines") or [])
    every = payload.get("every") or row["every"]
    if every not in EVERY:
        raise RecurringError("A pattern runs monthly, quarterly or yearly.")
    ends = (payload.get("ends_bs") or "").strip()
    if ends:
        _parse_bs(ends)

    conn.execute(
        """UPDATE recurring SET name = ?, every = ?, ends_bs = ?, party_id = ?,
                  narration = ?, note = ?, active = ?, updated_at = ?
           WHERE id = ?""",
        ((payload.get("name") or row["name"]).strip()[:120], every, ends,
         payload.get("party_id") or None,
         (payload.get("narration") or "").strip()[:300],
         (payload.get("note") or "").strip()[:300],
         1 if payload.get("active", 1) else 0, _now(), pattern_id))
    conn.execute("DELETE FROM recurring_lines WHERE recurring_id = ?", (pattern_id,))
    _write_lines(conn, pattern_id, lines)
    audit.log(conn, username, "recurring.update", "recurring", pattern_id,
              row["name"], "Changed %s" % row["name"], None, None)
    return True


def _clean_lines(conn, raw):
    """The double entry, checked now rather than every time it runs."""
    lines = []
    total_dr = total_cr = 0
    for index, row in enumerate(raw, start=1):
        account_id = row.get("account_id")
        if not account_id:
            continue
        account = conn.execute("SELECT id, name FROM accounts WHERE id = ?",
                               (account_id,)).fetchone()
        if account is None:
            raise RecurringError("Line %d points at a ledger that is not there." % index)
        dr = money.to_paisa(row.get("dr") or 0)
        cr = money.to_paisa(row.get("cr") or 0)
        if dr and cr:
            raise RecurringError("Line %d is on both sides at once." % index)
        if dr < 0 or cr < 0:
            raise RecurringError("Line %d cannot be a negative amount." % index)
        if not dr and not cr:
            continue
        total_dr += dr
        total_cr += cr
        lines.append({"account_id": account_id, "dr": dr, "cr": cr,
                      "narration": (row.get("narration") or "").strip()[:200]})
    if len(lines) < 2:
        raise RecurringError("An entry needs at least two lines.")
    if total_dr != total_cr:
        raise RecurringError(
            "It does not balance. Debits come to %s and credits to %s."
            % (money.format_money(total_dr), money.format_money(total_cr)))
    return lines


def _write_lines(conn, pattern_id, lines):
    conn.executemany(
        """INSERT INTO recurring_lines
           (recurring_id, line_no, account_id, dr_paisa, cr_paisa, narration)
           VALUES (?, ?, ?, ?, ?, ?)""",
        [(pattern_id, n, line["account_id"], line["dr"], line["cr"], line["narration"])
         for n, line in enumerate(lines, start=1)])


def listing(conn, as_at_bs=None):
    """
    Every pattern, with what it owes and what it has already made.

    The number due is the point of the screen, so it is worked out here rather
    than left for the screen to count.
    """
    as_at_bs = as_at_bs or _format_bs(*nd.today_bs())
    out = []
    for row in conn.execute("SELECT * FROM recurring ORDER BY active DESC, name"):
        pattern = dict(row)
        pattern["lines"] = [dict(line) for line in conn.execute(
            """SELECT l.*, a.code AS account_code, a.name AS account_name
               FROM recurring_lines l JOIN accounts a ON a.id = l.account_id
               WHERE l.recurring_id = ? ORDER BY l.line_no""", (row["id"],))]
        pattern["amount"] = sum(line["dr_paisa"] for line in pattern["lines"])
        pattern["due"] = due_list(conn, row["id"], as_at_bs)
        pattern["due_count"] = len(pattern["due"])
        pattern["posted_count"] = conn.execute(
            "SELECT COUNT(*) AS n FROM recurring_posted WHERE recurring_id = ?",
            (row["id"],)).fetchone()["n"]
        out.append(pattern)
    return {"rows": out, "as_at_bs": as_at_bs,
            "due_total": sum(p["due_count"] for p in out)}


def due_list(conn, pattern_id, as_at_bs=None):
    """
    Every date this pattern owes up to today, oldest first.

    Every one, not only the next. A pattern set up in Shrawan and looked at in
    Mangsir owes four months, and showing one of them would leave three quietly
    missing, which is exactly the failure this is meant to end.
    """
    as_at_bs = as_at_bs or _format_bs(*nd.today_bs())
    row = conn.execute("SELECT * FROM recurring WHERE id = ?", (pattern_id,)).fetchone()
    if row is None or not row["active"]:
        return []

    already = {done["due_bs"] for done in conn.execute(
        "SELECT due_bs FROM recurring_posted WHERE recurring_id = ?", (pattern_id,))}

    due = []
    when = row["starts_bs"]
    # A guard on the loop rather than trust in the dates: a pattern with a
    # start far in the past should give a long list, not run for ever.
    for _ in range(400):
        if when > as_at_bs:
            break
        if row["ends_bs"] and when > row["ends_bs"]:
            break
        if when not in already:
            year, month, day = _parse_bs(when)
            landed = _format_bs(year, month, _land_on(year, month, day))
            due.append({"due_bs": landed, "date_ad": to_ad(when)})
        when = step_on(when, row["every"])
    return due


def post_due(conn, username, pattern_id, due_bs):
    """
    Make the entry for one date.

    Refused where that date has already been made, which is what stops a month
    being posted twice by two people looking at the same screen.
    """
    row = conn.execute("SELECT * FROM recurring WHERE id = ?", (pattern_id,)).fetchone()
    if row is None:
        raise RecurringError("There is no such pattern.")
    if not row["active"]:
        raise RecurringError("That pattern has been switched off.")

    done = conn.execute(
        "SELECT voucher_id FROM recurring_posted WHERE recurring_id = ? AND due_bs = ?",
        (pattern_id, due_bs)).fetchone()
    if done is not None:
        raise RecurringError("That one has already been posted.")

    lines = conn.execute(
        "SELECT * FROM recurring_lines WHERE recurring_id = ? ORDER BY line_no",
        (pattern_id,)).fetchall()
    if not lines:
        raise RecurringError("That pattern has no entry to make.")

    voucher_id = ledger.post_voucher(conn, username, {
        "voucher_type": row["voucher_type"] or "journal",
        "date_ad": to_ad(due_bs),
        "party_id": row["party_id"],
        "narration": row["narration"] or row["name"],
        "entries": [{"account_id": line["account_id"],
                     "dr": money.to_rupees(line["dr_paisa"]),
                     "cr": money.to_rupees(line["cr_paisa"]),
                     "narration": line["narration"]} for line in lines],
    })

    conn.execute(
        """INSERT INTO recurring_posted (recurring_id, due_bs, voucher_id, posted_by, posted_at)
           VALUES (?, ?, ?, ?, ?)""",
        (pattern_id, due_bs, voucher_id, username, _now()))
    conn.execute("UPDATE recurring SET next_due_bs = ?, updated_at = ? WHERE id = ?",
                 (step_on(due_bs, row["every"]), _now(), pattern_id))
    audit.log(conn, username, "recurring.post", "recurring", pattern_id, row["name"],
              "Posted %s for %s" % (row["name"], due_bs), None, None)
    return voucher_id


def remove(conn, username, pattern_id):
    """
    Take a pattern away.

    What it has already posted stays. Those are real entries in the books and
    have nothing to do with whether the pattern goes on running.
    """
    row = conn.execute("SELECT name FROM recurring WHERE id = ?", (pattern_id,)).fetchone()
    if row is None:
        raise RecurringError("There is no such pattern.")
    conn.execute("DELETE FROM recurring WHERE id = ?", (pattern_id,))
    audit.log(conn, username, "recurring.remove", "recurring", pattern_id, row["name"],
              "Removed the pattern %s. Entries already posted are untouched."
              % row["name"], None, None)
    return True

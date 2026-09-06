"""
Tax deducted at source, both ways.

Two questions, and they are not the same one. What this business withheld from
people it paid, and owes to the Inland Revenue Department. And what its own
customers withheld from it, which is money already paid towards its own tax and
comes off the bill at the end of the year.

Both are read off the ledgers rather than from anything typed twice, so what
this says and what the trial balance says cannot drift apart.

What it deliberately does not do is work out what should have been deducted.
Whether a payment attracts tax, and at what rate, depends on who was paid and
what for, and a program guessing at that would produce a return somebody signs
without having thought about it. The rate on each ledger is shown alongside so
the two can be compared by eye, which is the part that is actually work.
"""

from ..core import money
from . import reports

# The ledgers tax withheld is carried in, and the one that carries tax withheld
# from this business. Codes rather than names, because a name can be edited and
# a code is what the chart is built on.
WITHHELD = ("2251", "2252", "2253", "2254", "2255", "2256", "2257")
SUFFERED = "1244"


def register(conn, from_ad, to_ad):
    """
    Everything withheld and everything paid over, section by section.

    A credit on one of these ledgers is tax withheld from somebody. A debit is
    that tax being paid over to the department. What is left at the end is what
    is still owed, and it is the figure that has to be nil after the fifteenth
    of the following month.
    """
    from . import masters

    opening = reports.balances_as_at(conn, _day_before(from_ad))
    sections = []
    totals = {"opening": 0, "withheld": 0, "deposited": 0, "closing": 0}

    for code in WITHHELD:
        account = masters.account_by_code(conn, code)
        if account is None:
            continue
        rows = _entries(conn, account["id"], from_ad, to_ad)
        withheld = sum(row["cr_paisa"] for row in rows)
        deposited = sum(row["dr_paisa"] for row in rows)
        # These are liabilities, so a credit balance is what is owed. Held the
        # right way up here rather than leaving every reader to negate it.
        opened = -opening.get(account["id"], 0)
        if not (rows or opened):
            continue
        section = _section(conn, account["tds_section"])
        sections.append({
            "code": code, "name": account["name"],
            "section": account["tds_section"] or "",
            "section_name": section["description"] if section else "",
            "rate_bp": account["tds_rate_bp"] or (section["rate_bp"] if section else 0),
            "opening": opened, "withheld": withheld, "deposited": deposited,
            "closing": opened + withheld - deposited,
            "rows": rows,
        })
        totals["opening"] += opened
        totals["withheld"] += withheld
        totals["deposited"] += deposited
        totals["closing"] += opened + withheld - deposited

    return {"from_ad": from_ad, "to_ad": to_ad,
            "sections": sections, "totals": totals,
            "suffered": suffered(conn, from_ad, to_ad)}


def suffered(conn, from_ad, to_ad):
    """
    Tax this business's own customers withheld from it.

    A debit is tax withheld from a bill; it is money already paid towards this
    year's income tax and comes off at the end of the computation. A credit is
    it being taken off, which happens when the year is settled.
    """
    from . import masters
    account = masters.account_by_code(conn, SUFFERED)
    if account is None:
        return {"rows": [], "opening": 0, "added": 0, "used": 0, "closing": 0,
                "name": "", "code": SUFFERED}
    opening = reports.balances_as_at(conn, _day_before(from_ad)).get(account["id"], 0)
    rows = _entries(conn, account["id"], from_ad, to_ad)
    added = sum(row["dr_paisa"] for row in rows)
    used = sum(row["cr_paisa"] for row in rows)
    return {"code": SUFFERED, "name": account["name"], "rows": rows,
            "opening": opening, "added": added, "used": used,
            "closing": opening + added - used}


def _entries(conn, account_id, from_ad, to_ad):
    """Every movement on one ledger, with who it was with."""
    rows = conn.execute(
        """SELECT e.dr_paisa, e.cr_paisa, e.narration AS line_narration,
                  v.id AS voucher_id, v.number, v.date_ad, v.date_bs,
                  v.voucher_type, v.narration,
                  p.name AS party_name, p.pan AS party_pan
           FROM voucher_entries e
           JOIN vouchers v ON v.id = e.voucher_id
           LEFT JOIN parties p ON p.id = v.party_id
           WHERE e.account_id = ? AND v.status = 'posted'
             AND v.date_ad >= ? AND v.date_ad <= ?
           ORDER BY v.date_ad, v.id""",
        (account_id, from_ad, to_ad)).fetchall()
    return [{
        "voucher_id": row["voucher_id"], "number": row["number"],
        "date_ad": row["date_ad"], "date_bs": row["date_bs"],
        "voucher_type": row["voucher_type"],
        "party_name": row["party_name"] or "",
        "party_pan": row["party_pan"] or "",
        "narration": row["line_narration"] or row["narration"] or "",
        "dr_paisa": row["dr_paisa"], "cr_paisa": row["cr_paisa"],
    } for row in rows]


def _section(conn, code):
    if not code:
        return None
    row = conn.execute(
        "SELECT code, description, rate_bp, legal_ref FROM tds_sections WHERE code = ?",
        (code,)).fetchone()
    return dict(row) if row else None


def _day_before(date_ad):
    import datetime
    try:
        day = datetime.date.fromisoformat(date_ad) - datetime.timedelta(days=1)
        return day.isoformat()
    except (ValueError, TypeError):
        return date_ad


def monthly(conn, bs_year, bs_month):
    """
    One Bikram Sambat month, which is how tax withheld is actually deposited.

    Section 90 asks for it within twenty five days of the month end, so the
    month is the unit that matters and the due date is worked out here rather
    than counted on a calendar.
    """
    from ..core import nepali_date as nd
    start = nd.bs_to_ad(bs_year, bs_month, 1).isoformat()
    last = 32
    while last > 28:
        try:
            end = nd.bs_to_ad(bs_year, bs_month, last).isoformat()
            break
        except Exception:                                           # noqa: BLE001
            last -= 1
    else:
        end = start

    found = register(conn, start, end)
    due_year, due_month = (bs_year, bs_month + 1) if bs_month < 12 else (bs_year + 1, 1)
    try:
        due = nd.bs_to_ad(due_year, due_month, 25).isoformat()
    except Exception:                                               # noqa: BLE001
        due = ""
    found["bs_year"] = bs_year
    found["bs_month"] = bs_month
    found["due_ad"] = due
    found["due_bs"] = "%04d-%02d-25" % (due_year, due_month)
    found["owing"] = found["totals"]["closing"]
    return found


def format_rate(rate_bp):
    return "%s%%" % money.format_rate(rate_bp) if hasattr(money, "format_rate") \
        else "%.1f%%" % (rate_bp / 100.0)

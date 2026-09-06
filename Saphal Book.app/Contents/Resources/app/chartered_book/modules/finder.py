"""
Finding one thing, without knowing which screen it is on.

Somebody looking for invoice SI0042, or for Sharma Nirman, or for the ledger
they call rates and taxes, should be able to type it and be taken there. Until
now they had to know that an invoice lives on the day book, a customer on the
records screen and a ledger somewhere else again, which is knowledge about the
software rather than about the books.

Four things are searched, and only four, because a search that returns
everything is a list and not an answer: entries, people, items and ledgers.

Each result carries where it lives and what to open, so the screen can take
somebody there rather than only telling them it exists.
"""

from ..core import money

# Enough of a word to mean something. One letter matches half the books and
# tells nobody anything.
SHORTEST = 2

# Per kind, so one busy kind cannot crowd out the others. A person typing a
# supplier name wants that supplier even if forty of their bills match too.
MOST_PER_KIND = 8


def search(conn, text, limit_per_kind=MOST_PER_KIND):
    """
    Look for one piece of text across the things worth finding.

    Case does not matter and neither does where in the word it falls, because
    somebody looking for a customer types the part of the name they remember,
    which is rarely the beginning.
    """
    text = (text or "").strip()
    if len(text) < SHORTEST:
        return {"query": text, "groups": [], "count": 0,
                "note": "Type a little more." if text else ""}

    like = "%" + text.replace("%", "").replace("_", "") + "%"
    groups = []

    entries = _entries(conn, like, text, limit_per_kind)
    if entries:
        groups.append({"kind": "entries", "title": "Entries", "rows": entries})

    people = _people(conn, like, limit_per_kind)
    if people:
        groups.append({"kind": "people", "title": "Customers and suppliers", "rows": people})

    things = _items(conn, like, limit_per_kind)
    if things:
        groups.append({"kind": "items", "title": "Items", "rows": things})

    ledgers = _ledgers(conn, like, limit_per_kind)
    if ledgers:
        groups.append({"kind": "ledgers", "title": "Ledgers", "rows": ledgers})

    found = sum(len(group["rows"]) for group in groups)
    return {"query": text, "groups": groups, "count": found,
            "note": "" if found else "Nothing matches that."}


def _entries(conn, like, text, limit):
    """
    Vouchers by their number, by who they were with, or by what was written on
    them. A cancelled one is still shown, marked as cancelled, because somebody
    searching for a number usually wants to know what became of it.
    """
    rows = conn.execute(
        """SELECT v.id, v.number, v.voucher_type, v.date_ad, v.date_bs, v.status,
                  v.total_paisa, v.narration, p.name AS party_name
           FROM vouchers v LEFT JOIN parties p ON p.id = v.party_id
           WHERE v.number LIKE ? OR v.narration LIKE ? OR p.name LIKE ?
                 OR v.reference_no LIKE ?
           ORDER BY (v.number = ?) DESC, v.date_ad DESC, v.id DESC
           LIMIT ?""",
        (like, like, like, like, text.upper(), limit)).fetchall()
    return [{
        "id": row["id"], "label": row["number"],
        "detail": " · ".join(part for part in (
            (row["party_name"] or ""), (row["narration"] or "")[:60]) if part),
        "amount": row["total_paisa"], "date_bs": row["date_bs"], "date_ad": row["date_ad"],
        "voucher_type": row["voucher_type"],
        "cancelled": row["status"] == "cancelled",
        "opens": "voucher",
    } for row in rows]


def _people(conn, like, limit):
    rows = conn.execute(
        """SELECT id, code, name, party_type, pan, phone, mobile, account_id
           FROM parties
           WHERE name LIKE ? OR code LIKE ? OR pan LIKE ? OR phone LIKE ? OR mobile LIKE ?
           ORDER BY active DESC, name
           LIMIT ?""", (like, like, like, like, like, limit)).fetchall()
    return [{
        "id": row["id"], "label": row["name"],
        "detail": " · ".join(part for part in (
            row["party_type"] or "", ("PAN " + row["pan"]) if row["pan"] else "",
            row["mobile"] or row["phone"] or "") if part),
        "account_id": row["account_id"],
        "opens": "party",
    } for row in rows]


def _items(conn, like, limit):
    rows = conn.execute(
        """SELECT i.id, i.code, i.name, i.hs_code, u.name AS unit, i.sale_rate_paisa
           FROM items i LEFT JOIN units u ON u.id = i.unit_id
           WHERE i.name LIKE ? OR i.code LIKE ? OR i.barcode LIKE ? OR i.hs_code LIKE ?
           ORDER BY i.active DESC, i.name
           LIMIT ?""", (like, like, like, like, limit)).fetchall()
    return [{
        "id": row["id"], "label": row["name"],
        "detail": " · ".join(part for part in (
            row["code"] or "", ("HS " + row["hs_code"]) if row["hs_code"] else "",
            ("sells at " + money.format_money(row["sale_rate_paisa"]))
            if row["sale_rate_paisa"] else "") if part),
        "opens": "item",
    } for row in rows]


def _ledgers(conn, like, limit):
    rows = conn.execute(
        """SELECT a.id, a.code, a.name, g.name AS group_name
           FROM accounts a JOIN account_groups g ON g.id = a.group_id
           WHERE a.name LIKE ? OR a.code LIKE ?
           ORDER BY a.active DESC, a.code
           LIMIT ?""", (like, like, limit)).fetchall()
    return [{
        "id": row["id"], "label": row["name"],
        "detail": "%s · %s" % (row["code"], row["group_name"]),
        "opens": "ledger",
    } for row in rows]

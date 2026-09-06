"""
Finding one thing, without knowing which screen it is on.

Somebody looking for invoice SI0042, or for Sharma Nirman, or for the ledger
they call rates and taxes, types it and is taken there. Knowing that an invoice
lives on the day book, a customer on the records screen and a ledger somewhere
else again is knowledge about the software rather than about the books.

Two things make this useful rather than merely present.

It matches the way people type. Half a word, two words in the wrong order, a
letter missed out. "sharma nir" finds Sharma Nirman Company, "cemnt" finds
cement, "0042" finds SI0042. Anything less and a search only works for somebody
who already knew the answer.

And it ranks. A search that returns forty things in the order the database
happened to hold them has moved the problem rather than solved it, so what was
typed is scored against what was found: an exact match first, then the start of
a word, then somewhere inside, then the letters in order with gaps.
"""

from ..core import money

# Enough of a word to mean something. One letter matches half the books.
SHORTEST = 2

# Per kind, so one busy kind cannot crowd out the others. A person typing a
# supplier name wants that supplier even if forty of their bills match too.
MOST_PER_KIND = 8

# How many rows are pulled back before scoring. Wider than what is shown,
# because the best answer is often not the one the database returns first.
CANDIDATES = 60


class Match(object):
    """How well one piece of text answers what was typed."""

    EXACT = 1000
    STARTS = 700
    WORD_STARTS = 500
    CONTAINS = 300
    SCATTERED = 120
    NOTHING = 0


def score(text, tokens):
    """
    How well one piece of text answers what was typed.

    Every token has to be found somewhere, otherwise this is not a match at
    all. The score is the best each token managed, added up, with a bonus for
    short text so that "Rent" beats "Repair and Maintenance, Rented Equipment"
    when somebody types rent.
    """
    if not text:
        return Match.NOTHING
    low = text.lower()
    total = 0
    for token in tokens:
        best = _one(low, token)
        if not best:
            return Match.NOTHING
        total += best
    # A shorter answer to the same query is usually the one meant.
    return total + max(0, 60 - len(low))


def _one(low, token):
    if low == token:
        return Match.EXACT
    if low.startswith(token):
        return Match.STARTS
    for word in low.replace(",", " ").replace("-", " ").split():
        if word.startswith(token):
            return Match.WORD_STARTS
    if token in low:
        return Match.CONTAINS
    return Match.SCATTERED if _scattered(low, token) else Match.NOTHING


def _scattered(low, token):
    """
    The letters in order, close together, with a little in between.

    This is what makes a missed letter survivable: cemnt still finds cement and
    sharman still finds Sharma Nirman.

    Close together is the important half. Without it, cemnt also matches Office
    Equipment, because those letters do appear in that order if you are allowed
    to wander the whole word to find them, and an answer arrived at that way is
    noise. The letters have to sit within roughly the space the word itself
    would take.
    """
    if len(token) < 3 or len(token) > 12:
        return False
    # Try each place the first letter appears, because the tight run may not
    # start at the first one.
    start = low.find(token[0])
    while start >= 0:
        at = start + 1
        ok = True
        for letter in token[1:]:
            at = low.find(letter, at)
            if at < 0:
                ok = False
                break
            at += 1
        if ok and (at - start) <= len(token) + 3:
            return True
        start = low.find(token[0], start + 1)
    return False


def _tokens(text):
    return [word for word in (text or "").lower().split() if word]


def search(conn, text, limit_per_kind=MOST_PER_KIND):
    """One search across the things worth finding, best answers first."""
    text = (text or "").strip()
    if len(text) < SHORTEST:
        return {"query": text, "groups": [], "count": 0,
                "note": "Type a little more." if text else ""}

    tokens = _tokens(text)
    groups = []
    for kind, title, gather in (
            ("entries", "Entries", _entries),
            ("people", "Customers and suppliers", _people),
            ("items", "Items", _items),
            ("ledgers", "Ledgers", _ledgers)):
        rows = _both_ways(gather, conn, tokens, text)
        rows.sort(key=lambda row: -row["score"])
        rows = rows[:limit_per_kind]
        if rows:
            groups.append({"kind": kind, "title": title, "rows": rows})

    # The kind with the best single answer goes first, so typing an invoice
    # number does not put four customers above the invoice.
    groups.sort(key=lambda group: -group["rows"][0]["score"])

    found = sum(len(group["rows"]) for group in groups)
    return {"query": text, "groups": groups, "count": found,
            "note": "" if found else "Nothing matches that."}


def _like(tokens, columns, scattered=False):
    """
    Pull back anything that could possibly match, to be scored properly after.

    Every token has to appear in at least one of the columns, which is the
    cheap half of the test. The expensive half, where in the text it appears
    and therefore how good a match it is, happens in Python.

    Where scattered is asked for, a token is matched letter by letter with
    anything in between, which is what lets cemnt find cement. It is a slower
    pattern for the database, so it is only used when the plain one found
    nothing at all.
    """
    clauses, args = [], []
    for token in tokens:
        safe = token.replace("%", "").replace("_", "")
        pattern = "%" + safe + "%"
        if scattered and 3 <= len(safe) <= 12:
            pattern = "%" + "%".join(safe) + "%"
        wanted = " OR ".join("%s LIKE ?" % column for column in columns)
        clauses.append("(%s)" % wanted)
        args.extend([pattern for _ in columns])
    return " AND ".join(clauses), args


def _both_ways(gather, conn, tokens, text):
    """
    The plain search first, and the forgiving one only if it found nothing.

    Almost every search is spelled correctly, so the common case stays cheap
    and the letter by letter pattern is kept for the one that was not.
    """
    rows = [row for row in gather(conn, tokens, text, False)
            if row["score"] > Match.NOTHING]
    if rows:
        return rows
    return [row for row in gather(conn, tokens, text, True)
            if row["score"] > Match.NOTHING]


def _entries(conn, tokens, text, scattered=False):
    """
    Vouchers by number, by who they were with, by what was written on them.

    A cancelled one still shows, marked cancelled, because somebody searching
    for a number usually wants to know what became of it.
    """
    where, args = _like(tokens, ["v.number", "v.narration", "p.name", "v.reference_no"], scattered)
    rows = conn.execute(
        """SELECT v.id, v.number, v.voucher_type, v.date_ad, v.date_bs, v.status,
                  v.total_paisa, v.narration, v.reference_no, p.name AS party_name
           FROM vouchers v LEFT JOIN parties p ON p.id = v.party_id
           WHERE %s
           ORDER BY v.date_ad DESC, v.id DESC
           LIMIT ?""" % where, args + [CANDIDATES]).fetchall()

    out = []
    for row in rows:
        best = max(score(row["number"], tokens),
                   score(row["party_name"], tokens),
                   score(row["narration"], tokens),
                   score(row["reference_no"], tokens))
        # A voucher number typed in full is what somebody wants above anything
        # else that happens to contain the same letters.
        if (row["number"] or "").lower() == text.lower():
            best += Match.EXACT
        out.append({
            "id": row["id"], "label": row["number"],
            "detail": " · ".join(part for part in (
                (row["party_name"] or ""), (row["narration"] or "")[:60]) if part),
            "amount": row["total_paisa"], "date_bs": row["date_bs"],
            "date_ad": row["date_ad"], "voucher_type": row["voucher_type"],
            "cancelled": row["status"] == "cancelled",
            "opens": "voucher", "score": best,
        })
    return out


def _people(conn, tokens, text, scattered=False):
    where, args = _like(tokens, ["name", "code", "pan", "phone", "mobile"], scattered)
    rows = conn.execute(
        """SELECT id, code, name, party_type, pan, phone, mobile, account_id, active
           FROM parties WHERE %s ORDER BY active DESC LIMIT ?""" % where,
        args + [CANDIDATES]).fetchall()
    return [{
        "id": row["id"], "label": row["name"],
        "detail": " · ".join(part for part in (
            row["party_type"] or "", ("PAN " + row["pan"]) if row["pan"] else "",
            row["mobile"] or row["phone"] or "") if part),
        "account_id": row["account_id"], "opens": "party",
        "score": max(score(row["name"], tokens), score(row["code"], tokens),
                     score(row["pan"], tokens)) + (0 if row["active"] else -200),
    } for row in rows]


def _items(conn, tokens, text, scattered=False):
    where, args = _like(tokens, ["i.name", "i.code", "i.barcode", "i.hs_code"], scattered)
    rows = conn.execute(
        """SELECT i.id, i.code, i.name, i.hs_code, i.active, u.name AS unit,
                  i.sale_rate_paisa
           FROM items i LEFT JOIN units u ON u.id = i.unit_id
           WHERE %s ORDER BY i.active DESC LIMIT ?""" % where,
        args + [CANDIDATES]).fetchall()
    return [{
        "id": row["id"], "label": row["name"],
        "detail": " · ".join(part for part in (
            row["code"] or "", ("HS " + row["hs_code"]) if row["hs_code"] else "",
            ("sells at " + money.format_money(row["sale_rate_paisa"]))
            if row["sale_rate_paisa"] else "") if part),
        "opens": "item",
        "score": max(score(row["name"], tokens), score(row["code"], tokens),
                     score(row["hs_code"], tokens)) + (0 if row["active"] else -200),
    } for row in rows]


def _ledgers(conn, tokens, text, scattered=False):
    where, args = _like(tokens, ["a.name", "a.code", "g.name"], scattered)
    rows = conn.execute(
        """SELECT a.id, a.code, a.name, a.active, g.name AS group_name
           FROM accounts a JOIN account_groups g ON g.id = a.group_id
           WHERE %s ORDER BY a.active DESC LIMIT ?""" % where,
        args + [CANDIDATES]).fetchall()
    return [{
        "id": row["id"], "label": row["name"],
        "detail": "%s · %s" % (row["code"], row["group_name"]),
        "opens": "ledger",
        # The group name counts for less than the ledger's own name: somebody
        # typing "rent" wants the rent ledger, not every ledger that happens to
        # sit under a group with rent in its name.
        "score": max(score(row["name"], tokens), score(row["code"], tokens),
                     score(row["group_name"], tokens) // 3)
                 + (0 if row["active"] else -200),
    } for row in rows]

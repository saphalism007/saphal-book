"""
Stock on the perpetual system.

Under the periodic system a purchase is charged to Purchases and nothing is
carried as an asset until a closing stock entry is passed at the year end. That
is sound, and it is what most Nepali trading houses have always done, but it
means the balance sheet shows no stock for eleven months of the year and gross
profit cannot be read until somebody remembers to pass the entry.

Under the perpetual system the goods are an asset from the moment they arrive:

    Purchase        debit  Stock in Trade          what the goods cost
                    credit the supplier            with the tax on top

    Sale            debit  the customer            what he agreed to pay
                    credit Sales                   the same, net of tax
                    debit  Cost of Goods Sold      what those goods cost us
                    credit Stock in Trade          the same

Cost is the weighted average on the day the goods went out, worked out by
replaying every movement of that item up to that point. Replaying rather than
keeping a running figure is what makes a backdated invoice safe: it changes the
average for everything after it, and the rebuild below puts the cost of sales
right on every voucher that was affected.

Nothing here decides what an item is worth. That is the stock ledger's job and
it has not changed. This module only decides which accounts the value lands in.
"""

from ..core import audit, money
from . import masters

STOCK_IN_TRADE = "1211"
COST_OF_GOODS_SOLD = "5401"
STOCK_SHORTAGE = "7304"

# Which way each kind of voucher moves goods, and therefore which way the value
# moves between Stock in Trade and Cost of Goods Sold.
DIRECTION = {"purchase": 1, "purchase_return": -1, "sales": -1, "sales_return": 1}


class InventoryError(Exception):
    """Raised when the stock postings cannot be worked out."""


def method(conn):
    """Which system this company keeps its stock on."""
    row = conn.execute("SELECT inventory_method FROM company WHERE id = 1").fetchone()
    return (row["inventory_method"] if row else "perpetual") or "perpetual"


def is_perpetual(conn):
    return method(conn) == "perpetual"


def set_method(conn, wanted, username="system"):
    """
    Move the books between the two systems.

    Changing this changes which accounts new entries land in, so the entries
    already posted are rebuilt straight afterwards. It is not something to do
    in the middle of a year without knowing why.
    """
    if wanted not in ("perpetual", "periodic"):
        raise InventoryError("Stock is kept either on the perpetual or the periodic system.")
    conn.execute("UPDATE company SET inventory_method = ? WHERE id = 1", (wanted,))
    audit.log(conn, username, "company.inventory_method", "company", 1, wanted,
              "Stock is now kept on the %s system" % wanted, None, None)
    return wanted


def account_id(conn, code, label):
    row = masters.account_by_code(conn, code)
    if row is None:
        raise InventoryError(
            "The %s account (code %s) is missing from the chart of accounts." % (label, code))
    return row["id"]


def holds_stock(conn, item_id):
    """Whether an item is goods whose quantity and value are being kept."""
    row = conn.execute(
        "SELECT item_type, maintain_stock FROM items WHERE id = ?", (item_id,)).fetchone()
    return bool(row and row["item_type"] == "goods" and row["maintain_stock"])


# What goods cost on the day they moved


def _running(conn, item_id, upto_ad, before_id=None):
    """
    Replay an item's movements and give back the quantity and value on hand.

    Movements are read in the order they are stored, by date and then by the
    order they were entered, so a voucher entered later on the same day comes
    after one entered earlier. Where a stock ledger id is given, the replay
    stops just before it. That is what lets a voucher be valued as at the moment
    it happened rather than as at today, which is the whole trick behind putting
    the cost of sales right after somebody enters a backdated bill.
    """
    item = conn.execute("SELECT opening_qty, opening_value_paisa FROM items WHERE id = ?",
                        (item_id,)).fetchone()
    if item is None:
        raise InventoryError("That item no longer exists.")
    qty = item["opening_qty"]
    value = item["opening_value_paisa"]

    sql = """SELECT s.id, s.direction, s.qty, s.value_paisa
             FROM stock_ledger s JOIN vouchers v ON v.id = s.voucher_id
             WHERE s.item_id = ? AND v.status = 'posted'"""
    args = [item_id]
    if before_id is None:
        sql += " AND s.date_ad <= ?"
        args.append(upto_ad)
    else:
        sql += " AND (s.date_ad < ? OR (s.date_ad = ? AND s.id < ?))"
        args.extend([upto_ad, upto_ad, before_id])
    sql += " ORDER BY s.date_ad, s.id"

    for move in conn.execute(sql, args):
        qty, value, _ = _apply(qty, value, move["direction"], move["qty"], move["value_paisa"])
    return qty, value


def _apply(qty, value, direction, move_qty, move_value):
    """
    Move one lot in or out and give back the new position and what it cost.

    Goods coming in add their value. Goods going out take away their share of
    what is on hand, which is the weighted average. Where more is going out than
    is on hand the whole value goes, because there is nothing left to carry.
    """
    if direction > 0:
        return qty + move_qty, value + move_value, move_value
    if move_qty >= qty or qty <= 0:
        cost = value
        return qty - move_qty, 0, cost
    cost = money.round_half_up(value * move_qty, qty)
    return qty - move_qty, value - cost, cost


def plan(conn, voucher_code, lines, date_ad, before_id=None):
    """
    Work out, once, what every stock line on a voucher does.

    This is the only place the figure is arrived at. The posting engine writes
    it into the stock ledger and the invoice builder charges the same figure to
    the accounts, so the balance on Stock in Trade and the value in the stock
    report can never drift apart. Two figures worked out twice is how an
    inventory goes wrong.

    Each line comes back with the quantity that moves, which way it moves, and
    the value that moves with it:

      Bought          what the goods cost, after every discount
      Sold            their share of the weighted average on the day
      Sold and back   what one of them is carried at on the day
      Bought and back their share of the weighted average on the day
    """
    direction = DIRECTION.get(voucher_code, 0)
    out = []
    position = {}
    for line in lines:
        item_id = line.get("item_id")
        qty = int(line.get("qty") or 0) + int(line.get("free_qty") or 0)
        if not direction or not item_id or not qty or not holds_stock(conn, item_id):
            out.append(None)
            continue
        if item_id not in position:
            position[item_id] = _running(conn, item_id, date_ad, before_id)
        on_hand, held = position[item_id]

        if direction > 0:
            if voucher_code == "purchase":
                value = int(line.get("taxable") or 0)
            else:
                # Goods a customer sends back come in at what they cost us, not
                # at what we sold them for.
                value = money.round_half_up(qty * _carrying_rate(conn, item_id, date_ad,
                                                                 on_hand, held),
                                            money.QTY_SCALE)
            on_hand, held, moved = _apply(on_hand, held, 1, qty, value)
        else:
            on_hand, held, moved = _apply(on_hand, held, -1, qty, 0)
            value = moved

        position[item_id] = (on_hand, held)
        out.append({"item_id": item_id, "qty": qty, "direction": direction, "value": value,
                    "rate": money.round_half_up(value * money.QTY_SCALE, qty) if qty else 0})
    return out


def _carrying_rate(conn, item_id, date_ad, on_hand, held):
    """
    What one unit is carried at. The weighted average of what is on hand, and
    where there is none on hand, the last price it was bought at.
    """
    if on_hand > 0 and held > 0:
        return money.round_half_up(held * money.QTY_SCALE, on_hand)
    last = conn.execute(
        """SELECT vi.taxable_paisa, vi.qty, vi.free_qty FROM voucher_items vi
           JOIN vouchers v ON v.id = vi.voucher_id
           WHERE vi.item_id = ? AND v.status = 'posted' AND v.voucher_type = 'purchase'
             AND v.date_ad <= ?
           ORDER BY v.date_ad DESC, v.id DESC LIMIT 1""", (item_id, date_ad)).fetchone()
    if last:
        moved = (last["qty"] or 0) + (last["free_qty"] or 0)
        if moved:
            return money.round_half_up((last["taxable_paisa"] or 0) * money.QTY_SCALE, moved)
    row = conn.execute("SELECT purchase_rate_paisa FROM items WHERE id = ?",
                       (item_id,)).fetchone()
    return row["purchase_rate_paisa"] if row else 0


# Putting the cost of sales right again


# Only these three carry lines whose value depends on the weighted average, so
# only these three ever need rebuilding. A purchase goes into stock at what the
# supplier charged, which no later entry can change.
REBUILDABLE = ("sales", "sales_return", "purchase_return")


def entries_for(conn, voucher_code, rows, goods_value=0):
    """
    The lines that move value between Stock in Trade and Cost of Goods Sold.

    One function, used both when a voucher is first posted and when it is
    rebuilt afterwards, so the two can never disagree about what a voucher
    ought to look like.
    """
    moved = sum(row["value"] for row in rows if row)
    if not moved:
        return []
    stock = account_id(conn, STOCK_IN_TRADE, "stock in trade")
    cogs = account_id(conn, COST_OF_GOODS_SOLD, "cost of goods sold")

    if voucher_code == "sales":
        return [(cogs, moved, 0, "Cost of the goods sold"),
                (stock, 0, moved, "Goods out of stock")]
    if voucher_code == "sales_return":
        return [(stock, moved, 0, "Goods back into stock at cost"),
                (cogs, 0, moved, "Cost of the goods returned")]
    if voucher_code == "purchase_return":
        lines = [(stock, 0, moved, "Goods out of stock at what they are carried at")]
        difference = goods_value - moved
        if difference:
            lines.append((cogs, 0 if difference > 0 else -difference,
                          difference if difference > 0 else 0,
                          "Difference between the credit note and what the goods cost"))
        return lines
    return []


def rebuild(conn, username, from_ad=None, to_ad=None):
    """
    Walk every voucher that moves goods, in the order it happened, and put the
    cost of sales right.

    A backdated bill changes the weighted average for everything entered after
    it. Under the periodic system that did not matter, because cost was worked
    out once at the year end. Under the perpetual system it matters on every
    sale, so this is run whenever a voucher lands earlier than the last one and
    whenever somebody asks for it.

    Nothing is invented here. Each voucher is valued again from the movements
    that genuinely came before it, and where the answer differs from what is
    posted, the posted figure is replaced and the change is written to the audit
    log. Quantities, prices, parties and tax are never touched.
    """
    if not is_perpetual(conn):
        return {"looked_at": 0, "changed": 0, "method": method(conn)}

    stock = account_id(conn, STOCK_IN_TRADE, "stock in trade")
    cogs = account_id(conn, COST_OF_GOODS_SOLD, "cost of goods sold")

    sql = """SELECT DISTINCT v.id, v.voucher_type, v.number, v.date_ad,
                    v.taxable_paisa + v.exempt_paisa AS goods_value
             FROM vouchers v JOIN stock_ledger s ON s.voucher_id = v.id
             WHERE v.status = 'posted'"""
    args = []
    if from_ad:
        sql += " AND v.date_ad >= ?"
        args.append(from_ad)
    if to_ad:
        sql += " AND v.date_ad <= ?"
        args.append(to_ad)
    sql += " ORDER BY v.date_ad, v.id"

    looked_at = changed = 0
    for voucher in conn.execute(sql, args).fetchall():
        looked_at += 1
        if voucher["voucher_type"] not in REBUILDABLE:
            continue

        first = conn.execute(
            "SELECT MIN(id) AS id FROM stock_ledger WHERE voucher_id = ?",
            (voucher["id"],)).fetchone()["id"]
        lines = conn.execute(
            """SELECT id, item_id, qty, free_qty, taxable_paisa AS taxable
               FROM voucher_items WHERE voucher_id = ? ORDER BY line_no""",
            (voucher["id"],)).fetchall()
        rows = plan(conn, voucher["voucher_type"],
                    [{"item_id": r["item_id"], "qty": r["qty"], "free_qty": r["free_qty"],
                      "taxable": r["taxable"]} for r in lines],
                    voucher["date_ad"], before_id=first)

        touched = False

        # The stock ledger first, because everything after this voucher is
        # valued from what it leaves behind.
        for line, row in zip(lines, rows):
            if row is None:
                continue
            movement = conn.execute(
                "SELECT id, rate_paisa, value_paisa FROM stock_ledger WHERE voucher_item_id = ?",
                (line["id"],)).fetchone()
            if movement is None:
                continue
            if movement["value_paisa"] != row["value"] or movement["rate_paisa"] != row["rate"]:
                conn.execute(
                    "UPDATE stock_ledger SET rate_paisa = ?, value_paisa = ? WHERE id = ?",
                    (row["rate"], row["value"], movement["id"]))
                touched = True

        # Then the two accounting lines that go with it.
        wanted = entries_for(conn, voucher["voucher_type"], rows, voucher["goods_value"] or 0)
        held = conn.execute(
            """SELECT id, account_id, dr_paisa, cr_paisa, narration FROM voucher_entries
               WHERE voucher_id = ? AND account_id IN (?, ?) ORDER BY line_no""",
            (voucher["id"], stock, cogs)).fetchall()
        same = ([(r["account_id"], r["dr_paisa"], r["cr_paisa"]) for r in held]
                == [(a, d, c) for a, d, c, _ in wanted])
        if not same:
            for row in held:
                conn.execute("DELETE FROM voucher_entries WHERE id = ?", (row["id"],))
            next_line = conn.execute(
                "SELECT COALESCE(MAX(line_no), 0) AS n FROM voucher_entries WHERE voucher_id = ?",
                (voucher["id"],)).fetchone()["n"]
            for account, dr, cr, narration in wanted:
                next_line += 1
                conn.execute(
                    """INSERT INTO voucher_entries (voucher_id, line_no, account_id,
                                                    dr_paisa, cr_paisa, narration)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (voucher["id"], next_line, account, dr, cr, narration))
            touched = True

        if touched:
            changed += 1
            audit.log(conn, username, "inventory.rebuild", "vouchers", voucher["id"],
                      "%s %s" % (voucher["voucher_type"], voucher["number"]),
                      "Cost of sales on %s recomputed after a change to what came before it"
                      % voucher["number"], None, {"date_ad": voucher["date_ad"]})

    conn.execute("UPDATE company SET stock_rebuild_pending = 0 WHERE id = 1")
    return {"looked_at": looked_at, "changed": changed, "method": "perpetual"}


# Moving a set of books that already exist onto the perpetual system


PERIODIC_ONLY = ("5301", "5302")


def convert_existing(conn, username):
    """
    Move books that were kept on the periodic system onto the perpetual one.

    Three things have to happen, and all three are things the owner would
    otherwise have to do by hand.

    Goods already bought are moved out of Purchases and into Stock in Trade,
    because under the perpetual system they were an asset from the day they
    arrived. Nothing about the supplier, the tax or the quantity is touched.

    The opening and closing stock entries are cancelled. Those two accounts only
    exist to make the periodic system work; leaving them would count the same
    stock twice. They are cancelled and not deleted, with the reason recorded,
    so the old workings can still be read.

    Then the cost of sales is rebuilt on every sale, in date order.

    This runs once. It is the only thing in the software that rewrites entries
    that were already posted, which is why it says so plainly in the audit log
    for every voucher it touches.
    """
    stock = account_id(conn, STOCK_IN_TRADE, "stock in trade")
    purchase_group = conn.execute(
        "SELECT id FROM account_groups WHERE code = '5100'").fetchone()
    purchase_accounts = set()
    if purchase_group:
        purchase_accounts = {row["id"] for row in conn.execute(
            "SELECT id FROM accounts WHERE group_id = ?", (purchase_group["id"],))}

    moved = 0
    for voucher in conn.execute(
            """SELECT DISTINCT v.id, v.number, v.date_ad FROM vouchers v
               JOIN stock_ledger s ON s.voucher_id = v.id
               WHERE v.status = 'posted' AND v.voucher_type = 'purchase'
               ORDER BY v.date_ad, v.id""").fetchall():
        lines = conn.execute(
            """SELECT vi.item_id, vi.taxable_paisa, i.purchase_account_id
               FROM voucher_items vi JOIN items i ON i.id = vi.item_id
               WHERE vi.voucher_id = ?""", (voucher["id"],)).fetchall()
        wanted = {}
        for line in lines:
            target = stock if holds_stock(conn, line["item_id"]) else line["purchase_account_id"]
            if not target:
                target = stock
            wanted[target] = wanted.get(target, 0) + (line["taxable_paisa"] or 0)

        watched = purchase_accounts | {stock}
        held = conn.execute(
            """SELECT id, account_id, dr_paisa, cr_paisa FROM voucher_entries
               WHERE voucher_id = ? ORDER BY line_no""", (voucher["id"],)).fetchall()
        current = {row["account_id"]: row["dr_paisa"] - row["cr_paisa"]
                   for row in held if row["account_id"] in watched}
        if current == {k: v for k, v in wanted.items() if v}:
            continue

        for row in held:
            if row["account_id"] in watched:
                conn.execute("DELETE FROM voucher_entries WHERE id = ?", (row["id"],))
        line_no = conn.execute(
            "SELECT COALESCE(MAX(line_no), 0) AS n FROM voucher_entries WHERE voucher_id = ?",
            (voucher["id"],)).fetchone()["n"]
        for account, amount in wanted.items():
            if not amount:
                continue
            line_no += 1
            conn.execute(
                """INSERT INTO voucher_entries (voucher_id, line_no, account_id,
                                                dr_paisa, cr_paisa, narration)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (voucher["id"], line_no, account, amount, 0,
                 "Goods into stock" if account == stock else ""))
        moved += 1
        audit.log(conn, username, "inventory.convert", "vouchers", voucher["id"],
                  voucher["number"],
                  "Goods on %s moved from Purchases into Stock in Trade when these books "
                  "went onto the perpetual system" % voucher["number"], None, None)

    cancelled = _cancel_periodic_entries(conn, username)
    rebuilt = rebuild(conn, username)
    return {"purchases_moved": moved, "period_end_cancelled": cancelled,
            "cost_of_sales_rebuilt": rebuilt["changed"]}


def _cancel_periodic_entries(conn, username):
    """
    Cancel the opening and closing stock entries.

    Those accounts belong to the periodic system and mean nothing once stock is
    carried as an asset all year. Cancelled rather than removed, with the reason
    on the voucher, so anybody looking at last year can still see what was done.
    """
    from . import ledger
    codes = ",".join("?" for _ in PERIODIC_ONLY)
    rows = conn.execute(
        """SELECT DISTINCT v.id FROM vouchers v
           JOIN voucher_entries e ON e.voucher_id = v.id
           JOIN accounts a ON a.id = e.account_id
           WHERE v.status = 'posted' AND a.code IN (%s)""" % codes,
        PERIODIC_ONLY).fetchall()
    for row in rows:
        ledger.cancel_voucher(
            conn, username, row["id"],
            "Cancelled when these books moved onto the perpetual system. Stock is now "
            "carried as an asset from the day the goods arrive, so an opening or closing "
            "stock entry would count the same goods twice.")
    return len(rows)

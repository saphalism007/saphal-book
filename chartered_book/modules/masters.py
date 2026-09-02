"""
Masters: accounts, parties, items, groups, units and warehouses.

A party and its ledger account are created together and stay linked. That way a
customer appears by name on an invoice and as a ledger in the trial balance
without anyone having to remember to make both.
"""

from ..core import audit, db, money


class MasterError(Exception):
    """Raised when a master record cannot be saved."""


def _next_code(conn, table, prefix, width=4):
    row = conn.execute(
        "SELECT code FROM %s WHERE code LIKE ? ORDER BY LENGTH(code) DESC, code DESC LIMIT 1"
        % table, (prefix + "%",)).fetchone()
    number = 1
    if row:
        tail = row["code"][len(prefix):]
        if tail.isdigit():
            number = int(tail) + 1
    while conn.execute("SELECT 1 FROM %s WHERE code = ?" % table,
                       ("%s%0*d" % (prefix, width, number),)).fetchone():
        number += 1
    return "%s%0*d" % (prefix, width, number)


# Account groups and accounts


def account_groups(conn, statement=None):
    sql = "SELECT * FROM account_groups WHERE active = 1"
    args = []
    if statement:
        sql += " AND statement = ?"
        args.append(statement)
    sql += " ORDER BY sort_order, code"
    return conn.execute(sql, args).fetchall()


def group_by_code(conn, code):
    return conn.execute("SELECT * FROM account_groups WHERE code = ?", (code,)).fetchone()


def accounts(conn, only_active=True, group_id=None, kind=None, search=None):
    sql = """SELECT a.*, g.code AS group_code, g.name AS group_name, g.nature, g.statement
             FROM accounts a JOIN account_groups g ON g.id = a.group_id WHERE 1 = 1"""
    args = []
    if only_active:
        sql += " AND a.active = 1"
    if group_id:
        sql += " AND a.group_id = ?"
        args.append(group_id)
    if kind:
        sql += " AND a.account_kind = ?"
        args.append(kind)
    if search:
        sql += " AND (a.name LIKE ? OR a.code LIKE ? OR a.name_np LIKE ?)"
        term = "%" + search + "%"
        args += [term, term, term]
    sql += " ORDER BY g.sort_order, a.code"
    return conn.execute(sql, args).fetchall()


def get_account(conn, account_id):
    return conn.execute(
        """SELECT a.*, g.code AS group_code, g.name AS group_name, g.nature, g.statement
           FROM accounts a JOIN account_groups g ON g.id = a.group_id WHERE a.id = ?""",
        (account_id,)).fetchone()


def account_by_code(conn, code):
    return conn.execute("SELECT * FROM accounts WHERE code = ?", (code,)).fetchone()


def create_account(conn, username, name, group_id, **fields):
    name = str(name).strip()
    if not name:
        raise MasterError("Account name is required.")
    group = conn.execute("SELECT * FROM account_groups WHERE id = ?", (group_id,)).fetchone()
    if group is None:
        raise MasterError("Choose a group for the account.")
    clash = conn.execute("SELECT id FROM accounts WHERE name = ? COLLATE NOCASE", (name,)).fetchone()
    if clash:
        raise MasterError("An account named %s already exists." % name)
    code = (fields.get("code") or "").strip() or _next_code(conn, "accounts", group["code"][:2], 4)
    if conn.execute("SELECT id FROM accounts WHERE code = ?", (code,)).fetchone():
        code = _next_code(conn, "accounts", group["code"][:2], 4)
    now = db.now_stamp()
    cur = conn.execute(
        """INSERT INTO accounts (code, name, name_np, group_id, account_kind, opening_paisa,
                                 party_id, bank_name, bank_account_no, bank_branch,
                                 tds_section, tds_rate_bp, vat_rate_bp, reconcilable,
                                 is_system, active, notes, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 1, ?, ?, ?)""",
        (code, name, fields.get("name_np", ""), group_id,
         fields.get("account_kind", "general"),
         money.to_paisa(fields.get("opening") or 0) * (1 if fields.get("opening_side", "dr") == "dr" else -1),
         fields.get("party_id"), fields.get("bank_name", ""), fields.get("bank_account_no", ""),
         fields.get("bank_branch", ""), fields.get("tds_section", ""),
         int(fields.get("tds_rate_bp") or 0), int(fields.get("vat_rate_bp") or 0),
         int(fields.get("reconcilable") or 0), fields.get("notes", ""), now, now))
    audit.log(conn, username, "account.create", "accounts", cur.lastrowid, code,
              "Ledger %s created under %s." % (name, group["name"]))
    return cur.lastrowid


def update_account(conn, username, account_id, **fields):
    before = get_account(conn, account_id)
    if before is None:
        raise MasterError("That account no longer exists.")
    editable = ("name", "name_np", "group_id", "account_kind", "bank_name", "bank_account_no",
                "bank_branch", "tds_section", "tds_rate_bp", "vat_rate_bp", "reconcilable",
                "active", "notes")
    sets, args = [], []
    for key in editable:
        if key in fields:
            sets.append("%s = ?" % key)
            args.append(fields[key])
    if "opening" in fields:
        side = fields.get("opening_side", "dr")
        amount = money.to_paisa(fields["opening"])
        sets.append("opening_paisa = ?")
        args.append(amount if side == "dr" else -amount)
    if before["is_system"] and fields.get("active") == 0:
        raise MasterError("%s is used by the software itself and cannot be switched off."
                          % before["name"])
    if not sets:
        return
    sets.append("updated_at = ?")
    args.append(db.now_stamp())
    args.append(account_id)
    conn.execute("UPDATE accounts SET %s WHERE id = ?" % ", ".join(sets), args)
    audit.log(conn, username, "account.update", "accounts", account_id, before["code"],
              "Ledger %s updated." % before["name"], dict(before), fields)


def delete_account(conn, username, account_id):
    account = get_account(conn, account_id)
    if account is None:
        raise MasterError("That account no longer exists.")
    if account["is_system"]:
        raise MasterError("%s is a system account and cannot be deleted." % account["name"])
    used = conn.execute("SELECT COUNT(*) AS n FROM voucher_entries WHERE account_id = ?",
                        (account_id,)).fetchone()["n"]
    if used:
        raise MasterError("%s has %d postings against it. Switch it off instead of deleting."
                          % (account["name"], used))
    conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
    audit.log(conn, username, "account.delete", "accounts", account_id, account["code"],
              "Ledger %s deleted." % account["name"], dict(account), None)


# Parties


def parties(conn, party_type=None, only_active=True, search=None):
    sql = """SELECT p.*, a.code AS account_code, a.opening_paisa
             FROM parties p LEFT JOIN accounts a ON a.id = p.account_id WHERE 1 = 1"""
    args = []
    if only_active:
        sql += " AND p.active = 1"
    if party_type:
        sql += " AND (p.party_type = ? OR p.party_type = 'both')"
        args.append(party_type)
    if search:
        sql += " AND (p.name LIKE ? OR p.code LIKE ? OR p.pan LIKE ? OR p.mobile LIKE ?)"
        term = "%" + search + "%"
        args += [term, term, term, term]
    sql += " ORDER BY p.name"
    return conn.execute(sql, args).fetchall()


def get_party(conn, party_id):
    return conn.execute(
        """SELECT p.*, a.code AS account_code, a.name AS account_name
           FROM parties p LEFT JOIN accounts a ON a.id = p.account_id WHERE p.id = ?""",
        (party_id,)).fetchone()


def create_party(conn, username, name, party_type="customer", **fields):
    """Create a party together with the ledger account it posts to."""
    name = str(name).strip()
    if not name:
        raise MasterError("Party name is required.")
    if party_type not in ("customer", "supplier", "both", "employee", "other"):
        raise MasterError("Unknown party type %r" % party_type)
    if conn.execute("SELECT id FROM parties WHERE name = ? COLLATE NOCASE", (name,)).fetchone():
        raise MasterError("A party named %s already exists." % name)

    pan = (fields.get("pan") or "").strip()
    if pan:
        if not pan.isdigit() or len(pan) != 9:
            raise MasterError("A Nepali PAN is nine digits. Check %r." % pan)
        clash = conn.execute("SELECT name FROM parties WHERE pan = ?", (pan,)).fetchone()
        if clash:
            raise MasterError("PAN %s already belongs to %s." % (pan, clash["name"]))

    group_code = {"customer": "1220", "supplier": "2210", "both": "1220",
                  "employee": "1230", "other": "1220"}[party_type]
    group = group_by_code(conn, group_code)
    kind = {"customer": "party_customer", "supplier": "party_supplier",
            "both": "party_customer", "employee": "general",
            "other": "party_customer"}[party_type]
    prefix = {"customer": "CU", "supplier": "SU", "both": "CU",
              "employee": "EM", "other": "PT"}[party_type]
    code = (fields.get("code") or "").strip() or _next_code(conn, "parties", prefix, 4)

    account_id = create_account(
        conn, username, name, group["id"],
        code=_next_code(conn, "accounts", group_code[:3], 4),
        account_kind=kind, name_np=fields.get("name_np", ""),
        opening=fields.get("opening") or 0,
        opening_side=fields.get("opening_side", "dr" if party_type != "supplier" else "cr"))

    now = db.now_stamp()
    cur = conn.execute(
        """INSERT INTO parties (code, name, name_np, party_type, account_id, pan, vat_registered,
                                contact_person, address, city, district, phone, mobile, email,
                                credit_limit_paisa, credit_days, tds_applicable, tds_section,
                                active, notes, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)""",
        (code, name, fields.get("name_np", ""), party_type, account_id, pan,
         1 if fields.get("vat_registered") else 0, fields.get("contact_person", ""),
         fields.get("address", ""), fields.get("city", ""), fields.get("district", ""),
         fields.get("phone", ""), fields.get("mobile", ""), fields.get("email", ""),
         money.to_paisa(fields.get("credit_limit") or 0), int(fields.get("credit_days") or 0),
         1 if fields.get("tds_applicable") else 0, fields.get("tds_section", ""),
         fields.get("notes", ""), now, now))
    party_id = cur.lastrowid
    conn.execute("UPDATE accounts SET party_id = ? WHERE id = ?", (party_id, account_id))
    audit.log(conn, username, "party.create", "parties", party_id, code,
              "%s %s created." % (party_type.title(), name))
    return party_id


def update_party(conn, username, party_id, **fields):
    before = get_party(conn, party_id)
    if before is None:
        raise MasterError("That party no longer exists.")
    editable = ("name", "name_np", "party_type", "pan", "vat_registered", "contact_person",
                "address", "city", "district", "phone", "mobile", "email", "credit_days",
                "tds_applicable", "tds_section", "active", "notes")
    sets, args = [], []
    for key in editable:
        if key in fields:
            sets.append("%s = ?" % key)
            args.append(fields[key])
    if "credit_limit" in fields:
        sets.append("credit_limit_paisa = ?")
        args.append(money.to_paisa(fields["credit_limit"]))
    if not sets:
        return
    sets.append("updated_at = ?")
    args.append(db.now_stamp())
    args.append(party_id)
    conn.execute("UPDATE parties SET %s WHERE id = ?" % ", ".join(sets), args)
    if "name" in fields and before["account_id"]:
        conn.execute("UPDATE accounts SET name = ?, updated_at = ? WHERE id = ?",
                     (fields["name"], db.now_stamp(), before["account_id"]))
    if "opening" in fields and before["account_id"]:
        side = fields.get("opening_side", "dr")
        amount = money.to_paisa(fields["opening"])
        conn.execute("UPDATE accounts SET opening_paisa = ? WHERE id = ?",
                     (amount if side == "dr" else -amount, before["account_id"]))
    audit.log(conn, username, "party.update", "parties", party_id, before["code"],
              "Party %s updated." % before["name"], dict(before), fields)


# Items


def items(conn, only_active=True, group_id=None, item_type=None, search=None):
    sql = """SELECT i.*, g.name AS group_name, u.symbol AS unit_symbol, u.name AS unit_name
             FROM items i LEFT JOIN item_groups g ON g.id = i.group_id
             LEFT JOIN units u ON u.id = i.unit_id WHERE 1 = 1"""
    args = []
    if only_active:
        sql += " AND i.active = 1"
    if group_id:
        sql += " AND i.group_id = ?"
        args.append(group_id)
    if item_type:
        sql += " AND i.item_type = ?"
        args.append(item_type)
    if search:
        sql += " AND (i.name LIKE ? OR i.code LIKE ? OR i.barcode LIKE ? OR i.name_np LIKE ?)"
        term = "%" + search + "%"
        args += [term, term, term, term]
    sql += " ORDER BY i.name"
    return conn.execute(sql, args).fetchall()


def get_item(conn, item_id):
    return conn.execute(
        """SELECT i.*, g.name AS group_name, u.symbol AS unit_symbol
           FROM items i LEFT JOIN item_groups g ON g.id = i.group_id
           LEFT JOIN units u ON u.id = i.unit_id WHERE i.id = ?""", (item_id,)).fetchone()


def create_item(conn, username, name, **fields):
    name = str(name).strip()
    if not name:
        raise MasterError("Item name is required.")
    if conn.execute("SELECT id FROM items WHERE name = ? COLLATE NOCASE", (name,)).fetchone():
        raise MasterError("An item named %s already exists." % name)
    item_type = fields.get("item_type", "goods")
    if item_type not in ("goods", "service"):
        raise MasterError("An item is either goods or a service.")
    code = (fields.get("code") or "").strip() or _next_code(
        conn, "items", "SV" if item_type == "service" else "IT", 4)
    if conn.execute("SELECT id FROM items WHERE code = ?", (code,)).fetchone():
        raise MasterError("Item code %s is already used." % code)

    opening_qty = money.to_qty(fields.get("opening_qty") or 0)
    opening_rate = money.to_paisa(fields.get("opening_rate") or 0)
    opening_value = money.to_paisa(fields.get("opening_value")) if fields.get("opening_value") \
        else money.round_half_up(opening_qty * opening_rate, money.QTY_SCALE)

    now = db.now_stamp()
    cur = conn.execute(
        """INSERT INTO items (code, barcode, name, name_np, group_id, item_type, unit_id,
                              alt_unit_id, alt_conversion, hs_code, vat_applicable, vat_rate_bp,
                              purchase_rate_paisa, sale_rate_paisa, mrp_paisa,
                              opening_qty, opening_value_paisa, reorder_qty, maintain_stock,
                              sales_account_id, purchase_account_id, active, notes,
                              created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)""",
        (code, fields.get("barcode", ""), name, fields.get("name_np", ""),
         fields.get("group_id"), item_type, fields.get("unit_id"), fields.get("alt_unit_id"),
         money.to_qty(fields.get("alt_conversion") or 0), fields.get("hs_code", ""),
         1 if fields.get("vat_applicable", 1) else 0,
         int(fields.get("vat_rate_bp", 1300)),
         money.to_paisa(fields.get("purchase_rate") or 0),
         money.to_paisa(fields.get("sale_rate") or 0),
         money.to_paisa(fields.get("mrp") or 0),
         opening_qty, opening_value, money.to_qty(fields.get("reorder_qty") or 0),
         1 if (fields.get("maintain_stock", 1) and item_type == "goods") else 0,
         fields.get("sales_account_id"), fields.get("purchase_account_id"),
         fields.get("notes", ""), now, now))
    audit.log(conn, username, "item.create", "items", cur.lastrowid, code,
              "Item %s created." % name)
    return cur.lastrowid


def update_item(conn, username, item_id, **fields):
    before = get_item(conn, item_id)
    if before is None:
        raise MasterError("That item no longer exists.")
    editable = ("name", "name_np", "barcode", "group_id", "unit_id", "alt_unit_id", "hs_code",
                "vat_applicable", "vat_rate_bp", "reorder_qty", "maintain_stock",
                "sales_account_id", "purchase_account_id", "active", "notes")
    sets, args = [], []
    for key in editable:
        if key in fields:
            sets.append("%s = ?" % key)
            args.append(fields[key])
    for key, column in (("purchase_rate", "purchase_rate_paisa"),
                        ("sale_rate", "sale_rate_paisa"), ("mrp", "mrp_paisa")):
        if key in fields:
            sets.append("%s = ?" % column)
            args.append(money.to_paisa(fields[key]))
    if "opening_qty" in fields:
        sets.append("opening_qty = ?")
        args.append(money.to_qty(fields["opening_qty"]))
    if "opening_value" in fields:
        sets.append("opening_value_paisa = ?")
        args.append(money.to_paisa(fields["opening_value"]))
    if not sets:
        return
    sets.append("updated_at = ?")
    args.append(db.now_stamp())
    args.append(item_id)
    conn.execute("UPDATE items SET %s WHERE id = ?" % ", ".join(sets), args)
    audit.log(conn, username, "item.update", "items", item_id, before["code"],
              "Item %s updated." % before["name"], dict(before), fields)


def delete_item(conn, username, item_id):
    item = get_item(conn, item_id)
    if item is None:
        raise MasterError("That item no longer exists.")
    used = conn.execute("SELECT COUNT(*) AS n FROM voucher_items WHERE item_id = ?",
                        (item_id,)).fetchone()["n"]
    if used:
        raise MasterError("%s appears on %d vouchers. Switch it off instead of deleting."
                          % (item["name"], used))
    conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
    audit.log(conn, username, "item.delete", "items", item_id, item["code"],
              "Item %s deleted." % item["name"], dict(item), None)


# Small lookup tables


def units(conn, only_active=True):
    sql = "SELECT * FROM units"
    if only_active:
        sql += " WHERE active = 1"
    return conn.execute(sql + " ORDER BY name").fetchall()


def item_groups(conn, only_active=True):
    sql = "SELECT * FROM item_groups"
    if only_active:
        sql += " WHERE active = 1"
    return conn.execute(sql + " ORDER BY name").fetchall()


def warehouses(conn, only_active=True):
    sql = "SELECT * FROM warehouses"
    if only_active:
        sql += " WHERE active = 1"
    return conn.execute(sql + " ORDER BY name").fetchall()


def unit_by_symbol(conn, symbol):
    return conn.execute("SELECT * FROM units WHERE symbol = ?", (symbol,)).fetchone()

"""
Creating a company and opening its books.

Creating a company writes a fresh SQLite file, lays out the schema, and seeds
the chart of accounts, units, voucher types and TDS sections that a Nepali
business needs on day one. From that point the books belong to the user and
everything is editable.
"""

import datetime
import os

from ..core import audit, coa, db, nepali_date as nd, schema

BUSINESS_TYPES = {
    "trading": "Trading, goods bought and sold",
    "service": "Service or professional practice",
    "both": "Both goods and services",
}

ENTITY_TYPES = {
    "proprietorship": "Sole proprietorship",
    "partnership": "Partnership firm",
    "private_limited": "Private limited company",
    "public_limited": "Public limited company",
    "ngo": "Non government organisation",
    "cooperative": "Cooperative",
    "other": "Other",
}


def open_company(slug):
    """Open an existing company book, applying any pending schema upgrade."""
    path = db.company_db_path(slug)
    if not os.path.exists(path):
        raise FileNotFoundError("No book found for %s" % slug)
    conn = db.connect(path)
    db.apply_migrations(conn, schema.COMPANY_MIGRATIONS, "company")
    sync_chart(conn)
    _first_stock_rebuild(conn)
    return conn


def _first_stock_rebuild(conn):
    """
    Books made before stock moved onto the perpetual system carry purchases in
    Purchases and no asset at all. The first time they are opened afterwards the
    entries are rebuilt once so the two systems are not mixed inside one year.
    """
    from . import inventory
    row = conn.execute("SELECT stock_rebuild_pending FROM company WHERE id = 1").fetchone()
    if row is None or not row["stock_rebuild_pending"]:
        return
    try:
        inventory.convert_existing(conn, "system")
        conn.commit()
    except Exception:
        # A book that cannot be rebuilt is still a book that must open. The
        # owner can run it by hand from the stock screen and see the reason.
        conn.rollback()


def sync_chart(conn, username="system"):
    """
    Bring the chart of accounts up to date with the standard one.

    Groups and ledgers added to the standard chart since this company was
    created are added here too. Nothing is renamed, reclassified or removed, so
    anything the owner has set up is left exactly as it is. Only what is
    genuinely missing gets added, and only ledgers that belong to the kind of
    business this company is.
    """
    profile_row = conn.execute("SELECT business_type FROM company WHERE id = 1").fetchone()
    if profile_row is None:
        return {"groups": 0, "accounts": 0}
    business_type = profile_row["business_type"]

    existing_groups = {row["code"]: row["id"]
                       for row in conn.execute("SELECT code, id FROM account_groups")}
    added_groups = 0
    pending = [row for row in coa.GROUPS if row[0] not in existing_groups]
    guard = 0
    while pending and guard < 30:
        guard += 1
        remaining = []
        for code, name, name_np, parent, nature, statement, section, sort in pending:
            if parent and parent not in existing_groups:
                remaining.append((code, name, name_np, parent, nature, statement, section, sort))
                continue
            cur = conn.execute(
                """INSERT INTO account_groups (code, name, name_np, parent_id, nature,
                                               statement, section, sort_order, is_system, active)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1)""",
                (code, name, name_np, existing_groups.get(parent), nature, statement, section, sort))
            existing_groups[code] = cur.lastrowid
            added_groups += 1
        pending = remaining

    existing_accounts = {row["code"] for row in conn.execute("SELECT code FROM accounts")}
    taken_names = {row["name"].lower() for row in conn.execute("SELECT name FROM accounts")}
    now = db.now_stamp()
    added_accounts = 0
    for code, name, name_np, group_code, kind, _applies, opts in coa.ledgers_for(business_type):
        if code in existing_accounts or name.lower() in taken_names:
            continue
        group_id = existing_groups.get(group_code)
        if group_id is None:
            continue
        conn.execute(
            """INSERT INTO accounts (code, name, name_np, group_id, account_kind,
                                     tds_section, tds_rate_bp, vat_rate_bp, reconcilable,
                                     is_system, active, notes, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)""",
            (code, name, name_np, group_id, kind,
             opts.get("tds_section", ""), int(opts.get("tds_rate_bp", 0)),
             int(opts.get("vat_rate_bp", 0)), int(opts.get("reconcilable", 0)),
             int(opts.get("is_system", 0)), opts.get("notes", ""), now, now))
        existing_accounts.add(code)
        taken_names.add(name.lower())
        added_accounts += 1

    if added_groups or added_accounts:
        audit.log(conn, username, "chart.sync", "accounts", None, "",
                  "Chart of accounts brought up to date: %d groups and %d ledgers added."
                  % (added_groups, added_accounts))
    return {"groups": added_groups, "accounts": added_accounts}


def list_companies(system_conn, include_inactive=False):
    sql = "SELECT * FROM companies"
    if not include_inactive:
        sql += " WHERE active = 1"
    sql += " ORDER BY sort_order, name"
    return system_conn.execute(sql).fetchall()


def get_company(system_conn, company_id):
    return system_conn.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()


def create_company(system_conn, name, business_type="trading", username="", **details):
    """
    Register a company and build its book of accounts.

    details may carry any column of the company table, for example pan,
    vat_registered, address, entity_type and books_begin_ad.
    """
    name = str(name).strip()
    if not name:
        raise ValueError("Company name is required.")
    if business_type not in BUSINESS_TYPES:
        raise ValueError("Unknown business type %r" % business_type)

    slug = db.slugify(name)
    taken = system_conn.execute("SELECT id FROM companies WHERE slug = ?", (slug,)).fetchone()
    if taken:
        suffix = 2
        while system_conn.execute("SELECT id FROM companies WHERE slug = ?",
                                  ("%s_%d" % (slug, suffix),)).fetchone():
            suffix += 1
        slug = "%s_%d" % (slug, suffix)

    path = db.company_db_path(slug)
    if os.path.exists(path):
        raise FileExistsError("A book file already exists at %s" % path)

    conn = db.connect(path)
    try:
        db.apply_migrations(conn, schema.COMPANY_MIGRATIONS, "company")
        _seed(conn, name, business_type, username, details)
    except Exception:
        conn.close()
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(path + suffix):
                os.remove(path + suffix)
        raise

    order = system_conn.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 AS n FROM companies"
                                ).fetchone()["n"]
    cur = system_conn.execute(
        """INSERT INTO companies (slug, name, name_np, business_type, active, sort_order, created_at)
           VALUES (?, ?, ?, ?, 1, ?, ?)""",
        (slug, name, details.get("name_np", ""), business_type, order, db.now_stamp()))
    return {"id": cur.lastrowid, "slug": slug, "conn": conn}


def _seed(conn, name, business_type, username, details):
    now = db.now_stamp()
    today = datetime.date.today()

    begin = details.get("books_begin_ad")
    if not begin:
        begin = nd.fiscal_year_of(today)["start_ad"]

    columns = {
        "name": name,
        "name_np": details.get("name_np", ""),
        "business_type": business_type,
        # These two drive which screens appear. They are kept as separate flags
        # rather than read from business_type every time, so a company can later
        # start selling goods without its whole type having to change.
        "has_goods": 1 if business_type in ("trading", "both") else 0,
        "has_services": 1 if business_type in ("service", "both") else 0,
        "entity_type": details.get("entity_type", "proprietorship"),
        "address": details.get("address", ""),
        "address_np": details.get("address_np", ""),
        "ward_no": details.get("ward_no", ""),
        "city": details.get("city", ""),
        "district": details.get("district", ""),
        "province": details.get("province", ""),
        "country": details.get("country", "Nepal"),
        "phone": details.get("phone", ""),
        "mobile": details.get("mobile", ""),
        "email": details.get("email", ""),
        "website": details.get("website", ""),
        "pan": details.get("pan", ""),
        "vat_registered": 1 if details.get("vat_registered") else 0,
        "vat_rate_bp": int(details.get("vat_rate_bp", 1300)),
        "ird_office": details.get("ird_office", ""),
        "registration_no": details.get("registration_no", ""),
        "registration_date": details.get("registration_date", ""),
        "books_begin_ad": begin,
        "language": details.get("language", "en"),
        "date_display": details.get("date_display", "both"),
        "number_grouping": details.get("number_grouping", "nepali"),
        "stock_valuation": details.get("stock_valuation", "weighted_average"),
        "created_at": now,
        "updated_at": now,
    }
    cols = ", ".join(["id"] + list(columns))
    marks = ", ".join(["1"] + ["?"] * len(columns))
    conn.execute("INSERT INTO company (%s) VALUES (%s)" % (cols, marks), list(columns.values()))

    # Fiscal year covering the date the books begin.
    fy = nd.fiscal_year_of(begin)
    conn.execute("""INSERT INTO fiscal_years (label, start_bs_year, start_ad, end_ad, status)
                    VALUES (?, ?, ?, ?, 'open')""",
                 (fy["label"], fy["start_bs"][0], fy["start_ad"], fy["end_ad"]))
    fy_id = conn.execute("SELECT id FROM fiscal_years WHERE label = ?", (fy["label"],)).fetchone()["id"]
    conn.execute("UPDATE company SET current_fy_id = ? WHERE id = 1", (fy_id,))

    # Account groups, parents before children.
    group_ids = {}
    pending = list(coa.GROUPS)
    guard = 0
    while pending:
        guard += 1
        if guard > 50:
            raise RuntimeError("Account group tree could not be resolved.")
        remaining = []
        for code, gname, gnp, parent, nature, statement, section, sort in pending:
            if parent and parent not in group_ids:
                remaining.append((code, gname, gnp, parent, nature, statement, section, sort))
                continue
            cur = conn.execute(
                """INSERT INTO account_groups (code, name, name_np, parent_id, nature,
                                               statement, section, sort_order, is_system, active)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1)""",
                (code, gname, gnp, group_ids.get(parent), nature, statement, section, sort))
            group_ids[code] = cur.lastrowid
        pending = remaining

    # Ledger accounts.
    for code, aname, anp, group_code, kind, _applies, opts in coa.ledgers_for(business_type):
        conn.execute(
            """INSERT INTO accounts (code, name, name_np, group_id, account_kind,
                                     tds_section, tds_rate_bp, vat_rate_bp, reconcilable,
                                     is_system, active, notes, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)""",
            (code, aname, anp, group_ids[group_code], kind,
             opts.get("tds_section", ""), int(opts.get("tds_rate_bp", 0)),
             int(opts.get("vat_rate_bp", 0)), int(opts.get("reconcilable", 0)),
             int(opts.get("is_system", 0)), opts.get("notes", ""), now, now))

    for uname, symbol, decimals in coa.UNITS:
        conn.execute("INSERT INTO units (name, symbol, decimals, active) VALUES (?, ?, ?, 1)",
                     (uname, symbol, decimals))

    for code, vname, vnp, prefix, stock, vat, side, sort in coa.VOUCHER_TYPES:
        conn.execute(
            """INSERT INTO voucher_types (code, name, name_np, prefix, affects_stock,
                                          affects_vat, vat_side, sort_order, is_system, active)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1)""",
            (code, vname, vnp, prefix, stock, vat, side, sort))
        conn.execute(
            """INSERT INTO number_series (voucher_type, fiscal_year_id, prefix, next_number, width)
               VALUES (?, ?, ?, 1, 4)""", (code, fy_id, prefix))

    for code, description, rate_bp, ref in coa.TDS_SECTIONS:
        conn.execute("""INSERT INTO tds_sections (code, description, rate_bp, legal_ref, active)
                        VALUES (?, ?, ?, ?, 1)""", (code, description, rate_bp, ref))

    groups = []
    if business_type in ("trading", "both"):
        groups += coa.ITEM_GROUPS_TRADING
    if business_type in ("service", "both"):
        groups += coa.ITEM_GROUPS_SERVICE
    for code, gname, gnp in groups:
        conn.execute("INSERT INTO item_groups (code, name, name_np, active) VALUES (?, ?, ?, 1)",
                     (code, gname, gnp))

    conn.execute("""INSERT INTO warehouses (code, name, address, is_default, active)
                    VALUES ('MAIN', 'Main Store', '', 1, 1)""")

    for key, value in (
        ("invoice_footer", "Goods once sold will not be taken back."),
        ("invoice_terms", ""),
        ("show_amount_in_words", "1"),
        ("auto_round_invoice", "1"),
        ("allow_negative_stock", "0"),
        ("default_stock_valuation", details.get("stock_valuation", "weighted_average")),
    ):
        conn.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (key, value))

    audit.log(conn, username, "company.create", "company", 1, name,
              "Book of accounts created for %s as a %s business." % (name, business_type))


def profile(conn):
    return conn.execute("SELECT * FROM company WHERE id = 1").fetchone()


def update_profile(conn, username, **fields):
    allowed = {row[1] for row in conn.execute("PRAGMA table_info(company)")}
    allowed -= {"id", "created_at"}
    # Changing what the business does has to move the two flags with it.
    if "business_type" in fields and fields["business_type"] in BUSINESS_TYPES:
        kind = fields["business_type"]
        fields["has_goods"] = 1 if kind in ("trading", "both") else 0
        fields["has_services"] = 1 if kind in ("service", "both") else 0
    sets, args = [], []
    before = profile(conn)
    for key, value in fields.items():
        if key in allowed:
            sets.append("%s = ?" % key)
            args.append(value)
    if not sets:
        return
    sets.append("updated_at = ?")
    args.append(db.now_stamp())
    conn.execute("UPDATE company SET %s WHERE id = 1" % ", ".join(sets), args)
    audit.log(conn, username, "company.update", "company", 1, "",
              "Company details updated.", dict(before), fields)


def fiscal_years(conn):
    return conn.execute("SELECT * FROM fiscal_years ORDER BY start_ad").fetchall()


def current_fiscal_year(conn):
    row = conn.execute("""SELECT f.* FROM fiscal_years f
                          JOIN company c ON c.current_fy_id = f.id""").fetchone()
    if row:
        return row
    return conn.execute("SELECT * FROM fiscal_years ORDER BY start_ad DESC LIMIT 1").fetchone()


def ensure_fiscal_year(conn, start_bs_year, username=""):
    """Create a fiscal year if it does not exist yet, and set up its numbering."""
    fy = nd.fiscal_year(start_bs_year)
    row = conn.execute("SELECT * FROM fiscal_years WHERE label = ?", (fy["label"],)).fetchone()
    if row:
        return row
    conn.execute("""INSERT INTO fiscal_years (label, start_bs_year, start_ad, end_ad, status)
                    VALUES (?, ?, ?, ?, 'open')""",
                 (fy["label"], start_bs_year, fy["start_ad"], fy["end_ad"]))
    row = conn.execute("SELECT * FROM fiscal_years WHERE label = ?", (fy["label"],)).fetchone()
    for vt in conn.execute("SELECT code, prefix FROM voucher_types").fetchall():
        conn.execute("""INSERT OR IGNORE INTO number_series
                        (voucher_type, fiscal_year_id, prefix, next_number, width)
                        VALUES (?, ?, ?, 1, 4)""", (vt["code"], row["id"], vt["prefix"]))
    # Opening a year earlier than the books begin is how somebody brings last
    # year in, and it has to move the date the books begin as well. Otherwise
    # every voucher dated in that year would be refused for being before the
    # start, and the year would sit there unusable.
    begins = conn.execute("SELECT books_begin_ad FROM company WHERE id = 1").fetchone()
    if begins and begins["books_begin_ad"] and fy["start_ad"] < begins["books_begin_ad"]:
        conn.execute("UPDATE company SET books_begin_ad = ? WHERE id = 1", (fy["start_ad"],))
        audit.log(conn, username, "company.books_begin", "company", 1, fy["start_ad"],
                  "The books now begin on %s, moved back so fiscal year %s can be used."
                  % (fy["start_ad"], fy["label"]))
    audit.log(conn, username, "fiscal_year.create", "fiscal_years", row["id"], fy["label"],
              "Fiscal year %s opened." % fy["label"])
    return row

"""
Schema of a company's book of accounts.

Conventions used throughout:

  Amounts     integer paisa. 1 rupee = 100 paisa.
  Quantities  integer thousandths, so 2.5 kg is stored as 2500.
  Rates       basis points, so 13 percent is 1300.
  Dates       AD stored as ISO text (YYYY-MM-DD) because it sorts correctly.
              The BS date is stored alongside for searching and printing.
  Debit and credit are held in two non negative columns rather than one signed
  column, so a printed entry always reads the way an accountant expects.

Each migration is applied once and recorded. Never edit a migration that has
already run on a live book. Add a new one instead.
"""

COMPANY_MIGRATIONS = [
    (1, "core books", """

    CREATE TABLE company (
        id                  INTEGER PRIMARY KEY CHECK (id = 1),
        name                TEXT NOT NULL,
        name_np             TEXT NOT NULL DEFAULT '',
        business_type       TEXT NOT NULL DEFAULT 'trading',
        entity_type         TEXT NOT NULL DEFAULT 'proprietorship',
        address             TEXT NOT NULL DEFAULT '',
        address_np          TEXT NOT NULL DEFAULT '',
        ward_no             TEXT NOT NULL DEFAULT '',
        city                TEXT NOT NULL DEFAULT '',
        district            TEXT NOT NULL DEFAULT '',
        province            TEXT NOT NULL DEFAULT '',
        country             TEXT NOT NULL DEFAULT 'Nepal',
        phone               TEXT NOT NULL DEFAULT '',
        mobile              TEXT NOT NULL DEFAULT '',
        email               TEXT NOT NULL DEFAULT '',
        website             TEXT NOT NULL DEFAULT '',
        pan                 TEXT NOT NULL DEFAULT '',
        vat_registered      INTEGER NOT NULL DEFAULT 0,
        vat_rate_bp         INTEGER NOT NULL DEFAULT 1300,
        ird_office          TEXT NOT NULL DEFAULT '',
        registration_no     TEXT NOT NULL DEFAULT '',
        registration_date   TEXT NOT NULL DEFAULT '',
        logo_path           TEXT NOT NULL DEFAULT '',
        books_begin_ad      TEXT NOT NULL,
        current_fy_id       INTEGER,
        language            TEXT NOT NULL DEFAULT 'en',
        date_display        TEXT NOT NULL DEFAULT 'both',
        number_grouping     TEXT NOT NULL DEFAULT 'nepali',
        stock_valuation     TEXT NOT NULL DEFAULT 'weighted_average',
        created_at          TEXT NOT NULL,
        updated_at          TEXT NOT NULL
    );

    CREATE TABLE fiscal_years (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        label           TEXT NOT NULL UNIQUE,
        start_bs_year   INTEGER NOT NULL,
        start_ad        TEXT NOT NULL,
        end_ad          TEXT NOT NULL,
        status          TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','closed')),
        closed_at       TEXT,
        closed_by       TEXT
    );

    CREATE TABLE account_groups (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        code            TEXT NOT NULL UNIQUE,
        name            TEXT NOT NULL,
        name_np         TEXT NOT NULL DEFAULT '',
        parent_id       INTEGER REFERENCES account_groups(id),
        nature          TEXT NOT NULL CHECK (nature IN ('asset','liability','equity','income','expense')),
        statement       TEXT NOT NULL CHECK (statement IN ('BS','PL')),
        section         TEXT NOT NULL DEFAULT '',
        sort_order      INTEGER NOT NULL DEFAULT 0,
        is_system       INTEGER NOT NULL DEFAULT 0,
        active          INTEGER NOT NULL DEFAULT 1,
        notes           TEXT NOT NULL DEFAULT ''
    );

    CREATE TABLE accounts (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        code            TEXT NOT NULL UNIQUE,
        name            TEXT NOT NULL,
        name_np         TEXT NOT NULL DEFAULT '',
        group_id        INTEGER NOT NULL REFERENCES account_groups(id),
        account_kind    TEXT NOT NULL DEFAULT 'general',
        opening_paisa   INTEGER NOT NULL DEFAULT 0,
        party_id        INTEGER,
        bank_name       TEXT NOT NULL DEFAULT '',
        bank_account_no TEXT NOT NULL DEFAULT '',
        bank_branch     TEXT NOT NULL DEFAULT '',
        tds_section     TEXT NOT NULL DEFAULT '',
        tds_rate_bp     INTEGER NOT NULL DEFAULT 0,
        vat_rate_bp     INTEGER NOT NULL DEFAULT 0,
        reconcilable    INTEGER NOT NULL DEFAULT 0,
        is_system       INTEGER NOT NULL DEFAULT 0,
        active          INTEGER NOT NULL DEFAULT 1,
        notes           TEXT NOT NULL DEFAULT '',
        created_at      TEXT NOT NULL,
        updated_at      TEXT NOT NULL
    );
    CREATE INDEX idx_accounts_group ON accounts(group_id);
    CREATE INDEX idx_accounts_name ON accounts(name);
    CREATE INDEX idx_accounts_kind ON accounts(account_kind);

    CREATE TABLE parties (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        code                TEXT NOT NULL UNIQUE,
        name                TEXT NOT NULL,
        name_np             TEXT NOT NULL DEFAULT '',
        party_type          TEXT NOT NULL DEFAULT 'customer'
                            CHECK (party_type IN ('customer','supplier','both','employee','other')),
        account_id          INTEGER REFERENCES accounts(id),
        pan                 TEXT NOT NULL DEFAULT '',
        vat_registered      INTEGER NOT NULL DEFAULT 0,
        contact_person      TEXT NOT NULL DEFAULT '',
        address             TEXT NOT NULL DEFAULT '',
        city                TEXT NOT NULL DEFAULT '',
        district            TEXT NOT NULL DEFAULT '',
        phone               TEXT NOT NULL DEFAULT '',
        mobile              TEXT NOT NULL DEFAULT '',
        email               TEXT NOT NULL DEFAULT '',
        credit_limit_paisa  INTEGER NOT NULL DEFAULT 0,
        credit_days         INTEGER NOT NULL DEFAULT 0,
        tds_applicable      INTEGER NOT NULL DEFAULT 0,
        tds_section         TEXT NOT NULL DEFAULT '',
        active              INTEGER NOT NULL DEFAULT 1,
        notes               TEXT NOT NULL DEFAULT '',
        created_at          TEXT NOT NULL,
        updated_at          TEXT NOT NULL
    );
    CREATE INDEX idx_parties_name ON parties(name);
    CREATE INDEX idx_parties_pan ON parties(pan);

    CREATE TABLE units (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT NOT NULL UNIQUE,
        symbol      TEXT NOT NULL,
        decimals    INTEGER NOT NULL DEFAULT 0,
        active      INTEGER NOT NULL DEFAULT 1
    );

    CREATE TABLE item_groups (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        code        TEXT NOT NULL UNIQUE,
        name        TEXT NOT NULL,
        name_np     TEXT NOT NULL DEFAULT '',
        parent_id   INTEGER REFERENCES item_groups(id),
        active      INTEGER NOT NULL DEFAULT 1
    );

    CREATE TABLE warehouses (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        code        TEXT NOT NULL UNIQUE,
        name        TEXT NOT NULL,
        address     TEXT NOT NULL DEFAULT '',
        is_default  INTEGER NOT NULL DEFAULT 0,
        active      INTEGER NOT NULL DEFAULT 1
    );

    CREATE TABLE items (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        code                TEXT NOT NULL UNIQUE,
        barcode             TEXT NOT NULL DEFAULT '',
        name                TEXT NOT NULL,
        name_np             TEXT NOT NULL DEFAULT '',
        group_id            INTEGER REFERENCES item_groups(id),
        item_type           TEXT NOT NULL DEFAULT 'goods' CHECK (item_type IN ('goods','service')),
        unit_id             INTEGER REFERENCES units(id),
        alt_unit_id         INTEGER REFERENCES units(id),
        alt_conversion      INTEGER NOT NULL DEFAULT 0,
        hs_code             TEXT NOT NULL DEFAULT '',
        vat_applicable      INTEGER NOT NULL DEFAULT 1,
        vat_rate_bp         INTEGER NOT NULL DEFAULT 1300,
        purchase_rate_paisa INTEGER NOT NULL DEFAULT 0,
        sale_rate_paisa     INTEGER NOT NULL DEFAULT 0,
        mrp_paisa           INTEGER NOT NULL DEFAULT 0,
        opening_qty         INTEGER NOT NULL DEFAULT 0,
        opening_value_paisa INTEGER NOT NULL DEFAULT 0,
        reorder_qty         INTEGER NOT NULL DEFAULT 0,
        maintain_stock      INTEGER NOT NULL DEFAULT 1,
        sales_account_id    INTEGER REFERENCES accounts(id),
        purchase_account_id INTEGER REFERENCES accounts(id),
        active              INTEGER NOT NULL DEFAULT 1,
        notes               TEXT NOT NULL DEFAULT '',
        created_at          TEXT NOT NULL,
        updated_at          TEXT NOT NULL
    );
    CREATE INDEX idx_items_name ON items(name);
    CREATE INDEX idx_items_group ON items(group_id);
    CREATE INDEX idx_items_barcode ON items(barcode);

    CREATE TABLE cost_centers (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        code        TEXT NOT NULL UNIQUE,
        name        TEXT NOT NULL,
        parent_id   INTEGER REFERENCES cost_centers(id),
        active      INTEGER NOT NULL DEFAULT 1
    );

    CREATE TABLE voucher_types (
        code            TEXT PRIMARY KEY,
        name            TEXT NOT NULL,
        name_np         TEXT NOT NULL DEFAULT '',
        prefix          TEXT NOT NULL DEFAULT '',
        affects_stock   INTEGER NOT NULL DEFAULT 0,
        affects_vat     INTEGER NOT NULL DEFAULT 0,
        vat_side        TEXT NOT NULL DEFAULT '',
        sort_order      INTEGER NOT NULL DEFAULT 0,
        is_system       INTEGER NOT NULL DEFAULT 1,
        active          INTEGER NOT NULL DEFAULT 1
    );

    CREATE TABLE number_series (
        voucher_type    TEXT NOT NULL REFERENCES voucher_types(code),
        fiscal_year_id  INTEGER NOT NULL REFERENCES fiscal_years(id),
        prefix          TEXT NOT NULL DEFAULT '',
        next_number     INTEGER NOT NULL DEFAULT 1,
        width           INTEGER NOT NULL DEFAULT 4,
        PRIMARY KEY (voucher_type, fiscal_year_id)
    );

    CREATE TABLE vouchers (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        fiscal_year_id      INTEGER NOT NULL REFERENCES fiscal_years(id),
        voucher_type        TEXT NOT NULL REFERENCES voucher_types(code),
        number              TEXT NOT NULL,
        date_ad             TEXT NOT NULL,
        date_bs             TEXT NOT NULL,
        party_id            INTEGER REFERENCES parties(id),
        party_account_id    INTEGER REFERENCES accounts(id),
        reference_no        TEXT NOT NULL DEFAULT '',
        reference_date_ad   TEXT NOT NULL DEFAULT '',
        due_date_ad         TEXT NOT NULL DEFAULT '',
        payment_mode        TEXT NOT NULL DEFAULT '',
        narration           TEXT NOT NULL DEFAULT '',
        subtotal_paisa      INTEGER NOT NULL DEFAULT 0,
        discount_paisa      INTEGER NOT NULL DEFAULT 0,
        taxable_paisa       INTEGER NOT NULL DEFAULT 0,
        exempt_paisa        INTEGER NOT NULL DEFAULT 0,
        vat_paisa           INTEGER NOT NULL DEFAULT 0,
        other_charges_paisa INTEGER NOT NULL DEFAULT 0,
        tds_paisa           INTEGER NOT NULL DEFAULT 0,
        round_off_paisa     INTEGER NOT NULL DEFAULT 0,
        total_paisa         INTEGER NOT NULL DEFAULT 0,
        is_vat_invoice      INTEGER NOT NULL DEFAULT 0,
        status              TEXT NOT NULL DEFAULT 'posted'
                            CHECK (status IN ('draft','posted','cancelled')),
        printed_count       INTEGER NOT NULL DEFAULT 0,
        created_by          TEXT NOT NULL DEFAULT '',
        created_at          TEXT NOT NULL,
        updated_by          TEXT NOT NULL DEFAULT '',
        updated_at          TEXT NOT NULL,
        cancelled_by        TEXT NOT NULL DEFAULT '',
        cancelled_at        TEXT NOT NULL DEFAULT '',
        cancel_reason       TEXT NOT NULL DEFAULT '',
        UNIQUE (voucher_type, fiscal_year_id, number)
    );
    CREATE INDEX idx_vouchers_date ON vouchers(date_ad);
    CREATE INDEX idx_vouchers_type_date ON vouchers(voucher_type, date_ad);
    CREATE INDEX idx_vouchers_party ON vouchers(party_id);
    CREATE INDEX idx_vouchers_status ON vouchers(status);

    CREATE TABLE voucher_entries (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        voucher_id          INTEGER NOT NULL REFERENCES vouchers(id) ON DELETE CASCADE,
        line_no             INTEGER NOT NULL,
        account_id          INTEGER NOT NULL REFERENCES accounts(id),
        dr_paisa            INTEGER NOT NULL DEFAULT 0 CHECK (dr_paisa >= 0),
        cr_paisa            INTEGER NOT NULL DEFAULT 0 CHECK (cr_paisa >= 0),
        narration           TEXT NOT NULL DEFAULT '',
        cost_center_id      INTEGER REFERENCES cost_centers(id),
        CHECK (dr_paisa = 0 OR cr_paisa = 0)
    );
    CREATE INDEX idx_entries_voucher ON voucher_entries(voucher_id);
    CREATE INDEX idx_entries_account ON voucher_entries(account_id);

    CREATE TABLE voucher_items (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        voucher_id          INTEGER NOT NULL REFERENCES vouchers(id) ON DELETE CASCADE,
        line_no             INTEGER NOT NULL,
        item_id             INTEGER NOT NULL REFERENCES items(id),
        description         TEXT NOT NULL DEFAULT '',
        warehouse_id        INTEGER REFERENCES warehouses(id),
        qty                 INTEGER NOT NULL DEFAULT 0,
        free_qty            INTEGER NOT NULL DEFAULT 0,
        unit_id             INTEGER REFERENCES units(id),
        rate_paisa          INTEGER NOT NULL DEFAULT 0,
        gross_paisa         INTEGER NOT NULL DEFAULT 0,
        discount_bp         INTEGER NOT NULL DEFAULT 0,
        discount_paisa      INTEGER NOT NULL DEFAULT 0,
        taxable_paisa       INTEGER NOT NULL DEFAULT 0,
        vat_bp              INTEGER NOT NULL DEFAULT 0,
        vat_paisa           INTEGER NOT NULL DEFAULT 0,
        amount_paisa        INTEGER NOT NULL DEFAULT 0,
        cost_paisa          INTEGER NOT NULL DEFAULT 0,
        batch               TEXT NOT NULL DEFAULT '',
        expiry_ad           TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX idx_vitems_voucher ON voucher_items(voucher_id);
    CREATE INDEX idx_vitems_item ON voucher_items(item_id);

    CREATE TABLE stock_ledger (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        voucher_id          INTEGER NOT NULL REFERENCES vouchers(id) ON DELETE CASCADE,
        voucher_item_id     INTEGER REFERENCES voucher_items(id) ON DELETE CASCADE,
        item_id             INTEGER NOT NULL REFERENCES items(id),
        warehouse_id        INTEGER REFERENCES warehouses(id),
        date_ad             TEXT NOT NULL,
        direction           INTEGER NOT NULL CHECK (direction IN (-1, 1)),
        qty                 INTEGER NOT NULL DEFAULT 0,
        rate_paisa          INTEGER NOT NULL DEFAULT 0,
        value_paisa         INTEGER NOT NULL DEFAULT 0,
        note                TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX idx_stock_item_date ON stock_ledger(item_id, date_ad);
    CREATE INDEX idx_stock_voucher ON stock_ledger(voucher_id);

    CREATE TABLE bill_allocations (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        voucher_id          INTEGER NOT NULL REFERENCES vouchers(id) ON DELETE CASCADE,
        account_id          INTEGER NOT NULL REFERENCES accounts(id),
        against_voucher_id  INTEGER REFERENCES vouchers(id),
        bill_reference      TEXT NOT NULL DEFAULT '',
        allocation_type     TEXT NOT NULL DEFAULT 'against'
                            CHECK (allocation_type IN ('new','against','advance','on_account')),
        amount_paisa        INTEGER NOT NULL DEFAULT 0
    );
    CREATE INDEX idx_alloc_account ON bill_allocations(account_id);
    CREATE INDEX idx_alloc_against ON bill_allocations(against_voucher_id);

    CREATE TABLE tds_sections (
        code        TEXT PRIMARY KEY,
        description TEXT NOT NULL,
        rate_bp     INTEGER NOT NULL,
        legal_ref   TEXT NOT NULL DEFAULT '',
        active      INTEGER NOT NULL DEFAULT 1
    );

    CREATE TABLE audit_log (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        at          TEXT NOT NULL,
        username    TEXT NOT NULL DEFAULT '',
        action      TEXT NOT NULL,
        table_name  TEXT NOT NULL DEFAULT '',
        record_id   INTEGER,
        reference   TEXT NOT NULL DEFAULT '',
        summary     TEXT NOT NULL DEFAULT '',
        before_json TEXT NOT NULL DEFAULT '',
        after_json  TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX idx_audit_at ON audit_log(at);
    CREATE INDEX idx_audit_record ON audit_log(table_name, record_id);

    CREATE TABLE settings (
        key     TEXT PRIMARY KEY,
        value   TEXT NOT NULL
    );

    CREATE TABLE attachments (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        voucher_id  INTEGER REFERENCES vouchers(id) ON DELETE CASCADE,
        filename    TEXT NOT NULL,
        stored_path TEXT NOT NULL,
        note        TEXT NOT NULL DEFAULT '',
        added_at    TEXT NOT NULL
    );
    """),
]

COMPANY_MIGRATIONS.append((2, "banking and reconciliation", """

    ALTER TABLE voucher_entries ADD COLUMN cleared_ad TEXT NOT NULL DEFAULT '';
    ALTER TABLE voucher_entries ADD COLUMN reconciliation_id INTEGER;
    ALTER TABLE voucher_entries ADD COLUMN instrument_no TEXT NOT NULL DEFAULT '';
    ALTER TABLE voucher_entries ADD COLUMN instrument_date_ad TEXT NOT NULL DEFAULT '';

    CREATE INDEX idx_entries_cleared ON voucher_entries(cleared_ad);

    CREATE TABLE reconciliations (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id          INTEGER NOT NULL REFERENCES accounts(id),
        statement_date_ad   TEXT NOT NULL,
        statement_date_bs   TEXT NOT NULL DEFAULT '',
        statement_balance   INTEGER NOT NULL DEFAULT 0,
        book_balance        INTEGER NOT NULL DEFAULT 0,
        difference          INTEGER NOT NULL DEFAULT 0,
        status              TEXT NOT NULL DEFAULT 'open'
                            CHECK (status IN ('open','completed')),
        note                TEXT NOT NULL DEFAULT '',
        created_by          TEXT NOT NULL DEFAULT '',
        created_at          TEXT NOT NULL,
        completed_at        TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX idx_recon_account ON reconciliations(account_id, statement_date_ad);

    ALTER TABLE company ADD COLUMN has_goods INTEGER NOT NULL DEFAULT 1;
    ALTER TABLE company ADD COLUMN has_services INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE company ADD COLUMN theme TEXT NOT NULL DEFAULT 'light';
"""))

COMPANY_MIGRATIONS.append((3, "set the goods and service flags from the business type", """
    UPDATE company SET has_goods = 1, has_services = 0 WHERE business_type = 'trading';
    UPDATE company SET has_goods = 0, has_services = 1 WHERE business_type = 'service';
    UPDATE company SET has_goods = 1, has_services = 1 WHERE business_type = 'both';
"""))

COMPANY_MIGRATIONS.append((4, "present fixed assets at carrying amount", """
    -- Accumulated depreciation was a group of its own, which put cost and
    -- depreciation on the face of the balance sheet as two separate lines.
    -- NAS 01 wants the carrying amount on the face, with the split in the note
    -- behind it, so the depreciation ledgers move inside the asset group.
    UPDATE accounts
       SET group_id = (SELECT id FROM account_groups WHERE code = '1110')
     WHERE group_id IN (SELECT id FROM account_groups WHERE code = '1120');

    DELETE FROM account_groups WHERE code = '1120';
"""))

COMPANY_MIGRATIONS.append((5, "fixed asset register", """

    -- One row for each asset the business owns, which is what makes a proper
    -- fixed asset register, a movement schedule, the depreciation working under
    -- Schedule 2 of the Income Tax Act, 2058, and the deferred tax note
    -- possible. The ledgers still carry the money. This carries the detail
    -- behind it.
    CREATE TABLE fixed_assets (
        id                      INTEGER PRIMARY KEY AUTOINCREMENT,
        code                    TEXT NOT NULL UNIQUE,
        name                    TEXT NOT NULL,
        description             TEXT NOT NULL DEFAULT '',
        asset_account_id        INTEGER NOT NULL REFERENCES accounts(id),
        depreciation_account_id INTEGER REFERENCES accounts(id),
        expense_account_id      INTEGER REFERENCES accounts(id),

        -- Schedule 2 of the Income Tax Act, 2058. A, B, C, D or E.
        tax_class               TEXT NOT NULL DEFAULT 'D',

        acquired_ad             TEXT NOT NULL,
        acquired_bs             TEXT NOT NULL DEFAULT '',
        cost_paisa              INTEGER NOT NULL DEFAULT 0,

        -- How the books depreciate it, which need not match the tax treatment.
        book_method             TEXT NOT NULL DEFAULT 'wdv'
                                CHECK (book_method IN ('wdv', 'slm', 'none')),
        book_rate_bp            INTEGER NOT NULL DEFAULT 0,
        useful_life_years       INTEGER NOT NULL DEFAULT 0,
        residual_paisa          INTEGER NOT NULL DEFAULT 0,

        -- Where the asset already existed when the books began.
        opening_cost_paisa      INTEGER NOT NULL DEFAULT 0,
        opening_accumulated_paisa INTEGER NOT NULL DEFAULT 0,
        opening_tax_wdv_paisa   INTEGER NOT NULL DEFAULT 0,

        location                TEXT NOT NULL DEFAULT '',
        serial_no               TEXT NOT NULL DEFAULT '',
        supplier                TEXT NOT NULL DEFAULT '',
        invoice_no              TEXT NOT NULL DEFAULT '',

        disposed_ad             TEXT NOT NULL DEFAULT '',
        disposal_proceeds_paisa INTEGER NOT NULL DEFAULT 0,
        disposal_note           TEXT NOT NULL DEFAULT '',

        active                  INTEGER NOT NULL DEFAULT 1,
        notes                   TEXT NOT NULL DEFAULT '',
        created_at              TEXT NOT NULL,
        updated_at              TEXT NOT NULL
    );
    CREATE INDEX idx_assets_account ON fixed_assets(asset_account_id);
    CREATE INDEX idx_assets_class ON fixed_assets(tax_class);
    CREATE INDEX idx_assets_acquired ON fixed_assets(acquired_ad);

    -- The opening written down value of each tax pool when the books began,
    -- so the depreciation working does not have to reach back before that.
    CREATE TABLE tax_pool_opening (
        tax_class       TEXT PRIMARY KEY,
        opening_wdv     INTEGER NOT NULL DEFAULT 0,
        as_at_ad        TEXT NOT NULL DEFAULT '',
        note            TEXT NOT NULL DEFAULT ''
    );
"""))

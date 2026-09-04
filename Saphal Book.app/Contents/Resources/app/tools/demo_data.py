#!/usr/bin/env python3
"""
Build a demonstration company, or remove it again.

The demonstration company is a hardware shop with real looking Nepali trade:
suppliers, customers, cement and rod, invoices, payments and a closing stock
entry. It is useful for trying a screen out before touching real books, and for
showing someone how the software works.

    python3 tools/demo_data.py            build it
    python3 tools/demo_data.py --remove   delete it again

It never touches any other company.
"""

import argparse
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chartered_book.core import db, money, nepali_date as nd  # noqa: E402
from chartered_book.modules import (company as company_module, invoices, ledger,  # noqa: E402
                                    masters, period_end)

DEMO_NAME = "Demonstration Hardware Store"
DEMO_SLUG = "demonstration_hardware_store"
USER = "demo"


def remove():
    system = db.open_system()
    row = system.execute("SELECT id FROM companies WHERE slug = ?", (DEMO_SLUG,)).fetchone()
    if row:
        system.execute("DELETE FROM user_company_access WHERE company_id = ?", (row["id"],))
        system.execute("UPDATE sessions SET company_id = NULL WHERE company_id = ?", (row["id"],))
        system.execute("DELETE FROM companies WHERE id = ?", (row["id"],))
    removed = 0
    for path in glob.glob(os.path.join(db.BOOKS_DIR, DEMO_SLUG + ".db*")):
        os.remove(path)
        removed += 1
    print("Demonstration company removed. %d file%s deleted."
          % (removed, "" if removed == 1 else "s"))
    return 0


def build():
    system = db.open_system()
    if system.execute("SELECT 1 FROM companies WHERE slug = ?", (DEMO_SLUG,)).fetchone():
        print("The demonstration company already exists. Remove it first with --remove.")
        return 1

    fy = nd.fiscal_year(nd.today_bs()[0] if nd.today_bs()[1] >= 4 else nd.today_bs()[0] - 1)
    result = company_module.create_company(
        system, DEMO_NAME, "trading", USER,
        pan="301234567", vat_registered=1, entity_type="proprietorship",
        address="Butwal Road, Ward 8", city="Butwal", district="Rupandehi",
        province="Lumbini", phone="071-540123", mobile="9857012345",
        email="demo@example.com", ird_office="Butwal",
        books_begin_ad=fy["start_ad"])
    conn = result["conn"]
    start = fy["start_ad"]

    # Opening capital and cash.
    cash = masters.account_by_code(conn, "1251")
    bank = masters.account_by_code(conn, "1261")
    capital = masters.account_by_code(conn, "3101")
    masters.update_account(conn, USER, cash["id"], opening="120000", opening_side="dr")
    masters.update_account(conn, USER, bank["id"], opening="480000", opening_side="dr",
                           name="Nabil Bank, Butwal, current account",
                           bank_name="Nabil Bank", bank_account_no="0801017500123",
                           bank_branch="Butwal")
    masters.update_account(conn, USER, capital["id"], opening="600000", opening_side="cr")

    suppliers = [
        ("Himal Cement Suppliers", "609876543", "Bhairahawa", 30),
        ("Everest Steel Udyog", "607654321", "Birgunj", 45),
        ("Lumbini Paints and Hardware", "605551234", "Butwal", 15),
    ]
    customers = [
        ("Ram Construction Sewa", "302345678", "Butwal", 15),
        ("Sharma Nirman Company", "303456789", "Tilottama", 30),
        ("Gautam Buddha Builders", "304567890", "Siddharthanagar", 21),
        ("Counter customers", "", "Butwal", 0),
    ]
    supplier_ids, customer_ids = [], []
    for name, pan, city, days in suppliers:
        supplier_ids.append(masters.create_party(
            conn, USER, name, "supplier", pan=pan, city=city, district="Rupandehi",
            vat_registered=bool(pan), credit_days=days, mobile="98570%05d" % (len(supplier_ids) + 10000)))
    for name, pan, city, days in customers:
        customer_ids.append(masters.create_party(
            conn, USER, name, "customer", pan=pan, city=city, district="Rupandehi",
            vat_registered=bool(pan), credit_days=days, credit_limit="500000",
            mobile="98410%05d" % (len(customer_ids) + 20000)))

    groups = {row["code"]: row["id"] for row in conn.execute("SELECT code, id FROM item_groups")}
    units = {row["symbol"]: row["id"] for row in conn.execute("SELECT symbol, id FROM units")}

    catalogue = [
        ("OPC Cement 50 kg", "HW01", "bag", "805", "915", "40"),
        ("PPC Cement 50 kg", "HW01", "bag", "760", "870", "40"),
        ("TMT Rod 12 mm", "HW02", "kg", "104.50", "121", "500"),
        ("TMT Rod 16 mm", "HW02", "kg", "103.75", "120", "500"),
        ("Binding Wire", "HW02", "kg", "118", "138", "50"),
        ("Emulsion Paint 20 litre", "HW03", "ltr", "5400", "6250", "10"),
        ("PVC Pipe 4 inch", "HW04", "m", "268", "320", "60"),
        ("GI Pipe 1 inch", "HW04", "m", "312", "375", "40"),
        ("Wire 2.5 sqmm, 90 metre coil", "HW05", "coil", "3850", "4450", "12"),
        ("Wire Nail 3 inch", "HW06", "kg", "142", "168", "40"),
        ("Cement Sheet", "HW08", "pcs", "1180", "1390", "25"),
    ]
    item_ids = {}
    for name, group, unit, buy, sell, reorder in catalogue:
        item_ids[name] = masters.create_item(
            conn, USER, name, group_id=groups.get(group), unit_id=units.get(unit),
            purchase_rate=buy, sale_rate=sell, reorder_qty=reorder, vat_rate_bp=1300)

    def day(bs_month, bs_day):
        year = fy["start_bs"][0] if bs_month >= 4 else fy["start_bs"][0] + 1
        return nd.bs_to_ad(year, bs_month, bs_day).isoformat()

    # Purchases.
    invoices.post_purchase(conn, USER, {
        "date_ad": day(4, 3), "party_id": supplier_ids[0], "reference_no": "HCS/2083/0417",
        "reference_date_ad": day(4, 3),
        "items": [
            {"item_id": item_ids["OPC Cement 50 kg"], "qty": "400", "rate": "805"},
            {"item_id": item_ids["PPC Cement 50 kg"], "qty": "250", "rate": "760"},
        ],
        "narration": "Season opening stock of cement"})
    invoices.post_purchase(conn, USER, {
        "date_ad": day(4, 8), "party_id": supplier_ids[1], "reference_no": "ESU/8302",
        "reference_date_ad": day(4, 8),
        "items": [
            {"item_id": item_ids["TMT Rod 12 mm"], "qty": "3200", "rate": "104.50"},
            {"item_id": item_ids["TMT Rod 16 mm"], "qty": "2400", "rate": "103.75"},
            {"item_id": item_ids["Binding Wire"], "qty": "180", "rate": "118"},
        ],
        "narration": "Rod and binding wire"})
    invoices.post_purchase(conn, USER, {
        "date_ad": day(4, 15), "party_id": supplier_ids[2], "reference_no": "LPH/1147",
        "items": [
            {"item_id": item_ids["Emulsion Paint 20 litre"], "qty": "24", "rate": "5400"},
            {"item_id": item_ids["PVC Pipe 4 inch"], "qty": "300", "rate": "268"},
            {"item_id": item_ids["GI Pipe 1 inch"], "qty": "220", "rate": "312"},
            {"item_id": item_ids["Wire 2.5 sqmm, 90 metre coil"], "qty": "40", "rate": "3850"},
            {"item_id": item_ids["Wire Nail 3 inch"], "qty": "160", "rate": "142"},
            {"item_id": item_ids["Cement Sheet"], "qty": "90", "rate": "1180"},
        ],
        "narration": "Paint, pipe, wire and sheet"})

    # Sales.
    invoices.post_sales(conn, USER, {
        "date_ad": day(4, 12), "party_id": customer_ids[0],
        "items": [
            {"item_id": item_ids["OPC Cement 50 kg"], "qty": "120", "rate": "915"},
            {"item_id": item_ids["TMT Rod 12 mm"], "qty": "900", "rate": "121"},
        ],
        "narration": "Supply to Butwal site, phase one"})
    invoices.post_sales(conn, USER, {
        "date_ad": day(4, 22), "party_id": customer_ids[1],
        "items": [
            {"item_id": item_ids["PPC Cement 50 kg"], "qty": "150", "rate": "870"},
            {"item_id": item_ids["TMT Rod 16 mm"], "qty": "1100", "rate": "120"},
            {"item_id": item_ids["Binding Wire"], "qty": "60", "rate": "138"},
        ],
        "narration": "Tilottama housing project"})
    invoices.post_sales(conn, USER, {
        "date_ad": day(5, 4), "party_id": customer_ids[2],
        "items": [
            {"item_id": item_ids["Emulsion Paint 20 litre"], "qty": "8", "rate": "6250"},
            {"item_id": item_ids["PVC Pipe 4 inch"], "qty": "120", "rate": "320"},
            {"item_id": item_ids["Cement Sheet"], "qty": "35", "rate": "1390"},
        ],
        "narration": "Siddharthanagar site"})
    for counter_day, lines in (
        (7, [("OPC Cement 50 kg", "12", "915"), ("Wire Nail 3 inch", "6", "168")]),
        (11, [("GI Pipe 1 inch", "18", "375"), ("Binding Wire", "4", "138")]),
        (14, [("Wire 2.5 sqmm, 90 metre coil", "3", "4450")]),
    ):
        invoices.post_sales(conn, USER, {
            "date_ad": day(5, counter_day), "payment_mode": "cash",
            "items": [{"item_id": item_ids[n], "qty": q, "rate": r} for n, q, r in lines],
            "narration": "Counter sale"})

    # Money in and out.
    def account_of(party_id):
        return masters.get_party(conn, party_id)["account_id"]

    ledger.post_voucher(conn, USER, {
        "voucher_type": "receipt", "date_ad": day(5, 2), "party_id": customer_ids[0],
        "payment_mode": "cheque", "reference_no": "Nabil 004518",
        "narration": "Part payment against phase one",
        "entries": [{"account_id": bank["id"], "dr": "150000", "cr": 0},
                    {"account_id": account_of(customer_ids[0]), "dr": 0, "cr": "150000"}]})
    ledger.post_voucher(conn, USER, {
        "voucher_type": "receipt", "date_ad": day(5, 9), "party_id": customer_ids[1],
        "payment_mode": "cash", "narration": "Cash received",
        "entries": [{"account_id": cash["id"], "dr": "90000", "cr": 0},
                    {"account_id": account_of(customer_ids[1]), "dr": 0, "cr": "90000"}]})
    ledger.post_voucher(conn, USER, {
        "voucher_type": "payment", "date_ad": day(5, 6), "party_id": supplier_ids[0],
        "payment_mode": "cheque", "reference_no": "Nabil 771204",
        "narration": "Against bill HCS/2083/0417",
        "entries": [{"account_id": account_of(supplier_ids[0]), "dr": "300000", "cr": 0},
                    {"account_id": bank["id"], "dr": 0, "cr": "300000"}]})
    ledger.post_voucher(conn, USER, {
        "voucher_type": "payment", "date_ad": day(5, 12), "party_id": supplier_ids[1],
        "payment_mode": "cheque", "reference_no": "Nabil 771205",
        "narration": "Against bill ESU/8302",
        "entries": [{"account_id": account_of(supplier_ids[1]), "dr": "250000", "cr": 0},
                    {"account_id": bank["id"], "dr": 0, "cr": "250000"}]})

    # Running costs.
    expenses = [
        ("6201", "48000", "Shop rent for Shrawan and Bhadra", 5, 1),
        ("6101", "96000", "Staff salary for Shrawan", 5, 1),
        ("6202", "7400", "Electricity and water", 5, 8),
        ("6203", "3200", "Telephone and internet", 5, 8),
        ("6207", "12500", "Diesel for the delivery vehicle", 5, 10),
        ("6209", "4800", "Printing of invoice books", 5, 13),
        ("5202", "18000", "Freight on inward stock", 4, 16),
    ]
    for code, amount, note, bs_month, bs_day in expenses:
        account = masters.account_by_code(conn, code)
        ledger.post_voucher(conn, USER, {
            "voucher_type": "payment", "date_ad": day(bs_month, bs_day), "narration": note,
            "entries": [{"account_id": account["id"], "dr": amount, "cr": 0},
                        {"account_id": cash["id"], "dr": 0, "cr": amount}]})

    # Bring the closing stock into the accounts so the profit reads properly.
    last = conn.execute("SELECT MAX(date_ad) d FROM vouchers").fetchone()["d"]
    period_end.post_closing_stock(conn, USER, last)

    system.execute("UPDATE companies SET sort_order = 99 WHERE slug = ?", (DEMO_SLUG,))

    from chartered_book.modules import reports
    tb = reports.trial_balance(conn, start, last)
    bs = reports.balance_sheet(conn, last, start)
    pl = reports.profit_and_loss(conn, start, last)
    stock = reports.stock_summary(conn, last)

    print()
    print("  Demonstration company built: %s" % DEMO_NAME)
    print("  Period %s to %s" % (start, last))
    print()
    print("    vouchers posted       %d" % conn.execute(
        "SELECT COUNT(*) n FROM vouchers WHERE status = 'posted'").fetchone()["n"])
    print("    revenue               %s" % money.format_money(pl["revenue"]))
    print("    gross profit          %s" % money.format_money(pl["gross_profit"]))
    print("    profit for the period %s" % money.format_money(pl["profit_after_tax"]))
    print("    stock on hand         %s" % money.format_money(stock["total_value"]))
    print("    trial balance ties    %s" % ("yes" if tb["balanced"] else "NO"))
    print("    balance sheet ties    %s" % ("yes" if bs["balanced"] else "NO"))
    print()
    print("  Remove it again with:  python3 tools/demo_data.py --remove")
    return 0 if (tb["balanced"] and bs["balanced"]) else 1


def main():
    parser = argparse.ArgumentParser(description="Build or remove the demonstration company.")
    parser.add_argument("--remove", action="store_true", help="Delete the demonstration company.")
    args = parser.parse_args()
    return remove() if args.remove else build()


if __name__ == "__main__":
    sys.exit(main())

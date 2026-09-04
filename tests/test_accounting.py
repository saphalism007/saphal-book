"""
End to end proof that the books hold together.

A small hardware business is created from nothing, real vouchers are posted,
and every figure is checked: the trial balance ties, the balance sheet balances,
stock values correctly under weighted average, and the VAT position agrees with
the ledger.

Run with:  python3 -m tests.test_accounting
"""

import glob
import os
import sys

from chartered_book.core import db, money, nepali_date as nd
from chartered_book.modules import (company, inventory, invoices, ledger, masters,
                                    reports)

FAILURES = []
USER = "testrunner"


def check(label, got, expected):
    if got != expected:
        FAILURES.append("%s: got %r, expected %r" % (label, got, expected))


def rs(paisa):
    return money.format_money(paisa)


def clean_up():
    """
    Leave nothing behind. The test builds its own company and must not leave it
    sitting in the list of real businesses when it finishes.
    """
    system = db.open_system()
    system.execute("DELETE FROM companies WHERE slug LIKE 'test_hardware%'")
    for path in glob.glob(os.path.join(db.BOOKS_DIR, "test_hardware*")):
        try:
            os.remove(path)
        except OSError:
            pass


def build_books():
    clean_up()
    system = db.open_system()
    result = company.create_company(
        system, "Test Hardware Nepal", "trading", USER,
        pan="301234567", vat_registered=1, city="Butwal", district="Rupandehi",
        books_begin_ad=nd.fiscal_year(2083)["start_ad"])
    # This suite is about the periodic system: purchases go to Purchases and a
    # closing stock entry brings the value in at the year end. The perpetual
    # system, which is what new books use, is covered in test_inventory.
    inventory.set_method(result["conn"], "periodic", USER)
    return result["conn"]


def main():
    conn = build_books()
    fy = company.current_fiscal_year(conn)
    start, end = fy["start_ad"], fy["end_ad"]

    # A business does not start empty. Put the opening capital and cash in.
    cash = masters.account_by_code(conn, "1251")
    capital = masters.account_by_code(conn, "3101")
    masters.update_account(conn, USER, cash["id"], opening="150000", opening_side="dr")
    masters.update_account(conn, USER, capital["id"], opening="150000", opening_side="cr")

    supplier = masters.create_party(conn, USER, "Himal Cement Suppliers", "supplier",
                                    pan="609876543", vat_registered=1, credit_days=30)
    customer = masters.create_party(conn, USER, "Ram Construction Sewa", "customer",
                                    pan="302345678", vat_registered=1, credit_days=15)

    bag = masters.unit_by_symbol(conn, "bag")
    kg = masters.unit_by_symbol(conn, "kg")
    cement = masters.create_item(conn, USER, "OPC Cement 50 kg", unit_id=bag["id"],
                                 purchase_rate="800", sale_rate="1000", vat_rate_bp=1300,
                                 reorder_qty="20")
    rod = masters.create_item(conn, USER, "TMT Rod 12 mm", unit_id=kg["id"],
                              purchase_rate="105", sale_rate="128", vat_rate_bp=1300)

    d1 = nd.bs_to_ad(2083, 4, 5).isoformat()
    d2 = nd.bs_to_ad(2083, 4, 12).isoformat()
    d3 = nd.bs_to_ad(2083, 4, 20).isoformat()
    d4 = nd.bs_to_ad(2083, 5, 2).isoformat()

    # Purchase 100 bags at 800 and 500 kg rod at 105, both on credit.
    purchase_id = invoices.post_purchase(conn, USER, {
        "date_ad": d1, "party_id": supplier, "reference_no": "HCS/2083/041",
        "items": [
            {"item_id": cement, "qty": "100", "rate": "800"},
            {"item_id": rod, "qty": "500", "rate": "105"},
        ],
        "narration": "Opening stock purchase for the season",
    })

    # Sell 60 bags at 1000 and 200 kg rod at 128, on credit.
    sales_id = invoices.post_sales(conn, USER, {
        "date_ad": d2, "party_id": customer,
        "items": [
            {"item_id": cement, "qty": "60", "rate": "1000"},
            {"item_id": rod, "qty": "200", "rate": "128"},
        ],
        "narration": "Supply for Butwal site",
    })

    # A cash counter sale that needs rounding.
    cash_sale_id = invoices.post_sales(conn, USER, {
        "date_ad": d3, "payment_mode": "cash",
        "items": [{"item_id": rod, "qty": "3.5", "rate": "127.75"}],
        "narration": "Counter sale",
    })

    # Receipt from the customer and payment to the supplier.
    customer_account = masters.get_party(conn, customer)["account_id"]
    supplier_account = masters.get_party(conn, supplier)["account_id"]
    ledger.post_voucher(conn, USER, {
        "voucher_type": "receipt", "date_ad": d4, "party_id": customer,
        "payment_mode": "cash", "narration": "Part payment received",
        "entries": [
            {"account_id": cash["id"], "dr": "50000", "cr": 0},
            {"account_id": customer_account, "dr": 0, "cr": "50000"},
        ]})
    ledger.post_voucher(conn, USER, {
        "voucher_type": "payment", "date_ad": d4, "party_id": supplier,
        "payment_mode": "cash", "narration": "Part payment made",
        "entries": [
            {"account_id": supplier_account, "dr": "80000", "cr": 0},
            {"account_id": cash["id"], "dr": 0, "cr": "80000"},
        ]})

    # An expense, so the profit and loss has something on both sides.
    rent = masters.account_by_code(conn, "6201")
    ledger.post_voucher(conn, USER, {
        "voucher_type": "payment", "date_ad": d4, "narration": "Shop rent for Shrawan",
        "entries": [
            {"account_id": rent["id"], "dr": "25000", "cr": 0},
            {"account_id": cash["id"], "dr": 0, "cr": "25000"},
        ]})

    # Checks

    purchase = ledger.get_voucher(conn, purchase_id)["voucher"]
    check("purchase taxable", purchase["taxable_paisa"], money.to_paisa("132500"))
    check("purchase vat", purchase["vat_paisa"], money.to_paisa("17225"))
    check("purchase total", purchase["total_paisa"], money.to_paisa("149725"))

    sale = ledger.get_voucher(conn, sales_id)["voucher"]
    check("sales taxable", sale["taxable_paisa"], money.to_paisa("85600"))
    check("sales vat", sale["vat_paisa"], money.to_paisa("11128"))
    check("sales total", sale["total_paisa"], money.to_paisa("96728"))

    # 3.5 kg at 127.75 is 447.125, which rounds to 447.13 at the paisa.
    # VAT at 13 percent is 58.13, giving 505.26, rounded to 505.00 on the invoice.
    counter = ledger.get_voucher(conn, cash_sale_id)["voucher"]
    check("counter taxable", counter["taxable_paisa"], money.to_paisa("447.13"))
    check("counter vat", counter["vat_paisa"], money.to_paisa("58.13"))
    check("counter total is a whole rupee", counter["total_paisa"] % 100, 0)
    check("counter total", counter["total_paisa"], money.to_paisa("505"))
    check("counter round off", counter["round_off_paisa"], money.to_paisa("-0.26"))

    # Every voucher must balance on its own.
    for row in conn.execute("SELECT id, number FROM vouchers WHERE status = 'posted'"):
        sums = conn.execute("""SELECT SUM(dr_paisa) dr, SUM(cr_paisa) cr
                               FROM voucher_entries WHERE voucher_id = ?""", (row["id"],)).fetchone()
        if sums["dr"] != sums["cr"]:
            FAILURES.append("voucher %s does not balance: %s against %s"
                            % (row["number"], rs(sums["dr"]), rs(sums["cr"])))

    tb = reports.trial_balance(conn, start, end)
    check("trial balance ties", tb["balanced"], True)
    if not tb["balanced"]:
        FAILURES.append("trial balance closing: dr %s, cr %s"
                        % (rs(tb["totals"]["closing_dr"]), rs(tb["totals"]["closing_cr"])))

    # Stock. 100 bags in, 60 out, leaves 40 at cost 800.
    cement_stock = reports.item_stock(conn, cement, end)
    check("cement quantity", money.format_qty(cement_stock["qty"]), "40")
    check("cement value", cement_stock["value"], money.to_paisa("32000"))
    check("cement average rate", cement_stock["average_rate"], money.to_paisa("800"))

    # Rod: 500 kg in at 105, out 200 then 3.5, leaves 296.5 kg at 105.
    rod_stock = reports.item_stock(conn, rod, end)
    check("rod quantity", money.format_qty(rod_stock["qty"]), "296.5")
    check("rod value", rod_stock["value"], money.to_paisa("31132.50"))

    summary = reports.stock_summary(conn, end)
    check("stock total value", summary["total_value"], money.to_paisa("63132.50"))

    # Party balances.
    receivable = reports.outstanding(conn, "receivable", end)
    check("customer outstanding", receivable["total"], money.to_paisa("46728"))
    payable = reports.outstanding(conn, "payable", end)
    check("supplier outstanding", payable["total"], money.to_paisa("69725"))

    # VAT position.
    output = reports.balances_as_at(conn, end)[masters.account_by_code(conn, "2241")["id"]]
    inputs = reports.balances_as_at(conn, end)[masters.account_by_code(conn, "1241")["id"]]
    check("vat output collected", -output, money.to_paisa("11186.13"))
    check("vat input paid", inputs, money.to_paisa("17225"))

    # Profit and loss.
    pl = reports.profit_and_loss(conn, start, end)
    check("revenue", pl["revenue"], money.to_paisa("86047.13"))
    check("cost of sales before closing stock", pl["cost_of_sales"], money.to_paisa("132500"))
    check("administrative expenses", pl["administrative"], money.to_paisa("25000"))

    # Balance sheet must balance even before the closing stock entry is passed.
    bs = reports.balance_sheet(conn, end, start)
    check("balance sheet balances", bs["balanced"], True)
    if not bs["balanced"]:
        FAILURES.append("balance sheet difference %s" % rs(bs["difference"]))

    # Cancelling a voucher must remove it from every figure.
    before_cancel = reports.trial_balance(conn, start, end)["totals"]["period_dr"]
    ledger.cancel_voucher(conn, USER, cash_sale_id, "Customer returned at the counter")
    after_cancel = reports.trial_balance(conn, start, end)["totals"]["period_dr"]
    check("cancelling reduces the totals", after_cancel < before_cancel, True)
    check("cancelled sale leaves stock behind",
          money.format_qty(reports.item_stock(conn, rod, end)["qty"]), "300")
    check("trial balance still ties after cancelling",
          reports.trial_balance(conn, start, end)["balanced"], True)

    # An unbalanced voucher must be refused.
    try:
        ledger.post_voucher(conn, USER, {
            "voucher_type": "journal", "date_ad": d4,
            "entries": [{"account_id": cash["id"], "dr": "100", "cr": 0},
                        {"account_id": rent["id"], "dr": 0, "cr": "90"}]})
        FAILURES.append("an unbalanced voucher was accepted")
    except ledger.PostingError:
        pass

    # A date outside any fiscal year must be refused.
    try:
        ledger.post_voucher(conn, USER, {
            "voucher_type": "journal", "date_ad": "2019-01-01",
            "entries": [{"account_id": cash["id"], "dr": "100", "cr": 0},
                        {"account_id": rent["id"], "dr": 0, "cr": "100"}]})
        FAILURES.append("a voucher dated outside the open year was accepted")
    except ledger.PostingError:
        pass

    # Voucher numbers must never repeat inside a year.
    numbers = [r["number"] for r in conn.execute(
        "SELECT number FROM vouchers WHERE voucher_type = 'sales'")]
    check("sales numbers are unique", len(numbers), len(set(numbers)))

    conn.close()
    clean_up()

    if FAILURES:
        print("FAILED (%d)" % len(FAILURES))
        for line in FAILURES:
            print("  " + line)
        return 1
    print("All accounting tests passed.")
    print("  Trial balance closing debit  %s" % rs(tb["totals"]["closing_dr"]))
    print("  Trial balance closing credit %s" % rs(tb["totals"]["closing_cr"]))
    print("  Stock on hand                %s" % rs(summary["total_value"]))
    print("  Receivable / payable         %s / %s" % (rs(receivable["total"]), rs(payable["total"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())

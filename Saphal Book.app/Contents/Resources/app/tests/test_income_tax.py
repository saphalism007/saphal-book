"""
The income tax computation, under the Income Tax Act, 2058.

Profit in the books and income under the Act are two different numbers, and
every step between them is a place where a return can go wrong. So each figure
here is worked out by hand first and the program is made to agree with it,
rather than the other way round.

The year is built deliberately: a profit large enough to reach the top slab, a
fine that is never deductible, a donation that is capped, a provision that is
not an expense yet, book depreciation that has to come out and pool
depreciation that has to go in, tax deducted at source, and advance tax paid.

Run with:  python3 -m tests.test_income_tax
"""

import glob
import os
import sys

from chartered_book.core import db, money, nepali_date as nd
from chartered_book.modules import company, income_tax, ledger, masters

FAILURES = []
USER = "incometaxtest"
SLUG = "income_tax_test_company"


def check(label, got, expected):
    if got != expected:
        FAILURES.append("%s: got %s, expected %s"
                        % (label,
                           money.format_money(got) if isinstance(got, int) else got,
                           money.format_money(expected) if isinstance(expected, int) else expected))


def clean_up():
    system = db.open_system()
    system.execute("DELETE FROM companies WHERE slug LIKE 'income_tax_test%'")
    system.commit()
    for path in glob.glob(os.path.join(db.BOOKS_DIR, SLUG + ".db*")):
        try:
            os.remove(path)
        except OSError:
            pass


def spend(conn, date_ad, code, amount, narration):
    """One expense, paid in cash, so the profit and loss has it."""
    account = masters.account_by_code(conn, code)
    cash = masters.account_by_code(conn, "1251")
    ledger.post_voucher(conn, USER, {
        "voucher_type": "payment", "date_ad": date_ad, "narration": narration,
        "entries": [
            {"account_id": account["id"], "dr": amount, "cr": 0},
            {"account_id": cash["id"], "dr": 0, "cr": amount},
        ]})


def main():
    clean_up()
    system = db.open_system()
    fy = nd.fiscal_year(2083)
    result = company.create_company(system, "Income Tax Test Company", "trading", USER,
                                    books_begin_ad=fy["start_ad"])
    conn = result["conn"]

    def day(month, dayno):
        return nd.bs_to_ad(2083, month, dayno).isoformat()

    cash = masters.account_by_code(conn, "1251")
    sales = masters.account_by_code(conn, "4111")

    # Income of thirty lakh, taken in cash so nothing else moves.
    ledger.post_voucher(conn, USER, {
        "voucher_type": "journal", "date_ad": day(4, 15), "narration": "Sales for the year",
        "entries": [
            {"account_id": cash["id"], "dr": "3000000", "cr": 0},
            {"account_id": sales["id"], "dr": 0, "cr": "3000000"},
        ]})

    # Expenses. Four of the six are treated differently by the Act.
    spend(conn, day(5, 1), "6201", "400000", "Shop rent")            # allowed
    spend(conn, day(5, 2), "7303", "25000", "Penalty on late VAT")   # never allowed
    spend(conn, day(5, 3), "6226", "150000", "Donation to a school") # capped
    spend(conn, day(5, 4), "6307", "60000", "Provision for a doubtful debt")
    spend(conn, day(5, 5), "7302", "40000", "Last year's electricity")
    spend(conn, day(5, 6), "7204", "50000", "Depreciation on office equipment")

    # Tax already suffered, and advance tax paid.
    tds = masters.account_by_code(conn, "1244")
    advance = masters.account_by_code(conn, "1243")
    ledger.post_voucher(conn, USER, {
        "voucher_type": "journal", "date_ad": day(6, 1),
        "narration": "Tax deducted by a customer",
        "entries": [
            {"account_id": tds["id"], "dr": "35000", "cr": 0},
            {"account_id": cash["id"], "dr": 0, "cr": "35000"},
        ]})
    ledger.post_voucher(conn, USER, {
        "voucher_type": "payment", "date_ad": day(9, 20),
        "narration": "Advance tax, first instalment",
        "entries": [
            {"account_id": advance["id"], "dr": "100000", "cr": 0},
            {"account_id": cash["id"], "dr": 0, "cr": "100000"},
        ]})

    # An asset, so Schedule 2 has a pool to work on. Class D, fifteen percent,
    # bought in Shrawan so the whole cost is absorbed in the first year.
    now = db.now_stamp()
    conn.execute(
        """INSERT INTO fixed_assets (code, name, asset_account_id, tax_class, acquired_ad,
                                     acquired_bs, cost_paisa, book_method, book_rate_bp,
                                     useful_life_years, active, created_at, updated_at)
           VALUES (?, ?, ?, 'D', ?, ?, ?, 'wdv', 1500, 0, 1, ?, ?)""",
        ("FA001", "Office equipment", masters.account_by_code(conn, "1117")["id"],
         day(4, 1), nd.format_bs(nd.ad_to_bs(day(4, 1)), "numeric"),
         money.to_paisa("400000"), now, now))

    company.apply_tax_treatments(conn)
    income_tax.set_treatment(
        conn, USER, masters.account_by_code(conn, "6226")["id"], "donation",
        note="Section 12")
    conn.commit()

    # Worked by hand.
    #
    #   Sales                                     30,00,000
    #   less rent                                 (4,00,000)
    #   less penalty                                (25,000)
    #   less donation                             (1,50,000)
    #   less provision                              (60,000)
    #   less prior period                           (40,000)
    #   less depreciation in the books              (50,000)
    #                                             (7,25,000)
    #   Net profit in the books                   22,75,000
    #
    #   add back the books' depreciation             50,000
    #   add back penalty, donation, provision and
    #        prior period  25 + 150 + 60 + 40 =     2,75,000
    #   less depreciation under Schedule 2,
    #        4,00,000 absorbed in full at 15%        (60,000)
    #   Assessable income                         25,40,000
    #
    #   Donation allowed is the lowest of
    #        1,50,000 given, 5% of 25,40,000 =
    #        1,27,000, and 1,00,000            so  (1,00,000)
    #   Taxable income                            24,40,000
    #
    #   Tax, as a single proprietor:
    #        first  5,00,000 at nil                        0
    #        next   2,00,000 at 10%                   20,000
    #        next   3,00,000 at 20%                   60,000
    #        next  10,00,000 at 30%                 3,00,000
    #        last   4,40,000 at 36%                 1,58,400
    #                                               5,38,400
    #   less tax deducted at source                  (35,000)
    #   less advance tax paid                      (1,00,000)
    #   Left to pay                                 4,03,400

    result = income_tax.computation(conn, 2083)

    check("net profit in the books", result["net_profit"], money.to_paisa("2275000"))
    check("the books' own depreciation is added back",
          result["book_depreciation"], money.to_paisa("50000"))
    check("what the Act does not allow is added back",
          result["additions"], money.to_paisa("275000"))
    check("depreciation under Schedule 2",
          result["tax_depreciation"], money.to_paisa("60000"))
    check("assessable income, section 7", result["assessable"], money.to_paisa("2540000"))
    check("what was given away", result["donation_given"], money.to_paisa("150000"))
    check("the section 12 cap", result["donation_cap"], money.to_paisa("100000"))
    check("what the donation is worth", result["donation_allowed"], money.to_paisa("100000"))
    check("taxable income, section 3", result["taxable"], money.to_paisa("2440000"))
    check("tax on that", result["tax"], money.to_paisa("538400"))
    check("tax deducted at source", result["tds"], money.to_paisa("35000"))
    check("advance tax comes off the ledger, not a typed figure",
          result["advance_tax"], money.to_paisa("100000"))
    check("left to pay", result["outstanding"], money.to_paisa("403400"))

    # A proprietor is on the slabs, and the first band is nil because the one
    # percent is a social security tax on remuneration.
    check("a proprietorship is assessed on the slabs",
          result["assessed_as"], "business_individual")
    check("the first band does not bite", result["bands"][0]["tax"], 0)

    # The statement has to add up on its own face, or nobody can check it.
    running = 0
    for row in result["rows"]:
        if row.get("kind") in ("total", "start"):
            if row.get("kind") == "start":
                running = row["amount"]
                continue
            check("the statement adds up at %s" % row["label"], running, row["amount"])
        else:
            running += row["amount"]
        if row.get("kind") == "total":
            running = row["amount"]

    # Every ledger that was added back has to be named, not hidden in a lump.
    named = {row["code"]: row["added_back"] for row in result["added_back"]}
    check("four ledgers were added back", len(named), 4)
    check("the penalty is named", named.get("7303"), money.to_paisa("25000"))
    check("the donation is named", named.get("6226"), money.to_paisa("150000"))
    check("the provision is named", named.get("6307"), money.to_paisa("60000"))
    check("the prior period item is named", named.get("7302"), money.to_paisa("40000"))

    # A partly allowed ledger comes back at the share that is not allowed.
    income_tax.set_treatment(conn, USER, masters.account_by_code(conn, "6201")["id"],
                             "partial", allowed_bp=7500, note="Three quarters allowed")
    partial = income_tax.computation(conn, 2083)
    rent_back = {row["code"]: row["added_back"] for row in partial["added_back"]}
    check("a quarter of the rent comes back", rent_back.get("6201"), money.to_paisa("100000"))
    income_tax.set_treatment(conn, USER, masters.account_by_code(conn, "6201")["id"],
                             "allowed")

    # A company pays a flat twenty five percent on the same income.
    income_tax.set_year(conn, USER, 2083, assessed_as="entity")
    as_company = income_tax.computation(conn, 2083)
    check("a company pays a flat rate", as_company["tax"], money.to_paisa("610000"))
    income_tax.set_year(conn, USER, 2083, assessed_as="business_individual")

    # A loss cannot be taxed, and it has to be carried forward rather than lost.
    spend(conn, day(10, 1), "6201", "4000000", "A very expensive year")
    conn.commit()
    loss = income_tax.computation(conn, 2083)
    check("a loss is not taxed", loss["taxable"], 0)
    check("and no tax falls due", loss["tax"], 0)
    check("the loss goes forward", loss["loss_carried_forward"],
          money.to_paisa("1460000"))
    check("nothing is deductible for the donation in a loss year",
          loss["donation_allowed"], 0)
    check("the year is refundable", loss["outstanding"], -money.to_paisa("135000"))

    # A loss brought in is used only against a profit, and only up to it.
    conn.execute("DELETE FROM voucher_items WHERE voucher_id IN "
                 "(SELECT id FROM vouchers WHERE narration = 'A very expensive year')")
    conn.execute("DELETE FROM vouchers WHERE narration = 'A very expensive year'")
    conn.commit()
    income_tax.set_year(conn, USER, 2083, brought_forward_loss="3000000")
    carried = income_tax.computation(conn, 2083)
    check("only as much of the loss as there is income gets used",
          carried["loss_used"], money.to_paisa("2440000"))
    check("the rest still goes forward", carried["loss_carried_forward"],
          money.to_paisa("560000"))
    check("and nothing is left to tax", carried["taxable"], 0)
    income_tax.set_year(conn, USER, 2083, brought_forward_loss=0)

    # Rates live in the books, and saving them stops the warning.
    seeded = income_tax.computation(conn, 2083)
    check("rates start out unconfirmed", seeded["rates_were_seeded"], True)
    income_tax.save_rates(conn, USER, 2083, "business_individual", [
        {"band_from": 0, "band_to": "500000", "rate_bp": 0, "note": "First 5,00,000 nil"},
        {"band_from": "500000", "band_to": "700000", "rate_bp": 10, "note": "Next 2,00,000"},
        {"band_from": "700000", "band_to": "1000000", "rate_bp": 20, "note": "Next 3,00,000"},
        {"band_from": "1000000", "band_to": "2000000", "rate_bp": 30, "note": "Next 10,00,000"},
        {"band_from": "2000000", "band_to": None, "rate_bp": 36, "note": "The rest"},
    ])
    conn.commit()
    confirmed = income_tax.computation(conn, 2083)
    check("once saved they are no longer a guess", confirmed["rates_were_seeded"], False)
    check("and the tax is the same figure", confirmed["tax"], money.to_paisa("538400"))

    # Bands that leave a gap are refused, because a gap means income nobody taxed.
    try:
        income_tax.save_rates(conn, USER, 2083, "entity", [
            {"band_from": 0, "band_to": "500000", "rate_bp": 10},
            {"band_from": "600000", "band_to": None, "rate_bp": 25},
        ])
        FAILURES.append("a gap between bands was accepted")
    except income_tax.TaxError:
        pass

    # A top band with a ceiling would leave the largest incomes untaxed.
    try:
        income_tax.save_rates(conn, USER, 2083, "entity", [
            {"band_from": 0, "band_to": "500000", "rate_bp": 25},
        ])
        FAILURES.append("a closed top band was accepted")
    except income_tax.TaxError:
        pass

    conn.commit()
    conn.close()
    clean_up()

    if FAILURES:
        print("Income tax: %d problem%s" % (len(FAILURES),
                                            "" if len(FAILURES) == 1 else "s"))
        for line in FAILURES:
            print("  " + line)
        return 1
    print("Income tax: every figure agrees with the one worked by hand.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

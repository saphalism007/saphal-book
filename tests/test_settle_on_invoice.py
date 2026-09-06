"""
Taking the money at the same time as writing the bill.

A customer who pays part of an invoice at the counter used to mean four
separate acts: save the invoice, leave it, open a receipt, find the bill again
and allocate against it. The amount goes on the invoice now and the receipt is
written with it.

What has to be true afterwards is the whole of this test. The customer owes the
bill less what they handed over, the cash box is up by exactly that, and the
receipt is allocated to the invoice rather than left floating on account.

Run with:  python3 -m tests.test_settle_on_invoice
"""

import glob
import os
import sys

from chartered_book.core import db, money, nepali_date as nd
from chartered_book.modules import company, invoices, masters, reports, settlements

FAILURES = []
USER = "settletest"


def check(label, got, expected):
    if got != expected:
        FAILURES.append("%s: got %s, expected %s"
                        % (label,
                           money.format_money(got) if isinstance(got, int) else got,
                           money.format_money(expected) if isinstance(expected, int) else expected))


def clean_up():
    system = db.open_system()
    system.execute("DELETE FROM companies WHERE slug LIKE 'settle_test%'")
    system.commit()
    for path in glob.glob(os.path.join(db.BOOKS_DIR, "settle_test*")):
        try:
            os.remove(path)
        except OSError:
            pass


def balance(conn, account_id, upto_ad):
    return reports.balances_as_at(conn, upto_ad).get(account_id, 0)


def main():
    clean_up()
    system = db.open_system()
    fiscal = nd.fiscal_year(nd.today_bs()[0])
    made = company.create_company(system, "Settle Test Shop", "trading", USER,
                                  books_begin_ad=fiscal["start_ad"])
    conn = made["conn"]
    day = nd.bs_to_ad(nd.today_bs()[0], 4, 10).isoformat()

    customer = masters.create_party(conn, USER, {
        "name": "Counter Customer", "party_type": "customer"})
    unit = conn.execute("SELECT id FROM units LIMIT 1").fetchone()["id"]
    item = masters.create_item(conn, USER, {
        "name": "Cement Bag", "unit_id": unit, "vat_applicable": 1,
        "sale_rate": "1000", "purchase_rate": "800", "maintain_stock": 1})

    cash = masters.account_by_code(conn, "1251")["id"]
    customer_account = masters.get_party(conn, customer)["account_id"]

    # Ten bags at a thousand, plus thirteen percent, is 11,300.
    voucher_id = invoices.post_sales(conn, USER, {
        "date_ad": day, "party_id": customer, "narration": "Counter sale",
        "round_invoice": False,
        "items": [{"item_id": item, "qty": "10", "rate": "1000"}]})
    conn.commit()

    invoice = conn.execute("SELECT number, total_paisa FROM vouchers WHERE id = ?",
                           (voucher_id,)).fetchone()
    check("the invoice comes to eleven thousand three hundred",
          invoice["total_paisa"], money.to_paisa("11300"))
    check("and the customer owes all of it",
          balance(conn, customer_account, day), money.to_paisa("11300"))

    cash_before = balance(conn, cash, day)

    # Now the part the screen does: four thousand handed over at the counter.
    settlements.post(conn, USER, {
        "date_ad": day,
        "party_id": customer,
        "bank_account_id": cash,
        "payment_mode": "cash",
        "narration": "Against %s" % invoice["number"],
        "allocations": [{"voucher_id": voucher_id, "amount": "4000"}],
    }, "receipt")
    conn.commit()

    check("the customer now owes the rest",
          balance(conn, customer_account, day), money.to_paisa("7300"))
    check("and the cash box is up by what was handed over",
          balance(conn, cash, day) - cash_before, money.to_paisa("4000"))

    # The receipt has to be allocated to the bill, not left on account, or the
    # invoice goes on showing as unpaid in every ageing report there is.
    open_bills = settlements.open_bills(conn, customer, "receivable", day)
    against = [b for b in open_bills["bills"] if b["voucher_id"] == voucher_id]
    check("the invoice is still open for the balance", "%d found" % len(against),
          "1 found")
    if against:
        check("for exactly what is left", against[0]["amount"], money.to_paisa("7300"))

    # Paying the whole bill closes it.
    settlements.post(conn, USER, {
        "date_ad": day, "party_id": customer, "bank_account_id": cash,
        "payment_mode": "cash", "narration": "Balance",
        "allocations": [{"voucher_id": voucher_id, "amount": "7300"}],
    }, "receipt")
    conn.commit()

    check("nothing is owed once it is all paid",
          balance(conn, customer_account, day), 0)
    left = settlements.open_bills(conn, customer, "receivable", day)
    check("and the bill drops off the open list",
          [b for b in left["bills"] if b["voucher_id"] == voucher_id], [])

    # More than the bill has to be refused, or a typed extra zero quietly
    # becomes an advance nobody meant to take.
    second = invoices.post_sales(conn, USER, {
        "date_ad": day, "party_id": customer, "narration": "Another",
        "round_invoice": False,
        "items": [{"item_id": item, "qty": "1", "rate": "1000"}]})
    conn.commit()
    total = conn.execute("SELECT total_paisa FROM vouchers WHERE id = ?",
                         (second,)).fetchone()["total_paisa"]
    check("the second invoice is one thousand one hundred and thirty",
          total, money.to_paisa("1130"))

    conn.commit()
    conn.close()
    clean_up()

    if FAILURES:
        print("Settle on invoice: %d problem%s"
              % (len(FAILURES), "" if len(FAILURES) == 1 else "s"))
        for line in FAILURES:
            print("  " + line)
        return 1
    print("Settle on invoice: the money lands on the bill it was paid against.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""
Period end work.

Under the periodic inventory system used here, purchases sit in cost of sales
in full until the closing stock is brought in. This module passes that entry,
and the opening stock entry that mirrors it at the start of the next year.

Both entries are adjusting journals. Running the closing stock tool a second
time posts only the difference, so it is safe to run again after a late invoice
has been entered.
"""

from ..core import money
from . import inventory, ledger, masters, reports

STOCK_IN_TRADE = "1211"
CLOSING_STOCK = "5302"
OPENING_STOCK = "5301"


class PeriodEndError(Exception):
    """Raised when a period end entry cannot be passed."""


def _account(conn, code, label):
    row = masters.account_by_code(conn, code)
    if row is None:
        raise PeriodEndError("The %s account (code %s) is missing." % (label, code))
    return row


def closing_stock_position(conn, date_ad):
    """What the closing stock entry would do if it were passed now."""
    stock = reports.stock_summary(conn, date_ad)
    valued = stock["total_value"]
    account = _account(conn, STOCK_IN_TRADE, "stock in trade")
    balances = reports.balances_as_at(conn, date_ad)
    booked = balances.get(account["id"], 0)
    return {
        "date_ad": date_ad,
        "valued_at": valued,
        "already_booked": booked,
        "adjustment": valued - booked,
        "item_count": len(stock["rows"]),
        "account_id": account["id"],
    }


def post_closing_stock(conn, username, date_ad, narration=""):
    """
    Bring the value of stock on hand into the accounts.

    Debit Stock in Trade, credit Closing Stock. Only the difference between the
    valued stock and what is already booked is posted, so the entry can be run
    again without doubling up.
    """
    if inventory.is_perpetual(conn):
        raise PeriodEndError(
            "These books keep stock on the perpetual system, so the cost of what was sold "
            "is already charged as each sale is made and Stock in Trade already carries "
            "what is on hand. A closing stock entry would count it twice.")
    position = closing_stock_position(conn, date_ad)
    adjustment = position["adjustment"]
    if adjustment == 0:
        raise PeriodEndError(
            "Stock is already booked at %s. There is nothing to adjust."
            % money.format_money(position["valued_at"]))
    stock_account = position["account_id"]
    closing_account = _account(conn, CLOSING_STOCK, "closing stock")["id"]
    if adjustment > 0:
        entries = [
            {"account_id": stock_account, "dr": money.to_rupees(adjustment), "cr": 0},
            {"account_id": closing_account, "dr": 0, "cr": money.to_rupees(adjustment)},
        ]
    else:
        entries = [
            {"account_id": closing_account, "dr": money.to_rupees(-adjustment), "cr": 0},
            {"account_id": stock_account, "dr": 0, "cr": money.to_rupees(-adjustment)},
        ]
    return ledger.post_voucher(conn, username, {
        "voucher_type": "journal",
        "date_ad": date_ad,
        "narration": narration or ("Closing stock valued at %s on %s"
                                   % (money.format_money(position["valued_at"]), date_ad)),
        "entries": entries,
    })


def post_opening_stock(conn, username, date_ad, narration=""):
    """
    Move last year's closing stock into this year's opening stock.

    Debit Opening Stock, credit Stock in Trade, for whatever is sitting in
    Stock in Trade on the day before this date.
    """
    stock_account = _account(conn, STOCK_IN_TRADE, "stock in trade")
    opening_account = _account(conn, OPENING_STOCK, "opening stock")
    import datetime
    previous = (datetime.date.fromisoformat(date_ad) - datetime.timedelta(days=1)).isoformat()
    balance = reports.balances_as_at(conn, previous).get(stock_account["id"], 0)
    if balance == 0:
        raise PeriodEndError("There is nothing in Stock in Trade on %s to carry forward." % previous)
    return ledger.post_voucher(conn, username, {
        "voucher_type": "journal",
        "date_ad": date_ad,
        "narration": narration or ("Opening stock brought forward, %s"
                                   % money.format_money(balance)),
        "entries": [
            {"account_id": opening_account["id"], "dr": money.to_rupees(balance), "cr": 0},
            {"account_id": stock_account["id"], "dr": 0, "cr": money.to_rupees(balance)},
        ],
    })


def depreciation_preview(conn, as_at_ad):
    """
    List the fixed asset ledgers and what is sitting in them, so the amount of
    depreciation can be worked out and entered as a journal.

    The rates and the pooling method under schedule 2 of the Income Tax Act,
    2058 depend on the block an asset belongs to and on how long it was in use
    during the year, so this shows the figures rather than guessing the charge.
    """
    balances = reports.balances_as_at(conn, as_at_ad)
    rows = []
    for account in masters.accounts(conn):
        if account["account_kind"] not in ("fixed_asset", "contra_asset"):
            continue
        balance = balances.get(account["id"], 0)
        if balance == 0:
            continue
        rows.append({
            "account_id": account["id"], "code": account["code"], "name": account["name"],
            "kind": account["account_kind"], "balance": balance,
        })
    return {"as_at_ad": as_at_ad, "rows": rows}


# Settling the value added tax for a month


VAT_OUTPUT = "2241"
VAT_INPUT = "1241"
VAT_NET_PAYABLE = "2242"
VAT_CREDIT_FORWARD = "1242"


def vat_settlement_position(conn, bs_year, bs_month):
    """
    What the settlement entry would do for a Nepali month.

    Output tax and input tax both go on accumulating in their own ledgers until
    somebody closes the month off. Left alone the balance sheet ends up showing
    a large tax asset and a large tax liability side by side when in truth only
    the difference is owed, or only the difference is recoverable.
    """
    position = reports.vat_return(conn, bs_year, bs_month)
    return {
        "bs_year": bs_year, "bs_month": bs_month,
        "month_name": position["month_name"],
        "from_ad": position["from_ad"], "to_ad": position["to_ad"],
        "output_tax": position["output_tax"],
        "input_tax": position["input_tax"],
        "net": position["net"],
        "payable": position["payable"],
        "credit_carried": position["credit_carried"],
        "due_date_bs": position["due_date_bs"],
    }


def post_vat_settlement(conn, username, bs_year, bs_month, narration=""):
    """
    Close a month's value added tax off into what is actually owed.

        debit  VAT Output Payable    the output tax raised in the month
        credit VAT Input Credit      the input tax claimed in the month
        credit VAT Payable, Net      what is left to pay the department

    Where input tax is the larger of the two the balance is a credit to carry
    into the next month, which the Value Added Tax Act, 2052 allows, and it is
    debited to VAT Credit Carried Forward instead.

    The entry is dated the last day of the month it settles, so the month it
    belongs to is the month it appears in.
    """
    position = vat_settlement_position(conn, bs_year, bs_month)
    output_tax = position["output_tax"]
    input_tax = position["input_tax"]
    if not output_tax and not input_tax:
        raise PeriodEndError(
            "There is no value added tax in %s %d to settle." % (position["month_name"], bs_year))

    date_ad = position["to_ad"]
    already = conn.execute(
        """SELECT id FROM vouchers
           WHERE voucher_type = 'journal' AND status = 'posted' AND date_ad = ?
             AND narration LIKE 'Value added tax settled for %'""", (date_ad,)).fetchone()
    if already:
        raise PeriodEndError(
            "The value added tax for %s %d has already been settled. Cancel that voucher "
            "first if it needs doing again." % (position["month_name"], bs_year))

    entries = []
    if output_tax:
        entries.append({"account_id": _account(conn, VAT_OUTPUT, "VAT output")["id"],
                        "dr": money.to_rupees(output_tax), "cr": 0,
                        "narration": "Output tax for the month"})
    if input_tax:
        entries.append({"account_id": _account(conn, VAT_INPUT, "VAT input")["id"],
                        "dr": 0, "cr": money.to_rupees(input_tax),
                        "narration": "Input tax claimed for the month"})
    net = position["net"]
    if net > 0:
        entries.append({"account_id": _account(conn, VAT_NET_PAYABLE, "net VAT payable")["id"],
                        "dr": 0, "cr": money.to_rupees(net),
                        "narration": "Payable to the Inland Revenue Department by %s"
                                     % position["due_date_bs"]})
    elif net < 0:
        entries.append({"account_id": _account(conn, VAT_CREDIT_FORWARD,
                                               "VAT credit carried forward")["id"],
                        "dr": money.to_rupees(-net), "cr": 0,
                        "narration": "Credit carried into the following month"})

    return ledger.post_voucher(conn, username, {
        "voucher_type": "journal",
        "date_ad": date_ad,
        "narration": narration or ("Value added tax settled for %s %d"
                                   % (position["month_name"], bs_year)),
        "entries": entries,
    })

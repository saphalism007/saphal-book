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
from . import ledger, masters, reports

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

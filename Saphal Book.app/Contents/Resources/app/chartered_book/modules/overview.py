"""
What the dashboard is missing: direction, and what needs doing.

A figure on its own says almost nothing. Revenue of six lakh is good or bad
entirely depending on what it was last year, and a business owner reading a
dashboard is asking two questions: is it going the right way, and is there
anything I should be dealing with today.

Three things here, and each one is a figure the books already hold rather than
anything new to enter.

The same period a year ago, so this year has something to be compared with.
The month by month shape of the year, so a bad month shows as a dip rather than
being averaged away. And the handful of things that are actually waiting: money
overdue, tax due, repeating entries not yet posted, stock below its reorder
level.

Nothing here guesses at the future. A forecast on a dashboard is a number
somebody starts believing, and these are books rather than a model.
"""

import datetime

from ..core import money, nepali_date as nd
from . import reports


def compare(conn, from_ad, to_ad):
    """
    This period against the same one a year ago.

    A year back rather than the previous month, because trade is seasonal:
    Dashain against Shrawan tells nobody anything, and Dashain against last
    Dashain tells them everything.
    """
    earlier_from = _year_before(from_ad)
    earlier_to = _year_before(to_ad)
    if not earlier_from or not earlier_to:
        return None

    now = reports.profit_and_loss(conn, from_ad, to_ad)
    then = reports.profit_and_loss(conn, earlier_from, earlier_to)

    # Nothing to compare against is not the same as a fall to nothing, and
    # showing "down 100 per cent" for a first year would be a lie.
    if not (then["revenue"] or then["gross_profit"] or then["profit_after_tax"]):
        return None

    return {
        "from_ad": earlier_from, "to_ad": earlier_to,
        "revenue": _movement(now["revenue"], then["revenue"]),
        "gross_profit": _movement(now["gross_profit"], then["gross_profit"]),
        "profit": _movement(now["profit_after_tax"], then["profit_after_tax"]),
    }


def _movement(now, then):
    change = now - then
    return {
        "now": now, "then": then, "change": change,
        # Basis points, so a percentage never needs a float to survive.
        "change_bp": money.round_half_up(change * 10000, abs(then)) if then else None,
        "direction": "up" if change > 0 else ("down" if change < 0 else "level"),
    }


def _year_before(date_ad):
    """
    The same day one Nepali year earlier.

    Worked out in Bikram Sambat rather than by subtracting three hundred and
    sixty five days, because the Nepali year is not that length and a business
    comparing Shrawan with Shrawan wants the month, not the arithmetic.
    """
    try:
        bs = nd.ad_to_bs(date_ad)
        year, month, day = bs if isinstance(bs, tuple) else (bs["year"], bs["month"], bs["day"])
    except Exception:                                               # noqa: BLE001
        return None
    for attempt in (day, 30, 29, 28):
        try:
            return nd.bs_to_ad(year - 1, month, attempt).isoformat()
        except Exception:                                           # noqa: BLE001
            continue
    return None


def by_month(conn, from_ad, to_ad):
    """
    Revenue and profit for each Nepali month of the year so far.

    The shape matters more than any single figure: a business that made its
    whole year in two months has a different problem from one that made it
    evenly, and an annual total hides which of those it is.
    """
    months = []
    try:
        start = nd.ad_to_bs(from_ad)
        year, month, _day = start if isinstance(start, tuple) else (
            start["year"], start["month"], start["day"])
    except Exception:                                               # noqa: BLE001
        return months

    for _ in range(12):
        try:
            first = nd.bs_to_ad(year, month, 1).isoformat()
        except Exception:                                           # noqa: BLE001
            break
        last = _month_end(year, month)
        if not last or first > to_ad:
            break
        pl = reports.profit_and_loss(conn, first, min(last, to_ad))
        months.append({
            "bs_year": year, "bs_month": month,
            "name": _month_name(month),
            "from_ad": first, "to_ad": min(last, to_ad),
            "revenue": pl["revenue"],
            "profit": pl["profit_after_tax"],
        })
        month += 1
        if month > 12:
            month = 1
            year += 1
    return months


def _month_end(year, month):
    for day in (32, 31, 30, 29):
        try:
            return nd.bs_to_ad(year, month, day).isoformat()
        except Exception:                                           # noqa: BLE001
            continue
    return None


MONTHS = ("Baisakh", "Jestha", "Ashadh", "Shrawan", "Bhadra", "Ashwin",
          "Kartik", "Mangsir", "Poush", "Magh", "Falgun", "Chaitra")


def _month_name(month):
    return MONTHS[month - 1] if 1 <= month <= 12 else str(month)


def attention(conn, to_ad):
    """
    The handful of things actually waiting, each with what it is worth.

    Kept short on purpose. A list of fifteen things is a list nobody reads, and
    the point of putting these on the front screen is that they get dealt with
    rather than admired.
    """
    waiting = []

    # Money owed past its due date. Not merely owed: a bill inside its credit
    # period is business as usual and does not belong on a list of problems.
    overdue = _overdue(conn, "receivable", to_ad)
    if overdue["amount"]:
        waiting.append({
            "kind": "overdue", "severity": "high",
            "title": "%s overdue from customers" % money.format_money(overdue["amount"]),
            "detail": "%d bill%s past its due date. The oldest is %d days."
                      % (overdue["count"], "" if overdue["count"] == 1 else "s",
                         overdue["oldest_days"]),
            "amount": overdue["amount"], "goes_to": "ageing",
        })

    owing = _overdue(conn, "payable", to_ad)
    if owing["amount"]:
        waiting.append({
            "kind": "owing", "severity": "medium",
            "title": "%s overdue to suppliers" % money.format_money(owing["amount"]),
            "detail": "%d bill%s past its due date."
                      % (owing["count"], "" if owing["count"] == 1 else "s"),
            "amount": owing["amount"], "goes_to": "ageing",
        })

    # Repeating entries that have come round and not been posted.
    try:
        from . import recurring
        due = recurring.listing(conn)
        if due["due_total"]:
            waiting.append({
                "kind": "recurring", "severity": "medium",
                "title": "%d repeating entr%s waiting"
                         % (due["due_total"], "y is" if due["due_total"] == 1 else "ies are"),
                "detail": "Rent, salary and the like. They are not in the books "
                          "until they are posted.",
                "amount": 0, "goes_to": "recurring",
            })
    except Exception:                                               # noqa: BLE001
        pass

    # Tax withheld and not yet deposited. Section 90 gives twenty five days
    # after the month end, and a penalty after that.
    try:
        from . import tds
        bs_year, bs_month = nd.today_bs()[0], nd.today_bs()[1]
        last_year, last_month = (bs_year, bs_month - 1) if bs_month > 1 else (bs_year - 1, 12)
        month = tds.monthly(conn, last_year, last_month)
        if month["owing"]:
            waiting.append({
                "kind": "tds", "severity": "high",
                "title": "%s of tax withheld to deposit"
                         % money.format_money(month["owing"]),
                "detail": "For %s. Due by %s under section 90."
                          % (_month_name(last_month),
                             nd.format_bs(nd.ad_to_bs(month["due_ad"]), "long")
                             if month["due_ad"] else "the 25th of this month"),
                "amount": month["owing"], "goes_to": "tds",
            })
    except Exception:                                               # noqa: BLE001
        pass

    return waiting


def _overdue(conn, side, as_at_ad):
    """What is past its due date, how much of it, and how old the oldest is."""
    ageing = reports.ageing(conn, side, as_at_ad)
    amount = 0
    count = 0
    oldest = 0
    for row in ageing.get("rows", []):
        for bill in row.get("details", []):
            if bill.get("amount", 0) <= 0:
                continue
            age = bill.get("age_days", 0) or 0
            credit = row.get("credit_days", 0) or 0
            if age <= credit:
                continue
            amount += bill["amount"]
            count += 1
            oldest = max(oldest, age)
    return {"amount": amount, "count": count, "oldest_days": oldest}

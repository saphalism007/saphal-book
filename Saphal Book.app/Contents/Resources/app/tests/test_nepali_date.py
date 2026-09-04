"""
Accuracy tests for the Bikram Sambat engine.

Run with:  python3 -m tests.test_nepali_date
"""

import datetime
import sys

from chartered_book.core import nepali_date as nd

FAILURES = []


def check(label, got, expected):
    if got != expected:
        FAILURES.append("%s: got %r, expected %r" % (label, got, expected))


def test_reference_anchors():
    """New year day of several BS years against published AD dates."""
    anchors = {
        (2000, 1, 1): "1943-04-14",
        (2050, 1, 1): "1993-04-13",
        (2070, 1, 1): "2013-04-14",
        (2079, 1, 1): "2022-04-14",
        (2080, 1, 1): "2023-04-14",
        (2081, 1, 1): "2024-04-13",
        (2082, 1, 1): "2025-04-14",
        (2083, 1, 1): "2026-04-14",
    }
    for bs, ad in anchors.items():
        check("new year %s" % (bs,), nd.bs_to_ad(*bs).isoformat(), ad)


def test_historical_events():
    """Dates that are independently documented in both calendars."""
    events = {
        (2072, 6, 3): "2015-09-20",   # Constitution of Nepal promulgated
        (2072, 1, 12): "2015-04-25",  # Gorkha earthquake
        (2058, 2, 19): "2001-06-01",  # Narayanhiti incident
        (2065, 2, 15): "2008-05-28",  # Republic declared
        (2007, 11, 7): "1951-02-18",  # Democracy Day, 7 Falgun 2007
        (2076, 9, 11): "2019-12-27",
    }
    for bs, ad in events.items():
        check("event %s" % (bs,), nd.bs_to_ad(*bs).isoformat(), ad)


def test_round_trip_every_day():
    """Convert every supported day both ways and confirm it returns unchanged."""
    day = nd.AD_MIN
    count = 0
    while day <= nd.AD_MAX:
        if nd.bs_to_ad(*nd.ad_to_bs(day)) != day:
            FAILURES.append("round trip broke at %s" % day)
            return
        count += 1
        day += datetime.timedelta(days=1)
    check("round trip day count", count, nd.TOTAL_DAYS)


def test_month_lengths():
    """A BS month is never shorter than 29 or longer than 32 days."""
    for year in range(nd.BS_START_YEAR, nd.BS_END_YEAR + 1):
        months = nd.MONTH_DAYS[year]
        if len(months) != 12:
            FAILURES.append("year %s does not have 12 months" % year)
        for i, length in enumerate(months):
            if not 29 <= length <= 32:
                FAILURES.append("year %s month %s has %s days" % (year, i + 1, length))
        if sum(months) not in (365, 366):
            FAILURES.append("year %s totals %s days" % (year, sum(months)))


def test_fiscal_year():
    """Nepali fiscal year runs 1 Shrawan to the last day of Ashadh."""
    fy = nd.fiscal_year(2082)
    check("fy label", fy["label"], "2082/83")
    check("fy start ad", fy["start_ad"], nd.bs_to_ad(2082, 4, 1).isoformat())
    check("fy end bs month", fy["end_bs"][1], 3)
    # A date in Ashadh belongs to the fiscal year that started the previous Shrawan.
    ashadh = nd.bs_to_ad(2083, 3, 10).isoformat()
    check("ashadh belongs to prior fy", nd.fiscal_year_of(ashadh)["label"], "2082/83")
    # A date in Shrawan starts the new one.
    shrawan = nd.bs_to_ad(2083, 4, 1).isoformat()
    check("shrawan starts new fy", nd.fiscal_year_of(shrawan)["label"], "2083/84")


def test_parsing():
    check("parse dashes", nd.parse_bs("2083-05-17"), (2083, 5, 17))
    check("parse slashes", nd.parse_bs("2083/5/17"), (2083, 5, 17))
    check("parse devanagari", nd.parse_bs("२०८३-०५-१७"), (2083, 5, 17))
    for bad in ("2083-13-01", "2083-05-33", "1999-01-01", "hello", ""):
        try:
            nd.parse_bs(bad)
            FAILURES.append("parse accepted invalid input %r" % bad)
        except nd.DateRangeError:
            pass


def test_boundaries():
    """Conversion must refuse dates outside the table rather than guess."""
    for bad in (datetime.date(1943, 4, 13), datetime.date(2043, 4, 14)):
        try:
            nd.ad_to_bs(bad)
            FAILURES.append("ad_to_bs accepted out of range %s" % bad)
        except nd.DateRangeError:
            pass


def main():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    if FAILURES:
        print("FAILED (%d)" % len(FAILURES))
        for f in FAILURES:
            print("  " + f)
        return 1
    print("All Bikram Sambat tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

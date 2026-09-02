"""
Bikram Sambat calendar engine.

Every date in Chartered Book is stored internally as an AD (Gregorian) date in
ISO form so that sorting, ageing and period comparison stay simple and correct.
The BS date is derived on the way in and on the way out. This module is the
single place where that conversion happens.

Coverage is BS 2000 to BS 2099, which corresponds to AD 1943-04-14 through
AD 2043-04-13. The month length table below is the standard published Nepali
Panchanga data and is verified in tests/test_nepali_date.py against known
historical dates.

No third party packages. Standard library only.
"""

import datetime

BS_START_YEAR = 2000
BS_END_YEAR = 2099

# AD date corresponding to BS 2000-01-01 (1 Baisakh 2000).
REFERENCE_AD = datetime.date(1943, 4, 14)

# Days in each of the twelve months, keyed by BS year.
MONTH_DAYS = {
    2000: (30, 32, 31, 32, 31, 30, 30, 30, 29, 30, 29, 31),  # 365
    2001: (31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30),  # 365
    2002: (31, 31, 32, 32, 31, 30, 30, 29, 30, 29, 30, 30),  # 365
    2003: (31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 31),  # 366
    2004: (30, 32, 31, 32, 31, 30, 30, 30, 29, 30, 29, 31),  # 365
    2005: (31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30),  # 365
    2006: (31, 31, 32, 32, 31, 30, 30, 29, 30, 29, 30, 30),  # 365
    2007: (31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 31),  # 366
    2008: (31, 31, 31, 32, 31, 31, 29, 30, 30, 29, 29, 31),  # 365
    2009: (31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30),  # 365
    2010: (31, 31, 32, 32, 31, 30, 30, 29, 30, 29, 30, 30),  # 365
    2011: (31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 31),  # 366
    2012: (31, 31, 31, 32, 31, 31, 29, 30, 30, 29, 30, 30),  # 365
    2013: (31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30),  # 365
    2014: (31, 31, 32, 32, 31, 30, 30, 29, 30, 29, 30, 30),  # 365
    2015: (31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 31),  # 366
    2016: (31, 31, 31, 32, 31, 31, 29, 30, 30, 29, 30, 30),  # 365
    2017: (31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30),  # 365
    2018: (31, 32, 31, 32, 31, 30, 30, 29, 30, 29, 30, 30),  # 365
    2019: (31, 32, 31, 32, 31, 30, 30, 30, 29, 30, 29, 31),  # 366
    2020: (31, 31, 31, 32, 31, 31, 30, 29, 30, 29, 30, 30),  # 365
    2021: (31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30),  # 365
    2022: (31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 30),  # 365
    2023: (31, 32, 31, 32, 31, 30, 30, 30, 29, 30, 29, 31),  # 366
    2024: (31, 31, 31, 32, 31, 31, 30, 29, 30, 29, 30, 30),  # 365
    2025: (31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30),  # 365
    2026: (31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 31),  # 366
    2027: (30, 32, 31, 32, 31, 30, 30, 30, 29, 30, 29, 31),  # 365
    2028: (31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30),  # 365
    2029: (31, 31, 32, 31, 32, 30, 30, 29, 30, 29, 30, 30),  # 365
    2030: (31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 31),  # 366
    2031: (30, 32, 31, 32, 31, 30, 30, 30, 29, 30, 29, 31),  # 365
    2032: (31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30),  # 365
    2033: (31, 31, 32, 32, 31, 30, 30, 29, 30, 29, 30, 30),  # 365
    2034: (31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 31),  # 366
    2035: (30, 32, 31, 32, 31, 31, 29, 30, 30, 29, 29, 31),  # 365
    2036: (31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30),  # 365
    2037: (31, 31, 32, 32, 31, 30, 30, 29, 30, 29, 30, 30),  # 365
    2038: (31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 31),  # 366
    2039: (31, 31, 31, 32, 31, 31, 29, 30, 30, 29, 30, 30),  # 365
    2040: (31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30),  # 365
    2041: (31, 31, 32, 32, 31, 30, 30, 29, 30, 29, 30, 30),  # 365
    2042: (31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 31),  # 366
    2043: (31, 31, 31, 32, 31, 31, 29, 30, 30, 29, 30, 30),  # 365
    2044: (31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30),  # 365
    2045: (31, 32, 31, 32, 31, 30, 30, 29, 30, 29, 30, 30),  # 365
    2046: (31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 31),  # 366
    2047: (31, 31, 31, 32, 31, 31, 30, 29, 30, 29, 30, 30),  # 365
    2048: (31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30),  # 365
    2049: (31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 30),  # 365
    2050: (31, 32, 31, 32, 31, 30, 30, 30, 29, 30, 29, 31),  # 366
    2051: (31, 31, 31, 32, 31, 31, 30, 29, 30, 29, 30, 30),  # 365
    2052: (31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30),  # 365
    2053: (31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 30),  # 365
    2054: (31, 32, 31, 32, 31, 30, 30, 30, 29, 30, 29, 31),  # 366
    2055: (31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30),  # 365
    2056: (31, 31, 32, 31, 32, 30, 30, 29, 30, 29, 30, 30),  # 365
    2057: (31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 31),  # 366
    2058: (30, 32, 31, 32, 31, 30, 30, 30, 29, 30, 29, 31),  # 365
    2059: (31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30),  # 365
    2060: (31, 31, 32, 32, 31, 30, 30, 29, 30, 29, 30, 30),  # 365
    2061: (31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 31),  # 366
    2062: (30, 32, 31, 32, 31, 31, 29, 30, 29, 30, 29, 31),  # 365
    2063: (31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30),  # 365
    2064: (31, 31, 32, 32, 31, 30, 30, 29, 30, 29, 30, 30),  # 365
    2065: (31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 31),  # 366
    2066: (31, 31, 31, 32, 31, 31, 29, 30, 30, 29, 29, 31),  # 365
    2067: (31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30),  # 365
    2068: (31, 31, 32, 32, 31, 30, 30, 29, 30, 29, 30, 30),  # 365
    2069: (31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 31),  # 366
    2070: (31, 31, 31, 32, 31, 31, 29, 30, 30, 29, 30, 30),  # 365
    2071: (31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30),  # 365
    2072: (31, 32, 31, 32, 31, 30, 30, 29, 30, 29, 30, 30),  # 365
    2073: (31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 31),  # 366
    2074: (31, 31, 31, 32, 31, 31, 30, 29, 30, 29, 30, 30),  # 365
    2075: (31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30),  # 365
    2076: (31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 30),  # 365
    2077: (31, 32, 31, 32, 31, 30, 30, 30, 29, 30, 29, 31),  # 366
    2078: (31, 31, 31, 32, 31, 31, 30, 29, 30, 29, 30, 30),  # 365
    2079: (31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30),  # 365
    2080: (31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 30),  # 365
    2081: (31, 32, 31, 32, 31, 30, 30, 30, 29, 30, 29, 31),  # 366
    2082: (31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30),  # 365
    2083: (31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30),  # 365
    2084: (31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 31),  # 366
    2085: (30, 32, 31, 32, 31, 30, 30, 30, 29, 30, 29, 31),  # 365
    2086: (31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30),  # 365
    2087: (31, 31, 32, 32, 31, 30, 30, 29, 30, 29, 30, 30),  # 365
    2088: (31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 31),  # 366
    2089: (30, 32, 31, 32, 31, 30, 30, 30, 29, 30, 29, 31),  # 365
    2090: (31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30),  # 365
    2091: (31, 31, 32, 32, 31, 30, 30, 29, 30, 29, 30, 30),  # 365
    2092: (31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 31),  # 366
    2093: (31, 31, 31, 32, 31, 31, 29, 30, 30, 29, 29, 31),  # 365
    2094: (31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30),  # 365
    2095: (31, 31, 32, 32, 31, 30, 30, 29, 30, 29, 30, 30),  # 365
    2096: (31, 32, 31, 32, 31, 30, 30, 30, 29, 29, 30, 31),  # 366
    2097: (31, 31, 31, 32, 31, 31, 29, 30, 30, 29, 30, 30),  # 365
    2098: (31, 31, 32, 31, 31, 31, 30, 29, 30, 29, 30, 30),  # 365
    2099: (31, 31, 32, 32, 31, 30, 30, 29, 30, 29, 30, 30),  # 365
}

MONTH_NAMES_EN = (
    "Baisakh", "Jestha", "Ashadh", "Shrawan", "Bhadra", "Ashwin",
    "Kartik", "Mangsir", "Poush", "Magh", "Falgun", "Chaitra",
)

MONTH_NAMES_NP = (
    "बैशाख", "जेठ", "असार", "श्रावण",
    "भाद्र", "आश्विन", "कार्तिक", "मंसिर",
    "पुष", "माघ", "फाल्गुन", "चैत",
)

# Monday is 0 in Python. Nepali weeks start on Sunday.
WEEKDAY_NAMES_EN = ("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")
WEEKDAY_NAMES_NP = (
    "आइतबार", "सोमबार", "मङ्गलबार",
    "बुधबार", "बिहिबार", "शुक्रबार", "शनिबार",
)

DEVANAGARI_DIGITS = "०१२३४५६७८९"


class DateRangeError(ValueError):
    """Raised when a date falls outside the supported BS range."""


def _cumulative_days_to_year(bs_year):
    """Days elapsed from BS 2000-01-01 to the first day of the given BS year."""
    total = 0
    for year in range(BS_START_YEAR, bs_year):
        total += sum(MONTH_DAYS[year])
    return total


# Cache so repeated conversions do not walk the table every time.
_YEAR_OFFSET = {}
_offset = 0
for _y in range(BS_START_YEAR, BS_END_YEAR + 1):
    _YEAR_OFFSET[_y] = _offset
    _offset += sum(MONTH_DAYS[_y])
TOTAL_DAYS = _offset
del _offset, _y

AD_MIN = REFERENCE_AD
AD_MAX = REFERENCE_AD + datetime.timedelta(days=TOTAL_DAYS - 1)


def days_in_bs_month(bs_year, bs_month):
    """Number of days in a given BS month."""
    _check_bs(bs_year, bs_month, 1)
    return MONTH_DAYS[bs_year][bs_month - 1]


def days_in_bs_year(bs_year):
    if bs_year not in MONTH_DAYS:
        raise DateRangeError("BS year %s is outside %s-%s" % (bs_year, BS_START_YEAR, BS_END_YEAR))
    return sum(MONTH_DAYS[bs_year])


def _check_bs(bs_year, bs_month, bs_day):
    if bs_year not in MONTH_DAYS:
        raise DateRangeError("BS year %s is outside the supported range %s to %s"
                             % (bs_year, BS_START_YEAR, BS_END_YEAR))
    if not 1 <= bs_month <= 12:
        raise DateRangeError("BS month must be 1 to 12, got %s" % bs_month)
    limit = MONTH_DAYS[bs_year][bs_month - 1]
    if not 1 <= bs_day <= limit:
        raise DateRangeError("%s %s has %s days, got day %s"
                             % (MONTH_NAMES_EN[bs_month - 1], bs_year, limit, bs_day))


def bs_to_ad(bs_year, bs_month, bs_day):
    """Convert a BS date to a datetime.date in AD."""
    _check_bs(bs_year, bs_month, bs_day)
    elapsed = _YEAR_OFFSET[bs_year] + sum(MONTH_DAYS[bs_year][:bs_month - 1]) + (bs_day - 1)
    return REFERENCE_AD + datetime.timedelta(days=elapsed)


def ad_to_bs(ad_date):
    """Convert a datetime.date (or ISO string) in AD to a (year, month, day) BS tuple."""
    if isinstance(ad_date, str):
        ad_date = datetime.date.fromisoformat(ad_date)
    if isinstance(ad_date, datetime.datetime):
        ad_date = ad_date.date()
    if ad_date < AD_MIN or ad_date > AD_MAX:
        raise DateRangeError("AD date %s is outside the convertible range %s to %s"
                             % (ad_date, AD_MIN, AD_MAX))
    elapsed = (ad_date - REFERENCE_AD).days
    year = BS_START_YEAR
    while elapsed >= sum(MONTH_DAYS[year]):
        elapsed -= sum(MONTH_DAYS[year])
        year += 1
    month = 1
    while elapsed >= MONTH_DAYS[year][month - 1]:
        elapsed -= MONTH_DAYS[year][month - 1]
        month += 1
    return (year, month, elapsed + 1)


def today_bs():
    return ad_to_bs(datetime.date.today())


def to_devanagari(text):
    """Render Arabic numerals inside a string as Devanagari numerals."""
    out = []
    for ch in str(text):
        if ch.isdigit():
            out.append(DEVANAGARI_DIGITS[int(ch)])
        else:
            out.append(ch)
    return "".join(out)


def from_devanagari(text):
    out = []
    for ch in str(text):
        idx = DEVANAGARI_DIGITS.find(ch)
        out.append(str(idx) if idx >= 0 else ch)
    return "".join(out)


def format_bs(bs_tuple, style="numeric", lang="en"):
    """
    Format a BS tuple for display.

    style "numeric"  -> 2082-05-17
    style "long"     -> 17 Bhadra 2082
    style "short"    -> 17 Bha 2082
    """
    year, month, day = bs_tuple
    if lang == "np":
        names = MONTH_NAMES_NP
        if style == "numeric":
            return to_devanagari("%04d-%02d-%02d" % (year, month, day))
        if style == "short":
            return to_devanagari("%d " % day) + names[month - 1] + " " + to_devanagari(year)
        return to_devanagari("%d " % day) + names[month - 1] + " " + to_devanagari(year)
    names = MONTH_NAMES_EN
    if style == "numeric":
        return "%04d-%02d-%02d" % (year, month, day)
    if style == "short":
        return "%d %s %d" % (day, names[month - 1][:3], year)
    return "%d %s %d" % (day, names[month - 1], year)


def parse_bs(text):
    """
    Accept 2082-05-17, 2082/05/17, 2082.5.17 or the Devanagari equivalents.
    Returns a validated (year, month, day) tuple.
    """
    if text is None:
        raise DateRangeError("Empty BS date")
    cleaned = from_devanagari(str(text).strip())
    for sep in ("-", "/", ".", " "):
        cleaned = cleaned.replace(sep, "-")
    parts = [p for p in cleaned.split("-") if p]
    if len(parts) != 3:
        raise DateRangeError("BS date must look like 2082-05-17, got %r" % text)
    try:
        year, month, day = (int(p) for p in parts)
    except ValueError:
        raise DateRangeError("BS date must be numeric, got %r" % text)
    _check_bs(year, month, day)
    return (year, month, day)


def weekday_index(ad_date):
    """0 for Sunday through 6 for Saturday, matching Nepali convention."""
    if isinstance(ad_date, str):
        ad_date = datetime.date.fromisoformat(ad_date)
    return (ad_date.weekday() + 1) % 7


def weekday_name(ad_date, lang="en"):
    idx = weekday_index(ad_date)
    return WEEKDAY_NAMES_NP[idx] if lang == "np" else WEEKDAY_NAMES_EN[idx]


def bs_month_grid(bs_year, bs_month):
    """
    Build the data a month view needs: the leading blank count and each day
    with its AD counterpart. Used by the date picker.
    """
    _check_bs(bs_year, bs_month, 1)
    first_ad = bs_to_ad(bs_year, bs_month, 1)
    count = MONTH_DAYS[bs_year][bs_month - 1]
    return {
        "year": bs_year,
        "month": bs_month,
        "month_name_en": MONTH_NAMES_EN[bs_month - 1],
        "month_name_np": MONTH_NAMES_NP[bs_month - 1],
        "lead_blanks": weekday_index(first_ad),
        "days": [
            {
                "bs_day": d,
                "ad": (first_ad + datetime.timedelta(days=d - 1)).isoformat(),
            }
            for d in range(1, count + 1)
        ],
    }


# Nepali fiscal year runs 1 Shrawan to end of Ashadh.
FY_START_MONTH = 4  # Shrawan
FY_END_MONTH = 3    # Ashadh


def fiscal_year_of(ad_date):
    """
    Return the fiscal year label and its AD boundaries for a given AD date.
    FY 2082/83 starts 1 Shrawan 2082 and ends the last day of Ashadh 2083.
    """
    year, month, _ = ad_to_bs(ad_date)
    start_year = year if month >= FY_START_MONTH else year - 1
    return fiscal_year(start_year)


def fiscal_year(start_bs_year):
    """Boundaries of the fiscal year that begins 1 Shrawan of start_bs_year."""
    end_bs_year = start_bs_year + 1
    start_ad = bs_to_ad(start_bs_year, FY_START_MONTH, 1)
    last_day = MONTH_DAYS[end_bs_year][FY_END_MONTH - 1]
    end_ad = bs_to_ad(end_bs_year, FY_END_MONTH, last_day)
    return {
        "label": "%d/%02d" % (start_bs_year, end_bs_year % 100),
        "start_bs": (start_bs_year, FY_START_MONTH, 1),
        "end_bs": (end_bs_year, FY_END_MONTH, last_day),
        "start_ad": start_ad.isoformat(),
        "end_ad": end_ad.isoformat(),
    }


def bs_month_range(bs_year, bs_month):
    """AD start and end dates of a BS month, useful for VAT return periods."""
    last = days_in_bs_month(bs_year, bs_month)
    return (bs_to_ad(bs_year, bs_month, 1).isoformat(),
            bs_to_ad(bs_year, bs_month, last).isoformat())


def describe(ad_date, lang="en"):
    """A single dictionary holding both calendars, for handing to the UI."""
    if isinstance(ad_date, str):
        ad_date = datetime.date.fromisoformat(ad_date)
    bs = ad_to_bs(ad_date)
    return {
        "ad": ad_date.isoformat(),
        "ad_long": ad_date.strftime("%d %b %Y"),
        "bs": format_bs(bs, "numeric"),
        "bs_long": format_bs(bs, "long", lang),
        "bs_parts": {"year": bs[0], "month": bs[1], "day": bs[2]},
        "weekday": weekday_name(ad_date, lang),
    }

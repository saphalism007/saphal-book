"""
Money handling for Saphal Book.

Every amount in this system is an integer number of paisa. One rupee is one
hundred paisa. Nothing is ever held as a float, because a float cannot hold
0.10 exactly and a trial balance built on floats eventually fails to tie by a
paisa or two. Integer paisa means the books balance to the last paisa forever.

Quantities are a separate matter. Hardware stock is sold in pieces, metres,
kilograms and bundles, so quantity is held as an integer in millis
(three decimal places) for the same reason.

No third party packages. Standard library only.
"""

import decimal
import re

PAISA = 100
QTY_SCALE = 1000  # quantity carries three decimal places

DEVANAGARI_DIGITS = "०१२३४५६७८९"
_DEVA_MAP = {DEVANAGARI_DIGITS[i]: str(i) for i in range(10)}

CURRENCY_SYMBOL = "Rs."
CURRENCY_NAME_EN = "Rupees"
CURRENCY_MINOR_EN = "Paisa"
CURRENCY_NAME_NP = "रुपैयाँ"
CURRENCY_MINOR_NP = "पैसा"


class MoneyError(ValueError):
    """Raised when a value cannot be read as an amount."""


def _strip(text):
    """Normalise a user typed amount into a plain decimal string."""
    s = str(text).strip()
    s = "".join(_DEVA_MAP.get(ch, ch) for ch in s)
    s = s.replace(",", "").replace(" ", "").replace(" ", "")
    s = s.replace("Rs.", "").replace("Rs", "").replace("रु.", "").replace("रु", "")
    s = s.replace("NPR", "").replace("npr", "")
    if s.startswith("(") and s.endswith(")"):  # accounting style negative
        s = "-" + s[1:-1]
    return s


def to_paisa(value):
    """
    Convert a user supplied amount into integer paisa.

    Accepts int, float, Decimal, or a string such as "1,234.5", "(90)" or
    Devanagari digits. Half up rounding is applied at the paisa, which is what
    Nepali practice and the IRD expect.
    """
    if value is None or value == "":
        return 0
    if isinstance(value, int) and not isinstance(value, bool):
        return value * PAISA
    text = _strip(value)
    if text in ("", "-", "+"):
        return 0
    if not re.fullmatch(r"[+-]?\d*\.?\d*", text):
        raise MoneyError("Not a valid amount: %r" % value)
    try:
        d = decimal.Decimal(text)
    except decimal.InvalidOperation:
        raise MoneyError("Not a valid amount: %r" % value)
    return int((d * PAISA).quantize(decimal.Decimal("1"), rounding=decimal.ROUND_HALF_UP))


def to_rupees(paisa):
    """Return a Decimal in rupees. Use only for display or export, never for maths."""
    return (decimal.Decimal(int(paisa)) / PAISA).quantize(decimal.Decimal("0.01"))


def to_qty(value):
    """Convert a quantity into integer thousandths."""
    if value is None or value == "":
        return 0
    text = _strip(value)
    if text in ("", "-", "+"):
        return 0
    try:
        d = decimal.Decimal(text)
    except decimal.InvalidOperation:
        raise MoneyError("Not a valid quantity: %r" % value)
    return int((d * QTY_SCALE).quantize(decimal.Decimal("1"), rounding=decimal.ROUND_HALF_UP))


def qty_value(units):
    return (decimal.Decimal(int(units)) / QTY_SCALE).quantize(decimal.Decimal("0.001"))


def group_nepali(digits):
    """
    Apply Nepali digit grouping: three digits at the end, then pairs.
    1234567 becomes 12,34,567.
    """
    digits = str(digits)
    if len(digits) <= 3:
        return digits
    head, tail = digits[:-3], digits[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts) + "," + tail


def group_western(digits):
    digits = str(digits)
    parts = []
    while len(digits) > 3:
        parts.insert(0, digits[-3:])
        digits = digits[:-3]
    if digits:
        parts.insert(0, digits)
    return ",".join(parts)


def format_money(paisa, grouping="nepali", decimals=2, blank_zero=False,
                 negative="minus", lang="en"):
    """
    Render integer paisa for display.

    grouping  "nepali" gives 12,34,567.00 and "western" gives 1,234,567.00
    negative  "minus" gives -1,200.00 and "bracket" gives (1,200.00)
    """
    paisa = int(paisa)
    if paisa == 0 and blank_zero:
        return ""
    sign = paisa < 0
    whole, minor = divmod(abs(paisa), PAISA)
    grouped = group_nepali(whole) if grouping == "nepali" else group_western(whole)
    if decimals == 0:
        body = grouped
    else:
        body = "%s.%02d" % (grouped, minor)
    if lang == "np":
        body = "".join(DEVANAGARI_DIGITS[int(c)] if c.isdigit() else c for c in body)
    if not sign:
        return body
    return "(%s)" % body if negative == "bracket" else "-" + body


def format_qty(units, lang="en", trim=True):
    """Render a quantity, dropping trailing zeros so 5.000 shows as 5."""
    units = int(units)
    sign = "-" if units < 0 else ""
    whole, frac = divmod(abs(units), QTY_SCALE)
    text = "%s.%03d" % (group_nepali(whole), frac)
    if trim:
        text = text.rstrip("0").rstrip(".")
        if text in ("", "-"):
            text = "0"
    text = sign + text
    if lang == "np":
        text = "".join(DEVANAGARI_DIGITS[int(c)] if c.isdigit() else c for c in text)
    return text


def round_half_up(numerator, denominator):
    """Integer division rounding halves away from zero, as Nepali tax practice does."""
    if denominator == 0:
        raise ZeroDivisionError("denominator is zero")
    sign = -1 if (numerator < 0) != (denominator < 0) else 1
    n, d = abs(numerator), abs(denominator)
    return sign * ((n * 2 + d) // (2 * d))


def apply_rate(base_paisa, rate_basis_points):
    """
    Apply a percentage held in basis points. 13 percent is 1300 basis points,
    1.5 percent is 150. Keeping rates as integers avoids float error on VAT.
    """
    return round_half_up(int(base_paisa) * int(rate_basis_points), 10000)


def rate_to_bp(rate):
    """Convert a percentage such as 13 or 1.5 into basis points."""
    d = decimal.Decimal(_strip(rate) or "0")
    return int((d * 100).quantize(decimal.Decimal("1"), rounding=decimal.ROUND_HALF_UP))


def bp_to_rate(bp):
    return (decimal.Decimal(int(bp)) / 100).normalize()


def extract_from_inclusive(gross_paisa, rate_bp):
    """
    Split a tax inclusive amount into net and tax.
    A gross of 113 at 13 percent gives net 100 and tax 13.
    """
    gross = int(gross_paisa)
    net = round_half_up(gross * 10000, 10000 + int(rate_bp))
    return net, gross - net


def allocate(total_paisa, weights):
    """
    Split an amount across weights without losing or inventing a paisa.
    Used for spreading freight, discount and rounding across invoice lines.
    """
    total = int(total_paisa)
    weights = [int(w) for w in weights]
    weight_sum = sum(weights)
    if weight_sum == 0:
        if not weights:
            return []
        out = [0] * len(weights)
        out[0] = total
        return out
    raw = [total * w for w in weights]
    shares = [r // weight_sum for r in raw]
    remainder = total - sum(shares)
    # Hand the leftover paisa to the lines with the largest fractional part.
    order = sorted(range(len(weights)), key=lambda i: (raw[i] % weight_sum), reverse=True)
    step = 1 if remainder >= 0 else -1
    for i in range(abs(remainder)):
        shares[order[i % len(order)]] += step
    return shares


# Words


_ONES_EN = (
    "Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
    "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
    "Seventeen", "Eighteen", "Nineteen",
)
_TENS_EN = ("", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety")

_NP_NUM = (
    "शून्य", "एक", "दुई", "तीन", "चार", "पाँच", "छ", "सात", "आठ", "नौ",
    "दश", "एघार", "बाह्र", "तेह्र", "चौध", "पन्ध्र", "सोह्र", "सत्र", "अठार", "उन्नाइस",
    "बीस", "एक्काइस", "बाइस", "तेइस", "चौबिस", "पच्चिस", "छब्बिस", "सत्ताइस", "अठ्ठाइस", "उनन्तिस",
    "तीस", "एकतिस", "बत्तिस", "तेत्तिस", "चौँतिस", "पैँतिस", "छत्तिस", "सैँतिस", "अठतिस", "उनन्चालिस",
    "चालिस", "एकचालिस", "बयालिस", "त्रिचालिस", "चवालिस", "पैँतालिस", "छयालिस", "सतचालिस", "अठचालिस", "उनन्चास",
    "पचास", "एकाउन्न", "बाउन्न", "त्रिपन्न", "चवन्न", "पचपन्न", "छपन्न", "सन्ताउन्न", "अन्ठाउन्न", "उनन्साठी",
    "साठी", "एकसट्ठी", "बयसट्ठी", "त्रिसट्ठी", "चौंसट्ठी", "पैंसट्ठी", "छयसट्ठी", "सतसट्ठी", "अठसट्ठी", "उनन्सत्तरी",
    "सत्तरी", "एकहत्तर", "बहत्तर", "त्रिहत्तर", "चौहत्तर", "पचहत्तर", "छयहत्तर", "सतहत्तर", "अठहत्तर", "उनासी",
    "असी", "एकासी", "बयासी", "त्रियासी", "चौरासी", "पचासी", "छयासी", "सतासी", "अठासी", "उनान्नब्बे",
    "नब्बे", "एकानब्बे", "बयानब्बे", "त्रियानब्बे", "चौरानब्बे", "पन्चानब्बे", "छयानब्बे", "सन्तानब्बे", "अन्ठानब्बे", "उनान्सय",
)

# Nepali place values, largest first, with the divisor for each.
_SCALES_EN = ((10 ** 11, "Kharab"), (10 ** 9, "Arab"), (10 ** 7, "Crore"),
              (10 ** 5, "Lakh"), (10 ** 3, "Thousand"), (100, "Hundred"))
_SCALES_NP = ((10 ** 11, "खरब"), (10 ** 9, "अरब"), (10 ** 7, "करोड"),
              (10 ** 5, "लाख"), (10 ** 3, "हजार"), (100, "सय"))


def _two_digit_en(n):
    if n < 20:
        return _ONES_EN[n]
    tens, ones = divmod(n, 10)
    return _TENS_EN[tens] + (" " + _ONES_EN[ones] if ones else "")


def _number_words_en(n):
    if n == 0:
        return "Zero"
    parts = []
    for divisor, name in _SCALES_EN:
        if n >= divisor:
            count, n = divmod(n, divisor)
            parts.append(_two_digit_en(count) if divisor >= 100 and count < 100
                         else _number_words_en(count))
            parts.append(name)
    if n:
        parts.append(_two_digit_en(n))
    return " ".join(p for p in parts if p)


def _number_words_np(n):
    if n == 0:
        return _NP_NUM[0]
    parts = []
    for divisor, name in _SCALES_NP:
        if n >= divisor:
            count, n = divmod(n, divisor)
            parts.append(_NP_NUM[count] if count < 100 else _number_words_np(count))
            parts.append(name)
    if n:
        parts.append(_NP_NUM[n])
    return " ".join(p for p in parts if p)


def amount_in_words(paisa, lang="en", currency=True):
    """
    Spell an amount for the face of an invoice.

    English:  Rupees One Lakh Twenty Three Thousand and Fifty Paisa Only
    Nepali:   रुपैयाँ एक लाख तेइस हजार पचास पैसा मात्र
    """
    paisa = int(paisa)
    negative = paisa < 0
    whole, minor = divmod(abs(paisa), PAISA)
    if lang == "np":
        words = _number_words_np(whole)
        text = (CURRENCY_NAME_NP + " " + words) if currency else words
        if minor:
            text += " " + _NP_NUM[minor] + " " + CURRENCY_MINOR_NP
        text += " मात्र"
        if negative:
            text = "ऋण " + text
        return text
    words = _number_words_en(whole)
    text = (CURRENCY_NAME_EN + " " + words) if currency else words
    if minor:
        text += " and " + _two_digit_en(minor) + " " + CURRENCY_MINOR_EN
    text += " Only"
    if negative:
        text = "Minus " + text
    return text

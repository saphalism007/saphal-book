"""
Reading someone else's trial balance and looking at it.

A practice is handed a trial balance far more often than a set of books. It
arrives as a spreadsheet with a column of names and two columns of figures, and
the first questions are always the same: does it cast, what is each line, does
the shape of it make sense, and what needs asking about.

This takes that spreadsheet, matches each line to the standard chart of
accounts so the statements can be drawn up, and runs the same analytical review
that runs over a set of books kept here.

Nothing is posted. The trial balance is read, mapped and reported on.
"""

import csv
import io
import re

from ..core import coa, money

# Words that give away what a line is, in the order they should be tried.
# Longer and more specific first, so "bank overdraft" is not caught by "bank".
HINTS = [
    ("2220", ["bank overdraft", "overdraft", "cash credit", "cc loan", "od account"]),
    ("1260", ["bank", "nabil", "nic asia", "nabil bank", "current account", "savings account",
              "bank balance", "with bank"]),
    ("1250", ["cash in hand", "cash at hand", "petty cash", "cash balance", "cash"]),
    ("1220", ["sundry debtor", "trade receivable", "accounts receivable", "debtor",
              "receivable", "bills receivable"]),
    ("2210", ["sundry creditor", "trade payable", "accounts payable", "creditor",
              "payable", "bills payable"]),
    ("1210", ["closing stock", "stock in trade", "inventory", "stock", "goods in transit",
              "raw material", "finished goods"]),
    ("1110", ["land", "building", "plant", "machinery", "furniture", "fixture", "vehicle",
              "computer", "equipment", "office equipment", "leasehold"]),
    ("1140", ["goodwill", "software", "trademark", "intangible", "licence", "license"]),
    ("1150", ["investment"]),
    ("1240", ["vat receivable", "input vat", "vat credit", "advance tax", "tds receivable",
              "tax deducted", "advance income tax"]),
    ("1230", ["advance to", "prepaid", "deposit", "security deposit", "staff advance",
              "accrued income"]),
    ("2240", ["vat payable", "output vat", "value added tax", "excise", "health service tax",
              "education service"]),
    ("2250", ["tds payable", "tax deducted at source", "withholding"]),
    ("2260", ["salary payable", "wages payable", "provident fund", "social security",
              "bonus payable", "gratuity payable", "cit payable"]),
    ("2270", ["outstanding", "accrued", "audit fee payable", "rent payable",
              "electricity payable", "interest payable"]),
    ("2280", ["provision"]),
    ("2110", ["term loan", "bank loan", "long term loan", "vehicle loan", "loan from"]),
    ("3100", ["capital", "share capital", "proprietor", "partner capital", "share premium"]),
    ("3200", ["reserve", "retained earning", "surplus", "profit and loss account",
              "accumulated profit"]),
    ("3300", ["drawing"]),
    ("4110", ["sales", "sale of goods", "turnover", "revenue from"]),
    ("4120", ["service income", "fee income", "audit fee income", "consultancy income",
              "professional fee"]),
    ("4130", ["sales return", "return inward", "discount allowed"]),
    ("4200", ["interest income", "commission income", "discount received", "rental income",
              "other income", "misc income", "miscellaneous income", "scrap"]),
    ("5100", ["purchase", "purchases"]),
    ("5200", ["carriage inward", "freight", "custom duty", "clearing", "direct wages",
              "loading", "octroi"]),
    ("5300", ["opening stock"]),
    ("6100", ["salary", "wages", "staff", "bonus", "gratuity", "provident", "employee",
              "festival", "overtime"]),
    ("6200", ["rent", "electricity", "water", "telephone", "internet", "repair",
              "maintenance", "fuel", "printing", "stationery", "postage", "courier",
              "office expense", "insurance", "legal", "audit fee", "consultancy",
              "registration", "renewal", "membership", "subscription", "bank charge",
              "travelling", "conveyance", "entertainment", "donation", "rates and taxes",
              "cleaning", "security", "newspaper", "software", "website"]),
    ("6300", ["advertisement", "publicity", "promotion", "commission on sales",
              "carriage outward", "packing", "bad debt", "warranty", "business promotion"]),
    ("7100", ["interest on", "interest expense", "finance cost", "loan processing",
              "exchange loss"]),
    ("7200", ["depreciation", "amortisation", "amortization"]),
    ("7300", ["loss on sale", "prior period", "penalty", "fine", "written off",
              "rounding", "miscellaneous expense", "sundry expense"]),
    ("8100", ["income tax", "current tax", "deferred tax", "provision for tax"]),
]


class ImportError_(Exception):
    """Raised when a trial balance cannot be read."""


def parse(text):
    """
    Read a trial balance out of pasted text or a comma separated file.

    Accepts commas or tabs, with or without a header row, and copes with the
    two shapes these arrive in: a debit column and a credit column, or a single
    signed amount column.
    """
    if not text or not text.strip():
        raise ImportError_("Nothing was pasted or uploaded.")

    sample = text[:4000]
    delimiter = "\t" if sample.count("\t") > sample.count(",") else ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    raw = [row for row in reader if any((cell or "").strip() for cell in row)]
    if not raw:
        raise ImportError_("The file has no rows in it.")

    header = None
    first = [(cell or "").strip().lower() for cell in raw[0]]
    if any(word in " ".join(first) for word in
           ("debit", "credit", "particular", "account", "amount", "dr", "cr", "ledger")):
        header = first
        raw = raw[1:]
    if not raw:
        raise ImportError_("The file has a heading but no figures under it.")

    name_at, debit_at, credit_at, amount_at, code_at = 0, None, None, None, None
    if header:
        for index, cell in enumerate(header):
            if code_at is None and cell in ("code", "account code", "gl code", "ledger code"):
                code_at = index
            elif ("account" in cell or "particular" in cell or "ledger" in cell
                  or "name" in cell or "description" in cell):
                name_at = index
            elif cell.startswith("debit") or cell == "dr":
                debit_at = index
            elif cell.startswith("credit") or cell == "cr":
                credit_at = index
            elif "amount" in cell or "balance" in cell:
                amount_at = index

    if debit_at is None and credit_at is None and amount_at is None:
        widths = max(len(row) for row in raw)
        if widths >= 3:
            debit_at, credit_at = widths - 2, widths - 1
        elif widths == 2:
            amount_at = 1
        else:
            raise ImportError_("Each row needs a name and at least one figure.")

    lines = []
    problems = []
    for number, row in enumerate(raw, start=1):
        def cell(index):
            if index is None or index >= len(row):
                return ""
            return (row[index] or "").strip()

        name = cell(name_at)
        if not name:
            continue
        if name.lower() in ("total", "totals", "grand total", "sum"):
            continue

        try:
            debit = money.to_paisa(cell(debit_at)) if debit_at is not None else 0
            credit = money.to_paisa(cell(credit_at)) if credit_at is not None else 0
            if amount_at is not None:
                signed = money.to_paisa(cell(amount_at))
                debit, credit = (signed, 0) if signed >= 0 else (0, -signed)
        except money.MoneyError:
            problems.append("Row %d, %s: the figures could not be read." % (number, name))
            continue

        if debit == 0 and credit == 0:
            continue
        # A trial balance sometimes puts a negative in the debit column instead
        # of a figure in the credit column.
        if debit < 0:
            credit, debit = credit - debit, 0
        if credit < 0:
            debit, credit = debit - credit, 0

        lines.append({
            "row": number,
            "code": cell(code_at),
            "name": name,
            "debit": debit,
            "credit": credit,
            "balance": debit - credit,
        })

    if not lines:
        raise ImportError_("No usable rows were found. Each row needs a name and a figure.")

    total_debit = sum(line["debit"] for line in lines)
    total_credit = sum(line["credit"] for line in lines)
    return {
        "lines": lines,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "difference": total_debit - total_credit,
        "balanced": total_debit == total_credit,
        "problems": problems,
        "count": len(lines),
    }


def suggest_mapping(lines):
    """
    Guess what each line is.

    Matched on the words in the name, longest and most specific first. A guess
    is only ever a guess, so each one comes back with how confident it is and
    the whole thing is meant to be looked over before it is used.
    """
    groups = {row[0]: row for row in coa.GROUPS}
    for line in lines:
        name = re.sub(r"[^a-z0-9 ]+", " ", line["name"].lower())
        name = re.sub(r"\s+", " ", name).strip()
        chosen, confidence, matched = None, 0, ""
        for group_code, words in HINTS:
            for word in words:
                if word in name:
                    score = len(word)
                    if score > confidence:
                        chosen, confidence, matched = group_code, score, word
        if chosen is None:
            # Nothing recognised. Put it where its sign suggests and say so.
            chosen = "1280" if line["balance"] > 0 else "2290"
            line["confidence"] = "none"
        else:
            line["confidence"] = "good" if confidence >= 8 else "fair"
        line["group_code"] = chosen
        line["group_name"] = groups[chosen][1] if chosen in groups else chosen
        line["matched_on"] = matched
    return lines


def summarise(lines):
    """Roll a mapped trial balance up into the shape of a set of accounts."""
    groups = {row[0]: row for row in coa.GROUPS}
    sections = {}
    for line in lines:
        group = groups.get(line["group_code"])
        if group is None:
            continue
        _code, name, _np, _parent, nature, statement, section, _sort = group
        bucket = sections.setdefault(section, {
            "section": section, "statement": statement, "total": 0, "lines": []})
        amount = line["balance"]
        if nature in ("liability", "equity", "income"):
            amount = -amount
        bucket["lines"].append(dict(line, presented=amount))
        bucket["total"] += amount

    def total(name):
        return sections.get(name, {}).get("total", 0)

    revenue = total("revenue")
    other_income = total("other_income")
    cost_of_sales = total("cost_of_sales")
    operating = total("employee") + total("administrative") + total("selling")
    finance = total("finance")
    depreciation = total("depreciation")
    other_expense = total("other_expense")
    tax = total("tax")

    gross = revenue - cost_of_sales
    profit_before_tax = gross + other_income - operating - finance - depreciation - other_expense
    profit = profit_before_tax - tax

    assets = total("assets")
    liabilities = total("liabilities")
    equity = total("equity") + profit

    return {
        "sections": sections,
        "revenue": revenue, "other_income": other_income, "cost_of_sales": cost_of_sales,
        "gross_profit": gross, "operating_expense": operating, "finance": finance,
        "depreciation": depreciation, "other_expense": other_expense, "tax": tax,
        "profit_before_tax": profit_before_tax, "profit": profit,
        "total_assets": assets, "total_liabilities": liabilities, "total_equity": equity,
        "difference": assets - (liabilities + equity),
        "balanced": assets == liabilities + equity,
    }

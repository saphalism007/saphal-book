"""
Cash, bank and reconciliation.

A bank reconciliation answers one question: our books say the account holds
this much, the bank statement says something else, and the difference has to be
explained item by item rather than written off.

The working here is the standard one:

    Balance as per our books
      less  deposits we have recorded that the bank has not yet credited
      plus  cheques we have issued that have not yet been presented
      ----
    Balance that the bank statement should show

Nothing is altered in the books by reconciling. Ticking an entry as cleared
only records the date the bank dealt with it.
"""

from ..core import audit, db, money
from . import masters, reports


class BankingError(Exception):
    """Raised when a banking action cannot be carried out."""


CASH_GROUP = "1250"
BANK_GROUP = "1260"
OVERDRAFT_GROUP = "2220"


def accounts(conn, as_at_ad=None, include_inactive=False):
    """Every cash, bank and overdraft ledger with its balance."""
    rows = conn.execute(
        """SELECT a.*, g.code AS group_code, g.name AS group_name
           FROM accounts a JOIN account_groups g ON g.id = a.group_id
           WHERE a.account_kind IN ('cash', 'bank')
           %s
           ORDER BY a.account_kind DESC, a.code""" % ("" if include_inactive else "AND a.active = 1")
    ).fetchall()
    balances = reports.balances_as_at(conn, as_at_ad) if as_at_ad else {}
    out = []
    for row in rows:
        record = dict(row)
        record["balance"] = balances.get(row["id"], row["opening_paisa"])
        record["uncleared"] = uncleared_total(conn, row["id"], as_at_ad) if as_at_ad else 0
        out.append(record)
    return out


def create_account(conn, username, name, kind="bank", **fields):
    """
    Add a bank account, a cash box or an overdraft.

    A bank account goes under Bank Balances, cash under Cash in Hand, and an
    overdraft under Short Term Borrowings because it is money owed, not held.
    """
    if kind not in ("bank", "cash", "overdraft"):
        raise BankingError("Choose bank, cash or overdraft.")
    group_code = {"bank": BANK_GROUP, "cash": CASH_GROUP, "overdraft": OVERDRAFT_GROUP}[kind]
    group = masters.group_by_code(conn, group_code)
    if group is None:
        raise BankingError("The %s group is missing from the chart of accounts." % group_code)
    return masters.create_account(
        conn, username, name, group["id"],
        account_kind="cash" if kind == "cash" else "bank",
        name_np=fields.get("name_np", ""),
        bank_name=fields.get("bank_name", ""),
        bank_account_no=fields.get("bank_account_no", ""),
        bank_branch=fields.get("bank_branch", ""),
        reconcilable=0 if kind == "cash" else 1,
        opening=fields.get("opening") or 0,
        opening_side=fields.get("opening_side", "cr" if kind == "overdraft" else "dr"),
        notes=fields.get("notes", ""))


def entries_for(conn, account_id, upto_ad, only_uncleared=False):
    """Every posting in one cash or bank ledger, with its clearance state."""
    sql = """SELECT e.id AS entry_id, e.dr_paisa, e.cr_paisa, e.narration, e.cleared_ad,
                    e.instrument_no, e.instrument_date_ad,
                    v.id AS voucher_id, v.number, v.date_ad, v.date_bs, v.voucher_type,
                    v.narration AS voucher_narration, v.reference_no,
                    p.name AS party_name,
                    (SELECT GROUP_CONCAT(a2.name, ', ')
                       FROM voucher_entries e2 JOIN accounts a2 ON a2.id = e2.account_id
                      WHERE e2.voucher_id = v.id AND e2.account_id <> ?) AS contra
             FROM voucher_entries e
             JOIN vouchers v ON v.id = e.voucher_id
             LEFT JOIN parties p ON p.id = v.party_id
             WHERE e.account_id = ? AND v.status = 'posted' AND v.date_ad <= ?"""
    args = [account_id, account_id, upto_ad]
    if only_uncleared:
        sql += " AND e.cleared_ad = ''"
    sql += " ORDER BY v.date_ad, v.id, e.line_no"
    return conn.execute(sql, args).fetchall()


def uncleared_total(conn, account_id, upto_ad):
    row = conn.execute(
        """SELECT COALESCE(SUM(e.dr_paisa), 0) AS dr, COALESCE(SUM(e.cr_paisa), 0) AS cr
           FROM voucher_entries e JOIN vouchers v ON v.id = e.voucher_id
           WHERE e.account_id = ? AND v.status = 'posted'
             AND v.date_ad <= ? AND e.cleared_ad = ''""", (account_id, upto_ad)).fetchone()
    return row["dr"] - row["cr"]


def worksheet(conn, account_id, statement_date_ad):
    """
    Everything the reconciliation screen needs.

    Returns the ledger balance, the entries with their clearance state, the two
    lists of items that explain the difference, and the bank balance those
    figures imply.
    """
    account = masters.get_account(conn, account_id)
    if account is None:
        raise BankingError("That account no longer exists.")
    if account["account_kind"] not in ("cash", "bank"):
        raise BankingError("%s is not a cash or bank account." % account["name"])

    balances = reports.balances_as_at(conn, statement_date_ad)
    book_balance = balances.get(account_id, account["opening_paisa"])

    lines = []
    uncleared_dr = uncleared_cr = 0
    for row in entries_for(conn, account_id, statement_date_ad):
        cleared = bool(row["cleared_ad"])
        if not cleared:
            uncleared_dr += row["dr_paisa"]
            uncleared_cr += row["cr_paisa"]
        lines.append({
            "entry_id": row["entry_id"],
            "voucher_id": row["voucher_id"],
            "number": row["number"],
            "voucher_type": row["voucher_type"],
            "date_ad": row["date_ad"],
            "date_bs": row["date_bs"],
            "party_name": row["party_name"] or "",
            "particulars": row["contra"] or row["narration"] or row["voucher_narration"] or "",
            "instrument_no": row["instrument_no"] or row["reference_no"] or "",
            "dr": row["dr_paisa"],
            "cr": row["cr_paisa"],
            "cleared": cleared,
            "cleared_ad": row["cleared_ad"],
        })

    # A debit in our books is money we say came in. Until the bank credits it,
    # the statement is lower than our books by that amount.
    implied_statement = book_balance - uncleared_dr + uncleared_cr

    previous = conn.execute(
        """SELECT * FROM reconciliations WHERE account_id = ? AND statement_date_ad <= ?
           ORDER BY statement_date_ad DESC, id DESC LIMIT 1""",
        (account_id, statement_date_ad)).fetchone()

    return {
        "account": dict(account),
        "statement_date_ad": statement_date_ad,
        "book_balance": book_balance,
        "uncleared_deposits": uncleared_dr,
        "uncleared_payments": uncleared_cr,
        "implied_statement_balance": implied_statement,
        "cleared_count": sum(1 for line in lines if line["cleared"]),
        "uncleared_count": sum(1 for line in lines if not line["cleared"]),
        "lines": lines,
        "last_reconciliation": dict(previous) if previous else None,
    }


def set_cleared(conn, username, entry_ids, cleared_ad, account_id=None):
    """Tick or untick entries. Passing a blank date marks them as not cleared."""
    if not entry_ids:
        return 0
    marks = ", ".join("?" for _ in entry_ids)
    conn.execute("UPDATE voucher_entries SET cleared_ad = ? WHERE id IN (%s)" % marks,
                 [cleared_ad or ""] + list(entry_ids))
    audit.log(conn, username, "bank.clear", "voucher_entries", account_id, "",
              "%d entries marked %s." % (len(entry_ids),
                                         "cleared on " + cleared_ad if cleared_ad else "not cleared"))
    return len(entry_ids)


def save_reconciliation(conn, username, account_id, statement_date_ad,
                        statement_balance, note="", complete=False):
    """Record the reconciliation so the next one can start where this left off."""
    sheet = worksheet(conn, account_id, statement_date_ad)
    statement_balance = money.to_paisa(statement_balance)
    difference = statement_balance - sheet["implied_statement_balance"]
    if complete and difference != 0:
        raise BankingError(
            "The reconciliation is out by %s. Tick the entries the bank has dealt with, "
            "or enter the missing voucher, before marking it complete."
            % money.format_money(abs(difference)))
    now = db.now_stamp()
    from ..core import nepali_date as nd
    cur = conn.execute(
        """INSERT INTO reconciliations (account_id, statement_date_ad, statement_date_bs,
                                        statement_balance, book_balance, difference,
                                        status, note, created_by, created_at, completed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (account_id, statement_date_ad,
         nd.format_bs(nd.ad_to_bs(statement_date_ad), "numeric"),
         statement_balance, sheet["book_balance"], difference,
         "completed" if complete else "open", note, username, now,
         now if complete else ""))
    audit.log(conn, username, "bank.reconcile", "reconciliations", cur.lastrowid,
              sheet["account"]["name"],
              "Reconciled to %s at %s. Difference %s."
              % (statement_date_ad, money.format_money(statement_balance),
                 money.format_money(difference)))
    return cur.lastrowid


def history(conn, account_id=None, limit=50):
    sql = """SELECT r.*, a.name AS account_name FROM reconciliations r
             JOIN accounts a ON a.id = r.account_id"""
    args = []
    if account_id:
        sql += " WHERE r.account_id = ?"
        args.append(account_id)
    sql += " ORDER BY r.statement_date_ad DESC, r.id DESC LIMIT ?"
    args.append(limit)
    return conn.execute(sql, args).fetchall()


def cash_position(conn, as_at_ad):
    """A one line summary for the dashboard and the banking screen."""
    rows = accounts(conn, as_at_ad)
    cash = sum(r["balance"] for r in rows if r["account_kind"] == "cash")
    bank = sum(r["balance"] for r in rows if r["account_kind"] == "bank")
    return {"cash": cash, "bank": bank, "total": cash + bank, "accounts": rows}

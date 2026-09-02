"""
Audit trail.

Every change to the books is written here with who did it, when, and the state
before and after. Nothing in this application deletes a posted voucher outright,
so between this log and the cancelled voucher itself there is always a full
history for an auditor to follow.
"""

import json

from . import db


def _dump(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        if hasattr(value, "keys"):
            value = {k: value[k] for k in value.keys()}
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except (TypeError, ValueError):
        return str(value)


def log(conn, username, action, table_name="", record_id=None,
        reference="", summary="", before=None, after=None):
    conn.execute(
        """INSERT INTO audit_log (at, username, action, table_name, record_id,
                                  reference, summary, before_json, after_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (db.now_stamp(), username or "", action, table_name, record_id,
         reference, summary, _dump(before), _dump(after)))


def recent(conn, limit=200, table_name=None, record_id=None):
    sql = "SELECT * FROM audit_log"
    args = []
    where = []
    if table_name:
        where.append("table_name = ?")
        args.append(table_name)
    if record_id is not None:
        where.append("record_id = ?")
        args.append(record_id)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC LIMIT ?"
    args.append(limit)
    return conn.execute(sql, args).fetchall()

"""
Carrying a set of books from one device to another.

The books on this machine are the real ones. This module makes a copy, locks it,
and leaves it with the server so another device can pick it up. Nothing here is
needed for the shop to trade, and everything goes on working with the network
unplugged.

Two things are done carefully because getting either wrong loses work.

A copy is taken with SQLite's own backup, not by reading the file. A database
being written to has part of its contents sitting in a write ahead log beside
it, so reading the file raw can hand over a half finished picture. The backup
call gives a whole one.

Bringing books down never writes over the live file until the downloaded copy
has been opened, checked and found to be a real set of books. A truncated
download that overwrote the shop's ledger would be the worst thing this software
could do.
"""

import datetime
import os
import shutil
import sqlite3
import tempfile

from ..core import cloud, db


class SyncError(Exception):
    """Raised when books cannot be sent or brought back."""


DEVICE_NAME_KEY = "device_name"


def set_device_name(system, name):
    """Give this device a name a person chose."""
    name = (name or "").strip()[:60]
    system.execute(
        "INSERT INTO app_settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (DEVICE_NAME_KEY, name))
    system.commit()
    return name


def device_name(system=None):
    """
    Something a person will recognise when told which device wrote last.

    Three places to look, in this order.

    A name somebody typed wins, because they know their own devices better than
    any guess. Then whatever the browser was able to say about itself, which is
    how a tablet comes to be called Safari on iPad. Only then the machine's own
    name, which is right on a computer and useless in a browser: inside the
    accounting engine every browser in the world calls itself emscripten, so
    two devices both ended up named the same thing and a person being asked
    which copy to keep was offered the same answer twice.
    """
    import os
    import platform

    if system is not None:
        try:
            row = system.execute("SELECT value FROM app_settings WHERE key = ?",
                                 (DEVICE_NAME_KEY,)).fetchone()
            if row and (row["value"] or "").strip():
                return row["value"].strip()
        except Exception:                                           # noqa: BLE001
            pass

    told = (os.environ.get("SAPHAL_DEVICE") or "").strip()
    if told:
        return told[:60]

    name = ""
    try:
        node = platform.node().strip()
        head = node.split(".")[0]
        # A machine whose name is an address, which happens on a network that
        # hands them out, tells nobody anything. And emscripten is the name the
        # engine gives itself in every browser, so it identifies nothing.
        if node and not node.replace(".", "").isdigit() and head.lower() != "emscripten":
            name = head
    except Exception:                                               # noqa: BLE001
        name = ""

    kind = platform.system()
    if kind == "Darwin":
        kind = "Mac"
    elif kind.lower() == "emscripten":
        kind = ""
    return ("%s, %s" % (name, kind)).strip(", ").strip() or "this device"


def _snapshot(slug):
    """A whole, consistent copy of a set of books, as bytes."""
    path = db.company_db_path(slug)
    if not os.path.exists(path):
        raise SyncError("There are no books called %s on this device." % slug)
    handle, temp = tempfile.mkstemp(suffix=".db")
    os.close(handle)
    try:
        source = sqlite3.connect(path)
        target = sqlite3.connect(temp)
        with target:
            source.backup(target)
        target.close()
        source.close()
        with open(temp, "rb") as reader:
            return reader.read()
    finally:
        for leftover in (temp, temp + "-wal", temp + "-shm"):
            if os.path.exists(leftover):
                os.remove(leftover)


def _looks_like_books(data):
    """
    Open a downloaded copy and satisfy ourselves it is what it claims to be.

    Checked before anything on this machine is touched.
    """
    handle, temp = tempfile.mkstemp(suffix=".db")
    os.close(handle)
    try:
        with open(temp, "wb") as writer:
            writer.write(data)
        conn = None
        try:
            conn = sqlite3.connect(temp)
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                return None, "The copy that came down is damaged."
            names = {row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'")}
            for needed in ("company", "accounts", "vouchers", "voucher_entries"):
                if needed not in names:
                    return None, "The copy that came down is not a set of books."
            row = conn.execute("SELECT name FROM company WHERE id = 1").fetchone()
            return (row[0] if row else ""), ""
        except sqlite3.Error:
            # Not a database at all. Rubbish rather than books, and the reason
            # this check happens before anything on the disk is touched.
            return None, "The copy that came down is not a set of books."
        finally:
            if conn is not None:
                conn.close()
    finally:
        for leftover in (temp, temp + "-wal", temp + "-shm"):
            if os.path.exists(leftover):
                os.remove(leftover)


def _state(system, slug):
    row = system.execute("SELECT * FROM cloud_books WHERE slug = ?", (slug,)).fetchone()
    if row is None:
        return {"slug": slug, "version": 0, "last_sent_at": "", "last_brought_at": "",
                "last_device": ""}
    return dict(row)


def _remember(system, slug, **fields):
    _state(system, slug)
    system.execute("INSERT OR IGNORE INTO cloud_books (slug) VALUES (?)", (slug,))
    for key, value in fields.items():
        system.execute("UPDATE cloud_books SET %s = ? WHERE slug = ?" % key, (value, slug))
    system.commit()


def status(system, session):
    """
    Where every set of books on this device stands against the server.

    One call, so the screen can show the whole picture rather than asking about
    each set of books in turn.
    """
    held = {}
    if session and session.signed_in():
        for row in session.list_books():
            held[row["book_id"]] = row

    out = []
    for company in system.execute(
            "SELECT slug, name FROM companies ORDER BY sort_order, name"):
        slug, name = company["slug"], company["name"]
        state = _state(system, slug)
        entry = {"slug": slug, "name": name, "version": state["version"],
                 "last_sent_at": state["last_sent_at"],
                 "last_brought_at": state["last_brought_at"],
                 "last_device": state["last_device"],
                 "server_version": 0, "server_device": "", "server_updated_at": "",
                 "standing": "not sent yet"}
        if session and session.signed_in():
            fingerprint = cloud.book_fingerprint(session.master_key, slug)
            there = held.pop(fingerprint, None)
            if there:
                entry["server_version"] = there["version"]
                entry["server_device"] = there.get("device", "")
                entry["server_updated_at"] = there.get("updated_at", "")
                if there["version"] == state["version"]:
                    entry["standing"] = "up to date"
                elif there["version"] > state["version"]:
                    entry["standing"] = "newer on the server"
                else:
                    entry["standing"] = "newer here"
            elif state["version"]:
                entry["standing"] = "removed from the server"
        out.append(entry)

    # Books the server carries that this device has never seen. Their names are
    # inside the locked file, so all that can be said is that they are there.
    #
    # What is left in hand at this point is everything the account carries that
    # this device could not account for, and not all of it is books. The Google
    # connection is filed the same way, so it was counted as a set of books
    # waiting, and a device with three companies on the server offered to bring
    # down four. Its fingerprint can be worked out here rather than fetched.
    if session and session.signed_in():
        for name in cloud.RESERVED_SLUGS:
            held.pop(cloud.book_fingerprint(session.master_key, name), None)
    strangers = len(held)
    return {"books": out, "waiting_elsewhere": strangers,
            "device": device_name(system),
            "username": session.username if session and session.signed_in() else ""}


def send_up(system, session, slug, decided=False):
    """
    Put this device's copy on the server.

    Ordinarily the server refuses a send from a device that has fallen behind,
    which is what stops one machine writing over another's day of work. Where
    somebody has been shown both and has said to keep this one, that refusal has
    served its purpose and is stepped past: decided says so, and nothing sets it
    but a person answering that question.
    """
    if not session or not session.signed_in():
        raise SyncError("Sign in to your account first.")
    state = _state(system, slug)
    expected = state["version"]
    if decided:
        expected = session.remote_version(slug)["version"]

    # Where this device believes it has sent these books before but the server
    # is holding nothing, they have been taken off it, by this person on another
    # device or by clearing the account. Refusing to send would leave the books
    # stranded here with no way back up, so the count starts again from nothing.
    if expected and session.remote_version(slug)["version"] == 0:
        expected = 0
        _remember(system, slug, version=0)

    data = _snapshot(slug)
    row = system.execute("SELECT name FROM companies WHERE slug = ?", (slug,)).fetchone()
    version = session.push(slug, data, expected, device=device_name(system),
                           name=row["name"] if row else slug)
    _remember(system, slug, version=version, last_sent_at=db.now_stamp(),
              last_device=device_name(system), last_hash=fingerprint(slug))
    return {"slug": slug, "version": version, "size": len(data)}


def _describe(data):
    """
    What is actually inside a set of books, without touching anything.

    Used when the same books have been changed in two places and somebody has
    to choose between them. Being asked to pick one of two copies with nothing
    to tell them apart is not a question anybody can answer, so this counts what
    is in each and finds the last day anything was entered.
    """
    handle, temp = tempfile.mkstemp(suffix=".db")
    os.close(handle)
    try:
        with open(temp, "wb") as writer:
            writer.write(data)
        conn = None
        try:
            conn = sqlite3.connect(temp)
            row = conn.execute(
                "SELECT COUNT(*) AS n, MAX(date_ad) AS last FROM vouchers "
                "WHERE status != 'cancelled'").fetchone()
            name = conn.execute("SELECT name FROM company WHERE id = 1").fetchone()
            return {"entries": row[0] or 0, "last_entry_ad": row[1] or "",
                    "name": name[0] if name else "", "size": len(data)}
        except sqlite3.Error:
            return {"entries": 0, "last_entry_ad": "", "name": "", "size": len(data)}
        finally:
            if conn is not None:
                conn.close()
    finally:
        for leftover in (temp, temp + "-wal", temp + "-shm"):
            if os.path.exists(leftover):
                os.remove(leftover)


def compare(system, session, slug):
    """
    Put the two copies of one set of books side by side.

    The copy on the server has to be brought down to be counted, because
    everything about it is inside the locked file. Nothing on this device is
    touched: it is fetched, counted, and let go.
    """
    if not session or not session.signed_in():
        raise SyncError("Sign in to your account first.")
    here = _describe(_snapshot(slug))
    here["device"] = device_name(system)

    there = None
    got = session.fetch(slug)
    if got is not None:
        there = _describe(got["data"])
        there["device"] = got.get("device", "")
        there["version"] = got.get("version", 0)
    return {"slug": slug, "here": here, "there": there}


def _install(system, slug, data, version, device):
    """
    Put a downloaded copy in place, once it has been found to be real books.

    The copy being replaced is moved aside rather than deleted, so what was here
    a moment ago still exists on the disk.
    """
    name, complaint = _looks_like_books(data)
    if complaint:
        raise SyncError(complaint + " Nothing on this device has been touched.")

    path = db.company_db_path(slug)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    kept = ""
    if os.path.exists(path):
        kept = "%s.replaced-%s" % (path, stamp)
        shutil.copy2(path, kept)
    for leftover in (path + "-wal", path + "-shm"):
        if os.path.exists(leftover):
            os.remove(leftover)
    with open(path, "wb") as writer:
        writer.write(data)

    system.execute("INSERT OR IGNORE INTO companies (slug, name, created_at) VALUES (?, ?, ?)",
                   (slug, name or slug, db.now_stamp()))
    if name:
        system.execute("UPDATE companies SET name = ? WHERE slug = ?", (name, slug))
    system.commit()
    # Taken from the books now on the disk, not from the bytes that arrived. A
    # snapshot is a rebuild of the database rather than a copy of the file, so
    # the two never match, and storing the wrong one would leave every fetched
    # set of books looking as though it had been edited the instant it landed.
    _remember(system, slug, version=version, last_brought_at=db.now_stamp(),
              last_device=device or "", last_hash=fingerprint(slug))
    return {"slug": slug, "name": name, "version": version, "size": len(data),
            "previous_copy_kept_at": kept}


def bring_new(system, session):
    """
    Fetch every set of books on the server that this device has never seen.

    This is what a fresh tablet needs and what it did not have. Signing in told
    it there was something waiting and then offered nothing to press, because the
    list from the server carries fingerprints and a fingerprint cannot be turned
    back into a name. The name is inside the locked file, so each one is fetched,
    opened, and only then does the device learn what it has.

    Two things it has to survive.

    Not everything the account carries is a set of books. The Google connection
    travels the same way and is filed in the same place, and a tablet that tried
    to open it as books said it was not a set of books and stopped, which is how
    a device with four companies waiting on the server ended up with none. Those
    are recognised and passed over without being fetched at all.

    And one bad row must not cost the rest. Anything that will not open is noted
    and the loop carries on, so three good sets of books arrive even when a
    fourth is unreadable, and the person is told which one it was.
    """
    if not session or not session.signed_in():
        raise SyncError("Sign in to your account first.")
    from ..core import cloud, vault

    mine = {cloud.book_fingerprint(session.master_key, row["slug"])
            for row in system.execute("SELECT slug FROM companies")}
    # Things kept under the account that are not books. Their fingerprints can
    # be worked out here, so they never have to be fetched to be recognised.
    reserved = {cloud.book_fingerprint(session.master_key, name)
                for name in cloud.RESERVED_SLUGS}

    brought, skipped = [], []
    for row in session.list_books():
        book_id = row["book_id"]
        if book_id in mine or book_id in reserved:
            continue
        try:
            got = session.fetch_by_id(book_id)
        except cloud.CloudError as exc:
            skipped.append({"slug": "", "why": str(exc)})
            continue
        except vault.VaultError:
            # Locked with a key this password does not make. That is what a
            # copy left behind by an older password looks like, and it is the
            # ordinary result of somebody changing theirs: the books that
            # matter were sent up again under the new one, and this is the old
            # row nobody can open any more.
            #
            # It has to be stepped over rather than allowed to stop the loop.
            # A row that cannot be opened used to end the whole fetch, which is
            # how a device with four companies waiting ended up with none, and
            # a password change would have walked straight back into it.
            skipped.append({"slug": "", "why": "Locked with an older password. "
                                               "It can be left alone."})
            continue
        if got is None:
            continue
        # An older device may have filed something that is not books without
        # marking it, so the name it comes back with is checked too.
        if cloud.is_reserved(got["slug"]):
            continue
        try:
            brought.append(_install(system, got["slug"], got["data"], got["version"],
                                    got.get("device", "")))
        except SyncError as exc:
            skipped.append({"slug": got["slug"], "why": str(exc)})
    return {"brought": brought, "count": len(brought),
            "skipped": skipped, "skipped_count": len(skipped)}


def bring_down(system, session, slug, expect_name=""):
    """
    Replace this device's copy with the one on the server.

    The live books are moved aside rather than deleted, so a copy taken a moment
    before still exists on the disk if anything goes wrong.
    """
    if not session or not session.signed_in():
        raise SyncError("Sign in to your account first.")
    got = session.fetch(slug)
    if got is None:
        raise SyncError("The server has no books called that under your account.")
    return _install(system, slug, got["data"], got["version"], got.get("device", ""))


# Doing it without being asked


def fingerprint(slug):
    """
    A short summary of a set of books as they stand.

    Taken from a proper snapshot rather than the file, so a write in progress
    cannot make the books look changed when they are not.
    """
    import hashlib
    return hashlib.sha256(_snapshot(slug)).hexdigest()[:32]


def _decide(system, session, slug):
    """
    What, if anything, should happen to one set of books.

    Four answers and no others. Changed here only, send it. Changed there only,
    fetch it. Changed in both places, stop: no rule can merge two days of
    separate entries, and choosing one without asking would throw the other
    away. Changed nowhere, leave it alone.
    """
    state = _state(system, slug)
    if not os.path.exists(db.company_db_path(slug)):
        return "nothing", state
    here = fingerprint(slug)
    there = session.remote_version(slug)["version"]
    agreed = state["version"]

    # Nothing has ever been sent.
    if agreed == 0 and there == 0:
        return "send", state

    # Sent once, but no longer on the server. Somebody cleared it, and the books
    # here are all there is. Put them back rather than leaving them stranded.
    if there == 0:
        return "send", state

    # Books synced before this device kept a fingerprint, which is every set of
    # books that existed when this was added. Nothing can be said about whether
    # they changed since. Where the server is still where it was left, the
    # sensible reading is that nothing has happened: take the books as they
    # stand now as the point the two agree from. Where it has moved, there is a
    # real question and it gets asked.
    if not state["last_hash"]:
        if there == agreed:
            _remember(system, slug, last_hash=here)
            return "nothing", state
        return "conflict", state

    changed_here = here != state["last_hash"]
    changed_there = there != agreed

    if changed_here and changed_there:
        return "conflict", state
    if changed_here:
        return "send", state
    if changed_there:
        return "fetch", state
    return "nothing", state


def auto(system, session):
    """
    Keep every set of books level with the server, without being asked.

    Run when somebody signs in, every so often afterwards, and once the dust has
    settled after something is entered. It never overwrites work: where both
    sides have moved it does nothing and says so, and the two buttons are still
    there for whoever has to decide.
    """
    if not session or not session.signed_in():
        return {"ran": False, "why": "not signed in"}

    from ..core import cloud
    sent, fetched, conflicts = [], [], []

    try:
        new_ones = bring_new(system, session)
        fetched.extend(book["name"] or book["slug"] for book in new_ones["brought"])
    except Exception as exc:                                        # noqa: BLE001
        conflicts.append({"name": "books waiting on the server", "why": str(exc)})

    for row in system.execute("SELECT slug, name FROM companies ORDER BY id").fetchall():
        slug, name = row["slug"], row["name"]
        try:
            what, _ = _decide(system, session, slug)
            if what == "send":
                send_up(system, session, slug)
                sent.append(name)
            elif what == "fetch":
                bring_down(system, session, slug)
                fetched.append(name)
            elif what == "conflict":
                held = session.remote_version(slug)
                conflicts.append({
                    "slug": slug, "name": name,
                    "why": "Entries have been made here and on %s since these last agreed. "
                           "Decide which copy to keep."
                           % (held.get("device") or "another device")})
        except cloud.Conflict as exc:
            conflicts.append({"slug": slug, "name": name, "why": str(exc)})
        except (cloud.CloudError, SyncError) as exc:
            conflicts.append({"slug": slug, "name": name, "why": str(exc)})

    return {"ran": True, "sent": sent, "fetched": fetched, "conflicts": conflicts,
            "quiet": not sent and not fetched and not conflicts}

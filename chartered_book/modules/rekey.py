"""
Moving an account, and everything on it, to a new password.

A password here is two things at once. Half of it signs in to the account, and
the other half is the key that every copy on the server is locked with. Both
come out of the one thing somebody types.

For a long time changing a password changed it on the device in front of you
and nowhere else. The account went on answering to the old one, the copies on
it stayed locked with the old key, and the next device to sign in with the new
password was told there was no such account. That is not a changed password,
it is a second password, and it is how somebody ends up locked out of their
own books by doing the sensible thing.

So this moves the lot, in an order chosen so that stopping at any point leaves
something that still works:

  1. Every copy on the account is unlocked with the old key and filed again
     under the new one, beside the old copy and at the same version. Nothing
     is removed yet. If this stops half way, the new copies are taken back off
     and nothing has changed.
  2. The account is told the new password. If it refuses, the new copies are
     taken back off and nothing has changed.
  3. Only then are the old copies removed. If that stops half way, what is
     left behind is a copy nobody can open, which is stepped over by name when
     books are brought down.

The copies are moved as they stand on the server, not sent afresh from this
device. That matters: another device may have sent something newer than this
one holds, and sending from here would flatten it. Versions are carried across
untouched for the same reason, so every device's idea of where it stands is
still true afterwards.

What cannot be opened with the old key is left exactly where it is.
"""

from ..core import cloud, vault


class RekeyError(Exception):
    pass


def move(session, username, new_password, fresh_session=None):
    """
    Take a signed in account from the key it has to the one the new password
    makes. Returns what was done. Raises RekeyError, having put things back,
    where it could not be done.

    fresh_session, where given, makes an unsigned connection, used to sign in
    again afterwards so the tickets in hand are ones issued under the new
    password.
    """
    if not session or not session.signed_in():
        raise RekeyError("Not signed in to the account.")

    new_secret, new_master = cloud._split_password(username, new_password)
    if new_master == session.master_key:
        return {"moved": 0, "left": 0, "same": True, "session": session}

    old_key = session.master_key.hex()
    new_key = new_master.hex()
    moved = []
    left = 0

    def take_back():
        for _old_id, new_id in moved:
            try:
                session.forget_by_id(new_id)
            except Exception:                                       # noqa: BLE001
                pass

    try:
        for row in session.list_books():
            raw = session.fetch_raw(row["book_id"])
            if raw is None:
                continue
            try:
                plain = vault.unlock(raw["blob"], old_key)
            except vault.VaultError:
                # Left behind by a password before this one. Nobody holds the
                # key to it any more and moving it is not possible.
                left += 1
                continue
            slug = cloud._unwrap(plain)["slug"]
            if not slug:
                left += 1
                continue
            new_id = cloud.book_fingerprint(new_master, slug)
            session.put_raw(new_id, vault.lock(plain, new_key),
                            raw["version"], raw["device"])
            moved.append((row["book_id"], new_id))

        session.change_sign_in(new_secret)
    except Exception as exc:                                        # noqa: BLE001
        take_back()
        raise RekeyError(str(exc) or "The account could not be moved.")

    # From here the account answers to the new password, and the new copies
    # are the real ones.
    session.master_key = new_master
    holding = session
    if fresh_session is not None:
        try:
            again = fresh_session()
            again.sign_in(username, new_password)
            holding = again
        except Exception:                                           # noqa: BLE001
            holding = session

    stranded = 0
    for old_id, new_id in moved:
        if old_id == new_id:
            continue
        try:
            holding.forget_by_id(old_id)
        except Exception:                                           # noqa: BLE001
            stranded += 1

    return {"moved": len(moved), "left": left + stranded, "same": False,
            "session": holding}

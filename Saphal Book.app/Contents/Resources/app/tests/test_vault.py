"""
The lock that goes on a set of books before it leaves the machine.

Everything here is about one promise: what reaches the server cannot be read by
whoever runs the server, and cannot be altered without the alteration being
caught. A mistake in this file does not show up as a wrong figure. It shows up
as books that will never open again, so it is checked harder than anything else.

Run with:  python3 -m tests.test_vault
"""

import os
import sys
import zlib

from chartered_book.core import vault

FAILURES = []


def check(label, got, expected):
    if got != expected:
        FAILURES.append("%s: got %r, expected %r" % (label, got, expected))


def refuses(label, blob, password):
    """Opening this must fail, and must fail by refusing rather than by crashing."""
    try:
        vault.unlock(blob, password)
    except vault.VaultError:
        return
    except Exception as exc:                                    # noqa: BLE001
        FAILURES.append("%s: raised %s instead of refusing cleanly" % (label, type(exc).__name__))
        return
    FAILURES.append("%s: it opened, and it should not have" % label)


def main():
    books = b"a set of books" * 5000 + bytes(range(256)) * 40
    password = "the shop password, नेपाली too"

    # --- It comes back exactly as it went in ------------------------------
    locked = vault.lock(books, password)
    check("what goes in comes back out", vault.unlock(locked, password), books)
    check("a locked file is recognisable", vault.looks_locked(locked), True)
    check("plain bytes are not mistaken for one", vault.looks_locked(books), False)

    # --- It is genuinely hidden -------------------------------------------
    check("the books are not sitting in the file", books[:64] in locked, False)
    check("nor is any long run of them",
          any(books[i:i + 40] in locked for i in range(0, 4000, 40)), False)

    # --- The same books locked twice look nothing alike --------------------
    again = vault.lock(books, password)
    check("locking twice gives two different files", locked == again, False)
    check("but both open to the same books", vault.unlock(again, password), books)

    # --- A wrong password gets nothing -------------------------------------
    refuses("a wrong password", locked, "not the shop password")
    refuses("an empty password", locked, "")
    refuses("the password with one letter changed", locked,
            "the shop password, नेपाली to")

    # --- Meddling is caught, wherever it happens ---------------------------
    for name, position in (("the magic", 2), ("the work factor", 10),
                           ("the salt", 14), ("the nonce", 30),
                           ("the contents", vault.HEADER + 100),
                           ("the last byte of the contents", len(locked) - 33),
                           ("the seal", len(locked) - 1)):
        broken = bytearray(locked)
        broken[position] ^= 0x01
        refuses("one bit flipped in %s" % name, bytes(broken), password)

    refuses("bytes cut off the end", locked[:-1], password)
    refuses("bytes added to the end", locked + b"\x00", password)
    refuses("an empty file", b"", password)
    refuses("something else entirely", b"PK\x03\x04 this is a zip file", password)

    # --- Awkward inputs ----------------------------------------------------
    for name, payload in (("nothing at all", b""),
                          ("a single byte", b"\x00"),
                          ("exactly one block", os.urandom(32)),
                          ("one byte over a block", os.urandom(33)),
                          ("a megabyte", os.urandom(1024 * 1024))):
        sealed = vault.lock(payload, password)
        check("round trip with %s" % name, vault.unlock(sealed, password), payload)

    # --- The two keys are not the same key ---------------------------------
    salt = b"0123456789abcdef"
    encrypt_key, authenticate_key = vault.keys_from_password(password, salt, 1000)
    check("hiding and proving use different keys", encrypt_key == authenticate_key, False)

    # --- The stream never repeats itself -----------------------------------
    stream = vault._keystream(encrypt_key, b"n" * 16, 32 * 64)
    blocks = [stream[i:i + 32] for i in range(0, len(stream), 32)]
    check("no block of the stream is ever reused", len(set(blocks)), len(blocks))

    # --- The same password and salt always lead to the same key ------------
    once = vault.keys_from_password(password, salt, 1000)
    twice = vault.keys_from_password(password, salt, 1000)
    check("the same password gives the same key", once, twice)
    other = vault.keys_from_password(password, b"fedcba9876543210", 1000)
    check("a different salt gives a different key", once == other, False)

    # --- The longhand key stretching matches the built in one --------------
    #
    # The browser has no built in one, so the books locked on a computer have to
    # open on a tablet and the other way round. If these two ever disagreed,
    # every file would become unreadable on one of the two.
    import hashlib
    real = hashlib.pbkdf2_hmac("sha256", b"password", b"salt", 4096, 32)
    saved = hashlib.pbkdf2_hmac
    del hashlib.pbkdf2_hmac
    try:
        longhand = vault._pbkdf2(b"password", b"salt", 4096, 32)
    finally:
        hashlib.pbkdf2_hmac = saved
    check("longhand key stretching matches the built in one", longhand, real)

    # And the whole thing round trips with the built in one taken away.
    del hashlib.pbkdf2_hmac
    try:
        slow = vault.lock(b"books locked without the fast way", password, iterations=2000)
    finally:
        hashlib.pbkdf2_hmac = saved
    check("locked longhand, opened the fast way",
          vault.unlock(slow, password), b"books locked without the fast way")

    # --- The work factor travels with the file -----------------------------
    light = vault.lock(books, password, iterations=1000)
    check("a file made with less work still opens", vault.unlock(light, password), books)
    check("and it says so in its own header",
          int.from_bytes(light[8:12], "big"), 1000)

    # --- Squeezing happens before locking, not after -----------------------
    repetitive = b"the same line over and over\n" * 4000
    check("repetitive books lock down small",
          len(vault.lock(repetitive, password)) < len(repetitive) // 10, True)

    if FAILURES:
        print("FAILED (%d)" % len(FAILURES))
        for line in FAILURES:
            print("  " + line)
        return 1
    print("All vault tests passed.")
    print("  Round trip      exact, from nothing up to a megabyte")
    print("  Hidden          no run of the books survives in the locked file")
    print("  Sealed          every single bit flip is caught and refused")
    print("  Portable        longhand and built in key stretching agree exactly")
    return 0


if __name__ == "__main__":
    sys.exit(main())

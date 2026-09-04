"""
Locking a set of books so that only the person with the password can read them.

Why this exists. Books are about to be copied to a server so they can reach a
phone and a tablet. That server belongs to somebody else. A chartered accountant
holding client books has no business handing them to a third party in a form
that party can read, so nothing leaves this machine until it has been locked,
and the key never leaves at all.

Why it is written out longhand. Python ships no cipher. There is no AES in the
standard library and no package may be installed, so the parts that do exist
have to be assembled into something sound:

    Turning a password into a key   PBKDF2 with HMAC SHA256, many times over,
                                    so guessing passwords is slow work.
    Hiding the contents             HMAC SHA256 run as a counter, which gives
                                    an endless stream of unpredictable bytes to
                                    exclusive-or the books against. This is the
                                    same idea as the expand half of HKDF.
    Proving nothing was altered     A second HMAC over the locked bytes, made
                                    with a different key and checked before a
                                    single byte is unlocked.

Two rules are followed because breaking either of them breaks everything:

    The key that hides and the key that proves are never the same key. They are
    two separate children of the master key.

    A nonce is never used twice with the same key. A fresh random one goes into
    every locked file, which is why locking the same books twice gives two
    different files.

The password is never stored, never sent and never recoverable. That is the
point of it, and it is also the danger: lose the password and the books inside
are gone for good. Nothing here can be made to give them back.
"""

import hashlib
import hmac
import os
import struct
import zlib

MAGIC = b"SBVAULT\x01"
SALT_BYTES = 16
NONCE_BYTES = 16
TAG_BYTES = 32
KEY_BYTES = 32
HEADER = len(MAGIC) + 4 + SALT_BYTES + NONCE_BYTES

# Measured rather than guessed. On this machine the longhand version, which is
# what runs when the books are opened inside a browser, takes about half a
# second at this count, and the fast version is instant. Slow enough to make
# guessing expensive, quick enough that nobody notices at sign in.
ITERATIONS = 200000

ENCRYPT_LABEL = b"saphal book vault, encryption key, version 1"
AUTHENTICATE_LABEL = b"saphal book vault, authentication key, version 1"


class VaultError(Exception):
    """Raised when a locked file cannot be opened."""


def _pbkdf2(password_bytes, salt, iterations, length=KEY_BYTES):
    """
    Stretch a password into a key.

    The built in version is used where there is one. Inside a browser there is
    not, so the same algorithm is written out by hand. The two were checked
    against each other byte for byte.
    """
    if hasattr(hashlib, "pbkdf2_hmac"):
        return hashlib.pbkdf2_hmac("sha256", password_bytes, salt, iterations, length)

    out = b""
    block = 1
    while len(out) < length:
        current = hmac.new(password_bytes, salt + struct.pack(">I", block),
                           hashlib.sha256).digest()
        result = bytearray(current)
        for _ in range(iterations - 1):
            current = hmac.new(password_bytes, current, hashlib.sha256).digest()
            for index in range(len(result)):
                result[index] ^= current[index]
        out += bytes(result)
        block += 1
    return out[:length]


def _subkey(master, label):
    """One child key of the master, for one purpose and no other."""
    return hmac.new(master, label, hashlib.sha256).digest()


def _keystream(key, nonce, length):
    """
    An unpredictable stream of bytes, as long as the books being hidden.

    Block n is the HMAC of the nonce and n, so no two blocks repeat and none of
    them can be worked out without the key.
    """
    out = bytearray()
    counter = 0
    while len(out) < length:
        out += hmac.new(key, nonce + struct.pack(">Q", counter), hashlib.sha256).digest()
        counter += 1
    return bytes(out[:length])


def _xor(data, stream):
    return bytes(a ^ b for a, b in zip(data, stream))


def keys_from_password(password, salt, iterations=ITERATIONS):
    """The pair of keys a password and salt lead to."""
    if isinstance(password, str):
        password = password.encode("utf-8")
    master = _pbkdf2(password, salt, iterations)
    return _subkey(master, ENCRYPT_LABEL), _subkey(master, AUTHENTICATE_LABEL)


def lock(plaintext, password, iterations=ITERATIONS, salt=None, nonce=None):
    """
    Lock a set of books.

    The books are squeezed first, because a database file is mostly repetition
    and there is no sense hiding, sending and storing bytes that need not be
    there. Squeezing before locking and not after is deliberate: locked bytes
    look random and will not squeeze at all.
    """
    if isinstance(plaintext, str):
        plaintext = plaintext.encode("utf-8")
    salt = salt or os.urandom(SALT_BYTES)
    nonce = nonce or os.urandom(NONCE_BYTES)
    if len(salt) != SALT_BYTES or len(nonce) != NONCE_BYTES:
        raise VaultError("The salt and the nonce are of a fixed size.")

    body = zlib.compress(plaintext, 6)
    encrypt_key, authenticate_key = keys_from_password(password, salt, iterations)
    hidden = _xor(body, _keystream(encrypt_key, nonce, len(body)))

    header = MAGIC + struct.pack(">I", iterations) + salt + nonce
    tag = hmac.new(authenticate_key, header + hidden, hashlib.sha256).digest()
    return header + hidden + tag


def unlock(blob, password):
    """
    Open a locked set of books.

    Nothing is unscrambled until the seal has been checked. Checking first means
    a file that somebody has altered, whether by meddling or by a bad transfer,
    is refused outright rather than quietly turning into wrong figures.
    """
    if not isinstance(blob, (bytes, bytearray)):
        raise VaultError("A locked file is a run of bytes.")
    blob = bytes(blob)
    if len(blob) < HEADER + TAG_BYTES or not blob.startswith(MAGIC):
        raise VaultError("That is not a Saphal Book locked file.")

    iterations = struct.unpack(">I", blob[8:12])[0]
    if not 1 <= iterations <= 5000000:
        raise VaultError("That locked file states an impossible amount of work.")
    salt = blob[12:12 + SALT_BYTES]
    nonce = blob[12 + SALT_BYTES:HEADER]
    hidden = blob[HEADER:-TAG_BYTES]
    tag = blob[-TAG_BYTES:]

    encrypt_key, authenticate_key = keys_from_password(password, salt, iterations)
    expected = hmac.new(authenticate_key, blob[:HEADER] + hidden, hashlib.sha256).digest()
    if not hmac.compare_digest(expected, tag):
        raise VaultError(
            "The password is wrong, or this file has been altered since it was locked. "
            "Nothing has been read from it.")

    body = _xor(hidden, _keystream(encrypt_key, nonce, len(hidden)))
    try:
        return zlib.decompress(body)
    except zlib.error:
        raise VaultError("The seal matched but the contents would not unpack.")


def looks_locked(blob):
    """Whether a run of bytes is one of ours, without needing the password."""
    return isinstance(blob, (bytes, bytearray)) and bytes(blob[:len(MAGIC)]) == MAGIC

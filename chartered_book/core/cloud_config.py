"""
Where the server is, and the key that identifies the application to it.

Both of these are meant to be public. The key below is the one Supabase calls
anon, and it grants nothing on its own: every table refuses it, and the rules on
the server only open up once somebody has signed in, and then only to that
person's own rows. It is the equivalent of the address on a shop front.

The key that matters is the one made from the password, which is worked out on
the device, never sent, and never written down anywhere including here.

Either can be overridden by the owner, in case the books are ever moved to a
different project. Whatever is in the settings table wins.
"""

DEFAULT_URL = "https://oswbrodmrwprdydxvtmx.supabase.co"
DEFAULT_ANON_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9zd2Jyb2RtcndwcmR5ZHh2dG14Iiwicm9sZSI6ImFub24iLCJp"
    "YXQiOjE3ODg1MTcwODksImV4cCI6MjEwNDA5MzA4OX0"
    ".MOY7Ipgd5tf8tmL1kaJCE5qcZ59Lw9jY2pMoocrlXqE")


def settings(system):
    """The address and key these books should use."""
    held = {row["key"]: row["value"] for row in system.execute(
        "SELECT key, value FROM app_settings WHERE key IN ('cloud_url', 'cloud_key')")}
    return {"url": held.get("cloud_url") or DEFAULT_URL,
            "anon_key": held.get("cloud_key") or DEFAULT_ANON_KEY}


def configured(system):
    found = settings(system)
    return bool(found["url"] and found["anon_key"])

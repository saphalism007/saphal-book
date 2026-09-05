#!/usr/bin/env python3
"""
Carry this machine's Google connection up to the owner's account.

Run once, after connecting a Drive:

    python3 tools/link_google_to_account.py

Afterwards, signing in as the same person on any other device reaches the same
Drive, with none of Google's consent screens again.
"""

import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chartered_book.core import backup, cloud, cloud_config, db     # noqa: E402


def main():
    system = db.open_system()
    if backup.google_settings(system) is None:
        print("No Google Drive is connected on this machine yet.")
        print("Run tools/connect_google_drive.py first.")
        return 1

    row = system.execute("SELECT username FROM cloud_account WHERE id = 1").fetchone()
    username = (row["username"] if row else "") or input("Your Saphal Book username: ").strip()
    if not username:
        print("A username is needed.")
        return 1

    print("Signing in as %s" % username)
    password = getpass.getpass("  Password: ")
    if not password:
        print("Nothing done.")
        return 1

    settings = cloud_config.settings(system)
    session = cloud.Cloud(settings["url"], settings["anon_key"])
    try:
        session.sign_in(username, password)
    except cloud.CloudError as exc:
        print("  %s" % exc)
        return 1

    who = backup.publish_google_link(system, session)
    print()
    print("Done. Any device signing in as %s now backs up to %s." % (username, who))
    print("The connection is locked with your password before it goes, so the server")
    print("holds something it cannot read.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

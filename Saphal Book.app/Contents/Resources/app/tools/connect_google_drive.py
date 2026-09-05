#!/usr/bin/env python3
"""
Ask Google once for lasting permission to put backups in Drive.

Run this by hand, the one time:

    python3 tools/connect_google_drive.py

It opens the browser, waits for the owner to say yes, and writes the permission
into the settings. Nothing else needs doing afterwards; backups go up on their
own from then on.
"""

import http.server
import os
import sys
import threading
import urllib.parse
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chartered_book.core import db, gdrive          # noqa: E402

# The two strings Google gives when an OAuth client is made. They are asked for
# rather than written down here, because anything written into a file in this
# folder ends up published, and one person's Google project should not be baked
# into everybody's copy of the software. Once given they are kept in the
# settings on this machine, which never leaves it.
def _credentials():
    system = db.open_system()
    held = {row["key"]: row["value"] for row in system.execute(
        "SELECT key, value FROM app_settings WHERE key LIKE 'gdrive_client%'")}
    client_id = held.get("gdrive_client_id") or os.environ.get("GDRIVE_CLIENT_ID", "")
    secret = held.get("gdrive_client_secret") or os.environ.get("GDRIVE_CLIENT_SECRET", "")
    if not client_id:
        print("Paste the Client ID from the Google Cloud console")
        print("  (it ends in .apps.googleusercontent.com)")
        client_id = input("  Client ID: ").strip()
    if not secret:
        print("Paste the Client secret (it starts with GOCSPX-)")
        secret = input("  Client secret: ").strip()
    if not client_id or not secret:
        print("\nBoth are needed. Nothing has been changed.")
        raise SystemExit(1)
    return client_id, secret

caught = {}


class Catcher(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        bits = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(bits.query)
        caught["code"] = (query.get("code") or [""])[0]
        caught["error"] = (query.get("error") or [""])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        if caught["code"]:
            message = ("<h2>Saphal Book is connected to Google Drive.</h2>"
                       "<p>You can close this tab and go back.</p>")
        else:
            message = ("<h2>Not connected.</h2><p>Google said: %s</p>"
                       % (caught["error"] or "nothing"))
        self.wfile.write(("<div style='font:16px -apple-system,system-ui,sans-serif;"
                          "padding:3rem;text-align:center;color:#243'>%s</div>"
                          % message).encode("utf-8"))

    def log_message(self, *_ignored):
        pass


def main():
    CLIENT_ID, CLIENT_SECRET = _credentials()
    server = http.server.HTTPServer(("127.0.0.1", 0), Catcher)
    port = server.server_address[1]
    redirect = "http://127.0.0.1:%d/" % port

    url = gdrive.consent_url(CLIENT_ID, redirect)
    print("Open this in your browser if it does not open by itself:\n")
    print(url)
    print()
    threading.Thread(target=lambda: webbrowser.open(url), daemon=True).start()

    print("Waiting for you to press Allow...")
    server.timeout = 300
    while "code" not in caught and "error" not in caught:
        server.handle_request()
    server.server_close()

    if not caught.get("code"):
        print("\nNot connected. Google said: %s" % (caught.get("error") or "nothing"))
        return 1

    tokens = gdrive.exchange_code(CLIENT_ID, CLIENT_SECRET, caught["code"], redirect)
    system = db.open_system()
    for key, value in (("gdrive_client_id", CLIENT_ID),
                       ("gdrive_client_secret", CLIENT_SECRET),
                       ("gdrive_refresh_token", tokens["refresh_token"])):
        system.execute(
            "INSERT INTO app_settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))
    system.commit()
    print("\nConnected. Saphal Book can now put backups into your Drive.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

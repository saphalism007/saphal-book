#!/usr/bin/env python3
"""
Start Saphal Book.

Double click run.command on a Mac, or run.bat on Windows. Either one runs this
file, which starts the local server and opens the browser at it.

By default the server listens only on this computer. Pass --lan and it also
answers to other machines on the same wifi, which is how a phone or a tablet
reaches the books. Nothing ever leaves your own network either way.
"""

import argparse
import datetime
import json
import os
import signal
import socket
import sys
import threading
import urllib.error
import urllib.request
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from chartered_book.core import backup, db, nepali_date as nd  # noqa: E402
from chartered_book.web import server  # noqa: E402


def local_addresses():
    """The addresses this machine answers to on the local network."""
    found = []
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.settimeout(0.4)
        # Nothing is actually sent. This only asks the operating system which
        # network card it would use to reach the outside world.
        probe.connect(("10.255.255.255", 1))
        found.append(probe.getsockname()[0])
        probe.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            address = info[4][0]
            if address not in found and not address.startswith("127."):
                found.append(address)
    except OSError:
        pass
    return found


def rule(text=""):
    print("  " + text)


def already_running(port):
    """
    True if a Saphal Book server is already answering on this port.

    Double clicking the icon a second time should bring the books back up, not
    start a rival copy writing to the same files.
    """
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/api/ping" % port, timeout=1.5) as answer:
            payload = json.loads(answer.read().decode("utf-8"))
            return payload.get("application") == "chartered-book"
    except (urllib.error.URLError, OSError, ValueError):
        return False


def find_running(start_port, span=20):
    for port in range(start_port, start_port + span):
        if already_running(port):
            return port
    return None


def open_in_own_window(url):
    """
    Show the books in a window of their own, without an address bar.

    A browser window announcing localhost:8790 across the top is a reminder that
    this is a web page, which it is, but it is not what somebody opening their
    accounts wants to look at. Chrome and its relatives will give a plain window
    with no address bar and no tabs when asked, and the icon in the Dock then
    belongs to Saphal Book rather than to the browser.

    Where none of them is installed, or the trick fails, the ordinary browser is
    opened instead. Being able to see the books always matters more than how the
    window looks.
    """
    import subprocess
    import shutil as _shutil

    candidates = []
    if sys.platform == "darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
    elif os.name == "nt":
        for base in (os.environ.get("PROGRAMFILES", ""),
                     os.environ.get("PROGRAMFILES(X86)", ""),
                     os.environ.get("LOCALAPPDATA", "")):
            if not base:
                continue
            candidates.append(os.path.join(base, "Google", "Chrome", "Application",
                                           "chrome.exe"))
            candidates.append(os.path.join(base, "Microsoft", "Edge", "Application",
                                           "msedge.exe"))
    else:
        for name in ("google-chrome", "chromium", "chromium-browser", "microsoft-edge"):
            found = _shutil.which(name)
            if found:
                candidates.append(found)

    # The window opens in the browser already running on the machine rather than
    # in a profile of its own.
    #
    # A separate profile sounds tidier and cost nearly five seconds on every
    # single launch, because it is a whole cold browser start each time however
    # long the real one has been open. Measured: the books themselves are ready
    # in a third of a second and the wait was entirely this. Nobody minds an
    # extension being loaded; everybody minds waiting five seconds to look up a
    # customer.
    for path in candidates:
        if not os.path.exists(path):
            continue
        try:
            subprocess.Popen(
                [path, "--app=%s" % url, "--no-first-run", "--no-default-browser-check"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception:
            continue
    webbrowser.open(url)
    return False


def main():
    parser = argparse.ArgumentParser(description="Start Saphal Book.")
    parser.add_argument("--port", type=int, default=8790,
                        help="Port to listen on. The next free one is used if this is busy.")
    parser.add_argument("--host", default=None,
                        help="Address to listen on. Leave this alone unless you know why.")
    parser.add_argument("--lan", action="store_true",
                        help="Also answer other machines on the same wifi, so a phone or "
                             "tablet can use the books.")
    parser.add_argument("--no-browser", action="store_true", help="Do not open the browser.")
    parser.add_argument("--no-backup", action="store_true",
                        help="Skip the backup normally taken at startup.")
    parser.add_argument("--app", action="store_true",
                        help="Started from the application icon. Keeps quiet, writes what it "
                             "would have printed to a log file, and reuses a copy that is "
                             "already running instead of starting a second one.")
    args = parser.parse_args()

    if args.app:
        return run_as_app(args)

    host = args.host or ("0.0.0.0" if args.lan else "127.0.0.1")

    db.ensure_dirs()
    today = datetime.date.today()
    described = nd.describe(today)

    print()
    rule("Saphal Book")
    rule("Bookkeeping and accounts for Nepal")
    rule()
    rule("Today is %s, %s" % (described["bs_long"], described["ad_long"]))

    if not args.no_backup and os.path.exists(db.SYSTEM_DB):
        try:
            info = backup.create_backup("Taken when the software was started", "automatic")
            note = info["filename"]
            copies = [c for c in info.get("copies", []) if c.get("ok")]
            if copies:
                note += ", copied to %d other folder%s" % (len(copies), "" if len(copies) == 1 else "s")
            rule("Startup backup: %s" % note)
        except Exception as exc:
            rule("Startup backup could not be taken: %s" % exc)

    try:
        httpd = server.build_server(host, args.port)
    except RuntimeError as exc:
        rule("Could not start: %s" % exc)
        return 1

    port = httpd.server_address[1]
    rule()
    rule("On this computer, open:")
    rule("    http://localhost:%d/" % port)
    if host == "0.0.0.0":
        addresses = local_addresses()
        if addresses:
            rule()
            rule("On a phone, tablet or another computer on the same wifi, open:")
            for address in addresses:
                rule("    http://%s:%d/" % (address, port))
            rule()
            rule("In that browser choose Install, or Add to Home Screen, and Chartered")
            rule("Book gets its own icon and opens like any other app.")
        else:
            rule("This computer does not appear to be on a network yet.")
        rule()
        rule("Anyone on this wifi can reach the sign in screen. They still need a")
        rule("username and password. Use --lan only on a network you trust.")
    else:
        rule()
        rule("Only this computer can reach it. To let a phone or tablet in as well,")
        rule("start it with:   python3 start.py --lan")

    rule()
    rule("Data folder:    %s" % db.DATA_DIR)
    rule("Backups folder: %s" % db.BACKUP_DIR)
    rule()
    rule("Press Control and C in this window to stop.")
    print()

    if not args.no_browser:
        threading.Timer(0.8, lambda: open_in_own_window("http://localhost:%d/" % port)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print()
        rule("Stopping. Taking a closing backup.")
        try:
            info = backup.create_backup("Taken when the software was closed", "automatic")
            rule("Saved %s" % info["filename"])
        except Exception as exc:
            rule("Closing backup could not be taken: %s" % exc)
        httpd.shutdown()
        rule("Saphal Book is closed.")
    return 0


def run_as_app(args):
    """
    Started by double clicking the icon.

    There is no terminal window to read, so anything worth saying goes to
    data/saphal-book.log instead, and the browser is opened automatically.
    """
    db.ensure_dirs()
    log_path = os.path.join(db.DATA_DIR, "saphal-book.log")
    try:
        log = open(log_path, "a", buffering=1, encoding="utf-8")
        sys.stdout = log
        sys.stderr = log
    except OSError:
        pass

    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print("\n[%s] Saphal Book starting" % stamp)

    running = find_running(args.port)
    if running:
        print("[%s] Already running on port %d, opening the browser at it." % (stamp, running))
        open_in_own_window("http://localhost:%d/" % running)
        return 0

    if not args.no_backup and os.path.exists(db.SYSTEM_DB):
        try:
            info = backup.create_backup("Taken when the software was started", "automatic")
            print("[%s] Startup backup: %s" % (stamp, info["filename"]))
        except Exception as exc:
            print("[%s] Startup backup could not be taken: %s" % (stamp, exc))

    host = "0.0.0.0" if args.lan else "127.0.0.1"
    try:
        httpd = server.build_server(host, args.port)
    except RuntimeError as exc:
        print("[%s] Could not start: %s" % (stamp, exc))
        _tell_the_user("Saphal Book could not start",
                       "Every port it tried was busy. Restart the computer and try again.")
        return 1

    port = httpd.server_address[1]
    print("[%s] Listening on %s port %d" % (stamp, host, port))
    if host == "0.0.0.0":
        for address in local_addresses():
            print("[%s] On the network at http://%s:%d/" % (stamp, address, port))

    closing = {"done": False}

    def shut_down(*_ignored):
        if closing["done"]:
            return
        closing["done"] = True
        try:
            info = backup.create_backup("Taken when the software was closed", "automatic")
            print("[%s] Closing backup: %s"
                  % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), info["filename"]))
        except Exception as exc:
            print("Closing backup could not be taken: %s" % exc)
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    for name in ("SIGTERM", "SIGINT", "SIGHUP"):
        if hasattr(signal, name):
            try:
                signal.signal(getattr(signal, name), shut_down)
            except (ValueError, OSError):
                pass

    threading.Timer(1.0, lambda: open_in_own_window("http://localhost:%d/" % port)).start()

    try:
        httpd.serve_forever()
    finally:
        shut_down()
    return 0


def _tell_the_user(title, message):
    """Show a dialog, because with no terminal there is nowhere else to say it."""
    if sys.platform != "darwin":
        return
    try:
        import subprocess
        subprocess.run(["osascript", "-e",
                        'display dialog %s with title %s buttons {"OK"} default button 1 '
                        'with icon caution' % (json.dumps(message), json.dumps(title))],
                       timeout=30, check=False)
    except Exception:
        pass


if __name__ == "__main__":
    sys.exit(main())

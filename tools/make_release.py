#!/usr/bin/env python3
"""
Build the downloads other people actually use.

    python3 tools/make_release.py

Writes two files into the download folder:

    Saphal Book for Mac.zip       the finished app, double click and go
    Saphal Book for Windows.zip   the software plus the Windows launcher

The Mac one holds the whole application, the software inside it, so there is
nothing to build and nothing to set up. The Windows one needs Python installed
once, which is free, because Windows does not ship with it.

Neither one carries any books. The books are kept in the operating system's own
application data folder, never inside the software, so there is nothing of
yours to leak.
"""

import os
import shutil
import subprocess
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Written straight into the published site rather than into a folder beside
# it. There used to be two: one the release script wrote and one the site
# served, and a copy that has to be kept in step with another copy is a copy
# that will one day be out of step without anybody noticing.
OUT = os.path.join(HERE, "docs", "download")
APP = os.path.join(HERE, "Saphal Book.app")

FORBIDDEN = (".db", ".db-wal", ".db-shm", ".sqlite", ".sqlite3", ".log", ".csv", ".xlsx")
SKIP_DIRS = {"__pycache__", "data", "backups", ".git", "download", "docs"}

WINDOWS_FILES = ["start.py", "README.md", "run.bat", "run on wifi.bat",
                 "Saphal Book.vbs"]
WINDOWS_DIRS = ["chartered_book", "tools", "tests", "docs"]


def safe(path):
    name = os.path.basename(path)
    if any(name.endswith(bad) for bad in FORBIDDEN):
        return False
    return not (set(path.split(os.sep)) & SKIP_DIRS)


def build_mac():
    """
    Zip the application with ditto, which is what macOS itself uses.

    A plain zip loses the permissions and the bundle stops being an
    application, which is exactly the failure that looks like nothing happening
    when somebody double clicks it.
    """
    if not os.path.isdir(APP):
        print("  The Mac app is not built yet. Run tools/make_mac_app.py first.")
        return None
    target = os.path.join(OUT, "Saphal Book for Mac.zip")
    if os.path.exists(target):
        os.remove(target)
    result = subprocess.run(
        ["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", APP, target],
        capture_output=True, text=True)
    if result.returncode != 0:
        print("  ditto failed: %s" % result.stderr.strip())
        return None
    return target


def build_windows():
    target = os.path.join(OUT, "Saphal Book for Windows.zip")
    if os.path.exists(target):
        os.remove(target)
    added = 0
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for filename in WINDOWS_FILES:
            source = os.path.join(HERE, filename)
            if os.path.exists(source) and safe(source):
                archive.write(source, os.path.join("Saphal Book", filename))
                added += 1
        for folder in WINDOWS_DIRS:
            root_dir = os.path.join(HERE, folder)
            if not os.path.isdir(root_dir):
                continue
            for root, dirs, files in os.walk(root_dir):
                dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
                for filename in files:
                    full = os.path.join(root, filename)
                    relative = os.path.relpath(full, HERE)
                    if not safe(relative):
                        continue
                    archive.write(full, os.path.join("Saphal Book", relative))
                    added += 1
        archive.writestr("Saphal Book/START HERE.txt", WINDOWS_NOTE)
    return target, added


WINDOWS_NOTE = """Saphal Book
Bookkeeping and accounts for Nepal

TO OPEN IT ON WINDOWS

  1. Windows does not come with Python, so install it once, free, from
     python.org/downloads

     IMPORTANT: on the first screen of the installer, tick the box that says
     "Add Python to PATH" before clicking Install. It is easy to miss and
     nothing works without it.

  2. Come back to this folder and double click:

         Saphal Book.vbs

     Your browser opens at the books. No black window appears.

  3. To use it from a phone or tablet on the same wifi, double click
     "run on wifi.bat" instead. It prints an address. Type that address into
     the browser on the phone.

WHERE YOUR BOOKS ARE KEPT

  Not in this folder. They go in your Windows application data folder, so you
  can replace this software later without touching them. The Backup screen
  inside the software shows you the exact place.

FIRST TIME

  It asks you to make a username and password, then to create your company.
  There is no way to recover the password, so write it down somewhere safe.

The full guide is in README.md.
"""


def main():
    os.makedirs(OUT, exist_ok=True)

    print()
    print("  Building the downloads")
    print()

    mac = build_mac()
    if mac:
        print("  Mac      %-34s %7.0f KB"
              % (os.path.basename(mac), os.path.getsize(mac) / 1024.0))

    windows, count = build_windows()
    print("  Windows  %-34s %7.0f KB  (%d files)"
          % (os.path.basename(windows), os.path.getsize(windows) / 1024.0, count))

    print()
    print("  Checking neither one carries books")
    trouble = False
    for path in [p for p in (mac, windows) if p]:
        with zipfile.ZipFile(path) as archive:
            bad = [n for n in archive.namelist()
                   if any(n.endswith(x) for x in FORBIDDEN)]
            if bad:
                trouble = True
                print("    %s: %s" % (os.path.basename(path), bad[:5]))
    if not trouble:
        print("    Clean. Nothing but the software in either.")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())

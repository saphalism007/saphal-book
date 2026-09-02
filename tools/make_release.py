#!/usr/bin/env python3
"""
Package Chartered Book up so it can be given to somebody else.

    python3 tools/make_release.py

Writes a single zip beside this project. Whoever receives it unzips it, and on
a Mac double clicks Chartered Book, or on Windows double clicks
Chartered Book.vbs. They get their own empty books. Nothing of yours travels
with it, because the books are never inside this folder in the first place.
"""

import datetime
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

INCLUDE_DIRS = ["chartered_book", "tools", "tests", "docs"]
INCLUDE_FILES = ["start.py", "README.md", "run.command", "run.bat",
                 "run on wifi.command", "run on wifi.bat", "Chartered Book.vbs",
                 ".gitignore"]

# Nothing that could carry a figure of yours.
FORBIDDEN = (".db", ".db-wal", ".db-shm", ".sqlite", ".sqlite3", ".log", ".csv", ".xlsx")
SKIP_DIRS = {"__pycache__", "data", "backups", ".git", "Chartered Book.app"}


def safe(path):
    name = os.path.basename(path)
    if any(name.endswith(bad) for bad in FORBIDDEN):
        return False
    parts = set(path.split(os.sep))
    return not (parts & SKIP_DIRS)


def main():
    from chartered_book.core import nepali_date as nd
    stamp = datetime.date.today()
    bs = nd.format_bs(nd.ad_to_bs(stamp), "numeric")
    name = "Chartered Book %s.zip" % bs
    target = os.path.join(HERE, name)

    added, refused = [], []
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for filename in INCLUDE_FILES:
            source = os.path.join(HERE, filename)
            if os.path.exists(source) and safe(source):
                archive.write(source, os.path.join("Chartered Book", filename))
                added.append(filename)
        for folder in INCLUDE_DIRS:
            root_dir = os.path.join(HERE, folder)
            if not os.path.isdir(root_dir):
                continue
            for root, dirs, files in os.walk(root_dir):
                dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
                for filename in files:
                    full = os.path.join(root, filename)
                    relative = os.path.relpath(full, HERE)
                    if not safe(relative):
                        refused.append(relative)
                        continue
                    archive.write(full, os.path.join("Chartered Book", relative))
                    added.append(relative)

        archive.writestr("Chartered Book/START HERE.txt",
            "Chartered Book\n"
            "Bookkeeping and accounts for Nepal\n"
            "\n"
            "On a Mac\n"
            "  1. Move this Chartered Book folder wherever you want to keep it.\n"
            "  2. Open a Terminal in the folder and run once:\n"
            "         python3 tools/make_mac_app.py\n"
            "     That builds the Chartered Book icon.\n"
            "  3. Double click Chartered Book from then on.\n"
            "\n"
            "On Windows\n"
            "  1. Install Python once from python.org, ticking Add Python to PATH.\n"
            "  2. Double click Chartered Book.vbs.\n"
            "\n"
            "On a phone or tablet\n"
            "  Start it with run on wifi, then open the address it prints in the\n"
            "  browser on the phone, and add it to the home screen.\n"
            "\n"
            "Your books are kept outside this folder, in the place your computer\n"
            "sets aside for application data, so updating the software never\n"
            "touches them. The Backup screen shows exactly where.\n"
            "\n"
            "The full guide is in README.md.\n")

    size = os.path.getsize(target)
    print()
    print("  Written: %s" % name)
    print("  %d files, %.1f KB" % (len(added), size / 1024.0))
    if refused:
        print("  Left out as they could hold data: %d" % len(refused))
    print()
    print("  Check before sending: nothing below should look like your books.")
    with zipfile.ZipFile(target) as archive:
        suspicious = [n for n in archive.namelist()
                      if any(n.endswith(bad) for bad in FORBIDDEN)]
        print("  Files that could hold figures: %s" % (suspicious or "none"))
    print()
    print("  Send that zip however you like. Whoever opens it gets empty books")
    print("  of their own.")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Build the Mac application, so Saphal Book can be opened by clicking an icon.

    python3 tools/make_mac_app.py

It writes "Saphal Book.app" beside this project. Drag that to the
Applications folder, or keep it in the Dock, and double click it. No terminal
window appears. Anything it wants to say goes to data/chartered-book.log.

The app carries its own copy of the software inside the bundle. It has to: an
app opened from the Finder is refused entry to the Documents folder, silently,
and closes again the moment it opens.

That has one consequence worth being loud about. Improving the code in this
folder does nothing at all to the app until this is run again. Run it after
every change, or double click "Update Saphal Book.command", which does the
same thing without a terminal. The app shows which copy it is running in the
bottom corner and turns that red when it is behind.
"""

import datetime
import os
import plistlib
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICON_DIR = os.path.join(HERE, "chartered_book", "web", "static", "icons")
APP_NAME = "Saphal Book"
BUNDLE_ID = "np.charteredbook.app"


def build_icns(target_dir):
    """Turn the 512 pixel icon into the set of sizes macOS wants."""
    source = os.path.join(ICON_DIR, "icon-512.png")
    if not os.path.exists(source):
        raise SystemExit("Run tools/make_icons.py first, icon-512.png is missing.")
    iconset = os.path.join(target_dir, "AppIcon.iconset")
    if os.path.exists(iconset):
        shutil.rmtree(iconset)
    os.makedirs(iconset)
    sizes = [16, 32, 64, 128, 256, 512]
    for size in sizes:
        for scale, suffix in ((1, ""), (2, "@2x")):
            pixels = size * scale
            if pixels > 1024:
                continue
            name = "icon_%dx%d%s.png" % (size, size, suffix)
            subprocess.run(["sips", "-z", str(pixels), str(pixels), source,
                            "--out", os.path.join(iconset, name)],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    icns = os.path.join(target_dir, "AppIcon.icns")
    subprocess.run(["iconutil", "-c", "icns", iconset, "-o", icns], check=True)
    shutil.rmtree(iconset)
    return icns


def main():
    if sys.platform != "darwin":
        raise SystemExit("This builds the Mac application, so it has to be run on a Mac.")

    app_path = os.path.join(HERE, APP_NAME + ".app")
    if os.path.exists(app_path):
        shutil.rmtree(app_path)

    contents = os.path.join(app_path, "Contents")
    macos = os.path.join(contents, "MacOS")
    resources = os.path.join(contents, "Resources")
    os.makedirs(macos)
    os.makedirs(resources)

    build_icns(resources)

    # The software is copied inside the app rather than read from where it was
    # written. An app opened from the Finder is refused entry to the Documents
    # folder, silently, and closes again the moment it opens. Carrying its own
    # copy means it works wherever the source happens to sit.
    inside = os.path.join(resources, "app")
    os.makedirs(inside)
    shutil.copy2(os.path.join(HERE, "start.py"), os.path.join(inside, "start.py"))
    shutil.copytree(os.path.join(HERE, "chartered_book"),
                    os.path.join(inside, "chartered_book"),
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for extra in ("tools", "tests"):
        source = os.path.join(HERE, extra)
        if os.path.isdir(source):
            shutil.copytree(source, os.path.join(inside, extra),
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    # Record when this copy was made, so the screen can say which one is
    # running and whether it has fallen behind the source.
    from chartered_book.core import build as build_stamp
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(os.path.join(inside, "chartered_book", "BUILD.txt"), "w",
              encoding="utf-8") as handle:
        handle.write(stamp + "\n")

    for extra in ("README.md",):
        source = os.path.join(HERE, extra)
        if os.path.exists(source):
            shutil.copy2(source, os.path.join(inside, extra))

    launcher = os.path.join(macos, "SaphalBook")
    with open(launcher, "w", encoding="utf-8") as handle:
        handle.write(
            '#!/bin/bash\n'
            '# Opens Saphal Book.\n'
            '# The software sits inside this app, in Contents/Resources/app.\n'
            '# The books are kept in Library/Application Support/Saphal Book.\n'
            'HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../Resources/app" && pwd)"\n'
            'cd "$HERE" || exit 1\n'
            'PY=""\n'
            'for candidate in /usr/bin/python3 /usr/local/bin/python3 '
            '/opt/homebrew/bin/python3; do\n'
            '  if [ -x "$candidate" ]; then PY="$candidate"; break; fi\n'
            'done\n'
            'if [ -z "$PY" ]; then PY="$(command -v python3)"; fi\n'
            'if [ -z "$PY" ]; then\n'
            '  osascript -e \'display dialog "Python 3 was not found on this Mac. Install it '
            'free from python.org and open Saphal Book again." with title "Saphal Book" '
            'buttons {"OK"} default button 1 with icon caution\'\n'
            '  exit 1\n'
            'fi\n'
            'exec "$PY" start.py --app --lan "$@"\n')
    os.chmod(launcher, 0o755)

    info = {
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleIdentifier": BUNDLE_ID,
        "CFBundleVersion": "1.0",
        "CFBundleShortVersionString": "1.0",
        "CFBundleExecutable": "SaphalBook",
        "CFBundleIconFile": "AppIcon",
        "CFBundlePackageType": "APPL",
        "LSMinimumSystemVersion": "10.13",
        "NSHighResolutionCapable": True,
        # Without this the launcher script keeps a Dock icon bouncing after the
        # browser opens, which looks as though something is stuck.
        "LSBackgroundOnly": False,
        "NSHumanReadableCopyright": "Private software. Not for sale.",
        # The books live in the Documents folder, which macOS protects. Without
        # these, the app is refused permission to read its own code and closes
        # again the moment it opens, saying nothing.
        "NSDocumentsFolderUsageDescription":
            "Saphal Book keeps your books in this folder.",
        "NSDesktopFolderUsageDescription":
            "Saphal Book keeps your books in this folder.",
        "NSDownloadsFolderUsageDescription":
            "Saphal Book keeps your books in this folder.",
        "NSRemovableVolumesUsageDescription":
            "So a backup can be written to a pen drive.",
        "NSNetworkVolumesUsageDescription":
            "So a backup can be written to a shared folder.",
    }
    with open(os.path.join(contents, "Info.plist"), "wb") as handle:
        plistlib.dump(info, handle)

    # An unsigned bundle gets a new identity every time it changes, so macOS
    # asks for permission again and again and forgets the answer. Signing it
    # with the machine's own ad hoc identity gives it one steady identity.
    signed = subprocess.run(
        ["codesign", "--force", "--deep", "--sign", "-", app_path],
        capture_output=True, text=True)
    if signed.returncode != 0:
        print("  Note: the app could not be signed. It will still run, but macOS")
        print("  may ask for permission to read the folder more than once.")
        print("  " + (signed.stderr or "").strip().splitlines()[0] if signed.stderr else "")

    # Finder caches icons hard. Touching the bundle makes it look afresh.
    subprocess.run(["touch", app_path], check=False)

    from chartered_book.core import db

    print()
    print("  Built: %s" % app_path)
    print()
    print("  Double click it to open Saphal Book.")
    print("  Drag it to Applications, or keep it in the Dock, so it is always to hand.")
    print()
    print("  The books are kept in:")
    print("    %s" % db.DATA_DIR)
    print()
    print("  The app carries its own copy of the software, so run this again after")
    print("  any change to the code to bring the app up to date.")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())

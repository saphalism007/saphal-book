"""
Which copy of the software is running.

This exists because of a trap that cost a day. The Mac application carries its
own copy of the code inside the bundle, so that opening it from the Finder does
not run into the Documents folder being out of bounds. The consequence is that
improving the code here does nothing at all to the app until the app is built
again, and there was no way to tell from the screen which of the two was
running. Fixes appeared not to work when in fact they had never arrived.

The build stamp is written when the app is built and shown in the corner of the
screen. If it does not match, the app is out of date and says so.
"""

import datetime
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STAMP_FILE = os.path.join(HERE, "BUILD.txt")


def read():
    """The stamp of the copy that is running, or the source date if unbuilt."""
    if os.path.exists(STAMP_FILE):
        try:
            with open(STAMP_FILE, encoding="utf-8") as handle:
                stamp = handle.read().strip()
            if stamp:
                return stamp
        except OSError:
            pass
    return "source of " + newest_source().strftime("%Y-%m-%d %H:%M")


def newest_source():
    """When the newest piece of the software was last touched."""
    newest = 0
    for folder, _dirs, files in os.walk(HERE):
        if "__pycache__" in folder:
            continue
        for name in files:
            if not name.endswith((".py", ".js", ".css", ".html")):
                continue
            try:
                when = os.path.getmtime(os.path.join(folder, name))
            except OSError:
                continue
            newest = max(newest, when)
    return datetime.datetime.fromtimestamp(newest or 0)


def write(stamp=None):
    """Record the stamp. Called when the application is built."""
    stamp = stamp or datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(STAMP_FILE, "w", encoding="utf-8") as handle:
        handle.write(stamp + "\n")
    return stamp

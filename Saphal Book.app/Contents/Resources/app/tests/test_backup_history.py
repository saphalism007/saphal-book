"""
There has to be more than one backup to go back to.

This exists because of a real mistake, and it was mine. The number of backups
kept was set to one, in every place at once: the local folder, the cloud folder
and Google Drive. The argument was that three places each holding a copy was
enough. It is not, and the reason is simple: one backup run writes to all three
in the same moment, so a damaged set of books replaces the good copy in every
one of them together. Three places holding the same bad copy is not three
chances, it is one.

The damage that matters is not a disk failing this afternoon. It is a wrong
opening balance or a party deleted by accident, which can sit in the books for
a fortnight before anybody notices. A history that only reaches back to
yesterday is no use at all by then.

So what is checked here is that a run of days survives, that a day's backup
still replaces that same day's rather than piling up, and that nothing which is
not ours is touched.

Run with:  python3 -m tests.test_backup_history
"""

import os
import shutil
import sys
import tempfile
import time

from chartered_book.core import backup

FAILURES = []


def check(label, got, expected):
    if got != expected:
        FAILURES.append("%s: got %r, expected %r" % (label, got, expected))


def main():
    # The whole point of this file, stated as a number.
    check("more than one backup is kept locally", backup.KEEP_LOCAL > 1, True)
    check("and a good many on Drive", backup.KEEP_ON_DRIVE >= 14, True)

    folder = tempfile.mkdtemp(prefix="saphal_backup_test_")
    try:
        # Twelve days of backups, oldest first, each with its own date in the
        # name the way the software writes them.
        made = []
        for day in range(1, 13):
            name = "%s2026%02d%02d.zip" % (backup.BACKUP_PREFIX, 9, day)
            path = os.path.join(folder, name)
            with open(path, "wb") as handle:
                handle.write(b"pretend books")
            # Ordered in time, because that is what the tidying sorts on.
            os.utime(path, (time.time() - (13 - day) * 86400,) * 2)
            made.append(name)

        # And two things that are not ours, which must be left alone.
        for stranger in ("the shop lease.pdf", "saphal_notes.txt"):
            with open(os.path.join(folder, stranger), "wb") as handle:
                handle.write(b"not a backup")

        removed = backup.tidy_folder(folder)
        left = sorted(n for n in os.listdir(folder)
                      if n.startswith(backup.BACKUP_PREFIX) and n.endswith(".zip"))

        check("the right number of days is left", len(left), backup.KEEP_LOCAL)
        check("and it removed the rest", removed, 12 - backup.KEEP_LOCAL)
        check("the newest day is one of them", made[-1] in left, True)
        check("and the oldest is gone", made[0] in left, False)

        strangers = sorted(n for n in os.listdir(folder)
                           if not n.startswith(backup.BACKUP_PREFIX))
        check("nothing that is not ours was touched",
              strangers, ["saphal_notes.txt", "the shop lease.pdf"])

        # Asking again changes nothing, because there is nothing left to remove.
        check("tidying twice removes nothing the second time",
              backup.tidy_folder(folder), 0)

        # A folder that is not there is not an error worth raising.
        check("a folder that does not exist is simply nothing to do",
              backup.tidy_folder(os.path.join(folder, "no such place")), 0)
    finally:
        shutil.rmtree(folder, ignore_errors=True)

    if FAILURES:
        print("Backup history: %d problem%s"
              % (len(FAILURES), "" if len(FAILURES) == 1 else "s"))
        for line in FAILURES:
            print("  " + line)
        return 1
    print("Backup history: %d days are kept here and %d on Drive, and there is "
          "something to go back to." % (backup.KEEP_LOCAL, backup.KEEP_ON_DRIVE))
    return 0


if __name__ == "__main__":
    sys.exit(main())

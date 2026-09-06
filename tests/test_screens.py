"""
Nothing anybody types can become part of the page.

Every screen is built out of things a person typed: a customer called
whatever they called it, a narration, an item description. If any of that
were ever put into the page as markup instead of as text, then a party
named after a script tag would run that script the next time anybody opened
a ledger. On accounting books that is not a cosmetic problem.

The whole defence is one rule: the function that builds elements sets text
and never markup. It has no way of doing otherwise. This walks the screens
and fails if any of the ways round that rule turn up in them, so the rule
cannot be quietly undone by a later change.

Run with:  python3 -m tests.test_screens
"""

import io
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCREENS = os.path.join(HERE, "chartered_book", "web", "static")

# Each way of turning a string into part of the page, and why it is not wanted.
SINKS = [
    (r"\.innerHTML\s*=", "sets markup from a string"),
    (r"\.outerHTML\s*=", "replaces an element from a string"),
    (r"\binsertAdjacentHTML\b", "inserts markup from a string"),
    (r"\bdocument\.write\b", "writes markup into the page"),
    (r"\bhtml\s*:", "asks the element builder for markup"),
    (r"\beval\s*\(", "runs a string as code"),
    (r"new\s+Function\s*\(", "makes code out of a string"),
]

# There are no exceptions. The goodbye screen was the last one, and it is
# built out of nodes now like everything else.
ALLOWED = set()

FAILURES = []


def main():
    checked = 0
    for name in sorted(os.listdir(SCREENS)):
        if not name.endswith(".js"):
            continue
        checked += 1
        text = io.open(os.path.join(SCREENS, name), encoding="utf-8").read()
        for line_no, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("*"):
                continue
            for pattern, why in SINKS:
                if re.search(pattern, line) and (name, pattern) not in ALLOWED:
                    FAILURES.append("%s line %d %s: %s"
                                    % (name, line_no, why, stripped[:70]))

    if not checked:
        FAILURES.append("no screens were found to check")

    if FAILURES:
        print("Screens: %d place%s where typed text could become part of the page"
              % (len(FAILURES), "" if len(FAILURES) == 1 else "s"))
        for line in FAILURES:
            print("  " + line)
        return 1
    print("Screens: %d checked, nothing typed can become part of the page." % checked)
    return 0


if __name__ == "__main__":
    sys.exit(main())

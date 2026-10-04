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


def layer(css, selector):
    """The z-index a selector's own block gives it."""
    found = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{([^}]*)\}", css)
    if not found:
        return None
    index = re.search(r"z-index:\s*(\d+)", found.group(1))
    return int(index.group(1)) if index else None


def check_what_sits_on_top_of_what():
    """
    Anything opened from the sign in screen has to be on top of it.

    The reset panel opened behind the sign in screen for as long as it existed.
    It was in the page, its text could be read by a program, and every check
    made of it passed, while the person pressing "Forgot your password?" saw
    nothing happen at all. The panel was one layer under the screen it was
    opened from. The same went for every message shown while signed out.

    A test that reads what a screen says cannot see this, so the order is
    checked for itself.
    """
    css = io.open(os.path.join(SCREENS, "style.css"), encoding="utf-8").read()
    gate, modal = layer(css, ".gate"), layer(css, ".modal")
    picker, floating = layer(css, ".picker"), layer(css, ".flash.floating")
    for name, value in (("sign in screen", gate), ("panel", modal),
                        ("picker", picker), ("message", floating)):
        if value is None:
            FAILURES.append("could not find which layer the %s is on" % name)
            return
    if not modal > gate:
        FAILURES.append("a panel (%d) opens behind the sign in screen (%d)"
                        % (modal, gate))
    if not picker > modal:
        FAILURES.append("a picker (%d) opens behind the panel it is in (%d)"
                        % (picker, modal))
    if not floating > modal:
        FAILURES.append("a message (%d) is hidden behind a panel (%d)"
                        % (floating, modal))


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

    check_what_sits_on_top_of_what()

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

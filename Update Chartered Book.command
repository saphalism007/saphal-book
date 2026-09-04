#!/bin/bash
# Double click this after any change to the software.
#
# The Mac app carries its own copy of Chartered Book inside it, so a change made
# to the code does not reach the app until the app is built again. This does
# that. It takes a few seconds and touches nothing else.
#
# Your books are NOT inside the app. They live in
#   ~/Library/Application Support/Chartered Book
# and are never touched by this.

cd "$(dirname "$0")" || exit 1

echo ""
echo "  Updating Chartered Book"
echo "  ======================="
echo ""

PY=""
for candidate in /usr/bin/python3 /usr/local/bin/python3 /opt/homebrew/bin/python3; do
  if [ -x "$candidate" ]; then PY="$candidate"; break; fi
done
if [ -z "$PY" ]; then PY="$(command -v python3)"; fi
if [ -z "$PY" ]; then
  echo "  Python 3 was not found on this Mac."
  echo "  Install it free from python.org and run this again."
  echo ""
  read -n 1 -s -r -p "  Press any key to close this window."
  exit 1
fi

echo "  Checking the accounting still adds up before building..."
echo ""
FAILED=""
for suite in test_nepali_date test_accounting test_statements test_vouchers \
             test_schedules test_settlements test_discounts test_inventory; do
  if "$PY" -m tests.$suite >/dev/null 2>&1; then
    printf "    passed   %s\n" "$suite"
  else
    printf "    FAILED   %s\n" "$suite"
    FAILED="yes"
  fi
done
echo ""

if [ -n "$FAILED" ]; then
  echo "  Something is wrong with the accounting, so the app was NOT rebuilt."
  echo "  The app you have keeps working. Tell Claude what this says."
  echo ""
  read -n 1 -s -r -p "  Press any key to close this window."
  exit 1
fi

if ! "$PY" tools/make_mac_app.py; then
  echo ""
  echo "  The app could not be built. The one you have keeps working."
  echo ""
  read -n 1 -s -r -p "  Press any key to close this window."
  exit 1
fi

echo ""
echo "  Done. Close Chartered Book if it is open, then open it again."
echo "  Your books were not touched."
echo ""
read -n 1 -s -r -p "  Press any key to close this window."

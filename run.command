#!/bin/bash
# Start Chartered Book on macOS. Double click this file.
# To let a phone or tablet on the same wifi use it too, change the last line to:
#     python3 start.py --lan
cd "$(dirname "$0")"
if command -v python3 >/dev/null 2>&1; then
  python3 start.py
else
  echo "Python 3 was not found on this Mac."
  echo "Install it free from https://www.python.org/downloads/ and try again."
  read -r -p "Press Enter to close."
fi

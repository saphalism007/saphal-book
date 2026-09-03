#!/bin/bash
# Send Chartered Book to GitHub.
#
# Create an empty repository on github.com first, with no readme and no
# licence, then run this and paste the address it asks for.
#
# Your books are not in this folder and are excluded by .gitignore, so nothing
# of yours travels with it. This checks that again before pushing.

cd "$(dirname "$0")/.." || exit 1
echo
echo "  Chartered Book, sending the source to GitHub"
echo

# Refuse to go anywhere near a database file.
RISKY=$(git ls-files | grep -Ei '\.db$|\.sqlite3?$|^data/|\.db-wal$|\.db-shm$' || true)
if [ -n "$RISKY" ]; then
  echo "  Stopping. These look like books rather than source:"
  echo "$RISKY" | sed 's/^/      /'
  echo
  echo "  Nothing was sent."
  exit 1
fi
echo "  Checked: no books are tracked, only source."
echo

if [ -n "$1" ]; then
  URL="$1"
else
  echo "  Paste the address of the empty repository you made."
  echo "  It looks like  https://github.com/yourname/chartered-book.git"
  echo
  printf "  Address: "
  read -r URL
fi

if [ -z "$URL" ]; then
  echo "  No address given. Nothing was sent."
  exit 1
fi

if git remote | grep -q '^origin$'; then
  git remote set-url origin "$URL"
else
  git remote add origin "$URL"
fi

git branch -M main
echo
echo "  Sending..."
if git push -u origin main; then
  PAGE=$(echo "$URL" | sed 's/\.git$//')
  echo
  echo "  Done. It is now at:"
  echo "      $PAGE"
  echo
  echo "  That address is the link to share. Anyone can download it from there"
  echo "  with the green Code button, then Download ZIP."
  echo
else
  echo
  echo "  It did not go. The usual reasons:"
  echo "    the repository was not created yet, or the address has a typo"
  echo "    the repository is not empty, so add --force once you are sure"
  echo "    the sign in was refused, in which case open github.com in a browser"
  echo "    and sign in there first so the keychain has a current token"
  echo
  exit 1
fi

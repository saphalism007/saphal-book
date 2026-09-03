#!/bin/bash
# Double click this file to put Chartered Book on GitHub.
# It asks you one question and does the rest.

cd "$(dirname "$0")" || exit 1
clear

say() { printf "%s\n" "$1"; }
rule() { say ""; say "  ------------------------------------------------------------"; say ""; }

say ""
say "  ============================================================"
say "     Putting Chartered Book on GitHub"
say "  ============================================================"
say ""
say "  This sends the software to your GitHub account so you get a"
say "  web address you can send to other people."
say ""
say "  Your books are NOT sent. Only the software itself."
rule

# Never send anything that looks like books.
RISKY=$(git ls-files 2>/dev/null | grep -Ei '\.db$|\.sqlite3?$|^data/|\.db-wal$|\.db-shm$')
if [ -n "$RISKY" ]; then
  say "  STOPPED. These look like your books, not software:"
  say ""
  printf "%s\n" "$RISKY" | sed 's/^/      /'
  say ""
  say "  Nothing was sent. Tell Claude what you see here."
  say ""
  printf "  Press Enter to close. "
  read -r _
  exit 1
fi
say "  Checked. No books are included, only the software."
rule

say "  STEP 1 of 2"
say ""
say "  A page should have opened in your browser called"
say "  'Create a new repository'."
say ""
say "  On that page:"
say "     1. Leave the name as it is, chartered-book"
say "     2. Click the circle next to Public"
say "     3. Do NOT tick anything else"
say "     4. Click the green Create repository button at the bottom"
say ""
say "  If the page did not open, go to this address yourself:"
say "     https://github.com/new?name=chartered-book"
say ""
open "https://github.com/new?name=chartered-book" 2>/dev/null
printf "  When you have created it, press Enter here. "
read -r _
rule

say "  STEP 2 of 2"
say ""
say "  After creating it, GitHub showed you a page with an address"
say "  near the top. It looks like this:"
say ""
say "      https://github.com/yourname/chartered-book.git"
say ""
say "  Copy that address and paste it below."
say "  To paste, press Command and V together."
say ""

URL=""
while [ -z "$URL" ]; do
  printf "  Paste the address here: "
  read -r URL
  if [ -z "$URL" ]; then
    say ""
    say "  Nothing was pasted. Try again, or close this window to stop."
    say ""
  fi
done

# Tidy up whatever they pasted.
URL=$(printf "%s" "$URL" | tr -d '[:space:]')
case "$URL" in
  *github.com*) : ;;
  *) say ""; say "  That does not look like a GitHub address. It should start"
     say "  with https://github.com/"
     say ""
     printf "  Press Enter to close. "; read -r _; exit 1 ;;
esac
case "$URL" in
  *.git) : ;;
  *) URL="${URL%/}.git" ;;
esac

rule
say "  Sending to:"
say "      $URL"
say ""

if git remote | grep -q '^origin$'; then
  git remote set-url origin "$URL"
else
  git remote add origin "$URL"
fi
git branch -M main >/dev/null 2>&1

if git push -u origin main 2>&1; then
  PAGE="${URL%.git}"
  rule
  say "  DONE."
  say ""
  say "  Your link is:"
  say ""
  say "      $PAGE"
  say ""
  say "  Send that to anyone. They click the green Code button, then"
  say "  Download ZIP, and they have their own copy."
  say ""
  open "$PAGE" 2>/dev/null
else
  rule
  say "  It did not go through. The usual reasons:"
  say ""
  say "    You have not created the repository yet on github.com"
  say "    The address was pasted wrong"
  say "    The repository already has files in it, so it is not empty"
  say "    GitHub did not recognise you. Open github.com in your"
  say "      browser, sign in there, then run this again."
  say ""
  say "  Nothing was broken. You can just run this file again."
  say ""
fi

printf "  Press Enter to close this window. "
read -r _

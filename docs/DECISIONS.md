# Chartered Book, design decisions

Reasons behind choices that are not obvious from the code. Read this before
changing anything structural.

## Why Python with no packages

The software must cost nothing, work with no internet, and still run in five
years. Every package added is something that can break on a future machine or
quietly disappear. Chartered Book uses only what ships with Python: sqlite3 for
storage, http.server for the screen, hashlib for passwords, decimal for parsing
money. Nothing to install, nothing to renew.

## Why the screen is a browser page

A browser is already on every Windows machine and this Mac. It prints invoices
properly, it handles Devanagari text correctly, and the same code runs on both
platforms. The server only listens on 127.0.0.1, so nothing is exposed to the
network unless that is deliberately changed.

## Why money is stored as integer paisa

A float cannot hold 0.10 exactly. Add enough of them and a trial balance stops
tying by a paisa or two, which is precisely the kind of error that costs a day
to find. Every amount is an integer count of paisa. Quantities are integers in
thousandths for the same reason. Rates are integers in basis points, so 13
percent is 1300.

## Why one database file for each company

A backup becomes a file copy. One business can be restored without touching
another. No query can accidentally mix two sets of books. The only shared file
is data/system.db, which holds users and the list of companies.

## Why dates are stored in AD and shown in BS

ISO AD dates sort correctly as text, which makes every date range query simple
and fast. The BS date is derived on the way in and out, and is also stored on
each voucher so it can be searched and printed. The conversion table covers
BS 2000 to 2099 and is verified against known historical dates in
tests/test_nepali_date.py.

## Why inventory is periodic, not perpetual

Most trading houses in Nepal, and the auditors who examine them, work on
opening stock plus purchases less closing stock. A sales invoice therefore does
not post cost of goods sold. The stock ledger still records every movement in
quantity and value, so stock reports are live, and the closing stock entry
brings the value into the accounts at period end. This also stays correct when
a backdated invoice is entered, which a perpetual running average does not.

## Why a posted voucher is cancelled rather than deleted

A missing invoice number cannot be explained to a tax officer. Cancelling keeps
the number, keeps the record, and records who cancelled it and why. Only a
draft can be deleted outright.

## Rounding

Half up, away from zero, applied once per invoice line. Nepali tax practice
rounds this way, and rounding once per line means the printed invoice always
adds up to the same figure as the ledger. Invoice totals are rounded to the
nearest rupee and the difference goes to account 7305 Rounding Off.

## Why an installable web page and not an Android or iPhone app

A real store app needs a developer account for each store, a signing key, a
review each time it changes, and a rebuild for each platform. An installable
web page gets the same icon on the home screen of Android, iPad, Windows and
Mac, for nothing, and updates the moment the code changes. The trade is that a
phone still needs the computer running the books to be switched on, which is
true of any small business system where the data lives in the shop.

The service worker exists to make the page installable and to keep the screens
usable if the connection drops for a moment. It never caches anything from the
API. A stale balance shown as if it were current would be worse than no balance.

## Why backups copy to a folder rather than connecting to Google Drive

Connecting an account means an application registration, keys that expire, a
sign in that breaks whenever the provider changes something, and books passing
through an account link. Naming a folder that a cloud service already keeps in
step does the same job: the copy uploads itself when the machine is next
online, it keeps working when the internet is down, there is nothing to renew,
and it works the same for Google Drive, OneDrive, Dropbox or a pen drive.

The software finds the cloud folders already on the machine and offers them as
buttons, but sets none of them without being asked.

## Why reconciliation never changes a figure

Ticking an entry records only that the bank has dealt with it. The working
subtracts deposits the bank has not credited and adds cheques not yet
presented, which turns an unexplained difference into a list anyone can check.
A reconciliation can only be marked complete when the difference is zero, so
the record cannot claim agreement that was never reached.

## Why the menu is built from what the company does

A practice that bills its time has no stock to count, and showing it stock
screens invites entries that make no sense. The company carries two flags,
has_goods and has_services, which drive the menu and the forms. They are kept
separate from the business type so a shop can start offering services later
without its whole type having to change.

## Why dialogs stack

Adding an item from inside a purchase bill, and a unit from inside that, has to
leave the bill exactly as it was when both are closed. Each dialog is kept and
put back rather than thrown away and rebuilt.

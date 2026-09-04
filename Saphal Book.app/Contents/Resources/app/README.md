# Saphal Book

Bookkeeping, accounting and audit for Nepal. Runs on your own computer, keeps
your books in Bikram Sambat, and costs nothing to run because there is nothing
to run it on but the machine in front of you.

Written in the Python standard library alone. No packages to install, no
account to open, no subscription, no internet needed after you have it.

```
Bikram Sambat throughout, checked against known historical dates
Money held as whole paisa, so the trial balance ties to the last one
The Nepali chart of accounts, presented the way NFRS and NAS ask for
VAT, tax deducted at source, stock, bank reconciliation, fixed assets
Financial statements with last year beside this year, notes behind every line
Depreciation under Schedule 2 of the Income Tax Act, 2058, on the pool basis
Deferred tax, financial instruments, cash flows under NAS 07
Audit tools: analytical review, ratios, ageing, trial balance import
Click any figure and it opens what is behind it, down to the voucher
```

## Download it

**Mac.** [**Download Saphal Book for Mac**](https://github.com/saphalism007/chartered-book/raw/main/download/Chartered%20Book%20for%20Mac.zip)
Unzip it and double click Saphal Book. Nothing to install, macOS already has
what it needs.

The first time you open it, macOS will say it cannot check the developer. That
is normal for any app not sold through the App Store. **Right click the app,
choose Open, then click Open again** on the box that appears. You only do that
once.

**Windows.** [**Download Saphal Book for Windows**](https://github.com/saphalism007/chartered-book/raw/main/download/Chartered%20Book%20for%20Windows.zip)
Install Python once from [python.org](https://www.python.org/downloads/),
ticking **Add Python to PATH** on the first screen of the installer. Then unzip
this and double click `Saphal Book.vbs`.

**Phone or tablet.** It runs on the computer that holds the books, and the
phone opens it over your wifi. Start it with *run on wifi*, and it prints the
address to type into the phone's browser. Then choose Install, or Add to Home
Screen, and it gets its own icon.

## Building it yourself instead

If you have taken the source rather than a download, build the Mac app once
with `python3 tools/make_mac_app.py` and double click the result from then on.

Your books are kept outside the software, in the place your operating system
sets aside for application data, so replacing the software never touches them.

## A word on what this is

It was written for two hardware shops and a chartered accountancy practice in
Nepal, and it is used on them. It is not a product and there is nobody to ring.
If it is useful to you, take it.

---

## Starting it

**On this Mac.** Double click **Saphal Book** (the icon with the ledger
page). The browser opens at the books by itself. Nothing else to do, and no
terminal window.

Drag it to your Applications folder, or keep it in the Dock, so it is always
one click away.

Opening it a second time does not start a second copy. It just brings the books
back up. It keeps running quietly after you close the browser, so it is ready
next time. To stop it fully, right click the icon in the Dock and choose Quit,
which also takes a closing backup.

**On a Windows computer.** See [docs/WINDOWS.md](docs/WINDOWS.md). In short:
install Python once from python.org, copy this folder onto the computer, and
double click **Saphal Book.vbs**. No black console window appears. Right
click it and Send to Desktop to make a shortcut.

**On a phone or tablet.** Open **Use on your phone** inside Saphal Book. It
shows the address to type into the browser on the phone, and the steps to add
it to the home screen for iPhone, iPad, Android and Windows. The phone reads
the books over your own wifi, so this computer has to be on and Saphal Book
running. Nothing goes over the internet.

**From a terminal**, if you ever want to:

    python3 start.py            this computer only
    python3 start.py --lan      also answer phones on the same wifi

## The first time

1. Choose a username and password. Write the password somewhere safe. There is
   no recovery, because there is no server anywhere to recover it from.
2. Create your first company. You choose whether it sells **goods only**,
   **services only**, or **both**, and the screens follow that choice. A
   practice that bills its time is never shown stock screens.
3. Set the date the books begin, usually 1 Shrawan. Nothing can be posted
   before that date.

Creating a company lays out 210 or more ledgers arranged the way NFRS and NAS
statements are presented in Nepal, thirty units, the voucher types, and the TDS
sections. You can add to any of it.

Each company keeps its books in its own file, so nothing can leak from one into
another. Add as many companies as you like and switch from the box at the top
left.

---

## Where everything is kept

On this Mac:

    ~/Library/Application Support/Saphal Book/

    books/            one file for each company, this is your books
    backups/          every backup, one zip each
    system.db         the list of users and companies
    chartered-book.log  what the software would have printed if it had a window

On Windows it is `C:\Users\<your name>\AppData\Local\Saphal Book`.

That folder is the thing to keep safe. Copying it to another computer, next to
the same software, moves everything across.

The books are deliberately not kept in Documents. macOS refuses an application
opened from the Finder permission to read or write anything in Documents or on
the Desktop unless it is granted, and it refuses silently, so the icon would
simply do nothing. Application Support is the folder macOS sets aside for
exactly this.

The Backup and safety screen shows the path at any time, so you never have to
remember it.

### Backups

A backup is taken automatically **each time the software starts and again when
it closes**. You can take one at any moment from **Backup and safety**, or from
**Back up now** at the bottom left. The last thirty automatic ones are kept and
every one you take by hand is kept for good.

**Keep a second copy somewhere else.** A backup on the same disk protects you
from a mistake, not from the disk failing. On the Backup and safety screen,
name another folder and every backup is copied there as well, the moment it is
taken.

If you point that at your Google Drive, OneDrive or Dropbox folder on the
machine, the copy uploads itself the next time the machine is online. On a Mac
the Drive folder sits under Library, CloudStorage, in a folder named after the
account. On Windows it is usually under your user folder.

The Backup and safety screen finds whichever of those you have and offers each
one as a button, so there is no path to type.

There is deliberately no Google account connected inside the software. That
would mean keys that expire, a sign in that breaks when Google changes
something, and your books passing through an account link. Letting Drive sync a
folder does the same job, keeps working when the internet is down, and there is
nothing to renew.

Restoring takes a safety copy of the present state first, so a restore started
by mistake can itself be undone.

---

## How the books are kept

- **Every amount is a whole number of paisa.** No decimals are stored, so the
  trial balance ties exactly and stays tied.
- **Every voucher must balance** before it can be saved. Debit and credit are
  checked to the paisa.
- **A posted voucher is never deleted.** It is cancelled, keeping its number
  and recording who cancelled it and why, so a gap in an invoice series can
  always be explained to a tax officer. Only a draft can be removed outright.
- **Everything is written to the audit trail** with the user and the time,
  including what the record looked like before the change.
- **Stock is kept on the periodic basis**, which is what most trading houses in
  Nepal and their auditors work on. A sales invoice does not post cost of goods
  sold. The stock ledger records every movement in quantity and value, and the
  closing stock entry brings the value into the accounts at period end. Run it
  again after a late invoice and it posts only the difference.

### Dates

The fiscal year runs 1 Shrawan to the last day of Ashadh. Type dates in Bikram
Sambat and the Gregorian date is shown beside it. Inside a date box:

    +  or  =     next day
    -  or  _     previous day
    Page Up      next week
    Page Down    previous week
    F4           open the calendar
    double click open the calendar

The calendar covers Bikram Sambat 2000 to 2099 and is checked against known
historical dates in the tests.

### Value added tax

The standard rate is 13 percent under the Value Added Tax Act, 2052. Sales VAT
collects in **2241 VAT Output Payable**, purchase VAT in **1241 VAT Input
Credit**. The VAT return screen sets one against the other for a Nepali month
and shows the sales and purchase registers in the layout the Inland Revenue
Department asks for. A return is due by the 25th of the following month, and
the screen shows that date.

### Tax deducted at source

The common rates are set up as ledgers under **2250 Tax Deducted at Source**.
Rates change with each Finance Act, so confirm the rate for the year before
filing.

---

## Reports

Every figure can be opened. Click a line on a statement and it shows the group
behind it, click the group and it shows the ledgers, click a ledger and it shows
the year month by month, click a month and it shows the vouchers, click a
voucher and the voucher itself appears. The trail across the top says where you
are and takes you back a step.

**Financial statements** puts the whole set on one screen, with last year beside
this year on every line:

- Statement of Financial Position, in the vertical form NAS 01 sets out, with a
  note number against each line. Fixed assets appear at their carrying amount,
  with cost and depreciation split out in the note behind
- Statement of Profit or Loss and Other Comprehensive Income
- Statement of Changes in Equity
- Statement of Cash Flows, indirect method under NAS 07, checked against the
  movement the cash and bank ledgers actually show and saying so either way
- Notes, a numbered schedule behind every line on the face of the statements
- Fixed asset schedule, the movement in cost and in depreciation, both years
- Intangible asset schedule, the same for software, goodwill and licences
- Fixed asset register, asset by asset, with what each one cost and what it is
  carried at
- Depreciation under Schedule 2 of the Income Tax Act, 2058, pool by pool, with
  an addition absorbed in full, two thirds or one third depending on when in the
  year it was bought, and a pool under two thousand rupees written off in full
- Deferred tax under NAS 12, what the books carry against what the tax working
  carries, and the tax effect of the difference
- Financial instruments under NFRS 7, by measurement category, with when the
  liabilities fall due, where the credit risk sits, and what is deliberately not
  a financial instrument
- Trading and Profit and Loss Account, the traditional two sided form many
  Nepali proprietors and auditors read first

The other reports are:

    Trial balance        opening, movement and closing for every ledger
    Ledger               one account in full, with a running balance
    Group summary        the whole chart of accounts as a tree you can open
    Stock                quantity and value at weighted average cost
    Receivable, payable  who owes what
    Ageing               how old the money owed is, bill by bill
    Bank reconciliation  the working, and what explains the difference
    VAT return           the monthly position with both registers
    Day book             everything posted, in date order

Ctrl and P prints whatever is on screen, laid out for paper rather than for the
browser.

---

## Fixed assets

Under Records, Fixed assets, there is a row for each thing the business owns:
what it cost, when it was bought, how the books write it down, and which class
it falls in under Schedule 2 of the Income Tax Act, 2058.

    Class A    5%   Buildings and structures of a permanent nature
    Class B   25%   Computers, fixtures, office furniture and office equipment
    Class C   20%   Automobiles, buses and minibuses
    Class D   15%   Construction and earth moving plant, and anything not in
                    another class
    Class E         Intangibles, written off over their useful life

What the books charge and what the Act allows are kept apart on purpose,
because they hardly ever agree. The difference between them is what the
deferred tax working is built on, and both come out of this one register.

Recording a disposal takes what the asset sold for out of the tax pool, which
is how Schedule 2 works. It does not post the entry that removes it from the
ledgers, so pass that yourself.

Rates change with the Finance Act. Check the rate for the year before a working
is used in a return.

---

## Keyboard

    F1  dashboard          F5  sales invoice       F6  purchase bill
    F7  receipt            F8  payment             F9  journal
    F2  calculator         Ctrl and P  print the screen

Amount boxes accept arithmetic. Type `12*450` and it works the answer out when
you leave the box, which is how you add up a delivery.

Under Corrections there are the vouchers that put something right after the
event:

    Sales return         goods coming back, into stock at cost, output tax
                         reversed. The lines can be pulled from the invoice
    Purchase return      goods going back, out of stock, input tax reversed
    Credit note          a rate agreed after the invoice, or an allowance,
                         where no goods move
    Debit note           a claim on a supplier for a short delivery or a rate
                         difference
    Stock adjustment     what the count found against what the book says,
                         valued at weighted average cost, with the reason
                         deciding which account the difference goes to, so a
                         breakage, a shortage and goods taken for the house are
                         never mixed together

Anywhere you have to pick a customer, supplier, item, service or ledger, start
typing. If it is not there, the last line of the list says **Add**, and you can
create it without losing the invoice you are in the middle of. Adding an item
lets you add a unit or a group from inside that, and comes straight back.

---

## Trying it out safely

    python3 tools/demo_data.py

builds a demonstration hardware shop with suppliers, customers, stock,
invoices, payments and a closing stock entry, so you can try any screen without
touching real books.

    python3 tools/demo_data.py --remove

deletes it again. It never touches any other company.

---

## Checking it still adds up

    python3 -m tests.test_nepali_date
    python3 -m tests.test_accounting

The first converts every day from Bikram Sambat 2000 to 2099 in both
directions and checks known historical dates. The second builds a set of books
from nothing, posts real vouchers, and proves the trial balance ties, the
balance sheet balances, stock values correctly, VAT agrees with the ledger, and
that an unbalanced voucher is refused. Both clean up after themselves.

Run these after any change.

---

## If something goes wrong

**A screen shows a red message.** The books are untouched. Move to another
screen and back.

**The browser cannot reach it.** The window that started it has probably been
closed. Start it again.

**You forgot the password.** There is no recovery. Someone with access to the
computer can create a fresh login by moving `data/system.db` aside and starting
again, but the companies then have to be added back to the list. The books
themselves in `data/books/` are untouched by this.

**You want to go back to yesterday.** Backup and safety, find the backup by its
Nepali date, and restore.

**The icon does nothing when you double click it.** Look in
`~/Library/Application Support/Saphal Book/chartered-book.log`. The last few
lines say what happened. If it mentions Python, install Python from python.org
and try again.

**The phone cannot reach it.** Check that the phone is on the same wifi, that
this computer is awake, and that the address on the Use on your phone screen
matches what you typed. The address changes if the router gives this computer a
new one, so check it there rather than remembering it.

---

## Rebuilding the Mac app after a change

The app carries its own copy of the software, which is what lets it work
without asking macOS for permission to read Documents. After any change to the
code, run this once to bring the app up to date:

    python3 tools/make_mac_app.py

The books are never inside the app, so rebuilding it cannot touch them.

---

## What is inside

    chartered_book/core/      calendar, money, database, chart of accounts,
                              users, audit trail, backup
    chartered_book/modules/   companies, posting, masters, invoices, reports,
                              period end, banking
    chartered_book/web/       the local server, the API, and the screens
    tools/                    icon drawing and the demonstration data
    tests/                    the accuracy tests
    docs/DECISIONS.md         why things are built the way they are

Python standard library only. Nothing to install, nothing to subscribe to,
nothing that phones home.

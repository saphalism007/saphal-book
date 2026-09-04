# Putting Saphal Book on GitHub

A step by step guide. No terminal, no commands to type.

## What this does, and why

GitHub is a free website that holds software. Putting Saphal Book there
gives you a web address, and anyone you send that address to can download their
own copy.

Your books do not go to GitHub. Only the software goes. Your books live in a
separate place on this Mac and are deliberately kept out.

You need a free GitHub account. If you do not have one, make it first at
**github.com**, then come back here.

---

## Step 1. Open the file

In the Finder, in this folder, find the file called:

**Put on GitHub**

Double click it.

A black window called Terminal will open. That is normal. You do not have to
type any commands into it. It will ask you questions and you answer them.

> **If you get a warning** saying the file cannot be opened because it is from
> an unidentified developer, right click the file instead, choose **Open**, and
> then click **Open** on the box that appears. You only need to do that once.

---

## Step 2. Create the empty repository

The window will check that no books are being sent, then open a page in your
browser called **Create a new repository**.

On that page:

1. The **Repository name** box will already say `chartered-book`. Leave it.
2. Below that, click the circle next to **Public**.
3. **Do not tick anything else.** Leave the readme, the .gitignore and the
   licence boxes all unticked. This matters. If you tick them the repository
   will not be empty and the next step will fail.
4. Scroll down and click the green **Create repository** button.

Now go back to the Terminal window and press the **Enter** key.

---

## Step 3. Copy the address

After you clicked Create, GitHub took you to a new page. Near the top of that
page there is a box with an address in it that looks like this:

```
https://github.com/yourname/chartered-book.git
```

There is a small copy button beside it. Click that button. That copies the
address.

---

## Step 4. Paste it

Go back to the Terminal window. It is asking you to paste the address.

Click once inside the Terminal window, then press **Command** and **V**
together to paste. You will see the address appear.

Press **Enter**.

---

## Step 5. Done

The window will say **DONE** and show you your link. It looks like:

```
https://github.com/yourname/chartered-book
```

That page will also open in your browser by itself.

**That address is your link.** Send it to anyone. When they open it, they click
the green **Code** button, then **Download ZIP**, and they have their own copy
of Saphal Book.

---

## If it did not work

Nothing is broken and nothing was damaged. You can double click
**Put on GitHub** again as many times as you like.

**"It did not go through"** usually means one of four things:

- You had not created the repository on github.com yet
- The address was pasted wrong, so try copying it again
- You ticked one of the boxes in step 2, so the repository is not empty.
  Delete it on GitHub and make a new one with nothing ticked
- GitHub did not recognise you. Open **github.com** in your browser, sign in
  there, then double click the file again

**If it says it stopped because it found books**, do not continue. Tell Claude
exactly what it printed.

---

## After it is up

Every time you change something and want the website updated, double click
**Put on GitHub** again. It will remember the address and just send the
changes.

---

## The other way to share, if you would rather not use GitHub

There is a zip file in this folder called something like
**Saphal Book 2083-05-18.zip**.

Put that in your Google Drive, right click it in Drive, choose **Share**, and
send the link. It works exactly the same for whoever receives it. No GitHub
account needed by anybody.

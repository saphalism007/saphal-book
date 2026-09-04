# Turning the website on

One switch. It takes about a minute, plus a minute of waiting.

## Why this is needed

The files are already on GitHub. GitHub just has not been told to serve them as
a website yet. Until it is, every address gives a 404.

The 404 you saw came from your other site, `saphalism007.github.io`. That one is
switched on, so it answers, and then says it has no file by that name. It is not
a sign that anything is broken.

## Do this

1. Open this address:

       https://github.com/saphalism007/chartered-book/settings/pages

   If it asks you to sign in, sign in.

2. You will see a heading that says **Build and deployment**, and under it
   **Source**.

3. Set **Source** to **Deploy from a branch**.

4. Two dropdown boxes appear underneath.

   - Set the first one, the branch, to **main**
   - Set the second one, the folder, to **/docs**

   If **/docs** is not offered, choose **/ (root)** instead. Either works now.

5. Click **Save**.

6. A yellow or blue bar appears saying your site is being built. **Wait one to
   two minutes.** This is the part people give up on too early.

7. Reload that same settings page. The bar turns green and shows your address.

## Your addresses

Once the bar is green:

**The page you send people**

    https://saphalism007.github.io/chartered-book/

**The app itself, to open on an iPad or Android**

    https://saphalism007.github.io/chartered-book/app/

Open that second one in **Safari** on an iPad, or **Chrome** on Android. Wait a
few seconds the first time while the accounting engine loads. Then add it to
the home screen and it behaves like any other app.

## If it still says 404 after the bar goes green

Wait another two minutes and reload. The first build is the slow one.

If it is still 404 after five minutes, go back to the settings page and check
the folder. Both **/docs** and **/ (root)** now work, so switching to the other
one and saving again will sort it.

## What you should see

The page has the Saphal Book icon at the top, a button saying **Open
Saphal Book in this browser**, and below that two download buttons for Mac
and Windows.

If you see that, it is working, and that address is the link to share.

#!/usr/bin/env python3
"""
Build the version that runs inside a browser.

    python3 tools/make_web_app.py

Writes docs/app, which GitHub Pages serves. Opening that address on an iPad or
an Android phone loads the whole Python engine into the browser through
Pyodide, so the books work with no computer involved and no server anywhere.

The same Python that runs on the Mac is what gets loaded. Nothing about the
accounting is rewritten for the browser, so a figure worked out on a phone
comes off exactly the same code, and the tests that cover one cover both.

The books made this way live in the browser's own storage on that device. They
are a separate set from the ones on the computer and do not sync with them.
"""

import json
import os
import shutil
import sys
import zipfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "docs", "app")
PKG = os.path.join(HERE, "chartered_book")
STATIC = os.path.join(PKG, "web", "static")

PYODIDE = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/"


def build_package_zip(target):
    """Everything Python, as one archive the browser unpacks in one go."""
    count = 0
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for root, dirs, files in os.walk(PKG):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for name in files:
                if not name.endswith(".py"):
                    continue
                full = os.path.join(root, name)
                archive.write(full, os.path.relpath(full, HERE))
                count += 1
    return count


def copy_static(target_dir):
    os.makedirs(target_dir, exist_ok=True)
    copied = 0
    for name in sorted(os.listdir(STATIC)):
        source = os.path.join(STATIC, name)
        if os.path.isdir(source):
            shutil.copytree(source, os.path.join(target_dir, name), dirs_exist_ok=True)
            copied += len(os.listdir(source))
        elif name.endswith((".js", ".css", ".json")):
            shutil.copy2(source, os.path.join(target_dir, name))
            copied += 1
    return copied


# The screens, in the order the page loads them. The service worker keeps
# exactly these addresses, so the two are made from the one list.
SCRIPTS = ["nepali.js", "ui.js", "app.js", "masters.js", "vouchers.js",
           "drill.js", "reports.js", "statements.js", "banking.js",
           "assets.js", "incometax.js", "analysis.js", "recurring.js", "quotations.js",
           "audit.js"]


def shell_html(stamp="1"):
    """
    The page the browser opens.

    It shows a loading screen straight away, because bringing Python into a
    browser takes a few seconds the first time and a blank screen would look
    broken. Afterwards it is cached and opens quickly.
    """
    tags = "\n".join('<script src="static/%s?v=%s"></script>' % (s, stamp)
                     for s in SCRIPTS)
    source = open(os.path.join(PKG, "web", "templates", "index.html"), encoding="utf-8").read()

    body_start = source.index("<body>") + len("<body>")
    body_end = source.index("<script src=")
    body = source[body_start:body_end]

    return """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Saphal Book</title>
<meta name="description" content="Bookkeeping and accounts for Nepal, running in your browser.">
<meta name="theme-color" content="#1d3557">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Saphal Book">
<meta name="mobile-web-app-capable" content="yes">
<link rel="manifest" href="manifest.webmanifest">
<link rel="icon" type="image/png" sizes="192x192" href="static/icons/icon-192.png?v=2">
<link rel="icon" sizes="any" href="static/icons/icon-192.png?v=2">
<link rel="apple-touch-icon" href="static/icons/icon-180.png?v=2">
<link rel="stylesheet" href="static/style.css?v=__STAMP__">
<style>
#starting{position:fixed;inset:0;display:grid;place-items:center;background:var(--ground);z-index:200}
#starting .inner{text-align:center;max-width:22rem;padding:1.5rem}
#starting img{width:72px;height:72px;border-radius:18px}
#starting h1{font-size:1.15rem;margin:1rem 0 .3rem}
#starting p{color:var(--ink-soft);font-size:.88rem;margin:0 0 .2rem}
#starting .step{color:var(--ink-faint);font-size:.8rem;margin-top:.9rem;min-height:1.2rem}
#starting .bar{height:3px;background:var(--line);border-radius:3px;overflow:hidden;margin-top:1rem}
#starting .bar span{display:block;height:100%;width:0;border-radius:3px;
  background:linear-gradient(90deg,var(--brand),var(--teal));transition:width .4s}
#starting .slow{display:none;color:var(--ink-faint);font-size:.76rem;margin-top:1.1rem;line-height:1.5}
#starting .slow.shown{display:block}
</style>
</head>
<body>

<div id="starting">
  <div class="inner">
    <img src="static/icons/icon-192.png" alt="">
    <h1>Saphal Book</h1>
    <p>Bookkeeping and accounts for Nepal</p>
    <div class="bar"><span id="startbar"></span></div>
    <div class="step" id="startstep">Starting</div>
    <div class="slow" id="startslow">Setting up on this device for the first
      time, which needs the internet once. After this it opens from the device.</div>
  </div>
</div>

__BODY__

<script>
window.CHARTERED_BOOK_WEB = true;
window.SAPHAL_BUILD = "__STAMP__";
if ("serviceWorker" in navigator) {
  window.addEventListener("load", function () {
    // A new version is fetched quietly in the background and used the next
    // time Saphal Book is opened. It never restarts a page somebody is using.
    //
    // It used to. When a new version arrived the open page reloaded itself,
    // so after every update the loading screen ran twice, and while updates
    // were going out several times a day that was most openings. Reloading a
    // page in the middle of an entry is also the one way to lose what is
    // typed into it.
    navigator.serviceWorker.register("sw.js", { updateViaCache: "none" })
      .then(function (reg) {
        var asked = Date.now();
        reg.update().catch(function () { /* offline, try later */ });
        // A phone keeps an app in the background for days, so ask again when
        // it comes back to the front, but not more than every fifteen minutes.
        document.addEventListener("visibilitychange", function () {
          if (document.visibilityState !== "visible") { return; }
          if (Date.now() - asked < 15 * 60 * 1000) { return; }
          asked = Date.now();
          reg.update().catch(function () { /* offline, try later */ });
        });
      }).catch(function () { /* nothing lost */ });
  });
}
</script>
<script src="boot.js?v=__STAMP__"></script>
__SCRIPTS__
</body>
</html>
""".replace("__BODY__", body).replace("__SCRIPTS__", tags)\
     .replace("__STAMP__", stamp)


def engine_js(stamp="1"):
    """
    The accounting engine, on a thread of its own.

    It used to run on the same thread that draws the screen, which is the
    ordinary way to do this and the reason the software froze. Python compiled
    to WebAssembly has no sockets, so every request it makes to a server has to
    be the blocking kind, and blocking on the drawing thread stops the page
    dead: no click lands and nothing repaints until the answer comes back. A
    backup uploading to Google Drive was measured at just under six seconds with
    the page frozen for all of it.

    Here the blocking is harmless. This thread has nothing to draw, so it can
    wait as long as it likes while the screen carries on.

    Everything it needs from the browser proper is handed to it at the start,
    because a worker cannot reach the window: what to call this device, and the
    sign in token, which lives in storage the worker cannot see and therefore
    travels with each call.
    """
    return """/* The accounting engine, on a thread of its own. See engine_js in
   tools/make_web_app.py for why. */

var PYODIDE = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/";
var ENGINE_STORE = "saphal-book-engine";
var SNAPSHOT = new URL("python-ready-v0.26.4", self.location).href;
var ZIP = new URL("chartered_book.zip?v=__STAMP__", self.location).href;
var BOOKS = "/books";
var pyodide = null;
var dispatch = null;
var fromSnapshot = false;
var realFetch = self.fetch.bind(self);

// How long each part of starting took, kept so a slow opening on somebody's
// phone can be looked into rather than guessed at.
var timings = [];
var lastMark = performance.now();
var lastName = "Before starting";
function mark(name) {
  var now = performance.now();
  timings.push([lastName, Math.round(now - lastMark)]);
  lastMark = now;
  lastName = name;
}

function step(text, portion, first) {
  mark(text);
  self.postMessage({ kind: "step", text: text, portion: portion, first: !!first });
}

function save() {
  return new Promise(function (resolve) {
    try { pyodide.FS.syncfs(false, function () { resolve(); }); }
    catch (error) { resolve(); }
  });
}

/* The engine, out of this device's own store.

   It is about twelve megabytes, from a different address, and it never
   changes for a given version. It used to be left to the service worker to
   answer from its store, and the service worker is not asked by every
   browser about requests made from inside a worker thread. Where it is not,
   the engine came over the internet, or out of an ordinary cache that a
   phone empties whenever it wants the room. So the engine is read out of the
   store here, directly, and only fetched when it is not there. */
function engineFile(url) {
  return caches.open(ENGINE_STORE).then(function (store) {
    return store.match(url).then(function (hit) {
      if (hit) { return hit; }
      return realFetch(url).then(function (response) {
        if (response && response.ok) {
          store.put(url, response.clone()).catch(function () { /* full, fine */ });
        }
        return response;
      });
    });
  }, function () { return realFetch(url); });
}

self.fetch = function (input, init) {
  var url = typeof input === "string" ? input : ((input && input.url) || String(input));
  if (url.indexOf(PYODIDE) === 0) { return engineFile(url); }
  return realFetch(input, init);
};

function engineIsHere() {
  return caches.open(ENGINE_STORE)
    .then(function (store) { return store.match(PYODIDE + "pyodide.asm.wasm"); })
    .then(function (hit) { return !!hit; }, function () { return false; });
}

/* Saphal Book itself, which is the same file for the whole of one version,
   so the copy on the device is used whenever there is one. Asked for as soon
   as this thread starts, so it is in hand by the time Python wants it rather
   than being waited for afterwards. */
function appFile() {
  return caches.match(ZIP).then(function (hit) {
    if (hit) { return hit.arrayBuffer(); }
    return realFetch(ZIP, { cache: "no-cache" }).then(function (response) {
      if (!response.ok) { throw new Error("the Saphal Book file is missing"); }
      return response.arrayBuffer();
    });
  });
}

/* Python, ready to go.

   Starting Python is most of the wait, and it is the same work every time:
   nothing about it depends on the books. So the first time it is started the
   result is saved, and every time after it is picked up from there, which
   was measured at thirty milliseconds against half a second, and a phone is
   slower than that.

   This is an experimental feature of the engine. Anything at all that goes
   wrong with the saved copy throws it away and starts Python the ordinary
   way, so the worst it can do is be no faster than before. */
function readSnapshot() {
  return caches.open(ENGINE_STORE)
    .then(function (store) { return store.match(SNAPSHOT); })
    .then(function (hit) { return hit ? hit.arrayBuffer() : null; })
    .then(function (buffer) { return buffer ? new Uint8Array(buffer) : null; },
          function () { return null; });
}

function forgetSnapshot() {
  return caches.open(ENGINE_STORE)
    .then(function (store) { return store.delete(SNAPSHOT); })
    .catch(function () { /* nothing to forget */ });
}

function keepSnapshot(bytes) {
  return caches.open(ENGINE_STORE)
    .then(function (store) { return store.put(SNAPSHOT, new Response(bytes)); })
    .catch(function () { /* no room, it is simply slower next time */ });
}

async function startPython(useSnapshot) {
  fromSnapshot = false;
  if (useSnapshot) {
    var stored = await readSnapshot();
    if (stored) {
      try {
        var restored = await loadPyodide({ indexURL: PYODIDE, _loadSnapshot: stored });
        restored.runPython("import sys, os, json");
        fromSnapshot = true;
        return { py: restored, made: null };
      } catch (error) {
        await forgetSnapshot();
      }
    }
  }
  try {
    var fresh = await loadPyodide({ indexURL: PYODIDE, _makeSnapshot: true });
    var made = null;
    try { made = fresh.makeMemorySnapshot(); } catch (error) { made = null; }
    return { py: fresh, made: made };
  } catch (error) {
    // An engine that does not know about saving: start it the ordinary way.
    return { py: await loadPyodide({ indexURL: PYODIDE }), made: null };
  }
}

async function open(device, zip, useSnapshot, first) {
  step(first ? "Fetching the accounting engine" : "Starting", 0.15, first);
  if (typeof loadPyodide === "undefined") { importScripts(PYODIDE + "pyodide.js"); }

  var started = await startPython(useSnapshot);
  pyodide = started.py;

  step("Loading the database", 0.5, first);
  await pyodide.loadPackage("sqlite3");

  step("Opening your books", 0.62, first);
  pyodide.FS.mkdirTree(BOOKS);
  pyodide.FS.mount(pyodide.FS.filesystems.IDBFS, {}, BOOKS);
  await new Promise(function (resolve) {
    pyodide.FS.syncfs(true, function () { resolve(); });
  });

  step("Unpacking Saphal Book", 0.78, first);
  await pyodide.unpackArchive(await zip, "zip");

  step("Setting it up", 0.9, first);
  pyodide.runPython(
    "import os, sys\\n" +
    "os.environ['CHARTERED_BOOK_DATA'] = '" + BOOKS + "'\\n" +
    "os.environ['SAPHAL_DEVICE'] = " + JSON.stringify(device || "") + "\\n" +
    "sys.path.insert(0, '/')\\n" +
    "from chartered_book.web import embedded\\n"
  );
  dispatch = pyodide.runPython("embedded.dispatch");
  await save();
  return started.made;
}

async function start(device) {
  var first = !(await engineIsHere());
  var zip = appFile();
  zip.catch(function () { /* reported when it is needed */ });
  var made = null;
  try {
    made = await open(device, zip, true, first);
  } catch (error) {
    if (!fromSnapshot) {
      return self.postMessage({ kind: "failed",
                                detail: String((error && error.message) || error || "") });
    }
    // Something went wrong after starting from the saved Python. Throw it
    // away and do the whole thing again the ordinary way.
    await forgetSnapshot();
    try {
      made = await open(device, appFile(), false, first);
    } catch (again) {
      return self.postMessage({ kind: "failed",
                                detail: String((again && again.message) || again || "") });
    }
  }
  step("Ready", 1, first);
  self.postMessage({ kind: "ready", fromSnapshot: fromSnapshot, timings: timings });
  if (made) { keepSnapshot(made); }
}

self.onmessage = async function (event) {
  var msg = event.data || {};

  if (msg.kind === "start") { return start(msg.device); }

  if (msg.kind === "call") {
    var answer;
    try {
      answer = dispatch(msg.method || "GET", msg.path,
                        JSON.stringify(msg.query || {}),
                        JSON.stringify(msg.body || {}),
                        msg.token || "");
    } catch (error) {
      return self.postMessage({ id: msg.id, kind: "answer", failed: true,
                                error: String((error && error.message) || error) });
    }
    // A write goes back into the browser's storage before the screen is told
    // it worked, so a tab closed a moment later has not lost it.
    var writing = msg.method && msg.method.toUpperCase() !== "GET";
    if (writing) { await save(); }
    return self.postMessage({ id: msg.id, kind: "answer", answer: answer });
  }

  if (msg.kind === "python") {
    // Kept so a problem can be looked into rather than guessed at.
    try {
      self.postMessage({ id: msg.id, kind: "answer",
                         answer: JSON.stringify({ result: String(pyodide.runPython(msg.code)) }) });
    } catch (error) {
      self.postMessage({ id: msg.id, kind: "answer", failed: true,
                         error: String((error && error.message) || error) });
    }
  }
};
""".replace("__STAMP__", stamp)


def boot_js(stamp="1"):
    return """/* Bringing the books up inside a browser.

   The accounting engine is Python compiled to WebAssembly, and it runs on a
   thread of its own rather than the one that draws the screen. That is the
   whole point of this file: what is left here is a thin messenger between the
   screens and that thread, so nothing the engine does can stop the page.

   The engine is the same one that runs on a computer, so nothing about the
   accounting changes. */

window.CB = (function () {
  "use strict";

  var worker = null;
  var ready = false;
  var nextId = 1;
  var waiting = {};
  var TOKEN_KEY = "cb_token";

  function step(text, portion, first) {
    var line = document.getElementById("startstep");
    var bar = document.getElementById("startbar");
    var slow = document.getElementById("startslow");
    if (line) { line.textContent = text; }
    if (bar) { bar.style.width = Math.round(portion * 100) + "%"; }
    // Only the first time is slow, so only the first time says so. It used to
    // say it every time, which made every opening look like the first.
    if (slow) { slow.className = first ? "slow shown" : "slow"; }
  }

  function fail(message, detail) {
    var line = document.getElementById("startstep");
    if (line) {
      line.innerHTML = "";
      var strong = document.createElement("div");
      strong.textContent = message;
      strong.style.color = "var(--bad)";
      strong.style.fontWeight = "600";
      line.appendChild(strong);
      if (detail) {
        var small = document.createElement("div");
        small.textContent = detail;
        small.style.fontSize = ".76rem";
        small.style.marginTop = ".4rem";
        line.appendChild(small);
      }
    }
    try { console.error("[Saphal Book]", message, detail); } catch (ignored) {}
  }

  function token() {
    try { return localStorage.getItem(TOKEN_KEY) || ""; } catch (e) { return ""; }
  }

  function setToken(value) {
    try {
      if (value) { localStorage.setItem(TOKEN_KEY, value); }
      else { localStorage.removeItem(TOKEN_KEY); }
    } catch (e) { /* private browsing, the session lasts the visit */ }
  }

  /* What to call this device.

     Worked out here rather than in the engine, twice over. Inside the engine
     every browser in the world calls itself emscripten, so two devices signed
     in to the same account were both named the same thing and a person being
     asked which copy to keep was offered the same answer twice. And the two
     things that say whether this is an installed app rather than a tab are on
     the window, which the engine's thread cannot reach. */
  function deviceName() {
    var ua = navigator.userAgent || "";
    var where = "this browser";
    if (/iPad/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1)) {
      where = "iPad";
    } else if (/iPhone/.test(ua)) { where = "iPhone"; }
    else if (/Android/.test(ua)) { where = /Mobile/.test(ua) ? "Android phone" : "Android tablet"; }
    else if (/Macintosh|Mac OS X/.test(ua)) { where = "Mac"; }
    else if (/Windows/.test(ua)) { where = "Windows"; }
    else if (/CrOS/.test(ua)) { where = "Chromebook"; }
    else if (/Linux/.test(ua)) { where = "Linux"; }

    var browser = "";
    if (/Edg\\//.test(ua)) { browser = "Edge"; }
    else if (/OPR\\//.test(ua)) { browser = "Opera"; }
    else if (/Firefox\\//.test(ua)) { browser = "Firefox"; }
    else if (/Chrome\\//.test(ua)) { browser = "Chrome"; }
    else if (/Safari\\//.test(ua)) { browser = "Safari"; }

    var installed = window.matchMedia
      && window.matchMedia("(display-mode: standalone)").matches;
    if (installed || window.navigator.standalone) { return "Saphal Book on " + where; }
    return browser ? browser + " on " + where : where;
  }

  /* The one call the screens make. Same shape as a request to the server.

     It goes to the other thread and comes back, so the screen is free the
     whole time it is away. Nothing here waits on anything. */
  function call(method, path, query, body) {
    if (!ready) { return Promise.reject(new Error("The books are still starting.")); }
    var id = nextId += 1;
    return new Promise(function (resolve, reject) {
      waiting[id] = { resolve: resolve, reject: reject };
      worker.postMessage({ kind: "call", id: id, method: method || "GET", path: path,
                           query: query || {}, body: body || {}, token: token() });
    });
  }

  function settle(msg) {
    var pending = waiting[msg.id];
    if (!pending) { return; }
    delete waiting[msg.id];
    if (msg.failed) { return pending.reject(new Error(msg.error || "That did not work.")); }

    var parsed;
    try { parsed = JSON.parse(msg.answer); }
    catch (error) { return pending.reject(new Error("The books gave an unreadable answer.")); }

    if (parsed.token) { setToken(parsed.token); }
    if (parsed.clear_token) { setToken(""); }
    if (parsed.status >= 400) {
      var error = new Error((parsed.payload && parsed.payload.error) || "That did not work.");
      error.status = parsed.status;
      return pending.reject(error);
    }
    pending.resolve(parsed.payload);
  }

  function runPython(code) {
    var id = nextId += 1;
    return new Promise(function (resolve, reject) {
      waiting[id] = { resolve: resolve, reject: reject };
      worker.postMessage({ kind: "python", id: id, code: code });
    });
  }

  function start() {
    try {
      worker = new Worker("engine.js?v=__STAMP__");
    } catch (error) {
      return fail("Saphal Book could not start.",
                  "This browser would not start the accounting engine. "
                  + String((error && error.message) || error));
    }
    worker.onerror = function (event) {
      fail("Saphal Book could not start.",
           "The first load needs the internet. Check the connection and open it again. "
           + "If it keeps failing: " + String((event && event.message) || ""));
    };
    worker.onmessage = function (event) {
      var msg = event.data || {};
      if (msg.kind === "step") { return step(msg.text, msg.portion, msg.first); }
      if (msg.kind === "answer") { return settle(msg); }
      if (msg.kind === "failed") {
        return fail("Saphal Book could not start.",
                    "The first load needs the internet. Check the connection and open "
                    + "it again. If it keeps failing: "
                    + String(msg.detail || "").split(String.fromCharCode(10))[0].slice(0, 160));
      }
      if (msg.kind === "ready") {
        ready = true;
        window.CB.ready = true;
        window.CB.startedIn = Math.round(performance.now());
        window.CB.fromSnapshot = !!msg.fromSnapshot;
        window.CB.timings = msg.timings || [];
        var screen = document.getElementById("starting");
        if (screen) { screen.style.display = "none"; }
        document.dispatchEvent(new Event("saphal-book-ready"));
      }
    };
    worker.postMessage({ kind: "start", device: deviceName() });
  }

  document.addEventListener("DOMContentLoaded", start);

  return { call: call, ready: false,
           // Writing already reaches the browser's storage before the screen
           // is told it worked, so there is nothing here left to flush.
           save: function () { return Promise.resolve(); },
           token: token, setToken: setToken,
           runPython: runPython };
}());
""".replace("__STAMP__", stamp)


def build_stamp():
    """
    A short name for this build, worked out from what is in it.

    Every file that goes to the device is read and summed. Change any of them
    and the name changes, which is what tells a browser its stored copy is no
    longer the current one.
    """
    import hashlib
    digest = hashlib.sha256()
    for root, _dirs, files in sorted(os.walk(OUT)):
        for name in sorted(files):
            # These three carry the stamp, so they cannot be part of what it
            # is worked out from.
            if name in ("sw.js", "index.html", "boot.js", "engine.js"):
                continue
            with open(os.path.join(root, name), "rb") as handle:
                digest.update(handle.read())
    # And the files that carry the stamp, as they would be without it. They
    # were left out entirely, so a change to how Saphal Book starts, which
    # lives only in those, kept the old name, and a device holding the old
    # copy under that name went on using it.
    for template in (shell_html, engine_js, boot_js, worker_js):
        digest.update(template("").encode("utf-8"))
    return digest.hexdigest()[:12]


def worker_js(stamp="1"):
    """
    Keeps this build on the device after the first visit.

    The name of the store is worked out from the contents of the build, not
    written by hand. It used to be a fixed string, which meant a browser that had
    once loaded the software would go on serving that copy for ever: the fix was
    published, the file on the server was right, and the tablet went on showing
    the old one. Nothing short of clearing site data would have shifted it.

    The accounting engine is kept here too, and that is the part that matters
    on a tablet. It comes from a different address, so it used to be left to
    the browser's ordinary cache, and on an iPad that cache is small and is
    emptied whenever the system wants the room. The result was a loading screen
    of the same length every single time, under a message promising it would be
    quick after the first go.

    So anything fetched from the engine's address is answered out of this store
    first and only asked for over the network when it is not there. It is put
    there on the first run and it stays, because a service worker cache is not
    thrown away the way an ordinary one is.
    """
    shell = (["./", "manifest.webmanifest",
              "boot.js?v=%s" % stamp, "engine.js?v=%s" % stamp,
              "chartered_book.zip?v=%s" % stamp, "static/style.css?v=%s" % stamp,
              "static/icons/icon-192.png", "static/icons/icon-192.png?v=2",
              "static/icons/icon-180.png?v=2", "static/icons/icon-512.png"]
             + ["static/%s?v=%s" % (name, stamp) for name in SCRIPTS])
    return ("""var VERSION = "saphal-book-web-%s";
var ENGINE = "%s";
var SHELL = %s;""" % (stamp, PYODIDE, json.dumps(shell, indent=0))) + """
var ENGINE_STORE = "saphal-book-engine";

/* How this keeps Saphal Book on the device, and why it is this way round.

   Everything a version needs is fetched in one go when the version is first
   seen, into a store named after that version, and only if every piece
   arrives. From then on Saphal Book opens out of that store, with no wait for
   the internet at all. A newer version is fetched the same way, quietly, in
   the background, and used the next time Saphal Book is opened.

   It used to be the other way round: every file was asked for over the
   internet on every opening, and the copy on the device was only used when
   the internet could not be reached. On a phone that is a wait of seconds
   before anything happens, every single time, and on a weak signal a good
   deal longer, because a slow connection is not a failed one and so the copy
   on the device was never reached for. The addresses it kept did not even
   match the ones the page asks for, so the copy was never used at all.

   The one cost is that a new version shows on the opening after the one that
   noticed it, not the same one. That is how installed apps behave, and it is
   what lets an opening never wait on the network. */

self.addEventListener("install", function (event) {
  event.waitUntil(caches.open(VERSION).then(function (cache) {
    // All or nothing. A version with a piece missing would open broken, so if
    // anything fails to arrive this version is not installed and the one
    // before it carries on; it is tried again the next time.
    return cache.addAll(SHELL.map(function (url) {
      return new Request(url, { cache: "reload" });
    }));
  }).then(function () { return self.skipWaiting(); }));
});

self.addEventListener("activate", function (event) {
  event.waitUntil(caches.keys().then(function (names) {
    return Promise.all(names.map(function (name) {
      // Only this app's own older versions, and the second copy of the engine
      // an earlier version used to keep. The engine store is never touched by
      // an update: it is twelve megabytes and it has not changed.
      var oldVersion = name.indexOf("saphal-book-web-") === 0 && name !== VERSION;
      if (oldVersion || name === "saphal-book-engine-v1") { return caches.delete(name); }
      return null;
    }));
  }).then(function () { return self.clients.claim(); }));
});

function fromEngineStore(request) {
  return caches.open(ENGINE_STORE).then(function (cache) {
    return cache.match(request).then(function (hit) {
      if (hit) { return hit; }
      return fetch(request).then(function (response) {
        if (response && (response.status === 200 || response.type === "opaque")) {
          cache.put(request, response.clone());
        }
        return response;
      });
    });
  });
}

function thePage(request) {
  return caches.open(VERSION).then(function (cache) {
    return cache.match("./");
  }).then(function (hit) {
    if (hit) { return hit; }
    return fetch(request, { cache: "no-store" }).catch(function () {
      return caches.match("./");
    });
  });
}

self.addEventListener("fetch", function (event) {
  var request = event.request;
  if (request.method !== "GET") { return; }
  if (request.url.indexOf(ENGINE) === 0) {
    event.respondWith(fromEngineStore(request));
    return;
  }
  var url = new URL(request.url);
  if (url.origin !== self.location.origin) { return; }
  var scope = new URL("./", self.location).pathname;
  if (url.pathname.indexOf(scope) !== 0) { return; }

  if (request.mode === "navigate"
      && (url.pathname === scope || url.pathname === scope + "index.html")) {
    event.respondWith(thePage(request));
    return;
  }
  event.respondWith(caches.match(request).then(function (hit) {
    if (hit) { return hit; }
    return fetch(request).then(function (response) {
      // A file named with its version never changes, so it can be kept.
      if (response && response.status === 200 && url.search.indexOf("v=") !== -1) {
        var copy = response.clone();
        caches.open(VERSION).then(function (cache) { cache.put(request, copy); });
      }
      return response;
    });
  }));
});
"""


def manifest():
    return """{
  "name": "Saphal Book",
  "short_name": "Chartered",
  "description": "Bookkeeping and accounts for Nepal, kept in your own browser.",
  "start_url": ".",
  "scope": ".",
  "display": "standalone",
  "background_color": "#f2f5f8",
  "theme_color": "#1d3557",
  "icons": [
    { "src": "static/icons/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any" },
    { "src": "static/icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any" },
    { "src": "static/icons/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable" }
  ]
}
"""


def main():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)

    print()
    print("  Building the browser version")
    print()

    modules = build_package_zip(os.path.join(OUT, "chartered_book.zip"))
    size = os.path.getsize(os.path.join(OUT, "chartered_book.zip"))
    print("  engine        %d python files, %.0f KB" % (modules, size / 1024.0))

    assets = copy_static(os.path.join(OUT, "static"))
    print("  screens       %d files" % assets)

    with open(os.path.join(OUT, "manifest.webmanifest"), "w", encoding="utf-8") as handle:
        handle.write(manifest())

    # Worked out before the two files that carry it are written, so it depends
    # on the software and not on itself.
    stamp = build_stamp()
    with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as handle:
        handle.write(shell_html(stamp))
    with open(os.path.join(OUT, "boot.js"), "w", encoding="utf-8") as handle:
        handle.write(boot_js(stamp))
    with open(os.path.join(OUT, "engine.js"), "w", encoding="utf-8") as handle:
        handle.write(engine_js(stamp))

    # The service worker built for the server version points at absolute
    # addresses that do not exist here, so it is replaced with one written for
    # this build.
    stale = os.path.join(OUT, "static", "sw.js")
    if os.path.exists(stale):
        os.remove(stale)
    with open(os.path.join(OUT, "sw.js"), "w", encoding="utf-8") as handle:
        handle.write(worker_js(stamp))
    print("  build         %s" % stamp)

    total = 0
    for root, _dirs, files in os.walk(OUT):
        for name in files:
            total += os.path.getsize(os.path.join(root, name))
    print("  altogether    %.0f KB, plus Pyodide fetched from its own address" % (total / 1024.0))
    print()
    print("  Written to docs/app")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())

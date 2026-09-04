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


def shell_html():
    """
    The page the browser opens.

    It shows a loading screen straight away, because bringing Python into a
    browser takes a few seconds the first time and a blank screen would look
    broken. Afterwards it is cached and opens quickly.
    """
    scripts = ["nepali.js", "ui.js", "app.js", "masters.js", "vouchers.js",
               "drill.js", "reports.js", "statements.js", "banking.js",
               "assets.js", "audit.js"]
    tags = "\n".join('<script src="static/%s"></script>' % s for s in scripts)
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
<link rel="icon" type="image/png" sizes="192x192" href="static/icons/icon-192.png">
<link rel="apple-touch-icon" href="static/icons/icon-180.png">
<link rel="stylesheet" href="static/style.css">
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
#starting .slow{color:var(--ink-faint);font-size:.76rem;margin-top:1.1rem;line-height:1.5}
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
    <div class="slow">The first time takes a few seconds while the accounting
      engine loads, and needs the internet. After that it is kept on the device
      and opens quickly. Your books never leave this device.</div>
  </div>
</div>

__BODY__

<script>
window.CHARTERED_BOOK_WEB = true;
if ("serviceWorker" in navigator) {
  window.addEventListener("load", function () {
    navigator.serviceWorker.register("sw.js").catch(function () { /* nothing lost */ });
  });
}
</script>
<script src="boot.js"></script>
__SCRIPTS__
</body>
</html>
""".replace("__BODY__", body).replace("__SCRIPTS__", tags)


def boot_js():
    return """/* Bringing the books up inside a browser.

   Loads Pyodide, which is Python compiled to run in a browser, unpacks the
   Saphal Book engine into it, and points the books at a folder that the
   browser keeps between visits.

   From then on the screens talk to Python directly instead of over HTTP. The
   engine is the same one that runs on a computer, so nothing about the
   accounting changes. */

window.CB = (function () {
  "use strict";

  var pyodide = null;
  var dispatch = null;
  var ready = false;
  var BOOKS = "/books";
  var TOKEN_KEY = "cb_token";

  function step(text, portion) {
    var line = document.getElementById("startstep");
    var bar = document.getElementById("startbar");
    if (line) { line.textContent = text; }
    if (bar) { bar.style.width = Math.round(portion * 100) + "%"; }
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

  function save() {
    // Write whatever changed back into the browser's own storage.
    return new Promise(function (resolve) {
      try {
        pyodide.FS.syncfs(false, function () { resolve(); });
      } catch (error) { resolve(); }
    });
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

  /* The one call the screens make. Same shape as a request to the server. */
  function call(method, path, query, body) {
    if (!ready) { return Promise.reject(new Error("The books are still starting.")); }
    var answer;
    try {
      answer = dispatch(method || "GET", path,
                        JSON.stringify(query || {}),
                        JSON.stringify(body || {}),
                        token());
    } catch (error) {
      return Promise.reject(new Error(String(error && error.message || error)));
    }
    var parsed;
    try { parsed = JSON.parse(answer); }
    catch (error) { return Promise.reject(new Error("The books gave an unreadable answer.")); }

    if (parsed.token) { setToken(parsed.token); }
    if (parsed.clear_token) { setToken(""); }

    var writing = method && method.toUpperCase() !== "GET";
    var settle = writing ? save() : Promise.resolve();

    return settle.then(function () {
      if (parsed.status >= 400) {
        var error = new Error((parsed.payload && parsed.payload.error) || "That did not work.");
        error.status = parsed.status;
        throw error;
      }
      return parsed.payload;
    });
  }

  async function start() {
    try {
      step("Fetching the accounting engine", 0.1);
      if (typeof loadPyodide !== "function") {
        await new Promise(function (resolve, reject) {
          var tag = document.createElement("script");
          tag.src = "__PYODIDE__pyodide.js";
          tag.onload = resolve;
          tag.onerror = function () { reject(new Error("could not fetch Pyodide")); };
          document.head.appendChild(tag);
        });
      }

      step("Starting Python", 0.35);
      pyodide = await loadPyodide({ indexURL: "__PYODIDE__" });

      step("Loading the database", 0.5);
      // Pyodide does not ship sqlite3 in the base image, it has to be asked
      // for. Everything the books are kept in depends on it.
      await pyodide.loadPackage("sqlite3");

      step("Opening your books", 0.6);
      pyodide.FS.mkdirTree(BOOKS);
      pyodide.FS.mount(pyodide.FS.filesystems.IDBFS, {}, BOOKS);
      await new Promise(function (resolve) {
        pyodide.FS.syncfs(true, function () { resolve(); });
      });

      step("Unpacking Saphal Book", 0.75);
      var response = await fetch("chartered_book.zip", { cache: "no-cache" });
      if (!response.ok) { throw new Error("the engine file is missing"); }
      var buffer = await response.arrayBuffer();
      await pyodide.unpackArchive(buffer, "zip");

      step("Setting it up", 0.9);
      pyodide.runPython(
        "import os, sys\\n" +
        "os.environ['CHARTERED_BOOK_DATA'] = '" + BOOKS + "'\\n" +
        "sys.path.insert(0, '/')\\n" +
        "from chartered_book.web import embedded\\n"
      );
      dispatch = pyodide.runPython("embedded.dispatch");
      await save();

      ready = true;
      window.CB.ready = true;
      step("Ready", 1);
      var screen = document.getElementById("starting");
      if (screen) { screen.style.display = "none"; }
      document.dispatchEvent(new Event("chartered-book-ready"));
    } catch (error) {
      var detail = String((error && error.message) || error || "");
      var short = detail.split(String.fromCharCode(10))[0].slice(0, 160);
      fail("Saphal Book could not start.",
           "The first load needs the internet. Check the connection and open it "
           + "again. If it keeps failing: " + short);
    }
  }

  document.addEventListener("DOMContentLoaded", start);

  return { call: call, ready: false, save: save,
           token: token, setToken: setToken,
           // Kept reachable so a problem can be looked into from the console
           // rather than guessed at.
           runtime: function () { return pyodide; } };
}());
""".replace("__PYODIDE__", PYODIDE)


def worker_js():
    """
    Keeps this build on the device after the first visit.

    Only the files served from here are stored. Pyodide comes from its own
    address and is left to the browser's ordinary cache, so this is not a
    promise that everything works with no connection at all, only that it does
    not have to be fetched again every time.
    """
    return """var VERSION = "chartered-book-web-1";
var SHELL = ["./", "index.html", "boot.js", "manifest.webmanifest",
  "chartered_book.zip",
  "static/style.css", "static/nepali.js", "static/ui.js", "static/app.js",
  "static/masters.js", "static/vouchers.js", "static/drill.js",
  "static/reports.js", "static/statements.js", "static/banking.js",
  "static/assets.js", "static/audit.js",
  "static/icons/icon-192.png", "static/icons/icon-512.png"];

self.addEventListener("install", function (event) {
  event.waitUntil(caches.open(VERSION).then(function (cache) {
    return Promise.all(SHELL.map(function (url) {
      return cache.add(url).catch(function () { return null; });
    }));
  }).then(function () { return self.skipWaiting(); }));
});

self.addEventListener("activate", function (event) {
  event.waitUntil(caches.keys().then(function (names) {
    return Promise.all(names.map(function (name) {
      return name === VERSION ? null : caches.delete(name);
    }));
  }).then(function () { return self.clients.claim(); }));
});

self.addEventListener("fetch", function (event) {
  var request = event.request;
  if (request.method !== "GET") { return; }
  if (new URL(request.url).origin !== self.location.origin) { return; }
  event.respondWith(
    fetch(request).then(function (response) {
      if (response && response.status === 200) {
        var copy = response.clone();
        caches.open(VERSION).then(function (cache) { cache.put(request, copy); });
      }
      return response;
    }).catch(function () {
      return caches.match(request).then(function (hit) {
        return hit || caches.match("index.html");
      });
    })
  );
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

    with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as handle:
        handle.write(shell_html())
    with open(os.path.join(OUT, "boot.js"), "w", encoding="utf-8") as handle:
        handle.write(boot_js())
    with open(os.path.join(OUT, "manifest.webmanifest"), "w", encoding="utf-8") as handle:
        handle.write(manifest())

    # The service worker built for the server version points at absolute
    # addresses that do not exist here, so it is replaced with one written for
    # this build.
    stale = os.path.join(OUT, "static", "sw.js")
    if os.path.exists(stale):
        os.remove(stale)
    with open(os.path.join(OUT, "sw.js"), "w", encoding="utf-8") as handle:
        handle.write(worker_js())

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

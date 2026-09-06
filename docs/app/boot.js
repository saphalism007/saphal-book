/* Bringing the books up inside a browser.

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

  // What to call this device.
  //
  // Inside the engine every browser in the world calls itself emscripten, so
  // two devices signed in to the same account were both named "emscripten,
  // Emscripten" and a person being asked which copy to keep was offered the
  // same answer twice. The browser knows better than the engine does, so it
  // says. Whatever is chosen here is only a starting point: it can be renamed,
  // and a name somebody typed always wins.
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
    if (/Edg\//.test(ua)) { browser = "Edge"; }
    else if (/OPR\//.test(ua)) { browser = "Opera"; }
    else if (/Firefox\//.test(ua)) { browser = "Firefox"; }
    else if (/Chrome\//.test(ua)) { browser = "Chrome"; }
    else if (/Safari\//.test(ua)) { browser = "Safari"; }

    // A page kept with the other apps is not "Safari on iPad", it is the app.
    var installed = window.matchMedia
      && window.matchMedia("(display-mode: standalone)").matches;
    if (installed || window.navigator.standalone) { return "Saphal Book on " + where; }
    return browser ? browser + " on " + where : where;
  }

  // Keep the engine on the device.
  //
  // The service worker will store whatever passes through it, but on the first
  // visit it is not yet in charge of the page, so the parts fetched during that
  // first run would go unstored and the next launch would fetch them all over
  // again. This puts them away deliberately, once, as soon as the books are
  // open, so the second launch is the fast one rather than the third.
  //
  // It is done quietly. If it fails the software still works, it is just slow
  // to start, which is what it was before.
  async function warmEngine() {
    if (!window.caches) { return; }
    try {
      var wanted = ["pyodide.js", "pyodide.asm.js", "pyodide.asm.wasm",
                    "pyodide-lock.json", "python_stdlib.zip"];
      try {
        var lock = await (await fetch("https://cdn.jsdelivr.net/pyodide/v0.26.4/full/pyodide-lock.json")).json();
        var packages = (lock && lock.packages) || {};
        Object.keys(packages).forEach(function (name) {
          if (packages[name] && packages[name].file_name
              && (name === "sqlite3" || name === "sqlite3-static-libs")) {
            wanted.push(packages[name].file_name);
          }
        });
      } catch (ignored) { /* the core files are the ones that matter */ }

      var cache = await caches.open("saphal-book-engine");
      for (var i = 0; i < wanted.length; i += 1) {
        var url = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/" + wanted[i];
        if (await cache.match(url)) { continue; }
        try { await cache.add(url); } catch (ignored) { /* skip it */ }
      }
    } catch (ignored) { /* nothing here is worth interrupting the books for */ }
  }

  async function start() {
    try {
      step("Fetching the accounting engine", 0.1);
      if (typeof loadPyodide !== "function") {
        await new Promise(function (resolve, reject) {
          var tag = document.createElement("script");
          tag.src = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/pyodide.js";
          tag.onload = resolve;
          tag.onerror = function () { reject(new Error("could not fetch Pyodide")); };
          document.head.appendChild(tag);
        });
      }

      step("Starting Python", 0.35);
      pyodide = await loadPyodide({ indexURL: "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/" });

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
      var response = await fetch("chartered_book.zip?v=3874c0deda68",
                                 { cache: "no-cache" });
      if (!response.ok) { throw new Error("the engine file is missing"); }
      var buffer = await response.arrayBuffer();
      await pyodide.unpackArchive(buffer, "zip");

      step("Setting it up", 0.9);
      pyodide.runPython(
        "import os, sys\n" +
        "os.environ['CHARTERED_BOOK_DATA'] = '" + BOOKS + "'\n" +
        "os.environ['SAPHAL_DEVICE'] = " + JSON.stringify(deviceName()) + "\n" +
        "sys.path.insert(0, '/')\n" +
        "from chartered_book.web import embedded\n"
      );
      dispatch = pyodide.runPython("embedded.dispatch");
      await save();

      ready = true;
      window.CB.ready = true;
      step("Ready", 1);
      warmEngine();
      var screen = document.getElementById("starting");
      if (screen) { screen.style.display = "none"; }
      document.dispatchEvent(new Event("saphal-book-ready"));
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

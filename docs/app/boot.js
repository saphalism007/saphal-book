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
      var response = await fetch("chartered_book.zip?v=6dca8a05b701",
                                 { cache: "no-cache" });
      if (!response.ok) { throw new Error("the engine file is missing"); }
      var buffer = await response.arrayBuffer();
      await pyodide.unpackArchive(buffer, "zip");

      step("Setting it up", 0.9);
      pyodide.runPython(
        "import os, sys\n" +
        "os.environ['CHARTERED_BOOK_DATA'] = '" + BOOKS + "'\n" +
        "sys.path.insert(0, '/')\n" +
        "from chartered_book.web import embedded\n"
      );
      dispatch = pyodide.runPython("embedded.dispatch");
      await save();

      ready = true;
      window.CB.ready = true;
      step("Ready", 1);
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

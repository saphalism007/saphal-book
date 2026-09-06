/* Bringing the books up inside a browser.

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
    if (/Edg\//.test(ua)) { browser = "Edge"; }
    else if (/OPR\//.test(ua)) { browser = "Opera"; }
    else if (/Firefox\//.test(ua)) { browser = "Firefox"; }
    else if (/Chrome\//.test(ua)) { browser = "Chrome"; }
    else if (/Safari\//.test(ua)) { browser = "Safari"; }

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
      worker = new Worker("engine.js?v=7150efc29fc4");
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
      if (msg.kind === "step") { return step(msg.text, msg.portion); }
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

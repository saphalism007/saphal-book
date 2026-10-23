var VERSION = "saphal-book-web-aec316cd6cad";
var ENGINE = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/";
var SHELL = [
"./",
"manifest.webmanifest",
"boot.js?v=aec316cd6cad",
"engine.js?v=aec316cd6cad",
"chartered_book.zip?v=aec316cd6cad",
"static/style.css?v=aec316cd6cad",
"static/icons/icon-192.png",
"static/icons/icon-192.png?v=2",
"static/icons/icon-180.png?v=2",
"static/icons/icon-512.png",
"static/nepali.js?v=aec316cd6cad",
"static/ui.js?v=aec316cd6cad",
"static/app.js?v=aec316cd6cad",
"static/masters.js?v=aec316cd6cad",
"static/vouchers.js?v=aec316cd6cad",
"static/drill.js?v=aec316cd6cad",
"static/reports.js?v=aec316cd6cad",
"static/statements.js?v=aec316cd6cad",
"static/banking.js?v=aec316cd6cad",
"static/assets.js?v=aec316cd6cad",
"static/incometax.js?v=aec316cd6cad",
"static/analysis.js?v=aec316cd6cad",
"static/recurring.js?v=aec316cd6cad",
"static/quotations.js?v=aec316cd6cad",
"static/audit.js?v=aec316cd6cad"
];
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

/* Service worker.

   Its only jobs are to make Saphal Book installable on a phone, tablet or
   desktop, and to keep the screens usable if the connection to the machine
   running the books drops for a moment.

   Accounting figures are never served from a cache. Every call to /api/ goes
   to the server or fails honestly, because a stale balance shown as if it were
   current would be worse than no balance at all. */

var VERSION = "saphal-book-v10";
var SHELL = [
  "/",
  "/static/style.css",
  "/static/nepali.js",
  "/static/ui.js",
  "/static/app.js",
  "/static/masters.js",
  "/static/vouchers.js",
  "/static/reports.js",
  "/static/drill.js",
  "/static/statements.js",
  "/static/banking.js",
  "/static/assets.js",
  "/static/incometax.js",
  "/static/analysis.js",
  "/static/recurring.js",
  "/static/quotations.js",
  "/static/audit.js",
  "/static/manifest.json",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png"
];

self.addEventListener("install", function (event) {
  event.waitUntil(
    caches.open(VERSION).then(function (cache) {
      return Promise.all(SHELL.map(function (url) {
        return cache.add(url).catch(function () { return null; });
      }));
    }).then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener("activate", function (event) {
  event.waitUntil(
    caches.keys().then(function (names) {
      return Promise.all(names.map(function (name) {
        return name === VERSION ? null : caches.delete(name);
      }));
    }).then(function () { return self.clients.claim(); })
  );
});

self.addEventListener("fetch", function (event) {
  var request = event.request;
  if (request.method !== "GET") { return; }
  var url = new URL(request.url);
  if (url.origin !== self.location.origin) { return; }

  // Live data only. Never answer an accounting question from a cache.
  if (url.pathname.indexOf("/api/") === 0) { return; }

  // Everything else: try the server first so a code change lands straight
  // away, and fall back to the stored copy only if the server cannot be
  // reached.
  event.respondWith(
    fetch(request).then(function (response) {
      if (response && response.status === 200 && response.type === "basic") {
        var copy = response.clone();
        caches.open(VERSION).then(function (cache) { cache.put(request, copy); });
      }
      return response;
    }).catch(function () {
      return caches.match(request).then(function (hit) {
        return hit || caches.match("/");
      });
    })
  );
});

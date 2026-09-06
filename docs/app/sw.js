var VERSION = "saphal-book-web-d8a08155f90a";
var ENGINE = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/";
var ENGINE_STORE = "saphal-book-engine";
var SHELL = ["./", "index.html", "boot.js", "engine.js", "manifest.webmanifest",
  "chartered_book.zip",
  "static/style.css", "static/nepali.js", "static/ui.js", "static/app.js",
  "static/masters.js", "static/vouchers.js", "static/drill.js",
  "static/reports.js", "static/statements.js", "static/banking.js",
  "static/assets.js", "static/incometax.js", "static/analysis.js", "static/recurring.js", "static/quotations.js", "static/audit.js",
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
      if (name === VERSION || name === ENGINE_STORE) { return null; }
      return caches.delete(name);
    }));
  }).then(function () { return self.clients.claim(); }));
});

// The engine never changes for a given build of it, so once it is here it is
// answered from here. This is what turns the second launch from thirty seconds
// into one.
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

self.addEventListener("fetch", function (event) {
  var request = event.request;
  if (request.method !== "GET") { return; }
  if (request.url.indexOf(ENGINE) === 0) {
    event.respondWith(fromEngineStore(request));
    return;
  }
  if (new URL(request.url).origin !== self.location.origin) { return; }
  // no-store, and this is the whole point of the line.
  //
  // This already went to the network first and fell back to the cache, which
  // sounded like enough. It was not. A plain fetch is still answered out of the
  // browser's own HTTP cache, and GitHub Pages sends max-age=600 on everything,
  // so for ten minutes after a change the network was never actually asked.
  //
  // What that cost was not ten minutes. index.html carries the build stamp on
  // every script it loads, so a stale index.html asks for the old app.js by
  // name, gets it, and keeps asking for it. Three fixes in a row looked to the
  // person using this like nothing had happened, because the screens they were
  // pressing were still the old ones.
  //
  // Offline still works. The cache is written on every good answer and read
  // whenever the network cannot be reached, which is what the catch below is.
  event.respondWith(
    fetch(request, { cache: "no-store" }).then(function (response) {
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

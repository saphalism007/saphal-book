var VERSION = "saphal-book-web-5e72e986a7b9";
var ENGINE = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/";
var ENGINE_STORE = "saphal-book-engine";
var SHELL = ["./", "index.html", "boot.js", "manifest.webmanifest",
  "chartered_book.zip",
  "static/style.css", "static/nepali.js", "static/ui.js", "static/app.js",
  "static/masters.js", "static/vouchers.js", "static/drill.js",
  "static/reports.js", "static/statements.js", "static/banking.js",
  "static/assets.js", "static/incometax.js", "static/audit.js",
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

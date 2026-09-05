var VERSION = "saphal-book-web-3fad94be1378";
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

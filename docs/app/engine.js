/* The accounting engine, on a thread of its own. See engine_js in
   tools/make_web_app.py for why. */

var PYODIDE = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/";
var ENGINE_STORE = "saphal-book-engine";
var SNAPSHOT = new URL("python-ready-v0.26.4", self.location).href;
var ZIP = new URL("chartered_book.zip?v=028b3c87da0a", self.location).href;
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
/* A download that breaks off part way is asked for again, a few times, with
   a short pause between. On a phone that happens: a signal drops for a
   moment, or the browser cuts off a request while one offline helper hands
   over to the next. Saphal Book used to give up on the first one and show
   "could not start", over a file that was there and would have come the
   second time. Only failing to reach anything counts; a file the server
   says is not there is not asked for again. */
async function patient(url, init) {
  var last = null;
  for (var attempt = 0; attempt < 4; attempt += 1) {
    try { return await realFetch(url, init); }
    catch (error) { last = error; }
    await new Promise(function (wait) { setTimeout(wait, 500 * (attempt + 1)); });
  }
  throw last;
}

function engineFile(url) {
  return caches.open(ENGINE_STORE).then(function (store) {
    return store.match(url).then(function (hit) {
      if (hit) { return hit; }
      return patient(url).then(function (response) {
        if (response && response.ok) {
          store.put(url, response.clone()).catch(function () { /* full, fine */ });
        }
        return response;
      });
    });
  }, function () { return patient(url); });
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
  function download() {
    return patient(ZIP, { cache: "no-cache" }).then(function (response) {
      if (!response.ok) { throw new Error("the Saphal Book file is missing"); }
      return response.arrayBuffer();
    });
  }
  return caches.match(ZIP).then(function (hit) {
    return hit ? hit.arrayBuffer() : download();
  }, download);
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
    "import os, sys\n" +
    "os.environ['CHARTERED_BOOK_DATA'] = '" + BOOKS + "'\n" +
    "os.environ['SAPHAL_DEVICE'] = " + JSON.stringify(device || "") + "\n" +
    "sys.path.insert(0, '/')\n" +
    "from chartered_book.web import embedded\n"
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
    // Whatever went wrong, start once more from the beginning, the ordinary
    // way, before saying anything. Most failures on a phone are a moment's
    // trouble with the connection and do not happen twice.
    if (fromSnapshot) { await forgetSnapshot(); }
    step("Trying again", 0.1, first);
    await new Promise(function (wait) { setTimeout(wait, 800); });
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

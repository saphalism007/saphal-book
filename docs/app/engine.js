/* The accounting engine, on a thread of its own. See engine_js in
   tools/make_web_app.py for why. */

var PYODIDE = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/";
var BOOKS = "/books";
var pyodide = null;
var dispatch = null;

function step(text, portion) {
  self.postMessage({ kind: "step", text: text, portion: portion });
}

function save() {
  return new Promise(function (resolve) {
    try { pyodide.FS.syncfs(false, function () { resolve(); }); }
    catch (error) { resolve(); }
  });
}

async function warmEngine() {
  // Keep the engine on the device so the second start needs no internet.
  try {
    var cache = await caches.open("saphal-book-engine-v1");
    var wanted = ["pyodide.js", "pyodide.asm.js", "pyodide.asm.wasm",
                  "python_stdlib.zip", "pyodide-lock.json"];
    for (var i = 0; i < wanted.length; i += 1) {
      var url = PYODIDE + wanted[i];
      if (await cache.match(url)) { continue; }
      try { await cache.add(url); } catch (ignored) { /* skip it */ }
    }
  } catch (ignored) { /* nothing here is worth interrupting the books for */ }
}

async function start(device) {
  try {
    step("Fetching the accounting engine", 0.1);
    importScripts(PYODIDE + "pyodide.js");

    step("Starting Python", 0.35);
    pyodide = await loadPyodide({ indexURL: PYODIDE });

    step("Loading the database", 0.5);
    await pyodide.loadPackage("sqlite3");

    step("Opening your books", 0.6);
    pyodide.FS.mkdirTree(BOOKS);
    pyodide.FS.mount(pyodide.FS.filesystems.IDBFS, {}, BOOKS);
    await new Promise(function (resolve) {
      pyodide.FS.syncfs(true, function () { resolve(); });
    });

    step("Unpacking Saphal Book", 0.75);
    var response = await fetch("chartered_book.zip?v=ac87942e7149", { cache: "no-cache" });
    if (!response.ok) { throw new Error("the engine file is missing"); }
    await pyodide.unpackArchive(await response.arrayBuffer(), "zip");

    step("Setting it up", 0.9);
    pyodide.runPython(
      "import os, sys\n" +
      "os.environ['CHARTERED_BOOK_DATA'] = '" + BOOKS + "'\n" +
      "os.environ['SAPHAL_DEVICE'] = " + JSON.stringify(device || "") + "\n" +
      "sys.path.insert(0, '/')\n" +
      "from chartered_book.web import embedded\n"
    );
    dispatch = pyodide.runPython("embedded.dispatch");
    await save();

    step("Ready", 1);
    self.postMessage({ kind: "ready" });
    warmEngine();
  } catch (error) {
    self.postMessage({ kind: "failed",
                       detail: String((error && error.message) || error || "") });
  }
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

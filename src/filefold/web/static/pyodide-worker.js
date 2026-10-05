// Web Worker for the static (GitHub Pages) build: runs FileFold's Python in the browser.
//
// Layout of the built site (see scripts/build_pages.py):
//   app/static/pyodide-worker.js   this file
//   app/pyodide/                   Pyodide runtime
//   app/filefold-py.zip            FileFold's Python sources (core, service, browser)
//
// Workspaces live in an Emscripten IDBFS mount (/workspaces), persisted to IndexedDB
// after every request that could have changed them.
import { loadPyodide } from "../pyodide/pyodide.mjs";

let py, handle;

const syncFs = populate =>
  new Promise((resolve, reject) => py.FS.syncfs(populate, err => (err ? reject(err) : resolve())));

async function init() {
  postMessage({ type: "progress", text: "Loading the Python runtime…" });
  py = await loadPyodide({ indexURL: new URL("../pyodide/", import.meta.url).href });

  postMessage({ type: "progress", text: "Loading FileFold…" });
  const zip = await (await fetch(new URL("../filefold-py.zip", import.meta.url))).arrayBuffer();
  py.unpackArchive(new Uint8Array(zip), "zip", { extractDir: "/home/pyodide/lib" });

  py.FS.mkdir("/workspaces");
  py.FS.mount(py.FS.filesystems.IDBFS, {}, "/workspaces");
  await syncFs(true);   // load previously saved workspaces from IndexedDB

  py.runPython(`
import os, sys
sys.path.insert(0, "/home/pyodide/lib")
os.environ["FILEFOLD_WORKSPACE_DIR"] = "/workspaces"
from filefold import browser
`);
  handle = py.runPython("browser.handle_js");
}

// One request at a time: Python is single-threaded and workspaces are plain files.
let queue = Promise.resolve();
const ready = init().then(
  () => postMessage({ type: "ready" }),
  err => { postMessage({ type: "init-error", text: String(err && err.message || err) }); throw err; },
);

self.onmessage = ev => {
  const m = ev.data;
  if (m.type !== "request") return;
  queue = queue.then(async () => {
    try {
      await ready;
      const raw = handle(
        m.method, m.path,
        m.json ?? undefined, m.fields ? JSON.stringify(m.fields) : undefined,
        m.fileName ?? undefined,
        m.fileBytes ? new Uint8Array(m.fileBytes) : undefined,
        m.bodyBytes ? new Uint8Array(m.bodyBytes) : undefined,
      );
      const [status, contentType, headersJson, body] = raw;
      if (m.method !== "GET") await syncFs(false);   // persist what the request changed
      postMessage(
        { type: "response", id: m.id, status, contentType, headers: JSON.parse(headersJson), body: body.buffer },
        [body.buffer],
      );
    } catch (err) {
      const text = JSON.stringify({ detail: String(err && err.message || err) });
      postMessage({ type: "response", id: m.id, status: 500, contentType: "application/json", headers: {},
                    body: new TextEncoder().encode(text).buffer });
    }
  });
};

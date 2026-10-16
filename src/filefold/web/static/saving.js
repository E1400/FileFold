// ═══════════════════════════════════════════════════════════════════════════════
// Saving: Export ZIP and single-file downloads, into a folder chosen per workspace
//
// The first save of a workspace asks where to put it; later saves of that workspace
// (the ZIP or any single file) go to the same folder without asking, until another
// folder is chosen with the folder button next to Export ZIP.
//   desktop app  - the app's local server saves the file (native folder dialog)
//   Chromium     - File System Access API; the folder handle is kept in IndexedDB
//   other        - an ordinary download; the browser decides where it goes
// A file already in the folder is never replaced without asking: the folder may be
// the person's project folder, holding their original deck under the same name.
// ═══════════════════════════════════════════════════════════════════════════════
const isDesktopApp = () => document.documentElement.dataset.desktop === "1";
const canChooseFolder = () => isDesktopApp() || typeof window.showDirectoryPicker === "function";

function _desktopSaveUrl(ws, leaf) {
  return `/api/desktop/workspaces/${encodeURIComponent(ws)}/${leaf}`;
}

// A one-store IndexedDB for folder handles, keyed by workspace name. Handles cannot go in
// localStorage; they survive here between visits (permission is asked again when needed).
function _folderStore(mode, use) {
  return new Promise((resolve, reject) => {
    const open = window.indexedDB.open("filefold-save-folders", 1);
    open.onupgradeneeded = () => open.result.createObjectStore("folders");
    open.onerror = () => reject(open.error);
    open.onsuccess = () => {
      const db = open.result;
      const tx = db.transaction("folders", mode);
      const req = use(tx.objectStore("folders"));
      tx.oncomplete = () => { db.close(); resolve(req?.result); };
      tx.onerror = () => { db.close(); reject(tx.error); };
    };
  });
}
const _getFolder = ws => _folderStore("readonly", s => s.get(ws)).catch(() => undefined);
const _setFolder = (ws, handle) => _folderStore("readwrite", s => s.put(handle, ws));

// Folder names follow a workspace when it is renamed; a deleted workspace forgets its folder.
async function moveSaveFolder(oldName, newName) {
  try {
    if (isDesktopApp() || !window.indexedDB) return;
    const handle = await _getFolder(oldName);
    if (handle && newName) await _setFolder(newName, handle);
    await _folderStore("readwrite", s => s.delete(oldName));
  } catch { /* nothing remembered */ }
}

const _isCancel = e => e?.name === "AbortError";

// The folder this workspace saves to, for the button label; null when none is set yet.
async function saveFolderLabel(ws) {
  if (isDesktopApp()) return (await api("GET", _desktopSaveUrl(ws, "save-dir"))).dir;
  if (!canChooseFolder()) return null;
  return (await _getFolder(ws))?.name ?? null;
}

// Ask for a folder (also used on the first save). Returns its label, or null if canceled.
async function chooseSaveFolder(ws) {
  if (isDesktopApp()) return (await api("POST", _desktopSaveUrl(ws, "save-dir"))).dir;
  try {
    const current = await _getFolder(ws);
    const handle = await window.showDirectoryPicker({ mode: "readwrite", startIn: current || "downloads" });
    await _setFolder(ws, handle);
    return handle.name;
  } catch (e) {
    if (_isCancel(e)) return null;
    throw e;
  }
}

// A folder we may write to, asking for one (or for permission again) when needed.
async function _writableFolder(ws) {
  let handle = await _getFolder(ws);
  if (handle) {
    const opts = { mode: "readwrite" };
    if (await handle.queryPermission(opts) !== "granted" && await handle.requestPermission(opts) !== "granted") {
      handle = null;   // refused: ask for a folder instead
    }
  }
  if (!handle) {
    if (await chooseSaveFolder(ws) === null) return null;
    handle = await _getFolder(ws);
  }
  return handle;
}

async function _exists(folder, leaf) {
  try { await folder.getFileHandle(leaf); return true; } catch { return false; }
}

async function _fetchBlob(ws, filename) {
  if (!filename) return api("GET", `/api/workspaces/${encodeURIComponent(ws)}/export`);
  // fetch rather than a link, so it also works where /api/ is served from inside the page
  const res = await fetch(`/api/workspaces/${encodeURIComponent(ws)}/files/${encodeURIComponent(filename)}`);
  if (!res.ok) throw await apiErrorFrom(res);
  return res.blob();
}

function _download(blob, leaf) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = leaf;
  a.click();
  URL.revokeObjectURL(a.href);
}

const _replaceQuestion = (leaf, where) => `"${leaf}" is already in ${where}. Replace it?`;

// Save one file of a workspace, or the whole workspace as <ws>.zip (filename omitted).
// Returns true when something was saved.
async function saveWorkspaceFile(ws, filename) {
  const leaf = filename || `${ws}.zip`;
  const what = filename ? "Couldn't download the file" : "Couldn't export the workspace";
  try {
    if (isDesktopApp()) {
      const url = _desktopSaveUrl(ws, "save");
      let r = await api("POST", url, filename ? { filename } : {});
      if (r.exists) {
        if (!confirm(_replaceQuestion(leaf, r.dir))) return false;
        r = await api("POST", url, filename ? { filename, replace: true } : { replace: true });
      }
      if (!r.saved) return false;                         // folder dialog canceled
      toast(`Saved ${leaf} to ${r.dir}`, "ok");
      refreshSaveFolderButton(ws);
      return true;
    }
    if (!canChooseFolder()) {
      _download(await _fetchBlob(ws, filename), leaf);
      toast(`${leaf} downloaded`);
      return true;
    }
    const folder = await _writableFolder(ws);            // before the fetch: a picker needs the click's activation
    if (!folder) return false;
    refreshSaveFolderButton(ws);
    const blob = await _fetchBlob(ws, filename);
    if (await _exists(folder, leaf) && !confirm(_replaceQuestion(leaf, `"${folder.name}"`))) return false;
    const out = await (await folder.getFileHandle(leaf, { create: true })).createWritable();
    await out.write(blob);
    await out.close();
    toast(`Saved ${leaf} to "${folder.name}"`, "ok");
    return true;
  } catch (e) {
    if (_isCancel(e)) return false;
    toastError(what, e);
    return false;
  }
}

// ── Folder button next to Export ZIP ─────────────────────────────────────────
async function refreshSaveFolderButton(ws) {
  const btn = document.getElementById("save-folder-btn");
  if (!btn) return;
  if (!canChooseFolder() || !ws) { btn.hidden = true; return; }
  let label = null;
  try { label = await saveFolderLabel(ws); } catch { /* shown as not set */ }
  if (ws !== state.activeWs) return;                     // another workspace opened meanwhile
  btn.hidden = false;
  btn.querySelector(".lbl").textContent = label ? label.split(/[\\/]/).filter(Boolean).pop() || label : "Choose folder…";
  btn.title = label
    ? `Exports and downloads of this workspace are saved in ${label}. Click to choose another folder.`
    : "Choose the folder this workspace's exports and downloads are saved in. Otherwise you're asked on the first export.";
}

async function changeSaveFolder() {
  const ws = state.activeWs;
  try {
    const label = await chooseSaveFolder(ws);
    if (label) toast(`${ws} now saves to ${label}`, "ok");
  } catch (e) {
    toastError("Couldn't change the folder", e);
  }
  refreshSaveFolderButton(ws);
}

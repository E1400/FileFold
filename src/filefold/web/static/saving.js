// ═══════════════════════════════════════════════════════════════════════════════
// Saving: Export ZIP and single-file downloads
//
// Every save opens a Save dialog that starts where this workspace was last saved,
// so pressing Enter saves to the same place again and any other folder is one click away.
//   desktop app  - the app's local server shows a native Save dialog and writes the file
//   Chromium     - showSaveFilePicker; the browser remembers the folder per picker id,
//                  and each workspace has its own id
//   other        - an ordinary download; the browser decides where it goes
// Replacing a file that is already there is confirmed by the Save dialog itself.
// ═══════════════════════════════════════════════════════════════════════════════
const isDesktopApp = () => document.documentElement.dataset.desktop === "1";
const canPickSaveLocation = () => typeof window.showSaveFilePicker === "function";

// A picker id for a workspace: at most 32 letters, digits, "-" or "_" (FNV-1a of the name).
function savePickerId(ws) {
  let h = 0x811c9dc5;
  for (const ch of ws) { h ^= ch.codePointAt(0); h = Math.imul(h, 0x01000193) >>> 0; }
  return `ff-${h.toString(36)}`;
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

// Save one file of a workspace, or the whole workspace as <ws>.zip (filename omitted).
// Returns true when something was saved; canceling the dialog is not an error.
async function saveWorkspaceFile(ws, filename) {
  const leaf = filename || `${ws}.zip`;
  try {
    if (isDesktopApp()) {
      const r = await api("POST", `/api/desktop/workspaces/${encodeURIComponent(ws)}/save`, filename ? { filename } : {});
      if (!r.saved) return false;
      toast(`Saved ${leaf} to ${r.dir}`, "ok");
      return true;
    }
    if (!canPickSaveLocation()) {
      _download(await _fetchBlob(ws, filename), leaf);
      toast(`${leaf} downloaded`);
      return true;
    }
    // The dialog first: it needs the click that started this, which a slow fetch would outlast.
    const handle = await window.showSaveFilePicker({
      id: savePickerId(ws),
      suggestedName: leaf,
      ...(filename ? {} : { types: [{ description: "ZIP archive", accept: { "application/zip": [".zip"] } }] }),
    });
    const blob = await _fetchBlob(ws, filename);
    const out = await handle.createWritable();
    await out.write(blob);
    await out.close();
    toast(`Saved ${handle.name}`, "ok");
    return true;
  } catch (e) {
    if (e?.name === "AbortError") return false;
    toastError(filename ? "Couldn't download the file" : "Couldn't export the workspace", e);
    return false;
  }
}

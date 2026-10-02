// ═══════════════════════════════════════════════════════════════════════════════
// Reimport
// ═══════════════════════════════════════════════════════════════════════════════
function startReimp() {
  resetReimp();
  document.getElementById("reimp-title").textContent = `Re-import → ${state.activeWs}`;
  showView("reimport");
}

// Markup for the idle re-import drop zone. handleReimpUpload overwrites the zone
// with a spinner, so it has to be restored here — otherwise re-opening the view
// shows the previous run's "Analysing <other-file>…" spinner, which looks like a
// hang but is just stale DOM with no request behind it.
const _REIMP_DROP_IDLE = `
  <div class="icon">📂</div>
  <p>Drop the updated <code>.inp</code> here or click to browse</p>
  <div class="hint">This becomes the new mother file</div>`;

function resetReimp() {
  state.reimp = { file: null, preview: null, checked: new Set(), availableNewCats: [] };
  document.getElementById("reimp-upload-section").style.display = "";
  document.getElementById("reimp-preview-section").style.display = "none";
  document.getElementById("reimp-input").value = "";
  const zone = document.getElementById("reimp-drop");
  if (zone) zone.innerHTML = _REIMP_DROP_IDLE;
}

async function handleReimpUpload(file) {
  if (!file) return;
  state.reimp.file = file;
  const zone = document.getElementById("reimp-drop");
  zone.innerHTML = `<div class="icon"><div class="spinner"></div></div><p>Analysing ${esc(file.name)}…</p>`;

  try {
    const fd = new FormData();
    fd.append("file", file);
    const data = await api("POST", `/api/workspaces/${encodeURIComponent(state.activeWs)}/reimport/preview`, fd);
    state.reimp.preview = data;
    state.reimp.checked = new Set((data.safe_to_update ?? []).map(s => s.filename));

    document.getElementById("reimp-file-label").textContent = data.filename ?? file.name;
    renderReimpInspector(data.blocks ?? []);
    renderReimpNewCats(data.blocks ?? []);
    renderReimportPreview(data);

    document.getElementById("reimp-upload-section").style.display = "none";
    document.getElementById("reimp-preview-section").style.display = "";
  } catch (e) {
    zone.innerHTML = `<div class="icon">⚠</div><p>${esc(e.message)}</p>`;
    toast("Preview failed: " + e.message, "error");
  }
}

function toggleReimpInspector() {
  const tree = document.getElementById("reimp-inspector-tree");
  const tog  = document.getElementById("reimp-insp-toggle");
  const open = tree.style.display === "none";
  tree.style.display = open ? "" : "none";
  tog.textContent = open ? "▾ hide" : "▸ show";
}

function renderReimpInspector(blocks) {
  const el = document.getElementById("reimp-inspector-tree");
  el.innerHTML = blocks.map(b => treeNodeHTML(b, 0)).join("");
  el.querySelectorAll(".tree-node-header").forEach(h => {
    h.addEventListener("click", () => {
      const children = h.nextElementSibling;
      if (!children) return;
      const open = children.classList.toggle("open");
      h.querySelector(".tree-toggle").textContent = open ? "▾" : "▸";
    });
  });
}

function renderReimpNewCats(blocks) {
  const existingCats = new Set((state.wsData?.selections ?? []).map(s => s.category));
  // Top-level only — matches what compute_split can actually route. NON_EXTRACTABLE
  // (not just "unknown"): the server rejects those, so offering them here only
  // produces a checkbox that errors on apply.
  const fileCats = new Set();
  blocks.forEach(b => { if (!NON_EXTRACTABLE.has(b.category)) fileCats.add(b.category); });

  const newCats = [...fileCats].filter(c => !existingCats.has(c));
  state.reimp.availableNewCats = newCats;

  const section = document.getElementById("reimp-new-cats-section");
  const el = document.getElementById("reimp-new-cats");

  if (!newCats.length) { section.style.display = "none"; return; }

  section.style.display = "";
  el.innerHTML = newCats.map(cat => {
    const c = CAT_COLORS_var(cat);
    return `<div class="split-row" id="reimp-row-${cat}">
      <label>
        <input type="checkbox" id="reimp-sel-${cat}" onchange="toggleReimpNewCat('${cat}')">
        <span class="chip" style="background:color-mix(in srgb, ${c} 26%, transparent);border-color:color-mix(in srgb, ${c} 45%, transparent);color:${c}">${cat}</span>
      </label>
      <input type="text" id="reimp-fn-${cat}" value="${cat}.inp" placeholder="filename.inp" style="opacity:.4" disabled>
      <span class="text-muted text-sm mono">new</span>
    </div>`;
  }).join("");
}

function toggleReimpNewCat(cat) {
  const checked = document.getElementById(`reimp-sel-${cat}`).checked;
  const row = document.getElementById(`reimp-row-${cat}`);
  const fnInput = document.getElementById(`reimp-fn-${cat}`);
  row.classList.toggle("selected", checked);
  fnInput.disabled = !checked;
  fnInput.style.opacity = checked ? "1" : ".4";
}

function renderReimportPreview(data) {
  const el = document.getElementById("reimp-results");
  const safe      = data.safe_to_update ?? [];
  const attn      = data.needs_attention ?? [];
  const unchanged = data.unchanged ?? [];
  let html = "";

  if (!safe.length && !attn.length && !unchanged.length) {
    html = `<div class="text-muted text-sm" style="padding:12px 0">No existing sections to update. The mother file will still be refreshed.</div>`;
  }

  if (safe.length) {
    html += `<div class="reimport-section">
      <h3><span class="badge badge-ok">Safe to update</span></h3>
      ${safe.map(s => `
        <div class="reimport-row safe">
          <input type="checkbox" checked onchange="toggleReimpCheck('${esc(s.filename)}', this.checked)" style="accent-color:var(--success)">
          <span class="fname">${esc(s.filename)}</span>
          ${catChip(s.category)}
        </div>`).join("")}
    </div>`;
  }

  if (attn.length) {
    html += `<div class="reimport-section">
      <h3><span class="badge badge-warn">Conflict</span> — changed in new file AND manually edited</h3>
      <p class="text-muted text-sm" style="margin-bottom:8px">Check to overwrite with new version, uncheck to keep your edits.</p>
      ${attn.map(s => `
        <div class="reimport-row pending">
          <input type="checkbox" onchange="toggleReimpCheck('${esc(s.filename)}', this.checked)" style="accent-color:var(--warn)">
          <span class="fname">${esc(s.filename)}</span>
          ${catChip(s.category)}
          <span class="badge badge-warn">conflict</span>
        </div>`).join("")}
    </div>`;
  }

  if (unchanged.length) {
    html += `<div class="reimport-section">
      <h3><span class="badge badge-muted">Unchanged</span></h3>
      ${unchanged.map(s => `
        <div class="reimport-row">
          <span class="fname">${esc(s.filename)}</span>
          ${catChip(s.category)}
          <span class="badge badge-muted">no change</span>
        </div>`).join("")}
    </div>`;
  }

  el.innerHTML = html;
}

function toggleReimpCheck(filename, checked) {
  if (checked) state.reimp.checked.add(filename);
  else state.reimp.checked.delete(filename);
}

async function applyReimp() {
  if (!state.reimp.file) return;
  const btn = document.getElementById("reimp-apply-btn");
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner"></span> Applying…`;

  // Collect newly selected categories
  const addedSelections = [];
  for (const cat of state.reimp.availableNewCats) {
    const cb = document.getElementById(`reimp-sel-${cat}`);
    if (cb && cb.checked) {
      const fn = document.getElementById(`reimp-fn-${cat}`)?.value.trim() || `${cat}.inp`;
      addedSelections.push({ category: cat, filename: fn });
    }
  }

  try {
    const fd = new FormData();
    fd.append("file", state.reimp.file);
    fd.append("filenames", JSON.stringify([...state.reimp.checked]));
    fd.append("added_selections", JSON.stringify(addedSelections));
    const result = await api("POST", `/api/workspaces/${encodeURIComponent(state.activeWs)}/reimport/apply`, fd);
    const wsName = result.workspace ?? state.activeWs;
    toast(`Reimport applied`, "ok");
    // workspace name in state may have changed if source_name updated
    state.activeWs = wsName;
    await loadWorkspaces();
    openWorkspace(wsName);
  } catch (e) {
    toast("Apply failed: " + e.message, "error");
    btn.disabled = false;
    btn.textContent = "Apply updates";
  }
}

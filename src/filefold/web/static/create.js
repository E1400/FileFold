// ═══════════════════════════════════════════════════════════════════════════════
// Upload + Inspect
// ═══════════════════════════════════════════════════════════════════════════════
function setupDropZone(zoneId, handler) {
  const zone = document.getElementById(zoneId);
  if (!zone) return;
  zone.addEventListener("dragover", e => { e.preventDefault(); zone.classList.add("drag-over"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("drag-over"));
  zone.addEventListener("drop", e => {
    e.preventDefault(); zone.classList.remove("drag-over");
    const f = e.dataTransfer.files[0];
    if (f) handler(f);
  });
}

async function handleUpload(file) {
  if (!file) return;
  state.uploadedFile = file;

  // Default workspace name from filename
  const base = file.name.replace(/\.inp$/i, "");
  const nameInput = document.getElementById("ws-name-input");
  if (!nameInput.value) nameInput.value = base;

  const zone = document.getElementById("upload-zone");
  zone.innerHTML = `<div class="icon"><div class="spinner"></div></div><p>Parsing ${esc(file.name)}…</p>`;

  try {
    const fd = new FormData();
    fd.append("file", file);
    const data = await api("POST", "/api/inspect", fd);
    state.inspectResult = data;

    zone.innerHTML = `
      <div class="icon">✓</div>
      <p><strong>${esc(file.name)}</strong></p>
      <div class="hint">${countBlocks(data.blocks)} blocks detected — <a href="#" onclick="document.getElementById('upload-input').click();return false">change file</a></div>`;

    document.getElementById("inspector-section").style.display = "";
    renderInspector(data.blocks);
    document.getElementById("split-config-section").style.display = "";
    renderSplitConfig(data.blocks);
    document.getElementById("create-btn-row").style.display = "";
  } catch (e) {
    zone.innerHTML = `<div class="icon">⚠</div><p>${esc(e.message)}</p>`;
    toast("Parse error: " + e.message, "error");
  }
}

function countBlocks(blocks, n = 0) {
  for (const b of blocks) { n++; n = countBlocks(b.children, n); }
  return n;
}

// ── Block inspector tree ────────────────────────────────────────────────────
function renderInspector(blocks) {
  document.getElementById("inspector-tree").innerHTML =
    blocks.map(b => treeNodeHTML(b, 0)).join("");
  document.querySelectorAll(".tree-node-header").forEach(h => {
    h.addEventListener("click", () => {
      const children = h.nextElementSibling;
      if (!children) return;
      const open = children.classList.toggle("open");
      h.querySelector(".tree-toggle").textContent = open ? "▾" : "▸";
    });
  });
}

function treeNodeHTML(b, depth) {
  const c = CAT_COLORS_var(b.category);
  const hasChildren = b.children && b.children.length > 0;
  return `<div class="tree-node">
    <div class="tree-node-header">
      <span class="tree-toggle">${hasChildren ? "▸" : " "}</span>
      <span class="tree-kw" style="color:${c}">*${esc(b.keyword)}</span>
      <span class="tree-cat" style="background:color-mix(in srgb, ${c} 26%, transparent);border-color:color-mix(in srgb, ${c} 45%, transparent);color:${c}">${esc(b.category)}</span>
      <span class="tree-lines">${b.line_start}–${b.line_end}</span>
    </div>
    ${hasChildren ? `<div class="tree-children">${b.children.map(ch => treeNodeHTML(ch, depth+1)).join("")}</div>` : ""}
  </div>`;
}

// ── Split config ─────────────────────────────────────────────────────────────
function renderSplitConfig(blocks) {
  // Only collect categories from TOP-LEVEL blocks — the splitter routes by
  // top-level category, so nested blocks (e.g. *SOLID SECTION inside *PART)
  // always follow their container and cannot be independently extracted.
  const cats = new Set();
  blocks.forEach(b => { if (!NON_EXTRACTABLE.has(b.category)) cats.add(b.category); });

  const el = document.getElementById("split-config");
  if (!cats.size) { el.innerHTML = `<p class="text-muted">No categories available.</p>`; return; }

  // Same master toggle as the edit menu. Ids avoid the "sel-"/"sub-" prefixes that
  // createWorkspace uses to find real rows, and nothing reads these when building
  // the selections payload — they are purely a time-saver for ticking everything.
  const masterRow = `
    <div class="split-row" style="background:transparent;border-style:dashed">
      <label style="cursor:pointer;user-select:none;font-weight:600">
        <input type="checkbox" id="master-cats" onchange="toggleAllCategories()">
        Select all categories
      </label>
      <span class="text-muted text-sm">${cats.size} available</span>
    </div>`;

  el.innerHTML = masterRow + [...cats].map(cat => {
    const c = CAT_COLORS_var(cat);
    const id = `sel-${cat}`;
    // Only offer sub-splits whose blocks exist in this deck (reported by /api/inspect).
    const presentSubs = new Set(state.inspectResult?.sub_cats?.[cat] ?? []);
    const subOpts = (state.subOptions[cat] ?? []).filter(o => presentSubs.has(o.sub_category));
    const subPanel = subOpts.length ? `
      <div class="sub-options" id="sub-opts-${cat}">
        <div class="text-muted text-sm" style="margin-bottom:4px;display:flex;align-items:center;gap:8px">
          <span>Split into sub-files:</span>
          <label style="display:inline-flex;align-items:center;gap:4px;cursor:pointer;user-select:none">
            <input type="checkbox" id="submaster-${cat}" onchange="toggleAllSubOptions('${cat}')">
            <span>all</span>
          </label>
        </div>
        ${subOpts.map(opt => `
          <div class="sub-option-row">
            <label>
              <input type="checkbox" id="sub-${cat}-${opt.sub_category}" value="${opt.sub_category}" onchange="toggleSubOption('${cat}','${opt.sub_category}')">
              ${esc(opt.label)}
            </label>
            <input type="text" id="subfn-${cat}-${opt.sub_category}" value="${opt.default_filename}" placeholder="${opt.default_filename}" disabled style="opacity:.4">
          </div>`).join("")}
      </div>` : "";
    return `<div class="split-row" id="row-${cat}">
      <label>
        <input type="checkbox" id="${id}" onchange="toggleSplitRow('${cat}')">
        <span class="chip" style="background:color-mix(in srgb, ${c} 26%, transparent);border-color:color-mix(in srgb, ${c} 45%, transparent);color:${c}">${cat}</span>
      </label>
      <input type="text" id="fn-${cat}" value="${cat}.inp" placeholder="filename.inp" style="opacity:.4" disabled>
      <span class="text-muted text-sm" style="font-family:var(--mono)">*.inp</span>
      ${subPanel}
    </div>`;
  }).join("");
}

function toggleSplitRow(cat) {
  const checked = document.getElementById(`sel-${cat}`).checked;
  const row = document.getElementById(`row-${cat}`);
  const fnInput = document.getElementById(`fn-${cat}`);
  row.classList.toggle("selected", checked);
  fnInput.disabled = !checked;
  fnInput.style.opacity = checked ? "1" : ".4";
  _syncCreateMasterCats();  // unchecking one category clears "select all"

  const subPanel = document.getElementById(`sub-opts-${cat}`);
  if (subPanel) {
    subPanel.classList.toggle("visible", checked);
    // When the parent is toggled off, uncheck and disable all sub-checkboxes
    subPanel.querySelectorAll("input[type=checkbox]").forEach(cb => {
      if (!checked) cb.checked = false;
    });
    subPanel.querySelectorAll("input[type=text]").forEach(inp => {
      inp.disabled = true;
      inp.style.opacity = ".4";
    });
  }
}

function toggleSubOption(cat, subCat) {
  const cb = document.getElementById(`sub-${cat}-${subCat}`);
  const inp = document.getElementById(`subfn-${cat}-${subCat}`);
  if (!inp) return;
  inp.disabled = !cb.checked;
  inp.style.opacity = cb.checked ? "1" : ".4";
  _syncCreateSubMaster(cat);
}

// ── Create-menu select-all (mirrors the edit menu; derived state only) ───────
function _syncCreateSubMaster(cat) {
  const master = document.getElementById(`submaster-${cat}`);
  const panel  = document.getElementById(`sub-opts-${cat}`);
  if (!master || !panel) return;
  const boxes = [...panel.querySelectorAll("input[type=checkbox]")].filter(b => b !== master);
  master.checked = boxes.length > 0 && boxes.every(b => b.checked);
}

function _syncCreateMasterCats() {
  const master = document.getElementById("master-cats");
  if (!master) return;
  const rows = [...document.querySelectorAll("#split-config input[type=checkbox][id^='sel-']")];
  master.checked = rows.length > 0 && rows.every(cb => cb.checked);
}

function toggleAllSubOptions(cat) {
  const master = document.getElementById(`submaster-${cat}`);
  const panel  = document.getElementById(`sub-opts-${cat}`);
  if (!master || !panel) return;
  // Sub-files only apply to an extracted parent; ticking "all" implies the parent.
  const parent = document.getElementById(`sel-${cat}`);
  if (master.checked && parent && !parent.checked) {
    parent.checked = true;
    toggleSplitRow(cat);
  }
  const on = master.checked;
  panel.querySelectorAll("input[type=checkbox]").forEach(cb => {
    if (cb === master) return;
    cb.checked = on;
    toggleSubOption(cat, cb.id.slice(`sub-${cat}-`.length));
  });
  _syncCreateSubMaster(cat);
}

function toggleAllCategories() {
  const master = document.getElementById("master-cats");
  if (!master) return;
  const on = master.checked;
  document.querySelectorAll("#split-config input[type=checkbox][id^='sel-']").forEach(cb => {
    if (cb.checked === on) return;
    cb.checked = on;
    toggleSplitRow(cb.id.slice("sel-".length));
  });
}

// ═══════════════════════════════════════════════════════════════════════════════
// Create workspace
// ═══════════════════════════════════════════════════════════════════════════════
async function createWorkspace() {
  if (!state.uploadedFile) { toast("Upload a file first", "warn"); return; }

  const name = document.getElementById("ws-name-input").value.trim();
  if (!name) { toast("Enter a workspace name", "warn"); return; }

  // Collect selections
  const selections = [];
  if (state.inspectResult) {
    const cats = new Set();
    // Must match renderSplitConfig's filter, or this loop looks for rows that were
    // never rendered (and the server rejects them anyway).
    state.inspectResult.blocks.forEach(b => { if (!NON_EXTRACTABLE.has(b.category)) cats.add(b.category); });
    cats.forEach(cat => {
      const cb = document.getElementById(`sel-${cat}`);
      if (cb && cb.checked) {
        const fn = document.getElementById(`fn-${cat}`).value.trim() || `${cat}.inp`;
        const sub_selections = [];
        const subOpts = state.subOptions[cat] ?? [];
        subOpts.forEach(opt => {
          const subCb = document.getElementById(`sub-${cat}-${opt.sub_category}`);
          if (subCb && subCb.checked) {
            const subFn = document.getElementById(`subfn-${cat}-${opt.sub_category}`).value.trim()
              || opt.default_filename;
            sub_selections.push({ sub_category: opt.sub_category, filename: subFn });
          }
        });
        selections.push({ category: cat, filename: fn, sub_selections });
      }
    });
  }

  const btn = document.querySelector("#create-btn-row button");
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner"></span> Creating…`;

  try {
    const fd = new FormData();
    fd.append("file", state.uploadedFile);
    fd.append("name", name);
    fd.append("selections", JSON.stringify(selections));
    await api("POST", "/api/workspaces", fd);
    toast(`Workspace "${name}" created`, "ok");
    await loadWorkspaces();
    openWorkspace(name);
    resetNewWorkspace();
  } catch (e) {
    toast("Failed: " + e.message, "error");
  } finally {
    // Always restore the button. On success the row is only hidden, so a button
    // left reading "Creating…" and disabled comes back that way on the next
    // upload and looks like an upload that hangs forever.
    btn.disabled = false;
    btn.textContent = "Create workspace";
  }
}

function resetNewWorkspace() {
  state.uploadedFile = null;
  state.inspectResult = null;
  document.getElementById("upload-zone").innerHTML = `
    <div class="icon">📂</div>
    <p>Drop <code>.inp</code> file here or click to browse</p>
    <div class="hint">Abaqus input files only</div>`;
  document.getElementById("upload-input").value = "";
  document.getElementById("ws-name-input").value = "";
  document.getElementById("inspector-section").style.display = "none";
  document.getElementById("split-config-section").style.display = "none";
  document.getElementById("create-btn-row").style.display = "none";
  document.getElementById("inspector-tree").innerHTML = "";
  document.getElementById("split-config").innerHTML = "";
}

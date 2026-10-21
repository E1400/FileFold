// ═══════════════════════════════════════════════════════════════════════════════
// View router
// ═══════════════════════════════════════════════════════════════════════════════
function showView(name) {
  // Unsaved edits in the editor: ask before going anywhere else.
  if (state.view === "editor" && name !== "editor" && !guardLeaveEditor(() => showView(name))) return;
  // Leaving a workspace with split choices not applied yet: ask first. The editor is
  // not "leaving" (Back returns to the same Splits tab, choices intact).
  if ((state.view === "detail" || state.view === "editor") && name !== "detail" && name !== "editor"
      && !guardLeaveSplits(() => showView(name))) return;
  document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
  document.getElementById(`view-${name}`).classList.add("active");
  state.view = name;

  if (name === "home" || name === "new-workspace") {
    state.activeWs = null;
  }
  // Every visit to "new workspace" starts blank. Resetting only after a successful
  // create left an abandoned upload on screen the next time the user pressed New.
  if (name === "new-workspace") { resetNewWorkspace(); offerTourIfNew(); }
  else { endTour(null); removeTourPrompt(); }
  closeInfoPopover();
  document.getElementById("nav-info")?.classList.toggle("active", name === "help");
  renderSidebar();  // re-mark the open workspace
  if (name === "home") loadWorkspaces();
}

// ═══════════════════════════════════════════════════════════════════════════════
// Workspaces — list + sidebar
// ═══════════════════════════════════════════════════════════════════════════════
async function loadWorkspaces() {
  try {
    const wsData = await api("GET", "/api/workspaces");
    state.workspaces = wsData.workspaces ?? [];
    // Summaries drive the registry cards; keyed by name so renderHome can look
    // one up without caring about ordering.
    state.wsSummary = Object.fromEntries((wsData.summaries ?? []).map(s => [s.name, s]));
    renderSidebar();
    renderHome();
  } catch (e) {
    toastError("Couldn't load your workspaces", e);
  }
}

// The Workspaces panel is a file explorer: the open workspace (and any the person
// expands) lists its files; a click opens one in the editor while the tree stays.
function renderSidebar() {
  const el = document.getElementById("ws-list");
  document.getElementById("ws-count").textContent = state.workspaces.length || "";
  if (!state.workspaces.length) {
    el.innerHTML = `<div class="panel-empty">No workspaces yet</div>`;
  } else {
    const js = v => esc(v).replace(/'/g, "\\'");
    el.innerHTML = state.workspaces.map(name => {
      const open = name === state.activeWs || state.wsOpen.has(name);
      const files = state.wsFiles[name];
      const edited = (files || []).some(f => f.manually_edited);
      const head = `<div class="ws-item ${name === state.activeWs ? "active" : ""}" data-ws="${esc(name)}"${name === state.activeWs ? ' aria-current="true"' : ""}
             onclick="openWorkspace('${js(name)}')">
          <button type="button" class="ws-twisty" aria-expanded="${open}" aria-label="${open ? "Hide files" : "Show files"}"
                  onclick="event.stopPropagation(); toggleWsFiles('${js(name)}')">${open ? "▾" : "▸"}</button>
          <span class="lbl">${esc(name)}</span>
          ${edited ? `<span class="ws-edited" title="has edited files">●</span>` : ""}
        </div>`;
      if (!open) return head;
      if (!files) { _loadWsFiles(name); return head + `<div class="ws-tree" data-ws="${esc(name)}"><div class="panel-empty">Loading…</div></div>`; }
      const rows = orderedFiles(files, state.wsIncludeOrder[name]).map(f => {
        const current = state.view === "editor" && name === state.activeWs && f.filename === _modalFile;
        const mark = !f.exists ? `<span class="file-mark is-missing" title="missing">!</span>`
                   : f.manually_edited ? `<span class="file-mark is-edited" title="edited">●</span>` : "";
        return `<div class="ws-file role-${f.role}" data-file="${esc(f.filename)}" role="button" tabindex="0"
                     ${current ? 'aria-current="true"' : ""} title="${esc(f.filename)}"
                     onclick="openFileFromTree('${js(name)}', '${js(f.filename)}')"
                     onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();openFileFromTree('${js(name)}', '${js(f.filename)}')}">
            <span class="lbl">${esc(f.filename)}</span>${mark}</div>`;
      }).join("");
      return head + `<div class="ws-tree" data-ws="${esc(name)}">${rows}</div>`;
    }).join("");
  }
  renderSearch();
}

function toggleWsFiles(name) {
  const open = name === state.activeWs || state.wsOpen.has(name);
  if (open && name === state.activeWs) return;     // the open workspace always shows its files
  if (open) state.wsOpen.delete(name); else state.wsOpen.add(name);
  renderSidebar();
}

async function _loadWsFiles(name) {
  if (state.wsFilesLoading.has(name)) return;
  state.wsFilesLoading.add(name);
  try {
    const data = await api("GET", `/api/workspaces/${encodeURIComponent(name)}`);
    state.wsFiles[name] = data.files;
    state.wsIncludeOrder[name] = data.include_order || [];
  } catch (e) {
    state.wsOpen.delete(name);
    toastError(`Couldn't list the files of "${name}"`, e);
  } finally {
    state.wsFilesLoading.delete(name);
    renderSidebar();
  }
}

// Open a file from the tree: keep unsaved edits safe, switch workspace if needed.
async function openFileFromTree(ws, filename) {
  const go = async () => {
    if (ws !== state.activeWs) {
      await openWorkspace(ws);
      if (state.activeWs !== ws) return;           // the person stayed (pending split changes)
    }
    viewFile(filename);
  };
  if (state.view === "editor" && filename === _modalFile && ws === state.activeWs) return;
  if (!guardLeaveEditor(go)) return;
  go();
}

// ═══════════════════════════════════════════════════════════════════════════════
// Sidebar chrome — activity bar, collapsible panel, workspace group, search
// ═══════════════════════════════════════════════════════════════════════════════
const _sideKey = "filefold.sidebar";

function _sidePref() {
  try { return JSON.parse(localStorage.getItem(_sideKey)) || {}; } catch { return {}; }
}
function _saveSidePref() {
  try { localStorage.setItem(_sideKey, JSON.stringify({ panel: state.panel, collapsed: state.sideCollapsed })); } catch { /* private mode */ }
}

function applyPanel() {
  document.getElementById("sidebar").classList.toggle("collapsed", state.sideCollapsed);
  for (const name of ["workspaces", "search"]) {
    document.getElementById(`panel-${name}`).hidden = state.panel !== name;
    document.getElementById(`act-${name}`).classList.toggle("active", !state.sideCollapsed && state.panel === name);
  }
}

// Like VS Code: choosing another icon switches panel; choosing the active icon collapses it.
function selectPanel(name) {
  if (state.panel === name && !state.sideCollapsed) state.sideCollapsed = true;
  else { state.panel = name; state.sideCollapsed = false; }
  applyPanel();
  _saveSidePref();
  if (name === "search" && !state.sideCollapsed) document.getElementById("search-input").focus();
}

function renderSearch() {
  const out = document.getElementById("search-results");
  if (!out) return;
  const q = document.getElementById("search-input").value.trim().toLowerCase();
  if (!q) { out.innerHTML = `<div class="panel-empty">Type to search workspace titles.</div>`; return; }
  const rows = state.workspaces.filter(name => name.toLowerCase().includes(q));
  out.innerHTML = rows.length
    ? rows.map(name => `<div class="ws-item" onclick="openWorkspace('${esc(name).replace(/'/g, "\\'")}')"><span class="dot"></span><span class="lbl">${esc(name)}</span></div>`).join("")
    : `<div class="panel-empty">No results for “${esc(q)}”.</div>`;
}

(function initSidebar() {
  const p = _sidePref();
  state.panel = p.panel === "search" ? "search" : "workspaces";
  state.sideCollapsed = !!p.collapsed;
  applyPanel();
  document.getElementById("search-input").addEventListener("input", renderSearch);
  document.getElementById("search-input").addEventListener("keydown", e => {
    if (e.key === "Escape") { e.target.value = ""; renderSearch(); }
  });
})();

function renderHome() {
  const el = document.getElementById("home-cards");
  if (!state.workspaces.length) {
    el.innerHTML = `
      <div class="empty" style="grid-column:1/-1">
        <h2 class="empty-title">No workspaces yet</h2>
        <p>Split an Abaqus <code>.inp</code> file into a mother file and organized child files.</p>
        <div class="empty-actions">
          <button class="btn btn-primary" onclick="showView('new-workspace')">New workspace</button>
          <button class="btn btn-ghost" onclick="showView('new-workspace'); loadSample('Job-1')">Try a sample</button>
        </div>
      </div>`;
    return;
  }
  const n = state.workspaces.length;
  const footR = document.getElementById("sheet-foot-right");
  if (footR) {
    const bytes = Object.values(state.wsSummary).reduce((a, s) => a + (s.bytes || 0), 0);
    footR.textContent = `${n} ${n === 1 ? "workspace" : "workspaces"} · ${fmtBytes(bytes)} on disk`;
  }

  el.innerHTML = state.workspaces.map(name => {
    const sel = state.selectedWs.has(name);
    const sn = esc(name).replace(/'/g, "\\'");
    const s = state.wsSummary[name];

    if (!s || s.broken) {
      return `<div class="workspace-card" data-ws="${esc(name)}" onclick="openWorkspace('${sn}')">
        <div class="wsc-body">
          <div class="wsc-top"><span class="wsc-name">${esc(name)}</span></div>
          <div class="wsc-broken">manifest unreadable</div>
        </div>
      </div>`;
    }

    // Composition by size. Each slice is floored so a category that is a rounding
    // error of the deck still draws as a sliver rather than disappearing.
    const total = Math.max(1, s.categories.reduce((a, c) => a + c.bytes, 0));
    const bar = s.categories.map(c =>
      `<i style="background:${CAT_COLORS_var(c.category)};width:${Math.max(1.5, (c.bytes / total) * 100)}%"
          title="${esc(c.category)} — ${fmtBytes(c.bytes)}"></i>`).join("");

    // Cap the chips so a deck with six categories cannot stretch the card; the
    // remainder collapses into a +N.
    const SHOWN = 3;
    const shown = s.categories.slice(0, SHOWN);
    const extra = s.categories.length - shown.length;
    const chips = shown.map(c => {
      const col = CAT_COLORS_var(c.category);
      return `<span class="wsc-chip" style="--c:${col}">${esc(c.category)}</span>`;
    }).join("") + (extra > 0
      ? `<span class="wsc-chip" style="--c:var(--muted)"
               title="${esc(s.categories.slice(SHOWN).map(c => c.category).join(", "))}">+${extra}</span>`
      : "");

    return `<div class="workspace-card${sel ? " selected" : ""}" data-ws="${esc(name)}"
                 tabindex="0" role="button" aria-label="Open workspace ${esc(name)}"
                 onclick="openWorkspace('${sn}')"
                 onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();openWorkspace('${sn}')}">
      <div class="wsc-body">
        <div class="wsc-top">
          <input type="checkbox" class="wsc-check" ${sel ? "checked" : ""}
                 aria-label="Select ${esc(name)}"
                 onchange="toggleWsSelect('${sn}', this)" onclick="event.stopPropagation()">
          <span class="wsc-name">${esc(name)}</span>
          <span class="wsc-open">Open</span>
        </div>
        <div class="wsc-chips">${chips}</div>
        <div class="wsc-bar">${bar}</div>
        <div class="wsc-meta"><b>${s.file_count}</b> files · <b>${fmtBytes(s.bytes)}</b> · ${fmtCardDate(s.updated_at)}</div>
      </div>
      <div class="wsc-actions" onclick="event.stopPropagation()">
          <button class="btn btn-ghost btn-sm" onclick="renameWorkspace('${sn}')" title="Rename">Rename</button>
          <button class="btn btn-ghost btn-sm" onclick="exportWsCard('${sn}')" title="Export ZIP">Export</button>
        <button class="btn btn-ghost btn-sm" style="color:var(--danger)" onclick="deleteWsCard('${sn}')" title="Delete">Delete</button>
      </div>
    </div>`;
  }).join("");
}

function fmtBytes(n) {
  if (!n) return "0 B";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(n < 10240 ? 1 : 0)} KB`;
  return `${(n / 1048576).toFixed(1)} MB`;
}

// Short date for the card meta line: "7 Aug", with the year only when it is not
// the current one, so last year's decks are never ambiguous.
// "18 Oct, 13:14": the card date plus the time, for the Files tab.
function fmtDateTime(iso) {
  const d = new Date(iso);
  if (!iso || isNaN(d)) return "—";
  return `${fmtCardDate(iso)}, ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function fmtCardDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d)) return "—";
  const M = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  const now = new Date();
  const year = d.getFullYear() === now.getFullYear() ? "" : ` ${d.getFullYear()}`;
  return `${d.getDate()} ${M[d.getMonth()]}${year}`;
}

// ── Workspace selection ───────────────────────────────────────────────────────
function toggleWsSelect(name, cb) {
  if (cb.checked) state.selectedWs.add(name);
  else state.selectedWs.delete(name);
  const card = document.querySelector(`.workspace-card[data-ws="${name.replace(/"/g,'\\"')}"]`);
  if (card) card.classList.toggle("selected", cb.checked);
  updateSelToolbar();
}

function clearWsSelection() {
  state.selectedWs.clear();
  renderHome();
  updateSelToolbar();
}

function updateSelToolbar() {
  const n = state.selectedWs.size;
  const toolbar = document.getElementById("ws-sel-toolbar");
  toolbar.style.display = n ? "flex" : "none";
  document.getElementById("ws-sel-count").textContent = `${n} selected`;
}

// ── Single-card actions ───────────────────────────────────────────────────────
function renameWorkspace(name) {
  const card = document.querySelector(`.workspace-card[data-ws="${name.replace(/"/g,'\\"')}"]`);
  if (!card) return;
  const nameEl = card.querySelector(".wsc-name");
  const input = document.createElement("input");
  input.type = "text";
  input.id = "ws-rename-input";
  input.setAttribute("aria-label", "New workspace name");
  input.value = name;
  input.style.cssText = "font-size:var(--fs-lg);font-weight:600;width:100%;background:transparent;border:none;border-bottom:1px solid var(--accent);outline:none;color:var(--text);padding:0";
  let busy = false;
  const close = () => {
    clearFieldError(input);
    nameEl.textContent = name;
    nameEl.style.display = "";
    input.replaceWith(nameEl);
  };
  // Like a form field: a problem is shown under the name and the field stays open to fix
  // (Escape cancels). Nothing is sent until the name is acceptable.
  const commit = async () => {
    if (busy || !input.isConnected) return;
    const newName = input.value.trim();
    if (newName === name) { close(); return; }
    const problem = workspaceNameProblem(newName, name);
    if (problem) { showFieldError(input, problem); return; }
    busy = true;
    try {
      await api("PATCH", `/api/workspaces/${encodeURIComponent(name)}`, { name: newName });
      close();
      toast(`Renamed to "${newName}"`, "ok");
      state.selectedWs.delete(name);
      await loadWorkspaces();
    } catch (e) {
      if (!showApiErrorOnField(e, { name: input })) { close(); toastError(`Couldn't rename "${name}"`, e); }
    } finally {
      busy = false;
    }
  };
  // The card underneath opens the workspace on click and on Enter: keep those to the field.
  input.addEventListener("click", e => e.stopPropagation());
  input.addEventListener("keydown", e => {
    e.stopPropagation();
    if (e.key === "Enter") { e.preventDefault(); commit(); }
    if (e.key === "Escape") { e.preventDefault(); close(); }
  });
  input.addEventListener("blur", () => { if (!input.classList.contains("field-invalid")) commit(); });
  nameEl.style.display = "none";
  nameEl.insertAdjacentElement("afterend", input);
  input.focus();
  input.select();
}

async function exportWsCard(name) {
  await saveWorkspaceFile(name);   // Save dialog (saving.js)
}

async function deleteWsCard(name) {
  if (!confirm(`Delete workspace "${name}"? This cannot be undone.`)) return;
  try {
    await api("DELETE", `/api/workspaces/${encodeURIComponent(name)}`);
    state.selectedWs.delete(name);
    toast(`Deleted ${name}`);
    await loadWorkspaces();
    updateSelToolbar();
  } catch(e) {
    toastError("Couldn't delete the workspace", e);
  }
}

// ── Batch actions ─────────────────────────────────────────────────────────────
async function exportSelected() {
  for (const name of state.selectedWs) await exportWsCard(name);
}

async function deleteSelected() {
  const names = [...state.selectedWs];
  if (!names.length) return;
  if (!confirm(`Delete ${names.length} workspace(s)? This cannot be undone.\n\n${names.join(", ")}`)) return;
  for (const name of names) {
    try {
      await api("DELETE", `/api/workspaces/${encodeURIComponent(name)}`);
      state.selectedWs.delete(name);
    } catch(e) {
      toastError(`Couldn't delete "${name}"`, e);
    }
  }
  toast(`Deleted ${names.length} workspace(s)`);
  await loadWorkspaces();
  updateSelToolbar();
}

// ═══════════════════════════════════════════════════════════════════════════════
// Workspace detail
// ═══════════════════════════════════════════════════════════════════════════════
async function openWorkspace(name) {
  if (state.view === "editor" && !guardLeaveEditor(() => openWorkspace(name))) return;
  if ((state.view === "detail" || state.view === "editor") && name !== state.activeWs
      && !guardLeaveSplits(() => openWorkspace(name))) return;
  state.activeWs = name;
  // Drop the previous workspace's detail immediately. Leaving it in place means a
  // failed fetch below would strand activeWs and wsData pointing at different
  // workspaces, and every mutating action reads the plan from one and the target
  // name from the other.
  state.wsData = null;
  renderSidebar();
  showView("detail");
  document.getElementById("detail-title").textContent = name;
  document.getElementById("detail-meta").textContent = "Loading…";
  document.getElementById("detail-files").innerHTML = "";
  closeNewFileForm();
  // Clear stale splits content from any previously-opened workspace.
  document.getElementById("ws-split-config").innerHTML = "";

  try {
    const data = await api("GET", `/api/workspaces/${encodeURIComponent(name)}`);
    state.wsData = data;
    renderDetail(data);
    // If the Splits tab is already visible, populate it now for the new workspace.
    if (document.getElementById("tab-btn-splits")?.classList.contains("active")) {
      renderSplitsTab(data);
    }
  } catch (e) {
    toastError("Couldn't open the workspace", e);
  }
}

// Mother first, then each child (in the order the mother includes them, i.e. the deck's)
// followed by its sub-children (grandchildren).
function orderedFiles(files, includeOrder = []) {
  const rank = f => { const i = includeOrder.indexOf(f.filename); return i < 0 ? Infinity : i; };
  const children = files.filter(f => f.role === "child").sort((a, b) => rank(a) - rank(b));
  const grandchildren = files.filter(f => f.role === "grandchild");
  const ordered = files.filter(f => f.role === "mother");
  children.forEach(child => {
    ordered.push(child);
    grandchildren.filter(gc => gc.parent === child.filename).forEach(gc => ordered.push(gc));
  });
  // Any grandchildren whose parent wasn't in children list (shouldn't happen, but safe)
  grandchildren.filter(gc => !children.some(c => c.filename === gc.parent)).forEach(gc => ordered.push(gc));
  return ordered;
}

// A click anywhere on a Files row opens that file, except on the row's own controls.
function openFileRow(event, filename) {
  if (event.target.closest("button, a, input, .sort-cell")) return;
  viewFile(filename);
}

function renderDetail(data) {
  document.getElementById("detail-meta").innerHTML =
    `Source: <span class="mono">${esc(data.source_name)}</span> &nbsp;·&nbsp; Updated ${esc(fmtDateTime(data.updated_at))}`;

  const ordered = orderedFiles(data.files, data.include_order);
  state.wsFiles[data.name] = data.files;     // the sidebar tree shows the same files, same order
  state.wsIncludeOrder[data.name] = data.include_order || [];
  renderSidebar();

  // File order: a child file and its sub-file rows move as one item (sortable.js). The step
  // file is the fence, as in the Splits tab: model data must stay before the first *STEP.
  const included = new Set(data.include_order || []);
  const stepFile = data.selections.find(s => s.category === "step")?.filename;
  const sortCell = f => {
    if (f.role === "mother") return sortHandle(`mother:${f.filename}`, f.filename, false,
      "The mother file includes the others, so it stays at the top.");
    if (f.role === "grandchild") return sortHandle(`sub:${f.filename}`, f.filename, false,
      `Sub-files move with their parent file. Move ${f.parent} instead.`);
    if (f.filename === stepFile) return sortHandle(f.filename, f.filename, false,
      "The step file stays last: model data must come before the first *STEP.");
    if (!included.has(f.filename)) return sortHandle(f.filename, f.filename, false,
      "This file isn't included by the mother file, so it has no place in the deck.");
    return sortHandle(f.filename, f.filename, true, "");
  };

  const tbody = document.getElementById("detail-files");
  tbody.innerHTML = ordered.map(f => {
    let statusBadge;
    if (!f.exists)               statusBadge = `<span class="badge badge-danger">missing</span>`;
    else if (f.manually_edited)  statusBadge = `<span class="badge badge-warn">edited</span>`;
    else                         statusBadge = `<span class="badge badge-ok">clean</span>`;

    const roleBadge = f.role === "mother"
      ? `<span class="badge badge-muted">mother</span>`
      : f.role === "grandchild"
        ? `<span class="badge badge-sub">sub-child</span>`
        : f.added
          ? `<span class="badge badge-accent" title="A file you created, not one made by a split">added</span>`
          : `<span class="badge badge-accent">child</span>`;

    const lineCount = f.line_count != null
      ? `<span style="font-variant-numeric:tabular-nums">${f.line_count.toLocaleString()}</span>`
      : `<span class="text-muted">—</span>`;

    const indent = f.role === "grandchild"
      ? `<span class="tree-indent" aria-hidden="true"></span>`
      : "";

    const owner = f.role === "grandchild" ? f.parent : f.role === "mother" ? `mother:${f.filename}` : f.filename;
    const fn = esc(f.filename).replace(/'/g,"\\'");
    // The whole row opens the file (the name is the keyboard target); hover marks it.
    return `<tr data-sort-key="${esc(owner)}" data-role="${f.role}"${f.exists ? ` class="openable" onclick="openFileRow(event, '${fn}')"` : ""}>
      <td class="sort-cell">${sortCell(f)}</td>
      <td class="filename"><div class="filename-cell">${indent}<button type="button" class="filename-text filename-open" onclick="viewFile('${fn}')" ${f.exists ? "" : "disabled"}
              title="Open ${esc(f.filename)} to view or edit">${esc(f.filename)}</button><span class="open-hint" aria-hidden="true">Open</span></div></td>
      <td>${roleBadge}</td>
      <td>${f.category ? catChip(f.category) : "—"}</td>
      <td>${lineCount}</td>
      <td>${statusBadge}</td>
      <td>
        <div class="row-actions">
          ${f.added ? `<button class="btn btn-ghost btn-sm" onclick="foldAddedFile('${fn}')" ${f.exists ? "" : "disabled"}
                  title="Put this file's lines into ${esc(data.source_name)} where its *INCLUDE is, and delete the file">Fold into mother</button>` : ""}
          <button class="btn btn-ghost btn-sm" onclick="downloadFile('${esc(f.filename).replace(/'/g,"\\'")}')" ${f.exists ? "" : "disabled"}
                  aria-label="Download ${esc(f.filename)}" title="Download ${esc(f.filename)}">⬇</button>
        </div>
      </td>
    </tr>`;
  }).join("");
  syncSortButtons(tbody, _fileItems());
}

// The Files table as sortable items: each child with its sub-file rows.
function _fileItems() {
  const data = state.wsData;
  const included = new Set(data?.include_order || []);
  const stepFile = data?.selections.find(s => s.category === "step")?.filename;
  const items = [];
  let group = 0;
  document.querySelectorAll("#detail-files tr[data-sort-key]").forEach(tr => {
    const key = tr.dataset.sortKey, role = tr.dataset.role;
    if (role === "grandchild") {
      items.find(it => it.key === key)?.els.push(tr);
      const grip = tr.querySelector(".grip");
      items.push({ key: grip.dataset.key, els: [tr], movable: false, reason: grip.title, group: -1 });
      return;
    }
    if (key === stepFile) group++;
    const grip = tr.querySelector(".grip");
    const movable = role === "child" && key !== stepFile && included.has(key);
    items.push({ key: grip.dataset.key, els: [tr], movable, reason: grip.title, group });
  });
  return items;
}

// A file moved in the Files tab: applied straight away (this tab has no Apply button).
async function _filesReordered(order) {
  const ws = state.activeWs;
  try {
    await api("POST", `/api/workspaces/${encodeURIComponent(ws)}/reorder`, { order });   // quiet: the table shows it
  } catch (e) {
    toastError("Couldn't change the file order", e);
  }
  try { await _refreshDetail(ws); } catch (_) { /* the next open shows the real state */ }
}

makeSortable(document.getElementById("detail-files"), { items: _fileItems, onMove: _filesReordered });

// Re-read the open workspace after a change made from the Files tab.
async function _refreshDetail(ws) {
  const fresh = await api("GET", `/api/workspaces/${encodeURIComponent(ws)}`);
  if (ws !== state.activeWs) return;
  state.wsData = fresh;
  renderDetail(fresh);
  document.getElementById("ws-split-config").innerHTML = "";   // the Splits tab re-renders on its next visit
}

// New file: an empty file the mother *INCLUDEs before the first step; it opens in the editor.
// The name box pops up from the small button under the table.
function toggleNewFileForm() {
  if (document.getElementById("new-file-form").hidden) openNewFileForm(); else closeNewFileForm();
}

function openNewFileForm() {
  const form = document.getElementById("new-file-form");
  form.hidden = false;
  document.getElementById("new-file-btn").setAttribute("aria-expanded", "true");
  const input = document.getElementById("new-file-name");
  input.value = "";
  clearFieldErrors(form);
  input.focus();
}

function closeNewFileForm({ focusButton = false } = {}) {
  const form = document.getElementById("new-file-form");
  if (form.hidden) return;
  form.hidden = true;
  clearFieldErrors(form);
  const btn = document.getElementById("new-file-btn");
  btn.setAttribute("aria-expanded", "false");
  if (focusButton) btn.focus();
}

async function createNewFile(event) {
  event.preventDefault();
  const form = document.getElementById("new-file-form");
  const input = document.getElementById("new-file-name");
  const filename = input.value.trim();
  clearFieldErrors(form);
  const problem = filenameProblem(filename);
  if (problem) { showFieldError(input, problem); return; }
  const ws = state.activeWs;
  let added;
  try {
    ({ added } = await api("POST", `/api/workspaces/${encodeURIComponent(ws)}/new-file`, { filename }));
  } catch (e) {
    if (!showApiErrorOnField(e, { filename: input })) toastError("Couldn't create the file", e);
    return;
  }
  closeNewFileForm();
  toast(`Created ${added}, included by the mother`, "ok");
  try { await _refreshDetail(ws); } catch (_) { /* the next open shows the real state */ }
  if (ws === state.activeWs) viewFile(added);
}

document.getElementById("new-file-form").addEventListener("keydown", e => {
  if (e.key === "Escape") closeNewFileForm({ focusButton: true });
});
// A click anywhere outside the pop-up (and its button) closes it, like a menu.
document.addEventListener("mousedown", e => {
  if (!e.target.closest("#new-file-form, #new-file-btn")) closeNewFileForm();
});

// An added file goes back the way a split does: its lines replace its *INCLUDE in the mother.
async function foldAddedFile(filename) {
  const ws = state.activeWs;
  try {
    await api("POST", `/api/workspaces/${encodeURIComponent(ws)}/recombine`, { filenames: [filename] });
    toast(`Folded ${filename} into the mother file`, "ok");
  } catch (e) {
    toastError(`Couldn't fold ${filename} into the mother file`, e);
  }
  try { await _refreshDetail(ws); } catch (_) { /* the next open shows the real state */ }
}

async function exportWorkspace() {
  await saveWorkspaceFile(state.activeWs);
}

async function downloadFile(filename) {
  await saveWorkspaceFile(state.activeWs, filename);
}

async function deleteWorkspace() {
  if (!confirm(`Delete workspace "${state.activeWs}"? This cannot be undone.`)) return;
  try {
    await api("DELETE", `/api/workspaces/${encodeURIComponent(state.activeWs)}`);
    toast(`Deleted ${state.activeWs}`);
    state.activeWs = null;
    await loadWorkspaces();
    showView("home");
  } catch (e) {
    toastError("Couldn't delete the workspace", e);
  }
}

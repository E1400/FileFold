// ═══════════════════════════════════════════════════════════════════════════════
// View router
// ═══════════════════════════════════════════════════════════════════════════════
function showView(name) {
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
    toast("Failed to load workspaces: " + e.message, "error");
  }
}

function renderSidebar() {
  const el = document.getElementById("ws-list");
  document.getElementById("ws-count").textContent = state.workspaces.length || "";
  if (!state.workspaces.length) {
    el.innerHTML = `<div class="panel-empty">No workspaces yet</div>`;
  } else {
    el.innerHTML = state.workspaces.map(name =>
      `<div class="ws-item ${name === state.activeWs ? "active" : ""}" onclick="openWorkspace('${esc(name).replace(/'/g, "\\'")}')">
         <span class="dot"></span><span class="lbl">${esc(name)}</span>
       </div>`
    ).join("");
  }
  renderSearch();
}

// ═══════════════════════════════════════════════════════════════════════════════
// Sidebar chrome — activity bar, collapsible panel, workspace group, search
// ═══════════════════════════════════════════════════════════════════════════════
const _sideKey = "filefold.sidebar";

function _sidePref() {
  try { return JSON.parse(localStorage.getItem(_sideKey)) || {}; } catch { return {}; }
}
function _saveSidePref() {
  try { localStorage.setItem(_sideKey, JSON.stringify({ panel: state.panel, collapsed: state.sideCollapsed, wsOpen: state.wsGroupOpen })); } catch { /* private mode */ }
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

function toggleWsGroup() {
  state.wsGroupOpen = !state.wsGroupOpen;
  applyWsGroup();
  _saveSidePref();
}
function applyWsGroup() {
  document.getElementById("ws-group-toggle").setAttribute("aria-expanded", String(state.wsGroupOpen));
  document.getElementById("ws-list").hidden = !state.wsGroupOpen;
}

function _hl(text, q) {
  const i = q ? text.toLowerCase().indexOf(q) : -1;
  if (i < 0) return `<span class="lbl">${esc(text)}</span>`;
  return `<span class="lbl">` + esc(text.slice(0, i)) + "<mark>" + esc(text.slice(i, i + q.length)) + "</mark>" + esc(text.slice(i + q.length)) + `</span>`;
}

function renderSearch() {
  const out = document.getElementById("search-results");
  if (!out) return;
  const q = document.getElementById("search-input").value.trim().toLowerCase();
  if (!q) { out.innerHTML = `<div class="panel-empty">Type to search workspaces, categories and help topics.</div>`; return; }

  const wsRows = state.workspaces.filter(name => {
    const s = state.wsSummary[name] || {};
    return [name, s.source_name || "", ...(s.categories || []).map(c => c.category)].some(t => t.toLowerCase().includes(q));
  }).map(name => {
    const s = state.wsSummary[name] || {};
    const cat = (s.categories || []).find(c => c.category.toLowerCase().includes(q));
    const note = !name.toLowerCase().includes(q) && cat ? cat.category : (!name.toLowerCase().includes(q) && s.source_name ? s.source_name : "");
    return `<div class="ws-item" onclick="openWorkspace('${esc(name).replace(/'/g, "\\'")}')"><span class="dot"></span>${_hl(name, q)}${note ? `<span class="sub">${esc(note)}</span>` : ""}</div>`;
  });

  const topics = [...document.querySelectorAll("#view-help .help-toc a")]
    .filter(a => a.textContent.toLowerCase().includes(q))
    .map(a => `<div class="ws-item" onclick="openHelpTopic('${a.getAttribute("href").slice(1)}')"><span class="dot"></span>${_hl(a.textContent, q)}</div>`);

  out.innerHTML = (wsRows.length ? `<div class="search-group">Workspaces</div>${wsRows.join("")}` : "")
    + (topics.length ? `<div class="search-group">Help</div>${topics.join("")}` : "")
    || `<div class="panel-empty">No results for “${esc(q)}”.</div>`;
}

function openHelpTopic(id) {
  showView("help");
  document.getElementById(id)?.scrollIntoView({ block: "start" });
}

(function initSidebar() {
  const p = _sidePref();
  state.panel = p.panel === "search" ? "search" : "workspaces";
  state.sideCollapsed = !!p.collapsed;
  state.wsGroupOpen = p.wsOpen !== false;
  applyPanel();
  applyWsGroup();
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
        <div class="icon">📁</div>
        <p>No workspaces yet. Upload an Abaqus <code>.inp</code> file to get started.</p>
        <button class="btn btn-primary" onclick="showView('new-workspace')">+ New workspace</button>
      </div>`;
    return;
  }
  const n = state.workspaces.length;
  const footR = document.getElementById("sheet-foot-right");
  if (footR) {
    const bytes = Object.values(state.wsSummary).reduce((a, s) => a + (s.bytes || 0), 0);
    footR.textContent = `${n} ${n === 1 ? "deck" : "decks"} · ${fmtBytes(bytes)} on disk`;
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
      return `<span class="wsc-chip" style="background:color-mix(in srgb, ${col} 26%, transparent);` +
             `border-color:color-mix(in srgb, ${col} 45%, transparent);color:${col}">${esc(c.category)}</span>`;
    }).join("") + (extra > 0
      ? `<span class="wsc-chip" style="background:color-mix(in srgb, var(--muted) 22%, transparent);border-color:color-mix(in srgb, var(--muted) 40%, transparent);color:var(--muted)"
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
  input.value = name;
  input.style.cssText = "font-size:var(--fs-lg);font-weight:600;width:100%;background:transparent;border:none;border-bottom:1px solid var(--accent);outline:none;color:var(--text);padding:0";
  let committed = false;
  const finish = async () => {
    if (committed) return;
    committed = true;
    const newName = input.value.trim();
    nameEl.textContent = name;
    nameEl.style.display = "";
    input.replaceWith(nameEl);
    if (!newName || newName === name) return;
    try {
      await api("PATCH", `/api/workspaces/${encodeURIComponent(name)}`, { name: newName });
      toast(`Renamed to "${newName}"`, "ok");
      state.selectedWs.delete(name);
      await loadWorkspaces();
    } catch(e) {
      toast("Rename failed: " + e.message, "error");
    }
  };
  input.addEventListener("keydown", e => {
    if (e.key === "Enter") { e.preventDefault(); input.blur(); }
    if (e.key === "Escape") { input.value = name; input.blur(); }
  });
  input.addEventListener("blur", finish);
  nameEl.style.display = "none";
  nameEl.insertAdjacentElement("afterend", input);
  input.focus();
  input.select();
}

async function exportWsCard(name) {
  try {
    const blob = await api("GET", `/api/workspaces/${encodeURIComponent(name)}/export`);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `${name}.zip`; a.click();
    URL.revokeObjectURL(url);
    toast(`${name}.zip downloaded`);
  } catch(e) {
    toast("Export failed: " + e.message, "error");
  }
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
    toast("Delete failed: " + e.message, "error");
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
      toast(`Failed to delete ${name}: ` + e.message, "error");
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
    toast("Failed to load workspace: " + e.message, "error");
  }
}

function renderDetail(data) {
  document.getElementById("detail-meta").innerHTML =
    `Source: <span class="mono">${esc(data.source_name)}</span> &nbsp;·&nbsp; Updated: ${esc(data.updated_at)}`;

  // Sort files: mother first, then children (no parent), then grandchildren
  // immediately after the child they belong to.
  const mothers = data.files.filter(f => f.role === "mother");
  const children = data.files.filter(f => f.role === "child");
  const grandchildren = data.files.filter(f => f.role === "grandchild");

  const ordered = [...mothers];
  children.forEach(child => {
    ordered.push(child);
    grandchildren.filter(gc => gc.parent === child.filename).forEach(gc => ordered.push(gc));
  });
  // Any grandchildren whose parent wasn't in children list (shouldn't happen, but safe)
  grandchildren.filter(gc => !children.some(c => c.filename === gc.parent))
    .forEach(gc => ordered.push(gc));

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
        : `<span class="badge badge-accent">child</span>`;

    const lineCount = f.line_count != null
      ? `<span style="font-variant-numeric:tabular-nums">${f.line_count.toLocaleString()}</span>`
      : `<span class="text-muted">—</span>`;

    const indent = f.role === "grandchild"
      ? `<span class="tree-indent">└</span>`
      : "";

    return `<tr>
      <td class="filename"><div class="filename-cell">${indent}<span class="filename-text">${esc(f.filename)}</span></div></td>
      <td>${roleBadge}</td>
      <td>${f.category ? catChip(f.category) : "—"}</td>
      <td>${lineCount}</td>
      <td>${statusBadge}</td>
      <td>
        <button class="btn btn-ghost btn-sm" onclick="viewFile('${esc(f.filename).replace(/'/g,"\\'")}')" ${f.exists ? "" : "disabled"}>View / Edit</button>
      </td>
    </tr>`;
  }).join("");
}

async function exportWorkspace() {
  try {
    const blob = await api("GET", `/api/workspaces/${encodeURIComponent(state.activeWs)}/export`);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `${state.activeWs}.zip`; a.click();
    URL.revokeObjectURL(url);
    toast("Export downloaded");
  } catch (e) {
    toast("Export failed: " + e.message, "error");
  }
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
    toast("Delete failed: " + e.message, "error");
  }
}

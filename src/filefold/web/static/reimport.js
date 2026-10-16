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
// shows the previous run's "Analyzing <other-file>…" spinner, which looks like a
// hang but is just stale DOM with no request behind it.
const _REIMP_DROP_IDLE = `
  <div class="icon">📂</div>
  <p>Drop the updated <code>.inp</code> here or click to browse</p>
  <div class="hint">This becomes the new mother file</div>`;

function resetReimp() {
  // choice: conflicts -> "keep" | "take"; update: safe files ticked for updating
  state.reimp = { file: null, preview: null, choice: new Map(), update: new Set(), availableNewCats: [] };
  document.getElementById("reimp-upload-section").style.display = "";
  document.getElementById("reimp-preview-section").style.display = "none";
  document.getElementById("reimp-input").value = "";
  const zone = document.getElementById("reimp-drop");
  if (zone) { clearFieldError(zone); zone.innerHTML = _REIMP_DROP_IDLE; }
}

async function handleReimpUpload(file) {
  if (!file) return;
  const zone = document.getElementById("reimp-drop");
  clearFieldError(zone);
  if (!/\.inp$/i.test(file.name)) {
    showFieldError(zone, `FileFold reads Abaqus input files (.inp), and "${file.name}" isn't one. Choose a .inp file.`);
    return;
  }
  state.reimp.file = file;
  zone.innerHTML = `<div class="icon"><div class="spinner"></div></div><p>Analyzing ${esc(file.name)}…</p>`;

  try {
    const fd = new FormData();
    fd.append("file", file);
    const data = await api("POST", `/api/workspaces/${encodeURIComponent(state.activeWs)}/reimport/preview`, fd);
    state.reimp.preview = data;
    // Safe updates are ticked; conflicts keep your edits unless you choose otherwise.
    state.reimp.update = new Set((data.safe_to_update ?? []).map(s => s.filename));
    state.reimp.choice = new Map((data.needs_attention ?? []).map(s => [s.filename, "keep"]));

    document.getElementById("reimp-file-label").textContent = data.filename ?? file.name;
    renderReimpInspector(data.blocks ?? []);
    renderReimportPreview(data);

    document.getElementById("reimp-upload-section").style.display = "none";
    document.getElementById("reimp-preview-section").style.display = "";
  } catch (e) {
    zone.innerHTML = `<div class="icon">⚠</div><p>Couldn't read ${esc(file.name)}</p>`;
    showFieldError(zone, plainError(e));
    if (!(e instanceof ApiError)) console.error(e);
  }
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

// Categories in the new file that this workspace has not extracted yet. Top level only
// (what compute_split can route); never NON_EXTRACTABLE (the server rejects those).
function _reimpNewCats(blocks) {
  const existingCats = new Set((state.wsData?.selections ?? []).map(s => s.category));
  const fileCats = [];
  blocks.forEach(b => { if (!NON_EXTRACTABLE.has(b.category) && !fileCats.includes(b.category)) fileCats.push(b.category); });
  return fileCats.filter(c => !existingCats.has(c));
}

function toggleReimpNewCat(cat) {
  const checked = document.getElementById(`reimp-sel-${cat}`).checked;
  const row = document.getElementById(`reimp-row-${cat}`);
  const fnInput = document.getElementById(`reimp-fn-${cat}`);
  row.classList.toggle("selected", checked);
  fnInput.disabled = !checked;
  fnInput.style.opacity = checked ? "1" : ".4";
  _refreshReimpSummary();
}

// Your version and the incoming one, side by side, lines aligned per change.
function renderDiff(diff) {
  if (!diff) return "";
  if (diff.too_large) {
    return `<p class="text-muted text-sm diff-note">Too large to compare here (${diff.old_lines.toLocaleString()} lines now, ${diff.new_lines.toLocaleString()} incoming). Export the workspace to compare the files in another tool.</p>`;
  }
  const line = (cls, item) => item
    ? `<div class="dl ${cls}"><span class="ln">${item[0]}</span><span class="lt">${esc(item[1]) || "&nbsp;"}</span></div>`
    : `<div class="dl pad"><span class="ln"></span><span class="lt">&nbsp;</span></div>`;
  let left = "", right = "";
  for (const row of diff.rows) {
    if (row.type === "gap") {
      left += `<div class="dl gap">⋯</div>`; right += `<div class="dl gap">⋯</div>`;
      continue;
    }
    const n = Math.max(row.left.length, row.right.length);
    const cls = row.type === "equal" ? ["ctx", "ctx"] : ["del", "add"];
    for (let i = 0; i < n; i++) {
      left += line(cls[0], row.left[i]);
      right += line(cls[1], row.right[i]);
    }
  }
  const note = diff.truncated ? `<p class="text-muted text-sm diff-note">Showing the first changes only.</p>` : "";
  return `<div class="diff">
      <div class="diff-side yours"><div class="diff-head">Your version (now)</div>${left}</div>
      <div class="diff-side incoming"><div class="diff-head">Incoming</div>${right}</div>
    </div>${note}`;
}

function _diffSize(diff) {
  if (!diff || diff.too_large || diff.added == null) return "";
  return `<span class="diff-size"><span class="add">+${diff.added}</span> <span class="del">−${diff.removed}</span></span>`;
}

function toggleReimpDiff(btn) {
  const panel = btn.closest(".reimp-item").querySelector(".reimp-diff");
  const open = panel.hidden;
  panel.hidden = !open;
  btn.textContent = open ? "Hide changes" : "Show changes";
  btn.setAttribute("aria-expanded", String(open));
}

function renderReimportPreview(data) {
  const el = document.getElementById("reimp-results");
  const conflicts = data.needs_attention ?? [];
  const updates   = data.safe_to_update ?? [];
  const unchanged = data.unchanged ?? [];
  const newCats   = _reimpNewCats(data.blocks ?? []);
  state.reimp.availableNewCats = newCats;
  const id = name => name.replace(/[^A-Za-z0-9_-]/g, "_");
  let html = "";

  if (conflicts.length) {
    html += `<section class="reimp-group" data-group="conflict">
      <h3><span class="badge badge-warn">Conflict</span> ${conflicts.length} — you edited ${conflicts.length === 1 ? "this file" : "these files"} and ${conflicts.length === 1 ? "it" : "they"} also changed in the new file</h3>
      ${conflicts.map(s => `
        <div class="reimp-item is-conflict">
          <div class="reimp-item-head">
            <span class="fname">${esc(s.filename)}</span>${catChip(s.category)}${_diffSize(s.diff)}
            <span class="spacer"></span>
            <button type="button" class="btn btn-ghost btn-sm" aria-expanded="true" onclick="toggleReimpDiff(this)">Hide changes</button>
          </div>
          <div class="reimp-diff">${renderDiff(s.diff)}</div>
          <div class="reimp-choice" role="radiogroup" aria-label="What to do with ${esc(s.filename)}">
            <label><input type="radio" name="reimp-choice-${id(s.filename)}" value="keep" checked
                   onchange="setReimpChoice('${esc(s.filename)}', 'keep')"> Keep my edits</label>
            <label><input type="radio" name="reimp-choice-${id(s.filename)}" value="take"
                   onchange="setReimpChoice('${esc(s.filename)}', 'take')"> Take incoming</label>
          </div>
        </div>`).join("")}
    </section>`;
  }

  if (updates.length) {
    html += `<section class="reimp-group" data-group="update">
      <h3><span class="badge badge-ok">Will update</span> ${updates.length} — changed in the new file, not edited here</h3>
      ${updates.map(s => `
        <div class="reimp-item is-update">
          <div class="reimp-item-head">
            <label class="reimp-check"><input type="checkbox" checked aria-label="Update ${esc(s.filename)}"
                   onchange="toggleReimpUpdate('${esc(s.filename)}', this.checked)">
              <span class="fname">${esc(s.filename)}</span></label>${catChip(s.category)}${_diffSize(s.diff)}
            <span class="spacer"></span>
            <button type="button" class="btn btn-ghost btn-sm" aria-expanded="false" onclick="toggleReimpDiff(this)">Show changes</button>
          </div>
          <div class="reimp-diff" hidden>${renderDiff(s.diff)}</div>
        </div>`).join("")}
    </section>`;
  }

  if (newCats.length) {
    html += `<section class="reimp-group" data-group="new">
      <h3>New categories — in the new file, not extracted here yet. Tick any to give it its own child file.</h3>
      <div class="split-grid">${newCats.map(cat => {
        const c = CAT_COLORS_var(cat);
        return `<div class="split-row" id="reimp-row-${cat}">
          <label>
            <input type="checkbox" id="reimp-sel-${cat}" onchange="toggleReimpNewCat('${cat}')">
            <span class="chip" style="background:color-mix(in srgb, ${c} 26%, transparent);border-color:color-mix(in srgb, ${c} 45%, transparent);color:${c}">${cat}</span>
          </label>
          <input type="text" id="reimp-fn-${cat}" value="${cat}.inp" placeholder="filename.inp" style="opacity:.4" disabled>
          <span class="text-muted text-sm mono">new</span>
        </div>`;
      }).join("")}</div>
    </section>`;
  }

  if (unchanged.length) {
    html += `<section class="reimp-group" data-group="unchanged">
      <h3><span class="badge badge-muted">Unchanged</span> ${unchanged.length} — same in both, left alone</h3>
      <p class="reimp-unchanged">${unchanged.map(s => `<span class="fname">${esc(s.filename)}</span>`).join(" · ")}</p>
    </section>`;
  }

  const mother = data.mother;
  if (mother) {
    html += `<section class="reimp-group" data-group="mother">
      <h3>Mother file</h3>
      <p><span class="fname">${esc(mother.filename)}</span> is always updated from the new file${mother.changed ? "." : " (no change in it)."}</p>
    </section>`;
  }

  el.innerHTML = html;
  _refreshReimpSummary();
}

function setReimpChoice(filename, choice) {
  state.reimp.choice.set(filename, choice);
  _refreshReimpSummary();
}

function toggleReimpUpdate(filename, checked) {
  if (checked) state.reimp.update.add(filename);
  else state.reimp.update.delete(filename);
  _refreshReimpSummary();
}

function _reimpNewSelections() {
  return state.reimp.availableNewCats
    .filter(cat => document.getElementById(`reimp-sel-${cat}`)?.checked)
    .map(cat => ({ category: cat, filename: document.getElementById(`reimp-fn-${cat}`)?.value.trim() || `${cat}.inp` }));
}

// What Apply will do, in words, next to the button.
function _refreshReimpSummary() {
  const el = document.getElementById("reimp-summary");
  if (!el) return;
  const choices = [...state.reimp.choice.values()];
  const kept = choices.filter(c => c === "keep").length;
  const replaced = choices.filter(c => c === "take").length;
  const parts = [];
  if (kept) parts.push(`${kept} kept`);
  if (replaced) parts.push(`${replaced} replaced`);
  if (state.reimp.update.size) parts.push(`${state.reimp.update.size} updated`);
  const added = _reimpNewSelections().length;
  if (added) parts.push(`${added} new`);
  el.textContent = parts.length ? `Apply: ${parts.join(", ")}, mother updated` : "Apply: mother updated";
}

async function applyReimp() {
  if (!state.reimp.file) return;
  const btn = document.getElementById("reimp-apply-btn");
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner"></span> Applying…`;

  const toUpdate = [...state.reimp.update,
    ...[...state.reimp.choice].filter(([, c]) => c === "take").map(([f]) => f)];

  try {
    const fd = new FormData();
    fd.append("file", state.reimp.file);
    fd.append("filenames", JSON.stringify(toUpdate));
    fd.append("added_selections", JSON.stringify(_reimpNewSelections()));
    const result = await api("POST", `/api/workspaces/${encodeURIComponent(state.activeWs)}/reimport/apply`, fd);
    const wsName = result.workspace ?? state.activeWs;
    toast(`Reimport applied`, "ok");
    // workspace name in state may have changed if source_name updated
    state.activeWs = wsName;
    await loadWorkspaces();
    openWorkspace(wsName);
  } catch (e) {
    toastError("Couldn't apply the reimport", e);
    btn.disabled = false;
    btn.textContent = "Apply updates";
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Workspace detail tabs + Splits tab
// ═══════════════════════════════════════════════════════════════════════════════
function switchDetailTab(tab) {
  ["files", "splits"].forEach(t => {
    document.getElementById(`tab-content-${t}`).style.display = t === tab ? "" : "none";
    document.getElementById(`tab-btn-${t}`).classList.toggle("active", t === tab);
  });
  if (tab === "splits" && state.wsData) {
    const grid = document.getElementById("ws-split-config");
    // Render only when the grid is empty or shows another workspace. Coming back from the
    // Files tab (or the editor) must keep choices that are not applied yet; Apply and
    // Discard re-render explicitly.
    if (!grid.children.length || state.splitsRenderedFor !== state.wsData.name) renderSplitsTab(state.wsData);
  }
}

function renderSplitsTab(data) {
  const existingByCategory = {};
  data.selections.forEach(sel => { existingByCategory[sel.category] = sel; });

  // Use file_records (data.files) as ground truth for which sub-splits actually exist on disk.
  // selections may list sub-splits that were never created (stale state from a failed extract).
  const actualGrandchildren = new Set(
    (data.files || []).filter(f => f.role === "grandchild" && f.exists).map(f => f.filename)
  );

  // Only show categories that actually exist in this workspace's source file
  const allCats = [...(data.available_categories || [])];
  data.selections.forEach(sel => { if (!allCats.includes(sel.category)) allCats.push(sel.category); });

  const el = document.getElementById("ws-split-config");
  state.splitsRenderedFor = data.name;
  if (!el.dataset.watching) {            // one listener for every checkbox and filename field
    el.dataset.watching = "1";
    el.addEventListener("input", refreshSplitsPending);
    el.addEventListener("change", refreshSplitsPending);
  }
  if (!allCats.length) {
    el.innerHTML = `<p class="text-muted">No categories available.</p>`;
    refreshSplitsPending();
    return;
  }

  // Master toggle. Its id deliberately avoids the "ws-sel-" prefix: applyEditSplits
  // collects categories with [id^='ws-sel-'] and would otherwise read this box as a
  // category literally named "all", send it to /extract, and fail the whole batch.
  // The master is display-only — nothing reads it when building the apply payload.
  const togglable = allCats.filter(c => !NON_EXTRACTABLE.has(c));
  const allOn = togglable.length > 0 && togglable.every(c => !!existingByCategory[c]);
  const masterRow = `
    <div class="split-row" style="background:transparent;border-style:dashed">
      <div class="split-row-header">
        <input type="checkbox" id="ws-master-cats" ${allOn ? "checked" : ""}
               onchange="wsToggleAllCategories()">
        <label for="ws-master-cats" style="cursor:pointer;user-select:none;font-weight:600">
          Select all categories
        </label>
        <span class="text-muted text-sm" style="margin-left:8px">${togglable.length} available</span>
      </div>
    </div>`;

  el.innerHTML = masterRow + allCats.map(cat => {
    const c = CAT_COLORS_var(cat);
    const existing = existingByCategory[cat];
    const isExtracted = !!existing;
    const defaultFn = isExtracted ? existing.filename : `${cat}.inp`;
    const subOpts = data.sub_options?.[cat] ?? [];  // per-deck: only what exists
    const existingSubs = {};
    if (existing) existing.sub_selections.forEach(ss => { existingSubs[ss.sub_category] = ss.filename; });

    // A sub-split is checked only if its file actually exists on disk (in file_records).
    // A parent ("Elements") also shows checked when one of its refinements ("Element type: X")
    // is: together they mean "split elements by type", even if no elements were left over.
    const onDisk = key => !!(existingSubs[key] && actualGrandchildren.has(existingSubs[key]));
    const isOn = opt => onDisk(opt.sub_category) || subOpts.some(o => o.parent === opt.sub_category && onDisk(o.sub_category));
    const allSubsOn = subOpts.length > 0 && subOpts.every(isOn);
    const subPanel = subOpts.length ? `
      <div class="sub-options visible" id="ws-sub-opts-${cat}">
        <div class="text-muted text-sm" style="margin-bottom:4px;display:flex;align-items:center;gap:8px">
          <span>Split into sub-files: ${infoBtn("subsplit", "sub-files")}</span>
          <label style="display:inline-flex;align-items:center;gap:4px;cursor:pointer;user-select:none">
            <input type="checkbox" id="ws-submaster-${cat}" ${allSubsOn ? "checked" : ""}
                   ${isExtracted ? "" : "disabled"}
                   onchange="wsToggleAllSubOptions('${cat}')">
            <span>all</span>
          </label>
        </div>
        ${subOpts.map(opt => {
          const subFn = existingSubs[opt.sub_category] || opt.default_filename;
          const subChecked = isOn(opt);
          // Sub-options are interactive only when the parent category is extracted
          const subDisabled = !isExtracted;
          return `<div class="sub-option-row${opt.parent ? " sub-child" : ""}">
            <input type="checkbox" id="ws-sub-${cat}-${opt.sub_category}"
                   value="${opt.sub_category}" ${subChecked ? "checked" : ""}
                   ${subDisabled ? "disabled" : ""}
                   onchange="wsToggleSubOption('${cat}','${opt.sub_category}')">
            <label for="ws-sub-${cat}-${opt.sub_category}"
                   style="cursor:pointer;user-select:none">${esc(opt.label)}</label>
            <span class="sub-hint" id="ws-subhint-${cat}-${opt.sub_category}"></span>
            <span class="pending-slot" id="ws-submark-${cat}-${opt.sub_category}"></span>
            <input type="text" id="ws-subfn-${cat}-${opt.sub_category}" value="${subFn}"
                   placeholder="${opt.default_filename}"
                   ${!subChecked || subDisabled ? "disabled" : ""}
                   style="opacity:${subChecked && !subDisabled ? "1" : ".4"}">
          </div>`;
        }).join("")}
      </div>` : "";

    // A non-extractable category only appears here when it was split by an older
    // build. It can still be folded back, but not re-extracted — say so, rather
    // than letting the row silently disappear after the next apply.
    const oneWay = NON_EXTRACTABLE.has(cat) && isExtracted;

    return `<div class="split-row${isExtracted ? " selected" : ""}" id="ws-row-${cat}">
      <div class="split-row-header">
        <input type="checkbox" id="ws-sel-${cat}" ${isExtracted ? "checked" : ""}
               onchange="wsToggleSplitRow('${cat}')">
        <label for="ws-sel-${cat}" style="cursor:pointer;display:inline-flex;align-items:center;gap:6px;user-select:none">
          <span class="chip" style="background:color-mix(in srgb, ${c} 26%, transparent);border-color:color-mix(in srgb, ${c} 45%, transparent);color:${c}">${cat}</span>
          ${isExtracted ? `<span class="badge badge-accent">extracted</span>` : ""}
          <span class="pending-slot" id="ws-mark-${cat}"></span>
          ${oneWay ? `<span class="badge badge-warn"
                            title="${cat} owns the *INCLUDE directives. Unchecking folds it back into the mother permanently — it cannot be re-extracted.">can't re-split</span>` : ""}
        </label>
      </div>
      <input type="text" id="ws-fn-${cat}" value="${defaultFn}" placeholder="${cat}.inp"
             style="opacity:${isExtracted ? "1" : ".4"}" ${isExtracted ? "" : "disabled"}>
      <span class="text-muted text-sm" style="font-family:var(--mono)">*.inp</span>
      ${subPanel}
    </div>`;
  }).join("");
  // Apply availability to extracted categories as rendered (their sub-files start ticked).
  allCats.forEach(cat => {
    if (document.getElementById(`ws-sel-${cat}`)?.checked) { _refreshWsSubs(cat); _syncSubAllBox(cat); }
  });
  refreshSplitsPending();
}

function wsToggleSplitRow(cat) {
  const checked = document.getElementById(`ws-sel-${cat}`).checked;
  const row = document.getElementById(`ws-row-${cat}`);
  const fnInput = document.getElementById(`ws-fn-${cat}`);
  row.classList.toggle("selected", checked);
  fnInput.disabled = !checked;
  fnInput.style.opacity = checked ? "1" : ".4";
  _syncMasterCatBox();  // unchecking any single category must clear "select all"
  const subPanel = document.getElementById(`ws-sub-opts-${cat}`);
  if (!subPanel) return;
  if (!checked) {
    // Parent unchecked: disable all sub-inputs (panel stays visible)
    subPanel.querySelectorAll("input[type=checkbox]").forEach(cb => { cb.disabled = true; });
    subPanel.querySelectorAll("input[type=text]").forEach(inp => { inp.disabled = true; inp.style.opacity = ".4"; });
  } else {
    // Parent checked: enable sub-option checkboxes; text inputs follow their own checkbox
    subPanel.querySelectorAll("input[type=checkbox]").forEach(cb => { cb.disabled = false; });
    subPanel.querySelectorAll("input[type=text]").forEach(inp => {
      const subCat = inp.id.slice(`ws-subfn-${cat}-`.length);
      const subCb = document.getElementById(`ws-sub-${cat}-${subCat}`);
      const on = subCb ? subCb.checked : false;
      inp.disabled = !on;
      inp.style.opacity = on ? "1" : ".4";
    });
    _refreshWsSubs(cat);   // disable options that would produce no file
  }
}

function wsToggleSubOption(cat, subCat) {
  const options = state.wsData?.sub_options?.[cat] ?? [];
  const followed = followSubTree(options, subCat, key => document.getElementById(`ws-sub-${cat}-${key}`));
  [subCat, ...followed].forEach(key => {
    const cb = document.getElementById(`ws-sub-${cat}-${key}`);
    const inp = document.getElementById(`ws-subfn-${cat}-${key}`);
    if (!cb || !inp) return;
    inp.disabled = !cb.checked;
    inp.style.opacity = cb.checked ? "1" : ".4";
  });
  _refreshWsSubs(cat);
  _syncSubAllBox(cat);
}

function _refreshWsSubs(cat) {
  const data = state.wsData;
  refreshSubAvailability(data?.sub_claims?.[cat], data?.sub_options?.[cat] ?? [], {
    box: key => `ws-sub-${cat}-${key}`,
    name: key => `ws-subfn-${cat}-${key}`,
    hint: key => `ws-subhint-${cat}-${key}`,
  });
}

// Keep a category's "all" box in sync when its sub-options are toggled one by one,
// so it never claims everything is selected when it isn't. Derived state only —
// applyEditSplits reads the individual ws-sub-<cat>-<subcat> boxes by explicit id
// and never consults this one.
function _syncSubAllBox(cat) {
  const master = document.getElementById(`ws-submaster-${cat}`);
  const panel  = document.getElementById(`ws-sub-opts-${cat}`);
  if (!master || !panel) return;
  const boxes = [...panel.querySelectorAll("input[type=checkbox]")].filter(b => b !== master && !b.disabled);
  master.checked = boxes.length > 0 && boxes.every(b => b.checked);
}

function wsToggleAllSubOptions(cat) {
  const master = document.getElementById(`ws-submaster-${cat}`);
  const panel  = document.getElementById(`ws-sub-opts-${cat}`);
  if (!master || !panel) return;
  const on = master.checked;
  panel.querySelectorAll("input[type=checkbox]").forEach(cb => {
    if (cb === master || cb.disabled) return;
    cb.checked = on;
    const subCat = cb.id.slice(`ws-sub-${cat}-`.length);
    wsToggleSubOption(cat, subCat);
  });
  _refreshWsSubs(cat);
  _syncSubAllBox(cat);  // re-derive rather than assert: disabled rows may not have moved
}

// The master box is derived state, never an input to apply. Recompute it from the
// individual rows so unchecking any one category clears it, and it can never claim
// a state the rows don't actually have.
function _syncMasterCatBox() {
  const master = document.getElementById("ws-master-cats");
  if (!master) return;
  const rows = [...document.querySelectorAll("#ws-split-config input[type=checkbox][id^='ws-sel-']")]
    .filter(cb => !NON_EXTRACTABLE.has(cb.id.slice("ws-sel-".length)));
  master.checked = rows.length > 0 && rows.every(cb => cb.checked);
}

function wsToggleAllCategories() {
  const master = document.getElementById("ws-master-cats");
  if (!master) return;
  const on = master.checked;
  document.querySelectorAll("#ws-split-config input[type=checkbox][id^='ws-sel-']").forEach(cb => {
    const cat = cb.id.slice("ws-sel-".length);
    // Never flip a category the server refuses to extract; unchecking one is a
    // permanent fold-back, so leave those rows entirely under manual control.
    if (NON_EXTRACTABLE.has(cat)) return;
    if (cb.checked === on) return;
    cb.checked = on;
    wsToggleSplitRow(cat);
  });
}

// ── What Apply would do ──────────────────────────────────────────────────────────
// Read the Splits tab against the workspace as it is. Used by Apply itself, by the
// pending-changes bar, by the row marks and by the leave guard, so they always agree.
// Returns { toMerge, toExtract, toResplit, toRename, count, marks: {cat: {kind, text}},
// subMarks: {"cat:key": text} }.
function planSplitChanges(data = state.wsData) {
  const plan = { toMerge: [], toExtract: [], toResplit: [], toRename: [], count: 0, marks: {}, subMarks: {} };
  if (!data || state.splitsRenderedFor !== data.name) return plan;
  const existingByCategory = {};
  data.selections.forEach(sel => { existingByCategory[sel.category] = sel; });
  const actualGrandchildren = new Set(
    (data.files || []).filter(f => f.role === "grandchild" && f.exists).map(f => f.filename)
  );
  // Only real categories. Any master/decorative checkbox that ends up matching this
  // selector must never reach the server as a category name.
  const knownCats = new Set([...(data.available_categories || []), ...data.selections.map(s => s.category)]);
  const val = id => document.getElementById(id)?.value.trim();

  document.querySelectorAll("#ws-split-config input[type=checkbox][id^='ws-sel-']").forEach(cb => {
    const cat = cb.id.slice("ws-sel-".length);
    if (!knownCats.has(cat)) return;
    const existing = existingByCategory[cat];
    const subOpts = data.sub_options?.[cat] ?? [];

    if (existing && !cb.checked) {
      // Fold the whole category (and any sub-splits) back into the mother
      plan.toMerge.push(existing.filename);
      existing.sub_selections.forEach(ss => plan.toMerge.push(ss.filename));
      plan.marks[cat] = { kind: "fold", text: `folds back into ${data.source_name}` };
      plan.count++;

    } else if (!existing && cb.checked) {
      // Extract a brand-new category from the mother file
      const filename = val(`ws-fn-${cat}`) || `${cat}.inp`;
      const ticked = new Set(subOpts.map(o => o.sub_category)
        .filter(k => document.getElementById(`ws-sub-${cat}-${k}`)?.checked));
      const effective = effectiveSubKeys(data.sub_claims?.[cat], subOpts, ticked);
      const sub_selections = subOpts.filter(o => effective.has(o.sub_category)).map(o => ({
        sub_category: o.sub_category,
        filename: val(`ws-subfn-${cat}-${o.sub_category}`) || o.default_filename,
      }));
      sub_selections.forEach(ss => { plan.subMarks[`${cat}:${ss.sub_category}`] = "new file"; });
      plan.toExtract.push({ category: cat, filename, sub_selections });
      plan.marks[cat] = { kind: "new", text: "new" };
      plan.count++;

    } else if (existing && cb.checked) {
      const currentFn = val(`ws-fn-${cat}`) || existing.filename;
      if (currentFn !== existing.filename) {
        plan.toRename.push({ old_filename: existing.filename, new_filename: currentFn });
        plan.marks[cat] = { kind: "rename", text: `renamed from ${existing.filename}` };
        plan.count++;
      }
      if (!subOpts.length) return;
      const existingSubMap = {};
      existing.sub_selections.forEach(ss => { existingSubMap[ss.sub_category] = ss; });
      // A ticked parent its refinements emptied makes no file: not a change, not sent.
      const ticked = new Set(subOpts.map(o => o.sub_category)
        .filter(k => document.getElementById(`ws-sub-${cat}-${k}`)?.checked));
      const effective = effectiveSubKeys(data.sub_claims?.[cat], subOpts, ticked);
      let subChanged = false;
      const newSubSelections = [];
      subOpts.forEach(opt => {
        const key = opt.sub_category;
        const isOn = effective.has(key);
        const entry = existingSubMap[key];
        const wasOn = !!(entry && actualGrandchildren.has(entry.filename));
        const fn = val(`ws-subfn-${cat}-${key}`) || (entry?.filename ?? opt.default_filename);
        const renamed = isOn && wasOn && fn !== entry?.filename;
        if (isOn !== wasOn || renamed) {
          subChanged = true;
          plan.count++;
          plan.subMarks[`${cat}:${key}`] = !wasOn ? "new file" : !isOn ? `folds back into ${existing.filename}` : `renamed from ${entry.filename}`;
        }
        if (isOn) newSubSelections.push({ sub_category: key, filename: fn });
      });
      if (subChanged) plan.toResplit.push({ category: cat, sub_selections: newSubSelections });
    }
  });
  return plan;
}

// The workspace's files after Apply, with exact line counts and what changes, computed in
// the browser from the split plan (no request) whenever a choice changes.
function renderWsResult(data = state.wsData) {
  const el = document.getElementById("ws-result-tree");
  const plan = data?.split_plan?.categories;
  if (!el || !plan || state.splitsRenderedFor !== data.name) return;
  const files = data.files || [];
  const motherFile = files.find(f => f.role === "mother");
  const existingByCategory = {};
  data.selections.forEach(sel => { existingByCategory[sel.category] = sel; });
  const onDisk = new Set(files.filter(f => f.exists).map(f => f.filename));
  const val = id => document.getElementById(id)?.value.trim();
  const rows = [];
  let mother = motherFile?.line_count ?? 0;

  document.querySelectorAll("#ws-split-config input[type=checkbox][id^='ws-sel-']").forEach(cb => {
    const cat = cb.id.slice("ws-sel-".length);
    const nodes = plan[cat] || [];
    const existing = existingByCategory[cat];
    const oldSubs = existing ? existing.sub_selections.filter(ss => onDisk.has(ss.filename)) : [];
    if (!cb.checked) {
      if (!existing) return;
      mother += categoryLines(nodes) - 1;                 // folds back, its *INCLUDE goes
      rows.push({ name: existing.filename, role: "child", cat, mark: `folds back into ${data.source_name}`, markKind: "fold" });
      oldSubs.forEach(ss => rows.push({ name: ss.filename, role: "sub", cat, mark: "folds back", markKind: "fold" }));
      return;
    }
    if (!nodes.length) return;
    const filename = val(`ws-fn-${cat}`) || existing?.filename || `${cat}.inp`;
    const subOpts = data.sub_options?.[cat] ?? [];
    const ticked = new Set(subOpts.map(o => o.sub_category)
      .filter(k => document.getElementById(`ws-sub-${cat}-${k}`)?.checked));
    const effective = effectiveSubKeys(data.sub_claims?.[cat], subOpts, ticked);
    const subs = {};
    subOpts.filter(o => effective.has(o.sub_category)).forEach(o => {
      const old = oldSubs.find(ss => ss.sub_category === o.sub_category);
      subs[o.sub_category] = val(`ws-subfn-${cat}-${o.sub_category}`) || old?.filename || o.default_filename;
    });
    const lines = splitCategoryLines(nodes, filename, subs);
    if (!existing) mother -= categoryLines(nodes) - 1;     // newly extracted
    const childMark = !existing ? ["new", "new"] : filename !== existing.filename ? [`renamed from ${existing.filename}`, "rename"] : [];
    rows.push({ name: filename, role: "child", cat, lines: lines[filename], mark: childMark[0], markKind: childMark[1] });
    Object.entries(subs).forEach(([key, fn]) => {
      if (!lines[fn]) return;
      const old = oldSubs.find(ss => ss.sub_category === key);
      const m = !old ? ["new", "new"] : old.filename !== fn ? [`renamed from ${old.filename}`, "rename"] : [];
      rows.push({ name: fn, role: "sub", cat, lines: lines[fn], mark: m[0], markKind: m[1] });
    });
    oldSubs.filter(ss => !(ss.sub_category in subs)).forEach(ss =>
      rows.push({ name: ss.filename, role: "sub", cat, mark: `folds back into ${filename}`, markKind: "fold" }));
  });
  rows.unshift({ name: data.source_name, role: "mother", lines: mother });
  renderResultTree(el, rows);
  const n = rows.filter(r => r.markKind !== "fold").length;
  document.getElementById("ws-result-count").textContent = `${n} file${n === 1 ? "" : "s"}`;
}

// Update the pending-changes bar, the marks next to each changed row and the result tree.
function refreshSplitsPending() {
  renderWsResult();
  const plan = planSplitChanges();
  const bar = document.getElementById("splits-pending-bar");
  if (!bar) return plan;
  const n = plan.count;
  document.getElementById("splits-pending-count").textContent = n ? `${n} change${n === 1 ? "" : "s"} not applied yet` : "No changes";
  bar.classList.toggle("has-changes", n > 0);
  const apply = document.getElementById("ws-splits-apply-btn");
  if (!apply.querySelector(".spinner")) apply.disabled = n === 0;
  document.getElementById("splits-discard-btn").disabled = n === 0;
  document.querySelectorAll("#ws-split-config .pending-slot").forEach(slot => {
    const id = slot.id;
    let html = "";
    if (id.startsWith("ws-mark-")) {
      const m = plan.marks[id.slice("ws-mark-".length)];
      if (m) html = `<span class="pending-mark is-${m.kind}">${esc(m.text)}</span>`;
    } else {
      const [cat, ...rest] = id.slice("ws-submark-".length).split("-");
      const text = plan.subMarks[`${cat}:${rest.join("-")}`];
      if (text) html = `<span class="pending-mark-sub">${esc(text)}</span>`;
    }
    if (slot.innerHTML !== html) slot.innerHTML = html;
  });
  return plan;
}

function discardSplitChanges() {
  if (state.wsData) renderSplitsTab(state.wsData);
}

function hasPendingSplitChanges() {
  return !!state.wsData && planSplitChanges().count > 0;
}

// Leaving the workspace with choices that are not applied: ask, like the editor does.
// Returns true when it is fine to leave now; otherwise shows the dialog and calls
// `proceed` later if the person chooses Apply (and it worked) or Discard.
function guardLeaveSplits(proceed) {
  const plan = planSplitChanges();
  if (!plan.count) return true;
  const dlg = document.getElementById("pending-dialog");
  document.getElementById("pending-dialog-count").textContent = `${plan.count} change${plan.count === 1 ? "" : "s"}`;
  document.getElementById("pending-dialog-ws").textContent = state.wsData.name;
  askDialogChoice(dlg).then(async choice => {
    if (choice === "apply") {
      await applyEditSplits();
      if (!hasPendingSplitChanges()) proceed();
    } else if (choice === "discard") {
      discardSplitChanges();
      proceed();
    }
  });
  return false;
}

window.addEventListener("beforeunload", e => {
  if (state.view === "detail" && hasPendingSplitChanges()) { e.preventDefault(); e.returnValue = ""; }
});

async function applyEditSplits() {
  const data = state.wsData;
  if (!data) return;
  // The plan is built from wsData but posted against activeWs. Refuse to act if the
  // two ever disagree rather than applying one workspace's changes to another.
  if (data.name !== state.activeWs) {
    toast("The workspace changed while you were editing. Reopen it and try again.", "warn");
    return;
  }
  const grid = document.getElementById("ws-split-config");
  clearFieldErrors(grid);
  // Every file that will exist needs a valid name of its own (checked like a form).
  const fileInputs = [...grid.querySelectorAll("input[type=text][id^='ws-fn-'], input[type=text][id^='ws-subfn-']")]
    .filter(inp => !inp.disabled && !(parseFloat(inp.style.opacity) < 1))
    .map(inp => ({ input: inp, fn: inp.value.trim() || inp.placeholder }));
  const used = new Map([[data.source_name, null]]);
  for (const { fn, input } of fileInputs) {
    const problem = filenameProblem(fn)
      || (used.has(fn) ? (used.get(fn) ? errorText({ code: "duplicate_filename", value: fn })
                                        : `The mother file is already called "${fn}". Choose a different name.`) : null);
    if (problem) {
      // A clash concerns two fields: mark the one the person changed, if either.
      const other = used.get(fn);
      showFieldError(other && other.value !== other.defaultValue && input.value === input.defaultValue ? other : input, problem);
      return;
    }
    used.set(fn, input);
  }

  const { toMerge, toExtract, toResplit, toRename, count } = planSplitChanges(data);
  if (!count) {
    toast("No changes to apply", "warn");
    return;
  }

  let failed = null;
  const btn = document.getElementById("ws-splits-apply-btn");
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner"></span> Applying…`;

  const parts = [];
  if (toMerge.length)   parts.push(`${toMerge.length} merged back`);
  if (toExtract.length) parts.push(`${toExtract.length} extracted`);
  if (toResplit.length) parts.push(`${toResplit.length} re-split`);
  if (toRename.length)  parts.push(`${toRename.length} renamed`);

  try {
    if (toMerge.length)
      await api("POST", `/api/workspaces/${encodeURIComponent(state.activeWs)}/recombine`, { filenames: toMerge });
    if (toExtract.length)
      await api("POST", `/api/workspaces/${encodeURIComponent(state.activeWs)}/extract`, { selections: toExtract });
    for (const r of toResplit)
      await api("POST", `/api/workspaces/${encodeURIComponent(state.activeWs)}/resplit-child`, r);
    for (const r of toRename)
      await api("POST", `/api/workspaces/${encodeURIComponent(state.activeWs)}/rename-file`, r);
    toast(parts.join(", "), "ok");
  } catch (e) {
    failed = e;
  } finally {
    // Always refresh from server so the UI reflects actual workspace state, even after a
    // partial failure (e.g. recombine succeeded but resplit failed mid-way).
    try {
      const freshData = await api("GET", `/api/workspaces/${encodeURIComponent(state.activeWs)}`);
      state.wsData = freshData;
      renderDetail(freshData);
      renderSplitsTab(freshData);
    } catch (_) {}
    btn.textContent = "Apply changes";
    refreshSplitsPending();
  }
  // After the re-render, so a field error lands on the input that is now on screen.
  if (failed) {
    const findInput = value => [...document.querySelectorAll("#ws-split-config input[type=text]")]
      .find(inp => (inp.value.trim() || inp.placeholder) === value);
    if (!showApiErrorOnField(failed, { filename: findInput })) toastError("Couldn't apply the changes", failed);
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Workspace detail tabs + Splits tab
// ═══════════════════════════════════════════════════════════════════════════════
function switchDetailTab(tab) {
  const wasAlreadyActive = document.getElementById(`tab-btn-${tab}`)?.classList.contains("active");
  ["files", "splits"].forEach(t => {
    document.getElementById(`tab-content-${t}`).style.display = t === tab ? "" : "none";
    document.getElementById(`tab-btn-${t}`).classList.toggle("active", t === tab);
  });
  if (tab === "splits" && state.wsData) {
    const grid = document.getElementById("ws-split-config");
    // Re-render when switching from another tab, or when the grid was cleared (workspace changed).
    // Skip re-render only when already on Splits with content — that would wipe unsaved checkbox changes.
    if (!wasAlreadyActive || !grid.children.length) renderSplitsTab(state.wsData);
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
  if (!allCats.length) {
    el.innerHTML = `<p class="text-muted">No categories available.</p>`;
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

    const allSubsOn = subOpts.length > 0 && subOpts.every(
      opt => existingSubs[opt.sub_category] && actualGrandchildren.has(existingSubs[opt.sub_category])
    );
    const subPanel = subOpts.length ? `
      <div class="sub-options visible" id="ws-sub-opts-${cat}">
        <div class="text-muted text-sm" style="margin-bottom:4px;display:flex;align-items:center;gap:8px">
          <span>Split into sub-files:</span>
          <label style="display:inline-flex;align-items:center;gap:4px;cursor:pointer;user-select:none">
            <input type="checkbox" id="ws-submaster-${cat}" ${allSubsOn ? "checked" : ""}
                   ${isExtracted ? "" : "disabled"}
                   onchange="wsToggleAllSubOptions('${cat}')">
            <span>all</span>
          </label>
        </div>
        ${subOpts.map(opt => {
          const subFn = existingSubs[opt.sub_category] || opt.default_filename;
          // A sub-split is checked only if its file actually exists on disk (in file_records)
          const subChecked = !!(existingSubs[opt.sub_category] && actualGrandchildren.has(existingSubs[opt.sub_category]));
          // Sub-options are interactive only when the parent category is extracted
          const subDisabled = !isExtracted;
          return `<div class="sub-option-row">
            <input type="checkbox" id="ws-sub-${cat}-${opt.sub_category}"
                   value="${opt.sub_category}" ${subChecked ? "checked" : ""}
                   ${subDisabled ? "disabled" : ""}
                   onchange="wsToggleSubOption('${cat}','${opt.sub_category}')">
            <label for="ws-sub-${cat}-${opt.sub_category}"
                   style="cursor:pointer;user-select:none">${esc(opt.label)}</label>
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
  allCats.forEach(cat => { if (document.getElementById(`ws-sel-${cat}`)?.checked) _refreshWsSubs(cat); });
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
  const cb = document.getElementById(`ws-sub-${cat}-${subCat}`);
  const inp = document.getElementById(`ws-subfn-${cat}-${subCat}`);
  if (!inp) return;
  inp.disabled = !cb.checked;
  inp.style.opacity = cb.checked ? "1" : ".4";
  _refreshWsSubs(cat);
  _syncSubAllBox(cat);
}

function _refreshWsSubs(cat) {
  const data = state.wsData;
  refreshSubAvailability(data?.sub_claims?.[cat], data?.sub_options?.[cat] ?? [], {
    box: key => `ws-sub-${cat}-${key}`,
    name: key => `ws-subfn-${cat}-${key}`,
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

async function applyEditSplits() {
  const data = state.wsData;
  if (!data) return;
  // The plan is built from wsData but posted against activeWs. Refuse to act if the
  // two ever disagree rather than applying one workspace's changes to another.
  if (data.name !== state.activeWs) {
    toast("Workspace changed while editing — reopen it and try again", "warn");
    return;
  }

  const existingByCategory = {};
  data.selections.forEach(sel => { existingByCategory[sel.category] = sel; });

  const toMerge   = [];
  const toExtract = [];
  const toResplit = [];  // sub-split checkbox/filename changes within extracted categories
  const toRename  = [];  // simple file renames (no re-extraction needed)

  const actualGrandchildren = new Set(
    (data.files || []).filter(f => f.role === "grandchild" && f.exists).map(f => f.filename)
  );

  // Only real categories. Any master/decorative checkbox that ends up matching this
  // selector must never reach the server as a category name — that fails the whole
  // batch and the refresh afterwards looks like the selection silently resetting.
  const knownCats = new Set([
    ...(data.available_categories || []),
    ...data.selections.map(s => s.category),
  ]);

  document.querySelectorAll("#ws-split-config input[type=checkbox][id^='ws-sel-']").forEach(cb => {
    const cat = cb.id.slice("ws-sel-".length);
    if (!knownCats.has(cat)) return;
    const isChecked = cb.checked;
    const wasExtracted = !!existingByCategory[cat];

    if (wasExtracted && !isChecked) {
      // Fold the whole category (and any sub-splits) back into the mother
      toMerge.push(existingByCategory[cat].filename);
      existingByCategory[cat].sub_selections.forEach(ss => toMerge.push(ss.filename));

    } else if (!wasExtracted && isChecked) {
      // Extract a brand-new category from the mother file
      const fn = document.getElementById(`ws-fn-${cat}`)?.value.trim() || `${cat}.inp`;
      const subOpts = data.sub_options?.[cat] ?? [];  // per-deck: only what exists
      const sub_selections = subOpts
        .filter(opt => document.getElementById(`ws-sub-${cat}-${opt.sub_category}`)?.checked)
        .map(opt => ({
          sub_category: opt.sub_category,
          filename: document.getElementById(`ws-subfn-${cat}-${opt.sub_category}`)?.value.trim() || opt.default_filename,
        }));
      toExtract.push({ category: cat, filename: fn, sub_selections });

    } else if (wasExtracted && isChecked) {
      const existingSel = existingByCategory[cat];

      // Check if the parent child filename was renamed
      const currentFn = document.getElementById(`ws-fn-${cat}`)?.value.trim() || existingSel.filename;
      if (currentFn !== existingSel.filename) {
        toRename.push({ old_filename: existingSel.filename, new_filename: currentFn });
      }

      // Check sub-split checkbox and filename changes
      const subOpts = data.sub_options?.[cat] ?? [];  // per-deck: only what exists
      if (!subOpts.length) return;  // no sub-options for this category

      const existingSubMap = {};
      existingSel.sub_selections.forEach(ss => { existingSubMap[ss.sub_category] = ss; });

      let subChanged = false;
      const newSubSelections = [];
      subOpts.forEach(opt => {
        const isSubChecked = !!(document.getElementById(`ws-sub-${cat}-${opt.sub_category}`)?.checked);
        const existingEntry = existingSubMap[opt.sub_category];
        const wasSubExtracted = !!(existingEntry && actualGrandchildren.has(existingEntry.filename));

        // Detect both checkbox change AND filename change (for already-extracted sub-splits)
        const currentSubFn = document.getElementById(`ws-subfn-${cat}-${opt.sub_category}`)?.value.trim()
                             || (existingEntry?.filename ?? opt.default_filename);
        const fnChanged = isSubChecked && wasSubExtracted && currentSubFn !== existingEntry?.filename;

        if (isSubChecked !== wasSubExtracted || fnChanged) subChanged = true;
        if (isSubChecked) {
          newSubSelections.push({ sub_category: opt.sub_category, filename: currentSubFn });
        }
      });
      if (subChanged) toResplit.push({ category: cat, sub_selections: newSubSelections });
    }
  });

  if (!toMerge.length && !toExtract.length && !toResplit.length && !toRename.length) {
    toast("No changes to apply", "warn");
    return;
  }

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
    toast("Failed: " + e.message, "error");
  } finally {
    // Always refresh from server so the UI reflects actual workspace state, even after a
    // partial failure (e.g. recombine succeeded but resplit failed mid-way).
    try {
      const freshData = await api("GET", `/api/workspaces/${encodeURIComponent(state.activeWs)}`);
      state.wsData = freshData;
      renderDetail(freshData);
      renderSplitsTab(freshData);
    } catch (_) {}
    btn.disabled = false;
    btn.textContent = "Apply changes";
  }
}

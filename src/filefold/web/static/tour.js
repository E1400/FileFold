// ═══════════════════════════════════════════════════════════════════════════════
// Guided tour of creating a workspace
// ═══════════════════════════════════════════════════════════════════════════════
// Offered (never forced) to new visitors on the New Workspace screen, like the floating
// prompt in a spreadsheet app. Every step can be skipped or stepped back, Esc ends it, and
// the page stays fully usable underneath: the dimming is purely visual. The tour never
// loads a file on its own; where a step needs one it offers a button.

const TOUR_KEY = "filefold.tour";   // "done" | "dismissed"; absent for a first-time visitor

function _tourPref() { try { return localStorage.getItem(TOUR_KEY); } catch { return null; } }
function _setTourPref(v) { try { localStorage.setItem(TOUR_KEY, v); } catch { /* private mode: fine */ } }

const TOUR_STEPS = [
  { title: "Start with a model", target: () => document.getElementById("upload-zone"), side: "right",
    text: "Drop a .inp file here or click to browse. Nothing changes until you create the workspace." },
  { title: "No file handy?", target: () => document.getElementById("sample-btn"), side: "bottom",
    text: "Sample data has three real decks to try. Nothing loads until you choose one." },
  { title: "See what's inside", needsFile: true, target: () => document.getElementById("inspector-section"), side: "right",
    text: "Every keyword block in the file, coloured by category." },
  { title: "Choose what to extract", needsFile: true, target: () => document.getElementById("split-config-section"), side: "left",
    text: "Tick a category to give it its own file. Model set-up always stays in the main file." },
  { title: "Go deeper if you like", needsFile: true,
    target: () => document.querySelector("#split-config .split-row:has(.sub-options)") || document.querySelector("#split-config .split-row"),
    side: "left",
    text: "Ticking a category can reveal finer splits, such as one file per material. Skip this if whole categories are enough." },
  { title: "Name it and create", needsFile: true, target: () => document.getElementById("create-btn-row"), side: "top",
    text: "Give the workspace a name, then press Create workspace. You can change the split later from the Splits tab." },
];

const _tour = { active: false, i: 0, card: null, spot: null };

function _hasFile() { return !!state.uploadedFile; }

// ── the first-visit offer ─────────────────────────────────────────────────────────
function removeTourPrompt() { document.getElementById("tour-prompt")?.remove(); }

function offerTourIfNew() {
  if (_tour.active || _tourPref() || document.getElementById("tour-prompt")) return;
  const box = document.createElement("div");
  box.id = "tour-prompt";
  box.setAttribute("role", "region");
  box.setAttribute("aria-label", "Guided tour offer");
  box.innerHTML = `
    <strong>New to FileFold?</strong>
    <span>Take a one-minute tour of creating a workspace.</span>
    <div class="tour-prompt-actions">
      <button type="button" class="btn btn-primary btn-sm" data-act="start">Start tour</button>
      <button type="button" class="btn btn-ghost btn-sm" data-act="no">No thanks</button>
    </div>`;
  box.addEventListener("click", e => {
    const act = e.target.closest("[data-act]")?.dataset.act;
    if (act === "start") startTour();
    else if (act === "no") { _setTourPref("dismissed"); removeTourPrompt(); }
  });
  document.body.appendChild(box);
}

// ── the tour itself ───────────────────────────────────────────────────────────────
function startTour() {
  removeTourPrompt();
  if (state.view !== "new-workspace") showView("new-workspace");
  endTour(null);
  _tour.active = true;
  _tour.i = 0;
  _tour.spot = Object.assign(document.createElement("div"), { id: "tour-spot" });
  _tour.card = Object.assign(document.createElement("div"), { id: "tour-card" });
  _tour.card.setAttribute("role", "dialog");
  _tour.card.setAttribute("aria-label", "Guided tour");
  document.body.append(_tour.spot, _tour.card);
  _tour.card.addEventListener("click", _tourClick);
  document.addEventListener("keydown", _tourKey, true);
  window.addEventListener("resize", _tourRender);
  document.addEventListener("scroll", _tourRender, true);
  document.addEventListener("filefold:upload-ready", _tourRender);
  _tourRender(true);
}

// persist: "done" | "dismissed" | null (just tear down, e.g. when the screen changes)
function endTour(persist) {
  if (!_tour.active) return;
  _tour.active = false;
  _tour.card?.remove();
  _tour.spot?.remove();
  _tour.card = _tour.spot = null;
  document.removeEventListener("keydown", _tourKey, true);
  window.removeEventListener("resize", _tourRender);
  document.removeEventListener("scroll", _tourRender, true);
  document.removeEventListener("filefold:upload-ready", _tourRender);
  if (persist) _setTourPref(persist);
}

function _tourGo(delta) {
  const next = _tour.i + delta;
  if (next < 0) return;
  if (next >= TOUR_STEPS.length) { endTour("done"); return; }
  _tour.i = next;
  _tourRender(true);
}

function _tourClick(e) {
  const act = e.target.closest("[data-act]")?.dataset.act;
  if (act === "next") _tourGo(1);
  else if (act === "back") _tourGo(-1);
  else if (act === "skip") endTour("dismissed");
  else if (act === "sample") loadSample("Job-1");
}

function _tourKey(e) {
  if (!_tour.active) return;
  if (e.key === "Escape") { e.stopPropagation(); endTour("dismissed"); return; }
  if (e.target.closest("input, textarea, select, [contenteditable]")) return;   // don't hijack typing
  if (e.key === "ArrowRight") { e.preventDefault(); _tourGo(1); }
  else if (e.key === "ArrowLeft") { e.preventDefault(); _tourGo(-1); }
}

function _tourRender(focusNext = false) {
  if (!_tour.active) return;
  const step = TOUR_STEPS[_tour.i];
  const last = _tour.i === TOUR_STEPS.length - 1;
  const waitingForFile = step.needsFile && !_hasFile();
  const target = waitingForFile ? null : step.target();
  const visible = target && target.getClientRects().length > 0;

  _tour.card.innerHTML = `
    <span class="tour-arrow" data-side="none"></span>
    <h3>${esc(step.title)}</h3>
    <p>${waitingForFile ? "Add a file to see this step. Drop your own, or:" : esc(step.text)}</p>
    ${waitingForFile ? `<button type="button" class="btn btn-ghost btn-sm tour-sample" data-act="sample">Load the Job-1 sample</button>` : ""}
    <div class="tour-foot">
      <span class="tour-progress">${_tour.i + 1} of ${TOUR_STEPS.length}</span>
      <span class="spacer"></span>
      <button type="button" class="btn btn-ghost btn-sm" data-act="skip">Skip tour</button>
      <button type="button" class="btn btn-ghost btn-sm" data-act="back" ${_tour.i === 0 ? "disabled" : ""}>Back</button>
      <button type="button" class="btn btn-primary btn-sm" data-act="next">${last ? "Done" : "Next"}</button>
    </div>`;

  if (!visible) {                       // no target to point at: centre the card, no spotlight
    _tour.spot.style.display = "none";
    _tour.card.querySelector(".tour-arrow").remove();
    Object.assign(_tour.card.style, { left: "50%", top: "50%", transform: "translate(-50%, -50%)" });
  } else {
    if (focusNext === true) target.scrollIntoView({ block: "center", inline: "nearest" });
    _tourPlace(target, step.side);
  }
  if (focusNext === true) _tour.card.querySelector("[data-act=next]")?.focus({ preventScroll: true });
}

function _tourPlace(target, preferred) {
  const pad = 6, gap = 14, m = 12;
  const r = target.getBoundingClientRect();
  const spot = _tour.spot;
  Object.assign(spot.style, {
    display: "block", left: `${r.left - pad}px`, top: `${r.top - pad}px`,
    width: `${r.width + 2 * pad}px`, height: `${r.height + 2 * pad}px`,
  });
  const card = _tour.card;
  card.style.transform = "none";
  const w = card.offsetWidth, h = card.offsetHeight, vw = window.innerWidth, vh = window.innerHeight;
  const fits = {
    bottom: r.bottom + pad + gap + h <= vh - m,
    top: r.top - pad - gap - h >= m,
    right: r.right + pad + gap + w <= vw - m,
    left: r.left - pad - gap - w >= m,
  };
  const side = [preferred, "bottom", "top", "right", "left"].find(s => fits[s]) || "bottom";
  const clampX = x => Math.min(Math.max(x, m), vw - w - m);
  const clampY = y => Math.min(Math.max(y, m), vh - h - m);
  let left, top;
  if (side === "bottom" || side === "top") {
    left = clampX(r.left + r.width / 2 - w / 2);
    top = side === "bottom" ? r.bottom + pad + gap : r.top - pad - gap - h;
  } else {
    top = clampY(r.top + r.height / 2 - h / 2);
    left = side === "right" ? r.right + pad + gap : r.left - pad - gap - w;
  }
  top = clampY(top);
  card.style.left = `${left}px`;
  card.style.top = `${top}px`;
  // the arrow points from the card edge facing the target, toward the target's centre
  const arrow = card.querySelector(".tour-arrow");
  arrow.dataset.side = { bottom: "top", top: "bottom", right: "left", left: "right" }[side];
  if (side === "bottom" || side === "top") {
    arrow.style.left = `${Math.min(Math.max(r.left + r.width / 2 - left, 16), w - 16)}px`;
    arrow.style.top = "";
  } else {
    arrow.style.top = `${Math.min(Math.max(r.top + r.height / 2 - top, 16), h - 16)}px`;
    arrow.style.left = "";
  }
}

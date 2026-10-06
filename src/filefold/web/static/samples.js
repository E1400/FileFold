// ═══════════════════════════════════════════════════════════════════════════════
// Home page: chalkboard notes + sample data
// ═══════════════════════════════════════════════════════════════════════════════

// ── Notes (collapsible reference, not a walkthrough) ─────────────────────────────
// Open on a first visit (no workspaces yet), collapsed for people who already have
// workspaces; once the person toggles it, their choice wins and is remembered.
const NOTES_KEY = "filefold.notes";

function _notesPref() {
  try { return localStorage.getItem(NOTES_KEY); } catch { return null; }
}

function setNotesOpen(open, remember = true) {
  const toggle = document.getElementById("notes-toggle");
  const body = document.getElementById("notes-body");
  if (!toggle || !body) return;
  toggle.setAttribute("aria-expanded", String(open));
  body.hidden = !open;
  if (remember) {
    try { localStorage.setItem(NOTES_KEY, open ? "open" : "closed"); } catch { /* private mode: fine */ }
  }
}

function toggleNotes() {
  setNotesOpen(document.getElementById("notes-toggle").getAttribute("aria-expanded") !== "true");
}

// Called once the workspace list is known (renderHome), to choose the default.
let _notesDecided = false;
function applyNotesDefault(workspaceCount) {
  if (_notesDecided) return;
  _notesDecided = true;
  const pref = _notesPref();
  setNotesOpen(pref ? pref === "open" : workspaceCount === 0, false);
}

// Where files live depends on the build; show only the sentence that is true here.
function applyNotesMode() {
  const keep = window.FILEFOLD_STATIC ? "static" : "server";
  document.querySelectorAll("#notes [data-mode]").forEach(el => {
    if (el.dataset.mode !== keep) el.remove();
  });
}

// ── Sample decks ──────────────────────────────────────────────────────────────────
const SAMPLE_BASE = "static/samples/";   // relative, so it works under a sub-path (GitHub Pages)

function _sampleFacts(f) {
  const plural = (n, word) => `${n.toLocaleString()} ${word}${n === 1 ? "" : "s"}`;
  const facts = [fmtBytes(f.bytes), `${f.lines.toLocaleString()} lines`];
  if (f.parts.length) facts.push(plural(f.parts.length, "part"));
  if (f.steps.length) facts.push(plural(f.steps.length, "step"));
  if (f.materials) facts.push(plural(f.materials, "material"));
  if (f.contact_pairs) facts.push(plural(f.contact_pairs, "contact pair"));
  if (f.element_types.length) facts.push(f.element_types.join(", ") + " elements");
  if (f.line_endings === "windows") facts.push("Windows line endings");
  return facts;
}

function renderSamples(samples) {
  const el = document.getElementById("sample-cards");
  if (!el) return;
  el.innerHTML = samples.map(s => {
    const cats = Object.keys(s.facts.categories).filter(c => c !== "model" && c !== "unknown");
    return `<article class="sample-card" data-sample="${esc(s.id)}">
      <h3>${esc(s.title)}</h3>
      <p class="blurb">${esc(s.blurb)}</p>
      <ul class="sample-facts">${_sampleFacts(s.facts).map(t => `<li>${esc(t)}</li>`).join("")}</ul>
      <div class="chip-row" aria-label="Categories in this deck">${cats.map(catChip).join("")}</div>
      <div class="sample-actions">
        <button class="btn btn-primary btn-sm" type="button" onclick="loadSample('${esc(s.id)}')">Load into new workspace</button>
        <a class="btn btn-ghost btn-sm" href="${SAMPLE_BASE}${encodeURIComponent(s.file)}" download="${esc(s.file)}">Download</a>
      </div>
    </article>`;
  }).join("");
}

async function initSamples() {
  try {
    const res = await fetch(`${SAMPLE_BASE}manifest.json`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    renderSamples((await res.json()).samples);
  } catch (e) {
    const el = document.getElementById("sample-cards");
    if (el) el.innerHTML = `<p class="text-muted text-sm">Sample decks could not be loaded (${esc(e.message)}).</p>`;
  }
}

// Fetch a sample, hand it to the normal upload flow exactly as if it had been dropped in.
async function loadSample(id) {
  try {
    const res = await fetch(`${SAMPLE_BASE}${encodeURIComponent(id)}.inp`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const file = new File([await res.blob()], `${id}.inp`, { type: "text/plain" });
    showView("new-workspace");
    await handleUpload(file);
  } catch (e) {
    toast("Could not load the sample: " + e.message, "error");
  }
}

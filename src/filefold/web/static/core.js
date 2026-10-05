// ═══════════════════════════════════════════════════════════════════════════════
// State
// ═══════════════════════════════════════════════════════════════════════════════
const state = {
  view: "home",
  workspaces: [],       // list of workspace names
  activeWs: null,       // name of open workspace
  wsData: null,         // full detail response for the open workspace
  inspectResult: null,  // { filename, blocks }
  uploadedFile: null,   // File object
  wsSummary: {},        // { [name]: {file_count, split_count, bytes, categories[]} }
  selectedWs: new Set(), // workspace names selected on home page
  reimp: {
    file: null,
    preview: null,
    checked: new Set(),    // existing child filenames to update
    availableNewCats: [],  // cat names present in new file but not in workspace
  },
};

// Category colour lives in CSS (--cat-*) and nowhere else. Returning a var()
// reference rather than a hex means chips follow the theme automatically — the
// previous JS table held the old palette, so retuning the tokens changed nothing
// on screen and the two sets had silently diverged.
// Mirrors NON_EXTRACTABLE in api/main.py (the server rejects these outright);
// tests/e2e/test_ui.py asserts the two stay identical.
const NON_EXTRACTABLE = new Set(["unknown", "model"]);

const CAT_NAMES = new Set([
  "mesh", "material", "step", "loads", "contact", "constraint", "initial", "output", "model", "section", "unknown",
]);
function CAT_COLORS_var(cat) {
  return `var(--cat-${CAT_NAMES.has(cat) ? cat : "unknown"})`;
}
// Back-compat alias for the places that read a colour for a category.
const CAT_COLORS = new Proxy({}, { get: (_, k) => CAT_COLORS_var(String(k)) });

function catChip(cat) {
  const c = CAT_COLORS_var(cat);
  return `<span class="chip" style="background:color-mix(in srgb, ${c} 26%, transparent);` +
         `border-color:color-mix(in srgb, ${c} 45%, transparent);color:${c}">${cat}</span>`;
}

// ═══════════════════════════════════════════════════════════════════════════════
// API helper
// ═══════════════════════════════════════════════════════════════════════════════
async function api(method, path, body) {
  const opts = { method };
  if (body instanceof FormData) {
    opts.body = body;
  } else if (body !== undefined) {
    opts.headers = { "Content-Type": "application/json" };
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(txt || `HTTP ${res.status}`);
  }
  const ct = res.headers.get("content-type") ?? "";
  if (ct.includes("application/json")) return res.json();
  if (ct.includes("application/zip")) return res.blob();
  return res.text();
}

// ═══════════════════════════════════════════════════════════════════════════════
// Toast
// ═══════════════════════════════════════════════════════════════════════════════
function toast(msg, type = "ok") {
  const icons = { ok: "✓", warn: "⚠", error: "✕" };
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.innerHTML = `<span>${icons[type] ?? ""}</span><span>${msg}</span>`;
  document.getElementById("toast-container").appendChild(el);
  setTimeout(() => el.remove(), 3500);
}

// ═══════════════════════════════════════════════════════════════════════════════
// Theme toggle
// ═══════════════════════════════════════════════════════════════════════════════
function toggleTheme() {
  const root = document.documentElement;
  const cur = root.dataset.theme;
  if (!cur) {
    const sys = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    root.dataset.theme = sys === "dark" ? "light" : "dark";
  } else {
    root.dataset.theme = cur === "dark" ? "light" : "dark";
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Utility
// ═══════════════════════════════════════════════════════════════════════════════
function esc(s) {
  return String(s ?? "")
    .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")
    .replace(/"/g,"&quot;").replace(/'/g,"&#39;");
}


// ── Sub-split availability ───────────────────────────────────────────────────
// Several sub-split options can claim the same block (the "Elements" group and an
// "Element type: X" split both want an *ELEMENT; a part wants everything inside it).
// The splitter gives each block to the most specific ticked option, so a ticked option
// can end up with nothing and no file is made. The server reports, per kind of block,
// the keys that could receive it in the splitter's order ("claims"); from that we know
// exactly which options would produce a file and keep the rest from being offered.

// Keys that would receive at least one block if exactly `ticked` were selected.
// Mirrors filefold.core.subsplits.live_keys (a test keeps them in agreement).
function liveSubKeys(claims, ticked) {
  const live = new Set();
  for (const pattern of claims) {
    const owner = pattern.find(key => ticked.has(key));
    if (owner) live.add(owner);
  }
  return live;
}

// Untick options that a more specific ticked option fully covers, and disable any
// option that would produce an empty file if ticked now. `ids` maps an option key to
// its checkbox and filename-input element ids.
function refreshSubAvailability(claims, options, ids) {
  if (!claims || !claims.length) return;
  const rows = options.map(opt => ({
    key: opt.sub_category,
    box: document.getElementById(ids.box(opt.sub_category)),
    name: document.getElementById(ids.name(opt.sub_category)),
  })).filter(r => r.box);

  const ticked = () => new Set(rows.filter(r => r.box.checked).map(r => r.key));

  // 1. A ticked option with nothing left to take is dropped (the later, more specific
  //    choice wins).
  const live = liveSubKeys(claims, ticked());
  for (const r of rows) {
    if (r.box.checked && !live.has(r.key)) {
      r.box.checked = false;
      if (r.name) { r.name.disabled = true; r.name.style.opacity = ".4"; }
    }
  }
  // 2. An unticked option is only available if ticking it would give it blocks.
  const now = ticked();
  for (const r of rows) {
    if (r.box.checked) { r.box.disabled = false; r.box.title = ""; continue; }
    const wouldTake = liveSubKeys(claims, new Set([...now, r.key])).has(r.key);
    r.box.disabled = !wouldTake;
    r.box.title = wouldTake ? "" : "Nothing left for this option: everything it would match is already taken by another ticked option.";
  }
}

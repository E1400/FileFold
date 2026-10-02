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
  subOptions: {},       // { [category]: [{sub_category, label, default_filename}] }
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

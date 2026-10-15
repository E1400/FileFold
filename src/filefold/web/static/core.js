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
  let res;
  try {
    res = await fetch(path, opts);
  } catch {
    throw new ApiError(0, { code: "unreachable" });
  }
  if (!res.ok) {
    const txt = await res.text();
    let payload;
    try { payload = JSON.parse(txt); } catch { payload = { detail: txt }; }
    throw new ApiError(res.status, payload && typeof payload === "object" ? payload : { detail: txt });
  }
  const ct = res.headers.get("content-type") ?? "";
  if (ct.includes("application/json")) return res.json();
  if (ct.includes("application/zip")) return res.blob();
  return res.text();
}

// ═══════════════════════════════════════════════════════════════════════════════
// Errors: the server says what went wrong with a code (and the form field it is
// about); the app words it. Raw server text is never shown to the user.
// ═══════════════════════════════════════════════════════════════════════════════
class ApiError extends Error {
  constructor(status, payload = {}) {
    const info = { status, code: payload.code || (status >= 500 ? "server" : "error"),
                   field: payload.field || null, value: payload.value ?? null };
    super(errorText(info));
    Object.assign(this, info);
    this.detail = typeof payload.detail === "string" ? payload.detail : "";
  }
}

const NAME_RULE = "Names can't contain / or \\ and can't be just \".\" or \"..\".";

// One plain sentence per kind of problem. `field` tells a workspace name from a file name.
function errorText({ code, field, value, status }) {
  const v = value != null ? `"${value}"` : "";
  switch (code) {
    case "workspace_exists":    return `You already have a workspace called ${v}. Choose a different name.`;
    case "required":            return field === "filename" ? "Enter a file name." : field === "name" ? "Give the workspace a name." : "Something required was missing. Reload the page and try again.";
    case "invalid_name":        return field === "filename" ? `${v || "That"} isn't a valid file name. ${NAME_RULE}` : `${v || "That"} can't be used as a workspace name. ${NAME_RULE}`;
    case "filename_taken":      return `Another file in this workspace is already called ${v}. Choose a different name.`;
    case "duplicate_filename":  return `Two files would both be called ${v}. Give each one its own name.`;
    case "workspace_not_found": return "This workspace no longer exists. It may have been renamed or deleted in another window.";
    case "file_not_found":      return "This file is no longer in the workspace. It may have been renamed or folded back.";
    case "mother_missing":      return "The workspace's mother file is missing, so nothing more can be extracted from it.";
    case "not_extractable":     return "Model set-up always stays in the mother file and can't get a file of its own.";
    case "not_extracted":       return "That file is no longer split out. Reopen the workspace and try again.";
    case "unknown_category":    return "FileFold didn't recognise one of the categories. Reload the page and try again.";
    case "file_too_large":      return "This file is larger than this server accepts.";
    case "auth_required":       return "You need to sign in again. Reload the page.";
    case "unreachable":         return "FileFold can't be reached. Check that it is still running, then try again.";
    case "server":              return "Something went wrong inside FileFold. Try again; if it keeps happening, reload the page.";
    default:                    return status === 404 ? "That couldn't be found. Reload the page and try again."
                                                      : "That didn't work. Check your choices and try again.";
  }
}

// For code that calls fetch itself: a failed response as an ApiError (worded like the rest).
async function apiErrorFrom(res) {
  const txt = await res.text().catch(() => "");
  let payload;
  try { payload = JSON.parse(txt); } catch { payload = { detail: txt }; }
  return new ApiError(res.status, payload && typeof payload === "object" ? payload : { detail: txt });
}

// Plain wording for any thrown error (an ApiError, or a bug in the page itself).
function plainError(e) {
  return e instanceof ApiError ? e.message : "Something went wrong in the page. Reload it and try again.";
}

// Problems with a name typed into a form, checked before anything is sent.
function workspaceNameProblem(name, current = null) {
  if (!name) return errorText({ code: "required", field: "name" });
  if (/[\\/\u0000]/.test(name) || name === "." || name === "..") return errorText({ code: "invalid_name", field: "name", value: name });
  if (name !== current && (state.workspaces || []).includes(name)) return errorText({ code: "workspace_exists", value: name });
  return null;
}

function filenameProblem(name) {
  if (!name) return errorText({ code: "required", field: "filename" });
  if (/[\\/\u0000]/.test(name) || name === "." || name === "..") return errorText({ code: "invalid_name", field: "filename", value: name });
  return null;
}

// Mark a form field as wrong, like a web form does for a required field: red outline,
// the message right under it, and focus on it. Editing the field clears the mark.
function showFieldError(el, message) {
  if (!el) return false;
  clearFieldError(el);
  el.classList.add("field-invalid");
  const msg = document.createElement("p");
  msg.className = "field-error";
  msg.id = `${el.id || "field"}-error`;
  msg.setAttribute("role", "alert");
  msg.textContent = message;
  el.insertAdjacentElement("afterend", msg);
  if (el.matches("input, textarea, select")) {
    el.setAttribute("aria-invalid", "true");
    el.setAttribute("aria-describedby", msg.id);
    el.addEventListener("input", () => clearFieldError(el), { once: true });
    el.focus({ preventScroll: true });
  }
  el.scrollIntoView({ block: "center", behavior: "smooth" });
  return true;
}

function clearFieldError(el) {
  if (!el) return;
  el.classList.remove("field-invalid");
  el.removeAttribute("aria-invalid");
  el.removeAttribute("aria-describedby");
  const next = el.nextElementSibling;
  if (next?.classList.contains("field-error")) next.remove();
}

function clearFieldErrors(root) {
  root?.querySelectorAll(".field-invalid").forEach(clearFieldError);
}

// If the server's error is about a form field, show it on that field. `fields` maps a
// field ("name", "filename") to its input, or to a function finding the input for a value.
function showApiErrorOnField(e, fields) {
  if (!(e instanceof ApiError) || !e.field || !fields[e.field]) return false;
  const target = typeof fields[e.field] === "function" ? fields[e.field](e.value) : fields[e.field];
  return showFieldError(target, e.message);
}

// ═══════════════════════════════════════════════════════════════════════════════
// Toast
// ═══════════════════════════════════════════════════════════════════════════════
// Short confirmations fade on their own; a warning stays a little longer; an error stays
// until it is closed, so there is time to read it. `msg` is plain text, never HTML.
function toast(msg, type = "ok", title = "") {
  const icons = { ok: "✓", warn: "⚠", error: "✕" };
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.setAttribute("role", type === "error" ? "alert" : "status");
  el.innerHTML = `<span class="toast-icon">${icons[type] ?? ""}</span>
    <div class="toast-body">${title ? `<strong>${esc(title)}</strong>` : ""}<span>${esc(msg)}</span></div>
    ${type === "error" ? `<button type="button" class="toast-close" aria-label="Dismiss">×</button>` : ""}`;
  el.querySelector(".toast-close")?.addEventListener("click", () => el.remove());
  document.getElementById("toast-container").appendChild(el);
  if (type !== "error") setTimeout(() => el.remove(), type === "warn" ? 7000 : 3500);
  return el;
}

// An error with a short title ("Couldn't save mesh.inp") and a plain explanation.
function toastError(title, e) {
  if (!(e instanceof ApiError)) console.error(e);   // a bug in the page: keep it visible to developers
  return toast(plainError(e), "error", title);
}

// ═══════════════════════════════════════════════════════════════════════════════
// Theme toggle
// ═══════════════════════════════════════════════════════════════════════════════
// Inside the desktop app (it opens "/?desktop=1"): hide web-only things such as the
// "Download desktop app" button, and describe where files live accordingly.
if (new URLSearchParams(location.search).get("desktop") === "1") {
  document.documentElement.dataset.desktop = "1";
}

// The choice is remembered, and shared with the landing page (same origin, same key).
const THEME_KEY = "filefold.theme";
(function applyStoredTheme() {
  try {
    const t = localStorage.getItem(THEME_KEY);
    if (t === "light" || t === "dark") document.documentElement.dataset.theme = t;
  } catch { /* storage blocked: follow the system setting */ }
})();

function toggleTheme() {
  const root = document.documentElement;
  const cur = root.dataset.theme;
  if (!cur) {
    const sys = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    root.dataset.theme = sys === "dark" ? "light" : "dark";
  } else {
    root.dataset.theme = cur === "dark" ? "light" : "dark";
  }
  try { localStorage.setItem(THEME_KEY, root.dataset.theme); } catch { /* fine */ }
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

// Ticked parents ("Elements") left with no blocks because their ticked refinements
// ("Element type: X") took them all. Such a parent makes no file, which is fine.
// Mirrors filefold.core.subsplits.covered_parents.
function coveredSubParents(claims, ticked, options) {
  const live = liveSubKeys(claims, ticked);
  const parents = new Set(options.filter(o => o.parent && ticked.has(o.sub_category)).map(o => o.parent));
  return new Set([...ticked].filter(k => !live.has(k) && parents.has(k)));
}

// Decide which sub-split options can be ticked. A choice is never silently unticked:
// the first choice stays, and an option is disabled when ticking it would give it no
// blocks or would leave an already-ticked option with none (e.g. "Part: X" and "Nodes"
// are alternative depths for the same blocks). A refinement and its parent ("Element
// type: X" under "Elements") never conflict: the parent takes whatever is left.
// Mirrors filefold.core.subsplits.can_tick. `ids.box` maps an option key to its checkbox
// id; `ids.hint`, if given, to an element that explains a parent with nothing left.
function refreshSubAvailability(claims, options, ids) {
  if (!claims || !claims.length) return;
  const known = new Set(claims.flat());
  // Options the claims know nothing about (an already-extracted split) are left alone.
  const rows = options.filter(opt => known.has(opt.sub_category)).map(opt => ({
    key: opt.sub_category,
    parent: opt.parent && known.has(opt.parent) ? opt.parent : null,
    box: document.getElementById(ids.box(opt.sub_category)),
  })).filter(r => r.box);

  const ticked = new Set(rows.filter(r => r.box.checked).map(r => r.key));
  for (const r of rows) {
    if (r.box.checked) { r.box.disabled = false; r.box.title = ""; continue; }
    const after = new Set([...ticked, r.key]);
    if (r.parent) after.add(r.parent);              // ticking a refinement ticks its parent
    const live = liveSubKeys(claims, after);
    const covered = coveredSubParents(claims, after, options);
    const ok = [...after].every(k => live.has(k) || covered.has(k));
    r.box.disabled = !ok;
    r.box.title = ok ? "" : "Not available with your current choices: the blocks it would split are already taken by another ticked option.";
  }
  if (!ids.hint) return;
  const covered = coveredSubParents(claims, ticked, options);
  for (const r of rows) {
    const hint = document.getElementById(ids.hint(r.key));
    if (hint) hint.textContent = covered.has(r.key) ? "all split by type below, so no file of its own" : "";
    const name = ids.name && document.getElementById(ids.name(r.key));
    if (name && r.box.checked && !name.disabled) name.style.opacity = covered.has(r.key) ? ".4" : "1";
  }
}

// Keep refinements and their parent consistent after `key` was toggled: ticking a
// refinement ticks its parent; unticking a parent unticks its refinements. Returns the
// keys whose box changed, so the caller can update their filename inputs.
function followSubTree(options, key, boxOf) {
  const box = boxOf(key);
  if (!box) return [];
  const changed = [];
  const opt = options.find(o => o.sub_category === key);
  if (box.checked && opt?.parent) {
    const parent = boxOf(opt.parent);
    if (parent && !parent.checked) { parent.checked = true; changed.push(opt.parent); }
  }
  if (!box.checked) {
    for (const child of options.filter(o => o.parent === key)) {
      const cb = boxOf(child.sub_category);
      if (cb && cb.checked) { cb.checked = false; changed.push(child.sub_category); }
    }
  }
  return changed;
}

// The sub-split keys that will actually make a file: ticked, minus a parent its
// refinements emptied (sending it would only record a file that is never written).
function effectiveSubKeys(claims, options, ticked) {
  if (!claims || !claims.length) return new Set(ticked);
  const covered = coveredSubParents(claims, ticked, options);
  return new Set([...ticked].filter(k => !covered.has(k)));
}

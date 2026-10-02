// ═══════════════════════════════════════════════════════════════════════════════
// File editor (embedded view)
// ═══════════════════════════════════════════════════════════════════════════════
let _modalFile = null;
let _modalOrig = null;
let _findQuery  = "";
let _findMatches = [];
let _findIdx    = 0;

function _editorTa()     { return document.getElementById("editor-ta"); }
function _editorHL()     { return document.getElementById("editor-highlight"); }
function _editorGutter() { return document.getElementById("editor-gutter-inner"); }
function _editorArea()   { return document.getElementById("editor-code-area"); }

async function viewFile(filename) {
  _modalFile = filename;
  _modalOrig = null;
  _findQuery = ""; _findMatches = []; _findIdx = 0;

  const findInput = document.getElementById("find-input");
  if (findInput) findInput.value = "";
  const findCount = document.getElementById("find-count");
  if (findCount) findCount.textContent = "";

  document.getElementById("editor-filename").textContent = filename;
  const url = `/api/workspaces/${encodeURIComponent(state.activeWs)}/files/${encodeURIComponent(filename)}`;
  const dlBtn   = document.getElementById("editor-download");
  const saveBtn = document.getElementById("editor-save-btn");
  const discBtn = document.getElementById("editor-discard-btn");
  const dot     = document.getElementById("unsaved-dot");

  dlBtn.href = url;
  dlBtn.download = filename;
  saveBtn.style.display = "none";
  discBtn.style.display = "none";
  dot.classList.remove("visible");
  resetChunkBar();  // line numbers are per-file; a range from the last file means nothing here

  const loading = document.getElementById("editor-loading");
  const body    = document.getElementById("editor-body");
  loading.innerHTML = `<span class="spinner"></span> Loading…`;
  loading.style.cssText = "";
  loading.style.display = "";
  body.style.display    = "none";

  showView("editor");

  try {
    // Stream the response so the spinner shows while downloading large files
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const text = await res.text();
    _modalOrig = text;

    const lineCount = (text.match(/\n/g) || []).length + 1;
    if (lineCount > _LARGE_FILE_LINES) {
      loading.innerHTML = `<span class="spinner"></span> Rendering ${lineCount.toLocaleString()} lines…`;
    }

    _editorTa().value = text;
    loading.style.display = "none";
    body.style.display = "";

    // Gutter first (synchronous, establishes height), highlight deferred
    _syncGutter(text);
    requestAnimationFrame(() => syncHighlight());

    saveBtn.style.display = "";
    discBtn.style.display = "";
  } catch (e) {
    loading.innerHTML = `Failed to load: ${esc(e.message)}`;
    loading.style.color = "var(--danger)";
  }
}

// ── Highlight + gutter sync ───────────────────────────────────────────────────
const _LARGE_FILE_LINES = 5000;

function _syncGutter(text) {
  const gt = _editorGutter();
  if (!gt) return;
  // Count lines without splitting the full string (avoids allocating N substrings)
  const lineCount = (text.match(/\n/g) || []).length + 1;
  gt.textContent = Array.from({length: lineCount}, (_, i) => i + 1).join("\n");
}

function syncHighlight() {
  const ta = _editorTa();
  const hl = _editorHL();
  if (!ta || !hl) return;
  const text = ta.value;
  const lineCount = (text.match(/\n/g) || []).length + 1;
  const isLarge = lineCount > _LARGE_FILE_LINES;

  if (isLarge) {
    // Textarea shows its own text; pre is used only for scroll height + match backgrounds
    ta.style.color = "var(--text)";
    if (_findMatches.length) {
      // Match span backgrounds show through the transparent-text textarea overlay
      hl.innerHTML = _buildMatchOnlyHTML(text, _findMatches, _findIdx);
    } else {
      // Blank newlines establish correct scroll height without any visible content in pre
      hl.textContent = "\n".repeat(lineCount - 1);
    }
  } else {
    ta.style.color = "";  // CSS rule keeps it transparent; pre provides visible text
    hl.innerHTML = buildHighlightHTML(text, _findQuery, _findMatches, _findIdx);
  }
}

function _escHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function _buildMatchOnlyHTML(text, matches, curIdx) {
  // For large files: position spans using newlines for vertical placement and
  // the line-prefix text (chars from line start to match) for horizontal placement.
  // Without the prefix, every span lands at column 0 of the correct line.
  const totalNl = (text.match(/\n/g) || []).length;
  if (!matches.length) {
    return totalNl > 0 ? "\n".repeat(totalNl) : " ";
  }
  const parts = [];
  let pos = 0;
  matches.forEach((m, i) => {
    const gap = text.slice(pos, m.start);
    const lastNl = gap.lastIndexOf("\n");
    if (lastNl >= 0) {
      // Vertical: newlines to reach the right line
      parts.push("\n".repeat((gap.match(/\n/g) || []).length));
      // Horizontal: characters on this line before the match
      const linePrefix = gap.slice(lastNl + 1);
      if (linePrefix) parts.push(_escHtml(linePrefix));
    } else {
      // Same line as previous match — include all gap characters
      if (gap) parts.push(_escHtml(gap));
    }
    parts.push(`<span class="${i === curIdx ? "hl-match-cur" : "hl-match"}">${_escHtml(text.slice(m.start, m.end))}</span>`);
    pos = m.end;
  });
  const trailingNl = (text.slice(pos).match(/\n/g) || []).length;
  if (trailingNl > 0) parts.push("\n".repeat(trailingNl));
  return parts.join("");
}

function buildHighlightHTML(text, query, matches, curIdx) {
  const n = text.length;
  // Per-character syntax class: 0=data 1=comment 2=keyword 3=param
  const syn = new Uint8Array(n);
  let pos = 0;
  for (const line of text.split("\n")) {
    const len = line.length;
    if (line.startsWith("**")) {
      syn.fill(1, pos, pos + len);
    } else if (/^\s*\*[^*]/.test(line)) {
      const ci = line.indexOf(",");
      const kEnd = ci === -1 ? len : ci;
      syn.fill(2, pos, pos + kEnd);
      if (ci !== -1) syn.fill(3, pos + ci, pos + len);
    }
    pos += len + 1;
  }
  // Per-character find class: 0=none 1=match 2=current
  const find = new Uint8Array(n);
  matches.forEach((m, i) => find.fill(i === curIdx ? 2 : 1, m.start, m.end));

  const SYN  = ["", "hl-comment", "hl-keyword", "hl-param"];
  const FIND = ["", "hl-match",   "hl-match-cur"];
  let html = "", i = 0;
  while (i < n) {
    const sc = syn[i], fc = find[i];
    let j = i + 1;
    while (j < n && syn[j] === sc && find[j] === fc) j++;
    const seg = text.slice(i, j)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    const cls = [SYN[sc], FIND[fc]].filter(Boolean).join(" ");
    html += cls ? `<span class="${cls}">${seg}</span>` : seg;
    i = j;
  }
  return html;
}

// ── Find bar ──────────────────────────────────────────────────────────────────
function openFindBar() {
  const inp = document.getElementById("find-input");
  if (!inp) return;
  // Pre-fill with any active selection in the editor
  const ta = _editorTa();
  if (ta && ta.selectionStart !== ta.selectionEnd) {
    inp.value = ta.value.slice(ta.selectionStart, ta.selectionEnd);
    runFind();
  }
  inp.focus();
  inp.select();
}

function closeFindBar() {
  const inp = document.getElementById("find-input");
  if (inp) inp.value = "";
  _findQuery = ""; _findMatches = []; _findIdx = 0;
  const fc = document.getElementById("find-count");
  if (fc) fc.textContent = "";
  syncHighlight();
  _editorTa()?.focus();
}

let _findTimer = null;
function _runFindDebounced() {
  clearTimeout(_findTimer);
  _findTimer = setTimeout(runFind, 200);
}

function runFind() {
  const inp = document.getElementById("find-input");
  _findQuery = inp?.value ?? "";
  _recomputeMatches();
  _findIdx = 0;
  _updateFindCount();
  syncHighlight();
  _scrollToMatch();
}

// Matches are character offsets into the text. Any edit shifts every offset after
// the caret, so re-rendering the highlight layer without recomputing them paints
// the spans at stale positions — the highlights visibly slide away from the words
// they belong to as you type. Recompute against the current text instead.
function _recomputeMatches() {
  _findMatches = [];
  const ta = _editorTa();
  if (!ta || !_findQuery) return;
  const re = new RegExp(_escRe(_findQuery), "gi");
  let m;
  while ((m = re.exec(ta.value)) !== null) {
    _findMatches.push({ start: m.index, end: m.index + m[0].length });
    if (m.index === re.lastIndex) re.lastIndex++;  // guard against empty match
  }
}

// ── Chunk selection (Notepad++ style line-range selection) ───────────────────
// Notepad++ lets you click a line number in the margin to select that line and
// shift-click another to select the range between them. The gutter here is one
// text node with pointer-events:none, so the line is derived from the click's Y
// position against the measured line height instead of per-line elements.
let _chunkAnchor = null;   // first line of an in-progress gutter selection

function _editorLineCount() {
  const ta = _editorTa();
  return ta ? (ta.value.match(/\n/g) || []).length + 1 : 0;
}

function _lineToOffsets(line) {
  // 1-based line -> [startOffset, endOffsetIncludingNewline]
  const text = _editorTa().value;
  let start = 0;
  for (let i = 1; i < line; i++) {
    const nl = text.indexOf("\n", start);
    if (nl === -1) { start = text.length; break; }
    start = nl + 1;
  }
  const nl = text.indexOf("\n", start);
  return [start, nl === -1 ? text.length : nl + 1];
}

function selectLineRange(from, to, {scroll = true} = {}) {
  const ta = _editorTa();
  if (!ta) return;
  const total = _editorLineCount();
  let a = Math.max(1, Math.min(total, from));
  let b = Math.max(1, Math.min(total, to));
  if (a > b) [a, b] = [b, a];

  const [start] = _lineToOffsets(a);
  const [, end] = _lineToOffsets(b);
  ta.focus();
  ta.setSelectionRange(start, end);

  if (scroll) {
    const cs = getComputedStyle(_editorHL());
    const lh = parseFloat(cs.lineHeight) || 19;
    const pad = parseFloat(cs.paddingTop) || 16;
    const area = _editorArea();
    const target = pad + (a - 1) * lh;
    // Only scroll when the start line is outside the viewport
    if (target < area.scrollTop || target > area.scrollTop + area.clientHeight - lh)
      area.scrollTop = Math.max(0, target - area.clientHeight / 3);
  }
  _setChunkHint(a === b ? `L${a}` : `${a}–${b} · ${b - a + 1} lines`);
}

function _gutterLineFromEvent(e) {
  const inner = _editorGutter();
  const area  = _editorArea();
  if (!inner || !area) return 1;
  const cs = getComputedStyle(inner);
  const lh = parseFloat(cs.lineHeight) || 19;
  const padTop = parseFloat(cs.paddingTop) || 16;
  // The gutter is translated to follow the scroll container, so add scrollTop back.
  const rect = document.getElementById("editor-gutter").getBoundingClientRect();
  const y = (e.clientY - rect.top) + area.scrollTop - padTop;
  return Math.max(1, Math.min(_editorLineCount(), Math.floor(y / lh) + 1));
}

// Clear the chunk bar between files. Line numbers only mean something relative to
// the file that is open, so carrying "46-392" into the next file is meaningless
// and, worse, looks like a live selection that isn't there.
function resetChunkBar() {
  _chunkAnchor = null;
  const wrap = document.getElementById("chunk-wrap");
  const inp  = document.getElementById("chunk-input");
  if (inp) inp.value = "";
  if (wrap) wrap.style.display = "none";
  _setChunkHint("");
}

function toggleChunkBar() {
  const wrap = document.getElementById("chunk-wrap");
  if (!wrap) return;
  const showing = wrap.style.display !== "none";
  wrap.style.display = showing ? "none" : "";
  if (!showing) {
    const inp = document.getElementById("chunk-input");
    inp.value = "";
    _setChunkHint("click gutter, shift-click to extend");
    inp.focus();
  }
}

function _setChunkHint(msg) {
  const el = document.getElementById("chunk-hint");
  if (el) el.textContent = msg;
}

function _chunkKey(e) {
  if (e.key === "Escape") { toggleChunkBar(); _editorTa()?.focus(); return; }
  if (e.key !== "Enter") return;
  e.preventDefault();
  applyChunkRange();
}

function applyChunkRange() {
  const raw = (document.getElementById("chunk-input")?.value ?? "").trim();
  if (!raw) return;
  // Accept "46-892", "46:892", "46 892", or a single "46"
  const parts = raw.split(/[-:,\s]+/).filter(Boolean).map(Number);
  if (!parts.length || parts.some(n => !Number.isFinite(n) || n < 1)) {
    _setChunkHint("enter a line or range, e.g. 46-892");
    return;
  }
  selectLineRange(parts[0], parts.length > 1 ? parts[1] : parts[0]);
}

function _swapMatchCur(newIdx) {
  const hl = _editorHL();
  if (!hl) return;
  hl.querySelectorAll(".hl-match-cur").forEach(el => {
    el.classList.remove("hl-match-cur");
    el.classList.add("hl-match");
  });
  const all = hl.querySelectorAll(".hl-match");
  if (all[newIdx]) {
    all[newIdx].classList.remove("hl-match");
    all[newIdx].classList.add("hl-match-cur");
  }
}

function findNext() {
  if (!_findMatches.length) return;
  _findIdx = (_findIdx + 1) % _findMatches.length;
  _updateFindCount();
  _swapMatchCur(_findIdx);
  _scrollToMatch();
}

function findPrev() {
  if (!_findMatches.length) return;
  _findIdx = (_findIdx - 1 + _findMatches.length) % _findMatches.length;
  _updateFindCount();
  _swapMatchCur(_findIdx);
  _scrollToMatch();
}

function _findKey(e) {
  if (e.key === "Enter") { e.preventDefault(); e.shiftKey ? findPrev() : findNext(); }
  if (e.key === "Escape") closeFindBar();
}

function _updateFindCount() {
  const el = document.getElementById("find-count");
  if (!el) return;
  el.textContent = _findMatches.length
    ? `${_findIdx + 1} / ${_findMatches.length}`
    : (_findQuery ? "No matches" : "");
}

function _scrollToMatch() {
  if (!_findMatches.length) return;
  const ta = _editorTa();
  if (!ta) return;
  const m = _findMatches[_findIdx];
  ta.setSelectionRange(m.start, m.end);
  requestAnimationFrame(() => {
    const area = _editorArea();
    if (!area) return;
    const cur = _editorHL()?.querySelector(".hl-match-cur");
    if (cur) {
      // Use the actual rendered position of the highlighted span
      const areaRect = area.getBoundingClientRect();
      const curRect  = cur.getBoundingClientRect();
      area.scrollTop += (curRect.top - areaRect.top) - area.clientHeight / 2;
    } else {
      // Fallback: line-count calculation
      const linesBefore = ta.value.slice(0, m.start).split("\n").length - 1;
      area.scrollTop = Math.max(0, 16 + linesBefore * 19.2 - area.clientHeight / 2);
    }
  });
}

function _escRe(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); }

// ── Comment toggle (Ctrl+/) ───────────────────────────────────────────────────
function toggleComment() {
  const ta = _editorTa();
  if (!ta) return;
  const val  = ta.value;
  const sS   = ta.selectionStart;
  const sE   = ta.selectionEnd;
  const lineStart = val.lastIndexOf("\n", sS - 1) + 1;
  const lineEnd   = val.indexOf("\n", sE);
  const blockEnd  = lineEnd === -1 ? val.length : lineEnd;
  const block     = val.slice(lineStart, blockEnd);
  const lines     = block.split("\n");
  const allCommented = lines.every(l => l.startsWith("**"));
  const newLines  = lines.map(l => allCommented ? l.slice(2) : "**" + l);
  const newBlock  = newLines.join("\n");
  const delta     = newBlock.length - block.length;
  // Use execCommand so Cmd+Z undoes this
  ta.setSelectionRange(lineStart, blockEnd);
  document.execCommand("insertText", false, newBlock);
  ta.selectionStart = sS + (allCommented ? -2 : 2);
  ta.selectionEnd   = sE + delta;
  syncHighlight();
  document.getElementById("unsaved-dot")?.classList.toggle("visible", ta.value !== _modalOrig);
}

// ── Save / discard / close ────────────────────────────────────────────────────
async function saveFile() {
  const ta  = _editorTa();
  const btn = document.getElementById("editor-save-btn");
  if (!ta || !_modalFile) return;
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner"></span>`;
  try {
    const res = await fetch(
      `/api/workspaces/${encodeURIComponent(state.activeWs)}/files/${encodeURIComponent(_modalFile)}`,
      { method: "PUT", body: ta.value, headers: { "Content-Type": "text/plain" } }
    );
    // fetch only rejects on network failure; a 4xx/5xx must not be reported as saved.
    if (!res.ok) throw new Error(`${res.status} ${(await res.text()).slice(0, 120)}`);
    _modalOrig = ta.value;
    document.getElementById("unsaved-dot").classList.remove("visible");
    toast(`Saved ${_modalFile}`, "ok");
    if (state.wsData) {
      const data = await api("GET", `/api/workspaces/${encodeURIComponent(state.activeWs)}`);
      state.wsData = data;
      renderDetail(data);
    }
  } catch (e) {
    toast("Save failed: " + e.message, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "Save";
  }
}

function discardEdits() {
  const ta = _editorTa();
  if (!ta || _modalOrig === null) return;
  if (ta.value !== _modalOrig && !confirm("Discard unsaved changes?")) return;
  ta.value = _modalOrig;
  syncHighlight();
  document.getElementById("unsaved-dot").classList.remove("visible");
}

function closeEditor() {
  const ta = _editorTa();
  if (ta && ta.value !== _modalOrig) {
    if (!confirm("Close without saving?")) return;
  }
  if (ta) ta.style.color = "";  // Reset large-file color override
  _modalFile = null; _modalOrig = null;
  _findQuery = ""; _findMatches = []; _findIdx = 0;
  const fi = document.getElementById("find-input");
  if (fi) fi.value = "";
  const fc = document.getElementById("find-count");
  if (fc) fc.textContent = "";
  showView("detail");
}

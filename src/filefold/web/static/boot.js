// ═══════════════════════════════════════════════════════════════════════════════
// Boot
// ═══════════════════════════════════════════════════════════════════════════════
setupDropZone("upload-zone",   f => handleUpload(f));
setupDropZone("reimp-drop",    f => handleReimpUpload(f));
loadWorkspaces();
applyNotesMode();
initSamples();

// ── Editor: one-time event setup (elements are static HTML now) ───────────────
(function _initEditor() {
  const ta   = _editorTa();
  const area = _editorArea();
  if (!ta || !area) return;

  let _hlTimer = null;
  let _lastLineCount = 0;
  ta.addEventListener("input", () => {
    document.getElementById("unsaved-dot")?.classList.toggle("visible", ta.value !== _modalOrig);
    clearTimeout(_hlTimer);
    _hlTimer = setTimeout(() => {
      const lc = ta.value.split("\n").length;
      if (lc !== _lastLineCount) { _syncGutter(ta.value); _lastLineCount = lc; }
      if (_findQuery) {
        // Keep the caret's match selected across the edit rather than snapping
        // back to match 1, which would yank the viewport to the top of the file.
        const caret = ta.selectionStart;
        _recomputeMatches();
        const at = _findMatches.findIndex(m => m.end >= caret);
        _findIdx = at === -1 ? Math.max(0, _findMatches.length - 1) : at;
        _updateFindCount();
      }
      syncHighlight();
    }, 150);
  });

  ta.addEventListener("keydown", e => {
    if (e.key === "Tab") {
      e.preventDefault();
      const s = ta.selectionStart, en = ta.selectionEnd;
      ta.value = ta.value.slice(0, s) + "  " + ta.value.slice(en);
      ta.selectionStart = ta.selectionEnd = s + 2;
      syncHighlight();
    }
    if ((e.key === "*" || e.key === "Backspace") && ta.selectionStart !== ta.selectionEnd) {
      const val = ta.value;
      const s = ta.selectionStart, en = ta.selectionEnd;
      const blockStart = val.lastIndexOf("\n", s - 1) + 1;
      const nlAfter    = val.indexOf("\n", en - 1);
      const blockEnd   = nlAfter === -1 ? val.length : nlAfter;
      const lines      = val.slice(blockStart, blockEnd).split("\n");
      if (e.key === "Backspace" && !lines.every(l => l.startsWith("*"))) {
        // not all starred — let default run
      } else {
        e.preventDefault();
        const removing = e.key === "Backspace";
        const newLines = removing ? lines.map(l => l.slice(1)) : lines.map(l => "*" + l);
        const newBlock = newLines.join("\n");
        const delta    = removing ? -lines.length : lines.length;
        ta.setSelectionRange(blockStart, blockEnd);
        document.execCommand("insertText", false, newBlock);
        ta.selectionStart = s + (removing ? -1 : 1);
        ta.selectionEnd   = en + delta;
        syncHighlight();
        document.getElementById("unsaved-dot")?.classList.toggle("visible", ta.value !== _modalOrig);
      }
    }
  });

  area.addEventListener("scroll", () => {
    const g = _editorGutter();
    if (g) g.style.transform = `translateY(-${area.scrollTop}px)`;
  });

  // Gutter click selects a line; shift-click extends from the last anchor, so a
  // range of any size is two clicks with nothing held down in between.
  const gutter = document.getElementById("editor-gutter");
  if (gutter) {
    gutter.style.cursor = "pointer";
    gutter.addEventListener("mousedown", e => {
      e.preventDefault();  // don't steal focus mid-selection
      const line = _gutterLineFromEvent(e);
      if (e.shiftKey && _chunkAnchor !== null) {
        selectLineRange(_chunkAnchor, line, {scroll: false});
      } else {
        _chunkAnchor = line;
        selectLineRange(line, line, {scroll: false});
      }
    });
  }
})();

// Persistent keyboard handler for the editor view
document.addEventListener("keydown", e => {
  if (state.view !== "editor") return;
  if (e.key === "Escape") {
    const fi = document.getElementById("find-input");
    if (fi && document.activeElement === fi) { fi.blur(); closeFindBar(); }
    else closeEditor();
  }
  if ((e.ctrlKey || e.metaKey) && e.key === "s") { e.preventDefault(); saveFile(); }
  if ((e.ctrlKey || e.metaKey) && e.key === "f") { e.preventDefault(); openFindBar(); }
  // Ctrl/Cmd+G — Notepad++'s go-to-line, reused here to open the chunk range box
  if ((e.ctrlKey || e.metaKey) && e.key === "g") {
    e.preventDefault();
    const wrap = document.getElementById("chunk-wrap");
    if (wrap && wrap.style.display === "none") toggleChunkBar();
    else document.getElementById("chunk-input")?.focus();
  }
  if ((e.ctrlKey || e.metaKey) && e.key === "/") { e.preventDefault(); toggleComment(); }
});

// ═══════════════════════════════════════════════════════════════════════════════
// (i) reminders and the Info page
// ═══════════════════════════════════════════════════════════════════════════════
// Small floating reminders next to titles that are not self-explanatory. They are
// deliberately short: the app is meant to be intuitive, the reminder only jogs memory.
// The full description of every function is on the Info page.

const INFO = {
  upload: "Drop a .inp file, click to browse, or use Sample data. Nothing is created until you press Create workspace.",
  inspector: "Every keyword block in the file, coloured by category. Click a block with ▸ to see what is nested inside it.",
  extract: "Each ticked category becomes its own file. Model set-up (*HEADING, *ASSEMBLY ...) always stays in the mother file.",
  subsplit: "Split this category further. Only options that would make a file are shown; ones that overlap grey out once you pick one.",
  status: "clean: exactly as FileFold wrote it. edited: changed since. missing: the file is gone.",
  splits: "Change how this workspace is split. Unticking a category or sub-file folds it back into its parent.",
  reimport: "Upload a newer version of the original file. Existing children are compared against it before anything changes.",
  "reimport-status": "Safe: changed upstream only. Unchanged: same in both. Conflict: changed upstream and edited here, you decide.",
  editor: "Ctrl/Cmd+S save, +F find, +G select a line range, +/ comment. Leaving with unsaved edits asks first.",
};

// Markup for an (i) button, for templates that build HTML in JS.
function infoBtn(key, label) {
  return `<button type="button" class="info-btn" data-info="${key}" aria-label="About ${label}" aria-expanded="false">i</button>`;
}

let _closeInfoPopover = () => {};
function closeInfoPopover() { _closeInfoPopover(); }

(function initInfoPopover() {
  let openBtn = null;
  let pop = null;

  function ensurePop() {
    if (pop) return pop;
    pop = document.createElement("div");
    pop.id = "info-pop";
    pop.setAttribute("role", "note");
    pop.hidden = true;
    document.body.appendChild(pop);
    return pop;
  }

  function place(btn) {
    const margin = 8;
    const r = btn.getBoundingClientRect();
    const w = Math.min(280, window.innerWidth - 2 * margin);
    pop.style.width = `${w}px`;
    const h = pop.offsetHeight;
    const left = Math.min(Math.max(r.left + r.width / 2 - w / 2, margin), window.innerWidth - w - margin);
    const below = r.bottom + 8 + h <= window.innerHeight - margin;
    pop.style.left = `${left}px`;
    pop.style.top = `${below ? r.bottom + 8 : Math.max(margin, r.top - 8 - h)}px`;
    pop.dataset.side = below ? "below" : "above";
    pop.style.setProperty("--arrow-x", `${Math.min(Math.max(r.left + r.width / 2 - left, 14), w - 14)}px`);
  }

  function close(refocus) {
    if (!openBtn) return;
    const btn = openBtn;
    openBtn = null;
    pop.hidden = true;
    btn.setAttribute("aria-expanded", "false");
    btn.removeAttribute("aria-describedby");
    if (refocus) btn.focus();
  }

  function open(btn) {
    close(false);
    ensurePop();
    pop.textContent = INFO[btn.dataset.info] || "";
    pop.hidden = false;
    openBtn = btn;
    btn.setAttribute("aria-expanded", "true");
    btn.setAttribute("aria-describedby", "info-pop");
    place(btn);
  }

  document.addEventListener("click", e => {
    const btn = e.target.closest(".info-btn");
    if (btn) {
      e.preventDefault();
      e.stopPropagation();
      openBtn === btn ? close(false) : open(btn);
      return;
    }
    if (openBtn && !e.target.closest("#info-pop")) close(false);
  });
  document.addEventListener("keydown", e => { if (e.key === "Escape" && openBtn) { e.stopPropagation(); close(true); } }, true);
  window.addEventListener("resize", () => close(false));
  document.addEventListener("scroll", () => close(false), true);
  _closeInfoPopover = () => close(false);
})();

// ── Info page ────────────────────────────────────────────────────────────────────
function helpJump(event, id) {
  event.preventDefault();
  document.getElementById(id)?.scrollIntoView({ block: "start" });
}

(function initHelpPage() {
  // category chips are drawn with the same function the rest of the app uses
  document.querySelectorAll("#view-help [data-cat]").forEach(el => { el.innerHTML = catChip(el.dataset.cat); });
  // where files live depends on the build: keep only the sentence that is true here
  const keep = window.FILEFOLD_STATIC ? "static" : "server";
  document.querySelectorAll("#view-help [data-mode]").forEach(el => { if (el.dataset.mode !== keep) el.remove(); });
})();

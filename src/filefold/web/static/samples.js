// ═══════════════════════════════════════════════════════════════════════════════
// Sample data: three real decks, offered on the New Workspace screen
// ═══════════════════════════════════════════════════════════════════════════════
// Nothing is loaded until the person chooses one. Choosing hands the deck to the normal
// upload flow exactly as if they had dropped the file in.

const SAMPLE_BASE = "static/samples/";   // relative, so it works under a sub-path (GitHub Pages)

function _sampleSummary(f) {
  const plural = (n, word) => `${n.toLocaleString()} ${word}${n === 1 ? "" : "s"}`;
  const bits = [fmtBytes(f.bytes)];
  if (f.parts.length) bits.push(plural(f.parts.length, "part"));
  if (f.steps.length) bits.push(plural(f.steps.length, "step"));
  if (f.materials) bits.push(plural(f.materials, "material"));
  if (f.contact_pairs) bits.push(plural(f.contact_pairs, "contact pair"));
  return bits.join(" · ");
}

let _sampleManifest = null;

async function _loadSampleManifest() {
  if (_sampleManifest) return _sampleManifest;
  const res = await fetch(`${SAMPLE_BASE}manifest.json`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  _sampleManifest = (await res.json()).samples;
  return _sampleManifest;
}

function _renderSampleMenu(samples) {
  document.getElementById("sample-menu").innerHTML = samples.map(s => `
    <button type="button" role="menuitem" class="sample-item" data-sample="${esc(s.id)}" tabindex="-1">
      <span class="sample-item-title">${esc(s.title)}</span>
      <span class="sample-item-facts">${esc(_sampleSummary(s.facts))}</span>
      <span class="sample-item-blurb">${esc(s.blurb.split(". ")[0].replace(/\.$/, ""))}.</span>
    </button>`).join("");
}

function closeSampleMenu(refocus = false) {
  const menu = document.getElementById("sample-menu");
  const btn = document.getElementById("sample-btn");
  if (!menu || menu.hidden) return;
  menu.hidden = true;
  btn.setAttribute("aria-expanded", "false");
  if (refocus) btn.focus();
}

// Opens at once (so Escape and outside clicks behave immediately) and fills in the list as
// soon as it is available.
async function openSampleMenu() {
  const menu = document.getElementById("sample-menu");
  const btn = document.getElementById("sample-btn");
  menu.hidden = false;
  btn.setAttribute("aria-expanded", "true");
  if (!_sampleManifest) menu.innerHTML = `<p class="sample-error" role="status">Loading samples…</p>`;
  try {
    const samples = await _loadSampleManifest();
    if (!menu.hidden) _renderSampleMenu(samples);          // still open: show them
  } catch (e) {
    if (!menu.hidden) menu.innerHTML = `<p class="sample-error">Sample decks could not be loaded (${esc(e.message)}).</p>`;
  }
}

// Fetch a sample and feed it to the upload flow. Used by the menu and by the tour.
async function loadSample(id) {
  try {
    const res = await fetch(`${SAMPLE_BASE}${encodeURIComponent(id)}.inp`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const file = new File([await res.blob()], `${id}.inp`, { type: "text/plain" });
    if (state.view !== "new-workspace") showView("new-workspace");
    await handleUpload(file);
  } catch (e) {
    toast("Could not load the sample: " + e.message, "error");
  }
}

(function initSampleMenu() {
  const btn = document.getElementById("sample-btn");
  const menu = document.getElementById("sample-menu");
  if (!btn || !menu) return;
  const items = () => [...menu.querySelectorAll("[role=menuitem]")];

  btn.addEventListener("click", async e => {
    e.stopPropagation();
    if (!menu.hidden) { closeSampleMenu(false); return; }
    await openSampleMenu();
    // keyboard users land on the first choice; mouse users are not disturbed
    if (e.detail === 0 && !menu.hidden) items()[0]?.focus();
  });
  btn.addEventListener("keydown", e => {
    if (e.key === "Escape" && !menu.hidden) { e.preventDefault(); e.stopPropagation(); closeSampleMenu(true); }
  });
  menu.addEventListener("click", e => {
    const item = e.target.closest("[data-sample]");
    if (!item) return;
    closeSampleMenu(false);
    loadSample(item.dataset.sample);
  });
  menu.addEventListener("keydown", e => {
    const list = items();
    const i = list.indexOf(document.activeElement);
    if (e.key === "ArrowDown") { e.preventDefault(); list[(i + 1) % list.length]?.focus(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); list[(i - 1 + list.length) % list.length]?.focus(); }
    else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); closeSampleMenu(true); }
    else if (e.key === "Tab") closeSampleMenu(false);
  });
  document.addEventListener("click", e => {
    if (!menu.hidden && !e.target.closest(".sample-wrap")) closeSampleMenu(false);
  });
})();

// ═══════════════════════════════════════════════════════════════════════════════
// Sortable lists (file order in the Splits and Files tabs)
//
// An item is one or more elements that move together (a Files row and its sub-file rows).
// Its first element holds a grip (.grip) and, when it can move, ↑/↓ buttons. While an item
// is dragged the list rearranges live, and the item itself is drawn as a dashed slot, so
// where it will land is always visible. Releasing it anywhere keeps that place; Escape or
// dropping outside the list puts everything back. Items only move within their group (the
// step file splits a list into groups that never mix). Grabbing an item that cannot move
// says why instead of doing nothing.
//
//   makeSortable(container, {
//     items: () => [{ key, els, movable, reason, group }]   // in screen order
//     onMove: keys => ...     // the moved item's group, in its new order
//   })
// ═══════════════════════════════════════════════════════════════════════════════
function makeSortable(container, opts) {
  const itemFor = key => opts.items().find(it => it.key === key);
  const groupOf = item => opts.items().filter(it => it.group === item.group && it.movable);
  const keysOf = items => items.map(it => it.key);

  // Put the group's items into the places they occupy now, in the order of `keys`.
  function place(group, keys) {
    const byKey = Object.fromEntries(group.map(it => [it.key, it]));
    const marks = group.map(it => {
      const mark = document.createComment("slot");
      it.els[0].before(mark);
      it.els.forEach(el => el.remove());
      return mark;
    });
    marks.forEach((mark, i) => { mark.replaceWith(...byKey[keys[i]].els); });
  }

  function refuse(item) {
    toast(item.reason || "This file can't be moved.", "warn");
  }

  // ── Buttons ──────────────────────────────────────────────────────────────
  container.addEventListener("click", e => {
    const btn = e.target.closest?.("[data-move]");
    if (btn && container.contains(btn)) {
      const item = itemFor(btn.dataset.key);
      if (!item?.movable) return;
      const group = groupOf(item);
      const keys = keysOf(group), i = keys.indexOf(item.key), j = i + Number(btn.dataset.move);
      if (j < 0 || j >= keys.length) return;
      [keys[i], keys[j]] = [keys[j], keys[i]];
      place(group, keys);
      container.querySelector(`[data-move="${btn.dataset.move}"][data-key="${CSS.escape(item.key)}"]`)?.focus();
      opts.onMove(keys);
      return;
    }
    const grip = e.target.closest?.(".grip");
    if (grip && container.contains(grip)) {
      const item = itemFor(grip.dataset.key);
      if (item && !item.movable) refuse(item);       // a click on a fixed item explains it
    }
  });

  // ── Dragging ─────────────────────────────────────────────────────────────
  let drag = null;   // { item, group, before: keys, dropped }
  container.addEventListener("dragstart", e => {
    const grip = e.target.closest?.(".grip");
    const item = grip && itemFor(grip.dataset.key);
    if (!item) return;
    if (!item.movable) { e.preventDefault(); refuse(item); return; }
    const group = groupOf(item);
    drag = { item, group: group.map(it => it.key), before: keysOf(group), dropped: false };
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", item.key);
    e.dataTransfer.setDragImage(item.els[0], 24, 16);
    // After the browser took its picture of the item: then draw it as the landing slot.
    requestAnimationFrame(() => item.els.forEach(el => el.classList.add("sort-slot")));
    container.classList.add("sorting");
  });

  container.addEventListener("dragover", e => {
    if (!drag) return;
    e.preventDefault();                              // anywhere in the list keeps the live order
    e.dataTransfer.dropEffect = "move";
    const over = e.target.closest?.("[data-sort-key]");
    const target = over && itemFor(over.dataset.sortKey);
    if (!target || target.key === drag.item.key || !drag.group.includes(target.key)) return;
    const first = target.els[0].getBoundingClientRect(), last = target.els.at(-1).getBoundingClientRect();
    const after = e.clientY > (first.top + last.bottom) / 2;
    const group = groupOf(drag.item);
    const keys = keysOf(group).filter(k => k !== drag.item.key);
    keys.splice(keys.indexOf(target.key) + (after ? 1 : 0), 0, drag.item.key);
    if (keys.join("\n") !== keysOf(group).join("\n")) place(group, keys);
  });

  container.addEventListener("drop", e => {
    if (!drag) return;
    e.preventDefault();
    drag.dropped = true;
  });

  container.addEventListener("dragend", () => {
    if (!drag) return;
    const { item, before, dropped } = drag;
    drag = null;
    item.els.forEach(el => el.classList.remove("sort-slot"));
    container.classList.remove("sorting");
    const group = groupOf(item);
    if (!dropped) { place(group, before); return; }   // Escape, or let go outside the list
    const keys = keysOf(group);
    if (keys.join("\n") !== before.join("\n")) opts.onMove(keys);
  });
}

// The handle shown at the start of a sortable item: a grip, and ↑/↓ when it can move.
function sortHandle(key, label, movable, reason) {
  const k = esc(key);
  if (!movable) {
    return `<span class="sort-handle fixed">
      <span class="grip" draggable="true" data-key="${k}" role="button" tabindex="-1"
            title="${esc(reason)}" aria-label="${esc(reason)}">⠿</span><span class="sort-arrows"></span></span>`;
  }
  return `<span class="sort-handle">
    <span class="grip" draggable="true" data-key="${k}" title="Drag to change where ${esc(label)} comes in the deck" aria-hidden="true">⠿</span>
    <span class="sort-arrows">
      <button type="button" class="sort-btn" data-move="-1" data-key="${k}" aria-label="Move ${esc(label)} up" title="Move up">↑</button>
      <button type="button" class="sort-btn" data-move="1" data-key="${k}" aria-label="Move ${esc(label)} down" title="Move down">↓</button>
    </span></span>`;
}

// Disable ↑ on the first and ↓ on the last item of each group.
function syncSortButtons(container, items) {
  const groups = {};
  items.filter(it => it.movable).forEach(it => (groups[it.group] ??= []).push(it));
  for (const group of Object.values(groups)) {
    group.forEach((it, i) => {
      const up = container.querySelector(`[data-move="-1"][data-key="${CSS.escape(it.key)}"]`);
      const down = container.querySelector(`[data-move="1"][data-key="${CSS.escape(it.key)}"]`);
      if (up) up.disabled = i === 0;
      if (down) down.disabled = i === group.length - 1;
    });
  }
}

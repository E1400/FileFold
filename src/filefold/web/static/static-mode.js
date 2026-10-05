// Static (GitHub Pages) mode: serve /api/* from Python running in a Web Worker.
//
// Only the built site loads this file (scripts/build_pages.py injects it ahead of the
// other scripts); the server-backed app never does. It replaces window.fetch for URLs
// under /api/ and leaves every other request alone, so the rest of the UI is unchanged.
(() => {
  const worker = new Worker(new URL("pyodide-worker.js", document.currentScript.src), { type: "module" });
  window.FILEFOLD_STATIC = true;

  const banner = document.createElement("div");
  banner.id = "static-banner";
  banner.setAttribute("role", "status");
  banner.style.cssText = "position:fixed;inset:auto 16px 16px auto;z-index:9999;max-width:340px;padding:10px 14px;" +
    "background:var(--surface,#eee);color:var(--text,#222);border:1px solid var(--border,#999);" +
    "font:13px system-ui,sans-serif";
  banner.textContent = "Starting Python in your browser…";
  document.addEventListener("DOMContentLoaded", () => document.body.appendChild(banner));

  let nextId = 1;
  const pending = new Map();

  worker.onmessage = ev => {
    const m = ev.data;
    if (m.type === "progress") banner.textContent = m.text;
    else if (m.type === "ready") banner.remove();
    else if (m.type === "init-error") {
      banner.textContent = "Could not start the in-browser Python runtime: " + m.text;
      banner.style.borderColor = "var(--danger,#b00)";
    } else if (m.type === "response") {
      const done = pending.get(m.id);
      pending.delete(m.id);
      done(m);
    }
  };

  const realFetch = window.fetch.bind(window);

  window.fetch = async (input, init = {}) => {
    const url = new URL(typeof input === "string" ? input : input.url, location.href);
    if (!url.pathname.startsWith("/api/")) return realFetch(input, init);

    const msg = { type: "request", id: nextId++, method: (init.method || "GET").toUpperCase(), path: url.pathname };
    const transfer = [];
    const body = init.body;
    if (body instanceof FormData) {
      msg.fields = {};
      for (const [key, value] of body.entries()) {
        if (value instanceof File) {
          msg.fileName = value.name;
          msg.fileBytes = await value.arrayBuffer();
          transfer.push(msg.fileBytes);
        } else {
          msg.fields[key] = String(value);
        }
      }
    } else if (typeof body === "string") {
      const type = new Headers(init.headers || {}).get("content-type") || "";
      if (type.includes("json")) msg.json = body;
      else { msg.bodyBytes = new TextEncoder().encode(body).buffer; transfer.push(msg.bodyBytes); }
    }

    const reply = await new Promise(resolve => {
      pending.set(msg.id, resolve);
      worker.postMessage(msg, transfer);
    });
    // The browser logs failed network requests itself; a shimmed call must do the same
    // so error-watching tests and DevTools see the failure.
    if (reply.status >= 400) console.error(`HTTP ${reply.status} ${msg.method} ${msg.path}`);
    return new Response(reply.body, {
      status: reply.status,
      headers: { "Content-Type": reply.contentType, ...reply.headers },
    });
  };
})();

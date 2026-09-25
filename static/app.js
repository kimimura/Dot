/* SPA: router, three screens (Upload / Profiles / Library), Excel-style grid, chat. */
(() => {
  const NAME = document.body.dataset.name || "Dot";
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));
  const view = $("#view");
  const state = { doc: null, busy: false, opsQueue: [], opsTimer: null, health: null, search: "" };

  // ── helpers ────────────────────────────────────────────────────────────────
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const md = s => esc(s).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");
  const letter = i => { let s = ""; i += 1; while (i > 0) { const m = (i - 1) % 26; s = String.fromCharCode(65 + m) + s; i = Math.floor((i - 1) / 26); } return s; };
  const fmtDate = s => { if (!s) return "—"; const d = new Date(s.replace(" ", "T")); return isNaN(d) ? s : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }); };
  const fmtDay = s => { if (!s) return "—"; const d = new Date(s.replace(" ", "T")); return isNaN(d) ? s : d.toLocaleDateString(undefined, { dateStyle: "medium" }); };
  const ago = s => { if (!s) return "never"; const ms = Date.now() - new Date(s.replace(" ", "T")); const m = Math.round(ms / 60000); if (m < 1) return "just now"; if (m < 60) return m + " min ago"; const h = Math.round(m / 60); if (h < 24) return h + " h ago"; return Math.round(h / 24) + " d ago"; };
  const el = html => { const t = document.createElement("template"); t.innerHTML = html.trim(); return t.content.firstElementChild; };
  const ICON = {
    ok: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12 5 5L20 7"/></svg>',
    warn: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><path d="M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/></svg>',
    dl: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4v12M6 10l6 6 6-6M4 20h16"/></svg>',
    undo: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><path d="M9 14 4 9l5-5"/><path d="M4 9h11a5 5 0 0 1 0 10h-3"/></svg>',
    trash: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14"/></svg>',
    chev: '<svg class="tpl-chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="14" height="14"><path d="m9 6 6 6-6 6"/></svg>',
    send: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><path d="M22 2 11 13M22 2l-7 20-4-9-9-4z"/></svg>',
    back: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m15 18-6-6 6-6"/></svg>',
    file: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/></svg>',
  };

  async function api(method, path, body) {
    const opts = { method, headers: {} };
    if (body instanceof FormData) opts.body = body;
    else if (body !== undefined) { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
    const r = await fetch(path, opts);
    let data = null;
    try { data = await r.json(); } catch (e) { data = { error: "bad response", say: "I got a reply I couldn't read." }; }
    if (!r.ok) { const e = new Error(data.say || data.error || r.statusText); e.data = data; e.status = r.status; throw e; }
    return data;
  }

  function toast(msg, kind) {
    let t = $("#toast");
    if (!t) { t = el('<div id="toast" class="toast" role="status"></div>'); document.body.appendChild(t); }
    t.textContent = msg; t.className = "toast show" + (kind ? " " + kind : "");
    clearTimeout(t._t); t._t = setTimeout(() => t.classList.remove("show"), 2600);
  }

  // ── shell ──────────────────────────────────────────────────────────────────
  $("#brand-mark").innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="3" width="16" height="18" rx="3"/><circle cx="9.5" cy="10" r="1.2" fill="currentColor"/><circle cx="14.5" cy="10" r="1.2" fill="currentColor"/><path d="M9 15q3 2.4 6 0"/></svg>';
  $("#theme-btn").addEventListener("click", () => {
    const cur = document.documentElement.getAttribute("data-theme");
    const dark = cur ? cur === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
    const next = dark ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem("theme", next); } catch (e) {}
  });
  $("#search-input").addEventListener("input", e => {
    state.search = e.target.value.trim();
    if (!location.hash.startsWith("#/library")) location.hash = "#/library";
    clearTimeout(state._st); state._st = setTimeout(() => { if (location.hash === "#/library") views.library(); }, 250);
  });

  async function loadHealth() {
    try {
      state.health = await api("GET", "/api/health");
      const s = $("#llm-status");
      const m = state.health.llm;
      const bad = { missing_key: "no API key", missing_model: "no model set", unknown_provider: "unknown provider" };
      s.className = "st " + (bad[m] ? "s-held" : m === "offline" ? "s-recv" : "s-ok");
      s.lastElementChild.textContent = bad[m] || (m === "offline" ? "offline mode" : "model connected");
    } catch (e) {}
  }

  async function loadSideProfiles() {
    try {
      const { profiles } = await api("GET", "/api/profiles");
      const box = $("#side-profiles");
      if (!profiles.length) { box.innerHTML = '<div class="side-label">Formats</div><div class="co-item dim"><span class="name">Nothing learned yet</span></div>'; return; }
      box.innerHTML = '<div class="co-group"><button class="co-group-head" type="button"><svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>Formats<span class="rt">' + profiles.length + '</span></button>' +
        profiles.map(p => `<a class="co-item" href="#/profiles/${p.id}"><span class="dot"></span><span class="name">${esc(p.name)}</span><span class="count">${p.times_used}</span></a>`).join("") + "</div>";
      $(".co-group-head", box).addEventListener("click", e => e.currentTarget.parentElement.classList.toggle("collapsed"));
    } catch (e) {}
  }

  function setCrumb(parts) {
    $("#crumb").innerHTML = [`<b>${esc(NAME)}</b>`].concat(parts.map(p => p.href ? `<a href="${p.href}">${esc(p.label)}</a>` : `<span class="node">${esc(p.label)}</span>`)).join('<span class="sep">/</span>');
  }
  function setNav(route) { $$(".nav-item").forEach(a => a.classList.toggle("active", a.dataset.route === route)); }

  // ── router ─────────────────────────────────────────────────────────────────
  const views = {};
  function route() {
    const h = location.hash || "#/upload";
    const m = h.match(/^#\/(upload|profiles|library)(?:\/([^/]+))?/);
    const page = m ? m[1] : "upload", id = m && m[2];
    setNav(page);
    if (page === "upload") views.upload(id);
    else if (page === "profiles") views.profiles(id);
    else views.library(id);
  }
  window.addEventListener("hashchange", e => {
    try { const h = new URL(e.oldURL).hash; if (h && h !== location.hash) state.from = h; } catch (err) {}
    route();
  });

  // ── Upload ─────────────────────────────────────────────────────────────────
  views.upload = async function (docId) {
    setCrumb([{ label: "Upload" }]);
    view.className = "content page-upload";
    view.innerHTML = `
      <div class="page-head">
        <div><h1>Upload</h1><div class="sub">Drop a PDF. ${esc(NAME)} reads it, shows you the sheet, and learns the format.</div></div>
        <div class="btn-row" id="sheet-actions"></div>
      </div>
      <div id="notes"></div>
      <div class="grid-2 upload-grid">
        <section class="sheet-col" id="sheet-col"></section>
        <aside class="detail-col bot-col">
          <div class="bot-stage" id="bot-stage"></div>
          <div class="chat-log detail-scroll" id="chat-log"></div>
          <div class="chat-options" id="chat-options"></div>
          <form class="chat-input" id="chat-form" autocomplete="off">
            <input type="text" id="chat-text" placeholder="Type a reply…" disabled>
            <button class="btn primary" type="submit" id="chat-send" disabled aria-label="Send">${ICON.send}</button>
          </form>
        </aside>
      </div>`;
    Companion.mount($("#bot-stage"));
    $("#chat-form").addEventListener("submit", onChatSubmit);
    if (state.health && ["missing_key", "missing_model", "unknown_provider"].includes(state.health.llm)) {
      $("#notes").appendChild(el(`<div class="note">${ICON.warn}<div><b>Not configured.</b> Set <code>LLM_API_KEY</code> and <code>LLM_MODEL</code> in <code>.env</code> and restart, or leave the key blank to try the flow offline.</div></div>`));
    }
    if (docId) {
      try { renderEnvelope(await api("GET", `/api/docs/${docId}`)); return; } catch (e) { toast(e.message, "f"); }
    }
    state.doc = null;
    renderDropzone();
    chatReset();
    Companion.set("idle");
    Companion.status(`Hi, I'm ${NAME}. Drop a PDF and I'll read it.`, 4000);
    try {
      const { docs } = await api("GET", "/api/docs?unfinished=1");
      if (docs.length) {
        const d = docs[0];
        $("#notes").appendChild(el(`<div class="note resume">${ICON.file}<div><b>Unfinished:</b> ${esc(d.filename)} · ${esc(stageLabel(d.stage))} · ${ago(d.uploaded_at)} <a class="btn small" href="#/upload/${d.id}">Resume</a>${docs.length > 1 ? ` <span class="hint">+${docs.length - 1} more in Library</span>` : ""}</div></div>`));
      }
    } catch (e) {}
  };

  function renderDropzone() {
    const col = $("#sheet-col");
    col.innerHTML = `
      <div class="panel dropzone" id="dropzone" tabindex="0">
        <input type="file" id="file-input" accept="application/pdf,.pdf" hidden>
        <div class="empty-state">
          <div class="dz-icon">${ICON.file}</div>
          <b>Drop a PDF here</b> or click to browse.<br>
          Up to 20 MB and 80 pages. ${esc(NAME)} reads it and shows the extracted sheet right here.
        </div>
      </div>`;
    $("#sheet-actions").innerHTML = "";
    const dz = $("#dropzone"), input = $("#file-input");
    dz.addEventListener("click", () => input.click());
    dz.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); } });
    ["dragenter", "dragover"].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.add("over"); }));
    ["dragleave", "drop"].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.remove("over"); }));
    dz.addEventListener("drop", e => { const f = e.dataTransfer.files && e.dataTransfer.files[0]; if (f) { Companion.catchFrom(e.clientX, e.clientY); upload(f); } });
    input.addEventListener("change", () => { if (input.files[0]) { const r = dz.getBoundingClientRect(); Companion.catchFrom(r.left + r.width / 2, r.top + r.height / 2); upload(input.files[0]); } input.value = ""; });
  }

  async function upload(file) {
    if (state.busy) return;
    if (!/\.pdf$/i.test(file.name)) { toast("I only read PDFs.", "f"); return; }
    setBusy(true, "reading");
    $("#sheet-col").innerHTML = `<div class="panel dropzone busy"><div class="empty-state"><span class="spin-dot"></span> Uploading <b>${esc(file.name)}</b>…</div></div>`;
    chatAdd("bot", `Reading <b>${esc(file.name)}</b>…`);
    const fd = new FormData(); fd.append("file", file);
    try {
      const env = await api("POST", "/api/upload", fd);
      history.replaceState(null, "", `#/upload/${env.doc.id}`);
      renderEnvelope(env);
    } catch (e) {
      setBusy(false, "confused");
      chatAdd("bot", md(e.message));
      renderDropzone();
    }
  }

  function setBusy(b, botState) {
    state.busy = b;
    const box = $("#chat-options");
    if (box) box.classList.toggle("muted", b);
    $$("#chat-options button").forEach(x => x.disabled = b);
    const t = $("#chat-text"), s = $("#chat-send");
    if (t) t.disabled = b || !state.inputMode || state.inputMode === "none";
    if (s) s.disabled = t ? t.disabled : true;
    if (botState) Companion.set(botState);
  }

  // ── envelope → screen ──────────────────────────────────────────────────────
  function renderEnvelope(env, opts = {}) {
    state.doc = env.doc;
    state.table = env.table;
    state.inputMode = env.bot.input;
    renderTranscript(env.transcript);
    if (env.changes && env.changes.length) chatChanges(env.changes);
    renderOptions(env.bot);
    if (env.table) renderSheet($("#sheet-col"), env.table, { readonly: false, doc: env.doc });
    else if (!$("#dropzone") || opts.force) renderSheetPlaceholder(env.doc);
    renderSheetActions(env.doc);
    state.busy = false;
    setBusy(false, env.bot.state);
    if (env.bot.next === "extract") runExtract(env.doc.id);
    else if (env.bot.input && env.bot.input !== "none") { const t = $("#chat-text"); if (t) { t.placeholder = env.bot.input === "name" ? "Name this format…" : "Type a reply…"; t.focus(); } }
  }

  function stageLabel(s) {
    return { identify: "waiting for you", pick: "choose a format", extracting: "reading", review: "review", revising: "revising", confirm_ops: "confirm?",
             save_ask: "save?", naming: "naming", pick_existing: "choose a profile", confirmed: "confirmed", failed: "failed", duplicate: "duplicate?" }[s] || s;
  }

  function renderSheetPlaceholder(doc) {
    $("#sheet-col").innerHTML = `<div class="panel dropzone busy"><div class="empty-state">${ICON.file}<br><b>${esc(doc.filename)}</b><br>${doc.n_pages} page${doc.n_pages === 1 ? "" : "s"} · ${doc.has_text_layer ? "text layer found" : "scanned, no text layer"}<br><span class="hint">The sheet appears here once ${esc(NAME)} has read it.</span></div></div>`;
  }

  function renderSheetActions(doc) {
    const box = $("#sheet-actions");
    if (!box) return;
    let h = "";
    if (state.table) h += `<button class="btn" id="undo-btn" ${doc.can_undo ? "" : "disabled"}>${ICON.undo}Undo</button>`;
    if (doc.xlsx_url) h += `<a class="btn" href="${doc.xlsx_url}">${ICON.dl}Excel</a><a class="btn" href="${doc.csv_url}">${ICON.dl}CSV</a>`;
    h += `<a class="btn" href="#/upload" id="new-upload-btn">New upload</a>`;
    box.innerHTML = h;
    const u = $("#undo-btn"); if (u) u.addEventListener("click", () => act("POST", `/api/docs/${doc.id}/undo`));
    $("#new-upload-btn").addEventListener("click", e => { e.preventDefault(); location.hash = "#/upload"; state.doc = null; views.upload(); });
  }

  async function runExtract(id) {
    setBusy(true, "reading");
    try { renderEnvelope(await api("POST", `/api/docs/${id}/extract`)); }
    catch (e) {
      if (e.status === 409) { await waitWhileBusy(id); return; }
      setBusy(false, "confused"); chatAdd("bot", md(e.message));
    }
  }
  async function waitWhileBusy(id) {
    for (let i = 0; i < 90; i++) {
      await new Promise(r => setTimeout(r, 2000));
      if (!state.doc || state.doc.id !== id) return;
      try {
        const env = await api("GET", `/api/docs/${id}`);
        if (env.doc.stage !== "extracting") { renderEnvelope(env); return; }
        const r = await fetch(`/api/docs/${id}/extract`, { method: "POST" });
        if (r.ok) { renderEnvelope(await r.json()); return; }
      } catch (err) {}
    }
    setBusy(false, "confused"); chatAdd("bot", "That took too long — try again from the Library.");
  }

  async function act(method, path, body) {
    if (state.busy) return;
    setBusy(true, "thinking");
    try { renderEnvelope(await api(method, path, body)); }
    catch (e) {
      if (e.status === 409 && state.doc) { chatAdd("bot", md(e.message)); await waitWhileBusy(state.doc.id); return; }
      setBusy(false, "confused"); chatAdd("bot", md(e.message)); toast(e.message, "f");
    }
  }

  // ── chat ───────────────────────────────────────────────────────────────────
  function chatReset() { $("#chat-log").innerHTML = ""; $("#chat-options").innerHTML = ""; state.inputMode = "none"; }
  function chatAdd(who, html) {
    const log = $("#chat-log"); if (!log) return;
    log.appendChild(el(`<div class="msg ${who}"><div class="bubble">${html}</div></div>`));
    log.scrollTop = log.scrollHeight;
  }
  function chatChanges(changes) {
    const log = $("#chat-log"); if (!log) return;
    log.appendChild(el(`<div class="msg sys"><ul class="changes">${changes.map(c => `<li class="${c.ok ? "ok" : "bad"}">${c.ok ? ICON.ok : ICON.warn}${esc(c.text)}</li>`).join("")}</ul></div>`));
    log.scrollTop = log.scrollHeight;
  }
  function renderTranscript(t) {
    const log = $("#chat-log"); if (!log) return;
    log.innerHTML = "";
    (t || []).forEach(m => log.appendChild(el(`<div class="msg ${m.who}"><div class="bubble">${md(m.text)}</div></div>`)));
    log.scrollTop = log.scrollHeight;
  }
  function renderOptions(bot) {
    const box = $("#chat-options"); if (!box) return;
    box.innerHTML = "";
    (bot.options || []).forEach(o => {
      const b = el(`<button class="btn chip ${o.primary ? "primary" : ""}" type="button">${esc(o.label)}</button>`);
      b.addEventListener("click", () => onOption(o));
      box.appendChild(b);
    });
    box.classList.toggle("muted", state.busy);
    (box.querySelectorAll("button")).forEach(x => x.disabled = state.busy);
    const t = $("#chat-text");
    t.disabled = state.busy || !bot.input || bot.input === "none";
    $("#chat-send").disabled = t.disabled;
    if (!bot.input || bot.input === "none") t.value = "";
  }
  async function onOption(o) {
    const d = state.doc; if (!d) return;
    if (o.id === "new_upload") { location.hash = "#/upload"; state.doc = null; views.upload(); return; }
    if (o.id === "open" && d.duplicate_of) { location.hash = `#/library/${d.duplicate_of}`; return; }
    chatAdd("user", esc(o.label));
    if (o.id === "yes" && d.stage === "review") Companion.set("happy");
    await act("POST", `/api/docs/${d.id}/answer`, { option: o.id, label: o.label });
  }
  async function onChatSubmit(e) {
    e.preventDefault();
    const t = $("#chat-text"), msg = t.value.trim();
    if (!msg || !state.doc || state.busy) return;
    t.value = "";
    chatAdd("user", esc(msg));
    if (state.inputMode === "name") await act("POST", `/api/docs/${state.doc.id}/answer`, { option: "submit", name: msg, label: msg });
    else await act("POST", `/api/docs/${state.doc.id}/chat`, { message: msg });
  }

  // ── Excel-style grid ───────────────────────────────────────────────────────
  function renderSheet(container, table, opts = {}) {
    const cols = table.columns, rows = table.rows, ver = table.verification || { cells: {}, verified: 0, total: 0, checked: false };
    const nDoc = cols.filter(c => c.kind === "doc").length, nRow = cols.length - nDoc;
    const pct = ver.total ? Math.round(100 * ver.verified / ver.total) : 0;
    const shownRows = rows.slice(0, 500);
    const hint = `${rows.length} row${rows.length === 1 ? "" : "s"} · ${cols.length} column${cols.length === 1 ? "" : "s"}` + (ver.checked ? ` · ${pct}% verified` : " · not verifiable (scanned)");
    let h = `<div class="panel xgrid-panel${opts.readonly ? " flat" : ""}"><div class="panel-head"><h2>${esc(opts.doc ? opts.doc.filename : "Extracted table")}</h2><span class="hint">${hint}</span></div>`;
    h += `<div class="csv-scroll xgrid-wrap"><table class="xgrid${opts.readonly ? " readonly" : ""}"><thead>`;
    if (nDoc && nRow) h += `<tr class="xg-groups"><th class="corner"></th><th class="grp doc" colspan="${nDoc}">Document</th><th class="grp row" colspan="${nRow}">Rows</th></tr>`;
    h += `<tr class="xg-names"><th class="corner"></th>` + cols.map((c, i) => `<th class="col ${c.kind}" data-col="${esc(c.name)}"><span class="th-in"><span class="letter">${letter(i)}</span><span class="name" title="${esc(c.name)}">${esc(c.name)}</span>${opts.readonly ? "" : `<button class="colmenu" type="button" aria-label="Column menu">⋯</button>`}</span></th>`).join("") + "</tr></thead><tbody>";
    let lastDoc = null;
    shownRows.forEach((r, ri) => {
      const ds = r._doc !== lastDoc && lastDoc !== null; lastDoc = r._doc;
      h += `<tr data-row="${ri}" ${ds ? 'class="doc-start"' : ""}><td class="rn">${ri + 1}</td>` + cols.map(c => {
        const v = r[c.name] ?? "", st = ver.cells[`${ri}|${c.name}`] || (v ? "na" : "na");
        return `<td class="cell ${c.kind} ${st}" data-row="${ri}" data-col="${esc(c.name)}" tabindex="0" title="${st === "miss" ? "Not found in the PDF text" : st === "edited" ? "Edited" : ""}">${v ? esc(v) : '<span class="empty">—</span>'}</td>`;
      }).join("") + "</tr>";
    });
    h += "</tbody></table></div>";
    h += `<div class="panel-foot"><span class="legend"><i class="lg ok"></i>verified <i class="lg miss"></i>not in PDF text <i class="lg edited"></i>edited</span><span>${rows.length > 500 ? `showing 500 of ${rows.length} rows (all exported) · ` : ""}${nDoc ? "document values repeat on every row" : ""}</span></div></div>`;
    container.innerHTML = h;
    if (!opts.readonly) bindGridEditing(container, table);
  }

  function bindGridEditing(container, table) {
    const tbl = $("table.xgrid", container);
    tbl.addEventListener("dblclick", e => { const td = e.target.closest("td.cell"); if (td) editCell(td); const th = e.target.closest("th.col .name"); if (th) renameHeader(th.closest("th")); });
    tbl.addEventListener("keydown", e => {
      const td = e.target.closest("td.cell"); if (!td || td.isContentEditable) return;
      if (e.key === "Enter" || e.key === "F2") { e.preventDefault(); editCell(td); }
      const move = { ArrowRight: [0, 1], ArrowLeft: [0, -1], ArrowDown: [1, 0], ArrowUp: [-1, 0] }[e.key];
      if (move) {
        e.preventDefault();
        const tr = td.parentElement, ci = Array.from(tr.children).indexOf(td);
        const nr = move[0] ? (move[0] > 0 ? tr.nextElementSibling : tr.previousElementSibling) : tr;
        const nt = nr && nr.children[ci + move[1]];
        if (nt && nt.classList.contains("cell")) nt.focus();
      }
    });
    tbl.addEventListener("click", e => { const b = e.target.closest("button.colmenu"); if (b) { e.stopPropagation(); columnMenu(b.closest("th"), table); } });
  }

  function editCell(td) {
    if (td.isContentEditable) return;
    const orig = td.dataset.orig = td.querySelector(".empty") ? "" : td.textContent;
    td.textContent = orig; td.contentEditable = "plaintext-only"; td.classList.add("editing"); td.focus();
    const sel = getSelection(); sel.selectAllChildren(td); sel.collapseToEnd();
    const finish = commit => {
      td.removeEventListener("blur", onBlur); td.removeEventListener("keydown", onKey);
      td.contentEditable = "false"; td.classList.remove("editing");
      const val = td.textContent.trim();
      if (!commit || val === orig) { td.innerHTML = orig ? esc(orig) : '<span class="empty">—</span>'; return; }
      td.innerHTML = val ? esc(val) : '<span class="empty">—</span>';
      td.classList.remove("ok", "miss", "na"); td.classList.add("edited");
      queueOp({ op: "set_cell", row: +td.dataset.row, col: td.dataset.col, value: val });
    };
    const onBlur = () => finish(true);
    const onKey = e => {
      if (e.key === "Enter" || e.key === "Tab") { e.preventDefault(); finish(true); const n = e.key === "Tab" ? td.nextElementSibling : (td.parentElement.nextElementSibling && td.parentElement.nextElementSibling.children[Array.from(td.parentElement.children).indexOf(td)]); if (n && n.classList.contains("cell")) n.focus(); }
      if (e.key === "Escape") { e.preventDefault(); finish(false); td.focus(); }
    };
    td.addEventListener("blur", onBlur); td.addEventListener("keydown", onKey);
  }

  function renameHeader(th) {
    const name = th.dataset.col;
    const v = prompt("Rename column", name);
    if (v && v.trim() && v.trim() !== name) act("POST", `/api/docs/${state.doc.id}/ops`, { ops: [{ op: "rename_col", col: name, new_name: v.trim() }] });
  }

  function columnMenu(th, table) {
    $$(".menu").forEach(m => m.remove());
    const name = th.dataset.col, col = table.columns.find(c => c.name === name), idx = table.columns.indexOf(col);
    const m = el(`<div class="menu" role="menu">
      <button data-a="rename">Rename</button>
      <button data-a="kind">${col.kind === "doc" ? "Make row-level" : "Make document-level"}</button>
      <button data-a="left" ${idx === 0 ? "disabled" : ""}>Move left</button>
      <button data-a="right" ${idx === table.columns.length - 1 ? "disabled" : ""}>Move right</button>
      <button data-a="date">Format as date</button>
      <button data-a="number">Format as number</button>
      <button data-a="fill">Fill blanks down</button>
      <button data-a="drop" class="danger">Drop column</button></div>`);
    const r = th.getBoundingClientRect();
    m.style.left = Math.min(r.left, innerWidth - 220) + "px"; m.style.top = (r.bottom + 4) + "px";
    document.body.appendChild(m);
    const close = () => { m.remove(); document.removeEventListener("click", close); };
    setTimeout(() => document.addEventListener("click", close), 0);
    m.addEventListener("click", e => {
      const a = e.target.closest("button") && e.target.closest("button").dataset.a; if (!a) return;
      close();
      const id = state.doc.id, ops = [];
      if (a === "rename") return renameHeader(th);
      if (a === "kind") ops.push({ op: "set_col_kind", col: name, kind: col.kind === "doc" ? "row" : "doc" });
      if (a === "left" || a === "right") { const order = table.columns.map(c => c.name); const j = a === "left" ? idx - 1 : idx + 1; [order[idx], order[j]] = [order[j], order[idx]]; ops.push({ op: "reorder_cols", order }); }
      if (a === "date") ops.push({ op: "transform_col", col: name, kind: "date" });
      if (a === "number") ops.push({ op: "transform_col", col: name, kind: "number" });
      if (a === "fill") ops.push({ op: "fill_down", col: name });
      if (a === "drop") ops.push({ op: "drop_col", col: name });
      if (ops.length) act("POST", `/api/docs/${id}/ops`, { ops });
    });
  }

  function queueOp(op) {
    state.opsQueue.push(op);
    clearTimeout(state.opsTimer);
    state.opsTimer = setTimeout(flushOps, 350);
  }
  async function flushOps() {
    if (!state.opsQueue.length || !state.doc) return;
    const ops = state.opsQueue.splice(0);
    try {
      const env = await api("POST", `/api/docs/${state.doc.id}/ops`, { ops });
      state.doc = env.doc; state.table = env.table;
      const active = document.activeElement, keep = active && active.classList.contains("cell") ? [active.dataset.row, active.dataset.col] : null;
      renderSheet($("#sheet-col"), env.table, { readonly: false, doc: env.doc });
      renderSheetActions(env.doc);
      if (keep) { const td = $(`td.cell[data-row="${keep[0]}"][data-col="${CSS.escape(keep[1])}"]`); if (td) td.focus(); }
      if (env.changes && env.changes.some(c => !c.ok)) chatChanges(env.changes.filter(c => !c.ok));
    } catch (e) { toast(e.message, "f"); }
  }

  // ── Profiles ───────────────────────────────────────────────────────────────
  views.profiles = async function (pid) {
    setCrumb([{ label: "Profiles" }]);
    view.className = "content";
    view.innerHTML = `<div class="page-head"><div><h1>Profiles</h1><div class="sub">Every format ${esc(NAME)} has learned. Open one to edit the columns and rules it uses.</div></div>
      <div class="btn-row"><button class="btn" id="new-profile">New profile</button></div></div><div id="profile-list"></div>`;
    $("#new-profile").addEventListener("click", async () => {
      const name = prompt("Profile name"); if (!name || !name.trim()) return;
      try { await api("POST", "/api/profiles", { name: name.trim() }); loadSideProfiles(); views.profiles(); } catch (e) { toast(e.message, "f"); }
    });
    let profiles = [];
    try { ({ profiles } = await api("GET", "/api/profiles")); } catch (e) { toast(e.message, "f"); }
    const list = $("#profile-list");
    if (!profiles.length) { list.innerHTML = `<div class="empty-state"><b>No profiles yet.</b><br>Upload a PDF, confirm the sheet, and say yes when ${esc(NAME)} asks to save the format.</div>`; return; }
    list.innerHTML = "";
    profiles.forEach(p => list.appendChild(profileCard(p, p.id === pid)));
    if (pid) { const c = $(`[data-pid="${pid}"]`); if (c) c.scrollIntoView({ block: "start", behavior: "smooth" }); }
  };

  function statTiles(items) {
    return items.map(([lab, val, meta]) => `<div class="stat"><div class="lab">${esc(lab)}</div><div class="val">${esc(String(val))}</div><div class="meta">${esc(meta)}</div></div>`).join("");
  }

  function profileCard(p, open) {
    const card = el(`<div class="tpl-card ${open ? "" : "collapsed"}" data-pid="${p.id}">
      <div class="tpl-head"><span class="tpl-toggle">${ICON.chev}</span><span class="tpl-name-label">${esc(p.name)}</span>
        <span class="tpl-meta">${p.columns.length} col · used ${p.times_used}× · ${p.last_used_at ? ago(p.last_used_at) : "never used"}</span>
        <span class="tpl-head-actions"><button class="btn small" data-a="rename">Rename</button><button class="btn small danger" data-a="delete">${ICON.trash}</button></span></div>
      <div class="panel tpl-body"><div class="tpl-loading empty-state">Loading…</div></div></div>`);
    const head = $(".tpl-head", card);
    head.addEventListener("click", e => { if (e.target.closest("button")) return; card.classList.toggle("collapsed"); if (!card.classList.contains("collapsed") && !card._loaded) loadProfileBody(card, p.id); });
    head.addEventListener("click", async e => {
      const a = e.target.closest("button") && e.target.closest("button").dataset.a; if (!a) return;
      if (a === "rename") { const n = prompt("Rename profile", p.name); if (n && n.trim() && n.trim() !== p.name) { try { await api("PUT", `/api/profiles/${p.id}`, { name: n.trim() }); loadSideProfiles(); views.profiles(p.id); } catch (err) { toast(err.message, "f"); } } }
      if (a === "delete") { if (confirm(`Delete profile "${p.name}"? Documents keep their data; ${NAME} just forgets the format.`)) { await api("DELETE", `/api/profiles/${p.id}`); loadSideProfiles(); views.profiles(); } }
    });
    if (open) loadProfileBody(card, p.id);
    return card;
  }

  async function loadProfileBody(card, pid) {
    card._loaded = true;
    let p; try { p = await api("GET", `/api/profiles/${pid}`); } catch (e) { toast(e.message, "f"); return; }
    const body = $(".tpl-body", card);
    const sig = p.signature || {};
    body.innerHTML = `
      <div class="panel-head"><h2>Columns</h2><span class="hint">drag to reorder · these exact names are requested from every document of this format</span></div>
      <div class="table-wrap"><table class="tpl-cols-table"><colgroup><col class="c-drag"><col class="c-name"><col class="c-level"><col class="c-hint"><col class="c-seen"><col class="c-del"></colgroup><thead><tr><th class="drag-cell"></th><th>Name</th><th>Level</th><th>Hint for ${esc(NAME)}</th><th class="n">Seen</th><th class="del-cell"></th></tr></thead><tbody id="cols-${p.id}"></tbody>
      <tfoot><tr class="new-col-row"><td></td><td><input type="text" placeholder="New column name" data-new="name"></td><td><select data-new="kind"><option value="row">Row</option><option value="doc">Document</option></select></td><td><input type="text" placeholder="Optional hint" data-new="hint"></td><td class="add-cell" colspan="2"><button class="btn small" data-a="add">Add</button></td></tr></tfoot></table></div>
      <div class="panel-head"><h2>Rules learned</h2><span class="hint">from your chat corrections; applied on every future read</span></div>
      <div class="hints-list" id="hints-${p.id}">${p.hints.length ? p.hints.map((h, i) => `<div class="field-row"><span class="key">rule</span><span class="sample grow">${esc(h.text)}</span><button class="col-del-btn" data-hint="${i}" title="Forget this rule">×</button></div>`).join("") : '<div class="help">Nothing yet. Corrections you make in chat land here.</div>'}</div>
      <div class="panel-head"><h2>Fingerprint</h2><span class="hint">${p.n_docs} document${p.n_docs === 1 ? "" : "s"} · words that always appear on page 1${sig.issuer ? " · " + esc(sig.issuer) : ""}${sig.doc_kind && sig.doc_kind !== "other" ? " · " + esc(sig.doc_kind.replace("_", " ")) : ""}</span></div>
      <div class="doc-body"><div class="finder-list">${p.core_tokens.length ? p.core_tokens.map(t => `<span class="finder-chip">${esc(t)}</span>`).join("") : '<span class="help">No fingerprint yet — confirm a document to build one.</span>'}</div></div>
      <div class="panel-head"><h2>Documents</h2><span class="hint">${p.documents.length} in the Library</span></div>
      <div class="doc-body docs-mini">${p.documents.length ? p.documents.map(d => `<a class="doc-mini" href="#/library/${d.id}">${ICON.file}<span>${esc(d.filename)}</span><span class="hint">${d.n_rows} rows · ${ago(d.confirmed_at || d.uploaded_at)}</span></a>`).join("") : '<span class="help">None yet.</span>'}</div>
      <div class="panel-foot"><span class="hint" id="save-hint-${p.id}">Changes are saved when you press Save.</span><button class="btn primary" data-a="save">Save changes</button></div>`;
    const cols = p.columns.map(c => ({ ...c }));
    const hints = p.hints.map(h => ({ ...h }));
    const tbody = $(`#cols-${p.id}`, body);
    const drawCols = () => {
      tbody.innerHTML = cols.map((c, i) => `<tr class="col-row" draggable="true" data-i="${i}"><td class="drag-cell"><span class="drag-handle">⋮⋮</span></td>
        <td><input type="text" value="${esc(c.name)}" data-f="name" data-i="${i}">${c.aliases && c.aliases.length ? `<div class="help">also printed as: ${c.aliases.map(esc).join(", ")}</div>` : ""}</td>
        <td><select data-f="kind" data-i="${i}"><option value="row" ${c.kind !== "doc" ? "selected" : ""}>Row</option><option value="doc" ${c.kind === "doc" ? "selected" : ""}>Document</option></select></td>
        <td><input type="text" value="${esc(c.hint || "")}" placeholder="e.g. the delivery date, not the order date" data-f="hint" data-i="${i}"></td>
        <td class="n tnum">${c.seen || 0}</td><td class="del-cell"><button class="col-del-btn" data-del="${i}" title="Remove">×</button></td></tr>`).join("");
    };
    drawCols();
    let dragI = null;
    tbody.addEventListener("dragstart", e => { const tr = e.target.closest("tr"); if (!tr) return; dragI = +tr.dataset.i; tr.classList.add("dragging"); e.dataTransfer.effectAllowed = "move"; });
    tbody.addEventListener("dragover", e => { e.preventDefault(); });
    tbody.addEventListener("drop", e => { e.preventDefault(); const tr = e.target.closest("tr"); if (!tr || dragI === null) return; const j = +tr.dataset.i; const [m] = cols.splice(dragI, 1); cols.splice(j, 0, m); dragI = null; drawCols(); });
    tbody.addEventListener("dragend", () => $$("tr.dragging", tbody).forEach(t => t.classList.remove("dragging")));
    body.addEventListener("input", e => { const f = e.target.dataset.f; if (f) cols[+e.target.dataset.i][f] = e.target.value; });
    body.addEventListener("click", async e => {
      const b = e.target.closest("button"); if (!b) return;
      if (b.dataset.del !== undefined) { cols.splice(+b.dataset.del, 1); drawCols(); }
      if (b.dataset.hint !== undefined) { hints.splice(+b.dataset.hint, 1); b.closest(".field-row").remove(); }
      if (b.dataset.a === "add") { const n = $('[data-new="name"]', body).value.trim(); if (!n) return; cols.push({ name: n, kind: $('[data-new="kind"]', body).value, hint: $('[data-new="hint"]', body).value.trim(), seen: 0 }); $('[data-new="name"]', body).value = ""; $('[data-new="hint"]', body).value = ""; drawCols(); }
      if (b.dataset.a === "save") {
        try { await api("PUT", `/api/profiles/${p.id}`, { columns: cols, hints }); toast("Profile saved", "ok"); $(`#save-hint-${p.id}`, body).textContent = "Saved " + new Date().toLocaleTimeString(); }
        catch (err) { toast(err.message, "f"); }
      }
    });
  }

  // ── Library ────────────────────────────────────────────────────────────────
  views.library = async function (docId) {
    if (docId) return views.doc(docId);
    setCrumb([{ label: "Library" }]);
    view.className = "content";
    view.innerHTML = `<div class="page-head"><div><h1>Library</h1><div class="sub">Everything ${esc(NAME)} has read, with the sheet and the conversation behind it.</div></div></div>
      <div id="lib-stats" class="stats"></div>
      <div class="grid-2 lib-grid"><div><div class="sec-head"><h2>Documents</h2><span class="hint" id="lib-count"></span></div><div class="panel" id="lib-table"></div></div>
      <div class="rail-col"><div><div class="sec-head"><h2>By format</h2><span class="hint">confirmed uploads</span></div><div class="bars" id="lib-bars"></div></div>
      <div><div class="sec-head"><h2>Last 14 days</h2><span class="hint">uploads per day</span></div><div class="spark" id="lib-days"></div></div></div></div>`;
    let stats = {}, docs = [];
    try { [stats, { docs }] = await Promise.all([api("GET", "/api/stats"), api("GET", "/api/docs" + (state.search ? "?q=" + encodeURIComponent(state.search) : ""))]); } catch (e) { toast(e.message, "f"); }
    $("#lib-stats").innerHTML = statTiles([
      ["Documents", stats.documents ?? 0, `${stats.confirmed ?? 0} confirmed · ${stats.drafts ?? 0} in progress`],
      ["Rows extracted", stats.rows ?? 0, "across confirmed sheets"],
      ["Recognized", stats.documents ? Math.round(100 * (stats.recognized || 0) / Math.max(stats.confirmed || 1, 1)) + "%" : "—", "of confirmed uploads matched a profile"],
      ["Verified", stats.verified_pct != null ? stats.verified_pct + "%" : "—", "values found in the PDF text"],
    ]);
    const bars = $("#lib-bars"), maxN = Math.max(1, ...(stats.by_profile || []).map(b => b.n));
    bars.innerHTML = (stats.by_profile || []).length ? stats.by_profile.map(b => `<div class="bar-row"><span class="nm" title="${esc(b.name)}">${esc(b.name)}</span><div class="bar-track"><div class="fill" style="width:${Math.round(100 * b.n / maxN)}%"></div></div><span class="num">${b.n}</span></div>`).join("") : '<div class="help">No profiles used yet.</div>';
    const days = [], byDay = Object.fromEntries((stats.by_day || []).map(d => [d.day, d.n]));
    for (let i = 13; i >= 0; i--) { const d = new Date(); d.setDate(d.getDate() - i); const k = d.toISOString().slice(0, 10); days.push([k, byDay[k] || 0]); }
    const maxD = Math.max(1, ...days.map(d => d[1]));
    $("#lib-days").innerHTML = days.map(([k, n]) => `<div class="sp" title="${k}: ${n}"><div class="sp-bar" style="height:${Math.round(100 * n / maxD)}%"></div></div>`).join("") + `<div class="sp-axis"><span>${days[0][0].slice(5)}</span><span>today</span></div>`;
    $("#lib-count").textContent = state.search ? `matching "${state.search}"` : `${docs.length} total`;
    const t = $("#lib-table");
    if (!docs.length) { t.innerHTML = `<div class="empty-state">${state.search ? "Nothing matches that search." : `<b>Nothing here yet.</b><br>Upload a PDF and it lands here once ${esc(NAME)} has read it.`}</div>`; return; }
    t.innerHTML = `<div class="table-wrap"><table><thead><tr><th>Document</th><th>Format</th><th class="n">Rows</th><th class="n">Verified</th><th>Status</th><th></th></tr></thead><tbody>` +
      docs.map(d => `<tr class="click" data-id="${d.id}"><td><span class="po">${esc(d.filename)}</span><div class="fn">${fmtDate(d.uploaded_at)} · ${d.n_pages} p</div></td>
        <td>${d.profile_name ? `<a href="#/profiles/${d.profile_id}">${esc(d.profile_name)}</a>` : '<span class="hint">—</span>'}</td>
        <td class="n">${d.n_rows}</td><td class="n">${d.verified_pct != null ? d.verified_pct + "%" : '<span class="hint">n/a</span>'}</td>
        <td>${statusPill(d.stage)}</td>
        <td class="n"><span class="row-actions">${d.has_output ? `<a class="icon-btn sm" href="/api/docs/${d.id}/download.xlsx" title="Download Excel">${ICON.dl}</a>` : `<a class="btn small" href="#/upload/${d.id}">Resume</a>`}<button class="icon-btn sm" data-del="${d.id}" title="Delete">${ICON.trash}</button></span></td></tr>`).join("") + "</tbody></table></div>";
    t.addEventListener("click", async e => {
      const del = e.target.closest("[data-del]");
      if (del) { e.stopPropagation(); if (confirm("Delete this document and its files?")) { await api("DELETE", `/api/docs/${del.dataset.del}`); views.library(); } return; }
      if (e.target.closest("a, button")) return;
      const tr = e.target.closest("tr[data-id]"); if (tr) location.hash = `#/library/${tr.dataset.id}`;
    });
  };

  function statusPill(stage) {
    const cls = stage === "confirmed" ? "s-ok" : stage === "failed" ? "s-fail" : "s-held";
    return `<span class="st ${cls}"><span class="d"></span>${esc(stage === "confirmed" ? "confirmed" : stageLabel(stage))}</span>`;
  }

  views.doc = async function (id) {
    let env; try { env = await api("GET", `/api/docs/${id}`); } catch (e) { toast(e.message, "f"); location.hash = "#/library"; return; }
    const d = env.doc;
    const from = state.from && /^#\/(library|profiles)(\/|$)/.test(state.from) && state.from !== `#/library/${d.id}` ? state.from : "#/library";
    setCrumb([{ label: from.startsWith("#/profiles") ? "Profiles" : "Library", href: from }, { label: d.filename }]);
    view.className = "content";
    const ver = env.table ? env.table.verification : null;
    view.innerHTML = `<a class="btn backbtn" href="${from}">${ICON.back}Back</a>
      <div class="page-head"><div><h1>${esc(d.filename)}</h1><div class="detail-meta">
        <div class="dm"><div class="k">Uploaded</div><div class="v">${fmtDate(d.uploaded_at)}</div></div>
        <div class="dm"><div class="k">Format</div><div class="v">${d.profile_name ? `<a href="#/profiles/${d.profile_id}">${esc(d.profile_name)}</a>` : "—"}</div></div>
        <div class="dm"><div class="k">Status</div><div class="v">${statusPill(d.stage)}</div></div>
        <div class="dm"><div class="k">Rows</div><div class="v">${env.table ? env.table.rows.length : 0}</div></div>
        <div class="dm"><div class="k">Verified</div><div class="v">${ver && ver.checked ? Math.round(100 * ver.verified / Math.max(ver.total, 1)) + "%" : "n/a"}</div></div></div></div>
        <div class="btn-row">${d.xlsx_url ? `<a class="btn" href="${d.xlsx_url}">${ICON.dl}Excel</a><a class="btn" href="${d.csv_url}">${ICON.dl}CSV</a>` : ""}
          ${d.stage === "confirmed" ? `<button class="btn primary" id="revise-btn">Revise with ${esc(NAME)}</button>` : `<a class="btn primary" href="#/upload/${d.id}">Continue</a>`}
          <button class="btn danger" id="del-btn">${ICON.trash}</button></div></div>
      <div class="panel"><div class="doc-tabs"><button class="doc-tab on" data-t="table">Sheet</button><button class="doc-tab" data-t="chat">Conversation</button><button class="doc-tab" data-t="pdf">PDF</button></div>
        <div id="tab-table" class="tab-pane"></div>
        <div id="tab-chat" class="tab-pane doc-body" hidden><div class="chat-log static">${(env.transcript || []).map(m => `<div class="msg ${m.who}"><div class="bubble">${md(m.text)}</div></div>`).join("") || '<div class="help">No conversation recorded.</div>'}</div></div>
        <div id="tab-pdf" class="tab-pane" hidden><iframe class="pdf-frame" title="PDF" loading="lazy"></iframe></div></div>`;
    if (env.table) renderSheet($("#tab-table"), env.table, { readonly: true });
    else $("#tab-table").innerHTML = `<div class="empty-state">No sheet yet — ${esc(stageLabel(d.stage))}.</div>`;
    $$(".doc-tab").forEach(b => b.addEventListener("click", () => {
      $$(".doc-tab").forEach(x => x.classList.toggle("on", x === b));
      $$(".tab-pane").forEach(p => p.hidden = p.id !== "tab-" + b.dataset.t);
      if (b.dataset.t === "pdf") { const f = $("#tab-pdf iframe"); if (!f.src) f.src = `/api/docs/${d.id}/pdf`; }
    }));
    const rb = $("#revise-btn"); if (rb) rb.addEventListener("click", async () => { await api("POST", `/api/docs/${d.id}/revise`); location.hash = `#/upload/${d.id}`; });
    $("#del-btn").addEventListener("click", async () => { if (confirm("Delete this document and its files?")) { await api("DELETE", `/api/docs/${d.id}`); location.hash = "#/library"; } });
  };

  // ── boot ───────────────────────────────────────────────────────────────────
  loadHealth().then(() => { loadSideProfiles(); route(); });
  window.addEventListener("hashchange", () => { if (location.hash.startsWith("#/profiles") || location.hash.startsWith("#/library")) loadSideProfiles(); });
})();

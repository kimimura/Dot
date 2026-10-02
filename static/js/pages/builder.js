import { NAME, $, $$, view, esc, md, ago, el, ICON } from "../shared/dom.js";
import { state } from "../shared/state.js";
import { views } from "../shared/views.js";
import { api, toast } from "../shared/api.js";
import { setCrumb } from "../shared/shell.js";
import { stageLabel } from "../shared/labels.js";
import { renderSheet } from "../shared/sheet.js";

views.builder = async function (docId) {
  setCrumb([{ label: "Profile Builder" }]);
  view.className = "content page-upload";
  view.innerHTML = `
    <div class="page-head">
      <div><h1>Profile Builder</h1><div class="sub">Teach ${esc(NAME)} a format: drop a PDF, check the sheet, fix anything in chat, and save it. From then on, Upload converts that format on its own.</div></div>
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
  if (docId) {
    try { renderEnvelope(await api("GET", `/api/docs/${docId}`)); return; } catch (e) { toast(e.message, "f"); }
  }
  state.doc = null;
  renderDropzone();
  chatReset();
  Companion.set("idle");
  Companion.status(Companion.line("greet"), 4000);
  try {
    const { docs } = await api("GET", "/api/docs?unfinished=1");
    if (docs.length) {
      const d = docs[0];
      $("#notes").appendChild(el(`<div class="note resume">${ICON.file}<div><b>Unfinished:</b> ${esc(d.filename)} · ${esc(stageLabel(d.stage))} · ${ago(d.uploaded_at)} <a class="btn small" href="#/builder/${d.id}">Resume</a>${docs.length > 1 ? ` <span class="hint">+${docs.length - 1} more in Library</span>` : ""}</div></div>`));
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
        Up to 20 MB and 500 pages. ${esc(NAME)} reads it and shows the extracted sheet right here.
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
    history.replaceState(null, "", `#/builder/${env.doc.id}`);
    renderEnvelope(env);
  } catch (e) {
    setBusy(false, "confused");
    chatAdd("bot", md(e.message));
    renderDropzone();
  }
}

function setBusy(b, botState) {
  state.busy = b;
  clearTimeout(state.slowT);
  if (b) state.slowT = setTimeout(() => { if (state.busy) Companion.status(Companion.line("slow")); }, 12000);
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
  if (env.table) renderSheet($("#sheet-col"), env.table, { readonly: false, doc: env.doc, edit: bindGridEditing });
  else if (!$("#dropzone") || opts.force) renderSheetPlaceholder(env.doc);
  renderSheetActions(env.doc);
  state.busy = false;
  setBusy(false, env.bot.state);
  if (env.bot.next === "extract") runExtract(env.doc.id);
  else if (env.bot.input && env.bot.input !== "none") { const t = $("#chat-text"); if (t) { t.placeholder = env.bot.input === "name" ? "Name this format…" : "Type a reply…"; t.focus(); } }
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
  h += `<a class="btn" href="#/builder" id="new-upload-btn">New upload</a>`;
  box.innerHTML = h;
  const u = $("#undo-btn"); if (u) u.addEventListener("click", () => act("POST", `/api/docs/${doc.id}/undo`));
  $("#new-upload-btn").addEventListener("click", e => { e.preventDefault(); location.hash = "#/builder"; state.doc = null; views.builder(); });
}

// the server reads in the background; the page only watches, for as long as the server is working
async function runExtract(id) {
  if (state.watching === id) return;
  state.watching = id;
  setBusy(true, "reading");
  let shown = "", nudges = 0, env;
  try {
    try { env = await api("POST", `/api/docs/${id}/extract`); } catch (e) { env = null; }
    for (;;) {
      if (!$("#chat-log") || !state.doc || state.doc.id !== id) return;
      if (env && env.doc.stage !== "extracting") { renderEnvelope(env); return; }
      const p = env && env.progress;
      if (p && p.of) {
        const text = Companion.line("pages").replace("{pct}", Math.round(100 * p.done / p.of)).replace("{n}", p.of);
        if (text !== shown) { shown = text; clearTimeout(state.slowT); Companion.status(text); }
      }
      if (env && !env.working) {
        if (++nudges > 3) { setBusy(false, "confused"); chatAdd("bot", Companion.line("timeout")); return; }
        await new Promise(r => setTimeout(r, 1500));
        try { env = await api("POST", `/api/docs/${id}/extract`); } catch (e) {}
        continue;
      }
      await new Promise(r => setTimeout(r, 2000));
      try { env = await api("GET", `/api/docs/${id}`); } catch (e) {}
    }
  } finally {
    if (state.watching === id) state.watching = null;
  }
}

async function act(method, path, body) {
  if (state.busy) return;
  setBusy(true, "thinking");
  try { renderEnvelope(await api(method, path, body)); }
  catch (e) {
    if (e.status === 409 && state.doc) {
      chatAdd("bot", md(e.message));
      const id = state.doc.id;
      await new Promise(r => setTimeout(r, 1500));
      try { const env = await api("GET", `/api/docs/${id}`); if (env.doc.stage === "extracting") runExtract(id); else renderEnvelope(env); }
      catch (err) { setBusy(false, "confused"); }
      return;
    }
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
  if (o.id === "new_upload") { location.hash = "#/builder"; state.doc = null; views.builder(); return; }
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

// ── grid editing ─────────────────────────────────────────────────────────────
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
    td.classList.remove("ok", "miss", "elsewhere", "na"); td.classList.add("edited");
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
    renderSheet($("#sheet-col"), env.table, { readonly: false, doc: env.doc, edit: bindGridEditing });
    renderSheetActions(env.doc);
    if (keep) { const td = $(`td.cell[data-row="${keep[0]}"][data-col="${CSS.escape(keep[1])}"]`); if (td) td.focus(); }
    if (env.changes && env.changes.some(c => !c.ok)) chatChanges(env.changes.filter(c => !c.ok));
  } catch (e) { toast(e.message, "f"); }
}

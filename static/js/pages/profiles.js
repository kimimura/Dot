import { NAME, $, $$, view, esc, ago, el, fmtDate, ICON } from "../shared/dom.js";
import { views } from "../shared/views.js";
import { api, toast } from "../shared/api.js";
import { loadSideProfiles, setCrumb } from "../shared/shell.js";

views.profiles = async function (pid) {
  setCrumb([{ label: "Profiles" }]);
  view.className = "content";
  view.innerHTML = `<div class="page-head"><div><h1>Profiles</h1><div class="sub">Every format ${esc(NAME)} has learned. Open one to edit the columns it uses.</div></div>
    <div class="btn-row"><button class="btn" id="new-profile">New profile</button></div></div><div id="profile-list"></div>`;
  $("#new-profile").addEventListener("click", async () => {
    const name = prompt("Profile name"); if (!name || !name.trim()) return;
    try { await api("POST", "/api/profiles", { name: name.trim() }); loadSideProfiles(); views.profiles(); } catch (e) { toast(e.message, "f"); }
  });
  let profiles = [];
  try { ({ profiles } = await api("GET", "/api/profiles")); } catch (e) { toast(e.message, "f"); }
  const list = $("#profile-list");
  if (!profiles.length) { list.innerHTML = `<div class="empty-state"><b>No profiles yet.</b><br>Drop a PDF in Profile Builder, confirm the sheet, and say yes when ${esc(NAME)} asks to save the format.</div>`; return; }
  list.innerHTML = "";
  profiles.forEach(p => list.appendChild(profileCard(p, p.id === pid)));
  if (pid) { const c = $(`[data-pid="${pid}"]`); if (c) c.scrollIntoView({ block: "start", behavior: "smooth" }); }
};

function profileCard(p, open) {
  const card = el(`<div class="tpl-card ${open ? "" : "collapsed"}" data-pid="${p.id}">
    <div class="tpl-head"><span class="tpl-toggle">${ICON.chev}</span><span class="tpl-name-label">${esc(p.name)}<span class="tpl-edited" title="When a file was last confirmed for it, or it was last saved here; on email, the format edited last wins a tie">last edited ${fmtDate(p.updated_at)}</span></span>
      <span class="tpl-meta">${p.columns.length} col · used ${p.n_docs}×${p.reads_directly ? ' · <span title="Files of this format are read straight from their learned layout">reads directly</span>' : p.layout_problem ? ` · <span title="${esc(p.layout_problem)}">can't read directly yet</span>` : ""}</span>
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
    <tfoot><tr class="new-col-row"><td></td><td><input type="text" placeholder="New column name" data-new="name"></td><td><select data-new="kind"><option value="row">Row</option><option value="doc">Document</option></select></td><td><input type="text" placeholder="Optional, e.g. Extract the number only" data-new="hint"></td><td class="add-cell" colspan="2"><button class="btn small" data-a="add">Add</button></td></tr></tfoot></table></div>
    <div class="panel-head"><h2>Fingerprint</h2><span class="hint">${p.n_docs} document${p.n_docs === 1 ? "" : "s"} · words that always appear on page 1${sig.issuer ? " · " + esc(sig.issuer) : ""}${sig.doc_kind && sig.doc_kind !== "other" ? " · " + esc(sig.doc_kind.replace("_", " ")) : ""}</span></div>
    <div class="doc-body"><div class="finder-list">${p.core_tokens.length ? p.core_tokens.map(t => `<span class="finder-chip">${esc(t)}</span>`).join("") : '<span class="help">No fingerprint yet — confirm a document to build one.</span>'}</div></div>
    <div class="panel-head"><h2>Documents</h2><span class="ph-side"><span class="hint">${p.documents.length} in the Library</span>${p.documents.length ? `<button class="btn small" data-a="reread" title="Read every file of this format again with the format as it is saved now">Re-read all files</button>` : ""}</span></div>
    <div class="doc-body docs-mini">${p.documents.length ? p.documents.map(d => `<a class="doc-mini" href="#/library/${d.id}">${ICON.file}<span>${esc(d.filename)}</span><span class="hint">${d.n_rows} rows · ${ago(d.confirmed_at || d.uploaded_at)}</span></a>`).join("") : '<span class="help">None yet.</span>'}</div>
    <div class="panel-foot"><span class="hint" id="save-hint-${p.id}">Changes are saved when you press Save.</span><button class="btn primary" data-a="save">Save changes</button></div>`;
  // each column remembers the name it was loaded with, so a rename carries what was learned about it
  const cols = p.columns.map(c => ({ ...c, was: c.name }));
  const tbody = $(`#cols-${p.id}`, body);
  const drawCols = () => {
    tbody.innerHTML = cols.map((c, i) => `<tr class="col-row" data-i="${i}"><td class="drag-cell"><span class="drag-handle">⋮⋮</span></td>
      <td><input type="text" value="${esc(c.name)}" data-f="name" data-i="${i}">${c.aliases && c.aliases.length ? `<div class="help">also printed as: ${c.aliases.map(esc).join(", ")}</div>` : ""}</td>
      <td><select data-f="kind" data-i="${i}"><option value="row" ${c.kind !== "doc" ? "selected" : ""}>Row</option><option value="doc" ${c.kind === "doc" ? "selected" : ""}>Document</option></select></td>
      <td><input type="text" value="${esc(c.hint || "")}" placeholder="e.g. Extract the delivery date, not the order date" data-f="hint" data-i="${i}"></td>
      <td class="n tnum">${c.seen || 0}</td><td class="del-cell"><button class="col-del-btn" data-del="${i}" title="Remove">×</button></td></tr>`).join("");
  };
  drawCols();
  let dragI = null;
  // only the handle moves a row, so text in its boxes can still be selected and dragged
  tbody.addEventListener("pointerdown", e => { const tr = e.target.closest("tr"); if (tr) tr.draggable = !!e.target.closest(".drag-cell"); });
  tbody.addEventListener("dragstart", e => { const tr = e.target.closest("tr"); if (!tr || !tr.draggable || e.target !== tr) return; dragI = +tr.dataset.i; tr.classList.add("dragging"); e.dataTransfer.effectAllowed = "move"; });
  tbody.addEventListener("dragover", e => { if (dragI !== null) e.preventDefault(); });
  tbody.addEventListener("drop", e => { if (dragI === null) return; e.preventDefault(); const tr = e.target.closest("tr"); if (!tr) return; const j = +tr.dataset.i; const [m] = cols.splice(dragI, 1); cols.splice(j, 0, m); dragI = null; drawCols(); });
  tbody.addEventListener("dragend", () => { dragI = null; $$("tr", tbody).forEach(t => { t.classList.remove("dragging"); t.draggable = false; }); });
  body.addEventListener("input", e => { const f = e.target.dataset.f; if (f) cols[+e.target.dataset.i][f] = e.target.value; });
  body.addEventListener("click", async e => {
    const b = e.target.closest("button"); if (!b) return;
    if (b.dataset.del !== undefined) { cols.splice(+b.dataset.del, 1); drawCols(); }
    if (b.dataset.a === "add") { const n = $('[data-new="name"]', body).value.trim(); if (!n) return; cols.push({ name: n, kind: $('[data-new="kind"]', body).value, hint: $('[data-new="hint"]', body).value.trim(), seen: 0 }); $('[data-new="name"]', body).value = ""; $('[data-new="hint"]', body).value = ""; drawCols(); }
    if (b.dataset.a === "reread") {
      if (!confirm(`Re-read every ${p.name} file with its current format? A file that doesn't fit it keeps its sheet, and each re-read can be undone from the file's Library page.`)) return;
      b.disabled = true;
      try {
        const r = await api("POST", `/api/profiles/${p.id}/reread`);
        toast(`Re-reading ${r.started} file${r.started === 1 ? "" : "s"} in the background` + (r.skipped ? ` · ${r.skipped} skipped (open or busy)` : ""), "ok");
      } catch (err) { toast(err.message, "f"); }
      b.disabled = false;
    }
    if (b.dataset.a === "save") {
      try { await api("PUT", `/api/profiles/${p.id}`, { columns: cols }); cols.forEach(c => { c.was = c.name; }); toast("Profile saved", "ok"); $(`#save-hint-${p.id}`, body).textContent = "Saved " + new Date().toLocaleTimeString(); }
      catch (err) { toast(err.message, "f"); }
    }
  });
}

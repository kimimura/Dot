import { NAME, $, $$, view, esc, fmtDate, ago, ICON } from "../shared/dom.js";
import { state } from "../shared/state.js";
import { views } from "../shared/views.js";
import { api, toast } from "../shared/api.js";
import { setCrumb } from "../shared/shell.js";
import { sourcePill } from "../shared/labels.js";
import { pctOf, renderSheet } from "../shared/sheet.js";

views.library = async function (docId) {
  if (docId) return views.doc(docId);
  setCrumb([{ label: "Library" }]);
  view.className = "content";
  view.innerHTML = `<div class="page-head"><div><h1>Library</h1><div class="sub">Everything ${esc(NAME)} has read, as CSV, JSON and the original PDF.</div></div></div>
    <div id="lib-stats" class="stats"></div>
    <div class="grid-2 lib-grid"><div><div class="sec-head"><h2>Documents</h2><span class="hint" id="lib-count"></span></div><div class="panel" id="lib-table"></div></div>
    <div class="rail-col"><div><div class="sec-head"><h2>By format</h2><span class="hint">confirmed files</span></div><div class="bars" id="lib-bars"></div></div>
    <div><div class="sec-head"><h2>Last 14 days</h2><span class="hint">files per day</span></div><div class="spark" id="lib-days"></div></div></div></div>`;
  let stats = {}, docs = [];
  try { [stats, { docs }] = await Promise.all([api("GET", "/api/stats"), api("GET", "/api/docs" + (state.search ? "?q=" + encodeURIComponent(state.search) : ""))]); } catch (e) { toast(e.message, "f"); }
  $("#lib-stats").innerHTML = statTiles([
    ["Documents", stats.documents ?? 0, `${stats.confirmed ?? 0} confirmed · ${stats.converted ?? 0} converted · ${stats.drafts ?? 0} in progress`],
    ["Rows extracted", stats.rows ?? 0, "across finished sheets"],
    ["Recognized", stats.documents ? Math.round(100 * (stats.recognized || 0) / Math.max(stats.confirmed || 1, 1)) + "%" : "—", "of confirmed files matched a profile"],
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
  if (!docs.length) { t.innerHTML = `<div class="empty-state">${state.search ? "Nothing matches that search." : `<b>Nothing here yet.</b><br>PDFs sent by email or dropped in Profile Builder land here once ${esc(NAME)} has read them.`}</div>`; return; }
  t.innerHTML = `<div class="table-wrap"><table><thead><tr><th>Document</th><th>Format</th><th class="n">Rows</th><th class="n">Verified</th><th>Source</th><th></th></tr></thead><tbody>` +
    docs.map(d => `<tr class="click" data-id="${d.id}"><td><span class="po">${esc(d.filename)}</span><div class="fn">${fmtDate(d.uploaded_at)} · ${d.n_pages} page${d.n_pages === 1 ? "" : "s"}</div></td>
      <td>${d.profile_name ? `<a href="#/profiles/${d.profile_id}">${esc(d.profile_name)}</a>` : '<span class="hint">—</span>'}</td>
      <td class="n">${d.n_rows}</td><td class="n">${d.verified_pct != null ? d.verified_pct + "%" : '<span class="hint">n/a</span>'}</td>
      <td>${sourcePill(d.source, d.stage, d.sender)}</td>
      <td class="n"><span class="row-actions">${d.has_output ? `<a class="icon-btn sm" href="/api/docs/${d.id}/download.csv" title="Download CSV">${ICON.dl}</a>` : (d.stage === "queued" || d.stage === "converting") ? '<span class="hint">converting…</span>' : `<a class="btn small" href="#/builder/${d.id}">Resume</a>`}<button class="icon-btn sm" data-del="${d.id}" title="Delete">${ICON.trash}</button></span></td></tr>`).join("") + "</tbody></table></div>";
  t.addEventListener("click", async e => {
    const del = e.target.closest("[data-del]");
    if (del) { e.stopPropagation(); if (confirm("Delete this document and its files?")) { await api("DELETE", `/api/docs/${del.dataset.del}`); views.library(); } return; }
    if (e.target.closest("a, button")) return;
    const tr = e.target.closest("tr[data-id]"); if (tr) location.hash = `#/library/${tr.dataset.id}`;
  });
};

function statTiles(items) {
  return items.map(([lab, val, meta]) => `<div class="stat"><div class="lab">${esc(lab)}</div><div class="val">${esc(String(val))}</div><div class="meta">${esc(meta)}</div></div>`).join("");
}

views.doc = async function (id) {
  let env; try { env = await api("GET", `/api/docs/${id}`); } catch (e) { toast(e.message, "f"); location.hash = "#/library"; return; }
  const d = env.doc;
  const from = state.from && /^#\/(library|profiles)(\/|$)/.test(state.from) && state.from !== `#/library/${d.id}` ? state.from : "#/library";
  setCrumb([{ label: from.startsWith("#/profiles") ? "Profiles" : "Library", href: from }, { label: d.filename }]);
  view.className = "content";
  const ver = env.table ? env.table.verification : null;
  const tabs = [["csv", "CSV", d.csv_url], ["json", "JSON", d.json_url], ["pdf", "PDF", d.pdf_url]].filter(t => t[2]);
  view.innerHTML = `<a class="btn backbtn" href="${from}">${ICON.back}Back</a>
    <div class="page-head"><div><h1>${esc(d.filename)}</h1><div class="detail-meta">
      <div class="dm"><div class="k">Uploaded</div><div class="v">${fmtDate(d.uploaded_at)}</div></div>
      <div class="dm"><div class="k">Format</div><div class="v">${d.profile_name ? `<a href="#/profiles/${d.profile_id}">${esc(d.profile_name)}</a>` : "—"}</div></div>
      <div class="dm"><div class="k">Source</div><div class="v">${sourcePill(d.source, d.stage, d.sender)}</div></div>
      <div class="dm"><div class="k">Rows</div><div class="v">${env.table ? env.table.rows.length : 0}</div></div>
      <div class="dm"><div class="k">Verified</div><div class="v">${ver && ver.checked ? pctOf(ver.verified, ver.total) + "%" : "n/a"}</div></div></div></div>
      <div class="btn-row">${(d.stage === "confirmed" || d.stage === "converted") && d.profile_id ? `<button class="btn" id="reread-btn" title="Read this PDF again with the format as it is saved now">Re-read with current format</button>` : ""}
        ${d.stage === "confirmed" ? `<button class="btn primary" id="revise-btn">Revise with ${esc(NAME)}</button>`
          : d.stage === "converted" ? `<button class="btn primary" id="review-btn">Review in Profile Builder</button>`
          : (d.stage === "queued" || d.stage === "converting" || d.stage === "rereading") ? "" : `<a class="btn primary" href="#/builder/${d.id}">Continue</a>`}
        <button class="btn danger" id="del-btn">${ICON.trash}</button></div></div>
    ${rereadNote(d, env.progress)}
    ${d.read_note && d.stage === "converted" ? `<div class="note">${ICON.file}<div>Format: <b>${esc(d.profile_name || "")}</b> · ${esc(d.read_note)}. Review it in Profile Builder and confirm it to teach the new layout.</div></div>` : ""}
    <div class="panel"><div class="doc-tabs">${tabs.map(([t, label], i) => `<button class="doc-tab${i ? "" : " on"}" data-t="${t}">${label}</button>`).join("")}
        <a class="btn small tab-dl" id="tab-dl" href="${tabs[0][2]}">${ICON.dl}Download</a></div>
      ${tabs.map(([t], i) => `<div id="tab-${t}" class="tab-pane${t === "json" ? " doc-body" : ""}"${i ? " hidden" : ""}>${t === "pdf" ? '<iframe class="pdf-frame" title="PDF" loading="lazy"></iframe>' : t === "json" ? '<pre class="json-view">Loading…</pre>' : ""}</div>`).join("")}</div>`;
  // the CSV tab shows the file as downloaded, with who sent it as the last column
  const sent = d.sender_column;
  if (d.csv_url) renderSheet($("#tab-csv"), { ...env.table, columns: [...env.table.columns, { name: sent, kind: "doc" }],
    rows: env.table.rows.map(r => ({ ...r, [sent]: d.sender || "" })) }, { readonly: true });
  const show = t => {
    $$(".doc-tab").forEach(x => x.classList.toggle("on", x.dataset.t === t));
    $$(".tab-pane").forEach(p => p.hidden = p.id !== "tab-" + t);
    $("#tab-dl").href = tabs.find(x => x[0] === t)[2];
    const f = $("#tab-pdf iframe");
    if (t === "pdf" && !f.src) f.src = `/api/docs/${d.id}/pdf`;
    const pre = $("#tab-json pre");
    if (t === "json" && !pre.dataset.loaded) {
      pre.dataset.loaded = "1";
      fetch(d.json_url).then(r => r.ok ? r.text() : Promise.reject()).then(text => showJson(pre, text), () => { pre.textContent = "The JSON couldn't be loaded."; });
    }
  };
  show(tabs[0][0]);
  $$(".doc-tab").forEach(b => b.addEventListener("click", () => show(b.dataset.t)));
  const rb = $("#revise-btn"); if (rb) rb.addEventListener("click", async () => { await api("POST", `/api/docs/${d.id}/revise`); location.hash = `#/builder/${d.id}`; });
  const vb = $("#review-btn"); if (vb) vb.addEventListener("click", async () => { await api("POST", `/api/docs/${d.id}/review`); location.hash = `#/builder/${d.id}`; });
  $("#del-btn").addEventListener("click", async () => { if (confirm("Delete this document and its files?")) { await api("DELETE", `/api/docs/${d.id}`); location.hash = "#/library"; } });
  const rr = $("#reread-btn");
  if (rr) rr.addEventListener("click", async () => {
    rr.disabled = true;
    try { const e2 = await api("POST", `/api/docs/${d.id}/reread`); const c = e2.changes[0]; if (c && !c.ok) toast(c.text, "f"); }
    catch (err) { toast(err.message, "f"); }
    views.doc(d.id);
  });
  const ur = $("#undo-reread-btn");
  if (ur) ur.addEventListener("click", async () => {
    ur.disabled = true;
    try { await api("POST", `/api/docs/${d.id}/reread/undo`); toast("Previous sheet restored", "ok"); } catch (err) { toast(err.message, "f"); }
    views.doc(d.id);
  });
  if (d.stage === "rereading") watchReread(d.id);
};

// a long file is laid out a page of lines at a time as it is scrolled to, so opening it stays quick
function showJson(pre, text) {
  const PAGE = 500, lines = text.split("\n"), end = document.createElement("span");
  let shown = 0, io = null;
  const grow = () => {
    const next = Math.min(shown + PAGE, lines.length);
    pre.insertBefore(document.createTextNode(lines.slice(shown, next).join("\n") + (next < lines.length ? "\n" : "")), end);
    shown = next;
    if (shown >= lines.length) { if (io) io.disconnect(); end.remove(); }
  };
  pre.textContent = "";
  pre.appendChild(end);
  grow();
  if (shown >= lines.length || !window.IntersectionObserver) { while (shown < lines.length) grow(); return; }
  io = new IntersectionObserver(entries => { if (entries.some(e => e.isIntersecting) && end.isConnected) grow(); },
    { root: pre.closest(".tab-pane"), rootMargin: "600px" });
  io.observe(end);
}

function rereadNote(d, progress) {
  const fmt = d.profile_name ? `<b>${esc(d.profile_name)}</b>` : "its";
  if (d.stage === "rereading") {
    const pct = progress && progress.of ? ` ${Math.round(100 * progress.done / progress.of)}%` : "";
    return `<div class="note" id="reread-note">${ICON.file}<div>Re-reading with the current ${fmt} format…<span class="pct">${pct}</span> The sheet below is the previous one until it finishes.</div></div>`;
  }
  if (d.reread_error) return `<div class="note f">${ICON.file}<div>Re-read failed: ${esc(d.reread_error)}. The previous sheet is unchanged.</div></div>`;
  if (d.can_undo_reread) return `<div class="note">${ICON.file}<div>Re-read with the current ${fmt} format ${ago(d.reread_at)}. <button class="btn small" id="undo-reread-btn">Undo re-read</button></div></div>`;
  return "";
}

function watchReread(id) {
  const token = state.rereadWatch = (state.rereadWatch || 0) + 1;
  const tick = async () => {
    if (token !== state.rereadWatch || location.hash !== `#/library/${id}`) return;
    let e2;
    try { e2 = await api("GET", `/api/docs/${id}`); } catch (err) { setTimeout(tick, 4000); return; }
    if (token !== state.rereadWatch || location.hash !== `#/library/${id}`) return;
    if (e2.doc.stage !== "rereading") { views.doc(id); return; }
    const pct = $("#reread-note .pct"), p = e2.progress;
    if (pct && p && p.of) pct.textContent = ` ${Math.round(100 * p.done / p.of)}%`;
    setTimeout(tick, 1500);
  };
  setTimeout(tick, 1500);
}

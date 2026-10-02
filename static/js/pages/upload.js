import { NAME, $, view, esc, ICON } from "../shared/dom.js";
import { state } from "../shared/state.js";
import { views } from "../shared/views.js";
import { api, toast } from "../shared/api.js";
import { setCrumb } from "../shared/shell.js";

const HOW = { "best guess": "best guess", scanned: "scanned", reused: "reused" };
const cap = t => t ? t[0].toUpperCase() + t.slice(1) : t;
const DOC_SVG = (label, color) => `<svg viewBox="0 0 30 38"><path d="M3 2h17l7 7v27H3z" fill="var(--surface)" stroke="var(--ink-3)" stroke-width="1.6" stroke-linejoin="round"/><path d="M20 2v7h7" fill="none" stroke="var(--ink-3)" stroke-width="1.6" stroke-linejoin="round"/>${label === "CSV" ? '<path d="M8 13h14M8 17h14M8 21h14M15 11v12" stroke="var(--ink-4)" stroke-width="1.1"/>' : '<path d="M8 12h12M8 16h12" stroke="var(--ink-4)" stroke-width="1.1"/>'}<rect x="0" y="24" width="22" height="10" rx="2" fill="${color}"/><text x="11" y="31.6" text-anchor="middle" font-size="7" font-weight="700" fill="#fff" font-family="Inter, system-ui, sans-serif">${label}</text></svg>`;
const PDF_ICON = DOC_SVG("PDF", "#d6453d"), CSV_ICON = DOC_SVG("CSV", "#1f9d55");

views.upload = async function (batchId) {
  setCrumb([{ label: "Upload" }]);
  view.className = "content page-convert";
  view.innerHTML = `
    <div class="page-head">
      <div><h1>Upload</h1><div class="sub">Drop PDFs on the left and ${esc(NAME)} turns each one into a CSV on the right, one at a time. Saved formats keep their columns; for anything else ${esc(NAME)} picks them. Teach new formats in <a href="#/builder">Profile Builder</a>.</div></div>
      <div class="cv-head-side"><div class="cv-now" id="cv-now"></div></div>
    </div>
    <div class="cv-stage">
      <section class="cv-col">
        <div class="sec-head"><h2>PDFs</h2><span class="hint" id="cv-in-count"></span></div>
        <div class="cv-top cv-drop" id="cv-drop" tabindex="0"><input type="file" id="cv-input" accept="application/pdf,.pdf" multiple hidden><span><b>Drop PDFs here</b> or click to browse</span><span class="hint">Up to 20 MB and 500 pages each</span></div>
        <div class="cv-stack" id="cv-in" data-empty="Your PDFs wait here."></div>
      </section>
      <section class="cv-col">
        <div class="sec-head"><h2>CSVs</h2><span class="hint" id="cv-out-count"></span></div>
        <a class="cv-top cv-ready off" id="cv-zip"><span>${ICON.dl}<b>Download all</b></span><span class="hint" id="cv-zip-hint">Ready once the first CSV is done</span></a>
        <div class="cv-stack" id="cv-out" data-empty="Finished CSVs land here."></div>
      </section>
      <div class="cv-mid"><div class="bot-stage" id="bot-stage"></div></div>
    </div>`;
  Companion.mount($("#bot-stage"));
  clearTimeout(state.cvTimer);
  if (!batchId) {
    batchId = state.lastBatch || null;
    if (batchId) history.replaceState(null, "", `#/upload/${batchId}`);
  }
  const same = !!batchId && state.batch === batchId;
  state.cvRej = state.cvRej || {};
  Object.assign(state, { doc: null, batch: batchId || null, cvRejected: batchId ? (state.cvRej[batchId] = state.cvRej[batchId] || []) : [],
                         cvMood: null, cvSeen: null, cvDone: [], cvUploading: same ? state.cvUploading : false });
  const dz = $("#cv-drop"), input = $("#cv-input");
  dz.addEventListener("click", () => input.click());
  dz.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); } });
  ["dragenter", "dragover"].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.add("over"); }));
  ["dragleave", "drop"].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.remove("over"); }));
  dz.addEventListener("drop", e => { const fs = [...(e.dataTransfer.files || [])]; if (fs.length) convertFiles(fs); });
  input.addEventListener("change", () => { const fs = [...input.files]; input.value = ""; if (fs.length) convertFiles(fs); });
  $("#cv-in").addEventListener("click", async e => {
    const rb = e.target.closest("[data-retry]"), cx = e.target.closest("[data-cancel]"), dx = e.target.closest("[data-dismiss]"), rs = e.target.closest("[data-resend]");
    if (rb) { rb.disabled = true; try { await api("POST", `/api/docs/${rb.dataset.retry}/reconvert`); } catch (err) { toast(err.message, "f"); } refreshBatch(); }
    else if (cx) {
      const card = cx.closest(".cv-card");
      cx.disabled = true; card.classList.add("leaving");
      try { await api("POST", `/api/docs/${cx.dataset.cancel}/cancel`); }
      catch (err) { card.classList.remove("leaving"); cx.disabled = false; toast(err.message, "f"); }
      refreshBatch();
    }
    else if (rs) { if (state.cvUploading) return; const [x] = state.cvRejected.splice(+rs.dataset.resend, 1); convertFiles([x.file]); }
    else if (dx) { state.cvRejected.splice(+dx.dataset.dismiss, 1); if (state.batch) refreshBatch(); else renderBatch([]); }
  });
  if (state.batch) { refreshBatch(); return; }
  Companion.set("idle");
  Companion.status(Companion.line("cvGreet"), 4000);
  cvNow("Waiting for PDFs");
};

async function convertFiles(files) {
  if (state.cvUploading) return;
  state.cvUploading = true;
  let bid = state.batch;
  for (let i = 0; i < files.length; i++) {
    const f = files[i];
    cvNow(`Uploading ${i + 1} of ${files.length}<br><b>${esc(f.name)}</b>`);
    const fd = new FormData(); fd.append("file", f);
    try {
      const r = await api("POST", "/api/convert" + (bid ? `?batch=${bid}` : ""), fd);
      if (!bid) {
        bid = state.batch = r.batch;
        state.cvRej[bid] = state.cvRejected;
        history.replaceState(null, "", `#/upload/${bid}`);
        state.lastBatch = bid;
        if (state.cvSeen === null) state.cvSeen = {};
      }
      (r.rejected || []).forEach(x => state.cvRejected.push(x));
    } catch (e) {
      state.cvRejected.push({ filename: f.name, error: e.message, file: !e.status || e.status >= 500 ? f : null });
    }
    if (state.batch !== bid) break;
    await refreshBatch(true);
  }
  state.cvUploading = false;
  if (bid) refreshBatch(); else renderBatch([]);
}

async function refreshBatch(once) {
  clearTimeout(state.cvTimer);
  const bid = state.batch;
  if (!bid) return;
  const seq = state.cvSeq = (state.cvSeq || 0) + 1;
  let data;
  try { data = await api("GET", `/api/batches/${bid}`); }
  catch (e) { if (!once && seq === state.cvSeq) state.cvTimer = setTimeout(refreshBatch, 4000); return; }
  if (seq !== state.cvSeq || state.batch !== bid || !$("#cv-in")) return;
  if (!data.files.length && !state.cvRejected.length && !state.cvUploading) {
    if (state.lastBatch === bid) state.lastBatch = null;
    state.batch = null;
    history.replaceState(null, "", "#/upload");
    renderBatch([]);
    return;
  }
  renderBatch(data.files);
  const active = data.files.some(f => f.stage === "queued" || f.stage === "converting");
  if (!once && (active || state.cvUploading)) state.cvTimer = setTimeout(refreshBatch, 1500);
}

function cvNow(html) { const n = $("#cv-now"); if (n) n.innerHTML = html; }

// keyed update, so cards keep their place and animation instead of being redrawn every poll
function syncCards(box, items) {
  const old = new Map([...box.children].map(n => [n.dataset.key, n]));
  let prev = null;
  for (const it of items) {
    let n = old.get(it.key);
    if (!n) { n = document.createElement("div"); n.dataset.key = it.key; }
    old.delete(it.key);
    const keep = ["incoming", "arrive"].filter(c => n.classList.contains(c));
    n.className = ["cv-card", it.cls, ...keep].join(" ");
    if (n._html !== it.html) { n.innerHTML = it.html; n._html = it.html; }
    const want = prev ? prev.nextSibling : box.firstChild;
    if (n !== want) box.insertBefore(n, want);
    prev = n;
  }
  old.forEach(n => n.remove());
}

function pdfCard(f) {
  const p = f.progress, pct = p && p.of ? Math.round(100 * p.done / p.of) : null;
  const pages = `${f.n_pages} page${f.n_pages === 1 ? "" : "s"}`;
  let body, cls;
  if (f.stage === "converting") {
    cls = "active";
    body = `<div class="sub">${pages} · ${pct != null ? pct + "%" : "reading…"}</div><div class="bar-track${pct == null ? " indet" : ""}"><div class="fill" style="width:${pct ?? 30}%"></div></div>`;
  } else if (f.stage === "failed") {
    cls = "failed";
    body = `<div class="sub">${pages}</div><div class="err">${esc(cap(f.error) || "Failed")}</div><button class="btn small" data-retry="${f.id}">Retry</button>`;
  } else {
    cls = "waiting";
    body = `<div class="sub">${pages} · waiting</div>`;
  }
  const x = f.stage === "converting" ? "" : `<button class="cv-x" data-cancel="${f.id}" title="Remove" aria-label="Remove">&times;</button>`;
  return { key: f.id, cls: "pdf " + cls, html: `<div class="ic">${PDF_ICON}</div><div class="meta"><div class="nm" title="${esc(f.filename)}">${esc(f.filename)}</div>${body}</div>${x}` };
}

function rejectedCard(x, i) {
  return { key: "rejected-" + i, cls: "pdf failed", html: `<div class="ic">${PDF_ICON}</div><div class="meta"><div class="nm" title="${esc(x.filename)}">${esc(x.filename)}</div><div class="err">${esc(cap(x.error))}</div>${x.file ? `<button class="btn small" data-resend="${i}">Retry</button>` : ""}</div><button class="cv-x" data-dismiss="${i}" title="Remove" aria-label="Remove">&times;</button>` };
}

function csvCard(f) {
  const stem = f.filename.replace(/\.pdf$/i, "");
  const how = HOW[f.auto_how];
  const fmt = (f.profile_name ? `Format: ${esc(f.profile_name)}` : "Unidentified format") + (f.read_note ? ` · ${esc(f.read_note)}` : how ? ` · ${how}` : "");
  const check = ["best guess", "new", "scanned"].includes(f.auto_how) || !!f.read_note;
  const stats = f.stage === "converted" ? `${Number(f.n_rows || 0).toLocaleString()} rows${f.verified_pct != null ? ` · ${f.verified_pct}% verified` : ""}`
    : `<a href="#/builder/${f.id}">in Profile Builder</a>`;
  return { key: f.id, cls: "csv" + (check ? " check" : ""),
    html: `<div class="ic">${CSV_ICON}</div><div class="meta"><a class="nm" href="#/library/${f.id}" title="Open in Library">${esc(stem)}.csv</a><div class="sub fmt">${fmt}</div><div class="sub">${stats}</div></div>` +
          (f.csv_url ? `<a class="icon-btn sm" href="${f.csv_url}" title="Download CSV">${ICON.dl}</a>` : "") };
}

function renderBatch(files) {
  const inBox = $("#cv-in"), outBox = $("#cv-out");
  if (!inBox) return;
  const first = state.cvSeen === null, seen = state.cvSeen || {};
  const isDone = st => !!st && !["queued", "converting", "failed"].includes(st);
  const started = first ? [] : files.filter(f => f.stage === "converting" && seen[f.id] !== "converting");
  const finished = first ? [] : files.filter(f => isDone(f.stage) && !isDone(seen[f.id]));
  if (first) state.cvDone = files.filter(f => isDone(f.stage)).map(f => f.id);
  finished.forEach(f => { if (!state.cvDone.includes(f.id)) state.cvDone.push(f.id); });
  state.cvSeen = Object.fromEntries(files.map(f => [f.id, f.stage]));

  const rank = { converting: 0, queued: 1, failed: 2 };
  const left = files.filter(f => !isDone(f.stage)).sort((a, b) => (rank[a.stage] ?? 1) - (rank[b.stage] ?? 1));
  const byId = Object.fromEntries(files.map(f => [f.id, f]));
  const right = state.cvDone.slice().reverse().map(id => byId[id]).filter(Boolean);
  syncCards(inBox, left.map(pdfCard).concat(state.cvRejected.map(rejectedCard)));
  syncCards(outBox, right.map(csvCard));

  const card = (box, id) => [...box.children].find(n => n.dataset.key === id);
  const mid = r => [r.left + 22, r.top + r.height / 2];
  started.forEach(f => { const c = card(inBox, f.id); if (c) Companion.catchFrom(...mid(c.getBoundingClientRect())); });
  finished.forEach((f, i) => {
    const c = card(outBox, f.id);
    if (!c || !window.World) return;
    c.classList.add("incoming");
    setTimeout(() => { if (c.classList.contains("incoming")) { c.classList.remove("incoming"); c.classList.add("arrive"); } }, i * 700 + 2500);
    const fromQueue = seen[f.id] !== "converting";
    setTimeout(() => {
      const go = () => World.throwTo(...mid(c.getBoundingClientRect()), () => { c.classList.remove("incoming"); c.classList.add("arrive"); });
      if (fromQueue) { const src = card(inBox, f.id); if (src) Companion.catchFrom(...mid(src.getBoundingClientRect())); setTimeout(go, 650); }
      else go();
    }, i * 700);
  });

  const done = right.length, failed = files.filter(f => f.stage === "failed").length + state.cvRejected.length;
  const togo = left.filter(f => f.stage !== "failed").length;
  $("#cv-in-count").textContent = [togo ? `${togo} to go` : "", failed ? `${failed} not converted` : ""].filter(Boolean).join(" · ");
  $("#cv-out-count").textContent = done ? `${done} ready` : "";
  const zip = $("#cv-zip");
  zip.classList.toggle("off", !done);
  if (done) zip.href = `/api/batches/${state.batch}/download.zip`; else zip.removeAttribute("href");
  $("#cv-zip-hint").textContent = done ? `${done} CSV${done === 1 ? "" : "s"} in one zip` : "Ready once the first CSV is done";
  const now = files.find(f => f.stage === "converting");
  const active = now || files.some(f => f.stage === "queued");
  if (!state.cvUploading) {
    cvNow(now ? `Reading<br><b>${esc(now.filename)}</b>` : active ? "Next file coming up…"
      : done ? `All done · ${done} CSV${done === 1 ? "" : "s"}${failed ? `<br>${failed} not converted` : ""}` : failed ? `${failed} not converted` : "Waiting for PDFs");
  }
  const mood = active || state.cvUploading ? "reading" : failed && !done ? "confused" : done ? "happy" : "idle";
  if (mood !== state.cvMood) {
    state.cvMood = mood;
    Companion.set(mood);
    if (mood === "happy") setTimeout(() => Companion.status(Companion.line("batchDone").replace("{n}", done), 5000), finished.length ? finished.length * 700 + 700 : 0);
  }
}

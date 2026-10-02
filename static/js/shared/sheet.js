import { $, esc, letter } from "./dom.js";

// never shows 100% unless every value checked out
export const pctOf = (v, t) => !t || v >= t ? 100 : Math.floor(1000 * v / t) / 10;

export function renderSheet(container, table, opts = {}) {
  const cols = table.columns, rows = table.rows, ver = table.verification || { cells: {}, verified: 0, total: 0, checked: false };
  const nDoc = cols.filter(c => c.kind === "doc").length, nRow = cols.length - nDoc;
  const pct = pctOf(ver.verified, ver.total);
  const PAGE = 500;
  let shown = Math.min(PAGE, rows.length);
  const rowHtml = ri => {
    const r = rows[ri], ds = ri > 0 && r._doc !== rows[ri - 1]._doc;
    return `<tr data-row="${ri}" ${ds ? 'class="doc-start"' : ""}><td class="rn">${ri + 1}</td>` + cols.map(c => {
      const v = r[c.name] ?? "", st = ver.cells[`${ri}|${c.name}`] || "na";
      return `<td class="cell ${c.kind} ${st}" data-row="${ri}" data-col="${esc(c.name)}" tabindex="0" title="${st === "miss" ? "Not found in the PDF text" : st === "elsewhere" ? "In the PDF, but printed on a different row" : st === "edited" ? "Edited" : ""}">${v ? esc(v) : '<span class="empty">—</span>'}</td>`;
    }).join("") + "</tr>";
  };
  const range = (a, b) => Array.from({ length: b - a }, (_, i) => rowHtml(a + i)).join("");
  const count = () => shown < rows.length ? `showing ${shown.toLocaleString()} of ${rows.length.toLocaleString()} rows` : "";
  const hint = `${rows.length} row${rows.length === 1 ? "" : "s"} · ${cols.length} column${cols.length === 1 ? "" : "s"}` + (ver.checked ? ` · ${pct}% verified` : " · not verifiable (scanned)");
  let h = `<div class="panel xgrid-panel${opts.readonly ? " flat" : ""}"><div class="panel-head"><h2>${esc(opts.doc ? opts.doc.filename : "Extracted table")}</h2><span class="hint">${hint}</span></div>`;
  h += `<div class="csv-scroll xgrid-wrap"><table class="xgrid${opts.readonly ? " readonly" : ""}"><thead>`;
  if (nDoc && nRow) h += `<tr class="xg-groups"><th class="corner"></th><th class="grp doc" colspan="${nDoc}">Document</th><th class="grp row" colspan="${nRow}">Rows</th></tr>`;
  h += `<tr class="xg-names"><th class="corner"></th>` + cols.map((c, i) => `<th class="col ${c.kind}" data-col="${esc(c.name)}"><span class="th-in"><span class="letter">${letter(i)}</span><span class="name" title="${esc(c.name)}">${esc(c.name)}</span>${opts.readonly ? "" : `<button class="colmenu" type="button" aria-label="Column menu">⋯</button>`}</span></th>`).join("") + "</tr></thead><tbody>";
  h += range(0, shown) + `</tbody></table><div class="xgrid-more"></div></div>`;
  h += `<div class="panel-foot"><span class="legend"><i class="lg ok"></i>verified <i class="lg miss"></i>not in PDF text <i class="lg elsewhere"></i>on another row <i class="lg edited"></i>edited</span><span class="sheet-count">${count()}</span></div></div>`;
  container.innerHTML = h;
  if (!opts.readonly && opts.edit) opts.edit(container, table);
  const more = $(".xgrid-more", container);
  if (shown >= rows.length || !window.IntersectionObserver) { more.remove(); return; }
  const io = new IntersectionObserver(entries => {
    if (!entries.some(e => e.isIntersecting) || !more.isConnected) return;
    const next = Math.min(shown + PAGE, rows.length);
    $("table.xgrid tbody", container).insertAdjacentHTML("beforeend", range(shown, next));
    shown = next;
    $(".sheet-count", container).textContent = count();
    if (shown >= rows.length) { io.disconnect(); more.remove(); }
  }, { root: $(".xgrid-wrap", container), rootMargin: "600px" });
  io.observe(more);
}

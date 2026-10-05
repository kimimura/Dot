import { $, esc, letter } from "./dom.js";

// never shows 100% unless every value checked out
export const pctOf = (v, t) => !t || v >= t ? 100 : Math.floor(1000 * v / t) / 10;

const MARKS = [["miss", "doesn't match PDF"], ["blank", "missing"], ["elsewhere", "on another row"], ["edited", "edited"]];

function markedCells(table, ver) {
  const at = Object.fromEntries(table.columns.map((c, i) => [c.name, i]));
  const found = Object.fromEntries(MARKS.map(([st]) => [st, []]));
  for (const [key, st] of Object.entries(ver.cells)) {
    const cut = key.indexOf("|"), ri = +key.slice(0, cut), name = key.slice(cut + 1);
    if (found[st] && ri < table.rows.length && name in at) found[st].push([ri, name]);
  }
  for (const list of Object.values(found)) list.sort((a, b) => a[0] - b[0] || at[a[1]] - at[b[1]]);
  return found;
}

export function renderSheet(container, table, opts = {}) {
  const cols = table.columns, rows = table.rows, ver = table.verification || { cells: {}, verified: 0, total: 0, checked: false };
  const nDoc = cols.filter(c => c.kind === "doc").length, nRow = cols.length - nDoc;
  const pct = pctOf(ver.verified, ver.total);
  const found = markedCells(table, ver), toCheck = found.miss.length + found.blank.length + found.elsewhere.length;
  const PAGE = 500;
  let shown = Math.min(PAGE, rows.length), io = null;
  const rowHtml = ri => {
    const r = rows[ri], ds = ri > 0 && r._doc !== rows[ri - 1]._doc;
    return `<tr data-row="${ri}" ${ds ? 'class="doc-start"' : ""}><td class="rn">${ri + 1}</td>` + cols.map(c => {
      const v = r[c.name] ?? "", st = ver.cells[`${ri}|${c.name}`] || "na";
      return `<td class="cell ${c.kind} ${st}" data-row="${ri}" data-col="${esc(c.name)}" tabindex="0" title="${st === "miss" ? "Doesn't match the PDF: a character differs or part is missing" : st === "blank" ? "Missing: other rows of this document have a value" : st === "elsewhere" ? "In the PDF, but printed on a different row" : st === "edited" ? "Edited" : ""}">${v ? esc(v) : '<span class="empty">—</span>'}</td>`;
    }).join("") + "</tr>";
  };
  const range = (a, b) => Array.from({ length: b - a }, (_, i) => rowHtml(a + i)).join("");
  const count = () => shown < rows.length ? `showing ${shown.toLocaleString()} of ${rows.length.toLocaleString()} rows` : "";
  const hint = `${rows.length} row${rows.length === 1 ? "" : "s"} · ${cols.length} column${cols.length === 1 ? "" : "s"}` + (ver.checked ? ` · ${pct}% verified` : " · not verifiable (scanned)")
    + (ver.checked && toCheck ? ` · <b class="to-check">${toCheck.toLocaleString()} cell${toCheck === 1 ? "" : "s"} to check</b>` : "");
  const legend = `<span class="legend"><i class="lg ok"></i>verified` + MARKS.map(([st, label]) =>
    `<button class="lg-jump" type="button" data-st="${st}"${found[st].length ? ' title="Go to the next one"' : " disabled"}><i class="lg ${st}"></i>${label} <b>${found[st].length.toLocaleString()}</b></button>`).join("") + "</span>";
  let h = `<div class="panel xgrid-panel${opts.readonly ? " flat" : ""}"><div class="panel-head"><h2>${esc(opts.doc ? opts.doc.filename : "Extracted table")}</h2><span class="hint">${hint}</span></div>`;
  h += `<div class="csv-scroll xgrid-wrap"><table class="xgrid${opts.readonly ? " readonly" : ""}"><thead>`;
  if (nDoc && nRow) h += `<tr class="xg-groups"><th class="corner"></th><th class="grp doc" colspan="${nDoc}">Document</th><th class="grp row" colspan="${nRow}">Rows</th></tr>`;
  h += `<tr class="xg-names"><th class="corner"></th>` + cols.map((c, i) => `<th class="col ${c.kind}" data-col="${esc(c.name)}"><span class="th-in"><span class="letter">${letter(i)}</span><span class="name" title="${esc(c.name)}">${esc(c.name)}</span>${opts.readonly ? "" : `<button class="colmenu" type="button" aria-label="Column menu">⋯</button>`}</span></th>`).join("") + "</tr></thead><tbody>";
  h += range(0, shown) + `</tbody></table><div class="xgrid-more"></div></div>`;
  h += `<div class="panel-foot">${legend}<span class="sheet-count">${count()}</span></div></div>`;
  container.innerHTML = h;
  if (!opts.readonly && opts.edit) opts.edit(container, table);
  const more = $(".xgrid-more", container);
  const grow = to => {
    if (to > shown) {
      $("table.xgrid tbody", container).insertAdjacentHTML("beforeend", range(shown, to));
      shown = to;
      $(".sheet-count", container).textContent = count();
    }
    if (shown >= rows.length) { if (io) io.disconnect(); more.remove(); }
  };
  const turn = {};
  // each click on a count goes to the next cell with that mark, wrapping round at the end
  $(".legend", container).addEventListener("click", e => {
    const b = e.target.closest("button.lg-jump");
    if (!b) return;
    const list = found[b.dataset.st], k = turn[b.dataset.st] = ((turn[b.dataset.st] ?? -1) + 1) % list.length;
    const [ri, name] = list[k];
    grow(Math.min(rows.length, Math.ceil((ri + 1) / PAGE) * PAGE));
    const td = $(`td.cell[data-row="${ri}"][data-col="${CSS.escape(name)}"]`, container);
    td.scrollIntoView({ block: "center", inline: "center", behavior: "smooth" });
    td.focus({ preventScroll: true });
    $("b", b).textContent = `${(k + 1).toLocaleString()} of ${list.length.toLocaleString()}`;
  });
  if (shown >= rows.length || !window.IntersectionObserver) { more.remove(); return; }
  io = new IntersectionObserver(entries => {
    if (entries.some(e => e.isIntersecting) && more.isConnected) grow(Math.min(shown + PAGE, rows.length));
  }, { root: $(".xgrid-wrap", container), rootMargin: "600px" });
  io.observe(more);
}

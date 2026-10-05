import { ICON, esc, md } from "./dom.js";

export const changesHtml = changes =>
  `<div class="msg sys"><ul class="changes">${changes.map(c => `<li class="${c.ok ? "ok" : "bad"}">${c.ok ? ICON.ok : ICON.warn}${esc(c.text)}</li>`).join("")}</ul></div>`;

export const entryHtml = m => m.who === "sys" ? changesHtml(m.changes || []) : `<div class="msg ${m.who}"><div class="bubble">${md(m.text)}</div></div>`;

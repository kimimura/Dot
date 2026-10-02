import { $, el } from "./dom.js";

export const avatar = () => (window.Robot && Robot.skin) || "classic";

export async function api(method, path, body) {
  const opts = { method, headers: { "X-Avatar": avatar() } };
  if (body instanceof FormData) opts.body = body;
  else if (body !== undefined) { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
  const r = await fetch(path, opts);
  let data = null;
  try { data = await r.json(); } catch (e) { data = { error: "bad response", say: "I got a reply I couldn't read." }; }
  if (!r.ok) { const e = new Error(data.say || data.error || r.statusText); e.data = data; e.status = r.status; throw e; }
  return data;
}

export function toast(msg, kind) {
  let t = $("#toast");
  if (!t) { t = el('<div id="toast" class="toast" role="status"></div>'); document.body.appendChild(t); }
  t.textContent = msg; t.className = "toast show" + (kind ? " " + kind : "");
  clearTimeout(t._t); t._t = setTimeout(() => t.classList.remove("show"), 2600);
}

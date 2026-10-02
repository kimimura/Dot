import { NAME, $, $$, esc } from "./dom.js";
import { state } from "./state.js";
import { views } from "./views.js";
import { api } from "./api.js";

export function initShell() {
  $("#brand-mark").innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="3" width="16" height="18" rx="3"/><circle cx="9.5" cy="10" r="1.2" fill="currentColor"/><circle cx="14.5" cy="10" r="1.2" fill="currentColor"/><path d="M9 15q3 2.4 6 0"/></svg>';
  const HEAD_BOX = { classic: "22 -12 116 116", ironman: "29 4 102 102" };
  const avatarBtns = $$("#avatar-pick [data-skin]");
  const markAvatar = name => avatarBtns.forEach(b => b.setAttribute("aria-checked", String(b.dataset.skin === name)));
  if (window.Robot) {
    avatarBtns.forEach(b => {
      b.innerHTML = Robot.markup(b.dataset.skin).replace(/viewBox="[^"]*"/, `viewBox="${HEAD_BOX[b.dataset.skin]}"`);
      const svg = b.querySelector("svg");
      svg.dataset.skin = b.dataset.skin;
      svg.classList.add("av-thumb");
    });
    markAvatar(Robot.skin);
  }
  avatarBtns.forEach(b => b.addEventListener("click", () => {
    if (!window.Robot || b.dataset.skin === Robot.skin) return;
    markAvatar(Robot.setSkin(b.dataset.skin));
    if (window.Companion) Companion.status(Companion.line("suitUp"), 1600);
  }));

  const themeSw = $("#theme-switch");
  const darkPref = matchMedia("(prefers-color-scheme: dark)");
  const isDark = () => {
    const t = document.documentElement.getAttribute("data-theme");
    return t ? t === "dark" : darkPref.matches;
  };
  const syncTheme = () => themeSw.setAttribute("aria-checked", String(isDark()));
  syncTheme();
  requestAnimationFrame(() => themeSw.classList.add("ready"));
  darkPref.addEventListener("change", syncTheme);
  themeSw.addEventListener("click", () => {
    const next = isDark() ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem("theme", next); } catch (e) {}
    syncTheme();
  });
  $("#search-input").addEventListener("input", e => {
    state.search = e.target.value.trim();
    if (!location.hash.startsWith("#/library")) location.hash = "#/library";
    clearTimeout(state._st); state._st = setTimeout(() => { if (location.hash === "#/library") views.library(); }, 250);
  });
}

function setStatus(el, cls, text, title) {
  if (!el) return;
  el.className = "st " + cls;
  el.lastElementChild.textContent = text;
  el.title = title || "";
}

export async function loadHealth() {
  try {
    state.health = await api("GET", "/api/health");
    const m = state.health.llm;
    setStatus($("#llm-status"), m === "offline" ? "s-recv" : "s-ok", m === "offline" ? "offline mode" : "model connected");
    const d = state.health.db || "";
    setStatus($("#db-status"), d === "ok" ? "s-ok" : "s-fail",
              d === "ok" ? "database connected" : "database unreachable",
              d === "ok" ? "" : d);
  } catch (e) {
    setStatus($("#llm-status"), "s-fail", "app not responding");
    setStatus($("#db-status"), "s-fail", "app not responding");
  }
}

export async function loadSideProfiles() {
  try {
    const { profiles } = await api("GET", "/api/profiles");
    const box = $("#side-profiles");
    if (!profiles.length) { box.innerHTML = '<div class="side-label">Formats</div><div class="co-item dim"><span class="name">Nothing learned yet</span></div>'; return; }
    box.innerHTML = '<div class="co-group"><button class="co-group-head" type="button"><svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>Formats<span class="rt">' + profiles.length + '</span></button>' +
      profiles.map(p => `<a class="co-item" href="#/profiles/${p.id}"><span class="dot"></span><span class="name">${esc(p.name)}</span><span class="count">${p.times_used}</span></a>`).join("") + "</div>";
    $(".co-group-head", box).addEventListener("click", e => e.currentTarget.parentElement.classList.toggle("collapsed"));
  } catch (e) {}
}

export function setCrumb(parts) {
  $("#crumb").innerHTML = [`<b>${esc(NAME)}</b>`].concat(parts.map(p => p.href ? `<a href="${p.href}">${esc(p.label)}</a>` : `<span class="node">${esc(p.label)}</span>`)).join('<span class="sep">/</span>');
}
export function setNav(route) { $$(".nav-item").forEach(a => a.classList.toggle("active", a.dataset.route === route)); }

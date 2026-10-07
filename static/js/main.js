import { state } from "./shared/state.js";
import { views } from "./shared/views.js";
import { initShell, loadHealth, loadSideProfiles, setNav } from "./shared/shell.js";
import "./pages/builder.js";
import "./pages/profiles.js";
import "./pages/library.js";

initShell();

function route() {
  const h = location.hash || "#/builder";
  const m = h.match(/^#\/(builder|profiles|library)(?:\/([^/]+))?/);
  const page = m ? m[1] : "builder", id = m && m[2];
  setNav(page);
  if (page === "builder") views.builder(id);
  else if (page === "profiles") views.profiles(id);
  else views.library(id);
}
window.addEventListener("hashchange", e => {
  try { const h = new URL(e.oldURL).hash; if (h && h !== location.hash) state.from = h; } catch (err) {}
  route();
});

loadHealth().then(() => { loadSideProfiles(); route(); });
setInterval(loadHealth, 20000);
window.addEventListener("hashchange", () => { if (location.hash.startsWith("#/profiles") || location.hash.startsWith("#/library")) loadSideProfiles(); });

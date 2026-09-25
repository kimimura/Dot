/* Companion: mood state machine + speech. Body/physics live in World (world.js), drawing in Robot (robot.js).
   Lottie files in /static/art replace the robot's drawing if present (see art/README.md). */
const Companion = (() => {
  const NAME = document.body.dataset.name || "Dot";
  const STATES = ["idle", "reading", "thinking", "asking", "happy", "confused", "sleepy", "poked"];
  const ONCE = ["happy", "poked"];
  const QUIPS = ["Still here!", "Drop me a PDF.", "I read fast, promise.", "Boop.", "Formats are my favourite.",
                 "Ready when you are.", "I never forget a layout.", "Feed me spreadsheets.", "Beep.", "My antenna tingles for tables.",
                 "Try dragging me.", "Careful, I bruise."];
  let state = "idle", resting = "idle", pokeT, lastActivity = Date.now();
  const art = { ready: null, mode: null, files: {}, segments: null, data: {}, anim: null, once: new Set(ONCE), fileData: null };
  const face = () => (window.World ? World.face : null);

  // ── Lottie art (optional) ─────────────────────────────────────────────────
  async function loadArt() {
    if (!window.lottie) return false;
    const get = async p => { try { const r = await fetch("/static/art/" + p, { cache: "no-cache" }); return r.ok ? await r.json() : null; } catch (e) { return null; } };
    const manifest = await get("manifest.json");
    if (manifest && manifest.file && manifest.segments) {
      art.fileData = await get(manifest.file);
      if (!art.fileData) return false;
      art.mode = "segments"; art.segments = manifest.segments;
      if (manifest.once) art.once = new Set(manifest.once);
      return true;
    }
    const files = manifest && manifest.files ? manifest.files : Object.fromEntries(STATES.map(s => [s, s + ".json"]));
    if (manifest && manifest.once) art.once = new Set(manifest.once);
    const idle = await get(files.idle || "idle.json");
    if (!idle) return false;
    art.data.idle = idle; art.files = files; art.mode = "files";
    await Promise.all(STATES.filter(s => s !== "idle" && files[s]).map(async s => { const d = await get(files[s]); if (d) art.data[s] = d; }));
    return true;
  }
  function hasArt(s) { return art.mode === "segments" ? !!(art.segments && art.segments[s]) : !!art.data[s]; }
  function playArt(s) {
    const f = face(); if (!art.mode || !f) return;
    const once = art.once.has(s);
    const after = () => { if (state === s && once) set(s === "poked" ? resting : (resting === s ? "idle" : resting)); };
    if (art.mode === "segments") {
      const seg = art.segments[s] || art.segments.idle; if (!seg) return;
      if (!art.anim) art.anim = lottie.loadAnimation({ container: f, renderer: "svg", loop: true, autoplay: false, animationData: art.fileData, rendererSettings: { preserveAspectRatio: "xMidYMid meet" } });
      art.anim.loop = !once; art.anim.removeEventListener("complete"); art.anim.playSegments([seg[0], seg[1]], true);
      if (once) art.anim.addEventListener("complete", after);
      return;
    }
    const data = art.data[s] || art.data.idle;
    if (art.anim) { art.anim.destroy(); art.anim = null; }
    f.innerHTML = "";
    art.anim = lottie.loadAnimation({ container: f, renderer: "svg", loop: !once, autoplay: true, animationData: data, rendererSettings: { preserveAspectRatio: "xMidYMid meet" } });
    if (once) art.anim.addEventListener("complete", after);
  }

  // ── boot: the body lives in the world layer for the whole session ────────
  function boot() {
    if (!window.World) return;
    World.init();
    World.onTap = poke;
    const f = face(); if (f) f.dataset.state = state;
    art.ready = loadArt();
    art.ready.then(ok => { if (ok && face()) { if (window.Robot) Robot.unmount(); face().classList.add("lottie"); playArt(state); } });
    ["pointerdown", "keydown", "pointermove"].forEach(ev => window.addEventListener(ev, wake, { passive: true }));
    setInterval(checkSleep, 5000);
  }

  // mount = "this is Dot's home spot" (the chat column). Leaves a same-size placeholder in the layout.
  function mount(container) {
    container.innerHTML = `<div class="bot-home" aria-hidden="true"></div>`;
    if (window.World) World.setHome(container.querySelector(".bot-home"));
    return api;
  }

  function set(s) {
    if (!STATES.includes(s)) s = "idle";
    if (s !== "poked" && s !== "sleepy") resting = s;
    const changed = s !== state;
    state = s;
    const f = face(); if (f) f.dataset.state = s;
    if (window.Robot && !art.mode) Robot.setState(s);
    if (art.mode && (changed || art.once.has(s))) playArt(s);
    if (window.World) World.onWork(s);
    if (s === "reading" || s === "thinking") status(s === "reading" ? "Reading…" : "Thinking…");
    else if (s !== "poked") hideBubble();
  }
  function busy(kind) { set(kind || "thinking"); }
  function done(s) { set(s || "idle"); }
  function status(text, ms) { if (window.World) World.say(text, ms); }
  function hideBubble() { if (window.World) World.hush(); }

  function poke() {
    const before = state === "poked" ? resting : (state === "sleepy" ? "idle" : state);
    resting = before;
    state = "poked";
    const f = face(); if (f) f.dataset.state = "poked";
    status(QUIPS[Math.floor(Math.random() * QUIPS.length)], 1800);
    if (art.mode) {
      if (hasArt("poked")) playArt("poked");
      else if (f) { f.classList.add("bounce"); setTimeout(() => f.classList.remove("bounce"), 480); }
    } else if (window.Robot) Robot.setState("poked");
    clearTimeout(pokeT);
    pokeT = setTimeout(() => { if (state === "poked") set(before); }, art.mode ? 900 : 650);
  }

  function checkSleep() { if (Date.now() - lastActivity > 60000 && (state === "idle" || state === "asking")) set("sleepy"); }
  function wake() { lastActivity = Date.now(); if (state === "sleepy") set(resting); }
  function catchFrom(x, y) { if (window.World) World.catchFrom(x, y); }

  const api = { mount, set, busy, done, status, poke, catchFrom, name: NAME, get state() { return state; } };
  boot();
  return api;
})();
window.Companion = Companion;

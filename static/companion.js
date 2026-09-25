const Companion = (() => {
  const NAME = document.body.dataset.name || "Dot";
  const STATES = ["idle", "reading", "thinking", "asking", "happy", "confused", "sleepy", "poked"];
  const QUIPS = ["Still here!", "Drop me a PDF.", "I read fast, promise.", "Boop.", "Formats are my favourite.",
                 "Ready when you are.", "I never forget a layout.", "Feed me spreadsheets.", "Beep.",
                 "My antenna tingles for tables.", "Try dragging me.", "Careful, I bruise."];
  let state = "idle", resting = "idle", pokeT, lastActivity = Date.now();
  const face = () => (window.World ? World.face : null);

  function boot() {
    if (!window.World) return;
    World.init();
    World.onTap = poke;
    const f = face();
    if (f) f.dataset.state = state;
    ["pointerdown", "keydown", "pointermove"].forEach(ev => window.addEventListener(ev, wake, { passive: true }));
    setInterval(checkSleep, 5000);
  }

  function mount(container) {
    container.innerHTML = `<div class="bot-home" aria-hidden="true"></div>`;
    if (window.World) World.setHome(container.querySelector(".bot-home"));
    return api;
  }

  function set(s) {
    if (!STATES.includes(s)) s = "idle";
    if (s !== "poked" && s !== "sleepy") resting = s;
    state = s;
    const f = face();
    if (f) f.dataset.state = s;
    if (window.Robot) Robot.setState(s);
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
    const f = face();
    if (f) f.dataset.state = "poked";
    status(QUIPS[Math.floor(Math.random() * QUIPS.length)], 1800);
    if (window.Robot) Robot.setState("poked");
    clearTimeout(pokeT);
    pokeT = setTimeout(() => { if (state === "poked") set(before); }, 650);
  }

  function checkSleep() {
    if (Date.now() - lastActivity > 60000 && (state === "idle" || state === "asking")) set("sleepy");
  }

  function wake() {
    lastActivity = Date.now();
    if (state === "sleepy") set(resting);
  }

  function catchFrom(x, y) { if (window.World) World.catchFrom(x, y); }

  const api = { mount, set, busy, done, status, poke, catchFrom, name: NAME, get state() { return state; } };
  boot();
  return api;
})();
window.Companion = Companion;

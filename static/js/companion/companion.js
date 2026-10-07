const Companion = (() => {
  const NAME = document.body.dataset.name || "Dot";
  const STATES = ["idle", "reading", "thinking", "asking", "happy", "confused", "sleepy", "poked"];
  // What the character says, per avatar. Keys missing from a voice fall back to Dot's.
  const VOICES = {
    classic: {
      greet: `Hi, I'm ${NAME}. Drop a PDF and I'll read it.`,
      reading: "Reading…", thinking: "Thinking…",
      quips: ["Still here!", "Drop me a PDF.", "I read fast, promise.", "Boop.", "Formats are my favourite.",
              "Ready when you are.", "I never forget a layout.", "Feed me spreadsheets.", "Beep.",
              "My antenna tingles for tables.", "Try dragging me.", "Careful, I bruise."],
      tickle: "Hehe!", tickleMore: "Hahaha, stop!", annoyed: "Stop that!",
      fall: ["Oof.", "Ow!", "Whee— oof.", "I'm okay!"],
      suitUp: "Back to Dot.", timeout: "That took too long — try again from the Library.",
      slow: "Still on it, this one's taking a little longer…",
      pages: "Reading… {pct}% of {n} pages",
    },
    ironman: {
      greet: "Tony Stark. Well, the suit. Drop a PDF and I'll take it apart.",
      reading: "Scanning…", thinking: "Running the numbers…",
      quips: ["I am Iron Man. Also, a PDF reader.", "Genius at work.", "Suit's charged. Drop a PDF.",
              "Careful, the repulsors are live.", "Don't touch the arc reactor.", "Billionaire. Genius. Spreadsheet enthusiast.",
              "I built a suit in a cave. Your invoices don't scare me.", "Try dragging me. I dare you.",
              "I don't do small talk. I do tables.", "JARVIS would've been faster. Kidding."],
      tickle: "Hey, that tickles.", tickleMore: "Okay, okay, stop!", annoyed: "Do that again and I'm calling my lawyers.",
      fall: ["Nailed the landing.", "Flight stabilisers offline.", "That was on purpose.", "I'm fine. Suit's fine."],
      suitUp: "Suit up.", timeout: "That took way too long. Try again from the Library.",
      slow: "Still on it. Genius takes a minute…",
      pages: "Scanning… {pct}% of {n} pages",
    },
  };

  function line(key) {
    const skin = window.Robot ? Robot.skin : "classic";
    const v = (VOICES[skin] && VOICES[skin][key]) || VOICES.classic[key];
    return Array.isArray(v) ? v[Math.floor(Math.random() * v.length)] : v;
  }
  let state = "idle", resting = "idle", pokeT, lastActivity = Date.now(), workBubble = false;
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
    if (s === "reading" || s === "thinking") status(line(s));
    else if (s !== "poked" && workBubble) hideBubble();
  }

  function busy(kind) { set(kind || "thinking"); }
  function done(s) { set(s || "idle"); }
  // Untimed text ("Reading…") is cleared when work ends; timed lines are left to run out.
  function status(text, ms) { workBubble = !ms; if (window.World) World.say(text, ms); }
  function hideBubble() { workBubble = false; if (window.World) World.hush(); }

  function poke() {
    const before = state === "poked" ? resting : (state === "sleepy" ? "idle" : state);
    resting = before;
    state = "poked";
    const f = face();
    if (f) f.dataset.state = "poked";
    status(line("quips"), 1800);
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

  const api = { mount, set, busy, done, status, poke, catchFrom, line, name: NAME, get state() { return state; } };
  boot();
  return api;
})();
window.Companion = Companion;

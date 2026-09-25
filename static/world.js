/* World: Dot's body in space. A floating layer over the page with physics (drag, throw, gravity, bounce, walking)
   and a small behaviour brain (wander, fidget, pet, tickle, catch). Robot.js draws; Companion.js decides the mood. */
const World = (() => {
  const W = 136, H = 156, GRAV = 2400, REST = 0.42, PAD = 6, WALK_SPEED = 150;
  const REDUCED = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  let layer, face, bubble, home = null, mode = "home", x = 0, y = 0, vx = 0, vy = 0, rot = 0, vrot = 0, last = 0, raf = null;
  let grab = null, ptr = { x: 0, y: 0, t: 0, vx: 0, vy: 0 }, taps = [], hover = null, petting = false, petAt = 0;
  let nextIdea = 0, roamUntil = 0, target = null, phase = 0, dir = 1, workState = "idle", settledAt = 0, bubbleT = null, catching = null, onTap = null, jumpAim = null;

  function init() {
    if (layer) return api;
    layer = document.createElement("div"); layer.id = "dot-layer";
    layer.innerHTML = `<div class="bot-face" tabindex="0" role="img" aria-label="Dot"></div><div class="bot-bubble" hidden></div>`;
    document.body.appendChild(layer);
    face = layer.querySelector(".bot-face"); bubble = layer.querySelector(".bot-bubble");
    if (window.Robot) Robot.mount(face);
    const r = homeRect(); x = r.x; y = r.y;
    face.addEventListener("pointerdown", onDown);
    window.addEventListener("pointermove", onMove, { passive: true });
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
    face.addEventListener("pointerenter", () => { hover = { x: ptr.x, y: ptr.y, since: performance.now(), still: 0 }; });
    face.addEventListener("pointerleave", () => { hover = null; if (petting) { petting = false; Robot.clearGesture(); } });
    face.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); tapped(); } });
    window.addEventListener("resize", () => { if (mode === "roam" || mode === "walk") y = floorY(); });
    nextIdea = performance.now() + 15000 + Math.random() * 15000;
    last = performance.now();
    raf = requestAnimationFrame(tick);
    return api;
  }

  const floorY = () => window.innerHeight - H - PAD;
  function homeRect() {
    if (home && home.isConnected) { const r = home.getBoundingClientRect(); if (r.width) return { x: r.left, y: r.top, real: true }; }
    return { x: Math.max(8, window.innerWidth - W - 28), y: floorY(), real: false };
  }
  function setHome(el) { home = el; if (el && mode !== "held" && mode !== "fly") goHome(); }
  function onWork(state) {
    workState = state;
    const busy = state !== "idle" && state !== "sleepy";
    if (busy && (mode === "roam" || mode === "walk" || mode === "fidget")) goHome();
    if (busy) nextIdea = Math.max(nextIdea, performance.now() + 20000);
  }
  function goHome() {
    const hr = homeRect();
    if (!hr.real) { mode = "roam"; roamUntil = performance.now() + 8000 + Math.random() * 8000; return; }
    if (Math.abs(y - hr.y) < 40 && Math.abs(x - hr.x) < 60) { mode = "home"; return; }
    if (y >= floorY() - 2) { target = hr.x; mode = "walk"; }
    else mode = "home";
  }

  // ── pointer: drag, throw, tap, pet ───────────────────────────────────────
  function onDown(e) {
    if (e.button !== 0) return;
    e.preventDefault();
    face.setPointerCapture && face.setPointerCapture(e.pointerId);
    grab = { dx: e.clientX - x, dy: e.clientY - y, sx: e.clientX, sy: e.clientY, t: performance.now(), moved: false };
    ptr = { x: e.clientX, y: e.clientY, t: performance.now(), vx: 0, vy: 0 };
  }
  function onMove(e) {
    const now = performance.now(), dt = Math.max(1, now - ptr.t) / 1000;
    const nvx = (e.clientX - ptr.x) / dt, nvy = (e.clientY - ptr.y) / dt;
    ptr = { x: e.clientX, y: e.clientY, t: now, vx: ptr.vx * 0.5 + nvx * 0.5, vy: ptr.vy * 0.5 + nvy * 0.5 };
    if (window.Robot) Robot.look(e.clientX, e.clientY);
    if (grab) {
      if (!grab.moved && Math.hypot(e.clientX - grab.sx, e.clientY - grab.sy) > 5) { grab.moved = true; mode = "held"; face.classList.add("held"); Robot.clearGesture(); catching = null; }
      return;
    }
    if (hover && !REDUCED) {
      const speed = Math.hypot(nvx, nvy);
      const onHead = (e.clientY - y) < H * 0.5;
      if (speed < 160 && onHead) { hover.still += 1; if (hover.still > 12 && !petting && mode === "home" && (workState === "idle" || workState === "asking")) { petting = true; petAt = now; } }
      else hover.still = Math.max(0, hover.still - 3);
      if (petting) { if (speed > 400 || !onHead) { petting = false; Robot.clearGesture(); } else Robot.gesture("pet", 500); }
    }
  }
  function onUp(e) {
    if (!grab) return;
    const g = grab; grab = null;
    face.classList.remove("held");
    if (!g.moved) { tapped(); return; }
    vx = Math.max(-2600, Math.min(2600, ptr.vx)); vy = Math.max(-2600, Math.min(2600, ptr.vy));
    vrot = Math.max(-540, Math.min(540, vx * 0.35));
    mode = "fly";
    Robot.gesture("flail", 4000);
  }
  function tapped() {
    const now = performance.now();
    taps = taps.filter(t => now - t < 1600); taps.push(now);
    const n = taps.length;
    if (n >= 6) { say("Stop that!", 1500); Robot.gesture("annoyed", 1800); taps = []; }
    else if (n >= 3) { say(n === 3 ? "Hehe!" : "Hahaha, stop!", 1200); Robot.gesture("giggle", 1100); }
    else if (onTap) onTap();
  }

  // ── behaviour ────────────────────────────────────────────────────────────
  function think(now) {
    if (REDUCED || now < nextIdea) return;
    const hr = homeRect();
    const free = workState === "idle" || workState === "sleepy";
    if (!free) { nextIdea = now + 10000; return; }
    const roll = Math.random();
    if (mode === "home" || (mode === "roam" && !hr.real)) {
      if (roll < 0.55) { fidget(); nextIdea = now + 14000 + Math.random() * 16000; }
      else if (roll < 0.85 && hr.real) { leaveHome(); nextIdea = now + 30000 + Math.random() * 30000; }
      else if (!hr.real) { target = 30 + Math.random() * Math.max(60, window.innerWidth - W - 60); mode = "walk"; nextIdea = now + 20000 + Math.random() * 20000; }
      else nextIdea = now + 12000;
    } else nextIdea = now + 8000;
  }
  function fidget() { const g = ["stretch", "scratch", "check", "tap"][Math.floor(Math.random() * 4)]; Robot.gesture(g, g === "stretch" ? 1800 : 2200); mode = mode === "home" ? "home" : mode; }
  function leaveHome() {
    if (mode !== "home") return;
    vx = (Math.random() < 0.5 ? -1 : 1) * (140 + Math.random() * 180); vy = -260;
    mode = "fly"; roamUntil = performance.now() + 9000 + Math.random() * 9000;
    Robot.gesture("wave", 900);
  }
  function jumpHome(now) {
    const hr = homeRect();
    const h = Math.max(20, y - hr.y + 24);
    const vy0 = -Math.sqrt(2 * GRAV * h);
    const tApex = -vy0 / GRAV;
    vx = (hr.x - x) / tApex; vy = vy0; vrot = 0; jumpAim = { x: hr.x, y: hr.y, until: now + tApex * 1000 + 400 };
    mode = "jump";
    Robot.gesture("flail", 300);
  }

  // ── catch a dropped PDF ──────────────────────────────────────────────────
  function catchFrom(px, py) {
    const icon = document.createElement("div"); icon.className = "pdf-fly"; icon.innerHTML = '<svg viewBox="0 0 24 30"><path d="M3 2h11l7 7v19H3z"/><path d="M14 2v7h7M7 15h10M7 20h10M7 25h6"/></svg>';
    layer.appendChild(icon);
    catching = { el: icon, x0: px, y0: py, t0: performance.now(), dur: 620 };
    Robot.gesture("catch", 900);
    if (mode !== "home" && mode !== "held") goHome();
  }

  // ── speech ───────────────────────────────────────────────────────────────
  function say(text, ms) {
    if (!bubble) return;
    bubble.textContent = text; bubble.hidden = false;
    clearTimeout(bubbleT); if (ms) bubbleT = setTimeout(() => { bubble.hidden = true; }, ms);
  }
  function hush() { if (bubble) bubble.hidden = true; }

  // ── main loop ────────────────────────────────────────────────────────────
  function tick(now) {
    const dt = Math.min(0.05, (now - last) / 1000); last = now;
    const fy = floorY(), maxX = window.innerWidth - W;
    let ext = null;
    think(now);

    if (mode === "held") {
      const tx = ptr.x - grab.dx, ty = ptr.y - grab.dy;
      vx = (tx - x) / Math.max(dt, 0.008); vy = (ty - y) / Math.max(dt, 0.008);
      x = tx; y = ty;
      const lean = Math.max(-28, Math.min(28, ptr.vx * 0.018));
      rot += (lean - rot) * 0.18;
      ext = { mode: "held", swing: Math.max(-25, Math.min(25, -ptr.vx * 0.015)), lift: 20, eyeScale: 1.25, mouth: "o", browY: -4, look: 0, pupilY: 2 };
    } else if (mode === "fly" || mode === "jump") {
      vy += GRAV * dt; x += vx * dt; y += vy * dt; rot += vrot * dt;
      if (x < 0) { x = 0; vx = -vx * REST; vrot *= -0.5; }
      if (x > maxX) { x = maxX; vx = -vx * REST; vrot *= -0.5; }
      if (y < 0) { y = 0; vy = -vy * REST; }
      if (mode === "jump" && jumpAim) {
        if (vy > 0 && Math.abs(y - jumpAim.y) < 34 && Math.abs(x - jumpAim.x) < 60) { mode = "home"; vx = vy = vrot = 0; jumpAim = null; Robot.gesture("land", 400); }
        else if (now > jumpAim.until) { mode = "fly"; jumpAim = null; }
      }
      if (y >= fy) {
        y = fy;
        if (vy > 260) { Robot.impact(Math.min(1, vy / 1600)); if (vy > 900) { Robot.gesture("dazed", 1400); say(["Oof.", "Ow!", "Whee— oof.", "I'm okay!"][Math.floor(Math.random() * 4)], 1200); } }
        vy = Math.abs(vy) < 140 ? 0 : -vy * REST; vx *= 0.75; vrot *= 0.4;
        if (vy === 0) { vx *= 0.9; rot += (0 - rot) * 0.15; if (Math.abs(vx) < 12 && Math.abs(rot) < 2) { vx = 0; rot = 0; vrot = 0; if (mode === "fly") { mode = "roam"; settledAt = now; if (!roamUntil || roamUntil < now) roamUntil = now + 6000 + Math.random() * 8000; if (Robot.gesture_ === "flail") Robot.clearGesture(); } } }
      }
      const airborne = y < fy - 2;
      ext = { mode: airborne ? "fly" : "land", lift: Math.max(0, (fy - y) * 0.15), look: 0 };
      if (!airborne) ext = { mode: "land", look: 0 };
    } else if (mode === "walk") {
      const tx = target == null ? x : target;
      const d = tx - x;
      if (Math.abs(d) < 6) { x = tx; vx = 0; const hr = homeRect(); if (hr.real && Math.abs(tx - hr.x) < 8 && y > hr.y + 40) jumpHome(now); else { mode = "roam"; roamUntil = now + 6000 + Math.random() * 8000; } }
      else { dir = d > 0 ? 1 : -1; const step = Math.min(Math.abs(d), WALK_SPEED * dt); x += dir * step; y = fy; phase += dt * 9; ext = { mode: "walk", phase, bodyRot: dir * 3, headRot: dir * 4, look: 0, pupilX: dir * 2.5 }; }
      rot += (0 - rot) * 0.2;
    } else if (mode === "roam") {
      y = fy; rot += (0 - rot) * 0.2;
      if (now > roamUntil) { const hr = homeRect(); if (hr.real) { target = hr.x; mode = "walk"; } else if (Math.random() < 0.5) { target = 30 + Math.random() * Math.max(60, maxX - 60); mode = "walk"; roamUntil = now + 8000 + Math.random() * 8000; } else { roamUntil = now + 6000 + Math.random() * 8000; if (!REDUCED) fidget(); } }
    } else {
      const hr = homeRect();
      x += (hr.x - x) * 0.25; y += (hr.y - y) * 0.25; rot += (0 - rot) * 0.2;
      if (!hr.real) { y = fy; }
    }

    if (catching) {
      const p = Math.min(1, (now - catching.t0) / catching.dur);
      const hx = x + W * 0.72, hy = y + H * 0.66;
      const cx = catching.x0 + (hx - catching.x0) * p, cy = catching.y0 + (hy - catching.y0) * p - Math.sin(p * Math.PI) * 120;
      catching.el.style.transform = `translate(${cx.toFixed(1)}px, ${cy.toFixed(1)}px) rotate(${(p * 360).toFixed(1)}deg)`;
      if (p >= 1) { catching.el.remove(); catching = null; }
    }

    if (window.Robot) Robot.setExternal(ext);
    face.style.transform = `translate(${x.toFixed(1)}px, ${y.toFixed(1)}px) rotate(${rot.toFixed(2)}deg)`;
    if (!bubble.hidden) {
      const right = x + W + 10 + 220 < window.innerWidth;
      bubble.style.left = right ? (x + W + 10) + "px" : "";
      bubble.style.right = right ? "" : (window.innerWidth - x + 10) + "px";
      bubble.style.top = (y + 18) + "px";
      bubble.classList.toggle("flip", !right);
    }
    raf = requestAnimationFrame(tick);
  }

  const api = { init, setHome, onWork, say, hush, catchFrom, get face() { return face; }, get mode() { return mode; }, set onTap(f) { onTap = f; }, fidget, leaveHome };
  return api;
})();
window.World = World;

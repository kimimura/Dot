/* Dot the robot: SVG rig + procedural animation.
   Companion.js sets the expression state; World.js layers physical poses (held, flying, walking) and gestures on top. */
const Robot = (() => {
  const REDUCED = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;

  const BASE = { bodyY: 0, bodyRot: 0, headRot: 0, headY: 0, armL: 0, armR: 0, legL: 0, legR: 0, eyeOpen: 1, eyeScale: 1, look: 1, pupilX: 0, pupilY: 0,
                 browL: 0, browR: 0, browY: 0, mouth: "smile", glow: 0.15, cheeks: 0, page: 0, dots: 0, q: 0, zzz: 0, happyEyes: 0, sx: 1, sy: 1, ledRate: 1, spin: 0 };
  const POSES = {
    idle:     {},
    reading:  { armR: -78, armL: 6, headRot: 7, headY: 2, eyeOpen: .9, look: 0, pupilY: 2.5, mouth: "flat", page: 1, glow: .25 },
    thinking: { armL: -152, headRot: -9, look: 0, pupilX: 3, pupilY: -3.5, browL: -12, browY: -2, mouth: "wave", glow: 1, dots: 1, ledRate: 3 },
    asking:   { bodyRot: -3, headY: -2, browY: -4, eyeScale: 1.15, mouth: "o", armR: -45, glow: .45 },
    happy:    { armL: -165, armR: -165, eyeOpen: .35, happyEyes: 1, mouth: "grin", cheeks: 1, glow: .9, browY: -2, ledRate: 4 },
    confused: { headRot: -13, browL: -15, browR: 12, mouth: "wave", armL: 28, armR: -28, q: 1, glow: .3, look: 0, pupilX: -2 },
    sleepy:   { headRot: 11, headY: 5, bodyY: 3, eyeOpen: .05, mouth: "flat", zzz: 1, glow: 0, armL: 10, armR: 10, look: 0, ledRate: .3 },
    poked:    { eyeScale: 1.35, mouth: "o", sx: 1.14, sy: .84, glow: 1, browY: -5, armL: -40, armR: -40 },
  };
  const GESTURES = {
    stretch: { armL: -172, armR: -172, sy: 1.07, sx: .97, headY: -3, eyeOpen: .25, mouth: "o", browY: -3 },
    scratch: { armR: -150, headRot: 9, mouth: "flat", pupilX: -2.5, pupilY: -1, browL: -6, look: 0 },
    check:   { headRot: 0, headY: 5, pupilY: 4, armL: -70, armR: -20, mouth: "o", look: 0, ledRate: 5, glow: .5 },
    tap:     { headRot: -4, mouth: "flat", look: 1 },
    giggle:  { happyEyes: 1, eyeOpen: .35, mouth: "grin", cheeks: 1, armL: -30, armR: -30, glow: .8 },
    annoyed: { armL: 42, armR: -42, browL: -12, browR: 12, browY: 2, mouth: "flat", eyeScale: .9, look: 0, pupilX: 3, headRot: -5 },
    dazed:   { spin: 1, mouth: "wave", browL: -10, browR: 10, armL: 20, armR: -20, look: 0, headRot: 6 },
    catch:   { armR: -95, armL: -35, eyeScale: 1.2, mouth: "o", browY: -4, look: 0, pupilX: 2, pupilY: -3 },
    pet:     { happyEyes: 1, eyeOpen: .3, mouth: "smile", cheeks: 1, headY: 2, glow: .6, look: 0 },
    held:    { eyeScale: 1.25, mouth: "o", browY: -4, look: 0, pupilY: 2 },
    flail:   { eyeScale: 1.35, mouth: "o", browY: -5, look: 0 },
    land:    { eyeOpen: .5, mouth: "flat", browY: 1 },
    wave:    { armR: -160, mouth: "smile", eyeOpen: 1, browY: -2 },
  };
  const NUMERIC = Object.keys(BASE).filter(k => typeof BASE[k] === "number");

  let svg, el = {}, cur = { ...BASE }, vel = { sx: 0, sy: 0, bodyY: 0 }, state = "idle", enteredAt = 0, raf = null;
  let cursor = null, blinkAt = 0, blinkUntil = 0, mouthClass = "", ext = null, gest = null;

  function markup() {
    return `
<svg class="bot robot" viewBox="0 0 160 184" aria-hidden="true">
  <defs>
    <linearGradient id="rb-metal" x1="0" y1="0" x2="0" y2="1"><stop offset="0" class="m1"/><stop offset="1" class="m2"/></linearGradient>
    <linearGradient id="rb-metal2" x1="0" y1="0" x2="1" y2="1"><stop offset="0" class="m1"/><stop offset="1" class="m2"/></linearGradient>
    <linearGradient id="rb-screen" x1="0" y1="0" x2="0" y2="1"><stop offset="0" class="sc1"/><stop offset="1" class="sc2"/></linearGradient>
    <radialGradient id="rb-glow"><stop offset="0" class="g1"/><stop offset="1" class="g2"/></radialGradient>
    <radialGradient id="rb-eye"><stop offset="0" class="e1"/><stop offset="1" class="e2"/></radialGradient>
  </defs>
  <ellipse class="shadow" cx="80" cy="174" rx="36" ry="6"/>
  <g class="rig">
    <g class="legs">
      <g class="leg-l"><rect class="leg" x="61" y="140" width="14" height="20" rx="6"/><rect class="foot" x="52" y="154" width="28" height="13" rx="6.5"/></g>
      <g class="leg-r"><rect class="leg" x="85" y="140" width="14" height="20" rx="6"/><rect class="foot" x="80" y="154" width="28" height="13" rx="6.5"/></g>
    </g>
    <g class="body">
      <g class="arm arm-l">
        <rect class="upper" x="42" y="98" width="15" height="32" rx="7.5"/>
        <circle class="hand" cx="49.5" cy="133" r="8.5"/>
      </g>
      <g class="arm arm-r">
        <rect class="upper" x="103" y="98" width="15" height="32" rx="7.5"/>
        <circle class="hand" cx="110.5" cy="133" r="8.5"/>
        <g class="page"><rect x="92" y="112" width="32" height="40" rx="3"/><path d="M98 122h20M98 129h20M98 136h13"/></g>
      </g>
      <rect class="torso" x="50" y="90" width="60" height="54" rx="17"/>
      <rect class="torso-hi" x="56" y="95" width="18" height="8" rx="4"/>
      <rect class="panel" x="61" y="104" width="38" height="22" rx="7"/>
      <circle class="led led1" cx="70" cy="115" r="3"/><circle class="led led2" cx="80" cy="115" r="3"/><circle class="led led3" cx="90" cy="115" r="3"/>
      <rect class="neck" x="72" y="84" width="16" height="10" rx="3"/>
      <g class="head">
        <line class="antenna" x1="80" y1="30" x2="80" y2="17"/>
        <circle class="antenna-glow" cx="80" cy="12" r="12"/>
        <circle class="antenna-ball" cx="80" cy="12" r="5"/>
        <rect class="ear" x="24" y="52" width="11" height="22" rx="4.5"/><rect class="ear" x="125" y="52" width="11" height="22" rx="4.5"/>
        <rect class="helmet" x="32" y="30" width="96" height="62" rx="24"/>
        <rect class="helmet-hi" x="42" y="35" width="26" height="7" rx="3.5"/>
        <rect class="screen" x="42" y="41" width="76" height="45" rx="15"/>
        <g class="eyes">
          <g class="eye eye-l"><ellipse class="eyeball" cx="64" cy="61" rx="8" ry="9"/><circle class="pupil" cx="64" cy="61" r="3.6"/><circle class="spark" cx="66.5" cy="57.5" r="1.6"/><path class="eye-happy" d="M55.5 63.5 q8.5 -11 17 0"/></g>
          <g class="eye eye-r"><ellipse class="eyeball" cx="96" cy="61" rx="8" ry="9"/><circle class="pupil" cx="96" cy="61" r="3.6"/><circle class="spark" cx="98.5" cy="57.5" r="1.6"/><path class="eye-happy" d="M87.5 63.5 q8.5 -11 17 0"/></g>
        </g>
        <line class="brow brow-l" x1="56" y1="48" x2="72" y2="48"/><line class="brow brow-r" x1="88" y1="48" x2="104" y2="48"/>
        <g class="mouths">
          <path class="mouth m-smile" d="M70 75 q10 7 20 0"/>
          <path class="mouth m-flat" d="M71 76 h18"/>
          <path class="mouth m-o" d="M80 71.5 a5 5.5 0 1 0 .01 0"/>
          <path class="mouth m-grin" d="M67 72 q13 13 26 0 z"/>
          <path class="mouth m-wave" d="M69 76 q5.5 -5 11 0 t11 0"/>
        </g>
        <circle class="cheek" cx="53" cy="71" r="5"/><circle class="cheek" cx="107" cy="71" r="5"/>
      </g>
    </g>
    <g class="fx">
      <g class="dots"><circle cx="122" cy="30" r="2.5"/><circle cx="131" cy="21" r="3.5"/><circle cx="142" cy="10" r="4.5"/></g>
      <text class="qmark" x="124" y="34">?</text>
      <g class="zzz"><text class="z z1" x="120" y="34">z</text><text class="z z2" x="130" y="22">z</text><text class="z z3" x="141" y="10">z</text></g>
    </g>
  </g>
</svg>`;
  }

  function mount(container) {
    container.innerHTML = markup();
    svg = container.querySelector("svg.robot");
    const q = s => svg.querySelector(s);
    el = { rig: q(".rig"), body: q(".body"), head: q(".head"), armL: q(".arm-l"), armR: q(".arm-r"), legL: q(".leg-l"), legR: q(".leg-r"),
           eyeL: q(".eye-l"), eyeR: q(".eye-r"), pupils: svg.querySelectorAll(".pupil, .spark"), browL: q(".brow-l"), browR: q(".brow-r"),
           glow: q(".antenna-glow"), ball: q(".antenna-ball"), cheeks: svg.querySelectorAll(".cheek"), page: q(".page"), dots: q(".dots"),
           q: q(".qmark"), zzz: q(".zzz"), zs: svg.querySelectorAll(".z"), shadow: q(".shadow"), leds: svg.querySelectorAll(".led") };
    cur = { ...BASE }; vel = { sx: 0, sy: 0, bodyY: 0 };
    blinkAt = performance.now() + 2500 + Math.random() * 3000;
    if (raf) cancelAnimationFrame(raf);
    raf = requestAnimationFrame(tick);
    return api;
  }

  function unmount() { if (raf) cancelAnimationFrame(raf); raf = null; svg = null; }

  function setState(s) {
    if (!POSES[s]) s = "idle";
    if (s !== state) { state = s; enteredAt = performance.now(); if (s === "poked") { vel.sy = -0.08; vel.sx = 0.05; } if (s === "happy") vel.bodyY = -2.5; }
  }

  function setExternal(o) { ext = o || null; }
  function gesture(name, ms) { if (!GESTURES[name]) { gest = null; return; } gest = { name, until: performance.now() + (ms || 1500), started: performance.now() }; }
  function clearGesture() { gest = null; }
  function impact(strength) { const s = Math.min(1, Math.max(0, strength)); vel.sy -= 0.12 * s; vel.sx += 0.08 * s; }
  function look(x, y) { cursor = { x, y }; }

  const lerp = (a, b, k) => a + (b - a) * k;

  function tick(now) {
    if (!svg || !svg.isConnected) { raf = null; return; }
    const t = now / 1000, age = (now - enteredAt) / 1000;
    if (gest && now > gest.until) gest = null;
    const g = gest ? GESTURES[gest.name] : null;
    const target = { ...BASE, ...POSES[state], ...(g || {}), ...(ext || {}) };
    if (state === "poked" && age > 0.16 && !g && !ext) Object.assign(target, { sx: 1, sy: 1, eyeScale: 1.1, armL: -20, armR: -20 });

    // blink
    if (now > blinkAt && state !== "sleepy" && !target.happyEyes) { blinkUntil = now + 110; blinkAt = now + 2600 + Math.random() * 3400; }
    if (now < blinkUntil) target.eyeOpen = 0.02;

    // easing toward pose; springs for squash + hop
    for (const k of NUMERIC) {
      if (k === "sx" || k === "sy" || k === "bodyY") continue;
      cur[k] = lerp(cur[k], target[k], k === "eyeOpen" ? 0.45 : k === "legL" || k === "legR" ? 0.3 : 0.14);
    }
    for (const k of ["sx", "sy", "bodyY"]) { vel[k] += (target[k] - cur[k]) * 0.22; vel[k] *= 0.72; cur[k] += vel[k]; }
    cur.sx = Math.min(1.3, Math.max(0.7, cur.sx)); cur.sy = Math.min(1.3, Math.max(0.7, cur.sy));
    cur.mouth = target.mouth;

    // procedural motion layered on top
    const m = REDUCED ? 0 : 1;
    let bodyY = cur.bodyY, headRot = cur.headRot, headY = cur.headY, armL = cur.armL, armR = cur.armR, bodyRot = cur.bodyRot;
    let legL = cur.legL, legR = cur.legR, pupilX = cur.pupilX, pupilY = cur.pupilY, sx = cur.sx, sy = cur.sy, glow = cur.glow, pageRot = 0;
    const phys = ext && ext.mode;
    if (!phys && !g && (state === "idle" || state === "asking")) { bodyY += Math.sin(t * 1.7) * 1.4 * m; headRot += Math.sin(t * 0.8) * 1.6 * m; armL += Math.sin(t * 1.7) * 2.5 * m; armR -= Math.sin(t * 1.7) * 2.5 * m; }
    if (!phys && state === "asking") armR += Math.sin(t * 5.5) * 9 * m;
    if (!phys && state === "reading") { pupilX += Math.sin(t * 4.2) * 3 * m; pageRot = Math.sin(t * 2.1) * 3 * m; headRot += Math.sin(t * 2.1) * 1.2 * m; bodyY += Math.sin(t * 1.7) * 1 * m; }
    if (!phys && state === "thinking") { headRot += Math.sin(t * 2.4) * 1.5 * m; armL += Math.sin(t * 6) * 4 * m; glow = 0.55 + Math.sin(t * 5) * 0.45; }
    if (!phys && state === "happy") { const hop = age < 1.5 ? Math.abs(Math.sin(age * Math.PI * 3)) * 9 : Math.abs(Math.sin(t * 2.2)) * 2; bodyY -= hop * m; armL += Math.sin(t * 11) * 16 * m; armR -= Math.sin(t * 11) * 16 * m; }
    if (!phys && state === "confused") { headRot += Math.sin(t * 1.4) * 2.5 * m; armL += Math.sin(t * 2.5) * 5 * m; armR -= Math.sin(t * 2.5) * 5 * m; }
    if (!phys && state === "sleepy") { bodyY += Math.sin(t * 0.9) * 1.8 * m; headRot += Math.sin(t * 0.9) * 1.2 * m; }
    if (g) {
      const ga = (now - gest.started) / 1000;
      if (gest.name === "scratch") armR += Math.sin(ga * 14) * 6 * m;
      if (gest.name === "tap") { legL += Math.max(0, Math.sin(ga * 9)) * -10 * m; bodyY += Math.max(0, Math.sin(ga * 9)) * -1 * m; }
      if (gest.name === "giggle") { bodyRot += Math.sin(ga * 16) * 4 * m; bodyY += Math.abs(Math.sin(ga * 16)) * -2 * m; }
      if (gest.name === "stretch") { headRot += Math.sin(ga * 2) * 3 * m; }
      if (gest.name === "check") { headRot += Math.sin(ga * 3) * 3 * m; }
      if (gest.name === "pet") { headRot += Math.sin(ga * 3) * 4 * m; bodyY += Math.sin(ga * 6) * -1.2 * m; }
      if (gest.name === "annoyed") { headRot += Math.sin(ga * 8) * 1.5 * m; }
      if (gest.name === "wave") { armR += Math.sin(ga * 9) * 18 * m; }
      if (gest.name === "dazed") { headRot += Math.sin(ga * 3) * 5 * m; }
    }
    if (cur.spin > 0.05) { pupilX += Math.cos(t * 13) * 3.2 * cur.spin; pupilY += Math.sin(t * 13) * 3.2 * cur.spin; }
    if (ext) {
      if (ext.mode === "walk") { const ph = ext.phase || 0; legL += Math.sin(ph) * 16; legR -= Math.sin(ph) * 16; bodyY += Math.abs(Math.cos(ph)) * -2.5; armL += Math.sin(ph) * -14; armR += Math.sin(ph) * 14; headRot += Math.sin(ph) * 1.5; }
      if (ext.mode === "held") { const sw = ext.swing || 0; legL += sw + Math.sin(t * 3.1) * 7; legR += sw + Math.sin(t * 3.1 + 0.8) * 7; armL += sw * 0.8 + 18 + Math.sin(t * 2.7) * 6; armR += -sw * 0.8 - 18 - Math.sin(t * 2.7 + 1) * 6; }
      if (ext.mode === "fly") { armL += -110 + Math.sin(t * 15) * 25; armR += 110 - Math.sin(t * 15) * 25; legL += Math.sin(t * 12) * 14; legR -= Math.sin(t * 12) * 14; }
    }

    // look at cursor
    if (cur.look > 0.05 && cursor && svg) {
      const r = svg.getBoundingClientRect();
      if (r.width) {
        const cx = r.left + r.width * 0.5, cy = r.top + r.height * 0.33;
        let dx = cursor.x - cx, dy = cursor.y - cy;
        const len = Math.hypot(dx, dy) || 1, mag = Math.min(3.2, len / 60);
        pupilX += dx / len * mag * cur.look; pupilY += dy / len * mag * cur.look;
        headRot += dx / len * Math.min(1, len / 300) * 3 * cur.look * m;
      }
    }

    // apply
    el.rig.setAttribute("transform", `translate(80 168) scale(${sx.toFixed(3)} ${sy.toFixed(3)}) translate(-80 -168)`);
    el.body.setAttribute("transform", `translate(0 ${bodyY.toFixed(2)}) translate(80 144) rotate(${bodyRot.toFixed(2)}) translate(-80 -144)`);
    el.head.setAttribute("transform", `translate(0 ${headY.toFixed(2)}) translate(80 90) rotate(${headRot.toFixed(2)}) translate(-80 -90)`);
    el.armL.setAttribute("transform", `translate(49.5 104) rotate(${(-armL).toFixed(2)}) translate(-49.5 -104)`);
    el.armR.setAttribute("transform", `translate(110.5 104) rotate(${armR.toFixed(2)}) translate(-110.5 -104)`);
    el.legL.setAttribute("transform", `translate(68 142) rotate(${legL.toFixed(2)}) translate(-68 -142)`);
    el.legR.setAttribute("transform", `translate(92 142) rotate(${legR.toFixed(2)}) translate(-92 -142)`);
    const eo = Math.max(0.02, Math.min(1, cur.eyeOpen)) * cur.eyeScale, es = cur.eyeScale;
    el.eyeL.setAttribute("transform", `translate(64 61) scale(${es.toFixed(3)} ${eo.toFixed(3)}) translate(-64 -61)`);
    el.eyeR.setAttribute("transform", `translate(96 61) scale(${es.toFixed(3)} ${eo.toFixed(3)}) translate(-96 -61)`);
    el.pupils.forEach(p => p.setAttribute("transform", `translate(${pupilX.toFixed(2)} ${pupilY.toFixed(2)})`));
    el.browL.setAttribute("transform", `translate(0 ${cur.browY.toFixed(2)}) translate(64 48) rotate(${cur.browL.toFixed(2)}) translate(-64 -48)`);
    el.browR.setAttribute("transform", `translate(0 ${cur.browY.toFixed(2)}) translate(96 48) rotate(${cur.browR.toFixed(2)}) translate(-96 -48)`);
    el.glow.style.opacity = (glow * 0.85).toFixed(3);
    el.ball.style.opacity = (0.55 + glow * 0.45).toFixed(3);
    el.cheeks.forEach(c => c.style.opacity = cur.cheeks.toFixed(3));
    el.page.style.opacity = cur.page.toFixed(3);
    el.page.setAttribute("transform", `translate(108 132) rotate(${pageRot.toFixed(2)}) translate(-108 -132)`);
    el.dots.style.opacity = cur.dots.toFixed(3);
    el.dots.querySelectorAll("circle").forEach((c, i) => c.style.opacity = (0.35 + 0.65 * Math.max(0, Math.sin(t * 3 - i * 0.9))).toFixed(3));
    el.q.style.opacity = cur.q.toFixed(3);
    el.q.setAttribute("transform", `translate(0 ${(Math.sin(t * 2) * 2 * m).toFixed(2)})`);
    el.zzz.style.opacity = cur.zzz.toFixed(3);
    el.zs.forEach((z, i) => { const ph = (t * 0.6 + i * 0.33) % 1; z.style.opacity = (Math.sin(ph * Math.PI)).toFixed(3); z.setAttribute("transform", `translate(${(ph * 6).toFixed(2)} ${(-ph * 10).toFixed(2)})`); });
    el.leds.forEach((l, i) => l.style.opacity = (0.35 + 0.65 * Math.max(0, Math.sin(t * cur.ledRate * 2 + i * 2.1))).toFixed(3));
    const lift = Math.max(0, -bodyY) + (ext && ext.lift ? ext.lift : 0);
    el.shadow.setAttribute("transform", `translate(80 174) scale(${Math.max(0.3, 1 - lift * 0.03).toFixed(3)} 1) translate(-80 -174)`);
    el.shadow.style.opacity = Math.max(0, 0.35 - lift * 0.012).toFixed(3);
    svg.classList.toggle("eyes-happy", cur.happyEyes > 0.5);
    if (cur.mouth !== mouthClass) { mouthClass = cur.mouth; svg.setAttribute("data-mouth", mouthClass); }
    raf = requestAnimationFrame(tick);
  }

  const api = { mount, unmount, setState, setExternal, gesture, clearGesture, impact, look, markup, GESTURES, get state() { return state; }, get gesture_() { return gest && gest.name; } };
  return api;
})();
window.Robot = Robot;

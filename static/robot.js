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

  let svg, host = null, el = {}, cur = { ...BASE }, vel = { sx: 0, sy: 0, bodyY: 0 }, state = "idle", enteredAt = 0, raf = null;
  let cursor = null, blinkAt = 0, blinkUntil = 0, mouthClass = "", ext = null, gest = null;
  let skin = (() => { try { return localStorage.getItem("dot-skin") || "classic"; } catch (e) { return "classic"; } })();

  const DEFS = `
  <defs>
    <linearGradient id="rb-metal" x1="0" y1="0" x2="0" y2="1"><stop offset="0" class="m1"/><stop offset="1" class="m2"/></linearGradient>
    <linearGradient id="rb-metal2" x1="0" y1="0" x2="1" y2="1"><stop offset="0" class="m1"/><stop offset="1" class="m2"/></linearGradient>
    <linearGradient id="rb-screen" x1="0" y1="0" x2="0" y2="1"><stop offset="0" class="sc1"/><stop offset="1" class="sc2"/></linearGradient>
    <radialGradient id="rb-glow"><stop offset="0" class="g1"/><stop offset="1" class="g2"/></radialGradient>
    <radialGradient id="rb-eye"><stop offset="0" class="e1"/><stop offset="1" class="e2"/></radialGradient>
  </defs>
  <ellipse class="shadow" cx="80" cy="174" rx="36" ry="6"/>`;

  const FX = `
    <g class="fx">
      <g class="dots"><circle cx="122" cy="30" r="2.5"/><circle cx="131" cy="21" r="3.5"/><circle cx="142" cy="10" r="4.5"/></g>
      <text class="qmark" x="124" y="34">?</text>
      <g class="zzz"><text class="z z1" x="120" y="34">z</text><text class="z z2" x="130" y="22">z</text><text class="z z3" x="141" y="10">z</text></g>
    </g>`;

  function markupClassic() {
    return `
<svg class="bot robot" viewBox="0 0 160 184" aria-hidden="true">${DEFS}
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
${FX}
  </g>
</svg>`;
  }

  function markupIronman() {
    return `
<svg class="bot robot" viewBox="0 0 160 184" aria-hidden="true">${DEFS}
  <g class="rig">
    <g class="legs">
      <g class="leg-l"><path class="ol" d="M59.60 142.15L61.77 142.42L63.66 144.31L64.47 143.77L67.98 144.04L70.68 144.85L72.84 146.74L73.92 145.93L75.27 146.20L79.32 149.71L79.05 154.30L77.70 155.92L78.51 157.01L78.51 159.71L77.43 161.06L78.24 162.14L78.24 163.76L75.81 166.19L73.38 166.73L60.69 167.00L58.52 166.19L56.09 163.76L56.09 162.41L57.98 160.52L57.71 156.46L58.79 155.11L57.98 154.30L57.71 152.14L57.71 144.04Z"/>
        <path class="pl gold" d="M59.60 155.92L62.31 156.19L64.74 158.90L66.36 159.44L69.06 159.17L71.49 156.73L76.35 156.73L76.89 157.01L76.89 159.71L76.35 160.25L74.19 161.06L63.93 161.06L59.88 160.52L59.33 158.63Z"/>
        <path class="pl gold" d="M59.06 161.60L64.47 162.41L72.30 162.41L76.08 161.87L76.62 162.14L76.62 163.76L75.54 164.57L74.46 165.11L71.76 165.38L60.69 165.38L58.52 164.57L57.71 163.76L57.71 162.41Z"/>
        <path class="pl red" d="M59.60 143.77L61.77 144.04L62.85 145.66L63.66 148.90L63.93 152.68L63.39 153.76L62.31 154.30L59.60 154.30Z"/>
        <path class="pl red" d="M73.92 147.55L75.27 147.82L77.70 149.71L77.43 154.30L76.35 155.38L75.00 155.38L72.30 155.38L70.95 154.30L70.95 152.68L71.76 150.52L72.57 148.90Z"/>
        <path class="pl red" d="M64.47 145.39L67.98 145.66L71.22 146.74L71.76 147.55L70.41 150.25L69.33 151.60L66.09 151.33L64.74 148.90L64.20 146.74Z"/>
        <path class="pl red" d="M66.09 152.41L68.79 152.95L70.41 155.11L69.87 157.55L69.06 158.36L67.98 158.63L66.09 158.63L64.74 158.09L63.66 156.19L63.66 154.84L64.47 153.49Z"/>
      </g>
      <g class="leg-r"><path class="ol" d="M100.67 141.61L102.56 141.88L104.18 143.50L104.45 152.95L103.37 154.84L104.45 155.92L104.18 159.98L106.07 161.87L106.34 163.22L103.91 165.65L102.56 166.19L97.96 166.73L90.94 166.73L86.62 166.19L84.19 163.49L84.19 161.87L85.00 161.06L83.92 159.98L83.65 157.28L84.73 155.92L83.11 153.76L82.84 149.71L85.00 147.28L87.43 145.93L89.32 146.20L90.94 144.58L96.07 143.23L97.69 143.50L98.23 144.04Z"/>
        <path class="pl gold" d="M100.94 155.38L102.83 155.92L102.83 159.44L102.02 159.98L96.07 161.06L87.70 160.79L85.54 159.98L85.27 157.28L85.81 156.73L90.67 156.73L93.10 158.63L95.53 159.17L97.42 158.63L99.85 155.92Z"/>
        <path class="pl gold" d="M101.21 161.06L103.91 161.33L104.72 162.41L104.72 163.22L102.56 164.57L97.96 165.11L89.05 165.11L86.62 164.57L85.81 163.49L85.81 161.87L96.61 162.14Z"/>
        <path class="pl red" d="M87.43 147.55L89.32 148.09L91.48 152.68L91.21 154.30L90.40 155.11L88.24 155.38L85.81 155.38L85.00 154.57L84.46 152.14L84.73 149.17Z"/>
        <path class="pl red" d="M100.67 143.23L102.56 143.50L102.83 152.95L102.56 153.76L101.75 154.03L99.31 153.76L98.23 152.14L98.77 147.28L99.31 145.39Z"/>
        <path class="pl red" d="M96.07 144.85L97.69 145.12L97.69 146.74L96.61 150.25L95.53 151.33L93.10 151.33L91.75 150.52L90.40 146.74L90.94 146.20Z"/>
        <path class="pl red" d="M94.18 152.14L97.15 152.68L98.50 154.57L98.23 156.73L96.34 158.09L93.64 158.09L91.48 155.38L92.02 154.03Z"/>
      </g>
    </g>
    <g class="body">
      <g class="arm arm-l"><path class="ol" d="M60.96 98.93L61.77 99.20L63.66 101.63L63.66 107.57L62.85 110.81L61.23 112.43L61.77 113.24L61.77 116.21L60.15 123.24L58.79 126.48L56.90 128.37L57.44 129.72L55.01 139.99L53.39 142.15L54.20 143.50L51.23 146.47L45.56 147.01L41.24 146.20L38.53 144.85L35.29 141.88L34.48 139.45L35.83 137.83L35.29 136.74L35.83 133.23L40.16 123.51L41.24 121.62L44.21 118.65L44.48 117.03L47.18 112.70L51.23 108.65L52.04 107.03L59.06 100.01Z"/>
        <path class="pl red" d="M50.96 110.54L52.85 110.81L56.09 112.43L60.15 113.24L60.15 116.21L59.06 121.35L56.63 127.02L53.93 127.02L50.69 125.94L47.72 124.59L46.10 122.97L46.10 117.03L48.80 112.70Z"/>
        <path class="pl red" d="M50.15 127.02L54.20 128.10L55.28 128.64L55.82 129.72L52.85 141.07L48.80 141.07L42.86 139.99L41.24 138.91L41.24 137.83L42.59 134.04L43.94 133.23L45.56 132.96L47.45 131.07L49.07 127.83Z"/>
        <path class="pl red" d="M43.94 120.54L44.48 121.08L45.02 123.51L47.99 126.21L47.99 127.83L45.83 131.88L43.13 132.69L41.51 134.04L40.16 137.83L38.53 138.10L37.45 137.56L36.91 136.74L36.91 135.12L40.43 126.21L42.86 121.62Z"/>
        <path class="pl red" d="M60.96 100.55L61.77 100.82L62.04 101.63L62.04 107.57L61.50 110.00L60.69 111.35L57.71 111.35L53.39 109.73L52.85 109.19L52.85 108.38L53.66 107.03L59.06 101.63Z"/>
        <path class="pl gold" d="M36.64 138.64L44.75 141.61L52.04 142.69L52.58 143.50L51.23 144.85L48.53 145.39L44.21 145.39L41.24 144.58L36.91 141.88L36.10 139.99Z"/>
      </g>
      <g class="arm arm-r"><path class="ol" d="M99.85 98.39L101.21 98.93L105.26 102.44L108.50 105.68L109.85 108.11L110.66 108.38L114.44 112.43L116.87 115.94L117.14 118.11L118.22 118.65L121.20 122.16L126.06 132.69L126.60 135.39L125.79 136.47L127.41 138.10L126.87 140.26L122.82 144.04L119.84 145.39L117.14 145.93L110.93 145.93L110.12 145.66L107.69 142.96L108.77 141.61L107.15 139.99L104.45 130.53L104.45 128.37L104.99 127.83L102.02 124.32L99.31 114.05L99.31 112.97L100.12 112.16L98.50 110.27L97.42 106.49L97.42 101.09Z"/>
        <path class="pl red" d="M109.58 109.73L111.20 110.54L114.98 115.40L115.52 116.76L115.52 120.81L114.98 122.43L113.36 124.05L108.77 125.94L106.07 126.48L105.26 126.48L103.64 124.32L101.75 118.11L100.94 112.97L106.34 111.35Z"/>
        <path class="pl red" d="M110.39 126.48L112.28 126.75L114.71 131.07L116.33 132.15L118.49 132.69L120.11 135.12L120.11 138.37L114.44 139.99L112.55 140.53L109.31 140.53L108.77 139.99L106.07 130.53L106.07 128.37Z"/>
        <path class="pl red" d="M117.41 120.00L118.22 120.27L119.57 122.16L123.63 130.53L124.98 134.58L124.98 135.39L123.90 136.74L122.55 137.29L121.74 136.74L120.39 133.50L119.03 132.15L115.79 130.80L114.71 129.72L113.63 127.02L113.63 125.13L115.79 123.78Z"/>
        <path class="pl red" d="M99.85 100.01L101.21 100.55L105.26 104.06L108.23 107.57L107.96 108.92L104.18 110.54L100.67 111.08L100.12 110.27L98.77 104.60L99.04 101.09Z"/>
        <path class="pl gold" d="M124.17 137.83L125.79 138.10L125.79 139.18L125.25 140.26L122.82 142.42L119.03 144.04L115.52 144.58L111.47 144.31L109.58 143.50L109.31 142.96L109.85 142.15L117.68 140.53Z"/>
        <g class="page"><rect x="102.6" y="118.8" width="30" height="38" rx="3"/><path d="M108.6 129.8h18M108.6 136.8h18M108.6 143.8h12"/></g>
      </g>
      <path class="ol" d="M73.65 92.98L91.48 93.25L93.64 95.41L94.72 97.58L94.72 100.55L96.34 100.82L98.23 102.71L98.23 103.25L96.61 104.87L99.04 107.57L99.58 110.27L98.77 112.16L100.40 113.78L102.29 120.81L102.56 124.32L101.75 125.40L103.10 126.75L103.37 128.10L103.37 130.26L102.29 131.61L103.64 133.23L103.91 140.53L103.37 141.61L100.67 143.77L91.75 145.66L87.70 147.55L84.46 149.44L77.70 149.44L70.68 146.20L60.96 144.04L59.88 143.50L57.98 141.34L57.98 134.58L58.25 133.23L59.33 132.15L58.25 130.80L58.25 128.10L58.52 127.02L59.60 125.94L59.06 124.86L59.60 119.46L60.69 114.86L62.58 112.70L61.77 111.08L62.04 108.92L62.85 106.76L64.20 105.41L62.85 103.25L65.01 100.82L66.36 100.82L66.09 98.93L66.63 97.31L69.33 93.79Z"/>
      <path class="pl gold" d="M73.65 103.52L88.78 103.79L90.40 105.41L95.53 105.95L97.15 107.03L97.96 110.00L97.42 111.62L91.48 119.73L89.86 121.35L87.43 122.70L83.92 124.05L77.43 124.05L75.00 123.51L71.49 121.35L65.55 114.32L63.39 111.08L64.47 106.76L71.49 105.41L72.30 103.79Z"/>
      <path class="pl red" d="M99.31 132.42L101.75 132.69L102.02 133.23L102.29 140.53L101.75 141.61L99.85 142.42L91.75 144.04L88.24 145.39L84.46 147.82L77.70 147.82L70.68 144.58L62.04 142.69L59.88 141.88L59.33 139.72L59.88 133.23L60.96 132.69L67.44 134.04L71.22 135.39L73.38 138.10L77.16 141.34L82.57 141.88L85.81 140.53L90.67 135.12Z"/>
      <path class="pl gold" d="M73.65 94.60L91.48 94.87L93.10 97.58L93.37 100.01L92.02 100.82L87.43 101.36L79.05 101.63L68.79 101.09L67.71 100.55L67.71 98.93L69.33 95.41Z"/>
      <path class="pl gold" d="M86.62 124.59L88.51 125.13L88.78 128.37L87.70 129.45L82.30 130.53L79.05 130.53L75.00 129.72L74.19 129.72L73.11 128.91L73.38 124.86L80.95 125.67L84.19 125.40Z"/>
      <path class="pl gold" d="M87.70 129.99L88.78 130.26L89.05 131.07L89.05 133.23L87.97 134.58L82.84 135.66L77.97 135.66L74.19 134.85L73.38 134.58L72.57 133.50L72.57 131.88L73.38 130.26L77.97 131.07L83.11 131.07Z"/>
      <path class="pl red" d="M98.23 113.24L98.77 113.78L100.12 118.38L100.94 124.32L98.50 126.75L97.42 127.02L96.88 127.02L95.80 125.67L93.37 119.46L94.99 116.76Z"/>
      <path class="pl red" d="M62.85 114.05L63.93 114.32L65.28 115.67L67.98 120.00L66.09 125.40L65.28 127.02L64.47 127.56L61.77 126.21L60.69 124.86L61.23 119.46L62.04 115.67Z"/>
      <path class="pl gold" d="M74.46 135.66L77.97 136.47L83.38 136.47L85.00 135.93L87.70 135.93L87.43 137.29L85.27 139.45L83.65 140.26L78.51 140.53L76.35 139.45L74.73 137.83L74.19 136.74Z"/>
      <path class="pl red" d="M60.42 126.75L61.50 127.02L67.98 131.07L69.06 131.07L70.14 129.45L71.49 128.64L71.49 132.96L70.95 133.77L69.87 133.77L60.15 131.07L59.88 128.10Z"/>
      <path class="pl red" d="M100.40 126.48L101.48 126.75L101.75 128.10L101.75 130.26L101.21 130.80L90.94 133.50L90.40 133.23L90.67 128.37L92.83 130.80L93.64 130.80Z"/>
      <path class="pl gold" d="M91.75 121.35L93.10 121.89L95.53 127.02L95.53 128.64L94.45 129.45L93.37 129.45L91.75 127.83L89.59 124.05L90.13 122.70Z"/>
      <path class="pl gold" d="M69.06 121.62L70.14 121.89L71.49 123.24L71.76 124.32L69.60 128.64L68.52 129.72L67.98 129.72L65.82 128.91L65.82 128.37L66.90 125.40Z"/>
      <path class="pl gold" d="M65.01 102.44L67.17 102.71L68.79 103.52L68.52 104.06L67.98 104.06L65.01 104.33L64.47 103.79Z"/>
      <path class="pl gold" d="M94.72 102.17L96.34 102.44L96.61 103.25L96.07 103.79L94.18 104.06L92.56 103.79L92.02 103.25Z"/>
      <circle class="antenna-glow" cx="80.7" cy="113.5" r="10.8"/>
      <path class="antenna-ball" d="M79.32 108.11L82.57 108.38L84.19 109.19L86.08 111.89L86.08 114.86L85.27 116.76L83.38 118.38L82.30 118.65L79.05 118.92L77.43 118.11L76.08 116.76L75.27 114.86L75.27 112.97L76.08 110.54L77.70 108.92Z"/>
      <g class="head">
        <path class="ol" d="M74.19 6.00L87.97 6.27L99.04 7.89L104.99 9.78L110.93 13.83L118.22 21.94L122.55 29.77L125.25 37.88L126.06 45.98L126.06 51.11L127.95 51.11L129.84 53.00L130.38 54.62L130.11 65.43L128.76 74.61L127.41 78.94L123.63 82.99L122.28 83.26L120.93 81.91L117.95 87.31L113.63 91.63L104.18 97.31L103.10 97.31L102.29 96.49L99.85 99.20L97.15 100.55L96.07 100.55L93.64 98.12L91.75 94.60L85.54 94.33L74.73 94.33L69.06 94.87L67.44 98.66L65.01 100.82L63.66 100.82L61.77 100.01L59.06 97.31L57.98 98.12L56.63 97.85L48.80 93.52L45.02 90.55L42.05 87.31L39.89 83.26L37.99 84.61L36.64 84.07L34.21 81.64L31.78 75.96L30.16 66.78L29.62 60.84L29.62 57.33L30.16 54.62L32.59 51.92L33.67 52.73L33.94 52.46L33.94 42.20L35.29 35.98L37.99 28.42L42.05 21.67L49.34 13.83L52.85 11.13L57.98 8.97L62.04 7.89Z"/>
        <path class="pl gold" d="M97.42 23.56L105.26 25.45L112.28 28.15L115.25 29.77L116.87 31.93L119.30 44.36L119.84 50.30L119.84 57.60L118.76 66.51L117.14 72.72L115.79 75.96L112.28 78.67L107.15 81.64L105.53 83.26L100.40 96.77L99.85 97.58L97.15 98.93L96.07 98.93L95.26 98.12L93.10 93.52L92.29 92.98L74.73 92.71L68.25 93.52L66.63 96.22L65.82 98.66L65.01 99.20L63.66 99.20L61.77 98.39L60.69 97.31L57.71 90.01L55.01 83.80L53.93 82.72L44.48 76.78L41.78 68.40L40.43 58.95L40.43 47.06L41.24 39.77L43.40 31.66L45.29 30.04L50.15 27.61L57.71 24.91L62.85 24.10L63.93 24.91L65.01 27.07L71.49 43.28L72.84 45.71L75.00 46.25L86.08 45.98L86.89 45.71L87.97 44.36L94.99 25.45L96.07 24.10Z"/>
        <path class="pl red" d="M74.19 7.62L87.97 7.89L92.83 8.43L99.04 9.51L104.99 11.40L109.31 14.10L114.44 19.24L117.68 23.56L120.93 29.77L123.63 37.88L124.44 45.98L124.17 62.19L122.01 74.34L119.57 81.37L116.33 87.31L112.55 90.82L104.18 95.68L103.10 95.68L102.83 94.33L106.88 83.53L117.14 76.51L118.22 74.61L119.84 68.94L121.47 57.33L121.47 50.30L120.66 42.47L118.76 33.01L117.14 29.77L114.17 27.61L104.45 23.83L96.88 21.94L95.53 22.21L94.18 23.83L92.29 28.96L91.21 30.58L85.00 30.58L77.97 30.31L68.52 31.12L64.47 23.29L63.66 22.48L62.31 22.48L57.44 23.56L50.42 25.99L44.75 28.69L42.05 30.85L40.70 34.09L38.80 47.60L38.80 59.76L40.16 68.67L42.05 74.88L43.67 77.59L47.99 80.83L53.93 84.34L57.17 91.90L58.25 96.22L56.63 96.22L46.91 90.55L43.67 87.31L40.43 81.10L36.91 68.94L35.56 58.14L35.56 42.20L37.45 34.09L39.61 28.42L42.32 23.56L44.75 20.32L49.34 15.45L52.85 12.75L57.98 10.59L62.04 9.51Z"/>
        <path class="pl gold" d="M74.19 31.66L90.13 32.20L90.13 34.09L87.16 42.74L85.54 44.63L73.65 44.63L70.41 37.07L69.33 32.74L70.95 31.93Z"/>
        <path class="pl dark" d="M32.59 53.54L33.40 54.35L33.94 61.92L35.29 70.29L38.80 82.45L37.99 82.99L36.64 82.45L35.29 80.83L33.40 75.96L32.59 72.18L31.24 60.84L31.51 55.70Z"/>
        <path class="pl dark" d="M126.87 52.46L128.22 53.00L128.76 54.62L128.76 61.11L127.95 70.29L125.79 78.94L123.36 81.37L122.28 81.64L122.01 80.83L123.90 74.61L125.52 66.78L126.33 60.03L126.33 53.54Z"/>
        <g class="eyes">
          <g class="eye eye-l"><path class="eyeball" d="M46.37 64.08L49.07 64.35L60.42 67.32L69.06 68.67L69.87 69.21L69.87 69.75L67.44 71.91L65.28 72.72L60.15 73.53L54.47 73.53L50.42 72.45L47.45 70.83L45.83 68.94L45.56 66.24Z"/><ellipse class="pupil" cx="57.7" cy="68.8" rx="4.1" ry="2.8"/><path class="eye-happy" d="M46.6 73.5 Q57.7 61.1 68.9 68.8"/></g>
          <g class="eye eye-r"><path class="eyeball" d="M112.28 63.27L114.44 63.81L114.71 67.32L113.63 69.48L112.01 70.83L109.85 71.91L105.80 72.99L99.04 72.99L94.72 72.18L92.02 71.10L90.40 69.48L90.67 68.40L100.67 66.78Z"/><ellipse class="pupil" cx="102.6" cy="68.1" rx="4.1" ry="2.9"/><path class="eye-happy" d="M91.4 73.0 Q102.6 60.3 113.7 68.1"/></g>
        </g>
        <line class="brow brow-l" x1="46.6" y1="65.6" x2="68.9" y2="64.6"/>
        <line class="brow brow-r" x1="91.4" y1="64.8" x2="113.7" y2="63.8"/>
      </g>
    </g>${FX}
  </g>
</svg>`;
  }

  const SKIN_MARKUP = { classic: markupClassic, ironman: markupIronman };

  const BASE_PIVOTS = { rig: [80, 168], body: [80, 144], head: [80, 90], armL: [49.5, 104], armR: [110.5, 104],
                        legL: [68, 142], legR: [92, 142], eyeL: [64, 61], eyeR: [96, 61], browL: [64, 48], browR: [96, 48],
                        page: [108, 132], shadow: [80, 174] };
  const PIVOTS = {
    classic: BASE_PIVOTS,
    ironman: { rig: [80, 168], body: [80, 138], head: [80, 97.2], armL: [49.1, 103.5], armR: [112.3, 103.0], legL: [67.7, 145.8], legR: [94.6, 145.2], eyeL: [57.7, 68.8], eyeR: [102.6, 68.1], browL: [57.7, 59.1], browR: [102.6, 58.3], page: [117.6, 137.8], shadow: [80, 174] },
  };
  let P = BASE_PIVOTS;

  function markup() {
    return (SKIN_MARKUP[skin] || markupClassic)();
  }

  const REQUIRED = [".rig", ".body", ".head", ".arm-l", ".arm-r", ".leg-l", ".leg-r", ".eye-l", ".eye-r",
                    ".brow-l", ".brow-r", ".antenna-glow", ".antenna-ball", ".page", ".dots", ".qmark",
                    ".zzz", ".shadow"];

  function render() {
    host.innerHTML = markup();
    svg = host.querySelector("svg.robot");
    const missing = REQUIRED.filter(s => !svg.querySelector(s));
    if (missing.length) {
      console.warn("Robot skin", skin, "is missing", missing.join(" "), "- falling back to classic");
      skin = "classic";
      host.innerHTML = markupClassic();
      svg = host.querySelector("svg.robot");
    }
    const q = s => svg.querySelector(s);
    el = { rig: q(".rig"), body: q(".body"), head: q(".head"), armL: q(".arm-l"), armR: q(".arm-r"), legL: q(".leg-l"), legR: q(".leg-r"),
           eyeL: q(".eye-l"), eyeR: q(".eye-r"), pupils: svg.querySelectorAll(".pupil, .spark"), browL: q(".brow-l"), browR: q(".brow-r"),
           glow: q(".antenna-glow"), ball: q(".antenna-ball"), cheeks: svg.querySelectorAll(".cheek"), page: q(".page"), dots: q(".dots"),
           q: q(".qmark"), zzz: q(".zzz"), zs: svg.querySelectorAll(".z"), shadow: q(".shadow"), leds: svg.querySelectorAll(".led") };
    P = PIVOTS[skin] || BASE_PIVOTS;
    svg.dataset.skin = skin;
    svg.setAttribute("data-mouth", mouthClass || cur.mouth);
    svg.classList.toggle("eyes-happy", cur.happyEyes > 0.5);
  }

  function mount(container) {
    host = container;
    cur = { ...BASE }; vel = { sx: 0, sy: 0, bodyY: 0 };
    render();
    blinkAt = performance.now() + 2500 + Math.random() * 3000;
    if (raf) cancelAnimationFrame(raf);
    raf = requestAnimationFrame(tick);
    return api;
  }

  function unmount() { if (raf) cancelAnimationFrame(raf); raf = null; svg = null; host = null; }

  const SKINS = ["classic", "ironman"];

  function setSkin(name) {
    if (!SKINS.includes(name)) name = "classic";
    skin = name;
    if (host) render();
    try { localStorage.setItem("dot-skin", skin); } catch (e) {}
    return skin;
  }

  function nextSkin() {
    return setSkin(SKINS[(SKINS.indexOf(skin) + 1) % SKINS.length]);
  }

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
    const pv = (n, t) => `translate(${P[n][0]} ${P[n][1]}) ${t} translate(${-P[n][0]} ${-P[n][1]})`;
    el.rig.setAttribute("transform", pv("rig", `scale(${sx.toFixed(3)} ${sy.toFixed(3)})`));
    el.body.setAttribute("transform", `translate(0 ${bodyY.toFixed(2)}) ` + pv("body", `rotate(${bodyRot.toFixed(2)})`));
    el.head.setAttribute("transform", `translate(0 ${headY.toFixed(2)}) ` + pv("head", `rotate(${headRot.toFixed(2)})`));
    el.armL.setAttribute("transform", pv("armL", `rotate(${(-armL).toFixed(2)})`));
    el.armR.setAttribute("transform", pv("armR", `rotate(${armR.toFixed(2)})`));
    el.legL.setAttribute("transform", pv("legL", `rotate(${legL.toFixed(2)})`));
    el.legR.setAttribute("transform", pv("legR", `rotate(${legR.toFixed(2)})`));
    const eo = Math.max(0.02, Math.min(1, cur.eyeOpen)) * cur.eyeScale, es = cur.eyeScale;
    el.eyeL.setAttribute("transform", pv("eyeL", `scale(${es.toFixed(3)} ${eo.toFixed(3)})`));
    el.eyeR.setAttribute("transform", pv("eyeR", `scale(${es.toFixed(3)} ${eo.toFixed(3)})`));
    el.pupils.forEach(p => p.setAttribute("transform", `translate(${pupilX.toFixed(2)} ${pupilY.toFixed(2)})`));
    el.browL.setAttribute("transform", `translate(0 ${cur.browY.toFixed(2)}) ` + pv("browL", `rotate(${cur.browL.toFixed(2)})`));
    el.browR.setAttribute("transform", `translate(0 ${cur.browY.toFixed(2)}) ` + pv("browR", `rotate(${cur.browR.toFixed(2)})`));
    el.glow.style.opacity = (glow * 0.85).toFixed(3);
    el.ball.style.opacity = (0.55 + glow * 0.45).toFixed(3);
    el.cheeks.forEach(c => c.style.opacity = cur.cheeks.toFixed(3));
    el.page.style.opacity = cur.page.toFixed(3);
    el.page.setAttribute("transform", pv("page", `rotate(${pageRot.toFixed(2)})`));
    el.dots.style.opacity = cur.dots.toFixed(3);
    el.dots.querySelectorAll("circle").forEach((c, i) => c.style.opacity = (0.35 + 0.65 * Math.max(0, Math.sin(t * 3 - i * 0.9))).toFixed(3));
    el.q.style.opacity = cur.q.toFixed(3);
    el.q.setAttribute("transform", `translate(0 ${(Math.sin(t * 2) * 2 * m).toFixed(2)})`);
    el.zzz.style.opacity = cur.zzz.toFixed(3);
    el.zs.forEach((z, i) => { const ph = (t * 0.6 + i * 0.33) % 1; z.style.opacity = (Math.sin(ph * Math.PI)).toFixed(3); z.setAttribute("transform", `translate(${(ph * 6).toFixed(2)} ${(-ph * 10).toFixed(2)})`); });
    el.leds.forEach((l, i) => l.style.opacity = (0.35 + 0.65 * Math.max(0, Math.sin(t * cur.ledRate * 2 + i * 2.1))).toFixed(3));
    const lift = Math.max(0, -bodyY) + (ext && ext.lift ? ext.lift : 0);
    el.shadow.setAttribute("transform", pv("shadow", `scale(${Math.max(0.3, 1 - lift * 0.03).toFixed(3)} 1)`));
    el.shadow.style.opacity = Math.max(0, 0.35 - lift * 0.012).toFixed(3);
    svg.classList.toggle("eyes-happy", cur.happyEyes > 0.5);
    if (cur.mouth !== mouthClass) { mouthClass = cur.mouth; svg.setAttribute("data-mouth", mouthClass); }
    raf = requestAnimationFrame(tick);
  }

  const api = { mount, unmount, setState, setExternal, gesture, clearGesture, impact, look, markup, setSkin, nextSkin, SKINS, GESTURES, get state() { return state; }, get skin() { return skin; }, get gesture_() { return gest && gest.name; } };
  return api;
})();
window.Robot = Robot;

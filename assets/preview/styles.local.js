/**
 * Camada local — entradas extras para a aba Estilo do editor.
 *
 * Loaded BEFORE app.js (which is why it only defines a global and waits). app.js
 * then calls install() with its three registries, and everything below mutates
 * them in place. That keeps the footprint inside the repo down to one guarded
 * line per file, so `git pull` has almost nothing to conflict with.
 *
 * Deliberately self-contained: no app.js helper (`el`, `clamp01`, `FPS_REF`) is
 * used, because they are module-scope consts there and reaching for them would
 * couple this file to internals upstream is free to rename. Plain DOM only.
 *
 * The palette/roles below are INJECTED from brand/avelin.json by overlay.py at
 * install time — do not edit them here, edit the brand file and re-run
 * `overlay.py apply-skill`. The accent is the exception: it reads the live
 * `var(--hl-accent)` so the preview follows the colour picker.
 */
(function () {
  const BRAND = {
  "_readme": "Brand preset — the ONE place the Avelin identity lives. Caption styles, headline styles and bespoke graphics all read from here instead of hardcoding a hex. Derived from the site design kit (SiteKit v3.1 tokens: index.html / styles/Style.css / js/index.js) so video and web share one vocabulary. To add another brand, copy this file.",
  "id": "avelin",
  "name": "Avelin",
  "default": true,
  "source": "designkit.md — SiteKit v3.1",

  "palette": {
    "_note": "Names mirror the site's :root tokens on purpose — renaming them would break the one thing this file is for, which is being the same vocabulary on both sides.",

    "accent": "#FF6B1A",
    "accentHover": "#FF8C47",
    "accentSoft": "#FFAD7A",
    "accentMist": "#FFE8D6",
    "accentDark": "#CC4E0D",

    "night": "#0D2137",
    "cardBlue": "#1C2E40",
    "blue3": "#2E4560",
    "blueMid": "#4A7FA5",
    "blueLight": "#7A95AA",
    "blueBorder": "#D4DDE5",

    "offwhite": "#F5F2EE",
    "white": "#FFFFFF",

    "_video": "Over footage the site's light-background roles invert: offwhite is the reading colour and blueLight is the dimmed one. accentSoft (#FFAD7A) is the site's accent-on-dark — hold it in reserve for a shot too dark for #FF6B1A to sit on.",
    "_webOnly": {"cardEnd": "#142A42", "waBg": "#E5DDD5", "waOut": "#E1F5D6", "online": "#22c55e"}
  },

  "fonts": {
    "_note": "The real Avelin faces, both on Google Fonts — no substitution needed and nothing licensed to ship. The serif is ALWAYS weight 400; its italic is the expressive move, not a variant.",
    "sans": {"family": "OpenSans", "regular": "400", "semibold": "600", "bold": "700"},
    "serif": {"family": "LibreBaskerville", "style": "italic", "weight": "400"}
  },

  "roles": {
    "_note": "Per-word roles for the editorial caption style. `em` multiplies captions.fontSize. This IS the site's editorial pattern moved to video: `.amber` — serif italic in orange for the emphasis — with dimmed connectives around it. Flatten the contrast and it stops being Avelin and starts being subtitles.",
    "ctx":      {"font": "sans",  "weight": "400", "color": "blueLight", "em": 0.62},
    "stress":   {"font": "sans",  "weight": "700", "color": "offwhite",  "em": 1.0},
    "serif":    {"font": "serif", "color": "offwhite", "em": 1.12},
    "serifAcc": {"font": "serif", "color": "accent",   "em": 1.12},
    "punch":    {"font": "sans",  "weight": "700", "color": "accent", "em": 1.0},
    "num":      {"font": "serif", "color": "accent", "em": 2.0}
  },

  "motion": {
    "_note": "The site keeps two motion layers separate — CSS easing/loops for hover and continuous things, GSAP+ScrollTrigger for entrances — and so does this file. In the composition both become GSAP timeline tweens; CSS transitions do not render. Durations in seconds.",

    "ease": {
      "_note": "cubic-bezier(.2,.8,.2,1) is the site's easing-mãe: every CSS transition uses it. Default to it for anything Avelin. `dec` is the overshoot-free decelerate kept for pops and clip reveals.",
      "out": [0.2, 0.8, 0.2, 1],
      "dec": [0.16, 0.84, 0.44, 1]
    },

    "_captions": "entries used by the editorial caption style",
    "fade":    {"dur": 0.34, "blur": 2, "ease": "out"},
    "serifIn": {"dur": 0.32, "scale": 0.8, "origin": "left center", "ease": "out"},
    "type":    {"dur": 0.24, "riseY": 5, "staggerPerChar": 0.045, "ease": "linear"},
    "pop":     {"dur": 0.50, "blur": 20, "scale": 0, "tracking": -0.5, "ease": "dec"},
    "glow":    {"dur": 0.42, "blur": 11, "scale": 1.05, "shadowPx": 22, "ease": "out"},
    "wordStaggerMs": 185,
    "serifStaggerMs": 230,

    "_graphics": "the site's scroll vocabulary, for CustomGraphics and b-roll. On the site these fire on scroll; in a video they fire on a cue's frame. Same shape, same feel — which is the point.",
    "reveal":     {"dur": 0.9, "y": 28, "opacity": [0, 1], "ease": "out"},
    "clip":       {"dur": 1.1, "from": "inset(0 0 100% 0)", "to": "inset(0)", "ease": "dec"},
    "splitLines": {"dur": 1.0, "yPercent": [110, 0], "stagger": 0.12, "ease": "out"},
    "splitWords": {"dur": 0.6, "yPercent": [60, 0], "stagger": 0.012, "ease": "out"},
    "parallax":   {"y": -50},
    "ringSpin":   {"outerSec": 60, "midSec": 45, "midReverse": true},
    "pulseSec":   2
  },

  "layout": {
    "_note": "The editorial block is LEFT-anchored, not centred — half of what makes it read as editorial rather than as subtitles.",
    "align": "left",
    "safeLeftPx": 90,
    "lineHeight": 1.0,
    "letterSpacing": -0.02,
    "eyebrow": {"sizePx": 11, "weight": 600, "tracking": 0.12, "uppercase": true, "color": "accent"}
  },

  "graphics": {
    "_note": "For CustomGraphics / SVG b-roll, so a card built for a video looks like a card on the site. The shadows are the signature: big Y, big blur, NEGATIVE spread, tinted night-blue rather than black.",
    "radius": {"button": 4, "card": 16, "image": 22, "sheetTop": 20, "pill": 999},
    "shadow": {
      "card":  "0 16px 40px -16px rgba(13,33,55,.25)",
      "image": "0 30px 70px -28px rgba(13,33,55,.5)",
      "mock":  "0 30px 70px -20px rgba(13,33,55,.45)"
    },
    "captionShadow": "0 6px 14px rgba(13,33,55,.72)",
    "frame": {"borderPx": 6, "borderColor": "night", "radius": 26},
    "surfaces": {"light": "offwhite", "dark": "night", "card": "cardBlue"}
  }
};

  // Exactly the site's own font link — same two faces, same weights.
  const FONTS_HREF =
    'https://fonts.googleapis.com/css2?family=Libre+Baskerville:ital,wght@0,400;1,400&family=Open+Sans:wght@400;600;700&display=swap';

  function once() {
    if (document.getElementById('avelin-local-css')) return;
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = FONTS_HREF;
    document.head.appendChild(link);

    const st = document.createElement('style');
    st.id = 'avelin-local-css';
    st.textContent = `
      .edt-cue { position:absolute; inset:0; display:flex; flex-direction:column;
                 justify-content:center; align-items:flex-start; padding-left:7%;
                 line-height:${BRAND.layout.lineHeight}; letter-spacing:${BRAND.layout.letterSpacing}em; }
      .edt-line { display:flex; align-items:baseline; white-space:pre; }
      .edt-line span { display:inline-block; transform-origin:left center;
                       filter:drop-shadow(0 3px 7px rgba(13,33,55,.72)); }
    `;
    document.head.appendChild(st);
  }

  // ctx · stress · serifAcc · punch — the four roles that carry the look. A demo
  // that shows only one of them does not show the style, it shows a font.
  const LINES = [
    [{t: 'A ', r: 'ctx'}, {t: 'sua ', r: 'ctx'}, {t: 'legenda', r: 'stress'}],
    [{t: 'com ', r: 'ctx'}, {t: 'acento', r: 'serifAcc'}],
    [{t: 'editorial', r: 'punch'}],
  ];

  const clamp01 = (n) => (n < 0 ? 0 : n > 1 ? 1 : n);
  const easeOut = (t) => 1 - Math.pow(1 - t, 3);

  function paint(sp, role, s) {
    const r = BRAND.roles[role];
    sp.style.fontFamily =
      r.font === 'serif' ? "'Libre Baskerville', Georgia, serif" : "'Open Sans', system-ui, sans-serif";
    sp.style.fontStyle = r.font === 'serif' ? 'italic' : 'normal';
    if (r.weight) sp.style.fontWeight = r.weight;
    // accent follows the live picker; every other colour comes from the brand
    sp.style.color = r.color === 'accent' ? 'var(--hl-accent)' : BRAND.palette[r.color] || r.color;
    sp.style.fontSize = `${76 * r.em * s}px`;
  }

  function buildEditorialDemo(host) {
    once();
    const s = host.clientWidth / 1080;
    host.innerHTML = '';
    const cue = document.createElement('div');
    cue.className = 'edt-cue';
    host.appendChild(cue);

    const STEP = BRAND.motion.wordStaggerMs / 1000;
    const HOLD = 1.0;
    const all = [];
    let idx = 0;
    for (const ln of LINES) {
      const row = document.createElement('div');
      row.className = 'edt-line';
      cue.appendChild(row);
      for (const w of ln) {
        const sp = document.createElement('span');
        sp.textContent = w.t;
        row.appendChild(sp);
        paint(sp, w.r, s);
        const anim = w.r === 'serifAcc' ? 'serifIn' : w.r === 'punch' ? 'glow' : 'fade';
        all.push({sp, role: w.r, anim, start: idx * STEP, dur: BRAND.motion[anim].dur});
        idx++;
      }
    }
    const exitStart = (idx - 1) * STEP + 0.4 + HOLD;
    const EXIT = 0.3;
    const cycle = exitStart + EXIT + 0.15;

    return (now) => {
      const p = now % cycle;
      const out = 1 - clamp01((p - exitStart) / EXIT);
      for (const a of all) {
        const e = easeOut(clamp01((p - a.start) / a.dur));
        a.sp.style.opacity = e * out;
        if (a.anim === 'fade') {
          a.sp.style.filter = `blur(${((1 - e) * BRAND.motion.fade.blur * s).toFixed(2)}px)`;
          a.sp.style.transform = '';
        } else if (a.anim === 'serifIn') {
          a.sp.style.filter = '';
          a.sp.style.transform = `scale(${(BRAND.motion.serifIn.scale + (1 - BRAND.motion.serifIn.scale) * e).toFixed(3)})`;
        } else {
          a.sp.style.filter = `blur(${((1 - e) * BRAND.motion.glow.blur * s).toFixed(2)}px)`;
          a.sp.style.transform = `scale(${(1 + (1 - e) * (BRAND.motion.glow.scale - 1)).toFixed(3)})`;
        }
      }
    };
  }

  window.AVELIN_LOCAL = {
    install({STYLE_CATALOG, CAP_BUILDERS, ACCENT_USERS}) {
      if (STYLE_CATALOG.captions.some((o) => o.id === 'editorial')) return;
      // after the three animated ones, before the static block
      STYLE_CATALOG.captions.splice(3, 0, {id: 'editorial', name: 'Editorial', demo: 'editorial'});
      CAP_BUILDERS.editorial = buildEditorialDemo;
      ACCENT_USERS.captions.push('editorial');
    },
  };
})();

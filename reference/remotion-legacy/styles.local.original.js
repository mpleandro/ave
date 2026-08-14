/**
 * Avelin overlay — extra entries for the edvid preview's Estilo tab.
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
  const BRAND = __BRAND__;

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

  window.EDVID_LOCAL = {
    install({STYLE_CATALOG, CAP_BUILDERS, ACCENT_USERS}) {
      if (STYLE_CATALOG.captions.some((o) => o.id === 'editorial')) return;
      // after the three animated ones, before the static block
      STYLE_CATALOG.captions.splice(3, 0, {id: 'editorial', name: 'Editorial', demo: 'editorial'});
      CAP_BUILDERS.editorial = buildEditorialDemo;
      ACCENT_USERS.captions.push('editorial');
    },
  };
})();

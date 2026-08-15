/* Editor da Avelin — interactive editing timeline.
 * IMMUTABLE app: everything per-session comes from /api/state (state.json,
 * edl.json) + /gen/* (waveform, thumbs) + /media/* (video, captions, edit-data).
 * User adjustments are POSTed to /api/save → <edit>/preview_edits.json and
 * applied by the skill (which re-renders and bumps state).
 *
 * Three interaction rules worth knowing before editing this file:
 *  - Tracks are identified by ICON only (ICON.captions/video/audio/inserts/music),
 *    painted into .tl-chip cards. LABEL_W must stay in sync with .track-label's
 *    width. The gutter masks the lanes with .track-label::before painted in
 *    --panel-bg (the panel is a solid surface for exactly this reason), pinned by
 *    native position:sticky. #gutterLine is the divider, pinned by a scroll-driven
 *    CSS timeline on `translate`. Do NOT re-drive either from a JS scroll handler
 *    or a clip-path animation — both lag a frame and the column visibly breathes
 *    while scrolling. JS only publishes --max-scroll (on zoom/resize).
 *  - Correction markers: M (or the transport button) drops an IN, the next M closes
 *    the range and opens the note editor. They ride in S.notes and ship as
 *    payload.notes on save; watch_edits.py turns each save into a chat notification.
 *  - Zoom: the slider is anchored on the needle, trackpad pinch (wheel+ctrlKey)
 *    on the pointer. Both go through applyZoom(pps, t, anchorX) — never on scroll 0.
 *  - Layout follows the SOURCE aspect: portrait clips get body.portrait (player
 *    right at full column height, transport+timeline left), landscape keeps the
 *    stacked layout. #stage keeps the split from swallowing anything below it.
 *  - Timecode relies on the UI face having TABULAR figures (Inter does). With a
 *    face that lacks them, `font-variant-numeric: tabular-nums` silently does
 *    nothing and every digit change resizes the readout, shoving the row sideways.
 *  - No glows anywhere — depth shadows are fine, coloured halos are not.
 *  - The style picks (STYLE_CATALOG → #layersPanel) live INSIDE Finalização: when
 *    state.awaitingStyle is true it replaces the stage entirely, so the choice of
 *    editing style / caption style / edit elements cannot be skipped. It saves to
 *    <edit>/preview_style.json (never preview_edits.json — different screens,
 *    different moments, one would clobber the other).
 */
'use strict';

// ---------- dom ----------
const $ = (id) => document.getElementById(id);

/* As telas (régua, waveform) pintam em canvas, e canvas não enxerga `var(--x)`.
 * Antes disso as cores viviam duas vezes: uma no CSS e outra em hexa cru aqui —
 * o que garantia que uma troca de marca deixasse metade da interface para trás.
 * `tok()` lê o token computado do :root, então o canvas segue a folha de estilo
 * sozinho. Os trios `*-rgb` existem para poder aplicar transparência sobre o
 * token em vez de sobre um valor decorado à mão. */
const TOKENS = new Map();
const tok = (name) => {
  if (!TOKENS.has(name)) {
    TOKENS.set(name, getComputedStyle(document.documentElement).getPropertyValue(name).trim());
  }
  return TOKENS.get(name);
};
// mesma regra do CSS: o trio vem separado por espaço, então a transparência
// entra depois da barra. `rgba(x, y, z, a)` com trio de espaços não parseia.
const tokA = (name, a) => `rgb(${tok(name)} / ${a})`;
const video = $('video');
const panel = $('timelinePanel');
const timelineEl = $('timeline');
const rulerCv = $('ruler');
const waveCv = $('wave');
const laneVideo = $('laneVideo');
const laneAudio = $('laneAudio');
const laneCaptions = $('laneCaptions');
const insertTracksEl = $('insertTracks');
const needle = $('needle');
const tooltip = $('tooltip');

// minimal solid icons (design-system consistent — no emoji)
const ICON = {
  play: '<svg viewBox="0 0 16 16"><path d="M4 2.2v11.6c0 .9 1 1.5 1.8 1L15 9.2c.8-.5.8-1.7 0-2.2L5.8 1.2C5 .7 4 1.3 4 2.2z"/></svg>',
  pause: '<svg viewBox="0 0 16 16"><rect x="3" y="2" width="3.6" height="12" rx="1"/><rect x="9.4" y="2" width="3.6" height="12" rx="1"/></svg>',
  vol: '<svg viewBox="0 0 16 16"><path d="M2 6v4h2.8L9 13.4V2.6L4.8 6H2z"/><path d="M11 5.2a3.4 3.4 0 0 1 0 5.6V9.4a2 2 0 0 0 0-2.8V5.2z"/></svg>',
  mute: '<svg viewBox="0 0 16 16"><path d="M2 6v4h2.8L9 13.4V2.6L4.8 6H2z"/><path d="M11.2 6.2l3.6 3.6m0-3.6l-3.6 3.6" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" fill="none"/></svg>',
  // track identity — icons replace text labels (data-icon in index.html)
  captions: '<svg viewBox="0 0 16 16"><rect x="1" y="3" width="14" height="10" rx="2.4" fill="none" stroke="currentColor" stroke-width="1.4"/><rect x="3.4" y="8.4" width="4.4" height="1.5" rx=".75"/><rect x="8.9" y="8.4" width="3.7" height="1.5" rx=".75"/></svg>',
  video: '<svg viewBox="0 0 16 16"><rect x="1" y="3" width="14" height="10" rx="2.4" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M6.5 5.9v4.2c0 .4.44.64.79.42l3.3-2.1a.5.5 0 0 0 0-.85l-3.3-2.1a.5.5 0 0 0-.79.43z"/></svg>',
  audio: '<svg viewBox="0 0 16 16"><path d="M2.4 6.2v3.6h2.4l3.5 2.8V3.4L4.8 6.2H2.4z"/><path d="M10.5 5.7a3.2 3.2 0 0 1 0 4.6" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/><path d="M12.4 3.9a5.7 5.7 0 0 1 0 8.2" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>',
  inserts: '<svg viewBox="0 0 16 16"><rect x="1.2" y="3.2" width="13.6" height="9.6" rx="2.2" fill="none" stroke="currentColor" stroke-width="1.4"/><circle cx="5.3" cy="6.6" r="1.15"/><path d="M2.6 11.7l3-2.9a1 1 0 0 1 1.34-.05l1.84 1.58 1.5-1.24a1 1 0 0 1 1.29.02l1.72 1.5" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  music: '<svg viewBox="0 0 16 16"><path d="M13.1 1.9 6.6 3.5a.8.8 0 0 0-.6.78v6.06a2.25 2.25 0 1 0 1.5 2.12V6.6l5-1.22v3.5a2.25 2.25 0 1 0 1.5 2.12V2.68a.8.8 0 0 0-.9-.78z"/></svg>',
  text: '<svg viewBox="0 0 16 16"><path d="M2 2.6h12v2.5h-1.5V4.1H8.75v8.1h1.6v1.3H5.65v-1.3h1.6V4.1H3.5v1H2V2.6z"/></svg>',
  notes: '<svg viewBox="0 0 16 16"><rect x="1.9" y="1.4" width="1.6" height="13.2" rx=".8"/><path d="M5 2.7h7.6a.6.6 0 0 1 .47.97L11.36 6l1.71 2.33a.6.6 0 0 1-.47.97H5V2.7z"/></svg>',
  zoomIn: '<svg viewBox="0 0 16 16"><path d="M7 1.6a5.4 5.4 0 1 0 3.3 9.7l3.2 3.2a.9.9 0 0 0 1.3-1.3l-3.2-3.2A5.4 5.4 0 0 0 7 1.6zm0 1.8a3.6 3.6 0 1 1 0 7.2 3.6 3.6 0 0 1 0-7.2zm-.9 1.5v1.2H4.9v1.8h1.2v1.2h1.8V7.9h1.2V6.1H7.9V4.9H6.1z"/></svg>',
  zoomOut: '<svg viewBox="0 0 16 16"><path d="M7 1.6a5.4 5.4 0 1 0 3.3 9.7l3.2 3.2a.9.9 0 0 0 1.3-1.3l-3.2-3.2A5.4 5.4 0 0 0 7 1.6zm0 1.8a3.6 3.6 0 1 1 0 7.2 3.6 3.6 0 0 1 0-7.2zM4.9 6.1v1.8h4.2V6.1H4.9z"/></svg>',
  fit: '<svg viewBox="0 0 16 16"><path d="M2 2h4.2v1.8H3.8v2.4H2V2zm7.8 0H14v4.2h-1.8V3.8H9.8V2zM2 9.8h1.8v2.4h2.4V14H2V9.8zm10.2 0H14V14H9.8v-1.8h2.4V9.8z"/></svg>',
  flag: '<svg viewBox="0 0 16 16"><rect x="1.9" y="1.4" width="1.6" height="13.2" rx=".8"/><path d="M5 2.7h7.6a.6.6 0 0 1 .47.97L11.36 6l1.71 2.33a.6.6 0 0 1-.47.97H5V2.7z"/></svg>',
};

/* ---------- style catalog (the Fase 1 → Fase 2 gate) ----------
 * The one place that knows which looks Edvid can build. It is APP-level, not
 * session-level: a new editing style or caption style is a new entry here plus
 * its implementation in the track reference — never a per-session UI.
 * The user's pick ships to <edit>/preview_style.json; the skill reads it once,
 * at the gate, and builds Fase 2 from it.
 */
// O que já existe de verdade no motor. O catálogo abaixo descreve o produto
// inteiro; este mapa diz o que dele está pronto hoje. Manter os dois separados
// é de propósito: o catálogo é a promessa, isto é o estado.
const PORTED = {
  captions: new Set(['karaoke', 'simples', 'serifada', 'classica', 'scatter', 'stacked']),
  headlines: new Set(['outline', 'card', 'realce', 'misto']),
  edits: new Set(['limpa', 'split', 'split2']),
};

const STYLE_CATALOG = {
  edits: [
    {
      // First on purpose: defaultStyle() takes edits[0], so this is also the
      // default for every new project — a clean full-frame cut, with inserts as
      // something the user opts into.
      id: 'limpa',
      name: 'Limpa',
      mock: `<svg viewBox="0 0 66 118" xmlns="http://www.w3.org/2000/svg">
        <rect x=".5" y=".5" width="65" height="117" rx="7" fill="var(--bg1)" stroke="rgba(255,255,255,.12)"/>
        <rect x="3" y="3" width="60" height="112" rx="5" fill="rgba(255,255,255,.05)"/>
        <circle cx="33" cy="48" r="13" fill="rgba(255,255,255,.16)"/>
        <path d="M12 115a21 21 0 0142 0z" fill="rgba(255,255,255,.16)"/>
        <rect x="14" y="14" width="38" height="4.4" rx="2.2" fill="rgba(255,255,255,.5)"/>
        <rect x="20" y="21.5" width="26" height="4.4" rx="2.2" fill="rgba(255,255,255,.3)"/>
        <rect x="12" y="74" width="42" height="11" rx="5.5" fill="var(--bg1)" stroke="rgb(var(--blue-rgb) / .65)"/>
        <rect x="16" y="78.5" width="12" height="2.4" rx="1.2" fill="rgb(var(--blue-rgb) / .9)"/>
        <rect x="30" y="78.5" width="8" height="2.4" rx="1.2" fill="rgba(255,255,255,.5)"/>
        <rect x="40" y="78.5" width="10" height="2.4" rx="1.2" fill="rgba(255,255,255,.5)"/>
      </svg>`,
    },
    {
      id: 'split',
      name: 'Tela dividida',
      mock: `<svg viewBox="0 0 66 118" xmlns="http://www.w3.org/2000/svg">
        <rect x=".5" y=".5" width="65" height="117" rx="7" fill="var(--bg1)" stroke="rgba(255,255,255,.12)"/>
        <rect x="3" y="3" width="60" height="36" rx="5" fill="rgb(var(--orange-rgb) / .16)"/>
        <circle cx="17" cy="15" r="3.6" fill="rgb(var(--orange-rgb) / .6)"/>
        <path d="M6 36l11-11a2 2 0 013 0l7 7 5-4a2 2 0 013 0l11 8" fill="none" stroke="rgb(var(--orange-rgb) / .6)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        <path d="M3 40.5h60" stroke="rgba(255,255,255,.5)" stroke-width="1.2"/>
        <rect x="3" y="42" width="60" height="73" rx="5" fill="rgba(255,255,255,.05)"/>
        <circle cx="33" cy="70" r="12" fill="rgba(255,255,255,.16)"/>
        <path d="M15 115a18 18 0 0136 0z" fill="rgba(255,255,255,.16)"/>
        <rect x="12" y="35" width="42" height="11" rx="5.5" fill="var(--bg1)" stroke="rgb(var(--blue-rgb) / .65)"/>
        <rect x="16" y="39.5" width="12" height="2.4" rx="1.2" fill="rgb(var(--blue-rgb) / .9)"/>
        <rect x="30" y="39.5" width="8" height="2.4" rx="1.2" fill="rgba(255,255,255,.5)"/>
        <rect x="40" y="39.5" width="10" height="2.4" rx="1.2" fill="rgba(255,255,255,.5)"/>
      </svg>`,
    },
    {
      id: 'split2',
      name: 'Tela dividida 2',
      mock: `<svg viewBox="0 0 66 118" xmlns="http://www.w3.org/2000/svg">
        <rect x=".5" y=".5" width="65" height="117" rx="7" fill="var(--bg1)" stroke="rgba(255,255,255,.12)"/>
        <rect x="3" y="3" width="60" height="65" rx="5" fill="rgba(255,255,255,.05)"/>
        <circle cx="33" cy="24" r="11" fill="rgba(255,255,255,.16)"/>
        <path d="M16 68a17 17 0 0134 0z" fill="rgba(255,255,255,.16)"/>
        <path d="M3 69.5h60" stroke="rgba(255,255,255,.5)" stroke-width="1.2"/>
        <rect x="3" y="71" width="60" height="44" rx="5" fill="rgb(var(--orange-rgb) / .16)"/>
        <circle cx="17" cy="83" r="3.6" fill="rgb(var(--orange-rgb) / .6)"/>
        <path d="M6 111l11-11a2 2 0 013 0l7 7 5-4a2 2 0 013 0l11 8" fill="none" stroke="rgb(var(--orange-rgb) / .6)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        <rect x="12" y="58" width="42" height="11" rx="5.5" fill="var(--bg1)" stroke="rgb(var(--blue-rgb) / .65)"/>
        <rect x="16" y="62.5" width="12" height="2.4" rx="1.2" fill="rgb(var(--blue-rgb) / .9)"/>
        <rect x="30" y="62.5" width="8" height="2.4" rx="1.2" fill="rgba(255,255,255,.5)"/>
        <rect x="40" y="62.5" width="10" height="2.4" rx="1.2" fill="rgba(255,255,255,.5)"/>
      </svg>`,
    },
  ],
  // No names on purpose: the sample headline IS the label. Ids and geometry
  // mirror HL_STYLES in the template's Main.tsx — keep the two in step.
  headlines: [
    {id: 'outline', name: 'Contorno', hl: 'outline'},
    {id: 'card', name: 'Cartão', hl: 'card'},
    {id: 'realce', name: 'Realce', hl: 'realce'},
    {id: 'misto', name: 'Misto', hl: 'misto'},
  ],
  captions: [
    {id: 'karaoke', name: 'Karaokê', demo: 'karaoke'},
    {id: 'stacked', name: 'Empilhado', demo: 'stacked'},
    {id: 'scatter', name: 'Disperso', demo: 'scatter'},
    {id: 'simples', name: 'Simples', stat: 'simples'},
    {id: 'serifada', name: 'Serifada', stat: 'serifada'},
    {id: 'classica', name: 'Clássica', stat: 'classica'},
  ],
  elements: [
    {
      id: 'tracking',
      name: 'Movimento de tracking',
      def: false,
      icon: '<svg viewBox="0 0 16 16"><path d="M2 5.6V3.4A1.4 1.4 0 013.4 2h2.2M10.4 2h2.2A1.4 1.4 0 0114 3.4v2.2M14 10.4v2.2a1.4 1.4 0 01-1.4 1.4h-2.2M5.6 14H3.4A1.4 1.4 0 012 12.6v-2.2" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><circle cx="8" cy="8" r="2.1"/></svg>',
    },
    {
      id: 'zoomAuto',
      name: 'Automação de zoom in',
      def: true,
      icon: '<svg viewBox="0 0 16 16"><circle cx="7" cy="7" r="4.6" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M10.6 10.6L14 14" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" fill="none"/><path d="M7 5.1v3.8M5.1 7h3.8" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" fill="none"/></svg>',
    },
    {
      id: 'zoomCuts',
      name: 'Zoom in e out nos cortes',
      def: true,
      icon: '<svg viewBox="0 0 16 16"><rect x="1.2" y="3.4" width="6" height="9.2" rx="1.6" fill="none" stroke="currentColor" stroke-width="1.4"/><rect x="9.6" y="1.9" width="5.2" height="12.2" rx="1.6" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M8.4 8h.7" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>',
    },
    {
      id: 'flashCut',
      name: 'Flash na transição',
      def: false,
      icon: '<svg viewBox="0 0 16 16"><path d="M3 13.2L13 3.2" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" fill="none"/><path d="M6.6 14L9.4 11.2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" fill="none" opacity=".55"/><path d="M6.6 4.8L3.8 2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" fill="none" opacity=".55"/></svg>',
    },
    {
      id: 'musicAI',
      name: 'Trilha sonora com IA',
      def: true,
      icon: '<svg viewBox="0 0 16 16"><path d="M12.6 1.6L6.9 3a.7.7 0 00-.55.68v5.6a2 2 0 101.35 1.9V5.9l4.4-1.05v2.9a2 2 0 101.35 1.9V2.3a.7.7 0 00-.85-.7z"/><path d="M2.4 2.2l.6 1.5 1.5.6-1.5.6-.6 1.5-.6-1.5-1.5-.6 1.5-.6z"/></svg>',
    },
  ],
};

/* ---------- caption previews: the template's animation, not an impression ----
 * Every number here is lifted from the render (Main.tsx Karaoke/Word and
 * StackedCaptions.tsx STACK_MIXED) and scaled by boxWidth/1080, so the preview
 * shows the real proportions, the real faces and the real motion. If the
 * template's caption look changes, change it HERE too — a preview that lies
 * about the style is worse than no preview.
 */
const CAP_TEXT = 'É assim que sua legenda irá aparecer';
const FPS_REF = 30; // the template's reference fps for frame-based timings

// cubic-bezier solver — the stacked style eases on bezier(.16,1,.3,1)
function bez(x1, y1, x2, y2) {
  const cx = 3 * x1, bx = 3 * (x2 - x1) - cx, ax = 1 - cx - bx;
  const cy = 3 * y1, by = 3 * (y2 - y1) - cy, ay = 1 - cy - by;
  const fx = (t) => ((ax * t + bx) * t + cx) * t;
  const dfx = (t) => (3 * ax * t + 2 * bx) * t + cx;
  return (x) => {
    let t = x;
    for (let i = 0; i < 6; i++) {
      const e = fx(t) - x;
      if (Math.abs(e) < 1e-4) break;
      const d = dfx(t);
      if (Math.abs(d) < 1e-6) break;
      t -= e / d;
    }
    return ((ay * t + by) * t + cy) * t;
  };
}
const easeOutCubic = (t) => 1 - Math.pow(1 - t, 3); // Easing.out(Easing.cubic)
const easeStack = bez(0.16, 1, 0.3, 1);
const clamp01 = (v) => (v < 0 ? 0 : v > 1 ? 1 : v);

let capAnims = []; // step(nowSeconds) per visible caption demo

// Karaoke: lines of ≤3 words (captions.maxWords), Poppins 900 white, each word
// rises 34px and fades in over 7 frames; the line is replaced by the next one.
function buildKaraokeDemo(host) {
  const s = host.clientWidth / 1080;
  host.innerHTML = '';
  const wrap = el('div', 'cap-demo', host);
  const words = CAP_TEXT.split(' ');
  const lines = [];
  for (let i = 0; i < words.length; i += 3) lines.push(words.slice(i, i + 3));

  const STEP = 0.26, ENTER = 7 / FPS_REF, HOLD = 0.6;
  const rise = 34 * s;
  const built = [];
  let t = 0;
  for (const ln of lines) {
    const box = el('div', 'kar-line', wrap);
    box.style.fontSize = `${76 * s}px`;
    const spans = ln.map((w) => {
      const sp = el('span', '', box);
      sp.textContent = w;
      sp.style.marginRight = `${18 * s}px`;
      return sp;
    });
    const start = t;
    t = start + (ln.length - 1) * STEP + ENTER + HOLD;
    built.push({ box, spans, start, end: t });
  }
  const cycle = t + 0.3;

  return (now) => {
    const p = now % cycle;
    for (const L of built) {
      const on = p >= L.start && p < L.end;
      L.box.style.display = on ? '' : 'none';
      if (!on) continue;
      L.spans.forEach((sp, j) => {
        const e = easeOutCubic(clamp01((p - (L.start + j * STEP)) / ENTER));
        sp.style.opacity = e;
        sp.style.translate = `0px ${((1 - e) * rise).toFixed(2)}px`;
      });
    }
  };
}

// Stacked: one cue, lines cycling the STACK_MIXED styles (bold-italic gradient →
// regular small → Playfair italic orange). Words rise 46px with a blur that
// resolves; the cue leaves with the blur_up exit.
const STK_LINES = [
  { words: ['É', 'assim'], style: 0 },
  { words: ['que', 'sua', 'legenda'], style: 1 },
  { words: ['irá', 'aparecer'], style: 2 },
];
function buildStackedDemo(host) {
  const s = host.clientWidth / 1080;
  host.innerHTML = '';
  const wrap = el('div', 'cap-demo', host);
  const cue = el('div', 'stk-cue', wrap);

  const STEP = 0.2, ENTER = 8 / FPS_REF, HOLD = 0.8, EXIT = 7 / FPS_REF;
  const rise = 46 * s, blurIn = 5 * s, upY = 55 * s, cueBlur = 14 * s;
  const shadow = `drop-shadow(0 ${(5 * s).toFixed(2)}px ${(9 * s).toFixed(2)}px rgba(0,0,0,0.5))`;
  const all = [];
  let idx = 0;
  for (const L of STK_LINES) {
    const row = el('div', 'stk-line', cue);
    let size = 86;
    if (L.style === 1) size = Math.round(size * 0.72);
    if (L.style === 2) size = Math.round(size * 0.95);
    row.style.fontSize = `${size * s}px`;
    L.words.forEach((w, i) => {
      // the face/gradient belongs to the WORD, like the template's `...ls` spread
      const sp = el('span', `s${L.style}`, row);
      sp.textContent = w + (i < L.words.length - 1 ? ' ' : '');
      all.push({ sp, start: idx * STEP });
      idx++;
    });
  }
  const exitStart = (idx - 1) * STEP + ENTER + HOLD;
  // short gap after the exit: side by side with the karaoke card, a preview that
  // sits blank for half a second reads as broken rather than as a cue boundary
  const cycle = exitStart + EXIT + 0.15;

  return (now) => {
    const p = now % cycle;
    const ex = clamp01((p - exitStart) / EXIT);
    cue.style.opacity = 1 - ex;
    cue.style.translate = `0px ${(-upY * ex).toFixed(2)}px`;
    cue.style.filter = ex > 0.02 ? `blur(${(cueBlur * ex).toFixed(2)}px)` : '';
    for (const w of all) {
      const e = easeStack(clamp01((p - w.start) / ENTER));
      const eb = (1 - e) * blurIn;
      w.sp.style.opacity = e;
      w.sp.style.translate = `0px ${((1 - e) * rise).toFixed(2)}px`;
      w.sp.style.filter = `${eb > 0.06 ? `blur(${eb.toFixed(2)}px) ` : ''}${shadow}`;
    }
  };
}

/* ---------- headline previews: the template's own hook styles ----------------
 * Same contract as the caption demos — these render what `HookInner` renders,
 * scaled from 1080-wide. The two-line break and the size fit run the SAME
 * algorithm as the template (balance by measured width, then fit to safeW), so
 * the preview shows the real break at the real size, not an approximation.
 * HL_STYLES exists on both sides; change one, change the other.
 */
const HEADLINE_TEXT = 'É assim que vai ficar a sua headline';
const HL_MIN = 40;
const HL_STYLES = {
  outline: { weights: [800, 800], cap: 92, safeW: 900, lh: 1.02 },
  card: { weights: [900, 900], cap: 82, safeW: 820, lh: 1.06 },
  realce: { weights: [900, 900], cap: 86, safeW: 830, lh: 1.04 },
  misto: { weights: [400, 900], cap: 98, safeW: 900, lh: 0.98 },
};

// Measured in RENDER units (1080-wide), scaled to the box only at the end — the
// template's letterSpacing is -1px at 1080, which is NOT proportional once the
// preview shrinks it, so measuring in preview px would break the fit.
let hlMeter = null;
function measureType(text, size, weight, family, tracking) {
  if (!text) return 0;
  if (!hlMeter) {
    hlMeter = document.createElement('span');
    hlMeter.style.cssText =
      'position:absolute;left:-9999px;top:0;visibility:hidden;white-space:pre;';
    document.body.appendChild(hlMeter);
  }
  hlMeter.style.fontFamily = family || "'Poppins',sans-serif";
  hlMeter.style.letterSpacing = `${tracking == null ? -1 : tracking}px`;
  hlMeter.style.fontSize = `${size}px`;
  hlMeter.style.fontWeight = String(weight);
  hlMeter.textContent = text;
  return hlMeter.offsetWidth;
}
const hlWidth = (text, size, weight) => measureType(text, size, weight);

// Balance by MEASURED width, not word count: "É assim que vai" and "ficar a sua
// headline" are 4 and 3 words but nearly the same width — counting words breaks
// the line in the wrong place.
function hlTwoLines(text, weights) {
  const words = text.trim().split(/\s+/).filter(Boolean);
  if (words.length < 2) return [words[0] || '', ''];
  let best = [words[0], words.slice(1).join(' ')];
  let bestDiff = Infinity;
  for (let i = 1; i < words.length; i++) {
    const a = words.slice(0, i).join(' ');
    const b = words.slice(i).join(' ');
    const d = Math.abs(hlWidth(a, 100, weights[0]) - hlWidth(b, 100, weights[1]));
    if (d < bestDiff) { bestDiff = d; best = [a, b]; }
  }
  return best;
}

function hlFit(lines, S) {
  const widest = (size) =>
    Math.max(hlWidth(lines[0], size, S.weights[0]), hlWidth(lines[1], size, S.weights[1]));
  let size = Math.floor((S.safeW / Math.max(1, widest(100))) * 100);
  size = Math.floor((S.safeW / Math.max(1, widest(size))) * size);
  return Math.max(HL_MIN, Math.min(size, S.cap));
}

function buildHeadlineDemo(host, styleId) {
  const s = host.clientWidth / 1080;
  const S = HL_STYLES[styleId];
  host.innerHTML = '';
  const wrap = el('div', 'cap-demo', host);
  const raw = styleId === 'card' ? HEADLINE_TEXT.toUpperCase() : HEADLINE_TEXT;
  const lines = hlTwoLines(raw, S.weights);
  const size = hlFit(lines, S) * s;
  const box = el('div', `hl-demo hl-${styleId}`, wrap);
  box.style.lineHeight = String(S.lh);
  box.style.letterSpacing = `${-1 * s}px`;

  if (styleId === 'realce') {
    for (const l of lines) {
      if (!l) continue;
      const b = el('div', 'hl-block', box);
      b.style.fontSize = `${size}px`;
      b.style.borderRadius = `${12 * s}px`;
      b.textContent = l;
    }
    return;
  }
  if (styleId === 'card') {
    box.style.borderRadius = `${24 * s}px`;
    box.style.padding = `${28 * s}px ${46 * s}px`;
  }
  if (styleId === 'outline') {
    box.style.webkitTextStroke = `${12 * s}px #000`;
  }
  lines.forEach((l, i) => {
    if (!l) return;
    const d = el('div', '', box);
    d.style.fontSize = `${size}px`;
    d.style.fontWeight = String(S.weights[i]);
    // var(), not a literal — an inline colour would beat the accent variable and
    // this preview would keep painting orange while the others followed the pick
    if (styleId === 'misto') d.style.color = i === 1 ? 'var(--hl-accent)' : '#fff';
    d.textContent = l;
  });
}

// Scatter ("disperso"): serif, lowercase, one word at a time, off-white with a
// slight darkening toward the baseline. Ordinary words FADE only — no movement;
// the one highlighted word resolves out of a blur and dissolves back into it.
// Mirrors ScatterCaptions.tsx: same line rules, same SPREAD, same hash.
const SCAT = { base: 72, hiScale: 1.62, gap: 12, spread: 0.45, safeW: 820 };
const scatHash = (n) => { const x = Math.sin(n * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); };

function buildScatterDemo(host) {
  const s = host.clientWidth / 1080;
  host.innerHTML = '';
  const wrap = el('div', 'cap-demo', host);
  const cue = el('div', 'scat-cue', wrap);

  const words = CAP_TEXT.toLowerCase().split(' ');
  // highlight = longest word of the cue, and only if it carries weight (>6)
  let hiIdx = -1, hiLen = 6;
  words.forEach((w, i) => { if (w.length > hiLen) { hiLen = w.length; hiIdx = i; } });

  // ragged lines of 3–4 words; the highlighted word takes a line of its own
  const lines = [];
  let line = [];
  words.forEach((w, i) => {
    if (i === hiIdx) {
      if (line.length) lines.push(line);
      lines.push([{ w, i, hi: true }]);
      line = [];
      return;
    }
    line.push({ w, i, hi: false });
    if (line.length >= (scatHash(31 + i) > 0.5 ? 4 : 3)) { lines.push(line); line = []; }
  });
  if (line.length) lines.push(line);

  const STEP = 0.22, ENTER = 7 / FPS_REF, HI_ENTER = 10 / FPS_REF, HOLD = 0.9, EXIT = 8 / FPS_REF;
  const all = [];
  lines.forEach((ln, li) => {
    const row = el('div', 'scat-line', cue);
    row.style.gap = `${SCAT.gap * s}px`;
    let w = 0;
    for (const it of ln) {
      const sp = el('span', it.hi ? 'hi' : '', row);
      sp.textContent = it.w;
      sp.style.fontSize = `${(it.hi ? SCAT.base * SCAT.hiScale : SCAT.base) * s}px`;
      all.push({ sp, start: it.i * STEP, hi: it.hi });
      w += sp.offsetWidth + SCAT.gap * s;
    }
    const room = Math.max(0, (SCAT.safeW * s - w) / 2) * SCAT.spread;
    row.style.translate = `${((scatHash(17 + li * 5 + 3) * 2 - 1) * room).toFixed(1)}px 0px`;
  });

  const exitStart = (words.length - 1) * STEP + ENTER + HOLD;
  const cycle = exitStart + EXIT + 0.35;
  const blurIn = 26 * s, blurOut = 30 * s;

  return (now) => {
    const p = now % cycle;
    const out = clamp01((p - exitStart) / EXIT);
    for (const w of all) {
      const t = easeOutCubic(clamp01((p - w.start) / (w.hi ? HI_ENTER : ENTER)));
      w.sp.style.opacity = t * (1 - out);
      if (w.hi) {
        const b = (1 - t) * blurIn + out * blurOut;
        w.sp.style.filter = b > 0.1 ? `blur(${b.toFixed(2)}px)` : '';
      }
    }
  };
}

/* ---------- the three STATIC caption styles ---------------------------------
 * No animation, so no entry in capAnims — built once and left alone. Mirrors
 * SIMPLE_VARIANTS in SimpleCaptions.tsx, including the rule that matters most:
 * lines are grouped by MEASURED WIDTH, capped at maxWords. That is why a long
 * word ends up alone and short ones ride together.
 */
const STATIC_VARIANTS = {
  simples: {family: "'Poppins',sans-serif", weight: 600, size: 82, maxWords: 3, lines: 1, sx: 0.9, sy: 0.9, tracking: -3, maxW: 860},
  serifada: {family: "'Libre Baskerville',serif", weight: 700, size: 84, maxWords: 3, lines: 1, sx: 1, sy: 1, tracking: -1, maxW: 860},
  classica: {family: "'Inter',sans-serif", weight: 500, size: 52, maxWords: 14, lines: 2, sx: 1, sy: 1, tracking: 0, maxW: 840},
};
const ORPHAN_PT = /^(o|a|os|as|e|é|de|do|da|em|no|na|um|uma|que|se|ao|à|por|com)$/i;

function buildStaticDemo(host, id) {
  const V = STATIC_VARIANTS[id];
  const s = host.clientWidth / 1080;
  host.innerHTML = '';
  const wrap = el('div', 'cap-demo', host);
  const words = CAP_TEXT.split(' ');
  const wOf = (ws) => measureType(ws.join(' '), V.size, V.weight, V.family, V.tracking) * V.sx;

  // the WHOLE sentence, cut into cues exactly as the render would
  const cues = [];
  let cur = [];
  for (const w of words) {
    const trial = [...cur, w];
    if (cur.length && (trial.length > V.maxWords || wOf(trial) > V.maxW * V.lines)) {
      cues.push(cur);
      cur = [w];
    } else {
      cur = trial;
    }
  }
  if (cur.length) cues.push(cur);

  const boxes = cues.map((cue) => {
    let lines = [cue];
    if (V.lines === 2 && cue.length > 1) {
      let best = 1, bestScore = Infinity;
      for (let i = 1; i < cue.length; i++) {
        const score = Math.abs(wOf(cue.slice(0, i)) - wOf(cue.slice(i))) + (ORPHAN_PT.test(cue[i - 1]) ? 200 : 0);
        if (score < bestScore) { bestScore = score; best = i; }
      }
      lines = [cue.slice(0, best), cue.slice(best)];
    }
    const box = el('div', 'stat-demo', wrap);
    box.style.fontFamily = V.family;
    box.style.fontWeight = String(V.weight);
    box.style.fontSize = `${V.size * s}px`;
    box.style.letterSpacing = `${V.tracking * s}px`;
    box.style.transform = V.sx === 1 && V.sy === 1 ? '' : `scale(${V.sx}, ${V.sy})`;
    for (const ln of lines) el('div', '', box).textContent = ln.join(' ');
    return box;
  });

  // A style with no animation still has a RHYTHM — the cues replacing each other
  // is what the viewer sees. So the card plays the whole sentence, cue by cue,
  // on hard cuts. A single-cue style (the two-line "classica" fits the sentence
  // whole) has nothing to step through and stays still.
  if (boxes.length < 2) return null;
  const HOLD = 0.95;
  const cycle = boxes.length * HOLD;
  return (now) => {
    const i = Math.floor((now % cycle) / HOLD);
    boxes.forEach((b, k) => { b.style.display = k === i ? '' : 'none'; });
  };
}

const CAP_BUILDERS = { karaoke: buildKaraokeDemo, stacked: buildStackedDemo, scatter: buildScatterDemo };

// Largura da calha = deslocamento x das pistas dentro do conteúdo rolável.
// Lida do token `--label-w` em vez de repetida aqui: era um número duplicado em
// três arquivos, e errar a sincronia desloca a agulha e o scrub em silêncio —
// nada quebra, só passa a apontar para o instante errado.
const LABEL_W = parseFloat(tok('--label-w')) || 132;
const MIN_SEG = 0.2; // s
const THUMB_EVERY = 2.0;

// ---------- state ----------
let S = {
  state: {}, // state.json
  rendered: [], // ranges as rendered (from edl.json) — the video's truth
  draft: [], // user-editable copy [{source,start,end,beat,removed,orig:{start,end}}]
  videoDuration: 0,
  fps: 24,
  captions: [], // grouped caption lines [{text,start,end}] (rendered space)
  editData: null, // edit-data.json content (phase 2)
  insertsDraft: [], // editable inserts [{kind,label,start,end,ref,orig}]
  wave: null,
  thumbCount: 0,
  tab: 1,
  pps: 10, // px per second (zoom)
  minPps: 4,
  selected: -1, // selected clip index (draft)
  lastSig: '', // change detection
  savedPending: false,
  notes: [], // correction markers [{id,start,end,text}] — draft-timeline seconds
  showFinal: false, // tocando o render final em vez do corte
  pendingIn: null, // an IN is open, waiting for its OUT
  editingNote: null, // id of the note the editor is bound to
  style: null, // current picks {edit, captions, elements:{…}, note}
  jcut: null, // jcut_timeline from edl.json — real output positions per take
  // A1/A2 live folded inside the audio track. They answer "where is the J-cut",
  // which is a question you ask once — so the default is closed, and the choice
  // is remembered rather than re-made every reload.
  jcutOpen: localStorage.getItem('edvid.jcutOpen') === '1',
};

function defaultStyle() {
  const elements = {};
  for (const e of STYLE_CATALOG.elements) elements[e.id] = !!e.def;
  return {
    edit: STYLE_CATALOG.edits[0].id,
    headline: STYLE_CATALOG.headlines[0].id,
    captions: STYLE_CATALOG.captions[0].id,
    accent: ACCENT_DEFAULT,
    capColor: '#FFFFFF',
    headlineText: '',
    elements,
    note: '',
  };
}

const fmt = (t) => {
  if (!isFinite(t) || t < 0) t = 0;
  const m = Math.floor(t / 60);
  const s = t - m * 60;
  return `${m}:${s.toFixed(2).padStart(5, '0')}`;
};
const el = (tag, cls, parent) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (parent) parent.appendChild(e);
  return e;
};

const plural = (n) => `${n} camada${n === 1 ? '' : 's'}`;

/* Contagem das trilhas fixas. Fica junto do render das pistas porque é a mesma
   pergunta — quanta coisa tem aqui — só que para as pistas que existem no HTML
   em vez de serem criadas por JS. */
function refreshCounts() {
  const put = (id, txt) => { const n = $(id); if (n) n.textContent = txt; };
  const notes = (S.notes || []).length;
  put('cntNotes', notes ? `${notes} marcação${notes === 1 ? '' : 'ões'}` : 'nenhuma');
  put('cntCaptions', S.captions.length ? `${S.captions.length} deixas` : '—');
  const takes = (S.draft || []).length;
  put('cntVideo', takes ? `${takes} trecho${takes === 1 ? '' : 's'}` : '1 camada');
  put('cntAudio', S.jcut && S.jcut.length ? '2 camadas (J-cut)' : '1 camada');
}

// ---------- draft layout (output-timeline positions) ----------
/* Per-take J-cut geometry, in seconds. `lead` is how far the take's sound runs
 * ahead of its picture; `tail` is what was trimmed off its end. Both are fixed
 * frame counts, so they survive the user trimming a take in the UI. */
function jcutGeom(i) {
  const j = S.jcut && S.jcut[i];
  if (!j) return { lead: 0, tail: 0 };
  return {
    lead: Math.max(0, (j.video_start_in_output || 0) - (j.audio_start_in_output || 0)),
    tail: (j.tail_trim_frames || 0) / (S.fps || 30),
  };
}

/* The draft timeline has to model the J-cut, not just sum the ranges: a take's
 * picture is shorter than its range by the lead it gives up plus the tail it had
 * trimmed. Summing raw ranges made the ruler read 8.07s over a 7.60s render, and
 * every clip after the first sat late by the accumulated lead. Each item also
 * carries its AUDIO placement (aout/adur), which is what the A1/A2 lanes draw —
 * derived here so the lanes follow the user's trims instead of going stale. */
/* `freeze` congela UM trecho no tamanho que ele tinha antes do arrasto.
 *
 * Sem isso, puxar o início de um trecho encolhe o bloco pela direita — a borda
 * esquerda está presa pelo trecho anterior, porque esta é a linha do tempo do
 * CORTE, não da fonte. O resultado é que a alça que a pessoa está segurando não
 * se move e a outra ponta sim, que lê como "mexi no começo e ele arrastou o
 * fim". Congelando durante o arrasto, nada se desloca: a parte removida aparece
 * escurecida e a alça acompanha o cursor. O rearranjo acontece ao soltar, uma
 * vez só, que é quando a pessoa espera por ele. */
function draftLayout(freeze) {
  let t = 0;
  let at = 0;
  return S.draft.map((r, i) => {
    if (r.removed) return { ...r, out: t, dur: 0, aout: at, adur: 0 };
    const g = jcutGeom(i);
    const frozen = freeze != null && i === freeze;
    const span = frozen ? r.orig.end - r.orig.start : r.end - r.start;
    const adur = Math.max(0, span - g.tail);
    const dur = Math.max(0, adur - g.lead);
    const item = { ...r, out: t, dur, aout: Math.max(0, at - g.lead), adur, lead: g.lead };
    t += dur;
    at = item.aout + adur;
    return item;
  });
}
function renderedLayout() {
  // Under a J-cut the rendered positions come from render.py, not from summing
  // the ranges — the takes overlap in sound and the picture of each one starts
  // a few frames in. Summing here would place every clip after the first too late.
  if (S.jcut && S.jcut.length === S.rendered.length) {
    return S.rendered.map((r, i) => ({
      ...r,
      out: S.jcut[i].video_start_in_output,
      dur: S.jcut[i].video_duration,
    }));
  }
  let t = 0;
  return S.rendered.map((r) => {
    const dur = r.end - r.start;
    const item = { ...r, out: t, dur };
    t += dur;
    return item;
  });
}
// Durante um aparo, o total também congela: se ele encolhesse, a régua e a
// largura da linha do tempo se reescalariam no meio do arrasto e TUDO andaria
// debaixo do cursor.
const draftTotal = () =>
  draftLayout(drag && drag.type === 'trim' ? drag.i : null)
    .reduce((a, r) => a + r.dur, 0);

// draft time → rendered time (for scrubbing the old render while editing)
function draftToRendered(t) {
  const dl = draftLayout();
  const rl = renderedLayout();
  for (let i = dl.length - 1; i >= 0; i--) {
    const d = dl[i];
    if (d.removed || t < d.out) continue;
    const off = Math.min(t - d.out, (rl[i]?.dur ?? d.dur) - 0.02);
    return (rl[i]?.out ?? d.out) + Math.max(0, off);
  }
  return Math.min(t, S.videoDuration);
}
// rendered time → draft time (needle position during playback)
function renderedToDraft(t) {
  const dl = draftLayout();
  const rl = renderedLayout();
  for (let i = rl.length - 1; i >= 0; i--) {
    const r = rl[i];
    if (t < r.out) continue;
    if (dl[i]?.removed) return dl[i].out; // playing removed material → park at its slot
    const off = Math.min(t - r.out, dl[i]?.dur ?? r.dur);
    return (dl[i]?.out ?? r.out) + off;
  }
  return t;
}

// ---------- dirty tracking ----------
function edlDirty() {
  return S.draft.some((r) => r.removed || r.start !== r.orig.start || r.end !== r.orig.end);
}
function insertsDirty() {
  return S.insertsDraft.some((c) => c.start !== c.orig.start || c.end !== c.orig.end);
}
function dirtyCount() {
  let n = S.draft.filter((r) => r.removed || r.start !== r.orig.start || r.end !== r.orig.end).length;
  n += S.insertsDraft.filter((c) => c.start !== c.orig.start || c.end !== c.orig.end).length;
  n += S.notes.length; // each correction marker is an unsaved adjustment too
  return n;
}
function refreshHeader() {
  const n = dirtyCount();
  $('dirtyPill').classList.toggle('hidden', n === 0);
  $('dirtyCount').textContent = n;
  $('btnSave').classList.toggle('hidden', n === 0);
  $('btnDiscard').classList.toggle('hidden', n === 0);
  $('savedPill').classList.toggle('hidden', !(S.savedPending && n === 0));
}

// ---------- data loading ----------
async function poll() {
  try {
    const res = await fetch('/api/state');
    const data = await res.json();
    const sig = JSON.stringify([data.state, data.edl, data.mtimes, data.videoDuration]);
    if (sig !== S.lastSig) {
      const hadEdits = dirtyCount() > 0;
      if (!hadEdits) {
        S.lastSig = sig;
        await applyState(data);
      } else {
        toast('Novo estado disponível — salve ou descarte seus ajustes para atualizar', 4000);
      }
    }
  } catch (e) { /* server restarting; keep polling */ }
  setTimeout(poll, 2000);
}

async function applyState(data) {
  S.state = data.state || {};
  S.mtimes = data.mtimes || {};
  S.videoDuration = data.videoDuration || 0;
  S.fps = S.state.fps || 24;
  S.savedPending = !!data.hasPendingEdits;

  $('projectName').textContent = S.state.project || 'Edvid';
  // o recado de estado saiu do cabeçalho; ainda chega pelo title da janela,
  // que é onde ele não disputa espaço com nada
  document.title = S.state.project ? `${S.state.project} — Avelin` : 'Avelin — Editor';

  const ranges = (data.edl && data.edl.ranges) || [];
  // J-cut timeline, written by render.py. Under a J-cut the picture of every take
  // after the first starts a few frames into itself, so the rendered clip is
  // SHORTER than end-start and the takes do not simply abut. Without this the
  // filmstrip and the needle drift a little further at each junction.
  S.jcut = (data.edl && data.edl.jcut_timeline) || null;
  S.rendered = ranges.map((r) => ({ source: r.source, start: +r.start, end: +r.end, beat: r.beat || '' }));
  S.draft = S.rendered.map((r) => ({ ...r, removed: false, orig: { start: r.start, end: r.end } }));
  S.selected = -1;

  // style picks: the skill's copy wins, so applying a change (or reopening the
  // session) shows what is actually rendered — not a stale local selection
  S.style = { ...defaultStyle(), ...(S.state.style || {}) };
  S.style.elements = { ...defaultStyle().elements, ...((S.state.style || {}).elements || {}) };
  $('setupNote').value = S.style.note || '';
  // a skill pediu uma escolha de estilo → leva o usuário para a Finalização,
  // onde o painel de camadas agora mora

  const hasVideo = S.videoDuration > 0;
  $('playerWrap').classList.toggle('hidden', !hasVideo);
  $('editorCol').classList.toggle('hidden', !hasVideo);

  if (hasVideo) {
    updateVideoSrc();
    loadWave();
    loadThumbsMeta();
  }

  S.captions = [];
  S.editData = null;
  S.insertsDraft = [];
  if ((S.state.phase || 1) >= 2) {
    if (S.state.captions) {
      try {
        const caps = await (await fetch(`/media/${S.state.captions}?v=${Date.now()}`)).json();
        S.captions = groupCaptions(caps);
      } catch (e) { /* absent yet */ }
    }
    if (S.state.editData) {
      try {
        S.editData = await (await fetch(`/media/${S.state.editData}?v=${Date.now()}`)).json();
        buildInsertsDraft();
      } catch (e) { /* absent yet */ }
    }
  }

  refreshSrcToggle();
  fitZoom();
  renderAll();
  renderSetup();
  refreshHeader();
}

// Fase 1 plays the clean cut; Fase 2 plays the Phase-2 render (state.finalVideo)
// when it exists, so captions/inserts are visible. Keeps the playback position.
function updateVideoSrc() {
  // A fonte é ESCOLHA do usuário, não efeito colateral de trocar de aba. Antes,
  // mudar de aba trocava o arquivo em silêncio e dava para passar minutos
  // ouvindo o render antigo achando que era o corte novo.
  const wantFinal = S.showFinal && S.state.finalVideo;
  const rel = wantFinal ? S.state.finalVideo : (S.state.video || 'cut.mp4');
  const vsrc = `/media/${rel}?v=${(S.mtimes && (S.mtimes.finalVideo || S.mtimes.video)) || 0}`;
  if (video.dataset.src === vsrc) return;
  const t = video.currentTime;
  const wasPlaying = !video.paused && !video.ended;
  video.dataset.src = vsrc;
  video.src = vsrc;
  video.currentTime = t;
  if (wasPlaying) video.play();
}

function groupCaptions(caps) {
  // mirror the template: lines of ≤3 words, break on punctuation
  const lines = [];
  let cur = [];
  for (const w of caps) {
    cur.push(w);
    if (cur.length >= 3 || /[.,!?…]$/.test(w.text)) { lines.push(cur); cur = []; }
  }
  if (cur.length) lines.push(cur);
  return lines.map((line) => ({
    text: line.map((w) => w.text.replace(/[.,!?…]+$/, '')).join(' '),
    start: line[0].startMs / 1000,
    end: line[line.length - 1].endMs / 1000,
  }));
}

function buildInsertsDraft() {
  const d = S.editData;
  const list = [];
  if (d.hook && d.hook.enabled) {
    list.push({ kind: 'hook', label: `HOOK — ${(d.hook.lines || []).join(' / ')}`, start: 0, end: d.hook.endSec || 4 });
  }
  (d.inserts || []).forEach((it, i) => {
    list.push({ kind: 'insert', label: (it.src || '').split('/').pop(), start: +it.start, end: +it.end, ref: i });
  });
  // split-layout images (CustomGraphics reads the same array) — they are images
  // like any other insert, so they belong on the image track, not in code
  (d.splitInserts || []).forEach((it, i) => {
    list.push({
      kind: 'split',
      label: it.label || (it.src || '').split('/').pop(),
      start: +it.start, end: +it.end, ref: i,
    });
  });
  // split-layout VIDEO bands — same seam and geometry as splitInserts, but the
  // band plays a clip (generated b-roll, screen capture). Its own array because
  // the renderer mounts it with a different component; on the timeline it is an
  // image-track element like any other.
  (d.splitVideos || []).forEach((it, i) => {
    list.push({
      kind: 'splitvideo',
      label: it.label || (it.src || '').split('/').pop(),
      start: +it.start, end: +it.end, ref: i,
    });
  });
  // bespoke motion graphics drawn in CustomGraphics.tsx — they have no `src`,
  // so the label is the graphic's id. Without this the windows are invisible
  // here: the user sees a full-frame graphic in the player with nothing on the
  // timeline to grab, and cannot retime or remove it.
  (d.brollGraphics || []).forEach((g, i) => {
    list.push({
      kind: 'broll',
      label: g.label || (g.id || 'gráfico').replace(/_/g, ' '),
      start: +g.start, end: +g.end, ref: i,
    });
  });
  (d.behind || []).forEach((b, i) => {
    list.push({ kind: 'behind', label: `BEHIND ${b.kind === 'words' ? (b.words || []).map((w) => w.t).join(' ') : (b.src || '').split('/').pop()}`, start: +b.start, end: +b.start + +b.dur, ref: i });
  });
  // held single words in the caption's own visual language (a keyword the viewer
  // must type, an emphasis beat) — text, so they ride the text track next to the
  // hook rather than the image track
  (d.wordAccents || []).forEach((w, i) => {
    list.push({ kind: 'word', label: w.text, start: +w.start, end: +w.end, ref: i });
  });
  S.insertsDraft = list.map((c) => ({ ...c, orig: { start: c.start, end: c.end } }));
}

async function loadWave() {
  try {
    S.wave = await (await fetch('/gen/waveform.json')).json();
    drawWave();
  } catch (e) { S.wave = null; }
}
async function loadThumbsMeta() {
  try {
    const meta = await (await fetch('/gen/thumbs/meta.json')).json();
    S.thumbCount = meta.count || 0;
    renderClips();
  } catch (e) { S.thumbCount = 0; }
}

// ---------- zoom / layout ----------
function contentWidth() { return LABEL_W + Math.max(draftTotal(), S.videoDuration, 1) * S.pps + 14; }
function fitZoom() {
  const avail = panel.clientWidth - LABEL_W - 40;
  const total = Math.max(draftTotal(), S.videoDuration, 1);
  S.minPps = Math.max(1, avail / total);
  S.pps = S.minPps;
  $('zoom').value = 0;
}
const MAX_PPS = 200;

// Zoom keeping `t` (seconds) parked at `anchorX` (px from the panel's left edge).
function applyZoom(pps, t, anchorX) {
  S.pps = Math.min(MAX_PPS, Math.max(S.minPps, pps));
  const span = Math.log(MAX_PPS / S.minPps);
  $('zoom').value = span > 0 ? Math.round((100 * Math.log(S.pps / S.minPps)) / span) : 0;
  renderAll();
  panel.scrollLeft = Math.max(0, LABEL_W + t * S.pps - anchorX);
  drawRuler();
  drawWave();
  positionNeedle();
}

// Trackpad pinch arrives as a wheel event with ctrlKey set. Anchored on the
// pointer (a direct gesture zooms where the fingers are); the slider stays
// anchored on the needle.
panel.addEventListener('wheel', (e) => {
  if (!e.ctrlKey) return; // plain two-finger scrolling stays untouched
  e.preventDefault();
  const pr = panel.getBoundingClientRect();
  const anchorX = e.clientX - pr.left;
  const t = (panel.scrollLeft + anchorX - LABEL_W) / S.pps;
  applyZoom(S.pps * Math.exp(-e.deltaY * 0.01), Math.max(0, t), anchorX);
}, { passive: false });

function setZoom(v) { // slider 0..100 → minPps..200, anchored on the needle
  const t = renderedToDraft(video.currentTime || 0);
  // viewport x of the needle before the zoom; if it is off-screen, pull it to
  // the middle so zooming always lands on the playhead the user is looking at
  const xBefore = LABEL_W + t * S.pps - panel.scrollLeft;
  const visible = xBefore >= LABEL_W && xBefore <= panel.clientWidth;
  const anchor = visible ? xBefore : LABEL_W + (panel.clientWidth - LABEL_W) / 2;
  applyZoom(S.minPps * Math.pow(MAX_PPS / S.minPps, v / 100), t, anchor);
}

// Lanes are clipped at the gutter (and the divider is positioned) by a
// scroll-driven CSS timeline, so both stay pinned to scrollLeft with zero lag.
// All JS has to publish is the scroll RANGE, which only changes on zoom/resize.
function updateScrollRange() {
  const max = Math.max(0, panel.scrollWidth - panel.clientWidth);
  timelineEl.style.setProperty('--max-scroll', `${max}px`);
}

// ---------- rendering ----------
function renderAll() {
  timelineEl.style.width = `${contentWidth()}px`;
  renderClips();
  renderJcutAudio();
  renderChips();
  renderNotes();
  drawRuler();
  drawWave();
  refreshCounts();
  updateScrollRange();
  positionNeedle();
}

// ---------- correction markers ----------
function renderNotes() {
  refreshCounts();   // a contagem vive aqui: adicionar uma nota não passa por renderAll
  const lane = $('laneNotes');
  lane.innerHTML = '';
  for (const n of S.notes) {
    const chip = el('div', 'note-chip', lane);
    chip.style.left = `${n.start * S.pps}px`;
    chip.style.width = `${Math.max((n.end - n.start) * S.pps, 10)}px`;
    chip.textContent = n.text || '(sem descrição)';
    chip.title = `${fmt(n.start)} → ${fmt(n.end)}\n${n.text || ''}\n\nclique para editar`;
    chip.dataset.id = n.id;
  }
  if (S.pendingIn != null) {
    const p = el('div', 'note-pending', lane);
    p.style.left = `${S.pendingIn * S.pps}px`;
  }
  const btn = $('btnMark');
  btn.classList.toggle('armed', S.pendingIn != null);
  $('markText').textContent = S.pendingIn != null ? 'Fim' : 'Marcar';
}

function toggleMark() {
  const t = renderedToDraft(video.currentTime || 0);
  if (S.pendingIn == null) {
    S.pendingIn = t;
    renderNotes();
    toast('IN marcado — leve a agulha ao fim do trecho e marque o OUT', 2600);
    return;
  }
  const start = Math.min(S.pendingIn, t);
  const end = Math.max(S.pendingIn, t);
  if (end - start < 0.05) {
    toast('Trecho curto demais — afaste a agulha do IN', 2200);
    return;
  }
  S.pendingIn = null;
  const note = { id: `n${Date.now()}`, start, end, text: '' };
  S.notes.push(note);
  S.notes.sort((a, b) => a.start - b.start);
  renderNotes();
  openNoteEditor(note.id, true);
}

function openNoteEditor(id, isNew) {
  const n = S.notes.find((x) => x.id === id);
  if (!n) return;
  S.editingNote = id;
  $('noteRange').textContent = `${fmt(n.start)} → ${fmt(n.end)}`;
  $('noteText').value = n.text || '';
  $('noteDelete').classList.toggle('hidden', !!isNew);
  // centred over the timeline (where the user's eyes are), then clamped so a
  // short timeline panel cannot push the editor off-screen
  const ed = $('noteEditor');
  ed.classList.remove('hidden');
  const p = panel.getBoundingClientRect();
  const h = ed.offsetHeight;
  const w = ed.offsetWidth;
  const cy = Math.min(
    Math.max(p.top + p.height / 2, h / 2 + 12),
    window.innerHeight - h / 2 - 12,
  );
  const cx = Math.min(Math.max(p.left + p.width / 2, w / 2 + 12), window.innerWidth - w / 2 - 12);
  ed.style.left = `${cx}px`;
  ed.style.top = `${cy}px`;
  $('noteText').focus();
}

function closeNoteEditor() {
  // a brand-new marker with no text is not worth keeping
  const n = S.notes.find((x) => x.id === S.editingNote);
  if (n && !n.text.trim()) S.notes = S.notes.filter((x) => x.id !== n.id);
  S.editingNote = null;
  $('noteEditor').classList.add('hidden');
  renderNotes();
  refreshHeader();
}

// ---------- style setup ----------
const styleName = (group, id) => (STYLE_CATALOG[group].find((o) => o.id === id) || {}).name || '—';
// the accent is a free colour, not a named entry in a list — it names itself
const accentName = (hex) => String(hex || ACCENT_DEFAULT).toUpperCase();
const normHex = (v) => {
  let s = String(v || '').trim().replace(/^#/, '');
  if (/^[0-9a-f]{3}$/i.test(s)) s = s.split('').map((c) => c + c).join(''); // #abc → #aabbcc
  return /^[0-9a-f]{6}$/i.test(s) ? `#${s.toLowerCase()}` : null;
};

/* Which styles actually paint the accent. Kept as data because the honest UI
 * note depends on it: with `karaoke` + `outline` picked, nothing on screen uses
 * the colour, and saying so beats letting the user wonder why the previews did
 * not move. Mirrors the template — update both together. */
const ACCENT_USERS = {headlines: ['realce', 'misto'], captions: ['stacked']};
/* AVELIN-OVERLAY */ if (window.AVELIN_LOCAL) window.AVELIN_LOCAL.install({STYLE_CATALOG, CAP_BUILDERS, ACCENT_USERS});
const ACCENT_DEFAULT = '#ff5200';

function applyAccent() {
  $('layersPanel').style.setProperty('--hl-accent', S.style.accent || ACCENT_DEFAULT);
}

/* One spectral swatch (the OS picker) plus a hex field — no preset row. A grid of
 * canned colours competes with the style cards for attention and still never has
 * the brand colour the user actually wants. */
/* O MESMO widget para as duas cores. Generalizado por parâmetro em vez de
 * copiado: o par de campos (roda do sistema + hexa, sincronizados nos dois
 * sentidos) tem sutileza suficiente — não brigar com quem digita no meio da
 * tecla — para que duas cópias divergissem na primeira correção. */
function renderColor(hostId, key, fallback, label) {
  const host = $(hostId);
  if (!host) return;
  host.innerHTML = '';
  const cur = normHex(S.style[key]) || fallback;

  const custom = el('label', 'swatch custom', host);
  custom.title = 'Escolher cor';
  custom.style.setProperty('--swatch-fill', cur);
  const inp = el('input', '', custom);
  inp.type = 'color';
  inp.value = cur;

  const field = el('div', 'hex-field', host);
  el('span', 'hex-hash', field).textContent = '#';
  const hex = el('input', 'hex-input', field);
  hex.type = 'text';
  hex.spellcheck = false;
  hex.maxLength = 7;
  hex.value = cur.slice(1).toUpperCase();
  hex.setAttribute('aria-label', `${label} em hexadecimal`);

  const commit = (v, {fromHexField} = {}) => {
    const n = normHex(v);
    if (!n) return false;
    S.style[key] = n;
    custom.style.setProperty('--swatch-fill', n);
    inp.value = n;
    if (!fromHexField) hex.value = n.slice(1).toUpperCase();
    applyAccent();   // live — no full rebuild, so dragging the picker stays smooth
    updateAccentNote();
    updateSummary();
    LIVE.key = null; renderLive();   // a legenda sobre o vídeo segue a cor na hora
    return true;
  };

  inp.addEventListener('input', () => commit(inp.value));
  // typing: accept as soon as it parses, but never fight the user mid-keystroke
  hex.addEventListener('input', () => {
    field.classList.toggle('bad', !normHex(hex.value) && hex.value.trim() !== '');
    commit(hex.value, {fromHexField: true});
  });
  // leaving an unparseable value snaps back rather than silently keeping the old
  // colour behind text that says something else
  hex.addEventListener('blur', () => {
    field.classList.remove('bad');
    hex.value = (normHex(S.style.accent) || ACCENT_DEFAULT).slice(1).toUpperCase();
  });
  hex.addEventListener('keydown', (e) => { if (e.key === 'Enter') hex.blur(); });

  updateAccentNote();
}

function renderAccents() {
  renderColor('optAccent', 'accent', ACCENT_DEFAULT, 'Cor de destaque');
  renderColor('optCapColor', 'capColor', '#FFFFFF', 'Cor principal da legenda');
}

const accentUsed = () =>
  ACCENT_USERS.headlines.includes(S.style.headline)
  || ACCENT_USERS.captions.includes(S.style.captions);

function updateAccentNote() {
  const where = [
    ACCENT_USERS.headlines.includes(S.style.headline) && 'na headline',
    ACCENT_USERS.captions.includes(S.style.captions) && 'na legenda',
  ].filter(Boolean);
  const n = $('accentNote');
  if (!n) return; // as linhas ainda não foram montadas — nada a atualizar
  n.textContent = where.length
    ? `aplicada ${where.join(' e ')}`
    : 'os estilos escolhidos não usam destaque';
}

/* Separate from renderSetup so the live colour drag can refresh it without
 * rebuilding every demo. Skipping it there left the footer naming the previous
 * colour while the previews already showed the new one. */
function updateSummary() {
  const box = $('setupSummary');
  if (!box) return;   // o resumo saiu da tela — nada a escrever
  const on = STYLE_CATALOG.elements.filter((e) => S.style.elements[e.id]);
  const accentBit = accentUsed() ? ` · destaque ${accentName(S.style.accent)}` : '';
  box.textContent =
    `${styleName('edits', S.style.edit)} · headline ${styleName('headlines', S.style.headline)}` +
    ` · legenda ${styleName('captions', S.style.captions)}${accentBit} · ` +
    (on.length ? on.map((e) => e.name).join(', ') : 'sem elementos extras');
}

/* CAMADAS DO RENDER — as escolhas de estilo, agrupadas pelo que elas MEXEM no
 * vídeo em vez de por qual widget as controla.
 *
 * O agrupamento antigo era o do catálogo: "tipo de edição", "estilo de
 * headline", "estilo de legenda", "elementos". Isso descreve o formato do dado,
 * não o ofício — e obrigava a varrer quatro blocos para responder "o que tem de
 * texto neste vídeo?". Aqui cada linha é uma camada do render, e os controles
 * que a afetam moram dentro dela, venham de onde vierem no catálogo.
 *
 * Uma linha sem controle NENHUM ainda aparece, com o motivo escrito. Some-la
 * faria o painel prometer que a lista está completa. */
const LAYERS = [
  { id: 'elementos', name: 'Elementos visuais', sub: 'Figurinhas, imagens, formas e gráficos',
    ico: 'inserts', groups: ['edits'] },
  { id: 'headline', name: 'Headline', sub: 'O título fixo sobre a imagem',
    ico: 'text', headlineText: true, groups: ['headlines'] },
  { id: 'legendas', name: 'Legendas', sub: 'Estilo, cor principal e cor de destaque',
    ico: 'captions', colors: true, groups: ['captions'] },
  { id: 'movimento', name: 'Movimento & tracking', sub: 'Animações, máscaras, rastreamento e keyframes',
    ico: 'video', elements: ['tracking', 'zoomAuto', 'zoomCuts'] },
  { id: 'transicoes', name: 'Transições', sub: 'Cortes, fades e transições entre clipes',
    ico: 'notes', elements: ['flashCut'] },
  { id: 'trilha', name: 'Trilha & mixagem', sub: 'Áudio, níveis, ducking e mixagem final',
    ico: 'music', elements: ['musicAI'] },
];

const GROUP_TITLE = { edits: 'Tipo de edição', headlines: 'Estilo de headline', captions: 'Estilo de legenda' };
/* Uma camada por vez, num INSPETOR de altura fixa — o modelo de NLE.
 * O acordeão anterior crescia para dentro do layout: cada clique mudava a
 * altura do painel e empurrava a linha do tempo e o preview. Trocar de camada
 * não é redimensionar a mesa de trabalho. Aqui a área não muda de tamanho
 * nunca; só muda o que está dentro dela. */
let activeLayer = 'elementos';

let wasShowing = false; // painel estava aberto no render anterior (para o re-fit)

/* Quais camadas o painel oferece. Antes o portão era uma tela cheia com
 * `S.tab === 'style'`; agora ele vive DENTRO da Finalização, então a condição
 * deixou de ser "que aba" e passou a ser "este trabalho tem estilo a escolher". */
const setupApplies = () => !!(S.state.awaitingStyle || S.state.style);

function renderSetup() {
  const show = setupApplies();
  $('layersPanel').classList.toggle('hidden', !show);
  const hasVideo = S.videoDuration > 0;
  $('stage').classList.toggle('hidden', !hasVideo);
  $('emptyState').classList.toggle('hidden', hasVideo);

  if (!show) {
    capAnims = []; // para de animar demos que não estão na tela
    if (wasShowing && hasVideo) requestAnimationFrame(() => { fitZoom(); renderAll(); });
    wasShowing = false;
    return;
  }
  wasShowing = true;

  // O texto no HTML é só o estado inicial — quem manda é esta linha, e foi por
  // isso que trocar o rótulo no HTML sozinho não teve efeito nenhum.
  $('setupGo').textContent = S.state.awaitingStyle ? 'Visualizar' : 'Refazer';
  $('setupGo').title = S.state.awaitingStyle
    ? 'Monta a finalização com estas escolhas'
    : 'Refaz a finalização com as escolhas atuais';

  buildLayerRows();
  capAnims = [];
  const radios = (host, group, chosen) => {
    const opts = STYLE_CATALOG[group];
    host.innerHTML = '';
    for (const o of opts) {
      // Estilos ainda não portados para o HyperFrames aparecem apagados e não
      // clicáveis, em vez de sumirem: esconder faria a aba mentir sobre o que o
      // produto vai ser, e escolher um deles levaria a um beco sem saída na
      // hora de renderizar.
      const off = PORTED[group] && !PORTED[group].has(o.id);
      const card = el('div', `opt${o.id === chosen ? ' on' : ''}${off ? ' unavailable' : ''}`, host);
      card.dataset.group = group;
      card.dataset.id = o.id;
      if (off) card.title = 'ainda não disponível';
      // headline previews are two short lines — they do not need the caption
      // box's height, and with four groups on one screen that height is scarce
      const kind = o.mock ? 'frame' : o.hl ? 'cap hlbox' : 'cap';
      const prev = el('div', `opt-preview ${kind}`, card);
      if (o.demo) capAnims.push(CAP_BUILDERS[o.demo](prev));
      else if (o.hl) buildHeadlineDemo(prev, o.hl);
      else if (o.stat) {
        const step = buildStaticDemo(prev, o.stat);
        if (step) capAnims.push(step);
      }
      else prev.innerHTML = o.mock || '';
      // Only the abstract mockups get a title. A card that renders the real
      // caption or the real headline is already labelled — by itself.
      if (o.mock) el('div', 'opt-name', card).textContent = o.name;
      el('div', 'opt-mark', card);
    }
    // the ghost only earns its space where there is a single option to explain
    if (opts.length < 2) el('div', 'opt ghost', host).textContent = 'mais estilos em breve';
  };
  // set BEFORE the demos are built: buildHeadlineDemo reads the accent through
  // var(), so the variable has to be in place when the previews first paint
  applyAccent();

  const chosen = { edits: S.style.edit, headlines: S.style.headline, captions: S.style.captions };
  for (const L of LAYERS) {
    for (const g of L.groups || []) {
      const host = $(`opt-${g}`);
      if (host) radios(host, g, chosen[g]);
    }
    const eh = $(`optEl-${L.id}`);
    if (!eh) continue;
    eh.innerHTML = '';
    for (const id of L.elements) {
      const e = STYLE_CATALOG.elements.find((x) => x.id === id);
      if (!e) continue;
      const on = !!S.style.elements[e.id];
      const row = el('div', `chk${on ? ' on' : ''}`, eh);
      row.dataset.id = e.id;
      el('div', 'chk-box', row);
      el('div', 'chk-ico', row).innerHTML = e.icon || '';
      el('div', 'chk-name', row).textContent = e.name;
    }
  }
  renderAccents();
  refreshLayerSummaries();
  updateSummary();
  LIVE.key = null; // o estilo pode ter mudado — força o redesenho da prévia
  renderLive();
}

/* Monta a faixa de camadas e o corpo do inspetor. Reconstrói do zero a cada
 * render porque o estado que ele mostra (o que está escolhido) vive em S.style,
 * não no DOM — um diff incremental aqui só criaria uma segunda fonte de verdade.
 * O que sobrevive é `activeLayer`: qual camada está aberta é decisão do usuário. */
function buildLayerRows() {
  const tabs = $('layerTabs');
  const body = $('layerBody');
  tabs.innerHTML = '';
  body.innerHTML = '';

  for (const L of LAYERS) {
    const chip = el('button', `layer-chip${L.id === activeLayer ? ' on' : ''}`, tabs);
    chip.type = 'button';
    chip.dataset.layer = L.id;
    chip.title = L.sub;
    el('span', 'layer-ico', chip).innerHTML = ICON[L.ico] || '';
    el('span', 'layer-chip-name', chip).textContent = L.name;
    el('span', 'layer-chip-sum', chip).id = `sum-${L.id}`;
  }

  const L = LAYERS.find((x) => x.id === activeLayer) || LAYERS[0];
  if (L.soon) { el('div', 'layer-soon', body).textContent = L.soon; return; }

  if (L.headlineText) {
    /* A headline é a única escolha desta tela que é CONTEÚDO, não estilo — e
       por isso ela nunca coube num catálogo de cartões. Quem escreve é o
       usuário; os cartões abaixo só decidem como ela é pintada. */
    const g = el('div', 'setup-group', body);
    el('span', 'group-title', el('div', 'group-head', g)).textContent = 'Texto da headline';
    const ta = el('textarea', 'hl-text', g);
    ta.id = 'headlineText';
    ta.rows = 2;
    ta.placeholder = 'Ex.: 3 respostas dizem se você está na carreira certa';
    ta.value = S.style.headlineText || '';
  }

  if (L.colors) {
    /* DUAS cores, e a distinção importa: a principal é o corpo da legenda (era
       branco cravado na folha), a de destaque é a que pinta a palavra realçada
       — e ela é a MESMA da headline, porque um vídeo com dois laranjas
       diferentes não lê como um vídeo, lê como um erro. */
    const g = el('div', 'setup-group', body);
    const h = el('div', 'group-head', g);
    el('span', 'group-title', h).textContent = 'Cores';
    el('span', 'group-note', h).id = 'accentNote';
    const row = el('div', 'color-row', g);
    const main = el('div', 'color-slot', row);
    el('span', 'color-lab', main).textContent = 'principal';
    el('div', 'swatches', main).id = 'optCapColor';
    const acc = el('div', 'color-slot', row);
    el('span', 'color-lab', acc).textContent = 'destaque';
    el('div', 'swatches', acc).id = 'optAccent';
  }

  for (const gid of L.groups || []) {
    const g = el('div', 'setup-group', body);
    el('span', 'group-title', el('div', 'group-head', g)).textContent = GROUP_TITLE[gid] || gid;
    el('div', 'opt-grid', g).id = `opt-${gid}`;
  }
  if (L.elements) el('div', 'check-row', body).id = `optEl-${L.id}`;
}

/* O resumo no chip. Sem ele a faixa vira seis botões iguais e o usuário precisa
 * visitar todos para lembrar o que decidiu. */
function refreshLayerSummaries() {
  for (const L of LAYERS) {
    const n = $(`sum-${L.id}`);
    if (!n) continue;
    if (L.soon) { n.textContent = 'em breve'; continue; }
    const bits = [];
    for (const g of L.groups || []) bits.push(styleName(g, { edits: S.style.edit, headlines: S.style.headline, captions: S.style.captions }[g]));
    if (L.elements) {
      const on = L.elements.filter((id) => S.style.elements[id]);
      bits.push(on.length ? `${on.length} ativo${on.length === 1 ? '' : 's'}` : 'desligado');
    }
    n.textContent = bits.filter(Boolean).join(' · ');
  }
}

$('layersPanel').addEventListener('click', (e) => {
  // the accent controls manage themselves (live, no rebuild) — keep the card
  // handler off them, or a click in the hex field would count as a style pick
  if (e.target.closest('#optAccent')) return;

  // acordeão mestre: recolhe o painel inteiro e devolve a altura para a timeline
  if (e.target.closest('#layersToggle')) {
    const wrap = $('layersPanel');
    wrap.classList.toggle('collapsed');
    // a timeline acabou de ganhar (ou perder) altura — reajusta a escala nela
    requestAnimationFrame(() => { fitZoom(); renderAll(); });
    return;
  }

  // abre/fecha a camada. Vem ANTES dos controles: o cabeçalho é um <button> e
  // engoliria o clique de qualquer forma, mas a ordem explícita evita que um
  // controle futuro colocado no cabeçalho passe a alternar a linha sem querer.
  const chip = e.target.closest('.layer-chip');
  if (chip) {
    activeLayer = chip.dataset.layer;
    renderSetup();
    return;
  }

  const opt = e.target.closest('.opt:not(.ghost):not(.unavailable)');
  if (opt) {
    const key = {edits: 'edit', headlines: 'headline', captions: 'captions'}[opt.dataset.group];
    S.style[key] = opt.dataset.id;
    renderSetup();
    return;
  }
  const chk = e.target.closest('.chk:not(.layer-chip)');
  if (chk) {
    S.style.elements[chk.dataset.id] = !S.style.elements[chk.dataset.id];
    renderSetup();
  }
});

document.addEventListener('input', (e) => {
  if (e.target && e.target.id === 'headlineText') S.style.headlineText = e.target.value;
});

$('setupGo').addEventListener('click', async () => {
  S.style.note = $('setupNote').value.trim();
  const rerender = !S.state.awaitingStyle;
  const payload = {
    // a save with Fase 2 already on disk is a RE-RENDER request, not a first
    // pick — the skill has to know which of the two it is looking at
    type: 'style-setup',
    rerender,
    edit: S.style.edit,
    editName: styleName('edits', S.style.edit),
    headline: S.style.headline,
    headlineName: styleName('headlines', S.style.headline),
    captions: S.style.captions,
    captionsName: styleName('captions', S.style.captions),
    accent: S.style.accent,
    accentName: accentName(S.style.accent),
    capColor: S.style.capColor || '#FFFFFF',
    headlineText: (S.style.headlineText || '').trim(),
    // whether the picked styles actually paint it — so the skill does not go
    // hunting for an accent in a look that has none
    accentUsed: accentUsed(),
    elements: { ...S.style.elements },
    elementNames: STYLE_CATALOG.elements
      .filter((e) => S.style.elements[e.id])
      .map((e) => e.name),
    note: S.style.note,
  };
  const res = await fetch('/api/save', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if ((await res.json()).ok) {
    renderSetup();
    toast(rerender
      ? '✓ Novo estilo enviado — o Claude vai refazer a finalização com ele'
      : '✓ Estilo enviado — o Claude vai montar a finalização com essas escolhas', 5000);
  } else {
    toast('Erro ao enviar — o servidor está de pé?', 4000);
  }
});

// Declarado ANTES de renderClips porque ela lê o arrasto em curso para
// congelar o trecho sendo aparado; um `let` depois do primeiro uso cai na
// zona morta temporal e derruba a primeira renderização.
let drag = null; // {type:'scrub'|'trim'|'chip-trim'|'chip-move', ...}

function renderClips() {
  laneVideo.innerHTML = '';
  const trimming = drag && drag.type === 'trim' ? drag.i : null;
  const dl = draftLayout(trimming);
  const rl = renderedLayout();
  const editable = true;
  dl.forEach((r, i) => {
    if (r.removed && r.dur === 0) {
      // removed: show a slim ghost at its slot
      const g = el('div', 'clip removed', laneVideo);
      g.style.left = `${r.out * S.pps}px`;
      g.style.width = `${Math.max((r.orig.end - r.orig.start) * S.pps * 0.4, 34)}px`;
      g.dataset.i = i;
      g.title = 'clique e pressione delete para restaurar';
      return;
    }
    const c = el('div', 'clip', laneVideo);
    c.style.left = `${r.out * S.pps}px`;
    c.style.width = `${Math.max(r.dur * S.pps, 8)}px`;
    c.dataset.i = i;
    if (i === S.selected) c.classList.add('selected');
    if (r.start !== r.orig.start || r.end !== r.orig.end) c.classList.add('dirty');

    // Enquanto este trecho está sendo aparado, ele fica no tamanho antigo e o
    // que sai aparece escurecido nas pontas — assim a alça acompanha o cursor
    // em vez de a outra borda se mexer.
    if (i === trimming) {
      const head = (r.start - r.orig.start) * S.pps;
      const tail = (r.orig.end - r.end) * S.pps;
      if (head > 0.5) {
        const g = el('div', 'trim-cut', c);
        g.style.left = '0px';
        g.style.width = `${head}px`;
      }
      if (tail > 0.5) {
        const g = el('div', 'trim-cut', c);
        g.style.right = '0px';
        g.style.width = `${tail}px`;
      }
    }

    // filmstrip from the rendered cut
    if (S.thumbCount > 0 && rl[i]) {
      const strip = el('div', 'thumbs', c);
      const first = Math.floor(rl[i].out / THUMB_EVERY);
      const n = Math.ceil(rl[i].dur / THUMB_EVERY) + 1;
      for (let k = 0; k < n; k++) {
        const idx = first + k + 1; // ffmpeg %04d is 1-based
        if (idx > S.thumbCount) break;
        const img = el('img', '', strip);
        img.src = `/gen/thumbs/${String(idx).padStart(4, '0')}.jpg`;
        img.style.width = `${THUMB_EVERY * S.pps}px`;
        img.style.objectFit = 'cover';
      }
    }
    const lab = el('div', 'clip-label', c);
    lab.textContent = `${r.beat || r.source} `;
    const dur = el('div', 'clip-dur', c);
    dur.textContent = `${r.dur.toFixed(2)}s`;

    if (editable) {
      const hl = el('div', 'handle l', c); hl.dataset.i = i;
      const hr = el('div', 'handle r', c); hr.dataset.i = i;
      // no trecho congelado a alça senta na BORDA DO CORTE, não na do bloco —
      // é ela que tem que acompanhar o cursor
      if (i === trimming) {
        hl.style.left = `${(r.start - r.orig.start) * S.pps}px`;
        hr.style.right = `${(r.orig.end - r.end) * S.pps}px`;
      }
    }
  });
}

/* J-cut audio lanes.
 * The point is legibility, not decoration: on one lane an overlap is invisible,
 * because two blocks that overlap in time just look like one continuous block.
 * Alternating takes across A1/A2 is what makes the "J" readable — exactly how it
 * reads in Premiere. The overlap itself gets a marker on the incoming block, so
 * the user can see how many frames of voice arrive before the picture.
 */
function renderJcutAudio() {
  const t1 = $('trkAudioA1'), t2 = $('trkAudioA2');
  const l1 = $('laneAudioA1'), l2 = $('laneAudioA2');
  const btn = $('jcutToggle');
  l1.innerHTML = ''; l2.innerHTML = '';

  const has = !!(S.jcut && S.jcut.length);
  // the caret only appears when there is a J-cut to expand; otherwise the chip
  // stays an ordinary track icon
  btn.classList.toggle('disclose', has);
  btn.disabled = !has;
  btn.setAttribute('aria-expanded', String(has && S.jcutOpen));
  btn.title = !has ? 'Áudio (mix)'
    : S.jcutOpen ? 'Áudio (mix) — recolher as faixas do J-cut (A1/A2)'
                 : 'Áudio (mix) — expandir as faixas do J-cut (A1/A2)';

  const on = has && S.jcutOpen;
  t1.classList.toggle('hidden', !on);
  t2.classList.toggle('hidden', !on);
  if (!on) return;

  // Desenhadas sobre o layout do RASCUNHO, com o mesmo congelamento da trilha
  // de vídeo. Sem ele o bloco de áudio encolhia pela DIREITA quando a pessoa
  // puxava o início — o corte "andava" para o lado oposto ao que ela mexia.
  const trimming = drag && drag.type === 'trim' ? drag.i : null;
  draftLayout(trimming).forEach((r, i) => {
    if (r.removed && r.adur === 0) return;
    const lane = i % 2 === 0 ? l1 : l2;
    const b = el('div', 'ablock', lane);
    b.style.left = `${r.aout * S.pps}px`;
    b.style.width = `${Math.max(r.adur * S.pps, 6)}px`;
    el('div', 'ablock-label', b).textContent = r.beat || r.source || '';

    // o que sai do áudio, escurecido na ponta em que está saindo
    if (i === trimming) {
      const head = (r.start - r.orig.start) * S.pps;
      const tail = (r.orig.end - r.end) * S.pps;
      if (head > 0.5) {
        const g = el('div', 'trim-cut', b);
        g.style.left = '0px';
        g.style.width = `${head}px`;
      }
      if (tail > 0.5) {
        const g = el('div', 'trim-cut', b);
        g.style.right = '0px';
        g.style.width = `${tail}px`;
      }
    }

    // the lead: sound already playing while the previous take is still on screen
    if (r.lead > 1e-6) {
      const ov = el('div', 'ablock-lead', b);
      ov.style.width = `${r.lead * S.pps}px`;
    }
    const tf = (S.jcut[i] || {}).tail_trim_frames || 0;
    let tip = `${r.beat || r.source}\náudio ${r.adur.toFixed(2)}s`;
    if (r.lead > 1e-6) {
      tip += `\nJ-cut: ${Math.round(r.lead * S.fps)}f (${Math.round(r.lead * 1000)}ms) `
           + 'de voz antes da imagem';
    }
    if (tf) tip += `\ncauda aparada ${tf}f`;
    b.title = tip;
  });
}

function renderChips() {
  // as pistas aparecem quando existe o que mostrar — a pergunta é sobre o dado
  const phase2 = !!(S.captions.length || S.insertsDraft.length || (S.editData && S.editData.soundtrack));
  $('trkCaptions').classList.toggle('hidden', !phase2);
  insertTracksEl.classList.toggle('hidden', !phase2);
  insertTracksEl.innerHTML = '';
  if (!phase2) return;

  laneCaptions.innerHTML = '';
  for (const c of S.captions) {
    const start = renderedToDraft(c.start);
    const end = renderedToDraft(c.end);
    const chip = el('div', 'chip caption', laneCaptions);
    chip.style.left = `${start * S.pps}px`;
    chip.style.width = `${Math.max((end - start) * S.pps, 6)}px`;
    chip.textContent = c.text;
    chip.title = c.text;
  }

  // TEXT and IMAGE get their own tracks — a headline and a photo are different
  // kinds of edit, and mixing them on one lane hid the images entirely.
  const isText = (c) => c.kind === 'hook' || c.kind === 'word';
  const groups = [
    { icon: 'text', cls: 'blue', name: 'Texto', items: S.insertsDraft.map((c, i) => ({ c, i })).filter(({ c }) => isText(c)) },
    { icon: 'inserts', cls: 'orange', name: 'Elementos', items: S.insertsDraft.map((c, i) => ({ c, i })).filter(({ c }) => !isText(c)) },
  ];

  for (const g of groups) {
    if (!g.items.length) continue;
    // overlapping elements stack onto extra lanes within the same group
    const order = [...g.items].sort((a, b) => a.c.start - b.c.start || a.c.end - b.c.end);
    const trackEnd = [];
    const assign = new Map();
    for (const { c, i } of order) {
      let t = trackEnd.findIndex((end) => c.start >= end - 1e-6);
      if (t < 0) { t = trackEnd.length; trackEnd.push(0); }
      trackEnd[t] = c.end;
      assign.set(i, t);
    }
    const lanes = [];
    const nLanes = Math.max(trackEnd.length, 1);
    for (let t = 0; t < nLanes; t++) {
      const trk = el('div', 'track', insertTracksEl);
      // só a PRIMEIRA pista do grupo carrega ícone e nome; as outras recuam.
      // Repetir o rótulo em cada pista faria quatro elementos empilhados
      // parecerem quatro trilhas diferentes, que é o oposto do que são.
      const lab = el('div', `track-label${t === 0 ? '' : ' cont'}`, trk);
      if (t === 0) {
        el('span', `tl-chip ${g.cls}`, lab).innerHTML = ICON[g.icon];
        const txt = el('span', 'tl-text', lab);
        el('span', 'tl-name', txt).textContent = g.name;
        el('br', '', txt);
        el('span', 'tl-count', txt).textContent = plural(nLanes);
      }
      lanes.push(el('div', 'lane', trk));
    }
    for (const { c, i } of g.items) {
      const chip = el('div', `chip insert ${isText(c) ? 'hook' : ''}`, lanes[assign.get(i) ?? 0]);
      chip.style.left = `${c.start * S.pps}px`;
      chip.style.width = `${Math.max((c.end - c.start) * S.pps, 10)}px`;
      chip.textContent = c.label;
      chip.title = c.label;
      chip.dataset.i = i;
      if (c.start !== c.orig.start || c.end !== c.orig.end) chip.classList.add('dirty');
      el('div', 'handle l', chip).dataset.i = i;
      el('div', 'handle r', chip).dataset.i = i;
    }
  }

  // soundtrack → its own read-only track, one chip spanning the whole video
  const st = S.editData && S.editData.soundtrack;
  if (st && st.enabled) {
    const trk = el('div', 'track', insertTracksEl);
    const lab = el('div', 'track-label', trk);
    el('span', 'tl-chip soft', lab).innerHTML = ICON.music;
    const txt = el('span', 'tl-text', lab);
    el('span', 'tl-name', txt).textContent = 'Trilha';
    el('br', '', txt);
    el('span', 'tl-count', txt).textContent = '1 camada';
    const lane = el('div', 'lane', trk);
    const chip = el('div', 'chip music', lane);
    const dur = S.editData.durationSec || S.videoDuration || draftTotal();
    chip.style.left = '0px';
    chip.style.width = `${Math.max(dur * S.pps, 10)}px`;
    const name = (st.file || 'trilha.mp3').split('/').pop();
    const vol = st.volume != null ? `  ·  vol ${st.volume}` : '';
    chip.textContent = `${name}${vol}`;
    chip.title = chip.textContent;
  }
}

/* ---------- PRÉVIA AO VIVO ----------
 *
 * A legenda desenhada sobre o vídeo com as folhas de `assets/styles/` — as
 * MESMAS que o render usa, servidas em /styles/. Não é economia de código: uma
 * cópia no editor começaria idêntica e divergiria na primeira correção feita de
 * um lado só, e o SKILL.md já registra "uma prévia que mente sobre o estilo é
 * pior que nenhuma prévia" como anti-padrão recorrente.
 *
 * As folhas foram autoradas para isto: tudo em coordenadas de referência de
 * 1080px de largura, multiplicado por `--cap-scale`. Aqui o fator é
 * `largura em tela / 1080`; na composição é 1. Nenhum dos dois lados redefine
 * medida — só o fator.
 *
 * O que ela NÃO promete: o render continua sendo a palavra final. Tela dividida,
 * elemento atrás do sujeito e trilha não aparecem aqui, e a legenda cai numa
 * deixa de exemplo enquanto a Fase 2 não tiver gerado as de verdade. A tarja
 * embaixo avisa quando é exemplo — uma prévia que não conta que está inventando
 * é exatamente a mentira que ela existe para evitar. */
const LIVE = { variants: null, css: new Set(), key: null };

const CAP_CSS = {
  karaoke: 'karaoke.css', simples: 'static.css', serifada: 'static.css',
  classica: 'static.css', stacked: 'stacked.css', scatter: 'scatter.css',
};

function liveCss(file) {
  if (!file || LIVE.css.has(file)) return;
  LIVE.css.add(file);
  const l = document.createElement('link');
  l.rel = 'stylesheet';
  l.href = `/styles/${file}`;
  document.head.appendChild(l);
}

/* A caixa segue o retângulo do VÍDEO, não o da moldura. O vídeo é contido
   dentro dela e sobra barra dos lados; medir a moldura poria a legenda fora da
   imagem — e o erro cresce com o quanto a janela é mais larga que o clipe. */
function syncOverlay() {
  const ov = $('liveOverlay');
  const frame = video.parentElement;
  if (!ov || !frame || !video.videoWidth) return 0;
  const fr = frame.getBoundingClientRect();
  const vr = video.getBoundingClientRect();
  ov.style.left = `${vr.left - fr.left}px`;
  ov.style.top = `${vr.top - fr.top}px`;
  ov.style.width = `${vr.width}px`;
  ov.style.height = `${vr.height}px`;
  return vr.width;
}

/* A deixa visível AGORA. Com a Fase 2 pronta usa as legendas de verdade; antes
   disso devolve um exemplo fixo, porque um quadro vazio não deixa comparar
   estilo nenhum. */
const SAMPLE_WORDS = 'a sua legenda aparece exatamente assim no vídeo'.split(' ');

function liveCue(t, v) {
  if (S.captions && S.captions.length) {
    const c = S.captions.find((x) => t >= renderedToDraft(x.start) && t < renderedToDraft(x.end));
    return c ? { text: c.text, sample: false } : null;
  }
  // O exemplo respeita o `maxWords` DO ESTILO. Uma frase de tamanho fixo faz o
  // karaokê (3 palavras) transbordar o quadro e a clássica parecer curta — e aí
  // a prévia estaria mentindo sobre a única coisa que ela existe para mostrar.
  // `maxWords` é teto de PALAVRAS; `lines` é teto de LINHAS. O empilhado tem
  // uma palavra por linha, então quem manda nele é `lines` — sem isso o exemplo
  // vira uma coluna de oito palavras que desce para fora do quadro.
  const cap = LIVE.stackedLike ? (v.lines || 3) : (v.maxWords || 3);
  const n = Math.max(2, Math.min(cap, SAMPLE_WORDS.length));
  return { text: SAMPLE_WORDS.slice(0, n).join(' '), sample: true };
}

function renderLive() {
  const ov = $('liveOverlay');
  if (!ov) return;
  const on = setupApplies() && video.videoWidth > 0;
  ov.classList.toggle('hidden', !on);
  if (!on) { LIVE.key = null; return; }

  const w = syncOverlay();
  if (!w) return;
  const id = (S.style && S.style.captions) || 'karaoke';
  const v = (LIVE.variants && LIVE.variants.styles && LIVE.variants.styles[id]) || {};
  liveCss(CAP_CSS[id]);

  LIVE.stackedLike = (id === 'stacked');
  const cue = liveCue(renderedToDraft(video.currentTime || 0), v);
  if (!cue) { ov.innerHTML = ''; LIVE.key = null; return; }

  // remonta só quando a deixa, o estilo ou a largura mudam — a cada quadro
  // seria refazer o DOM 60 vezes por segundo para escrever o mesmo texto
  const key = `${id}|${cue.text}|${Math.round(w)}`;
  if (key === LIVE.key) return;
  LIVE.key = key;

  ov.innerHTML = '';
  const sc = w / 1080;
  const words = cue.text.split(/\s+/);

  /* CADA ESTILO TEM MARCAÇÃO PRÓPRIA, e é por isso que existe um ramo por
     estilo em vez de uma caixa genérica com a fonte trocada. O empilhado é uma
     PILHA de linhas com quatro papéis tipográficos alternados; o disperso são
     palavras soltas com uma destacada. Desenhar os dois como uma faixa
     centralizada carregaria a fonte certa e mostraria um estilo que não existe
     — que é a mentira que esta prévia existe para não contar. */
  if (id === 'stacked') {
    const box = el('div', 'ave-stacked', ov);
    box.style.setProperty('--stk-scale', sc);
    box.style.setProperty('--stk-orange', S.style.accent || ACCENT_DEFAULT);
    const cueEl = el('div', 'stk-cue', box);
    // s0 s1 s2 s3 é a rotação de papéis do estilo: itálico pesado, contorno,
    // serifada no accent, seminegrito
    words.forEach((word, i) => {
      const line = el('div', 'stk-line', cueEl);
      // O corpo é por PALAVRA neste estilo (vem do caption-cues.json que o
      // diretor prepara). Sem esse dado a prévia usa o corpo base do estilo —
      // a hierarquia entre palavras é o que ela não tem como adivinhar.
      line.style.fontSize = `${(v.size || 86) * sc}px`;
      const sp = el('span', `s${i % 4}`, line);
      sp.textContent = word;
      sp.style.opacity = 1; // a folha nasce em 0 porque quem anima é o render
    });
  } else if (id === 'scatter') {
    const box = el('div', 'ave-scatter', ov);
    box.style.setProperty('--scat-scale', sc);
    if (v.size) box.style.setProperty('--scat-size', v.size);
    const cueEl = el('div', 'scat-cue', box);
    box.style.setProperty('--scat-scale', sc);
    /* AGRUPAMENTO IGUAL AO DO COMPOSITOR: 3 ou 4 palavras por linha, e a
       destacada — a mais longa — sozinha na linha dela. Uma palavra por linha
       (como estava) transforma o disperso numa COLUNA que desce pelo quadro
       inteiro e transborda; o estilo é feito de linhas curtas e irregulares,
       não de uma pilha. */
    let hi = 0;
    words.forEach((word, i) => { if (word.length > words[hi].length) hi = i; });
    const lines = [];
    let cur = [];
    words.forEach((word, i) => {
      if (i === hi) {
        if (cur.length) lines.push(cur);
        lines.push([[word, true]]);
        cur = [];
        return;
      }
      cur.push([word, false]);
      if (cur.length >= (i % 2 ? 4 : 3)) { lines.push(cur); cur = []; }
    });
    if (cur.length) lines.push(cur);
    for (const ln of lines) {
      const lineEl = el('div', 'scat-line', cueEl);
      for (const [word, isHi] of ln) {
        const sp = el('span', isHi ? 'hi' : '', lineEl);
        sp.textContent = word;
        sp.style.opacity = 1; // a folha nasce em 0 porque quem anima é o render
      }
    }
  } else if (id === 'karaoke') {
    const box = el('div', 'ave-cap', ov);
    box.style.setProperty('--cap-scale', sc);
    box.style.setProperty('--cap-color', S.style.capColor || '#fff');
    if (v.size) box.style.setProperty('--cap-size', v.size);
    const line = el('div', 'ave-cap-line', box);
    for (const word of words) el('span', '', line).textContent = word;
  } else {
    const box = el('div', 'ave-cap-static', ov);
    box.style.setProperty('--cap-scale', sc);
    if (v.size) box.style.setProperty('--cap-size', v.size);
    if (v.tracking != null) box.style.setProperty('--cap-track', v.tracking);
    if (v.sx != null) box.style.setProperty('--cap-sx', v.sx);
    if (v.sy != null) box.style.setProperty('--cap-sy', v.sy);
    if (v.cssFamily) box.style.setProperty('--cap-family', v.cssFamily);
    if (v.weight) box.style.setProperty('--cap-weight', v.weight);
    box.style.setProperty('--cap-color', S.style.capColor || '#fff');
    el('div', 'ave-cue', box).textContent = cue.text;
  }
}

// ---------- canvases (viewport-sized, redrawn on scroll) ----------
function canvasSetup(cv, lane) {
  const dpr = window.devicePixelRatio || 1;
  const w = panel.clientWidth;
  const h = lane.clientHeight;
  cv.width = w * dpr;
  cv.height = h * dpr;
  cv.style.width = `${w}px`;
  cv.style.height = `${h}px`;
  cv.style.position = 'absolute';
  // lanes start LABEL_W into the scrolled content — offset the viewport-sized
  // canvas so it covers exactly the visible strip of the lane
  const left = Math.max(0, panel.scrollLeft - LABEL_W);
  cv.style.left = `${left}px`;
  const ctx = cv.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  return { ctx, w, h, x0: left };
}

function drawRuler() {
  const { ctx, w, h, x0 } = canvasSetup(rulerCv, rulerCv.parentElement);
  const laneX0 = x0; // canvas positioned at scrollLeft within lane coords
  const t0 = laneX0 / S.pps;
  const t1 = (laneX0 + w) / S.pps;
  // tick step: nice value ≥ 60px apart
  const steps = [0.1, 0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120];
  const step = steps.find((s) => s * S.pps >= 56) || 300;
  ctx.font = "600 9.5px 'Inter', system-ui, sans-serif";
  ctx.fillStyle = tokA('--blue-rgb', 0.9);
  ctx.strokeStyle = 'rgba(255,255,255,0.14)';
  for (let t = Math.floor(t0 / step) * step; t <= t1; t += step) {
    if (t < 0) continue;
    const x = t * S.pps - laneX0;
    ctx.beginPath();
    ctx.moveTo(x, h - 7);
    ctx.lineTo(x, h);
    ctx.stroke();
    ctx.fillText(fmt(t), x + 3, h - 9);
    // minor ticks
    const minor = step / 5;
    for (let m = 1; m < 5; m++) {
      const xm = (t + m * minor) * S.pps - laneX0;
      ctx.beginPath();
      ctx.moveTo(xm, h - 3.5);
      ctx.lineTo(xm, h);
      ctx.stroke();
    }
  }
}

function drawWave() {
  if (!S.wave) return;
  const { ctx, w, h, x0 } = canvasSetup(waveCv, laneAudio);
  const mid = h / 2;
  ctx.strokeStyle = tokA('--orange-soft-rgb', 0.06);
  ctx.beginPath(); ctx.moveTo(0, mid); ctx.lineTo(w, mid); ctx.stroke();
  ctx.fillStyle = tokA('--orange-soft-rgb', 0.75);
  const pps = S.wave.peaksPerSec;
  for (let px = 0; px < w; px++) {
    const tDraft = (x0 + px) / S.pps;
    if (tDraft > draftTotal()) break;
    const tRend = draftToRendered(tDraft);
    const idx = Math.floor(tRend * pps);
    if (idx < 0 || idx >= S.wave.max.length) continue;
    const hi = (S.wave.max[idx] / 100) * (mid - 2);
    const lo = (S.wave.min[idx] / 100) * (mid - 2);
    ctx.fillRect(px, mid - hi, 1, Math.max(1, hi - lo));
  }
}

// Vertical sources get the split layout (player right, editor left) — stacked,
// a 9:16 clip is tiny above a full-width timeline. Driven off the decoded frame
// size, so it works for cut.mp4 and the Phase-2 render alike.
function applyOrientation() {
  const w = video.videoWidth;
  const h = video.videoHeight;
  if (!w || !h) return;
  const portrait = h > w;
  // o formato sai do quadro DECODIFICADO, não de um campo no state: é o mesmo
  // número que decide o layout, então os dois nunca podem discordar
  const fmt = $('layersFmt');
  if (fmt) {
    const g = (a, b) => (b ? g(b, a % b) : a);
    const d = g(w, h) || 1;
    fmt.textContent = `formato detectado · ${w / d}:${h / d}`;
  }
  if (portrait === document.body.classList.contains('portrait')) return;
  document.body.classList.toggle('portrait', portrait);
  // the timeline's width just changed — re-fit after layout settles
  requestAnimationFrame(() => { fitZoom(); renderAll(); });
}
video.addEventListener('loadedmetadata', applyOrientation);

// ---------- needle / playback sync ----------
function positionNeedle() {
  const tDraft = renderedToDraft(video.currentTime || 0);
  const x = LABEL_W + tDraft * S.pps;
  needle.style.left = `${x}px`;
  needle.style.visibility = x < panel.scrollLeft + LABEL_W ? 'hidden' : '';
  $('timeNow').textContent = fmt(tDraft);
  $('timeTotal').textContent = fmt(draftTotal() || S.videoDuration);
}
function rafLoop() {
  if (capAnims.length) {
    const now = performance.now() / 1000;
    for (const step of capAnims) step(now);
  }
  positionNeedle();
  renderLive();
  if (!video.paused && !video.ended) {
    // keep needle visible
    const x = LABEL_W + renderedToDraft(video.currentTime) * S.pps;
    const right = panel.scrollLeft + panel.clientWidth;
    if (x > right - 80) panel.scrollLeft = x - panel.clientWidth * 0.25;
  }
  requestAnimationFrame(rafLoop);
}

function seekDraft(tDraft) {
  tDraft = Math.max(0, Math.min(tDraft, draftTotal() || S.videoDuration));
  video.currentTime = draftToRendered(tDraft);
  positionNeedle();
}

// ---------- interactions ----------

panel.addEventListener('pointerdown', (e) => {
  // The gutter is chrome, not timeline. Without this guard a pointerdown on a
  // track icon fell through to the scrub branch below, which both yanked the
  // needle to 0 (the gutter is left of t=0, so it computes a negative time) and
  // called setPointerCapture on the panel — retargeting the following click and
  // swallowing it, so a real click on the A1/A2 disclosure never fired while a
  // programmatic .click() did.
  if (e.target.closest('.track-label') || e.target.closest('button')) return;

  const handle = e.target.closest('.handle');
  const clip = e.target.closest('.clip');
  const chip = e.target.closest('.chip.insert');

  if (handle && clip) {
    const i = +handle.dataset.i;
    drag = { type: 'trim', i, side: handle.classList.contains('l') ? 'l' : 'r', x0: e.clientX, r: { ...S.draft[i] } };
    try { panel.setPointerCapture(e.pointerId); } catch (err) { /* synthetic/touch */ }
    e.preventDefault();
    return;
  }
  if (handle && chip) {
    const i = +handle.dataset.i;
    drag = { type: 'chip-trim', i, side: handle.classList.contains('l') ? 'l' : 'r', x0: e.clientX, c: { ...S.insertsDraft[i] } };
    try { panel.setPointerCapture(e.pointerId); } catch (err) { /* synthetic/touch */ }
    e.preventDefault();
    return;
  }
  if (chip) {
    const i = +chip.dataset.i;
    drag = { type: 'chip-move', i, x0: e.clientX, c: { ...S.insertsDraft[i] } };
    try { panel.setPointerCapture(e.pointerId); } catch (err) { /* synthetic/touch */ }
    e.preventDefault();
    return;
  }
  if (clip) {
    S.selected = +clip.dataset.i;
    renderClips();
    return;
  }
  // background / ruler → scrub
  const rect = timelineEl.getBoundingClientRect();
  const t = (e.clientX - rect.left - LABEL_W) / S.pps;
  drag = { type: 'scrub' };
  seekDraft(t);
  try { panel.setPointerCapture(e.pointerId); } catch (err) { /* synthetic/touch */ }
});

panel.addEventListener('pointermove', (e) => {
  if (!drag) return;
  if (drag.type === 'scrub') {
    const rect = timelineEl.getBoundingClientRect();
    seekDraft((e.clientX - rect.left - LABEL_W) / S.pps);
    return;
  }
  const dt = (e.clientX - drag.x0) / S.pps;

  if (drag.type === 'trim') {
    const r = S.draft[drag.i];
    if (drag.side === 'l') {
      r.start = Math.min(Math.max(0, drag.r.start + dt), r.end - MIN_SEG);
    } else {
      r.end = Math.max(drag.r.end + dt, r.start + MIN_SEG);
      const srcDur = (S.state.sourceDurations || {})[r.source];
      if (srcDur) r.end = Math.min(r.end, srcDur);
    }
    renderClips();
    renderJcutAudio();
    drawWave();
    refreshHeader();
    const d = drag.side === 'l' ? r.start - r.orig.start : r.end - r.orig.end;
    showTooltip(e, `${fmt(r.start)} → ${fmt(r.end)} <span class="delta">(${d >= 0 ? '+' : ''}${d.toFixed(2)}s)</span>`);
  } else if (drag.type === 'chip-trim') {
    const c = S.insertsDraft[drag.i];
    if (drag.side === 'l') c.start = Math.min(Math.max(0, drag.c.start + dt), c.end - 0.15);
    else c.end = Math.max(drag.c.end + dt, c.start + 0.15);
    renderChips();
    refreshHeader();
    showTooltip(e, `${fmt(c.start)} → ${fmt(c.end)}`);
  } else if (drag.type === 'chip-move') {
    const c = S.insertsDraft[drag.i];
    const dur = drag.c.end - drag.c.start;
    c.start = Math.max(0, drag.c.start + dt);
    c.end = c.start + dur;
    renderChips();
    refreshHeader();
    showTooltip(e, `${fmt(c.start)} → ${fmt(c.end)}`);
  }
});

['pointerup', 'pointercancel'].forEach((ev) =>
  panel.addEventListener(ev, () => {
    const wasTrim = drag && drag.type === 'trim';
    drag = null;
    hideTooltip();
    // o rearranjo acontece agora, ao soltar: durante o arrasto o trecho ficava
    // congelado para a alça acompanhar o cursor
    // renderAll: ao soltar, o rearranjo vale para TUDO — vídeo, áudio, régua e
    // largura da linha do tempo, que ficaram congelados durante o arrasto
    if (wasTrim) { renderAll(); refreshHeader(); }
  })
);

// double-click a clip = reset it
laneVideo.addEventListener('dblclick', (e) => {
  const clip = e.target.closest('.clip');
  if (!clip) return;
  const r = S.draft[+clip.dataset.i];
  r.start = r.orig.start; r.end = r.orig.end; r.removed = false;
  renderAll(); refreshHeader();
});

// keyboard
document.addEventListener('keydown', (e) => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
  if (e.key === 'm' || e.key === 'M') {
    e.preventDefault();
    toggleMark();
    return;
  }
  if (e.key === 'Escape' && !$('helpModal').classList.contains('hidden')) {
    toggleHelp(false);
    return;
  }
  if (e.key === '?' || (e.key === '/' && e.shiftKey)) {
    e.preventDefault();
    toggleHelp($('helpModal').classList.contains('hidden'));
    return;
  }
  if (e.key === 'Escape' && S.pendingIn != null) {
    S.pendingIn = null;
    renderNotes();
    toast('IN cancelado', 1600);
    return;
  }
  if (e.code === 'Space') {
    e.preventDefault();
    video.paused ? video.play() : video.pause();
  } else if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
    const step = e.shiftKey ? 1 : 1 / S.fps;
    seekDraft(renderedToDraft(video.currentTime) + (e.key === 'ArrowRight' ? step : -step));
  } else if ((e.key === 'Delete' || e.key === 'Backspace') && S.selected >= 0) {
    const r = S.draft[S.selected];
    r.removed = !r.removed;
    renderAll(); refreshHeader();
  }
});

// transport
$('btnPlay').innerHTML = ICON.play;
$('btnMute').innerHTML = ICON.vol;
$('btnPlay').addEventListener('click', () => {
  video.paused ? video.play() : video.pause();
});
video.addEventListener('play', () => { $('btnPlay').innerHTML = ICON.pause; });
video.addEventListener('pause', () => { $('btnPlay').innerHTML = ICON.play; });
video.addEventListener('ended', () => { $('btnPlay').innerHTML = ICON.play; });
$('btnMute').addEventListener('click', () => {
  video.muted = !video.muted;
  $('btnMute').innerHTML = video.muted ? ICON.mute : ICON.vol;
});
$('zoom').addEventListener('input', (e) => setZoom(+e.target.value));

// ---------- correction markers: button, chips, editor ----------
$('markIcon').innerHTML = ICON.flag;
$('btnZoomIn').innerHTML = ICON.zoomIn;
$('btnZoomOut').innerHTML = ICON.zoomOut;
$('btnFit').innerHTML = ICON.fit;

/* Os botões movem o MESMO estado que a barra deslizante movia — a barra virou
   um input escondido para não duplicar a lógica de ancoragem na agulha, que é
   o que faz o zoom não jogar o usuário para outro trecho do vídeo. */
const zoomStep = (dir) => {
  const z = $('zoom');
  z.value = Math.max(0, Math.min(100, (+z.value || 0) + dir * 12));
  z.dispatchEvent(new Event('input'));
};
$('btnZoomIn').addEventListener('click', () => zoomStep(1));
$('btnZoomOut').addEventListener('click', () => zoomStep(-1));
$('btnMark').addEventListener('click', toggleMark);
$('laneNotes').addEventListener('click', (e) => {
  const chip = e.target.closest('.note-chip');
  if (chip) openNoteEditor(chip.dataset.id, false);
});
$('noteOk').addEventListener('click', () => {
  const n = S.notes.find((x) => x.id === S.editingNote);
  if (n) {
    n.text = $('noteText').value.trim();
    if (!n.text) { toast('Escreva o ajuste desejado', 2000); return; }
  }
  S.editingNote = null;
  $('noteEditor').classList.add('hidden');
  renderNotes();
  refreshHeader();
});
$('noteDelete').addEventListener('click', () => {
  S.notes = S.notes.filter((x) => x.id !== S.editingNote);
  S.editingNote = null;
  $('noteEditor').classList.add('hidden');
  renderNotes();
  refreshHeader();
});
$('noteClose').addEventListener('click', closeNoteEditor);

// ---------- help modal (the old footer hint strip) ----------
function toggleHelp(open) {
  $('helpModal').classList.toggle('hidden', !open);
  $('helpBackdrop').classList.toggle('hidden', !open);
}
$('btnHelp').addEventListener('click', () => toggleHelp($('helpModal').classList.contains('hidden')));
$('helpClose').addEventListener('click', () => toggleHelp(false));
$('helpBackdrop').addEventListener('click', () => toggleHelp(false));
$('noteText').addEventListener('keydown', (e) => {
  if (e.key === 'Escape') { e.stopPropagation(); closeNoteEditor(); }
  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); $('noteOk').click(); }
});
$('btnFit').addEventListener('click', () => { fitZoom(); renderAll(); });
panel.addEventListener('scroll', () => requestAnimationFrame(() => { drawRuler(); drawWave(); positionNeedle(); }));
// renderSetup too: the caption demos bake their scale from the box width, so a
// resize (or the short-pane media query kicking in) has to rebuild them
window.addEventListener('resize', () => { fitZoom(); renderAll(); renderSetup(); });

// alterna entre o CORTE e o render final. Só aparece quando o final existe —
// oferecer a troca sem ter o que trocar é prometer um estado que não há.
$('srcToggle').addEventListener('click', () => {
  S.showFinal = !S.showFinal;
  refreshSrcToggle();
  updateVideoSrc();
});

function refreshSrcToggle() {
  const b = $('srcToggle');
  const has = !!S.state.finalVideo;
  b.classList.toggle('hidden', !has);
  if (!has) S.showFinal = false;
  b.textContent = S.showFinal ? 'final' : 'corte';
  b.classList.toggle('on', !!S.showFinal);
}

// ---------- save / discard ----------
$('btnSave').addEventListener('click', async () => {
  const payload = { type: 'timeline-edits' };
  if (edlDirty()) {
    payload.edl = {
      ranges: S.draft.filter((r) => !r.removed).map((r) => ({
        source: r.source, start: +r.start.toFixed(3), end: +r.end.toFixed(3), beat: r.beat,
      })),
      removed: S.draft.filter((r) => r.removed).map((r) => ({ source: r.source, beat: r.beat, start: r.orig.start, end: r.orig.end })),
      changes: S.draft.filter((r) => !r.removed && (r.start !== r.orig.start || r.end !== r.orig.end)).map((r) => ({
        source: r.source, beat: r.beat,
        from: { start: r.orig.start, end: r.orig.end },
        to: { start: +r.start.toFixed(3), end: +r.end.toFixed(3) },
      })),
    };
  }
  if (insertsDirty()) {
    payload.editData = {
      inserts: S.insertsDraft.filter((c) => c.kind === 'insert').map((c) => ({ ref: c.ref, start: +c.start.toFixed(3), end: +c.end.toFixed(3) })),
      splitInserts: S.insertsDraft.filter((c) => c.kind === 'split').map((c) => ({ ref: c.ref, label: c.label, start: +c.start.toFixed(3), end: +c.end.toFixed(3) })),
      splitVideos: S.insertsDraft.filter((c) => c.kind === 'splitvideo').map((c) => ({ ref: c.ref, label: c.label, start: +c.start.toFixed(3), end: +c.end.toFixed(3) })),
      brollGraphics: S.insertsDraft.filter((c) => c.kind === 'broll').map((c) => ({ ref: c.ref, label: c.label, start: +c.start.toFixed(3), end: +c.end.toFixed(3) })),
      hook: S.insertsDraft.filter((c) => c.kind === 'hook').map((c) => ({ endSec: +c.end.toFixed(3) }))[0] || null,
      behind: S.insertsDraft.filter((c) => c.kind === 'behind').map((c) => ({ ref: c.ref, start: +c.start.toFixed(3), dur: +(c.end - c.start).toFixed(3) })),
      wordAccents: S.insertsDraft.filter((c) => c.kind === 'word').map((c) => ({ ref: c.ref, text: c.label, start: +c.start.toFixed(3), end: +c.end.toFixed(3) })),
    };
  }
  if (S.notes.length) {
    // written in the draft timeline the user was actually looking at, plus the
    // rendered-timeline equivalent so the skill can find the spot in cut.mp4
    payload.notes = S.notes.map((n) => ({
      start: +n.start.toFixed(3),
      end: +n.end.toFixed(3),
      renderedStart: +draftToRendered(n.start).toFixed(3),
      renderedEnd: +draftToRendered(n.end).toFixed(3),
      phase: S.state.phase || 1,
      text: n.text,
    }));
  }
  const res = await fetch('/api/save', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
  if ((await res.json()).ok) {
    S.savedPending = true;
    S.notes = [];
    S.pendingIn = null;
    S.draft.forEach((r) => { r.orig = { start: r.start, end: r.end }; if (r.removed) r.hardRemoved = true; });
    // keep visual state but clear dirty counters
    S.draft = S.draft.filter((r) => !r.removed);
    S.insertsDraft.forEach((c) => { c.orig = { start: c.start, end: c.end }; });
    renderAll(); refreshHeader();
    toast('✓ Salvo — o Claude foi avisado e vai aplicar os ajustes', 5000);
  } else {
    toast('Erro ao salvar — o servidor está de pé?', 4000);
  }
});

$('btnDiscard').addEventListener('click', () => {
  S.draft = S.rendered.map((r) => ({ ...r, removed: false, orig: { start: r.start, end: r.end } }));
  buildInsertsDraft();
  S.notes = [];
  S.pendingIn = null;
  S.editingNote = null;
  $('noteEditor').classList.add('hidden');
  S.selected = -1;
  renderAll(); refreshHeader();
  toast('Ajustes descartados', 2000);
});

// ---------- ui helpers ----------
function showTooltip(e, html) {
  tooltip.innerHTML = html;
  tooltip.style.left = `${e.clientX + 14}px`;
  tooltip.style.top = `${e.clientY - 34}px`;
  tooltip.classList.remove('hidden');
}
function hideTooltip() { tooltip.classList.add('hidden'); }
let toastTimer = null;
function toast(msg, ms) {
  const t = $('toast');
  t.textContent = msg;
  t.classList.remove('hidden');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.add('hidden'), ms || 3000);
}

// ---------- boot ----------
document.querySelectorAll('.tl-chip[data-icon]').forEach((c) => {
  c.innerHTML = ICON[c.dataset.icon] || '';
});

// A1/A2 accordion, folded into the audio track
$('jcutToggle').addEventListener('click', () => {
  if (!(S.jcut && S.jcut.length)) return;
  S.jcutOpen = !S.jcutOpen;
  localStorage.setItem('edvid.jcutOpen', S.jcutOpen ? '1' : '0');
  renderJcutAudio();
  updateScrollRange();
  positionNeedle();
});

poll();
rafLoop();
// the headline fit is MEASURED, so it is wrong until Poppins is actually
// loaded — rebuild once the fonts land
if (document.fonts && document.fonts.ready) {
  document.fonts.ready.then(() => { if (S.style) renderSetup(); });
fetch('/styles/variants.json')
  .then((r) => r.json())
  .then((v) => { LIVE.variants = v; LIVE.key = null; renderLive(); })
  .catch(() => { /* sem os números a prévia cai no CSS puro, que já é honesto */ });
}

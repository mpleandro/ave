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
  cam: '<svg viewBox="0 0 16 16"><rect x="1" y="3.6" width="10.2" height="8.8" rx="2"/><path d="M12.4 7.1l2.3-1.6c.5-.35 1.3-.05 1.3.6v3.8c0 .65-.8.95-1.3.6l-2.3-1.6V7.1z"/></svg>',
  script: '<svg viewBox="0 0 16 16"><rect x="1.5" y="2.4" width="13" height="1.9" rx=".95"/><rect x="1.5" y="6.1" width="13" height="1.9" rx=".95"/><rect x="1.5" y="9.8" width="9" height="1.9" rx=".95"/></svg>',
  ai: '<svg viewBox="0 0 16 16"><path d="M8 .9l1.5 4.1 4.1 1.5-4.1 1.5L8 12.1 6.5 8 2.4 6.5 6.5 5 8 .9zM13 10.4l.7 1.9 1.9.7-1.9.7-.7 1.9-.7-1.9-1.9-.7 1.9-.7.7-1.9zM3.2 10.9l.5 1.4 1.4.5-1.4.5-.5 1.4-.5-1.4-1.4-.5 1.4-.5.5-1.4z"/></svg>',
  zoomIn: '<svg viewBox="0 0 16 16"><path d="M7 1.6a5.4 5.4 0 1 0 3.3 9.7l3.2 3.2a.9.9 0 0 0 1.3-1.3l-3.2-3.2A5.4 5.4 0 0 0 7 1.6zm0 1.8a3.6 3.6 0 1 1 0 7.2 3.6 3.6 0 0 1 0-7.2zm-.9 1.5v1.2H4.9v1.8h1.2v1.2h1.8V7.9h1.2V6.1H7.9V4.9H6.1z"/></svg>',
  zoomOut: '<svg viewBox="0 0 16 16"><path d="M7 1.6a5.4 5.4 0 1 0 3.3 9.7l3.2 3.2a.9.9 0 0 0 1.3-1.3l-3.2-3.2A5.4 5.4 0 0 0 7 1.6zm0 1.8a3.6 3.6 0 1 1 0 7.2 3.6 3.6 0 0 1 0-7.2zM4.9 6.1v1.8h4.2V6.1H4.9z"/></svg>',
  fit: '<svg viewBox="0 0 16 16"><path d="M2 2h4.2v1.8H3.8v2.4H2V2zm7.8 0H14v4.2h-1.8V3.8H9.8V2zM2 9.8h1.8v2.4h2.4V14H2V9.8zm10.2 0H14V14H9.8v-1.8h2.4V9.8z"/></svg>',
  undo: '<svg viewBox="0 0 16 16"><path d="M3.4 6.5h6.1a4.2 4.2 0 0 1 0 8.4H7.2v-1.9h2.3a2.3 2.3 0 0 0 0-4.6H3.4l2.4 2.4-1.35 1.35L.6 7.55 4.45 3.7 5.8 5.05 3.4 6.5z"/></svg>',
  flag: '<svg viewBox="0 0 16 16"><rect x="1.9" y="1.4" width="1.6" height="13.2" rx=".8"/><path d="M5 2.7h7.6a.6.6 0 0 1 .47.97L11.36 6l1.71 2.33a.6.6 0 0 1-.47.97H5V2.7z"/></svg>',
};

/* ---------- style catalog (the Fase 1 → Fase 2 gate) ----------
 * The one place that knows which looks Avelin can build. It is APP-level, not
 * session-level: a new editing style or caption style is a new entry here plus
 * its implementation in the track reference — never a per-session UI.
 * The user's pick ships to <edit>/preview_style.json; the skill reads it once,
 * at the gate, and builds Fase 2 from it.
 */
// O que já existe de verdade no motor. O catálogo abaixo descreve o produto
// inteiro; este mapa diz o que dele está pronto hoje. Manter os dois separados
// é de propósito: o catálogo é a promessa, isto é o estado.
/* Os dezenove estilos do motor `palavra` (assets/styles/palavra.*): um estado
   por palavra — antes de ser dita, ativa, já dita — e o que cada estado pinta
   vindo do `pal` no variants.json. A ORDEM aqui é a ordem do cartão na aba, e
   está agrupada por família: realce que corre, foco por luz, caixa, ritmo,
   editorial. */
const PAL = [
  ['marcador', 'Marcador'], ['marcadorDuplo', 'Marcador duplo'],
  ['marcaTexto', 'Marca-texto'], ['sublinhado', 'Sublinhado'],
  ['progressivo', 'Progressivo'],
  ['foco', 'Foco'], ['focoBlur', 'Foco desfocado'], ['contorno', 'Contorno'],
  ['neon', 'Neon'],
  ['chapa', 'Bloco sólido'], ['chips', 'Chips'], ['vidro', 'Vidro'],
  ['onda', 'Onda'], ['rotativo', 'Rotativo'], ['maquina', 'Máquina de escrever'],
  ['rolagem', 'Rolagem'],
  ['cinema', 'Cinema'], ['manchete', 'Manchete'], ['barra', 'Barra lateral'],
];
const PAL_IDS = new Set(PAL.map((p) => p[0]));

/* As headlines do motor `cartela` (assets/styles/cartela.*): um bloco de
   slots com entrada e saída em tween. As onze primeiras entram SOBRE o vídeo;
   as dez últimas (`cheia`) tomam o quadro inteiro e o devolvem na saída — é o
   gancho que vira cold open. */
const CARTELAS = [
  ['fita', 'Fita'], ['jornal', 'Recorte de jornal'], ['terminal', 'Terminal'],
  ['alerta', 'Alerta'], ['placar', 'Placar'], ['sombra_longa', 'Sombra longa'],
  ['neon', 'Neon tubo'], ['balao', 'Balão de fala'], ['filete', 'Filete duplo'],
  ['adesivo', 'Adesivo'], ['noticia', 'Notícia'],
  ['capa', 'Capa sólida'], ['capa_blur', 'Capa desfocada'], ['cortina', 'Cortina'],
  ['meia_tela', 'Meia-tela'], ['moldura', 'Moldura'], ['contagem', 'Contagem'],
  ['knockout', 'Knockout'], ['poster', 'Pôster tipográfico'], ['aspas', 'Aspas'],
  ['ficha', 'Ficha técnica'],
];
const CT_IDS = new Set(CARTELAS.map((c) => c[0]));

const PORTED = {
  captions: new Set(['karaoke', 'simples', 'serifada', 'classica', 'scatter', 'stacked',
                     'pop', 'popLinha', 'popBloco', 'revelar', 'editorial', 'dinamico',
                     ...PAL.map((p) => p[0])]),
  headlines: new Set(['', 'outline', 'card', 'realce', 'misto',
                      'bloco', 'etiqueta', 'manuscrito', 'gigante',
                      'relevo', 'grifo', 'contorno_duplo',
                      ...CARTELAS.map((c) => c[0])]),
  edits: new Set(['limpa', 'split', 'split2', 'brollOverlay', 'caixinha']),
};

const STYLE_CATALOG = {
  edits: [
    {
      // First on purpose: defaultStyle() takes edits[0], so this is also the
      // default for every new project — a clean full-frame cut, with inserts as
      // something the user opts into.
      id: 'limpa',
      // O RÓTULO muda, o id não: `limpa`/`split`/`split2` são carga estrutural
      // em compose_shortform.py, variants.json, split.css/js e no edit-data de
      // todo projeto já salvo. Renomear o id por cosmética quebraria os três.
      name: 'Nenhum',
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
      name: 'Dividida ↑',
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
      name: 'Dividida ↓',
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
    {
      /* CAIXINHA DE PERGUNTAS — o adesivo do Instagram como gancho do vídeo.
         A miniatura mostra o gesto do formato: faixa escura com a chamada,
         corpo branco com a pergunta, e a pessoa falando atrás. */
      id: 'caixinha',
      name: 'Caixinha',
      mock: `<svg viewBox="0 0 66 118" xmlns="http://www.w3.org/2000/svg">
        <rect x=".5" y=".5" width="65" height="117" rx="7" fill="var(--bg1)" stroke="rgba(255,255,255,.12)"/>
        <rect x="3" y="3" width="60" height="112" rx="5" fill="rgba(255,255,255,.05)"/>
        <circle cx="33" cy="62" r="13" fill="rgba(255,255,255,.16)"/>
        <path d="M12 115a21 21 0 0142 0z" fill="rgba(255,255,255,.16)"/>
        <rect x="9" y="17" width="48" height="30" rx="5" fill="#fff"/>
        <path d="M9 22a5 5 0 015-5h38a5 5 0 015 5v4H9z" fill="#26262b"/>
        <rect x="19" y="20" width="28" height="2.6" rx="1.3" fill="rgba(255,255,255,.75)"/>
        <rect x="14" y="31" width="38" height="3" rx="1.5" fill="rgba(0,0,0,.72)"/>
        <rect x="14" y="37" width="30" height="3" rx="1.5" fill="rgba(0,0,0,.55)"/>
        <rect x="33" y="49" width="24" height="10" rx="5" fill="rgb(var(--orange-rgb) / .85)"/>
      </svg>`,
    },
    {
      /* BROLL OVERLAY — animações HyperFrames POR CIMA do vídeo, para ênfase.
         O mock mostra o gesto: quadro escurecido (scrim) com um elemento de
         destaque no centro. As janelas vivem em `brollOverlays[]` do
         edit-data; o conteúdo nasce de uma conversa (sugestões da IA sobre o
         transcrito + escolha do usuário), nunca de um catálogo fixo. */
      id: 'brollOverlay',
      name: 'Broll Overlay',
      mock: `<svg viewBox="0 0 66 118" xmlns="http://www.w3.org/2000/svg">
        <rect x=".5" y=".5" width="65" height="117" rx="7" fill="var(--bg1)" stroke="rgba(255,255,255,.12)"/>
        <rect x="3" y="3" width="60" height="112" rx="5" fill="rgba(255,255,255,.05)"/>
        <circle cx="33" cy="48" r="13" fill="rgba(255,255,255,.10)"/>
        <path d="M12 115a21 21 0 0142 0z" fill="rgba(255,255,255,.10)"/>
        <rect x="3" y="3" width="60" height="112" rx="5" fill="rgba(0,0,0,.55)"/>
        <rect x="10" y="44" width="46" height="20" rx="4" fill="var(--bg1)" stroke="rgb(var(--orange-rgb) / .8)"/>
        <rect x="15" y="50" width="24" height="4" rx="2" fill="rgb(var(--orange-rgb) / .9)"/>
        <rect x="15" y="57" width="34" height="3" rx="1.5" fill="rgba(255,255,255,.6)"/>
        <path d="M46 50l6 4-6 4z" fill="rgb(var(--orange-rgb) / .9)"/>
        <rect x="12" y="74" width="42" height="11" rx="5.5" fill="var(--bg1)" stroke="rgb(var(--blue-rgb) / .65)"/>
        <rect x="16" y="78.5" width="12" height="2.4" rx="1.2" fill="rgb(var(--blue-rgb) / .9)"/>
        <rect x="30" y="78.5" width="8" height="2.4" rx="1.2" fill="rgba(255,255,255,.5)"/>
        <rect x="40" y="78.5" width="10" height="2.4" rx="1.2" fill="rgba(255,255,255,.5)"/>
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
    {id: 'bloco', name: 'Bloco', hl: 'bloco'},
    {id: 'etiqueta', name: 'Etiqueta', hl: 'etiqueta'},
    {id: 'manuscrito', name: 'Manuscrito', hl: 'manuscrito'},
    {id: 'gigante', name: 'Gigante', hl: 'gigante'},
    {id: 'relevo', name: 'Relevo', hl: 'relevo'},
    {id: 'grifo', name: 'Grifo', hl: 'grifo'},
    {id: 'contorno_duplo', name: 'Contorno duplo', hl: 'contorno_duplo'},
    // as vinte do motor `cartela`, banda primeiro e tela cheia depois
    ...CARTELAS.map(([id, name]) => ({id, name, ct: id})),
    /* SEM HEADLINE precisa ser uma ESCOLHA, não a ausência de uma.
     *
     * Até aqui as onze opções eram todas estilos e `outline` vinha marcada por
     * padrão, então `S.style.headline` era sempre verdadeiro e não existia
     * estado para "não quero headline". Quem não queria uma deixava o texto em
     * branco — e o envio batia no aviso "Falta o texto da headline" em TODO
     * projeto novo, sem saída a não ser cancelar o próprio aviso.
     *
     * O render já se comportava assim: `phase2.py` desliga o hook quando não há
     * texto. Esta opção só torna dizível o que o produto já fazia.
     *
     * ÚLTIMA e não primeira: `defaultStyle()` lê `headlines[0]`, e promover
     * "Nenhum" a padrão marcaria como alterado todo projeto salvo com o padrão
     * antigo — a alteração fantasma que `styleState()` existe para evitar. */
    {
      id: '',
      name: 'Nenhum',
      mock: `<svg viewBox="0 0 66 118" xmlns="http://www.w3.org/2000/svg">
        <rect x=".5" y=".5" width="65" height="117" rx="7" fill="var(--bg1)" stroke="rgba(255,255,255,.12)"/>
        <rect x="3" y="3" width="60" height="112" rx="5" fill="rgba(255,255,255,.05)"/>
        <circle cx="33" cy="52" r="13" fill="rgba(255,255,255,.16)"/>
        <path d="M12 115a21 21 0 0142 0z" fill="rgba(255,255,255,.16)"/>
        <rect x="14" y="16" width="38" height="4.4" rx="2.2" fill="rgba(255,255,255,.10)"/>
        <rect x="20" y="23.5" width="26" height="4.4" rx="2.2" fill="rgba(255,255,255,.10)"/>
        <path d="M17 14.5L49 30" stroke="rgba(255,255,255,.34)" stroke-width="1.6" stroke-linecap="round"/>
      </svg>`,
    },
  ],
  captions: [
    {id: 'karaoke', name: 'Karaokê', demo: 'karaoke'},
    {id: 'stacked', name: 'Empilhado', demo: 'stacked'},
    {id: 'scatter', name: 'Disperso', demo: 'scatter'},
    {id: 'simples', name: 'Simples', stat: 'simples'},
    {id: 'serifada', name: 'Serifada', stat: 'serifada'},
    {id: 'classica', name: 'Clássica', stat: 'classica'},
    {id: 'popBloco', name: 'Estouro (bloco)', demo: 'popBloco'},
    {id: 'popLinha', name: 'Estouro (linha)', demo: 'popLinha'},
    {id: 'pop', name: 'Estouro (palavra)', demo: 'pop'},
    {id: 'revelar', name: 'Revelação', demo: 'revelar'},
    // os dezenove do motor `palavra`, na ordem das famílias
    ...PAL.map(([id, name]) => ({id, name, demo: id})),
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
      id: 'sfx',
      /* Efeitos LOCAIS, da biblioteca em assets/sfx/. Vem antes da geração por
       * IA de propósito: é o caminho que não custa token nem espera, e a
       * ordem da lista é a ordem em que se pensa nas opções. */
      name: 'Aplicar efeitos sonoros',
      def: true,
      icon: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M8 2.2 4.6 5H2.2v6h2.4L8 13.8z" fill="currentColor" stroke-linejoin="round"/><path d="M11.2 5.6a3.4 3.4 0 0 1 0 4.8" opacity=".75"/><path d="M13.4 3.4a6.4 6.4 0 0 1 0 9.2" opacity=".45"/></svg>',
    },
    {
      id: 'musicAI',
      name: 'Gerar com IA',
      /* TRAVADA SÓ SEM A CHAVE — o servidor informa se ela existe.
       * Ligada sem chave, a opção prometia trilha em todo render e entregava
       * silêncio, e a falha só aparecia assistindo o vídeo pronto depois de
       * dois minutos. Com a chave no lugar, é uma opção normal: deduzir do
       * ambiente é o que faz a trava sumir sozinha quando ela entra, sem
       * ninguém ter de lembrar de destravar. */
      needsKey: 'treblo',
      keyMsg: 'Gerar trilha com IA precisa da chave da Treblo.\n\n'
            + 'Coloque TREBLO_API_KEY no .env da skill e reinicie o servidor '
            + 'de preview. Enquanto isso, use "Aplicar efeitos sonoros", '
            + 'que roda com a biblioteca local.',
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

/* O QUADRO DO PROJETO — largura e altura do vídeo DECODIFICADO, a mesma fonte
   que decide `body.portrait`. Os cartões de estilo e as prévias vivem nele: um
   cartão que não é o quadro mostra a letra e esconde o lugar, que é metade da
   escolha. Sem vídeo carregado, o padrão é o 9:16 do short-form, que é o que a
   aba Estilo serve. */
function quadroProj() {
  const w = video.videoWidth || 1080;
  const h = video.videoHeight || 1920;
  return { w, h, retrato: h >= w };
}

/* A ESCALA das prévias. As folhas são autoradas em referência de 1080px e a
   composição passa `--cap-scale: 1` — então o fator do editor é
   `largura em tela / largura do QUADRO`, e não `/1080` fixo: num projeto
   horizontal (1920 de largura) o fixo faria a legenda sair quase o dobro do
   tamanho que ela terá no render. */
const projW = () => quadroProj().w;

/* O tamanho do cartão, escrito como variável de CSS. Retrato manda na altura
   (o quadro é alto e estreito); paisagem manda na largura, senão um 16:9 com
   196px de altura sairia com 348px e caberiam dois por fileira. */
function aplicarQuadro() {
  const q = quadroProj();
  const [w, h] = q.retrato
    ? [Math.round(196 * q.w / q.h), 196]
    : [232, Math.round(232 * q.h / q.w)];
  const r = document.documentElement.style;
  r.setProperty('--quadro-w', `${w}px`);
  r.setProperty('--quadro-h', `${h}px`);
}

/* Onde a deixa deste estilo senta, em px de referência — o mesmo número que o
   compositor lê (`bottom` do estilo, ou o global). */
function capOffset(id, def) {
  const st = ((LIVE.variants || {}).styles || {})[id] || {};
  return st.offsetY != null ? st.offsetY : def;
}

function capBottom(id) {
  const v = LIVE.variants || {};
  const st = (v.styles || {})[id] || {};
  return st.bottom || v.bottom || 430;
}

// Karaoke: lines of ≤3 words (captions.maxWords), Poppins 900 white, each word
// rises 34px and fades in over 7 frames; the line is replaced by the next one.
function buildKaraokeDemo(host) {
  const s = host.clientWidth / projW();
  host.innerHTML = '';
  const wrap = el('div', 'cap-demo', host);
  const words = CAP_TEXT.split(' ');
  const lines = [];
  for (let i = 0; i < words.length; i += 3) lines.push(words.slice(i, i + 3));

  const STEP = 0.26, ENTER = 7 / FPS_REF, HOLD = 0.6;
  const rise = 34 * s;
  const built = [];
  let t = 0;
  const bot = capBottom('karaoke') * s;
  for (const ln of lines) {
    const box = el('div', 'kar-line', wrap);
    // no LUGAR do render: a 430px do fundo, não centrada no cartão
    box.style.bottom = `${bot}px`;
    box.style.left = '0';
    box.style.right = '0';
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
  const s = host.clientWidth / projW();
  host.innerHTML = '';
  const wrap = el('div', 'cap-demo', host);
  const cue = el('div', 'stk-cue', wrap);
  /* NO LUGAR DO RENDER. A folha do render ancora a pilha em
     `top: calc((0.5 + offset) * 100%)` com translateY(-50%) — o número vem do
     variants.json, aqui como estilo inline. Pôr a classe `ave-stacked` no
     contêiner traria junto `height: 0`, que é o que a folha usa para ancorar, e
     colapsaria o cartão. */
  cue.style.top = `${(0.5 + capOffset('stacked', 0.156)) * 100}%`;
  cue.style.transform = 'translateY(-50%)';

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
const HEADLINE_TEXT = 'É assim que vai ficar / a sua headline';
const HL_MIN = 40;

/* OS NÚMEROS VÊM DO `variants.json`, não de uma cópia aqui.
 *
 * Esta constante já foi uma segunda tabela mantida à mão ao lado da do
 * compositor, com um comentário pedindo para atualizar as duas juntas — que é
 * exatamente o arranjo que a skill proíbe para os estilos de legenda, e pela
 * razão que se confirmou: ao ganhar sete layouts, a cópia teria nascido
 * desatualizada. O fallback existe só para a janela entre o app carregar e o
 * fetch do variants voltar. */
const HL_FALLBACK = {
  outline: { weights: [800, 800], cap: 92, safeW: 900, lh: 1.02 },
  card: { weights: [900, 900], cap: 82, safeW: 820, lh: 1.06, upper: true },
  realce: { weights: [900, 900], cap: 86, safeW: 830, lh: 1.04 },
  misto: { weights: [400, 900], cap: 98, safeW: 900, lh: 0.98 },
};
const hlStyle = (id) =>
  ((LIVE.variants && LIVE.variants.headlines) || {})[id] || HL_FALLBACK[id] || HL_FALLBACK.card;

/* ---------- as duas famílias ----------
 * Catálogo CURADO do Google Fonts, não a API inteira. Duas razões, e a segunda
 * é a que obriga: mil e quinhentas famílias não se escolhem numa lista, e a
 * API v2 responde ERRO — sem CSS nenhum — quando se pede um peso que a família
 * não tem. Uma fonte de peso único como a Anton pedida em 900 derrubaria o
 * carregamento inteiro, e o sintoma seria a headline renderizar na fonte de
 * sistema. Por isso os pesos disponíveis são DADO aqui, e o peso pedido é
 * grudado no mais próximo que existe. */
const GFONTS_FALLBACK = [
  { n: 'Poppins', w: [400, 500, 600, 700, 800, 900], k: 'display' },
  { n: 'Montserrat', w: [400, 500, 600, 700, 800, 900], k: 'display' },
  { n: 'Inter', w: [400, 500, 600, 700, 800, 900], k: 'display' },
  { n: 'Rubik', w: [400, 500, 600, 700, 800, 900], k: 'display' },
  { n: 'Oswald', w: [400, 500, 600, 700], k: 'display' },
  { n: 'Barlow Condensed', w: [400, 500, 600, 700, 800, 900], k: 'display' },
  { n: 'Teko', w: [400, 500, 600, 700], k: 'display' },
  { n: 'Anton', w: [400], k: 'display' },
  { n: 'Archivo Black', w: [400], k: 'display' },
  { n: 'Bebas Neue', w: [400], k: 'display' },
  { n: 'Fjalla One', w: [400], k: 'display' },
  { n: 'Titan One', w: [400], k: 'display' },
  { n: 'Passion One', w: [400, 700, 900], k: 'display' },
  { n: 'Alfa Slab One', w: [400], k: 'display' },
  { n: 'Playfair Display', w: [400, 500, 600, 700, 800, 900], k: 'serif' },
  { n: 'Libre Baskerville', w: [400, 700], k: 'serif' },
  { n: 'Lora', w: [400, 500, 600, 700], k: 'serif' },
  { n: 'Merriweather', w: [300, 400, 700, 900], k: 'serif' },
  { n: 'Bitter', w: [400, 500, 600, 700, 800, 900], k: 'serif' },
  { n: 'Caveat', w: [400, 500, 600, 700], k: 'manuscrita' },
  { n: 'Dancing Script', w: [400, 500, 600, 700], k: 'manuscrita' },
  { n: 'Permanent Marker', w: [400], k: 'manuscrita' },
  { n: 'Shadows Into Light', w: [400], k: 'manuscrita' },
  { n: 'Kalam', w: [300, 400, 700], k: 'manuscrita' },
  { n: 'Satisfy', w: [400], k: 'manuscrita' },
  { n: 'Pacifico', w: [400], k: 'manuscrita' },
  { n: 'Gloria Hallelujah', w: [400], k: 'manuscrita' },
];
/* O catálogo mora no `variants.json`, com a lista acima só de reserva para a
 * janela antes do fetch voltar — mesma razão dos números dos layouts: uma
 * segunda cópia mantida à mão diverge na primeira família adicionada de um
 * lado só, e o sintoma seria a prévia oferecer uma fonte que o render não sabe
 * pedir. */
const gfonts = () => (LIVE.variants && LIVE.variants.gfonts) || GFONTS_FALLBACK;

/* AS FONTES DO PRÓPRIO USUÁRIO, indexadas pelo servidor (`/api/localfonts`).
 *
 * O catálogo do Google cobre o genérico e não cobre a MARCA de ninguém: a
 * tipografia da identidade está instalada no computador de quem edita. Isto
 * funciona porque o render roda em Chrome NESTA máquina e o Chrome resolve
 * `font-family: 'Gotham'` pelo nome, direto do sistema — nem a prévia nem o
 * render precisam do arquivo. Quem precisa é a medição, que é local.
 *
 * O PREÇO, dito na interface: um projeto com fonte local não renderiza igual
 * em outra máquina. */
let LOCAL_FONTS = [];
async function loadLocalFonts() {
  try {
    const d = await (await fetch('/api/localfonts')).json();
    LOCAL_FONTS = Array.isArray(d.families) ? d.families : [];
  } catch (e) { LOCAL_FONTS = []; }
}
const allFonts = () => gfonts().concat(LOCAL_FONTS);
const GF = (name) => allFonts().find((f) => f.n === name) || gfonts()[0];
const isLocal = (name) => (GF(name) || {}).k === 'local';
const FONT_MAIN_DEF = 'Poppins';
const FONT_ACCENT_DEF = 'Caveat';

/* O peso PEDIDO grudado no que a família TEM. Sem isto, escolher a Anton num
 * layout que pede 900 deixaria o navegador falsear o negrito — engorda o glifo
 * por transformação e o texto fica sujo, além de medir diferente do render. */
function nearestWeight(family, w) {
  const ws = GF(family).w;
  return ws.reduce((a, b) => (Math.abs(b - w) < Math.abs(a - w) ? b : a), ws[0]);
}
const FALLBACK_GENERICO = { manuscrita: 'cursive', serif: 'serif' };
const cssFamily = (name) =>
  `'${name}', ${FALLBACK_GENERICO[GF(name).k] || 'sans-serif'}`;

/* A folha do Google para o par escolhido. Uma família por vez e só os pesos que
 * ela tem — ver o comentário do catálogo. */
function gfontHref(fams) {
  const q = [...new Set(fams)].filter(Boolean)
    // EMPACOTADAS e LOCAIS não existem por este caminho, e pedi-las devolve
    // erro na folha INTEIRA — derrubando junto a família que existe
    .filter((n) => !GF(n).file && GF(n).k !== 'local')
    .map((n) => {
      const f = GF(n);
      const ws = f.w.length > 1 ? `:wght@${f.w.join(';')}` : '';
      return `family=${n.replace(/ /g, '+')}${ws}`;
    });
  return q.length ? `https://fonts.googleapis.com/css2?${q.join('&')}&display=swap` : '';
}

/* `@font-face` das famílias que viajam com a skill, servidas de /styles/fonts/.
 * A prévia tem de desenhar a MESMA letra do render — sem isto ela cairia numa
 * genérica, e o layout seria escolhido sobre uma mentira. */
let bundledStyle = null;
function ensureBundled() {
  const regras = gfonts().filter((f) => f.file).map((f) =>
    `@font-face{font-family:'${f.n}';src:url('/styles/fonts/${f.file}');`
    + `font-weight:${f.w[0]};font-style:normal;font-display:block}`).join('');
  if (!regras) return;
  if (!bundledStyle) {
    bundledStyle = document.createElement('style');
    document.head.appendChild(bundledStyle);
  }
  if (bundledStyle.textContent !== regras) bundledStyle.textContent = regras;
}

let gfontLink = null;
function ensureFonts(fams) {
  ensureBundled();
  const href = gfontHref(fams);
  if (!href) return;   // só empacotadas — não há folha do Google a pedir
  if (!gfontLink) {
    gfontLink = document.createElement('link');
    gfontLink.rel = 'stylesheet';
    document.head.appendChild(gfontLink);
  }
  if (gfontLink.href !== href) gfontLink.href = href;
}

/* ---------- degradê: a segunda parada é DERIVADA ----------
 * A regra é do MODELO, não do usuário: ele escolhe uma cor e o layout decide
 * se o degradê caminha para o escuro ou para o claro. Pedir as duas pontas
 * devolveria degradê sujo com o dobro de perguntas. */
function shadeHex(hex, amount, toDark) {
  const n = parseInt((normHex(hex) || '#FFFFFF').slice(1), 16);
  const ch = [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  const f = (c) => (toDark ? Math.round(c * (1 - amount)) : Math.round(c + (255 - c) * amount));
  return `#${ch.map((c) => f(c).toString(16).padStart(2, '0')).join('')}`;
}

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

/* A QUEBRA. O "/" MANDA; sem ele, equilibra por LARGURA MEDIDA.
 *
 * A barra é o controle que faltava: quem escreve sabe onde a frase respira, e
 * o equilíbrio automático não sabe — ele só sabe deixar as linhas do mesmo
 * tamanho. Com a barra o autor decide a quebra E quantas linhas existem, que é
 * o que destrava os layouts de três linhas e os de linha herói.
 *
 * Sem barra, o antigo equilíbrio de DUAS linhas continua: por largura medida e
 * não por contagem de palavras, porque "É assim que vai" e "ficar a sua
 * headline" têm 4 e 3 palavras e quase a mesma largura. */
function hlLines(text, S) {
  const t = (text || '').trim();
  if (t.includes('/')) {
    const parts = t.split('/').map((s) => s.trim()).filter(Boolean);
    if (parts.length) return parts;
  }
  if (S.quebra === 'encher') return hlWrap(t, S);
  const words = t.split(/\s+/).filter(Boolean);
  if (words.length < 2) return [words[0] || ''];
  let best = [words[0], words.slice(1).join(' ')];
  let bestDiff = Infinity;
  for (let i = 1; i < words.length; i++) {
    const a = words.slice(0, i).join(' ');
    const b = words.slice(i).join(' ');
    const d = Math.abs(hlWidth(a, 100, S.weights[0]) - hlWidth(b, 100, S.weights[1]));
    if (d < bestDiff) { bestDiff = d; best = [a, b]; }
  }
  return best;
}

/* QUEBRA ENCHENDO A LARGURA — espelho de `hl_wrap` no compositor.
 * O equilíbrio em duas linhas é o certo para uma frase de gancho e o errado
 * para uma manchete: duas linhas longas fazem o ajuste encolher o corpo, e sai
 * uma manchete pequena num cartão grande. A largura-alvo é medida em unidades
 * de corpo 100 (`safeW * 100 / cap`), que é como o `hlWidth` mede. */
function hlWrap(text, S) {
  const alvo = (S.safeW * 100) / Math.max(1, S.cap || 100);
  const linhas = [];
  let atual = '';
  text.split(/\s+/).filter(Boolean).forEach((w) => {
    const tent = (atual ? atual + ' ' + w : w);
    if (atual && hlWidth(tent, 100, S.weights[0]) > alvo) { linhas.push(atual); atual = w; }
    else atual = tent;
  });
  if (atual) linhas.push(atual);
  return linhas.length ? linhas : [''];
}

/* CAIXA ALTA É DO CÓDIGO, NUNCA DO CSS.
 * `text-transform` aplica DEPOIS da medição: mede-se a minúscula e desenha-se a
 * maiúscula, que é mais larga — e a headline estoura o quadro sem erro nenhum.
 * Foi o que aconteceu com o manuscrito e o gigante ao serem montados. */
function hlUpper(i, n, S) {
  if (S.upper) return true;
  if (S.upperLines === 'last') return i === n - 1;
  if (S.upperLines === 'rest') return i > 0;
  if (Array.isArray(S.upperLines)) return S.upperLines.includes(i);
  return false;
}

// o multiplicador de corpo de cada linha; a última entrada vale para as extras
function hlKs(lines, S) {
  if (!S.sizes) return lines.map(() => 1);
  return lines.map((_, i) => S.sizes[Math.min(i, S.sizes.length - 1)]);
}
const hlWeight = (S, i) => S.weights[Math.min(i, S.weights.length - 1)];
const hlFamily = (S, i, fonts) =>
  (S.fontRole && S.fontRole[Math.min(i, S.fontRole.length - 1)] === 'accent')
    ? fonts.accent : fonts.main;

function hlFit(lines, S, fonts) {
  const ks = hlKs(lines, S);
  /* A LINHA HERÓI SAI DA CONTA COMUM. Ela é medida sozinha, contra a largura
     inteira: no ajuste conjunto uma palavra curta ficaria pequena e uma longa
     puxaria todas as outras linhas para baixo junto com ela. */
  const idx = lines.map((_, i) => i).filter((i) => !(S.heroLast && i === lines.length - 1));
  const alvo = idx.length ? idx : lines.map((_, i) => i);
  const widest = (size) => Math.max(...alvo.map((i) =>
    measureType(lines[i], size * ks[i], nearestWeight(hlFamily(S, i, fonts), hlWeight(S, i)),
                cssFamily(hlFamily(S, i, fonts)))));
  let size = (S.safeW / Math.max(1, widest(100))) * 100;
  size = (S.safeW / Math.max(1, widest(size))) * size;
  return Math.max(HL_MIN, Math.min(size, S.cap));
}

function hlHeroSize(lines, S, fonts) {
  const i = lines.length - 1;
  const fam = cssFamily(hlFamily(S, i, fonts));
  const w = nearestWeight(hlFamily(S, i, fonts), hlWeight(S, i));
  let s = (S.safeW / Math.max(1, measureType(lines[i], 100, w, fam))) * 100;
  s = (S.safeW / Math.max(1, measureType(lines[i], s, w, fam))) * s;
  return Math.min(s, S.cap);
}

/* As quatro variáveis de cor de UM bloco. As duas derivadas do degradê saem
 * daqui junto com as escolhidas — separá-las deixaria a segunda parada com a
 * cor antiga por um quadro, que é visível no arrasto. */
function paintHook(box, S, main, accent) {
  box.style.setProperty('--hl-main', main);
  box.style.setProperty('--hl-accent', accent);
  if (S && S.gradient) {
    const dark = S.gradient.to === 'dark';
    box.style.setProperty('--hl-main-2', shadeHex(main, S.gradient.amount, dark));
    box.style.setProperty('--hl-accent-2', shadeHex(accent, S.gradient.amount, dark));
  }
}

/* Repinta as prévias JÁ MONTADAS. A cor não muda medida nenhuma, então
 * remontar as onze a cada quadro do arrasto seria pagar a medição de todas
 * elas para trocar duas variáveis. */
function paintHeadlines() {
  const main = normHex(S.style.textColor) || '#FFFFFF';
  const accent = normHex(S.style.accent) || ACCENT_DEFAULT;
  document.querySelectorAll('#opt-headlines .ave-hook').forEach((box) => {
    const id = [...box.classList].find((c) => c !== 'ave-hook');
    paintHook(box, hlStyle(id), main, accent);
  });
  /* As cartelas repintam por VARIÁVEL — elas não têm `paint` por classe como
     os layouts antigos, a folha é que decide quem recebe qual cor. Sem esta
     linha os vinte cartões novos ficavam presos na cor de fábrica enquanto o
     usuário arrastava a roda, que é o defeito que `paintHeadlines` existe para
     não ter. */
  document.querySelectorAll('#opt-headlines .ave-cartela').forEach((box) => {
    box.style.setProperty('--hl-main', main);
    box.style.setProperty('--hl-accent', accent);
    box.style.setProperty('--hl-accent-rgb', trioRGB(accent));
  });
}

/* Monta uma headline REAL — a mesma marcação e as mesmas classes que o
 * compositor emite, com o mesmo `headline.css`. É o que permite escolher um
 * layout olhando, em vez de escolher pelo nome. */
function buildHeadline(host, styleId, text, opts) {
  const o = opts || {};
  const S = hlStyle(styleId);
  const fonts = { main: o.fontMain || FONT_MAIN_DEF, accent: o.fontAccent || FONT_ACCENT_DEF };
  ensureFonts([fonts.main, fonts.accent]);
  const s = (o.width || host.clientWidth) / projW();
  host.innerHTML = '';
  const box = el('div', `ave-hook ${styleId}`, host);
  box.style.setProperty('--hl-scale', s);
  box.style.setProperty('--hl-top', o.top == null ? 0 : o.top);
  box.style.setProperty('--hl-lh', S.lh);
  box.style.setProperty('--hl-stroke', S.stroke || 0);
  box.style.setProperty('--hl-font', cssFamily(fonts.main));
  box.style.setProperty('--hl-font-accent', cssFamily(fonts.accent));
  /* AS CORES VÃO CRAVADAS NA CAIXA, e não herdadas do painel.
     Herdar não funciona: o próprio `.ave-hook` DECLARA `--hl-main`/`--hl-accent`
     como padrão na folha, e uma declaração na regra vence o valor herdado — as
     prévias ficariam presas no laranja de fábrica enquanto o usuário arrasta a
     roda. Quem repinta ao vivo é `paintHeadlines()`, que só troca as variáveis
     das caixas já montadas, sem remedir nada. */
  const main = normHex(o.main) || '#FFFFFF';
  const accent = normHex(o.accent) || ACCENT_DEFAULT;
  paintHook(box, S, main, accent);
  if (o.position) box.style.position = o.position;

  let lines = hlLines(text, S);
  lines = lines.map((l, i) => (hlUpper(i, lines.length, S) ? l.toUpperCase() : l));
  const size = hlFit(lines, S, fonts);
  box.style.setProperty('--hl-size', size);
  const ks = hlKs(lines, S);
  if (S.heroLast) ks[lines.length - 1] = hlHeroSize(lines, S, fonts) / size;

  const paint = S.paint || {};
  lines.forEach((l, i) => {
    const d = el('div', 'hl-line', box);
    d.style.setProperty('--hl-k', ks[i]);
    // o peso vai INLINE porque foi grudado no que a família tem — deixar a
    // folha pedir 900 numa fonte de peso único faz o navegador falsear o negrito
    d.style.fontWeight = String(nearestWeight(hlFamily(S, i, fonts), hlWeight(S, i)));
    d.dataset.text = l;   // a extrusão do relevo lê daqui
    if (paint.tagBox != null && i === (paint.tag == null ? 0 : paint.tag)) d.classList.add('hl-tag');
    if (paint.hollowLines && paint.hollowLines.includes(i)) d.classList.add('hl-hollow');
    if (paint.wordBox) {
      // sem nó de espaço entre as tarjas: o espaço ficaria DENTRO da tarja e as
      // caixas se encostariam. A folga é a margem do .hl-word.
      l.split(/\s+/).forEach((w) => { el('span', 'hl-word', d).textContent = w; });
    } else {
      d.textContent = l;
    }
  });
  return box;
}

/* Prévia das headlines do motor `cartela`. Usa `/styles/cartela.*` — a MESMA
 * folha, o MESMO script e a mesma marcação do render, com a cartela ASSENTADA
 * (entrada terminada, saída ainda não começada). O movimento não roda aqui de
 * propósito: esta prévia responde "como fica", e o quadro do meio de uma
 * entrada de 500ms não é como fica. */
function buildCartelaDemo(host, styleId) {
  const C = window.AVE_CARTELA;
  const h = hlStyle(styleId);
  host.innerHTML = '';
  if (!C || !h || h.motor !== 'cartela') return () => {};
  const fonts = { main: S.style.fontMain || FONT_MAIN_DEF,
                  accent: S.style.fontAccent || FONT_ACCENT_DEF };
  ensureFonts([fonts.main, fonts.accent]);
  const sc = host.clientWidth / projW();

  const partes = C.fatiar(S.style.headlineText || HEADLINE_TEXT, h);
  let linhas = (h.linhaUnica && partes.titulo.indexOf('/') < 0)
    ? [partes.titulo] : hlLines(partes.titulo, h);
  linhas = linhas.filter(Boolean).map((l, i) => (hlUpper(i, linhas.length, h) ? l.toUpperCase() : l));
  if (!linhas.length) linhas = [''];
  const size = hlFit(linhas, h, fonts);
  const ks = hlKs(linhas, h);
  const dados = {
    olho: partes.olho, num: partes.num, assinatura: partes.assinatura, meta: partes.meta,
    size, familia: fonts.main,
    linhas: linhas.map((l, i) => ({
      txt: l, k: ks[i],
      peso: nearestWeight(hlFamily(h, i, fonts), hlWeight(h, i)),
    })),
  };
  const box = C.montar(host, h, styleId, dados);
  box.style.setProperty('--hl-scale', sc);
  box.style.setProperty('--hl-size', size);
  box.style.setProperty('--hl-lh', h.lh);
  box.style.setProperty('--hl-top', h.top || 0);
  box.style.setProperty('--hl-stroke', h.stroke || 0);
  box.style.setProperty('--hl-font', cssFamily(fonts.main));
  box.style.setProperty('--hl-font-accent', cssFamily(fonts.accent));
  const main = normHex(S.style.textColor) || '#FFFFFF';
  const acc = normHex(S.style.accent) || ACCENT_DEFAULT;
  box.style.setProperty('--hl-main', main);
  box.style.setProperty('--hl-accent', acc);
  box.style.setProperty('--hl-accent-rgb', trioRGB(acc));
  box.style.setProperty('--hl-sobre-accent', sobreAccent(acc));
  C.assentar(box);
  return () => {};
}

function buildHeadlineDemo(host, styleId) {
  const wrap = el('div', 'cap-demo', host);
  const fit = el('div', 'hl-fit', wrap);
  buildHeadline(fit, styleId, S.style.headlineText || HEADLINE_TEXT, {
    width: host.clientWidth,
    // no ALTO do quadro, onde ela vai aparecer — o cartão agora tem altura para
    // isso, e a altura era a única razão de ela vir com top 0
    top: (hlStyle(styleId) || {}).top || 0,
    main: S.style.textColor,
    accent: S.style.accent,
    fontMain: S.style.fontMain,
    fontAccent: S.style.fontAccent,
  });
  /* ENCAIXE NA ALTURA DO CARTÃO. O corpo é ajustado à LARGURA segura, então
     uma headline de três linhas é simplesmente mais alta — e com o `/` três
     linhas deixaram de ser exceção. Sem isto a última linha some cortada pela
     borda do cartão, e o usuário escolhe um layout sem ver o fim dele.
     Reduzir a escala e não o corpo: mexer no corpo mudaria a QUEBRA, e a
     prévia passaria a mostrar um arranjo de linhas que o render não vai fazer. */
  requestAnimationFrame(() => {
    const h = fit.getBoundingClientRect().height;
    const alvo = host.clientHeight - 8;
    fit.style.setProperty('--hl-fit', h > alvo && h > 0 ? Math.min(1, alvo / h) : 1);
  });
}

// Scatter ("disperso"): serif, lowercase, one word at a time, off-white with a
// slight darkening toward the baseline. Ordinary words FADE only — no movement;
// the one highlighted word resolves out of a blur and dissolves back into it.
// Mirrors ScatterCaptions.tsx: same line rules, same SPREAD, same hash.
const SCAT = { base: 72, hiScale: 1.62, gap: 12, spread: 0.45, safeW: 820 };
const scatHash = (n) => { const x = Math.sin(n * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); };

function buildScatterDemo(host) {
  const s = host.clientWidth / projW();
  host.innerHTML = '';
  const wrap = el('div', 'cap-demo', host);
  const cue = el('div', 'scat-cue', wrap);
  // o disperso vive sobre o PEITO (0.72 da altura), não no meio do quadro
  cue.style.top = `${capOffset('scatter', 0.72) * 100}%`;
  cue.style.transform = 'translateY(-50%)';

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
  const s = host.clientWidth / projW();
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
    // no rodapé real do estilo, como o render — não centrada no cartão
    box.style.bottom = `${capBottom(id) * s}px`;
    box.style.left = '0';
    box.style.right = '0';
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

/* Prévias dos estilos MEDIDOS do CapCut. Usam o CSS e o JS do RENDER
 * (`/styles/pop.*`, `/styles/revelar.*`), não uma imitação: os tempos vêm de
 * AVE_POP/AVE_REVELAR, que são os mesmos módulos que a composição carrega.
 * Uma prévia que anima com outra curva é pior que nenhuma prévia. */
function buildCapCutDemo(host, tipo, grupo) {
  const s = host.clientWidth / projW();
  host.innerHTML = '';
  const wrap = el('div', 'cap-demo', host);
  const raiz = el('div', tipo === 'pop' ? `ave-pop grupo-${grupo}` : 'ave-rev', wrap);
  raiz.style.position = 'absolute';
  raiz.style.setProperty('--cap-scale', s);
  if (S.style.capFont) {
    ensureFonts([S.style.capFont]);
    raiz.style.setProperty('--cap-family', cssFamily(S.style.capFont));
  }
  /* A FRASE COMPLETA, em DUAS linhas (pedido do usuário, 2026-08-19): com uma
     linha só, "linha" e "bloco" eram literalmente a mesma animação e os dois
     cartões pulsavam idênticos — a dimensão que os separa (o que estoura
     JUNTO) só existe a partir da segunda linha. No RENDER a legenda senta a
     `--cap-bottom` px do fundo; no cartão, o par de linhas é centrado — a
     prévia mostra o ESTILO e a animação, não o posicionamento no quadro. */
  const palavras = CAP_TEXT.split(' ');
  const metade = Math.ceil(palavras.length / 2);
  const linhasTx = [palavras.slice(0, metade), palavras.slice(metade)];
  const rows = [];
  const spans = [];
  const bot = capBottom(tipo === 'pop' ? 'pop' : 'revelar') * s;
  const lh = 76 * 1.08 * s;   // corpo x entrelinha do estilo
  linhasTx.forEach((ws, li) => {
    const row = el('div', 'ave-cap-line', raiz);
    // as duas linhas empilhadas SOBRE a base real, em vez de 56%/38% do cartão
    row.style.bottom = `${bot + (li === 0 ? lh : 0)}px`;
    rows.push(row);
    for (const w of ws) {
      const sp = el('span', spans.length === 1 ? 'hi' : '', row);
      sp.textContent = w.toUpperCase();
      spans.push(sp);
    }
  });

  if (tipo === 'pop') {
    const P = window.AVE_POP;
    if (!P) return () => {};
    const T = P.TIMING;
    /* palavra: cada uma na sua vez · linha: uma LINHA depois da outra ·
       bloco: as duas linhas estouram JUNTAS — agora dá para ver a diferença */
    let alvos = spans;
    let step = T.STEP;
    if (grupo === 'linha') { alvos = rows; step = T.TOTAL + 0.12; }
    if (grupo === 'bloco') { alvos = rows; step = 0; }
    const ciclo = (alvos.length - 1) * step + T.TOTAL + T.HOLD + 0.35;
    return (now) => {
      const t = now % ciclo;
      alvos.forEach((elm, i) => {
        const st = P.unitState(t, i, step);
        elm.style.opacity = st.opacity;
        elm.style.transform = `skewX(-1deg) scale(${st.scale})`;
      });
    };
  }
  const R = window.AVE_REVELAR;
  if (!R) return () => {};
  const off = R.wordOffsets(palavras.map((w) => w.toUpperCase()));
  const ciclo = R.lineDuration() + 0.4;
  return (now) => {
    const t = now % ciclo;
    spans.forEach((elm, i) => {
      const o = off.spans[i];
      elm.style.setProperty('--rev-w', R.wordReveal(t, o.start, o.len, off.total));
    });
  };
}

/* A frase de exemplo com TEMPO DE FALA. Os estilos do motor `palavra` são
   todos karaokê de alguma forma — o que eles mostram é a palavra chegando na
   voz — então um exemplo sem tempo mostraria uma legenda parada, que é
   justamente o que nenhum deles é. Duração por palavra proporcional ao
   comprimento, com um piso: é o que a fala faz, e é o que faz "a" passar
   depressa e "aparecer" segurar. */
function palRoteiro(palavras) {
  let t = 0;
  return palavras.map((w) => {
    const d = Math.max(0.2, Math.min(0.62, 0.13 + w.length * 0.055));
    const item = {texto: w, at: t, dur: d};
    t += d + 0.05;
    return item;
  });
}

/* A quebra do exemplo obedece ao ESTILO: `maxWords` é teto de palavras e
   `lines` de linhas. Sem isto o rotativo (uma palavra) mostraria sete e o
   cinema (nove) mostraria três — e a prévia estaria mentindo sobre a única
   coisa que ela existe para mostrar. */
function palLinhas(v) {
  const todas = palRoteiro(CAP_TEXT.split(' '));
  const cola = (v.pal || {}).cola;
  let cap = Math.max(1, Math.min(v.maxWords || 5, todas.length));
  // com `cola` (o rotativo), palavra curta não fecha a deixa: senão o cartão
  // do estilo seria a palavra "É" sozinha, que não mostra estilo nenhum
  if (cola) {
    cap = 1;
    while (cap < todas.length && todas[cap - 1].texto.length <= cola) cap++;
  }
  const usadas = todas.slice(0, cap);
  if ((v.lines || 1) < 2 || usadas.length < 2) return [usadas];
  const meio = Math.ceil(usadas.length / 2);
  return [usadas.slice(0, meio), usadas.slice(meio)];
}

/* Prévia dos estilos do motor `palavra`. Usa `/styles/palavra.*` — a MESMA
   folha e o MESMO script do render, montando a mesma marcação e pintando os
   mesmos estados. O que muda é só quem conta o tempo: aqui é o relógio do
   cartão, no render é o seek do GSAP. */
function buildPalavraDemo(host, id) {
  const s = host.clientWidth / projW();
  host.innerHTML = '';
  const wrap = el('div', 'cap-demo', host);
  const P = window.AVE_PALAVRA;
  const v = ((LIVE.variants && LIVE.variants.styles) || {})[id] || {};
  const cfg = v.pal || {};
  const box = el('div', `ave-pal pal-${id}`, wrap);
  if (!P || !v.pal) { box.textContent = ''; return () => {}; }
  vestirPal(box, id, v, s);
  const linhas = palLinhas(v);
  const cue = P.montar(box, linhas, cfg, id);
  const cores = P.paleta(box);
  const ult = linhas[linhas.length - 1];
  const ciclo = ult[ult.length - 1].at + ult[ult.length - 1].dur + 0.9;
  return (now) => { P.pintar(cue, cfg, v.motion || {}, now % ciclo, s, cores); };
}

/* As variáveis do contêiner — o que o compositor escreve no `style` da deixa.
   As do `pal` ficam com o motor (`varsPal`); aqui vai só o que é comum a
   qualquer legenda: corpo, cor, letra e peso. */
function vestirPal(box, id, v, escala) {
  box.style.position = 'absolute';
  box.style.inset = '0';
  box.style.setProperty('--cap-scale', escala);
  box.style.setProperty('--cap-size', v.size || 58);
  box.style.setProperty('--cap-weight', v.weight || 600);
  box.style.setProperty('--cap-track', v.tracking || 0);
  box.style.setProperty('--cap-lh', v.lineHeight || 1.26);
  const cor = S.style.capColor || '#F5F2EE';
  const acc = S.style.accent || ACCENT_DEFAULT;
  box.style.setProperty('--cap-color', cor);
  box.style.setProperty('--cap-color-rgb', trioRGB(cor));
  box.style.setProperty('--cap-accent', acc);
  box.style.setProperty('--cap-accent-rgb', trioRGB(acc));
  const fam = S.style.capFont ? cssFamily(S.style.capFont) : v.cssFamily;
  if (S.style.capFont) ensureFonts([S.style.capFont]);
  if (fam) box.style.setProperty('--cap-family', fam);
  window.AVE_PALAVRA.varsPal(box, v.pal || {});
}

/* `#FF6B1A` -> `255 107 26`. Espelha o `rgb_trio` do compositor: sem o trio
   separado por espaço, `rgb(var(--x) / .5)` não resolve e a regra cai CALADA —
   o halo do neon e a chapa translúcida simplesmente não aparecem. */
function trioRGB(hex) {
  let h = String(hex || '').replace('#', '');
  if (h.length === 3) h = h.split('').map((c) => c + c).join('');
  const n = parseInt(h, 16);
  if (!isFinite(n) || h.length !== 6) return '255 255 255';
  return `${(n >> 16) & 255} ${(n >> 8) & 255} ${n & 255}`;
}

/* A cor legível SOBRE o destaque — espelho de `sobre_accent` no compositor.
 * Branco é a convenção da manchete e é o que o usuário reconhece; a medição
 * entra só para o caso em que o branco FALHA (destaque amarelo ou creme, com
 * razão de contraste abaixo de 3:1), senão o vermelho receberia texto escuro —
 * mais legível e não é uma manchete. */
function sobreAccent(hex) {
  const t = trioRGB(hex).split(' ').map(Number);
  const lin = (v) => { const c = v / 255; return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); };
  const lum = 0.2126 * lin(t[0]) + 0.7152 * lin(t[1]) + 0.0722 * lin(t[2]);
  return 1.05 / (lum + 0.05) >= 3 ? '#ffffff' : '#10202e';
}

const CAP_BUILDERS = {
  karaoke: buildKaraokeDemo, stacked: buildStackedDemo, scatter: buildScatterDemo,
  pop: (h) => buildCapCutDemo(h, 'pop', 'palavra'),
  popLinha: (h) => buildCapCutDemo(h, 'pop', 'linha'),
  popBloco: (h) => buildCapCutDemo(h, 'pop', 'bloco'),
  revelar: (h) => buildCapCutDemo(h, 'revelar'),
};
for (const [id] of PAL) CAP_BUILDERS[id] = (h) => buildPalavraDemo(h, id);

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
  view: 'tl',       // 'tl' linha do tempo · 'tx' transcrição
  words: [],        // transcrito do corte (/gen/words.json)
  cutWords: new Set(), // índices riscados = PEDIDO de corte, não corte feito
  cutBreaths: new Set(), // respiros marcados: índice da palavra que vem ANTES
  undo: [],         // pilha de instantâneos de S.draft (apagar / redimensionar)
  approved: false,  // aprovação enviada nesta sessão (some a barra na hora)
  selWords: new Set(),
  processing: false, // a IA está refazendo algo lá fora
  procFrom: 0,
  keys: null, // chaves de API PRESENTES (nunca o valor) — vem do /api/state
  deps: null, // ffmpeg, uv, node… o que esta máquina tem instalado
  pendingIn: null, // an IN is open, waiting for its OUT
  editingNote: null, // id of the note the editor is bound to
  style: null, // current picks {edit, captions, elements:{…}, note}
  prefs: null, // as escolhas da última vez (~/.avelin/estilo.json)
  jcut: null, // jcut_timeline from edl.json — real output positions per take
  // A1/A2 live folded inside the audio track. They answer "where is the J-cut",
  // which is a question you ask once — so the default is closed, and the choice
  // is remembered rather than re-made every reload.
  jcutOpen: localStorage.getItem('avelin.jcutOpen') === '1',
};

/* Falta a chave que esta opção exige? Devolve a explicação; senão, ''.
 * A resposta vem do servidor (`keys`), não de um campo fixo no catálogo:
 * assim a trava some sozinha quando a chave entra, sem ninguém ter de lembrar
 * de destravar nada. */
function elLocked(e) {
  if (!e.needsKey) return '';
  const keys = S.keys || {};
  // sem resposta do servidor ainda: não trave. Um "false" por ausência de
  // dado travaria a opção no primeiro segundo de cada carregamento.
  if (!(e.needsKey in keys)) return '';
  return keys[e.needsKey] ? '' : (e.keyMsg || 'Falta a chave de API para isto.');
}

function defaultStyle() {
  const elements = {};
  for (const e of STYLE_CATALOG.elements) elements[e.id] = !!e.def;
  return {
    edit: STYLE_CATALOG.edits[0].id,
    headline: STYLE_CATALOG.headlines[0].id,
    captions: STYLE_CATALOG.captions[0].id,
    accent: ACCENT_DEFAULT,
    capColor: '#FFFFFF',
    /* A COR PRINCIPAL DA HEADLINE, separada da `capColor` da legenda.
       O destaque continua ÚNICO para as duas de propósito — um vídeo com dois
       laranjas diferentes não lê como um vídeo, lê como um erro. Já a cor do
       corpo se separa porque headline e legenda vivem sobre fundos diferentes:
       a legenda cai sobre a costura da tela dividida e a headline sobre a
       imagem, e a mesma escolha raramente serve às duas. */
    textColor: '#FFFFFF',
    fontMain: FONT_MAIN_DEF,
    fontAccent: FONT_ACCENT_DEF,
    /* A LEGENDA TEM FONTE PRÓPRIA — UMA — e não herda a da headline: as duas
       vivem em zonas diferentes do quadro e raramente pedem a mesma letra (a
       headline grita, a legenda tem de ser lida corrida). UMA e não um par:
       onde um estilo alterna famílias, como a serifada do empilhado, isso é
       identidade DELE, não vaga de escolha. O `null` é "o padrão do estilo",
       então trocar de estilo traz de volta a letra com que ele foi desenhado. */
    capFont: null,
    capDy: 0,   // deslocamento GLOBAL da legenda, em px de referência 1080
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
/* Lead e cauda vêm do render (jcut_timeline), MENOS quando o usuário discordou
 * deles arrastando as bordas em A1/A2. O override mora no rascunho em QUADROS,
 * que é a unidade do `edl.json` (`jcut_lead_frames` / `jcut_tail_frames`) e a do
 * render — converter para segundos aqui e de volta na hora de salvar traria
 * erro de arredondamento numa grandeza onde 1 quadro importa. */
function jcutGeom(i) {
  const fps = S.fps || 30;
  const r = S.draft && S.draft[i];
  const j = S.jcut && S.jcut[i];
  const base = j
    ? { lead: Math.max(0, (j.video_start_in_output || 0) - (j.audio_start_in_output || 0)),
        tail: (j.tail_trim_frames || 0) / fps }
    : { lead: 0, tail: 0 };
  if (!r) return base;
  return {
    lead: r.leadF != null ? r.leadF / fps : base.lead,
    tail: r.tailF != null ? r.tailF / fps : base.tail,
  };
}

// limites de ofício: mais de 1s de lead põe a imagem no meio da fala seguinte,
// e mais de 1s de cauda aparada come palavra em qualquer take que feche justo
const JCUT_MAX_F = 30;

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
/* Qual take está sendo aparado agora — usado para CONGELAR o bloco durante o
   arraste, para que aparar o começo não encolha o bloco pela direita. Precisa
   ser global: a onda e os clipes desenham a mesma decisão, e uma cópia local
   em cada um foi o que deixou as duas pistas discordando. */
const trimIdx = () => (drag && drag.type === 'trim' ? drag.i : null);

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
const wordsDirty = () => S.cutWords.size > 0 || S.cutBreaths.size > 0;

/* ---------- DESFAZER ----------
 * Cobre DUAS ações, de propósito: apagar um take da linha do tempo e
 * redimensioná-lo. São as únicas destrutivas de verdade — desfazer uma rasura
 * de palavra ou um respiro já é clicar de novo no mesmo lugar, e empilhar isso
 * aqui faria ⌘Z desfazer algo diferente do que a pessoa acabou de fazer, que é
 * pior que não ter undo.
 *
 * Instantâneo de `S.draft` inteiro, não uma inversa por ação: um take carrega
 * start, end, removed, leadF, tailF e `orig`, e restaurar campo a campo é onde
 * se acaba devolvendo QUASE o estado certo. São ~30 objetos rasos por edição.
 *
 * `pushUndo()` é sempre a PRIMEIRA linha de quem muta — chamada depois, salva o
 * estado já alterado e o desfazer vira um no-op silencioso. */
const UNDO_MAX = 50;

function pushUndo(label) {
  S.undo.push({ label, draft: (S.draft || []).map((r) => ({ ...r, orig: { ...r.orig } })) });
  if (S.undo.length > UNDO_MAX) S.undo.shift();
  refreshUndo();
}

function undoLast() {
  const s = S.undo.pop();
  if (!s) return;
  S.draft = s.draft;
  S.selected = -1;   // o índice selecionado pode ter mudado de dono
  renderAll();
  refreshHeader();
  refreshUndo();
  toast(`desfeito: ${s.label}`, 1800);
}

function refreshUndo() {
  const b = $('btnUndo');
  if (!b) return;
  const s = S.undo[S.undo.length - 1];
  b.disabled = !s;
  b.title = s ? `Desfazer ${s.label} (⌘Z)` : 'Nada a desfazer';
}
const jcutDirty = () => S.draft.some((r) => r.leadF != null || r.tailF != null);

function edlDirty() {
  return S.draft.some((r) => r.removed || r.start !== r.orig.start || r.end !== r.orig.end) || jcutDirty();
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
  $('savedPill').classList.toggle('hidden', !(S.savedPending && dirtyCount() === 0));
  refreshExport();
  refreshActionBar();
}

/* O estilo diverge do que está gravado no projeto?
 *
 * Devolve 'changed' (o usuário mexeu), 'unset' (nunca houve escolha) ou ''.
 * A distinção não é cosmética: as duas coisas pedem frases OPOSTAS na barra.
 * Enquanto isto era um booleano, um projeto com `awaitingStyle` anunciava
 * "1 alteração — vai refazer a finalização" sem ninguém ter alterado nada,
 * e a barra descrevia um refazimento onde não havia o que refazer.
 */
function styleState() {
  if (!setupApplies()) return '';
  /* `awaitingStyle` NÃO dispensa a comparação — só muda o que o empate quer
   * dizer. Enquanto ele devolvia 'unset' de saída, a barra anunciava "Estilo
   * ainda não escolhido" por mais opções que a pessoa marcasse: a tela negava
   * a escolha que ela acabara de fazer, e isso lê como clique que não pegou.
   * Agora 'unset' quer dizer "ninguém mexeu, os padrões valem" e 'changed'
   * quer dizer "mexeu" — nos dois casos `styleDirty()` segue verdadeiro,
   * porque é enviando o estilo que o projeto sai de `awaitingStyle`. */
  const def = defaultStyle();
  const cur = S.state.style || {};
  /* AUSENTE é igual ao PADRÃO. Sem isto, toda chave nova (o `capColor` foi a
   * última) marcava como alterado todo projeto salvo antes dela existir: o
   * lado local tinha o padrão, o gravado não tinha a chave, e a comparação
   * dizia "mudou" para sempre — uma alteração fantasma que não some nem
   * salvando, porque salvar grava o padrão e o próximo projeto antigo repete. */
  const val = (o, k, d) => {
    const v = o[k];
    return JSON.stringify((v === undefined || v === null ? d : v) ?? null);
  };
  const same = (k, d) => val(S.style, k, d) === val(cur, k, d);
  const ok = same('edit', def.edit) && same('headline', def.headline)
    && same('captions', def.captions) && same('accent', def.accent)
    && same('capColor', def.capColor) && same('headlineText', def.headlineText)
    && same('capDy', 0)
    /* `elements` compara CHAVE A CHAVE, não como objeto inteiro.
     *
     * O JSON do objeto todo repete, um nível mais fundo, o mesmo defeito que
     * `same()` corrige na superfície: um projeto salvo ANTES de uma opção
     * existir não tem a chave dela, o lado local tem o padrão, e o objeto
     * inteiro sai diferente. Cada opção nova no catálogo marcava como alterado
     * todo projeto anterior a ela — e salvar não resolvia, porque o próximo
     * projeto antigo repetia. Foi o que a opção `sfx` acabou de causar. */
    && Object.keys(def.elements).every((k) => {
      const d = !!def.elements[k];
      const a = S.style.elements || {}, b = cur.elements || {};
      const va = k in a ? !!a[k] : d;
      const vb = k in b ? !!b[k] : d;
      return va === vb;
    });
  if (S.state.awaitingStyle) return ok ? 'unset' : 'changed';
  return ok ? '' : 'changed';
}
const styleDirty = () => styleState() !== '';

/* A BARRA DE AÇÃO nomeia a CONSEQUÊNCIA, não o verbo. "Enviar" não distingue
 * mandar duas marcações de disparar um render de minutos, e essas duas coisas
 * não podem custar o mesmo clique sem aviso. */
function refreshActionBar() {
  const bar = $('actionBar');
  if (!bar) return;
  const cuts = edlDirty();
  const ins = insertsDirty();
  const notes = S.notes.length + (wordsDirty() ? 1 : 0);
  const style = styleDirty();
  const has = cuts || ins || notes || style;
  /* O PEDIDO EM TEXTO é um canal, não um apêndice das alterações.
   *
   * A barra inteira sumia quando não havia nada marcado — e levava a caixa de
   * texto junto. Resultado: no estado mais comum da tela (nada alterado), o
   * usuário ficava SEM NENHUMA forma de pedir uma mudança à IA. Ele tinha de
   * marcar algo que não queria só para o campo aparecer.
   *
   * Agora a barra fica sempre que há vídeo e nada rodando. Quem some não é o
   * canal: é a AÇÃO, pelo botão desabilitado. */
  const pedido = ($('setupNote') && $('setupNote').value.trim()) || '';
  const temAlgo = has || !!pedido;
  bar.classList.toggle('hidden', !(S.videoDuration > 0) || S.processing);
  $('procBar').classList.toggle('hidden', !S.processing);

  /* A barra de aprovação divide o mesmo canto e é MUTUAMENTE EXCLUSIVA com a de
     alterações: aprovar com correção pendente diria "está pronto" e "conserte
     isto" ao mesmo tempo. Aparece na FASE 1, com vídeo em tela, nada pendente e
     nada rodando — e some quando a fase vira 2.

     Deliberadamente NÃO exige `onProxy()`. Prender o botão ao nome do arquivo
     misturava duas perguntas diferentes: QUAL versão está em tela e SE o corte
     já foi aprovado. Um projeto cujo Fase 1 saiu direto como `preview.mp4`
     (sem passar pelo proxy) continua precisando de aprovação, e escondia o
     botão exatamente de quem não tinha outro jeito de aprovar. O proxy segue
     governando as CAMADAS DO RENDER, que é onde ele importa. */
  /* A BARRA DE APROVAÇÃO FOI UNIFICADA NO BOTÃO DE ENVIO. Duas barras no mesmo
     canto respondiam à mesma pergunta ("o que eu faço agora?") com dois lugares
     diferentes — e o pedido do usuário foi direto: sem mudanças o botão diz
     "Aprovar corte"; com mudanças, "Enviar". O arquivo continua o mesmo
     (`preview_approval.json`) e a nota vai no campo único. */
  const ap = $('approveBar');
  if (ap) ap.classList.add('hidden');

  if (!(S.videoDuration > 0) || S.processing) return;

  /* A TRAVA. Sem alteração e sem texto não há o que executar, e um botão vivo
   * que não faz nada é pior que um apagado: o usuário clica, não acontece
   * nada, e ele não sabe se falhou ou se não havia o que fazer. */
  const go = $('setupGo');
  go.disabled = !temAlgo;
  $('btnDiscard').classList.toggle('hidden', !has);

  const podeAprovar = !temAlgo && !S.approved
    && S.videoDuration > 0 && (S.state.phase || 1) === 1;
  go.dataset.mode = podeAprovar ? 'approve' : '';
  go.classList.toggle('aprovar', podeAprovar);
  if (podeAprovar) {
    $('actionCount').textContent = 'Fase 1 pronta para aprovação';
    go.disabled = false;
    go.innerHTML = 'Aprovar corte';
    go.title = 'Libera o corte final e as camadas do render — mudou algo, o botão vira Enviar';
    $('actionWhat').textContent = '';
    return;
  }
  if (!temAlgo) {
    $('actionCount').textContent = 'Nada a enviar';

    go.innerHTML = `<span class="btn-ai">${ICON.ai}</span>Enviar`;
    go.title = 'Escreva um pedido ou faça uma marcação para habilitar';
  $('actionWhat').textContent = '';
    return;
  }

  /* Só texto, nada marcado: é um PEDIDO, e nomear isso importa. "0 alterações"
   * ao lado de um botão que vai acionar a IA seria mentira nas duas metades. */
  if (!has) {
    $('actionCount').textContent = 'Pedido para a IA';

    go.innerHTML = `<span class="btn-ai">${ICON.ai}</span>Enviar pedido`;
    go.title = 'Manda o texto para a IA ler; ela decide se precisa renderizar';
    $('actionWhat').textContent = '';
    return;
  }

  // dirtyCount() conta corte, inserções e marcações — não conta estilo. Sem
  // este ajuste, mudar só o estilo mostrava "0 alterações" ao lado de um botão
  // que ia renderizar o vídeo inteiro.
  const stState = styleState();
  const total = dirtyCount() + (style ? 1 : 0);
  /* "escolha nunca feita" NÃO é alteração. Contá-la como uma dava
     "1 alteração" numa tela onde o usuário não tinha tocado em nada. */
  const onlyUnset = stState === 'unset' && dirtyCount() === 0;
  $('actionCount').textContent = onlyUnset
    ? 'Estilo ainda não escolhido'
    : (total === 1 ? '1 alteração' : `${total} alterações`);

  const vai = [];
  if (cuts) vai.push('refazer o corte');
  if (style || ins) vai.push(S.state.finalVideo ? 'refazer a finalização' : 'montar a finalização');
  if (notes) vai.push(wordsDirty() ? 'ler o que foi riscado no texto e as marcações' : 'ler as suas marcações');
  if (pedido) vai.push('ler o seu pedido');
  /* A CONSEQUÊNCIA saiu da barra e virou o `title` do botão.
   * A frase longa competia com o número — que é a informação que se lê de
   * relance — e repetia o que o próprio rótulo do botão já diz. */
  $('actionWhat').textContent = '';

  /* O aviso que substituiu o modal. `actionWhat` estava vazio desde que a
     CONSEQUÊNCIA virou `title` do botão — e um alerta não é uma consequência:
     é uma coisa errada agora, que precisa estar na tela antes do clique. */
  if (styleDirty() && S.style.headline && !(S.style.headlineText || '').trim()) {
    $('actionWhat').innerHTML = '<span class="warn-inline">⚠ headline sem texto — '
      + 'vai sair sem headline</span>';
  }

  const caro = style || ins || cuts;
  $('setupGo').innerHTML = `<span class="btn-ai">${ICON.ai}</span>`
    + (caro ? 'Enviar e renderizar' : 'Enviar marcações');
  $('setupGo').title = caro
    ? 'Vai para a IA e renderiza de novo — leva alguns minutos'
    : 'Manda as marcações para a IA ler; não renderiza nada';
}

// ---------- data loading ----------
/* Quando ESTA página nasceu, em segundos de relógio de parede — a régua do
   aviso de página velha logo abaixo. Servidor e navegador são a mesma máquina
   (localhost), então comparar Date.now() com mtime de arquivo é honesto. */
const PAGE_BORN = Date.now() / 1000;
async function poll() {
  try {
    const res = await fetch('/api/state');
    const data = await res.json();
    const sig = JSON.stringify([data.state, data.edl, data.mtimes, data.videoDuration]);
    // FORA da assinatura, de propósito: o progresso muda a cada segundo, e
    // remontar a timeline a cada tique seria absurdo. Pior — o guarda de
    // "você tem ajustes não salvos" logo abaixo bloquearia a atualização
    // justamente enquanto o usuário espera, que é quando ele mais precisa ver.
    if (data.keys) S.keys = data.keys;
    // O QUE A MÁQUINA TEM. Fora da assinatura pelo mesmo motivo do progresso:
    // não muda a linha do tempo, e a checklist tem de acertar já no primeiro
    // poll — inclusive na tela inicial, onde não há projeto e `applyState`
    // sai antes de tudo.
    if (data.deps) S.deps = data.deps;
    renderDepsCard();
    setProgress(data.progress || null);
    // servidor velho servindo app novo: avisa UMA vez, com a instrução, em vez
    // de deixar o usuário descobrir por 404 em cada botão novo
    if (data.serverStale && !S.staleWarned) {
      S.staleWarned = true;
      toast('O servidor de preview está desatualizado em relação ao editor — reinicie-o para liberar o que é novo', 9000);
    }
    // O ESPELHO: página velha com arquivos novos no disco. Um estilo que
    // entrou no catálogo depois desta aba carregar não existe aqui — sem
    // erro, sem 404, o cartão só não aparece (medido: a cartela `noticia`).
    // Os 2s de folga evitam acusar a própria carga da página.
    if (data.appMtime && data.appMtime > PAGE_BORN + 2 && !S.pageStaleWarned) {
      S.pageStaleWarned = true;
      toast('O editor foi atualizado desde que esta aba abriu — recarregue a página (⌘R) para ver o que é novo', 9000);
    }
    checkProcessing();
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
  /* NENHUM PROJETO ABERTO É UM ESTADO, não uma falha de carregamento.
     Sai antes de tudo: o resto desta função pressupõe um corte, um vídeo e um
     EDL, e sem projeto nada disso existe — seguir daqui desenharia uma linha
     do tempo vazia sob o cabeçalho de um projeto que ninguém abriu. */
  if (data.keys) S.keys = data.keys;
  if (data.deps) S.deps = data.deps;
  if (data.noProject) { showHome(); return; }
  hideHome();
  S.state = data.state || {};
  S.mtimes = data.mtimes || {};
  S.videoDuration = data.videoDuration || 0;
  S.fps = S.state.fps || 24;
  S.savedPending = !!data.hasPendingEdits;

  $('projectName').textContent = S.state.project || 'Avelin';
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
  /* A MARCA ENTRA ENTRE O PADRÃO E O PROJETO, nessa ordem exata.
     Cor e fonte são de QUEM faz, não do que está sendo feito — então um projeto
     novo já nasce com as do usuário em vez do laranja de fábrica. Mas o que o
     PROJETO gravou vence sempre: reabrir um vídeo entregue tem de mostrar as
     cores com que ele foi entregue, e não as de hoje. */
  /* Quatro camadas, nesta ordem: o padrão de fábrica, as ESCOLHAS da última
     vez, a marca (cor e letra), e por último o que o projeto gravou. As
     escolhas vêm antes da marca porque a marca é mais específica — ela é sobre
     quem faz, não sobre como se costuma fazer — e as duas antes do projeto,
     que vence sempre. */
  S.style = { ...defaultStyle(), ...(S.prefs || {}), ...(S.brand || {}),
              ...(S.state.style || {}) };
  S.style.elements = { ...defaultStyle().elements, ...((S.prefs || {}).elements || {}),
                       ...((S.state.style || {}).elements || {}) };
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
  // Legenda é da Fase 2 e só existe depois do render — continua atrás do portão.
  if ((S.state.phase || 1) >= 2 && S.state.captions) {
    try {
      const caps = await (await fetch(`/media/${S.state.captions}?v=${Date.now()}`)).json();
      S.captions = groupCaptions(caps);
    } catch (e) { /* absent yet */ }
  }
  /* O edit-data, NÃO. Ele é lido desde a Fase 1, porque é onde moram os
     RESERVADOS: os elementos que ocupam tempo de tela e ainda não existem —
     a roleta, o B-roll, a faixa de tela dividida. Sem eles na linha do tempo o
     usuário aprova uma montagem com buracos que não consegue ver, e descobre
     que o buraco não fecha depois de o portão já ter passado. */
  if (S.state.editData) {
    try {
      S.editData = await (await fetch(`/media/${S.state.editData}?v=${Date.now()}`)).json();
      buildInsertsDraft();
    } catch (e) { /* absent yet */ }
  }
  /* Efeitos sonoros. Vêm do sfx-events.json que o composer publica, e não do
     edit-data: eles são DERIVADOS (entrada de cartão, corte, deixa em
     destaque), então o edit-data não os conhece. Como só existem depois de
     compor, ficam atrás do mesmo portão da legenda. */
  S.sfx = [];
  /* FASE 2 NÃO É O MESMO QUE JÁ COMPÔS. O portão era só `phase >= 2`, e o
     caminho padrão `hyperframes/sfx-events.json` é escrito pelo compositor —
     então todo projeto que entra na Fase 2 e ainda não renderizou pedia um
     arquivo que não existe e levava um 404 no console a cada carga. O try/catch
     escondia a consequência, não a causa: um erro de rede visível que não é
     erro nenhum ensina a ignorar o console.
     Agora só se busca quando há composição de fato — `sfxEvents` publicado pelo
     servidor, ou um `finalVideo` que prova que o compositor já rodou. */
  const alvoSfx = S.state.sfxEvents
    || (S.state.finalVideo ? 'hyperframes/sfx-events.json' : null);
  if ((S.state.phase || 1) >= 2 && alvoSfx) {
    try {
      S.sfx = await (await fetch(`/media/${alvoSfx}?v=${Date.now()}`)).json();
    } catch (e) { /* ainda não compôs */ }
  }

  fitZoom();
  renderAll();
  renderSetup();
  refreshHeader();
}

// Fase 1 plays the clean cut; Fase 2 plays the Phase-2 render (state.finalVideo)
// when it exists, so captions/inserts are visible. Keeps the playback position.
function updateVideoSrc() {
  /* A FONTE SE RESOLVE SOZINHA, e o botão de alternar saiu.
   *
   * A pergunta nunca foi "qual dos dois você quer ver" — é sempre o mais
   * completo que ainda seja VERDADE. Antes da finalização só existe o corte;
   * depois, o final. E se o corte mudar, o final vira um render do corte
   * ANTERIOR: a linha do tempo passa a dizer uma coisa e o vídeo a mostrar
   * outra, sem nada avisar. Aí a resposta certa é voltar ao corte, não deixar
   * o usuário perceber sozinho.
   *
   * Obsoleto = o corte é mais novo que o final, OU há ajuste ainda não enviado.
   * Os dois querem dizer a mesma coisa: o que está na tela não é o que a
   * timeline descreve. */
  const mt = S.mtimes || {};
  const stale = !S.state.finalVideo
    || (mt.video && mt.finalVideo && mt.video > mt.finalVideo)
    || dirtyCount() > 0;
  S.showFinal = !stale;
  const rel = S.showFinal ? S.state.finalVideo : (S.state.video || 'preview.mp4');
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

/* Um elemento é RESERVADO enquanto não tem mídia no disco: `planned: true` no
   dado, ou simplesmente nenhum `src`/`file`. Ele guarda o tempo e diz o que vai
   ali. A distinção é do DADO, não da fase — na Fase 2 um insert cuja imagem
   ainda não baixou também é um buraco, e mostrá-lo como pronto esconderia isso. */
const isPlanned = (it) => !!it.planned || !(it.src || it.file || it.id);

function buildInsertsDraft() {
  const d = S.editData;
  const list = [];
  if (d.hook && d.hook.enabled) {
    list.push({ kind: 'hook', label: `HOOK — ${(d.hook.lines || []).join(' / ')}`, start: 0, end: d.hook.endSec || 4 });
  }
  (d.inserts || []).forEach((it, i) => {
    list.push({ kind: 'insert', label: it.label || (it.src || '').split('/').pop() || '(reservado)',
                start: +it.start, end: +it.end, ref: i, planned: isPlanned(it) });
  });
  // split-layout images (CustomGraphics reads the same array) — they are images
  // like any other insert, so they belong on the image track, not in code
  (d.splitInserts || []).forEach((it, i) => {
    list.push({
      kind: 'split',
      label: it.label || (it.src || '').split('/').pop() || '(reservado)',
      start: +it.start, end: +it.end, ref: i, planned: isPlanned(it),
    });
  });
  // split-layout VIDEO bands — same seam and geometry as splitInserts, but the
  // band plays a clip (generated b-roll, screen capture). Its own array because
  // the renderer mounts it with a different component; on the timeline it is an
  // image-track element like any other.
  (d.splitVideos || []).forEach((it, i) => {
    list.push({
      kind: 'splitvideo',
      label: it.label || (it.src || '').split('/').pop() || '(reservado)',
      start: +it.start, end: +it.end, ref: i, planned: isPlanned(it),
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
  (d.brollOverlays || []).forEach((o, i) => {
    const rot = o.kind === 'media'
      ? (o.src || 'mídia').split('/').pop()
      : (o.text || o.value || (o.items || []).join(' · ') || o.kind || 'overlay');
    list.push({
      kind: 'broll',
      label: `${o.dim ? 'OVERLAY● ' : 'OVERLAY '}${rot}`,
      start: +o.start, end: +o.end, ref: i,
    });
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
  renderSfx();
  renderChips();
  renderNotes();
  renderCutMarks();
  drawRuler();
  drawWave();
  refreshCounts();
  updateScrollRange();
  positionNeedle();
}

/* ---------- onde o texto riscado cai na linha do tempo ----------
 *
 * Marcação, e só. Nada aqui é clicável (`pointer-events:none` no CSS) — o que
 * também evita mexer no `pointerdown` do painel, que já tem um histórico ruim:
 * ele captura o ponteiro e retarget a o clique seguinte.
 *
 * As palavras são desenhadas pelo tempo de SAÍDA (`outStart` + a duração da
 * palavra na fonte), que é o mesmo relógio das trilhas. E palavras vizinhas
 * viram UMA faixa: riscar quatro palavras seguidas tem de ler como um trecho a
 * sair, não como quatro tracinhos que o olho ainda precisa juntar.
 *
 * Respiros marcados ficam DE FORA de propósito. Eles são encurtados, não
 * removidos — sai o excedente e o piso permanece —, então uma faixa cobrindo o
 * respiro inteiro afirmaria uma remoção que não vai acontecer. Marca que mente
 * é pior que marca ausente. */
const CUTMARK_JOIN = 0.20;   // vão abaixo disto funde duas faixas

function cutSpans() {
  if (!S.cutWords.size || !S.words.length) return [];
  const idx = [...S.cutWords].sort((a, b) => a - b);
  const spans = [];
  for (const i of idx) {
    const w = S.words[i];
    if (!w) continue;
    const dur = Math.max(0.05, (w.srcEnd || 0) - (w.srcStart || 0));
    const a = w.outStart, b = w.outStart + dur;
    const last = spans[spans.length - 1];
    if (last && a - last.end <= CUTMARK_JOIN) {
      last.end = Math.max(last.end, b);
      last.n += 1;
    } else {
      spans.push({ start: a, end: b, n: 1 });
    }
  }
  return spans;
}

function renderCutMarks() {
  const host = $('cutOverlay');
  if (!host) return;
  host.innerHTML = '';
  for (const s of cutSpans()) {
    const band = el('div', 'cut-band', host);
    band.style.left = `${s.start * S.pps}px`;
    band.style.width = `${Math.max((s.end - s.start) * S.pps, 2)}px`;
    band.title = `${s.n} palavra(s) marcada(s) para remoção`;
  }
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
  // marcar no modo compacto criaria o pino numa trilha invisível — expande
  // antes, para o IN já nascer na frente dos olhos
  if ($('timeline').classList.contains('compact')) setTlMode(false);
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
/* Quem PINTA o destaque sai do `variants.json` (`usesAccent`), com esta lista
 * de reserva só para a janela antes do fetch voltar. Era uma lista fixa com um
 * pedido de "mantenha em dia com o template" — e ao entrarem sete layouts ela
 * teria dito que nenhum deles usa destaque, deixando a nota da interface
 * mentir exatamente onde ela existe para não mentir. */
const ACCENT_USERS_FALLBACK = {headlines: ['realce', 'misto'], captions: ['stacked']};
const ACCENT_USERS = {
  get headlines() {
    const H = (LIVE.variants || {}).headlines;
    return H ? Object.keys(H).filter((k) => H[k].usesAccent) : ACCENT_USERS_FALLBACK.headlines;
  },
  get captions() { return ACCENT_USERS_FALLBACK.captions; },
};
/* AVELIN-OVERLAY */ if (window.AVELIN_LOCAL) window.AVELIN_LOCAL.install({STYLE_CATALOG, CAP_BUILDERS, ACCENT_USERS});
const ACCENT_DEFAULT = '#ff3b30';

function applyAccent() {
  const p = $('layersPanel');
  p.style.setProperty('--hl-accent', S.style.accent || ACCENT_DEFAULT);
  /* A cor principal desce pelo PAINEL, não por atributo em cada prévia. É o que
     deixa arrastar a roda de cor atualizar as onze prévias ao vivo: um valor
     embutido em cada caixa venceria a variável, e a cor só mudaria no próximo
     remonte — que não acontece durante o arrasto, de propósito. */
  p.style.setProperty('--hl-main', normHex(S.style.textColor) || '#FFFFFF');
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
    paintHeadlines();
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
    // `key`/`def`, NAO `accent`/ACCENT_DEFAULT: fixo no accent, digitar algo
    // invalido no campo da cor PRINCIPAL e sair preenchia ele com o hex do
    // destaque — o campo passava a mentir sobre a propria cor.
    hex.value = (normHex(S.style[key]) || fallback).slice(1).toUpperCase();
  });
  hex.addEventListener('keydown', (e) => { if (e.key === 'Enter') hex.blur(); });

  updateAccentNote();
}

function renderAccents() {
  renderColor('optAccent', 'accent', ACCENT_DEFAULT, 'Cor de destaque');
  renderColor('optCapColor', 'capColor', '#FFFFFF', 'Cor principal da legenda');
  // A headline tem os mesmos DOIS controles, na camada dela. O destaque é a
  // MESMA chave `accent` — mudar por um lado muda o outro, que é o ponto.
  renderColor('optAccentHl', 'accent', ACCENT_DEFAULT, 'Cor de destaque');
  renderColor('optTextColor', 'textColor', '#FFFFFF', 'Cor principal da headline');
  renderFonts();
}

/* O seletor de família. Um `<select>` e não uma grade de cartões: são 27
 * famílias, e cada opção se desenha NA PRÓPRIA FONTE — é assim que se escolhe
 * tipo, olhando a letra, não lendo o nome dela. */
function renderFont(hostId, key, fallback, label) {
  const host = $(hostId);
  if (!host) return;
  host.innerHTML = '';
  const cur = S.style[key] || fallback;
  // só as do GOOGLE precisam ser carregadas; as locais já estão no sistema e
  // as empacotadas entram pelo @font-face de ensureBundled()
  ensureFonts(gfonts().map((f) => f.n));
  const sel = el('select', 'font-sel', host);
  sel.setAttribute('aria-label', label);
  const GRUPO = { display: 'sem serifa', serif: 'com serifa',
                  manuscrita: 'manuscrita', local: 'do seu computador' };
  let grupo = null;
  let og = null;
  for (const f of allFonts()) {
    if (f.k !== grupo) {
      grupo = f.k;
      og = el('optgroup', '', sel);
      og.label = GRUPO[grupo] || grupo;
    }
    const o = el('option', '', og || sel);
    o.value = f.n;
    o.textContent = f.n;
    // a opção desenhada NA PRÓPRIA FONTE — é assim que se escolhe tipo
    o.style.fontFamily = cssFamily(f.n);
    if (f.n === cur) o.selected = true;
  }
  const amostra = el('div', 'font-sample', host);
  const pinta = (n) => { amostra.style.fontFamily = cssFamily(n); amostra.textContent = 'Aa Gg 123'; };
  pinta(cur);
  sel.addEventListener('change', () => {
    S.style[key] = sel.value;
    pinta(sel.value);
    updateFontNote();
    updateSummary();
    // as prévias medem com a fonte REAL: sem esperar o carregamento, a primeira
    // montagem ajusta o corpo pela fonte de sistema e sai com a largura errada
    ensureFonts([S.style.fontMain, S.style.fontAccent]);
    // fonte local já está no sistema: esperar `document.fonts.load` por ela
    // resolve na hora, mas a chamada existe para as que baixam
    document.fonts.load(`900 40px "${sel.value}"`).then(() => renderSetup(), () => renderSetup());
  });
}

function renderFonts() {
  renderFont('optFontMain', 'fontMain', FONT_MAIN_DEF, 'Fonte principal');
  renderFont('optFontAccent', 'fontAccent', FONT_ACCENT_DEF, 'Fonte de destaque');
  // A legenda tem o par dela. O padrão de cada campo é a família do ESTILO
  // escolhido, não uma constante: assim trocar de estilo traz de volta a letra
  // com que ele foi desenhado, até alguém escolher outra de propósito.
  const v = capVariant();
  renderFont('optCapFontMain', 'capFont', v.family || FONT_MAIN_DEF, 'Fonte da legenda');
  updateFontNote();
  updateCapFontNote();
}

// os números do estilo de legenda escolhido
const capVariant = () =>
  ((LIVE.variants && LIVE.variants.styles) || {})[S.style.captions] || {};

function updateCapFontNote() {
  const n = $('capFontNote');
  if (!n) return;
  const fam = S.style.capFont || capVariant().family;
  n.textContent = isLocal(fam)
    ? 'do seu computador: sai igual aqui, não em outra máquina'
    : (S.style.capFont ? '' : 'a família de fábrica deste estilo');
}

/* ---------- a marca ----------
 * Cor e família não mudam de vídeo para vídeo: são de quem faz. Guardadas em
 * `~/.avelin/brand.json`, FORA do projeto, elas viram o ponto de partida do
 * próximo — em vez de o usuário redigitar o mesmo hexadecimal toda vez e um
 * dia errar um dígito, entregando dois laranjas parecidos na mesma série.
 * O agente escreve no mesmo arquivo quando descobre a marca por outro caminho. */
const BRAND_KEYS = ['accent', 'textColor', 'capColor', 'fontMain', 'fontAccent',
                    'capFont'];

async function loadBrand() {
  try {
    const d = await (await fetch('/api/brand')).json();
    S.brand = d && typeof d === 'object' ? d : null;
  } catch (e) { S.brand = null; }
}

/* AS ESCOLHAS DA ÚLTIMA VEZ (~/.avelin/estilo.json): formato do corte,
   headline, estilo de legenda, elementos ligados e o deslocamento da legenda.
   Escrito pelo servidor no mesmo ato do envio do estilo — aqui só se lê.
   Existe pela mesma razão do brand: refazer as mesmas escolhas em todo projeto
   é trabalho que a ferramenta pode poupar. E vale a MESMA ordem: o que o
   projeto gravou continua vencendo, senão reabrir um vídeo entregue mostraria
   o gosto de hoje no lugar do que foi entregue. */
async function loadEstilo() {
  try {
    const d = await (await fetch('/api/estilo')).json();
    S.prefs = d && typeof d === 'object' ? d : null;
  } catch (e) { S.prefs = null; }
}

async function saveBrand(btn) {
  const body = {};
  for (const k of BRAND_KEYS) if (S.style[k]) body[k] = S.style[k];
  try {
    const r = await fetch('/api/brand', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || 'falhou');
    S.brand = d.brand;
    if (btn) { btn.textContent = '✓ guardado'; setTimeout(() => { btn.textContent = 'salvar como minha marca'; }, 2200); }
  } catch (e) { toast(`não consegui guardar a marca: ${e.message}`, 4000); }
}

// a marca já está gravada e IGUAL ao que está na tela? então não há o que salvar
const brandMatches = () =>
  !!S.brand && BRAND_KEYS.every((k) => !S.style[k] || S.brand[k] === S.style[k]);

/* Quais layouts realmente usam a SEGUNDA família. Mesma honestidade da nota do
 * destaque: escolher uma manuscrita para um layout que não a desenha é escolher
 * no vazio, e a interface tem de dizer isso. */
function updateFontNote() {
  const n = $('fontNote');
  if (!n) return;
  const S2 = hlStyle(S.style.headline);
  const papel = (S2 && S2.fontRole)
    ? 'a de destaque desenha a primeira linha deste layout'
    : 'este layout usa só a principal';
  /* O PREÇO DA FONTE LOCAL, dito onde ela é escolhida. Ela funciona porque o
     render roda NESTA máquina — e é exatamente por isso que o projeto deixa de
     sair igual em outra. Descobrir isso ao trocar de computador, com o vídeo já
     aprovado, seria caro; a frase custa uma linha. */
  const locais = [
    isLocal(S.style.fontMain) && 'principal',
    (S2 && S2.fontRole) && isLocal(S.style.fontAccent) && 'destaque',
  ].filter(Boolean);
  n.textContent = locais.length
    ? `${papel} · a ${locais.join(' e a ')} ${locais.length > 1 ? 'são' : 'é'} `
      + 'do seu computador: sai igual aqui, não em outra máquina'
    : papel;
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
  const box = $('depsSummary');
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
    ico: 'inserts', caixaText: true, groups: ['edits'] },
  { id: 'headline', name: 'Headline', sub: 'Título, cores, fontes e layout',
    ico: 'text', headlineText: true, hlColors: true, fonts: true, groups: ['headlines'] },
  { id: 'legendas', name: 'Legendas', sub: 'Estilo, cores e fontes',
    ico: 'captions', colors: true, capFonts: true, groups: ['captions'] },
  { id: 'movimento', name: 'Movimento & tracking', sub: 'Animações, máscaras, rastreamento e keyframes',
    ico: 'video', elements: ['tracking', 'zoomAuto', 'zoomCuts'] },
  { id: 'transicoes', name: 'Transições', sub: 'Cortes, fades e transições entre clipes',
    ico: 'notes', elements: ['flashCut'] },
  { id: 'trilha', name: 'Trilha & mixagem', sub: 'Áudio, níveis, ducking e mixagem final',
    ico: 'music', elements: ['sfx', 'musicAI'] },
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
/* E o portão é ESTRUTURAL, não só de comportamento. `awaitingStyle` depende de
 * alguém do outro lado lembrar de ligá-lo na hora certa; o proxy não depende de
 * ninguém. Enquanto o vídeo em tela for o `preview_proxy.mp4` — 720p, a versão
 * que se ITERA — a Fase 1 não foi aprovada, e escolher acabamento sobre um corte
 * que ainda vai mudar é trabalho que se joga fora.
 * Aprovado, o render final vira `preview.mp4` e o painel libera sozinho. */
const onProxy = () => /(^|\/)preview_proxy\.mp4$/.test(S.state.video || '');
const setupApplies = () => !!(S.state.awaitingStyle || S.state.style) && !onProxy();

function renderSetup() {
  // o tamanho do cartão é o do quadro, e tem de estar escrito ANTES de os
  // construtores medirem `clientWidth` para calcular a escala
  aplicarQuadro();
  /* O REBUILD NÃO PODE ROUBAR O CURSOR. Esta função recria o painel inteiro —
     inclusive o textarea da headline e o campo hex — e é chamada no debounce da
     própria digitação: sem isto, cada pausa de 260ms destruía o elemento
     focado e o usuário perdia o ponteiro de texto no meio da frase (reportado
     em 2026-08-18). Captura o foco ANTES de reconstruir e o devolve, com a
     seleção, no frame seguinte — cobre qualquer caminho de retorno abaixo. */
  const af = document.activeElement;
  if (af && af.id && $('layersPanel') && $('layersPanel').contains(af)) {
    const sel = (af.selectionStart != null && af.selectionEnd != null)
      ? [af.selectionStart, af.selectionEnd] : null;
    const afId = af.id;
    requestAnimationFrame(() => {
      const novo = $(afId);
      if (novo && document.activeElement !== novo) {
        novo.focus({ preventScroll: true });
        if (sel && novo.setSelectionRange) {
          try { novo.setSelectionRange(sel[0], sel[1]); } catch (e) { /* input sem seleção */ }
        }
      }
    });
  }
  /* SEM PROJETO NA TELA, esta função não tem sobre o que decidir — e decidir
     assim mesmo estraga a tela inicial. Ela é chamada por caminhos ASSÍNCRONOS
     (a fonte local que terminou de carregar, o resize), e qualquer um deles
     chegando depois de `showHome()` acendia o "Aguardando o primeiro render"
     por baixo da dropzone, num momento em que não há projeto nenhum aberto. */
  if (homeOn || !Object.keys(S.state || {}).length) {
    ['layersPanel', 'stage', 'emptyState', 'startPanel'].forEach((id) => {
      if ($(id)) $(id).classList.add('hidden');
    });
    capAnims = [];
    wasShowing = false;
    return;
  }
  const show = setupApplies();
  $('layersPanel').classList.toggle('hidden', !show);
  const hasVideo = S.videoDuration > 0;
  $('stage').classList.toggle('hidden', !hasVideo);
  /* SEM VÍDEO SÃO TRÊS TELAS, e não uma. Antes de existir a de início, um
     projeto recém-criado e um projeto sendo processado mostravam a MESMA
     frase ("aguardando o primeiro render"), que não diz qual dos dois é.
     `#emptyState` fica com o que sobra: o projeto antigo, sem `awaitingStart`
     nem `startedAt`, que espera um render que a IA já foi mandada fazer. */
  const modoInicio = renderStart();
  $('emptyState').classList.toggle('hidden', hasVideo || !!modoInicio);

  /* O portão precisa APARECER, não só faltar. Escondido, o painel de camadas
     some sem explicação e o usuário conclui que a interface está incompleta —
     não que ele tem um passo a cumprir. A tarja diz as duas coisas que faltavam:
     que existe uma etapa seguinte, e o que a destranca. */
  const gate = $('gateNote');
  if (gate) {
    const trancado = hasVideo && onProxy();
    gate.classList.toggle('hidden', !trancado);
  }

  if (!show) {
    capAnims = []; // para de animar demos que não estão na tela
    if (wasShowing && hasVideo) requestAnimationFrame(() => { fitZoom(); renderAll(); });
    wasShowing = false;
    return;
  }
  wasShowing = true;

  // O rótulo do botão de envio pertence à BARRA DE AÇÃO (refreshActionBar), que
  // é quem sabe tudo o que mudou — estilo, cortes e marcações. Escrever aqui
  // também fazia a última das duas ganhar, e era a errada: esta só enxerga o
  // estilo, então o botão dizia "Visualizar" mesmo havendo cortes a refazer.

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
      const kind = o.mock ? 'frame' : o.ct ? 'cap ctbox' : o.hl ? 'cap hlbox' : 'cap';
      const prev = el('div', `opt-preview ${kind}`, card);
      // um `demo` sem construtor deixa o cartão parado em vez de derrubar a
      // aba inteira: a lista de estilos é dado, e dado erra
      if (o.demo && CAP_BUILDERS[o.demo]) capAnims.push(CAP_BUILDERS[o.demo](prev));
      else if (o.ct) buildCartelaDemo(prev, o.ct);
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
      const trava = elLocked(e);
      const on = !!S.style.elements[e.id] && !trava;
      const row = el('div', `chk${on ? ' on' : ''}${trava ? ' locked' : ''}`, eh);
      row.dataset.id = e.id;
      if (trava) row.title = trava.split('\n')[0];
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
  /* E A BARRA DE AÇÃO, que até aqui ninguém redesenhava depois de uma troca de
     estilo. O comentário lá em cima já dizia que o rótulo do envio pertence ao
     `refreshActionBar` "que é quem sabe tudo o que mudou" — só que nenhum
     caminho o chamava ao escolher uma opção. O defeito ficou escondido enquanto
     `styleState()` respondia 'unset' de saída: o texto não mudava porque não
     tinha como mudar. Com a comparação honesta, marcar uma opção e ver a barra
     insistir em "Estilo ainda não escolhido" seria o mesmo sintoma de antes. */
  refreshActionBar();
}

/* Monta a faixa de camadas e o corpo do inspetor. Reconstrói do zero a cada
 * render porque o estado que ele mostra (o que está escolhido) vive em S.style,
 * não no DOM — um diff incremental aqui só criaria uma segunda fonte de verdade.
 * O que sobrevive é `activeLayer`: qual camada está aberta é decisão do usuário. */
/* Devolve o `scrollTop` DEPOIS que o conteúdo novo mediu a altura. No mesmo
 * quadro o corpo ainda está vazio, `scrollHeight` é zero e o navegador prende
 * o valor em 0 — a atribuição parece funcionar e não faz nada. */
function restauraRolagem(el2, topo) {
  if (!topo) return;
  requestAnimationFrame(() => { el2.scrollTop = topo; });
}

function buildLayerRows() {
  const tabs = $('layerTabs');
  const body = $('layerBody');
  /* A ROLAGEM SOBREVIVE AO REBUILD.
     Escolher um cartão chama `renderSetup()`, que refaz este corpo inteiro — e
     um `innerHTML = ''` zera o `scrollTop` do contêiner. O efeito é a aba
     saltar para o topo a cada clique: quem estava escolhendo o nono cartão de
     legenda perdia o lugar e tinha de rolar de novo para ver o que acabou de
     escolher. Só apareceu quando a lista cresceu para onze — com quatro
     cartões nada rolava e o defeito era invisível.
     Guardar e devolver, em vez de rolar até o cartão: rolar até ele MOVE a
     tela mesmo quando o cartão já estava visível, que é o mesmo incômodo com
     outro nome. */
  const scrollAntes = body.scrollTop;
  tabs.innerHTML = '';
  body.innerHTML = '';
  restauraRolagem(body, scrollAntes);

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
    const g = el('div', 'dep-group', body);
    el('span', 'group-title', el('div', 'group-head', g)).textContent = 'Texto da headline';
    const ta = el('textarea', 'hl-text', g);
    ta.id = 'headlineText';
    ta.rows = 2;
    ta.placeholder = 'Ex.: 3 respostas dizem / se você está na carreira certa';
    ta.value = S.style.headlineText || '';
    /* A BARRA É O CONTROLE DE QUEBRA, e precisa estar escrito onde se escreve.
       Sem a dica ela é um recurso invisível: quem não sabe deixa o equilíbrio
       automático decidir e nunca descobre que podia mandar. */
    el('span', 'group-note', g).textContent =
      'use " / " para quebrar a linha onde você quiser — sem barra, o corte é '
      + 'equilibrado pela largura medida e o corpo se ajusta sozinho';
  }

  for (const gid of L.groups || []) {
    const g = el('div', 'dep-group', body);
    el('span', 'group-title', el('div', 'group-head', g)).textContent = GROUP_TITLE[gid] || gid;
    el('div', 'opt-grid', g).id = `opt-${gid}`;
  }
  /* A CAIXINHA DE PERGUNTAS pede o único dado do formato que não se mede: o
     texto. Aparece DEPOIS da grade de tipos de edição e só quando ela está
     escolhida — campos de um formato que não foi escolhido são ruído em toda
     abertura da aba. A resposta é opcional: nem todo vídeo mostra a resposta
     escrita; muitos só a falam. */
  if (L.caixaText && S.style.edit === 'caixinha') {
    const g = el('div', 'dep-group', body);
    el('span', 'group-title', el('div', 'group-head', g)).textContent = 'Caixinha de perguntas';
    /* OS TETOS VÊM DO `variants.json`, não de constantes aqui — a mesma régua
       que o compositor usa. 60 na faixa escura, 72 no corpo branco: é o que
       cabe legível no adesivo a 1080 de largura. O campo TRAVA na digitação e
       mostra o quanto falta, em vez de deixar escrever e cortar depois. */
    const lim = (LIVE.variants && LIVE.variants.caixinha) || {};
    const LIM_CH = lim.limiteChamada || 60;
    const LIM_PG = lim.limitePergunta || 72;
    const contador = (campo, teto) => {
      const marca = el('span', 'cx-count', g);
      const pinta = () => {
        const n = campo.value.length;
        marca.textContent = `${n}/${teto}`;
        marca.classList.toggle('no-limite', n >= teto);
      };
      campo.addEventListener('input', pinta);
      pinta();
      return marca;
    };
    const chamada = el('input', 'hl-text cx-input', g);
    chamada.id = 'caixaChamada';
    chamada.type = 'text';
    chamada.maxLength = LIM_CH;
    chamada.placeholder = 'chamada do adesivo — ex.: mande sua dúvida 🤎';
    chamada.value = (S.style.caixaChamada || '').slice(0, LIM_CH);
    contador(chamada, LIM_CH);
    const perg = el('textarea', 'hl-text', g);
    perg.id = 'caixaPergunta';
    perg.rows = 2;
    perg.maxLength = LIM_PG;
    perg.placeholder = 'a pergunta que veio da caixinha';
    perg.value = (S.style.caixaPergunta || '').slice(0, LIM_PG);
    contador(perg, LIM_PG);
    const resp = el('textarea', 'hl-text', g);
    resp.id = 'caixaResposta';
    resp.rows = 2;
    resp.placeholder = 'resposta curta que aparece escrita (opcional — deixe vazio se só falar)';
    resp.value = S.style.caixaResposta || '';
    el('span', 'group-note', g).textContent =
      'a caixinha entra no gancho, junto com você falando; se ela sai depois de '
      + 'lida ou fica até o fim é decidido no chat, com os tempos medidos do corte';
  }



  /* CORES E FONTES DEPOIS DO LAYOUT, e não antes.
     A ordem anterior pedia a cor de destaque antes de existir um layout que a
     pintasse — decidir a cor de uma coisa que ainda não foi escolhida. Agora a
     página desce: escolha o layout em cima, acerte cor e fonte embaixo. */
  /* O acabamento só abre DEPOIS do layout. Enquanto não abre, diz por quê —
     um espaço vazio leria como interface incompleta, não como um passo a
     cumprir. */
  if ((L.hlColors || L.fonts) && !S.style.headlinePicked) {
    el('div', 'layer-soon', body).textContent =
      'escolha um layout acima e as cores e fontes aparecem aqui';
  }

  if (L.hlColors && S.style.headlinePicked) {
    const g = el('div', 'dep-group acabamento', body);
    const h = el('div', 'group-head', g);
    el('span', 'group-title', h).textContent = 'Cores';
    el('span', 'group-note', h).id = 'accentNote';
    const row = el('div', 'color-row', g);
    const main = el('div', 'color-slot', row);
    el('span', 'color-lab', main).textContent = 'principal';
    el('div', 'swatches', main).id = 'optTextColor';
    const acc = el('div', 'color-slot', row);
    el('span', 'color-lab', acc).textContent = 'destaque';
    el('div', 'swatches', acc).id = 'optAccentHl';
  }

  if (L.fonts && S.style.headlinePicked) {
    /* DUAS famílias, e o par não é enfeite: o manuscrito desenha a primeira
       linha na de destaque e a segunda na principal. Nos outros layouts a de
       destaque fica sem uso — e a nota abaixo diz isso, em vez de deixar o
       usuário escolher uma fonte que não vai aparecer em lugar nenhum. */
    const g = el('div', 'dep-group acabamento', body);
    const h = el('div', 'group-head', g);
    el('span', 'group-title', h).textContent = 'Fontes';
    el('span', 'group-note', h).id = 'fontNote';
    const row = el('div', 'color-row', g);
    const a = el('div', 'color-slot', row);
    el('span', 'color-lab', a).textContent = 'principal';
    el('div', 'font-pick', a).id = 'optFontMain';
    const b = el('div', 'color-slot', row);
    el('span', 'color-lab', b).textContent = 'destaque';
    el('div', 'font-pick', b).id = 'optFontAccent';
    /* Guardar é EXPLÍCITO. Salvar sozinho a cada mexida transformaria uma
       experiência ("e se eu testar em verde?") na marca da pessoa. */
    const save = el('button', 'linkish brand-save', g);
    save.type = 'button';
    save.textContent = 'salvar como minha marca';
    save.title = 'guarda cor e fonte para os próximos projetos (~/.avelin/brand.json)';
    save.addEventListener('click', (ev) => { ev.stopPropagation(); saveBrand(save); });
  }

  if ((L.colors || L.capFonts) && !S.style.captionsPicked) {
    /* MESMO PORTÃO DA HEADLINE: primeiro o que a legenda É, depois com que cor
       e que letra. Antes de haver estilo escolhido, perguntar a cor de
       destaque é perguntar a cor de uma coisa que ainda não existe — e metade
       dos estilos de legenda não pinta destaque nenhum. */
    el('div', 'layer-soon', body).textContent =
      'escolha um estilo acima e as cores e fontes aparecem aqui';
  }

  if (L.colors && S.style.captionsPicked) {
    /* DUAS cores, e a distinção importa: a principal é o corpo da legenda (era
       branco cravado na folha), a de destaque é a que pinta a palavra realçada
       — e ela é a MESMA da headline, porque um vídeo com dois laranjas
       diferentes não lê como um vídeo, lê como um erro. */
    const g = el('div', 'dep-group acabamento', body);
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

  if (L.capFonts && S.style.captionsPicked) {
    /* UMA fonte. Estilos que alternam famílias (a serifada do empilhado) o
       fazem por identidade própria — expor isso como escolha dissolveria o
       estilo, e quem quer outra letra ali quer outro estilo. */
    const g = el('div', 'dep-group acabamento', body);
    const h = el('div', 'group-head', g);
    el('span', 'group-title', h).textContent = 'Fontes';
    el('span', 'group-note', h).id = 'capFontNote';
    const row = el('div', 'color-row', g);
    const a = el('div', 'color-slot', row);
    el('span', 'color-lab', a).textContent = 'família';
    el('div', 'font-pick', a).id = 'optCapFontMain';
    const save = el('button', 'linkish brand-save', g);
    save.type = 'button';
    save.textContent = 'salvar como minha marca';
    save.title = 'guarda cor e fonte para os próximos projetos (~/.avelin/brand.json)';
    save.addEventListener('click', (ev) => { ev.stopPropagation(); saveBrand(save); });
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
  // os DOIS controles de cor se gerem sozinhos (ao vivo, sem remontar).
  // Faltando o da principal aqui, um clique no campo hex dela contava como
  // escolha de estilo e remontava o cartao por baixo do cursor.
  if (e.target.closest('#optAccent') || e.target.closest('#optCapColor')
      || e.target.closest('#optAccentHl') || e.target.closest('#optTextColor')
      || e.target.closest('#optFontMain') || e.target.closest('#optFontAccent')
      || e.target.closest('#optCapFontMain')) return;

  // acordeão mestre: recolhe o painel inteiro e devolve a altura para a timeline
  if (e.target.closest('#layersToggle')) {
    const wrap = $('layersPanel');
    wrap.classList.toggle('collapsed');
    // abrir as camadas devolve a linha do tempo: é ela que convive com o painel
    if (!wrap.classList.contains('collapsed') && S.view !== 'tl') setView('tl');
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
    // trocar de CAMADA começa do topo: é conteúdo novo, e manter a rolagem
    // anterior abriria a camada nova no meio dela, sem contexto
    $('layerBody').scrollTop = 0;
    renderSetup();
    return;
  }

  const opt = e.target.closest('.opt:not(.ghost):not(.unavailable)');
  if (opt) {
    const key = {edits: 'edit', headlines: 'headline', captions: 'captions'}[opt.dataset.group];
    S.style[key] = opt.dataset.id;
    /* ESCOLHER O LAYOUT ABRE O ACABAMENTO. São dois momentos: em cima o que a
       headline É, embaixo com que cor e que letra. Antes de haver layout
       escolhido, perguntar a cor de destaque é perguntar a cor de uma coisa que
       ainda não existe — metade dos layouts nem pinta destaque. */
    const doCaption = opt.dataset.group === 'captions';
    const revelouCap = doCaption && !S.style.captionsPicked;
    if (doCaption) S.style.captionsPicked = true;
    const doHeadline = opt.dataset.group === 'headlines';
    /* Só na PRIMEIRA escolha o acabamento aparece — e só aí faz sentido descer
       até ele. Descer a cada troca de layout arrastaria a tela para longe dos
       cartões justamente enquanto a pessoa compara um com o outro, que é o
       mesmo incômodo que a rolagem preservada existe para eliminar. */
    const revelou = doHeadline && !S.style.headlinePicked;
    if (doHeadline) S.style.headlinePicked = true;
    /* ESCOLHER TEM DE MOSTRAR. O gancho vive nos primeiros segundos do corte;
       com o ponteiro em 00:40 o usuário clicaria num layout e o vídeo não
       mudaria nada — escolher sem ver a escolha é o mesmo que não ter
       escolhido. Só move quando está FORA da janela: dentro dela, mexer no
       ponteiro seria tirar a pessoa de onde ela estava olhando. */
    if (doHeadline && video.videoWidth
        && renderedToDraft(video.currentTime || 0) > GANCHO_SEC) {
      video.currentTime = draftToRendered(0.6);
    }
    LIVE.hookKey = null;   // o layout mudou: a prévia ao vivo remonta
    renderSetup();
    if (revelou || revelouCap) {
      // desce até o acabamento sem tirar da tela o estilo que acabou de ser
      // escolhido — `nearest` rola o mínimo, `start` jogaria os cartões para cima
      requestAnimationFrame(() => {
        const alvo = document.querySelector('.dep-group.acabamento');
        if (alvo) alvo.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      });
    }
    return;
  }
  const chk = e.target.closest('.chk:not(.layer-chip)');
  if (chk) {
    const cat = STYLE_CATALOG.elements.find((x) => x.id === chk.dataset.id);
    const trava = cat && elLocked(cat);
    if (trava) {
      // alerta em vez de marcação silenciosa: marcar e não cumprir é o que
      // esta trava existe para impedir
      alert(trava);
      S.style.elements[chk.dataset.id] = false;
      return;
    }
  }
  if (chk) {
    S.style.elements[chk.dataset.id] = !S.style.elements[chk.dataset.id];
    renderSetup();
  }
});

/* AS PRÉVIAS DESENHAM O TEXTO QUE VOCÊ ESTÁ ESCREVENDO.
 *
 * Antes elas mostravam uma frase de exemplo fixa, e o layout se escolhia sobre
 * um texto que não era o do vídeo — o que esconde justamente a decisão que
 * importa: quantas linhas a SUA frase faz, onde ela quebra e que corpo sobra.
 * Com o `/` isso deixou de ser detalhe: a mesma frase rende duas ou três linhas
 * conforme onde a barra cai, e cada layout reage diferente.
 *
 * Com atraso porque remontar onze prévias medidas a cada tecla trava a
 * digitação — a medição roda com a fonte real, uma vez por prévia. */
let hlTextTimer = null;
document.addEventListener('input', (e) => {
  if (!e.target || e.target.id !== 'headlineText') return;
  S.style.headlineText = e.target.value;
  clearTimeout(hlTextTimer);
  hlTextTimer = setTimeout(() => renderSetup(), 260);
});

async function sendStyle() {
  S.style.note = $('setupNote').value.trim();
  for (const [id, chave] of [['caixaPergunta', 'caixaPergunta'],
                             ['caixaResposta', 'caixaResposta'],
                             ['caixaChamada', 'caixaChamada']]) {
    if ($(id)) S.style[chave] = $(id).value;
  }
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
    textColor: S.style.textColor || '#FFFFFF',
    fontMain: S.style.fontMain || FONT_MAIN_DEF,
    fontAccent: S.style.fontAccent || FONT_ACCENT_DEF,
    capFont: S.style.capFont || capVariant().family || FONT_MAIN_DEF,
    // se a segunda família chega a aparecer neste layout — sem isto a skill
    // não sabe se a fonte de destaque é uma instrução ou um valor sem uso
    fontAccentUsed: !!(hlStyle(S.style.headline) || {}).fontRole,
    capDy: S.style.capDy || 0,   // deslocamento GLOBAL da legenda, px de ref 1080
    headlineText: (S.style.headlineText || '').trim(),
    // a caixinha de perguntas: o único dado do formato que não se mede
    caixaPergunta: (S.style.caixaPergunta || '').trim(),
    caixaResposta: (S.style.caixaResposta || '').trim(),
    caixaChamada: (S.style.caixaChamada || '').trim(),
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
  /* `applying` diz se o servidor REALMENTE disparou o trabalho, e o toast
     depende disso. Enquanto só se lia `ok`, um pedido que ficou parado no disco
     esperando uma sessão de IA saía anunciado como "✓ Enviado — a IA foi
     avisada": verdade pela metade, e a metade falsa é a que o usuário usa para
     decidir se pode fechar a aba. */
  const j = await res.json();
  S.lastApplying = !!j.applying;
  return !!j.ok;
}

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
/* ---------- efeitos sonoros ----------
 *
 * Pista de leitura, abaixo do áudio: os efeitos são derivados na composição,
 * então não há o que arrastar aqui — o que importa é PODER CONFERIR se o efeito
 * caiu onde devia, que antes só se sabia ouvindo o render pronto.
 *
 * Um chip por efeito, no instante REAL em que ele soa (o composer já desconta o
 * silêncio inicial do arquivo, então `start` é onde o som começa, não onde o
 * evento aconteceu). Efeitos que se sobrepõem vão para camadas diferentes na
 * composição; aqui eles dividem a mesma faixa e se distinguem pelo rótulo —
 * empilhar faixas por causa de 300ms de encavalamento custaria mais tela do que
 * informa.
 */
function renderSfx() {
  const trk = $('trkSfx'), lane = $('laneSfx');
  if (!trk || !lane) return;
  lane.innerHTML = '';
  const evs = S.sfx || [];
  trk.classList.toggle('hidden', !evs.length);
  const cnt = $('cntSfx');
  if (cnt) cnt.textContent = evs.length ? `${evs.length} efeito${evs.length === 1 ? '' : 's'}` : '—';
  if (!evs.length) return;

  for (const e of evs) {
    const chip = el('div', 'chip sfx', lane);
    chip.style.left = `${(+e.start || 0) * S.pps}px`;
    // Piso de largura: um clique de 96ms daria 3px e viraria um risco sem
    // rótulo. O chip mente um pouco na largura para não sumir — o tempo certo
    // fica no title.
    chip.style.width = `${Math.max((+e.dur || 0) * S.pps, 14)}px`;
    const nome = String(e.file || '').replace(/\.[^.]+$/, '');
    chip.textContent = nome;
    chip.title = `${nome}  ·  ${(+e.start).toFixed(3)}s  ·  ${(+e.dur).toFixed(3)}s`
      + `  ·  vol ${e.volume}`
      + (e.layer ? `  ·  camada ${e.layer + 1}` : '');
  }
}

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
    // As bordas do bloco de ÁUDIO editam o J-cut daquele trecho: a esquerda é
    // quanto da voz entra antes da imagem, a direita é quanto da cauda é
    // aparada. Não mexem no range — mexem em `jcut_lead_frames`/`tail_frames`,
    // que o render.py já lê por trecho.
    el('div', 'handle l', b).dataset.i = i;
    el('div', 'handle r', b).dataset.i = i;
    const g = jcutGeom(i);
    b.title = `${r.beat || r.source}\nvoz entra ${Math.round(g.lead * (S.fps || 30))}f antes da imagem`
      + `\ncauda aparada ${Math.round(g.tail * (S.fps || 30))}f`
      + '\n\narraste as bordas para ajustar';

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
      // RESERVADO tem de PARECER reservado. Um chip igual ao de um elemento
      // pronto afirma que a mídia existe, e o buraco volta a ficar invisível —
      // exatamente o problema que o reservado veio resolver.
      if (c.planned) {
        chip.classList.add('planned');
        chip.title = `${c.label} — RESERVADO: guarda o tempo, a mídia ainda não existe`;
      }
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
const LIVE = { variants: null, css: new Set(), key: null, hookKey: null };

/* A FOLHA DE CADA ESTILO, para a legenda AO VIVO sobre o vídeo.
   Faltar aqui não dá erro: `liveCss(undefined)` sai calado, o estilo cai no
   ramo genérico de legenda estática e — sem a folha correspondente carregada —
   o texto é desenhado CRU, branco e encostado no topo do quadro. Foi
   exatamente o sintoma dos estilos novos: "estáticas no topo". */
const CAP_CSS = {
  karaoke: 'karaoke.css', simples: 'static.css', serifada: 'static.css',
  classica: 'static.css', stacked: 'stacked.css', scatter: 'scatter.css',
  pop: 'pop.css', popLinha: 'pop.css', popBloco: 'pop.css',
  revelar: 'revelar.css', editorial: 'editorial.css', dinamico: 'dinamico.css',
};
for (const [id] of PAL) CAP_CSS[id] = 'palavra.css';

// os estilos medidos do CapCut, e o grupo de cada um
const POP_GRUPO = { pop: 'palavra', popLinha: 'linha', popBloco: 'bloco' };

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

/* A JANELA DO GANCHO. O compositor usa `hook.endSec` e o padrão dele é 4s —
   fora dessa janela o gancho não existe no vídeo, e a prévia diz isso
   apagando-o em vez de escondê-lo. */
const GANCHO_SEC = 4.0;

/* O GANCHO AO VIVO sobre o vídeo (pedido do usuário, 2026-08-19): clicar num
   layout tem de MOSTRAR o layout no vídeo, não só no cartão. Caixa própria,
   irmã da legenda, porque o overlay da legenda é reconstruído a cada troca de
   deixa — a headline não pode nascer e morrer sessenta vezes por segundo junto
   com ela. */
function renderLiveHook() {
  const ov = $('liveOverlay');
  const frame = video.parentElement;
  if (!ov || !frame) return;
  const id = (S.style && S.style.headline) || '';
  const on = setupApplies() && video.videoWidth > 0 && !S.showFinal && !!id;
  let box = document.getElementById('liveHook');
  if (!on) {
    if (box) box.remove();
    LIVE.hookKey = null;
    return;
  }
  syncOverlay();
  if (!box) {
    box = document.createElement('div');
    box.id = 'liveHook';
    box.style.position = 'absolute';
    box.style.overflow = 'hidden';
    box.style.pointerEvents = 'none';
    frame.appendChild(box);
  }
  // a MESMA caixa da legenda: o retângulo do vídeo, não o da moldura
  for (const k of ['left', 'top', 'width', 'height']) box.style[k] = ov.style[k];
  const w = box.clientWidth;
  if (!w) return;

  const h = hlStyle(id);
  const texto = (S.style.headlineText || '').trim() || HEADLINE_TEXT;
  const dentro = renderedToDraft(video.currentTime || 0) <= GANCHO_SEC;
  const key = [id, texto, Math.round(w), dentro, S.style.accent, S.style.textColor,
               S.style.fontMain, S.style.fontAccent].join('|');
  if (key === LIVE.hookKey) return;
  LIVE.hookKey = key;

  box.innerHTML = '';
  const host = el('div', `live-hook${dentro ? '' : ' fora'}`, box);
  if (h && h.motor === 'cartela') {
    buildCartelaDemo(host, id);
  } else {
    buildHeadline(host, id, texto, {
      width: w, top: (h || {}).top || 0,
      main: S.style.textColor, accent: S.style.accent,
      fontMain: S.style.fontMain, fontAccent: S.style.fontAccent,
    });
  }
}

function renderLive() {
  renderLiveHook();
  const ov = $('liveOverlay');
  if (!ov) return;
  /* Com o render final na tela a legenda JÁ ESTÁ QUEIMADA nele — desenhar por
     cima produz duas legendas sobrepostas, uma do render e outra da prévia. A
     prévia existe para mostrar o que AINDA não foi renderizado; quando o render
     existe e está sendo exibido, ela não tem função. */
  const on = setupApplies() && video.videoWidth > 0 && !S.showFinal;
  ov.classList.toggle('hidden', !on);
  if (!on) { LIVE.key = null; return; }

  const w = syncOverlay();
  if (!w) return;
  const id = (S.style && S.style.captions) || 'karaoke';
  const v = (LIVE.variants && LIVE.variants.styles && LIVE.variants.styles[id]) || {};
  liveCss(CAP_CSS[id]);

  LIVE.stackedLike = (id === 'stacked');
  /* A família escolhida desce por variável, e o padrão é a do próprio estilo.
     Aplicada uma vez aqui, no contêiner, em vez de repetida em cada ramo — os
     ramos já divergem na MARCAÇÃO, e divergir também na fonte é onde um deles
     acabaria esquecido. */
  const capFam = S.style.capFont ? cssFamily(S.style.capFont) : (v.cssFamily || null);
  if (S.style.capFont) ensureFonts([S.style.capFont]);
  const vestir = (box) => {
    if (capFam) {
      box.style.setProperty('--cap-family', capFam);
      box.style.setProperty('--stk-family', capFam);
      box.style.setProperty('--scat-family', capFam);
    }
    return box;
  };
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
    const box = vestir(el('div', 'ave-stacked', ov));
    box.style.setProperty('--stk-scale', sc);
    applyCapDy(box, id, v);
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
    const box = vestir(el('div', 'ave-scatter', ov));
    box.style.setProperty('--scat-scale', sc);
    applyCapDy(box, id, v);
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
  } else if (POP_GRUPO[id]) {
    /* Estouro. Ao vivo a legenda é mostrada ASSENTADA (escala 1), não a meio
       estouro: esta prévia responde "como fica", e o quadro do meio de uma
       animação de 400ms não é como fica. O movimento se vê nos cartões, que
       rodam em laço. */
    const box = vestir(el('div', `ave-pop grupo-${POP_GRUPO[id]}`, ov));
    box.style.setProperty('--cap-scale', sc);
    applyCapDy(box, id, v);
    box.style.setProperty('--cap-color', S.style.capColor || '#fff');
    box.style.setProperty('--cap-accent', S.style.accent || ACCENT_DEFAULT);
    if (v.size) box.style.setProperty('--cap-size', v.size);
    const line = el('div', 'ave-cap-line', box);
    for (const word of words) el('span', '', line).textContent = word.toUpperCase();
  } else if (id === 'revelar') {
    const box = vestir(el('div', 'ave-rev', ov));
    box.style.setProperty('--cap-scale', sc);
    applyCapDy(box, id, v);
    box.style.setProperty('--cap-color', S.style.capColor || '#fff');
    box.style.setProperty('--cap-accent', S.style.accent || ACCENT_DEFAULT);
    if (v.size) box.style.setProperty('--cap-size', v.size);
    const line = el('div', 'ave-cap-line', box);
    for (const word of words) {
      const sp = el('span', '', line);
      sp.textContent = word.toUpperCase();
      /* A folha nasce com `--rev-w: 0` porque quem revela é o render. Ao vivo,
         sem forçar 1, a legenda inteira fica INVISÍVEL — e um estilo que some
         na prévia lê como quebrado, não como "ainda não animou". */
      sp.style.setProperty('--rev-w', 1);
    }
  } else if (PAL_IDS.has(id)) {
    /* O motor `palavra` ao vivo. A deixa é mostrada com a ÚLTIMA palavra ativa
       — a frase inteira já dita, o realce onde ele para. É a mesma escolha do
       estouro: esta prévia responde "como fica", e o quadro do meio de uma
       animação de 190ms não é como fica. O movimento se vê nos cartões, que
       rodam em laço. */
    const P = window.AVE_PALAVRA;
    const box = el('div', `ave-pal pal-${id}`, ov);
    if (P && v.pal) {
      vestirPal(box, id, v, sc);
      box.style.position = 'absolute';
      box.style.inset = '0';
      applyCapDy(box, id, v);
      let t = 0;
      const linha = words.map((w) => {
        const item = {texto: w, at: t, dur: 0.3};
        t += 0.35;
        return item;
      });
      const linhas = (v.lines || 1) > 1 && linha.length > 2
        ? [linha.slice(0, Math.ceil(linha.length / 2)), linha.slice(Math.ceil(linha.length / 2))]
        : [linha];
      const cue = P.montar(box, linhas, v.pal, id);
      // medir depois de estar no documento: a tarja é posicionada contra a
      // caixa da deixa, e uma caixa fora da árvore mede zero
      requestAnimationFrame(() => P.pintar(cue, v.pal, v.motion || {}, t, sc, P.paleta(box)));
    }
  } else if (id === 'karaoke') {
    const box = vestir(el('div', 'ave-cap', ov));
    box.style.setProperty('--cap-scale', sc);
    applyCapDy(box, id, v);
    box.style.setProperty('--cap-color', S.style.capColor || '#fff');
    if (v.size) box.style.setProperty('--cap-size', v.size);
    const line = el('div', 'ave-cap-line', box);
    for (const word of words) el('span', '', line).textContent = word;
  } else {
    const box = vestir(el('div', 'ave-cap-static', ov));
    box.style.setProperty('--cap-scale', sc);
    applyCapDy(box, id, v);
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

/* A onda é desenhada POR TAKE, não como uma fita contínua.
 *
 * Antes era um traçado só cobrindo a linha inteira. O conteúdo já estava certo
 * — o mapeamento rascunho→render respeita as aparas —, mas visualmente o áudio
 * não tinha junção nenhuma: aparar um take encurtava a fita pela ponta direita
 * do TODO, em vez de encurtar aquele bloco. A imagem contradizia a pista de
 * vídeo logo acima, onde os mesmos cortes aparecem como blocos separados.
 *
 * As posições vêm do mesmo `draftLayout()` que desenha os blocos de vídeo, pelo
 * par de áudio (`aout`/`adur`) — que não é igual ao de imagem: sob J-cut o som
 * de um take começa antes da imagem dele. Usar o par de imagem aqui alinharia a
 * onda com o quadro errado. */
function drawWave() {
  if (!S.wave) return;
  const { ctx, w, h, x0 } = canvasSetup(waveCv, laneAudio);
  const mid = h / 2;
  const pps = S.wave.peaksPerSec;

  const tri = trimIdx();
  const itens = draftLayout(tri).filter((it) => !it.removed && it.adur > 0);
  const blocos = itens.map((it) => [it.aout * S.pps, (it.aout + it.adur) * S.pps]);

  ctx.fillStyle = tokA('--orange-soft-rgb', 0.07);
  for (const [a, b] of blocos) ctx.fillRect(a - x0, 0, Math.max(1, b - a), h);

  /* A BORDA precisa ser desenhada, não deduzida do vão. Sob J-cut o som de um
     take COMEÇA antes de o anterior acabar — os blocos se sobrepõem e não sobra
     espaço vazio entre eles. Sem um traço explícito, a pista volta a parecer uma
     fita só, que é a queixa que este bloco existe para resolver. */
  ctx.fillStyle = tokA('--orange-soft-rgb', 0.5);
  for (let i = 1; i < blocos.length; i++) ctx.fillRect(blocos[i][0] - x0, 0, 1, h);

  ctx.strokeStyle = tokA('--orange-soft-rgb', 0.12);
  ctx.beginPath();
  for (const [a, b] of blocos) { ctx.moveTo(a - x0, mid); ctx.lineTo(b - x0, mid); }
  ctx.stroke();

  ctx.fillStyle = tokA('--orange-soft-rgb', 0.75);
  for (const [a, b] of blocos) {
    const px0 = Math.max(0, Math.floor(a - x0));
    const px1 = Math.min(w, Math.ceil(b - x0));
    for (let px = px0; px < px1; px++) {
      const tRend = draftToRendered((x0 + px) / S.pps);
      const idx = Math.floor(tRend * pps);
      if (idx < 0 || idx >= S.wave.max.length) continue;
      const hi = (S.wave.max[idx] / 100) * (mid - 2);
      const lo = (S.wave.min[idx] / 100) * (mid - 2);
      ctx.fillRect(px, mid - hi, 1, Math.max(1, hi - lo));
    }
  }

  /* Durante o arraste, o take aparado mantém o tamanho ORIGINAL e o pedaço que
     sai fica apagado — igual à pista de vídeo. É isso que faz aparar o começo
     ler como encurtar pela ESQUERDA; sem o congelamento, o bloco reflui e a
     borda que você não está arrastando parece se mexer sozinha. */
  if (tri != null) {
    const it = itens.find((x) => x.i === tri) || itens[tri];
    const r = S.draft[tri];
    if (it && r && r.orig) {
      const head = Math.max(0, r.start - r.orig.start);
      const tail = Math.max(0, r.orig.end - r.end);
      const a0 = it.aout * S.pps;
      const b0 = (it.aout + it.adur) * S.pps;
      ctx.fillStyle = 'rgba(8, 23, 38, 0.66)';
      if (head > 0) ctx.fillRect(a0 - x0, 0, head * S.pps, h);
      if (tail > 0) ctx.fillRect(b0 - tail * S.pps - x0, 0, tail * S.pps, h);
    }
  }
}

// Vertical sources get the split layout (player right, editor left) — stacked,
// a 9:16 clip is tiny above a full-width timeline. Driven off the decoded frame
// size, so it works for preview.mp4 and the Phase-2 render alike.
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
  // os cartões de estilo seguem o QUADRO: mesma fonte, mesmo instante
  aplicarQuadro();
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
  markNowWord();
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
    // no INÍCIO do arrasto, uma vez. Empilhar a cada `pointermove` encheria a
    // pilha de estados intermediários e ⌘Z andaria um pixel por vez.
    pushUndo('redimensionar trecho');
    drag = { type: 'trim', i, side: handle.classList.contains('l') ? 'l' : 'r', x0: e.clientX, r: { ...S.draft[i] } };
    try { panel.setPointerCapture(e.pointerId); } catch (err) { /* synthetic/touch */ }
    e.preventDefault();
    return;
  }
  const ablock = e.target.closest('.ablock');
  if (handle && ablock) {
    const i = +handle.dataset.i;
    const g = jcutGeom(i);
    const fps = S.fps || 30;
    drag = { type: 'jcut', i, side: handle.classList.contains('l') ? 'l' : 'r', x0: e.clientX,
             lead0: Math.round(g.lead * fps), tail0: Math.round(g.tail * fps) };
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

  if (drag.type === 'jcut') {
    const r = S.draft[drag.i];
    const fps = S.fps || 30;
    const df = Math.round(dt * fps);
    if (drag.side === 'l') {
      // puxar a borda ESQUERDA para a esquerda aumenta o lead
      r.leadF = Math.max(0, Math.min(JCUT_MAX_F, drag.lead0 - df));
    } else {
      // puxar a borda DIREITA para a esquerda apara mais cauda
      r.tailF = Math.max(0, Math.min(JCUT_MAX_F, drag.tail0 - df));
    }
    renderClips();
    renderJcutAudio();
    drawWave();
    refreshHeader();
    const g = jcutGeom(drag.i);
    showTooltip(e, drag.side === 'l'
      ? `voz entra <b>${Math.round(g.lead * fps)}f</b> antes da imagem`
      : `cauda aparada <b>${Math.round(g.tail * fps)}f</b>`);
    return;
  }

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
  pushUndo('restaurar bordas');
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
  } else if ((e.key === 'Delete' || e.key === 'Backspace') && S.view === 'tx' && S.selWords.size) {
    // rasura = PEDIDO. Alternar deixa desfazer com a mesma tecla.
    const todas = [...S.selWords].every((i) => S.cutWords.has(i));
    for (const i of S.selWords) todas ? S.cutWords.delete(i) : S.cutWords.add(i);
    S.selWords.clear();
    renderTx();
    refreshHeader();
    e.preventDefault();
  } else if ((e.key === 'Delete' || e.key === 'Backspace') && S.selected >= 0) {
    const r = S.draft[S.selected];
    pushUndo(r.removed ? 'restaurar trecho' : 'apagar trecho');
    r.removed = !r.removed;
    renderAll(); refreshHeader();
  } else if ((e.key === 'z' || e.key === 'Z') && (e.metaKey || e.ctrlKey) && !e.shiftKey) {
    e.preventDefault();
    undoLast();
  }
});

/* APROVAR O CORTE. Arquivo próprio (`preview_approval.json`), não o de
   marcações: aprovar não pode apagar correções que ainda não foram lidas.
   `S.approved` esconde a barra no ato — a confirmação de verdade chega quando o
   agente troca o `video` para o corte final, e esperar por isso deixaria o
   usuário clicando de novo achando que não pegou. */
$('btnApprove').addEventListener('click', async () => {
  const btn = $('btnApprove');
  btn.disabled = true;
  try {
    const r = await fetch('/api/save', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type: 'approve-cut',
                             note: ($('approveNote').value || '').trim(),
                             video: S.state.video || null }),
    });
    if (!(await r.json()).ok) throw new Error('save');
    S.approved = true;
    refreshActionBar();
    toast('Corte aprovado — renderizando o final e liberando a Fase 2', 4000);
  } catch (e) {
    btn.disabled = false;
    toast('não consegui salvar a aprovação — tente de novo', 3000);
  }
});

$('btnUndo').innerHTML = ICON.undo;
$('btnUndo').addEventListener('click', undoLast);

/* MODO da linha do tempo: compacta (vídeo + waveform geral) ⇄ expandida (com
   marcações, legendas, J-cut, efeitos). Compacta é o PADRÃO — a leitura de
   clip único, estilo NLE — e a escolha é lembrada, como a do J-cut. Substitui
   o recolher da barra, que escondia o painel inteiro: o que se alterna é a
   densidade, não a existência da timeline. */
$('tlMode').innerHTML = '<span class="caret">⌄</span><span>Camadas</span>';
function setTlMode(compact) {
  $('timeline').classList.toggle('compact', compact);
  // compacta, a timeline devolve a altura que não usa: o painel encolhe ao
  // conteúdo e o de camadas do render pode crescer além do teto usual
  $('timelinePanel').classList.toggle('compacta', compact);
  $('layersPanel').classList.toggle('tl-compacta', compact);
  const b = $('tlMode');
  b.setAttribute('aria-expanded', String(!compact));
  b.title = compact ? 'Expandir as camadas (marcações, legendas, J-cut, efeitos)'
                    : 'Recolher para vídeo + áudio';
  try { localStorage.setItem('avelin.tlMode', compact ? 'compact' : 'full'); } catch (e) { /* privado */ }
  // a régua e a waveform desenham em canvas dimensionado pelo layout: trocar a
  // densidade muda a altura da pista de áudio, então remede e redesenha
  requestAnimationFrame(() => { fitZoom(); renderAll(); });
}
$('tlMode').addEventListener('click', () =>
  setTlMode(!$('timeline').classList.contains('compact')));
try {
  setTlMode(localStorage.getItem('avelin.tlMode') !== 'full');
} catch (e) { setTlMode(true); }

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


// ---------- save / discard ----------
async function sendTimeline() {
  const payload = { type: 'timeline-edits' };
  /* O PEDIDO EM TEXTO vai por aqui, e não pelo canal de estilo.
   *
   * Este canal é o "leia isto e decida"; o de estilo é "REFAÇA a Fase 2
   * assim". Um pedido escrito ("deixa a legenda mais alta") não é uma escolha
   * de estilo e não deve disparar render sozinho — quem decide é quem lê. */
  const pedido = ($('setupNote') && $('setupNote').value.trim()) || '';
  if (pedido) payload.request = pedido;
  if (edlDirty()) {
    payload.edl = {
      ranges: S.draft.filter((r) => !r.removed).map((r) => ({
        source: r.source, start: +r.start.toFixed(3), end: +r.end.toFixed(3), beat: r.beat,
        // só viajam quando o usuário DISCORDOU do valor calculado; ausentes, o
        // render.py volta a decidir sozinho (lead 5f, cauda medida no silêncio)
        ...(r.leadF != null ? { jcut_lead_frames: r.leadF } : {}),
        ...(r.tailF != null ? { jcut_tail_frames: r.tailF } : {}),
      })),
      removed: S.draft.filter((r) => r.removed).map((r) => ({ source: r.source, beat: r.beat, start: r.orig.start, end: r.orig.end })),
      changes: S.draft.filter((r) => !r.removed && (r.start !== r.orig.start || r.end !== r.orig.end)).map((r) => ({
        source: r.source, beat: r.beat,
        from: { start: r.orig.start, end: r.orig.end },
        to: { start: +r.start.toFixed(3), end: +r.end.toFixed(3) },
      })),
    };
  }
  // guarda ESPECÍFICA, não `wordsDirty()`: ele agora também cobre respiros, e
  // marcar só respiro emitiria um `cutWords: []` — que o outro lado leria como
  // "nenhuma palavra a cortar" quando o certo é "não pediram palavra nenhuma".
  if (S.cutWords.size) {
    /* PEDIDO, não corte. Vai com o texto e os tempos DA FONTE para a IA achar a
       borda limpa — mais a folga medida, que é o que diz onde ela vai ter de
       improvisar. Deliberadamente não mando um EDL já recortado: os tempos de
       palavra do Whisper não são bordas de corte, e um recorte feito aqui
       chegaria com a emenda no meio da sílaba. */
    payload.cutWords = [...S.cutWords].sort((a, b) => a - b).map((i) => {
      const w = S.words[i];
      return { text: w.text, source: w.source, range: w.range,
               srcStart: w.srcStart, srcEnd: w.srcEnd, outStart: w.outStart,
               gapBefore: w.gapBefore, gapAfter: w.gapAfter };
    });
  }
  if (breathsDirty()) {
    /* Também PEDIDO, e com uma diferença que precisa chegar do lado de lá: o
       respiro não é apagado, é ENCURTADO. `keep` é o piso e `trim` é quanto sai.
       Mando os dois em vez de só o intervalo, porque um intervalo cru seria lido
       como "remova isto" e a fala voltaria a soar metralhada. */
    payload.cutBreaths = [...S.cutBreaths].sort((a, b) => a - b).map((i) => {
      const w = S.words[i], nx = S.words[i + 1], br = breathAt(i);
      return { afterWord: w.text, beforeWord: nx ? nx.text : null,
               source: w.source, range: w.range,
               srcFrom: w.srcEnd, srcTo: nx ? nx.srcStart : null,
               outStart: w.outStart,
               dur: br.dur, keep: br.keep, trim: br.trim };
    });
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
    // rendered-timeline equivalent so the skill can find the spot in preview.mp4
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
  const j = await res.json();
  S.lastApplying = !!j.applying;   // ver o comentário em sendStyle
  if (!j.ok) return false;
  S.savedPending = true;
  S.notes = [];
  S.pendingIn = null;
  S.draft.forEach((r) => { r.orig = { start: r.start, end: r.end }; if (r.removed) r.hardRemoved = true; });
  S.draft = S.draft.filter((r) => !r.removed);
  S.insertsDraft.forEach((c) => { c.orig = { start: c.start, end: c.end }; });
  S.cutWords.clear();
  S.cutBreaths.clear();
  // A pilha morre no salvamento, e tem de morrer: o pedido já saiu daqui, e os
  // takes marcados como removidos acabaram de ser FILTRADOS de S.draft. Um
  // instantâneo anterior traria de volta trechos que já foram enviados como
  // apagados — a tela passaria a discordar do que o outro lado recebeu.
  S.undo.length = 0;
  refreshUndo();
  renderTx();
  return true;
}

/* UM clique, os dois pacotes. Eles continuam indo para arquivos separados —
   escolha de estilo e correção de linha do tempo são consumidas em momentos
   diferentes, e um arquivo só faria uma sobrescrever a outra. O que se unifica
   é o GESTO, não o formato. */
$('setupGo').addEventListener('click', async () => {
  /* MODO APROVAR (Fase 1, nada alterado). Mesmo contrato da barra antiga:
     `preview_approval.json` próprio, para a aprovação nunca apagar marcação
     não lida. A nota sai do campo único. */
  if ($('setupGo').dataset.mode === 'approve') {
    const btn = $('setupGo');
    btn.disabled = true;
    try {
      const r = await fetch('/api/save', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: 'approve-cut',
                               note: ($('setupNote').value || '').trim(),
                               video: S.state.video || null }),
      });
      if (!(await r.json()).ok) throw new Error('save');
      S.approved = true;
      $('setupNote').value = '';
      refreshActionBar();
      toast('Corte aprovado — renderizando o final e liberando a Fase 2', 4000);
    } catch (e) {
      btn.disabled = false;
      toast('não consegui salvar a aprovação — tente de novo', 3000);
    }
    return;
  }
  /* DUAS PERGUNTAS ANTES DE GASTAR. O clique dispara trabalho de IA que custa
     tokens e minutos, e até aqui ele era indistinguível de qualquer outro botão
     da tela. */
  const caroAgora = styleDirty() || edlDirty() || insertsDirty();

  /* O AVISO DA HEADLINE SAIU DAQUI, e essa é a correção de verdade.
     
     Ele era um `confirm()` disparado DEPOIS do clique, em que OK — a resposta
     reflexa — abortava o envio. A primeira tentativa de conserto foi reescrever
     a pergunta para dizer "OK = escrever agora (nada é enviado)". O editor do
     projeto leu essa versão já corrigida e caiu na mesma armadilha, o que
     resolve a dúvida: o problema nunca foi a redação, é pedir uma decisão
     inesperada no meio de outra. Reflexo não se conserta com texto melhor.
     
     O aviso agora é PERMANENTE na barra de ação (`refreshActionBar`), visível
     ENQUANTO a pessoa escolhe e não depois que ela decidiu. O clique voltou a
     ter um único diálogo: o de custo, que é o que ela foi buscar. E com a opção
     "Nenhum" na grade, quem não quer headline nem vê o aviso. */
  // o aviso de custo é sobre RENDER. Um pedido escrito não renderiza nada
  // sozinho — cobrar a confirmação de minutos ali seria mentir sobre o preço.
  if (caroAgora && !confirm(
      'O pedido vai para a IA e consome tokens, além de alguns minutos de render.\n\n'
      + 'Tem certeza das alterações?')) return;

  const pedidoTxt = ($('setupNote') && $('setupNote').value.trim()) || '';
  const quer = {
    style: styleDirty(),
    // `pedidoTxt` entra aqui: sem ele, um pedido só de texto saía com os dois
    // canais falsos, NADA era gravado, e o toast ainda dizia "✓ Enviado".
    tl: edlDirty() || insertsDirty() || S.notes.length > 0 || wordsDirty() || !!pedidoTxt,
  };
  const caro = quer.style || edlDirty() || insertsDirty();
  let ok = true;
  if (quer.style) ok = (await sendStyle()) && ok;
  if (quer.tl) ok = (await sendTimeline()) && ok;
  if (ok && caro) startProcessing();
  renderAll();
  renderSetup();
  refreshHeader();
  if (ok && $('setupNote')) {
    // esvaziar é parte do envio: deixar o texto no campo mantém o botão
    // habilitado com um pedido que já saiu, e reenviar duplica o trabalho
    $('setupNote').value = '';
    S.style.note = '';
  }
  refreshActionBar();
  toast(!ok ? 'Erro ao enviar — o servidor está de pé?'
    : S.lastApplying ? '✓ Enviado — trabalhando, acompanhe na barra de progresso'
    : 'Pedido salvo — aguardando uma sessão da IA executar', 5000);
});

/* ESTADO DE PROCESSAMENTO. O clique dispara trabalho que acontece FORA do
   navegador e leva minutos — sem sinal na tela, a interface fica idêntica a
   antes do clique e o usuário clica de novo. Sai quando um render novo chega:
   o mtime do vídeo mudar é o único sinal que não depende de ninguém avisar. */
function startProcessing() {
  S.processing = true;
  S.procFrom = (S.mtimes && (S.mtimes.finalVideo || S.mtimes.video)) || 0;
  refreshHeader();
}
function checkProcessing() {
  if (!S.processing) return;
  const now = (S.mtimes && (S.mtimes.finalVideo || S.mtimes.video)) || 0;
  if (now !== S.procFrom) { S.processing = false; S.savedPending = false; refreshHeader(); }
  else $('procWhat').textContent = S.state.message || 'trabalhando…';
}

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
  localStorage.setItem('avelin.jcutOpen', S.jcutOpen ? '1' : '0');
  renderJcutAudio();
  updateScrollRange();
  positionNeedle();
});

// a marca ANTES do primeiro poll: ela entra na montagem do estilo, e chegando
// depois o painel abriria no laranja de fábrica e trocaria de cor sozinho
Promise.all([loadBrand(), loadEstilo(), loadLocalFonts()]).then(poll);
rafLoop();
// the headline fit is MEASURED, so it is wrong until Poppins is actually
// loaded — rebuild once the fonts land
if (document.fonts && document.fonts.ready) {
  document.fonts.ready.then(() => { if (S.style) renderSetup(); });
fetch('/styles/variants.json')
  .then((r) => r.json())
  .then((v) => {
    LIVE.variants = v;
    LIVE.key = null;
    renderLive();
    // os cartões do motor `palavra` são desenhados a partir DESTES números
    // (corpo, teto de palavras, papéis de estado). Montados antes do fetch,
    // saíam vazios e ficavam assim — a aba mostrava dezenove retângulos pretos.
    if (S.style) renderSetup();
  })
  .catch(() => { /* sem os números a prévia cai no CSS puro, que já é honesto */ });
}


/* ---------- TRANSCRIÇÃO ----------
 *
 * Riscar palavra é INDICAR onde cortar, não executar o corte. Quem resolve a
 * borda é a IA, com o áudio na mão — os tempos do Whisper adiantam o início e
 * esticam o fim, e cortar neles come a palavra vizinha. Foi essa distinção que
 * salvou o desenho: como ferramenta de corte, o dado dizia que só 3 das 241
 * palavras deste vídeo eram removíveis sem emenda, o que a tornaria inútil.
 * Como indicação, as 241 valem — a emenda é problema de quem executa.
 *
 * A marca de risco discreta (`.tight`) diz onde a emenda vai ser apertada. É
 * informação para quem edita, não impedimento. */
async function loadWords() {
  try {
    const d = await (await fetch(`/gen/words.json?v=${Date.now()}`)).json();
    S.words = d.words || [];
  } catch (e) { S.words = []; }
  renderTx();
}

/* Camadas e transcrição DISPUTAM a mesma altura: uma quer o painel de cima
 * aberto, a outra quer a área de baixo alta. Deixar as duas abertas espreme as
 * duas. Então elas se alternam — abrir uma recolhe a outra, e voltar a abrir as
 * camadas devolve a linha do tempo embaixo. */
function setView(v) {
  S.view = v;
  if (v === 'tx') $('layersPanel').classList.add('collapsed');
  document.querySelectorAll('.vseg').forEach((b) => b.classList.toggle('on', b.dataset.view === v));
  $('timelinePanel').classList.toggle('hidden', v !== 'tl');
  $('txPanel').classList.toggle('hidden', v !== 'tx');
  if (v === 'tx' && !S.words.length) loadWords();
  if (v === 'tl') requestAnimationFrame(() => { fitZoom(); renderAll(); });
  renderTx();
}

/* AGRUPAMENTO EM DEIXAS — o texto aparece como a legenda vai aparecer.
 *
 * Duas regras, e a ordem importa: quebra no SILÊNCIO medido (é o que o
 * compositor usa, e é onde uma deixa naturalmente termina) e, na falta dele,
 * no teto de palavras do estilo escolhido. Agrupar só por contagem produziria
 * linhas que cortam no meio de uma oração; agrupar só por silêncio produziria
 * linhas gigantes em quem fala corrido — e este fala corrido.
 *
 * É uma PREVISÃO enquanto a Fase 2 não rodou: sem `captions.json` não existem
 * deixas de verdade, existe a regra que vai gerá-las. */
function txLines() {
  const id = (S.style && S.style.captions) || 'karaoke';
  const v = (LIVE.variants && LIVE.variants.styles && LIVE.variants.styles[id]) || {};
  const max = v.maxWords || 3;
  const linhas = [];
  let cur = null;
  S.words.forEach((w, i) => {
    if (!cur || w.range !== cur.range || cur.idx.length >= max) {
      cur = { range: w.range, start: w.outStart, idx: [] };
      linhas.push(cur);
    }
    cur.idx.push(i);
    if (w.gapAfter > 0.25) cur = null;   // silêncio real fecha a deixa
  });
  return linhas;
}

/* RESPIROS — o silêncio ENTRE duas palavras, oferecido como coisa removível.
 *
 * Três decisões que definem quais aparecem, e todas têm motivo:
 *
 * 1. **Só dentro do mesmo trecho.** O vão entre o fim de um take e o começo do
 *    próximo NÃO é respiro, é a emenda — quem cuida dela é o J-cut, com o
 *    silêncio medido. Oferecer a emenda aqui daria dois donos ao mesmo silêncio.
 * 2. **`gapAfter` é a medida, e 999 é sentinela** (`cut_words.py` devolve isso
 *    quando não há região seguinte, ou seja, fim do material). Tratar 999 como
 *    duração ofereceria um respiro de 16 minutos no último trecho.
 * 3. **Nunca some por inteiro.** Tirar todo o silêncio deixa a fala
 *    metralhada — o ouvido lê como locução de robô, não como edição ágil. O
 *    corte reduz ao PISO; o que se remove é só o excedente. É por isso que o
 *    chip mostra "0,8s → 0,15s" em vez de "remover". */
const BREATH_MIN = 0.20;   // abaixo disto é articulação, não respiro
const BREATH_KEEP = 0.15;  // o que SEMPRE fica
const BREATH_WORTH = 0.08; // excedente menor que isto não paga um corte

function breathAt(i) {
  const w = S.words[i], nx = S.words[i + 1];
  if (!w || !nx || nx.range !== w.range) return null;
  const dur = w.gapAfter;
  if (!(dur >= BREATH_MIN) || dur > 900) return null;
  const trim = dur - BREATH_KEEP;
  if (trim < BREATH_WORTH) return null;
  return { dur: +dur.toFixed(3), keep: BREATH_KEEP, trim: +trim.toFixed(3) };
}

const breathsDirty = () => S.cutBreaths.size > 0;

function renderTx() {
  const host = $('txBody');
  if (!host || S.view !== 'tx') return;
  host.innerHTML = '';
  if (!S.words.length) {
    host.innerHTML = '<div class="tx-hint">montando o transcrito do corte… '
      + '(mede o silêncio de cada fronteira na fonte, leva alguns segundos)</div>';
    return;
  }
  let lastRange = -1;
  for (const ln of txLines()) {
    if (ln.range !== lastRange) {
      lastRange = ln.range;
      const r = (S.draft && S.draft[ln.range]) || {};
      el('div', 'tw-src', host).textContent = `${r.beat || 'trecho'} · ${S.words[ln.idx[0]].source}`;
    }
    const row = el('div', 'tx-line', host);
    if (ln.idx.every((i) => S.cutWords.has(i))) row.classList.add('cut');
    // o carimbo é também a alça da LINHA: clicar seleciona a deixa inteira
    const t = el('button', 'tx-t', row);
    t.type = 'button';
    t.dataset.line = ln.idx.join(',');
    t.textContent = fmt(ln.start);
    const txt = el('div', 'tx-words', row);
    for (const i of ln.idx) {
      const w = S.words[i];
      const sp = el('span', 'tw', txt);
      sp.dataset.i = i;
      sp.textContent = w.text;
      if (w.gapBefore === 0 && w.gapAfter === 0) sp.classList.add('tight');
      if (S.cutWords.has(i)) sp.classList.add('cut');
      if (S.selWords.has(i)) sp.classList.add('sel');
      sp.title = `${fmt(w.outStart)} · folga ${w.gapBefore.toFixed(2)}s / ${w.gapAfter.toFixed(2)}s`;
      // o respiro entra COMO CHIP no lugar do espaço: ele ocupa tempo no vídeo,
      // então ocupa espaço no texto. Um respiro invisível não se remove.
      const br = breathAt(i);
      if (br) {
        const chip = el('button', 'tw-breath', txt);
        chip.type = 'button';
        chip.dataset.breath = i;
        chip.textContent = `${br.dur.toFixed(1)}s`;
        chip.title = S.cutBreaths.has(i)
          ? `respiro de ${br.dur.toFixed(2)}s → fica ${br.keep.toFixed(2)}s (−${br.trim.toFixed(2)}s)`
          : `respiro de ${br.dur.toFixed(2)}s · clique para encurtar até ${br.keep.toFixed(2)}s`;
        if (S.cutBreaths.has(i)) chip.classList.add('cut');
      } else {
        txt.append(' ');
      }
    }
  }
  const n = S.cutWords.size;
  const b = S.cutBreaths.size;
  const partes = [];
  if (n) partes.push(`${n} palavra${n === 1 ? '' : 's'}`);
  if (b) {
    const ganho = [...S.cutBreaths].reduce((s, i) => s + (breathAt(i)?.trim || 0), 0);
    partes.push(`${b} respiro${b === 1 ? '' : 's'} (−${ganho.toFixed(1)}s)`);
  }
  $('txCount').textContent = partes.length ? `${partes.join(' · ')} para remoção` : '';
  renderCutMarks();   // a marca segue o texto, mesmo com a timeline recolhida
  markNowWord();
}

/* A palavra que está tocando. É o que amarra o texto à agulha — sem isso são
   duas telas, e a razão de o switch existir é serem a mesma. */
function markNowWord() {
  if (S.view !== 'tx' || !S.words.length) return;
  const t = renderedToDraft(video.currentTime || 0);
  let hit = -1;
  for (let i = 0; i < S.words.length; i++) {
    if (S.words[i].outStart <= t) hit = i; else break;
  }
  document.querySelectorAll('.tw.now').forEach((n) => n.classList.remove('now'));
  if (hit >= 0) {
    const n = $('txBody').querySelector(`.tw[data-i="${hit}"]`);
    if (n) n.classList.add('now');
  }
}

document.querySelectorAll('.vseg').forEach((b) => {
  b.innerHTML = ICON[b.dataset.view === 'tl' ? 'cam' : 'script'];
  b.addEventListener('click', () => setView(b.dataset.view));
});

/* SELEÇÃO POR ARRASTO. Marcar palavra a palavra funciona para um gaguejo, mas
   apagar uma oração inteira vira trabalho braçal — e apagar orações é o uso
   real. Arrastar é o gesto que qualquer um já usa em texto. O carimbo de tempo
   é a alça da deixa: um clique nele pega a linha toda. */
let txDrag = null;

const txPaint = (a, b) => {
  S.selWords.clear();
  for (let k = Math.min(a, b); k <= Math.max(a, b); k++) S.selWords.add(k);
  // repinta sem reconstruir: remontar a cada movimento do mouse pisca a tela
  $('txBody').querySelectorAll('.tw').forEach((n) => {
    n.classList.toggle('sel', S.selWords.has(+n.dataset.i));
  });
};

$('txBody').addEventListener('pointerdown', (e) => {
  // O respiro vem ANTES da palavra no teste: o chip é filho de `.tx-words`, e
  // um `closest('.tw')` mais abaixo não o pegaria — mas a seleção por arraste
  // pegaria, e clicar num respiro passaria a pintar palavras.
  const br = e.target.closest('.tw-breath');
  if (br) {
    const i = +br.dataset.breath;
    S.cutBreaths.has(i) ? S.cutBreaths.delete(i) : S.cutBreaths.add(i);
    renderTx();
    e.preventDefault();
    return;
  }
  const t = e.target.closest('.tx-t');
  if (t) {
    const idx = t.dataset.line.split(',').map(Number);
    S.selWords = new Set(idx);
    seekDraft(S.words[idx[0]].outStart);
    renderTx();
    e.preventDefault();
    return;
  }
  const sp = e.target.closest('.tw');
  if (!sp) return;
  const i = +sp.dataset.i;
  if (e.shiftKey && S.selWords.size) { txPaint(Math.min(...S.selWords), i); return; }
  if (e.metaKey || e.ctrlKey) {
    S.selWords.has(i) ? S.selWords.delete(i) : S.selWords.add(i);
    renderTx();
    return;
  }
  txDrag = { from: i, moved: false };
  txPaint(i, i);
  try { $('txBody').setPointerCapture(e.pointerId); } catch (err) { /* toque */ }
  e.preventDefault();
});

$('txBody').addEventListener('pointermove', (e) => {
  if (!txDrag) return;
  const sp = document.elementFromPoint(e.clientX, e.clientY);
  const w = sp && sp.closest && sp.closest('.tw');
  if (!w) return;
  const i = +w.dataset.i;
  if (i !== txDrag.from) txDrag.moved = true;
  txPaint(txDrag.from, i);
});

$('txBody').addEventListener('pointerup', (e) => {
  if (!txDrag) return;
  // clique seco (sem arrastar) também LEVA a agulha até a palavra
  if (!txDrag.moved) seekDraft(S.words[txDrag.from].outStart);
  txDrag = null;
  renderTx();
});


/* ---------- POSIÇÃO DA LEGENDA ----------
 *
 * Arrastar a legenda sobre o vídeo move TODAS: é um ajuste de estilo, não uma
 * correção de deixa. Uma legenda que muda de altura no meio do vídeo lê como
 * defeito, não como intenção — e o compositor também trata a posição como um
 * número só (`captions.paddingBottom`).
 *
 * O deslocamento é guardado em px de referência 1080, a mesma unidade das
 * folhas. Guardar em pixels de tela quebraria ao redimensionar a janela; guardar
 * em fração da altura quebraria ao trocar de proporção.
 *
 * As ancoragens são DIFERENTES e é por isso que existe esta função em vez de uma
 * variável só: karaokê e estáticas medem da BASE do quadro (mais px = mais alto),
 * empilhado e disperso medem do CENTRO por fração (mais fração = mais baixo).
 * Aplicar o mesmo sinal aos dois mandaria metade dos estilos para o lado errado. */
const CAP_ANCHOR = {
  karaoke: { var: '--cap-bottom', base: 430, dir: +1, scale: 1 },
  simples: { var: '--cap-bottom', base: 430, dir: +1, scale: 1 },
  serifada: { var: '--cap-bottom', base: 430, dir: +1, scale: 1 },
  classica: { var: '--cap-bottom', base: 430, dir: +1, scale: 1 },
  stacked: { var: '--stk-offset-y', base: 0.156, dir: -1, scale: 1 / 1920 },
  scatter: { var: '--scat-offset-y', base: 0.72, dir: -1, scale: 1 / 1920 },
};
// os do motor `palavra` sentam no rodapé como o karaokê — menos o rotativo,
// que vive no CENTRO do quadro e por isso se move pela fração, não pelos px
for (const [id] of PAL) {
  CAP_ANCHOR[id] = id === 'rotativo'
    ? { var: '--pal-centro', base: 0.5, dir: +1, scale: 1 / 1920 }
    : { var: '--cap-bottom', base: 430, dir: +1, scale: 1 };
}

function applyCapDy(box, id, v) {
  const a = CAP_ANCHOR[id];
  if (!a) return;
  const base = (a.var === '--cap-bottom' && v.bottom) || (v.offsetY != null && a.var !== '--cap-bottom' ? v.offsetY : a.base);
  const dy = S.style.capDy || 0;
  box.style.setProperty(a.var, base + a.dir * dy * a.scale);
}

/* O overlay é `pointer-events: none` para não roubar clique do player. A caixa
   da legenda reabre os eventos só nela — arrastar a legenda não pode custar a
   possibilidade de clicar no vídeo. */
let capDrag = null;
$('liveOverlay').addEventListener('pointerdown', (e) => {
  const box = e.target.closest('.ave-cap, .ave-cap-static, .ave-stacked, .ave-scatter, .ave-pal');
  if (!box) return;
  const w = $('liveOverlay').clientWidth || 1;
  capDrag = { y0: e.clientY, dy0: S.style.capDy || 0, sc: w / 1080 };
  try { $('liveOverlay').setPointerCapture(e.pointerId); } catch (err) { /* toque */ }
  e.preventDefault();
});
window.addEventListener('pointermove', (e) => {
  if (!capDrag) return;
  // para CIMA é positivo, e a conversão volta para a referência 1080
  const dy = capDrag.dy0 + (capDrag.y0 - e.clientY) / capDrag.sc;
  S.style.capDy = Math.round(Math.max(-380, Math.min(760, dy)));
  LIVE.key = null;
  renderLive();
  showTooltip(e, `legenda <b>${S.style.capDy >= 0 ? '+' : ''}${S.style.capDy}</b> px`);
});
window.addEventListener('pointerup', () => {
  if (!capDrag) return;
  capDrag = null;
  hideTooltip();
  refreshHeader();   // virou uma alteração a enviar
});

/* ---------- faixa de progresso: o que está acontecendo AGORA ----------
 *
 * Lida do mesmo `/api/state` que o resto, mas desenhada FORA do `applyState`:
 * o `applyState` só roda quando a assinatura muda, e o progresso muda a cada
 * segundo. Passar o progresso pela assinatura remontaria a timeline inteira a
 * cada tique — e pior, o guarda de "você tem ajustes não salvos" bloquearia a
 * atualização justamente enquanto o usuário espera, que é quando ele mais
 * precisa ver.
 *
 * O relógio anda LOCALMENTE entre os polls (o poll é de 2s; um cronômetro que
 * pula de 2 em 2 lê como travado, que é o oposto do que esta faixa existe para
 * dizer).
 */
let progLocal = null;      // último progresso recebido, para o relógio local
let progTick = null;

function fmtElapsed(sec) {
  sec = Math.max(0, Math.floor(sec));
  const m = Math.floor(sec / 60), s = sec % 60;
  return m ? `${m}m ${String(s).padStart(2, '0')}s` : `${s}s`;
}

/* Um sucesso não fica na tela para sempre — ele confirma e sai de cena.
   Um ERRO fica: sumir com a mensagem é como não ter avisado. */
const DONE_LINGER_S = 6;

function paintProgress() {
  const el = $('progress');
  const p = progLocal;
  if (!el) return;
  if (!p || !p.state) { el.classList.add('hidden'); return; }

  const elapsed = (p.endedAt || (Date.now() / 1000)) - (p.startedAt || 0);
  if (p.state === 'done' && (Date.now() / 1000) - (p.endedAt || 0) > DONE_LINGER_S) {
    el.classList.add('hidden');
    return;
  }

  el.classList.remove('hidden');
  el.classList.toggle('ai', !!p.ai && p.state === 'running');
  el.classList.toggle('done', p.state === 'done');
  el.classList.toggle('failed', p.state === 'failed');
  el.classList.toggle('indet', p.state === 'running' && (p.pct === null || p.pct === undefined));

  $('progAi').classList.toggle('hidden', !p.ai);
  $('progLabel').textContent = p.label || 'Processando…';
  // no fim, o tempo vira "levou X" — o número que interessa muda de sentido
  $('progTime').textContent = p.state === 'running'
    ? fmtElapsed(elapsed)
    : (p.state === 'failed' ? 'falhou' : `levou ${fmtElapsed(elapsed)}`);
  $('progDetail').textContent = p.detail || '';
  const fill = $('progFill');
  if (p.state === 'running' && p.pct !== null && p.pct !== undefined) {
    fill.style.width = `${p.pct}%`;
  } else if (p.state !== 'running') {
    fill.style.width = '100%';
  } else {
    fill.style.width = '';        // indeterminada: quem manda é a animação
  }
}

function setProgress(p) {
  progLocal = p;
  paintProgress();
  if (progTick) clearInterval(progTick);
  // o relógio só corre enquanto há o que cronometrar
  if (p && p.state === 'running') progTick = setInterval(paintProgress, 1000);
}

/* ---------- Exportar: o arquivo pronto, sem passar pela IA ----------
 *
 * O arquivo já existe no disco. Pedir a um agente para copiá-lo gastaria uma
 * conversa inteira (e tokens) num download — e o usuário ainda ficaria sem
 * escolher onde salvar.
 *
 * Dois caminhos, e o primeiro só existe em navegador que o suporte:
 *   1. `showSaveFilePicker` — o diálogo NATIVO de salvar. É o único que deixa
 *      escolher a pasta de verdade; o `download` do <a> obedece à configuração
 *      do navegador e normalmente joga em Downloads sem perguntar.
 *   2. `<a download>` — a reserva, que funciona em qualquer lugar.
 *
 * A ORDEM entre perguntar e baixar não é detalhe: o seletor exige ativação do
 * usuário e baixar primeiro queima essa janela. Está explicado no `doExport`,
 * onde o defeito morava.
 *
 * O nome do arquivo vem do servidor (do `project` do state), não daqui: baixar
 * `final.mp4` é inútil na pasta de quem edita cinco vídeos por semana.
 */
function exportName() {
  const slug = String(S.state.project || 'avelin')
    .normalize('NFKD').replace(/[̀-ͯ]/g, '')
    .replace(/[^A-Za-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 70).toLowerCase();
  return `${slug || 'avelin'}-${S.state.finalVideo ? 'final' : 'corte'}.mp4`;
}

function refreshExport() {
  const b = $('exportBtn');
  if (!b) return;
  const temFinal = !!S.state.finalVideo;
  const temAlgo = temFinal || S.videoDuration > 0;
  b.disabled = !temAlgo;
  $('exportLabel').textContent = temFinal ? 'Exportar' : 'Baixar corte';
  b.title = !temAlgo
    ? 'Ainda não há vídeo para exportar'
    : (temFinal
        ? `Baixa o vídeo finalizado (${exportName()})`
        : 'A finalização ainda não foi montada — isto baixa o CORTE, sem legenda nem gráficos');
}

async function doExport() {
  const b = $('exportBtn');
  if (!b || b.disabled) return;
  const nome = exportName();
  const lab = $('exportLabel');
  const textoOriginal = lab.textContent;

  /* O SELETOR DE DESTINO VEM PRIMEIRO, e a ordem é o conserto.
   *
   * Antes o arquivo era baixado inteiro e só então se perguntava onde salvar.
   * `showSaveFilePicker` exige ativação do usuário — a janela de ~5s aberta
   * pelo clique — e baixar 80MB para a memória consome essa janela. O seletor
   * então falhava com SecurityError, o `catch` o tratava como "sem seletor" e
   * o código caía CALADO no `<a download>`, que salva na pasta de downloads do
   * navegador. O usuário escolhia um destino e o arquivo aparecia em outro,
   * com um aviso dizendo "Exportado" — medido: a exportação foi parar em
   * ~/Documents.
   *
   * Perguntando antes, o clique ainda está valendo. E o download passa a ir
   * direto para o disco, sem os 80MB de blob na memória. */
  let handle = null;
  if (window.showSaveFilePicker) {
    try {
      handle = await window.showSaveFilePicker({
        suggestedName: nome,
        types: [{ description: 'Vídeo MP4', accept: { 'video/mp4': ['.mp4'] } }],
      });
    } catch (e) {
      // cancelar o diálogo é uma escolha, não um erro: sair calado.
      if (e && e.name === 'AbortError') return;
      handle = null;   // sem seletor neste navegador — cai na pasta de downloads
    }
  }
  b.classList.add('busy');

  try {
    const res = await fetch('/download');
    if (!res.ok) {
      // a MENSAGEM do servidor, não o número: "unknown route" significa
      // servidor velho (reinicie), "nada para exportar" significa outra coisa
      // completamente. Um "404" cru não distingue as duas.
      let motivo = `HTTP ${res.status}`;
      try { motivo = (await res.json()).error || motivo; } catch (_) {}
      if (/unknown route/i.test(motivo)) {
        throw new Error('o servidor de preview é anterior a este botão — reinicie-o');
      }
      throw new Error(motivo);
    }

    // Progresso por bytes: um arquivo de 80MB em rede local é rápido, mas em
    // disco lento não é — e um botão que não muda durante a espera parece
    // um clique que não pegou, que é o defeito que esta interface já corrigiu
    // em outros lugares.
    const total = +(res.headers.get('Content-Length') || 0);
    const reader = res.body && res.body.getReader ? res.body.getReader() : null;
    const progresso = (lidos) => {
      lab.textContent = total
        ? `${Math.round(lidos / total * 100)}%`
        : `${(lidos / 1048576).toFixed(0)} MB`;
    };

    // Com destino escolhido, os bytes vão direto para o arquivo. Um `write`
    // por pedaço, sem juntar o vídeo inteiro na memória antes.
    if (handle) {
      const w = await handle.createWritable();
      try {
        if (reader) {
          let lidos = 0;
          for (;;) {
            const { done, value } = await reader.read();
            if (done) break;
            await w.write(value); lidos += value.length; progresso(lidos);
          }
        } else {
          await w.write(await res.blob());
        }
        await w.close();
      } catch (e) {
        // um writable deixado aberto tranca o arquivo e deixa meio vídeo no
        // disco parecendo exportação boa
        try { await w.abort(); } catch (_) {}
        throw e;
      }
      toast(`Exportado para ${handle.name}`, 3000);
      return;
    }

    let blob;
    if (reader) {
      const partes = []; let lidos = 0;
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        partes.push(value); lidos += value.length; progresso(lidos);
      }
      blob = new Blob(partes, { type: 'video/mp4' });
    } else {
      blob = await res.blob();
    }

    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = nome;
    document.body.appendChild(a); a.click(); a.remove();
    // revogar cedo demais cancela o download em alguns navegadores
    setTimeout(() => URL.revokeObjectURL(url), 60000);
    toast('Exportado para a pasta de downloads', 3000);
  } catch (e) {
    // "Failed to fetch" é o navegador dizendo que o SERVIDOR não respondeu —
    // na prática, ele reiniciou embaixo da aba (medido: export de 0 KB no
    // destino em 2026-08-19). Traduzir é o que transforma o erro em ação.
    const rede = e && (e.name === 'TypeError' || /fetch/i.test(e.message || ''));
    toast(rede
      ? 'O servidor reiniciou — recarregue a página (F5) e exporte de novo'
      : `Não consegui exportar: ${e.message}`, 6000);
  } finally {
    b.classList.remove('busy');
    lab.textContent = textoOriginal;
    refreshExport();
  }
}

if ($('exportBtn')) $('exportBtn').addEventListener('click', doExport);

/* O botão segue o que está escrito, tecla a tecla. Recalcular só no poll (2s)
 * deixaria o usuário terminar a frase olhando para um botão ainda apagado —
 * e a leitura disso é "quebrado", não "espere". */
if ($('setupNote')) $('setupNote').addEventListener('input', refreshActionBar);

/* ==========================================================================
   A TELA SEM PROJETO — dropzone, recentes e navegador de pastas
   ==========================================================================
   O editor abre aqui. Antes ele abria dentro da pasta passada na linha de
   comando por quem subiu o processo, que na prática era o último projeto de
   alguém — um vídeo entregue meses antes ocupando a tela como se fosse o
   trabalho da vez, sem nenhuma forma de fechá-lo.

   A DROPZONE É A ENTRADA. Soltar o vídeo é como um editor começa, e o resto
   (recentes, navegar o disco) é o caso menos frequente de quem volta a um
   trabalho que já existe.

   O QUE O NAVEGADOR NÃO DÁ, e que decide todo o desenho daqui: o CAMINHO do
   arquivo solto. `File` traz nome, tamanho e conteúdo; `webkitdirectory` traz
   os nomes dos filhos. Nenhum dos dois diz onde a coisa está, e não é falta de
   API — é fronteira de segurança do navegador. Por isso o par nome+tamanho vai
   ao servidor, que procura o arquivo no disco e o usa ONDE ELE ESTÁ. Uma fonte
   de 5 GB não vira duas. Só quando a busca falha é que os bytes sobem. */

let homeOn = false;

function showHome() {
  if (!homeOn) {
    homeOn = true;
    const v = $('video');
    if (v) { try { v.pause(); } catch (e) { /* ainda sem fonte */ } }
    loadProjects();
  }
  $('home').classList.remove('hidden');
  $('stage').classList.add('hidden');
  $('emptyState').classList.add('hidden');
  if ($('startPanel')) $('startPanel').classList.add('hidden');
  $('homeBtn').classList.add('hidden');
  renderDepsCard();
  /* O cabeçalho é do PROJETO. Sem um aberto, tudo o que ele mostra é falso:
     "Exportar" oferece um arquivo que não existe, o `?` explica atalhos de uma
     linha do tempo que não está na tela, e o nome repetia a marca que o logo
     ao lado já diz. Esconder é mais honesto que desabilitar — um botão apagado
     ainda promete que há algo ali, só que agora não. */
  $('exportBtn').classList.add('hidden');
  if ($('btnHelp')) $('btnHelp').classList.add('hidden');
  /* As barras de ação vivem FORA do `#stage` — esconder o palco não as levava
     junto. O sintoma era um rodapé oferecendo "enviar ao Claude" sobre uma
     tela onde não há corte nenhum, e ele só aparecia na VOLTA de um projeto,
     que é o caminho que ninguém testa primeiro. */
  ['approveBar', 'actionBar', 'procBar', 'savedPill'].forEach((id) => {
    if ($(id)) $(id).classList.add('hidden');
  });
  $('projectName').textContent = '';
  document.title = 'Avelin — Editor';
}

function hideHome() {
  homeOn = false;
  $('home').classList.add('hidden');
  $('homeBtn').classList.remove('hidden');
  $('exportBtn').classList.remove('hidden');
  if ($('btnHelp')) $('btnHelp').classList.remove('hidden');
}

function faseLabel(p) {
  return p == null ? '' : (p >= 3 ? 'entregue' : `fase ${p}`);
}

function projRow(c) {
  const b = document.createElement('button');
  b.className = 'proj';
  b.title = c.path;
  const fase = faseLabel(c.phase);
  b.innerHTML = `<span class="proj-name"></span><span class="proj-meta">`
    + `<span class="proj-phase"></span><span class="sep"></span></span>`;
  b.querySelector('.proj-name').textContent = c.name;
  b.querySelector('.proj-phase').textContent = fase;
  // O RECADO do state, que é onde está escrito o que falta fazer. É a
  // diferença entre uma lista de nomes e uma lista de trabalhos.
  b.querySelector('.sep').textContent = c.message ? (fase ? ' · ' : '') + c.message : '';
  b.addEventListener('click', () => openProject(c.path));
  return b;
}

async function loadProjects() {
  try {
    const d = await (await fetch('/api/projects')).json();
    for (const [alvo, itens, vazio] of [
      ['recentList', d.recent || [], 'nenhum ainda — solte um vídeo acima'],
      ['foundList', d.found || [], 'nada encontrado em Movies, Desktop ou Documents'],
    ]) {
      const el = $(alvo);
      el.textContent = '';
      if (!itens.length) {
        const p = document.createElement('div');
        p.className = 'proj-empty';
        p.textContent = vazio;
        el.appendChild(p);
        continue;
      }
      itens.forEach((c) => el.appendChild(projRow(c)));
    }
  } catch (e) { /* servidor reiniciando; o poll volta */ }
}

/* Abrir NÃO espera o poll de 2s. Entre clicar e ver, dois segundos de tela
   parada leem como clique perdido, e a pessoa clica de novo. */
async function refreshNow() {
  try {
    const data = await (await fetch('/api/state')).json();
    S.lastSig = JSON.stringify([data.state, data.edl, data.mtimes, data.videoDuration]);
    await applyState(data);
  } catch (e) { /* o poll pega */ }
}

async function openProject(path, create) {
  try {
    const res = await fetch('/api/open', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path, create: !!create }),
    });
    const d = await res.json();
    if (!res.ok) {
      // A pasta existe e não tem projeto: isso é uma OFERTA, não um erro.
      if (d.canCreate && confirm(`Criar um projeto novo em ${path}?`)) {
        return openProject(path, true);
      }
      toast(d.error || 'não consegui abrir', 5000);
      return false;
    }
    closeBrowser();
    await refreshNow();
    return true;
  } catch (e) {
    toast(`não consegui abrir: ${e.message}`, 5000);
    return false;
  }
}

// ---------- dropzone ----------
const dzMsg = (txt, err) => {
  const el = $('dzMsg');
  if (!el) return;
  el.textContent = txt || '';
  el.classList.toggle('err', !!err);
};

function dzBusy(on) {
  $('dropzone').classList.toggle('busy', on);
  if (!on) { $('dzProg').classList.add('hidden'); $('dzProgFill').style.width = '0'; }
}

async function handleFile(file) {
  dzBusy(true);
  dzMsg(`procurando “${file.name}” no seu disco…`);
  let d;
  try {
    const res = await fetch('/api/drop', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: file.name, size: file.size }),
    });
    d = await res.json();
    if (!res.ok && !d.needUpload) { dzBusy(false); dzMsg(d.error || 'não deu', true); return; }
  } catch (e) { dzBusy(false); dzMsg(e.message, true); return; }

  if (d.needUpload) {
    // Não achou no disco: agora sim os bytes sobem. XHR e não fetch porque só
    // ele reporta progresso de ENVIO — e é o envio que demora aqui.
    dzMsg(`não achei no disco — copiando ${(file.size / 1048576).toFixed(0)} MB…`);
    $('dzProg').classList.remove('hidden');
    try {
      await new Promise((ok, fail) => {
        const x = new XMLHttpRequest();
        x.open('POST', `/api/upload?name=${encodeURIComponent(file.name)}`);
        x.upload.onprogress = (ev) => {
          if (ev.lengthComputable) {
            $('dzProgFill').style.width = `${(ev.loaded / ev.total) * 100}%`;
          }
        };
        x.onload = () => (x.status < 300 ? ok() : fail(new Error(
          (JSON.parse(x.responseText || '{}').error) || `HTTP ${x.status}`)));
        x.onerror = () => fail(new Error('a transferência falhou'));
        x.send(file);
      });
    } catch (e) { dzBusy(false); dzMsg(e.message, true); return; }
  }
  dzBusy(false);
  dzMsg('');
  await refreshNow();
}

async function handleDirEntry(entry) {
  dzBusy(true);
  dzMsg(`procurando a pasta “${entry.name}”…`);
  // Os filhos são o desempate: há três pastas `Broll` no disco desta máquina.
  let entries = [];
  try {
    entries = await new Promise((ok) => {
      const r = entry.createReader();
      r.readEntries((es) => ok(es.map((e) => e.name)), () => ok([]));
    });
  } catch (e) { /* segue só com o nome */ }
  try {
    const res = await fetch('/api/drop', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ kind: 'dir', name: entry.name, entries }),
    });
    const d = await res.json();
    dzBusy(false);
    if (!res.ok) {
      dzMsg(`${d.error || 'não achei'} — use “selecione uma pasta”`, true);
      return;
    }
    dzMsg('');
    await refreshNow();
  } catch (e) { dzBusy(false); dzMsg(e.message, true); }
}

function wireDropzone() {
  const dz = $('dropzone');
  if (!dz) return;
  // A JANELA INTEIRA precisa cancelar o padrão, não só a zona. Sem isto,
  // soltar o vídeo um pixel fora faz o Chrome NAVEGAR para o arquivo — a
  // página do editor some e o trabalho vai junto.
  ['dragenter', 'dragover', 'drop'].forEach((ev) => {
    window.addEventListener(ev, (e) => { e.preventDefault(); }, false);
  });
  dz.addEventListener('dragenter', () => dz.classList.add('over'));
  dz.addEventListener('dragover', (e) => {
    e.dataTransfer.dropEffect = 'copy';
    dz.classList.add('over');
  });
  // `dragleave` dispara ao cruzar para um filho da própria zona. Sem checar
  // para ONDE foi, a moldura pisca a cada movimento do mouse lá dentro.
  dz.addEventListener('dragleave', (e) => {
    if (!dz.contains(e.relatedTarget)) dz.classList.remove('over');
  });
  dz.addEventListener('drop', async (e) => {
    dz.classList.remove('over');
    const it = e.dataTransfer.items && e.dataTransfer.items[0];
    const entry = it && it.webkitGetAsEntry && it.webkitGetAsEntry();
    if (entry && entry.isDirectory) return handleDirEntry(entry);
    const f = e.dataTransfer.files && e.dataTransfer.files[0];
    if (f) return handleFile(f);
    dzMsg('não veio arquivo nenhum nesse arrasto', true);
  });

  dz.addEventListener('click', (e) => {
    if (e.target.closest('button')) return; // os dois links têm dono próprio
    $('fileInput').click();
  });
  dz.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); $('fileInput').click(); }
  });
  $('pickFile').addEventListener('click', (e) => { e.stopPropagation(); $('fileInput').click(); });
  $('pickFolder').addEventListener('click', (e) => { e.stopPropagation(); openBrowser(); });
  $('fileInput').addEventListener('change', (e) => {
    const f = e.target.files && e.target.files[0];
    e.target.value = ''; // reescolher o MESMO arquivo tem de disparar de novo
    if (f) handleFile(f);
  });
}

// ---------- navegador de pastas ----------
let brPath = null;

function elidePath(p, max = 58) {
  if (p.length <= max) return p;
  // O corte cai num separador: partir um nome de pasta pela metade produz um
  // fragmento que parece outra pasta.
  const cauda = p.slice(-(max - 14));
  const sep = cauda.indexOf('/');
  return `${p.slice(0, 12)}…${sep >= 0 ? cauda.slice(sep) : cauda}`;
}

async function openBrowser(path) {
  $('browser').classList.remove('hidden');
  await browseTo(path || null);
}
function closeBrowser() { $('browser').classList.add('hidden'); }

async function browseTo(path) {
  let d;
  try {
    d = await (await fetch(`/api/browse${path ? `?path=${encodeURIComponent(path)}` : ''}`)).json();
  } catch (e) { toast(`não consegui listar: ${e.message}`, 4000); return; }
  if (d.error) { toast(d.error, 4000); return; }
  brPath = d.path;
  // Encurta pelo MEIO: num caminho longo quem identifica onde você está é o
  // fim, e a raiz dá o contexto — o miolo é a parte descartável.
  $('brPath').textContent = elidePath(d.path);
  $('brPath').title = d.path;
  $('brUp').disabled = !d.parent;
  $('brUp').onclick = () => d.parent && browseTo(d.parent);
  const eProj = d.dirs.some((x) => x.isProject || x.hasProject);
  $('brHint').textContent = eProj
    ? 'as marcadas já têm um projeto do Avelin'
    : 'sem projeto aqui — abrir esta pasta cria um';
  const list = $('brList');
  list.textContent = '';
  d.dirs.forEach((x) => {
    const b = document.createElement('button');
    b.className = 'br-row';
    b.innerHTML = '<span class="ic">▸</span><span class="nm"></span>';
    b.querySelector('.nm').textContent = x.name;
    if (x.isProject || x.hasProject) {
      const t = document.createElement('span');
      t.className = 'tag';
      t.textContent = 'projeto';
      b.appendChild(t);
      // Uma pasta que É o projeto abre; uma que CONTÉM o projeto também —
      // descer mais um nível para clicar em `edit` é um passo sem escolha.
      b.addEventListener('click', () => openProject(x.path));
    } else {
      b.addEventListener('click', () => browseTo(x.path));
    }
    list.appendChild(b);
  });
  if (!d.dirs.length) {
    const p = document.createElement('div');
    p.className = 'proj-empty';
    p.textContent = 'nenhuma subpasta aqui';
    list.appendChild(p);
  }
}

if ($('brClose')) $('brClose').addEventListener('click', closeBrowser);
if ($('brOpen')) $('brOpen').addEventListener('click', () => brPath && openProject(brPath, true));
if ($('browser')) {
  $('browser').addEventListener('click', (e) => { if (e.target === $('browser')) closeBrowser(); });
}
window.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && !$('browser').classList.contains('hidden')) closeBrowser();
});

if ($('homeBtn')) {
  $('homeBtn').addEventListener('click', async () => {
    // Fechar é do SERVIDOR, não da tela. Só esconder a interface deixaria o
    // root apontando para o projeto antigo, e o próximo poll o traria de volta.
    await fetch('/api/close', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
    await refreshNow();
  });
}

wireDropzone();

/* ==========================================================================
   A CHECKLIST DA INSTALAÇÃO
   ==========================================================================
   O servidor já publicava `deps` e `keys` a cada poll e ninguém lia. Enquanto
   isso, quem instalava descobria cada dependência por MENSAGEM DE ERRO, uma de
   cada vez, e sempre no meio de um trabalho: esperar dois minutos por uma
   transcrição para então ler que falta o ffmpeg é o pior lugar possível para
   dar essa notícia.

   Duas regras de desenho:
   · OBRIGATÓRIO e OPCIONAL ficam separados e nomeados. Uma lista única de onze
     itens com ✓ e ✗ misturados não diz o que impede de trabalhar hoje.
   · Recolhida quando está tudo certo. Dez confirmações verdes em toda abertura
     são ruído; o que importa nesse caso cabe numa linha. */

const IS_WIN = /Win/i.test((navigator.userAgentData && navigator.userAgentData.platform)
                           || navigator.platform || navigator.userAgent || '');

const DEP_ITEMS = [
  { id: 'ffmpeg', dep: 'ffmpeg', req: true, name: 'ffmpeg',
    why: 'corta, converte e exporta — a Fase 1 inteira passa por ele',
    fix: IS_WIN ? 'winget install Gyan.FFmpeg' : 'brew install ffmpeg' },
  { id: 'ffprobe', dep: 'ffprobe', req: true, name: 'ffprobe',
    why: 'lê duração, resolução e fps das fontes',
    fix: 'vem junto com o ffmpeg' },
  { id: 'uv', dep: 'uv', req: true, name: 'uv (Python)',
    why: 'roda os helpers da skill no ambiente certo',
    fix: IS_WIN ? 'winget install astral-sh.uv' : 'brew install uv' },
  { id: 'groq', key: 'groq', req: true, name: 'Chave do Groq',
    why: 'transcrição — sem ela nada é cortado, porque o corte parte do texto',
    fix: 'console.groq.com/keys → GROQ_API_KEY no .env da skill' },
  /* Node é obrigatório, mas só a partir da Fase 2 — e essa diferença muda o
     que a tela deve fazer: ela AVISA, e não impede de gerar o corte. */
  { id: 'node', dep: 'node', req: true, phase2: true, name: 'Node.js 18+',
    why: 'motor da Fase 2 (legendas, gráficos, imagens)',
    fix: IS_WIN ? 'winget install OpenJS.NodeJS.LTS' : 'brew install node' },

  { id: 'hyperframes', dep: 'hyperframes', name: 'Cache do HyperFrames',
    why: 'os ~365 MB do motor da Fase 2',
    fix: 'baixa sozinho na primeira Fase 2 — nada a fazer' },
  { id: 'ytdlp', dep: 'ytdlp', name: 'yt-dlp',
    why: 'trazer material de uma URL (YouTube, Drive)',
    fix: IS_WIN ? 'winget install yt-dlp.yt-dlp' : 'brew install yt-dlp' },
  { id: 'elevenlabs', key: 'elevenlabs', name: 'Chave da ElevenLabs',
    why: 'transcrever fontes longas (>5 min) com mais precisão',
    fix: 'elevenlabs.io/app/settings/api-keys → ELEVENLABS_API_KEY' },
  { id: 'pexels', key: 'pexels', name: 'Chave da Pexels',
    why: 'imagens e vídeos ilustrativos na Fase 2',
    fix: 'pexels.com/api → PEXELS_API_KEY' },
  { id: 'treblo', key: 'treblo', name: 'Chave da Treblo',
    why: 'trilha gerada por IA na Fase 3 (um arquivo local não precisa de chave)',
    fix: 'sonauto.ai → TREBLO_API_KEY' },
  { id: 'google', key: 'google', name: 'Busca do Google',
    why: 'marcas e pessoas que a Pexels não tem — a Wikimedia cobre sem chave',
    fix: 'GOOGLE_API_KEY + GOOGLE_CSE_ID (mesmo projeto no Google Cloud)' },
];

/* Sem resposta do servidor ainda devolve `null`, não `false`: um ✗ por
   ausência de dado acusaria o usuário de não ter instalado o que ele tem. */
function depOk(it) {
  const src = it.dep ? S.deps : S.keys;
  if (!src) return null;
  const k = it.dep || it.key;
  return k in src ? !!src[k] : null;
}

const depMissing = (f) => DEP_ITEMS.filter((it) => depOk(it) === false).filter(f || (() => true));
/* O que impede de gerar o corte HOJE. O Node fica de fora de propósito: ele
   trava a Fase 2, e travar o botão por causa dele mandaria o usuário instalar
   um motor de render para ver um corte que não usa nenhum. */
const depBlocking = () => depMissing((it) => it.req && !it.phase2);

function depRow(it) {
  const ok = depOk(it);
  const row = document.createElement('div');
  row.className = `dep-row${ok === false ? ' miss' : ''}${ok === null ? ' unk' : ''}`;
  row.innerHTML = '<span class="dep-ic"></span>'
    + '<span class="dep-txt"><span class="dep-name"></span>'
    + '<span class="dep-why"></span></span>';
  row.querySelector('.dep-ic').textContent = ok === null ? '·' : (ok ? '✓' : '✗');
  row.querySelector('.dep-name').textContent = it.name
    + (it.phase2 ? ' — a partir da Fase 2' : '');
  // Faltando, a linha diz COMO resolver; presente, diz para que serve. As duas
  // frases servem a momentos diferentes e mostrar as duas juntas dobra a lista.
  row.querySelector('.dep-why').textContent = ok === false ? it.fix : it.why;
  return row;
}

function depGroup(titulo, itens) {
  const wrap = document.createElement('div');
  wrap.className = 'dep-group';
  const h = document.createElement('h4');
  h.textContent = titulo;
  wrap.appendChild(h);
  itens.forEach((it) => wrap.appendChild(depRow(it)));
  return wrap;
}

let depsOpenUser = null;   // o usuário mandou abrir/fechar? aí a vontade dele manda
let depsSig = '';

function renderDepsCard() {
  const card = $('depsCard');
  if (!card) return;
  if (!S.deps && !S.keys) { card.classList.add('hidden'); return; }
  const sig = JSON.stringify([S.deps, S.keys, depsOpenUser]);
  if (sig === depsSig) return;      // o poll é de 2s; remontar onze linhas a cada tique é à toa
  depsSig = sig;
  card.classList.remove('hidden');

  const faltaObrig = depBlocking();
  const faltaNode = depMissing((it) => it.phase2).length > 0;
  const faltaOpc = depMissing((it) => !it.req).length;

  let resumo;
  if (faltaObrig.length) {
    resumo = `Falta ${faltaObrig.length === 1 ? 'um item obrigatório' : `${faltaObrig.length} itens obrigatórios`}: `
      + faltaObrig.map((it) => it.name).join(', ');
  } else if (faltaNode) {
    resumo = 'Pronto para cortar — o Node.js falta só para a Fase 2';
  } else {
    resumo = 'Tudo pronto para editar';
    if (faltaOpc) resumo += ` · ${faltaOpc} opciona${faltaOpc === 1 ? 'l' : 'is'} sem configurar`;
  }
  $('depsSummary').textContent = resumo;
  card.classList.toggle('warn', faltaObrig.length > 0);

  const body = $('depsBody');
  body.textContent = '';
  body.appendChild(depGroup('Obrigatórios', DEP_ITEMS.filter((it) => it.req)));
  body.appendChild(depGroup('Opcionais — a IA pede quando o recurso for usado',
                              DEP_ITEMS.filter((it) => !it.req)));
  const pe = document.createElement('div');
  pe.className = 'dep-foot';
  pe.textContent = 'As chaves moram no arquivo .env dentro da pasta da skill. '
    + 'Peça à IA no chat — “põe minha chave do Groq no .env” — e ela grava para você.';
  body.appendChild(pe);

  // Aberta sozinha só quando há o que resolver. Depois que o usuário toca no
  // acordeão, quem manda é ele.
  const aberta = depsOpenUser === null ? faltaObrig.length > 0 : depsOpenUser;
  body.classList.toggle('hidden', !aberta);
  $('depsToggle').setAttribute('aria-expanded', String(aberta));
}

if ($('depsToggle')) {
  $('depsToggle').addEventListener('click', () => {
    depsOpenUser = $('depsBody').classList.contains('hidden');
    depsSig = '';               // força a remontagem com o novo estado
    renderDepsCard();
  });
}

/* ==========================================================================
   O COMEÇO DO TRABALHO — submeter o primeiro vídeo, e esperar vendo
   ==========================================================================
   Soltar o arquivo MONTAVA o projeto e PEDIA a Fase 1 na mesma batida. Quem
   soltava não tinha onde ler o que ia acontecer, não tinha como desistir, e a
   tela seguinte ("aguardando o primeiro render") era idêntica à de um projeto
   parado: nada ali distinguia "a IA está trabalhando" de "falta você fazer
   alguma coisa". Agora são dois estados explícitos, e o servidor só escreve o
   `preview_request.json` quando o botão daqui é apertado.

   Formato e briefing moram nesta tela porque são exatamente as duas perguntas
   que a Fase 1 faria no chat antes de começar — respondê-las aqui é o que
   deixa o primeiro envio virar trabalho, e não uma conversa. */

/* As expressões são ESTREITAS de propósito. Com `/cort/` a mensagem inicial —
   "Fase 1 — gerando os cortes" — casava com a terceira etapa e a tela abria
   dizendo que já tinha transcrito e escolhido as tomadas, o que é mentira e
   some com a única informação que o usuário quer. Sem casar nada, a primeira
   fica correndo: transcrever é sempre o começo. */
/* AS ETAPAS QUE O PIPELINE REALMENTE TEM HOJE.
 *
 * A lista antiga cobria cinco e o trabalho passou a ter oito: medir o papel das
 * fontes, auditar o transcrito e medir os respiros entraram depois e não
 * casavam com nenhuma linha. O efeito na tela é pior que faltar uma linha — o
 * destaque fica parado na etapa anterior enquanto a máquina trabalha, e um
 * indicador que não anda é indistinguível de um travado.
 *
 * A ORDEM importa: `forEach` deixa vencer o ÚLTIMO que casar, então uma
 * mensagem que fala de duas etapas cai na mais adiantada — que é a certa. */
const F1_STEPS = [
  { label: 'Medindo as fontes', re: /papel d|fonte|multicam|source_roles|medindo o material/i },
  { label: 'Transcrevendo o áudio', re: /transcri|whisper|scribe/i },
  { label: 'Conferindo a transcrição', re: /audit|conferindo|densidade|reinício|repetiç/i },
  { label: 'Escolhendo as melhores tomadas', re: /tomada|\btake|decupa|estratégia|\bedl\b/i },
  { label: 'Medindo os respiros', re: /respiro|ar morto|pausa|ritmo/i },
  { label: 'Corrigindo a cor', re: /correção de cor|graduaç|color.?grade|\bgrade\b/i },
  { label: 'Cortando e montando', re: /cortando|silêncio|montando o corte|renderiz|encod/i },
  { label: 'Conferindo o corte', re: /proxy|linha do tempo|verific|conferindo o corte|pronto para|aprovaç/i },
];

let startTick = null;

/* '' = esta tela não é da vez · 'working' = a IA está com ele. O vídeo em
   tela vence: se há corte, o lugar do usuário é a linha do tempo.

   Não existe mais o modo 'ready' (formato + briefing + "Gerar cortes"):
   soltar o vídeo já dispara a Fase 1 no servidor, seguindo o aspect ratio da
   fonte. Um `awaitingStart` que ainda apareça aqui é um projeto nascendo (ou
   um antigo que o servidor destrava ao abrir) — mostra-se como trabalho em
   curso, nunca como uma tela pedindo um clique que não existe mais. */
function startMode() {
  if (S.videoDuration > 0) return '';
  if (S.state.awaitingStart) return 'working';
  if (S.state.startedAt) return 'working';
  /* SEM VÍDEO E COM ALGUÉM FALANDO É TRABALHO EM CURSO.
   *
   * `startedAt` era a única porta para a tela de etapas, e ele só é escrito
   * quando o projeto nasce pelo botão "Gerar cortes" do editor. Um projeto
   * criado por fora — que é o caminho do `/ave <pasta>` e de qualquer sessão
   * que monte o `state.json` na mão — caía no `#emptyState`: "aguardando o
   * primeiro render", parado, enquanto oito etapas rodavam do outro lado.
   *
   * O `message` é a prova de que alguém está dirigindo: ele não existe sozinho.
   * Então ele basta para mostrar as etapas. O relógio é que depende do
   * `startedAt` — sem ele mostra-se o progresso sem o tempo decorrido, que é
   * melhor que não mostrar nada. */
  if ((S.state.message || '').trim() && (S.state.phase || 1) === 1) return 'working';
  return '';
}

function renderStartWorking() {
  const msg = (S.state.message || '').trim();
  const linha = (progLocal && progLocal.state === 'running' && progLocal.label) || msg
    || 'Preparando o material…';
  $('startWorkMsg').textContent = linha;

  /* Qual etapa está correndo sai do TEXTO que a skill publica — não de um
     contador nosso. Um contador local mentiria a cada caminho que a Fase 1
     toma (fonte longa, LOG, várias tomadas); o texto, pelo menos, é o que
     está acontecendo de fato. Sem casar nada, o destaque fica na primeira:
     transcrever é sempre o começo. */
  const alvo = `${linha} ${msg}`;
  let ativa = 0;
  F1_STEPS.forEach((s, i) => { if (s.re.test(alvo)) ativa = i; });

  const ol = $('startSteps');
  ol.textContent = '';
  F1_STEPS.forEach((s, i) => {
    const li = document.createElement('li');
    li.className = i < ativa ? 'done' : (i === ativa ? 'now' : '');
    li.textContent = s.label;
    ol.appendChild(li);
  });

  const t0 = +S.state.startedAt || 0;
  $('startElapsed').textContent = t0 ? `Rodando há ${fmtElapsed(Date.now() / 1000 - t0)}.` : '';
}

function renderStart() {
  const painel = $('startPanel');
  if (!painel) return;
  const modo = startMode();
  painel.classList.toggle('hidden', !modo);
  if (modo) renderStartWorking();

  // O relógio anda localmente: o poll é de 2s e um cronômetro que pula de dois
  // em dois lê como travado — que é o oposto do que esta tela existe para dizer.
  if (modo && !startTick) startTick = setInterval(renderStartWorking, 1000);
  if (!modo && startTick) { clearInterval(startTick); startTick = null; }
  return modo;
}

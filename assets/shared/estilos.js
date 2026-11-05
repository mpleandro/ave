/* AVE_ESTILOS — o catálogo de estilos e as prévias, num módulo só.
 *
 * POR QUE EXISTE. O editor (assets/preview) e a galeria de cortes
 * (helpers/cortes_view.py) têm de oferecer a MESMA escolha: os mesmos ids, os
 * mesmos cartões, a mesma legenda e a mesma headline ao vivo, e a escolha tem
 * de virar o MESMO `preview_style.json` que o phase2.py lê. Enquanto tudo isso
 * morava solto no app.js, a galeria só tinha duas saídas: copiar o catálogo (e
 * divergir no primeiro estilo novo, que é o defeito que este repositório já
 * pagou com HL_FALLBACK/GFONTS) ou embutir o editor inteiro num iframe — que
 * foi tentado e desfeito (a61a82d).
 *
 * UM IIFE, UM GLOBAL: `window.AVE_ESTILOS`. Scripts comuns dividem o mesmo
 * escopo global para `const`; um `const PAL` aqui e outro no app.js é
 * SyntaxError, e o editor inteiro deixa de carregar. Por isso nada aqui é
 * declarado no topo, e o app.js desestrutura cada nome uma vez só.
 *
 * SEM ESTADO DA PÁGINA. Nada aqui lê `S`, `LIVE` ou o `<video>` do editor.
 * Quem chama passa `ctx = {frameW, frameH, style}` (style no formato do
 * `S.style` do editor) ou configura UMA vez o padrão com
 * `configurar({quadro, estilo})` — é o que o editor faz, e por isso as chamadas
 * dele continuam sem ctx e o comportamento não mudou.
 *
 * O CORPO NÃO É INDENTADO de propósito: boa parte dele veio do app.js como
 * estava, e os mocks em SVG são template strings — reindentar mexeria no
 * conteúdo delas só para agradar o alinhamento.
 *
 * Ordem de carga: ANTES do app.js (que desestrutura daqui no parse). Os
 * módulos do render (`/styles/{pop,revelar,palavra,cartela}.js`) são lidos na
 * hora de montar cada cartão, então a ordem deles não importa.
 */
(function () {
'use strict';

/* ---------- o ambiente: quem chama sem ctx cai aqui ----------
 * `quadro()` devolve {w, h} do vídeo do projeto (o editor passa o quadro
 * DECODIFICADO; sem nada, o 9:16 de 1080 do short-form). `estilo()` devolve o
 * objeto de escolhas vivo — o editor passa `() => S.style`, então trocar uma
 * escolha não pede reconfigurar nada. `base` é de onde vêm as folhas, os
 * scripts, o variants.json e as fontes empacotadas do render; `assets`, as duas
 * PNGs dos cartões de CTA. */
const amb = {
  quadro: () => ({ w: 1080, h: 1920 }),
  estilo: () => null,
  base: '/styles/',
  assets: '/assets/',
};
function configurar(o) {
  for (const k of Object.keys(o || {})) if (k in amb && o[k] != null) amb[k] = o[k];
}
function ctxDe(ctx) {
  const q = amb.quadro() || {};
  return {
    frameW: (ctx && ctx.frameW) || q.w || 1080,
    frameH: (ctx && ctx.frameH) || q.h || 1920,
    style: (ctx && ctx.style) || amb.estilo() || {},
  };
}
/* A ESCALA das prévias: `largura em tela / largura do QUADRO`. As folhas são
   autoradas em referência de 1080px e a composição passa `--cap-scale: 1`, então
   num projeto horizontal (1920 de largura) um `/1080` fixo faria a legenda sair
   quase o dobro do tamanho que ela terá no render. */
const projW = (ctx) => ctxDe(ctx).frameW;
const ST = (ctx) => ctxDe(ctx).style;

/* O variants.json, quando chegar (ver `carregar`). Antes disso cada leitura cai
   no fallback da própria tabela — e quem desenha espera `pronto()`. */
let VARS = null;
const FOLHAS = new Set();   // as folhas de estilo de legenda já pedidas (liveCss)

const el = (tag, cls, parent) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (parent) parent.appendChild(e);
  return e;
};
/* As marcas de controle do texto da headline — `+`/`-` no começo da linha
 * (±10% de corpo) e "/ /" (mais espaço) — são lidas no RENDER
 * (compose_shortform.hl_marcas). A prévia mostra o texto sem elas. */
const semMarcas = (t) => String(t || '').replace(/\/\s*\//g, '/')
  .split('/').map((l) => l.replace(/^\s*[+-]+/, '')).join('/');
const normHex = (v) => {
  let s = String(v || '').trim().replace(/^#/, '');
  if (/^[0-9a-f]{3}$/i.test(s)) s = s.split('').map((c) => c + c).join(''); // #abc → #aabbcc
  return /^[0-9a-f]{6}$/i.test(s) ? `#${s.toLowerCase()}` : null;
};
const ACCENT_DEFAULT = '#ff3b30';

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
  // legenda Hormozi + cartões visuais (conta, versus, gráfico) acompanhando a fala
  ['grafico', 'Gráfico'],
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
  ['adesivo', 'Adesivo'],
  // 'noticia' NÃO mora aqui: virou elemento independente em STYLE_CATALOG.elements
  // (ela e a Caixinha disputavam a mesma zona alta da tela sem nenhuma arbitragem —
  // ver limpaConflitoZonaAlta(), que hoje resolve por substituição).
  ['capa', 'Capa sólida'], ['capa_blur', 'Capa desfocada'], ['cortina', 'Cortina'],
  ['meia_tela', 'Meia-tela'], ['moldura', 'Moldura'], ['contagem', 'Contagem'],
  ['knockout', 'Knockout'], ['poster', 'Pôster tipográfico'], ['aspas', 'Aspas'],
  ['ficha', 'Ficha técnica'],
];
const CT_IDS = new Set(CARTELAS.map((c) => c[0]));
// As dez cartelas "banda" (cheia:false, entram SOBRE o vídeo) — disputam a
// mesma zona alta que a Caixinha e a Notícia. Lista explícita, não um slice
// da ordem do array: a substituição não pode quebrar em silêncio se alguém
// reordenar CARTELAS por outro motivo.
const CARTELA_BANDA_IDS = new Set(['fita', 'jornal', 'terminal', 'alerta', 'placar',
                                    'sombra_longa', 'neon', 'balao', 'filete', 'adesivo']);

const PORTED = {
  captions: new Set(['karaoke', 'simples', 'serifada', 'classica', 'scatter', 'stacked',
                     'pop', 'popLinha', 'popBloco', 'revelar', 'editorial', 'dinamico',
                     ...PAL.map((p) => p[0])]),
  headlines: new Set(['caixinha', 'noticia', '', 'outline', 'texto', 'card', 'realce', 'misto',
                      'bloco', 'etiqueta', 'manuscrito', 'gigante',
                      'relevo', 'grifo', 'contorno_duplo', 'tarjas', 'vidro',
                      ...CARTELAS.map((c) => c[0])]),
  // os três de `EDIT_ELEMENTS` entram aqui porque o radio de FORMATO os
  // oferece junto com limpa/split/split2 (ver `radios()`) — e os três têm
  // caminho de render de verdade no compositor (`questionBox`,
  // `brollOverlays[]`, `hook.style="noticia"`).
  edits: new Set(['limpa', 'split', 'split2', 'caixinha', 'brollOverlay', 'noticia',
                  'animTexto', 'anim3d', 'explicativo', 'ilustrado', 'fundoTrocado', 'caderno']),
};

/* FORMATO É UMA ESCOLHA SÓ, e ela mora em dois lugares no dado.
 *
 * `limpa`/`split`/`split2` viajam em `S.style.edit` (→ `editStyle`); Caixinha,
 * Broll Overlay e Notícia viajam em `S.style.elements` (→ `questionBox`,
 * `brollOverlays[]`, `hook.style`). São contratos DIFERENTES com o compositor,
 * e é por isso que o dado continua separado — mas na TELA os seis são o mesmo
 * radio: o usuário escolhe um formato, não uma combinação.
 *
 * Escolher um destes três zera os outros dois E devolve `edit` a `limpa` (ver
 * o handler de clique): sem isso, `editStyle: "split"` + `questionBox` sairiam
 * os dois no render, que é exatamente a combinação que o radio nega. */
/* ANIMAÇÃO EM TEXTO / EM 3D (2026-10-12) entram pelo mesmo caminho: são o
 * vídeo INTEIRO num estilo, então um formato, não um extra. O render delas é
 * sob medida (gráficos em `compositions/`, montados a partir da especificação
 * em `assets/estilos-animacao/<id>/ESTILO.md`) — o `phase2.py` recusa pelo
 * nome até o agente montar as cenas, nunca substitui por algo parecido. A 3D
 * instala MediaPipe + Depth Anything sozinha na primeira vez
 * (`helpers/instalar_anim3d.py`). */
/* MOLDURA EXPLICATIVA (2026-10-13): o apresentador muda de formato quando a
 * fala pede — grande quando não há o que explicar; PIP, tela dividida ou
 * quadrado quando cita lista, exemplo ou comparação. Roteiro de cenas escrito
 * pela IA lendo a fala (`helpers/explicativo.py`); o `phase2.py` recusa pelo
 * nome enquanto ele não existir. */
/* ILUSTRADO, FUNDO TROCADO e CADERNO (2026-10-15, motor de efeitos —
 * helpers/efeitos.py): os três são formato porque decidem quais efeitos
 * AUTOMÁTICOS podem entrar (`variants.json → efeitos.formatos`). "Nenhum" não
 * prevê efeito nenhum; o Ilustrado é o quadro cheio com todos eles. */
const EDIT_ELEMENTS = ['brollOverlay', 'animTexto', 'anim3d', 'explicativo',
                       'ilustrado', 'fundoTrocado', 'caderno'];
/* CAIXINHA e NOTÍCIA moram na camada HEADLINE (pedido do usuário, 2026-10-14),
 * como as DUAS PRIMEIRAS opções do radio: as duas ocupam a mesma zona alta da
 * headline, então são uma escolha de headline, não de formato. O dado não
 * mudou — continuam em `elements` (→ `questionBox`, `hook.style="noticia"`) —,
 * só a tela: escolher uma zera `headline`, e escolher uma headline as desliga. */
const HEADLINE_ELEMENTS = ['caixinha', 'noticia'];

// Quadro de foco de câmera — substitui o "boneco" genérico (círculo+blob) nos
// mocks de tipo de edição por um vocabulário de editor: cantos em L, ponto de
// gravação, três traços de timecode. Proposta em ~/.avelin/propostas/camadas-render-4areas.html.
function viewfinder(cx, cy, s) {
  const h = s / 2;
  const bx = cx - h, by = cy - h;
  const L = 6;
  return `
    <rect x="${bx}" y="${by}" width="${s}" height="${s}" rx="6" fill="rgba(255,255,255,.04)" stroke="rgba(255,255,255,.22)" stroke-width="1.1"/>
    <path d="M${bx} ${by + L}v-${L - 2}a2 2 0 012-2h${L - 2}" fill="none" stroke="rgba(255,255,255,.55)" stroke-width="1.4" stroke-linecap="round"/>
    <path d="M${bx + s - L} ${by}h${L - 2}a2 2 0 012 2v${L - 2}" fill="none" stroke="rgba(255,255,255,.55)" stroke-width="1.4" stroke-linecap="round"/>
    <path d="M${bx + s} ${by + s - L}v${L - 2}a2 2 0 01-2 2h-${L - 2}" fill="none" stroke="rgba(255,255,255,.55)" stroke-width="1.4" stroke-linecap="round"/>
    <path d="M${bx + L} ${by + s}h-${L - 2}a2 2 0 01-2-2v-${L - 2}" fill="none" stroke="rgba(255,255,255,.55)" stroke-width="1.4" stroke-linecap="round"/>
    <circle cx="${bx + s - 6}" cy="${by + 6}" r="2.6" fill="rgb(var(--orange-rgb) / .85)"/>
    <rect x="${cx - 9}" y="${by + s + 6}" width="6" height="3" rx="1" fill="rgba(255,255,255,.4)"/>
    <rect x="${cx - 1}" y="${by + s + 6}" width="6" height="3" rx="1" fill="rgba(255,255,255,.4)"/>
    <rect x="${cx + 7}" y="${by + s + 6}" width="6" height="3" rx="1" fill="rgb(var(--orange-rgb) / .7)"/>`;
}

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
        <rect x="14" y="14" width="38" height="4.4" rx="2.2" fill="rgba(255,255,255,.5)"/>
        <rect x="20" y="21.5" width="26" height="4.4" rx="2.2" fill="rgba(255,255,255,.3)"/>
        ${viewfinder(33, 44, 24)}
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
        ${viewfinder(33, 64, 20)}
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
        ${viewfinder(33, 30, 18)}
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
    // Caixinha e Broll Overlay NÃO moram mais aqui — viraram elementos
    // independentes em STYLE_CATALOG.elements. Como "tipo de edição" era um
    // radio ÚNICO, escolher Caixinha excluía Broll Overlay e vice-versa, sem
    // nenhum motivo técnico: o compositor já os monta como dados
    // independentes (`questionBox`, `brollOverlays[]`). Ver elLocked().
  ],
  // No names on purpose: the sample headline IS the label. Ids and geometry
  // mirror HL_STYLES in the template's Main.tsx — keep the two in step.
  headlines: [
    {id: 'outline', name: 'Contorno', hl: 'outline'},
    {id: 'texto', name: 'Texto simples', hl: 'texto'},
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
    {id: 'tarjas', name: 'Tarjas', hl: 'tarjas'},
    // VIDRO — Glass Type da referência de efeitos (2026-10-15): cartão fosco
    {id: 'vidro', name: 'Vidro', hl: 'vidro'},
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
      def: false, // desmarcado por padrão — pedido do usuário, 2026-10-15
      icon: '<svg viewBox="0 0 16 16"><rect x="1.2" y="3.4" width="6" height="9.2" rx="1.6" fill="none" stroke="currentColor" stroke-width="1.4"/><rect x="9.6" y="1.9" width="5.2" height="12.2" rx="1.6" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M8.4 8h.7" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>',
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
    /* CAIXINHA, BROLL OVERLAY e NOTÍCIA — três elementos de tela, sem campo de
     * texto/cor/fonte aqui de propósito. Ligar um sem conteúdo é o sinal para
     * o agente perguntar via AskUserQuestion na conversa (o mesmo protocolo
     * que o Broll Overlay já seguia: "o conteúdo não vem de catálogo, nasce
     * de uma conversa") — não um formulário na tela. Ver check_supported()
     * gêmeo em phase2.py. */
    {
      id: 'caixinha',
      name: 'Caixinha de perguntas',
      def: false,
      icon: '<svg viewBox="0 0 16 16"><path d="M2 3.6A1.6 1.6 0 013.6 2h8.8A1.6 1.6 0 0114 3.6v5.8a1.6 1.6 0 01-1.6 1.6H8l-3 2.6v-2.6H3.6A1.6 1.6 0 012 9.4V3.6z" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><rect x="4.2" y="4.6" width="7.6" height="1.4" rx=".7"/><rect x="4.2" y="7.2" width="5" height="1.4" rx=".7"/></svg>',
      // O mock imita o ADESIVO DE VERDADE (fidelidade com o app, não com a
      // marca — ver caixinha.css): faixa escura no topo, corpo branco embaixo,
      // cantos largos, sem inclinação. As cores são as MESMAS fixas do
      // render, não um placeholder — mudar o CSS real muda este mock junto
      // só se alguém lembrar de atualizar os dois; os dois vivem lidos lado a
      // lado na mesma aba, então uma prévia que mentisse sobre a forma seria
      // pior que nenhuma.
      mock: `<svg viewBox="0 0 66 118" xmlns="http://www.w3.org/2000/svg">
        <rect x=".5" y=".5" width="65" height="117" rx="7" fill="var(--bg1)" stroke="rgba(255,255,255,.12)"/>
        <rect x="3" y="3" width="60" height="112" rx="5" fill="rgba(255,255,255,.05)"/>
        <circle cx="33" cy="76" r="12" fill="rgba(255,255,255,.12)"/>
        <path d="M18 112a15 15 0 0130 0z" fill="rgba(255,255,255,.12)"/>
        <rect x="9" y="16" width="48" height="27" rx="6" fill="#fff" opacity=".92"/>
        <rect x="9" y="16" width="48" height="11" rx="6" fill="#20252b"/>
        <rect x="9" y="22" width="48" height="5" fill="#20252b"/>
        <rect x="14" y="19.7" width="21" height="3" rx="1.5" fill="#fff" opacity=".85"/>
        <rect x="14" y="33" width="34" height="3" rx="1.5" fill="#20252b" opacity=".55"/>
        <rect x="14" y="38" width="24" height="3" rx="1.5" fill="#20252b" opacity=".32"/>
      </svg>`,
    },
    {
      id: 'brollOverlay',
      /* O NOME É DO ELEMENTO, não do dado que ele preenche em Fase 1
       * (`brollGraphics[]`/`inserts[]`) — esta é a ênfase COSMÉTICA sobre o
       * a-roll já cortado (`brollOverlays[]`), decidida numa conversa sobre o
       * transcrito aprovado, nunca no meio do corte. */
      name: 'Broll Overlay',
      def: false,
      icon: '<svg viewBox="0 0 16 16"><rect x="1.2" y="2.2" width="13.6" height="9.6" rx="1.8" fill="none" stroke="currentColor" stroke-width="1.4"/><rect x="8.6" y="7.2" width="6.2" height="6.6" rx="1.4" fill="var(--bg1)" stroke="currentColor" stroke-width="1.4"/></svg>',
      // O formato tem quatro tipos (`words`/`stat`/`labels`/`media`) e três
      // posições — nenhum mock cabe todos. Este mostra o mais comum: uma
      // faixa escurecida (o `dim`, NUNCA opacity no vídeo — ver
      // brollOverlay_markup) por cima do a-roll, com a palavra de destaque
      // (`bo-w.acc`) na cor de acento, e os anéis do cenário "hero" ao fundo.
      mock: `<svg viewBox="0 0 66 118" xmlns="http://www.w3.org/2000/svg">
        <rect x=".5" y=".5" width="65" height="117" rx="7" fill="var(--bg1)" stroke="rgba(255,255,255,.12)"/>
        <rect x="3" y="3" width="60" height="112" rx="5" fill="rgba(255,255,255,.05)"/>
        <circle cx="46" cy="26" r="13" fill="none" stroke="rgba(255,255,255,.16)" stroke-width="1.3"/>
        <circle cx="46" cy="26" r="19" fill="none" stroke="rgba(255,255,255,.09)" stroke-width="1.1"/>
        <rect x="3" y="80" width="60" height="35" rx="5" fill="rgba(0,0,0,.42)"/>
        <rect x="11" y="88" width="19" height="4.2" rx="2.1" fill="rgba(255,255,255,.55)"/>
        <rect x="32" y="88" width="15" height="4.2" rx="2.1" fill="rgb(var(--orange-rgb) / .9)"/>
        <rect x="11" y="95.5" width="28" height="4.2" rx="2.1" fill="rgba(255,255,255,.55)"/>
      </svg>`,
    },
    {
      /* NOTÍCIA — cartela banda (motor `cartela`) que virou elemento por
       * disputar a mesma zona alta que a Caixinha, sem nenhuma arbitragem
       * antes disto. Ligá-la zera o Headline (e vice-versa) em
       * limpaConflitoZonaAlta(): as duas usam o MESMO `hook.style`. */
      id: 'noticia',
      name: 'Notícia',
      def: false,
      icon: '<svg viewBox="0 0 16 16"><rect x="1.4" y="3" width="13.2" height="10" rx="1.4" fill="none" stroke="currentColor" stroke-width="1.4"/><rect x="3.2" y="4.8" width="4.4" height="3.4" rx=".5" fill="none" stroke="currentColor" stroke-width="1.2"/><rect x="8.6" y="4.9" width="4.6" height="1.2" rx=".6"/><rect x="8.6" y="7" width="4.6" height="1.2" rx=".6"/><rect x="3.2" y="9.6" width="10" height="1.2" rx=".6"/></svg>',
      // Espelha `paint` do variants.json (`lines: papelEscuro, barra: accent,
      // olho: sobreAccent`): cartão claro, barra lateral na cor de acento, o
      // rótulo (olho) sentado SOBRE a barra em contraste, manchete escura
      // preenchendo a largura (`quebra: "encher"`).
      mock: `<svg viewBox="0 0 66 118" xmlns="http://www.w3.org/2000/svg">
        <rect x=".5" y=".5" width="65" height="117" rx="7" fill="var(--bg1)" stroke="rgba(255,255,255,.12)"/>
        <rect x="3" y="3" width="60" height="112" rx="5" fill="rgba(255,255,255,.05)"/>
        <circle cx="33" cy="80" r="12" fill="rgba(255,255,255,.12)"/>
        <path d="M18 114a15 15 0 0130 0z" fill="rgba(255,255,255,.12)"/>
        <rect x="7" y="17" width="52" height="34" rx="4" fill="#eee7d8" opacity=".95"/>
        <rect x="7" y="17" width="5" height="34" rx="2" fill="rgb(var(--orange-rgb) / .9)"/>
        <rect x="18" y="21.5" width="19" height="6" rx="3" fill="rgb(var(--orange-rgb) / .9)"/>
        <rect x="21" y="23.6" width="13" height="1.8" rx=".9" fill="#fff" opacity=".92"/>
        <rect x="18" y="33" width="36" height="4.6" rx="1" fill="#241f18" opacity=".82"/>
        <rect x="18" y="40" width="28" height="4.6" rx="1" fill="#241f18" opacity=".82"/>
      </svg>`,
    },
    {
      /* ANIMAÇÃO EM TEXTO — tipografia cinética sobre tela escura: o texto da
       * fala nasce palavra a palavra no tempo da voz. Spec:
       * assets/estilos-animacao/text-anim/ESTILO.md. */
      id: 'animTexto',
      name: 'Animação em Texto',
      def: false,
      icon: '<svg viewBox="0 0 16 16"><path d="M2.5 3.5h11M8 3.5v9" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/><path d="M11.5 10.5h3" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" opacity=".6"/></svg>',
      mock: `<svg viewBox="0 0 66 118" xmlns="http://www.w3.org/2000/svg">
        <rect x=".5" y=".5" width="65" height="117" rx="7" fill="#0b0b0b" stroke="rgba(255,255,255,.12)"/>
        <g stroke="rgba(255,255,255,.06)" stroke-width=".6">
          <path d="M3 20h60M3 37h60M3 54h60M3 71h60M3 88h60M3 105h60M14 3v112M30 3v112M46 3v112"/>
        </g>
        <rect x="9" y="40" width="22" height="3.2" rx="1.6" fill="rgba(255,255,255,.7)"/>
        <rect x="9" y="47" width="46" height="9" rx="1.5" fill="#fff" opacity=".92"/>
        <rect x="9" y="59" width="38" height="9" rx="1.5" fill="rgb(var(--orange-rgb) / .95)"/>
        <rect x="49" y="59" width="1.6" height="9" fill="rgb(var(--orange-rgb))"/>
        <rect x="9" y="76" width="14" height="6" rx="1" fill="none" stroke="rgba(255,255,255,.35)" stroke-width=".8"/>
        <path d="M23 79h12" stroke="rgb(var(--orange-rgb) / .8)" stroke-width=".8"/>
        <rect x="35" y="76" width="14" height="6" rx="1" fill="none" stroke="rgba(255,255,255,.35)" stroke-width=".8"/>
      </svg>`,
    },
    {
      /* ANIMAÇÃO EM 3D — a fala vira efeito: profundidade, recorte, painel 3D,
       * rastreio de mãos e objetos que reagem à palavra. Spec:
       * assets/estilos-animacao/edit-3d/ESTILO.md. Instala MediaPipe + Depth
       * Anything na primeira escolha (phase2.py → instalar_anim3d.py). */
      id: 'anim3d',
      name: 'Animação em 3D',
      def: false,
      icon: '<svg viewBox="0 0 16 16"><path d="M8 1.8l5.4 3.1v6.2L8 14.2 2.6 11.1V4.9z" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><path d="M2.6 4.9L8 8l5.4-3.1M8 8v6.2" fill="none" stroke="currentColor" stroke-width="1.2" opacity=".7"/></svg>',
      mock: `<svg viewBox="0 0 66 118" xmlns="http://www.w3.org/2000/svg">
        <rect x=".5" y=".5" width="65" height="117" rx="7" fill="var(--bg1)" stroke="rgba(255,255,255,.12)"/>
        <g stroke="rgba(255,255,255,.1)" stroke-width=".6">
          <path d="M3 96l60 0M3 104h60M3 112h60M18 92l-10 23M33 92v23M48 92l10 23"/>
        </g>
        <path d="M14 22l34-6v66l-34-6z" fill="rgba(255,255,255,.06)" stroke="rgba(255,255,255,.28)" stroke-width=".9"/>
        <circle cx="31" cy="44" r="8" fill="rgba(255,255,255,.16)"/>
        <path d="M19 76a12 12 0 0124 0" fill="rgba(255,255,255,.16)"/>
        <path d="M31 36c-6 0-9 4-9 8s3 8 9 8 9-4 9-8-3-8-9-8z" fill="none" stroke="rgb(var(--orange-rgb) / .9)" stroke-width="1"/>
        <rect x="6" y="6" width="22" height="5" rx="2.5" fill="rgba(0,0,0,.5)" stroke="rgba(255,255,255,.2)" stroke-width=".5"/>
        <circle cx="9.5" cy="8.5" r="1.2" fill="rgb(var(--orange-rgb))"/>
        <path d="M49 54l6-3.4 6 3.4v6.8l-6 3.4-6-3.4z" fill="rgb(var(--orange-rgb) / .35)" stroke="rgb(var(--orange-rgb))" stroke-width=".9"/>
      </svg>`,
    },
    {
      /* MOLDURA EXPLICATIVA — mock: o PIP circular no canto e a lista que a
       * fala está citando, um item aceso. */
      id: 'explicativo',
      name: 'Moldura explicativa',
      def: false,
      icon: '<svg viewBox="0 0 16 16"><circle cx="11.5" cy="4.5" r="2.8" fill="none" stroke="currentColor" stroke-width="1.4"/><rect x="2" y="9" width="12" height="2" rx="1"/><rect x="2" y="12.6" width="8" height="2" rx="1" opacity=".6"/></svg>',
      mock: `<svg viewBox="0 0 66 118" xmlns="http://www.w3.org/2000/svg">
        <rect x=".5" y=".5" width="65" height="117" rx="7" fill="#120b08" stroke="rgba(255,255,255,.12)"/>
        <circle cx="47" cy="25" r="13.5" fill="url(#expg)"/>
        <defs><linearGradient id="expg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stop-color="#FB7C62"/><stop offset="1" stop-color="#F0BE48"/></linearGradient></defs>
        <circle cx="47" cy="25" r="12" fill="#2a2522"/>
        <circle cx="47" cy="22" r="4.2" fill="rgba(255,255,255,.22)"/>
        <path d="M39 33a8 8 0 0116 0z" fill="rgba(255,255,255,.22)"/>
        <rect x="7" y="50" width="16" height="4.5" rx="2.2" fill="rgb(var(--orange-rgb))"/>
        <rect x="7" y="58" width="52" height="10" rx="2.5" fill="rgba(255,255,255,.08)" stroke="rgba(255,255,255,.14)" stroke-width=".5"/>
        <rect x="9" y="60" width="6" height="6" rx="1.5" fill="rgb(var(--orange-rgb))"/>
        <rect x="18" y="61.8" width="22" height="2.4" rx="1.2" fill="rgba(255,255,255,.85)"/>
        <rect x="7" y="71" width="52" height="10" rx="2.5" fill="rgba(255,255,255,.08)" stroke="rgba(255,255,255,.14)" stroke-width=".5"/>
        <rect x="9" y="73" width="6" height="6" rx="1.5" fill="rgb(var(--orange-rgb))"/>
        <rect x="18" y="74.8" width="28" height="2.4" rx="1.2" fill="rgba(255,255,255,.85)"/>
        <rect x="7" y="84" width="52" height="10" rx="2.5" fill="rgba(255,255,255,.04)" stroke="rgba(255,255,255,.08)" stroke-width=".5"/>
        <rect x="18" y="87.8" width="18" height="2.4" rx="1.2" fill="rgba(255,255,255,.3)"/>
      </svg>`,
    },
    /* ---------- MOTOR DE EFEITOS (2026-10-15, helpers/efeitos.py) ----------
     * Formatos que prevêem efeitos automáticos, e os efeitos em si. Os chips
     * de efeito (`efx: true`) só valem quando o FORMATO prevê o efeito — fora
     * dele aparecem travados com o motivo (elLocked), e a escolha do usuário
     * fica guardada para quando ele trocar de formato. */
    {
      id: 'ilustrado',
      name: 'Ilustrado',
      def: false,
      icon: '<svg viewBox="0 0 16 16"><rect x="1.4" y="2" width="13.2" height="12" rx="2" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M4 9l1.4 1.4L8 7.6" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/><rect x="10" y="7" width="1.6" height="4.4" rx=".6"/><rect x="12.2" y="5" width="1.4" height="6.4" rx=".6"/></svg>',
      mock: `<svg viewBox="0 0 66 118" xmlns="http://www.w3.org/2000/svg">
        <rect x=".5" y=".5" width="65" height="117" rx="7" fill="var(--bg1)" stroke="rgba(255,255,255,.12)"/>
        <rect x="3" y="3" width="60" height="112" rx="5" fill="rgba(255,255,255,.05)"/>
        <circle cx="33" cy="34" r="12" fill="rgba(255,255,255,.14)"/>
        <path d="M14 76a19 19 0 0138 0z" fill="rgba(255,255,255,.14)"/>
        <rect x="9" y="56" width="48" height="34" rx="5" fill="rgba(10,10,12,.8)" stroke="rgba(255,255,255,.18)" stroke-width=".6"/>
        <circle cx="15" cy="64" r="2.6" fill="rgb(var(--orange-rgb))"/>
        <rect x="20" y="62.8" width="20" height="2.4" rx="1.2" fill="rgba(255,255,255,.85)"/>
        <circle cx="15" cy="73" r="2.6" fill="rgb(var(--orange-rgb))"/>
        <rect x="20" y="71.8" width="16" height="2.4" rx="1.2" fill="rgba(255,255,255,.85)"/>
        <circle cx="15" cy="82" r="2.6" fill="none" stroke="rgba(255,255,255,.4)" stroke-width=".8"/>
        <rect x="20" y="80.8" width="22" height="2.4" rx="1.2" fill="rgba(255,255,255,.4)"/>
        <rect x="46" y="76" width="3.4" height="9" rx="1" fill="rgba(255,255,255,.35)"/>
        <rect x="51" y="70" width="3.4" height="15" rx="1" fill="rgb(var(--orange-rgb))"/>
      </svg>`,
    },
    {
      id: 'fundoTrocado',
      name: 'Fundo trocado',
      def: false,
      icon: '<svg viewBox="0 0 16 16"><rect x="1.4" y="2" width="13.2" height="12" rx="2" fill="none" stroke="currentColor" stroke-width="1.4"/><circle cx="8" cy="7" r="2.2"/><path d="M4 14a4 4 0 018 0"/></svg>',
      mock: `<svg viewBox="0 0 66 118" xmlns="http://www.w3.org/2000/svg">
        <defs><linearGradient id="ftg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="rgb(var(--orange-rgb))" stop-opacity=".55"/><stop offset="1" stop-color="#1b2a44"/></linearGradient></defs>
        <rect x=".5" y=".5" width="65" height="117" rx="7" fill="url(#ftg)" stroke="rgba(255,255,255,.12)"/>
        <path d="M3 84l14-16 10 9 14-18 22 25v31H3z" fill="rgba(0,0,0,.28)"/>
        <circle cx="33" cy="54" r="13" fill="#d9d4cf"/>
        <path d="M11 115a22 22 0 0144 0z" fill="#d9d4cf"/>
      </svg>`,
    },
    {
      id: 'caderno',
      name: 'Caderno',
      def: false,
      icon: '<svg viewBox="0 0 16 16"><rect x="2" y="1.6" width="12" height="12.8" rx="1.6" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M4.6 5.4c2-1.4 4.6 1.4 6.8 0M4.6 8.6c2-1.4 4.6 1.4 6.8 0" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>',
      mock: `<svg viewBox="0 0 66 118" xmlns="http://www.w3.org/2000/svg">
        <rect x=".5" y=".5" width="65" height="117" rx="7" fill="#efeadf" stroke="rgba(255,255,255,.12)"/>
        <g stroke="rgba(80,110,160,.25)" stroke-width=".5"><path d="M3 20h60M3 30h60M3 40h60M3 50h60M3 60h60M3 70h60M3 80h60M3 90h60M3 100h60M3 110h60"/></g>
        <path d="M10 18c8-6 14 6 22 0s14 6 24 0M12 26c8-6 14 6 22 0" fill="none" stroke="#8a9ad8" stroke-width="2.4" stroke-linecap="round" opacity=".8"/>
        <circle cx="33" cy="56" r="13" fill="#4a3f3a" stroke="#fff" stroke-width="2.6"/>
        <path d="M11 115a22 22 0 0144 0z" fill="#2b2b2b" stroke="#fff" stroke-width="2.6"/>
        <path d="M48 40l3 3m0-3l-3 3" stroke="#d84a3a" stroke-width="1.2"/>
        <rect x="44" y="64" width="16" height="8" rx="1" fill="#f3d84b" opacity=".85" transform="rotate(-8 52 68)"/>
      </svg>`,
    },
    {
      id: 'checklist', efx: true, name: 'Checklist', def: true,
      icon: '<svg viewBox="0 0 16 16"><path d="M2 4.2l1.3 1.3L5.6 3M2 10.2l1.3 1.3 2.3-2.5" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/><rect x="7.4" y="3.6" width="7" height="1.6" rx=".8"/><rect x="7.4" y="9.6" width="5.4" height="1.6" rx=".8"/></svg>',
    },
    {
      id: 'chartGrow', efx: true, name: 'Gráfico crescendo', def: true,
      icon: '<svg viewBox="0 0 16 16"><rect x="1.6" y="9" width="2.6" height="5" rx=".7"/><rect x="5.4" y="6.4" width="2.6" height="7.6" rx=".7"/><rect x="9.2" y="3.8" width="2.6" height="10.2" rx=".7"/><path d="M12.6 2.2h2v2" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>',
    },
    {
      id: 'conta', efx: true, name: 'Cálculo na tela', def: true,
      icon: '<svg viewBox="0 0 16 16"><rect x="2" y="1.6" width="12" height="12.8" rx="2" fill="none" stroke="currentColor" stroke-width="1.4"/><rect x="4.4" y="4" width="7.2" height="2" rx=".6"/><path d="M5 9.4h2.4M6.2 8.2v2.4M9 9.4h2.4M9 11.6h2.4" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>',
    },
    {
      id: 'versus', efx: true, name: 'A vs B', def: true,
      icon: '<svg viewBox="0 0 16 16"><rect x="1.4" y="3" width="5.6" height="8" rx="1.4"/><rect x="9" y="3" width="5.6" height="8" rx="1.4" opacity=".6"/><rect x="3" y="12.6" width="10" height="1.6" rx=".8"/></svg>',
    },
    {
      id: 'phoneMockup', efx: true, name: 'Celular na tela', def: true,
      icon: '<svg viewBox="0 0 16 16"><rect x="4" y="1.2" width="8" height="13.6" rx="2" fill="none" stroke="currentColor" stroke-width="1.4"/><rect x="6.4" y="2.6" width="3.2" height="1" rx=".5"/><rect x="5.6" y="6" width="4.8" height="2" rx=".6" opacity=".7"/></svg>',
    },
    {
      id: 'uiWorld', efx: true, name: 'Mundo de interface', def: true,
      icon: '<svg viewBox="0 0 16 16"><rect x="1.2" y="2" width="6" height="3.4" rx="1.2"/><rect x="8.8" y="6.2" width="6" height="3.4" rx="1.7" opacity=".7"/><path d="M3.2 9.4l3.6 1.6-1.5.6-.6 1.5z"/><rect x="2" y="12.6" width="7" height="1.6" rx=".8" opacity=".6"/></svg>',
    },
    {
      id: 'zoomPunch', efx: true, name: 'Zoom digital na frase de efeito', def: true,
      icon: '<svg viewBox="0 0 16 16"><path d="M1.6 5V2.4a.8.8 0 01.8-.8H5M11 1.6h2.6a.8.8 0 01.8.8V5M14.4 11v2.6a.8.8 0 01-.8.8H11M5 14.4H2.4a.8.8 0 01-.8-.8V11" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/><rect x="5" y="5" width="6" height="6" rx="1.4"/></svg>',
    },
    {
      id: 'zoomThrough', efx: true, name: 'Zoom através do corte', def: false, // idem zoomCuts
      icon: '<svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="2" /><circle cx="8" cy="8" r="4.6" fill="none" stroke="currentColor" stroke-width="1.2" opacity=".7"/><circle cx="8" cy="8" r="7" fill="none" stroke="currentColor" stroke-width="1" opacity=".4"/></svg>',
    },
  ],
  /* EFEITO DO GANCHO — escolha explícita, um por vídeo, nos primeiros
   * segundos (`edit-data.json → ganchoEfeito`). Combina com o layout da
   * headline acima; a Capa de revista desenha o texto do gancho ela mesma. */
  ganchoFx: [
    { id: '', name: 'Nenhum',
      mock: `<svg viewBox="0 0 66 118" xmlns="http://www.w3.org/2000/svg">
        <rect x=".5" y=".5" width="65" height="117" rx="7" fill="var(--bg1)" stroke="rgba(255,255,255,.12)"/>
        <circle cx="33" cy="52" r="13" fill="rgba(255,255,255,.16)"/>
        <path d="M12 115a21 21 0 0142 0z" fill="rgba(255,255,255,.16)"/>
        <path d="M17 14.5L49 30" stroke="rgba(255,255,255,.34)" stroke-width="1.6" stroke-linecap="round"/>
      </svg>` },
    { id: 'frameBreak', name: 'Quebra de moldura',
      mock: `<svg viewBox="0 0 66 118" xmlns="http://www.w3.org/2000/svg">
        <rect x=".5" y=".5" width="65" height="117" rx="7" fill="#15110f" stroke="rgba(255,255,255,.12)"/>
        <rect x="10" y="40" width="46" height="66" rx="6" fill="rgba(255,255,255,.08)" stroke="rgba(255,255,255,.5)" stroke-width="1.2" transform="rotate(-3 33 73)"/>
        <circle cx="33" cy="40" r="12" fill="#d9d4cf"/>
        <path d="M14 106a19 19 0 0138 0z" fill="#d9d4cf"/>
        <path d="M45 62l12-10" stroke="#d9d4cf" stroke-width="5" stroke-linecap="round"/>
      </svg>` },
    { id: 'coverStory', name: 'Capa de revista',
      mock: `<svg viewBox="0 0 66 118" xmlns="http://www.w3.org/2000/svg">
        <rect x=".5" y=".5" width="65" height="117" rx="7" fill="#2a2a2e" stroke="rgba(255,255,255,.12)"/>
        <text x="33" y="30" text-anchor="middle" font-family="Georgia,serif" font-weight="700" font-size="17" fill="rgb(var(--orange-rgb))">CAPA</text>
        <circle cx="33" cy="42" r="13" fill="#d9d4cf"/>
        <path d="M11 115a22 22 0 0144 0z" fill="#d9d4cf"/>
        <rect x="6" y="70" width="16" height="2.4" rx="1" fill="#fff"/><rect x="6" y="75" width="12" height="2.4" rx="1" fill="#fff" opacity=".7"/>
        <rect x="46" y="100" width="12" height="9" fill="#fff"/>
      </svg>` },
    { id: 'headlineWall', name: 'Parede de manchetes',
      mock: `<svg viewBox="0 0 66 118" xmlns="http://www.w3.org/2000/svg">
        <rect x=".5" y=".5" width="65" height="117" rx="7" fill="var(--bg1)" stroke="rgba(255,255,255,.12)"/>
        <rect x="5" y="10" width="22" height="13" rx="1" fill="#f2efe8" transform="rotate(-6 16 16)"/>
        <rect x="38" y="8" width="22" height="15" rx="1" fill="#f2efe8" transform="rotate(5 49 15)"/>
        <rect x="6" y="32" width="18" height="12" rx="1" fill="#1d1d1f" stroke="rgba(255,255,255,.3)" stroke-width=".5" transform="rotate(4 15 38)"/>
        <rect x="42" y="30" width="18" height="12" rx="1" fill="#f2efe8" transform="rotate(-5 51 36)"/>
        <circle cx="33" cy="54" r="13" fill="#d9d4cf"/>
        <path d="M11 115a22 22 0 0144 0z" fill="#d9d4cf"/>
      </svg>` },
    { id: 'couchWall', name: 'Parede de vídeos',
      mock: `<svg viewBox="0 0 66 118" xmlns="http://www.w3.org/2000/svg">
        <rect x=".5" y=".5" width="65" height="117" rx="7" fill="var(--bg1)" stroke="rgba(255,255,255,.12)"/>
        <g fill="rgba(255,255,255,.22)"><rect x="5" y="7" width="12" height="20" rx="2"/><rect x="19" y="7" width="12" height="20" rx="2"/><rect x="35" y="7" width="12" height="20" rx="2"/><rect x="49" y="7" width="12" height="20" rx="2"/>
        <rect x="5" y="30" width="12" height="20" rx="2"/><rect x="49" y="30" width="12" height="20" rx="2"/></g>
        <circle cx="33" cy="54" r="13" fill="#d9d4cf"/>
        <path d="M11 115a22 22 0 0144 0z" fill="#d9d4cf"/>
      </svg>` },
    { id: 'orbit', name: 'Órbita',
      mock: `<svg viewBox="0 0 66 118" xmlns="http://www.w3.org/2000/svg">
        <rect x=".5" y=".5" width="65" height="117" rx="7" fill="var(--bg1)" stroke="rgba(255,255,255,.12)"/>
        <ellipse cx="33" cy="56" rx="27" ry="9" fill="none" stroke="rgba(255,255,255,.25)" stroke-dasharray="2 2"/>
        <circle cx="33" cy="54" r="13" fill="#d9d4cf"/>
        <path d="M11 115a22 22 0 0144 0z" fill="#d9d4cf"/>
        <rect x="2" y="50" width="11" height="15" rx="2" fill="rgb(var(--orange-rgb))"/>
        <rect x="52" y="44" width="11" height="15" rx="2" fill="rgba(255,255,255,.7)"/>
      </svg>` },
    { id: 'vertigo', name: 'Vertigo',
      mock: `<svg viewBox="0 0 66 118" xmlns="http://www.w3.org/2000/svg">
        <rect x=".5" y=".5" width="65" height="117" rx="7" fill="var(--bg1)" stroke="rgba(255,255,255,.12)"/>
        <g fill="none" stroke="rgba(255,255,255,.18)"><rect x="6" y="10" width="54" height="98"/><rect x="14" y="24" width="38" height="70"/><rect x="22" y="38" width="22" height="42"/></g>
        <path d="M6 10l16 28M60 10L44 38M6 108l16-28M60 108L44 80" stroke="rgba(255,255,255,.18)"/>
        <circle cx="33" cy="54" r="12" fill="#d9d4cf"/>
        <path d="M13 115a20 20 0 0140 0z" fill="#d9d4cf"/>
      </svg>` },
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

/* Onde a deixa deste estilo senta, em px de referência — o mesmo número que o
   compositor lê (`bottom` do estilo, ou o global). */
function capOffset(id, def) {
  const st = ((VARS || {}).styles || {})[id] || {};
  return st.offsetY != null ? st.offsetY : def;
}

function capBottom(id) {
  const v = VARS || {};
  const st = (v.styles || {})[id] || {};
  return st.bottom || v.bottom || 430;
}

// Karaoke: lines of ≤3 words (captions.maxWords), Poppins 900 white, each word
// rises 34px and fades in over 7 frames; the line is replaced by the next one.
function buildKaraokeDemo(host, ctx) {
  const s = host.clientWidth / projW(ctx);
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
function buildStackedDemo(host, ctx) {
  const s = host.clientWidth / projW(ctx);
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
  ((VARS && VARS.headlines) || {})[id] || HL_FALLBACK[id] || HL_FALLBACK.card;

// Mesmo padrão de `hlStyle`, para a legenda — espelha a busca já usada em
// `renderLive` (linha ~3138). Faltava ESTE helper: `sendStyle()` chamava uma
// função `capVariant()` que nunca existiu, e quebrava com `ReferenceError`
// ANTES do `fetch('/api/save')` — o clique em "Enviar e renderizar" morria
// ali, sem POST nenhum sair e sem toast nenhum avisar. Sem `.family`: o campo
// do variant é `.cssFamily` (ver `vestirPal`/`renderLive`), não `.family`.
const capVariant = (id) => ((VARS && VARS.styles) || {})[id] || {};

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
const gfonts = () => (VARS && VARS.gfonts) || GFONTS_FALLBACK;

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
async function carregarFontesLocais(url) {
  try {
    const d = await (await fetch(url || '/api/localfonts')).json();
    LOCAL_FONTS = Array.isArray(d.families) ? d.families : [];
  } catch (e) { LOCAL_FONTS = []; }
  return LOCAL_FONTS;
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
    `@font-face{font-family:'${f.n}';src:url('${amb.base}fonts/${f.file}');`
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
// Espelho de `hl_hero_index`/`hl_ks` do compositor: nos layouts `heroMid` a
// herói é a linha do MEIO (n//2), escolhida por índice e não por `sizes`.
function hlHeroIndex(lines, S) {
  const i = S.heroIndex;
  return (i != null && i >= 0 && i < lines.length) ? i : Math.floor(lines.length / 2);
}

function hlKs(lines, S) {
  if (S.heroMid) {
    const hero = hlHeroIndex(lines, S);
    return lines.map((_, i) => (i === hero ? 1 : (S.minorK == null ? 0.6 : S.minorK)));
  }
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

/* Monta uma headline REAL — a mesma marcação e as mesmas classes que o
 * compositor emite, com o mesmo `headline.css`. É o que permite escolher um
 * layout olhando, em vez de escolher pelo nome. */
function buildHeadline(host, styleId, text, opts, ctx) {
  const o = opts || {};
  const S = hlStyle(styleId);
  const fonts = { main: o.fontMain || FONT_MAIN_DEF, accent: o.fontAccent || FONT_ACCENT_DEF };
  ensureFonts([fonts.main, fonts.accent]);
  const s = (o.width || host.clientWidth) / projW(ctx);
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
     roda. Quem repinta é o remonte do cartão (`renderSetup` no editor). */
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
    if (paint.heroBox && S.heroMid && i === hlHeroIndex(lines, S)) d.classList.add('hl-hero');
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
function buildCartelaDemo(host, styleId, ctx) {
  const st = ST(ctx);
  const C = window.AVE_CARTELA;
  const h = hlStyle(styleId);
  host.innerHTML = '';
  if (!C || !h || h.motor !== 'cartela') return () => {};
  const fonts = { main: st.fontMain || FONT_MAIN_DEF,
                  accent: st.fontAccent || FONT_ACCENT_DEF };
  ensureFonts([fonts.main, fonts.accent]);
  const sc = host.clientWidth / projW(ctx);

  const partes = C.fatiar(semMarcas(st.headlineText) || HEADLINE_TEXT, h);
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
  const main = normHex(st.textColor) || '#FFFFFF';
  const acc = normHex(st.accent) || ACCENT_DEFAULT;
  box.style.setProperty('--hl-main', main);
  box.style.setProperty('--hl-accent', acc);
  box.style.setProperty('--hl-accent-rgb', trioRGB(acc));
  box.style.setProperty('--hl-sobre-accent', sobreAccent(acc));
  // a mesma margem lateral segura do compositor (area_segura.lateral_minima)
  box.style.setProperty('--ct-lat', (130 * sc) + 'px');
  C.assentar(box);
  return () => {};
}

function buildHeadlineDemo(host, styleId, ctx) {
  const st = ST(ctx);
  const wrap = el('div', 'cap-demo', host);
  const fit = el('div', 'hl-fit', wrap);
  buildHeadline(fit, styleId, semMarcas(st.headlineText) || HEADLINE_TEXT, {
    width: host.clientWidth,
    // no ALTO do quadro, onde ela vai aparecer — o cartão agora tem altura para
    // isso, e a altura era a única razão de ela vir com top 0
    top: (hlStyle(styleId) || {}).top || 0,
    main: st.textColor,
    accent: st.accent,
    fontMain: st.fontMain,
    fontAccent: st.fontAccent,
  }, ctx);
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

function buildScatterDemo(host, ctx) {
  const s = host.clientWidth / projW(ctx);
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

function buildStaticDemo(host, id, ctx) {
  const V = STATIC_VARIANTS[id];
  const s = host.clientWidth / projW(ctx);
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
function buildCapCutDemo(host, tipo, grupo, ctx) {
  // `escolha` e não `st`: mais abaixo, `st` é o estado de cada unidade do estouro
  const escolha = ST(ctx);
  const s = host.clientWidth / projW(ctx);
  host.innerHTML = '';
  const wrap = el('div', 'cap-demo', host);
  const raiz = el('div', tipo === 'pop' ? `ave-pop grupo-${grupo}` : 'ave-rev', wrap);
  raiz.style.position = 'absolute';
  raiz.style.setProperty('--cap-scale', s);
  if (escolha.capFont) {
    ensureFonts([escolha.capFont]);
    raiz.style.setProperty('--cap-family', cssFamily(escolha.capFont));
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
  const todas = palRoteiro((v.upper ? CAP_TEXT.toUpperCase() : CAP_TEXT).split(' '));
  // palavra-chave (`pal.hi`): no exemplo, a mais longa faz o papel do número
  if ((v.pal || {}).hi && todas.length) {
    todas.slice(0, v.maxWords || 5)
      .reduce((a, b) => (b.texto.length > a.texto.length ? b : a)).hi = true;
  }
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
function buildPalavraDemo(host, id, ctx) {
  const s = host.clientWidth / projW(ctx);
  host.innerHTML = '';
  const wrap = el('div', 'cap-demo', host);
  const P = window.AVE_PALAVRA;
  const v = ((VARS && VARS.styles) || {})[id] || {};
  const cfg = v.pal || {};
  const box = el('div', `ave-pal pal-${id}`, wrap);
  if (!P || !v.pal) { box.textContent = ''; return () => {}; }
  vestirPal(box, id, v, s, ctx);
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
function vestirPal(box, id, v, escala, ctx) {
  const st = ST(ctx);
  box.style.position = 'absolute';
  box.style.inset = '0';
  box.style.setProperty('--cap-scale', escala);
  box.style.setProperty('--cap-size', v.size || 58);
  box.style.setProperty('--cap-weight', v.weight || 600);
  box.style.setProperty('--cap-track', v.tracking || 0);
  box.style.setProperty('--cap-lh', v.lineHeight || 1.26);
  const cor = st.capColor || '#F5F2EE';
  const acc = st.accent || ACCENT_DEFAULT;
  box.style.setProperty('--cap-color', cor);
  box.style.setProperty('--cap-color-rgb', trioRGB(cor));
  box.style.setProperty('--cap-accent', acc);
  box.style.setProperty('--cap-accent-rgb', trioRGB(acc));
  const fam = st.capFont ? cssFamily(st.capFont) : v.cssFamily;
  if (st.capFont) ensureFonts([st.capFont]);
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

/* Um construtor por `demo` do catálogo, sempre `(host, id, ctx) → step|null`.
 * Os de fora (styles.local.js, legendas privadas) entram aqui pelo mesmo
 * formato — quem chama não precisa saber de onde cada um veio. */
const CAP_BUILDERS = {
  karaoke: (h, _id, ctx) => buildKaraokeDemo(h, ctx),
  stacked: (h, _id, ctx) => buildStackedDemo(h, ctx),
  scatter: (h, _id, ctx) => buildScatterDemo(h, ctx),
  pop: (h, _id, ctx) => buildCapCutDemo(h, 'pop', 'palavra', ctx),
  popLinha: (h, _id, ctx) => buildCapCutDemo(h, 'pop', 'linha', ctx),
  popBloco: (h, _id, ctx) => buildCapCutDemo(h, 'pop', 'bloco', ctx),
  revelar: (h, _id, ctx) => buildCapCutDemo(h, 'revelar', undefined, ctx),
};
for (const [id] of PAL) CAP_BUILDERS[id] = (h, _id, ctx) => buildPalavraDemo(h, id, ctx);

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
    const H = (VARS || {}).headlines;
    return H ? Object.keys(H).filter((k) => H[k].usesAccent) : ACCENT_USERS_FALLBACK.headlines;
  },
  get captions() { return ACCENT_USERS_FALLBACK.captions; },
};

const styleName = (group, id) => (STYLE_CATALOG[group].find((o) => o.id === id) || {}).name || '—';

/* As OPÇÕES do radio de formato: as três de `edits` mais as três que moram em
 * `elements` (ver EDIT_ELEMENTS). Uma função, e não uma lista montada uma vez,
 * porque `STYLE_CATALOG` é dado e a ordem do catálogo é a ordem da tela. */
const editOptions = () => [
  ...STYLE_CATALOG.edits,
  ...EDIT_ELEMENTS.map((id) => STYLE_CATALOG.elements.find((e) => e.id === id)).filter(Boolean),
];
/* Qual dos três está ligado (string vazia = o formato é um `edit` comum). */
const formatoEl = (style) => EDIT_ELEMENTS.find((id) => style.elements[id]) || '';
/* O radio da headline: Caixinha e Notícia primeiro, depois o catálogo. */
const headlineOptions = () => [
  ...HEADLINE_ELEMENTS.map((id) => STYLE_CATALOG.elements.find((e) => e.id === id)).filter(Boolean),
  ...STYLE_CATALOG.headlines,
];
const headlineEl = (style) => HEADLINE_ELEMENTS.find((id) => style.elements[id]) || '';
const headlineName = (style) => {
  const id = headlineEl(style);
  return id ? ((STYLE_CATALOG.elements.find((e) => e.id === id) || {}).name || '—')
            : styleName('headlines', style.headline);
};
/* O NOME do formato escolhido, para os resumos. `styleName('edits', …)` não
 * serve sozinho: com Caixinha ligada o `edit` é `limpa`, e o resumo diria
 * "Nenhum" para um vídeo que tem um adesivo na tela. */
const formatoName = (style) => {
  const id = formatoEl(style);
  return id ? ((STYLE_CATALOG.elements.find((e) => e.id === id) || {}).name || '—')
            : styleName('edits', style.edit);
};
// the accent is a free colour, not a named entry in a list — it names itself
const accentName = (hex) => String(hex || ACCENT_DEFAULT).toUpperCase();
const accentUsed = (style) =>
  ACCENT_USERS.headlines.includes(style.headline)
  || ACCENT_USERS.captions.includes(style.captions);

/* Falta a chave que esta opção exige? Devolve a explicação; senão, ''.
 * A resposta vem do servidor (`keys`), não de um campo fixo no catálogo:
 * assim a trava some sozinha quando a chave entra, sem ninguém ter de lembrar
 * de destravar nada. */
function elLocked(e, style, keys) {
  if (e.needsKey) {
    keys = keys || {};
    // sem resposta do servidor ainda: não trave. Um "false" por ausência de
    // dado travaria a opção no primeiro segundo de cada carregamento.
    if (e.needsKey in keys && !keys[e.needsKey]) return e.keyMsg || 'Falta a chave de API para isto.';
  }
  /* EFEITO AUTOMÁTICO FORA DO FORMATO (regra do usuário, 2026-10-15): o chip
   * trava com o motivo, e a escolha dele fica guardada para quando o formato
   * mudar. A lista é a do `variants.json → efeitos.formatos`, a mesma que o
   * helpers/efeitos.py aplica no render — sem o variants carregado, não trava. */
  if (e.efx) {
    const fm = ((VARS || {}).efeitos || {}).formatos;
    // a LEGENDA também prevê: o estilo "Gráfico" traz os cartões dele
    const fl = ((VARS || {}).efeitos || {}).legendas || {};
    if (fm) {
      const f = formatoEl(style) || style.edit || 'limpa';
      if (!(fm[f] || []).includes(e.id) && !(fl[style.captions] || []).includes(e.id)) {
        return `O formato "${formatoName(style)}" não prevê este efeito.\n\n`
          + 'Efeito automático só entra quando o formato prevê — escolha "Ilustrado" '
          + '(ou outro formato que o preveja) na camada Formato.';
      }
    }
  }
  /* ZONA ALTA: a trava virou SUBSTITUIÇÃO (decisão do usuário, 2026-09-15).
   *
   * Caixinha, Notícia e as cartelas "banda" continuam disputando o mesmo canto
   * superior (top:300, janela do gancho) — isso é física do render e não mudou.
   * O que mudou é a resposta da interface: em vez de DESABILITAR a opção em
   * conflito, escolher uma desliga a outra (ver `limpaConflitoZonaAlta`).
   *
   * O motivo é que a trava não tinha saída visível. "Nenhum" é a última opção
   * de uma lista de 31 headlines, e até chegar nela o usuário via Notícia
   * permanentemente apagada — com uma dica que pedia justamente o passo que ele
   * não encontrava. Desabilitar explica o conflito depois que a pessoa já
   * desistiu; substituir resolve no próprio clique. */
  return '';
}

/* Escolher na zona alta DESLIGA o que colide, em vez de impedir o clique.
 *
 * Só desliga o que colide de verdade: a Notícia é tecnicamente uma cartela
 * banda (mesmo `hook.style`, mesma trilha), então ela e QUALQUER headline
 * nunca coexistem; a Caixinha é um elemento próprio e só briga com as cartelas
 * BANDA — com uma cartela de tela cheia ou com os onze estilos clássicos ela
 * convive, e essa combinação continua alcançável. */
function limpaConflitoZonaAlta(style, origem) {
  const els = style.elements;
  if (origem === 'headline') {
    if (style.headline) els.noticia = false;
    if (CARTELA_BANDA_IDS.has(style.headline)) els.caixinha = false;
  } else {
    if (els.noticia) style.headline = '';
    if (els.caixinha && CARTELA_BANDA_IDS.has(style.headline)) style.headline = '';
  }
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
    // POSIÇÃO E TAMANHO DA HEADLINE — arrastada/redimensionada sobre o vídeo
    // (ver a seção "POSIÇÃO DA HEADLINE"). px de referência 1080, como a
    // legenda; dy positivo = para CIMA; escala multiplica o layout inteiro.
    hookDx: 0, hookDy: 0, hookScale: 1,
    elements,
    // CTA DE FECHAMENTO (aba CTA). `modelo` vazio = nenhum. O @ vem do
    // brand.json (`instagram`) quando o projeto não tem o seu.
    cta: { modelo: '', arroba: '' },
    // EFEITO DO GANCHO (motor de efeitos): '' = nenhum
    ganchoEfeito: '',
    note: '',
  };
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
  /* Sem `elements`: Caixinha, Broll Overlay e Notícia entram no PRÓPRIO radio
     de `edits` (ver EDIT_ELEMENTS) em vez de virem como checkbox ao lado dele.
     Listá-los aqui também os desenharia duas vezes na mesma camada. */
  { id: 'elementos', name: 'Formato', sub: 'Um formato por vídeo — layout do corte, broll overlay ou animação',
    ico: 'inserts', groups: ['edits'] },
  { id: 'headline', name: 'Headline', sub: 'Caixinha, notícia ou layout — o texto é combinado no chat',
    ico: 'text', groups: ['headlines', 'ganchoFx'] },
  { id: 'legendas', name: 'Legendas', sub: 'Estilo',
    ico: 'captions', groups: ['captions'] },
  /* EFEITOS (2026-10-15): ilustram a fala e entram SOZINHOS — mas só quando o
     formato os prevê (regra do usuário; "Nenhum" não prevê nada). O chip é a
     permissão; o lugar de cada um sai da leitura da fala (helpers/efeitos.py). */
  { id: 'efeitos', name: 'Efeitos', sub: 'Ilustram a fala — entram sozinhos quando o formato prevê',
    ico: 'fx', elements: ['checklist', 'chartGrow', 'conta', 'versus', 'phoneMockup', 'uiWorld'] },
  { id: 'movimento', name: 'Movimento & tracking', sub: 'Animações, máscaras, rastreamento e keyframes',
    ico: 'video', elements: ['tracking', 'zoomAuto', 'zoomCuts', 'zoomPunch', 'zoomThrough'] },
  { id: 'trilha', name: 'Trilha & mixagem', sub: 'Áudio, níveis, ducking e mixagem final',
    ico: 'music', elements: ['sfx', 'musicAI'] },
  /* A ÚLTIMA porque é o último segundo do vídeo: o pedido de seguir. */
  { id: 'cta', name: 'CTA', sub: 'Fecho do vídeo — siga o perfil, card ou botão do Instagram',
    ico: 'follow', cta: true },
];

// `edits` deixou de ser só "tipo de edição" quando Caixinha, Broll Overlay e
// Notícia entraram no mesmo radio (ver EDIT_ELEMENTS) — o título tem de
// cobrir os seis, e "um por vídeo" é a regra que o radio impõe.
const GROUP_TITLE = { edits: 'Formato — um por vídeo', headlines: 'Headline — caixinha, notícia ou layout',
                      ganchoFx: 'Efeito do gancho — os primeiros segundos', captions: 'Estilo de legenda' };

/* ---------- CTA DE FECHAMENTO ----------
 * Os modelos moram em assets/cta/ e quem monta é helpers/cta.py. Aqui só se
 * escolhe o modelo, o @ e a foto. A FOTO não é estilo: é arquivo, e vai direto
 * para o servidor no ato (projeto + ~/.avelin/cta/perfil.png) em vez de esperar
 * o envio — sem ela, a Fase 2 recusa os modelos que a pedem. */
const CTA_MODELOS = [
  { id: '', name: 'Nenhum', foto: false },
  { id: 'siga-perfil', name: 'Siga o perfil', foto: true,
    title: 'Cápsula no topo que abre da foto: "Siga o perfil" + @, cursor aperta Seguir' },
  { id: 'instagram-card', name: 'Instagram Card', foto: true,
    title: 'O ícone do Instagram vira um cartão com foto, @ e Seguir → Seguindo' },
  { id: 'instagram-simples', name: 'Instagram Simples', foto: false,
    title: 'Só o botão Seguir → Seguindo, sem foto' },
  /* RECUO PARA O APP (motor de efeitos, 2026-10-15): o vídeo recua para dentro
     de uma janela de editor e um cartão de seguir é clicado */
  { id: 'revelarApp', name: 'Recuo para o app', foto: false,
    title: 'O vídeo recua para dentro de uma janela de app; o cursor aperta Seguir' },
];

/* A miniatura de cada modelo leva a FOTO DE VERDADE quando ela existe: escolher
   o card vendo o próprio rosto nele é a prévia que importa. */
function ctaMock(id, host, o) {
  o = o || {};
  const foto = o.foto || '';
  const arroba = o.arroba || '';
  const accent = o.accent || ACCENT_DEFAULT;
  if (id === 'siga-perfil') {
    host.innerHTML = '<div class="cta-pill"><span class="cta-pill-foto"></span>'
      + '<span class="cta-pill-txt"><b>Siga o perfil</b><i></i></span>'
      + '<span class="cta-pill-btn">Seguir</span></div>';
    host.querySelector('.cta-pill-btn').style.background = accent;
    host.querySelector('.cta-pill-txt i').textContent = arroba || '@perfil';
    if (foto) host.querySelector('.cta-pill-foto').style.backgroundImage = `url("${foto}")`;
  } else if (id === 'instagram-card') {
    host.innerHTML = `<div class="cta-card"><img src="${amb.assets}cta-card.png" alt="">`
      + '<span class="cta-card-foto"></span></div>';
    if (foto) host.querySelector('.cta-card-foto').style.backgroundImage = `url("${foto}")`;
  } else if (id === 'instagram-simples') {
    host.innerHTML = `<div class="cta-simples"><img src="${amb.assets}cta-simples.png" alt=""></div>`;
  } else if (id === 'revelarApp') {
    host.innerHTML = '<svg viewBox="0 0 66 118" xmlns="http://www.w3.org/2000/svg">'
      + '<rect x=".5" y=".5" width="65" height="117" rx="7" fill="#ECE8E1"/>'
      + '<rect x="13" y="16" width="40" height="4" rx="1.5" fill="#fff"/>'
      + '<circle cx="16" cy="18" r="1" fill="#ff5f57"/><circle cx="19" cy="18" r="1" fill="#febc2e"/>'
      + '<rect x="13" y="20" width="40" height="62" rx="3" fill="#3a3840"/>'
      + '<circle cx="33" cy="44" r="8" fill="#d9d4cf"/><path d="M20 82a13 13 0 0126 0z" fill="#d9d4cf"/>'
      + '<rect x="13" y="86" width="40" height="5" rx="1.5" fill="#fff"/>'
      + `<rect x="13" y="95" width="40" height="10" rx="3" fill="#fff"/><rect x="38" y="97" width="13" height="6" rx="3" fill="${accent}"/>`
      + '</svg>';
  } else {
    host.innerHTML = '<div class="cta-nenhum">sem CTA</div>';
  }
}

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
  if (!file || FOLHAS.has(file)) return;
  FOLHAS.add(file);
  const l = document.createElement('link');
  l.rel = 'stylesheet';
  l.href = `${amb.base}${file}`;
  document.head.appendChild(l);
}

/* A JANELA DO GANCHO. O compositor usa `hook.endSec` e o padrão dele é 4s —
   fora dessa janela o gancho não existe no vídeo, e a prévia diz isso
   apagando-o em vez de escondê-lo. */
const GANCHO_SEC = 4.0;

/* ---------- POSIÇÃO E TAMANHO DA HEADLINE ----------
 *
 * Como a legenda: arrastar move, e vale para o vídeo inteiro (a headline é uma
 * só). Mais o canto: puxar o canto inferior direito redimensiona.
 *
 * A MESMA CONTA DO RENDER, não um transform por cima da prévia. O tamanho
 * multiplica `--hl-scale` — que já atravessa fonte, margem, sombra, raio e
 * altura de TODO layout das duas folhas — e a altura é dividida pelo mesmo
 * fator, senão crescer empurraria a headline para baixo (o `top` também é
 * multiplicado pela escala). O `compose_shortform.py` escreve exatamente estes
 * dois números no `#hook`; um `transform: scale` aqui faria a prévia mostrar
 * uma coisa e o render entregar outra.
 *
 * Cartela de TELA CHEIA não se move nem redimensiona: ela É o quadro. */
const HOOK_LIM = { dx: 540, dyMin: -1500, dyMax: 400, kMin: 0.5, kMax: 1.6 };
function hookAjuste(box, host, h, ctx) {
  const st = ST(ctx);
  const alvo = host.querySelector('.ave-hook, .ave-cartela');
  if (!alvo || (h && h.cheia)) return;
  const sc0 = parseFloat(alvo.style.getPropertyValue('--hl-scale')) || (box.clientWidth / projW(ctx));
  const top0 = parseFloat(alvo.style.getPropertyValue('--hl-top')) || ((h || {}).top || 0);
  const k = st.hookScale || 1;
  const dx = st.hookDx || 0;
  const dy = st.hookDy || 0;
  alvo.style.setProperty('--hl-scale', sc0 * k);
  alvo.style.setProperty('--hl-top', (top0 - dy) / k);
  alvo.style.translate = `${dx * sc0}px 0`;
  // a ALÇA: um retângulo sobre o que está desenhado, o único pedaço do
  // overlay que recebe ponteiro (o resto continua deixando clicar no vídeo)
  requestAnimationFrame(() => {
    const partes = alvo.querySelectorAll('.hl-line, .ct-bloco');
    if (!partes.length || !box.isConnected) return;
    const ref = box.getBoundingClientRect();
    let l = Infinity, t = Infinity, r = -Infinity, b = -Infinity;
    partes.forEach((n) => {
      const q = n.getBoundingClientRect();
      if (!q.width) return;
      l = Math.min(l, q.left); t = Math.min(t, q.top);
      r = Math.max(r, q.right); b = Math.max(b, q.bottom);
    });
    if (!isFinite(l)) return;
    let alca = box.querySelector('.hook-alca');
    if (!alca) {
      alca = el('div', 'hook-alca', box);
      el('div', 'hook-canto', alca);
      alca.title = 'arraste para mover · canto para redimensionar · duplo clique volta ao padrão';
    }
    Object.assign(alca.style, {
      left: `${l - ref.left - 6}px`, top: `${t - ref.top - 6}px`,
      width: `${r - l + 12}px`, height: `${b - t + 12}px`,
    });
  });
}

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

function applyCapDy(box, id, v, capDy) {
  const a = CAP_ANCHOR[id];
  if (!a) return;
  const base = (a.var === '--cap-bottom' && v.bottom) || (v.offsetY != null && a.var !== '--cap-bottom' ? v.offsetY : a.base);
  const dy = capDy || 0;
  box.style.setProperty(a.var, base + a.dir * dy * a.scale);
}

/* LEGENDAS PRIVADAS — estilos de legenda de UMA pessoa, que moram em
   ~/.avelin/legendas e nunca entram no repositório (helpers/legendas_privadas.py).
   O servidor lista; aqui a folha e o script de cada uma são carregados de
   /legpriv/<id>/, e ela entra PRIMEIRO na galeria de legendas, com a borda
   laranja dos estilos pessoais. A prévia é do próprio script dela
   (`AVE_LEGPRIV[id].demo`) — a galeria não sabe nada do estilo. */
async function carregarLegendasPrivadas() {
  try {
    const d = await (await fetch('/api/legendas-privadas')).json();
    const lista = (d && d.legendas) || [];
    const novas = lista.filter((m) => !STYLE_CATALOG.captions.some((o) => o.id === m.id));
    if (!novas.length) return false;
    await Promise.all(novas.map((m) => new Promise((ok) => {
      if (m.css) {
        const l = document.createElement('link');
        l.rel = 'stylesheet';
        l.href = `/legpriv/${m.id}/${m.css}`;
        document.head.appendChild(l);
      }
      const sc = document.createElement('script');
      sc.src = `/legpriv/${m.id}/${m.js}`;
      sc.onload = sc.onerror = () => ok();
      document.head.appendChild(sc);
      CAP_BUILDERS[m.id] = (h, _id, ctx) => {
        const L = (window.AVE_LEGPRIV || {})[m.id];
        const c = ctxDe(ctx);
        return (L && L.demo) ? (L.demo(h, { largura: c.frameW, altura: c.frameH,
                                         accent: c.style.accent || ACCENT_DEFAULT })
                                || (() => {})) : (() => {});
      };
    })));
    STYLE_CATALOG.captions.unshift(
      ...novas.map((m) => ({ id: m.id, name: m.nome, demo: m.id, priv: true, desc: m.descricao })));
    return true;
  } catch (e) { return false; }
}

/* O @ do CTA: o do projeto, senão o da marca (`brand.json → instagram`). */
function ctaArroba(style, brand) {
  const a = (((style || {}).cta || {}).arroba || '').trim() || ((brand || {}).instagram || '').trim();
  return a ? (a.startsWith('@') ? a : '@' + a) : '';
}

/* ---------- o cartão de uma opção do catálogo ----------
 * A mesma decisão que o `radios()` do editor fazia em linha: `demo` → o
 * construtor animado, `ct` → cartela assentada, `hl` → headline, `stat` →
 * legenda estática, senão o mock em SVG. Devolve o `step(now)` de quem anima
 * (para o laço da página) ou null. Um `demo` sem construtor deixa o cartão
 * parado em vez de derrubar a aba inteira: a lista de estilos é dado, e dado
 * erra. */
function montarCartao(prev, o, ctx) {
  if (o.demo && CAP_BUILDERS[o.demo]) return CAP_BUILDERS[o.demo](prev, o.demo, ctx) || null;
  if (o.ct) { buildCartelaDemo(prev, o.ct, ctx); return null; }
  if (o.hl) { buildHeadlineDemo(prev, o.hl, ctx); return null; }
  if (o.stat) return buildStaticDemo(prev, o.stat, ctx) || null;
  prev.innerHTML = o.mock || '';
  return null;
}
/* A classe da caixa do cartão: o mock é um quadro de mock; o resto é o QUADRO
   do vídeo (`--quadro-w/h`), e headline/cartela pedem a moldura delas. */
const tipoCartao = (o) => (o.mock ? 'frame' : o.ct ? 'cap ctbox' : o.hl ? 'cap hlbox' : 'cap');

/* ---------- AO VIVO: a legenda sobre o vídeo ----------
 * Desenha a deixa `texto` no estilo `id` dentro de `ov` — uma caixa do tamanho
 * do VÍDEO em tela, não da moldura. Quem decide QUANDO remontar (a deixa mudou,
 * a largura mudou) é a página: remontar a cada quadro seria refazer o DOM
 * sessenta vezes por segundo para escrever o mesmo texto. `ctx.largura` é a
 * largura exata do vídeo em tela; sem ela, mede `ov`.
 *
 * A escala aqui é `/1080` FIXO, como sempre foi no editor (o arrasto e o
 * `capDy` contam na mesma unidade). Num 9:16 é a mesma do cartão; num
 * horizontal ela diverge da dos cartões (`/frameW`). Divergência herdada, que
 * não se corrige aqui sem mudar o que o editor mostra. */
function montarLegendaViva(ov, id, texto, ctx) {
  const st = ST(ctx);
  const v = capVariant(id);
  liveCss(CAP_CSS[id]);
  /* A família escolhida desce por variável, e o padrão é a do próprio estilo.
     Aplicada uma vez aqui, no contêiner, em vez de repetida em cada ramo — os
     ramos já divergem na MARCAÇÃO, e divergir também na fonte é onde um deles
     acabaria esquecido. */
  const capFam = st.capFont ? cssFamily(st.capFont) : (v.cssFamily || null);
  if (st.capFont) ensureFonts([st.capFont]);
  const vestir = (box) => {
    if (capFam) {
      box.style.setProperty('--cap-family', capFam);
      box.style.setProperty('--stk-family', capFam);
      box.style.setProperty('--scat-family', capFam);
    }
    return box;
  };
  const w = (ctx && ctx.largura) || ov.getBoundingClientRect().width;
  ov.innerHTML = '';
  const sc = w / 1080;
  const words = String(texto || '').split(/\s+/);

  /* CADA ESTILO TEM MARCAÇÃO PRÓPRIA, e é por isso que existe um ramo por
     estilo em vez de uma caixa genérica com a fonte trocada. O empilhado é uma
     PILHA de linhas com quatro papéis tipográficos alternados; o disperso são
     palavras soltas com uma destacada. Desenhar os dois como uma faixa
     centralizada carregaria a fonte certa e mostraria um estilo que não existe
     — que é a mentira que esta prévia existe para não contar. */
  if (id === 'stacked') {
    const box = vestir(el('div', 'ave-stacked', ov));
    box.style.setProperty('--stk-scale', sc);
    applyCapDy(box, id, v, st.capDy);
    box.style.setProperty('--stk-orange', st.accent || ACCENT_DEFAULT);
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
    applyCapDy(box, id, v, st.capDy);
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
    applyCapDy(box, id, v, st.capDy);
    box.style.setProperty('--cap-color', st.capColor || '#fff');
    box.style.setProperty('--cap-accent', st.accent || ACCENT_DEFAULT);
    if (v.size) box.style.setProperty('--cap-size', v.size);
    const line = el('div', 'ave-cap-line', box);
    for (const word of words) el('span', '', line).textContent = word.toUpperCase();
  } else if (id === 'revelar') {
    const box = vestir(el('div', 'ave-rev', ov));
    box.style.setProperty('--cap-scale', sc);
    applyCapDy(box, id, v, st.capDy);
    box.style.setProperty('--cap-color', st.capColor || '#fff');
    box.style.setProperty('--cap-accent', st.accent || ACCENT_DEFAULT);
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
      vestirPal(box, id, v, sc, ctx);
      box.style.position = 'absolute';
      box.style.inset = '0';
      applyCapDy(box, id, v, st.capDy);
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
    applyCapDy(box, id, v, st.capDy);
    box.style.setProperty('--cap-color', st.capColor || '#fff');
    if (v.size) box.style.setProperty('--cap-size', v.size);
    const line = el('div', 'ave-cap-line', box);
    for (const word of words) el('span', '', line).textContent = word;
  } else {
    const box = vestir(el('div', 'ave-cap-static', ov));
    box.style.setProperty('--cap-scale', sc);
    applyCapDy(box, id, v, st.capDy);
    if (v.size) box.style.setProperty('--cap-size', v.size);
    if (v.tracking != null) box.style.setProperty('--cap-track', v.tracking);
    if (v.sx != null) box.style.setProperty('--cap-sx', v.sx);
    if (v.sy != null) box.style.setProperty('--cap-sy', v.sy);
    if (v.cssFamily) box.style.setProperty('--cap-family', v.cssFamily);
    if (v.weight) box.style.setProperty('--cap-weight', v.weight);
    box.style.setProperty('--cap-color', st.capColor || '#fff');
    el('div', 'ave-cue', box).textContent = texto;
  }
}

/* ---------- AO VIVO: a headline sobre o vídeo ----------
 * Monta dentro de `box` (a caixa do tamanho do vídeo, irmã da legenda — o
 * overlay da legenda é reconstruído a cada troca de deixa, e a headline não
 * pode nascer e morrer sessenta vezes por segundo junto com ela). O texto é o
 * `style.headlineText` sem as marcas. `ctx.dentro === false` = fora da janela
 * do gancho (`GANCHO_SEC`): continua desenhada, APAGADA (`.fora`). Devolve o
 * host `.live-hook`. */
function montarHeadlineViva(box, id, ctx) {
  const st = ST(ctx);
  const h = hlStyle(id);
  const texto = semMarcas((st.headlineText || '').trim()) || HEADLINE_TEXT;
  const dentro = !(ctx && ctx.dentro === false);
  box.innerHTML = '';
  const host = el('div', `live-hook${dentro ? '' : ' fora'}`, box);
  if (h && h.motor === 'cartela') {
    buildCartelaDemo(host, id, ctx);
  } else {
    buildHeadline(host, id, texto, {
      width: (ctx && ctx.largura) || box.clientWidth, top: (h || {}).top || 0,
      main: st.textColor, accent: st.accent,
      fontMain: st.fontMain, fontAccent: st.fontAccent,
    }, ctx);
  }
  hookAjuste(box, host, h, ctx);
  return host;
}

/* ---------- O PEDIDO: o corpo exato do `/api/save` ----------
 * Um lugar só para os dois lados (editor e galeria) escreverem o MESMO
 * `preview_style.json` — é ele que o `phase2.py` lê (`apply_style_pick`), e um
 * campo escrito de um jeito numa tela e de outro na outra é uma Fase 2 que muda
 * conforme a porta por onde se entrou. A ordem das chaves é a de sempre, e o
 * que cada uma significa está comentado junto dela. `o.rerender` diz se já
 * existe Fase 2 em disco (o editor passa `!state.awaitingStyle`); `o.note`,
 * se vier, vence `style.note`. */
function payloadEstilo(style, o) {
  o = o || {};
  return {
    // a save with Fase 2 already on disk is a RE-RENDER request, not a first
    // pick — the skill has to know which of the two it is looking at
    type: 'style-setup',
    rerender: !!o.rerender,
    /* ESTILO SALVO escolhido: o phase2.py aplica também fonte e cor dele (o
       envio comum não aplica — quem muda fonte e cor é o chat) e as opções da
       moldura explicativa. Mexer em qualquer cartão depois apaga a marca. */
    estiloSalvo: style.estiloSalvo || null,
    explicativoOpcoes: (style.estiloSalvo && style.explicativo) || null,
    edit: style.edit,
    editName: styleName('edits', style.edit),
    cta: { modelo: (style.cta || {}).modelo || '',
           arroba: ((style.cta || {}).arroba || '').trim() },
    /* O FORMATO como UMA coisa, para quem LÊ o pedido. `edit`/`elements`
       continuam sendo o contrato de máquina (o phase2.py lê os dois e não
       sabe deste campo), mas sozinho o `edit` diz "Nenhum" quando a escolha
       foi Caixinha — e é essa a linha que o watch_edits.py mostra à sessão. */
    formato: formatoEl(style) || style.edit,
    formatoName: formatoName(style),
    headline: style.headline,
    headlineName: headlineName(style),
    ganchoEfeito: style.ganchoEfeito || '',
    ganchoEfeitoName: style.ganchoEfeito ? styleName('ganchoFx', style.ganchoEfeito) : '',
    captions: style.captions,
    captionsName: styleName('captions', style.captions),
    accent: style.accent,
    accentName: accentName(style.accent),
    capColor: style.capColor || '#FFFFFF',
    textColor: style.textColor || '#FFFFFF',
    fontMain: style.fontMain || FONT_MAIN_DEF,
    fontAccent: style.fontAccent || FONT_ACCENT_DEF,
    capFont: style.capFont || capVariant(style.captions || 'karaoke').cssFamily || FONT_MAIN_DEF,
    // se a segunda família chega a aparecer neste layout — sem isto a skill
    // não sabe se a fonte de destaque é uma instrução ou um valor sem uso
    fontAccentUsed: !!(hlStyle(style.headline) || {}).fontRole,
    capDy: style.capDy || 0,   // deslocamento GLOBAL da legenda, px de ref 1080
    hookDx: style.hookDx || 0, hookDy: style.hookDy || 0,
    hookScale: style.hookScale || 1,
    // sem campo na tela — passa adiante o que o chat já tiver escrito direto
    // em `preview_style.json`/`edit-data.json`, para não apagar ao reenviar
    headlineText: (style.headlineText || '').trim(),
    // a caixinha de perguntas: o único dado do formato que não se mede
    caixaPergunta: (style.caixaPergunta || '').trim(),
    caixaChamada: (style.caixaChamada || '').trim(),
    // whether the picked styles actually paint it — so the skill does not go
    // hunting for an accent in a look that has none
    accentUsed: accentUsed(style),
    elements: { ...style.elements },
    elementNames: STYLE_CATALOG.elements
      .filter((e) => style.elements[e.id])
      .map((e) => e.name),
    note: o.note != null ? o.note : style.note,
  };
}

/* ---------- carregar o que as prévias medem ----------
 * O variants.json traz os números dos layouts, das legendas e o catálogo de
 * fontes. Antes dele chegar, `hlStyle` só tem quatro reservas: as cartelas
 * saem em branco (falta `motor`) e os cartões do motor `palavra` saem vazios —
 * por isso a página desenha de novo quando `carregar()` resolver. Uma vez só:
 * a promessa fica guardada e todos esperam a mesma. Falhou, resolve `null`: sem
 * os números a prévia cai no CSS puro, que já é honesto. */
let prontoP = null;
function carregar() {
  if (!prontoP) {
    // uma segunda tentativa, pela mesma razão das folhas em garantirRecursos
    const pede = () => fetch(`${amb.base}variants.json`).then((r) => r.json());
    prontoP = pede()
      .catch(() => new Promise((ok) => setTimeout(ok, 250)).then(pede))
      .then((v) => { VARS = v; return v; })
      .catch(() => null);
  }
  return prontoP;
}

/* As famílias que os cartões de legenda desenham SEM pedir (karaokê, empilhado,
   disperso, estáticas): o editor as traz no `<head>` do index.html. Mesma URL de
   lá, para a página que já tem a folha não ganhar uma segunda. */
const FONTES_BASE = 'https://fonts.googleapis.com/css2?family=Open+Sans:wght@400;600;700&family=Libre+Baskerville:ital,wght@0,400;0,700;1,400&family=Poppins:ital,wght@0,400;0,600;0,700;0,800;0,900;1,900&family=Playfair+Display:ital,wght@1,900&family=Lora:ital,wght@0,400;0,600;1,400;1,600&family=Inter:wght@400;500;600;700&display=swap';
const FOLHAS_RENDER = ['headline.css', 'pop.css', 'revelar.css', 'palavra.css', 'cartela.css'];
const SCRIPTS_RENDER = ['pop.js', 'revelar.js', 'palavra.js', 'cartela.js'];

/* Para uma página que NÃO é o editor: as fontes base, as folhas e os scripts do
   render que os cartões usam. O que a página já tiver (mesmo href/src) não é
   pedido de novo. Resolve quando os scripts terminaram de carregar.

   UM SCRIPT POR VEZ, e cada pedido que falha é refeito UMA vez. Medido na
   galeria (cortes_view.py: HTTP/1.0, fila de `listen` de 5): pedir os quatro
   juntos com as folhas derrubava conexões (ERR_CONNECTION_RESET em pop.js e
   palavra.js em 3 de 4 cargas), e sem o palavra.js os cartões do motor
   `palavra` saíam vazios — sem erro nenhum na tela. */
function garantirRecursos() {
  const temLink = (href) => [...document.querySelectorAll('link[rel="stylesheet"]')]
    .some((l) => l.getAttribute('href') === href);
  const link = (href, retry) => {
    if (!retry && temLink(href)) return;
    const l = document.createElement('link');
    l.rel = 'stylesheet';
    l.href = href;
    if (!retry) l.onerror = () => { l.remove(); setTimeout(() => link(href, true), 250); };
    document.head.appendChild(l);
  };
  link(FONTES_BASE);
  for (const f of FOLHAS_RENDER) link(amb.base + f);
  const script = (src, retry) => new Promise((ok) => {
    if (!retry && [...document.scripts].some((x) => x.getAttribute('src') === src)) return ok();
    const x = document.createElement('script');
    x.src = src;
    x.onload = () => ok();
    x.onerror = () => {
      x.remove();
      if (retry) ok();
      else setTimeout(() => script(src, true).then(ok), 250);
    };
    document.head.appendChild(x);
  });
  return SCRIPTS_RENDER.reduce((p, f) => p.then(() => script(amb.base + f)), Promise.resolve());
}

/* ---------- um laço para quem não tem o seu ----------
 * O editor anima os cartões no `rafLoop` dele (que também move a agulha e a
 * legenda ao vivo). Uma página que só mostra cartões não tem laço nenhum, e
 * sem ele cada cartão animado fica parado no primeiro quadro. `animar(step ou
 * [steps])` devolve a função que os desliga; `parar()` desliga todos. Um step
 * que quebra sai do laço sozinho, em vez de congelar os outros. */
const PASSOS = new Set();
let lacoId = 0;
function tique() {
  const now = performance.now() / 1000;
  for (const s of PASSOS) {
    try { s(now); } catch (e) { PASSOS.delete(s); console.error(e); }
  }
  lacoId = PASSOS.size ? requestAnimationFrame(tique) : 0;
}
function animar(steps) {
  const lista = [].concat(steps || []).filter((s) => typeof s === 'function');
  for (const s of lista) PASSOS.add(s);
  if (PASSOS.size && !lacoId) lacoId = requestAnimationFrame(tique);
  return () => { for (const s of lista) PASSOS.delete(s); };
}
function parar() {
  PASSOS.clear();
  if (lacoId) cancelAnimationFrame(lacoId);
  lacoId = 0;
}

/* ---------- O PAINEL "CAMADAS DO RENDER" para quem NÃO é o editor ----------
 *
 * POR QUE EXISTE. A galeria de cortes oferece a MESMA escolha da coluna do
 * editor (Formato, Headline, Legendas, Efeitos, Movimento, Trilha, CTA), com os
 * mesmos cartões e as mesmas regras de clique. O `renderSetup`/`buildLayerRows`
 * do editor vivem amarrados ao `S`, ao `<video>` e aos ids do DOM de lá —
 * trazê-los para cá mudaria o editor. Então o editor fica como está, e esta
 * função é a versão autocontida: recebe o objeto de escolhas (`o.estilo()`, no
 * formato do `S.style`) e o MUTA no lugar, exatamente como os handlers do
 * editor mutam o `S.style`. O pedido sai do mesmo `payloadEstilo`.
 *
 * O QUE NÃO VEM DO EDITOR, de propósito:
 *  - os estilos SALVOS (moram no servidor do editor, em ~/.avelin);
 *  - o OLHO das demos no player (precisa do demos.js e do palco do editor);
 *  - a foto do CTA (o upload é rota do editor; a Fase 2 usa a foto salva).
 * O QUE ENTRA A MAIS com `o.camposHeadline`: sem chat no circuito, a aba
 * Headline ganha o texto (com as marcas do render), a cor principal, a de
 * destaque e a família — no editor, quem muda essas coisas é a conversa.
 *
 * `o` = { estilo: () => style, aoMudar(oque), avisar(msg), keys, brand, inicial,
 *         indisponivel: {id: motivo}, camposHeadline, idPrefixo }
 * Devolve { render(), camada(id), ativa(), destruir() }. */
const ICONES_CAMADA = {
  captions: '<svg viewBox="0 0 16 16"><rect x="1" y="3" width="14" height="10" rx="2.4" fill="none" stroke="currentColor" stroke-width="1.4"/><rect x="3.4" y="8.4" width="4.4" height="1.5" rx=".75"/><rect x="8.9" y="8.4" width="3.7" height="1.5" rx=".75"/></svg>',
  video: '<svg viewBox="0 0 16 16"><rect x="1" y="3" width="14" height="10" rx="2.4" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M6.5 5.9v4.2c0 .4.44.64.79.42l3.3-2.1a.5.5 0 0 0 0-.85l-3.3-2.1a.5.5 0 0 0-.79.43z"/></svg>',
  inserts: '<svg viewBox="0 0 16 16"><rect x="1.2" y="3.2" width="13.6" height="9.6" rx="2.2" fill="none" stroke="currentColor" stroke-width="1.4"/><circle cx="5.3" cy="6.6" r="1.15"/><path d="M2.6 11.7l3-2.9a1 1 0 0 1 1.34-.05l1.84 1.58 1.5-1.24a1 1 0 0 1 1.29.02l1.72 1.5" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  music: '<svg viewBox="0 0 16 16"><path d="M13.1 1.9 6.6 3.5a.8.8 0 0 0-.6.78v6.06a2.25 2.25 0 1 0 1.5 2.12V6.6l5-1.22v3.5a2.25 2.25 0 1 0 1.5 2.12V2.68a.8.8 0 0 0-.9-.78z"/></svg>',
  follow: '<svg viewBox="0 0 16 16"><circle cx="6.2" cy="5" r="2.9"/><path d="M1 13.6c0-2.9 2.3-4.7 5.2-4.7s5.2 1.8 5.2 4.7v.6H1v-.6z"/><path d="M13 4.6v4.6M10.7 6.9h4.6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" fill="none"/></svg>',
  text: '<svg viewBox="0 0 16 16"><path d="M2 2.6h12v2.5h-1.5V4.1H8.75v8.1h1.6v1.3H5.65v-1.3h1.6V4.1H3.5v1H2V2.6z"/></svg>',
  fx: '<svg viewBox="0 0 16 16"><rect x="1.4" y="5" width="9.2" height="9.2" rx="2.2" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M3.8 9.6l1.6 1.6 2.9-3.2" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/><path d="M12.6.9l.7 1.8 1.8.7-1.8.7-.7 1.8-.7-1.8-1.8-.7 1.8-.7z"/></svg>',
};
function montarPainel(host, o) {
  o = o || {};
  const st = () => (o.estilo ? o.estilo() : amb.estilo()) || {};
  const pre = o.idPrefixo || 'ave-painel';
  const indisp = o.indisponivel || {};
  const mudou = (oque) => { if (o.aoMudar) o.aoMudar(oque); };
  const avisa = (m) => (o.avisar ? o.avisar(m) : window.alert(m));
  let ativa = LAYERS.some((L) => L.id === o.inicial) ? o.inicial : LAYERS[0].id;
  let pararAnim = null;
  let tTexto = null;

  host.classList.add('ave-painel');
  host.innerHTML = '';
  const abas = el('div', 'ave-painel-abas', host);
  abas.setAttribute('role', 'tablist');
  const corpo = el('div', 'ave-painel-corpo', host);

  /* O destaque e a cor principal descem por VARIÁVEL no painel, como no
     editor (`applyAccent`): arrastar a roda de cor atualiza os cartões de
     headline sem remontar nenhum. */
  const cores = () => {
    const s = st();
    host.style.setProperty('--hl-accent', s.accent || ACCENT_DEFAULT);
    host.style.setProperty('--hl-main', normHex(s.textColor) || '#FFFFFF');
  };

  // o resumo de cada aba — a mesma conta do refreshLayerSummaries do editor
  const resumo = (L) => {
    const s = st();
    if (L.soon) return 'em breve';
    if (L.cta) {
      const m = CTA_MODELOS.find((x) => x.id === ((s.cta || {}).modelo || ''));
      return m && m.id ? m.name : 'nenhum';
    }
    const bits = [];
    for (const g of L.groups || []) bits.push(g === 'edits' ? formatoName(s)
      : g === 'headlines' ? headlineName(s)
      : g === 'ganchoFx' ? (s.ganchoEfeito ? styleName('ganchoFx', s.ganchoEfeito) : '')
      : styleName(g, s.captions));
    if (L.elements) {
      const on = L.elements.filter((id) => {
        const cat = STYLE_CATALOG.elements.find((x) => x.id === id);
        return s.elements[id] && !(cat && cat.efx && elLocked(cat, s, o.keys));
      });
      bits.push(on.length ? `${on.length} ativo${on.length === 1 ? '' : 's'}` : 'desligado');
    }
    return bits.filter(Boolean).join(' · ');
  };

  function pintarAbas() {
    abas.innerHTML = '';
    for (const L of LAYERS) {
      const b = el('button', `ave-aba${L.id === ativa ? ' on' : ''}`, abas);
      b.type = 'button';
      b.dataset.camada = L.id;
      b.title = L.sub;
      b.setAttribute('role', 'tab');
      b.setAttribute('aria-selected', L.id === ativa ? 'true' : 'false');
      el('span', 'ave-aba-ico', b).innerHTML = ICONES_CAMADA[L.ico] || '';
      el('span', 'ave-aba-nome', b).textContent = L.name.replace(/ &.*$/, '');
      el('span', 'ave-aba-resumo', b).textContent = resumo(L);
    }
  }

  /* O RADIO de um grupo — o `radios()` do editor sem os salvos: as mesmas
     opções, o mesmo "marcado", o mesmo apagado para o que não foi portado. */
  function radios(grid, group, steps) {
    const s = st();
    const opts = group === 'edits' ? editOptions()
      : group === 'headlines' ? headlineOptions() : STYLE_CATALOG[group];
    const chosen = { edits: s.edit, headlines: s.headline, captions: s.captions,
                     ganchoFx: s.ganchoEfeito || '' }[group];
    const elAtivo = formatoEl(s);
    const hlAtivo = headlineEl(s);
    grid.innerHTML = '';
    for (const op of opts) {
      let off = PORTED[group] && !PORTED[group].has(op.id);
      let offMsg = 'ainda não disponível';
      if (group === 'edits' && EDIT_ELEMENTS.includes(op.id)) {
        const trava = elLocked(op, s, o.keys);
        if (trava) { off = true; offMsg = trava.split('\n')[0]; }
      }
      if (!off && indisp[op.id] && (group === 'edits' || group === 'headlines')) {
        off = true; offMsg = indisp[op.id];
      }
      const on = group === 'edits'
        ? (EDIT_ELEMENTS.includes(op.id) ? op.id === elAtivo : !elAtivo && op.id === chosen)
        : group === 'headlines'
          ? (HEADLINE_ELEMENTS.includes(op.id) ? op.id === hlAtivo : !hlAtivo && op.id === chosen)
          : op.id === chosen;
      const card = el('div', `opt${op.priv ? ' salvo' : ''}${on ? ' on' : ''}${off ? ' unavailable' : ''}`, grid);
      card.dataset.group = group;
      card.dataset.id = op.id;
      card.tabIndex = off ? -1 : 0;
      card.setAttribute('role', 'radio');
      card.setAttribute('aria-checked', on ? 'true' : 'false');
      card.setAttribute('aria-label', op.name || op.id || 'Nenhum');
      card.title = off ? offMsg : (op.name || '');
      const prev = el('div', `ave-cartao ${tipoCartao(op)}`, card);
      const step = montarCartao(prev, op);
      if (step) steps.push(step);
      if (op.mock) el('div', 'opt-name', card).textContent = op.name;
      else if (op.priv) el('div', 'opt-name salvo-nome', card).textContent = op.name;
      el('div', 'opt-mark', card);
    }
  }

  /* Os liga/desliga de Efeitos, Movimento e Trilha — os chips do editor. */
  function chips(row, L) {
    const s = st();
    for (const id of L.elements) {
      const e = STYLE_CATALOG.elements.find((x) => x.id === id);
      if (!e) continue;
      const trava = elLocked(e, s, o.keys);
      const on = !!s.elements[e.id] && !trava;
      const b = el('div', `chk${on ? ' on' : ''}${trava ? ' locked' : ''}`, row);
      b.dataset.id = e.id;
      b.tabIndex = 0;
      b.setAttribute('role', 'checkbox');
      b.setAttribute('aria-checked', on ? 'true' : 'false');
      if (trava) b.title = trava.split('\n')[0];
      el('div', 'chk-box', b);
      el('div', 'chk-ico', b).innerHTML = e.icon || '';
      el('div', 'chk-name', b).textContent = e.name;
    }
  }

  function corpoCta(body) {
    const s = st();
    if (!s.cta) s.cta = { modelo: '', arroba: '' };
    const g = el('div', 'dep-group', body);
    el('span', 'group-title', el('div', 'group-head', g)).textContent = 'CTA — fecho do vídeo';
    const grid = el('div', 'opt-grid cta-grid', g);
    const atual = s.cta.modelo || '';
    for (const m of CTA_MODELOS) {
      const card = el('div', `opt${m.id === atual ? ' on' : ''}`, grid);
      card.dataset.cta = m.id;
      card.tabIndex = 0;
      card.setAttribute('role', 'radio');
      card.setAttribute('aria-checked', m.id === atual ? 'true' : 'false');
      if (m.title) card.title = m.title;
      ctaMock(m.id, el('div', 'ave-cartao frame cta-prev', card),
              { arroba: ctaArroba(s, o.brand), accent: s.accent || ACCENT_DEFAULT });
      el('div', 'opt-name', card).textContent = m.name;
      el('div', 'opt-mark', card);
    }
    const m = CTA_MODELOS.find((x) => x.id === atual);
    if (!m || !m.id) return;
    el('div', 'cta-nota', g).textContent = 'Entra no fim do vídeo. Tempo e posição finos, no editor.';
    const lab = el('label', 'ave-campo', g);
    el('span', '', lab).textContent = 'Perfil (@)';
    const inp = el('input', '', lab);
    inp.type = 'text';
    inp.id = `${pre}-arroba`;
    inp.spellcheck = false;
    inp.placeholder = ((o.brand || {}).instagram || '@seuperfil');
    inp.value = s.cta.arroba || '';
    inp.dataset.campo = 'arroba';
    if (m.foto) {
      el('div', 'cta-nota', g).textContent = `${m.name} usa a foto do perfil salva no editor do Avelin`
        + ' (aba CTA). Sem foto salva, a geração recusa este modelo.';
    }
  }

  /* SEM CHAT NO CIRCUITO: o texto, as cores e a família da headline são
     escolhidos aqui (no editor, pela conversa). As marcas são as do render
     (compose_shortform.hl_marcas): "/" quebra, "/ /" dá mais espaço, "+"/"-"
     no começo da linha = ±10% de corpo por sinal. */
  function camposHeadline(body) {
    const s = st();
    const g = el('div', 'dep-group ave-hl-campos', body);
    el('span', 'group-title', el('div', 'group-head', g)).textContent = 'Texto e cores da headline';
    const caixinha = !!s.elements.caixinha;
    const lab = el('label', 'ave-campo ave-campo-texto', g);
    el('span', '', lab).textContent = s.elements.noticia ? 'Texto da manchete' : 'Texto da headline';
    const ta = el('textarea', '', lab);
    ta.id = `${pre}-hl-texto`;
    ta.rows = 2;
    ta.dataset.campo = 'headlineText';
    ta.value = s.headlineText || '';
    ta.placeholder = 'Ex.: Falta de dinheiro? / / ++AMBIÇÃO';
    ta.disabled = caixinha || (!s.headline && !s.elements.noticia);
    el('div', 'ave-dica', g).innerHTML = '<b>/</b> quebra a linha · <b>/ /</b> dá mais espaço · '
      + '<b>+</b> ou <b>-</b> no começo da linha: ±10% no tamanho (cada sinal)';
    if (caixinha) {
      const lp = el('label', 'ave-campo ave-campo-texto', g);
      el('span', '', lp).textContent = 'Pergunta da caixinha';
      const tp = el('textarea', '', lp);
      tp.id = `${pre}-caixa`;
      tp.rows = 2;
      tp.dataset.campo = 'caixaPergunta';
      tp.value = s.caixaPergunta || '';
      tp.placeholder = 'Ex.: Qual é a sua maior dúvida sobre dinheiro?';
    }
    const linha = el('div', 'ave-cores', g);
    const cor = (rot, campo, val) => {
      const l = el('label', 'ave-cor', linha);
      const i = el('input', '', l);
      i.type = 'color';
      i.id = `${pre}-${campo}`;
      i.dataset.campo = campo;
      i.value = (normHex(val) || '#FFFFFF').toLowerCase();
      el('span', '', l).textContent = rot;
    };
    cor('Cor principal', 'textColor', s.textColor);
    cor('Cor de destaque', 'accent', s.accent || ACCENT_DEFAULT);
    const fonte = (rot, campo, val) => {
      const l = el('label', 'ave-campo ave-fonte', linha);
      el('span', '', l).textContent = rot;
      const sel = el('select', '', l);
      sel.id = `${pre}-${campo}`;
      sel.dataset.campo = campo;
      const grupos = {};
      for (const f of allFonts()) (grupos[f.k || 'outras'] ||= []).push(f.n);
      const ROT = { display: 'Sem serifa', serif: 'Serifa', manuscrita: 'Manuscrita',
                    local: 'Suas fontes', outras: 'Outras' };
      for (const [k, nomes] of Object.entries(grupos)) {
        const og = el('optgroup', '', sel);
        og.label = ROT[k] || k;
        for (const n of nomes) {
          const op = el('option', '', og);
          op.value = n;
          op.textContent = n;
        }
      }
      sel.value = val;
    };
    fonte('Fonte', 'fontMain', s.fontMain || FONT_MAIN_DEF);
    // a segunda família só existe nos layouts que a usam — fora deles seria
    // um controle que não muda nada no vídeo
    if ((hlStyle(s.headline) || {}).fontRole) fonte('Fonte de destaque', 'fontAccent', s.fontAccent || FONT_ACCENT_DEF);
  }

  function render() {
    const topo = corpo.scrollTop;
    if (pararAnim) { pararAnim(); pararAnim = null; }
    cores();
    pintarAbas();
    corpo.innerHTML = '';
    corpo.dataset.camada = ativa;
    const L = LAYERS.find((x) => x.id === ativa) || LAYERS[0];
    const steps = [];
    if (L.soon) el('div', 'layer-soon', corpo).textContent = L.soon;
    else if (L.cta) corpoCta(corpo);
    else {
      if (L.id === 'headline' && o.camposHeadline) camposHeadline(corpo);
      for (const gid of L.groups || []) {
        const g = el('div', 'dep-group', corpo);
        el('span', 'group-title', el('div', 'group-head', g)).textContent = GROUP_TITLE[gid] || gid;
        const grid = el('div', 'opt-grid', g);
        grid.dataset.grupo = gid;
        grid.setAttribute('role', 'radiogroup');
        radios(grid, gid, steps);
      }
      if (L.elements) chips(el('div', 'check-row', corpo), L);
    }
    pararAnim = animar(steps);
    requestAnimationFrame(() => { corpo.scrollTop = topo; });
  }

  // só os cartões de headline: o texto digitado aparece neles sem remontar o
  // campo onde se está digitando (o cursor não pode sumir no meio da frase)
  function redesenharHeadlines() {
    const grid = corpo.querySelector('.opt-grid[data-grupo="headlines"]');
    if (!grid) return;
    if (pararAnim) { pararAnim(); pararAnim = null; }
    const steps = [];
    radios(grid, 'headlines', steps);
    // os outros grupos da aba (efeito do gancho) continuam animando
    corpo.querySelectorAll('.opt-grid:not([data-grupo="headlines"])').forEach((g) => {
      radios(g, g.dataset.grupo, steps);
    });
    pararAnim = animar(steps);
  }

  function clique(e) {
    const s = st();
    const aba = e.target.closest('.ave-aba');
    if (aba) {
      ativa = aba.dataset.camada;
      corpo.scrollTop = 0;
      render();
      mudou('camada');
      return;
    }
    const ctaCard = e.target.closest('[data-cta]');
    if (ctaCard) {
      if (!s.cta) s.cta = { modelo: '', arroba: '' };
      s.cta.modelo = ctaCard.dataset.cta;
      render();
      mudou('cta');
      return;
    }
    const opt = e.target.closest('.opt:not(.ghost):not(.unavailable)');
    if (opt && opt.dataset.group) {
      delete s.estiloSalvo;
      const id = opt.dataset.id;
      if (opt.dataset.group === 'edits') {
        // FORMATO: um só — zera os de `elements` antes de ligar o escolhido
        for (const k of EDIT_ELEMENTS) s.elements[k] = (k === id);
        s.edit = EDIT_ELEMENTS.includes(id) ? 'limpa' : id;
        limpaConflitoZonaAlta(s, 'formato');
        render();
        mudou('formato');
        return;
      }
      if (opt.dataset.group === 'headlines') {
        // Caixinha/Notícia são opções do MESMO radio: uma escolha na zona alta
        for (const k of HEADLINE_ELEMENTS) s.elements[k] = (k === id);
        s.headline = HEADLINE_ELEMENTS.includes(id) ? '' : id;
        render();
        mudou('headline');
        return;
      }
      const key = { captions: 'captions', ganchoFx: 'ganchoEfeito' }[opt.dataset.group];
      if (key) s[key] = id;
      render();
      mudou(opt.dataset.group === 'captions' ? 'legenda' : 'gancho');
      return;
    }
    const chk = e.target.closest('.chk');
    if (chk) {
      const cat = STYLE_CATALOG.elements.find((x) => x.id === chk.dataset.id);
      const trava = cat && elLocked(cat, s, o.keys);
      if (trava) {
        // efeito travado pelo FORMATO guarda a escolha: trocar de formato a devolve
        if (!cat.efx) s.elements[chk.dataset.id] = false;
        avisa(trava);
        return;
      }
      s.elements[chk.dataset.id] = !s.elements[chk.dataset.id];
      render();
      mudou('elemento');
    }
  }
  function tecla(e) {
    if ((e.key === 'Enter' || e.key === ' ') && e.target.matches('.opt, .chk')) {
      e.preventDefault();
      e.target.click();
    }
  }
  function entrada(e) {
    const campo = e.target.dataset && e.target.dataset.campo;
    if (!campo) return;
    const s = st();
    const v = e.target.value;
    if (campo === 'arroba') {
      if (!s.cta) s.cta = { modelo: '', arroba: '' };
      s.cta.arroba = v.trim();
      mudou('cta');
    } else if (campo === 'headlineText' || campo === 'caixaPergunta') {
      s[campo] = v;
      mudou('texto');
      if (campo === 'headlineText') {
        clearTimeout(tTexto);
        tTexto = setTimeout(redesenharHeadlines, 260);
      }
    } else if (campo === 'textColor' || campo === 'accent') {
      s[campo] = (normHex(v) || v).toUpperCase();
      cores();
      mudou('cor');
    } else if (campo === 'fontMain' || campo === 'fontAccent') {
      s[campo] = v;
      ensureFonts([v]);
      if (e.type === 'change') redesenharHeadlines();
      mudou('fonte');
    }
  }
  host.addEventListener('click', clique);
  host.addEventListener('keydown', tecla);
  host.addEventListener('input', entrada);
  host.addEventListener('change', entrada);
  render();
  return {
    render,
    camada(id) { if (LAYERS.some((L) => L.id === id)) { ativa = id; corpo.scrollTop = 0; render(); } },
    ativa: () => ativa,
    destruir() {
      if (pararAnim) pararAnim();
      clearTimeout(tTexto);
      host.removeEventListener('click', clique);
      host.removeEventListener('keydown', tecla);
      host.removeEventListener('input', entrada);
      host.removeEventListener('change', entrada);
      host.innerHTML = '';
      host.classList.remove('ave-painel');
    },
  };
}

/* ---------- a camada local (styles.local.js) ----------
 * No EDITOR quem instala é a linha AVELIN-OVERLAY do app.js — o gancho que o
 * overlay.py põe e tira —, e este módulo carrega ANTES do styles.local.js, então
 * aqui não acontece nada lá. Numa página que carrega o styles.local.js PRIMEIRO
 * (a galeria), a instalação sai daqui. O `install` confere o id antes de
 * inserir, então chamar duas vezes nunca duplica. */
function instalarLocal() {
  if (window.AVELIN_LOCAL) window.AVELIN_LOCAL.install({ STYLE_CATALOG, CAP_BUILDERS, ACCENT_USERS });
}
instalarLocal();

window.AVE_ESTILOS = {
  // ambiente e carga
  configurar, contexto: ctxDe, carregar, pronto: carregar, garantirRecursos,
  variants: () => VARS, setVariants: (v) => { VARS = v; },
  carregarFontesLocais, fontesLocais: () => LOCAL_FONTS,
  carregarLegendasPrivadas, instalarLocal,
  // dados do catálogo
  STYLE_CATALOG, CATALOG: STYLE_CATALOG, PAL, PAL_IDS, CARTELAS, CT_IDS, CARTELA_BANDA_IDS,
  PORTED, EDIT_ELEMENTS, HEADLINE_ELEMENTS, LAYERS, GROUP_TITLE, CTA_MODELOS,
  CAP_CSS, POP_GRUPO, CAP_ANCHOR, GANCHO_SEC, HOOK_LIM, STATIC_VARIANTS,
  ACCENT_DEFAULT, ACCENT_USERS, FONT_MAIN_DEF, FONT_ACCENT_DEF,
  CAP_TEXT, HEADLINE_TEXT, HL_MIN, FPS_REF,
  // utilidades puras
  el, semMarcas, normHex, trioRGB, sobreAccent, shadeHex, accentName,
  bez, easeOutCubic, easeStack, clamp01,
  // fontes e medida
  gfonts, allFonts, GF, isLocal, nearestWeight, cssFamily, gfontHref, ensureBundled, ensureFonts,
  measureType, hlWidth, hlLines, hlWrap, hlUpper, hlHeroIndex, hlKs, hlWeight, hlFamily, hlFit,
  hlHeroSize, paintHook, hlStyle, capVariant, capOffset, capBottom,
  // cartões
  CAP_BUILDERS, montarCartao, tipoCartao,
  buildKaraokeDemo, buildStackedDemo, buildScatterDemo, buildStaticDemo, buildCapCutDemo,
  buildPalavraDemo, vestirPal, buildHeadline, buildCartelaDemo, buildHeadlineDemo,
  ctaMock, ctaArroba,
  // ao vivo
  liveCss, montarLegendaViva, montarHeadlineViva, hookAjuste, applyCapDy,
  // regras e pedido
  defaultStyle, limpaConflitoZonaAlta, elLocked, styleName, editOptions, headlineOptions,
  formatoEl, formatoName, headlineEl, headlineName, accentUsed, payloadEstilo,
  // o painel inteiro, para quem não é o editor (a galeria de cortes)
  montarPainel, ICONES_CAMADA,
  // laço
  animar, parar,
};
})();

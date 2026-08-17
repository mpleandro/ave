/* Estilo REVELAR — tempos da varredura, compartilhados entre a prévia do
 * editor e a composição HyperFrames. Par de `revelar.css`.
 *
 * OS NÚMEROS SÃO MEDIDOS. Saíram do `ADBE_Text_Percent_Start_0_0` dos pacotes
 * de animação do CapCut instalado, via `helpers/capcut_captions.py`.
 */
(function (root) {
  'use strict';

  var TIMING = {
    LEAD: 0.0667,     // espera antes de a varredura começar
    SWEEP: 1.7333,    // 67ms → 1800ms
    HOLD: 0.4,        // 1800ms → 2200ms, sustentando em 100%
    BEZ: [0.0619, 0, 0.2194, 0.8172],
  };
  TIMING.TOTAL = TIMING.LEAD + TIMING.SWEEP + TIMING.HOLD;

  function clamp01(n) { return n < 0 ? 0 : n > 1 ? 1 : n; }

  /* Mesmo resolvedor de bezier do POP, pela mesma razão: o `x` do bezier não é
     o tempo, então achar `y(t)` exige inverter `x` antes. Duplicado de
     propósito — cada estilo é um arquivo autossuficiente, e um utilitário
     compartilhado criaria uma quarta coisa para carregar nas duas pontas. */
  function bezierY(b, x) {
    var x1 = b[0], y1 = b[1], x2 = b[2], y2 = b[3];
    var lo = 0, hi = 1, t = x, i, u, cx;
    for (i = 0; i < 24; i++) {
      t = (lo + hi) / 2;
      u = 1 - t;
      cx = 3 * u * u * t * x1 + 3 * u * t * t * x2 + t * t * t;
      if (cx > x) hi = t; else lo = t;
    }
    u = 1 - t;
    return 3 * u * u * t * y1 + 3 * u * t * t * y2 + t * t * t;
  }

  /* Fração revelada a `tRel` segundos do início da linha. Função PURA. */
  function revealAt(tRel) {
    if (tRel <= TIMING.LEAD) return 0;
    var p = clamp01((tRel - TIMING.LEAD) / TIMING.SWEEP);
    return bezierY(TIMING.BEZ, p);
  }

  function lineDuration() { return TIMING.TOTAL; }

  /* A fração revelada de UMA palavra, dada a posição dela em CARACTERES.
     É a tradução literal do `Text_Percent_Start`: a varredura anda pelo texto
     em ordem de leitura, então a palavra que começa no caractere 12 de um
     total de 26 só começa a aparecer quando a revelação global passa de 12/26.
     Sem isto a máscara corta por posição na tela e as linhas de baixo aparecem
     antes de as de cima terminarem. */
  function wordReveal(tRel, charStart, charLen, charTotal) {
    if (!charLen || !charTotal) return 0;
    var global = revealAt(tRel) * charTotal;
    return clamp01((global - charStart) / charLen);
  }

  /* Os deslocamentos de cada palavra, em caracteres. O espaço conta: ele é
     tempo de varredura no original. */
  function wordOffsets(words) {
    var out = [], pos = 0, i;
    for (i = 0; i < words.length; i++) {
      out.push({ start: pos, len: words[i].length });
      pos += words[i].length + 1;
    }
    return { spans: out, total: pos > 0 ? pos - 1 : 0 };
  }

  function buildTimeline(rootEl, gsap, tl, scale) {
    var lines = rootEl.querySelectorAll('.ave-cap-line');
    for (var i = 0; i < lines.length; i++) {
      var line = lines[i];
      var start = parseFloat(line.getAttribute('data-start')) || 0;
      var spans = line.querySelectorAll('span');
      var palavras = [];
      for (var k = 0; k < spans.length; k++) palavras.push(spans[k].textContent || '');
      var off = wordOffsets(palavras);
      for (var j = 0; j < spans.length; j++) {
        /* Cada palavra tem a SUA janela de tempo dentro da varredura global —
           calculada aqui e não por callback, porque tween declarativo em tempo
           absoluto é seekable e callback não é. */
        var t0 = TIMING.LEAD + invRevealAt(off.spans[j].start / off.total);
        var t1 = TIMING.LEAD + invRevealAt((off.spans[j].start + off.spans[j].len) / off.total);
        tl.fromTo(spans[j], { '--rev-w': 0 },
          { '--rev-w': 1, duration: Math.max(0.02, t1 - t0), ease: 'none' },
          start + t0);
      }
    }
    return tl;
  }

  /* O tempo em que a varredura global atinge `frac` — a inversa de revealAt.
     Por busca binária: o bezier não tem inversa fechada, e uma tabela fixa
     erraria justamente na cauda longa, que é onde este efeito vive. */
  function invRevealAt(frac) {
    var lo = 0, hi = TIMING.SWEEP, m, i;
    for (i = 0; i < 24; i++) {
      m = (lo + hi) / 2;
      if (revealAt(TIMING.LEAD + m) < frac) lo = m; else hi = m;
    }
    return (lo + hi) / 2;
  }

  root.AVE_REVELAR = {
    TIMING: TIMING,
    bezierY: bezierY,
    revealAt: revealAt,
    wordReveal: wordReveal,
    wordOffsets: wordOffsets,
    lineDuration: lineDuration,
    buildTimeline: buildTimeline,
  };
})(typeof window !== 'undefined' ? window : this);

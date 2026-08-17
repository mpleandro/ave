/* Estilo POP — tempos e movimento, compartilhados entre a prévia do editor e a
 * composição HyperFrames. Par de `pop.css`.
 *
 * Script clássico de propósito (nada de `import`), como o karaokê: a prévia é
 * servida como script simples e a composição roda em página estática.
 *
 * OS NÚMEROS SÃO MEDIDOS, não escolhidos. Saíram do `ADBE_Scale_0_1` dos
 * pacotes de animação do CapCut instalado, via `helpers/capcut_captions.py`.
 * Mexer neles aqui é mexer na fidelidade ao original — se for para inventar um
 * ritmo próprio, o lugar é um estilo novo, não este.
 */
(function (root) {
  'use strict';

  var TIMING = {
    /* Os dois trechos do estouro, em segundos, com o bezier de cada um.
       `to` é a escala ao FIM do trecho (1.2 = 120%). */
    STAGES: [
      { at: 0, dur: 0.215, to: 1.2, bez: [0.1667, 0.1667, 0.6667, 1] },
      { at: 0.215, dur: 0.188, to: 1.0, bez: [0.0507, 0.3113, 0.6667, 1] },
    ],
    TOTAL: 0.403,
    STEP: 0.16,   // atraso entre unidades quando o agrupamento é por palavra
    HOLD: 0.6,    // sobra depois da última unidade, antes de a linha sair
  };

  /* Bezier cúbico resolvido por bisseção — o mesmo método que o motor do
     CapCut usa no Lua dele, e pela mesma razão: o `x` do bezier não é o tempo,
     então achar `y(t)` exige inverter `x` primeiro. Aproximar por uma curva
     pronta (easeOutBack e afins) erra justamente no overshoot, que é o efeito. */
  function bezierY(b, x) {
    var x1 = b[0], y1 = b[1], x2 = b[2], y2 = b[3];
    var lo = 0, hi = 1, t = x, i, u;
    for (i = 0; i < 24; i++) {
      t = (lo + hi) / 2;
      u = 1 - t;
      var cx = 3 * u * u * t * x1 + 3 * u * t * t * x2 + t * t * t;
      if (cx > x) hi = t; else lo = t;
    }
    u = 1 - t;
    return 3 * u * u * t * y1 + 3 * u * t * t * y2 + t * t * t;
  }

  function clamp01(n) { return n < 0 ? 0 : n > 1 ? 1 : n; }

  /* Estado de UMA unidade a `tRel` segundos do início da linha.
     Função PURA: mesmo tempo, mesmo resultado — é o que torna o seek do
     renderer confiável, e o motivo de não haver Math.random() aqui. */
  function unitState(tRel, index, step) {
    var t = tRel - index * (step == null ? TIMING.STEP : step);
    if (t <= 0) return { scale: 0, opacity: 0 };
    var s = TIMING.STAGES;
    if (t < s[1].at) {
      var p = bezierY(s[0].bez, clamp01(t / s[0].dur));
      return { scale: p * s[0].to, opacity: 1 };
    }
    if (t < TIMING.TOTAL) {
      var q = bezierY(s[1].bez, clamp01((t - s[1].at) / s[1].dur));
      return { scale: s[0].to + q * (s[1].to - s[0].to), opacity: 1 };
    }
    return { scale: 1, opacity: 1 };
  }

  /* Quantas unidades a linha tem, conforme o AGRUPAMENTO.
     É a única diferença entre "Multiline Combo", "Multi-Line" e "Bounce Out" —
     os três têm a MESMA curva; muda o que estoura junto. */
  function unitCount(nWords, grupo) {
    if (grupo === 'bloco') return 1;
    if (grupo === 'linha') return 1;
    return nWords;
  }

  function lineDuration(nWords, grupo) {
    var n = unitCount(nWords, grupo);
    return (n - 1) * TIMING.STEP + TIMING.TOTAL + TIMING.HOLD;
  }

  /* Timeline GSAP da composição, a partir do DOM já emitido.
     Tween declarativo em tempo ABSOLUTO — seekable por construção, para o
     renderer poder saltar para um frame qualquer. */
  function buildTimeline(rootEl, gsap, tl, scale) {
    var grupo = (rootEl.className.match(/grupo-(\w+)/) || [])[1] || 'palavra';
    var lines = rootEl.querySelectorAll('.ave-cap-line');
    var s = TIMING.STAGES;
    for (var i = 0; i < lines.length; i++) {
      var line = lines[i];
      var start = parseFloat(line.getAttribute('data-start')) || 0;
      // por linha/bloco quem anima é o CONTÊINER; por palavra, cada span
      var alvos = grupo === 'palavra'
        ? line.querySelectorAll('span')
        : [line];
      for (var j = 0; j < alvos.length; j++) {
        var t0 = start + j * TIMING.STEP;
        tl.fromTo(alvos[j], { scale: 0, opacity: 0 },
          { scale: s[0].to, opacity: 1, duration: s[0].dur,
            ease: 'cubic-bezier(' + s[0].bez.join(',') + ')' }, t0);
        tl.to(alvos[j],
          { scale: s[1].to, duration: s[1].dur,
            ease: 'cubic-bezier(' + s[1].bez.join(',') + ')' }, t0 + s[1].at);
      }
    }
    return tl;
  }

  root.AVE_POP = {
    TIMING: TIMING,
    bezierY: bezierY,
    unitState: unitState,
    unitCount: unitCount,
    lineDuration: lineDuration,
    buildTimeline: buildTimeline,
  };
})(typeof window !== 'undefined' ? window : this);

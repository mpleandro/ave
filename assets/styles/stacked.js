/* Legenda EMPILHADO — tempos e movimento, compartilhados com a prévia.
 *
 * Cada palavra entra no seu tempo FALADO, não num passo fixo: o preparador de
 * deixas já grava `fromMs` por palavra, e usar isso é o que faz a pilha
 * acompanhar a fala em deixas curtas — um passo fixo estoura a deixa e as
 * últimas palavras nunca aparecem.
 *
 * Duas saídas, escolhidas pelo dado:
 *   abrupt   — a deixa some nos últimos 2 quadros. É o corte seco.
 *   blur_up  — sobe 55px dissolvendo em desfoque. Guardado para as viradas.
 */
(function (root) {
  'use strict';

  /* Reemitidas em TODO valor animado de filter.
   *
   * Animar `filter` SUBSTITUI o valor inteiro: terminar a entrada em
   * `blur(0px)` apagava a sombra declarada no CSS, e as palavras brancas
   * sumiam sobre fundo claro — visto numa camiseta branca, onde só o acento
   * laranja continuava legível. A sombra é contraste, não enfeite.
   *
   * A REFORÇADA (dupla) é da linha em Poppins 400 menor: o corte mais leve no
   * menor corpo é o que menos se sustenta sozinho. */
  var SHADOW = ' drop-shadow(0 5px 9px rgba(0,0,0,0.5))';
  var SHADOW_STRONG = ' drop-shadow(0 5px 10px rgba(0,0,0,0.55))'
                    + ' drop-shadow(0 2px 3px rgba(0,0,0,0.55))';

  var TIMING = {
    FPS_REF: 30,
    ENTER_FRAMES: 8,
    RISE: 46,        // subida da palavra, em px de referência
    BLUR_IN: 5,      // desfoque de onde a palavra resolve
    EXIT_FRAMES: 7,
    EXIT_UP: 55,     // quanto a deixa sobe na saída blur_up
    EXIT_BLUR: 14,
  };
  TIMING.ENTER = TIMING.ENTER_FRAMES / TIMING.FPS_REF;
  TIMING.EXIT = TIMING.EXIT_FRAMES / TIMING.FPS_REF;

  function buildTimeline(rootEl, gsap, tl, scale) {
    scale = scale || 1;
    var cues = rootEl.querySelectorAll('.stk-cue');
    for (var c = 0; c < cues.length; c++) {
      var cue = cues[c];
      var start = parseFloat(cue.getAttribute('data-start')) || 0;
      var dur = parseFloat(cue.getAttribute('data-duration')) || 0;
      var end = start + dur;
      var blurUp = cue.getAttribute('data-exit') === 'blur_up';
      var exitAt = Math.max(start, end - (blurUp ? TIMING.EXIT : 2 / TIMING.FPS_REF));
      var spans = cue.querySelectorAll('span[data-at]');

      for (var i = 0; i < spans.length; i++) {
        var sp = spans[i];
        var at = parseFloat(sp.getAttribute('data-at'));
        if (isNaN(at) || at < start) at = start;
        // a entrada encolhe para caber antes da saída; nunca some inteira,
        // senão a palavra pisca em um quadro e lê como falha
        var enter = Math.max(2 / TIMING.FPS_REF, Math.min(TIMING.ENTER, exitAt - at));
        if (at >= exitAt) at = Math.max(start, exitAt - enter);

        var sh = sp.classList.contains('s1') ? SHADOW_STRONG : SHADOW;
        tl.fromTo(sp,
          { opacity: 0, y: TIMING.RISE * scale,
            filter: 'blur(' + TIMING.BLUR_IN * scale + 'px)' + sh },
          { opacity: 1, y: 0, filter: 'blur(0px)' + sh,
            duration: enter, ease: 'expo.out' },
          at);
      }

      if (blurUp) {
        tl.to(cue, {
          opacity: 0,
          y: -TIMING.EXIT_UP * scale,
          filter: 'blur(' + TIMING.EXIT_BLUR * scale + 'px)',
          duration: TIMING.EXIT, ease: 'none',
        }, exitAt);
      } else {
        tl.to(cue, { opacity: 0, duration: 1 / TIMING.FPS_REF, ease: 'none' }, exitAt);
      }
    }
    return tl;
  }

  root.AVE_STACKED = { TIMING: TIMING, buildTimeline: buildTimeline };
})(typeof window !== 'undefined' ? window : this);

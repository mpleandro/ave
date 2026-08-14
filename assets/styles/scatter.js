/* Legenda DISPERSO — tempos e movimento, compartilhados com a prévia do editor.
 *
 * NUNCA Math.random(). As posições irregulares das linhas saem de um hash do
 * índice da deixa. Um aleatório de verdade re-sorteia o layout a cada quadro e
 * o texto treme — e no HyperFrames faria pior: dois renders do mesmo projeto
 * sairiam diferentes, matando o determinismo que se ganhou na troca de motor.
 */
(function (root) {
  'use strict';

  var TIMING = {
    FPS_REF: 30,
    STEP: 0.22,        // atraso entre uma palavra e a seguinte
    ENTER_FRAMES: 7,   // entrada da palavra comum
    HI_ENTER_FRAMES: 10, // entrada da destacada, mais lenta
    HOLD: 0.9,
    EXIT_FRAMES: 8,
    BLUR_IN: 26,       // desfoque de onde a destacada resolve
    BLUR_OUT: 30,      // desfoque para onde ela se dissolve
  };
  TIMING.ENTER = TIMING.ENTER_FRAMES / TIMING.FPS_REF;
  TIMING.HI_ENTER = TIMING.HI_ENTER_FRAMES / TIMING.FPS_REF;
  TIMING.EXIT = TIMING.EXIT_FRAMES / TIMING.FPS_REF;

  /* Mesmo hash da prévia e do compositor: seno truncado. Determinístico por
     índice, então a mesma deixa sempre cai no mesmo lugar. */
  function hash(n) {
    var x = Math.sin(n * 127.1 + 311.7) * 43758.5453;
    return x - Math.floor(x);
  }

  function buildTimeline(rootEl, gsap, tl, scale) {
    var cues = rootEl.querySelectorAll('.scat-cue');
    for (var c = 0; c < cues.length; c++) {
      var cue = cues[c];
      var start = parseFloat(cue.getAttribute('data-start')) || 0;
      var end = start + (parseFloat(cue.getAttribute('data-duration')) || 0);
      var spans = cue.querySelectorAll('span');
      var exitAt = Math.max(start, end - TIMING.EXIT);

      for (var i = 0; i < spans.length; i++) {
        var sp = spans[i];
        var hi = sp.classList.contains('hi');
        // tempo absoluto vindo do dado: a palavra aparece quando é falada
        var at = parseFloat(sp.getAttribute('data-at'));
        if (isNaN(at)) at = start + i * TIMING.STEP;
        if (at < start) at = start;
        if (at >= exitAt) at = Math.max(start, exitAt - 0.01);
        var dur = hi ? TIMING.HI_ENTER : TIMING.ENTER;

        // palavra comum: só aparece. Sem deslocamento, de propósito.
        tl.fromTo(sp, { opacity: 0 }, { opacity: 1, duration: dur, ease: 'cubic.out' }, at);
        if (hi) {
          tl.fromTo(sp,
            { filter: 'blur(' + TIMING.BLUR_IN * scale + 'px)' },
            { filter: 'blur(0px)', duration: dur, ease: 'cubic.out' }, at);
        }
      }
      // a deixa inteira sai junto; só a destacada se dissolve em desfoque
      tl.to(spans, { opacity: 0, duration: TIMING.EXIT, ease: 'none' }, exitAt);
      var his = cue.querySelectorAll('span.hi');
      if (his.length) {
        tl.to(his, {
          filter: 'blur(' + TIMING.BLUR_OUT * scale + 'px)',
          duration: TIMING.EXIT, ease: 'none',
        }, exitAt);
      }
    }
    return tl;
  }

  root.AVE_SCATTER = { TIMING: TIMING, hash: hash, buildTimeline: buildTimeline };
})(typeof window !== 'undefined' ? window : this);

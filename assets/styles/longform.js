/* Camadas do longform — tempos e movimento.
 *
 * Cada elemento entra, segura e sai dentro da SUA janela, lendo início e
 * duração do próprio bloco. Nada depende de um relógio global, o que é o que
 * vai permitir arrastar qualquer um deles no editor sem recalcular os outros.
 */
(function (root) {
  'use strict';

  var FPS = 30;
  var T = {
    BROLL_IN: 10 / FPS, BROLL_OUT: 10 / FPS, KEN_BURNS: 1.06,
    LOWER_IN: 12 / FPS, LOWER_OUT: 10 / FPS, LOWER_X: -40,
    CHAPTER_IN: 14 / FPS, CHAPTER_OUT: 12 / FPS, CHAPTER_Y: 30, CHAPTER_RULE: 120,
    CALLOUT_IN: 8 / FPS, CALLOUT_OUT: 8 / FPS,
  };

  function win(el) {
    var s = parseFloat(el.getAttribute('data-start')) || 0;
    var d = parseFloat(el.getAttribute('data-duration')) || 0;
    return { s: s, d: d, e: s + d };
  }

  function buildTimeline(rootEl, gsap, tl, scale) {
    scale = scale || 1;

    rootEl.querySelectorAll('.ave-lf-broll').forEach(function (el) {
      var w = win(el);
      tl.fromTo(el, { opacity: 0 }, { opacity: 1, duration: T.BROLL_IN, ease: 'none' }, w.s);
      tl.to(el, { opacity: 0, duration: T.BROLL_OUT, ease: 'none' },
            Math.max(w.s, w.e - T.BROLL_OUT));
      // Ken-Burns só na IMAGEM: aplicar num vídeo brigaria com o movimento que
      // ele já tem, e o resultado é enjoo, não vida.
      if (el.tagName === 'IMG') {
        tl.fromTo(el, { scale: 1 }, { scale: T.KEN_BURNS, duration: w.d, ease: 'none' }, w.s);
      }
    });

    rootEl.querySelectorAll('.ave-lf-lower').forEach(function (el) {
      var w = win(el);
      tl.fromTo(el, { opacity: 0, x: T.LOWER_X * scale },
                { opacity: 1, x: 0, duration: T.LOWER_IN, ease: 'cubic.out' }, w.s);
      tl.to(el, { opacity: 0, duration: T.LOWER_OUT, ease: 'none' },
            Math.max(w.s, w.e - T.LOWER_OUT));
    });

    rootEl.querySelectorAll('.ave-lf-chapter').forEach(function (el) {
      var w = win(el);
      var rule = el.querySelector('.lf-rule');
      tl.fromTo(el, { opacity: 0, y: T.CHAPTER_Y * scale },
                { opacity: 1, y: 0, duration: T.CHAPTER_IN, ease: 'cubic.out' }, w.s);
      if (rule) {
        tl.fromTo(rule, { width: 0 },
                  { width: T.CHAPTER_RULE * scale, duration: T.CHAPTER_IN, ease: 'cubic.out' }, w.s);
      }
      tl.to(el, { opacity: 0, duration: T.CHAPTER_OUT, ease: 'none' },
            Math.max(w.s, w.e - T.CHAPTER_OUT));
    });

    rootEl.querySelectorAll('.ave-lf-callout').forEach(function (el) {
      var w = win(el);
      // `back.out` dá o repuxo do chip ao aparecer; é o que faz ele ler como
      // etiqueta colada e não como texto que apareceu
      tl.fromTo(el, { opacity: 0, scale: 0.01 },
                { opacity: 1, scale: 1, duration: T.CALLOUT_IN, ease: 'back.out(1.6)' }, w.s);
      tl.to(el, { opacity: 0, duration: T.CALLOUT_OUT, ease: 'none' },
            Math.max(w.s, w.e - T.CALLOUT_OUT));
    });

    return tl;
  }

  root.AVE_LONGFORM = { T: T, buildTimeline: buildTimeline };
})(typeof window !== 'undefined' ? window : this);

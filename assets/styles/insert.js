/* INSERTS — entrada, Ken-Burns e saída.
 *
 * O crescimento é da IMAGEM, o cartão fica parado: escalar o cartão inteiro
 * mexeria na sombra e nos cantos arredondados junto, e a moldura passaria a
 * respirar em vez de segurar a imagem.
 */
(function (root) {
  'use strict';
  var FPS = 30;
  var T = { IN: 9 / FPS, OUT: 7 / FPS, FROM_SCALE: 0.92, FROM_Y: 26, GROW: 1.08 };

  function buildTimeline(rootEl, gsap, tl, scale) {
    scale = scale || 1;
    rootEl.querySelectorAll('.ave-insert').forEach(function (el) {
      var s = parseFloat(el.getAttribute('data-start')) || 0;
      var d = parseFloat(el.getAttribute('data-duration')) || 0;
      var img = el.querySelector('img');
      tl.fromTo(el, { opacity: 0, scale: T.FROM_SCALE, y: T.FROM_Y * scale },
                { opacity: 1, scale: 1, y: 0, duration: T.IN, ease: 'cubic.out' }, s);
      if (img) tl.fromTo(img, { scale: 1 }, { scale: T.GROW, duration: d, ease: 'none' }, s);
      tl.to(el, { opacity: 0, duration: T.OUT, ease: 'none' }, Math.max(s, s + d - T.OUT));
    });
    return tl;
  }
  root.AVE_INSERT = { T: T, buildTimeline: buildTimeline };
})(typeof window !== 'undefined' ? window : this);

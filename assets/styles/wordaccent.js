/* Palavra em destaque — entra com um repuxo curto e sai limpa. */
(function (root) {
  'use strict';
  var FPS = 30;
  var T = { IN: 8 / FPS, OUT: 6 / FPS, FROM: 0.86 };

  function buildTimeline(rootEl, gsap, tl, scale) {
    rootEl.querySelectorAll('.ave-wordaccent').forEach(function (el) {
      var s = parseFloat(el.getAttribute('data-start')) || 0;
      var d = parseFloat(el.getAttribute('data-duration')) || 0;
      tl.fromTo(el, { opacity: 0, scale: T.FROM },
                { opacity: 1, scale: 1, duration: T.IN, ease: 'back.out(1.4)' }, s);
      tl.to(el, { opacity: 0, duration: T.OUT, ease: 'none' }, Math.max(s, s + d - T.OUT));
    });
    return tl;
  }
  root.AVE_WORDACCENT = { T: T, buildTimeline: buildTimeline };
})(typeof window !== 'undefined' ? window : this);

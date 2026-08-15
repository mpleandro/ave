/* PERSEGUIÇÃO DO OLHAR — o quadro segue os olhos enquanto está aproximado.
 *
 * Zoom e perseguição saem de UMA conta só, feita no compositor, e chegam aqui
 * como um caminho pronto. Não são duas animações: a translação depende do ponto
 * do rosto E do zoom daquele instante, então separá-las faria duas fontes
 * brigarem pelo mesmo transform e o enquadramento saltaria nos cortes.
 *
 * `transform-origin: 0 0` não é detalhe: a conta do original posiciona o ponto
 * do rosto em coordenadas absolutas do quadro. Com origem no centro, o mesmo
 * par de números aponta para outro lugar.
 *
 * Os quadros-chave são interpolados linearmente entre si — o caminho já vem
 * suavizado do rastreador, então amostrar a cada poucos quadros é
 * indistinguível de amostrar todos, e evita milhares de tweens.
 */
(function (root) {
  'use strict';

  function buildTimeline(el, gsap, tl, path) {
    if (!el || !path || !path.length) return tl;
    el.style.transformOrigin = '0 0';

    // primeiro estado, antes de qualquer movimento
    tl.set(el, { x: path[0][1], y: path[0][2], scale: path[0][3] }, 0);

    for (var i = 1; i < path.length; i++) {
      var t0 = path[i - 1][0];
      var p = path[i];
      var dur = p[0] - t0;
      // Salto de zoom no corte: duração zero vira `set`, senão o GSAP
      // interpolaria o corte seco e o enquadramento deslizaria de um take
      // para o outro.
      if (dur <= 1e-6) {
        tl.set(el, { x: p[1], y: p[2], scale: p[3] }, p[0]);
      } else {
        tl.to(el, { x: p[1], y: p[2], scale: p[3], duration: dur, ease: 'none' }, t0);
      }
    }
    return tl;
  }

  root.AVE_TRACKING = { buildTimeline: buildTimeline };
})(typeof window !== 'undefined' ? window : this);

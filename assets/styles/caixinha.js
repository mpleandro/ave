/* CAIXINHA DE PERGUNTAS — sem animação.
 *
 * A caixa entra já colada no lugar (fixa, sem gesto de entrada) e some no
 * corte quando a janela do clip termina — não há tween de entrada nem de
 * saída. Quem decide quando ela aparece e some é `data-start`/`data-duration`
 * do próprio clip, não este arquivo; o CSS já a desenha no estado final.
 */
(function (root) {
  'use strict';

  function buildTimeline(rootEl, gsap, tl) {
    return tl;
  }

  root.AVE_CAIXA = { buildTimeline: buildTimeline };
})(typeof window !== 'undefined' ? window : this);

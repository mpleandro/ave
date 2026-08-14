/* Câmera dinâmica e flash na transição — compartilhado com a prévia do editor.
 *
 * Três partes independentes, cada uma um item da aba Estilo:
 *   zoomCuts  — zoom duro que MUDA a cada corte (~1.10–1.22, ciclando)
 *   zoomAuto  — aproximação lenta DENTRO de cada segmento (+pushIn ao longo dele)
 *   tracking  — perseguição do olhar (exige dado de rastreio de rosto; ainda não)
 *
 * O que faz um plano fixo parecer editado é o zoomCuts: sem ele o vídeo é uma
 * câmera parada por um minuto inteiro. Os três são separáveis de propósito —
 * quem desliga tudo perde isso, e vale dizer antes de obedecer.
 *
 * Tudo em tween declarativo com tempo absoluto: o renderer salta para um frame
 * qualquer e o GSAP resolve o estado. Nada de animação por callback, nada de
 * aleatório — os dois quebram o seek e, com ele, o determinismo.
 */
(function (root) {
  'use strict';

  function buildCamera(el, gsap, tl, opts) {
    var segs = opts.segments || [];
    var zooms = opts.zooms || [1];
    var push = opts.pushIn || 0;
    if (!el || !segs.length) return tl;

    for (var i = 0; i < segs.length; i++) {
      var s = segs[i];
      var z = opts.zoomCuts ? zooms[i % zooms.length] : 1;
      var dur = Math.max(0.001, s.end - s.start);
      if (opts.zoomAuto && push) {
        // set + to no MESMO instante: o set fixa o ponto de partida do segmento
        // (senão o tween herda a escala em que o anterior parou e a aproximação
        // vira um acúmulo que estoura no fim do vídeo)
        tl.set(el, { scale: z }, s.start);
        tl.to(el, { scale: z + push, duration: dur, ease: 'none' }, s.start);
      } else {
        tl.set(el, { scale: z }, s.start);
      }
    }
    return tl;
  }

  /* O feixe ANTECIPA o corte em 2 quadros. Começando no quadro do corte, o olho
     vê a imagem mudar e só depois a luz — lê como flash atrasado. Antecipando,
     a luz parece a causa. */
  var FLASH_LEAD_FRAMES = 2;

  function flashStart(at, fps) {
    return Math.max(0, at - FLASH_LEAD_FRAMES / (fps || 30));
  }

  root.AVE_CAMERA = {
    buildCamera: buildCamera,
    flashStart: flashStart,
    FLASH_LEAD_FRAMES: FLASH_LEAD_FRAMES,
  };
})(typeof window !== 'undefined' ? window : this);

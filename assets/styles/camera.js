/* Câmera dinâmica — compartilhada com a prévia do editor.
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

    // NAVEGAÇÃO: plano com `zoom` explícito (e opcionalmente `x`/`y` em px de
    // referência e `glide` em s) é uma POSIÇÃO de câmera, não um degrau do
    // ciclo. Com `glide` a câmera DESLIZA da posição anterior até esta — é o
    // vídeo ampliado "andando" entre trechos do quadro para abrir espaço a um
    // gráfico. A translação é grampeada para nunca revelar a borda do vídeo.
    var nav = segs.some(function (s) { return typeof s.zoom === 'number'; });
    if (nav) {
      var W = opts.width || 1080, H = opts.height || 1920;
      var ox = opts.originX == null ? 0.5 : opts.originX;
      var oy = opts.originY == null ? 0.5 : opts.originY;
      var clamp = function (v, lo, hi) { return Math.min(hi, Math.max(lo, v)); };
      var st = function (s) {
        var S = typeof s.zoom === 'number' ? Math.max(1, s.zoom) : 1;
        return {
          scale: S,
          x: clamp(s.x || 0, -(1 - ox) * W * (S - 1), ox * W * (S - 1)),
          y: clamp(s.y || 0, -(1 - oy) * H * (S - 1), oy * H * (S - 1))
        };
      };
      tl.set(el, st(segs[0]), 0);
      for (var k = 0; k < segs.length; k++) {
        var g = segs[k], to = st(g);
        var gl = Math.max(0, Math.min(g.glide || 0, g.end - g.start));
        if (k > 0 && gl > 0) {
          tl.fromTo(el, st(segs[k - 1]),
            Object.assign({}, to, { duration: gl, ease: g.ease || 'power3.inOut' }), g.start);
        } else {
          tl.set(el, to, g.start);
        }
        if (push && opts.zoomAuto && g.end - g.start - gl > 0.5) {
          tl.to(el, { scale: to.scale + push * 0.5, duration: g.end - g.start - gl, ease: 'none' },
                g.start + gl);
        }
      }
      return tl;
    }

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

  root.AVE_CAMERA = { buildCamera: buildCamera };
})(typeof window !== 'undefined' ? window : this);

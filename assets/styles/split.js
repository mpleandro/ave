/* TELA DIVIDIDA — troca de layout por janela.
 *
 * Corte SECO, sem fade: cada janela liga a arte e reenquadra o vídeo num único
 * instante, e desliga no fim. Por isso tudo aqui é `set`, nunca `to` — um tween
 * entre dois enquadramentos faria o rosto deslizar pelo quadro, que é o oposto
 * do efeito (o rosto é o que fica PARADO enquanto o resto muda).
 *
 * O reenquadramento por janela existe porque num corte multi-take a cabeça se
 * move: medido, ~170px entre tomadas. Um valor único para o vídeo inteiro corta
 * as tomadas altas e deixa um vão sob a costura nas baixas.
 */
(function (root) {
  'use strict';

  function buildTimeline(rootEl, gsap, tl, scale) {
    scale = scale || 1;
    var win = rootEl.querySelector('#vidwin');
    var vid = win && win.querySelector('video');
    var wins = rootEl.querySelectorAll('.ave-split-win');
    if (!win || !vid || !wins.length) return tl;

    for (var i = 0; i < wins.length; i++) {
      var w = wins[i];
      var start = parseFloat(w.getAttribute('data-start')) || 0;
      var dur = parseFloat(w.getAttribute('data-duration')) || 0;
      var art = w.querySelector('.ave-split-art');
      var seam = w.querySelector('.ave-split-seam');
      var zoom = parseFloat(w.getAttribute('data-zoom')) || 1;
      var focus = parseFloat(w.getAttribute('data-focus')) || 0;
      var vidTop = parseFloat(w.getAttribute('data-vid-top')) || 0;
      var vidH = parseFloat(w.getAttribute('data-vid-height')) || 0;

      // entra
      tl.set(win, { top: vidTop * scale, height: vidH * scale }, start);
      tl.set(vid, { scale: zoom, y: -focus * scale }, start);
      if (art) tl.set(art, { display: 'block' }, start);
      if (seam) tl.set(seam, { display: 'block' }, start);

      // sai — o quadro cheio volta e o vídeo perde o reenquadramento
      var end = start + dur;
      tl.set(win, { top: 0, height: '100%' }, end);
      tl.set(vid, { scale: 1, y: 0 }, end);
      if (art) tl.set(art, { display: 'none' }, end);
      if (seam) tl.set(seam, { display: 'none' }, end);
    }
    return tl;
  }

  root.AVE_SPLIT = { buildTimeline: buildTimeline };
})(typeof window !== 'undefined' ? window : this);

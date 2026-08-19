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

    // As dimensões da FONTE, para montar o quadro inteiro em vez de recortá-lo.
    // `videoWidth` só existe depois dos metadados; o fallback é a proporção 9:16
    // do short-form, que é o que este arquivo sempre desenhou.
    var srcW = vid.videoWidth || 1080;
    var srcH = vid.videoHeight || 1920;

    /* Legendas ancoradas no CENTRO (empilhado, disperso) não se resolvem com o
       `captionBottom`: converter a base em centro põe o bloco mais baixo do que
       se quer, e na tela dividida ele acaba na boca de quem fala. Elas têm
       deslocamento próprio por layout, aplicado na variável do contêiner. */
    var centred = rootEl.querySelector('.ave-stacked, .ave-scatter');
    var centreVar = centred && centred.classList.contains('ave-stacked')
      ? '--stk-offset-y' : '--scat-offset-y';
    var centreBase = centred
      ? getComputedStyle(centred).getPropertyValue(centreVar).trim() : '';

    for (var i = 0; i < wins.length; i++) {
      var w = wins[i];
      var start = parseFloat(w.getAttribute('data-start')) || 0;
      var dur = parseFloat(w.getAttribute('data-duration')) || 0;
      // Só a IMAGEM é acesa aqui. O vídeo (`.ave-split-media`) está sob o
      // relógio do HyperFrames pelos próprios `data-start`/`data-duration`, e
      // mexer no `display` dele daqui brigaria com o renderer.
      var art = w.querySelector('.ave-split-art');
      var seam = w.querySelector('.ave-split-seam');
      var zoom = parseFloat(w.getAttribute('data-zoom')) || 1;
      var focus = parseFloat(w.getAttribute('data-focus')) || 0;
      var vidTop = parseFloat(w.getAttribute('data-vid-top')) || 0;
      var vidH = parseFloat(w.getAttribute('data-vid-height')) || 0;

      // entra
      tl.set(win, { top: vidTop * scale, height: vidH * scale }, start);
      /* O QUADRO INTEIRO, DIMENSIONADO — não `object-fit: cover` mais transform.
       *
       * O comentário do split.css sempre descreveu o modelo certo ("um ponto
       * y_src desenha em (y_src - focus) * zoom"), mas o CSS fazia outra coisa:
       * `width/height: 100%` com `object-fit: cover` RECORTA a fonte para a
       * janela ANTES de qualquer transform. Numa janela de 1170px sobre uma
       * fonte de 1920, isso descarta 375px em cima e 375px embaixo de forma
       * permanente — e nenhum `focusY` traz de volta o que o cover jogou fora.
       *
       * Medido: numa filmagem com o cabelo em y≈38, a faixa cobria o rosto e
       * mexer no foco só empurrava o vídeo para baixo, abrindo tarja preta. O
       * pixel do cabelo não estava mal posicionado: não estava sendo desenhado.
       *
       * Agora o elemento É o quadro inteiro vezes o zoom, deslocado para que
       * `focus` pouse no topo da janela. É o mesmo modelo do projeto de origem
       * desta skill, e o que o texto acima sempre prometeu. */
      tl.set(vid, {
        width: srcW * zoom * scale,
        height: srcH * zoom * scale,
        left: -((srcW * zoom - srcW) / 2) * scale,
        top: -focus * zoom * scale,
        scale: 1, y: 0, objectFit: 'fill',
      }, start);
      if (art) tl.set(art, { display: 'block' }, start);
      if (seam) tl.set(seam, { display: 'block' }, start);
      var off = w.getAttribute('data-centre-offset');
      if (centred && off !== null) {
        var props = {}; props[centreVar] = off;
        tl.set(centred, props, start);
      }

      // sai — o quadro cheio volta e o vídeo perde o reenquadramento
      var end = start + dur;
      tl.set(win, { top: 0, height: '100%' }, end);
      // volta ao quadro cheio: as dimensões explícitas saem e o cover retorna
      tl.set(vid, { width: '100%', height: '100%', left: 0, top: 0,
                    scale: 1, y: 0, objectFit: 'cover' }, end);
      if (art) tl.set(art, { display: 'none' }, end);
      if (seam) tl.set(seam, { display: 'none' }, end);
      if (centred && off !== null && centreBase) {
        var back = {}; back[centreVar] = centreBase;
        tl.set(centred, back, end);
      }
    }
    return tl;
  }

  root.AVE_SPLIT = { buildTimeline: buildTimeline };
})(typeof window !== 'undefined' ? window : this);

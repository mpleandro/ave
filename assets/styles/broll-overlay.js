/* BROLL OVERLAY — linha do tempo das janelas de ênfase.
 *
 * O RITMO vem do dado, não daqui: o compositor mede a duração de cada janela
 * contra a fala e escreve `data-in` (entrada) e `data-stagger` (cadência dos
 * filhos). Este arquivo só executa — janela curta entra seca, janela longa
 * respira, e mudar a régua é mexer no compose, não em keyframes.
 *
 * O scrim é irmão da janela (`data-bo-scrim` aponta o id): escurece o a-roll
 * ANTES de o elemento surgir (metade da entrada), e devolve a luz na saída.
 */
(function (root) {
  'use strict';
  var OUT = 0.24;              /* saída fixa: acento é na entrada, não na volta */

  function buildTimeline(rootEl, gsap, tl) {
    rootEl.querySelectorAll('.ave-bo-win').forEach(function (el) {
      var s = parseFloat(el.getAttribute('data-start')) || 0;
      var d = parseFloat(el.getAttribute('data-duration')) || 0;
      var IN = parseFloat(el.getAttribute('data-in')) || 0.3;
      var STAG = parseFloat(el.getAttribute('data-stagger')) || 0.11;
      var end = s + d;

      var scrimId = el.getAttribute('data-bo-scrim');
      if (scrimId) {
        var scrim = rootEl.querySelector('#' + scrimId);
        if (scrim) {
          var dim = parseFloat(scrim.getAttribute('data-dim')) || 0.9;
          tl.fromTo(scrim, { opacity: 0 }, { opacity: dim, duration: IN / 2, ease: 'power1.out' }, s);
          tl.to(scrim, { opacity: 0, duration: OUT, ease: 'none' }, end - OUT);
        }
      }

      tl.fromTo(el, { opacity: 0 }, { opacity: 1, duration: IN / 2, ease: 'none' }, s);
      tl.to(el, { opacity: 0, duration: OUT, ease: 'none' }, end - OUT);

      /* palavras: sobem uma a uma, como o karaokê — mas maiores e mais duras */
      el.querySelectorAll('.ave-bo-words .bo-w').forEach(function (w, i) {
        tl.fromTo(w, { opacity: 0, y: 46, scale: 0.94 },
                  { opacity: 1, y: 0, scale: 1, duration: IN, ease: 'back.out(1.6)' },
                  s + i * STAG);
      });

      /* estatística: o número CONTA até o valor quando é numérico; o rótulo
         chega depois, quando o número já assentou */
      var val = el.querySelector('.ave-bo-stat .bo-num');
      if (val) {
        var target = parseFloat(val.getAttribute('data-count'));
        tl.fromTo(val.parentNode, { opacity: 0, scale: 0.8 },
                  { opacity: 1, scale: 1, duration: IN, ease: 'back.out(1.8)' }, s);
        if (!isNaN(target)) {
          var obj = { n: 0 };
          var dec = (val.getAttribute('data-count').split('.')[1] || '').length;
          tl.to(obj, {
            n: target, duration: Math.min(1.1, Math.max(0.5, d * 0.28)), ease: 'power2.out',
            onUpdate: function () { val.textContent = obj.n.toFixed(dec).replace('.', ','); },
          }, s + IN * 0.4);
        }
        var lab = el.querySelector('.ave-bo-stat .bo-label');
        if (lab) {
          tl.fromTo(lab, { opacity: 0, y: 24 },
                    { opacity: 1, y: 0, duration: IN, ease: 'power2.out' }, s + IN + STAG);
        }
      }

      /* etiquetas: entram da esquerda, uma por vez */
      el.querySelectorAll('.ave-bo-labels .bo-item').forEach(function (it, i) {
        tl.fromTo(it, { opacity: 0, x: -70 },
                  { opacity: 1, x: 0, duration: IN, ease: 'power3.out' },
                  s + i * Math.max(STAG, 0.14));
      });

      /* mídia: entrada de cartão + crescimento lento, o mesmo gesto do insert */
      var med = el.querySelector('.ave-bo-media');
      if (med) {
        tl.fromTo(med, { scale: 0.93, y: 24 },
                  { scale: 1, y: 0, duration: IN, ease: 'cubic.out' }, s);
        var mv = med.querySelector('video, img');
        if (mv) tl.fromTo(mv, { scale: 1 }, { scale: 1.06, duration: d, ease: 'none' }, s);
      }
    });
    return tl;
  }

  root.AVE_BROLL = { buildTimeline: buildTimeline };
})(typeof window !== 'undefined' ? window : this);

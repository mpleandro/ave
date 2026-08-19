/* DINÂMICO — a linha do tempo do estilo acumulativo.
 *
 * Cada palavra chega NO SEU TEMPO DE FALA (data-at, absoluto na composição).
 * O que este arquivo executa (os números vêm do variants.json via data-motion;
 * este arquivo executa, nunca decide):
 *
 *   sansIn  — blur + subida leve; a palavra nasce na cor APAGADA (--din-dim)
 *   lit     — a palavra sans ACENDE para a cor plena em data-lit (o relógio é
 *             do diretor: a próxima palavra caiu, ou LIT_SELF depois da própria)
 *   cascade — serif letra a letra: cada caractere vem da direita/baixo com
 *             escala 1.42 e blur, assentando em sequência
 *   fig     — a figure estoura de 0.5 com back.out — presença, não fade
 *
 * Regra herdada do editorial/disperso: o drop-shadow do CSS é REAPLICADO em
 * todo valor animado de filter — animar `filter` substitui o valor inteiro e
 * a sombra some no primeiro quadro sem isso.
 */
(function (root) {
  'use strict';
  var SOMBRA = ' drop-shadow(0 2px 5px rgba(0,0,0,.92)) drop-shadow(0 10px 28px rgba(13,33,55,.85))';   // espelha o filter do dinamico.css

  function motionDe(el) {
    try { return JSON.parse(el.getAttribute('data-motion') || '{}'); }
    catch (e) { return {}; }
  }

  function buildTimeline(rootEl, gsap, tl) {
    var box = rootEl.querySelector('.ave-din');
    if (!box) return tl;
    var M = motionDe(box);
    var sansIn = M.sansIn || { dur: 0.38, blur: 8, riseEm: 0.10 };
    var lit = M.lit || { dur: 0.40 };
    var cas = M.cascade || { dur: 0.5, staggerPerChar: 0.055, fromXEm: 0.7, fromYEm: 0.16, fromScale: 1.42, blur: 7 };
    var fig = M.fig || { dur: 0.55, fromScale: 0.5, blur: 6 };
    var EXIT = M.exit || 0.2;

    var cs = getComputedStyle(box);
    var DIM = (cs.getPropertyValue('--din-dim') || '#8F8F8F').trim();

    rootEl.querySelectorAll('.din-cue').forEach(function (cue) {
      var s = parseFloat(cue.getAttribute('data-start')) || 0;
      var d = parseFloat(cue.getAttribute('data-duration')) || 0;

      var f = cue.querySelector('.din-fig');
      if (f) {
        var fat = parseFloat(f.getAttribute('data-at')) || s;
        tl.fromTo(f, { opacity: 0, scale: fig.fromScale, filter: 'blur(' + fig.blur + 'px)' + SOMBRA },
                  { opacity: 1, scale: 1, filter: 'blur(0px)' + SOMBRA,
                    duration: fig.dur, ease: 'back.out(1.4)' }, fat);
      }

      cue.querySelectorAll('.din-w').forEach(function (w) {
        var at = parseFloat(w.getAttribute('data-at')) || s;
        var fs = parseFloat(getComputedStyle(w).fontSize) || 76;
        var serif = w.classList.contains('r-serif') || w.classList.contains('r-serifAcc');

        if (serif) {
          /* a palavra só carrega os caracteres; quem entra são eles */
          tl.to(w, { opacity: 1, duration: 0.01, ease: 'none' }, at);
          w.querySelectorAll('.ch').forEach(function (ch, k) {
            tl.fromTo(ch,
                      { opacity: 0, x: cas.fromXEm * fs, y: cas.fromYEm * fs,
                        scale: cas.fromScale, filter: 'blur(' + cas.blur + 'px)' + SOMBRA },
                      { opacity: 1, x: 0, y: 0, scale: 1, filter: 'blur(0px)' + SOMBRA,
                        duration: cas.dur, ease: 'power3.out' },
                      at + k * cas.staggerPerChar);
          });
        } else {
          tl.fromTo(w, { opacity: 0, y: sansIn.riseEm * fs, filter: 'blur(' + sansIn.blur + 'px)' + SOMBRA },
                    { opacity: 1, y: 0, filter: 'blur(0px)' + SOMBRA,
                      duration: sansIn.dur, ease: 'power2.out' }, at);
          /* o ACENDER: nasce apagada, acende quando o diretor mandou */
          var litAt = w.getAttribute('data-lit');
          if (w.classList.contains('r-base') && litAt !== null) {
            var BASE = getComputedStyle(w).color;
            tl.set(w, { color: DIM }, 0);
            tl.to(w, { color: BASE, duration: lit.dur, ease: 'none' }, parseFloat(litAt));
          }
        }
      });

      /* saída: fade quando há respiro depois; abrupta fica com o clip do motor */
      if (cue.getAttribute('data-exit') === 'fade') {
        tl.to(cue, { opacity: 0, duration: EXIT, ease: 'none' }, s + d - EXIT);
      }
    });
    return tl;
  }

  root.AVE_DINAMICO = { buildTimeline: buildTimeline };
})(typeof window !== 'undefined' ? window : this);

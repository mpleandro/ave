/* EDITORIAL — a linha do tempo das legendas por papel.
 *
 * Cada palavra chega NO SEU TEMPO DE FALA (data-at, absoluto na composição) com
 * a entrada do seu papel — o karaokê do estilo é isso, não um destaque em cima
 * de texto parado. Os números do movimento vêm do variants.json (motion do
 * estilo), serializados pelo compositor em data-motion no contêiner: este
 * arquivo executa, nunca decide.
 *
 * Entradas (espelham BRAND.motion do styles.local.js):
 *   fade    — opacidade + desfoque 2px      (ctx, stress)
 *   serifIn — cresce de 0.8, origem esquerda (serif, serifAcc)
 *   glow    — desfoque 11px + escala 1.05    (punch)
 *   pop     — escala 0 + desfoque 20px       (num)
 *   type    — caracteres um a um, subindo    (serif que fecha frase)
 *
 * Regra herdada do disperso/empilhado: o drop-shadow do CSS é REAPLICADO em
 * todo valor animado de filter — animar `filter` substitui o valor inteiro e
 * a sombra some no primeiro quadro sem isso.
 */
(function (root) {
  'use strict';
  var SOMBRA = ' drop-shadow(0 2px 5px rgba(0,0,0,.92)) drop-shadow(0 10px 28px rgba(13,33,55,.85))';   // espelha o filter do editorial.css

  function motionDe(el) {
    try { return JSON.parse(el.getAttribute('data-motion') || '{}'); }
    catch (e) { return {}; }
  }

  function buildTimeline(rootEl, gsap, tl) {
    var box = rootEl.querySelector('.ave-edt');
    if (!box) return tl;
    var M = motionDe(box);
    var fade = M.fade || { dur: 0.34, blur: 2 };
    var serifIn = M.serifIn || { dur: 0.32, scale: 0.8 };
    var type = M.type || { dur: 0.24, riseY: 5, staggerPerChar: 0.045 };
    var pop = M.pop || { dur: 0.5, blur: 20 };
    var glow = M.glow || { dur: 0.42, blur: 11, scale: 1.05 };
    var EXIT = M.exit || 0.2;

    rootEl.querySelectorAll('.edt-cue').forEach(function (cue) {
      var s = parseFloat(cue.getAttribute('data-start')) || 0;
      var d = parseFloat(cue.getAttribute('data-duration')) || 0;

      cue.querySelectorAll('.edt-w').forEach(function (w) {
        var at = parseFloat(w.getAttribute('data-at')) || s;
        var anim = w.getAttribute('data-anim') || 'fade';
        if (anim === 'serifIn') {
          tl.fromTo(w, { opacity: 0, scale: serifIn.scale },
                    { opacity: 1, scale: 1, duration: serifIn.dur, ease: 'power3.out' }, at);
        } else if (anim === 'glow') {
          tl.fromTo(w, { opacity: 0, scale: glow.scale, filter: 'blur(' + glow.blur + 'px)' + SOMBRA },
                    { opacity: 1, scale: 1, filter: 'blur(0px)' + SOMBRA,
                      duration: glow.dur, ease: 'power3.out' }, at);
        } else if (anim === 'pop') {
          tl.fromTo(w, { opacity: 0, scale: 0, filter: 'blur(' + pop.blur + 'px)' + SOMBRA },
                    { opacity: 1, scale: 1, filter: 'blur(0px)' + SOMBRA,
                      duration: pop.dur, ease: 'expo.out' }, at);
        } else if (anim === 'type') {
          tl.to(w, { opacity: 1, duration: 0.01, ease: 'none' }, at);
          w.querySelectorAll('.ch').forEach(function (ch, k) {
            tl.fromTo(ch, { opacity: 0, y: type.riseY },
                      { opacity: 1, y: 0, duration: type.dur, ease: 'none' },
                      at + k * type.staggerPerChar);
          });
        } else {
          tl.fromTo(w, { opacity: 0, filter: 'blur(' + fade.blur + 'px)' + SOMBRA },
                    { opacity: 1, filter: 'blur(0px)' + SOMBRA,
                      duration: fade.dur, ease: 'power2.out' }, at);
        }
      });

      /* saída: fade quando há respiro depois; abrupta fica com o clip do motor */
      if (cue.getAttribute('data-exit') === 'fade') {
        tl.to(cue, { opacity: 0, duration: EXIT, ease: 'none' }, s + d - EXIT);
      }
    });
    return tl;
  }

  root.AVE_EDITORIAL = { buildTimeline: buildTimeline };
})(typeof window !== 'undefined' ? window : this);

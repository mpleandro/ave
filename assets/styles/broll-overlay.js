/* BROLL OVERLAY — a linha do tempo das janelas de ênfase, guiada pelo KIT.
 *
 * NENHUM número de movimento nasce aqui: o compositor lê o Motion Kit
 * (helpers/motion_kit.py) e escreve em cada janela `data-motion` (números do
 * kit) e `data-in`/`data-stagger` (o RITMO da janela, derivado da duração do
 * trecho). Este arquivo só executa. Trocar o gosto é trocar o kit.
 *
 * O gesto central vem da referência aprendida: texto sobe por MÁSCARA
 * (yPercent 110→0, o reveal de linhas das LPs), acento em itálico display,
 * linha-legenda que cresce e ganha o ponto, anéis girando em loop lento,
 * mídia revelada por clip-path de cima para baixo.
 */
(function (root) {
  'use strict';
  var OUT = 0.24;              /* saída fixa: o acento é a entrada, não a volta */

  function motionDe(el) {
    try { return JSON.parse(el.getAttribute('data-motion') || '{}'); }
    catch (e) { return {}; }
  }

  function buildTimeline(rootEl, gsap, tl) {
    rootEl.querySelectorAll('.ave-bo-win').forEach(function (el) {
      var s = parseFloat(el.getAttribute('data-start')) || 0;
      var d = parseFloat(el.getAttribute('data-duration')) || 0;
      var IN = parseFloat(el.getAttribute('data-in')) || 0.3;
      var STAG = parseFloat(el.getAttribute('data-stagger')) || 0.11;
      var M = motionDe(el);
      var ease = M.easing ? 'power3.out' : 'power3.out'; /* easing CSS fica nos hovers; GSAP usa a família power, como a referência */
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

      /* cenário: glow respira na entrada; anéis giram o tempo todo da janela */
      var glow = el.querySelector('.bo-glow');
      if (glow) tl.fromTo(glow, { scale: 0.85, opacity: 0 },
                          { scale: 1, opacity: 1, duration: IN * 2, ease: 'power2.out' }, s);
      var spins = M.ringSpinS || [60, 45];
      el.querySelectorAll('.bo-ring').forEach(function (r, i) {
        tl.fromTo(r, { opacity: 0 }, { opacity: 1, duration: IN, ease: 'none' }, s);
        tl.to(r, { rotation: i % 2 ? -360 : 360, duration: spins[i % spins.length],
                   ease: 'none', repeat: -1 }, s);
      });

      /* cartão (top/bottom): reveal de baixo, como os sticky cards */
      var card = el.querySelector('.bo-card');
      var rev = M.reveal || { y: 28, dur: 0.9 };
      if (card) tl.fromTo(card, { y: rev.y * 1.4, scale: 0.97 },
                          { y: 0, scale: 1, duration: rev.dur, ease: 'power2.out' }, s);

      var eyebrow = el.querySelector('.bo-eyebrow');
      if (eyebrow) tl.fromTo(eyebrow, { opacity: 0, y: rev.y * 0.6 },
                             { opacity: 1, y: 0, duration: rev.dur * 0.7, ease: 'power2.out' }, s + IN * 0.3);

      /* palavras: sobem POR DENTRO da máscara — o reveal de linhas da referência */
      var linhas = M.linhas || { yPercent: 110, stagger: 0.12, dur: 1.0 };
      var ws = el.querySelectorAll('.ave-bo-words .bo-w');
      ws.forEach(function (w, i) {
        tl.fromTo(w, { yPercent: linhas.yPercent },
                  { yPercent: 0, duration: Math.max(IN, linhas.dur * 0.7), ease: ease },
                  s + IN * 0.25 + i * STAG);
      });

      /* linha-legenda: cresce depois que o conteúdo assentou; o ponto pisca no fim */
      var cap = M.capline || { larguraPx: 140, dur: 1.0, dotDelay: 0.5 };
      var cl = el.querySelector('.bo-capline .l');
      var cd = el.querySelector('.bo-capline .d');
      var caplineAt = s + IN + Math.max(0, (ws.length - 1)) * STAG * 0.6;
      if (cl) tl.to(cl, { width: cap.larguraPx, duration: cap.dur * 0.8, ease: 'power2.out' }, caplineAt);
      if (cd) tl.fromTo(cd, { opacity: 0 }, { opacity: 1, duration: 0.25, ease: 'none' },
                        caplineAt + (cap.dotDelay || 0.5) * 0.8);

      /* estatística: o número CONTA; o rótulo chega quando ele assenta */
      var val = el.querySelector('.ave-bo-stat .bo-num');
      if (val) {
        var alvo = parseFloat(val.getAttribute('data-count'));
        tl.fromTo(val.parentNode, { opacity: 0, scale: 0.82 },
                  { opacity: 1, scale: 1, duration: IN, ease: 'back.out(1.7)' }, s);
        if (!isNaN(alvo)) {
          var obj = { n: 0 };
          var dec = (val.getAttribute('data-count').split('.')[1] || '').length;
          tl.to(obj, {
            n: alvo, duration: Math.min(1.1, Math.max(0.5, d * 0.28)), ease: 'power2.out',
            onUpdate: function () { val.textContent = obj.n.toFixed(dec).replace('.', ','); },
          }, s + IN * 0.4);
        }
        var lab = el.querySelector('.ave-bo-stat .bo-label');
        if (lab) tl.to(lab, { opacity: 1, duration: rev.dur * 0.6, ease: 'power2.out' },
                       s + IN + STAG * 2);
      }

      /* etiquetas: entram como reveals, numeradas. `data-at` manda quando
         existe — é o que deixa a lista acompanhar a FALA em vez de desfilar
         numa cadência constante que descola da voz. */
      el.querySelectorAll('.ave-bo-labels .bo-item').forEach(function (it, i) {
        var at = parseFloat(it.getAttribute('data-at'));
        if (isNaN(at)) at = s + i * Math.max(STAG, 0.14);
        tl.fromTo(it, { opacity: 0, y: rev.y, x: -30 },
                  { opacity: 1, y: 0, x: 0, duration: rev.dur * 0.7, ease: 'power3.out' }, at);
      });

      /* mídia: clip reveal de cima para baixo, na moldura de mockup */
      var med = el.querySelector('.ave-bo-media');
      if (med) {
        var clip = M.clip || { dur: 1.1 };
        tl.fromTo(med, { clipPath: 'inset(0 0 100% 0)', y: 20 },
                  { clipPath: 'inset(0% 0 0% 0)', y: 0, duration: clip.dur, ease: 'power2.inOut' }, s);
        var mv = med.querySelector('video, img');
        if (mv) tl.fromTo(mv, { scale: 1 }, { scale: 1.06, duration: d, ease: 'none' }, s);
      }
    });
    return tl;
  }

  root.AVE_BROLL = { buildTimeline: buildTimeline };
})(typeof window !== 'undefined' ? window : this);

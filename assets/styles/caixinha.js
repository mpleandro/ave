/* CAIXINHA DE PERGUNTAS — a linha do tempo do adesivo.
 *
 * O gesto é ADESIVO SENDO COLADO, não cartão surgindo: escala com sobra,
 * inclinação que assenta e um leve amortecimento no fim. Foi o que separou,
 * nos testes, "parece o Instagram" de "parece um card de PowerPoint".
 *
 * A pergunta chega PALAVRA A PALAVRA porque é texto sendo LIDO — em bloco ela
 * lê como legenda, e a caixinha deixa de ser a coisa que a pessoa acabou de
 * receber. A resposta entra depois, como balão de conversa.
 *
 * Tudo em tempo ABSOLUTO na timeline do pai: o motor renderiza saltando para
 * quadros avulsos, então nada aqui pode depender de ter passado antes.
 */
(function (root) {
  'use strict';

  function buildTimeline(rootEl, gsap, tl) {
    var box = rootEl.querySelector('.ave-caixa');
    if (!box) return tl;
    var s = parseFloat(box.getAttribute('data-start')) || 0;
    var d = parseFloat(box.getAttribute('data-duration')) || 0;
    var tilt = parseFloat(box.getAttribute('data-tilt'));
    if (isNaN(tilt)) tilt = -1.6;
    var respAt = parseFloat(box.getAttribute('data-reply-at'));
    var OUT = 0.42;

    var card = box.querySelector('.cx-card');
    if (card) {
      tl.fromTo(card,
        { opacity: 0, scale: 0.84, rotation: tilt * 3.2, y: -26 },
        { opacity: 1, scale: 1, rotation: tilt, y: 0,
          duration: 0.62, ease: 'back.out(1.7)' }, s);
    }

    /* as palavras da pergunta acendem em cascata curta — leitura, não digitação */
    box.querySelectorAll('.cx-corpo .cx-w').forEach(function (w, i) {
      tl.fromTo(w, { opacity: 0, y: 10 },
                { opacity: 1, y: 0, duration: 0.22, ease: 'power2.out' },
                s + 0.34 + i * 0.045);
    });

    var resp = box.querySelector('.cx-resposta');
    if (resp && !isNaN(respAt)) {
      tl.fromTo(resp, { opacity: 0, scale: 0.9, y: 18 },
                { opacity: 1, scale: 1, y: 0, duration: 0.5, ease: 'back.out(1.5)' }, respAt);
    }

    /* SAÍDA: sobe e encolhe, como adesivo sendo retirado. Só existe quando a
       janela termina antes do vídeo — quando a caixinha fica até o fim, o
       elemento simplesmente acaba com a composição, sem despedida. */
    if (box.getAttribute('data-exit') === '1') {
      tl.to(box, { opacity: 0, scale: 0.94, y: -34, duration: OUT, ease: 'power2.in' },
            s + d - OUT);
    }
    return tl;
  }

  root.AVE_CAIXA = { buildTimeline: buildTimeline };
})(typeof window !== 'undefined' ? window : this);

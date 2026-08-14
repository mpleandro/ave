/* Estilo KARAOKÊ — tempos e movimento, compartilhados entre a prévia do editor
 * e a composição HyperFrames. Par de `karaoke.css`.
 *
 * Script clássico de propósito (nada de `import`): a prévia do editor é servida
 * como script simples e a composição roda em página estática. Um módulo ES
 * obrigaria os dois lados a mudar de forma de carregar para ganhar nada.
 *
 * Os NÚMEROS são o ponto deste arquivo. Antes eles viviam duplicados — no
 * buildKaraokeDemo() do app.js e no Main.tsx do template — e divergir era
 * questão de tempo.
 */
(function (root) {
  'use strict';

  var TIMING = {
    FPS_REF: 30,     // referência de frames dos tempos abaixo
    STEP: 0.26,      // atraso entre uma palavra e a seguinte, em segundos
    ENTER_FRAMES: 7, // duração da entrada de cada palavra
    HOLD: 0.6,       // sobra depois da última palavra, antes da linha sair
    RISE: 34,        // subida na entrada, em px de referência (1080)
  };
  TIMING.ENTER = TIMING.ENTER_FRAMES / TIMING.FPS_REF;

  function clamp01(n) { return n < 0 ? 0 : n > 1 ? 1 : n; }
  function easeOutCubic(t) { return 1 - Math.pow(1 - t, 3); }

  /* Estado de UMA palavra a `tRel` segundos do início da linha.
     `index` é a posição da palavra, que define seu atraso. Função PURA: mesmo
     tempo, mesmo resultado. É o que torna o seek do renderer confiável — e o
     motivo de não existir Math.random() em lugar nenhum deste estilo. */
  function wordState(tRel, index) {
    var e = easeOutCubic(clamp01((tRel - index * TIMING.STEP) / TIMING.ENTER));
    return { opacity: e, y: (1 - e) * TIMING.RISE };
  }

  /* Duração natural de uma linha com `n` palavras (entrada escalonada + sobra). */
  function lineDuration(n) {
    return (n - 1) * TIMING.STEP + TIMING.ENTER + TIMING.HOLD;
  }

  /* Monta a timeline GSAP da composição a partir do DOM já emitido.
   *
   * Lê `data-start` de cada .ave-cap-line e cria tweens em tempo ABSOLUTO, em
   * vez de animar por callback. Tween declarativo é seekable por construção: o
   * renderer salta para um frame qualquer e o GSAP resolve o estado sozinho.
   * `scale` converte a subida de referência para a escala real da composição.
   */
  function buildTimeline(rootEl, gsap, tl, scale) {
    scale = scale || 1;
    var lines = rootEl.querySelectorAll('.ave-cap-line');
    for (var i = 0; i < lines.length; i++) {
      var line = lines[i];
      var start = parseFloat(line.getAttribute('data-start')) || 0;
      var spans = line.querySelectorAll('span');
      for (var j = 0; j < spans.length; j++) {
        tl.fromTo(
          spans[j],
          { opacity: 0, y: TIMING.RISE * scale },
          { opacity: 1, y: 0, duration: TIMING.ENTER, ease: 'cubic.out' },
          start + j * TIMING.STEP
        );
      }
    }
    return tl;
  }

  root.AVE_KARAOKE = {
    TIMING: TIMING,
    wordState: wordState,
    lineDuration: lineDuration,
    buildTimeline: buildTimeline,
  };
})(typeof window !== 'undefined' ? window : this);

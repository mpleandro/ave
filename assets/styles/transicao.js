/* TRANSIÇÃO — motor único para os efeitos de corte NOVOS. Par de `transicao.css`.
 *
 * O `flash` que já existia (feixe + clique) fica no caminho antigo, dentro de
 * camera.js/compose_shortform.py — provado, com o lead de 2 quadros e o SFX já
 * calibrados, e migrá-lo custava risco sem ganho. Este motor é para todo
 * `estilo` além dele: `chama`, `tranco`, `estouro`, `zoom_blur`, `deslize`,
 * `cortina`, `iris`, `falha` (e qualquer um que `variants.json.transicoes`
 * ganhar depois — SEM tocar este arquivo, se o `tipo` já existir).
 *
 * A JANELA É SIMÉTRICA NO CORTE: compose_shortform.py escreve
 * `data-start = at − dur/2`, então `at` cai sempre no MEIO da janela
 * (`start + duration/2`). Cada tipo decide sozinho como preencher os dois
 * lados — zoom é assimétrico (a entrada estufa mais rápido do que a saída
 * relaxa), cobre segura um platô no meio — mas o ponto central é sempre o
 * mesmo, e é ali que compose_shortform.py alinhou o `at` com o corte real
 * (segments.json / VIDEO_LAG), do mesmo jeito que o flash já faz.
 *
 * DOIS CAMINHOS, pelo `tipo`:
 *   'shake' | 'zoom'                    → anima o PRÓPRIO #a-roll (é câmera).
 *   'cor' | 'cobre' | 'swipe' | 'glitch' → desenha na camada da instância
 *      (`.tz-panel` / `.tz-slice`, sempre presentes — ver transicao.css) que
 *      ESCONDE a emenda por baixo. O preview.mp4 é um vídeo só, já cortado
 *      (Regra 2): nenhum destes é um crossfade real entre duas tomadas.
 *
 * Tudo em tween absoluto (GSAP), nunca @keyframes — o renderer salta de
 * quadro sem tempo de parede passar, e animação de CSS não sobrevive ao seek
 * (mesma razão documentada em cartela.js/palavra.js).
 */
(function (root) {
  'use strict';

  function num(v, d) {
    var n = parseFloat(v);
    return isFinite(n) ? n : d;
  }

  function lerJSON(el, attr) {
    try { return JSON.parse(el.getAttribute(attr) || '{}'); }
    catch (e) { return {}; }
  }

  function resolveCor(nome, accent) {
    return !nome || nome === 'accent' ? accent : nome;
  }

  /* Zoom: a entrada estufa mais rápido que a saída relaxa — mesma proporção
     medida na proposta (42% para dentro, 58% para fora). Constante do motor,
     não dado: é ritmo, não escolha por vídeo. */
  var ZOOM_IN_FRAC = 0.42;
  /* Cobre (cortina/íris): cresce, segura um platô cobrindo, e recolhe —
     35% / 30% / 35%. O corte acontece DENTRO do platô, nunca durante o
     movimento, senão a emenda apareceria a meio caminho do recorte. */
  var COBRE_FRACS = [0.35, 0.30, 0.35];

  /* zoomCuts/zoomAuto (camera.js) e tracking já animam scale/x/y do MESMO
     #a-roll, e os dois têm tweens no MESMO `tl` — camera_parts sempre entra
     na timeline antes deste motor (render_html monta `parts` nessa ordem).
     Por isso a base não é um literal (1, x:0, y:0): é o valor que o `tl` já
     tem naquele instante, amostrado por `seek` ANTES de somar o tween novo.
     Sem isto, ligar zoomCuts + um `estouro`/`zoom_blur` no mesmo corte fazia
     a transição pular para 1 e depois devolver 1 — perdendo o zoom da câmera
     pelo resto do segmento, porque nada o restabelecia depois. */
  function amostrar(gsap, tl, aroll, t, prop, fallback) {
    tl.seek(Math.max(0, t), true);
    var v = gsap.getProperty(aroll, prop);
    return typeof v === 'number' && isFinite(v) ? v : fallback;
  }

  /* As duas amostras — ANTES e DEPOIS do corte — porque o cut boundary da
     câmera cai bem no MEIO desta janela (o transicao_parts do Python centra
     `at` aqui de propósito). Assentar de volta em "antes" deixaria o vídeo
     preso no zoom do segmento ANTIGO pelo resto do segmento novo, já que
     nada reafirma a câmera depois — ela só seta de novo no PRÓXIMO corte. */
  function buildShake(el, gsap, tl, aroll, start, dur, def) {
    var px = def.px || 8;
    var bx = amostrar(gsap, tl, aroll, start, 'x', 0);
    var by = amostrar(gsap, tl, aroll, start, 'y', 0);
    var dx = amostrar(gsap, tl, aroll, start + dur, 'x', bx);
    var dy = amostrar(gsap, tl, aroll, start + dur, 'y', by);
    var q = dur / 4.5; // quatro batidas + um relaxar final
    tl.fromTo(aroll, { x: bx, y: by },
      { x: bx + px, y: by - px * 0.6, duration: q, ease: 'power1.inOut' }, start);
    tl.to(aroll, { x: bx - px * 1.1, y: by + px * 0.5, duration: q, ease: 'power1.inOut' }, start + q);
    tl.to(aroll, { x: bx + px * 0.7, y: by - px * 0.4, duration: q, ease: 'power1.inOut' }, start + 2 * q);
    tl.to(aroll, { x: dx, y: dy, duration: dur - 3 * q, ease: 'power2.out' }, start + 3 * q);
  }

  function buildZoom(el, gsap, tl, aroll, start, dur, def) {
    var esc = def.escala || 1.1;
    var blur = def.blur || 0;
    var antes = amostrar(gsap, tl, aroll, start, 'scale', 1);
    var depois = amostrar(gsap, tl, aroll, start + dur, 'scale', antes);
    var out = dur * ZOOM_IN_FRAC;
    var volta = dur - out;
    tl.fromTo(aroll, { scale: antes, filter: 'blur(0px)' },
      { scale: antes * esc, filter: 'blur(' + blur + 'px)', duration: out, ease: 'power2.in' }, start);
    tl.to(aroll, { scale: depois, filter: 'blur(0px)', duration: volta, ease: 'power2.out' }, start + out);
  }

  function buildCor(panel, gsap, tl, start, dur, def, accent) {
    var pico = def.pico != null ? def.pico : 0.85;
    panel.style.background = resolveCor(def.cor, accent);
    tl.set(panel, { clipPath: 'inset(0 0 0 0)' }, start);
    tl.fromTo(panel, { opacity: 0 }, { opacity: pico, duration: dur / 2, ease: 'power2.in' }, start);
    tl.to(panel, { opacity: 0, duration: dur / 2, ease: 'power2.out' }, start + dur / 2);
  }

  function buildCobre(panel, gsap, tl, start, dur, def, accent) {
    panel.style.background = resolveCor(def.cor, accent);
    var f0 = dur * COBRE_FRACS[0], f1 = dur * COBRE_FRACS[1], f2 = dur * COBRE_FRACS[2];
    var circulo = def.forma === 'circulo';
    var cx = (def.cx != null ? def.cx : 0.5) * 100;
    var cy = (def.cy != null ? def.cy : 0.5) * 100;
    var escondido = circulo
      ? 'circle(0% at ' + cx + '% ' + cy + '%)'
      : 'inset(100% 0 0 0)';
    var cobrindo = circulo
      ? 'circle(85% at ' + cx + '% ' + cy + '%)'
      : 'inset(0 0 0 0)';
    tl.set(panel, { opacity: 1, clipPath: escondido }, start);
    tl.to(panel, { clipPath: cobrindo, duration: f0, ease: 'power2.in' }, start);
    // platô: nenhum tween — o corte de vídeo acontece por baixo, escondido.
    tl.to(panel, { clipPath: escondido, duration: f2, ease: 'power2.out' }, start + f0 + f1);
  }

  function buildSwipe(panel, gsap, tl, start, dur, def, accent) {
    var dir = def.direcao || 'esquerda';
    var vertical = dir === 'cima' || dir === 'baixo';
    var eixo = vertical ? 'yPercent' : 'xPercent';
    var sentido = (dir === 'esquerda' || dir === 'cima') ? 1 : -1;
    panel.style.background = resolveCor(def.cor, accent);
    var de = { opacity: 1 }, para = { opacity: 1, duration: dur, ease: 'power2.inOut' };
    de[eixo] = 100 * sentido;
    para[eixo] = -100 * sentido;
    // atravessa de fora a fora, cobrindo por completo exatamente no meio —
    // que é onde `start + dur/2` cai o corte.
    tl.fromTo(panel, de, para, start);
  }

  function buildGlitch(fatias, gsap, tl, start, dur) {
    var offs = [22, -26, 14];
    for (var i = 0; i < fatias.length; i++) {
      var f = fatias[i];
      var o = offs[i % offs.length];
      var atraso = start + i * dur * 0.06;
      tl.fromTo(f, { opacity: 0, x: 0 },
        { opacity: 1, x: o, duration: dur * 0.3, ease: 'power1.inOut' }, atraso);
      tl.to(f, { opacity: 0, x: 0, duration: dur * 0.3, ease: 'power1.out' },
        start + dur * 0.55 + i * dur * 0.05);
    }
  }

  function buildOne(el, gsap, tl, aroll, accent) {
    var def = lerJSON(el, 'data-def');
    var start = num(el.getAttribute('data-start'), 0);
    var dur = num(el.getAttribute('data-duration'), 0.2);
    if (dur <= 0) return;
    var tipo = def.tipo || 'cor';

    if (tipo === 'shake') { buildShake(el, gsap, tl, aroll, start, dur, def); return; }
    if (tipo === 'zoom') { buildZoom(el, gsap, tl, aroll, start, dur, def); return; }

    var panel = el.querySelector('.tz-panel');
    if (tipo === 'cor') { buildCor(panel, gsap, tl, start, dur, def, accent); return; }
    if (tipo === 'cobre') { buildCobre(panel, gsap, tl, start, dur, def, accent); return; }
    if (tipo === 'swipe') { buildSwipe(panel, gsap, tl, start, dur, def, accent); return; }
    if (tipo === 'glitch') {
      var fatias = Array.prototype.slice.call(el.querySelectorAll('.tz-slice'));
      buildGlitch(fatias, gsap, tl, start, dur);
      return;
    }
  }

  function buildTimeline(rootEl, gsap, tl) {
    var aroll = document.getElementById('a-roll');
    var accent = rootEl.getAttribute('data-accent') || '#FF6B1A';
    var els = Array.prototype.slice.call(rootEl.querySelectorAll('.ave-transicao'));
    for (var i = 0; i < els.length; i++) {
      if (aroll) buildOne(els[i], gsap, tl, aroll, accent);
    }
    // As amostras de 'shake'/'zoom' movem o playhead durante o build (é
    // como se lê o valor da câmera num instante futuro); devolve a 0 para
    // não entregar a timeline com o seek de montagem ainda aplicado.
    tl.seek(0, true);
    return tl;
  }

  root.AVE_TRANSICAO = { buildTimeline: buildTimeline };
})(typeof window !== 'undefined' ? window : this);

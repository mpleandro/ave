/* EFEITOS — a animação dos efeitos da Fase 2 (helpers/efeitos_compose.py).
 *
 * Um construtor por tipo; o Python já resolveu tempo, posição e conteúdo, aqui
 * só se anima. Tudo em tween declarativo com tempo absoluto (`set` + `to` no
 * mesmo instante fixa o ponto de partida): o renderer salta para um quadro
 * qualquer e o GSAP resolve o estado. Nada de aleatório, nada de callback que
 * dependa de ordem — com uma exceção documentada: contagem de número, que é um
 * `onUpdate` de um proxy tweenado, determinístico no seek.
 */
(function (root) {
  'use strict';

  function entraSai(tl, alvo, t0, t1, cfg, de) {
    var ent = cfg.entrada, sai = cfg.saida;
    var ini = { opacity: 0 }, fim = { opacity: 1, duration: ent, ease: 'back.out(1.5)' };
    for (var k in de) { ini[k] = de[k]; fim[k] = (k === 'scale') ? 1 : 0; }
    tl.set(alvo, ini, t0);
    tl.to(alvo, fim, t0);
    var saida = { opacity: 0, duration: sai, ease: 'power2.in' };
    if ('y' in de) saida.y = -de.y * 0.5;
    if ('x' in de) saida.x = de.x;
    tl.to(alvo, saida, Math.max(t0 + ent, t1 - sai));
  }

  function numero(v, fmt) {
    var casas = /[.,]\d/.test(fmt) ? 1 : 0;
    var s = v.toFixed(casas).replace('.', ',');
    return fmt.replace(/-?\d+(?:[.,]\d+)?/, s);
  }

  var B = {};

  B.checklist = function (el, gsap, tl, it, cfg) {
    var card = el.querySelector('.efx-card');
    entraSai(tl, card, it.t0, it.t1, cfg, { y: 46, scale: 0.94 });
    var ns = el.querySelectorAll('.efx-ck-n');
    for (var n = 0; n < ns.length; n++) tl.set(ns[n], { opacity: n === 0 ? 1 : 0 }, it.t0);
    var rows = el.querySelectorAll('.efx-ck-item');
    for (var i = 0; i < rows.length; i++) {
      var r = rows[i], at = parseFloat(r.getAttribute('data-at'));
      var bola = r.querySelector('.efx-ck-bola'), p = r.querySelector('path');
      var txt = r.querySelector('.efx-ck-txt');
      tl.set(r, { opacity: 0, x: 26 }, it.t0);
      tl.to(r, { opacity: 1, x: 0, duration: 0.3, ease: 'power2.out' }, it.t0 + 0.14 + i * 0.07);
      tl.set(bola, { backgroundColor: 'rgba(0,0,0,0)', borderColor: 'rgba(255,255,255,.38)', scale: 1 }, it.t0);
      tl.set(p, { strokeDashoffset: 30 }, it.t0);
      tl.set(txt, { color: 'rgba(255,255,255,.55)' }, it.t0);
      tl.to(bola, { backgroundColor: cfg.accent, borderColor: cfg.accent, scale: 1.18,
                    duration: 0.13, ease: 'power2.out' }, at);
      tl.to(bola, { scale: 1, duration: 0.2, ease: 'power2.inOut' }, at + 0.13);
      tl.to(p, { strokeDashoffset: 0, duration: 0.26, ease: 'power2.out' }, at + 0.05);
      tl.to(txt, { color: '#ffffff', duration: 0.2 }, at);
      if (ns[i]) tl.set(ns[i], { opacity: 0 }, at);
      if (ns[i + 1]) tl.set(ns[i + 1], { opacity: 1 }, at);
    }
  };

  B.chartGrow = function (el, gsap, tl, it, cfg) {
    var c = cfg.chart || {}, ms = c.barraMs || 0.55, stg = c.stagger || 0.09;
    var card = el.querySelector('.efx-card');
    entraSai(tl, card, it.t0, it.t1, cfg, { y: 46, scale: 0.94 });
    var cols = el.querySelectorAll('.efx-ch-col');
    for (var i = 0; i < cols.length; i++) {
      var bar = cols[i].querySelector('.efx-ch-bar'), val = cols[i].querySelector('.efx-ch-val');
      bar.style.height = (parseFloat(bar.getAttribute('data-h')) * 100) + '%';
      var t = it.t0 + 0.3 + i * stg;
      tl.set(bar, { scaleY: 0, transformOrigin: '50% 100%' }, it.t0);
      tl.to(bar, { scaleY: 1, duration: ms, ease: 'power3.out' }, t);
      tl.set(val, { opacity: 0, y: 12 }, it.t0);
      tl.to(val, { opacity: 1, y: 0, duration: 0.25, ease: 'power2.out' }, t + ms * 0.7);
    }
    var big = el.querySelector('.efx-ch-big');
    if (big) {
      var alvo = parseFloat(big.getAttribute('data-alvo')), fmt = big.getAttribute('data-fmt');
      var o = { v: 0 };
      var pinta = function () { big.textContent = numero(o.v, fmt); };
      tl.set(o, { v: 0, onUpdate: pinta }, it.t0);
      tl.to(o, { v: alvo, duration: 1.1, ease: 'power2.out', onUpdate: pinta }, it.t0 + 0.25);
    }
  };

  /* CÁLCULO: o cartão entra, cada linha sobe na sua palavra; o resultado
   * estoura (escala) e fica parado até a saída. */
  B.conta = function (el, gsap, tl, it, cfg) {
    var card = el.querySelector('.efx-ct');
    entraSai(tl, card, it.t0, it.t1, cfg, { y: 40, scale: 0.94 });
    var ls = el.querySelectorAll('.efx-ct-linha');
    for (var i = 0; i < ls.length; i++) {
      var at = parseFloat(ls[i].getAttribute('data-at'));
      var res = ls[i].classList.contains('res');
      tl.set(ls[i], { opacity: 0, y: 30, scale: res ? 0.6 : 1, transformOrigin: '0% 50%' }, it.t0);
      tl.to(ls[i], { opacity: 1, y: 0, scale: 1, duration: res ? 0.34 : 0.26,
                     ease: res ? 'back.out(2.6)' : 'power3.out' }, at);
    }
  };

  /* A × B: lado A com o cartão, lado B na palavra dele, rodapé por último. */
  B.versus = function (el, gsap, tl, it, cfg) {
    var lados = el.querySelectorAll('.efx-vs-lado'), x = el.querySelector('.efx-vs-x');
    var rd = el.querySelector('.efx-vs-rodape');
    for (var i = 0; i < lados.length; i++) {
      var at = parseFloat(lados[i].getAttribute('data-at'));
      tl.set(lados[i], { opacity: 0, x: i ? 80 : -80, scale: 0.92 }, it.t0);
      tl.to(lados[i], { opacity: 1, x: 0, scale: 1, duration: 0.32, ease: 'back.out(1.6)' }, at);
      tl.to(lados[i], { opacity: 0, duration: cfg.saida, ease: 'power2.in' }, it.t1 - cfg.saida);
    }
    if (x) {
      tl.set(x, { opacity: 0, scale: 0.4 }, it.t0);
      tl.to(x, { opacity: 1, scale: 1, duration: 0.25, ease: 'back.out(2)' }, it.t0 + 0.15);
      tl.to(x, { opacity: 0, duration: cfg.saida }, it.t1 - cfg.saida);
    }
    if (rd) {
      var ra = parseFloat(rd.getAttribute('data-at'));
      tl.set(rd, { opacity: 0, y: 30 }, it.t0);
      tl.to(rd, { opacity: 1, y: 0, duration: 0.3, ease: 'power3.out' }, ra);
      tl.to(rd, { opacity: 0, duration: cfg.saida }, it.t1 - cfg.saida);
    }
  };

  B.phoneMockup = function (el, gsap, tl, it, cfg) {
    var ph = el.querySelector('.efx-phone');
    var dx = it.lado === 'esq' ? -300 : 300, rot = it.lado === 'esq' ? 4 : -4;
    tl.set(ph, { opacity: 0, x: dx, rotation: rot * 3, y: 0 }, it.t0);
    tl.to(ph, { opacity: 1, x: 0, rotation: rot, duration: 0.55, ease: 'back.out(1.3)' }, it.t0);
    var meio = Math.max(0.2, (it.t1 - it.t0 - 0.55 - cfg.saida) / 2);
    tl.to(ph, { y: -16, duration: meio, ease: 'sine.inOut', yoyo: true, repeat: 1 }, it.t0 + 0.55);
    tl.to(ph, { opacity: 0, x: dx, duration: cfg.saida + 0.08, ease: 'power2.in' },
          Math.max(it.t0 + 0.6, it.t1 - cfg.saida - 0.08));
    var ms = el.querySelectorAll('[data-at]');
    for (var i = 0; i < ms.length; i++) {
      var at = parseFloat(ms[i].getAttribute('data-at'));
      tl.set(ms[i], { opacity: 0, y: 24, scale: 0.9 }, it.t0);
      tl.to(ms[i], { opacity: 1, y: 0, scale: 1, duration: 0.3, ease: 'back.out(2)' }, at);
    }
  };

  /* ZOOM DIGITAL: corte seco para dentro do rosto e corte seco de volta. Anima
   * `#vidwin` — o `#a-roll` é da câmera (zoomCuts/zoomAuto), e duas fontes no
   * mesmo transform brigariam. */
  B.zoomPunch = function (el, gsap, tl, it) {
    var v = document.getElementById('vidwin');
    tl.set(v, { scale: it.escala, transformOrigin: it.ox + '% ' + it.oy + '%' }, it.t0);
    tl.set(v, { scale: 1, transformOrigin: '50% 50%' }, it.t1);
  };

  /* ZOOM ATRAVÉS DO CORTE: o quadro mergulha no rosto com borrão até o corte e
   * o plano seguinte nasce de dentro dele, voltando ao normal. */
  B.zoomThrough = function (el, gsap, tl, it) {
    var v = document.getElementById('vidwin');
    var o = it.ox + '% ' + it.oy + '%', t0 = Math.max(0, it.at - it.entra);
    tl.set(v, { transformOrigin: o, scale: 1, filter: 'blur(0px)' }, t0);
    tl.to(v, { scale: it.escala, filter: 'blur(' + it.blur + 'px)', duration: it.entra,
               ease: 'power3.in' }, t0);
    tl.to(v, { scale: 1, filter: 'blur(0px)', duration: it.sai, ease: 'power3.out' }, it.at);
    tl.set(v, { transformOrigin: '50% 50%' }, it.at + it.sai);
  };

  /* ---------------------------------------------------------- GANCHO
   * As peças de trás moram entre o vídeo e a pessoa recortada (`#efxg-fg`);
   * o recorte é o MESMO quadro do vídeo, então só precisa existir na janela. */

  function some(tl, alvo, t1, d) {
    tl.to(alvo, { opacity: 0, duration: d || 0.3, ease: 'power2.in' }, t1 - (d || 0.3));
  }

  B.coverStory = function (el, gsap, tl, it) {
    var mast = document.getElementById('efxg-mast'), fr = document.getElementById('efxg-front');
    if (mast) {
      tl.set(mast, { opacity: 0, y: -70 }, it.t0);
      tl.to(mast, { opacity: 1, y: 0, duration: 0.6, ease: 'power3.out' }, it.t0 + 0.05);
      some(tl, mast, it.t1);
    }
    if (fr) {
      var ks = fr.children;
      for (var i = 0; i < ks.length; i++) {
        tl.set(ks[i], { opacity: 0, x: -50 }, it.t0);
        tl.to(ks[i], { opacity: 1, x: 0, duration: 0.4, ease: 'power3.out' }, it.t0 + 0.35 + i * 0.12);
      }
      // a frente sai um pouco antes: a legenda volta na virada do gancho
      some(tl, fr, it.t1 - 0.15);
    }
  };

  B.headlineWall = function (el, gsap, tl, it) {
    ['efxg-wall', 'efxg-wall-f'].forEach(function (id) {
      var w = document.getElementById(id);
      if (!w) return;
      var ps = w.querySelectorAll('.efx-hw-peca');
      for (var i = 0; i < ps.length; i++) {
        var at = parseFloat(ps[i].getAttribute('data-at')), rot = parseFloat(ps[i].getAttribute('data-rot'));
        tl.set(ps[i], { opacity: 0, scale: 1.55, rotation: rot * 2.2 }, it.t0);
        tl.to(ps[i], { opacity: 1, scale: 1, rotation: rot, duration: 0.2, ease: 'power3.out' }, at);
      }
      some(tl, w, it.t1);
    });
  };

  B.couchWall = function (el, gsap, tl, it) {
    var w = document.getElementById('efxg-couch');
    if (!w) return;
    var cs = w.querySelectorAll('.efx-cw-cel');
    for (var i = 0; i < cs.length; i++) {
      var at = parseFloat(cs[i].getAttribute('data-at'));
      tl.set(cs[i], { opacity: 0, scale: 0.6, y: 40 }, it.t0);
      tl.to(cs[i], { opacity: 1, scale: 1, y: 0, duration: 0.42, ease: 'back.out(1.6)' }, at);
    }
    tl.set(w, { y: 0 }, it.t0);
    tl.to(w, { y: -60, duration: it.t1 - it.t0, ease: 'none' }, it.t0);
    some(tl, w, it.t1);
  };

  /* QUEBRA DE MOLDURA: o quadro encolhe para um cartão e a cabeça recortada
   * passa por cima da borda de cima. O recorte mostra só o que fica ACIMA do
   * cartão — e esse limite anda junto com a borda, mesma curva e duração. */
  B.frameBreak = function (el, gsap, tl, it) {
    var v = document.getElementById('vidwin'), fg = document.getElementById('efxg-fg');
    var bd = document.getElementById('efxg-fb-borda');
    var c = it.card, d = it.dur, r = it.raio;
    var cheio = 'inset(0% 0% 0% 0% round 0px)';
    var card = 'inset(' + c.top + '% ' + c.lados + '% ' + c.base + '% ' + c.lados + '% round ' + r + 'px)';
    var fgFora = 'inset(0% 0% 100% 0%)', fgCard = 'inset(0% 0% ' + (100 - c.top) + '% 0%)';
    var ida = it.t0 + 0.05, volta = it.t1 - d;
    tl.set(v, { clipPath: cheio }, it.t0);
    tl.to(v, { clipPath: card, duration: d, ease: 'power3.inOut' }, ida);
    tl.to(v, { clipPath: cheio, duration: d, ease: 'power3.inOut' }, volta);
    tl.set(v, { clipPath: 'none' }, it.t1);
    if (fg) {
      tl.set(fg, { clipPath: fgFora }, it.t0);
      tl.to(fg, { clipPath: fgCard, duration: d, ease: 'power3.inOut' }, ida);
      tl.to(fg, { clipPath: fgFora, duration: d, ease: 'power3.inOut' }, volta);
    }
    if (bd) {
      tl.set(bd, { left: c.lados + '%', top: c.top + '%', width: (100 - 2 * c.lados) + '%',
                   height: (100 - c.top - c.base) + '%', opacity: 0, scale: 1.12 }, it.t0);
      tl.to(bd, { opacity: 1, scale: 1, duration: d, ease: 'power3.inOut' }, ida);
      tl.to(bd, { opacity: 0, scale: 1.12, duration: d, ease: 'power3.inOut' }, volta);
    }
  };

  /* ÓRBITA: cartões girando em volta da pessoa. Cada cartão existe duas
   * vezes — atrás do recorte e na frente dele — e só um aparece: o de trás na
   * metade de cima da elipse, o da frente na de baixo (perto da câmera). A
   * posição é função do tempo (proxy tweenado), determinística no seek. */
  B.orbit = function (el, gsap, tl, it) {
    var A = document.getElementById('efxg-orb-a'), F = document.getElementById('efxg-orb-f');
    if (!A || !F) return;
    var tras = A.querySelectorAll('.efx-orb-c'), fren = F.querySelectorAll('.efx-orb-c');
    var n = tras.length, o = { p: 0 }, entra = { a: 0 };
    var pinta = function () {
      for (var i = 0; i < n; i++) {
        var th = it.fase + o.p * 2 * Math.PI * it.voltas + i * 2 * Math.PI / n;
        var sn = Math.sin(th), x = it.cx + it.rx * Math.cos(th), y = it.cy + it.ry * sn;
        var sc = (0.7 + 0.34 * (sn + 1) / 2) * (0.6 + 0.4 * entra.a);
        var tf = 'translate(' + (x - it.w / 2).toFixed(1) + 'px,' + (y - it.h / 2).toFixed(1) + 'px) scale(' + sc.toFixed(3) + ')';
        tras[i].style.transform = tf; fren[i].style.transform = tf;
        tras[i].style.opacity = sn > 0 ? 0 : entra.a;
        fren[i].style.opacity = sn > 0 ? entra.a : 0;
      }
    };
    tl.set(o, { p: 0, onUpdate: pinta }, it.t0);
    tl.set(entra, { a: 0 }, it.t0);
    tl.to(entra, { a: 1, duration: 0.45, ease: 'back.out(1.4)' }, it.t0);
    tl.to(o, { p: 1, duration: it.t1 - it.t0, ease: 'none', onUpdate: pinta }, it.t0);
    tl.to(entra, { a: 0, duration: 0.3, ease: 'power2.in' }, it.t1 - 0.3);
  };

  /* MUNDO DE INTERFACE: peças de app em volta da pessoa — as de cima atrás
   * da cabeça, as das laterais na frente. Cada uma vive na palavra que a cita. */
  B.uiWorld = function (el, gsap, tl, it, cfg) {
    ['-a', '-f'].forEach(function (suf) {
      var w = document.getElementById(it.ref + suf);
      if (!w) return;
      var ps = w.querySelectorAll('.efx-ui-p');
      for (var i = 0; i < ps.length; i++) {
        var p = ps[i], at = parseFloat(p.getAttribute('data-at'));
        tl.set(p, { opacity: 0, scale: 0.7, y: 30 }, it.t0);
        tl.to(p, { opacity: 1, scale: 1, y: 0, duration: 0.35, ease: 'back.out(1.8)' }, at);
        tl.to(p, { y: -12, duration: Math.max(0.3, (it.t1 - at - 0.6) / 2), ease: 'sine.inOut',
                   yoyo: true, repeat: 1 }, at + 0.35);
        var bt = p.querySelector('.efx-ui-bt'), cur = p.querySelector('.efx-ui-cursor');
        if (bt && cur) {
          tl.set(cur, { x: 120, y: 120, opacity: 0 }, it.t0);
          tl.to(cur, { x: 0, y: 0, opacity: 1, duration: 0.4, ease: 'power2.out' }, at + 0.3);
          tl.to(bt, { scale: 0.9, duration: 0.08 }, at + 0.75);
          tl.to(bt, { scale: 1, duration: 0.18, ease: 'back.out(2)' }, at + 0.83);
          tl.to(cur, { scale: 0.85, duration: 0.08 }, at + 0.75);
          tl.to(cur, { scale: 1, duration: 0.15 }, at + 0.83);
        }
        var kn = p.querySelector('.efx-ui-kn'), sw = p.querySelector('.efx-ui-sw');
        if (kn) {
          tl.set(kn, { x: 0 }, it.t0); tl.set(sw, { backgroundColor: 'rgba(255,255,255,.22)' }, it.t0);
          tl.to(kn, { x: 40, duration: 0.22, ease: 'power2.inOut' }, at + 0.5);
          tl.to(sw, { backgroundColor: cfg.accent, duration: 0.22 }, at + 0.5);
        }
        var fill = p.querySelector('.efx-ui-pr-fill'), pct = p.querySelector('.efx-ui-pct');
        if (fill) {
          var o = { v: 0 };
          var pinta = (function (o, pct) { return function () { pct.textContent = Math.round(o.v) + '%'; }; })(o, pct);
          tl.set(fill, { scaleX: 0 }, it.t0);
          tl.to(fill, { scaleX: 1, duration: 1.4, ease: 'power1.inOut' }, at + 0.3);
          tl.set(o, { v: 0, onUpdate: pinta }, it.t0);
          tl.to(o, { v: 100, duration: 1.4, ease: 'power1.inOut', onUpdate: pinta }, at + 0.3);
        }
        var bu = p.querySelector('.efx-ui-bu-txt');
        if (bu) {
          var alvo = bu.getAttribute('data-alvo') || '';
          tl.set(bu, { textContent: '' }, it.t0);
          for (var c = 1; c <= alvo.length; c++) tl.set(bu, { textContent: alvo.slice(0, c) }, at + 0.35 + c * 0.045);
        }
      }
      some(tl, w, it.t1);
    });
  };

  /* RECUO PARA O APP (CTA): o quadro recua para dentro de uma janela de
   * editor. O "buraco" (um retângulo cuja sombra pinta o resto da tela) anda
   * junto com o `#vidwin`, mesma curva e duração — as bordas casam. */
  B.revelarApp = function (el, gsap, tl, it) {
    var v = document.getElementById('vidwin'), hole = document.getElementById('efx-rv-hole');
    var ui = document.getElementById('efx-rv-ui');
    var r = it.rect, s = r[2] / it.W;
    var dx = r[0] + r[2] / 2 - it.W / 2, dy = r[1] + r[3] / 2 - it.H / 2;
    var d = 0.9, t = it.t0 + 0.1;
    tl.set(v, { scale: 1, x: 0, y: 0, transformOrigin: '50% 50%' }, it.t0);
    tl.to(v, { scale: s, x: dx, y: dy, duration: d, ease: 'power3.inOut' }, t);
    tl.set(hole, { left: 0, top: 0, width: it.W, height: it.H, borderRadius: 0 }, it.t0);
    tl.to(hole, { left: r[0], top: r[1], width: r[2], height: r[3], borderRadius: it.raio,
                  duration: d, ease: 'power3.inOut' }, t);
    tl.set(v, { borderRadius: 0 }, it.t0);
    var bar = ui.querySelector('.efx-rv-bar'), tlh = ui.querySelector('.efx-rv-tl');
    var card = ui.querySelector('.efx-rv-card'), cur = ui.querySelector('.efx-rv-cursor');
    var bt = ui.querySelector('.efx-rv-bt');
    [bar, tlh, card].forEach(function (x, i) {
      tl.set(x, { opacity: 0, y: 40 }, it.t0);
      tl.to(x, { opacity: 1, y: 0, duration: 0.45, ease: 'power3.out' }, t + d * 0.6 + i * 0.12);
    });
    // o cartão pode ser mais largo que o vídeo recuado (cresce até o @ caber):
    // o cursor mira o botão pela borda direita DO CARTÃO
    var ccx = parseFloat(card.style.getPropertyValue('--cx')), ccw = parseFloat(card.style.getPropertyValue('--cw'));
    var dir = (isFinite(ccx) && isFinite(ccw)) ? ccx + ccw : r[0] + r[2] + 44;
    var bx = dir - 184, by = r[1] + r[3] + 136;
    tl.set(cur, { x: it.W * 0.8, y: it.H * 0.95, opacity: 0 }, it.t0);
    tl.to(cur, { x: bx, y: by, opacity: 1, duration: 0.7, ease: 'power2.inOut' }, it.clique - 0.75);
    tl.to(cur, { scale: 0.85, duration: 0.07 }, it.clique);
    tl.to(cur, { scale: 1, duration: 0.15 }, it.clique + 0.07);
    tl.to(bt, { scale: 0.92, duration: 0.07 }, it.clique);
    tl.to(bt, { scale: 1, backgroundColor: '#2a2a2a', duration: 0.2 }, it.clique + 0.07);
    tl.set(bt.querySelector('.a'), { opacity: 1 }, it.t0);
    tl.set(bt.querySelector('.b'), { opacity: 0 }, it.t0);
    tl.set(bt.querySelector('.a'), { opacity: 0 }, it.clique + 0.07);
    tl.set(bt.querySelector('.b'), { opacity: 1 }, it.clique + 0.07);
  };

  /* DOODLE BOIL (formato Caderno): a semente do ruído que entorta o contorno
   * troca a cada passo — o traço "ferve" como animação feita à mão. */
  B.boil = function (el, gsap, tl, it) {
    var n = document.getElementById('efx-boil-n');
    if (!n) return;
    for (var i = 0; i < it.n; i++) tl.set(n, { attr: { seed: 1 + (i % 7) * 3 } }, i * it.passo);
  };

  /* TRAVA: onde a pessoa recortada entra, a câmera volta a 1 — o plano que
   * foi aparado parou em zoom, e o recorte é do quadro sem zoom. */
  B.trava = function (el, gsap, tl, it) {
    tl.set(document.getElementById('a-roll'), { scale: 1, x: 0, y: 0 }, it.t0);
  };

  function buildTimeline(rootEl, gsap, tl, cfg) {
    var itens = cfg.itens || [];
    for (var i = 0; i < itens.length; i++) {
      var it = itens[i], f = B[it.tipo];
      if (!f) continue;
      var el = it.id ? document.getElementById(it.id) : null;
      if (it.id && !el) continue;
      f(el, gsap, tl, it, cfg);
    }
    return tl;
  }

  root.AVE_EFEITOS = { buildTimeline: buildTimeline, construtores: B };
})(typeof window !== 'undefined' ? window : this);

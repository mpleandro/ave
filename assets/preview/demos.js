/* DEMOS NO PLAYER — o que cada escolha FAZ, tocando em loop de 5s.
 *
 * Pedido do usuário (2026-10-15): escolher um formato, um efeito, um movimento
 * ou um CTA tem de MOSTRAR o comportamento, não só um ícone. Duas bases, e a
 * escolha de cada uma é sobre o que a demo precisa provar:
 *
 *   * BONECO ILUSTRADO — formatos e efeitos do gancho. Eles mudam o LAYOUT
 *     (tela dividida, moldura, fundo novo, peças atrás da pessoa) e precisam da
 *     pessoa recortada, que no editor ainda não existe. Um boneco desenhado em
 *     duas camadas (fundo + boneco) faz o "atrás da pessoa" de verdade.
 *   * O VÍDEO DO PROJETO — efeitos de conteúdo, movimento e CTA. Zoom e
 *     cartões só fazem sentido sobre o enquadramento real: um zoom no rosto de
 *     um boneco não diz nada sobre o seu plano.
 *
 * Fidelidade: os efeitos são montados com as MESMAS classes de efeitos.css e
 * animados pelos MESMOS construtores de efeitos.js do render (window.AVE_EFEITOS);
 * os CTAs com página são a página do render (/cta-demo/<modelo>.html). O que
 * muda é só o conteúdo, que aqui é de exemplo.
 */
(function () {
  'use strict';

  var W = 1080, H = 1920, DUR = 5;
  var atual = null;   // { key, tl, host, video, iframe }

  function h(tag, cls, pai, html) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html != null) e.innerHTML = html;
    if (pai) pai.appendChild(e);
    return e;
  }

  /* ---------------------------------------------------------- o boneco */
  var PAREDE = 'radial-gradient(70% 40% at 72% 30%, rgba(255,170,90,.35), transparent 70%),'
             + 'linear-gradient(180deg, #5f5b68, #36343c)';

  function bonecoSvg(contorno) {
    var st = contorno ? ' style="filter:drop-shadow(8px 0 0 #fff) drop-shadow(-8px 0 0 #fff) '
      + 'drop-shadow(0 8px 0 #fff) drop-shadow(0 -8px 0 #fff) drop-shadow(10px 14px 0 rgba(0,0,0,.25))"' : '';
    return '<svg class="dm-boneco" viewBox="0 0 1080 1920" preserveAspectRatio="xMidYMax slice"' + st + '>'
      + '<path d="M180 1920C190 1470 360 1310 540 1310S890 1470 900 1920Z" fill="#26262c"/>'
      + '<path d="M470 1300h140l-20 120h-100z" fill="#cfa587"/>'
      + '<ellipse cx="540" cy="1010" rx="205" ry="240" fill="#e2bd9f"/>'
      + '<path d="M335 980C320 770 450 715 545 715S770 770 748 985C712 870 620 845 545 845S380 870 335 980Z" fill="#2a211c"/>'
      + '<circle cx="468" cy="1010" r="15" fill="#2a211c"/><circle cx="612" cy="1010" r="15" fill="#2a211c"/>'
      + '<path d="M480 1120q60 46 120 0" stroke="#7a4a3a" stroke-width="12" fill="none" stroke-linecap="round"/>'
      + '</svg>';
  }

  /* a cena do boneco dentro de #vidwin (o "vídeo" da demo) e, se pedido, a
     cópia só do boneco como `#efxg-fg` — a pessoa recortada por cima */
  function baseBoneco(tela, comFg) {
    var vw = h('div', 'dm-vidwin', tela);
    vw.id = 'vidwin';
    var cena = h('div', 'dm-cena', vw);
    cena.id = 'a-roll';
    cena.style.background = PAREDE;
    cena.innerHTML = bonecoSvg(false);
    return vw;
  }
  function fgBoneco(tela, id) {
    var fg = h('div', 'dm-fg', tela, bonecoSvg(false));
    fg.id = id || 'efxg-fg';
    return fg;
  }

  /* o vídeo do projeto, do ponto atual, sem som, reiniciado a cada volta */
  function baseVideo(tela, src, t0) {
    var vw = h('div', 'dm-vidwin', tela);
    vw.id = 'vidwin';
    var v = h('video', 'dm-video', vw);
    v.id = 'a-roll';
    v.muted = true; v.playsInline = true; v.preload = 'auto';
    v.src = src;
    v.addEventListener('loadedmetadata', function () {
      try { v.currentTime = Math.min(t0 || 0, Math.max(0, v.duration - DUR - 0.1)); } catch (e) { /* */ }
      v.play().catch(function () {});
    }, { once: true });
    v._t0 = t0 || 0;
    return v;
  }

  /* ---------------------------------------------------------- marcação dos efeitos
   * As mesmas classes que helpers/efeitos_compose.py escreve. */
  function cardChecklist(tela, id, accent) {
    var itens = ['Gravar o vídeo', 'Cortar os erros', 'Publicar'];
    var linhas = itens.map(function (t, i) {
      return '<div class="efx-ck-item" data-at="' + (1.0 + i * 0.9) + '"><div class="efx-ck-bola">'
        + '<svg viewBox="0 0 24 24"><path d="M5 12.5l4.2 4.2L19 7"/></svg></div>'
        + '<div class="efx-ck-txt">' + t + '</div></div>';
    }).join('');
    var cont = [0, 1, 2, 3].map(function (i) { return '<span class="efx-ck-n">' + i + ' de 3</span>'; }).join('');
    var b = h('div', 'efx efx-checklist', tela,
      '<div class="efx-card efx-ck"><div class="efx-ck-head"><span class="efx-ponto"></span>'
      + '<span class="efx-ck-tit">passo a passo</span><span class="efx-ck-cont">' + cont + '</span></div>'
      + linhas + '</div>');
    b.id = id;
    b.style.cssText = 'left:140px; top:1010px; width:800px; transform-origin:0 0; --efx-esc:1';
    return b;
  }
  function cardChart(tela, id) {
    var vals = [12, 30, 55, 140, 380], rot = ['seg', 'ter', 'qua', 'qui', 'sex'];
    var cols = vals.map(function (v, i) {
      return '<div class="efx-ch-col' + (i === 4 ? ' dest' : '') + '"><div class="efx-ch-val">' + v + '</div>'
        + '<div class="efx-ch-bar" data-h="' + (v / 380).toFixed(3) + '"></div>'
        + '<div class="efx-ch-rot">' + rot[i] + '</div></div>';
    }).join('');
    var b = h('div', 'efx efx-chart', tela,
      '<div class="efx-card efx-ch"><div class="efx-ch-head"><span class="efx-ponto"></span>'
      + '<span class="efx-ch-tit">resultado da semana</span></div>'
      + '<div class="efx-ch-big" data-alvo="3" data-fmt="+3 mil">+3 mil</div>'
      + '<div class="efx-ch-area">' + cols + '</div></div>');
    b.id = id;
    b.style.cssText = 'left:140px; top:1000px; width:800px; height:520px; transform-origin:0 0; --efx-esc:1';
    return b;
  }
  function cardPhone(tela, id) {
    var nots = [['Instagram', 'Novo comentário: 🔥🔥'], ['WhatsApp', 'Vi seu vídeo, top!']];
    var cards = nots.map(function (n, i) {
      return '<div class="efx-ph-not" data-at="' + (1.0 + i * 0.9) + '"><div class="efx-ph-ico"></div><div>'
        + '<div class="efx-ph-app">' + n[0] + '</div><div class="efx-ph-ntx">' + n[1] + '</div></div></div>';
    }).join('');
    var b = h('div', 'efx efx-phonebox dir', tela,
      '<div class="efx-phone"><div class="efx-ph-ilha"></div><div class="efx-ph-tela notificacao">'
      + '<div class="efx-ph-hora">9:41</div><div class="efx-ph-nots">' + cards + '</div></div></div>');
    b.id = id;
    b.style.cssText = 'left:500px; top:900px; width:350px; height:716px; --efx-k:0.814';
    return b;
  }
  function cardsUi(tela, id) {
    var pecas = [
      ['notificacao', 130, 330, '<div class="efx-ui-not"><span class="efx-ui-ico"></span><span><b>agora</b><i>Novo seguidor</i></span></div>'],
      ['busca', 520, 420, '<div class="efx-ui-bu"><svg viewBox="0 0 16 16"><circle cx="7" cy="7" r="4.5"/><path d="M10.4 10.4L14 14"/></svg><span class="efx-ui-bu-txt" data-alvo="como crescer"></span><span class="efx-ui-caret"></span></div>'],
      ['botao', 150, 1150, '<div class="efx-ui-bt"><span>Começar</span></div><svg class="efx-ui-cursor" viewBox="0 0 24 24"><path d="M4 2l16 10-7 1.6L9.6 21z"/></svg>'],
      ['toggle', 560, 1240, '<div class="efx-ui-tg"><span>Automático</span><span class="efx-ui-sw"><span class="efx-ui-kn"></span></span></div>'],
      ['progresso', 300, 1420, '<div class="efx-ui-pr"><div class="efx-ui-pr-top"><span>Processando</span><span class="efx-ui-pct">0%</span></div><div class="efx-ui-pr-bar"><div class="efx-ui-pr-fill"></div></div></div>']];
    var f = h('div', 'efx efx-ui', tela);
    f.id = id + '-f';
    pecas.forEach(function (p, i) {
      var e = h('div', 'efx-ui-p ' + p[0], f, p[3]);
      e.setAttribute('data-at', String(0.4 + i * 0.5));
      e.style.left = p[1] + 'px'; e.style.top = p[2] + 'px';
    });
  }

  /* ---------------------------------------------------------- legenda de exemplo */
  function legenda(tela, tl, palavras, accent) {
    var cap = h('div', 'dm-cap', tela);
    palavras.forEach(function (p, i) {
      var s = h('span', '', cap, p);
      tl.set(s, { opacity: 0.35, color: '#fff' }, 0);
      tl.set(s, { opacity: 1, color: i % 3 === 2 ? accent : '#fff' }, 0.4 + i * 0.35);
    });
    return cap;
  }

  /* ---------------------------------------------------------- FORMATOS (boneco) */
  var FORMATOS = {
    limpa: function (tela, tl, a) {
      baseBoneco(tela);
      legenda(tela, tl, ['o', 'seu', 'vídeo', 'assim,', 'limpo'], a);
    },
    split: function (tela, tl, a) { splitDemo(tela, tl, a, true); },
    split2: function (tela, tl, a) { splitDemo(tela, tl, a, false); },
    brollOverlay: function (tela, tl, a) {
      baseBoneco(tela);
      var esc = h('div', 'dm-escuro', tela);
      var txt = h('div', 'dm-bo', tela, '<span>3</span><span>ERROS</span><span>QUE</span><span>TRAVAM</span>');
      tl.set(esc, { opacity: 0 }, 0); tl.to(esc, { opacity: 1, duration: 0.3 }, 0.8);
      txt.querySelectorAll('span').forEach(function (s, i) {
        if (i === 1) s.style.color = a;
        tl.set(s, { opacity: 0, scale: 1.6 }, 0);
        tl.to(s, { opacity: 1, scale: 1, duration: 0.22, ease: 'back.out(2)' }, 1.0 + i * 0.35);
      });
      tl.to([esc, txt], { opacity: 0, duration: 0.3 }, 4.3);
    },
    animTexto: function (tela, tl, a) {
      var fundo = h('div', 'dm-escuro dm-grade', tela);
      fundo.style.opacity = 1;
      var t = h('div', 'dm-kin', tela, '<div>o texto</div><div>nasce</div><div class="ac">no tempo</div><div>da voz</div>');
      t.querySelector('.ac').style.color = a;
      t.querySelectorAll('div').forEach(function (d, i) {
        tl.set(d, { opacity: 0, y: 40 }, 0);
        tl.to(d, { opacity: 1, y: 0, duration: 0.3, ease: 'power3.out' }, 0.4 + i * 0.7);
      });
    },
    anim3d: function (tela, tl, a) {
      tela.style.perspective = '1600px';
      var vw = baseBoneco(tela);
      var piso = h('div', 'dm-piso', tela);
      tl.set(vw, { rotationY: 0, z: 0, scale: 1 }, 0);
      tl.set(piso, { opacity: 0 }, 0);
      tl.to(vw, { rotationY: -28, scale: 0.72, duration: 1.2, ease: 'power3.inOut' }, 0.6);
      tl.to(piso, { opacity: 1, duration: 0.8 }, 0.8);
      tl.to(vw, { rotationY: 0, scale: 1, duration: 1.0, ease: 'power3.inOut' }, 3.6);
      tl.to(piso, { opacity: 0, duration: 0.6 }, 3.8);
    },
    explicativo: function (tela, tl, a) {
      var vw = baseBoneco(tela);
      var lista = h('div', 'dm-lista', tela, '<div><b>1</b>Planejar</div><div><b>2</b>Gravar</div><div><b>3</b>Cortar</div>');
      lista.querySelectorAll('b').forEach(function (b) { b.style.background = a; });
      tl.set(vw, { clipPath: 'circle(100% at 50% 50%)', scale: 1, x: 0, y: 0 }, 0);
      tl.to(vw, { clipPath: 'circle(17% at 50% 50%)', scale: 1, x: 250, y: -560, duration: 0.6, ease: 'power3.inOut' }, 0.7);
      lista.querySelectorAll('div').forEach(function (d, i) {
        tl.set(d, { opacity: 0, x: 120 }, 0);
        tl.to(d, { opacity: 1, x: 0, duration: 0.3, ease: 'power2.out' }, 1.3 + i * 0.5);
      });
      tl.to(lista, { opacity: 0, duration: 0.25 }, 3.9);
      tl.to(vw, { clipPath: 'circle(100% at 50% 50%)', x: 0, y: 0, duration: 0.6, ease: 'power3.inOut' }, 4.0);
      tl.set(lista, { opacity: 1 }, 0);
    },
    ilustrado: function (tela, tl, a) {
      baseBoneco(tela);
      cardChecklist(tela, 'dmx-ck', a);
      AVE_EFEITOS.construtores.checklist(document.getElementById('dmx-ck'), gsap, tl,
        { t0: 0.2, t1: 4.8 }, cfgFx(a));
      zoomJs(tl, 'zoomPunch', a);
    },
    fundoTrocado: function (tela, tl, a) {
      var fundos = [PAREDE, 'linear-gradient(180deg,#7ab8e8,#e8d6b8 70%)',
        'radial-gradient(80% 50% at 50% 28%, rgba(255,82,45,.6), transparent 70%), linear-gradient(180deg,#1c1411,#0b0a0a)'];
      var camadas = fundos.map(function (f) { var d = h('div', 'dm-fundo', tela); d.style.background = f; return d; });
      fgBoneco(tela, 'dmx-pessoa');
      camadas.forEach(function (c, i) {
        tl.set(c, { opacity: i === 0 ? 1 : 0 }, 0);
        if (i) tl.to(c, { opacity: 1, duration: 0.4 }, i * 1.6);
      });
    },
    caderno: function (tela, tl, a) {
      var p = h('div', 'efx efx-cd-papel', tela);
      p.style.inset = '0';
      p.innerHTML = '<svg class="efx-cd-rab" viewBox="0 0 1080 1920" preserveAspectRatio="none">'
        + '<path class="dm-rab" d="M120 300c90-60 160 50 250-10s170 60 260 0 160 50 300-20" stroke="#7b8fd6" stroke-width="16" fill="none" stroke-linecap="round" pathLength="1"/>'
        + '<path class="dm-rab" d="M840 520l40 40m0-40l-40 40" stroke="#d84a3a" stroke-width="8" fill="none" stroke-linecap="round" pathLength="1"/></svg>';
      var fg = h('div', 'dm-fg', tela, bonecoSvg(true));
      p.querySelectorAll('.dm-rab').forEach(function (r, i) {
        r.style.strokeDasharray = 1;
        tl.set(r, { strokeDashoffset: 1 }, 0);
        tl.to(r, { strokeDashoffset: 0, duration: 0.8, ease: 'power1.inOut' }, 0.4 + i * 0.6);
      });
      // o contorno "ferve": um tremor a cada 4 quadros
      for (var i = 0; i < DUR * 7.5; i++) {
        tl.set(fg, { x: ((i * 7) % 5) - 2, y: ((i * 3) % 5) - 2, rotation: ((i * 5) % 3 - 1) * 0.3 }, i / 7.5);
      }
    },
  };

  function splitDemo(tela, tl, a, cima) {
    var vw = baseBoneco(tela);
    var arte = h('div', 'dm-arte', tela,
      '<svg viewBox="0 0 1080 960" preserveAspectRatio="none"><rect width="1080" height="960" fill="#f4c27a"/>'
      + '<circle cx="780" cy="300" r="120" fill="#fff3d6"/><path d="M0 960L320 520l220 260 180-180 360 360Z" fill="#c9673f"/></svg>');
    arte.style.top = cima ? '0' : '960px';
    var costura = h('div', 'dm-costura', tela);
    costura.style.top = '958px';
    tl.set(arte, { y: cima ? -960 : 960 }, 0);
    tl.set(vw, { y: 0, scale: 1 }, 0);
    tl.to(arte, { y: 0, duration: 0.5, ease: 'power3.out' }, 0.5);
    tl.to(vw, { y: cima ? 480 : -480, duration: 0.5, ease: 'power3.out' }, 0.5);
    tl.set(costura, { opacity: 0 }, 0); tl.to(costura, { opacity: 1, duration: 0.2 }, 0.9);
    legenda(tela, tl, ['imagem', 'e', 'você', 'juntos'], a).style.top = '880px';
  }

  /* ---------------------------------------------------------- efeitos e movimento (vídeo) */
  function cfgFx(a) {
    return { entrada: 0.38, saida: 0.26, accent: a, chart: { barraMs: 0.55, stagger: 0.09 } };
  }
  function zoomJs(tl, tipo, a) {
    var B = AVE_EFEITOS.construtores;
    if (tipo === 'zoomPunch') B.zoomPunch(null, gsap, tl, { t0: 1.6, t1: 3.2, escala: 1.32, ox: 50, oy: 38 });
    if (tipo === 'zoomThrough') B.zoomThrough(null, gsap, tl, { at: 2.5, entra: 0.23, sai: 0.3, escala: 2.6, blur: 16, ox: 50, oy: 38 });
  }

  var EFEITOS = {
    checklist: function (tela, tl, a) {
      cardChecklist(tela, 'dmx-ck', a);
      AVE_EFEITOS.construtores.checklist(document.getElementById('dmx-ck'), gsap, tl, { t0: 0.2, t1: 4.8 }, cfgFx(a));
    },
    chartGrow: function (tela, tl, a) {
      cardChart(tela, 'dmx-ch');
      AVE_EFEITOS.construtores.chartGrow(document.getElementById('dmx-ch'), gsap, tl, { t0: 0.2, t1: 4.8 }, cfgFx(a));
    },
    phoneMockup: function (tela, tl, a) {
      cardPhone(tela, 'dmx-ph');
      AVE_EFEITOS.construtores.phoneMockup(document.getElementById('dmx-ph'), gsap, tl,
        { t0: 0.2, t1: 4.8, lado: 'dir' }, cfgFx(a));
    },
    uiWorld: function (tela, tl, a) {
      cardsUi(tela, 'dmx-ui');
      AVE_EFEITOS.construtores.uiWorld(null, gsap, tl, { ref: 'dmx-ui', t0: 0.2, t1: 4.8 }, cfgFx(a));
    },
  };

  var MOVIMENTO = {
    zoomPunch: function (tela, tl, a) { zoomJs(tl, 'zoomPunch', a); },
    zoomThrough: function (tela, tl, a) { zoomJs(tl, 'zoomThrough', a); },
    zoomCuts: function (tela, tl) {
      var v = document.getElementById('a-roll');
      [1, 1.18, 1.08, 1.22].forEach(function (z, i) { tl.set(v, { scale: z, transformOrigin: '50% 40%' }, i * 1.25); });
    },
    zoomAuto: function (tela, tl) {
      var v = document.getElementById('a-roll');
      tl.set(v, { scale: 1, transformOrigin: '50% 40%' }, 0);
      tl.to(v, { scale: 1.14, duration: DUR, ease: 'none' }, 0);
    },
    tracking: function (tela, tl) {
      var v = document.getElementById('a-roll');
      tl.set(v, { scale: 1.3, x: 0, y: 0, transformOrigin: '50% 40%' }, 0);
      tl.to(v, { x: 60, y: -30, duration: 1.6, ease: 'sine.inOut' }, 0.2);
      tl.to(v, { x: -50, y: 20, duration: 1.8, ease: 'sine.inOut' }, 1.8);
      tl.to(v, { x: 0, y: 0, duration: 1.2, ease: 'sine.inOut' }, 3.6);
    },
  };

  /* ---------------------------------------------------------- gancho (boneco) */
  var GANCHO = {
    coverStory: function (tela, tl, a) {
      baseBoneco(tela);
      var m = h('div', 'efx efx-cover-mast', tela, '<div class="efx-cover-ed">EDIÇÃO ESPECIAL</div><div class="efx-cover-tit">CAPA</div>');
      m.id = 'efxg-mast'; m.style.setProperty('--mast', '300px');
      fgBoneco(tela);
      var f = h('div', 'efx efx-cover-front', tela, '<div class="efx-cover-tag">EXCLUSIVO</div>'
        + '<div class="efx-cover-linha">o segredo</div><div class="efx-cover-linha">por trás disso</div>'
        + '<div class="efx-cover-bar"><div class="efx-cover-cod"></div><div class="efx-cover-num">Nº 01</div></div>');
      f.id = 'efxg-front';
      AVE_EFEITOS.construtores.coverStory(null, gsap, tl, { t0: 0.1, t1: 4.9 });
    },
    headlineWall: function (tela, tl, a) {
      baseBoneco(tela);
      var w = h('div', 'efx efx-hw', tela);
      w.id = 'efxg-wall';
      var pos = [[0.03, 0.12, -6, 'jornal', 'Todo mundo fala disso'], [0.64, 0.1, 5, 'tweet', 'isso mudou meu jogo'],
                 [0.02, 0.33, 4, 'nota', 'ninguém te conta'], [0.66, 0.31, -5, 'jornal', 'O fim de uma era']];
      pos.forEach(function (p, i) {
        var c = p[3] === 'tweet'
          ? '<div class="efx-hw-tw-top"><span class="efx-hw-av"></span><span><b>Comentário</b><i>@internet</i></span></div><div class="efx-hw-tw-txt">' + p[4] + '</div>'
          : p[3] === 'nota' ? '<div class="efx-hw-nota">“' + p[4] + '”</div>'
            : '<div class="efx-hw-fonte">O DIÁRIO</div><div class="efx-hw-man">' + p[4] + '</div>';
        var e = h('div', 'efx-hw-peca ' + p[3], w, c);
        e.setAttribute('data-at', String(0.3 + i * 0.25)); e.setAttribute('data-rot', String(p[2]));
        e.style.left = (p[0] * 100) + '%'; e.style.top = (p[1] * 100) + '%';
      });
      fgBoneco(tela);
      AVE_EFEITOS.construtores.headlineWall(null, gsap, tl, { t0: 0.1, t1: 4.9 });
    },
    couchWall: function (tela, tl, a) {
      baseBoneco(tela);
      var w = h('div', 'efx efx-cw', tela);
      w.id = 'efxg-couch';
      for (var i = 0; i < 12; i++) {
        var c = i % 4, r = Math.floor(i / 4);
        var e = h('div', 'efx-cw-cel', w, '<span class="efx-cw-v">▶ ' + ['1,2 mi', '380 mil', '92 mil', '2,4 mi'][i % 4] + '</span>');
        e.style.cssText = 'left:' + (2 + c * 24.7) + '%; top:' + (3 + r * 23) + '%; width:23.5%; height:21.8%; background:'
          + ['#8a5a44', '#4f6a8a', '#7a7a3a', '#5a4a7a'][(i + r) % 4];
        e.setAttribute('data-at', String(0.1 + (Math.abs(c - 1.5) + r) * 0.09));
      }
      fgBoneco(tela);
      AVE_EFEITOS.construtores.couchWall(null, gsap, tl, { t0: 0.1, t1: 4.9 });
    },
    orbit: function (tela, tl, a) {
      baseBoneco(tela);
      var cartas = '';
      ['#8a5a44', '#4f6a8a', '#7a7a3a', '#5a4a7a', '#3a7a6a', '#9a6a3a'].forEach(function (c) {
        cartas += '<div class="efx-orb-c" style="width:210px; height:374px; background:' + c + '"></div>';
      });
      var A = h('div', 'efx efx-orb', tela, cartas); A.id = 'efxg-orb-a';
      fgBoneco(tela);
      var F = h('div', 'efx efx-orb', tela, cartas); F.id = 'efxg-orb-f';
      AVE_EFEITOS.construtores.orbit(null, gsap, tl, { t0: 0.1, t1: 4.9, cx: 540, cy: 1180, rx: 465, ry: 135,
                                                        w: 210, h: 374, voltas: 0.8, fase: 0.4 });
    },
    frameBreak: function (tela, tl, a) {
      var bg = h('div', 'efx efx-fb-bg', tela); bg.style.inset = '0';
      baseBoneco(tela);
      var bd = h('div', 'efx efx-fb-borda', tela); bd.id = 'efxg-fb-borda';
      var fg = fgBoneco(tela); fg.style.clipPath = 'inset(0 0 100% 0)';
      AVE_EFEITOS.construtores.frameBreak(null, gsap, tl, { t0: 0.1, t1: 4.9, dur: 0.5, raio: 46,
                                                             card: { top: 42, lados: 10, base: 4 } });
    },
    vertigo: function (tela, tl, a) {
      var fundo = h('div', 'dm-fundo dm-corredor', tela);
      fgBoneco(tela, 'dmx-pessoa');
      tl.set(fundo, { scale: 1 }, 0);
      tl.to(fundo, { scale: 0.62, duration: 3.2, ease: 'sine.inOut' }, 0.5);
      tl.to(fundo, { scale: 1, duration: 0.8, ease: 'power2.inOut' }, 4.0);
    },
  };

  /* ---------------------------------------------------------- CTA */
  function ctaDemo(tela, tl, a, modelo, est) {
    if (modelo === 'revelarApp') {
      var hole = h('div', 'efx efx-rv-hole', tela); hole.id = 'efx-rv-hole';
      var ui = h('div', 'efx efx-rv-ui', tela,
        '<div class="efx-rv-bar"><i></i><i></i><i></i><span>corte_final.mp4</span></div>'
        + '<div class="efx-rv-tl"><span style="flex:3"></span><span style="flex:5"></span><span style="flex:2"></span><span style="flex:4"></span><b></b></div>'
        + '<div class="efx-rv-card"><div class="efx-rv-av"></div><div class="efx-rv-tx"><b>' + (est.arroba || '@seuperfil')
        + '</b><i>conteúdo novo toda semana</i></div><div class="efx-rv-bt"><span class="a">Seguir</span>'
        + '<span class="b">Seguindo ✓</span></div></div><svg class="efx-rv-cursor" viewBox="0 0 24 24"><path d="M4 2l16 10-7 1.6L9.6 21z"/></svg>');
      ui.id = 'efx-rv-ui';
      var vw = 648, vh = 1152, vx = 216, vy = 330;
      ui.style.cssText = '--vx:' + vx + 'px; --vy:' + vy + 'px; --vw:' + vw + 'px; --vh:' + vh + 'px';
      AVE_EFEITOS.construtores.revelarApp(null, gsap, tl, { t0: 0.2, t1: 5, clique: 2.8, rect: [vx, vy, vw, vh],
                                                             W: W, H: H, raio: 36 });
      return null;
    }
    if (modelo === 'instagram-simples') {
      var b = h('div', 'dm-segue', tela, '<span class="a">Seguir</span><span class="b">Seguindo</span>');
      tl.set(b, { opacity: 0, scale: 0.6 }, 0);
      tl.to(b, { opacity: 1, scale: 1, duration: 0.35, ease: 'back.out(2)' }, 0.6);
      tl.to(b, { scale: 0.9, duration: 0.08 }, 2.0); tl.to(b, { scale: 1, duration: 0.15 }, 2.08);
      tl.set(b.querySelector('.a'), { opacity: 1 }, 0); tl.set(b.querySelector('.b'), { opacity: 0 }, 0);
      tl.set(b.querySelector('.a'), { opacity: 0 }, 2.08); tl.set(b.querySelector('.b'), { opacity: 1 }, 2.08);
      tl.to(b, { opacity: 0, duration: 0.3 }, 4.4);
      return null;
    }
    // os modelos com página: a página DO RENDER, num iframe, em loop
    var f = h('iframe', 'dm-iframe', tela);
    f.src = '/cta-demo/' + modelo + '.html';
    f.addEventListener('load', function () {
      try {
        var w = f.contentWindow, t = w.__timelines && w.__timelines.demo;
        var vids = w.document.querySelectorAll('video');
        if (t) { t.repeat(-1); t.repeatDelay(0.6); t.play(0); }
        vids.forEach(function (v) { v.muted = true; v.loop = true; v.play().catch(function () {}); });
      } catch (e) { /* mesma origem; se falhar, a página fica parada */ }
    });
    return f;
  }

  /* ---------------------------------------------------------- palco */
  function encaixar(host, tela) {
    var r = host.getBoundingClientRect();
    var k = Math.min(r.width / W, r.height / H);
    tela.style.transform = 'translate(' + ((r.width - W * k) / 2) + 'px,' + ((r.height - H * k) / 2) + 'px) scale(' + k + ')';
  }

  function parar() {
    if (!atual) return;
    if (atual.tl) atual.tl.kill();
    atual.host.innerHTML = '';
    atual.host.classList.add('hidden');
    atual = null;
  }

  /* spec: {kind: 'formato'|'efeito'|'movimento'|'gancho'|'cta', id, accent,
            videoSrc, t0, nome, arroba} */
  function mostrar(host, spec) {
    var key = JSON.stringify([spec.kind, spec.id, spec.accent, spec.videoSrc ? 1 : 0]);
    if (atual && atual.key === key) { encaixar(host, atual.tela); return; }
    parar();
    if (!spec || !spec.id && spec.kind !== 'formato') return;
    if (typeof gsap === 'undefined' || typeof AVE_EFEITOS === 'undefined') return;
    host.classList.remove('hidden');
    var tela = h('div', 'dm-tela', host);
    var tl = gsap.timeline({ paused: true, repeat: -1, repeatDelay: 0.4 });
    var a = spec.accent || '#ff3b30';
    tela.style.setProperty('--efx-accent', a);
    var video = null;
    var porVideo = spec.kind === 'efeito' || spec.kind === 'movimento' || spec.kind === 'cta';
    if (porVideo) {
      if (spec.videoSrc) video = baseVideo(tela, spec.videoSrc, spec.t0);
      else baseBoneco(tela);
    }
    if (spec.kind === 'formato') (FORMATOS[spec.id] || FORMATOS.limpa)(tela, tl, a);
    else if (spec.kind === 'efeito' && EFEITOS[spec.id]) EFEITOS[spec.id](tela, tl, a);
    else if (spec.kind === 'movimento' && MOVIMENTO[spec.id]) MOVIMENTO[spec.id](tela, tl, a);
    else if (spec.kind === 'gancho' && GANCHO[spec.id]) GANCHO[spec.id](tela, tl, a);
    else if (spec.kind === 'cta') ctaDemo(tela, tl, a, spec.id, spec);
    // a duração da volta é SEMPRE 5s, mesmo que o último tween acabe antes
    tl.set({}, {}, DUR);
    tl.eventCallback('onRepeat', function () {
      if (video) { try { video.currentTime = video._t0; video.play().catch(function () {}); } catch (e) { /* */ } }
    });
    if (spec.nome) h('div', 'dm-rotulo', host, 'demonstração · ' + spec.nome);
    atual = { key: key, tl: tl, host: host, tela: tela, video: video };
    encaixar(host, tela);
    tl.play(0);
  }

  window.AVE_DEMOS = { mostrar: mostrar, parar: parar, ativo: function () { return !!atual; },
                       encaixar: function () { if (atual) encaixar(atual.host, atual.tela); } };
})();

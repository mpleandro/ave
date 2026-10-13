/* MOLDURA EXPLICATIVA — o construtor da timeline.
 *
 * Tudo em tempo ABSOLUTO na timeline do HyperFrames (seek-safe): nada de
 * transição de CSS nem callback. Os números vêm medidos da referência
 * (Video-43569):
 *   - moldura entrando num formato: 0,30s power2.inOut, 0,1s ANTES da palavra
 *   - voltando ao sujeito grande:   0,33s power3.out
 *   - troca de fundo: wipe circular nascendo no centro do DESTINO da moldura,
 *     0,2s power1.in — leva o olho para onde o rosto vai
 *   - item de lista: da direita (+144px), 0,15s power3.out, na palavra
 *   - o conteúdo da cena sai 0,1s antes da troca (some antes de a moldura andar)
 *
 * cfg: {k, accent, capColor, capEscura, estados:[{t0,t1,layout,base,fundo,
 *       oculto,rect:{x,y,w,h,r},video:{vx,vy,vw,vh}}]}
 */
(function () {
  var I = {
    calendario: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
    prato: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="4"/>',
    check: '<path d="M5 12l5 5 9-10"/>',
    lista: '<path d="M9 6h11M9 12h11M9 18h11M4 6h.01M4 12h.01M4 18h.01"/>',
    grafico: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
    dinheiro: '<rect x="2" y="6" width="20" height="12" rx="2"/><circle cx="12" cy="12" r="3"/>',
    relogio: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    pessoa: '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 4-6 8-6s8 2 8 6"/>',
    grupo: '<circle cx="9" cy="8" r="3.5"/><circle cx="17" cy="9" r="2.5"/><path d="M2 20c0-3.5 3-5.5 7-5.5s7 2 7 5.5M16 14.5c3 0 6 1.5 6 4.5"/>',
    casa: '<path d="M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>',
    celular: '<rect x="6" y="2" width="12" height="20" rx="3"/><path d="M11 18h2"/>',
    ideia: '<path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-4 10.5c.8.8 1 1.5 1 2.5h6c0-1 .2-1.7 1-2.5A6 6 0 0 0 12 3z"/>',
    alvo: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
    raio: '<path d="M13 2L4 14h7l-1 8 9-12h-7z"/>',
    coracao: '<path d="M12 20s-8-5-8-11a4.5 4.5 0 0 1 8-2.8A4.5 4.5 0 0 1 20 9c0 6-8 11-8 11z"/>',
    chat: '<path d="M4 5h16v11H9l-5 4z"/>',
    livro: '<path d="M4 4h7a3 3 0 0 1 3 3v13a2 2 0 0 0-2-2H4zM20 4h-6M20 4v14h-6"/>',
    estrela: '<path d="M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9z"/>',
    seta: '<path d="M4 12h16M14 6l6 6-6 6"/>',
    cadeado: '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
    play: '<path d="M7 4l13 8-13 8z"/>',
    engrenagem: '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1"/>',
    foguete: '<path d="M12 3c4 2 6 6 6 10l-3 3H9l-3-3c0-4 2-8 6-10zM9 16l-2 5 5-3 5 3-2-5"/><circle cx="12" cy="10" r="1.5"/>',
    lupa: '<circle cx="11" cy="11" r="7"/><path d="M21 21l-5-5"/>',
    mundo: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
    camera: '<rect x="3" y="7" width="18" height="13" rx="2"/><circle cx="12" cy="13" r="4"/><path d="M8 7l2-3h4l2 3"/>'
  };
  var SVG = function (d) {
    return '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">' + d + '</svg>';
  };

  function px(o) {
    return { left: o.x + 'px', top: o.y + 'px', width: o.w + 'px', height: o.h + 'px' };
  }
  function moldura(e) {
    var r = e.rect;
    var m = px(r); m.borderRadius = r.r + 'px';
    return m;
  }
  function borda(e) {
    var r = e.rect, b = 6;
    var m = px({ x: r.x - b, y: r.y - b, w: r.w + 2 * b, h: r.h + 2 * b });
    m.borderRadius = (r.r + b) + 'px';
    return m;
  }
  function video(e) {
    // o #a-roll é filho da moldura: a posição dele é RELATIVA a ela
    var v = e.video, r = e.rect;
    return px({ x: v.vx - r.x, y: v.vy - r.y, w: v.vw, h: v.vh });
  }
  function sobreFundo(e) {
    // onde a legenda (75% da altura) cai sobre o fundo, não sobre o vídeo
    return e.layout === 'pip' || e.layout === 'oculto';
  }

  window.AVE_EXPLICATIVO = {
    buildTimeline: function (root, gsap, tl, cfg) {
      var es = cfg.estados || [];
      if (!es.length) return;
      var win = document.getElementById('vidwin');
      var vid = document.getElementById('a-roll');
      var bd = document.getElementById('exp-borda');
      var fundo = document.getElementById('exp-fundo');
      var cap = root.querySelector('[style*="--cap-color"]');
      win.classList.add('exp-moldura');

      // ícones: preenchidos uma vez, na montagem
      root.querySelectorAll('.exp-ico[data-icone]').forEach(function (el) {
        var d = I[el.getAttribute('data-icone')];
        if (d) el.innerHTML = SVG(d);
      });
      root.querySelectorAll('.exp-bola').forEach(function (el) {
        el.innerHTML = SVG(I.check);
      });

      // estado inicial
      var e0 = es[0];
      gsap.set(win, Object.assign(moldura(e0), { opacity: e0.oculto ? 0 : 1 }));
      gsap.set(bd, Object.assign(borda(e0), { opacity: (e0.oculto || e0.layout === 'cheia') ? 0 : 1 }));
      gsap.set(vid, video(e0));
      var bg0 = document.createElement('div');
      bg0.className = 'exp-bg ' + (e0.fundo || 'escuro');
      fundo.appendChild(bg0);
      if (cap) tl.set(cap, { '--cap-color': (sobreFundo(e0) && e0.fundo === 'claro') ? cfg.capEscura : cfg.capColor }, 0);

      var fundoAtual = e0.fundo || 'escuro';
      for (var i = 1; i < es.length; i++) {
        var e = es[i], p = es[i - 1];
        var at = Math.max(0, e.t0 - 0.1);
        var dur = e.base ? 0.33 : 0.30;
        var ease = e.base ? 'power3.out' : 'power2.inOut';
        tl.to(win, Object.assign(moldura(e), { opacity: e.oculto ? 0 : 1, duration: dur, ease: ease }), at);
        tl.to(vid, Object.assign(video(e), { duration: dur, ease: ease }), at);
        tl.to(bd, Object.assign(borda(e), {
          opacity: (e.oculto || e.layout === 'cheia') ? 0 : 1, duration: dur, ease: ease
        }), at);
        var f = e.fundo || fundoAtual;
        if (f !== fundoAtual) {
          var cx = e.rect.x + e.rect.w / 2, cy = e.rect.y + e.rect.h / 2;
          var bg = document.createElement('div');
          bg.className = 'exp-bg ' + f;
          fundo.appendChild(bg);
          tl.fromTo(bg, { clipPath: 'circle(0px at ' + cx + 'px ' + cy + 'px)' },
                    { clipPath: 'circle(2400px at ' + cx + 'px ' + cy + 'px)', duration: 0.2,
                      ease: 'power1.in' }, at);
          fundoAtual = f;
        }
        if (cap) {
          var escura = sobreFundo(e) && fundoAtual === 'claro';
          tl.set(cap, { '--cap-color': escura ? cfg.capEscura : cfg.capColor }, at + dur * 0.5);
        }
      }

      // CABEÇA VAZANDO: a camada recortada aparece quando a moldura já assentou
      // no card (a transição leva 0,3s) e sai antes de ela começar a andar —
      // parada no lugar enquanto a moldura se move, a cabeça ficaria solta.
      root.querySelectorAll('.exp-vaza').forEach(function (vz) {
        var a = parseFloat(vz.getAttribute('data-t0'));
        var b = parseFloat(vz.getAttribute('data-t1'));
        var entra = a < 0.05 ? 0 : a + 0.25;
        tl.fromTo(vz, { opacity: 0 }, { opacity: 1, duration: a < 0.05 ? 0.001 : 0.12, ease: 'none' }, entra);
        tl.to(vz, { opacity: 0, duration: 0.06, ease: 'none' }, Math.max(entra + 0.1, b - 0.12));
      });

      // os elementos de cada cena
      root.querySelectorAll('.exp-cena').forEach(function (cena) {
        var t0 = parseFloat(cena.getAttribute('data-t0'));
        var t1 = parseFloat(cena.getAttribute('data-t1'));
        tl.fromTo(cena, { opacity: 0 }, { opacity: 1, duration: 0.12, ease: 'none' }, t0 + 0.02);
        var cab = cena.querySelectorAll('.exp-tag:not(.exp-lado .exp-tag), .exp-titulo');
        if (cab.length) {
          tl.fromTo(cab, { y: 24, opacity: 0 }, { y: 0, opacity: 1, duration: 0.25,
                    ease: 'power3.out', stagger: 0.06 }, t0 + 0.05);
        }
        cena.querySelectorAll('.exp-item[data-at]').forEach(function (it) {
          tl.fromTo(it, { x: 144, opacity: 0 }, { x: 0, opacity: 1, duration: 0.15,
                    ease: 'power3.out' }, parseFloat(it.getAttribute('data-at')));
        });
        var txt = cena.classList.contains('claro') ? '#101010' : '#FFFFFF';
        cena.querySelectorAll('.exp-ck[data-at]').forEach(function (ck) {
          var at = parseFloat(ck.getAttribute('data-at'));
          var bola = ck.querySelector('.exp-bola'), sv = bola.querySelector('svg');
          var rot = ck.querySelector('.exp-rotulo');
          tl.to(bola, { backgroundColor: cfg.accent, borderColor: cfg.accent, duration: 0.12 }, at);
          tl.fromTo(sv, { opacity: 0, scale: 0.4 }, { opacity: 1, scale: 1, duration: 0.18,
                    ease: 'power3.out' }, at);
          tl.to(rot, { color: txt, duration: 0.12 }, at);
        });
        cena.querySelectorAll('.exp-lado[data-at], .exp-img[data-at]').forEach(function (el) {
          tl.fromTo(el, { y: 40, opacity: 0 }, { y: 0, opacity: 1, duration: 0.25,
                    ease: 'power3.out' }, parseFloat(el.getAttribute('data-at')));
        });
        cena.querySelectorAll('.exp-numero[data-at]').forEach(function (el) {
          tl.fromTo(el, { scale: 0.8, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.3,
                    ease: 'power3.out' }, parseFloat(el.getAttribute('data-at')));
        });
        tl.to(cena, { opacity: 0, duration: 0.07, ease: 'none' }, Math.max(t0, t1 - 0.1));
      });
    }
  };
})();

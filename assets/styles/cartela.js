/* CARTELA — o movimento das headlines de slots. Par de `cartela.css`.
 * Script clássico de propósito (nada de `import`), como o resto de assets/styles.
 *
 * VINTE LAYOUTS, DOIS MOMENTOS: a cartela ENTRA no começo do gancho e SAI no
 * fim dele. O que muda entre os layouts é o tipo de entrada e de saída, e isso
 * é dado — `variants.headlines.<id>.motion`, com os números junto.
 *
 * POR QUE TWEEN E NÃO @keyframes: o renderer salta para um quadro qualquer sem
 * tempo de parede passar. Animação de CSS não tem onde estar nesse salto — e
 * pior, ela VENCE o estilo inline, então nem dá para corrigir por fora. Só o
 * cursor do terminal pisca por CSS, e ele é o único movimento desta folha que
 * não carrega significado: pego aceso ou apagado, é um cursor piscando.
 *
 * A SAÍDA DAS CARTELAS DE TELA CHEIA É A ENTREGA DO VÍDEO. `cortina` sobe a
 * chapa, `corte` a apaga num quadro, `desfoca` dissolve o borrão, `abre`
 * afasta a moldura. Não é enfeite de saída: é a transição do gancho para a
 * primeira fala, e é ela que o espectador lê como "começou".
 */
(function (root) {
  'use strict';

  var EASE = 'cubic-bezier(.2,.8,.2,1)';

  function num(v, d) { var n = parseFloat(v); return isFinite(n) ? n : d; }

  function lerJSON(el, attr) {
    try { return JSON.parse(el.getAttribute(attr) || '{}'); }
    catch (e) { return {}; }
  }

  function pecas(box) {
    return {
      raiz: box,
      bloco: box.querySelector('.ct-bloco'),
      fundo: box.querySelector('.ct-fundo'),
      vinheta: box.querySelector('.ct-vinheta'),
      blur: box.querySelector('.ct-blur'),
      faixa: box.querySelector('.ct-faixa'),
      aspa: box.querySelector('.ct-aspa'),
      num: box.querySelector('.ct-num'),
      linhas: box.querySelector('.ct-linhas'),
      reguas: Array.prototype.slice.call(box.querySelectorAll('.ct-regua')),
      itens: Array.prototype.slice.call(box.querySelectorAll('.ct-anim')),
      /* o que se move como UM corpo na cartela de banda: a peça (faixa,
         cartão, painel, balão, adesivo) quando existe, senão o bloco */
      corpo: box.querySelector('.ct-peca') || box.querySelector('.ct-bloco'),
    };
  }

  /* ------------------------------------------------------------- ENTRADAS */

  function entrar(tl, p, m, t0, escala) {
    var tipo = m.tipo || 'fade';
    var dur = m.dur != null ? m.dur : 0.4;
    var ez = m.ease || EASE;
    var alvo = p.corpo;

    if (tipo === 'desliza') {
      tl.fromTo(alvo, { xPercent: m.de === 'dir' ? 120 : -120 },
                { xPercent: 0, duration: dur, ease: ez }, t0);
      return;
    }
    if (tipo === 'carimbo') {
      tl.fromTo(alvo, { opacity: 0, scale: m.de || 1.08 },
                { opacity: 1, scale: 1, duration: dur, ease: ez }, t0);
      return;
    }
    if (tipo === 'cola') {
      // quica ao colar: −16° → +2° → −3°, que é o gesto de uma mão, não de uma
      // interpolação — por isso são dois trechos e não um
      tl.fromTo(alvo, { opacity: 0, rotation: -16, scale: 0.5 },
                { opacity: 1, rotation: 2, scale: 1.06, duration: dur * 0.62, ease: ez }, t0);
      tl.to(alvo, { rotation: -3, scale: 1, duration: dur * 0.38, ease: EASE }, t0 + dur * 0.62);
      return;
    }
    if (tipo === 'flash') {
      tl.fromTo(alvo, { opacity: 0, scaleY: 0.4 },
                { opacity: 1, scaleY: 1, duration: dur * 0.5, ease: ez }, t0);
      // dois quadros de estouro de brilho: o susto do alerta
      tl.fromTo(alvo, { filter: 'brightness(3)' },
                { filter: 'brightness(1)', duration: 0.09, ease: 'none' }, t0 + dur * 0.5);
      return;
    }
    if (tipo === 'pisca') {
      // tubo velho acendendo: passos, nunca rampa
      tl.fromTo(alvo, { opacity: 0 },
                { opacity: 1, duration: 0.05, ease: 'steps(1)', repeat: 5, yoyo: true }, t0);
      tl.set(alvo, { opacity: 1 }, t0 + 0.3);
      tl.fromTo(alvo, { '--ct-halo': 0 }, { '--ct-halo': 1, duration: dur * 0.5, ease: ez }, t0 + 0.3);
      return;
    }
    if (tipo === 'risca') {
      tl.fromTo(p.reguas, { scaleX: 0 }, { scaleX: 1, duration: dur, ease: ez }, t0);
      tl.fromTo(p.linhas, { opacity: 0 }, { opacity: 1, duration: dur * 0.7, ease: ez }, t0 + dur * 0.3);
      return;
    }
    if (tipo === 'extrude') {
      tl.fromTo(alvo, { opacity: 0, y: 20 * escala }, { opacity: 1, y: 0, duration: dur * 0.5, ease: ez }, t0);
      // a extrusão CRESCE: os oito degraus saem de um número só (--ct-ext),
      // composto em CSS — sombra é string e string não interpola
      tl.fromTo(p.raiz, { '--ct-ext': 0 }, { '--ct-ext': 1, duration: dur, ease: ez }, t0 + dur * 0.3);
      return;
    }
    if (tipo === 'estoura') {
      var alvo1 = p.num || alvo;
      tl.fromTo(alvo1, { opacity: 0, scale: m.origem ? 0.4 : 0.4, transformOrigin: m.origem || '50% 50%' },
                { opacity: 1, scale: 1, duration: dur, ease: ez }, t0);
      if (p.num && p.linhas) {
        // a frase entra DEPOIS do algarismo: o número é a promessa, a frase é
        // a explicação — invertido, a explicação chega sem o que explicar
        tl.fromTo(p.linhas, { opacity: 0, x: 46 * escala },
                  { opacity: 1, x: 0, duration: dur * 0.7, ease: EASE }, t0 + (m.atraso || 0.2));
      }
      return;
    }
    // `sobe` e `fade`: com `escalona`, cada pedaço do bloco entra na sua vez
    var alvos = (m.escalona && p.itens.length) ? p.itens : [alvo];
    var de = tipo === 'sobe' ? { opacity: 0, y: 50 * escala } : { opacity: 0 };
    var para = { opacity: 1, y: 0, duration: dur, ease: ez };
    if (m.escalona) para.stagger = m.escalona;
    tl.fromTo(alvos, de, para, t0);
  }

  /* ---------------------------------------------------------------- SAÍDAS */

  function sair(tl, p, m, tf, escala) {
    var tipo = m.tipo || 'fade';
    var dur = m.dur != null ? m.dur : 0.3;
    var ez = m.ease || EASE;
    var t0 = Math.max(0, tf - dur);

    if (tipo === 'corte') {
      // um quadro, não um fade: o silêncio visual antes da fala só funciona se
      // o corte for CORTE
      tl.to(p.raiz, { opacity: 0, duration: dur, ease: 'none' }, t0);
      return;
    }
    if (tipo === 'cortina') {
      tl.to(p.raiz, { clipPath: m.dir === 'baixo' ? 'inset(100% 0 0 0)' : 'inset(0 0 100% 0)',
                      duration: dur, ease: ez }, t0);
      return;
    }
    if (tipo === 'sobeFora') {
      tl.to([p.fundo, p.bloco].filter(Boolean), { yPercent: -100, duration: dur, ease: ez }, t0);
      return;
    }
    if (tipo === 'desfoca') {
      tl.to(p.raiz, { '--ct-blur': 0, '--ct-brilho': 1, duration: dur, ease: ez }, t0);
      tl.to(p.bloco, { opacity: 0, duration: dur * 0.6, ease: ez }, t0);
      return;
    }
    if (tipo === 'abre' && p.vinheta) {
      tl.to(p.raiz, { '--ct-b-top': 0, '--ct-b-dir': 0, '--ct-b-bot': 0, '--ct-b-esq': 0,
                      '--ct-b-raio': 0, duration: dur, ease: ez }, t0);
      tl.to(p.bloco, { opacity: 0, duration: dur * 0.5, ease: ez }, t0);
      return;
    }
    if (tipo === 'desliza') {
      tl.to(p.corpo, { xPercent: m.para === 'esq' ? -120 : 120, duration: dur, ease: ez }, t0);
      return;
    }
    tl.to(p.raiz, { opacity: 0, duration: dur, ease: ez }, t0);
  }

  /* ----------------------------------------------------------------- RENDER */

  function buildTimeline(rootEl, gsap, tl) {
    var box = rootEl.querySelector('.ave-cartela');
    if (!box) return tl;
    var mo = lerJSON(box, 'data-motion');
    var escala = num(getComputedStyle(box).getPropertyValue('--hl-scale'), 1);
    var p = pecas(box);
    var s0 = num(box.getAttribute('data-start'), 0);
    var dur = num(box.getAttribute('data-duration'), 4);

    entrar(tl, p, mo.entra || {}, s0, escala);
    sair(tl, p, mo.sai || {}, s0 + dur, escala);
    return tl;
  }

  /* ----------------------------------------------------------------- PRÉVIA */

  /* A prévia do editor mostra a cartela ASSENTADA — entrada terminada, saída
     ainda não começada. Esta prévia responde "como fica", e o quadro do meio
     de uma entrada de 500ms não é como fica; o movimento se vê no cartão, que
     roda em laço. */
  function assentar(box) {
    var p = pecas(box);
    if (p.raiz) {
      p.raiz.style.setProperty('--ct-halo', 1);
      p.raiz.style.setProperty('--ct-ext', 1);
    }
    p.reguas.forEach(function (r) { r.style.transform = 'scaleX(1)'; });
    if (box.classList.contains('ct-adesivo') && p.corpo) p.corpo.style.transform = 'rotate(-3deg)';
  }

  /* ------------------------------------------------------------- MARCAÇÃO */

  /* De onde sai cada pedaço do texto digitado — espelho de `cartela_slots()`
     no compositor. Existe aqui para a prévia montar a MESMA marcação, que é a
     única forma de ela não mentir sobre o layout. */
  function fatiar(texto, h) {
    var slots = h.slots || {};
    var partes = String(texto || '').split('/').map(function (x) { return x.trim(); })
      .filter(function (x) { return x; });
    if (!partes.length) partes = [''];
    var olho = null, numero = null, assin = null, meta = [];

    if (slots.olho === 'primeira' && partes.length > 1) olho = partes.shift();
    if (slots.assinatura === 'traco') {
      for (var i = 0; i < partes.length; i++) {
        var c = partes[i].charAt(0);
        if ((c === '\u2014' || c === '\u2013' || c === '-') && partes.length > 1) {
          assin = partes.splice(i, 1)[0].replace(/^[\u2014\u2013-\s]+/, '');
          break;
        }
      }
    }
    if (slots.meta === 'chave:valor') {
      var restam = [];
      partes.forEach(function (x) {
        if (x.indexOf(':') > -1 && partes.length > 1) {
          var k = x.split(':')[0], v = x.slice(x.indexOf(':') + 1);
          meta.push([k.trim(), v.trim()]);
        } else restam.push(x);
      });
      partes = restam.length ? restam : [''];
    }
    if (slots.num === 'numero' && partes.length) {
      var m = partes[0].match(/^\s*(\d+[\d\u00ba\u00aa\u00b0%]*)\b[\s:.\u2014-]*(.*)$/);
      if (m) {
        numero = m[1];
        var resto = (m[2] || '').trim();
        partes = (resto ? [resto] : []).concat(partes.slice(1));
        if (!partes.length) partes = [''];
      }
    }
    return { olho: olho, num: numero, assinatura: assin, meta: meta,
             titulo: partes.filter(function (x) { return x; }).join(' / ') };
  }

  var PAPEIS = { accent: 'ct-acc', sobre: 'ct-escuro', papelEscuro: 'ct-escuro',
                 papel: 'ct-claro', serif: 'ct-serif' };

  /* A marcação da cartela — espelho de `cartela_markup()`. Recebe as linhas já
     quebradas e o corpo já medido: quebrar e medir é do compositor (e da cópia
     que a prévia já tinha para as headlines antigas), não deste arquivo. */
  function montar(host, h, id, dados) {
    var pecas = h.pecas || [];
    var pintura = (h.paint || {}).lines;
    var fr = h.fontRole || [];
    var box = document.createElement('div');
    box.className = 'ave-cartela ct-' + id + (h.cheia ? ' cheia' : '');

    var linhas = document.createElement('div');
    linhas.className = 'ct-linhas';
    dados.linhas.forEach(function (l, i) {
      var d = document.createElement('div');
      d.className = 'hl-line ct-anim';
      if (Object.prototype.toString.call(pintura) === '[object Array]') {
        var pp = PAPEIS[pintura[Math.min(i, pintura.length - 1)]];
        if (pp) d.classList.add(pp);
      } else if (PAPEIS[pintura]) d.classList.add(PAPEIS[pintura]);
      if (fr.length && fr[Math.min(i, fr.length - 1)] === 'serif') d.classList.add('ct-serif');
      d.style.setProperty('--hl-k', l.k);
      d.style.fontWeight = l.peso;
      d.dataset.text = l.txt;
      d.textContent = l.txt;
      if (pecas.indexOf('cursor') > -1 && i === dados.linhas.length - 1) {
        var c = document.createElement('i');
        c.className = 'ct-cursor';
        d.appendChild(c);
      }
      linhas.appendChild(d);
    });

    function slot(cls, txt) {
      var e = document.createElement('div');
      e.className = cls + ' ct-anim';
      e.textContent = txt;
      return e;
    }

    var bloco = document.createElement('div');
    bloco.className = 'ct-bloco';
    var alvo = bloco;

    function peca(cls) {
      var e = document.createElement('div');
      e.className = cls + ' ct-peca';
      bloco.appendChild(e);
      return e;
    }

    if (pecas.indexOf('fita') > -1) alvo = peca('ct-faixa');
    else if (pecas.indexOf('cartao') > -1) alvo = peca('ct-cartao');
    else if (pecas.indexOf('painel') > -1) alvo = peca('ct-painel');
    else if (pecas.indexOf('balao') > -1) alvo = peca('ct-balao');
    else if (pecas.indexOf('adesivo') > -1) alvo = peca('ct-adesivo');
    else if (pecas.indexOf('listras') > -1) alvo = peca('');
    else if (pecas.indexOf('noticia') > -1) {
      /* A NOTÍCIA tem duas superfícies, e o texto se reparte entre elas: o
         rótulo vai para a barra colorida e a manchete para a folha branca. O
         rótulo entra aqui, e não no caminho comum logo abaixo, porque ali ele
         cairia dentro da folha — junto da manchete, que é o oposto do layout. */
      var app = peca('ct-app');
      var barra = criar('div', 'ct-barra');
      barra.appendChild(criar('i', 'ct-menu'));
      barra.appendChild(slot('ct-olho', dados.olho || ''));
      barra.appendChild(criar('i', 'ct-lupa'));
      app.appendChild(barra);
      alvo = criar('div', 'ct-folha');
      app.appendChild(alvo);
    }

    if (dados.olho && pecas.indexOf('fita') < 0 && pecas.indexOf('noticia') < 0)
      alvo.appendChild(slot('ct-olho', dados.olho));
    if (dados.num) alvo.appendChild(slot('ct-num', dados.num));

    if (pecas.indexOf('painel') > -1 && pecas.indexOf('pontos') > -1) {
      var pts = document.createElement('div');
      pts.className = 'ct-pontos';
      pts.innerHTML = '<i></i><i></i><i></i>';
      alvo.insertBefore(pts, alvo.firstChild);
    }
    if (pecas.indexOf('listras') > -1) {
      var l1 = document.createElement('div'); l1.className = 'ct-listras';
      var chapa = document.createElement('div'); chapa.className = 'ct-chapa';
      var l2 = document.createElement('div'); l2.className = 'ct-listras';
      chapa.appendChild(linhas);
      alvo.appendChild(l1); alvo.appendChild(chapa); alvo.appendChild(l2);
    } else if (pecas.indexOf('reguas') > -1) {
      var r1 = document.createElement('i'); r1.className = 'ct-regua';
      var r2 = document.createElement('i'); r2.className = 'ct-regua';
      alvo.appendChild(r1); alvo.appendChild(linhas); alvo.appendChild(r2);
    } else if (pecas.indexOf('svg') < 0) {
      alvo.appendChild(linhas);
    }

    (dados.meta || []).forEach(function (kv) {
      var f = document.createElement('div');
      f.className = 'ct-fila ct-anim';
      f.innerHTML = '<span class="ct-k"></span><span class="ct-v"></span>';
      f.firstChild.textContent = kv[0];
      f.lastChild.textContent = kv[1];
      alvo.appendChild(f);
    });
    if (dados.assinatura) alvo.appendChild(slot('ct-assin', dados.assinatura));
    if (pecas.indexOf('rabicho') > -1) {
      var rb = document.createElement('i'); rb.className = 'ct-rabicho';
      alvo.appendChild(rb);
    }

    if (h.cheia && pecas.indexOf('svg') < 0 && pecas.indexOf('blur') < 0) {
      box.appendChild(criar('i', 'ct-fundo'));
    }
    if (pecas.indexOf('blur') > -1) box.appendChild(criar('i', 'ct-blur'));
    if (pecas.indexOf('vinheta') > -1) box.appendChild(criar('i', 'ct-vinheta'));
    if (pecas.indexOf('aspa') > -1) {
      var a = criar('div', 'ct-aspa'); a.textContent = '\u201c'; box.appendChild(a);
    }
    if (pecas.indexOf('svg') > -1) box.appendChild(svgRecorte(dados, h));
    box.appendChild(bloco);
    host.appendChild(box);
    return box;
  }

  function criar(tag, cls) {
    var e = document.createElement(tag);
    e.className = cls;
    return e;
  }

  /* O recorte do knockout também na prévia: sem ele o cartão mostraria uma
     chapa lisa, que é o oposto do que o layout faz. */
  function svgRecorte(dados, h) {
    var ns = 'http://www.w3.org/2000/svg';
    var svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('class', 'ct-svg');
    svg.setAttribute('viewBox', '0 0 1080 1920');
    svg.setAttribute('preserveAspectRatio', 'none');
    var lh = parseFloat(h.lh) || 1;
    var size = dados.size;
    var alt = dados.linhas.length * size * lh;
    var y0 = 960 - alt / 2 + size * 0.78;
    var tspans = dados.linhas.map(function (l, i) {
      return '<tspan x="540" y="' + (y0 + i * size * lh).toFixed(1) + '">' +
        String(l.txt).replace(/&/g, '&amp;').replace(/</g, '&lt;') + '</tspan>';
    }).join('');
    svg.innerHTML =
      '<defs><mask id="ct-ko-prev" maskUnits="userSpaceOnUse" x="0" y="0" width="1080" height="1920">' +
      '<rect width="1080" height="1920" fill="#fff"/>' +
      '<text text-anchor="middle" font-size="' + size.toFixed(1) + '" font-weight="' +
      (h.weights ? h.weights[0] : 900) + '" letter-spacing="-2" fill="#000" ' +
      'font-family="' + (dados.familia || 'Poppins') + '">' + tspans + '</text>' +
      '</mask></defs>' +
      '<rect width="1080" height="1920" style="fill:var(--hl-deep)" mask="url(#ct-ko-prev)"/>';
    return svg;
  }

  root.AVE_CARTELA = {
    fatiar: fatiar,
    montar: montar,
    pecas: pecas,
    entrar: entrar,
    sair: sair,
    assentar: assentar,
    buildTimeline: buildTimeline,
  };
})(typeof window !== 'undefined' ? window : this);

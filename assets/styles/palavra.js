/* PALAVRA — tempos e movimento dos estilos com estado por palavra.
 * Par de `palavra.css`. Script clássico de propósito (nada de `import`), como
 * o karaokê: a prévia é servida como script simples e a composição roda em
 * página estática.
 *
 * UMA DEFINIÇÃO DE ESTADO, DOIS CONSUMIDORES. `props()` diz o que cada estado
 * PINTA — e é a única fonte disso. O render chega nele por tween de GSAP
 * (`buildTimeline`), a prévia do editor escreve direto (`pintar`). Os dois
 * leem o mesmo `pal` do variants.json, então uma correção de estilo vale para
 * os dois lados no mesmo commit. Uma prévia com números próprios começa
 * idêntica e mente na primeira correção feita de um lado só.
 *
 * POR QUE TWEEN E NÃO TRANSIÇÃO DE CSS: o renderer salta para um quadro
 * qualquer sem tempo de parede passar. Transição de CSS não tem onde estar
 * nesse salto e sai congelada; tween de GSAP em tempo ABSOLUTO tem, e é o que
 * torna o seek confiável.
 *
 * MEDIDA TARDIA. As posições da tarja entram como FUNÇÃO, não como número: o
 * GSAP resolve valor-função quando o tween é renderizado pela primeira vez —
 * depois das fontes carregarem. Medindo na montagem, a largura seria a da
 * fonte de sistema e a tarja ficaria uns pixels fora da palavra a vida toda.
 */
(function (root) {
  'use strict';

  var EASE = 'cubic-bezier(.2,.8,.2,1)';

  function num(v, def) { var n = parseFloat(v); return isFinite(n) ? n : def; }

  function lerJSON(el, attr) {
    try { return JSON.parse(el.getAttribute(attr) || '{}'); }
    catch (e) { return {}; }
  }

  /* As cores do motor moram no CSS (papéis, não hexes soltos no script) e são
     lidas do contêiner: quem escolhe accent e cor do corpo é a aba Estilo, e
     ela escreve variáveis. `vazio` é o transparente do contorno — a palavra
     que ainda não foi preenchida. */
  function paleta(box) {
    var cs = getComputedStyle(box);
    var g = function (n, d) { return (cs.getPropertyValue(n) || '').trim() || d; };
    return {
      corpo: g('--cap-color', '#f5f2ee'),
      accent: g('--cap-accent', '#ff6b1a'),
      apagado: g('--pal-dim', '#6c7a88'),
      sobre: g('--pal-sobre', '#10202e'),
      chapa: g('--pal-chapa', 'rgba(13,33,55,.94)'),
      vidro: g('--pal-vidro', 'rgba(255,255,255,.12)'),
      suave: g('--pal-suave', '#ffad7a'),
      brilho: g('--pal-brilho', '#ffd9bc'),
      vazio: 'rgba(0,0,0,0)',
    };
  }

  /* O QUE UM ESTADO PINTA. Tudo que muda entre "ainda não dito", "sendo dito"
     e "já dito" passa por aqui — e nada além disto muda. */
  function props(est, cores, escala) {
    if (!est) return {};
    var p = {};
    if (est.cor) p.color = cores[est.cor] || est.cor;
    if (est.fundo) p.backgroundColor = cores[est.fundo] || est.fundo;
    if (est.opacidade != null) p.opacity = est.opacidade;
    if (est.escala != null) p.scale = est.escala;
    if (est.y != null) p.y = est.y * escala;
    if (est.rot != null) p.rotation = est.rot;
    if (est.blur != null) p.filter = est.blur ? 'blur(' + (est.blur * escala) + 'px)' : 'blur(0px)';
    if (est.glow != null) p['--pal-glow'] = est.glow;
    if (est.traco != null) p['--pal-traco-o'] = est.traco;
    return p;
  }

  /* A caixa da tarja em volta de uma palavra, no espaço da DEIXA. Medido por
     retângulo e não por offsetLeft: `offsetLeft` conta a borda do pai em uns
     navegadores e não em outros, e a tarja é justamente o que fica evidente
     quando erra por dois pixels. */
  /* MEDIR MESMO ESCONDIDO. O framework é quem mostra e esconde `.clip`, e um
     clipe fora do ar mede zero — a tarja nasceria com largura 0 e ficaria
     assim, porque o GSAP guarda o valor-função da PRIMEIRA renderização. Isso
     acontece de verdade quando o renderer salta direto para um quadro no meio
     do vídeo em vez de correr do início. Então, se a medida vier degenerada,
     as caixas escondidas do caminho são reabertas por um instante SÍNCRONO
     (nenhum quadro é pintado no meio) e o `display` inline de cada uma volta
     exatamente como estava. */
  function medindo(w, fn) {
    var r = w.getBoundingClientRect();
    if (r.width > 0) return fn();
    var pilha = [], el = w;
    while (el && el.nodeType === 1) {
      if (getComputedStyle(el).display === 'none') {
        pilha.push([el, el.style.display]);
        el.style.display = 'block';
      }
      el = el.parentElement;
    }
    var out = fn();
    for (var i = 0; i < pilha.length; i++) pilha[i][0].style.display = pilha[i][1];
    return out;
  }

  function caixa(cue, w, t, escala) {
    return medindo(w, function () { return _caixa(cue, w, t, escala); });
  }

  function _caixa(cue, w, t, escala) {
    var cr = cue.getBoundingClientRect(), wr = w.getBoundingClientRect();
    var px = (t.padX || 0) * escala, py = (t.padY || 0) * escala;
    if (t.forma === 'filete') {
      var sg = (t.sangra || 6) * escala;
      return {
        x: wr.left - cr.left - sg,
        y: wr.top - cr.top + wr.height - (t.desloca || 4) * escala,
        width: wr.width + sg * 2,
        height: (t.altura || 10) * escala,
      };
    }
    return {
      x: wr.left - cr.left - px,
      y: wr.top - cr.top - py,
      width: wr.width + px * 2,
      height: wr.height + py * 2,
    };
  }

  /* As palavras que o motor comanda. A linha ANTIGA da rolagem tem `.pal-w`
     para herdar a tipografia, mas não tem tempo de fala: entrando nesta lista
     ela era tratada como a primeira palavra da deixa e acendia inteira no
     accent, que é o oposto de ser o eco do que já passou. */
  function palavrasDe(cue) {
    return Array.prototype.slice.call(
      cue.querySelectorAll('.pal-line:not(.pal-antiga) .pal-w'));
  }

  /* AS VARIÁVEIS DO ESTILO, aplicadas pelo MOTOR e não por quem monta a
     página. O compositor emite o que é comum (corpo, cor, família, fundo da
     deixa) e o `pal` desce inteiro em `data-pal`; daí para diante quem traduz
     `pal` em variáveis de CSS é este arquivo, uma vez só. Traduzir isto também
     em Python no compositor e outra vez em JS na prévia é a divergência
     clássica: os três começam iguais e o primeiro ajuste feito de um lado só
     faz a prévia mentir. */
  function varsPal(box, cfg) {
    var s = function (n, v) { if (v != null) box.style.setProperty(n, v); };
    var t = cfg.tarja || {}, g = cfg.grifo || {}, pl = cfg.placa || {};
    var f = cfg.filete || {}, b = cfg.barra || {}, r = cfg.rola || {};
    s('--pal-raio', g.raio != null ? g.raio : t.raio);
    s('--pal-grifo-h', g.altura);
    s('--pal-grifo-o', g.opacidade);
    s('--pal-sangra', g.sangra);
    s('--pal-placa-raio', pl.raio);
    s('--pal-placa-px', pl.padX);
    s('--pal-placa-py', pl.padY);
    s('--pal-placa-blur', pl.blur);
    s('--pal-filete-w', f.largura);
    s('--pal-filete-h', f.altura);
    s('--pal-filete-vao', f.vao);
    s('--pal-barra-w', b.largura);
    s('--pal-barra-vao', b.vao);
    s('--pal-esq', cfg.esquerda);
    s('--pal-centro', cfg.centro);
    s('--pal-traco', cfg.traco);
    s('--pal-antiga', r.anterior);
  }

  /* ------------------------------------------------------------------ RENDER */

  function buildTimeline(rootEl, gsap, tl) {
    var box = rootEl.querySelector('.ave-pal');
    if (!box) return tl;
    var cfg = lerJSON(box, 'data-pal');
    var mo = lerJSON(box, 'data-motion');
    var escala = num(getComputedStyle(box).getPropertyValue('--cap-scale'), 1);
    var cores = paleta(box);
    varsPal(box, cfg);
    var DUR = mo.dur != null ? mo.dur : 0.18;
    var EZ = mo.ease || EASE;
    var TDUR = mo.tarja != null ? mo.tarja : 0.19;

    rootEl.querySelectorAll('.pal-cue').forEach(function (cue) {
      var s0 = num(cue.getAttribute('data-start'), 0);
      var fim = s0 + num(cue.getAttribute('data-duration'), 0);
      var ws = palavrasDe(cue);
      if (!ws.length) return;

      /* A deixa inteira entrando de uma vez — é o estilo sem estado por
         palavra (cinema), onde o que aparece é a frase, não a fala. */
      if (cfg.entrada && cfg.bloco) {
        tl.fromTo(cue, props(cfg.entrada, cores, escala),
                  { opacity: 1, duration: DUR, ease: EZ }, s0);
      }

      /* A rolagem entra empurrando: a linha nova sobe de uma altura de linha,
         levando a anterior para fora do recorte. */
      var rolo = cue.querySelector('.pal-rolo');
      if (rolo && cfg.rola) {
        var linha = cue.querySelector('.pal-line:last-child');
        tl.fromTo(rolo, { y: function () { return linha ? linha.offsetHeight : 0; } },
                  { y: 0, duration: mo.dur || 0.34, ease: EZ }, s0);
      }

      var tarja = cue.querySelector('.pal-tarja');
      if (tarja) tl.set(tarja, { opacity: 0 }, s0);

      ws.forEach(function (w, i) {
        var at = num(w.getAttribute('data-at'), s0);
        var dur = num(w.getAttribute('data-dur'), 0.3);
        // a palavra fica ATIVA até a próxima começar; a última segura até o
        // fim da deixa, como no karaokê — apagar a última deixaria a frase
        // terminando no escuro enquanto ela ainda está sendo dita
        var prox = i + 1 < ws.length ? num(ws[i + 1].getAttribute('data-at'), fim) : null;

        tl.set(w, props(cfg.antes, cores, escala), s0);

        if (cfg.entrada && !cfg.bloco) {
          tl.fromTo(w, props(cfg.entrada, cores, escala),
                    { opacity: 1, scale: 1, filter: 'blur(0px)', duration: DUR, ease: EZ }, at);
        }
        if (cfg.ativa) {
          var a = props(cfg.ativa, cores, escala);
          a.duration = DUR; a.ease = EZ;
          tl.to(w, a, at);
        }
        if (cfg.dita && prox != null) {
          var d = props(cfg.dita, cores, escala);
          d.duration = DUR; d.ease = EZ;
          tl.to(w, d, prox);
        }

        // MARCA-TEXTO: o traço cresce na duração MEDIDA da palavra e fica
        var grifo = w.querySelector('.pal-grifo');
        if (grifo) {
          tl.set(grifo, { scaleX: 0 }, s0);
          tl.to(grifo, { scaleX: 1, duration: Math.max(0.08, dur), ease: 'none' }, at);
        }

        // MÁQUINA: o cursor é um por palavra, e só o da ativa está aceso —
        // um cursor único MOVIDO no DOM não sobreviveria ao seek para trás
        var cur = w.querySelector('.pal-cursor');
        if (cur) {
          var ate = prox != null ? prox : fim;
          var meio = 0.45;   // meio ciclo do piscar, em segundos
          var voltas = Math.max(0, Math.ceil((ate - at) / meio) - 1);
          tl.set(cur, { opacity: 0 }, s0);
          // passos, não rampa: um cursor que faz fade não é um cursor
          tl.fromTo(cur, { opacity: 1 },
                    { opacity: 0, duration: meio, ease: 'steps(1)',
                      repeat: voltas, yoyo: true }, at);
          tl.set(cur, { opacity: 0 }, ate);
        }

        // A TARJA: salta invisível para a primeira palavra e daí em diante
        // PERCORRE. O percurso é o efeito; sem ele o estilo lê como pisca-pisca.
        if (tarja) {
          var alvo = (function (ww) {
            return function () { return caixa(cue, ww, cfg.tarja, escala); };
          })(w);
          if (i === 0) {
            tl.set(tarja, {
              x: function () { return alvo().x; }, y: function () { return alvo().y; },
              width: function () { return alvo().width; },
              height: function () { return alvo().height; },
            }, at);
            tl.to(tarja, { opacity: 1, duration: 0.12, ease: EZ }, at);
          } else {
            tl.to(tarja, {
              x: function () { return alvo().x; }, y: function () { return alvo().y; },
              width: function () { return alvo().width; },
              height: function () { return alvo().height; },
              duration: TDUR, ease: EZ,
            }, at);
          }
        }
      });
    });
    return tl;
  }

  /* ------------------------------------------------------------------ PRÉVIA */

  /* Qual palavra está sendo dita em `t` (segundos, relativo ao início da
     deixa). É a ÚLTIMA que já começou — a mesma regra do render, onde a
     palavra só sai de ativa quando a próxima entra. */
  function ativaEm(ws, t) {
    var idx = -1;
    for (var i = 0; i < ws.length; i++) {
      if (t >= num(ws[i].getAttribute('data-at'), 0)) idx = i;
    }
    return idx;
  }

  /* Escreve os estados direto, sem GSAP — a prévia do editor e os cartões de
     demonstração. A suavidade fica por conta de uma transição de CSS aplicada
     aqui: na prévia o tempo de parede existe, e é só ali que ele existe. */
  function pintar(cue, cfg, mo, t, escala, cores) {
    var ws = palavrasDe(cue);
    var idx = ativaEm(ws, t);
    var dur = (mo.dur != null ? mo.dur : 0.18) + 's';
    ws.forEach(function (w, i) {
      var est = i === idx ? cfg.ativa : (i < idx ? cfg.dita : cfg.antes);
      var p = props(est || cfg.antes, cores, escala);
      w.style.transition = 'color ' + dur + ', opacity ' + dur + ', transform ' + dur
        + ', filter ' + dur + ', background-color ' + dur;
      var tr = [];
      if (p.y != null) tr.push('translateY(' + p.y + 'px)');
      if (p.scale != null) tr.push('scale(' + p.scale + ')');
      if (p.rotation != null) tr.push('rotate(' + p.rotation + 'deg)');
      w.style.transform = tr.join(' ');
      if (p.color) w.style.color = p.color;
      if (p.backgroundColor) w.style.backgroundColor = p.backgroundColor;
      w.style.opacity = p.opacity != null ? p.opacity : 1;
      if (p.filter) w.style.filter = p.filter;
      if (p['--pal-glow'] != null) w.style.setProperty('--pal-glow', p['--pal-glow']);
      if (p['--pal-traco-o'] != null) w.style.setProperty('--pal-traco-o', p['--pal-traco-o']);

      var grifo = w.querySelector('.pal-grifo');
      if (grifo) {
        var at = num(w.getAttribute('data-at'), 0);
        var d = Math.max(0.08, num(w.getAttribute('data-dur'), 0.3));
        var k = i < idx ? 1 : (i === idx ? Math.max(0, Math.min(1, (t - at) / d)) : 0);
        grifo.style.transform = 'scaleX(' + k + ')';
      }
      var cur = w.querySelector('.pal-cursor');
      if (cur) cur.style.opacity = i === idx ? 1 : 0;
    });

    var tarja = cue.querySelector('.pal-tarja');
    if (tarja && cfg.tarja) {
      if (idx < 0) { tarja.style.opacity = 0; return; }
      var c = caixa(cue, ws[idx], cfg.tarja, escala);
      var td = (mo.tarja != null ? mo.tarja : 0.19) + 's';
      tarja.style.transition = 'transform ' + td + ', width ' + td + ', height ' + td
        + ', opacity .12s';
      tarja.style.opacity = 1;
      tarja.style.transform = 'translate(' + c.x + 'px,' + c.y + 'px)';
      tarja.style.width = c.width + 'px';
      tarja.style.height = c.height + 'px';
    }
    return idx;
  }

  /* MONTAGEM DA DEIXA — a mesma marcação que o compositor emite, para a prévia
     não desenhar um estilo que não existe. Recebe linhas já quebradas (quem
     quebra por largura medida é o compositor; a prévia usa o exemplo curto). */
  function montar(host, linhas, cfg, id) {
    var cue = document.createElement('div');
    cue.className = 'pal-cue';
    if (cfg.tarja) {
      var t = document.createElement('i');
      t.className = 'pal-tarja';
      cue.appendChild(t);
    }
    if (cfg.filete) {
      var f = document.createElement('i');
      f.className = 'pal-filete';
      cue.appendChild(f);
    }
    var alvo = cue;
    if (cfg.placa) {
      var pl = document.createElement('div');
      pl.className = 'pal-placa';
      cue.appendChild(pl);
      alvo = pl;
    }
    if (cfg.rola) {
      alvo = document.createElement('div');
      alvo.className = 'pal-rolo';
      cue.appendChild(alvo);
    }
    linhas.forEach(function (ln) {
      var linha = document.createElement('div');
      linha.className = 'pal-line';
      ln.forEach(function (p) {
        var w = document.createElement('span');
        w.className = 'pal-w' + (p.hi ? ' pal-hi' : '');
        w.setAttribute('data-at', p.at);
        w.setAttribute('data-dur', p.dur);
        w.textContent = p.texto;
        if (cfg.grifo) {
          var g = document.createElement('i');
          g.className = 'pal-grifo';
          w.appendChild(g);
        }
        if (cfg.cursor) {
          var c = document.createElement('i');
          c.className = 'pal-cursor';
          w.appendChild(c);
        }
        linha.appendChild(w);
      });
      alvo.appendChild(linha);
    });
    host.appendChild(cue);
    return cue;
  }

  root.AVE_PALAVRA = {
    props: props,
    varsPal: varsPal,
    paleta: paleta,
    caixa: caixa,
    ativaEm: ativaEm,
    pintar: pintar,
    montar: montar,
    buildTimeline: buildTimeline,
  };
})(typeof window !== 'undefined' ? window : this);

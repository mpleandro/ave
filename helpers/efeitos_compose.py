"""Os efeitos dentro da composição — chamado pelo compose_shortform.

Duas etapas, porque a legenda precisa saber ANTES de ser montada onde ela cala:

  * `preparar()` (no main do compose, antes das deixas): resolve `efeitos[]`
    (frase → tempo, regra do formato), soma os automáticos, mede o rosto e
    devolve as janelas que calam a legenda e os planos de câmera aparados;
  * `montar()` (dentro do render_html): escreve os blocos, as tags e a linha
    de JS, e empurra os sons para `events`.

Toda a geometria sai daqui em números — o JS (`efeitos.js`) só anima.
"""
from __future__ import annotations

import html as _html
import json
import re
import sys
from pathlib import Path

import efeitos as F
import explicativo as X
import area_segura

# Faixa de tracks própria (a do explicativo vai até 23). Cada efeito de
# conteúdo alterna entre duas para nunca dividir track com o vizinho colado.
TRACK_EFX = 30
TRACK_FUNDO = 34
TRACK_RECORTE = 36       # 36, 37 alternados: recortes vizinhos não se tocam
TRACK_ATRAS = 40
TRACK_FRENTE = 42

CFG = F.VARIANTS["efeitos"]


def _txt(s) -> str:
    """Escapa e transforma *ênfase* em <em> (no accent)."""
    s = _html.escape(str(s or ""))
    return re.sub(r"\*([^*]+)\*", r"<em>\1</em>", s)


# ---------------------------------------------------------------- preparar

def preparar(data: dict, duracao: float, segs: list[dict]) -> dict | None:
    """Plano dos efeitos, ou None quando não há nenhum."""
    tem = (data.get("efeitos") or F.ligados(data) or data.get("ganchoEfeito")
           or F.formato_de(data) in F.FORMATOS_RECORTE
           or (data.get("cta") or {}).get("modelo") == "revelarApp")
    if not tem:
        return None
    proj = Path(data.get("_proj", ".")).resolve()
    edit = proj.parent
    try:
        ws = X.palavras(edit)
    except SystemExit:
        ws = []
    itens, erros, avisos = F.resolver(data, ws, duracao)
    if erros:
        raise SystemExit("efeitos com erro — rode `efeitos.py validar <edit>`:\n  "
                         + "\n  ".join(erros))
    for a in avisos:
        print(f"  aviso (efeitos): {a}", file=sys.stderr)
    g = F.gancho(data)
    travas = [(a, b) for a, b, _ in F.janelas_recorte(data, itens, duracao)]
    # movimento automático NÃO entra onde a pessoa recortada precisa casar com
    # o vídeo: o zoom mexeria um e não o outro
    itens += [e for e in F.automaticos(data, ws, segs, duracao)
              if not any(a - 0.4 <= e.get("at", e.get("start", 0)) <= b + 0.4 for a, b in travas)]
    if (not itens and not g and F.formato_de(data) not in F.FORMATOS_RECORTE
            and (data.get("cta") or {}).get("modelo") != "revelarApp"):
        return None

    video = proj / data.get("_video", "preview.mp4")
    amostras = X.medir_rosto(video, proj / "rosto.json") if video.exists() else []

    # janelas que calam a legenda: efeito de conteúdo é o texto do momento
    mutes = [(e["start"], e["end"]) for e in itens
             if F.CATALOGO[e["tipo"]]["camada"] == "efeitos" and e.get("muteCaptions", True)]
    # CTA "Recuo para o app": a janela dele (alinhada ao "segue" da fala, como
    # os outros modelos) também cala a legenda — o app é o texto do momento
    rv = _janela_revelar(data, duracao, ws)
    if rv:
        mutes.append(rv)
    # gancho que é TEXTO (capa, parede de manchetes) cala a legenda na janela
    if g and g["tipo"] in ("coverStory", "headlineWall") and g.get("muteCaptions", True):
        mutes.append((g["start"], g["end"]))
    # câmera: some onde a pessoa recortada precisa casar pixel a pixel com o
    # vídeo (o zoom escalaria um e não o outro)
    return {"itens": sorted(itens, key=lambda e: e.get("start", e.get("at", 0))),
            "gancho": g, "rosto": amostras, "mutes": mutes, "travas": travas,
            "revelar": rv}


REVELAR_DUR, REVELAR_CLIQUE = 4.2, 2.6


def _janela_revelar(data: dict, duracao: float, ws: list) -> tuple[float, float] | None:
    """(início, fim) do CTA "Recuo para o app" — o clique no último "segue"."""
    c = data.get("cta") or {}
    if c.get("modelo") != "revelarApp":
        return None
    import cta as C
    if c.get("start") is not None:
        st = float(c["start"])
    elif c.get("momento") is not None:
        st = min(float(c["momento"]) - REVELAR_CLIQUE, duracao - REVELAR_DUR)
    else:
        palavras = [{"text": w["text"], "startMs": w["start"] * 1000, "endMs": w["end"] * 1000}
                    for w in ws]
        t = C.momento_clique(palavras, duracao)
        st = (t - REVELAR_CLIQUE) if t is not None else duracao - REVELAR_DUR
        st = min(st, duracao - REVELAR_DUR)
    st = max(0.0, st)
    return round(st, 3), round(min(st + REVELAR_DUR, duracao), 3)


def aparar_planos(segs: list[dict], travas: list[tuple[float, float]]) -> list[dict]:
    """Planos de câmera fora das janelas travadas. O plano que entra numa
    janela é cortado no começo dela; o que começa dentro passa a começar no
    fim dela — a câmera volta a valer assim que a pessoa recortada sai."""
    out = []
    for s in segs:
        a, b = float(s["start"]), float(s["end"])
        for t0, t1 in travas:
            if a < t1 and b > t0:
                if a < t0:
                    out.append({"start": a, "end": t0})
                a = max(a, t1)
        if b - a > 0.3:
            out.append({"start": round(a, 3), "end": round(b, 3)})
    return out


# ---------------------------------------------------------------- geometria

def _rosto_px(plano, a, b, W, H):
    cx, cy, fw = X.rosto_em(plano["rosto"], a, b)
    lado = fw * W
    return {"cx": cx * W, "cy": cy * H, "topo": cy * H - 0.7 * lado,
            "queixo": cy * H + 0.8 * lado, "lado": lado, "cxN": cx, "cyN": cy}


def _zona_conteudo(plano, a, b, W, H, alto):
    """(top, left, largura, escala) para um cartão de `alto` px.

    Fora do rosto: acima da testa se couber, senão abaixo do queixo até a área
    segura de baixo (a legenda está calada na janela). Abaixo de 1152 a coluna
    de ícones manda o cartão para a esquerda dela."""
    r = _rosto_px(plano, a, b, W, H)
    k = H / 1920
    topo_min = area_segura.topo_minimo(H)
    base_max = H - area_segura.base_minima(H)
    acima = (topo_min, r["topo"] - 30 * k)
    abaixo = (r["queixo"] + 30 * k, base_max)
    zonas = sorted([acima, abaixo], key=lambda z: z[1] - z[0], reverse=True)
    y0, y1 = zonas[0]
    if (y1 - y0) < alto * 0.62:
        # rosto ocupa a tela: o cartão senta no peito, onde fere menos
        y0, y1 = max(topo_min, r["cy"] + 0.35 * r["lado"]), base_max
    esc = min(1.0, (y1 - y0) / alto)
    altura = alto * esc
    top = y0 + max(0.0, ((y1 - y0) - altura) * (0.0 if zonas[0] is abaixo else 1.0))
    lat = area_segura.LATERAL * W / 1080 + 10
    direita = W - lat
    if top + altura > area_segura.ICONES_Y0 * k:
        direita = (area_segura.ICONES_X - area_segura.FOLGA) * W / 1080
    return top, lat, direita - lat, esc


# ---------------------------------------------------------------- blocos

def _bloco(eid, e, classes, style, corpo, track):
    return (f'  <div id="{eid}" class="efx {classes} clip" data-start="{e["start"]:.3f}" '
            f'data-duration="{e["end"] - e["start"]:.3f}" data-track-index="{track}" '
            f'style="{style}">{corpo}</div>')


def _sequencia(itens, t0, t1, passo=0.5):
    for i, it in enumerate(itens):
        if "at" not in it:
            it["at"] = round(min(t0 + 0.45 + passo * i, t1 - 0.3), 3)


def _checklist(eid, e, plano, W, H, track, events):
    c = CFG["checklist"]
    itens = [dict(i) if isinstance(i, dict) else {"texto": i} for i in e.get("itens") or []]
    _sequencia(itens, e["start"], e["end"], 0.6)
    alto = 150 + len(itens) * c["item"]
    top, left, larg, esc = _zona_conteudo(plano, e["start"], e["end"], W, H, alto)
    w = min(c["largura"], larg / esc)
    left = left + (larg - w * esc) / 2
    linhas = "".join(
        f'<div class="efx-ck-item" data-at="{it["at"]:.3f}"><div class="efx-ck-bola">'
        f'<svg viewBox="0 0 24 24"><path d="M5 12.5l4.2 4.2L19 7"/></svg></div>'
        f'<div class="efx-ck-txt">{_txt(it.get("texto"))}</div></div>' for it in itens)
    n = len(itens)
    cont = "".join(f'<span class="efx-ck-n" data-i="{i}">{i} de {n}</span>' for i in range(n + 1))
    corpo = (f'<div class="efx-card efx-ck"><div class="efx-ck-head"><span class="efx-ponto"></span>'
             f'<span class="efx-ck-tit">{_txt(e.get("titulo") or "checklist")}</span>'
             f'<span class="efx-ck-cont">{cont}</span></div>{linhas}</div>')
    style = (f"left:{left:.0f}px; top:{top:.0f}px; width:{w:.0f}px; "
             f"transform-origin:0 0; --efx-esc:{esc:.3f}")
    events.append((e["start"], "element"))
    for it in itens:
        events.append((it["at"], {"file": "click-tick.mp3", "volume": 0.22}))
    return _bloco(eid, e, "efx-checklist", style, corpo, track)


def _num(v) -> float:
    m = re.search(r"-?\d+(?:[.,]\d+)?", str(v))
    return float(m.group(0).replace(",", ".")) if m else 0.0


def _chart(eid, e, plano, W, H, track, events):
    c = CFG["chartGrow"]
    vals = [_num(v) for v in e.get("valores") or []]
    rot = list(e.get("rotulos") or [])
    rot += [""] * (len(vals) - len(rot))
    alto = c["altura"]
    top, left, larg, esc = _zona_conteudo(plano, e["start"], e["end"], W, H, alto)
    w = min(c["largura"], larg / esc)
    left = left + (larg - w * esc) / 2
    mx = max(vals) or 1.0
    dest = e.get("destaque", len(vals) - 1)
    barras = "".join(
        f'<div class="efx-ch-col{" dest" if i == dest else ""}">'
        f'<div class="efx-ch-val">{_txt(e.get("formatos", [None] * len(vals))[i] if e.get("formatos") else _fmt(v, e))}</div>'
        f'<div class="efx-ch-bar" data-h="{max(0.04, v / mx):.4f}"></div>'
        f'<div class="efx-ch-rot">{_txt(rot[i])}</div></div>'
        for i, v in enumerate(vals))
    grande = ""
    if e.get("numero"):
        grande = (f'<div class="efx-ch-big" data-alvo="{_num(e["numero"])}" '
                  f'data-fmt="{_html.escape(str(e["numero"]))}">{_txt(e["numero"])}</div>')
    corpo = (f'<div class="efx-card efx-ch"><div class="efx-ch-head"><span class="efx-ponto"></span>'
             f'<span class="efx-ch-tit">{_txt(e.get("titulo") or "")}</span></div>{grande}'
             f'<div class="efx-ch-area">{barras}</div></div>')
    style = (f"left:{left:.0f}px; top:{top:.0f}px; width:{w:.0f}px; height:{alto}px; "
             f"transform-origin:0 0; --efx-esc:{esc:.3f}")
    events.append((e["start"], "element"))
    events.append((e["start"] + 0.35, {"file": "riser-short.mp3", "volume": 0.12}))
    return _bloco(eid, e, "efx-chart", style, corpo, track)


def _fmt(v: float, e: dict) -> str:
    u = e.get("unidade", "")
    s = f"{v:.0f}" if abs(v - round(v)) < 1e-6 else f"{v:.1f}".replace(".", ",")
    return f"{e.get('prefixo', '')}{s}{u}"


def _phone(eid, e, plano, W, H, track, events):
    c = CFG["phoneMockup"]
    r = _rosto_px(plano, e["start"], e["end"], W, H)
    lado = e.get("lado") or ("esq" if r["cxN"] >= 0.5 else "dir")
    # O CELULAR NÃO TAPA O ROSTO: mora do queixo para baixo (pode encostar no
    # queixo), encolhendo até caber. Medido no primeiro render: em plano
    # fechado, centrado na altura do rosto ele cobria metade da cara.
    base_max = H - area_segura.base_minima(H)
    y0 = max(area_segura.topo_minimo(H), r["queixo"] - 0.2 * r["lado"])
    k = min(W / 1080, (base_max - y0) / c["altura"])
    k = max(k, 0.55 * W / 1080)
    w, h = c["largura"] * k, c["altura"] * k
    lat = area_segura.LATERAL * W / 1080 + 10
    left = lat if lado == "esq" else W - lat - w
    top = min(y0, base_max - h)
    if lado == "dir" and top + h > area_segura.ICONES_Y0 * H / 1920:
        left = min(left, (area_segura.ICONES_X - area_segura.FOLGA) * W / 1080 - w)
    tela = e.get("tela") or ("imagem" if e.get("src") else
                             "conversa" if e.get("mensagens") else "notificacao")
    if tela == "imagem":
        miolo = f'<img class="efx-ph-img" src="{_html.escape(e["src"])}" alt="">'
    elif tela == "conversa":
        msgs = [dict(m) if isinstance(m, dict) else {"texto": m} for m in e.get("mensagens") or []]
        _sequencia(msgs, e["start"], e["end"], 0.7)
        bolhas = "".join(
            f'<div class="efx-ph-msg {"eu" if m.get("lado", "ele") == "eu" else "ele"}" '
            f'data-at="{m["at"]:.3f}">{_txt(m.get("texto"))}</div>' for m in msgs)
        for m in msgs:
            events.append((m["at"], {"file": "pop.mp3", "volume": 0.08}))
        miolo = (f'<div class="efx-ph-topo"><div class="efx-ph-av"></div>'
                 f'<div class="efx-ph-nome">{_txt(e.get("contato") or e.get("app") or "")}</div></div>'
                 f'<div class="efx-ph-msgs">{bolhas}</div>')
    else:
        ns = [dict(m) if isinstance(m, dict) else {"texto": m} for m in
              (e.get("notificacoes") or e.get("mensagens") or [])]
        _sequencia(ns, e["start"], e["end"], 0.7)
        cards = "".join(
            f'<div class="efx-ph-not" data-at="{m["at"]:.3f}"><div class="efx-ph-ico"></div>'
            f'<div><div class="efx-ph-app">{_txt(m.get("app") or e.get("app") or "agora")}</div>'
            f'<div class="efx-ph-ntx">{_txt(m.get("texto"))}</div></div></div>' for m in ns)
        for m in ns:
            events.append((m["at"], {"file": "pop.mp3", "volume": 0.08}))
        miolo = (f'<div class="efx-ph-hora">{_txt(e.get("hora") or "9:41")}</div>'
                 f'<div class="efx-ph-nots">{cards}</div>')
    corpo = (f'<div class="efx-phone"><div class="efx-ph-ilha"></div>'
             f'<div class="efx-ph-tela {tela}">{miolo}</div></div>')
    style = (f"left:{left:.0f}px; top:{top:.0f}px; width:{w:.0f}px; height:{h:.0f}px; "
             f"--efx-k:{k:.4f}")
    e["lado"] = lado
    events.append((e["start"], "element"))
    return _bloco(eid, e, f"efx-phonebox {lado}", style, corpo, track)


def _som(events, at, kind):
    """`som` de um item: tipo do variants (`caching`, `impact`…) ou arquivo."""
    if not kind:
        return
    sfx = F.VARIANTS.get("sfx", {})
    events.append((at, kind if kind in sfx else {"file": kind, "volume": 0.3}))


def _conta(eid, e, plano, W, H, track, events):
    """CÁLCULO NA TELA: linhas da conta entrando na palavra que as cita e o
    resultado (o item `resultado: true`) maior, no accent. Fundo preto 80% e
    letra grossa — é informação, não enfeite, e precisa ler no mudo."""
    c = CFG["conta"]
    itens = [dict(i) if isinstance(i, dict) else {"texto": i} for i in e.get("itens") or []]
    _sequencia(itens, e["start"], e["end"], 0.7)
    n_res = sum(1 for it in itens if it.get("resultado"))
    alto = (110 if e.get("titulo") else 50) + (len(itens) - n_res) * c["linha"] + n_res * 160
    top, left, larg, esc = _zona_conteudo(plano, e["start"], e["end"], W, H, alto)
    w = min(c["largura"], larg / esc)
    left = left + (larg - w * esc) / 2
    linhas = "".join(
        f'<div class="efx-ct-linha{" res" if it.get("resultado") else ""}" '
        f'data-at="{it["at"]:.3f}">{_txt(it.get("texto"))}</div>' for it in itens)
    tit = (f'<div class="efx-ct-tit"><span class="efx-ponto"></span>{_txt(e["titulo"])}</div>'
           if e.get("titulo") else "")
    corpo = f'<div class="efx-ct">{tit}{linhas}</div>'
    style = (f"left:{left:.0f}px; top:{top:.0f}px; width:{w:.0f}px; "
             f"transform-origin:0 0; --efx-esc:{esc:.3f}")
    events.append((e["start"], "element"))
    for it in itens:
        # `som` presente e vazio = linha muda (o vídeo pode querer UM som só)
        _som(events, it["at"], it["som"] if "som" in it
             else ("impact" if it.get("resultado") else "callout"))
    return _bloco(eid, e, "efx-conta", style, corpo, track)


def _versus(eid, e, plano, W, H, track, events):
    """A × B: dois lados com rótulo e dado, rodapé com a conclusão. O lado
    `vence` acende no accent quando o rodapé entra."""
    c = CFG["versus"]
    alto = c["altura"]
    top, left, larg, esc = _zona_conteudo(plano, e["start"], e["end"], W, H, alto)
    w = min(c["largura"], larg / esc)
    left = left + (larg - w * esc) / 2

    def lado(k):
        d = e.get(k) or {}
        at = d.get("at", e["start"] + (0.05 if k == "a" else 0.6))
        vence = " vence" if e.get("vence") == k else ""
        return (f'<div class="efx-vs-lado{vence}" data-at="{at:.3f}">'
                f'<div class="efx-vs-rot">{_txt(d.get("rotulo") or k.upper())}</div>'
                f'<div class="efx-vs-val">{_txt(d.get("valor") or "")}</div>'
                f'<div class="efx-vs-det">{_txt(d.get("detalhe") or "")}</div></div>')
    rd = e.get("rodape") or {}
    rd = rd if isinstance(rd, dict) else {"texto": rd}
    rd_at = rd.get("at", max(e["start"] + 1.0, e["end"] - 1.2))
    corpo = (f'<div class="efx-vs">{lado("a")}<div class="efx-vs-x">vs</div>{lado("b")}</div>'
             f'<div class="efx-vs-rodape" data-at="{rd_at:.3f}">{_txt(rd.get("texto") or "")}</div>')
    style = (f"left:{left:.0f}px; top:{top:.0f}px; width:{w:.0f}px; height:{alto}px; "
             f"transform-origin:0 0; --efx-esc:{esc:.3f}")
    events.append((e["start"], "element"))
    events.append(((e.get("b") or {}).get("at", e["start"] + 0.6), "element"))
    _som(events, rd_at, rd["som"] if "som" in rd else "callout")
    return _bloco(eid, e, "efx-versus", style, corpo, track)


CONTEUDO = {"checklist": _checklist, "chartGrow": _chart, "phoneMockup": _phone,
            "conta": _conta, "versus": _versus}

# ---------------------------------------------------------------- recorte

def _recorte(proj: Path, t0: float, t1: float, fgr: bool) -> str:
    """O arquivo de recorte (relativo ao projeto) que cobre [t0, t1]."""
    man = proj.parent / "recorte" / "recorte.json"
    janelas = (json.loads(man.read_text()) if man.exists() else {}).get("janelas") or {}
    for nome, j in janelas.items():
        if bool(j.get("fundoNovo")) != fgr:
            continue
        if abs(float(j["inicio"]) - t0) < 0.02 and float(j["fim"]) >= t1 - 0.02:
            return f"recorte/{nome}"
    raise SystemExit(
        f"efeito com a pessoa recortada: falta o recorte de {t0:.2f}–{t1:.2f}s"
        f"{' (fundo novo)' if fgr else ''} — quem gera é o phase2.py "
        f"(recorte.py processar); rode a Fase 2 por ele")


def _fg_video(vid: str, src: str, t0: float, t1: float, track: int, style: str = "") -> str:
    # vídeo de topo: dentro de um elemento cronometrado ele sairia CONGELADO
    return (f'  <video id="{vid}" class="efx-fg clip" src="{src}" muted playsinline '
            f'data-start="{t0:.3f}" data-duration="{t1 - t0:.3f}" data-track-index="{track}" '
            f'style="position:absolute; left:0; top:0; width:100%; height:100%; '
            f'object-fit:cover; {style}"></video>')


# ---------------------------------------------------------------- gancho

def _linhas_gancho(data: dict) -> list[str]:
    hk = data.get("hook") or {}
    return [str(l) for l in (hk.get("lines") or []) if str(l).strip()]


def _frases_curtas(plano: dict, data: dict, n: int) -> list[str]:
    """Frases da própria fala, curtas, para preencher manchetes sem texto
    escrito — o vídeo citando a si mesmo é o que a parede de manchetes é."""
    proj = Path(data.get("_proj", ".")).resolve()
    try:
        fs = X.frases(X.palavras(proj.parent))
    except SystemExit:
        return []
    out = [f["texto"].strip() for f in fs if 3 <= len(f["texto"].split()) <= 9]
    return out[:n]


def _thumbs(data: dict, n: int, duracao: float, evitar: tuple[float, float]) -> list[str]:
    """Quadros do próprio vídeo como miniaturas da parede de vídeos."""
    import subprocess
    proj = Path(data.get("_proj", ".")).resolve()
    video = proj / data.get("_video", "preview.mp4")
    pasta = proj / "efeitos"
    pasta.mkdir(exist_ok=True)
    out = []
    for i in range(n):
        t = evitar[1] + (duracao - evitar[1] - 0.5) * (i + 0.5) / n
        f = pasta / f"thumb_{i}.jpg"
        if not f.exists() or f.stat().st_mtime < video.stat().st_mtime:
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(video),
                            "-frames:v", "1", "-vf", "scale=320:-2", "-q:v", "4", str(f)], check=True)
        out.append(f"efeitos/{f.name}")
    return out


def _cover(g, data, plano, W, H, accent, events):
    titulo = g.get("titulo") or (_linhas_gancho(data) or ["CAPA"])[0]
    titulo = str(titulo).upper()
    # Playfair 900 em caixa alta mede ~0,74 em por letra — medido no primeiro
    # render, 0,56 estourava "PÉROLA" para fora do quadro
    tam = max(110, min(300, int(0.9 * W / max(1, len(titulo)) / 0.74)))
    linhas = g.get("linhas") or _linhas_gancho(data)[1:] or _linhas_gancho(data)
    tag = g.get("tag") or "EXCLUSIVO"
    edicao = g.get("edicao") or "EDIÇÃO ESPECIAL"
    atras = (f'  <div id="efxg-mast" class="efx efx-cover-mast clip" data-start="{g["start"]:.3f}" '
             f'data-duration="{g["end"] - g["start"]:.3f}" data-track-index="{TRACK_ATRAS}" '
             f'style="--mast:{tam}px"><div class="efx-cover-ed">{_txt(edicao)}</div>'
             f'<div class="efx-cover-tit">{_txt(titulo)}</div></div>')
    cl = "".join(f'<div class="efx-cover-linha">{_txt(l)}</div>' for l in linhas[:3])
    frente = (f'  <div id="efxg-front" class="efx efx-cover-front clip" data-start="{g["start"]:.3f}" '
              f'data-duration="{g["end"] - g["start"]:.3f}" data-track-index="{TRACK_FRENTE}">'
              f'<div class="efx-cover-tag">{_txt(tag)}</div>{cl}'
              f'<div class="efx-cover-bar"><div class="efx-cover-cod"></div>'
              f'<div class="efx-cover-num">{_txt(g.get("numero") or "Nº 01")}</div></div></div>')
    events.append((g["start"] + 0.05, {"file": "camera.mp3", "volume": 0.22}))
    return atras, frente


# posições das peças na parede (x, y em fração do quadro, rotação) — fixas e
# determinísticas, nas laterais e no alto, onde a pessoa costuma não estar.
# A primeira é a MANCHETE PRINCIPAL (o texto do gancho), larga, no alto.
PAREDE = [(0.10, 0.135, -2), (0.03, 0.33, -6), (0.64, 0.31, 5), (0.05, 0.50, 4),
          (0.66, 0.49, -5), (0.36, 0.27, 3), (0.02, 0.66, -3), (0.68, 0.66, 6)]


def _headline_wall(g, data, plano, W, H, accent, events):
    principal = g.get("principal") or " ".join(_linhas_gancho(data))
    mans = list(g.get("manchetes") or []) or _frases_curtas(plano, data, 7)
    mans = ([principal] if principal else []) + mans
    mans = mans[:len(PAREDE)]
    d = g["end"] - g["start"]
    pecas = []
    for i, txt in enumerate(mans):
        x, y, rot = PAREDE[i]
        tipo = "principal" if (i == 0 and principal) else ("tweet", "jornal", "nota")[i % 3]
        # a principal bate primeiro; as outras em rajada logo depois
        at = g["start"] + (0.1 if i == 0 else 0.45 + (i - 1) * min(0.16, (d - 1.0) / max(1, len(mans))))
        if tipo == "tweet":
            corpo = (f'<div class="efx-hw-tw-top"><span class="efx-hw-av"></span><span>'
                     f'<b>{_txt(g.get("perfil") or "Comentário")}</b><i>@{_txt(g.get("arroba") or "internet")}</i>'
                     f'</span></div><div class="efx-hw-tw-txt">{_txt(txt)}</div>')
        elif tipo in ("jornal", "principal"):
            corpo = (f'<div class="efx-hw-fonte">{_txt(g.get("fonte") or "O DIÁRIO")}</div>'
                     f'<div class="efx-hw-man">{_txt(txt)}</div>')
        else:
            corpo = f'<div class="efx-hw-nota">“{_txt(txt)}”</div>'
        classe = "jornal principal" if tipo == "principal" else tipo
        peca = (f'<div class="efx-hw-peca {classe}" data-at="{at:.3f}" data-rot="{rot}" '
                f'style="left:{x * 100:.1f}%; top:{y * 100:.1f}%">{corpo}</div>')
        events.append((at, {"file": "caption-click.mp3", "volume": 0.3}))
        if tipo == "principal" and not _cabe_acima(plano, g, W, H, 330):
            # A MANCHETE PRINCIPAL É O GANCHO, e o gancho tem de ser lido. Em
            # plano fechado a cabeça cobre o alto do quadro (medido: o texto
            # sumia atrás dela) — aí ela vem para a FRENTE, colada no peito.
            r = _rosto_px(plano, g["start"], g["end"], W, H)
            top = min(r["queixo"] + 10, H - area_segura.base_minima(H) - 380)
            peca = peca.replace(f'top:{y * 100:.1f}%', f'top:{top:.0f}px')
            frente = (f'  <div id="efxg-wall-f" class="efx efx-hw clip" data-start="{g["start"]:.3f}" '
                      f'data-duration="{d:.3f}" data-track-index="{TRACK_FRENTE}">{peca}</div>')
            continue
        pecas.append(peca)
    atras = (f'  <div id="efxg-wall" class="efx efx-hw clip" data-start="{g["start"]:.3f}" '
             f'data-duration="{d:.3f}" data-track-index="{TRACK_ATRAS}">{"".join(pecas)}</div>')
    return atras, locals().get("frente", "")


def _cabe_acima(plano, g, W, H, alto) -> bool:
    """Cabe um bloco de `alto` px entre a área segura do topo e a testa?"""
    r = _rosto_px(plano, g["start"], g["end"], W, H)
    return r["topo"] - area_segura.topo_minimo(H) >= alto


def _couch_wall(g, data, plano, W, H, accent, events):
    imgs = list(g.get("imagens") or []) or _thumbs(data, 10, plano["duracao"], (g["start"], g["end"]))
    views = g.get("views") or ["1,2 mi", "380 mil", "92 mil", "2,4 mi", "640 mil",
                               "1,1 mi", "77 mil", "3,1 mi", "510 mil", "205 mil"]
    # grade 4 colunas × 3 linhas no alto; a pessoa cobre o miolo
    cel = []
    cw, ch = 0.235, 0.235 * W / H * 16 / 9
    for i, src in enumerate(imgs[:12]):
        c, r = i % 4, i // 4
        x = 0.02 + c * (cw + 0.012)
        y = 0.03 + r * (ch + 0.012)
        dist = abs(c - 1.5) + r
        cel.append(f'<div class="efx-cw-cel" data-at="{g["start"] + 0.08 + dist * 0.09:.3f}" '
                   f'style="left:{x * 100:.1f}%; top:{y * 100:.1f}%; width:{cw * 100:.1f}%; '
                   f'height:{ch * 100:.1f}%"><img src="{_html.escape(src)}" alt="">'
                   f'<span class="efx-cw-v">▶ {_txt(views[i % len(views)])}</span></div>')
    d = g["end"] - g["start"]
    atras = (f'  <div id="efxg-couch" class="efx efx-cw clip" data-start="{g["start"]:.3f}" '
             f'data-duration="{d:.3f}" data-track-index="{TRACK_ATRAS}">{"".join(cel)}</div>')
    events.append((g["start"] + 0.05, "element"))
    return atras, ""


GANCHO_ATRAS = {"coverStory": _cover, "headlineWall": _headline_wall, "couchWall": _couch_wall}




def _orbit(g, data, plano, W, H, accent, events):
    imgs = list(g.get("imagens") or []) or _thumbs(data, 6, plano["duracao"], (g["start"], g["end"]))
    imgs = imgs[:8]
    r = _rosto_px(plano, g["start"], g["end"], W, H)
    k = W / 1080
    w, h = 210 * k, 374 * k
    cartas = "".join(f'<div class="efx-orb-c" style="width:{w:.0f}px; height:{h:.0f}px">'
                     f'<img src="{_html.escape(src)}" alt=""></div>' for src in imgs)
    d = g["end"] - g["start"]
    comum = (f'data-start="{g["start"]:.3f}" data-duration="{d:.3f}"')
    atras = (f'  <div id="efxg-orb-a" class="efx efx-orb clip" {comum} '
             f'data-track-index="{TRACK_ATRAS}">{cartas}</div>')
    frente = (f'  <div id="efxg-orb-f" class="efx efx-orb clip" {comum} '
              f'data-track-index="{TRACK_FRENTE}">{cartas}</div>')
    g["_orbita"] = {"cx": round(r["cx"], 1), "cy": round(r["cy"] + 0.35 * r["lado"], 1),
                    "rx": round(0.43 * W, 1), "ry": round(0.07 * H, 1), "w": round(w), "h": round(h),
                    "voltas": float(g.get("voltas", 0.55)), "fase": 0.4}
    events.append((g["start"] + 0.05, "element"))
    return atras, frente


GANCHO_ATRAS["orbit"] = _orbit


# ---------------------------------------------------------------- mundo de interface

UI_PADRAO = [
    {"tipo": "notificacao", "texto": "Nova mensagem"},
    {"tipo": "botao", "texto": "Começar"},
    {"tipo": "toggle", "texto": "Automático"},
    {"tipo": "progresso", "texto": "Processando"},
    {"tipo": "busca", "texto": "como fazer isso"},
]


def _ui_peca(p: dict) -> str:
    t, txt = p.get("tipo", "chip"), _txt(p.get("texto"))
    if t == "notificacao":
        return (f'<div class="efx-ui-not"><span class="efx-ui-ico"></span><span><b>{_txt(p.get("app") or "agora")}</b>'
                f'<i>{txt}</i></span></div>')
    if t == "botao":
        return (f'<div class="efx-ui-bt"><span>{txt}</span></div>'
                f'<svg class="efx-ui-cursor" viewBox="0 0 24 24"><path d="M4 2l16 10-7 1.6L9.6 21z"/></svg>')
    if t == "toggle":
        return f'<div class="efx-ui-tg"><span>{txt}</span><span class="efx-ui-sw"><span class="efx-ui-kn"></span></span></div>'
    if t == "progresso":
        return (f'<div class="efx-ui-pr"><div class="efx-ui-pr-top"><span>{txt}</span>'
                f'<span class="efx-ui-pct">0%</span></div><div class="efx-ui-pr-bar"><div class="efx-ui-pr-fill"></div></div></div>')
    if t == "busca":
        alvo = _html.escape(str(p.get("texto") or ""))
        return (f'<div class="efx-ui-bu"><svg viewBox="0 0 16 16"><circle cx="7" cy="7" r="4.5"/>'
                f'<path d="M10.4 10.4L14 14"/></svg><span class="efx-ui-bu-txt" data-alvo="{alvo}"></span>'
                f'<span class="efx-ui-caret"></span></div>')
    return f'<div class="efx-ui-chip">{txt}</div>'


def _ui_world(eid, e, plano, W, H, events):
    itens = [dict(i) for i in (e.get("itens") or UI_PADRAO)][:6]
    _sequencia(itens, e["start"], e["end"], 0.42)
    r = _rosto_px(plano, e["start"], e["end"], W, H)
    k = W / 1080
    lat = area_segura.LATERAL * k + 10
    topo_min = area_segura.topo_minimo(H)
    base_max = H - area_segura.base_minima(H) - 120 * k
    # vagas: as duas primeiras no alto (ATRÁS da cabeça), as outras nas
    # laterais e no peito (NA FRENTE) — a pessoa no meio de uma interface
    vagas = [(lat, r["topo"] - 40 * k, True), (W * 0.55, r["topo"] + 10 * k, True),
             (lat - 10 * k, r["cy"] + 0.25 * r["lado"], False),
             (W * 0.52, r["cy"] + 0.55 * r["lado"], False),
             (lat + 40 * k, r["queixo"] + 90 * k, False),
             (W * 0.5, r["queixo"] + 220 * k, False)]
    atras, frente = [], []
    for i, it in enumerate(itens):
        x, y, tras = vagas[i]
        y = max(topo_min, min(base_max, y))
        peca = (f'<div class="efx-ui-p {it.get("tipo", "chip")}" data-at="{it["at"]:.3f}" '
                f'style="left:{x:.0f}px; top:{y:.0f}px">{_ui_peca(it)}</div>')
        (atras if tras and e.get("atras", True) else frente).append(peca)
        events.append((it["at"], {"file": "pop.mp3", "volume": 0.08}))
    d = e["end"] - e["start"]
    comum = f'data-start="{e["start"]:.3f}" data-duration="{d:.3f}"'
    a = (f'  <div id="{eid}-a" class="efx efx-ui clip" {comum} data-track-index="{TRACK_ATRAS + 1}">'
         f'{"".join(atras)}</div>')
    f = (f'  <div id="{eid}-f" class="efx efx-ui clip" {comum} data-track-index="{TRACK_FRENTE + 1}">'
         f'{"".join(frente)}</div>')
    return a, f


# ---------------------------------------------------------------- CTA: recuo para o app

def _revelar(data, plano, W, H, accent, events):
    t0, t1 = plano["revelar"]
    k = W / 1080
    vw, vh = 0.6 * W, 0.6 * H
    vx, vy = (W - vw) / 2, 330 * k
    proj = Path(data.get("_proj", ".")).resolve()
    c = data.get("cta") or {}
    arroba = (c.get("arroba") or "").strip()
    if not arroba:
        try:
            arroba = json.loads((Path.home() / ".avelin" / "brand.json").read_text()).get("instagram", "")
        except (OSError, json.JSONDecodeError):
            arroba = ""
    arroba = "@" + arroba.lstrip("@") if arroba else "@seuperfil"
    foto = (proj / "cta" / "perfil.png").exists()
    # O CARTÃO CRESCE ATÉ O @ CABER. Com a largura do vídeo recuado (648px)
    # um @ de 17 letras ficava embaixo do botão. Mede com a fonte do render
    # (Inter 800/30px; botão 28px) e para na área segura.
    try:
        import text_measure as TM
        tx = TM.measure(arroba, "Inter", 30, weight=800)
        bt = max(200.0, max(TM.measure(t, "Inter", 28, weight=800)
                            for t in ("Seguir", "Seguindo ✓")) + 52)
    except Exception:
        tx, bt = len(arroba) * 19.0, 220.0
    cw = min(max(vw, 44 + 76 + 40 + tx + bt + 16), W - 2 * 120 * k)
    cx = (W - cw) / 2
    av = ('<img src="cta/perfil.png" alt="">' if foto else "")
    d = t1 - t0
    clique = t0 + REVELAR_CLIQUE
    trilha = "".join(f'<span style="flex:{f}"></span>' for f in (3, 5, 2, 4, 3, 6))
    ui = (f'  <div id="efx-rv-hole" class="efx efx-rv-hole clip" data-start="{t0:.3f}" '
          f'data-duration="{d:.3f}" data-track-index="{TRACK_FRENTE + 2}"></div>\n'
          f'  <div id="efx-rv-ui" class="efx efx-rv-ui clip" data-start="{t0:.3f}" '
          f'data-duration="{d:.3f}" data-track-index="{TRACK_FRENTE + 3}" '
          f'style="--vx:{vx:.0f}px; --vy:{vy:.0f}px; --vw:{vw:.0f}px; --vh:{vh:.0f}px">'
          f'<div class="efx-rv-bar"><i></i><i></i><i></i><span>{_txt(c.get("arquivo") or "corte_final.mp4")}</span></div>'
          f'<div class="efx-rv-tl">{trilha}<b></b></div>'
          f'<div class="efx-rv-card" style="--cx:{cx:.0f}px; --cw:{cw:.0f}px"><div class="efx-rv-av">{av}</div>'
          f'<div class="efx-rv-tx"><b>{_txt(arroba)}</b><i>{_txt(c.get("chamada") or "conteúdo novo toda semana")}</i></div>'
          f'<div class="efx-rv-bt"><span class="a">Seguir</span><span class="b">Seguindo ✓</span></div></div>'
          f'<svg class="efx-rv-cursor" viewBox="0 0 24 24"><path d="M4 2l16 10-7 1.6L9.6 21z"/></svg></div>')
    events.append((t0, "hook"))
    events.append((clique, {"file": "caption-click.mp3", "volume": 0.45}))
    return ui, {"tipo": "revelarApp", "t0": t0, "t1": t1, "clique": clique,
                "rect": [round(vx), round(vy), round(vw), round(vh)], "W": W, "H": H,
                "raio": round(36 * k)}



# ---------------------------------------------------------------- formatos de recorte

RABISCOS = (
    '<svg class="efx-cd-rab" viewBox="0 0 1080 1920" preserveAspectRatio="none">'
    '<path d="M120 300c90-60 160 50 250-10s170 60 260 0 160 50 300-20" stroke="#7b8fd6" stroke-width="16" '
    'fill="none" stroke-linecap="round" opacity=".75"/>'
    '<path d="M140 360c80-40 150 40 230-6s150 40 230 0" stroke="#7b8fd6" stroke-width="12" fill="none" '
    'stroke-linecap="round" opacity=".55"/>'
    '<path d="M840 520l40 40m0-40l-40 40M900 610l26 26m0-26l-26 26" stroke="#d84a3a" stroke-width="7" '
    'stroke-linecap="round"/>'
    '<path d="M150 1240c30-30 60 30 90 0s60 30 90 0" stroke="#d84a3a" stroke-width="8" fill="none" '
    'stroke-linecap="round" opacity=".8"/>'
    '<circle cx="930" cy="1180" r="34" stroke="#7b8fd6" stroke-width="7" fill="none" opacity=".8"/>'
    '</svg>')


def _formato_recorte(data, plano, W, H, duracao, events):
    """Fundo trocado / Caderno: a pessoa recortada vira o próprio a-roll (a
    câmera continua valendo nela) e o fundo novo mora ANTES da janela."""
    fmt = F.formato_de(data)
    proj = Path(data.get("_proj", ".")).resolve()
    src = _recorte(proj, 0.0, round(duracao, 3), True)
    cfg = data.get(fmt) or {}
    antes, aroll_style, js = [], "", []
    comum = f'data-start="0" data-duration="{duracao:.3f}" data-track-index="{TRACK_FUNDO}"'
    if fmt == "fundoTrocado":
        fundo = cfg.get("fundo")
        if fundo:
            f = Path(fundo)
            if not f.is_absolute():
                f = proj / fundo
            if not f.exists():
                raise SystemExit(f"fundo trocado: não achei {fundo}")
            dest = proj / "efeitos" / f.name
            dest.parent.mkdir(exist_ok=True)
            if f.resolve() != dest.resolve():
                import shutil
                shutil.copy2(f, dest)
            rel = f"efeitos/{f.name}"
            if f.suffix.lower() in (".mp4", ".mov", ".webm"):
                antes.append(f'  <video id="efx-fundo" class="clip" src="{rel}" muted playsinline loop {comum} '
                             f'style="position:absolute; inset:0; width:100%; height:100%; object-fit:cover"></video>')
            else:
                antes.append(f'  <img id="efx-fundo" class="clip" src="{rel}" alt="" {comum} '
                             f'style="position:absolute; inset:0; width:100%; height:100%; object-fit:cover">')
        else:
            print("  aviso (fundo trocado): sem `fundoTrocado.fundo` — fundo da marca (gradiente). "
                  "Para uma imagem ou vídeo: pexels_search.py, e grave o caminho em "
                  "edit-data.json → fundoTrocado.fundo", file=sys.stderr)
            antes.append(f'  <div id="efx-fundo" class="efx efx-ft-marca clip" {comum}></div>')
    else:  # caderno
        antes.append(f'  <div id="efx-fundo" class="efx efx-cd-papel clip" {comum}>{RABISCOS}</div>')
        boil = cfg.get("boil", True)
        k = W / 1080
        antes.append(
            '  <svg width="0" height="0" style="position:absolute"><filter id="efx-papel" '
            'x="-5%" y="-5%" width="110%" height="110%" color-interpolation-filters="sRGB">'
            f'<feMorphology in="SourceAlpha" operator="dilate" radius="{9 * k:.1f}" result="d"/>'
            f'<feTurbulence id="efx-boil-n" type="fractalNoise" baseFrequency="0.035" numOctaves="2" seed="3" result="n"/>'
            f'<feDisplacementMap in="d" in2="n" scale="{(16 if boil else 0) * k:.1f}" xChannelSelector="R" '
            'yChannelSelector="G" result="dd"/>'
            '<feFlood flood-color="#ffffff"/><feComposite in2="dd" operator="in" result="borda"/>'
            '<feOffset in="dd" dx="10" dy="14" result="so"/><feFlood flood-color="#000" flood-opacity=".22"/>'
            '<feComposite in2="so" operator="in" result="sombra"/>'
            '<feMerge><feMergeNode in="sombra"/><feMergeNode in="borda"/><feMergeNode in="SourceGraphic"/></feMerge>'
            '</filter></svg>')
        aroll_style = "filter:url(#efx-papel);"
        if boil:
            # DOODLE BOIL: o contorno "ferve" — a semente do ruído troca a cada
            # 4 quadros, como desenho animado à mão. `set` em tempo absoluto.
            passo = 4 / float(data.get("fps", 30))
            n = int(duracao / passo)
            js.append({"tipo": "boil", "passo": round(passo, 4), "n": n})
    return {"antes": antes, "arollSrc": src, "arollStyle": aroll_style, "js": js}


# ---------------------------------------------------------------- montar

def montar(data: dict, plano: dict, duracao: float, accent: str, events: list) -> dict:
    W, H = int(data.get("width", 1080)), int(data.get("height", 1920))
    fps = float(data.get("fps", 30))
    blocos, cfg_js = [], []
    antes, atras, frente = [], [], []
    proj = Path(data.get("_proj", ".")).resolve()
    plano["duracao"] = duracao
    k_track = 0
    for i, e in enumerate(plano["itens"]):
        tipo = e["tipo"]
        if tipo == "uiWorld":
            eid = f"efx{i}"
            a, f = _ui_world(eid, e, plano, W, H, events)
            if e.get("atras", True):
                atras.append(a)
                atras.append(_fg_video(f"{eid}-fg", _recorte(proj, e["start"], e["end"], False),
                                       e["start"], e["end"], TRACK_RECORTE + 1 + k_track % 2))
            else:
                frente.append(a)
            frente.append(f)
            k_track += 1
            # `ref`, não `id`: os blocos são `<eid>-a` e `<eid>-f`, e um `id` sem
            # elemento faz o buildTimeline pular o efeito inteiro (medido)
            cfg_js.append({"ref": eid, "tipo": tipo, "t0": e["start"], "t1": e["end"]})
            events.append((e["start"], "element"))
        elif tipo in CONTEUDO:
            eid = f"efx{i}"
            blocos.append(CONTEUDO[tipo](eid, e, plano, W, H, TRACK_EFX + k_track % 2, events))
            k_track += 1
            cfg_js.append({"id": eid, "tipo": tipo, "t0": e["start"], "t1": e["end"],
                           **({"lado": e["lado"]} if "lado" in e else {})})
        elif tipo == "zoomPunch":
            r = _rosto_px(plano, e["start"], e["end"], W, H)
            esc = float(e.get("escala", CFG["zoomPunch"]["escala"]))
            cfg_js.append({"tipo": tipo, "t0": e["start"], "t1": e["end"], "escala": esc,
                           "ox": round(100 * r["cxN"], 2), "oy": round(100 * r["cyN"], 2)})
            events.append((e["start"], {"file": "impact.mp3", "volume": 0.1}))
        elif tipo == "zoomThrough":
            c = CFG["zoomThrough"]
            r = _rosto_px(plano, e["at"] - 0.5, e["at"] + 0.5, W, H)
            ent, sai = c["entraFrames"] / fps, c["saiFrames"] / fps
            cfg_js.append({"tipo": tipo, "at": e["at"], "entra": round(ent, 3),
                           "sai": round(min(sai, duracao - e["at"]), 3),
                           "escala": float(e.get("escala", c["escala"])), "blur": c["blur"],
                           "ox": round(100 * r["cxN"], 2), "oy": round(100 * r["cyN"], 2)})
            events.append((max(0.0, e["at"] - ent), "hook"))
    g = plano.get("gancho")
    if g:
        tipo = g["tipo"]
        fgr = F.GANCHOS[tipo].get("recorte") == "fgr"
        if tipo in GANCHO_ATRAS:
            a, f = GANCHO_ATRAS[tipo](g, data, plano, W, H, accent, events)
            atras.append(a)
            if f:
                frente.append(f)
            atras.append(_fg_video("efxg-fg", _recorte(proj, g["start"], g["end"], False),
                                   g["start"], g["end"], TRACK_RECORTE))
            cfg_js.append({"tipo": tipo, "t0": g["start"], "t1": g["end"], **(g.get("_orbita") or {})})
        elif tipo == "frameBreak":
            c = CFG["frameBreak"]
            antes.append(f'  <div id="efxg-fb-bg" class="efx efx-fb-bg clip" data-start="{g["start"]:.3f}" '
                         f'data-duration="{g["end"] - g["start"]:.3f}" data-track-index="{TRACK_FUNDO}"></div>')
            atras.append(f'  <div id="efxg-fb-borda" class="efx efx-fb-borda clip" data-start="{g["start"]:.3f}" '
                         f'data-duration="{g["end"] - g["start"]:.3f}" data-track-index="{TRACK_ATRAS}"></div>')
            atras.append(_fg_video("efxg-fg", _recorte(proj, g["start"], g["end"], fgr),
                                   g["start"], g["end"], TRACK_RECORTE, "clip-path:inset(0 0 100% 0)"))
            cfg_js.append({"tipo": tipo, "t0": g["start"], "t1": g["end"], "card": c["card"],
                           "raio": c["raio"], "dur": c["transicao"]})
            events.append((g["start"] + 0.05, "hook"))
        elif tipo == "vertigo":
            pass                      # gravado no vídeo base (anim3d_fx), nada a desenhar
    arroll = {}
    if F.formato_de(data) in F.FORMATOS_RECORTE:
        arroll = _formato_recorte(data, plano, W, H, duracao, events)
        antes += arroll["antes"]
        cfg_js += arroll["js"]
    if plano.get("revelar"):
        ui, cj = _revelar(data, plano, W, H, accent, events)
        frente.append(ui)
        cfg_js.append(cj)
    # a câmera volta a 1 onde a pessoa recortada entra — o plano aparado parou
    # em zoom, e o recorte é do quadro SEM zoom
    for a, b in plano.get("travas") or []:
        cfg_js.append({"tipo": "trava", "t0": a, "t1": b})
    blocos = atras + blocos + frente
    if not blocos and not cfg_js and not antes:
        return {}
    js = ("  AVE_EFEITOS.buildTimeline(document.getElementById('root'), gsap, tl, "
          + json.dumps({"itens": cfg_js, "entrada": CFG["entrada"], "saida": CFG["saida"],
                        "accent": accent, "chart": CFG["chartGrow"]}) + ");")
    return {"depois": "\n".join(blocos), "antes": "\n".join(antes), "js": js,
            "css": '<link rel="stylesheet" href="styles/efeitos.css">',
            "tag": '<script src="styles/efeitos.js"></script>',
            "style": f"--efx-accent:{accent};",
            "arollSrc": arroll.get("arollSrc"), "arollStyle": arroll.get("arollStyle", ""),
            "gfont": "family=Inter:wght@500;600;700;800;900&family=Playfair+Display:wght@700;900",
            "substituiHook": bool(g and F.GANCHOS[g["tipo"]].get("substituiHook"))}

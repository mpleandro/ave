"""A moldura explicativa dentro da composição — chamado pelo compose_shortform.

Recebe o `edit-data.json → explicativo` (roteiro de cenas, ver explicativo.py)
e devolve os blocos de HTML, as tags e a linha de JS. Toda a geometria e o
enquadramento do rosto saem daqui, em números, para o JS só animar.
"""
from __future__ import annotations

import html as _html
import json
import re
from pathlib import Path

import explicativo as X

FONTES = ("family=Inter:wght@700;800&family=Instrument+Serif:ital@1"
          "&family=JetBrains+Mono:wght@600")
TRACK_FUNDO, TRACK_BORDA, TRACK_CENA, TRACK_VAZA = 18, 19, 20, 21


def _manifesto_recorte(edit: Path) -> dict:
    p = edit / "recorte" / "recorte.json"
    return json.loads(p.read_text()) if p.exists() else {}


def _fg_para(janelas: dict, t0: float, t1: float) -> str | None:
    """O arquivo de recorte que cobre [t0, t1] — o primeiro quadro dele é t0."""
    for nome, j in janelas.items():
        # só o recorte de cor descontaminada serve aqui: o fundo do formato não
        # é o da gravação (ver person_matte.py --fgr)
        if not j.get("fundoNovo") and str(j.get("motor", "")).startswith("rvm"):
            continue
        if abs(float(j["inicio"]) - t0) < 0.02 and float(j["fim"]) >= t1 - 0.02:
            return nome
    return None


def _txt(s: str) -> str:
    """Escapa e transforma *ênfase* em <em> (serifada itálica no accent)."""
    s = _html.escape(str(s or ""))
    return re.sub(r"\*([^*]+)\*", r"<em>\1</em>", s)


def _altura(el: dict) -> float:
    t = el.get("tipo")
    h = 0.0
    if el.get("tag"):
        h += 80
    if el.get("titulo"):
        tam = 136 if el.get("tipo") == "titulo" else 92
        h += tam * len(str(el["titulo"]).split(" / ")) + 26
    n = len(el.get("itens") or [])
    if t == "lista":
        h += n * 110 + max(n - 1, 0) * 22
    elif t == "checklist":
        h += 68 + n * 84 + max(n - 1, 0) * 10
    elif t == "comparacao":
        h += 320
    elif t == "numero":
        h += 320
    elif t == "imagem":
        h += 560 + (70 if el.get("legenda") else 0)
    return h


def _sequencia(itens: list, t0: float, t1: float) -> None:
    """Item sem palavra achada entra em sequência — nunca todos de uma vez."""
    for i, it in enumerate(itens):
        if "at" not in it:
            it["at"] = round(min(t0 + 0.35 + 0.45 * i, t1 - 0.4), 3)


def _elemento(el: dict, t0: float, t1: float) -> str:
    t = el.get("tipo")
    partes = []
    if el.get("tag"):
        partes.append(f'<div class="exp-tag">{_txt(el["tag"])}</div>')
    if el.get("titulo"):
        linhas = "".join(f'<span class="exp-linha">{_txt(l)}</span>'
                         for l in str(el["titulo"]).split(" / "))
        partes.append(f'<div class="exp-titulo">{linhas}</div>')
    itens = [dict(i) for i in (el.get("itens") or [])]
    _sequencia(itens, t0, t1)
    if t == "lista":
        rows = []
        for n, it in enumerate(itens, 1):
            ico = (f'<div class="exp-ico" data-icone="{_html.escape(it["icone"])}"></div>'
                   if it.get("icone") else f'<div class="exp-num">{n}</div>')
            rows.append(f'<div class="exp-item" data-at="{it["at"]:.3f}">{ico}'
                        f'<div class="exp-rotulo">{_txt(it.get("texto"))}</div></div>')
        partes.append(f'<div class="exp-lista">{"".join(rows)}</div>')
    elif t == "checklist":
        rows = "".join(f'<div class="exp-ck" data-at="{it["at"]:.3f}"><div class="exp-bola"></div>'
                       f'<div class="exp-rotulo">{_txt(it.get("texto"))}</div></div>' for it in itens)
        partes.append(f'<div class="exp-check">{rows}</div>')
    elif t == "comparacao":
        lados = []
        for k, lado in (("a", el.get("esquerda") or {}), ("b", el.get("direita") or {})):
            at = float(lado.get("at", t0 + (0.3 if k == "a" else 1.2)))
            tag = f'<div class="exp-tag">{_txt(lado.get("rotulo"))}</div>' if lado.get("rotulo") else ""
            lados.append(f'<div class="exp-lado {k}" data-at="{at:.3f}">{tag}'
                         f'<div class="exp-rotulo">{_txt(lado.get("texto"))}</div></div>')
        partes.append(f'<div class="exp-comp">{"".join(lados)}</div>')
    elif t == "numero":
        at = float(el.get("at", t0 + 0.2))
        partes.append(f'<div class="exp-numero" data-at="{at:.3f}"><div class="exp-valor">'
                      f'{_txt(el.get("valor"))}</div><div class="exp-rotulo">{_txt(el.get("rotulo"))}'
                      f'</div></div>')
    elif t == "imagem":
        at = float(el.get("at", t0 + 0.2))
        partes.append(f'<div class="exp-img" data-at="{at:.3f}"><img src="{_html.escape(el["src"])}" alt=""></div>')
        if el.get("legenda"):
            partes.append(f'<div class="exp-rotulo">{_txt(el["legenda"])}</div>')
    return "".join(partes)


def montar(data: dict, duracao: float, accent: str, cap_color: str) -> dict | None:
    ex = data.get("explicativo") or {}
    if not ex.get("cenas"):
        return None
    W, H = int(data.get("width", 1080)), int(data.get("height", 1920))
    if abs(W / H - 9 / 16) > 0.02:
        raise SystemExit("moldura explicativa: por enquanto só vertical 9:16 — "
                         f"o projeto é {W}×{H}")
    proj = Path(data.get("_proj", "."))
    edit = proj.parent
    prefs = X.prefs()
    cenas, erros, avisos = X.resolver(data, X.palavras(edit), duracao, prefs)
    for a in avisos:
        print(f"  aviso (explicativo): {a}")
    if erros:
        raise SystemExit("moldura explicativa: roteiro com erro — rode "
                         "`explicativo.py validar <edit>`:\n  " + "\n  ".join(erros))
    video = proj / data.get("_video", "preview.mp4")
    Ws, Hs, _ = X.sonda(video)
    amostras = X.medir_rosto(video, proj / "rosto.json")
    base = ex.get("base") or prefs.get("base", "card")
    fundo_base = ex.get("fundo", "escuro")

    blocos = X.blocos(cenas, duracao, base)
    vaza = bool(ex.get("cabecaVaza")) and base == "card"

    estados = []
    for b in blocos:
        lay = b["layout"]
        geo = "pip" if lay == "oculto" else lay
        pos = b.get("pos") or ("centro" if lay == "oculto" else "esq")
        rect = X.moldura(geo, pos, W, H)
        if lay == "oculto":          # some encolhendo para o centro do topo
            rect = {**rect, "x": rect["x"] + rect["w"] * 0.2, "y": rect["y"] + rect["h"] * 0.2,
                    "w": rect["w"] * 0.6, "h": rect["h"] * 0.6, "r": rect["r"] * 0.6}
        rosto = X.rosto_em(amostras, b["start"], b["end"])
        vid = X.video_em(geo, rect, rosto, Ws, Hs, W, H, vaza=vaza)
        estados.append({"t0": round(b["start"], 3), "t1": round(b["end"], 3), "layout": lay,
                        "base": bool(b.get("base")), "oculto": lay == "oculto",
                        "fundo": b.get("fundo") or fundo_base, "rect": rect, "video": vid})

    k = W / X.REF_W
    cenas_html = []
    for i, b in enumerate(blocos):
        el = b.get("elemento")
        if not el:
            continue
        lay = b["layout"]
        y0, y1 = X.ZONA.get(lay, X.ZONA["pip"])
        alt = _altura(el)
        esc = min(1.0, (y1 - y0) / alt) if alt else 1.0
        centro = el.get("tipo") in ("titulo", "numero", "imagem") or lay == "oculto" and el.get("tipo") != "lista"
        classes = (f'exp-cena clip {estados[i]["fundo"]}' + (" exp-centro" if centro else "")
                   + (" so-titulo" if el.get("tipo") == "titulo" else ""))
        cenas_html.append(
            f'    <div class="{classes}" data-t0="{b["start"]:.3f}" data-t1="{b["end"]:.3f}" '
            f'data-start="{b["start"]:.3f}" data-duration="{b["end"] - b["start"]:.3f}" '
            f'data-track-index="{TRACK_CENA}" '
            f'style="top:{y0}px; height:{y1 - y0}px; transform:scale({esc:.3f})">'
            f'{_elemento(el, b["start"], b["end"])}</div>')

    # CABEÇA VAZANDO A BORDA DO CARD: a pessoa recortada (alfa do recorte
    # aprovado), na MESMA posição do vídeo do card, mostrada só ACIMA da borda.
    # Dentro do card quem aparece é o próprio vídeo; o recorte só completa o
    # que a moldura cortaria.
    vaza_html = []
    if vaza:
        janelas = (_manifesto_recorte(edit).get("janelas") or {})
        for e in estados:
            if e["layout"] != "card":
                continue
            arq = _fg_para(janelas, e["t0"], e["t1"])
            if not arq:
                raise SystemExit(
                    f"cabeça vazando: falta o recorte de {e['t0']:.2f}–{e['t1']:.2f}s — "
                    f"o phase2.py gera (recorte.py processar); rode a Fase 2 por ele")
            r, v = e["rect"], e["video"]
            d = e["t1"] - e["t0"]
            vaza_html.append(
                # o invólucro NÃO tem tempo: vídeo com data-start dentro de outro
                # elemento com data-start sai CONGELADO (o `check` barra —
                # `video_nested_in_timed_element`). Quem o mostra e esconde é o
                # fade do JS; quem toca o vídeo é o motor, pelo tempo do <video>.
                f'  <div class="exp-vaza" data-t0="{e["t0"]:.3f}" data-t1="{e["t1"]:.3f}" '
                f'style="position:absolute; left:0; top:0; width:{W}px; height:{r["y"]:.1f}px; '
                f'overflow:hidden; opacity:0">'
                f'<video id="vaza{len(vaza_html)}" class="clip" src="recorte/{arq}" muted playsinline '
                f'data-start="{e["t0"]:.3f}" data-duration="{d:.3f}" '
                f'data-track-index="{TRACK_VAZA + 1 + len(vaza_html) % 2}" '
                f'style="position:absolute; left:{v["vx"]}px; top:{v["vy"]}px; '
                f'width:{v["vw"]}px; height:{v["vh"]}px; object-fit:fill"></video></div>')

    cfg = {"k": k, "accent": accent, "capColor": cap_color, "capEscura": "#101010",
           "estados": estados}
    antes = (f'  <div id="exp-fundo" class="clip" data-start="0" data-duration="{duracao:.3f}" '
             f'data-track-index="{TRACK_FUNDO}"></div>\n'
             f'  <div id="exp-borda" class="clip" data-start="0" data-duration="{duracao:.3f}" '
             f'data-track-index="{TRACK_BORDA}"></div>')
    depois = ("\n".join(vaza_html) + "\n" if vaza_html else "") + (f'  <div id="exp-el" style="--exp-k:{k:.4f}; --exp-accent:{accent};">\n'
              + "\n".join(cenas_html) + "\n  </div>")
    fora = [(e["t0"], e["t1"]) for e in estados if not e["base"]]
    return {"antes": antes, "depois": depois, "fora": fora, "gfont": FONTES,
            # com o recorte por cima, a câmera não pode mexer o vídeo do card:
            # o zoom escalaria o vídeo e deixaria a cabeça recortada no lugar
            "camOff": vaza,
            "css": '<link rel="stylesheet" href="styles/explicativo.css">',
            "tag": '<script src="styles/explicativo.js"></script>',
            "js": "  AVE_EXPLICATIVO.buildTimeline(document.getElementById('root'), gsap, tl, "
                  + json.dumps(cfg) + ");"}

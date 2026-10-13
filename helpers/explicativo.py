#!/usr/bin/env python3
"""MOLDURA EXPLICATIVA — o apresentador muda de formato quando a fala pede.

Sem nada a explicar, o sujeito fica GRANDE (card ou tela cheia). Quando a fala
cita uma lista, um exemplo, uma comparação, um número, ele vai para o formato
que serve àquele trecho — PIP circular, tela dividida, quadrado, ou some e a
explicação ocupa a tela — e o espaço livre recebe o elemento. Terminou a ideia,
volta a ficar grande. A animação segue a LEITURA do vídeo, nunca o relógio:
cena começa na palavra que a pede, item de lista entra na palavra que o cita.

Referência medida: Video-43569 (transições 0,3s sem overshoot, wipe circular de
fundo nascendo no destino da moldura, itens deslizando da direita em 0,15s).

O roteiro de cenas é escrito pelo AGENTE, lendo a fala — gatilho é sentido, não
string. Este helper dá os instrumentos em volta dessa leitura:

    explicativo.py prefs [--formatos pip,dividida,quadrado,oculto] [--intensidade equilibrado] [--base card]
    explicativo.py fala <edit>        # a fala em frases, com tempo e gatilhos prováveis
    explicativo.py validar <edit> [--gravar]
                                      # resolve palavra→tempo, checa regras, imprime o roteiro
    explicativo.py rosto <edit>       # mede o rosto (cache em hyperframes/rosto.json)

O roteiro mora em `hyperframes/edit-data.json → explicativo`:

    {"base": "card",                       # o "sujeito grande": card | cheia
     "cenas": [
       {"layout": "pip", "pos": "esq", "fundo": "escuro",
        "de": "três pontos", "ate": "consiga manter",     # frases da fala (ou start/end)
        "elemento": {"tipo": "lista", "tag": "3 PONTOS",
                     "titulo": "o que *funciona*",
                     "itens": [{"texto": "Planejamento", "icone": "calendario",
                                "palavra": "planejamento"}, ...]}}]}

Layouts: cheia · card · pip (pos esq|dir|centro) · dividida · quadrado · oculto
(a explicação toma a tela, a voz continua). Elementos: lista, checklist,
titulo, comparacao, numero, imagem. Os trechos sem cena ficam na `base`.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

PREFS = Path.home() / ".avelin" / "explicativo.json"
LAYOUTS = ("cheia", "card", "pip", "dividida", "quadrado", "oculto")
ELEMENTOS = ("lista", "checklist", "titulo", "comparacao", "numero", "imagem")
ICONES = ("calendario", "prato", "check", "lista", "grafico", "dinheiro", "relogio",
          "pessoa", "grupo", "casa", "celular", "ideia", "alvo", "raio", "coracao",
          "chat", "livro", "estrela", "seta", "cadeado", "play", "engrenagem", "foguete",
          "lupa", "mundo", "camera")

# INTENSIDADE: quanto do vídeo pode ficar fora da base, e quanto cada formato
# precisa durar. Medido na referência: trocas a cada 1,5–3s cansam — o piso
# aqui é 2,5s mesmo no intenso.
INTENSIDADE = {
    "sobrio": {"minimo": 4.0, "fora": 0.35},
    "equilibrado": {"minimo": 3.0, "fora": 0.55},
    "intenso": {"minimo": 2.5, "fora": 0.75},
}
MAX_ITENS = 4
VAO_MINIMO = 1.0         # vão de base menor que isto entre duas cenas é absorvido
MAX_ROTULO = 26          # caracteres de um item de lista (cabe a 44px+ em 1080)

# Geometria em px de referência 1080×1920 (escala por W/1080). Medida na
# referência e ajustada às zonas da legenda (75% da altura).
REF_W, REF_H = 1080, 1920
GEOM = {
    "cheia": {"x": 0, "y": 0, "w": 1080, "h": 1920, "r": 0},
    "card": {"x": 135, "y": 883, "w": 810, "h": 1097, "r": 75},   # sangra embaixo
    "dividida": {"x": 48, "y": 1000, "w": 984, "h": 980, "r": 56},
    "quadrado": {"x": 200, "y": 980, "w": 680, "h": 680, "r": 48},
}
# PIP Ø 34% da largura. Posição pela ÁREA SEGURA (area_segura.py): topo ≥ 260,
# borda dentro de x 120…960 — a referência o punha a 42px da borda, em cima da
# margem da interface.
PIP_D, PIP_CY = 367, 444
PIP_CX = {"esq": 314, "dir": 766, "centro": 540}
# Onde o elemento mora em cada layout (y0..y1) — fora da moldura e acima da
# faixa da legenda.
# ÁREA SEGURA (area_segura.py): nada acima de 260 nem na faixa da coluna de
# ícones (y ≥ 1152); laterais de 120 (ver `.exp-cena` no CSS).
ZONA = {"card": (260, 850), "pip": (680, 1142), "dividida": (260, 940),
        "quadrado": (260, 930), "oculto": (260, 1142)}
# Enquadramento do rosto DENTRO da moldura: largura do rosto / largura da
# moldura, e a altura do centro do rosto como fração da moldura.
# O centro do rosto fica ACIMA da faixa da legenda (75% da altura = 1440):
# medido no primeiro render, a dividida com o rosto a 40% da moldura punha o
# "não" da legenda na boca do apresentador.
ROSTO = {"card": (0.30, 0.30), "pip": (0.50, 0.46), "dividida": (0.26, 0.25),
         "quadrado": (0.36, 0.30)}


# ---------------------------------------------------------------- preferências

def prefs() -> dict:
    base = {"formatos": ["pip", "dividida", "quadrado", "oculto"],
            "intensidade": "equilibrado", "base": "card", "perguntado": False}
    try:
        return {**base, **json.loads(PREFS.read_text())}
    except (OSError, json.JSONDecodeError):
        return base


def cmd_prefs(args) -> None:
    p = prefs()
    if args.formatos:
        fs = [f.strip() for f in args.formatos.split(",") if f.strip()]
        ruins = [f for f in fs if f not in LAYOUTS or f in ("cheia", "card")]
        if ruins:
            sys.exit(f"formato desconhecido: {ruins} (use pip, dividida, quadrado, oculto)")
        p["formatos"], p["perguntado"] = fs, True
    if args.intensidade:
        p["intensidade"], p["perguntado"] = args.intensidade, True
    if args.base:
        p["base"] = args.base
    if args.formatos or args.intensidade or args.base:
        PREFS.parent.mkdir(parents=True, exist_ok=True)
        PREFS.write_text(json.dumps(p, ensure_ascii=False, indent=2))
    print(json.dumps(p, ensure_ascii=False))


# ---------------------------------------------------------------- a fala

def _norm(s: str, virgula: bool = False) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9 ,]" if virgula else r"[^a-z0-9 ]", "", s)


def palavras(edit: Path) -> list[dict]:
    for nome in ("cut_mapped.json", "cut.json"):
        p = edit / "transcripts" / nome
        if p.exists():
            ws = [w for w in json.loads(p.read_text()).get("words", [])
                  if w.get("type", "word") == "word"]
            if ws:
                # aplica as correções que o usuário fez no painel — o MESMO texto
                # que vira legenda (Hard Rule 14)
                try:
                    sys.path.insert(0, str(Path(__file__).parent))
                    from cut_transcript import fix_for  # noqa: F401
                except Exception:
                    pass
                return ws
    sys.exit(f"sem transcrito do corte em {edit}/transcripts — rode a Fase 2 uma vez "
             "ou cut_transcript.py")


GATILHOS = [
    ("lista", r"\b(dois|duas|tres|quatro|cinco|seis) (pontos|passos|coisas|motivos|formas|"
              r"camadas|pilares|erros|dicas|movimentos|etapas|regras|perguntas|tipos)\b"),
    ("lista", r"\b(primeiro|segundo|terceiro|depois|por fim|alem disso)\b"),
    # enumeração por vírgula: "foco, direcionamento e especificidade"
    ("lista", r"\w+ \w+, \w+(?: \w+)?(?:, \w+(?: \w+)?)* e \w+"),
    ("exemplo", r"\b(por exemplo|imagina|imagine|tipo assim|olha so|veja|como esse)\b"),
    ("comparacao", r"\b(antes|depois|enquanto|versus|ao inves|em vez|diferenca|mas)\b"),
    ("numero", r"\b\d+[\d.,]*\b|\b(mil|milhao|milhoes|por cento|metade|dobro)\b"),
    ("pergunta", r"\?"),
    ("cta", r"\b(toque|clique|link|comenta|segue|siga|aula gratuita|saiba mais)\b"),
]


def frases(ws: list[dict]) -> list[dict]:
    out, cur = [], []
    for i, w in enumerate(ws):
        cur.append(w)
        prox = ws[i + 1] if i + 1 < len(ws) else None
        fim = re.search(r"[.!?…]$", w["text"]) or (prox and prox["start"] - w["end"] > 0.45)
        if fim or prox is None:
            out.append({"start": cur[0]["start"], "end": cur[-1]["end"],
                        "texto": " ".join(x["text"] for x in cur)})
            cur = []
    return out


def cmd_fala(args) -> None:
    edit = args.edit.resolve()
    for f in frases(palavras(edit)):
        # vírgula preservada: é ela que denuncia a enumeração
        t = _norm(f["texto"], virgula=True) + \
            ("?" if f["texto"].rstrip().endswith("?") else "")
        tags = sorted({g for g, rx in GATILHOS if re.search(rx, t)})
        marca = f"  ← {', '.join(tags)}" if tags else ""
        print(f"[{f['start']:6.2f}–{f['end']:6.2f}] {f['texto']}{marca}")


# ---------------------------------------------------------------- o rosto

def sonda(video: Path) -> tuple[int, int, float]:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height:format=duration", "-of", "json", str(video)],
                       capture_output=True, text=True, check=True)
    j = json.loads(r.stdout)
    return j["streams"][0]["width"], j["streams"][0]["height"], float(j["format"]["duration"])


def medir_rosto(video: Path, cache: Path) -> list[list[float]]:
    """[t, cx, cy, largura] normalizados, 2 amostras por segundo (Haar frontal)."""
    if cache.exists() and cache.stat().st_mtime > video.stat().st_mtime:
        return json.loads(cache.read_text())["amostras"]
    import cv2
    import numpy as np
    W, H, dur = sonda(video)
    dw = 360
    dh = int(round(H * dw / W / 2) * 2)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vf",
                          f"fps=2,scale={dw}:{dh}", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                         capture_output=True, check=True).stdout
    fr = np.frombuffer(raw, np.uint8).reshape(-1, dh, dw)
    casc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    out = []
    for i, g in enumerate(fr):
        fs = casc.detectMultiScale(g, 1.1, 5, minSize=(dw // 12, dw // 12))
        if len(fs):
            x, y, w, h = max(fs, key=lambda f: f[2] * f[3])
            out.append([round(i / 2, 2), round((x + w / 2) / dw, 4),
                        round((y + h / 2) / dh, 4), round(w / dw, 4)])
    cache.write_text(json.dumps({"amostras": out}))
    return out


def rosto_em(amostras: list, a: float, b: float) -> tuple[float, float, float]:
    sel = [s for s in amostras if a <= s[0] <= b] or amostras
    if not sel:
        return 0.5, 0.33, 0.28
    med = lambda k: float(sorted(s[k] for s in sel)[len(sel) // 2])
    return med(1), med(2), med(3)


# ---------------------------------------------------------------- geometria

def moldura(layout: str, pos: str, W: int, H: int) -> dict:
    k = W / REF_W
    if layout == "pip" or layout == "oculto":
        cx = PIP_CX.get(pos or "esq", PIP_CX["esq"])
        g = {"x": cx - PIP_D / 2, "y": PIP_CY - PIP_D / 2, "w": PIP_D, "h": PIP_D, "r": PIP_D / 2}
    else:
        g = dict(GEOM[layout])
    return {c: round(v * k, 1) for c, v in g.items()}


# CABEÇA VAZANDO: o rosto sobe no card até o alto da cabeça passar da borda.
# O quadrado do Haar vai de sobrancelha a queixo; o topo da cabeça fica ~0,35
# rosto acima dele.
# Medido no primeiro render: a 0,55 só ~35px de cabelo passavam da borda; a
# 0,42 sai a testa de cabelo, com os olhos ainda dentro do card.
VAZA_LARGURA, VAZA_CENTRO = 0.32, 0.42


def blocos(cenas: list[dict], duracao: float, base: str) -> list[dict]:
    """O vídeo inteiro em trechos: as cenas e, nos vãos, a base."""
    out, cur = [], 0.0
    for c in cenas:
        if "start" not in c or "end" not in c:
            continue
        if c["start"] - cur > 0.05:
            out.append({"start": cur, "end": c["start"], "layout": base, "base": True})
        out.append({**c, "base": c["layout"] == base})
        cur = c["end"]
    if duracao - cur > 0.05:
        out.append({"start": cur, "end": duracao, "layout": base, "base": True})
    return out


def video_em(layout: str, rect: dict, rosto: tuple, Ws: int, Hs: int, W: int, H: int,
             vaza: bool = False) -> dict:
    """Onde o vídeo fica para o rosto cair no lugar certo DA MOLDURA."""
    fx, fy, fw = rosto
    cover = max(W / Ws, H / Hs)
    if layout == "cheia":
        vw, vh = Ws * cover, Hs * cover
        return {"vx": round((W - vw) / 2, 1), "vy": round((H - vh) / 2, 1),
                "vw": round(vw, 1), "vh": round(vh, 1)}
    kf, ky = ROSTO.get(layout, ROSTO["pip"])
    vazando = vaza and layout == "card"
    if vazando:
        kf = VAZA_LARGURA
    # o que o vídeo PRECISA cobrir é a parte VISÍVEL da moldura: o card sangra
    # além do quadro (1980 > 1920), e exigir cobertura até 1980 empurrava o
    # rosto para baixo — medido, a cabeça "vazando" passava 30px da borda.
    base = min(rect["y"] + rect["h"], H)
    s = kf * rect["w"] / max(fw * Ws, 1)
    s = max(s, rect["w"] / Ws, (base - rect["y"]) / Hs)
    if vazando:
        # subir o rosto até a borda sem descobrir o pé do card: escala mínima
        # em que alvo_y + (1-fy)·vh alcança a base
        s = max(s, (base - rect["y"]) / (VAZA_CENTRO * fw * Ws + (1 - fy) * Hs))
    vw, vh = Ws * s, Hs * s
    vx = rect["x"] + rect["w"] / 2 - fx * vw
    alvo_y = (rect["y"] + VAZA_CENTRO * fw * Ws * s) if vazando else rect["y"] + ky * rect["h"]
    vy = alvo_y - fy * vh
    vx = min(rect["x"], max(rect["x"] + rect["w"] - vw, vx))
    vy = min(rect["y"], max(base - vh, vy))
    return {"vx": round(vx, 1), "vy": round(vy, 1), "vw": round(vw, 1), "vh": round(vh, 1)}


# ---------------------------------------------------------------- o roteiro

def _achar(ws: list[dict], frase: str, desde: float, ate: float = 1e9,
           fim: bool = False) -> float | None:
    """Tempo de uma frase da fala (começo, ou fim com `fim=True`)."""
    alvo = _norm(frase).split()
    if not alvo:
        return None
    nt = [_norm(w["text"]) for w in ws]
    for i in range(len(ws)):
        if ws[i]["start"] < desde - 0.05 or ws[i]["start"] > ate:
            continue
        if nt[i:i + len(alvo)] == alvo:
            return ws[i + len(alvo) - 1]["end"] if fim else ws[i]["start"]
    return None


def resolver(data: dict, ws: list[dict], duracao: float, p: dict) -> tuple[list[dict], list[str], list[str]]:
    """Cenas com tempos resolvidos + (erros, avisos). Não grava nada."""
    ex = data.get("explicativo") or {}
    cenas = [dict(c) for c in (ex.get("cenas") or [])]
    erros, avisos = [], []
    intens = INTENSIDADE.get(p.get("intensidade", "equilibrado"), INTENSIDADE["equilibrado"])
    cursor = 0.0
    for n, c in enumerate(cenas, 1):
        nome = f"cena {n}"
        lay = c.get("layout")
        if lay not in LAYOUTS:
            erros.append(f"{nome}: layout '{lay}' não existe ({', '.join(LAYOUTS)})")
            continue
        if lay not in ("cheia", "card") and lay not in p.get("formatos", []):
            avisos.append(f"{nome}: '{lay}' não está entre os formatos que o usuário liberou "
                          f"({', '.join(p.get('formatos', []))})")
        # a FRASE vence o tempo gravado: o tempo é derivado dela, e um roteiro
        # editado com o tempo antigo ainda no dado entraria no lugar errado
        if "de" in c:
            t = _achar(ws, c["de"], cursor)
            if t is None:
                erros.append(f"{nome}: não achei \"{c['de']}\" na fala depois de {cursor:.2f}s")
                continue
            c["start"] = t
        if "ate" in c:
            t = _achar(ws, c["ate"], c.get("start", cursor), fim=True)
            if t is None:
                erros.append(f"{nome}: não achei \"{c['ate']}\" na fala")
                continue
            c["end"] = t
        if "start" not in c or "end" not in c:
            erros.append(f"{nome}: precisa de start/end ou de/ate")
            continue
        c["start"], c["end"] = round(float(c["start"]), 3), round(min(float(c["end"]), duracao), 3)
        if c["start"] < cursor - 1e-3:
            erros.append(f"{nome}: começa ({c['start']:.2f}s) antes da cena anterior acabar ({cursor:.2f}s)")
        if c["end"] - c["start"] < intens["minimo"] - 1e-3:
            avisos.append(f"{nome}: {c['end'] - c['start']:.1f}s no ar — abaixo do mínimo de "
                          f"{intens['minimo']:.1f}s para '{p.get('intensidade')}'; troca rápida cansa")
        el = c.get("elemento")
        if el:
            if lay == "cheia":
                erros.append(f"{nome}: tela cheia não tem espaço livre para elemento")
            if el.get("tipo") not in ELEMENTOS:
                erros.append(f"{nome}: elemento '{el.get('tipo')}' não existe ({', '.join(ELEMENTOS)})")
            itens = el.get("itens") or []
            if len(itens) > MAX_ITENS:
                erros.append(f"{nome}: {len(itens)} itens — no máximo {MAX_ITENS} por tela")
            for it in itens + [x for x in (el.get("esquerda"), el.get("direita")) if x]:
                txt = it.get("texto") or it.get("rotulo") or ""
                if len(txt) > MAX_ROTULO:
                    avisos.append(f"{nome}: \"{txt}\" tem {len(txt)} caracteres — rótulo de "
                                  f"item quer 2–3 palavras (legível no celular)")
                if it.get("icone") and it["icone"] not in ICONES:
                    avisos.append(f"{nome}: ícone '{it['icone']}' não existe — sai sem ícone")
                if "palavra" in it:
                    t = _achar(ws, it["palavra"], c["start"] - 0.3, c["end"])
                    if t is None:
                        avisos.append(f"{nome}: não achei \"{it['palavra']}\" dentro da cena — "
                                      f"o item entra em sequência")
                    else:
                        it["at"] = round(t + 0.05, 3)
            if el.get("palavra"):
                t = _achar(ws, el["palavra"], c["start"] - 0.3, c["end"])
                if t is not None:
                    el["at"] = round(t + 0.05, 3)
            if el.get("tipo") == "imagem" and not el.get("src"):
                erros.append(f"{nome}: imagem sem `src`")
        cursor = c["end"]
    # VÃO CURTO ENTRE CENAS: voltar ao sujeito grande por 0,4s e sair de novo
    # é um piscar, não uma volta. A cena anterior segura até a próxima.
    ok = [c for c in cenas if "start" in c and "end" in c]
    for a, b in zip(ok, ok[1:]):
        if 0 < b["start"] - a["end"] < VAO_MINIMO:
            a["end"] = b["start"]
    if duracao > 0 and cenas:
        fora = sum(c["end"] - c["start"] for c in cenas
                   if "start" in c and "end" in c and c.get("layout") != ex.get("base", p.get("base")))
        if fora / duracao > intens["fora"] + 1e-3:
            avisos.append(f"{fora / duracao:.0%} do vídeo fora do sujeito grande — acima de "
                          f"{intens['fora']:.0%} para '{p.get('intensidade')}'")
    return cenas, erros, avisos


def tabela(cenas: list[dict], base: str, duracao: float, ws: list[dict]) -> str:
    def fala(a, b):
        t = " ".join(w["text"] for w in ws if a - 0.01 <= w["start"] < b)
        return (t[:42] + "…") if len(t) > 43 else t
    def mmss(t):
        return f"{int(t // 60)}:{t % 60:04.1f}"
    linhas, cur = [], 0.0
    blocos = []
    for c in cenas:
        if "start" not in c:
            continue
        if c["start"] - cur > 0.05:
            blocos.append({"start": cur, "end": c["start"], "layout": base})
        blocos.append(c)
        cur = c["end"]
    if duracao - cur > 0.05:
        blocos.append({"start": cur, "end": duracao, "layout": base})
    for b in blocos:
        lay = b["layout"] + (f" {b['pos']}" if b.get("pos") else "")
        el = b.get("elemento") or {}
        oq = el.get("tipo", "—")
        if el.get("itens"):
            oq += ": " + " · ".join(i.get("texto", "") for i in el["itens"])
        elif el.get("titulo") or el.get("valor"):
            oq += ": " + str(el.get("titulo") or el.get("valor"))
        linhas.append(f"{mmss(b['start'])}–{mmss(b['end'])}  {lay:<14} \"{fala(b['start'], b['end'])}\"  {oq}")
    return "\n".join(linhas)


def cmd_validar(args) -> None:
    edit = args.edit.resolve()
    dp = edit / "hyperframes" / "edit-data.json"
    data = json.loads(dp.read_text()) if dp.exists() else {}
    ws = palavras(edit)
    video = edit / "preview.mp4"
    duracao = sonda(video)[2] if video.exists() else (ws[-1]["end"] if ws else 0)
    p = prefs()
    cenas, erros, avisos = resolver(data, ws, duracao, p)
    base = (data.get("explicativo") or {}).get("base") or p.get("base", "card")
    print(tabela(cenas, base, duracao, ws))
    for a in avisos:
        print(f"  aviso: {a}")
    for e in erros:
        print(f"  ERRO: {e}")
    if args.gravar and not erros:
        data.setdefault("explicativo", {})["cenas"] = cenas
        data["explicativo"].setdefault("base", base)
        dp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        print("  roteiro gravado com os tempos resolvidos")
    sys.exit(1 if erros else 0)


def cmd_rosto(args) -> None:
    edit = args.edit.resolve()
    a = medir_rosto(edit / "preview.mp4", edit / "hyperframes" / "rosto.json")
    print(f"{len(a)} amostras com rosto; mediana {rosto_em(a, 0, 1e9)}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("prefs")
    s.add_argument("--formatos")
    s.add_argument("--intensidade", choices=list(INTENSIDADE))
    s.add_argument("--base", choices=["card", "cheia"])
    for nome in ("fala", "validar", "rosto"):
        x = sub.add_parser(nome)
        x.add_argument("edit", type=Path)
        if nome == "validar":
            x.add_argument("--gravar", action="store_true")
    args = ap.parse_args()
    {"prefs": cmd_prefs, "fala": cmd_fala, "validar": cmd_validar, "rosto": cmd_rosto}[args.cmd](args)


if __name__ == "__main__":
    main()

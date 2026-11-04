"""As headlines com DESENHO do popup "Com legenda" — as que o editor tem e o
libass consegue: caixinha de pergunta, notícia, balão, filete, fita, gigante,
contorno duplo, sombra longa, tarjas, grifo, moldura e aspas.

As de texto puro (faixa, etiqueta, contorno, texto, serifada) e a capa sólida
ficam em legenda.py, que é de onde vieram; aqui mora o que precisa de forma
desenhada (`\\p`) ou de uma linha por evento.

Tudo na referência 1080×1920 do .ass. Os números vêm dos layouts do editor
(assets/styles/variants.json → headlines/caixinha, cartela.css, caixinha.css),
com o corpo de CSS convertido para o do libass (×1,37, `css_k`). As formas têm
LARGURA FIXA (caixinha 1040, notícia de borda a borda, balão 860…), então só a
altura depende do texto — e altura é número de linhas × entrelinha, sem medir.
Onde o corpo se ajusta à largura (gigante, contorno duplo, sombra longa,
tarjas, grifo), a largura é medida com a fonte instalada (`largura`).

Cada layout devolve eventos como dicts — camada, estilo, posição, tags e corpo
— e `montar` aplica a ENTRADA (aparece, desliza, pop) igual em todos eles, para
a forma e o texto de um mesmo layout entrarem juntos.
"""
from __future__ import annotations

import functools
import subprocess

W, H = 1080, 1920
ESCURO = "#14181C"      # a tinta de "papel" do editor (notícia, balão)
PAPEL = "#F5F2EE"
CX_FAIXA = "#20252B"    # caixinha: a faixa escura do adesivo do Instagram
CX_TEXTO = "#111111"

ESTILOS = [
    # neutros: fonte, corpo e cor vêm por override em cada evento
    "Style: Hl,Arial,60,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1",
    "Style: HlBox,Arial,60,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,3,0,0,7,0,0,0,1",
]


def _c(hex_rgb: str) -> str:
    h = hex_rgb.lstrip("#")
    return f"&H{h[4:6]}{h[2:4]}{h[0:2]}&".upper()


@functools.lru_cache(maxsize=32)
def _fonte(nome: str):
    """(ImageFont a 1000px, unidades por em, altura de linha do libass em unidades)."""
    from fontTools.ttLib import TTFont  # noqa: PLC0415
    from PIL import ImageFont  # noqa: PLC0415
    caminho = subprocess.run(["fc-match", "-f", "%{file}", nome], capture_output=True,
                             text=True).stdout.strip()
    tt = TTFont(caminho, fontNumber=0, lazy=True)
    upem = tt["head"].unitsPerEm
    os2 = tt["OS/2"]
    return ImageFont.truetype(caminho, 1000), upem, os2.usWinAscent + os2.usWinDescent


def largura(texto: str, fonte: str, tamanho: float) -> float:
    """Largura de `texto` em px do .ass com corpo `tamanho`. O libass escala a
    fonte pela altura do OS/2 (winAscent + winDescent), não pelo em — por isso
    o corpo 104 da Poppins não é 104px de em."""
    try:
        f, upem, alt = _fonte(fonte)
        return f.getlength(texto) * upem / 1000 * tamanho / alt
    except Exception:   # sem fonte/fontTools: estimativa larga, o erro seguro
        return 0.58 * tamanho * len(texto)


def caber(linhas: list[str], fonte: str, teto: float, largura_max: float) -> float:
    """O maior corpo até `teto` em que a linha mais larga cabe em `largura_max`."""
    w100 = max(largura(ln, fonte, 100) for ln in linhas) or 1
    return round(min(teto, largura_max * 100 / w100))


# ------------------------------------------------------------------ formas

def encher(texto_: str, fonte: str, tam: float, largura_max: float) -> list[str]:
    """Quebra gulosa pela largura medida: cada linha leva o que couber."""
    linhas, cur = [], ""
    for w in texto_.split():
        teste = f"{cur} {w}".strip()
        if cur and largura(teste, fonte, tam) > largura_max:
            linhas.append(cur)
            cur = w
        else:
            cur = teste
    return linhas + [cur] if cur else linhas


def ret(x: float, y: float, w: float, h: float, r: float = 0, cima: bool = True,
        baixo: bool = True, inverso: bool = False) -> str:
    """Retângulo de cantos arredondados como desenho do .ass (horário; `inverso`
    anti-horário, para furar uma forma por dentro)."""
    k = 0.5523 * r
    rc, rb = (r if cima else 0), (r if baixo else 0)
    kc, kb = (k if cima else 0), (k if baixo else 0)
    p = [(x + rc, y), (x + w - rc, y), ("b", x + w - rc + kc, y, x + w, y + rc - kc, x + w, y + rc),
         (x + w, y + h - rb), ("b", x + w, y + h - rb + kb, x + w - rb + kb, y + h, x + w - rb, y + h),
         (x + rb, y + h), ("b", x + rb - kb, y + h, x, y + h - rb + kb, x, y + h - rb),
         (x, y + rc), ("b", x, y + rc - kc, x + rc - kc, y, x + rc, y)]
    if inverso:
        # o mesmo contorno percorrido ao contrário
        pts = [(x + rc, y), (x, y + rc), (x, y + h - rb), (x + rb, y + h), (x + w - rb, y + h),
               (x + w, y + h - rb), (x + w, y + rc), (x + w - rc, y)]
        return "m " + " l ".join(f"{a:.0f} {b:.0f}" for a, b in pts) + " "
    out = f"m {p[0][0]:.0f} {p[0][1]:.0f} "
    for seg in p[1:]:
        if seg[0] == "b":
            out += "b " + " ".join(f"{v:.0f}" for v in seg[1:]) + " "
        else:
            out += f"l {seg[0]:.0f} {seg[1]:.0f} "
    return out


def circulo(cx: float, cy: float, r: float, inverso: bool = False) -> str:
    k = 0.5523 * r
    if inverso:
        return (f"m {cx:.0f} {cy - r:.0f} b {cx - k:.0f} {cy - r:.0f} {cx - r:.0f} {cy - k:.0f} {cx - r:.0f} {cy:.0f} "
                f"b {cx - r:.0f} {cy + k:.0f} {cx - k:.0f} {cy + r:.0f} {cx:.0f} {cy + r:.0f} "
                f"b {cx + k:.0f} {cy + r:.0f} {cx + r:.0f} {cy + k:.0f} {cx + r:.0f} {cy:.0f} "
                f"b {cx + r:.0f} {cy - k:.0f} {cx + k:.0f} {cy - r:.0f} {cx:.0f} {cy - r:.0f} ")
    return (f"m {cx:.0f} {cy - r:.0f} b {cx + k:.0f} {cy - r:.0f} {cx + r:.0f} {cy - k:.0f} {cx + r:.0f} {cy:.0f} "
            f"b {cx + r:.0f} {cy + k:.0f} {cx + k:.0f} {cy + r:.0f} {cx:.0f} {cy + r:.0f} "
            f"b {cx - k:.0f} {cy + r:.0f} {cx - r:.0f} {cy + k:.0f} {cx - r:.0f} {cy:.0f} "
            f"b {cx - r:.0f} {cy - k:.0f} {cx - k:.0f} {cy - r:.0f} {cx:.0f} {cy - r:.0f} ")


def forma(camada: int, desenho: str, cor: str, extra: str = "") -> dict:
    """Uma forma desenhada em coordenadas de quadro. O libass alinha desenho
    pela caixa dele, então a âncora é o CENTRO dessa caixa (\\an5): é em torno
    dela que o Pop escala — com a âncora no canto 0,0 a forma voaria."""
    # E o desenho vai para coordenadas LOCAIS (mínimo em 0,0): o libass mede a
    # caixa a partir da origem do desenho, não do menor ponto — desenhado em
    # coordenada de quadro, a forma caía o próprio `topo` abaixo do texto.
    toks = desenho.split()
    nums = [float(v) for v in toks if v not in ("m", "l", "b")]
    x0, y0 = min(nums[0::2]), min(nums[1::2])
    local, k = [], 0
    for v in toks:
        if v in ("m", "l", "b"):
            local.append(v)
        else:
            local.append(f"{float(v) - (x0 if k % 2 == 0 else y0):.0f}")
            k += 1
    w, h = max(nums[0::2]) - x0, max(nums[1::2]) - y0
    return {"camada": camada, "estilo": "Hl", "an": 5, "x": x0 + w / 2, "y": y0 + h / 2,
            "tags": f"\\c{_c(cor)}\\bord0\\shad0{extra}\\p1", "corpo": " ".join(local) + "{\\p0}"}


def texto(camada: int, corpo: str, x: float, y: float, an: int, fonte: str, tam: float,
          cor: str, extra: str = "", estilo: str = "Hl") -> dict:
    return {"camada": camada, "estilo": estilo, "an": an, "x": x, "y": y,
            "tags": f"\\fn{fonte}\\fs{tam:.0f}\\b0\\c{_c(cor)}\\bord0\\shad0{extra}", "corpo": corpo}


def realce(ln: str, forca, cor_forca: str, base: str = "#FFFFFF") -> str:
    """Palavra de força na `cor_forca`; depois dela, volta à `base` do texto
    (um \\c vazio voltaria ao branco do estilo, e não à tinta do layout)."""
    return " ".join(f"{{\\c{_c(cor_forca)}}}{w}{{\\c{_c(base)}}}" if forca(w) else w for w in ln.split())


def _sombra(desenho: str, camada: int) -> dict:
    return forma(camada, desenho, "#000000", "\\alpha&H90&\\blur14")


# ------------------------------------------------------------------ layouts

def layout(nome: str, linhas_de, texto_: str, topo: float, P: str, F: str, forca) -> list[dict]:
    """Os eventos do layout `nome`. `linhas_de(texto, max_chars)` quebra o
    texto (as linhas digitadas no popup mandam); P e F são as cores principal
    e de fundo."""
    up = texto_.upper()
    if nome == "gigante":
        ps = texto_.split()
        heroi, resto = ps[-1], " ".join(ps[:-1])
        A = caber([heroi], "Poppins Black", 300, 920)
        a = max(54, round(A * 0.38))
        ev = []
        y = topo
        if resto:
            for ln in linhas_de(resto, 26):
                ev.append(texto(5, ln, 540, y, 8, "Poppins Bold", a, "#FFFFFF", "\\shad3\\4a&H70&"))
                y += a * 1.0
        ev.append(texto(5, heroi, 540, y - A * 0.08, 8, "Poppins Black", A, P, "\\shad4\\4a&H70&"))
        return ev
    if nome == "contorno_duplo":
        ls = linhas_de(up, max(6, len(up) // 2 + 1))[:2]
        A = caber(ls, "Anton", 190, 930)
        ev = [texto(5, ls[0], 540, topo, 8, "Anton", A, "#FFFFFF", "\\1a&HFF&\\3c&HFFFFFF&\\bord5")]
        if len(ls) > 1:
            ev.append(texto(5, ls[1], 540, topo + A * 0.92, 8, "Anton", A, P, "\\shad3\\4a&H70&"))
        return ev
    if nome == "sombra_longa":
        ls = linhas_de(up, 12)
        A = caber(ls, "Poppins Black", 150, 900)
        ev = []
        for i, ln in enumerate(ls):
            y = topo + i * A * 1.02
            for k in range(10, 0, -1):    # a extrusão: cópias duras na principal
                ev.append(texto(5, ln, 540 + k * 3.5, y + k * 3.5, 8, "Poppins Black", A, P))
            ev.append(texto(6, ln, 540, y, 8, "Poppins Black", A, "#FFFFFF"))
        return ev
    if nome == "tarjas":
        ls = linhas_de(texto_, max(8, len(texto_) // 3 + 2))
        meio = len(ls) // 2 if len(ls) > 2 else len(ls) - 1
        A = caber([ls[meio]], "Poppins Black", 150, 860)
        a = caber([x for i, x in enumerate(ls) if i != meio] or ls, "Poppins ExtraBold", round(A * 0.6), 860)
        ev, y, pad = [], topo, 16
        for i, ln in enumerate(ls):
            heroi = i == meio
            tam = A if heroi else a
            ev.append(texto(5, ln, 540, y + pad, 8, "Poppins Black" if heroi else "Poppins ExtraBold", tam,
                            "#FFFFFF" if heroi else F, f"\\3c{_c(P if heroi else '#FFFFFF')}\\bord{pad}",
                            "HlBox"))
            y += tam + 2 * pad + 10
        return ev
    if nome == "grifo":
        ls = linhas_de(up, 14)
        A = caber(ls, "Poppins Black", 130, 880)
        ev, pad = [], 12
        for i, ln in enumerate(ls):
            # cada PALAVRA com a sua tarja: o espaço entre elas fica sem caixa
            corpo = "{\\3a&HFF&} {\\3a&H00&}".join(ln.split())
            ev.append(texto(5, corpo, 540, topo + pad + i * (A + 2 * pad + 10), 8, "Poppins Black", A,
                            "#FFFFFF", f"\\3c{_c(P)}\\bord{pad}", "HlBox"))
        return ev
    if nome == "caixinha":
        # o adesivo de perguntas do Instagram (variants.json → caixinha)
        chamada, pergunta = _slot(texto_, "Me faça uma pergunta")
        ls = linhas_de(pergunta, 32)
        x0, w, faixa, pad, tam = 20, 1040, 132, 44, 64
        h = faixa + pad * 2 + len(ls) * tam
        return [
            _sombra(ret(x0, topo + 4, w, h, 46), 5),
            forma(6, ret(x0, topo, w, h, 46), "#FFFFFF"),
            forma(7, ret(x0, topo, w, faixa, 46, baixo=False), CX_FAIXA),
            texto(8, chamada, 540, topo + faixa / 2, 5, "Inter SemiBold", 53, "#FFFFFF"),
            texto(8, "\\N".join(ls), 540, topo + faixa + pad - 4, 8, "Inter", tam, CX_TEXTO),
        ]
    if nome == "noticia":
        olho, manchete = _slot(texto_, "ÚLTIMAS NOTÍCIAS")
        # a manchete ENCHE a linha, como o `quebra: encher` do editor: é texto
        # de app, alinhado à esquerda, não um bloco balanceado
        ls = encher(manchete, "Poppins ExtraBold", 100, W - 104)
        barra, tam = 134, 100
        h = barra + 54 + len(ls) * tam + 62
        cy = topo + barra / 2
        menu = "".join(ret(46, cy + d - 3.5, 50, 7, 3.5) for d in (-16, 0, 16))
        lupa = circulo(1012, cy - 4, 20) + circulo(1012, cy - 4, 13, inverso=True) + \
            f"m 1024 {cy + 5:.0f} l 1029 {cy:.0f} l 1046 {cy + 17:.0f} l 1041 {cy + 22:.0f} "
        return [
            _sombra(ret(0, topo + 10, W, h), 5),
            forma(6, ret(0, topo + barra, W, h - barra), "#FFFFFF"),
            forma(6, ret(0, topo, W, barra), P),
            forma(7, menu + lupa, "#FFFFFF"),
            texto(8, olho.upper(), 540, cy, 5, "Poppins ExtraBold", 66, "#FFFFFF"),
            texto(8, "\\N".join(ls), 52, topo + barra + 54, 7, "Poppins ExtraBold", tam, ESCURO),
        ]
    if nome == "balao":
        ls = linhas_de(texto_, 16)
        x0, w, pad, tam = 110, 860, 48, 100
        h = pad * 2 + len(ls) * tam
        rabicho = f"m {x0 + 110} {topo + h - 2} l {x0 + 200} {topo + h - 2} l {x0 + 70} {topo + h + 76} "
        return [
            _sombra(ret(x0, topo + 6, w, h, 44) + rabicho, 5),
            forma(6, ret(x0, topo, w, h, 44) + rabicho, PAPEL),
            texto(7, "\\N".join(realce(ln, forca, P, ESCURO) for ln in ls), 540, topo + pad, 8,
                  "Poppins Black", tam, ESCURO),
        ]
    if nome == "filete":
        ls = linhas_de(texto_, 18)
        tam, passo = 93, 87
        y_txt = topo + 8 + 30
        y_base = y_txt + len(ls) * passo + 26
        return [
            forma(5, ret(130, topo, 820, 8, 4) + ret(130, y_base, 820, 8, 4), P),
            *[texto(6, realce(ln, forca, P), 540, y_txt + i * passo, 8, "Poppins Black", tam, "#FFFFFF",
                    "\\shad3\\4a&H70&") for i, ln in enumerate(ls)],
        ]
    if nome == "fita":
        ls = linhas_de(up, 16)
        tam = 120
        h = len(ls) * tam + 56
        cy = topo + h / 2
        gira = f"\\org(540,{cy:.0f})\\frz4"
        return [
            forma(5, ret(-60, topo, W + 120, h), P, gira),
            texto(6, "\\N".join(ls), 540, cy, 5, "Anton", tam, "#FFFFFF", gira),
        ]
    if nome == "moldura":
        # tela "cheia" que não esconde: a borda na cor de fundo, o vídeo na janela
        ls = linhas_de(up, 14)
        A = caber(ls, "Poppins Black", 120, 860)
        furo = ret(90, 520, 900, 1160, 28, inverso=True)
        return [
            forma(10, ret(0, 0, W, H) + furo, F),
            texto(11, "\\N".join(realce(ln, forca, P) for ln in ls), 540, 260, 5, "Poppins Black", A, "#FFFFFF"),
        ]
    if nome == "aspas":
        ls = linhas_de(texto_, 15)
        return [
            forma(10, ret(0, 0, W, H), F),
            texto(11, "“", 80, 330, 7, "Libre Baskerville", 460, P),
            texto(11, "\\N".join(realce(ln, forca, P) for ln in ls), 100, 1000, 4, "Poppins Black", 108,
                  "#FFFFFF"),
        ]
    raise ValueError(f"headline sem desenho: {nome}")


def _slot(texto_: str, padrao: str) -> tuple[str, str]:
    """Caixinha e notícia têm um rótulo (a chamada, o olho): é a PRIMEIRA linha
    quando quem escreveu quebrou a linha, como o `slots: {olho: primeira}` do
    editor. Sem quebra, o rótulo padrão."""
    if "\n" in texto_:
        a, b = texto_.split("\n", 1)
        if a.strip() and b.strip():
            return a.strip(), " ".join(b.split())
    return padrao, texto_


CHEIA = {"moldura", "aspas"}


def montar(eventos: list[dict], ini: float, fim: float, entrada: str, ts) -> list[str]:
    """Os eventos como linhas Dialogue, com a ENTRADA aplicada igual a todos.
    As de tela cheia (camada ≥ 10) só saem em fade."""
    out = []
    for e in eventos:
        x, y = e["x"], e["y"]
        if e["camada"] >= 10 or entrada == "fade":
            pos = f"\\pos({x:.0f},{y:.0f})\\fad({0 if e['camada'] >= 10 else 160},240)"
        elif entrada == "desliza":
            pos = f"\\move({x:.0f},{y - 140:.0f},{x:.0f},{y:.0f},0,280)\\fad(120,240)"
        else:   # pop
            pos = (f"\\pos({x:.0f},{y:.0f})\\fscx60\\fscy60\\t(0,150,\\fscx108\\fscy108)"
                   f"\\t(150,280,\\fscx100\\fscy100)\\fad(0,240)")
        tags = e["tags"]
        # a forma desenhada escala no próprio desenho: o \p1 tem de vir por último
        p1 = tags.endswith("\\p1")
        if p1:
            tags = tags[:-3]
        out.append(f"Dialogue: {e['camada']},{ts(ini if e['camada'] < 10 else 0)},{ts(fim)},{e['estilo']},,0,0,0,,"
                   f"{{\\an{e['an']}{pos}{tags}{chr(92) + 'p1' if p1 else ''}}}{e['corpo']}")
    return out

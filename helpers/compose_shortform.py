#!/usr/bin/env python3
"""Monta a composição HyperFrames da Fase 2 short-form a partir dos dados.

Contrato: TUDO que o vídeo é sai de `edit-data.json` + `captions.json` + o
estilo escolhido na aba Estilo. Nenhuma decisão visual aqui dentro — a aparência
mora em `assets/styles/*.css` e os números em `assets/styles/variants.json`, os
mesmos que a prévia do editor lê. Um estilo escrito só aqui recria a divergência
prévia/render que o SKILL.md registra como anti-padrão.

    uv run python helpers/compose_shortform.py <edit-data.json> \\
        --captions <captions.json> -o <projeto>/index.html
"""
from __future__ import annotations

import argparse
import functools
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from text_measure import measure  # noqa: E402

SKILL_DIR = Path(__file__).resolve().parent.parent
STYLES_DIR = SKILL_DIR / "assets" / "styles"
VARIANTS = json.loads((STYLES_DIR / "variants.json").read_text())

HOLD = 0.6  # sobra depois da última palavra antes de a deixa sair

# Ordem das camadas, de baixo para cima. A arte da tela dividida fica logo
# ACIMA do vídeo e ABAIXO de tudo mais: o deslocamento documentado do empilhado
# põe a pilha DENTRO da arte, logo acima da costura, e com a arte por cima a
# legenda simplesmente sumia. É também por isso que o layout `top` tem degradê
# na costura — ele existe para dar base ao texto que fica SOBRE a arte.
TRACK = {
    "aroll": 0,
    # B-ROLL EM VÍDEO NA FAIXA, em track PRÓPRIA e logo abaixo da janela.
    #
    # Duas razões, ambas do renderer. Primeiro, ele recusa vídeo cronometrado
    # dentro de outro elemento cronometrado ("the framework cannot manage
    # playback of nested media — video will be FROZEN in renders"), então o
    # clipe sai da janela e vira irmão de topo. Segundo, irmão de topo na MESMA
    # track que a janela dá "overlapping_clips_same_track", porque os dois
    # ocupam o mesmo intervalo por construção.
    #
    # Abaixo de `split` e não acima: a costura mora na janela e existe para dar
    # base à legenda que senta sobre a arte. Com o vídeo por cima, a costura
    # sumiria e o texto perderia o fundo.
    "splitmedia": 1,
    "split": 2,      # arte (imagem) + costura
    "insert": 3,
    "bespoke": 4,
    # Grão, vazamento de luz, poeira: cobre a IMAGEM inteira (vídeo, inserções
    # e gráficos sob medida) e para ANTES da legenda. Sujar o texto é sujar a
    # única coisa da tela que não pode ficar suja.
    "overlay": 5,
    "caption": 6,
    "wordaccent": 7,
    "hook": 8,       # acima da legenda: os dois disputam a costura
    "flash": 9,      # por cima de tudo que é imagem
    "soundtrack": 10,
    "sfx": 11,
    # FORA da faixa do SFX. `SFX_LAYERS` numera 12–14 à mão logo abaixo, e o
    # áudio do a-roll ocupa a duração inteira: dividir track com um efeito curto
    # daria "overlapping_clips_same_track" em todo projeto com som.
    "audio": 16,
}

# Camadas de efeito. Com um índice só os efeitos eram obrigados a NUNCA se
# tocar, e o `check` barra a composição inteira quando dois se encavalam —
# derrubando o render por desenho de som legítimo (o riser do gancho correndo
# por baixo do whoosh de entrada). A voz mora na 11, então as camadas extras
# pulam para 12+.
SFX_LAYERS = [TRACK["sfx"], 12, 13, 14]

# O RISCO do empilhado — a volta a lápis que envolve a palavra, portada do
# edvid (`assets/shortform/src/PencilOutline.tsx`). Laço frouxo e ondulado com
# um rabo de sobra no fim: é o desenho à mão que faz o gesto ler como marcação
# de caneta, e não como forma geométrica. Uma elipse limpa no lugar dele lê como
# selo de software — foi o que esta fork tinha, e estava errado.
PENCIL_D = ("M 30 78 C 26 40, 120 20, 190 24 C 262 28, 300 52, 288 82 "
            "C 276 114, 150 132, 78 122 C 28 114, 8 92, 34 66 "
            "C 50 50, 96 40, 150 42")




def style_files(style_id: str, style: dict) -> list[str]:
    if style_id in ("scatter", "stacked", "editorial", "dinamico"):
        return [f"{style_id}.css", f"{style_id}.js"]
    # A FOLHA DECLARADA vence o nome do estilo. Os estilos que partilham um
    # motor (`css: "pop"`, `"revelar"`, `"palavra"`) são muitos e o motor é um;
    # sem este ramo, `render_html` pedia styles/pop.css e o que ia para o
    # projeto era o karaoke.css — a folha certa nunca chegava e a legenda saía
    # crua, com o defeito aparecendo só no render final.
    motor = style.get("css")
    if motor:
        return [f"{motor}.css", f"{motor}.js"]
    return ["karaoke.css", "karaoke.js"] if style["animated"] else ["static.css"]


def scat_hash(n: float) -> float:
    """Mesmo hash da prévia e do módulo do estilo: seno truncado.

    Determinístico por índice — a mesma deixa cai sempre no mesmo lugar. É o
    substituto de um aleatório, e o motivo é duro: aleatório de verdade
    re-sorteia o layout a cada quadro (texto tremendo) e faria dois renders do
    mesmo projeto saírem diferentes, matando o determinismo do motor.
    """
    x = math.sin(n * 127.1 + 311.7) * 43758.5453
    return x - math.floor(x)


def scatter_markup(timed: list[dict], st: dict) -> str:
    """Deixas do disperso: linhas irregulares, uma palavra destacada por deixa."""
    gap = st["gap"]
    blocks = []
    for ci, t in enumerate(timed):
        words = [w["text"].lower() for w in t["cue"]]
        # tempo ABSOLUTO de cada palavra: ela aparece quando é FALADA.
        # Um passo fixo (0.22s da prévia) supõe deixa longa — com 8 palavras
        # numa deixa de 1.39s a entrada levaria 1.76s e as últimas nunca
        # apareceriam, com a deixa já saindo. Seguir a fala é mais simples e
        # mais correto: é o que uma legenda faz.
        ats = [w["startMs"] / 1000 for w in t["cue"]]
        # destaque: a palavra mais longa da deixa, e só se ela tiver peso
        hi_idx, hi_len = -1, st["hiMinLen"] - 1
        for i, w in enumerate(words):
            if len(w) > hi_len:
                hi_idx, hi_len = i, len(w)

        lines, cur = [], []
        for i, w in enumerate(words):
            if i == hi_idx:
                if cur:
                    lines.append(cur)
                lines.append([(i, w, True)])   # a destacada fica sozinha na linha
                cur = []
                continue
            cur.append((i, w, False))
            if len(cur) >= (4 if scat_hash(31 + i) > 0.5 else 3):
                lines.append(cur)
                cur = []
        if cur:
            lines.append(cur)

        rows = []
        for li, ln in enumerate(lines):
            width = 0.0
            for _, w, hi in ln:
                size = st["size"] * (st["hiScale"] if hi else 1)
                weight = 600 if hi else st["weight"]
                width += measure(w, st["family"], size, weight) + gap
            room = max(0.0, (st["maxW"] - width) / 2) * st["spread"]
            dx = (scat_hash(17 + li * 5 + 3) * 2 - 1) * room
            spans = "".join(
                f'<span{" class=\"hi\"" if hi else ""} data-at="{ats[i]:.3f}">'
                f'{esc(w)}</span>'
                for i, w, hi in ln)
            rows.append(f'<div class="scat-line" style="translate:{dx:.1f}px 0px">'
                        f'{spans}</div>')

        blocks.append(
            f'<div class="scat-cue clip" data-start="{t["start"]:.3f}" '
            f'data-duration="{t["end"] - t["start"]:.3f}" data-track-index="{TRACK["caption"]}">'
            f'{"".join(rows)}</div>')
    return "\n".join("    " + b for b in blocks)


def fit_font(text: str, base: float, avail: float, factor: float) -> int:
    """Corpo estimado pela CONTAGEM de caracteres, não pela medida real.

    Deliberadamente igual ao original: o empilhado depende de as linhas de uma
    deixa guardarem proporção ENTRE SI, e uma estimativa uniforme faz isso
    melhor que a medida exata — com medida real, uma linha de letras estreitas
    cresce e quebra a pilha. Aqui a aproximação é a intenção, não um atalho.
    """
    n = max(1, len(text.strip()))
    est = n * base * factor
    return int(avail / (n * factor)) if est > avail else int(base)


def editorial_markup(cues: list[dict], st: dict, duration: float) -> str:
    """Blocos do estilo EDITORIAL: um clip por deixa; cada palavra chega no seu
    TEMPO DE FALA (data-at absoluto) com a entrada do PAPEL dela — o karaokê do
    estilo é a palavra chegando junto da voz, não um destaque sobre texto
    parado. `anim: type` vira caracteres soltos (.ch) aqui, porque o
    escalonamento por caractere precisa de um nó por caractere."""
    blocks: list[str] = []
    for c in cues:
        s = c["startMs"] / 1000
        if s >= duration:
            continue
        e = min(c["endMs"] / 1000, duration)
        linhas: list[str] = []
        for ln in c["lines"]:
            spans: list[str] = []
            for w in ln:
                at = w["fromMs"] / 1000
                anim = w.get("anim", "fade")
                if anim == "type":
                    corpo = "".join(f'<i class="ch">{esc(ch)}</i>' for ch in w["text"]) + " "
                else:
                    corpo = esc(w["text"]) + " "
                spans.append(f'<span class="edt-w r-{w["role"]}" data-at="{at:.3f}" '
                             f'data-anim="{anim}">{corpo}</span>')
            linhas.append('<div class="edt-line">' + "".join(spans) + "</div>")
        blocks.append(
            f'    <div class="edt-cue clip" data-start="{s:.3f}" '
            f'data-duration="{e - s:.3f}" data-exit="{c.get("exit", "abrupt")}" '
            f'data-track-index="{TRACK["caption"]}">' + "".join(linhas) + "</div>")
    return "\n".join(blocks)


def dinamico_markup(cues: list[dict], st: dict, duration: float) -> str:
    """Blocos do estilo DINÂMICO: um clip por deixa, bloco central diagramado
    inteiro e revelado palavra a palavra (data-at absoluto). A sans carrega
    data-lit — o instante em que ACENDE, decidido pelo diretor. Toda serif
    vira caracteres soltos (.ch): a cascata precisa de um nó por caractere.
    A figure viaja como nó irmão da coluna, com o corpo (--fig-em) decidido
    AQUI pelo comprimento do texto — o CSS não mede string."""
    blocks: list[str] = []
    for c in cues:
        s = c["startMs"] / 1000
        if s >= duration:
            continue
        e = min(c["endMs"] / 1000, duration)
        linhas: list[str] = []
        for ln in c["lines"]:
            spans: list[str] = []
            lead_serif = ln and ln[0]["role"] in ("serif", "serifAcc")
            for w in ln:
                at = w["fromMs"] / 1000
                lit = f' data-lit="{w["litMs"] / 1000:.3f}"' if "litMs" in w else ""
                if w["role"] in ("serif", "serifAcc"):
                    corpo = "".join(f'<i class="ch">{esc(ch)}</i>' for ch in w["text"]) + " "
                else:
                    corpo = esc(w["text"]) + " "
                spans.append(f'<span class="din-w r-{w["role"]}" data-at="{at:.3f}"'
                             f'{lit}>{corpo}</span>')
            cls = "din-line lead-serif" if lead_serif else "din-line"
            linhas.append(f'<div class="{cls}">' + "".join(spans) + "</div>")
        fig_html = ""
        has_fig = ""
        if c.get("figure"):
            fg = c["figure"]
            fig_em = st.get("figEmShort", 3.4) if len(fg["text"]) <= 2 else st.get("figEmLong", 2.1)
            fig_html = (f'<div class="din-fig" style="--fig-em:{fig_em}" '
                        f'data-at="{fg["fromMs"] / 1000:.3f}">{esc(fg["text"])}</div>')
            has_fig = " has-fig"
        blocks.append(
            f'    <div class="din-cue clip{has_fig}" data-start="{s:.3f}" '
            f'data-duration="{e - s:.3f}" data-exit="{c.get("exit", "abrupt")}" '
            f'data-track-index="{TRACK["caption"]}">' + fig_html
            + '<div class="din-col">' + "".join(linhas) + "</div></div>")
    return "\n".join(blocks)


def stacked_markup(cues: list[dict], st: dict, duration: float,
                   accent: str = "#5fd07a") -> tuple[str, int]:
    """Deixas do empilhado, do arquivo preparado. Retorna (markup, n_estendidas).

    O `accent` pinta o círculo do SOLO_OUTLINE. Ele era FIXO em `#5fd07a` aqui
    dentro — um verde que atravessava qualquer paleta escolhida na aba Estilo e
    aparecia no meio de uma composição laranja, sem nada reclamar. É exatamente
    o anti-padrão que a Hard Rule 11 nomeia: cor decidida no composer em vez de
    vir do dado.
    """
    blocks, stretched = [], 0
    min_solo = st["minSoloMs"] / 1000
    for k, c in enumerate(cues):
        start, end = c["startMs"] / 1000, c["endMs"] / 1000
        if start >= duration:
            continue
        solo = c["preset"] in ("SOLO_BIG", "SOLO_OUTLINE")
        # Palavra sozinha precisa de DURAÇÃO, não só de peso: abaixo de ~340ms
        # ela pisca em um quadro e lê como falha. Medido nesta fixture: o
        # preparador entregou uma deixa SOLO de 20ms.
        if solo and end - start < min_solo:
            limit = (cues[k + 1]["startMs"] / 1000 if k + 1 < len(cues) else duration)
            new_end = min(start + min_solo, limit, duration)
            if new_end > end:
                end, stretched = new_end, stretched + 1
        end = min(end, duration)
        if end <= start:
            continue

        rows = []
        if solo:
            w = c["lines"][0][0]
            size = fit_font(w["text"], st["soloBase"], st["maxW"], st["soloFitFactor"])
            # O risco começa APAGADO (`stroke-dashoffset: 1` sobre um
            # `pathLength` de 1) e o stacked.js o desenha. O gesto é metade do
            # efeito: um traço que já está lá quando a palavra chega não lê
            # como alguém riscando, lê como moldura.
            circle = ('<svg class="stk-ellipse" viewBox="0 0 312 150" fill="none" '
                      'preserveAspectRatio="none">'
                      f'<path d="{PENCIL_D}" fill="none" stroke="{accent}" '
                      'stroke-linecap="round" stroke-linejoin="round" '
                      'vector-effect="non-scaling-stroke" pathLength="1" '
                      'stroke-dasharray="1" stroke-dashoffset="1"/></svg>'
                      if c["preset"] == "SOLO_OUTLINE" else "")
            # O invólucro é uma DIV, não um span: `.stk-line span` zera a
            # opacidade (é a animação que a devolve, palavra a palavra), e um
            # span aqui herdaria isso e sumiria com a elipse dentro.
            rows.append(
                f'<div class="stk-line"><div class="stk-solo-wrap">{circle}'
                f'<span class="stk-solo s0" data-at="{w["fromMs"] / 1000:.3f}" '
                f'style="font-size:{size}px">{esc(w["text"])}</span></div></div>')
        else:
            for li, line in enumerate(c["lines"]):
                styles = c.get("lineStyles") or []
                idx = styles[li] if li < len(styles) else (li + c.get("styleOffset", 0)) % 4
                text = " ".join(w["text"] for w in line)
                size = fit_font(text, st["size"], st["maxW"], st["fitFactor"])
                if idx == 1:
                    size = round(size * 0.72)
                if idx == 2:
                    size = round(size * 0.95)
                if (c.get("lineEmph") or [])[li:li + 1] == [True]:
                    size = round(size * 1.12)
                if (c.get("lineBoost") or [])[li:li + 1] == [True]:
                    size = round(size * 1.35)
                spans = "".join(
                    f'<span class="s{idx}" data-at="{w["fromMs"] / 1000:.3f}">'
                    f'{esc(w["text"])}{" " if j < len(line) - 1 else ""}</span>'
                    for j, w in enumerate(line))
                rows.append(f'<div class="stk-line" style="font-size:{size}px">{spans}</div>')

        blocks.append(
            f'<div class="stk-cue clip" data-start="{start:.3f}" '
            f'data-duration="{end - start:.3f}" data-exit="{c.get("exit", "abrupt")}" '
            f'data-track-index="{TRACK["caption"]}">{"".join(rows)}</div>')
    return "\n".join("    " + b for b in blocks), stretched


def split_windows(data: dict, H: int, duration: float) -> list[dict]:
    """Janelas de tela dividida, com a geometria já resolvida por layout."""
    out = []
    for it in (data.get("splitInserts") or []):
        start = float(it.get("start", 0))
        end = min(float(it.get("end", start)), duration)
        if start >= duration or end <= start:
            continue
        layout = it.get("layout", "top")
        lay = VARIANTS["split"].get(layout)
        if lay is None:
            continue
        band = lay["band"]
        is_top = layout == "top"
        out.append({
            "start": start, "end": end, "layout": layout,
            "src": it.get("src") or it.get("ref"), "band": band,
            # a arte ocupa a faixa; o vídeo fica com o resto do quadro
            "artTop": 0 if is_top else H - band,
            "vidTop": band if is_top else 0,
            "vidHeight": H - band,
            # Override POR JANELA. Num corte multi-take a cabeça se move —
            # medido, ~170px entre tomadas — e um valor único para o vídeo
            # inteiro corta as tomadas altas e deixa um vão sob a costura nas
            # baixas.
            "zoom": float(it.get("zoom", lay["zoom"])),
            "focusY": float(it.get("focusY", lay["focusY"])),
            # COMO A ARTE PREENCHE A FAIXA. O port perdeu esta opção: o CSS
            # fixava `object-fit: cover`, e uma foto larga entrava cortada dos
            # dois lados sem que houvesse como pedir o contrário. `cover`
            # continua o padrão — só deixou de ser a única resposta.
            "fit": (it.get("fit") or "cover"),
            "captionBottom": lay["captionBottom"],
            "seam": lay["seam"],
            "centre": (lay.get("centreOffset") or {}),
        })
    return out


VIDEO_EXT = (".mp4", ".mov", ".webm", ".m4v")


def split_art(i: int, w: dict) -> str:
    """A arte da faixa — `<video>` quando é vídeo, `<img>` quando é imagem.

    O port para HyperFrames trouxe só a metade `<img>`, e com isso b-roll em
    vídeo era estruturalmente impossível: o arquivo entrava numa tag que não
    sabe tocar, e saía como um quadro parado. Em todo o compositor existia UMA
    tag `<video>`, e era o a-roll.

    O clock local sai de graça aqui. O `data-media-start` do HyperFrames é o
    ponto de entrada DA MÍDIA, independente de onde a janela cai na linha do
    tempo — que é exatamente o que impede o defeito clássico de inserção
    congelada: passar o tempo absoluto da composição para um clipe curto faz o
    seek passar do fim e o quadro travar no último frame.

    O `id` não é enfeite: sem ele o renderer não descobre o elemento (mesma
    razão documentada no `<audio>` do a-roll).

    Devolve (dentro_da_janela, irmão_de_topo): imagem vai dentro, vídeo vai
    fora. Ver o comentário no `split_markup`.
    """
    src = w.get("src")
    if not src:
        return "", ""
    geo = f'top:{w["artTop"]}px; height:{w["band"]}px; object-fit:{w.get("fit", "cover")}'
    if str(src).lower().endswith(VIDEO_EXT):
        # `clip` + `data-*` põem o vídeo sob o relógio do renderer. Por isso ele
        # NÃO leva a classe `ave-split-art`: aquela nasce `display:none` e é
        # acesa pelo split.js, e as duas gerências brigariam pelo mesmo estilo.
        return "", (f'<video id="splitart{i}" class="ave-split-media clip" src="{src}" '
                    f'muted playsinline data-start="{w["start"]:.3f}" '
                    f'data-duration="{w["end"] - w["start"]:.3f}" data-media-start="0" '
                    f'data-track-index="{TRACK['splitmedia']}" style="{geo}"></video>')
    return f'<img class="ave-split-art" src="{src}" alt="" style="{geo}">', ""


def _bo_ritmo(dur: float) -> tuple[float, float]:
    """O RITMO da janela decide a entrada — não uma constante.

    Janela curta é acento no meio de fala rápida: entra seca. Janela longa é um
    momento de respiro: a animação pode se dar ao luxo de chegar. Os números
    são (entrada, cadência-entre-filhos) em segundos; mudar a régua é aqui,
    nunca em keyframe."""
    if dur < 2.2:
        return 0.18, 0.07
    if dur > 4.5:
        return 0.42, 0.16
    return 0.30, 0.11


def _hex_rgb(hexa: str) -> str:
    """'#0D2137' → '13,33,55' — para as sombras rgba do kit."""
    h = (hexa or "").lstrip("#")
    if len(h) != 6:
        return "0,0,0"
    return ",".join(str(int(h[k:k + 2], 16)) for k in (0, 2, 4))


def _bo_vars(kit: dict, data: dict) -> str:
    """As variáveis CSS de uma janela, resolvidas do MOTION KIT.

    O kit já chega com a marca aplicada (motion_kit.carregar_kit resolve
    brand.json por cima); `brollColors` no edit-data é o override pontual de
    projeto. Nenhuma cor/fonte/forma nasce no CSS — trocar o gosto é trocar o
    kit, nunca editar folha de estilo."""
    cores = {**(kit.get("cores") or {}), **(data.get("brollColors") or {})}
    fontes = kit.get("fontes") or {}
    formas = kit.get("formas") or {}
    sombra = kit.get("sombra") or "0 30px 70px -28px"
    return (
        f"--bo-accent:{cores.get('accent', '#ff3b30')};"
        f"--bo-deep:{cores.get('deep', '#0B0B0F')};"
        f"--bo-card-top:{cores.get('cardTop', cores.get('deep', '#17171C'))};"
        f"--bo-card-bottom:{cores.get('cardBottom', cores.get('deep', '#0B0B0F'))};"
        f"--bo-paper:{cores.get('paper', '#F5F5F5')};"
        f"--bo-soft:{cores.get('accentSoft', cores.get('accent', '#ff3b30'))};"
        f"--bo-radius:{formas.get('raioCardPx', 16)}px;"
        f"--bo-pill:{formas.get('raioPillPx', 999)}px;"
        f"--bo-frame:{formas.get('molduraMock', '6px')};"
        f"--bo-shadow:{sombra} rgba({_hex_rgb(cores.get('deep', '#000000'))},.5);"
        f"--bo-font-display:'{fontes.get('display', 'Poppins')}';"
        f"--bo-font-ui:'{fontes.get('ui', 'Poppins')}'"
    )


def caixinha_markup(data: dict, duration: float, events: list, accent: str) -> tuple[str, str]:
    """A CAIXINHA DE PERGUNTAS do Instagram, como gancho do vídeo.

    Dado em `edit-data.json`:
        "questionBox": {"chamada": "mande sua dúvida 🤎",
                        "pergunta": "…", "resposta": "…" (opcional),
                        "start": 0.0, "end": 8.4 | null (fica até o fim),
                        "top": 300, "respostaAt": 4.2}

    Duas decisões de construção que o formato exige:

    · a caixa NÃO veste o Motion Kit — a fidelidade é com a interface do app,
      e um adesivo com a cara da marca de quem edita deixa de ser o adesivo;
    · `end` ausente (ou ≥ duração) significa FICAR ATÉ O FIM, e nesse caso não
      há animação de saída: despedir-se de algo que acaba junto com o vídeo lê
      como falha de render, não como escolha.
    """
    q = data.get("questionBox") or {}
    pergunta = (q.get("pergunta") or "").strip()
    if not pergunta:
        return "", ""
    cx0 = VARIANTS.get("caixinha", {})

    def _cabe(txt: str, teto: int, onde: str) -> str:
        """O TETO VALE AQUI TAMBÉM, e não só no campo da aba.

        O campo trava a digitação, mas o dado também chega escrito à mão (dado
        de projeto, uma sessão minha, um edit-data editado). Passar do teto
        encolheria a fonte ou estouraria a caixa, e as duas saídas estragam o
        formato — então corta na última palavra inteira e DIZ que cortou.
        """
        if len(txt) <= teto:
            return txt
        corte = txt[:teto].rsplit(" ", 1)[0].rstrip(",;:") or txt[:teto]
        print(f"  aviso: {onde} tem {len(txt)} caracteres (teto {teto}) — "
              f"cortado em “{corte}…”", file=sys.stderr)
        return corte + "…"

    pergunta = _cabe(pergunta, int(cx0.get("limitePergunta", 72)), "a pergunta da caixinha")
    cx = VARIANTS.get("caixinha", {})
    s = float(q.get("start", 0.0))
    fim_dado = q.get("end")
    fica_ate_o_fim = fim_dado in (None, "", 0) or float(fim_dado) >= duration - 0.05
    e = duration if fica_ate_o_fim else min(float(fim_dado), duration)
    d = max(0.1, e - s)

    # O ESPAÇO VAI FORA DO SPAN. Dentro dele o navegador o engole: `.cx-w` é
    # `inline-block`, e espaço no fim de uma caixa inline-block colapsa — as
    # palavras saem grudadas ("Comoo McDonald'sganha"). Separador entre caixas
    # é texto entre elas, não conteúdo delas.
    palavras = " ".join(f'<span class="cx-w">{esc(w)}</span>' for w in pergunta.split())
    chamada = esc(_cabe((q.get("chamada") or "mande sua dúvida").strip(),
                        int(cx0.get("limiteChamada", 60)), "a chamada da caixinha"))
    resposta = (q.get("resposta") or "").strip()
    resp_html, resp_attr = "", ""
    if resposta:
        # a resposta entra DEPOIS da pergunta ser lida; sem instrução, um respiro
        # proporcional ao tamanho dela (≈45ms por palavra, piso de 1,2s)
        resp_at = float(q.get("respostaAt", s + max(1.2, 0.34 + 0.045 * len(pergunta.split()) + 0.6)))
        resp_html = f'\n    <div class="cx-resposta">{esc(resposta)}</div>'
        resp_attr = f' data-reply-at="{resp_at:.3f}"'
        events.append((resp_at, "callout"))

    events.append((s, "element"))   # o adesivo colando
    r = cx.get("resposta", {})
    estilo = (f'--cx-top:{q.get("top", cx.get("topoPadrao", 300))}px;'
              f' --cx-w:{cx.get("largura", 820)}px; --cx-radius:{cx.get("raio", 30)}px;'
              f' --cx-bar-h:{cx.get("faixaAltura", 96)}px;'
              f' --cx-bar-bg:{cx.get("faixaFundo", "#26262b")};'
              f' --cx-bar-fg:{cx.get("faixaCor", "#e9e9ea")};'
              f' --cx-bar-size:{cx.get("faixaTamanho", 30)}px;'
              f' --cx-body-bg:{cx.get("corpoFundo", "#fff")};'
              f' --cx-body-fg:{cx.get("corpoCor", "#1c1c1e")};'
              f' --cx-body-size:{cx.get("corpoTamanho", 46)}px;'
              f' --cx-body-lh:{cx.get("corpoEntrelinha", 1.28)};'
              f' --cx-body-pad:{cx.get("corpoPadding", 44)}px;'
              f' --cx-shadow:{cx.get("sombra", "0 26px 60px -18px rgba(0,0,0,.55)")};'
              f' --cx-accent:{accent};'
              f' --cx-reply-size:{r.get("tamanho", 42)}px;'
              f' --cx-reply-radius:{r.get("raio", 26)}px;'
              f' --cx-reply-pad:{r.get("padding", "26px 34px")};'
              f' --cx-reply-inset:{r.get("recuo", 90)}px;'
              f' --cx-font:{VARIANTS["styles"]["karaoke"]["cssFamily"]}')
    html = (f'  <div class="ave-caixa clip" data-start="{s:.3f}" data-duration="{d:.3f}"'
            f' data-track-index="{TRACK["overlay"]}" data-tilt="{cx.get("inclinacao", -1.6)}"'
            f' data-exit="{"0" if fica_ate_o_fim else "1"}"{resp_attr}'
            f' style="{estilo}">\n'
            f'    <div class="cx-card">\n'
            f'      <div class="cx-faixa">{chamada}</div>\n'
            f'      <div class="cx-corpo">{palavras}</div>\n'
            f'    </div>{resp_html}\n  </div>')
    janela = f"{s:.3f}-{e:.3f}"
    return html, janela


def broll_markup(data: dict, duration: float, events: list, kit: dict) -> str:
    """Janelas de ênfase POR CIMA do a-roll — o formato "Broll Overlay".

    Quatro tipos (`kind`): `words` (frase cinética), `stat` (número que conta),
    `labels` (etiquetas em sequência), `media` (mp4/png pronto). `dim` liga o
    scrim — um DIV preto sobre o vídeo, NUNCA opacity no próprio vídeo
    (opacidade <1 cria contexto de empilhamento e mata blend; medido). `pos`:
    full/top/bottom, com o bottom acabando antes da faixa de legenda.

    Ordem no DOM: depois do split, antes do flash e das legendas — o scrim
    escurece o a-roll e as legendas continuam legíveis por cima. Janelas nunca
    durante o hook (o check acusaria texto sob elemento opaco) e nunca
    sobrepostas entre si (a mídia divide track com o split). Cada janela emite
    seu próprio SFX: whoosh cheio quando escurece, suave quando cavalga."""
    wins = [w for w in (data.get("brollOverlays") or [])
            if float(w.get("start", 0)) < duration
            and float(w.get("end", 0)) > float(w.get("start", 0))]
    if not wins:
        return ""
    vars_css = _bo_vars(kit, data)
    fontes = kit.get("fontes") or {}
    formas = kit.get("formas") or {}
    mo = kit.get("motion") or {}
    # os números do kit viajam num atributo só; o JS executa, nunca decide
    motion_attr = json.dumps({
        "linhas": mo.get("linhas") or {"yPercent": 110, "stagger": 0.1, "dur": 0.8},
        "reveal": mo.get("reveal") or {"y": 28, "dur": 0.7},
        "clip": mo.get("clip") or {"dur": 0.9},
        "capline": mo.get("capline") or {"larguraPx": 140, "dur": 0.8, "dotDelay": 0.4},
        "ringSpinS": mo.get("ringSpinS") or [60, 45],
    }, separators=(",", ":"))
    kit_classes = ""
    if fontes.get("displayItalico"):
        kit_classes += " kit-italico"
    if formas.get("topoFolha"):
        kit_classes += " folha"
    blocks: list[str] = []
    for i, o in enumerate(wins):
        s = float(o["start"])
        e = min(float(o["end"]), duration)
        d = e - s
        pos = o.get("pos", "full")
        if pos not in ("full", "top", "bottom"):
            pos = "full"
        dim = o.get("dim")
        dim_val = 0.9 if dim is True else (float(dim) if dim else 0.0)
        vin, stag = _bo_ritmo(d)
        # override por janela: quando a cadência precisa casar com a FALA
        # (etiquetas entrando no ritmo da enumeração falada), o autor manda
        vin = float(o.get("in", vin))
        stag = float(o.get("stagger", stag))
        scrim_attr = ""
        if dim_val > 0:
            blocks.append(f'  <div id="boscrim{i}" class="ave-bo-scrim" '
                          f'data-dim="{dim_val:.2f}"></div>')
            scrim_attr = f' data-bo-scrim="boscrim{i}"'
        kind = o.get("kind", "words")
        inner = ""
        if kind == "words":
            palavras = (o.get("text") or "").split()
            # o destaque cai na palavra mais longa quando ninguém escolheu —
            # heurística barata que acerta o substantivo na maioria das frases
            acc = set(o.get("accentWords") or (
                [max(range(len(palavras)), key=lambda k: len(palavras[k]))]
                if palavras else []))
            spans = "".join(
                f'<span class="bo-w{" acc" if k in acc else ""}">{esc(p)}</span>'
                for k, p in enumerate(palavras))
            inner = f'<div class="ave-bo-words">{spans}</div>'
        elif kind == "stat":
            num = o.get("count")
            num_attr = f' data-count="{num}"' if num is not None else ""
            pref = (f'<span class="bo-fix">{esc(str(o["prefix"]))}</span>'
                    if o.get("prefix") else "")
            suf = (f'<span class="bo-fix">{esc(str(o["suffix"]))}</span>'
                   if o.get("suffix") else "")
            lab = (f'<div class="bo-label">{esc(str(o["label"]))}</div>'
                   if o.get("label") else "")
            inner = (f'<div class="ave-bo-stat"><div class="bo-value">{pref}'
                     f'<span class="bo-num"{num_attr}>{esc(str(o.get("value", "")))}</span>'
                     f'{suf}</div>{lab}</div>')
            events.append((s + vin * 0.4, "callout"))
        elif kind == "labels":
            itens = o.get("items") or []
            # CADA ETIQUETA PODE TER SEU INSTANTE. Item como texto entra na
            # cadência fixa; item como {"t": "…", "at": 5.42} entra no tempo
            # ABSOLUTO da fala. Foi o que o vídeo das "4 perguntas" exigiu: as
            # perguntas são ditas com espaçamento irregular (3.8 · 5.42 · 6.79 ·
            # 9.60) e uma cadência constante descolaria a lista da voz — o
            # arquétipo existe para ACOMPANHAR a fala, não para desfilar sozinho.
            def _txt(it):
                return it.get("t", "") if isinstance(it, dict) else str(it)

            def _at(it, k):
                if isinstance(it, dict) and it.get("at") is not None:
                    return float(it["at"])
                return s + k * max(stag, 0.14)

            inner = ('<div class="ave-bo-labels">'
                     + "".join(f'<div class="bo-item" data-at="{_at(it, k):.3f}">'
                               f'<span class="bo-idx">{k + 1:02d}</span>'
                               f'<span>{esc(_txt(it))}</span></div>'
                               for k, it in enumerate(itens))
                     + '</div>')
            for k, it in enumerate(itens[:6]):
                events.append((_at(it, k), "tick"))
        elif kind == "media":
            src = o.get("src", "")
            aspect = o.get("aspect", "16 / 9")
            if str(src).lower().endswith(VIDEO_EXT):
                m = (f'<video id="bomedia{i}" class="clip" src="{src}" muted playsinline '
                     f'data-start="{s:.3f}" data-duration="{d:.3f}" '
                     f'data-media-start="{float(o.get("mediaStart", 0)):.3f}" '
                     f'data-track-index="{TRACK["splitmedia"]}"></video>')
            else:
                m = f'<img src="{src}" alt="">'
            inner = f'<div class="ave-bo-media" style="aspect-ratio:{aspect}">{m}</div>'
        else:
            print(f"  aviso: brollOverlay #{i} de kind '{kind}' desconhecido — pulado",
                  file=sys.stderr)
            continue
        events.append((s, "hook" if dim_val > 0 else "element"))
        # O CENÁRIO vem do kit: glow radial + anéis girando nas janelas cheias
        # (o hero das LPs); painel-cartão nas de faixa (o sticky card). Eyebrow
        # e linha-legenda são a assinatura editorial — entram quando fazem
        # sentido para o tipo, e o eyebrow só quando o autor escreveu um.
        cenario = ""
        if pos == "full":
            if formas.get("aneis", True):
                cenario += '<div class="bo-ring r1"></div><div class="bo-ring r2"></div>'
            if formas.get("glowRadial", True):
                cenario += '<div class="bo-glow"></div>'
        eyebrow = (f'<div class="bo-eyebrow">{esc(str(o["eyebrow"]))}</div>'
                   if o.get("eyebrow") else "")
        capline = ('<div class="bo-capline"><i class="l"></i><i class="d"></i></div>'
                   if kind in ("words", "stat") else "")
        conteudo = f"{eyebrow}{inner}{capline}"
        if pos in ("top", "bottom") and kind != "media":
            conteudo = f'<div class="bo-card">{conteudo}</div>'
        # `clip` + track são exigência do motor para elemento com timing — sem
        # eles o check barra (timed_element_missing_clip_class, medido). As
        # janelas não se sobrepõem entre si, então dividem um track só.
        blocks.append(
            f'  <div id="bo{i}" class="ave-bo-win pos-{pos} clip{kit_classes}"{scrim_attr} '
            f'data-start="{s:.3f}" data-duration="{d:.3f}" '
            f'data-track-index="{TRACK["overlay"]}" '
            f'data-in="{vin}" data-stagger="{stag}" '
            f"data-motion='{motion_attr}' "
            f'style="{vars_css}">'
            f'{cenario}{conteudo}</div>')
    return "\n".join(blocks)


def split_markup(wins: list[dict], style_id: str = "") -> str:
    blocks = []
    for i, w in enumerate(wins):
        art, art_irmao = split_art(i, w)
        # o degradê cobre a parte de baixo da arte, que é onde a legenda encosta
        seam = (f'<div class="ave-split-seam" '
                f'style="top:{w["artTop"] + w["band"] - 220}px; height:280px"></div>'
                if w["seam"] else "")
        blocks.append(
            f'<div id="split{i}" class="ave-split-win clip" data-start="{w["start"]:.3f}" '
            f'data-duration="{w["end"] - w["start"]:.3f}" data-track-index="{TRACK['split']}" '
            f'data-zoom="{w["zoom"]}" data-focus="{w["focusY"]}" '
            f'data-vid-top="{w["vidTop"]}" data-vid-height="{w["vidHeight"]}"'
            f'{w.get("centreAttr", "")}>'
            f'{art}{seam}</div>')
        # O VÍDEO SAI DE DENTRO DA JANELA, e não é organização: é requisito do
        # renderer. O linter do HyperFrames reprova com todas as letras —
        # "video_nested_in_timed_element: the framework cannot manage playback
        # of nested media — video will be FROZEN in renders" — porque a janela
        # também tem `data-start`. Dois relógios sobre o mesmo elemento e o de
        # fora vence, congelando o clipe no primeiro quadro. Como irmão de topo
        # ele tem relógio próprio; a geometria não muda, porque a janela não é
        # `position`ada e a arte já se posicionava contra o #root.
        if art_irmao:
            blocks.append(art_irmao)
    return "\n".join("  " + b for b in blocks)


def adaptive_accent(video: Path, brand_accent: str, top: float, height: float,
                    windows: list[tuple[float, float]]) -> list[str]:
    """Uma cor de accent por janela, medindo o FUNDO onde o elemento vai ficar.

    Existe porque #FF6B1A tem luminância MÉDIA (L=0.318): ele só passa em WCAG
    contra fundo bem escuro ou bem claro, e entre 0.10 e 0.35 fica em 1.09–2.46.
    Medido numa palavra em destaque sobre fundo quente: 1.05:1.

    A regra é de RESERVA, não de otimização: a cor ESCOLHIDA sempre, e só escala
    para outra da paleta quando ela reprova o contraste. Escolher sempre a de
    maior contraste trocaria a cor da marca em todo quadro, que é abandoná-la.

    **A primeira versão dizia isto e fazia o contrário.** Ela chamava
    `pick_accent` direto e devolvia o que a paleta mandasse — a cor escolhida
    pelo usuário nunca chegava a ser candidata. Resultado visível: `#ff5200`
    escolhido na aba Estilo saía como `#FFAD7A` (o `accentSoft`) em toda a
    headline, e lia como laranja "apagada". O usuário viu antes de mim.

    Agora a cor escolhida é MEDIDA primeiro; a paleta só entra se ela reprovar.
    """
    if not video.exists() or not windows:
        return [brand_accent] * len(windows)
    try:
        from backdrop_luma import (sample_band, pick_accent, contrast_ratio,
                                   relative_luminance, hex_to_rgb, WCAG_MIN)
        palette = json.loads((SKILL_DIR / "brand" / "avelin.json").read_text())["palette"]
        samples = sample_band(video, top, height, 0.06, 0.88)
    except Exception:
        return [brand_accent] * len(windows)
    if not samples:
        return [brand_accent] * len(windows)

    try:
        chosen_luma = relative_luminance(*hex_to_rgb(brand_accent))
    except Exception:
        return [brand_accent] * len(windows)

    out = []
    for a, b in windows:
        inside = [l for t, l in samples if a <= t < b]
        if not inside:
            inside = [min(samples, key=lambda tl: abs(tl[0] - (a + b) / 2))[1]]
        bg = sum(inside) / len(inside)
        # a escolhida passa? então é ela. Sem "otimizar" o que já serve.
        if contrast_ratio(chosen_luma, bg) >= WCAG_MIN:
            out.append(brand_accent)
            continue
        # Reprovou. Só vale trocar se a substituta PASSAR — trocar a cor da
        # marca por outra que também reprova é perder a marca sem ganhar
        # legibilidade. Medido na parede deste projeto (luma 0,28): #ff5200 dá
        # 1,02:1, o canônico 1,12:1 e o `accentSoft` 1,74:1 — a régua é 3,0, e
        # a versão anterior trocava para o soft assim mesmo, entregando uma
        # laranja "apagada" que continuava ilegível pela régua. Quando nada
        # passa, quem sustenta a leitura é a sombra que o estilo já desenha.
        name, ratio = pick_accent(bg, palette)
        out.append(palette.get(name, brand_accent) if ratio >= WCAG_MIN
                   else brand_accent)
    return out


def sfx_blocks(events: list[tuple[float, str]], proj: Path,
               duration: float) -> tuple[list[str], list[str]]:
    """Elementos de áudio dos efeitos, distribuídos em camadas. Retorna
    (blocos, avisos).

    Duas coisas que a referência documenta como já vividas e que só aparecem
    OUVINDO — a mixagem parece certa e não se escuta nada:

    - o arquivo começa ANTES do evento, compensando o silêncio inicial MEDIDO.
      Sem isso o clique do `caption-click` chega 158ms atrasado, depois de um
      efeito de 230ms já ter acabado.
    - o nível é conferido: abaixo de -12 dB o efeito some sob a fala, e o pacote
      tem dois arquivos assim.

    Isto só é possível porque o áudio da composição NÃO precisa de remux. No
    renderizador antigo o remux existia para corrigir drift e descartava os
    efeitos junto,
    obrigando a reconstruir ~20 deles à mão no ffmpeg. Com drift zero medido,
    eles simplesmente ficam.
    """
    from sfx import probe

    warns, seen, planned = [], set(), []
    for at, kind in events:
        # A DEIXA PODE TRAZER O ARQUIVO DO USUÁRIO. O catálogo do repo é o
        # vocabulário comum; a biblioteca de quem edita (~/.avelin/sfx.json)
        # é dele, e obrigá-lo a virar `kind` no repo compartilhado seria pedir
        # que o gosto de um vire dependência de todos.
        if isinstance(kind, dict):
            spec = {"file": kind["file"], "volume": float(kind.get("volume", 0.3))}
        else:
            spec = VARIANTS["sfx"].get(kind)
        if not spec:
            continue
        f = proj / "sfx" / spec["file"]
        if not f.exists():
            nome = spec["file"]
            if nome not in seen:
                warns.append(f"  aviso: efeito '{nome}' não encontrado — deixa muda")
                seen.add(nome)
            continue
        info = probe(str(f))
        if info["quiet"] and spec["file"] not in seen:
            warns.append(f"  aviso: {spec['file']} tem pico de {info['peak']:.1f} dB "
                         f"— vai sumir sob a fala")
            seen.add(spec["file"])
        # Arredondado AQUI, não na hora de imprimir: a decisão de camada abaixo
        # compara os mesmos números que vão para o atributo, senão um valor que
        # arredonda para baixo cria no HTML uma sobreposição de menos de 1ms que
        # o check enxerga e esta função não.
        start = round(max(0.0, at - info["lead"]), 3)
        dur = round(min(info["duration"], duration - start), 3)
        if dur <= 0:
            continue
        planned.append((start, dur, spec))

    # Cada efeito na PRIMEIRA camada livre no seu instante. Ordenar por início é
    # o que torna a escolha gulosa correta — os eventos chegam fora de ordem
    # (a entrada do gráfico sob medida é acrescentada depois das transições).
    planned.sort(key=lambda p: p[0])
    free = [0.0] * len(SFX_LAYERS)      # quando cada camada volta a vagar
    blocks, eventos = [], []
    for i, (start, dur, spec) in enumerate(planned):
        lane = next((j for j, end in enumerate(free) if start >= end), None)
        if lane is None:
            warns.append(f"  aviso: '{spec['file']}' em {start:.2f}s não coube — "
                         f"as {len(SFX_LAYERS)} camadas de efeito já estão "
                         f"ocupadas nesse instante; foi descartado")
            continue
        free[lane] = start + dur
        blocks.append(
            f'  <audio id="sfx{i}" src="sfx/{spec["file"]}" data-start="{start:.3f}" '
            f'data-duration="{dur:.3f}" data-track-index="{SFX_LAYERS[lane]}" '
            f'data-volume="{spec["volume"]}"></audio>')
        eventos.append({"file": spec["file"], "start": round(start, 3),
                        "dur": round(dur, 3), "volume": spec["volume"],
                        "layer": lane, "track": SFX_LAYERS[lane]})
    # Publica os eventos como DADO. O editor não tem como saber quais efeitos
    # entraram — eles não estão no edit-data, nascem aqui, dos eventos visuais.
    # Sem este arquivo a linha do tempo mostra tudo menos o som, e o usuário não
    # tem onde conferir se o efeito caiu onde ele queria.
    (proj / "sfx-events.json").write_text(
        json.dumps(eventos, ensure_ascii=False, indent=1))
    return blocks, warns


def midia_largura(path: Path) -> int | None:
    """Largura NATIVA do arquivo, em pixels. `None` se não der para medir.

    Serve ao overlay para distinguir textura (cobre o quadro) de peça de
    interface (entra no tamanho dela). Vale para imagem e vídeo — o ffprobe lê
    PNG igual lê ProRes.
    """
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                            "-show_entries", "stream=width", "-of",
                            "default=nw=1:nk=1", str(path)],
                           capture_output=True, text=True, check=True)
        return int(r.stdout.strip().splitlines()[0])
    except (subprocess.CalledProcessError, ValueError, IndexError, OSError):
        return None


def video_duration(path: Path) -> float:
    """Duração do stream de VÍDEO, nunca do container nem do áudio decodificado.

    Medido no corte longform "Fome de Poder": vídeo 786.167s, mas o decode do
    áudio entrega 789.184s COM SINAL — 3s de som além do fim da imagem, sem o
    container refletir. Tirar a duração do áudio poria 3s de preto no fim.
    """
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=duration", "-of",
         "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def width_of(texts: list[str], st: dict) -> float:
    """Largura da frase no estilo, já com tracking e distorção horizontal.

    O `sx` entra na conta porque comprimir horizontalmente muda o agrupamento —
    glifo mais estreito, mais palavra por linha. O `sy` não entra: agrupamento
    se decide na largura.
    """
    t = " ".join(texts)
    w = measure(t, st["family"], st["size"], st["weight"])
    return (w + st.get("tracking", 0) * len(t)) * st.get("sx", 1)


def build_cues(words: list[dict], st: dict, budget: float) -> list[list[dict]]:
    """Agrupa palavras em deixas por LARGURA MEDIDA, com maxWords como teto.

    A referência chama isto de "o ponto inteiro" dos estilos estáticos, e vale
    para todos: "inteligência" e "de" não cabem na mesma regra, então contar
    palavras erra em toda palavra longa.
    """
    limit = budget * st.get("lines", 1)
    cues, cur = [], []
    for w in words:
        trial = cur + [w]
        if cur and (len(trial) > st["maxWords"]
                    or width_of([x["text"] for x in trial], st) > limit):
            cues.append(cur)
            cur = [w]
        else:
            cur = trial
    if cur:
        cues.append(cur)
    return cues


def cola_cues(words: list[dict], minimo: int) -> list[list[dict]]:
    """Deixas de UMA palavra, com as curtas grudadas na seguinte.

    É o agrupamento do rotativo. Uma palavra por deixa é o estilo; um artigo
    sozinho a 124px no meio do quadro é um defeito — a deixa dura o tempo de
    fala de "o", pisca, e lê como falha de render. Então palavra de até
    `minimo` letras não fecha grupo: ela viaja com a que vem depois.
    """
    out: list[list[dict]] = []
    cur: list[dict] = []
    for w in words:
        cur.append(w)
        if len(w["text"].strip(".,!?;:\u2014-")) > minimo:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def split_two_lines(cue: list[dict], st: dict, orphans: set[str],
                    penalty: float) -> list[list[dict]]:
    """Quebra a deixa em duas linhas: equilíbrio de largura, com pena por órfã.

    Equilíbrio puro termina linha em "de"/"que" o tempo todo, coisa que legenda
    de verdade nunca faz — daí a penalidade por acabar numa palavra funcional
    curta.
    """
    if st.get("lines", 1) != 2 or len(cue) < 2:
        return [cue]
    best, best_score = 1, float("inf")
    for i in range(1, len(cue)):
        left = width_of([x["text"] for x in cue[:i]], st)
        right = width_of([x["text"] for x in cue[i:]], st)
        score = abs(left - right)
        if cue[i - 1]["text"].strip(".,!?;:").lower() in orphans:
            score += penalty
        if score < best_score:
            best, best_score = i, score
    return [cue[:best], cue[best:]]


def time_cues(cues: list[list[dict]], fps: int, end_cap: float) -> list[dict]:
    out = []
    for i, c in enumerate(cues):
        start = c[0]["startMs"] / 1000
        natural = c[-1]["endMs"] / 1000 + HOLD
        # a deixa vive até a próxima começar, menos um frame — dois clipes vivos
        # na mesma trilha ao mesmo tempo é erro de render, não crossfade
        nxt = (cues[i + 1][0]["startMs"] / 1000 - 1 / fps
               if i + 1 < len(cues) else end_cap)
        end = min(natural, nxt, end_cap)
        if end > start:
            out.append({"start": start, "end": end, "cue": c})
    return out


def rgb_trio(hexa: str) -> str:
    """`#FF6B1A` -> `255 107 26`. Separado por ESPAÇO, que é a forma que
    `rgb(var(--x) / .5)` aceita: sem o trio, todo halo e toda chapa
    translúcida caem CALADOS — a cor não resolve e o CSS descarta a regra
    inteira sem erro nenhum, que é o pior modo de falhar.
    """
    h = (hexa or "").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return f"{int(h[0:2], 16)} {int(h[2:4], 16)} {int(h[4:6], 16)}"
    except (ValueError, IndexError):
        return "255 255 255"


def esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


@functools.lru_cache(maxsize=1)
def _local_catalog() -> tuple:
    """As fontes instaladas nesta máquina. Ver `helpers/local_fonts.py`."""
    try:
        import local_fonts
        return tuple(local_fonts.catalog())
    except Exception:
        return ()


def _gf(name: str) -> dict:
    """A família no catálogo de fontes — do Google OU da máquina.

    Os pesos DISPONÍVEIS andam junto porque a API do Google devolve ERRO (sem
    CSS nenhum) quando se pede um peso que a família não tem: uma fonte de peso
    único pedida em 900 derrubaria o carregamento inteiro e a headline sairia
    na fonte de sistema, com a largura toda errada. O mesmo vale para a fonte
    local, por outro motivo — pedir um corte que ela não tem faz a MEDIÇÃO
    escolher o vizinho e o navegador falsear o negrito, e aí os dois discordam.
    """
    for f in VARIANTS["gfonts"]:
        if f["n"] == name:
            return f
    for f in _local_catalog():
        if f["n"] == name:
            return f
    return VARIANTS["gfonts"][0]


def hl_weight_for(family: str, w: int) -> int:
    """O peso pedido grudado no que a família TEM — senão o navegador falseia o
    negrito, que suja o glifo e mede diferente do que desenha."""
    ws = _gf(family)["w"]
    return min(ws, key=lambda x: abs(x - w))


def hl_css_family(name: str) -> str:
    k = _gf(name)["k"]
    tail = "cursive" if k == "manuscrita" else "serif" if k == "serif" else "sans-serif"
    return f"'{name}', {tail}"


def hl_gfont_query(fams: list[str]) -> str:
    """O trecho de `family=` da folha do Google para as famílias usadas.

    Famílias EMPACOTADAS (com `file`) e LOCAIS (`k == "local"`) ficam de fora:
    elas não existem por esse caminho, e pedi-las devolve erro na folha
    INTEIRA — derrubando junto a família que existe. Medido: pedir a Gotham
    junto da Caveat matava também a Caveat, e a headline saía na fonte de
    sistema com a largura toda diferente da medida."""
    out = []
    for n in dict.fromkeys([f for f in fams if f]):
        f = _gf(n)
        if f.get("file") or f.get("k") == "local":
            continue
        ws = ";".join(str(x) for x in f["w"]) if len(f["w"]) > 1 else ""
        out.append(f"family={n.replace(' ', '+')}" + (f":wght@{ws}" if ws else ""))
    return "&".join(out)


def hl_fontface_css(fams: list[str]) -> str:
    """`@font-face` das famílias empacotadas.

    Sem isto o render dependeria de a fonte estar INSTALADA na máquina de quem
    renderiza — funcionaria aqui e falharia em qualquer outra, silenciosamente,
    caindo numa genérica com a largura toda diferente da que foi medida."""
    regras = []
    for n in dict.fromkeys([f for f in fams if f]):
        f = _gf(n)
        if not f.get("file"):
            continue
        regras.append(
            f"@font-face{{font-family:'{n}';src:url('styles/fonts/{f['file']}');"
            f"font-weight:{f['w'][0]};font-style:normal;font-display:block}}")
    return f"<style>{''.join(regras)}</style>" if regras else ""


def hl_shade(hex_color: str, amount: float, to_dark: bool) -> str:
    """A SEGUNDA parada do degradê, derivada da primeira.

    O degradê é regra do MODELO, não escolha do usuário: ele escolhe uma cor e o
    layout decide se o caminho é para o escuro ou para o claro. Pedir as duas
    pontas devolveria degradê sujo com o dobro de perguntas."""
    h = (hex_color or "#FFFFFF").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    f = (lambda c: round(c * (1 - amount))) if to_dark else (lambda c: round(c + (255 - c) * amount))
    return "#" + "".join(f"{f(c):02x}" for c in (r, g, b))


def hl_width(text: str, size: float, weight: int, family: str | None = None) -> float:
    if not text:
        return 0.0
    fam = family or VARIANTS["headlineFamily"]
    return measure(text, fam, size, weight) - 1.0 * len(text)  # letter-spacing -1px


def hl_lines(text: str, h: dict) -> list[str]:
    """A QUEBRA. O "/" MANDA; sem ele, equilibra por LARGURA medida.

    A barra é o controle de quem escreve: ela decide onde a frase respira E
    quantas linhas existem, que é o que destrava os layouts de três linhas e os
    de linha herói. Sem barra, o equilíbrio de duas linhas continua — por
    largura e não por contagem de palavras, porque "É assim que vai" e "ficar a
    sua headline" têm 4 e 3 palavras e quase a mesma largura.
    """
    t = (text or "").strip()
    if "/" in t:
        parts = [x.strip() for x in t.split("/") if x.strip()]
        if parts:
            return parts
    if h.get("quebra") == "encher":
        return hl_wrap(t, h)
    words = t.split()
    if len(words) < 2:
        return [words[0] if words else ""]
    best, best_diff = [words[0], " ".join(words[1:])], float("inf")
    for i in range(1, len(words)):
        a, b = " ".join(words[:i]), " ".join(words[i:])
        d = abs(hl_width(a, 100, h["weights"][0]) - hl_width(b, 100, h["weights"][1]))
        if d < best_diff:
            best, best_diff = [a, b], d
    return best


def hl_wrap(text: str, h: dict) -> list[str]:
    """Quebra ENCHENDO a largura — a quebra de uma manchete de verdade.

    O equilíbrio em duas linhas é o certo para uma frase curta de gancho e o
    errado para uma manchete: duas linhas longas fazem o `hl_fit` encolher o
    corpo até caber, e o resultado é uma manchete pequena num cartão grande. A
    manchete de jornal faz o contrário — mantém o corpo e usa quantas linhas
    precisar.

    A largura-alvo é medida em unidades de corpo 100, que é como o `hl_width`
    mede: uma linha que a `cap` desenharia com `safeW` de largura tem, no corpo
    100, `safeW * 100 / cap`. Enchendo até esse limite, o `hl_fit` depois
    devolve um corpo colado no teto em vez de encolhido.
    """
    alvo = h["safeW"] * 100.0 / max(1.0, float(h.get("cap") or 100))
    linhas: list[str] = []
    atual = ""
    for w in text.split():
        tent = f"{atual} {w}".strip()
        if atual and hl_width(tent, 100, h["weights"][0]) > alvo:
            linhas.append(atual)
            atual = w
        else:
            atual = tent
    if atual:
        linhas.append(atual)
    return linhas or [""]


def sobre_accent(accent: str) -> str:
    """A cor legível SOBRE a cor de destaque — branco, até o destaque clarear.

    A convenção da manchete é branco sobre a tarja colorida, e é o que o
    usuário reconhece; medir o contraste e escolher sempre o maior devolveria
    texto escuro sobre o vermelho, que é mais legível e não é uma manchete. A
    medição entra só para o caso em que o branco FALHA — um destaque amarelo ou
    creme, onde a razão de contraste cai abaixo de 3:1 e o rótulo some.
    """
    try:
        from backdrop_luma import hex_to_rgb, relative_luminance
        lum = relative_luminance(*hex_to_rgb(accent))
    except Exception:
        return "#ffffff"
    return "#ffffff" if 1.05 / (lum + 0.05) >= 3.0 else "#10202e"


def hl_is_upper(i: int, n: int, h: dict) -> bool:
    """CAIXA ALTA É DO CÓDIGO, NUNCA DO CSS.

    `text-transform` aplica DEPOIS da medição: mede-se a minúscula e desenha-se
    a maiúscula, que é mais larga — e a headline estoura o quadro sem erro
    nenhum. Foi o que aconteceu com o manuscrito e o gigante ao serem montados.
    """
    if h.get("upper"):
        return True
    ul = h.get("upperLines")
    if ul == "last":
        return i == n - 1
    if ul == "rest":
        return i > 0
    if isinstance(ul, list):
        return i in ul
    return False


def hl_ks(lines: list[str], h: dict) -> list[float]:
    """Multiplicador de corpo por linha; a última entrada vale para as extras."""
    sizes = h.get("sizes")
    if not sizes:
        return [1.0] * len(lines)
    return [float(sizes[min(i, len(sizes) - 1)]) for i in range(len(lines))]


def hl_line_weight(h: dict, i: int) -> int:
    w = h["weights"]
    return w[min(i, len(w) - 1)]


def hl_line_family(h: dict, i: int, fonts: dict) -> str:
    role = h.get("fontRole")
    if role and role[min(i, len(role) - 1)] == "accent":
        return fonts["accent"]
    return fonts["main"]


def hl_fit(lines: list[str], h: dict, fonts: dict) -> float:
    """Corpo que faz a linha mais larga caber em `safeW`, limitado por `cap`.

    `cap` é TETO, não medida fixa: uma headline curta pode chegar nele, uma
    longa tem que encolher. Duas passadas porque a largura não é perfeitamente
    linear no corpo — a primeira estima, a segunda corrige.

    A LINHA HERÓI sai desta conta: ela é medida sozinha contra a largura
    inteira, senão uma palavra curta ficaria pequena e uma longa puxaria todas
    as outras linhas para baixo junto com ela.
    """
    ks = hl_ks(lines, h)
    idx = [i for i in range(len(lines))
           if not (h.get("heroLast") and i == len(lines) - 1)] or list(range(len(lines)))

    def widest(size: float) -> float:
        return max(hl_width(lines[i], size * ks[i],
                            hl_weight_for(hl_line_family(h, i, fonts), hl_line_weight(h, i)),
                            hl_line_family(h, i, fonts)) for i in idx)

    size = h["safeW"] / max(1.0, widest(100)) * 100
    size = h["safeW"] / max(1.0, widest(size)) * size
    return max(VARIANTS["headlineMinSize"], min(size, h["cap"]))


def hl_hero_size(lines: list[str], h: dict, fonts: dict) -> float:
    i = len(lines) - 1
    fam = hl_line_family(h, i, fonts)
    w = hl_weight_for(fam, hl_line_weight(h, i))
    s = h["safeW"] / max(1.0, hl_width(lines[i], 100, w, fam)) * 100
    s = h["safeW"] / max(1.0, hl_width(lines[i], s, w, fam)) * s
    return min(s, h["cap"])


def cartela_slots(hook: dict, h: dict) -> dict:
    """De onde sai cada pedaço do texto que o usuário digitou.

    Uma cartela tem mais lugares que uma frase: sobrancelha, algarismo, grade
    de rótulos, assinatura. Pedir cinco campos ao usuário mataria o gancho
    rápido, então tudo sai do MESMO texto, pela barra que ele já usa para
    quebrar linha — a convenção que a `etiqueta` estreou lendo a primeira linha
    como rótulo. Aqui ela vira regra explícita (`slots` no variants.json):

        primeira     a primeira parte é a sobrancelha
        numero       a primeira parte, se for um algarismo, vira a figura
        traco        a parte que começa com travessão é a assinatura
        chave:valor  as partes com dois-pontos viram fileiras da grade

    O que sobra é o título. Nada é obrigatório: sem barra nenhuma o layout cai
    no bloco de linhas comum, que é o comportamento de todos os outros.
    """
    slots = h.get("slots") or {}
    bruto = [x for x in (hook.get("lines") or []) if x] or [hook.get("text") or ""]
    texto = " / ".join(x.strip() for x in bruto if x.strip())
    partes = [x.strip() for x in texto.split("/") if x.strip()] or [""]

    olho = numero = assin = None
    meta: list[tuple[str, str]] = []

    if slots.get("olho") == "primeira" and len(partes) > 1:
        olho = partes.pop(0)
    if slots.get("assinatura") == "traco":
        for i, x in enumerate(partes):
            if x[:1] in ("\u2014", "\u2013", "-") and len(partes) > 1:
                assin = partes.pop(i).lstrip("\u2014\u2013- ").strip()
                break
    if slots.get("meta") == "chave:valor":
        restam = []
        for x in partes:
            if ":" in x and len(partes) > 1:
                k, v = x.split(":", 1)
                meta.append((k.strip(), v.strip()))
            else:
                restam.append(x)
        partes = restam or [""]
    if slots.get("num") == "numero" and partes:
        m = re.match(r"^\s*(\d+[\d\u00ba\u00aa\u00b0%]*)\b[\s:.\u2014-]*(.*)$", partes[0])
        if m and m.group(1):
            numero = m.group(1)
            resto = m.group(2).strip()
            partes = ([resto] if resto else []) + partes[1:] or [""]

    return {"olho": olho, "num": numero, "assinatura": assin, "meta": meta,
            "titulo": " / ".join(x for x in partes if x)}


def cartela_markup(data: dict, hook: dict, h: dict, style_id: str, fonts: dict,
                   main_color: str, accent: str, end: float, top: float) -> tuple[str, str]:
    """Bloco da headline com motor `cartela` — slots, peças e movimento.

    A marcação é a mesma para os vinte layouts; o que muda é quais PEÇAS
    existem (`pecas` no variants.json) e o que cada uma pinta, que é da folha.
    """
    partes = cartela_slots(hook, h)
    # `linhaUnica`: a quebra automática é por LARGURA e sempre em duas — o que
    # está certo para um bloco de texto e errado para uma faixa que atravessa o
    # quadro. A barra do usuário continua valendo.
    linhas = ([partes["titulo"]] if h.get("linhaUnica") and "/" not in partes["titulo"]
              else hl_lines(partes["titulo"], h))
    linhas = [x for x in linhas if x] or [""]
    linhas = [x.upper() if hl_is_upper(i, len(linhas), h) else x
              for i, x in enumerate(linhas)]
    size = hl_fit(linhas, h, fonts)
    ks = hl_ks(linhas, h)
    pecas = h.get("pecas") or []
    pintura = (h.get("paint") or {}).get("lines")
    papeis = {"accent": "ct-acc", "sobre": "ct-escuro", "papelEscuro": "ct-escuro",
              "papel": "ct-claro", "serif": "ct-serif"}
    fr = h.get("fontRole") or []

    def linha(i: int, txt: str) -> str:
        cls = ["hl-line", "ct-anim"]
        if isinstance(pintura, list):
            cls.append(papeis.get(pintura[min(i, len(pintura) - 1)], ""))
        elif isinstance(pintura, str) and pintura in papeis:
            cls.append(papeis[pintura])
        if fr and fr[min(i, len(fr) - 1)] == "serif":
            cls.append("ct-serif")
        wgt = hl_weight_for(hl_line_family(h, i, fonts), hl_line_weight(h, i))
        fim = '<i class="ct-cursor"></i>' if ("cursor" in pecas and i == len(linhas) - 1) else ""
        return (f'<div class="{" ".join(c for c in cls if c)}" data-text="{esc(txt)}" '
                f'style="--hl-k:{ks[i]:.4f}; font-weight:{wgt}">{esc(txt)}{fim}</div>')

    corpo_linhas = '<div class="ct-linhas">' + "".join(
        linha(i, x) for i, x in enumerate(linhas)) + "</div>"

    olho = (f'<div class="ct-olho ct-anim">{esc(partes["olho"])}</div>'
            if partes["olho"] else "")
    numero = (f'<div class="ct-num ct-anim">{esc(partes["num"])}</div>'
              if partes["num"] else "")
    assin = (f'<div class="ct-assin ct-anim">{esc(partes["assinatura"])}</div>'
             if partes["assinatura"] else "")
    grade = ""
    if partes["meta"]:
        grade = "".join(
            f'<div class="ct-fila ct-anim"><span class="ct-k">{esc(k)}</span>'
            f'<span class="ct-v">{esc(v)}</span></div>' for k, v in partes["meta"])

    dentro = olho + numero + corpo_linhas + grade + assin
    # QUEM DESENHA O TEXTO É O SVG no knockout — a letra ali é um FURO na
    # chapa. Emitir o bloco também punha a mesma frase por cima, em branco
    # opaco, e o recorte sumia atrás dela.
    if "svg" in pecas:
        dentro = ""

    # AS PEÇAS. `ct-peca` marca o que se move como um corpo só na entrada —
    # sem ela, uma faixa que desliza deixaria o texto para trás.
    if "fita" in pecas:
        dentro = f'<div class="ct-faixa ct-peca">{corpo_linhas}</div>'
    elif "cartao" in pecas:
        dentro = f'<div class="ct-cartao ct-peca">{olho}{corpo_linhas}</div>'
    elif "painel" in pecas:
        pontos = '<div class="ct-pontos"><i></i><i></i><i></i></div>' if "pontos" in pecas else ""
        dentro = f'<div class="ct-painel ct-peca">{pontos}{corpo_linhas}</div>'
    elif "listras" in pecas:
        listra = '<div class="ct-listras"></div>'
        dentro = (f'<div class="ct-peca">{listra}'
                  f'<div class="ct-chapa">{corpo_linhas}</div>{listra}</div>')
    elif "balao" in pecas:
        rab = '<i class="ct-rabicho"></i>' if "rabicho" in pecas else ""
        dentro = f'<div class="ct-balao ct-peca">{corpo_linhas}{rab}</div>'
    elif "adesivo" in pecas:
        dentro = f'<div class="ct-adesivo ct-peca">{corpo_linhas}</div>'
    elif "reguas" in pecas:
        dentro = ('<i class="ct-regua"></i>' + corpo_linhas + '<i class="ct-regua"></i>')
    elif "noticia" in pecas:
        # O rótulo da barra fica no lugar mesmo VAZIO: ele é o que centraliza
        # entre o hambúrguer e a lupa, e sem o nó a barra fica torta quando o
        # usuário escreve a headline sem a primeira linha.
        rotulo = olho or '<div class="ct-olho"></div>'
        dentro = (f'<div class="ct-app ct-peca">'
                  f'<div class="ct-barra"><i class="ct-menu"></i>{rotulo}'
                  f'<i class="ct-lupa"></i></div>'
                  f'<div class="ct-folha">{corpo_linhas}</div></div>')

    fora = ""
    if h.get("cheia") and "svg" not in pecas and "blur" not in pecas:
        fora += '<i class="ct-fundo"></i>'
    if "blur" in pecas:
        fora += '<i class="ct-blur"></i>'
    if "vinheta" in pecas:
        fora += '<i class="ct-vinheta"></i>'
    if "aspa" in pecas:
        fora += '<div class="ct-aspa">\u201c</div>'
    if "svg" in pecas:
        fora += cartela_svg(linhas, size, h, fonts)

    deep = data.get("deep") or "#0D2137"
    mo = json.dumps(h.get("motion") or {}, separators=(",", ":"))
    cheia = " cheia" if h.get("cheia") else ""
    bloco = (f'  <div id="hook" class="ave-cartela ct-{style_id}{cheia} clip" '
             f'data-start="0" data-duration="{end:.3f}" '
             f'data-track-index="{TRACK["hook"]}" '
             f'style="--hl-scale:1; --hl-size:{size:.2f}; --hl-lh:{h["lh"]}; '
             f'--hl-top:{top}; --hl-main:{main_color}; --hl-accent:{accent}; '
             f'--hl-accent-rgb:{rgb_trio(accent)}; --hl-deep:{deep}; '
             f'--hl-sobre-accent:{sobre_accent(accent)}; '
             f'--hl-stroke:{h.get("stroke", 0)}; '
             f'--hl-font:{hl_css_family(fonts["main"])}; '
             f'--hl-font-accent:{hl_css_family(fonts["accent"])}"'
             f" data-motion='{mo}'>"
             f'{fora}<div class="ct-bloco">{dentro}</div></div>')
    css = ('<link rel="stylesheet" href="styles/cartela.css">\n'
           '<script src="styles/cartela.js"></script>'
           + hl_fontface_css([fonts["main"], fonts["accent"]]))
    return bloco, css


def cartela_svg(linhas: list[str], size: float, h: dict, fonts: dict) -> str:
    """O recorte do knockout: uma MÁSCARA, não um clip de texto.

    O furo tem de ser no FUNDO — a chapa é que fica com buracos em forma de
    letra, e o vídeo aparece por eles. `background-clip: text` faz o contrário
    (preenche a letra com uma imagem) e não serve. Máscara SVG: branco mostra,
    preto esconde; a letra vai preta.
    """
    fam = hl_css_family(fonts["main"]).split(",")[0].strip("'\"")
    lh = float(h["lh"])
    alt = len(linhas) * size * lh
    y0 = 960 - alt / 2 + size * 0.78
    tspans = "".join(
        f'<tspan x="540" y="{y0 + i * size * lh:.1f}">{esc(x)}</tspan>'
        for i, x in enumerate(linhas))
    return (
        '<svg class="ct-svg" viewBox="0 0 1080 1920" preserveAspectRatio="none">'
        '<defs><mask id="ct-ko" maskUnits="userSpaceOnUse" x="0" y="0" width="1080" height="1920">'
        '<rect width="1080" height="1920" fill="#fff"/>'
        f'<text text-anchor="middle" font-family="{esc(fam)}" font-size="{size:.1f}" '
        f'font-weight="{h["weights"][0]}" letter-spacing="-2" fill="#000">{tspans}</text>'
        '</mask></defs>'
        '<rect width="1080" height="1920" style="fill:var(--hl-deep)" mask="url(#ct-ko)"/>'
        '</svg>')


def hook_markup(data: dict, accent: str, splits: list[dict] | None = None) -> tuple[str, str]:
    """(markup, css_extra) do hook. Bloco próprio, id estável, tempo próprio."""
    hook = data.get("hook", {})
    if not hook.get("enabled"):
        return "", ""
    style_id = hook.get("style", "card")
    h = VARIANTS["headlines"].get(style_id)
    if h is None:
        raise SystemExit(f"estilo de headline '{style_id}' não existe. "
                         f"Prontos: {', '.join(VARIANTS['headlines'])}")

    fonts = {
        "main": hook.get("fontMain") or VARIANTS["headlineFamily"],
        "accent": hook.get("fontAccent") or VARIANTS["headlineAccentFamily"],
    }
    main_color = hook.get("color") or "#FFFFFF"

    raw = [l for l in (hook.get("lines") or []) if l]
    # Uma linha só, ou um `text` corrido: a quebra é resolvida aqui — e o "/"
    # do usuário manda sobre o equilíbrio automático.
    if len(raw) <= 1:
        raw = hl_lines(raw[0] if raw else (hook.get("text") or ""), h)
    raw = [l for l in raw if l]
    if not raw:
        return "", ""
    raw = [l.upper() if hl_is_upper(i, len(raw), h) else l for i, l in enumerate(raw)]

    size = hl_fit(raw, h, fonts)
    ks = hl_ks(raw, h)
    if h.get("heroLast"):
        ks[-1] = hl_hero_size(raw, h, fonts) / size
    end = float(hook.get("endSec", 4.0))

    # O gancho NÃO transfere de graça para a tela dividida: a altura padrão o
    # põe DEBAIXO da arte (o linter acusa "texto escondido sob elemento
    # opaco"). Cada layout tem a sua — 738 no `top`, onde o texto senta na
    # costura sob a arte; ~920 no `bottom`, no vão entre o queixo e a costura.
    top = h["top"]
    for w in (splits or []):
        if w["start"] < end and w["end"] > 0:
            top = VARIANTS["split"][w["layout"]]["hookTop"]
            break

    # As headlines com motor `cartela` (as vinte novas) saem por outro caminho:
    # elas têm SLOTS e MOVIMENTO, e forçá-las no bloco de linhas antigo seria
    # perder as duas coisas. Os layouts antigos não têm `motor` e seguem aqui.
    if h.get("motor") == "cartela":
        return cartela_markup(data, hook, h, style_id, fonts, main_color,
                              accent, end, top)

    paint = h.get("paint") or {}
    out = []
    for i, l in enumerate(raw):
        cls = ["hl-line"]
        if paint.get("tagBox") is not None and i == (paint.get("tag") or 0):
            cls.append("hl-tag")
        if paint.get("hollowLines") and i in paint["hollowLines"]:
            cls.append("hl-hollow")
        wgt = hl_weight_for(hl_line_family(h, i, fonts), hl_line_weight(h, i))
        if paint.get("wordBox"):
            # sem espaço entre as tarjas: o espaço ficaria DENTRO da tarja e as
            # caixas se encostariam. A folga é a margem do .hl-word.
            inner = "".join(f'<span class="hl-word">{esc(w)}</span>' for w in l.split())
        else:
            inner = esc(l)
        out.append(
            f'<div class="{" ".join(cls)}" data-text="{esc(l)}" '
            f'style="--hl-k:{ks[i]:.4f}; font-weight:{wgt}">{inner}</div>')

    grad = h.get("gradient")
    extra = ""
    if grad:
        dark = grad.get("to") == "dark"
        amt = float(grad.get("amount", 0.35))
        extra = (f' --hl-main-2:{hl_shade(main_color, amt, dark)};'
                 f' --hl-accent-2:{hl_shade(accent, amt, dark)};')

    block = (f'  <div id="hook" class="ave-hook {style_id} clip" data-start="0" '
             f'data-duration="{end:.3f}" data-track-index="{TRACK['hook']}" '
             f'style="--hl-scale:1; --hl-size:{size:.2f}; --hl-lh:{h["lh"]}; '
             f'--hl-top:{top}; --hl-main:{main_color}; --hl-accent:{accent}; '
             f'--hl-font:{hl_css_family(fonts["main"])}; '
             f'--hl-font-accent:{hl_css_family(fonts["accent"])}; '
             f'--hl-stroke:{h["stroke"]};{extra}">'
             f'{"".join(out)}</div>')
    css = ('<link rel="stylesheet" href="styles/headline.css">'
           + hl_fontface_css([fonts["main"], fonts["accent"]]))
    return block, css


def markup(timed: list[dict], st: dict, style_id: str, orphans, penalty,
           splits: list[dict] | None = None) -> str:
    blocks = []
    for t in timed:
        # A legenda DESVIA para a costura enquanto a tela dividida está no ar.
        # Sem isso ela fica na posição de quadro cheio, que na tela dividida cai
        # sobre o corpo em vez de na costura. O desvio é por deixa, não global:
        # só as que caem dentro da janela se movem.
        dodge = ""
        for w in (splits or []):
            if t["start"] < w["end"] and t["end"] > w["start"]:
                dodge = f' style="bottom:{w["captionBottom"]}px"'
                break
        attrs = (f'data-start="{t["start"]:.3f}" '
                 f'data-duration="{t["end"] - t["start"]:.3f}" data-track-index="{TRACK["caption"]}"')
        if st["animated"]:
            spans = "".join(f"<span>{esc(w['text'])}</span>" for w in t["cue"])
            blocks.append(f'<div class="ave-cap-line clip" {attrs}{dodge}>{spans}</div>')
        else:
            lines = split_two_lines(t["cue"], st, orphans, penalty)
            inner = "".join(
                f'<div>{esc(" ".join(w["text"] for w in ln))}</div>' for ln in lines)
            blocks.append(f'<div class="ave-cue clip" {attrs}{dodge}>{inner}</div>')
    return "\n".join("    " + b for b in blocks)


def palavra_markup(timed: list[dict], st: dict, orphans, penalty,
                   splits: list[dict] | None = None) -> str:
    """Deixas do motor PALAVRA: um clipe por deixa, e cada palavra com o seu
    instante de fala (`data-at` absoluto) e a duração medida (`data-dur`).

    A marcação é a mesma para os dezenove estilos — o que muda entre eles é o
    que cada estado pinta, e isso vive no `pal` do variants.json, não aqui.
    Os únicos nós a mais são os que uma animação exige ter no DOM: o traço do
    marca-texto e o cursor da máquina não se animam por pseudo-elemento.
    """
    pal = st.get("pal") or {}
    blocks = []
    anterior: list[dict] = []
    for t in timed:
        dodge = ""
        for w in (splits or []):
            if t["start"] < w["end"] and t["end"] > w["start"]:
                dodge = f' style="bottom:{w["captionBottom"]}px"'
                break

        # o DESTAQUE de uma legenda comum sai do comprimento, como no disperso:
        # transcrição não traz papéis, e inventar um por posição destacaria uma
        # preposição em toda deixa
        hi = -1
        if pal.get("destaque") == "maisLonga":
            corte = pal.get("destaqueMin", 6) - 1
            for i, w in enumerate(t["cue"]):
                if len(w["text"].strip(".,!?;:")) > corte:
                    hi, corte = i, len(w["text"].strip(".,!?;:"))

        def span(w: dict, idx: int) -> str:
            extra = ""
            if pal.get("grifo"):
                extra += '<i class="pal-grifo"></i>'
            if pal.get("cursor"):
                extra += '<i class="pal-cursor"></i>'
            cls = "pal-w pal-hi" if idx == hi else "pal-w"
            dur = max(0.08, (w.get("endMs", w["startMs"]) - w["startMs"]) / 1000)
            return (f'<span class="{cls}" data-at="{w["startMs"] / 1000:.3f}" '
                    f'data-dur="{dur:.3f}">{esc(w["text"])}{extra}</span>')

        linhas = []
        # A ROLAGEM redesenha a deixa ANTERIOR dentro do clipe atual, apagada.
        # Deixar a anterior viva entre clipes poria dois clipes na mesma pista
        # ao mesmo tempo, que é erro de render — e o efeito de teleprompter não
        # precisa disso: precisa que a linha de cima ESTEJA ali, não que seja a
        # mesma caixa de antes.
        if pal.get("rola") and anterior:
            linhas.append('<div class="pal-line pal-antiga">'
                          + "".join(f'<span class="pal-w">{esc(w["text"])}</span>'
                                    for w in anterior) + "</div>")
        idx = 0
        for ln in split_two_lines(t["cue"], st, orphans, penalty):
            linhas.append('<div class="pal-line">'
                          + "".join(span(w, idx + k) for k, w in enumerate(ln))
                          + "</div>")
            idx += len(ln)
        corpo = "".join(linhas)
        if pal.get("rola"):
            corpo = f'<div class="pal-rolo">{corpo}</div>'
        # a placa do vidro envolve o BLOCO: uma por linha vira duas placas
        # desencontradas, que é o oposto do efeito
        if pal.get("placa"):
            corpo = f'<div class="pal-placa">{corpo}</div>'
        if pal.get("filete"):
            corpo = '<i class="pal-filete"></i>' + corpo
        if pal.get("tarja"):
            corpo = '<i class="pal-tarja"></i>' + corpo
        anterior = t["cue"]

        blocks.append(
            f'    <div class="pal-cue clip" data-start="{t["start"]:.3f}" '
            f'data-duration="{t["end"] - t["start"]:.3f}" '
            f'data-track-index="{TRACK["caption"]}"{dodge}>{corpo}</div>')
    return "\n".join(blocks)


def tracking_path(data, W, H, duration, track_file: Path, step: int = 3):
    """Caminho (t, tx, ty, escala) da câmera COM perseguição do olhar.

    Zoom e perseguição são UMA conta, não duas animações. A translação depende
    do ponto do rosto E do zoom daquele instante:

        tx = alvoX*W − cx*W*S        ty = alvoY*H − cy*H*S

    e é LIMITADA para nunca revelar borda — sem a trava o quadro sai do vídeo e
    entra preto, que é o defeito clássico de um follow solto.

    Amostrado a cada `step` quadros porque o caminho já vem suavizado do
    rastreador. Em cada corte são forçados dois pontos no mesmo instante, para
    o salto de zoom continuar seco em vez de deslizar entre tomadas.
    """
    if not track_file.exists():
        return [], "rastreio de rosto ausente — rode helpers/face_track.py"
    tk = json.loads(track_file.read_text())
    pts = tk.get("points") or []
    if not pts:
        return [], "rastreio de rosto vazio"

    cam = data.get("camera", {}) or {}
    d = VARIANTS["camera"]
    zooms = cam.get("zooms") or d["zooms"]
    push = cam.get("pushIn", d["pushIn"])
    tgt_x, tgt_y = cam.get("targetX", d["targetX"]), cam.get("targetY", d["targetY"])
    fps = data.get("fps", 30)
    segs = data.get("_segments") or [{"start": 0.0, "end": duration}]

    def state(t):
        i = max(0, sum(1 for s in segs if s["start"] <= t) - 1)
        seg = segs[min(i, len(segs) - 1)]
        span = max(1e-6, seg["end"] - seg["start"])
        S = zooms[i % len(zooms)] + push * min(1.0, max(0.0, (t - seg["start"]) / span))
        cx, cy = pts[min(int(round(t * fps)), len(pts) - 1)]
        tx = tgt_x * W - cx * W * S
        ty = tgt_y * H - cy * H * S
        tx = min(0.0, max(W - W * S, tx))   # nunca revelar borda
        ty = min(0.0, max(H - H * S, ty))
        return round(tx, 2), round(ty, 2), round(S, 4)

    bounds = sorted({round(s["start"], 3) for s in segs if 0 < s["start"] < duration})
    path, t, k = [], 0.0, step / fps
    while t < duration:
        path.append((round(t, 3),) + state(t))
        nxt = t + k
        for b in bounds:
            if t < b < nxt:
                path.append((round(b - 1 / fps, 3),) + state(b - 1 / fps))
                path.append((round(b, 3),) + state(b))
        t = nxt
    path.append((round(duration, 3),) + state(max(0.0, duration - 1e-3)))
    return path, ""


def camera_parts(data, duration):
    """(js da timeline, estilo do a-roll, blocos de flash).

    A câmera é um item da aba Estilo com três partes separáveis. `zoomCuts` é o
    que faz um plano fixo parecer editado — sem ele o vídeo é uma câmera parada
    por um minuto. Se o usuário desligar tudo, vale dizer o que ele perde.

    `tracking` (perseguição do olhar) ainda NÃO está portado: ele depende do
    rastreio de rosto quadro a quadro, que é outro dado. Ligado sem esse dado,
    seria inventar movimento — então ele é ignorado com aviso, não fingido.
    """
    cam = data.get("camera", {}) or {}
    els = data.get("elements", {}) or {}
    defaults = VARIANTS["camera"]
    segs = data.get("_segments") or []
    off = bool(data.get("_camOff"))
    zoom_cuts = bool(els.get("zoomCuts", True)) and bool(segs) and not off
    zoom_auto = bool(els.get("zoomAuto", True)) and bool(segs) and not off

    js, style, blocks = "", "", []
    if cam.get("enabled", True) and (zoom_cuts or zoom_auto):
        tx = cam.get("targetX", defaults["targetX"]) * 100
        ty = cam.get("targetY", defaults["targetY"]) * 100
        style = f"transform-origin:{tx:.1f}% {ty:.1f}%;"
        opts = {
            "segments": segs,
            "zooms": cam.get("zooms") or defaults["zooms"],
            "pushIn": cam.get("pushIn", defaults["pushIn"]),
            "zoomCuts": zoom_cuts,
            "zoomAuto": zoom_auto,
        }
        js = ("  AVE_CAMERA.buildCamera(document.getElementById('a-roll'), gsap, tl, "
              + json.dumps(opts) + ");")

    fps = data.get("fps", 30)
    W = data.get("width", 1080)
    fl = VARIANTS["flash"]
    for k, tr in enumerate(data.get("transitions") or []):
        at = float(tr.get("at", 0))
        if at >= duration:
            continue
        start = max(0.0, at - fl["durationFrames"] / fps)
        dur = (fl["durationFrames"] * 2) / fps
        blocks.append(
            f'  <div id="flash{k}" class="ave-flash clip" data-start="{start:.3f}" '
            f'data-duration="{min(dur, duration - start):.3f}" data-track-index="{TRACK['flash']}" '
            f'style="--flash-intensity:{tr.get("intensity", fl["intensity"])}; '
            f'--flash-blur:{fl["blur"]}"></div>'
        )
        # A varredura em PIXELS da composição, não em `xPercent`: o percentual
        # é da largura do elemento (150px) e nunca daria a travessia. Sai de
        # fora da borda esquerda e termina fora da direita, com folga para o
        # desfoque não entregar a borda dura do retângulo.
        folga = 220
        js += (f"\n  tl.fromTo('#flash{k}', {{x:{-folga}}}, "
               f"{{x:{W + folga}, duration:{dur:.3f}, ease:'power1.inOut'}}, "
               f"{start:.3f});")
        # O brilho SOBE e DESCE. Antes ia de 0 a 1 ao longo de toda a
        # travessia: o feixe ficava mais forte justamente ao sair de cena e
        # então era cortado no pico, quando o clipe acabava — o contrário de
        # um flash, que estoura no meio e se apaga.
        js += (f"\n  tl.to('#flash{k}', {{opacity:1, duration:{dur / 2:.3f}, "
               f"ease:'power2.out'}}, {start:.3f});")
        js += (f"\n  tl.to('#flash{k}', {{opacity:0, duration:{dur / 2:.3f}, "
               f"ease:'power2.in'}}, {start + dur / 2:.3f});")
        # Trava dura no fim. O render não toca a linha do tempo, ele BUSCA
        # quadro a quadro — e uma busca que caia depois do fade pode não ter
        # passado por ele, deixando o feixe aceso preso na tela. O `check`
        # barra por isso quando a saída termina em borda de clipe, que é
        # exatamente onde um flash de transição sempre termina.
        js += (f"\n  tl.set('#flash{k}', {{opacity:0}}, {start + dur:.3f});")
    return js, style, blocks


def render_html(data, timed, st, style_id, video, duration, orphans, penalty, vdur=None) -> str:
    vdur = duration if vdur is None else vdur
    accent = data.get("accent") or "#FF6B1A"
    # A COR DO TEXTO tambem e escolha, nao constante. Ficava branca fixa no
    # CSS: o usuario podia escolher o destaque e nao a fonte, o que e metade
    # de um controle de cor. `captions.color` fecha o par.
    cap_color = (data.get("captions") or {}).get("color") or "#FFFFFF"
    W, H = data.get("width", 1080), data.get("height", 1920)
    cfg = data.get("captions", {})
    bottom = cfg.get("paddingBottom", VARIANTS["bottom"])
    size = cfg.get("fontSize") or st["size"]
    # Eventos de efeito: cada um no instante em que a coisa acontece.
    events = []
    if data.get("hook", {}).get("enabled"):
        events.append((0.0, "hook"))
    for tr in (data.get("transitions") or []):
        at = float(tr.get("at", 0))
        if at < duration:
            events.append((at, "flash"))
    for c in (data.get("_soloCues") or []):
        events.append(c)
    # Deixas escritas à mão — o único canal para um som que NÃO nasce de um
    # evento visual. Todos os outros são consequência de algo que aparece
    # (o cartão entrou, o corte piscou, a palavra saltou), e há efeitos que
    # existem justamente onde nada aparece: o riser que resolve na virada do
    # gancho, a trava da roleta. No empilhado nem dava para contrabandear pelo
    # `_soloCues` — a legenda o REESCREVE, então uma deixa posta lá some sem
    # aviso no próximo compose. Aditivo: sem a chave, nada muda.
    # `at` é o instante do ATAQUE, como no resto — a compensação do silêncio
    # inicial do arquivo continua sendo medida em sfx_blocks.
    for c in (data.get("sfxCues") or []):
        at = float(c.get("at", 0))
        if at >= duration:
            continue
        if c.get("file"):
            events.append((at, {"file": c["file"], "volume": c.get("volume", 0.3)}))
        elif c.get("kind"):
            events.append((at, c["kind"]))

    # Perseguição do olhar: quando ligada, ela ABSORVE o zoom — o caminho já
    # traz a escala de cada instante. Deixar a câmera também animando `scale`
    # faria duas fontes disputarem o mesmo transform.
    track_js, track_warn = "", ""
    els = data.get("elements") or {}
    if els.get("tracking") and not data.get("splitInserts"):
        tk = Path(data.get("_proj", ".")) / "track.json"
        path, track_warn = tracking_path(data, W, H, duration, tk)
        if path:
            track_js = ("  AVE_TRACKING.buildTimeline(document.getElementById('a-roll'), "
                        "gsap, tl, " + json.dumps(path) + ");")
            data = {**data, "_camOff": True}
    elif els.get("tracking"):
        track_warn = "perseguição do olhar ignorada: a tela dividida fixa o rosto por conta própria"
    if track_warn:
        print(f"  aviso: {track_warn}", file=sys.stderr)

    splits = split_windows(data, H, duration)
    hook_accent = accent
    hk = data.get("hook") or {}
    # A cartela de TELA CHEIA não mede o vídeo: o fundo dela é a chapa da marca,
    # de cor conhecida, e o contraste ali é por construção. Medir a luminância
    # do vídeo atrás de uma chapa opaca escolheria a cor pelo que ninguém vê.
    _hkv = VARIANTS["headlines"].get(hk.get("style", "card"), {})
    if hk.get("enabled") and _hkv.get("usesAccent") and not _hkv.get("cheia"):
        hv = Path(data.get("_proj", ".")) / data.get("_video", "preview.mp4")
        htop = VARIANTS["headlines"][hk["style"]]["top"] / H
        hook_accent = adaptive_accent(hv, accent, max(0.0, htop - 0.01), 0.14,
                                      [(0.0, float(hk.get("endSec", 4.0)))])[0]
    hook_block, hook_css = hook_markup(data, hook_accent, splits)
    # A câmera é DESLIGADA enquanto a tela dividida está no ar: ela move o
    # quadro, e o efeito da tela dividida é justamente o rosto ficar parado
    # numa região fixa. As duas juntas brigam pelo mesmo transform.
    if splits:
        data = {**data, "_camOff": True}
    cam_js, cam_style, flash_blocks = camera_parts(data, duration)

    # A FAMÍLIA ESCOLHIDA NA ABA ESTILO, com o padrão sendo a do próprio
    # estilo. Vazio aqui não é "sem fonte": é "a de fábrica", e por isso a
    # variável só é emitida quando alguém escolheu — assim trocar de estilo
    # continua trazendo a letra com que ele foi desenhado.
    cap_fam = cfg.get("fontMain")
    fam_var = f" --cap-family:{hl_css_family(cap_fam)};" if cap_fam else ""

    # O MOTION KIT dos Broll Overlays (helpers/motion_kit.py): o do usuário
    # (~/.avelin/motion/kit.json) quando existe, senão o default do repo, com
    # a marca resolvida por cima. As fontes DELE entram na folha do Google via
    # `gfontQuery` do próprio kit — a consulta viaja no dado, nunca fixa aqui.
    bo_kit: dict = {}
    if data.get("brollOverlays"):
        from motion_kit import carregar_kit
        bo_kit = carregar_kit()

    gfont = st["gfont"]
    if bo_kit:
        bq = (bo_kit.get("fontes") or {}).get("gfontQuery")
        if bq:
            gfont = f"{gfont}&{bq}"
    # As famílias da LEGENDA entram na mesma folha. Sem isto, escolher uma
    # fonte na aba renderizava com a de fábrica — o CSS pedia a nova, o
    # navegador não a tinha, e caía numa genérica sem erro visível.
    q_cap = hl_gfont_query([cap_fam] if cap_fam else [])
    if q_cap:
        gfont = f"{gfont}&{q_cap}"
    cap_face = hl_fontface_css([cap_fam] if cap_fam else [])
    if cap_face:
        cap_css = f"{cap_css}\n{cap_face}"
    if hook_block:
        # AS FAMÍLIAS ESCOLHIDAS, montadas a partir do dado — nunca uma consulta
        # fixa. Com a consulta fixa, trocar a fonte no editor renderizaria com a
        # antiga: a folha do Google traria Poppins, o CSS pediria a nova, e o
        # texto cairia numa genérica sem erro visível em lugar nenhum.
        hk = data.get("hook") or {}
        q = hl_gfont_query([
            hk.get("fontMain") or VARIANTS["headlineFamily"],
            hk.get("fontAccent") or VARIANTS["headlineAccentFamily"],
        ])
        # A consulta sai VAZIA quando as duas famílias são locais/empacotadas —
        # e um `&` solto no fim da URL faz o Google recusar a folha inteira,
        # levando junto a fonte da LEGENDA, que não tem nada a ver com isso.
        if q:
            gfont = f"{gfont}&{q}"

    if style_id == "stacked":
        cap_css = ('<link rel="stylesheet" href="styles/stacked.css">\n'
                   '<script src="styles/stacked.js"></script>')
        # o DESTAQUE sai do accent escolhido, nao do `orange` da variante: o
        # controle de cor da aba Estilo nao pode valer para uns estilos e nao
        # para outros. O CORPO sai de captions.color.
        container = (f'<div class="ave-stacked" style="--stk-scale:1;'
                     f' --stk-offset-y:{cfg.get("stackedOffsetY", cfg.get("offsetY", st["offsetY"]))};'
                     f' --stk-color:{cap_color};'
                     + (f' --stk-family:{hl_css_family(cap_fam)};' if cap_fam else "")
                     + f' --stk-orange:{accent or st["orange"]}">')
    elif style_id == "scatter":
        cap_css = ('<link rel="stylesheet" href="styles/scatter.css">\n'
                   '<script src="styles/scatter.js"></script>')
        container = (f'<div class="ave-scatter" style="--scat-scale:1;'
                     f' --scat-size:{size}; --scat-gap:{st["gap"]};'
                     f' --scat-offset-y:{cfg.get("scatterOffsetY", cfg.get("offsetY", st["offsetY"]))}">')
    elif style_id == "editorial":
        cap_css = ('<link rel="stylesheet" href="styles/editorial.css">\n'
                   '<script src="styles/editorial.js"></script>')
        # os números do movimento viajam no dado (variants.styles.editorial.motion)
        mo_attr = json.dumps(st.get("motion") or {}, separators=(",", ":"))
        container = (f'<div class="ave-edt" style="--cap-scale:1;{fam_var}'
                     f' --cap-accent:{accent or "#ff3b30"}; --cap-size:{st["size"]}px;'
                     f' --edt-top:{cfg.get("offsetY", st.get("offsetY", 0.5)) * 100:.1f}%;'
                     f' --edt-left:{st.get("safeLeftPx", 90)}px;'
                     f' --edt-lh:{st.get("lineHeight", 1.0)};'
                     f' --edt-serif:{st.get("serifFamily", "serif")}"'
                     f" data-motion='{mo_attr}'>")
    elif style_id == "dinamico":
        cap_css = ('<link rel="stylesheet" href="styles/dinamico.css">\n'
                   '<script src="styles/dinamico.js"></script>')
        # os números do movimento viajam no dado (variants.styles.dinamico.motion)
        mo_attr = json.dumps(st.get("motion") or {}, separators=(",", ":"))
        container = (f'<div class="ave-din" style="--cap-scale:1;{fam_var}'
                     f' --cap-accent:{accent or "#ff3b30"}; --cap-size:{st["size"]}px;'
                     f' --din-top:{cfg.get("offsetY", st.get("offsetY", 0.47)) * 100:.1f}%;'
                     f' --din-lh:{st.get("lineHeight", 1.0)};'
                     f' --din-dim:{st.get("dimColor", "#8F8F8F")};'
                     f' --din-fig-shrink:{st.get("figShrink", 0.85)};'
                     f' --din-serif:{st.get("serifFamily", "serif")}"'
                     f" data-motion='{mo_attr}'>")
    elif st.get("css") == "palavra":
        cap_css = ('<link rel="stylesheet" href="styles/palavra.css">\n'
                   '<script src="styles/palavra.js"></script>')
        pal = st.get("pal") or {}
        # a GEOMETRIA é do estilo (o cinema senta a 230px do fundo, a barra a
        # 360): o padrão global só vale para quem não declara o seu
        pal_bottom = cfg.get("paddingBottom", st.get("bottom", VARIANTS["bottom"]))
        # As variáveis do `pal` (raio da tarja, margem esquerda, placa do vidro)
        # são aplicadas pelo MOTOR a partir do `data-pal`, não traduzidas aqui:
        # o mesmo mapa em Python e em JS divergiria no primeiro ajuste.
        # A FAIXA SEGURA vence a posição de fábrica também nos estilos de bloco
        # central (o rotativo). Entra pelo próprio `pal`, e não como variável
        # solta no `style`: quem traduz `pal` em variáveis de CSS é o motor, e
        # uma variável escrita aqui seria sobrescrita por ele no primeiro
        # quadro — em silêncio.
        if pal.get("centro") is not None and cfg.get("offsetY") is not None:
            pal = {**pal, "centro": cfg["offsetY"]}
        pal_attr = json.dumps(pal, separators=(",", ":"))
        mo_attr = json.dumps(st.get("motion") or {}, separators=(",", ":"))
        # a FAMÍLIA sempre desce: são dezenove estilos sobre uma folha só, e o
        # padrão dela não pode ser o de um deles. `fam_var` (a escolha do
        # usuário) vem depois e vence.
        container = (f'<div class="ave-pal pal-{style_id}" style="--cap-scale:1;'
                     f' --cap-family:{st["cssFamily"]};{fam_var}'
                     f' --cap-color:{cap_color}; --cap-color-rgb:{rgb_trio(cap_color)};'
                     f' --cap-accent:{accent or "#ff6b1a"};'
                     f' --cap-accent-rgb:{rgb_trio(accent or "#ff6b1a")};'
                     f' --cap-size:{st["size"]}; --cap-bottom:{pal_bottom};'
                     f' --cap-weight:{st.get("weight", 600)};'
                     f' --cap-track:{st.get("tracking", 0)};'
                     f' --cap-lh:{st.get("lineHeight", 1.26)};"'
                     f" data-pal='{pal_attr}' data-motion='{mo_attr}'>")
    elif st.get("css") == "pop":
        # Os TRÊS estilos de estouro compartilham a folha e o script: a curva é
        # a mesma (medida do CapCut, idêntica byte a byte entre eles) e o que
        # muda é o AGRUPAMENTO, que vai como classe.
        cap_css = ('<link rel="stylesheet" href="styles/pop.css">\n'
                   '<script src="styles/pop.js"></script>')
        container = (f'<div class="ave-pop grupo-{st.get("grupo", "palavra")}"'
                     f' style="--cap-scale:1;{fam_var} --cap-color:{cap_color};'
                     f' --cap-accent:{accent or "#ff3b30"};'
                     f' --cap-size:{size}; --cap-bottom:{bottom}">')
    elif st.get("css") == "revelar":
        cap_css = ('<link rel="stylesheet" href="styles/revelar.css">\n'
                   '<script src="styles/revelar.js"></script>')
        container = (f'<div class="ave-rev" style="--cap-scale:1;{fam_var}'
                     f' --cap-color:{cap_color}; --cap-accent:{accent or "#ff3b30"};'
                     f' --cap-size:{size}; --cap-bottom:{bottom}">')
    elif st["animated"]:
        cap_css = ('<link rel="stylesheet" href="styles/karaoke.css">\n'
                   '<script src="styles/karaoke.js"></script>')
        container = (f'<div class="ave-cap {style_id}" style="--cap-scale:1;{fam_var}'
                     f' --cap-color:{cap_color};'
                     f' --cap-size:{size}; --cap-bottom:{bottom}">')
    else:
        cap_css = '<link rel="stylesheet" href="styles/static.css">'
        container = (f'<div class="ave-cap-static {style_id}" style="--cap-scale:1;'
                     f' --cap-color:{cap_color};'
                     f' --cap-size:{size}; --cap-bottom:{bottom};'
                     f' --cap-family:{st["cssFamily"]}; --cap-weight:{st["weight"]};'
                     f' --cap-track:{st.get("tracking", 0)};'
                     f' --cap-sx:{st.get("sx", 1)}; --cap-sy:{st.get("sy", 1)}">')

    # A timeline é necessária se QUALQUER coisa se move — legenda animada,
    # câmera ou flash. Sem nada em movimento, `data-no-timeline` evita 45s
    # perdidos por render esperando um registro que nunca vem.
    parts = []
    if style_id == "stacked":
        parts.append("  AVE_STACKED.buildTimeline(document.getElementById('root'), gsap, tl, 1);")
    elif style_id == "scatter":
        parts.append("  AVE_SCATTER.buildTimeline(document.getElementById('root'), gsap, tl, 1);")
    elif style_id == "editorial":
        parts.append("  AVE_EDITORIAL.buildTimeline(document.getElementById('root'), gsap, tl);")
    elif style_id == "dinamico":
        parts.append("  AVE_DINAMICO.buildTimeline(document.getElementById('root'), gsap, tl);")
    elif st.get("css") == "palavra":
        parts.append("  AVE_PALAVRA.buildTimeline(document.getElementById('root'), gsap, tl);")
    elif st.get("css") == "pop":
        parts.append("  AVE_POP.buildTimeline(document.getElementById('root'), gsap, tl, 1);")
    elif st.get("css") == "revelar":
        parts.append("  AVE_REVELAR.buildTimeline(document.getElementById('root'), gsap, tl, 1);")
    elif st["animated"]:
        parts.append("  AVE_KARAOKE.buildTimeline(document.getElementById('root'), gsap, tl, 1);")
    # a cartela tem entrada e saída — e a SAÍDA dela é a entrega do vídeo,
    # então ela precisa da timeline mesmo quando nada mais se move
    if (data.get("hook") or {}).get("enabled") and \
            VARIANTS["headlines"].get(data["hook"].get("style", "card"), {}).get("motor") == "cartela":
        parts.append("  AVE_CARTELA.buildTimeline(document.getElementById('root'), gsap, tl);")
    if track_js:
        parts.append(track_js)
    if cam_js:
        parts.append(cam_js)
    needs_tl = bool(parts)
    track_tag = '<script src="styles/tracking.js"></script>' if track_js else ""

    # inserts: cartão de imagem no terço superior
    ins = VARIANTS["insert"]
    insert_blocks = []
    for i, it in enumerate(data.get("inserts") or []):
        st_, en = float(it.get("start", 0)), float(it.get("end", 0))
        en = min(en, duration)
        if st_ >= duration or en <= st_ or not (it.get("src") or it.get("ref")):
            continue
        insert_blocks.append(
            f'  <div id="ins{i}" class="ave-insert clip" data-start="{st_:.3f}" '
            f'data-duration="{en - st_:.3f}" data-track-index="{TRACK['insert']}" '
            f'style="--ins-scale:1; --ins-w:{ins["w"]}; --ins-h:{ins["h"]}; '
            f'--ins-top:{ins["top"]}">'
            f'<img src="{it.get("src") or it.get("ref")}" alt=""></div>')
        events.append((st_, "hook"))   # whoosh na entrada do cartão

    # palavras em destaque — trilha de TEXTO, ao lado do gancho
    wa_items = []
    for w in (data.get("wordAccents") or []):
        st_, en = float(w.get("start", 0)), min(float(w.get("end", 0)), duration)
        if st_ < duration and en > st_ and w.get("text"):
            wa_items.append((st_, en, w["text"]))
    wa_video = Path(data.get("_proj", ".")) / data.get("_video", "preview.mp4")
    wa_colors = adaptive_accent(wa_video, accent, 0.36, 0.12,
                                [(a, b) for a, b, _ in wa_items])
    wa_blocks = []
    for i, ((st_, en, text), col) in enumerate(zip(wa_items, wa_colors)):
        wa_blocks.append(
            f'  <div id="wa{i}" class="ave-wordaccent clip" data-start="{st_:.3f}" '
            f'data-duration="{en - st_:.3f}" data-track-index="{TRACK['wordaccent']}" '
            f'style="--wa-scale:1; --wa-accent:{col}">{esc(text)}</div>')

    # Gráficos sob medida: substituem o CustomGraphics.tsx, que era "o único
    # arquivo de código editável" do template antigo. Aqui cada um é um HTML
    # próprio montado como sub-composição — mecanismo nativo do HyperFrames.
    # Sem arquivo, o gráfico não aparece; avisar é obrigatório, porque a
    # composição renderiza sem erro e a falta só se vê assistindo.
    # Camadas de textura, da biblioteca em assets/overlays/. Copiadas para o
    # projeto como os efeitos sonoros já são: a composição resolve mídia a
    # partir da própria raiz, e um caminho apontando para dentro da skill
    # quebraria assim que o projeto fosse aberto em outra máquina.
    ov_blocks, ov_missing = [], []
    ovdir = SKILL_DIR / "assets" / "overlays"
    for i, o in enumerate(data.get("overlays") or []):
        f = str(o.get("file") or "").strip()
        st_, en = float(o.get("start", 0)), min(float(o.get("end", duration)), duration)
        if not f or st_ >= duration or en <= st_:
            continue
        src = ovdir / f
        if not src.exists():
            ov_missing.append(f)
            continue
        dest = Path(data.get("_proj", ".")) / "overlays" / f
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists() or dest.stat().st_mtime < src.stat().st_mtime:
            shutil.copy2(src, dest)
        blend = (o.get("blend") or "").strip()
        amt = float(o.get("opacity", 1))
        # COM blend, a intensidade vai por `brightness`, NUNCA por `opacity`:
        # opacidade < 1 cria contexto de empilhamento e mata a mistura — a
        # camada volta como chapa opaca no quadro em que deveria suavizar.
        # No `screen` o brightness faz o mesmo trabalho (fonte mais escura
        # contribui menos) sem quebrar nada.
        css = f"object-fit:{o.get('fit', 'cover')};"
        if blend:
            css += f" mix-blend-mode:{blend};"
            if amt < 1:
                css += f" filter:brightness({amt:.3f});"
        elif amt < 1:
            css += f" opacity:{amt:.3f};"
        # Peça posicionada: `width` em % da largura do quadro liga o modo, e aí
        # `object-fit` deixa de fazer sentido (o elemento passa a ter a
        # proporção do arquivo). `left` é o CENTRO — é como se pensa a posição
        # de uma peça, e centralizar é o caso comum.
        larg = o.get("width")
        # Sem `width` declarado, o TAMANHO DO ARQUIVO decide. Textura (grão,
        # vazamento de luz) vem grande, do tamanho do quadro, e cobre tudo —
        # que é o padrão histórico. Peça de interface vem pequena: o
        # `ig_follow` tem 544×272 num quadro de 1080, e no padrão de cobrir
        # tudo ele inflava para 1080×1920, virando tarja azul sobre o rosto.
        # O README promete que ele "entra sem preparo nenhum"; isto é o que
        # torna a promessa verdadeira. Declarar `width` no dado sempre vence.
        if larg is None:
            nativa = midia_largura(src)
            if nativa and nativa <= 0.7 * data.get("width", 1080):
                larg = round(100 * nativa / data.get("width", 1080), 2)
                print(f"  overlay '{f}' é menor que o quadro ({nativa}px) — entrando "
                      f"no tamanho nativo ({larg}%), centrado; use width/top/left "
                      f"para posicionar", file=sys.stderr)
        classe = "ave-overlay clip"
        if larg is not None:
            classe += " posicionado"
            css = (f"--ov-width:{float(larg):.2f}%;"
                   f" --ov-left:{float(o.get('left', 50)):.2f}%;"
                   f" --ov-top:{float(o.get('top', 50)):.2f}%;")
            if blend:
                css += f" mix-blend-mode:{blend};"
                if amt < 1:
                    css += f" filter:brightness({amt:.3f});"
            elif amt < 1:
                css += f" opacity:{amt:.3f};"
        tag = "video" if src.suffix.lower() in (".mp4", ".webm", ".mov") else "img"
        attrs = ('muted playsinline loop' if tag == "video" else 'alt=""')
        ov_blocks.append(
            f'  <{tag} id="ov{i}" class="{classe}" src="overlays/{f}" {attrs} '
            f'data-start="{st_:.3f}" data-duration="{en - st_:.3f}" '
            f'data-track-index="{TRACK["overlay"]}" style="{css}"'
            + (f'></{tag}>' if tag == "video" else '>'))
    for f in ov_missing:
        print(f"  aviso: overlay '{f}' não existe em assets/overlays/ — "
              f"não vai aparecer", file=sys.stderr)

    bg_blocks, bg_missing = [], []
    for i, g in enumerate(data.get("brollGraphics") or []):
        st_, en = float(g.get("start", 0)), min(float(g.get("end", 0)), duration)
        gid = g.get("id") or g.get("label") or f"grafico{i}"
        if st_ >= duration or en <= st_:
            continue
        rel = f"compositions/{gid}.html"
        if not (Path(data.get("_proj", ".")) / rel).exists():
            bg_missing.append(gid)
            continue
        bg_blocks.append(
            f'  <div id="bg{i}" class="clip" data-start="{st_:.3f}" '
            f'data-duration="{en - st_:.3f}" data-track-index="{TRACK['bespoke']}" '
            f'data-composition-id="{gid}" data-composition-src="{rel}"></div>')
        # mesmo whoosh de entrada dos cartões de inserção: um gráfico que
        # aparece sem som lê como falha de render, não como escolha
        events.append((st_, "hook"))
    for gid in bg_missing:
        print(f"  aviso: gráfico sob medida '{gid}' sem arquivo em "
              f"compositions/{gid}.html — não vai aparecer", file=sys.stderr)

    # Broll Overlay ANTES do corte de efeitos: as janelas emitem os próprios
    # eventos de som, e eles têm de existir quando sfx_blocks olhar a lista.
    bo_html = broll_markup(data, duration, events, bo_kit)
    cx_html, cx_janela = caixinha_markup(data, duration, events, accent or "#ff3b30")

    proj = Path(data.get("_proj", "."))
    # O interruptor da aba Estilo. Desligado, nenhum efeito entra — antes disso
    # os efeitos eram consequência automática de haver um evento, e não havia
    # como pedir um vídeo sem eles.
    if (data.get("elements") or {}).get("sfx", True):
        sfx_list, sfx_warns = sfx_blocks(events, proj, duration)
    else:
        sfx_list, sfx_warns = [], []
        # Desligado também é informação: sem zerar o arquivo, a linha do tempo
        # do editor continuaria mostrando os efeitos da rodada anterior.
        (proj / "sfx-events.json").write_text("[]")
    for w in sfx_warns:
        print(w, file=sys.stderr)
    sfx_html = "\n".join(sfx_list)

    # Trilha sonora como leito, sob tudo. Volume baixo por padrão: ela sustenta,
    # não disputa com a voz.
    snd = data.get("soundtrack") or {}
    track_block = ""
    if snd.get("enabled") and snd.get("file"):
        track_block = (f'  <audio id="soundtrack" src="{snd["file"]}" data-start="0" '
                       f'data-duration="{duration:.3f}" data-track-index="{TRACK['soundtrack']}" '
                       f'data-volume="{snd.get("volume", 0.1)}"></audio>')

    insert_html = "\n".join(insert_blocks)
    wa_html = "\n".join(wa_blocks)
    wa_css = '<link rel="stylesheet" href="styles/wordaccent.css">' if wa_blocks else ""
    wa_tag = '<script src="styles/wordaccent.js"></script>' if wa_blocks else ""
    if wa_blocks:
        parts.append("  AVE_WORDACCENT.buildTimeline(document.getElementById('root'), gsap, tl, 1);")
        needs_tl = True
    bg_html = "\n".join(bg_blocks)
    ov_html = "\n".join(ov_blocks)
    # O PADRÃO é quadro inteiro, porque a biblioteca nasceu de textura (grão,
    # vazamento de luz, poeira) e textura cobre tudo. Mas nem todo overlay é
    # textura: o `ig_follow` é um elemento de interface de 544×272, e no padrão
    # o `object-fit:cover` o inflou para 1080×1920 — saiu uma tarja azul
    # cobrindo o rosto, com "Seguir" em letra gigante. Quem passar `width`
    # (em % da largura do quadro) ganha `top`/`left` e o elemento vira peça
    # posicionada; quem não passar continua cobrindo o quadro como antes.
    ov_css = ("<style>.ave-overlay{position:absolute;inset:0;"
              "width:100%;height:100%;pointer-events:none}"
              ".ave-overlay.posicionado{inset:auto;height:auto;"
              "left:var(--ov-left);top:var(--ov-top);width:var(--ov-width);"
              "transform:translateX(-50%)}</style>"
              if ov_blocks else "")
    insert_css = '<link rel="stylesheet" href="styles/insert.css">' if insert_blocks else ""
    insert_tag = '<script src="styles/insert.js"></script>' if insert_blocks else ""
    if insert_blocks:
        parts.append("  AVE_INSERT.buildTimeline(document.getElementById('root'), gsap, tl, 1);")
        needs_tl = True

    for w in splits:
        off = w["centre"].get(style_id)
        w["centreAttr"] = f' data-centre-offset="{off}"' if off is not None else ""
    split_block = split_markup(splits, style_id) if splits else ""
    split_css = '<link rel="stylesheet" href="styles/split.css">' if splits else ""
    split_tag = '<script src="styles/split.js"></script>' if splits else ""
    if splits:
        parts.append("  AVE_SPLIT.buildTimeline(document.getElementById('root'), gsap, tl, 1);")
        needs_tl = True

    bo_css = '<link rel="stylesheet" href="styles/broll-overlay.css">' if bo_html else ""
    bo_tag = '<script src="styles/broll-overlay.js"></script>' if bo_html else ""
    cx_css = '<link rel="stylesheet" href="styles/caixinha.css">' if cx_html else ""
    cx_tag = '<script src="styles/caixinha.js"></script>' if cx_html else ""
    if cx_html:
        parts.append("  AVE_CAIXA.buildTimeline(document.getElementById('root'), gsap, tl);")
        needs_tl = True
    if bo_html:
        parts.append("  AVE_BROLL.buildTimeline(document.getElementById('root'), gsap, tl);")
        needs_tl = True

    extra_css = ""
    if cam_js and flash_blocks:
        extra_css = '<link rel="stylesheet" href="styles/camera.css">'
    elif flash_blocks:
        extra_css = '<link rel="stylesheet" href="styles/camera.css">'
    cam_tag = '<script src="styles/camera.js"></script>' if cam_js else ""
    gsap_tag = ('<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>'
                if needs_tl else "")
    no_tl = "" if needs_tl else " data-no-timeline"
    timeline = ("  var tl = gsap.timeline({ paused: true });\n"
                + "\n".join(parts) + '\n  window.__timelines["main"] = tl;'
                if needs_tl else "  // nada em movimento: sem timeline")

    return f"""<!doctype html>
<html lang="pt-BR" data-resolution="portrait">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width={W}, height={H}" />
<link href="https://fonts.googleapis.com/css2?{gfont}&display=swap" rel="stylesheet">
{gsap_tag}
{cam_tag}
{track_tag}
{split_tag}
{bo_tag}
{cx_tag}
{insert_tag}
{wa_tag}
{cap_css}
{hook_css}
{extra_css}
{split_css}
{bo_css}
{cx_css}
{insert_css}
{ov_css}
{wa_css}
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html, body {{ width:{W}px; height:{H}px; overflow:hidden; background:#000; }}
  #a-roll {{ position:absolute; inset:0; width:100%; height:100%; object-fit:cover;
             {"transform-origin:0 0;" if track_js else cam_style} }}
</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{duration:.3f}"
     data-width="{W}" data-height="{H}"{no_tl}>

  <div id="vidwin">
    <video id="a-roll" class="clip" src="{video}" muted playsinline
           data-start="0" data-duration="{vdur:.3f}" data-track-index="{TRACK['aroll']}"></video>
  </div>
  <!-- Áudio como trilha própria, do mesmo arquivo. Medido: drift zero em 78s e
       em 786s. O `id` NÃO é opcional: sem ele o renderer não descobre o
       elemento e o vídeo sai MUDO, sem erro em lugar nenhum além do linter. -->
  <audio id="a-roll-audio" src="{video}" data-start="0" data-duration="{vdur:.3f}"
         data-track-index="{TRACK['audio']}" data-volume="1"></audio>

{hook_block}
{cx_html}
{split_block}
{bo_html}
{chr(10).join(flash_blocks)}
{insert_html}
{wa_html}
{bg_html}
{ov_html}
{track_block}
{sfx_html}

  {container}
{data["_stackedMarkup"] if style_id == "stacked" else (data.get("_editorialMarkup", "") if style_id == "editorial" else (data.get("_dinamicoMarkup", "") if style_id == "dinamico" else (scatter_markup(timed, st) if style_id == "scatter" else (palavra_markup(timed, st, orphans, penalty, splits) if st.get("css") == "palavra" else markup(timed, st, style_id, orphans, penalty, splits)))))}
  </div>
</div>

<script>
  window.__timelines = window.__timelines || {{}};
{timeline}
</script>
</body>
</html>
"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edit_data", type=Path)
    ap.add_argument("--captions", type=Path, required=True)
    ap.add_argument("--video", default="preview.mp4")
    ap.add_argument("-o", "--output", type=Path, required=True)
    ap.add_argument("--style", default=None)
    ap.add_argument("--end", type=float, default=None)
    ap.add_argument("--cues", type=Path, default=None,
                    help="caption-cues.json (obrigatório para o estilo empilhado)")
    ap.add_argument("--edl", type=Path, default=None,
                    help="edl.json — de onde saem as fronteiras de segmento da câmera")
    args = ap.parse_args()

    data = json.loads(args.edit_data.read_text())
    cfg = data.get("captions", {})
    style_id = args.style or cfg.get("style", "karaoke")
    if style_id not in VARIANTS["styles"]:
        sys.exit(f"estilo '{style_id}' não existe. Prontos: "
                 f"{', '.join(VARIANTS['styles'])}")
    st = dict(VARIANTS["styles"][style_id])
    # A geometria é POR ESTILO: simples é 82, serifada 84, classica 52. As
    # afinações soltas em captions (fontSize/safeWidth) pertencem ao estilo que
    # o edit-data declara — aplicá-las a qualquer estilo composto fazia as três
    # estáticas saírem todas em 76px, o corpo do karaokê.
    tuned_for = cfg.get("style", "karaoke") == style_id
    if tuned_for and cfg.get("fontSize"):
        st["size"] = cfg["fontSize"]

    proj = args.output.parent
    proj.mkdir(parents=True, exist_ok=True)
    (proj / "styles").mkdir(exist_ok=True)
    files = style_files(style_id, st)
    if data.get("hook", {}).get("enabled"):
        # a folha do motor vai junto quando o layout escolhido é do motor:
        # o HTML pede `styles/cartela.css` e um arquivo que não foi copiado
        # não dá erro nenhum — a headline só sai crua no render final
        _hk = VARIANTS["headlines"].get(data["hook"].get("style", "card"), {})
        if _hk.get("motor") == "cartela":
            files += ["cartela.css", "cartela.js"]
        else:
            files.append("headline.css")
    if data.get("splitInserts"):
        files += ["split.css", "split.js"]
    if data.get("brollOverlays"):
        files += ["broll-overlay.css", "broll-overlay.js"]
    if (data.get("questionBox") or {}).get("pergunta"):
        files += ["caixinha.css", "caixinha.js"]
    if data.get("inserts"):
        files += ["insert.css", "insert.js"]
    if (data.get("elements") or {}).get("tracking"):
        files += ["tracking.js"]
    if data.get("wordAccents"):
        files += ["wordaccent.css", "wordaccent.js"]

    # os efeitos vão para o projeto: o renderer resolve caminho relativo a ele
    sfxdir = proj / "sfx"
    sfxdir.mkdir(exist_ok=True)
    for spec in VARIANTS["sfx"].values():
        src = SKILL_DIR / "assets" / "sfx" / spec["file"]
        if src.exists():
            shutil.copy2(src, sfxdir / spec["file"])

    if (data.get("camera", {}).get("enabled", True)
            and any((data.get("elements") or {}).get(k, True) for k in ("zoomCuts", "zoomAuto"))) \
            or data.get("transitions"):
        files += ["camera.js", "camera.css"]
    for f in files:
        shutil.copy2(STYLES_DIR / f, proj / "styles" / f)

    src_video = proj / args.video
    vdur = (video_duration(src_video) if src_video.exists()
            else float(data["durationSec"]))
    duration = vdur
    declared = float(data.get("durationSec", duration))
    # CARTÃO DE ENCERRAMENTO: um `durationSec` MAIOR que o vídeo estende a
    # composição além do corte — os segundos extras são tela livre para um
    # gráfico de fechamento (data do evento, logo, CTA). O a-roll continua com
    # a duração do PRÓPRIO arquivo (`vdur`): esticá-lo faria o renderer pedir
    # quadros que não existem, e o fim congelaria em vez de dar lugar ao cartão.
    if declared > vdur + 0.05:
        duration = declared
        print(f"  encerramento: composição vai a {duration:.2f}s "
              f"({duration - vdur:.2f}s depois do corte)")
    elif abs(declared - duration) > 0.5:
        print(f"  aviso: durationSec ({declared:.2f}s) diverge do stream de vídeo "
              f"({duration:.2f}s) — usando o stream", file=sys.stderr)
    if args.end:
        duration = min(duration, args.end)

    fps = data.get("fps", 30)

    # Fronteiras de segmento para a câmera: saem das junções REAIS do corte
    # (jcut_timeline), não de um arquivo à parte que pode ficar velho.
    segs = []
    edl_path = args.edl or (args.edit_data.parent.parent.parent / "edl.json")
    if edl_path.exists():
        tl = json.loads(edl_path.read_text()).get("jcut_timeline") or []
        for k, t in enumerate(tl):
            s0 = t.get("video_start_in_output")
            if s0 is None or s0 >= duration:
                continue
            s1 = (tl[k + 1].get("video_start_in_output")
                  if k + 1 < len(tl) else duration)
            segs.append({"start": round(s0, 3), "end": round(min(s1, duration), 3)})
    data["_segments"] = segs

    # DURANTE UM BROLL OVERLAY A LEGENDA SAI DE CENA (pedido do usuário,
    # 2026-08-19): o overlay já é o texto do momento, e os dois juntos
    # disputavam a mesma tela. Filtrado pelo PONTO MÉDIO da deixa — uma deixa
    # que só encosta na borda da janela continua existindo fora dela.
    bo_spans = [(float(o.get("start", 0)), float(o.get("end", 0)))
                for o in (data.get("brollOverlays") or [])]
    # gráfico sob medida que ESCURECE a tela também cala a legenda: os dois
    # disputariam o mesmo quadro. Explícito por entrada (`muteCaptions`) —
    # um gráfico de canto não tem por que silenciar nada.
    bo_spans += [(float(g.get("start", 0)), float(g.get("end", 0)))
                 for g in (data.get("brollGraphics") or []) if g.get("muteCaptions")]
    # A CAIXINHA na zona baixa ocupa a faixa da legenda — os dois ali viram
    # texto sobre texto. Medido no C0005: sobram 190px entre o queixo (1210px)
    # e a legenda (1400px), e o adesivo tem ~300px. Quem carrega o texto na
    # janela é ele. Na zona ALTA não há conflito e nada é silenciado.
    _qb = data.get("questionBox") or {}
    if _qb.get("pergunta") and _qb.get("muteCaptions", True) and float(_qb.get("top", 300)) > 900:
        bo_spans.append((float(_qb.get("start", 0.0)),
                         float(_qb.get("end") or duration)))

    def fora_broll(ms_a: float, ms_b: float) -> bool:
        mid = (ms_a + ms_b) / 2000.0
        return all(not (a <= mid <= b) for a, b in bo_spans)

    words = [w for w in json.loads(args.captions.read_text())
             if w["startMs"] / 1000 < duration
             and fora_broll(w["startMs"], w.get("endMs", w["startMs"]))]

    timed = []
    if style_id == "stacked":
        cues_path = args.cues or (args.captions.parent / "caption-cues.json")
        if not cues_path.exists():
            sys.exit("o empilhado precisa do caption-cues.json — rode antes:\n"
                     f"  uv run python helpers/caption_style.py --transcript "
                     f"<edit>/transcripts/cut.json -o {cues_path}")
        cues = json.loads(cues_path.read_text())
        cues = [c for c in cues
                if fora_broll(c.get("startMs", 0), c.get("endMs", c.get("startMs", 0)))]
        # o MESMO accent que o resto da composição usa — o círculo do solo era
        # verde fixo e atravessava qualquer paleta escolhida na aba Estilo
        mk, stretched = stacked_markup(cues, st, duration,
                                       data.get("accent") or "#FF6B1A")
        data["_stackedMarkup"] = mk
        data["_soloCues"] = [
            (c["startMs"] / 1000,
             "circled" if c["preset"] == "SOLO_OUTLINE" else "soloWord")
            for c in cues
            if c["preset"] in ("SOLO_BIG", "SOLO_OUTLINE")
            and c["startMs"] / 1000 < duration]
        data["_stackedCount"] = mk.count("stk-cue")
        data["_stackedStretched"] = stretched
    elif style_id == "editorial":
        cues_path = args.cues or (args.captions.parent / "caption-editorial.json")
        if not cues_path.exists():
            sys.exit("o editorial precisa do caption-editorial.json — rode antes:\n"
                     f"  uv run python helpers/caption_style_editorial.py --transcript "
                     f"<edit>/transcripts/cut.json -o {cues_path}")
        ecues = json.loads(cues_path.read_text())
        ecues = [c for c in ecues
                 if fora_broll(c.get("startMs", 0), c.get("endMs", c.get("startMs", 0)))]
        data["_editorialMarkup"] = editorial_markup(ecues, st, duration)
        # punch estala, algarismo estoura — os acentos do estilo SOAM, como no
        # empilhado; sem som, palavra que salta lê como falha de render
        data["_soloCues"] = [
            (w["fromMs"] / 1000, "callout" if w["role"] == "num" else "soloWord")
            for c in ecues for ln in c["lines"] for w in ln
            if w["role"] in ("punch", "num") and w["fromMs"] / 1000 < duration]
    elif style_id == "dinamico":
        cues_path = args.cues or (args.captions.parent / "caption-dinamico.json")
        if not cues_path.exists():
            sys.exit("o dinâmico precisa do caption-dinamico.json — rode antes:\n"
                     f"  uv run python helpers/caption_style_dinamico.py --transcript "
                     f"<edit>/transcripts/cut.json -o {cues_path}")
        dcues = json.loads(cues_path.read_text())
        dcues = [c for c in dcues
                 if fora_broll(c.get("startMs", 0), c.get("endMs", c.get("startMs", 0)))]
        data["_dinamicoMarkup"] = dinamico_markup(dcues, st, duration)
        # só a FIGURE soa: um acento serif por deixa clicando a cada ~1.5s
        # viraria metrônomo, não pontuação
        data["_soloCues"] = [
            (c["figure"]["fromMs"] / 1000, "callout")
            for c in dcues
            if c.get("figure") and c["figure"]["fromMs"] / 1000 < duration]
    elif cfg.get("enabled", True):
        budget = (cfg.get("safeWidth") if tuned_for else None) or st["maxW"]
        _pal = st.get("pal") or {}
        cues = (cola_cues(words, int(_pal["cola"])) if _pal.get("cola")
                else build_cues(words, st, budget))
        timed = time_cues(cues, fps, duration)

    orphans = set(VARIANTS["orphansPt"])
    penalty = VARIANTS["orphanPenalty"]
    data["_proj"] = str(proj)
    data["_video"] = args.video
    args.output.write_text(render_html(data, timed, st, style_id, args.video,
                                       duration, orphans, penalty, vdur))

    if style_id == "editorial":
        n = data.get("_editorialMarkup", "").count("edt-cue")
        print(f"{args.output}")
        print(f"  estilo editorial (animado) · {st['family']} + serif @ {st['size']}px")
        print(f"  {len(words)} palavras → {n} deixas com papéis")
        print(f"  duração {duration:.3f}s (stream de vídeo)")
        return

    if style_id == "dinamico":
        n = data.get("_dinamicoMarkup", "").count("din-cue")
        figs = data.get("_dinamicoMarkup", "").count("din-fig")
        print(f"{args.output}")
        print(f"  estilo dinâmico (animado) · {st['family']} + serif @ {st['size']}px")
        print(f"  {len(words)} palavras → {n} deixas acumulativas ({figs} com figure)")
        print(f"  duração {duration:.3f}s (stream de vídeo)")
        return

    if style_id == "stacked":
        n = data.get("_stackedCount", 0)
        extra = data.get("_stackedStretched", 0)
        print(f"{args.output}")
        print(f"  estilo stacked (animado) · {st['family']} {st['weight']} @ {st['size']}px")
        print(f"  {len(words)} palavras → {n} deixas preparadas")
        if extra:
            print(f"  {extra} deixa(s) sozinha(s) esticada(s) até {st['minSoloMs']}ms — "
                  f"abaixo disso a palavra pisca em um quadro e lê como falha")
        print(f"  duração {duration:.3f}s (stream de vídeo)")
        return

    sizes = [len(t["cue"]) for t in timed]
    hist = {n: sizes.count(n) for n in sorted(set(sizes))}
    print(f"{args.output}")
    print(f"  estilo {style_id} ({'animado' if st['animated'] else 'estático'}) · "
          f"{st['family']} {st['weight']} @ {st['size']}px"
          + (f" · escala {st['sx']}×{st['sy']}" if st.get('sx', 1) != 1 else ""))
    print(f"  {len(words)} palavras → {len(timed)} deixas · "
          f"palavras por deixa: {hist} (teto {st['maxWords']}, "
          f"{st.get('lines', 1)} linha{'s' if st.get('lines', 1) > 1 else ''})")
    print(f"  duração {duration:.3f}s (stream de vídeo)")


if __name__ == "__main__":
    main()

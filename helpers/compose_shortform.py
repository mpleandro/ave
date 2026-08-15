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


def style_files(style_id: str, style: dict) -> list[str]:
    if style_id in ("scatter", "stacked"):
        return [f"{style_id}.css", f"{style_id}.js"]
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
            f'data-duration="{t["end"] - t["start"]:.3f}" data-track-index="1">'
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


def stacked_markup(cues: list[dict], st: dict, duration: float) -> tuple[str, int]:
    """Deixas do empilhado, do arquivo preparado. Retorna (markup, n_estendidas)."""
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
            circle = ('<svg class="stk-ellipse" viewBox="0 0 200 100" fill="none">'
                      '<ellipse cx="100" cy="50" rx="94" ry="42" stroke="#5fd07a" '
                      'stroke-width="5" stroke-linecap="round" '
                      'stroke-dasharray="300 40" transform="rotate(-3 100 50)"/></svg>'
                      if c["preset"] == "SOLO_OUTLINE" else "")
            rows.append(
                f'<div class="stk-line" style="position:relative">{circle}'
                f'<span class="stk-solo s0" data-at="{w["fromMs"] / 1000:.3f}" '
                f'style="font-size:{size}px">{esc(w["text"])}</span></div>')
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
            f'data-track-index="1">{"".join(rows)}</div>')
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
            "captionBottom": lay["captionBottom"],
            "seam": lay["seam"],
        })
    return out


def split_markup(wins: list[dict]) -> str:
    blocks = []
    for i, w in enumerate(wins):
        art = (f'<img class="ave-split-art" src="{w["src"]}" alt="" '
               f'style="top:{w["artTop"]}px; height:{w["band"]}px">'
               if w["src"] else "")
        # o degradê cobre a parte de baixo da arte, que é onde a legenda encosta
        seam = (f'<div class="ave-split-seam" '
                f'style="top:{w["artTop"] + w["band"] - 220}px; height:280px"></div>'
                if w["seam"] else "")
        blocks.append(
            f'<div id="split{i}" class="ave-split-win clip" data-start="{w["start"]:.3f}" '
            f'data-duration="{w["end"] - w["start"]:.3f}" data-track-index="5" '
            f'data-zoom="{w["zoom"]}" data-focus="{w["focusY"]}" '
            f'data-vid-top="{w["vidTop"]}" data-vid-height="{w["vidHeight"]}">'
            f'{art}{seam}</div>')
    return "\n".join("  " + b for b in blocks)


def adaptive_accent(video: Path, brand_accent: str, top: float, height: float,
                    windows: list[tuple[float, float]]) -> list[str]:
    """Uma cor de accent por janela, medindo o FUNDO onde o elemento vai ficar.

    Existe porque #FF6B1A tem luminância MÉDIA (L=0.318): ele só passa em WCAG
    contra fundo bem escuro ou bem claro, e entre 0.10 e 0.35 fica em 1.09–2.46.
    Medido numa palavra em destaque sobre fundo quente: 1.05:1.

    A regra é de RESERVA, não de otimização: a laranja canônica sempre, e só
    escala para outra da paleta quando ela reprova. Escolher sempre a de maior
    contraste trocaria a cor da marca em todo quadro, que é abandoná-la.
    """
    if not video.exists() or not windows:
        return [brand_accent] * len(windows)
    try:
        from backdrop_luma import sample_band, pick_accent
        palette = json.loads((SKILL_DIR / "brand" / "avelin.json").read_text())["palette"]
        samples = sample_band(video, top, height, 0.06, 0.88)
    except Exception:
        return [brand_accent] * len(windows)
    if not samples:
        return [brand_accent] * len(windows)

    out = []
    for a, b in windows:
        inside = [l for t, l in samples if a <= t < b]
        if not inside:
            inside = [min(samples, key=lambda tl: abs(tl[0] - (a + b) / 2))[1]]
        name, _ = pick_accent(sum(inside) / len(inside), palette)
        out.append(palette.get(name, brand_accent))
    return out


def sfx_blocks(events: list[tuple[float, str]], proj: Path, duration: float,
               track: int = 8) -> tuple[list[str], list[str]]:
    """Elementos de áudio dos efeitos. Retorna (blocos, avisos).

    Duas coisas que a referência documenta como já vividas e que só aparecem
    OUVINDO — a mixagem parece certa e não se escuta nada:

    - o arquivo começa ANTES do evento, compensando o silêncio inicial MEDIDO.
      Sem isso o clique do `caption-click` chega 158ms atrasado, depois de um
      efeito de 230ms já ter acabado.
    - o nível é conferido: abaixo de -12 dB o efeito some sob a fala, e o pacote
      tem dois arquivos assim.

    Isto só é possível porque o áudio da composição NÃO precisa de remux. No
    Remotion o remux existia para corrigir drift e descartava os efeitos junto,
    obrigando a reconstruir ~20 deles à mão no ffmpeg. Com drift zero medido,
    eles simplesmente ficam.
    """
    from sfx import probe

    blocks, warns, seen = [], [], set()
    for i, (at, kind) in enumerate(events):
        spec = VARIANTS["sfx"].get(kind)
        if not spec:
            continue
        f = proj / "sfx" / spec["file"]
        if not f.exists():
            if kind not in seen:
                warns.append(f"  aviso: efeito '{spec['file']}' não encontrado — {kind} mudo")
                seen.add(kind)
            continue
        info = probe(str(f))
        if info["quiet"] and spec["file"] not in seen:
            warns.append(f"  aviso: {spec['file']} tem pico de {info['peak']:.1f} dB "
                         f"— vai sumir sob a fala")
            seen.add(spec["file"])
        start = max(0.0, at - info["lead"])
        dur = min(info["duration"], duration - start)
        if dur <= 0:
            continue
        blocks.append(
            f'  <audio id="sfx{i}" src="sfx/{spec["file"]}" data-start="{start:.3f}" '
            f'data-duration="{dur:.3f}" data-track-index="{track}" '
            f'data-volume="{spec["volume"]}"></audio>')
    return blocks, warns


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


def esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def hl_width(text: str, size: float, weight: int) -> float:
    if not text:
        return 0.0
    fam = VARIANTS["headlineFamily"]
    return measure(text, fam, size, weight) - 1.0 * len(text)  # letter-spacing -1px


def hl_two_lines(text: str, weights: list[int]) -> list[str]:
    """Divide em DUAS linhas equilibrando a largura medida.

    Só entra em ação quando o dado traz a headline como uma frase só. Em
    produção `hook.lines` já vem com as duas linhas escritas por quem redigiu —
    e aí a divisão é dele, não nossa.
    """
    words = text.split()
    if len(words) < 2:
        return [words[0] if words else "", ""]
    best, best_diff = [words[0], " ".join(words[1:])], float("inf")
    for i in range(1, len(words)):
        a, b = " ".join(words[:i]), " ".join(words[i:])
        d = abs(hl_width(a, 100, weights[0]) - hl_width(b, 100, weights[1]))
        if d < best_diff:
            best, best_diff = [a, b], d
    return best


def hl_fit(lines: list[str], h: dict) -> float:
    """Corpo que faz a linha mais larga caber em `safeW`, limitado por `cap`.

    `cap` é TETO, não medida fixa: uma headline curta pode chegar nele, uma
    longa tem que encolher. Duas passadas porque a largura não é perfeitamente
    linear no corpo — a primeira estima, a segunda corrige.
    """
    w = h["weights"]

    def widest(size: float) -> float:
        return max(hl_width(lines[0], size, w[0]),
                   hl_width(lines[1] if len(lines) > 1 else "", size, w[1]))

    size = int(h["safeW"] / max(1.0, widest(100)) * 100)
    size = int(h["safeW"] / max(1.0, widest(size)) * size)
    return max(VARIANTS["headlineMinSize"], min(size, h["cap"]))


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

    raw = [l for l in (hook.get("lines") or []) if l]
    if len(raw) == 1:
        raw = hl_two_lines(raw[0], h["weights"])
    raw = (raw + ["", ""])[:2]
    if h["upper"]:
        raw = [l.upper() for l in raw]

    size = hl_fit(raw, h)
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
    lines = "".join(f'<div class="hl-line">{esc(l)}</div>' for l in raw if l)
    block = (f'  <div id="hook" class="ave-hook {style_id} clip" data-start="0" '
             f'data-duration="{end:.3f}" data-track-index="2" '
             f'style="--hl-scale:1; --hl-size:{size}; --hl-lh:{h["lh"]}; '
             f'--hl-top:{top}; --hl-accent:{accent}; --hl-stroke:{h["stroke"]}">'
             f'{lines}</div>')
    return block, '<link rel="stylesheet" href="styles/headline.css">'


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
                 f'data-duration="{t["end"] - t["start"]:.3f}" data-track-index="1"')
        if st["animated"]:
            spans = "".join(f"<span>{esc(w['text'])}</span>" for w in t["cue"])
            blocks.append(f'<div class="ave-cap-line clip" {attrs}{dodge}>{spans}</div>')
        else:
            lines = split_two_lines(t["cue"], st, orphans, penalty)
            inner = "".join(
                f'<div>{esc(" ".join(w["text"] for w in ln))}</div>' for ln in lines)
            blocks.append(f'<div class="ave-cue clip" {attrs}{dodge}>{inner}</div>')
    return "\n".join("    " + b for b in blocks)


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
    fl = VARIANTS["flash"]
    for k, tr in enumerate(data.get("transitions") or []):
        at = float(tr.get("at", 0))
        if at >= duration:
            continue
        start = max(0.0, at - fl["durationFrames"] / fps)
        dur = (fl["durationFrames"] * 2) / fps
        blocks.append(
            f'  <div id="flash{k}" class="ave-flash clip" data-start="{start:.3f}" '
            f'data-duration="{min(dur, duration - start):.3f}" data-track-index="6" '
            f'style="--flash-intensity:{tr.get("intensity", fl["intensity"])}; '
            f'--flash-blur:{fl["blur"]}"></div>'
        )
        js += (f"\n  tl.fromTo('#flash{k}', {{opacity:0, xPercent:-120}}, "
               f"{{opacity:1, xPercent:120, duration:{dur:.3f}, ease:'power1.inOut'}}, "
               f"{start:.3f});")
    return js, style, blocks


def render_html(data, timed, st, style_id, video, duration, orphans, penalty) -> str:
    accent = data.get("accent") or "#FF6B1A"
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

    splits = split_windows(data, H, duration)
    hook_accent = accent
    hk = data.get("hook") or {}
    if hk.get("enabled") and VARIANTS["headlines"].get(hk.get("style", "card"), {}).get("usesAccent"):
        hv = Path(data.get("_proj", ".")) / data.get("_video", "cut.mp4")
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

    gfont = st["gfont"]
    if hook_block:
        # a headline usa Poppins em 400/800/900; pedir só o peso da legenda
        # deixaria o texto cair numa fonte genérica sem erro visível
        gfont = f"{gfont}&{VARIANTS['headlineGfont']}"

    if style_id == "stacked":
        cap_css = ('<link rel="stylesheet" href="styles/stacked.css">\n'
                   '<script src="styles/stacked.js"></script>')
        container = (f'<div class="ave-stacked" style="--stk-scale:1;'
                     f' --stk-offset-y:{cfg.get("stackedOffsetY", st["offsetY"])};'
                     f' --stk-orange:{st["orange"]}">')
    elif style_id == "scatter":
        cap_css = ('<link rel="stylesheet" href="styles/scatter.css">\n'
                   '<script src="styles/scatter.js"></script>')
        container = (f'<div class="ave-scatter" style="--scat-scale:1;'
                     f' --scat-size:{size}; --scat-gap:{st["gap"]};'
                     f' --scat-offset-y:{cfg.get("scatterOffsetY", st["offsetY"])}">')
    elif st["animated"]:
        cap_css = ('<link rel="stylesheet" href="styles/karaoke.css">\n'
                   '<script src="styles/karaoke.js"></script>')
        container = (f'<div class="ave-cap {style_id}" style="--cap-scale:1;'
                     f' --cap-size:{size}; --cap-bottom:{bottom}">')
    else:
        cap_css = '<link rel="stylesheet" href="styles/static.css">'
        container = (f'<div class="ave-cap-static {style_id}" style="--cap-scale:1;'
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
    elif st["animated"]:
        parts.append("  AVE_KARAOKE.buildTimeline(document.getElementById('root'), gsap, tl, 1);")
    if cam_js:
        parts.append(cam_js)
    needs_tl = bool(parts)

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
            f'data-duration="{en - st_:.3f}" data-track-index="3" '
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
    wa_video = Path(data.get("_proj", ".")) / data.get("_video", "cut.mp4")
    wa_colors = adaptive_accent(wa_video, accent, 0.36, 0.12,
                                [(a, b) for a, b, _ in wa_items])
    wa_blocks = []
    for i, ((st_, en, text), col) in enumerate(zip(wa_items, wa_colors)):
        wa_blocks.append(
            f'  <div id="wa{i}" class="ave-wordaccent clip" data-start="{st_:.3f}" '
            f'data-duration="{en - st_:.3f}" data-track-index="6" '
            f'style="--wa-scale:1; --wa-accent:{col}">{esc(text)}</div>')

    # Gráficos sob medida: substituem o CustomGraphics.tsx, que era "o único
    # arquivo de código editável" do template Remotion. Aqui cada um é um HTML
    # próprio montado como sub-composição — mecanismo nativo do HyperFrames.
    # Sem arquivo, o gráfico não aparece; avisar é obrigatório, porque a
    # composição renderiza sem erro e a falta só se vê assistindo.
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
            f'data-duration="{en - st_:.3f}" data-track-index="4" '
            f'data-composition-id="{gid}" data-composition-src="{rel}"></div>')
    for gid in bg_missing:
        print(f"  aviso: gráfico sob medida '{gid}' sem arquivo em "
              f"compositions/{gid}.html — não vai aparecer", file=sys.stderr)

    proj = Path(data.get("_proj", "."))
    sfx_list, sfx_warns = sfx_blocks(events, proj, duration)
    for w in sfx_warns:
        print(w, file=sys.stderr)
    sfx_html = "\n".join(sfx_list)

    # Trilha sonora como leito, sob tudo. Volume baixo por padrão: ela sustenta,
    # não disputa com a voz.
    snd = data.get("soundtrack") or {}
    track_block = ""
    if snd.get("enabled") and snd.get("file"):
        track_block = (f'  <audio id="soundtrack" src="{snd["file"]}" data-start="0" '
                       f'data-duration="{duration:.3f}" data-track-index="7" '
                       f'data-volume="{snd.get("volume", 0.1)}"></audio>')

    insert_html = "\n".join(insert_blocks)
    wa_html = "\n".join(wa_blocks)
    wa_css = '<link rel="stylesheet" href="styles/wordaccent.css">' if wa_blocks else ""
    wa_tag = '<script src="styles/wordaccent.js"></script>' if wa_blocks else ""
    if wa_blocks:
        parts.append("  AVE_WORDACCENT.buildTimeline(document.getElementById('root'), gsap, tl, 1);")
        needs_tl = True
    bg_html = "\n".join(bg_blocks)
    insert_css = '<link rel="stylesheet" href="styles/insert.css">' if insert_blocks else ""
    insert_tag = '<script src="styles/insert.js"></script>' if insert_blocks else ""
    if insert_blocks:
        parts.append("  AVE_INSERT.buildTimeline(document.getElementById('root'), gsap, tl, 1);")
        needs_tl = True

    split_block = split_markup(splits) if splits else ""
    split_css = '<link rel="stylesheet" href="styles/split.css">' if splits else ""
    split_tag = '<script src="styles/split.js"></script>' if splits else ""
    if splits:
        parts.append("  AVE_SPLIT.buildTimeline(document.getElementById('root'), gsap, tl, 1);")
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
{split_tag}
{insert_tag}
{wa_tag}
{cap_css}
{hook_css}
{extra_css}
{split_css}
{insert_css}
{wa_css}
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html, body {{ width:{W}px; height:{H}px; overflow:hidden; background:#000; }}
  #a-roll {{ position:absolute; inset:0; width:100%; height:100%; object-fit:cover;
             {cam_style} }}
</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{duration:.3f}"
     data-width="{W}" data-height="{H}"{no_tl}>

  <div id="vidwin">
    <video id="a-roll" class="clip" src="{video}" muted playsinline
           data-start="0" data-duration="{duration:.3f}" data-track-index="0"></video>
  </div>
  <!-- Áudio como trilha própria, do mesmo arquivo. Medido: drift zero em 78s e
       em 786s. O `id` NÃO é opcional: sem ele o renderer não descobre o
       elemento e o vídeo sai MUDO, sem erro em lugar nenhum além do linter. -->
  <audio id="a-roll-audio" src="{video}" data-start="0" data-duration="{duration:.3f}"
         data-track-index="9" data-volume="1"></audio>

{hook_block}
{split_block}
{chr(10).join(flash_blocks)}
{insert_html}
{wa_html}
{bg_html}
{track_block}
{sfx_html}

  {container}
{data["_stackedMarkup"] if style_id == "stacked" else (scatter_markup(timed, st) if style_id == "scatter" else markup(timed, st, style_id, orphans, penalty, splits))}
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
    ap.add_argument("--video", default="cut.mp4")
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
        files.append("headline.css")
    if data.get("splitInserts"):
        files += ["split.css", "split.js"]
    if data.get("inserts"):
        files += ["insert.css", "insert.js"]
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
    duration = (video_duration(src_video) if src_video.exists()
                else float(data["durationSec"]))
    declared = float(data.get("durationSec", duration))
    if abs(declared - duration) > 0.5:
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

    words = [w for w in json.loads(args.captions.read_text())
             if w["startMs"] / 1000 < duration]

    timed = []
    if style_id == "stacked":
        cues_path = args.cues or (args.captions.parent / "caption-cues.json")
        if not cues_path.exists():
            sys.exit("o empilhado precisa do caption-cues.json — rode antes:\n"
                     f"  uv run python helpers/caption_style.py --transcript "
                     f"<edit>/transcripts/cut.json -o {cues_path}")
        cues = json.loads(cues_path.read_text())
        mk, stretched = stacked_markup(cues, st, duration)
        data["_stackedMarkup"] = mk
        data["_soloCues"] = [
            (c["startMs"] / 1000,
             "circled" if c["preset"] == "SOLO_OUTLINE" else "soloWord")
            for c in cues
            if c["preset"] in ("SOLO_BIG", "SOLO_OUTLINE")
            and c["startMs"] / 1000 < duration]
        data["_stackedCount"] = mk.count("stk-cue")
        data["_stackedStretched"] = stretched
    elif cfg.get("enabled", True):
        budget = (cfg.get("safeWidth") if tuned_for else None) or st["maxW"]
        cues = build_cues(words, st, budget)
        timed = time_cues(cues, fps, duration)

    orphans = set(VARIANTS["orphansPt"])
    penalty = VARIANTS["orphanPenalty"]
    data["_proj"] = str(proj)
    data["_video"] = args.video
    args.output.write_text(render_html(data, timed, st, style_id, args.video,
                                       duration, orphans, penalty))

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

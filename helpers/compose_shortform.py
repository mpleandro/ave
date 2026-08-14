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
    return ["karaoke.css", "karaoke.js"] if style["animated"] else ["static.css"]


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


def markup(timed: list[dict], st: dict, style_id: str, orphans, penalty) -> str:
    blocks = []
    for t in timed:
        attrs = (f'data-start="{t["start"]:.3f}" '
                 f'data-duration="{t["end"] - t["start"]:.3f}" data-track-index="1"')
        if st["animated"]:
            spans = "".join(f"<span>{esc(w['text'])}</span>" for w in t["cue"])
            blocks.append(f'<div class="ave-cap-line clip" {attrs}>{spans}</div>')
        else:
            lines = split_two_lines(t["cue"], st, orphans, penalty)
            inner = "".join(
                f'<div>{esc(" ".join(w["text"] for w in ln))}</div>' for ln in lines)
            blocks.append(f'<div class="ave-cue clip" {attrs}>{inner}</div>')
    return "\n".join("    " + b for b in blocks)


def render_html(data, timed, st, style_id, video, duration, orphans, penalty) -> str:
    W, H = data.get("width", 1080), data.get("height", 1920)
    cfg = data.get("captions", {})
    bottom = cfg.get("paddingBottom", VARIANTS["bottom"])
    size = cfg.get("fontSize") or st["size"]

    if st["animated"]:
        css = '<link rel="stylesheet" href="styles/karaoke.css">\n' \
              '<script src="styles/karaoke.js"></script>'
        container = (f'<div class="ave-cap {style_id}" style="--cap-scale:1;'
                     f' --cap-size:{size}; --cap-bottom:{bottom}">')
        timeline = """  var tl = gsap.timeline({ paused: true });
  // Montada pelo MESMO módulo que a prévia do editor usa. Tween declarativo em
  // tempo absoluto é seekable por construção.
  AVE_KARAOKE.buildTimeline(document.getElementById('root'), gsap, tl, 1);
  window.__timelines["main"] = tl;"""
        gsap_tag = '<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>'
        no_tl = ""
    else:
        css = '<link rel="stylesheet" href="styles/static.css">'
        container = (f'<div class="ave-cap-static {style_id}" style="--cap-scale:1;'
                     f' --cap-size:{size}; --cap-bottom:{bottom};'
                     f' --cap-family:{st["cssFamily"]}; --cap-weight:{st["weight"]};'
                     f' --cap-track:{st.get("tracking", 0)};'
                     f' --cap-sx:{st.get("sx", 1)}; --cap-sy:{st.get("sy", 1)}">')
        # Estilo estático não registra timeline. Sem esta marca o produtor fica
        # 45 SEGUNDOS esperando o registro antes de desistir, em todo render.
        timeline = "  // estilo estático: sem animação, sem timeline"
        gsap_tag = ""
        no_tl = " data-no-timeline"

    return f"""<!doctype html>
<html lang="pt-BR" data-resolution="portrait">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width={W}, height={H}" />
<link href="https://fonts.googleapis.com/css2?{st['gfont']}&display=swap" rel="stylesheet">
{gsap_tag}
{css}
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html, body {{ width:{W}px; height:{H}px; overflow:hidden; background:#000; }}
  #a-roll {{ position:absolute; inset:0; width:100%; height:100%; object-fit:cover; }}
</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{duration:.3f}"
     data-width="{W}" data-height="{H}"{no_tl}>

  <video id="a-roll" class="clip" src="{video}" muted playsinline
         data-start="0" data-duration="{duration:.3f}" data-track-index="0"></video>
  <!-- Áudio como trilha própria, do mesmo arquivo. Medido: drift zero em 78s e
       em 786s. O `id` NÃO é opcional: sem ele o renderer não descobre o
       elemento e o vídeo sai MUDO, sem erro em lugar nenhum além do linter. -->
  <audio id="a-roll-audio" src="{video}" data-start="0" data-duration="{duration:.3f}"
         data-track-index="9" data-volume="1"></audio>

  {container}
{markup(timed, st, style_id, orphans, penalty)}
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
    for f in style_files(style_id, st):
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
    words = [w for w in json.loads(args.captions.read_text())
             if w["startMs"] / 1000 < duration]

    timed = []
    if cfg.get("enabled", True):
        budget = (cfg.get("safeWidth") if tuned_for else None) or st["maxW"]
        cues = build_cues(words, st, budget)
        timed = time_cues(cues, fps, duration)

    orphans = set(VARIANTS["orphansPt"])
    penalty = VARIANTS["orphanPenalty"]
    args.output.write_text(render_html(data, timed, st, style_id, args.video,
                                       duration, orphans, penalty))

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

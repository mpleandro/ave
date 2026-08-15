#!/usr/bin/env python3
"""Monta a composição HyperFrames da Fase 2 LONGFORM a partir dos dados.

Quatro camadas sobre o corte, todas vindas do `edit-data.json`:
  broll[]        cortes de imagem (com Ken-Burns) ou vídeo mudo sobre a narração
  lowerThirds[]  cartão de nome/título entrando pela esquerda
  chapters[]     card de título no começo de cada capítulo
  callouts[]     etiqueta no accent, numa posição x/y da tela

A regra que rege as quatro: gráfico em longform PONTUA, não satura. Densidade de
Reel num vídeo de treze minutos cansa antes do meio.

    uv run python helpers/compose_longform.py <edit-data.json> -o <projeto>/index.html
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
STYLES_DIR = SKILL_DIR / "assets" / "styles"

DEFAULT_DUR = {"broll": 4.0, "chapters": 2.4, "lowerThirds": 4.0, "callouts": 3.0}


def esc(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def video_duration(path: Path) -> float:
    """Duração do stream de VÍDEO, nunca do container nem do áudio decodificado.

    Medido neste próprio material ("Fome de Poder"): vídeo 786.167s, mas o
    decode do áudio entrega 789.184s COM SINAL — 3s de som além do fim da
    imagem, sem o container refletir. Tirar a duração do áudio poria 3s de
    preto no fim de todo longform.
    """
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=duration", "-of",
         "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def window(item: dict, kind: str, end_cap: float) -> tuple[float, float] | None:
    """Início e fim do elemento, com o padrão da camada quando falta duração."""
    start = float(item.get("start", 0))
    if start >= end_cap:
        return None
    if "end" in item:
        end = float(item["end"])
    elif "dur" in item:
        end = start + float(item["dur"])
    else:
        end = start + DEFAULT_DUR[kind]
    end = min(end, end_cap)
    return (start, end) if end > start else None


def layers(data: dict, end_cap: float) -> tuple[list[str], dict]:
    blocks, counts = [], {}

    for i, b in enumerate(data.get("broll") or []):
        w = window(b, "broll", end_cap)
        if not w:
            continue
        attrs = (f'class="ave-lf-broll clip" data-start="{w[0]:.3f}" '
                 f'data-duration="{w[1] - w[0]:.3f}" data-track-index="1"')
        # vídeo de B-roll entra MUDO: a narração do A-roll continua por baixo.
        # É cutaway, não troca de cena.
        if b.get("kind") == "video":
            blocks.append(f'<video id="broll{i}" {attrs} src="{b["src"]}" muted playsinline></video>')
        else:
            blocks.append(f'<img id="broll{i}" {attrs} src="{b["src"]}" alt="">')
    counts["broll"] = len(blocks)

    n = 0
    for i, c in enumerate(data.get("chapters") or []):
        w = window(c, "chapters", end_cap)
        if not w:
            continue
        blocks.append(
            f'<div id="chap{i}" class="ave-lf-chapter clip" data-start="{w[0]:.3f}" '
            f'data-duration="{w[1] - w[0]:.3f}" data-track-index="2">'
            f'<div class="lf-rule"></div>'
            f'<div class="lf-title">{esc(c.get("title", ""))}</div></div>')
        n += 1
    counts["chapters"] = n

    n = 0
    for i, l in enumerate(data.get("lowerThirds") or []):
        w = window(l, "lowerThirds", end_cap)
        if not w:
            continue
        title = (f'<div class="lf-title">{esc(l["title"])}</div>'
                 if l.get("title") else "")
        blocks.append(
            f'<div id="lower{i}" class="ave-lf-lower clip" data-start="{w[0]:.3f}" '
            f'data-duration="{w[1] - w[0]:.3f}" data-track-index="3">'
            f'<div class="lf-bar"></div><div class="lf-box">'
            f'<div class="lf-name">{esc(l.get("name", ""))}</div>{title}</div></div>')
        n += 1
    counts["lowerThirds"] = n

    n = 0
    for i, c in enumerate(data.get("callouts") or []):
        w = window(c, "callouts", end_cap)
        if not w:
            continue
        x, y = float(c.get("x", 0.5)) * 100, float(c.get("y", 0.3)) * 100
        blocks.append(
            f'<div id="call{i}" class="ave-lf-callout clip" data-start="{w[0]:.3f}" '
            f'data-duration="{w[1] - w[0]:.3f}" data-track-index="4" '
            f'style="left:{x:.2f}%; top:{y:.2f}%">{esc(c.get("text", ""))}</div>')
        n += 1
    counts["callouts"] = n
    return blocks, counts


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edit_data", type=Path)
    ap.add_argument("--video", default="cut.mp4")
    ap.add_argument("-o", "--output", type=Path, required=True)
    ap.add_argument("--end", type=float, default=None)
    args = ap.parse_args()

    data = json.loads(args.edit_data.read_text())
    W, H = data.get("width", 1920), data.get("height", 1080)
    accent = data.get("accent") or "#FF6B1A"

    proj = args.output.parent
    proj.mkdir(parents=True, exist_ok=True)
    (proj / "styles").mkdir(exist_ok=True)
    for f in ("longform.css", "longform.js"):
        shutil.copy2(STYLES_DIR / f, proj / "styles" / f)

    src = proj / args.video
    duration = video_duration(src) if src.exists() else float(data["durationSec"])
    declared = float(data.get("durationSec", duration))
    if abs(declared - duration) > 0.5:
        print(f"  aviso: durationSec ({declared:.2f}s) diverge do stream de vídeo "
              f"({duration:.2f}s) — usando o stream", file=sys.stderr)
    if args.end:
        duration = min(duration, args.end)

    blocks, counts = layers(data, duration)
    body = "\n".join("  " + b for b in blocks)

    args.output.write_text(f"""<!doctype html>
<html lang="pt-BR" data-resolution="landscape">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width={W}, height={H}" />
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@600;900&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<link rel="stylesheet" href="styles/longform.css">
<script src="styles/longform.js"></script>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html, body {{ width:{W}px; height:{H}px; overflow:hidden; background:#000; }}
  #a-roll {{ position:absolute; inset:0; width:100%; height:100%; object-fit:cover; }}
</style>
</head>
<body>
<div id="root" class="ave-lf" data-composition-id="main" data-start="0"
     data-duration="{duration:.3f}" data-width="{W}" data-height="{H}"
     style="--lf-scale:1; --lf-accent:{accent}">

  <video id="a-roll" class="clip" src="{args.video}" muted playsinline
         data-start="0" data-duration="{duration:.3f}" data-track-index="0"></video>
  <!-- O `id` do áudio NÃO é opcional: sem ele o renderer não descobre o
       elemento e o vídeo sai MUDO, sem erro em lugar nenhum além do linter. -->
  <audio id="a-roll-audio" src="{args.video}" data-start="0"
         data-duration="{duration:.3f}" data-track-index="9" data-volume="1"></audio>

{body}
</div>

<script>
  window.__timelines = window.__timelines || {{}};
  var tl = gsap.timeline({{ paused: true }});
  AVE_LONGFORM.buildTimeline(document.getElementById('root'), gsap, tl, 1);
  window.__timelines["main"] = tl;
</script>
</body>
</html>
""")

    print(f"{args.output}")
    print(f"  {W}x{H} · accent {accent} · duração {duration:.3f}s (stream de vídeo)")
    print("  camadas: " + " · ".join(f"{k} {v}" for k, v in counts.items()))


if __name__ == "__main__":
    main()

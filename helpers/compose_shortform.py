#!/usr/bin/env python3
"""Monta a composição HyperFrames da Fase 2 short-form a partir dos dados.

Contrato: TUDO que o vídeo é sai de `edit-data.json` + `captions.json` + o
estilo escolhido na aba Estilo. Nada de decisão visual aqui dentro — a
aparência mora em `assets/styles/<estilo>.css`, que é o MESMO arquivo que a
prévia do editor lê. Um estilo escrito aqui e não lá volta a criar a
divergência prévia/render que o SKILL.md registra como anti-padrão.

    uv run python helpers/compose_shortform.py <edit>/remotion/public/edit-data.json \\
        --captions <edit>/remotion/public/captions.json \\
        --video cut.mp4 -o <projeto>/index.html
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from text_measure import group_by_width  # noqa: E402

SKILL_DIR = Path(__file__).resolve().parent.parent
STYLES_DIR = SKILL_DIR / "assets" / "styles"

# Cada estilo declara a fonte com que ele MEDE — que precisa ser a mesma com
# que ele desenha, senão o agrupamento por largura mente.
STYLES = {
    "karaoke": {
        "css": "karaoke.css",
        "js": "karaoke.js",
        "family": "Poppins",
        "weight": 900,
        "gfont": "family=Poppins:wght@900",
        "gap_em": 18 / 76,   # --cap-gap sobre --cap-size, para a conta bater com o CSS
    },
}


def video_duration(path: Path) -> float:
    """Duração do stream de VÍDEO, nunca do container nem do áudio decodificado.

    Medido no cut.mp4 do longform "Fome de Poder": vídeo 786.167s, mas o decode
    do áudio entrega 789.184s COM SINAL — 3s de som além do fim da imagem, sem
    que o container reflita. Uma composição que tirasse a duração do áudio
    ganharia 3s de preto no fim.
    """
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=duration", "-of",
         "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def build_lines(words: list[dict], cfg: dict, style: dict, fps: int,
                end_cap: float) -> list[dict]:
    """Agrupa palavras em linhas e resolve o tempo de cada uma.

    O agrupamento é por LARGURA MEDIDA com `maxWords` só como teto — a regra
    que a referência de short-form chama de "o ponto inteiro" dos estilos
    estáticos e vale para todos: "inteligência" e "de" não cabem na mesma regra.
    """
    size = cfg.get("fontSize", 76)
    groups = group_by_width(
        words, style["family"], size,
        safe_width=cfg.get("safeWidth", 720),
        max_words=cfg.get("maxWords", 3),
        weight=style["weight"],
        space_em=style["gap_em"],
    )
    hold = 0.6  # AVE_KARAOKE.TIMING.HOLD — a linha sobra depois da última palavra
    out = []
    for i, g in enumerate(groups):
        start = g[0]["startMs"] / 1000
        natural = g[-1]["endMs"] / 1000 + hold
        # A linha vive até a próxima começar (menos um frame, senão os dois
        # clipes ocupam a mesma trilha no mesmo instante e o linter reprova),
        # mas nunca além da sua sobra natural — senão ela fica pendurada num
        # silêncio longo.
        nxt = groups[i + 1][0]["startMs"] / 1000 - 1 / fps if i + 1 < len(groups) else end_cap
        end = min(natural, nxt, end_cap)
        if end <= start:
            continue
        out.append({"start": start, "end": end, "words": [w["text"] for w in g]})
    return out


def render_html(data: dict, lines: list[dict], style: dict, style_id: str,
                video: str, duration: float) -> str:
    W, H = data.get("width", 1080), data.get("height", 1920)
    cfg = data.get("captions", {})
    blocks = []
    for i, ln in enumerate(lines):
        spans = "".join(f"<span>{w}</span>" for w in ln["words"])
        blocks.append(
            f'<div class="ave-cap-line clip" data-start="{ln["start"]:.3f}" '
            f'data-duration="{ln["end"] - ln["start"]:.3f}" data-track-index="1">'
            f'{spans}</div>'
        )
    return f"""<!doctype html>
<html lang="pt-BR" data-resolution="portrait">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width={W}, height={H}" />
<link href="https://fonts.googleapis.com/css2?{style['gfont']}&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<link rel="stylesheet" href="styles/{style['css']}">
<script src="styles/{style['js']}"></script>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html, body {{ width:{W}px; height:{H}px; overflow:hidden; background:#000; }}
  #a-roll {{ position:absolute; inset:0; width:100%; height:100%; object-fit:cover; }}
</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{duration:.3f}"
     data-width="{W}" data-height="{H}">

  <video id="a-roll" class="clip" src="{video}" muted playsinline
         data-start="0" data-duration="{duration:.3f}" data-track-index="0"></video>
  <!-- Áudio como trilha própria, do mesmo arquivo. Medido: drift zero em 78s e
       em 786s — o remux em ffmpeg que o Remotion exigia não é necessário.
       O `id` NÃO é opcional: sem ele o renderer não descobre o elemento e o
       vídeo sai MUDO, sem erro em lugar nenhum além do linter. -->
  <audio id="a-roll-audio" src="{video}" data-start="0" data-duration="{duration:.3f}"
         data-track-index="9" data-volume="1"></audio>

  <div class="ave-cap {style_id}" style="--cap-scale:1;
       --cap-size:{cfg.get('fontSize', 76)};
       --cap-bottom:{cfg.get('paddingBottom', 430)}">
{chr(10).join('    ' + b for b in blocks)}
  </div>
</div>

<script>
  window.__timelines = window.__timelines || {{}};
  var tl = gsap.timeline({{ paused: true }});
  // A timeline é montada pelo MESMO módulo que a prévia do editor usa; aqui só
  // se diz onde ela mora. Tween declarativo em tempo absoluto = seekable.
  AVE_KARAOKE.buildTimeline(document.getElementById('root'), gsap, tl, 1);
  window.__timelines["main"] = tl;
</script>
</body>
</html>
"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edit_data", type=Path)
    ap.add_argument("--captions", type=Path, required=True)
    ap.add_argument("--video", default="cut.mp4", help="caminho do A-roll DENTRO do projeto")
    ap.add_argument("-o", "--output", type=Path, required=True, help="<projeto>/index.html")
    ap.add_argument("--style", default=None, help="sobrepõe captions.style do edit-data")
    ap.add_argument("--end", type=float, default=None, help="corta a composição (probe)")
    args = ap.parse_args()

    data = json.loads(args.edit_data.read_text())
    cfg = data.get("captions", {})
    style_id = args.style or cfg.get("style", "karaoke")
    if style_id not in STYLES:
        sys.exit(f"estilo '{style_id}' ainda não portado. Disponíveis: {', '.join(STYLES)}")
    style = STYLES[style_id]

    proj = args.output.parent
    proj.mkdir(parents=True, exist_ok=True)
    dst = proj / "styles"
    dst.mkdir(exist_ok=True)
    for key in ("css", "js"):
        shutil.copy2(STYLES_DIR / style[key], dst / style[key])

    src_video = proj / args.video
    duration = video_duration(src_video) if src_video.exists() else float(data["durationSec"])
    declared = float(data.get("durationSec", duration))
    if abs(declared - duration) > 0.5:
        print(f"  aviso: durationSec do edit-data ({declared:.2f}s) diverge do stream "
              f"de vídeo ({duration:.2f}s) — usando o stream", file=sys.stderr)
    if args.end:
        duration = min(duration, args.end)

    fps = data.get("fps", 30)
    words = [w for w in json.loads(args.captions.read_text())
             if w["startMs"] / 1000 < duration]
    lines = build_lines(words, cfg, style, fps, duration) if cfg.get("enabled", True) else []

    args.output.write_text(render_html(data, lines, style, style_id, args.video, duration))

    sizes = [len(l["words"]) for l in lines]
    hist = {n: sizes.count(n) for n in sorted(set(sizes))}
    print(f"{args.output}")
    print(f"  estilo {style_id} · {style['family']} {style['weight']} @ "
          f"{cfg.get('fontSize', 76)}px · safeWidth {cfg.get('safeWidth', 720)}")
    print(f"  {len(words)} palavras → {len(lines)} linhas · "
          f"palavras por linha: {hist} (teto {cfg.get('maxWords', 3)})")
    print(f"  duração {duration:.3f}s (stream de vídeo)")


if __name__ == "__main__":
    main()

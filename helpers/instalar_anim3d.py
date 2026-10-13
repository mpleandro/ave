#!/usr/bin/env python3
"""Instala o que a "Animação em 3D" precisa — sozinho, na primeira vez.

    uv run python helpers/instalar_anim3d.py            # instala o que faltar
    uv run python helpers/instalar_anim3d.py --check    # só diz se está pronto (exit 0/1)

O formato "Animação em 3D" da aba Estilo usa duas bibliotecas pesadas que o
resto do Avelin não precisa, por isso elas são um extra opcional (`anim3d` no
pyproject) e não vêm na instalação base:

  · MediaPipe — 21 pontos por mão, 33 do corpo, malha do rosto. É o que desenha
    o esqueleto das mãos e prende objetos 3D nas palmas.
  · Depth Anything V2 (via transformers + torch) — mapa de profundidade por
    quadro. É o que pinta o fundo de "perto quente / longe frio", vira malha e
    nuvem de pontos.

Quem escolhe o formato na tela não deveria ter de abrir um terminal. O
`phase2.py` chama este arquivo antes de qualquer coisa quando o formato é
`anim3d`, e o servidor do editor também, logo no salvar.

Três cuidados, cada um com um defeito por trás:

  1. `uv sync --inexact`. Um `uv sync --extra anim3d` puro DESINSTALA os extras
     que não foram citados — quem tinha o `matting` (o recorte da pessoa)
     perderia o torch e o RVM no mesmo clique que pediu 3D.
  2. Os modelos são baixados AQUI, não no primeiro render. Um download de
     ~100 MB no meio da Fase 2 parece travamento; aqui ele tem uma linha de
     progresso dizendo o que está acontecendo.
  3. A conferência roda num processo NOVO. Pacote recém-instalado no mesmo
     interpretador que já importou numpy pode carregar meio-a-meio; um
     subprocesso limpo diz a verdade sobre a próxima execução.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
MODELOS = Path.home() / ".avelin" / "modelos"
MP_DIR = MODELOS / "mediapipe"
DEPTH_MODEL = "depth-anything/Depth-Anything-V2-Small-hf"

# Modelos do MediaPipe Tasks (a API "solutions" antiga foi aposentada).
MP_MODELS = {
    "hand_landmarker.task":
        "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task",
    "pose_landmarker_lite.task":
        "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task",
    "selfie_segmenter.tflite":
        "https://storage.googleapis.com/mediapipe-models/image_segmenter/selfie_segmenter/float16/latest/selfie_segmenter.tflite",
    "face_landmarker.task":
        "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task",
}

SMOKE = f"""
import numpy as np
import mediapipe as mp
from PIL import Image
from transformers import pipeline
from mediapipe.tasks.python import vision, BaseOptions
opts = vision.HandLandmarkerOptions(base_options=BaseOptions(model_asset_path={str(MP_DIR / 'hand_landmarker.task')!r}))
vision.HandLandmarker.create_from_options(opts).close()
pipe = pipeline("depth-estimation", model={DEPTH_MODEL!r})
out = pipe(Image.fromarray(np.zeros((64, 64, 3), dtype=np.uint8)))
assert out["depth"].size[0] > 0
print("ok", mp.__version__)
"""


def say(msg: str) -> None:
    print(f"[anim3d] {msg}", flush=True)


def python_do_projeto() -> str:
    venv = SKILL / ".venv" / "bin" / "python"
    return str(venv) if venv.exists() else sys.executable


def pacotes_ok(py: str) -> bool:
    r = subprocess.run([py, "-c", "import mediapipe, transformers, torch"],
                       capture_output=True, text=True)
    return r.returncode == 0


def modelos_mp_ok() -> bool:
    return all((MP_DIR / n).exists() and (MP_DIR / n).stat().st_size > 0 for n in MP_MODELS)


def achar_uv() -> str | None:
    for c in (shutil.which("uv"), str(Path.home() / ".local/bin/uv"),
              "/opt/homebrew/bin/uv", "/usr/local/bin/uv"):
        if c and Path(c).exists():
            return c
    return None


def instalar_pacotes() -> None:
    uv = achar_uv()
    if uv:
        say("instalando MediaPipe + Depth Anything (uv sync --extra anim3d --inexact)…")
        cmd = [uv, "sync", "--extra", "anim3d", "--inexact"]
        r = subprocess.run(cmd, cwd=SKILL)
    else:
        say("uv não encontrado — instalando com pip no ambiente atual…")
        r = subprocess.run([python_do_projeto(), "-m", "pip", "install",
                            "mediapipe>=0.10.14", "transformers>=4.45", "torch", "torchvision"])
    if r.returncode != 0:
        sys.exit("[anim3d] a instalação falhou — veja as linhas acima.")


def baixar_modelos_mp() -> None:
    MP_DIR.mkdir(parents=True, exist_ok=True)
    for nome, url in MP_MODELS.items():
        dst = MP_DIR / nome
        if dst.exists() and dst.stat().st_size > 0:
            continue
        say(f"baixando modelo do MediaPipe: {nome}")
        tmp = dst.with_suffix(".part")
        urllib.request.urlretrieve(url, tmp)
        tmp.replace(dst)


def conferir(py: str) -> tuple[bool, str]:
    say("conferindo (carrega o rastreio de mãos e o modelo de profundidade)…")
    env = {**os.environ, "HF_HUB_DISABLE_PROGRESS_BARS": "1"}
    r = subprocess.run([py, "-c", SMOKE], capture_output=True, text=True, env=env)
    out = (r.stdout + r.stderr).strip().splitlines()
    return r.returncode == 0, (out[-1] if out else "")


def status(py: str) -> dict:
    return {"pacotes": pacotes_ok(py), "modelos_mediapipe": modelos_mp_ok(),
            "python": py, "modelos": str(MODELOS)}


def garantir() -> bool:
    """Para os outros helpers: instala o que faltar e devolve True quando pronto."""
    py = python_do_projeto()
    if not pacotes_ok(py):
        instalar_pacotes()
    baixar_modelos_mp()
    ok, linha = conferir(py)
    say("pronto ✓" if ok else f"a conferência falhou: {linha}")
    return ok


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="só confere; exit 0 se pronto")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    py = python_do_projeto()
    if a.check:
        st = status(py)
        pronto = st["pacotes"] and st["modelos_mediapipe"]
        print(json.dumps({**st, "pronto": pronto}, ensure_ascii=False) if a.json
              else ("pronto" if pronto else "faltando: " + ", ".join(
                  k for k in ("pacotes", "modelos_mediapipe") if not st[k])))
        sys.exit(0 if pronto else 1)
    sys.exit(0 if garantir() else 1)


if __name__ == "__main__":
    main()

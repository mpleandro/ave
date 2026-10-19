"""A capa de cada corte na galeria: um frame logo depois do início.

0,3s depois do start, não no start: o primeiro quadro de uma frase costuma
pegar a boca fechada ou o piscar entre duas falas.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


def gerar(video: Path, cortes: list[dict], pasta: Path, largura: int = 360) -> None:
    pasta.mkdir(parents=True, exist_ok=True)
    for c in cortes:
        alvo = pasta / f"{c['id']}_{c['start']:.2f}.jpg"
        if not alvo.exists():
            subprocess.run(
                ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                 "-ss", f"{c['start'] + 0.3:.3f}", "-i", str(video), "-frames:v", "1",
                 "-vf", f"scale={largura}:-2", "-q:v", "4", str(alvo)], check=True)
        c["thumb"] = alvo.name

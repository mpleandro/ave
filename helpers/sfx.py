#!/usr/bin/env python3
"""Mede um arquivo de efeito ANTES de usá-lo, e compensa o silêncio inicial.

Dois defeitos que a referência de short-form documenta como já vividos, e que só
aparecem ouvindo — a mixagem parece certa e não se escuta nada:

1. NÍVEL. O `click2.mp3` do pacote tem pico de −25 dB: inaudível sob fala em
   qualquer volume sensato. Medido aqui, confere. O `cut-click.mp3` (−2 dB) é o
   que lê.

2. ONDE está o ataque DENTRO do arquivo. Medido neste pacote: `caption-click`
   tem 158ms de silêncio antes da batida, `caption-scratch` 233ms, `pop` 140ms.
   Agendar o arquivo no instante do evento faz o som chegar 158ms atrasado —
   depois de um efeito de 230ms já ter acabado. A compensação é começar o
   arquivo ANTES, para o ataque cair no lugar.

    uv run python helpers/sfx.py assets/sfx/*.mp3
"""
from __future__ import annotations

import argparse
import functools
import re
import subprocess
import sys
from pathlib import Path

QUIET_DB = -12.0  # abaixo disso, o efeito some sob a fala


@functools.lru_cache(maxsize=64)
def probe(path: str) -> dict:
    """(pico em dB, duração, silêncio inicial em segundos)."""
    p = Path(path)
    vol = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(p), "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True,
    ).stderr
    m = re.search(r"max_volume:\s*(-?[\d.]+) dB", vol)
    peak = float(m.group(1)) if m else 0.0

    dur = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(p)],
        capture_output=True, text=True,
    ).stdout.strip()

    sil = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(p),
         "-af", "silencedetect=n=-30dB:d=0.01", "-f", "null", "-"],
        capture_output=True, text=True,
    ).stderr
    # `silence_end` só existe se o arquivo COMEÇAR em silêncio; sem isso o
    # ataque está em 0 e não há nada a compensar
    starts_silent = bool(re.search(r"silence_start:\s*0(\.0+)?\b", sil))
    lead = 0.0
    if starts_silent:
        e = re.search(r"silence_end:\s*([\d.]+)", sil)
        lead = float(e.group(1)) if e else 0.0

    return {"peak": peak, "duration": float(dur or 0), "lead": lead,
            "quiet": peak < QUIET_DB}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path)
    args = ap.parse_args()
    bad = 0
    for f in args.files:
        d = probe(str(f))
        flag = "  ← BAIXO DEMAIS, some sob a fala" if d["quiet"] else ""
        lead = f"  ataque em {d['lead'] * 1000:.0f}ms" if d["lead"] > 0.005 else ""
        print(f"{f.name:22} pico {d['peak']:6.1f} dB   {d['duration']:.2f}s{lead}{flag}")
        bad += d["quiet"]
    if bad:
        print(f"\n{bad} arquivo(s) abaixo de {QUIET_DB:g} dB — trocar antes de usar",
              file=sys.stderr)


if __name__ == "__main__":
    main()

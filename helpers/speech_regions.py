"""Print true acoustic speech regions of a video using ffmpeg silencedetect.

PHASE 1 cut helper. Whisper word timestamps drift and STRETCH a word's end
across following silence, so they are unreliable for cut points. This runs
silencedetect on the source audio and prints the speech intervals (the
complement of the detected silences) — the acoustic truth to snap cuts to.

Snap each segment's START to a speech onset (a region start) and its END to a
speech offset (a region end), with a tiny lead (~30ms) and a decay-preserving
trail (~60ms) so the last letter/sibilant is never clipped.

**`--min-speech` is a trap for cut points — keep it near zero when the answer
feeds a CUT.** It drops speech regions shorter than the floor, which reads as
tidying and behaves as deletion: a plosive burst ("Go-" in "Gostei") or a
one-syllable word in a fast burst ("que", "de", "te") is 0.08–0.14s long. Drop
it and two things break at once — a start snapped to the "next" region begins
*after* the word, and the silence between the surviving regions swallows the
words in between, so a caller looking for dead air measures a 0.6s pause that
never existed. That second failure ate 11 of 24 breaths in one take. The floor
exists for READING an inventory, where a stray 40ms blip is noise; the default
is deliberately low so that using it wrong costs a row on screen, not a word in
the render.

Usage:
    python helpers/speech_regions.py <video>
    python helpers/speech_regions.py <video> --noise -33dB --min-silence 0.10
    python helpers/speech_regions.py <video> --start 30 --end 40
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# API IMPORTÁVEL — o silêncio MEDIDO, para quem precisa dele como dado e não
# como texto no stdout.
#
# Existe porque o `transcribe.py` passou a depender disto. O adaptador do Groq
# reconstruía o token `spacing` a partir do gap entre palavras do PRÓPRIO
# Whisper (`s > prev_end`), e esse número é sempre 0.00: o Whisper entrega uma
# timeline contígua e absorve a pausa na DURAÇÃO da palavra anterior. Medido num
# take de 60s: 10 tokens `spacing` para 14 silêncios reais, e os 8 ausentes eram
# exatamente os que caíam dentro de uma palavra — invisíveis para o
# `pack_transcripts`, que é a única coisa que o editor lê. Seis defeitos de fala
# passaram para o corte final por causa disso.
#
# A regra que sai daí, e que vale para o pipeline inteiro: **silêncio se mede no
# áudio, nunca no transcrito.**
# ---------------------------------------------------------------------------


def measured_silences(
    video: Path,
    min_silence: float = 0.12,
    noise_db: float | None = None,
) -> list[tuple[float, float]]:
    """Os silêncios REAIS do áudio, em segundos. A fonte de verdade.

    `noise_db=None` calibra o limiar no próprio material via
    `cut_words.noise_floor_for()` — o ponto médio entre o piso de ruído e a
    mediana da voz. Um limiar fixo de −33 dBFS chama de silêncio quem fala a
    −41, o que é metade dos projetos desta série.

    `min_silence` é deliberadamente baixo (0.12s). Quem consome decide o que é
    grande demais para deixar passar; esta função não filtra por gosto, só mede.
    """
    if noise_db is None:
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from cut_words import noise_floor_for  # noqa: PLC0415
            noise_db = noise_floor_for(video)
        except Exception:
            # Sem calibração o padrão histórico da skill ainda é melhor que nada.
            noise_db = -33.0
    return _silences_ffmpeg(video, f"{noise_db:.1f}dB", min_silence)


def _silences_ffmpeg(video: Path, noise: str, min_silence: float) -> list[tuple[float, float]]:
    """silencedetect, com o pareamento start/end feito na ordem em que sai.

    Não reusa `detect_silences()` abaixo porque aquela devolve `(s, s)` quando o
    arquivo termina em silêncio — um intervalo de duração zero, que para o
    consumidor de `measured_silences` seria um vão inexistente.
    """
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(video),
         "-af", f"silencedetect=noise={noise}:d={min_silence}", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    out: list[tuple[float, float]] = []
    start: float | None = None
    for line in proc.stderr.splitlines():
        m = re.search(r"silence_start:\s*(-?[\d.]+)", line)
        if m:
            start = max(0.0, float(m.group(1)))
            continue
        m = re.search(r"silence_end:\s*([\d.]+)", line)
        if m and start is not None:
            end = float(m.group(1))
            if end > start:
                out.append((start, end))
            start = None
    return out


def detect_silences(video: Path, noise: str, min_silence: float) -> list[tuple[float, float]]:
    cmd = [
        "ffmpeg", "-hide_banner", "-i", str(video),
        "-af", f"silencedetect=noise={noise}:d={min_silence}",
        "-f", "null", "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    text = proc.stderr
    starts = [float(m) for m in re.findall(r"silence_start:\s*([\d.]+)", text)]
    ends = [float(m) for m in re.findall(r"silence_end:\s*([\d.]+)", text)]
    # pair them; a leading silence_start at 0 may have no preceding speech
    pairs: list[tuple[float, float]] = []
    ei = 0
    for s in starts:
        # find the first end greater than s
        while ei < len(ends) and ends[ei] <= s:
            ei += 1
        e = ends[ei] if ei < len(ends) else None
        pairs.append((s, e if e is not None else s))
    return pairs


def speech_regions(video: Path, noise: str, min_silence: float,
                   min_speech: float = 0.05) -> list[tuple[float, float]]:
    # total duration
    dur = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nokey=1:noprint_wrappers=1", str(video)],
        capture_output=True, text=True).stdout.strip() or 0.0)

    silences = detect_silences(video, noise, min_silence)
    # Build speech regions = gaps between silences
    regions: list[tuple[float, float]] = []
    cursor = 0.0
    for s_start, s_end in silences:
        if s_start > cursor:
            regions.append((cursor, s_start))
        cursor = max(cursor, s_end)
    if cursor < dur:
        regions.append((cursor, dur))
    # drop tiny blips
    return [(a, b) for a, b in regions if (b - a) >= min_speech]


def main() -> None:
    ap = argparse.ArgumentParser(description="Print acoustic speech regions (silencedetect)")
    ap.add_argument("video", type=Path)
    ap.add_argument("--noise", default="-33dB", help="silence threshold (default -33dB)")
    ap.add_argument("--min-silence", type=float, default=0.10, help="min silence seconds (default 0.10)")
    # 0.05 e não 0.15: ver o aviso no topo. Uma plosiva ou uma palavra de uma
    # sílaba tem 0,08–0,14s, e o piso antigo as descartava — o que fazia esta
    # ferramenta MENTIR justamente sobre os pontos onde ela é usada para cortar.
    ap.add_argument("--min-speech", type=float, default=0.05, help="drop speech regions shorter than this")
    ap.add_argument("--start", type=float, default=0.0, help="only show regions overlapping [start,end]")
    ap.add_argument("--end", type=float, default=None)
    args = ap.parse_args()

    if not args.video.exists():
        sys.exit(f"not found: {args.video}")

    regions = speech_regions(args.video, args.noise, args.min_silence, args.min_speech)
    hi = args.end if args.end is not None else 1e9
    print(f"speech regions (noise={args.noise}, min_silence={args.min_silence}s):")
    for a, b in regions:
        if b < args.start or a > hi:
            continue
        print(f"  {a:8.2f} -> {b:8.2f}   ({b - a:5.2f}s)")


if __name__ == "__main__":
    main()

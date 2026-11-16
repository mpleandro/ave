"""Person matting → a transparent-background foreground video, for the
"element behind the subject" effect (text/image sits between the person and the
background).

Robust Video Matting (RVM) — recurrent video matting with clean, temporally
stable hair edges — now run through `matte_engine.py`, which picks the fastest
backend on THIS machine (CoreML / torch MPS on a Mac, onnxruntime DirectML or
CUDA on Windows, onnxruntime CPU anywhere — no torch required).

Writes the light MASK first (H.264 gray) and derives the alpha file from it:
ProRes 4444 `.mov` by default — the format the Phase-2 renderer reliably
decodes with alpha. `.webm` (VP9 alpha) is honored but libvpx on some ffmpeg
builds silently drops the alpha (verified again on 2026-11-16) — check it.

Usage:
    python helpers/person_matte.py preview.mp4 -o hyperframes/fg.mov
    python helpers/person_matte.py preview.mp4 -o fg.mov --model resnet50   # rvm-hq
    python helpers/person_matte.py preview.mp4 -o fg.mov --start 8 --duration 6
    python helpers/person_matte.py preview.mp4 -o fg.mov --fgr      # person over a NEW background
    python helpers/person_matte.py preview.mp4 --mask-only -o m.mp4 # just the mask
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import matte_engine as ME  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="Matte the person out of a video (RVM)")
    ap.add_argument("video", type=Path)
    ap.add_argument("-o", "--output", type=Path, required=True,
                    help="alpha .mov (ProRes 4444) / .webm, or the mask .mp4 with --mask-only")
    ap.add_argument("--model", choices=["mobilenetv3", "resnet50"], default="mobilenetv3",
                    help="mobilenetv3 = fast/good (default); resnet50 = best edges, slower")
    ap.add_argument("--backend", choices=["auto", *ME.MOTORES], default="auto",
                    help="auto = fastest measured on this machine (matte_engine.py bench)")
    ap.add_argument("--start", type=float, default=0.0, help="Start time (s)")
    ap.add_argument("--duration", type=float, default=None, help="Duration (s); default = to end")
    ap.add_argument("--mask-only", action="store_true", help="write only the gray mask .mp4")
    ap.add_argument("--fgr", action="store_true",
                    help="cor DESCONTAMINADA do RVM em vez da fonte — para pôr a pessoa "
                         "sobre um fundo DIFERENTE. Com a cor da fonte, a borda do cabelo "
                         "carrega a parede original e vira halo claro sobre fundo escuro")
    args = ap.parse_args()
    if args.backend != "auto":
        os.environ["AVE_RECORTE_BACKEND"] = args.backend

    out = args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    mascara = out if args.mask_only else out.with_suffix(".mask.mp4")
    cor = out.with_suffix(".cor.mp4") if args.fgr else None
    ME.recortar(args.video, mascara, motor=args.model, start=args.start,
                dur=args.duration, cor=cor)
    if args.mask_only:
        print(f"done: {mascara}")
        return
    if out.suffix.lower() == ".webm":
        print("warning: VP9 alpha WebM — verify alpha survived; .mov/ProRes is safer")
        src = cor or args.video
        ss, _ = ME._janela(0 if cor else args.start, None, ME.sonda(src)[2])
        subprocess.run(["ffmpeg", "-v", "error", "-y", *ss, "-i", str(src),
                        "-i", str(mascara), "-filter_complex",
                        "[1:v]format=gray[m];[0:v][m]alphamerge,format=yuva420p[v]",
                        "-map", "[v]", "-an", "-shortest", "-c:v", "libvpx-vp9", "-b:v", "0",
                        "-crf", "20", "-auto-alt-ref", "0", "-metadata:s:v:0", "alpha_mode=1",
                        str(out)], check=True)
    elif cor:
        ME.derivar_alfa(cor, mascara, out)
    else:
        ME.derivar_alfa(args.video, mascara, out, start=args.start, dur=args.duration)
    for p in (mascara, cor):
        if p:
            p.unlink(missing_ok=True)
    print(f"done: {out}")


if __name__ == "__main__":
    main()

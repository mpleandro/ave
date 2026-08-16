#!/usr/bin/env python3
"""Encurta o ar morto DENTRO de cada trecho do EDL — a limpeza automática.

    uv run python helpers/propose_breaths.py <edit-dir> [--apply]

Cortar no silêncio resolve o ar morto ENTRE tomadas. O que sobra é o de dentro:
a pausa que a pessoa faz no meio do próprio raciocínio, que nenhuma escolha de
tomada remove porque ela está no meio da tomada escolhida. Num vídeo curto é o
que mais custa retenção, e é o tipo de trabalho que ninguém deveria fazer à mão.

DUAS FAIXAS, e a diferença entre elas é de quem é a decisão:

  - AUTOMÁTICA (aqui): só o que é indefensável. Pausa acima de `--min` (0,60s)
    cai para `--keep` (0,30s). É conservadora de propósito — a máquina remove o
    que qualquer editor removeria, e para aí.
  - MANUAL (chips da aba Transcrição): a partir de 0,20s, com piso de 0,15s. É
    onde mora o gosto, e por isso é decisão do usuário.

O piso automático é MAIOR que o manual justamente porque é automático: errar
para o lado de deixar ar sobrando é recuperável com dois cliques, e errar para o
lado de metralhar a fala obriga a refazer o corte.

**As bordas vêm do detector ACÚSTICO, nunca do Whisper.** O carimbo de fim de
palavra do Whisper se estica pelo silêncio adiante, então medir o respiro por
ele devolveria pausas que não existem e encurtaria por um valor que ninguém
pediu. Aqui o silêncio é o complemento das regiões de fala, medido no áudio.

Sem `--apply` só relata; com `--apply` escreve `breaths[]` nos ranges do
edl.json (o anterior fica em edl.prev.json). O `render.py` expande cada respiro
em dois trechos e FIXA a emenda que criou — sem isso o J-cut comeria o piso.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HELPERS = Path(__file__).resolve().parent

MIN_DEFAULT = 0.60   # abaixo disto a pausa é ritmo, não ar morto
KEEP_DEFAULT = 0.30  # o que fica de respiro depois do encurtamento
EDGE = 0.02          # tolerância ao casar borda de região com borda de trecho


def speech_regions(video: Path, start: float, end: float) -> list[tuple[float, float]]:
    """Regiões de fala acústica dentro de [start, end], via o helper que existe."""
    r = subprocess.run(
        [sys.executable, str(HELPERS / "speech_regions.py"), str(video),
         "--start", str(max(0.0, start)), "--end", str(end),
         "--min-silence", "0.12"],
        capture_output=True, text=True,
    )
    out: list[tuple[float, float]] = []
    for line in r.stdout.splitlines():
        parts = line.replace("->", " ").replace("-", " ").split()
        nums = [p for p in parts if p.replace(".", "", 1).isdigit()]
        if len(nums) >= 2:
            out.append((float(nums[0]), float(nums[1])))
    return out


def gaps_inside(regions: list[tuple[float, float]], a: float, b: float,
                min_dur: float) -> list[tuple[float, float]]:
    """Silêncios INTERNOS ao trecho, acima do limiar.

    Só o que está entre duas falas. O silêncio que encosta na borda do trecho
    não entra: aquele é a folga do corte, e mexer nele é assunto do J-cut e do
    pad de borda — dois donos no mesmo silêncio é como um deles some.
    """
    dentro = [(s, e) for s, e in regions if e > a + EDGE and s < b - EDGE]
    dentro.sort()
    out = []
    for (s1, e1), (s2, _e2) in zip(dentro, dentro[1:]):
        dur = s2 - e1
        if dur >= min_dur and e1 > a + EDGE and s2 < b - EDGE:
            out.append((round(e1, 3), round(s2, 3)))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edit", type=Path)
    ap.add_argument("--min", type=float, default=MIN_DEFAULT,
                    help=f"pausa mínima para encurtar (padrão {MIN_DEFAULT}s)")
    ap.add_argument("--keep", type=float, default=KEEP_DEFAULT,
                    help=f"respiro que fica (padrão {KEEP_DEFAULT}s)")
    ap.add_argument("--apply", action="store_true", help="escreve no edl.json")
    args = ap.parse_args()

    edit = args.edit.resolve()
    edl_path = edit / "edl.json"
    if not edl_path.exists():
        sys.exit(f"não achei o edl.json em {edit}")
    edl = json.loads(edl_path.read_text())
    sources = edl.get("sources", {})

    total, ganho = 0, 0.0
    for r in edl.get("ranges", []):
        src = sources.get(r["source"])
        if not src:
            continue
        path = Path(src)
        if not path.is_absolute():
            path = (edit / src).resolve()
        if not path.exists():
            print(f"  ! fonte ausente para {r['source']} — pulado")
            continue
        a, b = float(r["start"]), float(r["end"])
        marcas = []
        for at, to in gaps_inside(speech_regions(path, a, b), a, b, args.min):
            if to - at <= args.keep:
                continue
            marcas.append({"at": at, "to": to, "keep": args.keep})
            ganho += (to - at) - args.keep
            total += 1
        if marcas:
            beat = r.get("beat") or r["source"]
            print(f"  {beat}: {len(marcas)} respiro(s) — "
                  + ", ".join(f"{m['at']:.2f}s ({m['to'] - m['at']:.2f}s)" for m in marcas))
            if args.apply:
                r["breaths"] = marcas

    if not total:
        print(f"nenhuma pausa interna acima de {args.min}s — nada a encurtar")
        return 0

    print(f"\n{total} respiro(s), −{ganho:.1f}s no total "
          f"(limiar {args.min}s → piso {args.keep}s)")
    if args.apply:
        (edit / "edl.prev.json").write_text(
            json.dumps(json.loads(edl_path.read_text()), ensure_ascii=False, indent=2))
        edl_path.write_text(json.dumps(edl, ensure_ascii=False, indent=2))
        print("escrito no edl.json (anterior em edl.prev.json) — refaça o render")
    else:
        print("nada foi escrito — rode com --apply para aplicar")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

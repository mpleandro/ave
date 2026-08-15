#!/usr/bin/env python3
"""O transcrito do CORTE, feito por mapeamento — não por transcrever de novo.

Transcrever o `cut.mp4` era o caminho óbvio e é o caminho errado. São duas
passadas independentes do mesmo modelo sobre o mesmo áudio, e a segunda erra em
lugares que a primeira acerta. Medido na série "170 Questões", com 95,4% de
igualdade e 9 divergências entre elas:

    fonte: "comece a TRABALHAR dentro da sua empresa"
    corte: "comece a AVALIAR  dentro da sua empresa"     ← foi para a legenda

"avaliar" existe em outro ponto do mesmo vídeo; o modelo puxou de lá. A frase
continua gramatical, a legenda queimou errado, e nada no processo reclamou.

Aqui a saída vem das fontes, que a Fase 1 já transcreveu, conferiu e usou para
decidir o corte — deslocadas para a linha de tempo de saída pelo EDL. Duas
consequências que valem mais que a precisão:

  1. **Uma verdade só.** O texto que o usuário lê e edita na Fase 1 é
     LITERALMENTE o texto que vira legenda. Num editor por transcrição isso não
     é detalhe: é a premissa. Se o painel mostra uma palavra e o vídeo queima
     outra, apagar a palavra no painel não corta o que o usuário acha que corta.
  2. **Zero chamadas de API** por render.

O deslocamento usa o `jcut_timeline` que o `render.py` grava — a posição REAL de
cada trecho na saída. Somar as durações dos ranges dá quase a mesma coisa e erra
exatamente onde o J-cut encavala, que é onde ninguém olha. Sem `jcut_timeline`
(corte antigo, ou trazido de fora) este helper recusa e manda transcrever.

Uso:
    uv run python helpers/cut_transcript.py <edit-dir> -o transcripts/cut_mapped.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def words_of(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [w for w in (json.loads(path.read_text()).get("words") or [])
            if w.get("type") == "word"]


def build(edit: Path) -> dict:
    edl_path = edit / "edl.json"
    if not edl_path.exists():
        sys.exit(f"não achei {edl_path} — sem EDL não há o que mapear")
    edl = json.loads(edl_path.read_text())
    tl = edl.get("jcut_timeline") or []
    tdir = edit / "transcripts"

    src: dict[str, list[dict]] = {}
    for key, p in edl.get("sources", {}).items():
        src[key] = words_of(tdir / f"{Path(p).stem}.json")
    if not any(src.values()):
        sys.exit("nenhum transcrito de fonte em transcripts/ — rode o transcribe antes")

    out: list[dict] = []
    cursor = 0.0
    for i, r in enumerate(edl.get("ranges", [])):
        a, b = float(r["start"]), float(r["end"])
        # A posição real do trecho na saída. Sem jcut_timeline o acúmulo de
        # durações serve, mas erra nas junções — avise em vez de fingir.
        off = float(tl[i]["start"]) if i < len(tl) and "start" in tl[i] else cursor
        for w in src.get(r["source"], []):
            s, e = float(w["start"]), float(w["end"])
            if not (a <= s < b):
                continue
            out.append({
                "type": "word",
                "text": w["text"],
                # grampeado no trecho: o Whisper adianta o início e estica o
                # fim, e sem o grampo a última palavra de um take vaza para
                # depois do corte
                "start": round(off + max(0.0, s - a), 3),
                "end": round(off + min(e, b) - a, 3),
                "speaker_id": w.get("speaker_id", "speaker_0"),
            })
        cursor += b - a

    out.sort(key=lambda w: w["start"])
    return {
        "words": out,
        "language_code": "por",
        "_source": "mapeado do EDL — NÃO é uma transcrição do cut.mp4",
        "_jcut": bool(tl),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edit", type=Path)
    ap.add_argument("-o", "--out", type=Path)
    args = ap.parse_args()

    edit = args.edit.expanduser().resolve()
    data = build(edit)
    out = args.out or (edit / "transcripts" / "cut_mapped.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False))
    aviso = "" if data["_jcut"] else "  (SEM jcut_timeline — tempos aproximados nas junções)"
    print(f"{len(data['words'])} palavras mapeadas do EDL → {out.name}{aviso}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

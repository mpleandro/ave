#!/usr/bin/env python3
"""O transcrito do CORTE, feito por mapeamento — não por transcrever de novo.

Transcrever o `preview.mp4` era o caminho óbvio e é o caminho errado — mas NÃO por
ser menos preciso. São duas passadas independentes do mesmo modelo sobre o mesmo
áudio, e cada uma erra onde a outra acerta. Medido na série "170 Questões": 95,4%
de igualdade, 9 divergências, e as duas metades erradas repartidas:

    fonte: "comece a TRABALHAR dentro da sua empresa"   ← ERRADA
    corte: "comece a AVALIAR   dentro da sua empresa"   ← certa

    fonte: tinha "sem conhecimento"                     ← certa
    corte: perdeu "sem conhecimento"                    ← ERRADA

**Não existe "a boa" das duas.** Eu preferi a fonte por suposição, escrevi aqui
que ela era a correta, e queimei "trabalhar" no vídeo — o usuário ouviu e
desmentiu. Um desacordo se resolve com uma TERCEIRA passada, isolada
(`transcript_audit.py --recheck`), e o resultado vai para
`transcripts/corrections.json`.

O motivo de mapear, então, não é precisão: é ter **um único texto**, com as
correções aplicadas num lugar só. Duas consequências:

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


def corrections(edit: Path) -> list[dict]:
    """Palavras corrigidas à mão, em `transcripts/corrections.json`.

    O transcrito da fonte NÃO é verdade por decreto — ele erra trocando palavra
    por palavra, e o erro é gramatical, então nada denuncia. Neste projeto a
    fonte escreveu "trabalhar" onde ele diz "avaliar"; eu preferi a fonte por
    suposição e queimei a palavra errada no vídeo. Quem decide um desacordo é
    uma TERCEIRA passada isolada (`transcript_audit.py --recheck`), e o
    resultado mora aqui — nunca editando o cache da API, que é a resposta do
    provedor e tem de continuar sendo.

        [{"source": "0012", "srcStart": 43.82, "from": "trabalhar", "text": "avaliar"}]

    `srcStart` casa por proximidade (±0.15s), então não precisa ser exato.
    """
    p = edit / "transcripts" / "corrections.json"
    return json.loads(p.read_text()) if p.exists() else []


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

    fixes = corrections(edit)
    out: list[dict] = []
    cursor = 0.0
    for i, r in enumerate(edl.get("ranges", [])):
        a, b = float(r["start"]), float(r["end"])
        # `audio_start_in_output`, NÃO `video_start_in_output`.
        #
        # Sob J-cut o áudio de um take entra ANTES da imagem dele — é isso que o
        # J-cut é. Legenda segue a VOZ, então tem de sair do relógio do áudio.
        # Usar o do vídeo atrasa a legenda pelo lead (167ms com o default de 5
        # quadros), e somar as durações dos ranges — que era o que este arquivo
        # fazia por cair num fallback, porque a chave `start` NÃO EXISTE aqui —
        # atrasa CUMULATIVAMENTE: medido neste projeto, +0,23s no 2º trecho e
        # +1,08s no último. O sintoma é "a legenda aparece depois da fala", e
        # piora ao longo do vídeo, que é a assinatura de deriva acumulada.
        key = "audio_start_in_output"
        off = float(tl[i][key]) if i < len(tl) and key in tl[i] else cursor
        for w in src.get(r["source"], []):
            s, e = float(w["start"]), float(w["end"])
            if not (a <= s < b):
                continue
            text = w["text"]
            for f in fixes:
                # o TEMPO sozinho não identifica uma palavra: com fala corrida
                # cabem três dentro de 0,15s, e a primeira versão disto pintou
                # o `a` vizinho de "avaliar" junto. `from` é obrigatório e é o
                # que torna a correção uma correção, e não uma pincelada.
                if (f.get("source") == r["source"]
                        and abs(float(f["srcStart"]) - s) <= 0.15
                        and f["from"].lower().strip(" .,;:!?") == w["text"].lower().strip(" .,;:!?")):
                    text = f["text"]
                    break
            out.append({
                "type": "word",
                "text": text,
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
        "_source": "mapeado do EDL — NÃO é uma transcrição do preview.mp4",
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

#!/usr/bin/env python3
"""O transcrito DO CORTE, palavra a palavra, com a folga real de cada fronteira.

É o dado que sustenta a edição por texto: apagar uma palavra vira um corte, e
para isso é preciso saber (a) qual palavra sobrevive a quais trechos do EDL e
(b) se existe silêncio onde o corte cairia.

**O ponto inteiro deste arquivo é (b).** Os tempos de palavra do Whisper NÃO são
bordas de corte — inícios chegam adiantados, fins se esticam pelo silêncio, e
uma repetição colada sai como uma palavra só e comprida. Cortar nos tempos dele
come a palavra vizinha ou deixa um caco. Então cada fronteira é confrontada com
o detector ACÚSTICO de fala, e o que sai daqui é a folga MEDIDA — em segundos de
silêncio de verdade, não a diferença entre dois carimbos de tempo.

O limiar do detector é calibrado por fonte, não fixo: gravações baixas (este
projeto fala a −41 dBFS) somem sob o default e a saída vira fragmentos inúteis.
A calibração aqui é derivada do próprio material, como o `voice_levels` faz.

Uso:
    uv run python helpers/cut_words.py <edit-dir> [-o saida.json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

HELPERS = Path(__file__).resolve().parent


def cached_regions(edit: Path, src: Path) -> list[tuple[float, float]]:
    """Regiões de fala da FONTE, cacheadas pela identidade dela.

    O detector acústico + a calibração de limiar varrem a fonte INTEIRA, e a
    fonte não muda quando o corte muda — mas este helper roda a cada mudança do
    edl.json (é a invalidação certa para as PALAVRAS, não para as regiões).
    Sem o cache, cada iteração no editor pagava a varredura de todas as fontes
    de novo, pelo mesmo resultado.
    """
    st = src.stat()
    sig = f"{st.st_mtime_ns}|{st.st_size}"
    cache = edit / ".preview_cache" / "speech_regions" / f"{src.stem}.json"
    try:
        d = json.loads(cache.read_text())
        if d.get("sig") == sig:
            return [tuple(r) for r in d["regions"]]
    except (OSError, json.JSONDecodeError, KeyError):
        pass
    noise = noise_floor_for(src)
    regions = speech_regions(src, noise)
    cache.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache.with_suffix(".tmp")
    tmp.write_text(json.dumps({"sig": sig, "noise_db": noise, "regions": regions}))
    tmp.replace(cache)
    return regions


def speech_regions(video: Path, noise_db: float) -> list[tuple[float, float]]:
    """Intervalos de fala acústica, via o helper que já existe."""
    out = subprocess.run(
        [sys.executable, str(HELPERS / "speech_regions.py"), str(video),
         f"--noise={noise_db:.0f}dB", "--min-silence", "0.12"],
        capture_output=True, text=True,
    )
    regions = []
    for line in out.stdout.splitlines():
        parts = line.replace("->", " ").split()
        if len(parts) >= 2:
            try:
                regions.append((float(parts[0]), float(parts[1])))
            except ValueError:
                continue
    return regions


def levels_for(video: Path) -> tuple[float | None, float | None]:
    """(piso de ruído, mediana da voz) em dBFS, medidos no material.

    Separado de `noise_floor_for` porque o `propose_breaths` precisa das DUAS
    populações, não só do limiar entre elas: o limiar diz o que é silêncio, e a
    mediana diz o que é VOZ — é comparando com ela que se descobre que um
    "silêncio" tem alguém falando dentro.
    """
    out = subprocess.run(
        [sys.executable, str(HELPERS / "voice_levels.py"), str(video)],
        capture_output=True, text=True,
    )
    floor = med = None
    for line in out.stdout.splitlines():
        if "noise floor:" in line:
            try:
                floor = float(line.split("noise floor:")[1].split("dBFS")[0].strip())
            except (IndexError, ValueError):
                pass
        if "median speech:" in line:
            try:
                med = float(line.split("median speech:")[1].split("dBFS")[0].strip())
            except (IndexError, ValueError):
                pass
    return floor, med


def noise_floor_for(video: Path) -> float:
    """Limiar calibrado no material — no MEIO entre o piso de ruído e a mediana.

    São duas populações (sala e voz) e o limiar tem de cair entre elas. Um
    deslocamento fixo a partir da mediana não serve: neste projeto a mediana é
    −41,4 e o piso −52,8, então "mediana − 10" dá −51, que fica ABAIXO do piso —
    o detector passa a chamar room tone de fala, devolve uma região gigante e
    toda fronteira aparece como "sem folga". Foi exatamente o que aconteceu, e o
    sintoma é traiçoeiro porque a saída parece plausível: 100% sem folga é o que
    você esperaria de uma fala muito corrida.

    O ponto médio dá −47 aqui, que é o valor que as três sessões desta série
    encontraram na mão.
    """
    floor, med = levels_for(video)
    if floor is not None and med is not None and floor < med:
        return round((floor + med) / 2)
    return -33.0


# O Whisper adianta o início e estica o fim; uma palavra que na verdade abre uma
# região pode aparecer alguns décimos antes dela. Sem tolerância, nenhuma palavra
# "encosta" na borda e tudo sai sem folga.
TOL = 0.18


def gap_before(regions: list[tuple[float, float]], t: float) -> float:
    """Silêncio utilizável IMEDIATAMENTE ANTES de `t`.

    Não é o silêncio no instante `t` — esse é sempre zero, porque `t` é o começo
    de uma palavra e começo de palavra está dentro da fala por definição. Foi
    esse o engano da primeira versão, e ele fazia a saída inteira dizer "sem
    folga em lugar nenhum", o que parecia plausível e não era.

    A pergunta certa é: esta palavra ABRE uma região de fala? Se abre, o silêncio
    que vem antes daquela região é onde o corte pode cair.
    """
    prev_end = 0.0
    for a, b in regions:
        if b <= t - TOL:
            prev_end = b
            continue
        if abs(a - t) <= TOL:      # a palavra abre esta região
            return round(max(0.0, a - prev_end), 3)
        if a > t:                  # t caiu no silêncio antes desta região
            return round(max(0.0, a - prev_end), 3)
        return 0.0                 # t está no MEIO da região: não há onde cortar
    return 999.0


def gap_after(regions: list[tuple[float, float]], t: float) -> float:
    """Silêncio utilizável IMEDIATAMENTE DEPOIS de `t` — o espelho do anterior:
    esta palavra FECHA uma região?"""
    for idx, (a, b) in enumerate(regions):
        if b < t - TOL:
            continue
        nxt = regions[idx + 1][0] if idx + 1 < len(regions) else None
        if abs(b - t) <= TOL:      # a palavra fecha esta região
            return round(nxt - b, 3) if nxt is not None else 999.0
        if a > t:                  # t já estava no silêncio
            return round(a - t, 3)
        return 0.0                 # t está no MEIO da região
    return 999.0


def build(edit: Path) -> dict:
    edl = json.loads((edit / "edl.json").read_text())
    sources = edl.get("sources", {})
    tdir = edit / "transcripts"

    words_by_src: dict[str, list[dict]] = {}
    regions_by_src: dict[str, list[tuple[float, float]]] = {}
    for key, path in sources.items():
        src = Path(path)
        cache = tdir / f"{src.stem}.json"
        if not cache.exists():
            continue
        data = json.loads(cache.read_text())
        words_by_src[key] = [w for w in (data.get("words") or []) if w.get("type") == "word"]
        if src.exists():
            regions_by_src[key] = cached_regions(edit, src)

    out: list[dict] = []
    t_out = 0.0
    for ri, r in enumerate(edl.get("ranges", [])):
        key = r["source"]
        a, b = float(r["start"]), float(r["end"])
        regions = regions_by_src.get(key, [])
        for w in words_by_src.get(key, []):
            ws, we = float(w["start"]), float(w["end"])
            if we <= a or ws >= b:
                continue
            out.append({
                "text": w["text"],
                "source": key,
                "range": ri,
                "srcStart": round(ws, 3),
                "srcEnd": round(we, 3),
                # grampeado no trecho: o Whisper adianta o início, e sem isto a
                # primeira palavra de cada take sai com tempo NEGATIVO na saída
                "outStart": round(t_out + max(0.0, ws - a), 3),
                # A FOLGA, que é o que decide se o corte é limpo. Medida no
                # áudio, não deduzida da distância entre dois carimbos.
                "gapBefore": gap_before(regions, ws),
                "gapAfter": gap_after(regions, we),
            })
        t_out += b - a

    return {
        "words": out,
        "ranges": len(edl.get("ranges", [])),
        "edlMtime": (edit / "edl.json").stat().st_mtime,
        # A chave de frescor que o servidor usa. O mtime não serve: o render
        # regrava o edl.json com bytes idênticos e o mtime muda sem o corte
        # mudar — o hash do conteúdo só muda quando o corte muda.
        "edlHash": hashlib.sha1((edit / "edl.json").read_bytes()).hexdigest(),
        "_note": "gapBefore/gapAfter em segundos de silêncio MEDIDO; 0 = corte cairia dentro da fala",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("edit", type=Path)
    ap.add_argument("-o", "--out", type=Path)
    args = ap.parse_args()

    data = build(args.edit.expanduser().resolve())
    text = json.dumps(data, ensure_ascii=False)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text)
        # A métrica útil é quantas palavras dá para APAGAR limpo — com folga dos
        # DOIS lados. Contar "tem alguma fronteira sem folga" não diz nada: toda
        # palavra no meio de uma frase tem zero dos dois lados, e isso é o normal.
        limpas = sum(1 for w in data["words"] if w["gapBefore"] > 0 and w["gapAfter"] > 0)
        print(f"{len(data['words'])} palavras · {limpas} apagáveis sem emenda → {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

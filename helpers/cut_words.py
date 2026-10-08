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
import json
import subprocess
import sys
from pathlib import Path

HELPERS = Path(__file__).resolve().parent

# O MESMO leitor e a MESMA régua de correção que a legenda usa. Importado, não
# recopiado: este arquivo alimenta o painel que o usuário LÊ, o `cut_transcript`
# alimenta a legenda que o vídeo QUEIMA, e a Regra 14 do SKILL.md promete que os
# dois textos são o mesmo. Enquanto só a legenda aplicava `corrections.json`, a
# promessa era falsa sempre que houvesse uma correção.
sys.path.insert(0, str(HELPERS))
from cut_transcript import corrections, fix_for  # noqa: E402


# Os parâmetros do detector, num lugar só — eles entram na CHAVE do cache, e
# uma chave que não os contém devolve a medição de outro limiar.
MIN_SILENCE = "0.12"
MIN_SPEECH = "0"


def speech_regions(video: Path, noise_db: float) -> list[tuple[float, float]]:
    """Intervalos de fala acústica, via o helper que já existe — CACHEADO.

    O spawn continua: `speech_regions.py` é um programa com lógica própria e
    trazê-la para dentro daqui seria copiá-la. O que muda é que o resultado
    passa a ser um derivado endereçado pela fonte MAIS o limiar, porque o mesmo
    arquivo medido a −47 dB e a −35 dB dá dois mapas diferentes de fala. Medido:
    2,7s por chamada numa fonte de 3 min, e é o passo que o painel de
    transcrição espera antes de aparecer.
    """
    from derivado import derivado  # noqa: PLC0415
    return derivado(
        "regions", [video],
        {"noise_db": round(float(noise_db), 1),
         "min_silence": MIN_SILENCE, "min_speech": MIN_SPEECH},
        "1", lambda: _medir_regioes(video, noise_db))


def _medir_regioes(video: Path, noise_db: float) -> list[tuple[float, float]]:
    out = subprocess.run(
        [sys.executable, str(HELPERS / "speech_regions.py"), str(video),
         # `--min-speech 0` NÃO É DETALHE AQUI. O piso padrão (0,05s) descarta
         # regiões de fala curtas — uma plosiva, um monossílabo — e o efeito é
         # o oposto de arrumar: sem a região, o silêncio entre as sobreviventes
         # engorda, e este arquivo, cujo propósito inteiro é medir a FOLGA onde
         # o corte cairia, passa a relatar uma folga que não existe. Cortar
         # nela come a palavra que o piso escondeu.
         f"--noise={noise_db:.0f}dB", "--min-silence", MIN_SILENCE,
         "--min-speech", MIN_SPEECH],
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


class SemNiveis(RuntimeError):
    """A medição não aconteceu. Existe como exceção PRÓPRIA para atravessar o
    cache sem ser guardada: `derivado` só grava o que o produtor devolve, então
    uma falha transitória de ffmpeg não pode virar um arquivo em cache que
    responde "sem níveis" para sempre."""


def _medir_niveis(video: Path) -> list[float | None]:
    """As duas populações, calculadas em processo. Devolve [piso, mediana].

    É a MESMA aritmética do `voice_levels.analyze` — `rms_timeline`,
    `estimate_floor`, mediana dos quadros acima do piso — e os dois valores
    saem arredondados a uma decimal porque era assim que chegavam pelo console.
    Reproduzir o arredondamento não é preciosismo: `noise_floor_for` arredonda
    o PONTO MÉDIO dos dois, e uma decimal a mais aqui muda o limiar em 1 dB nos
    casos de fronteira — ou seja, mudaria decisões de corte em silêncio.

    Lista em vez de tupla porque isto atravessa JSON no cache.
    """
    import numpy as np  # noqa: PLC0415 — só quem mede paga o import
    sys.path.insert(0, str(HELPERS))
    from voice_levels import estimate_floor, rms_timeline  # noqa: PLC0415

    # `rms_timeline` chama `sys.exit` quando o ffmpeg falha ou o arquivo não tem
    # faixa de áudio. Como PROGRAMA isso é correto; importado, o SystemExit
    # derrubaria o chamador — que era justamente o que o spawn tolerava. A
    # tolerância tem de sobreviver à mudança, só não em silêncio.
    try:
        _, levels = rms_timeline(video)
    except SystemExit as e:
        raise SemNiveis(str(e)) from e
    floor = estimate_floor(levels)
    fala = levels[levels > floor]
    if fala.size == 0:
        # NÃO `sys.exit`, que é o que o `voice_levels` faz como programa: aqui
        # somos biblioteca, e derrubar o chamador seria pior. Mas também não
        # calado — ver o aviso em `noise_floor_for`.
        return [None, None]
    return [round(float(floor), 1), round(float(np.percentile(fala, 50)), 1)]


def levels_for(video: Path) -> tuple[float | None, float | None]:
    """(piso de ruído, mediana da voz) em dBFS, medidos no material.

    Separado de `noise_floor_for` porque o `propose_breaths` precisa das DUAS
    populações, não só do limiar entre elas: o limiar diz o que é silêncio, e a
    mediana diz o que é VOZ — é comparando com ela que se descobre que um
    "silêncio" tem alguém falando dentro.

    ISTO ERA UM SPAWN COM PARSE DE STDOUT, e o problema não era a lentidão
    (0,8s numa fonte de 3 min, cinco módulos chamando em cinco processos). Era
    que dois floats eram recuperados fazendo `split` no console de outro
    programa: qualquer mudança no formato do `print` — ou uma fonte sem faixa de
    áudio — devolvia `(None, None)`, e o `noise_floor_for` respondia −33,0 dBFS
    **em silêncio**. Medido: numa fonte real o limiar calibrado é −27; o
    fallback dava −33, e o docstring do `noise_floor_for` explica que um limiar
    errado faz toda fronteira aparecer como "sem folga" — saída plausível e
    errada, que é o pior tipo.
    """
    from derivado import derivado  # noqa: PLC0415
    from voice_levels import FRAME  # noqa: PLC0415
    try:
        floor, med = derivado(
            "levels", [video], {"frame": FRAME}, "1", lambda: _medir_niveis(video))
    except SemNiveis:
        return None, None
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
    # O FALLBACK PASSA A FALAR. Ele continua existindo — derrubar o pipeline por
    # causa de uma fonte sem áudio seria pior — mas chegar aqui significa que a
    # calibração NÃO aconteceu, e um limiar não calibrado faz toda fronteira
    # parecer "sem folga": saída plausível, decisões erradas, nada denunciando.
    print(f"aviso: não consegui calibrar o limiar em {video.name} — "
          f"usando -33.0 dBFS fixo, e as folgas medidas daqui saem suspeitas",
          file=sys.stderr)
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

    fixes = corrections(edit)
    words_by_src: dict[str, list[dict]] = {}
    regions_by_src: dict[str, list[tuple[float, float]]] = {}
    for key, path in sources.items():
        # MESMA resolução do `render.py`: absoluto, ou relativo ao <edit>. Aqui
        # era `Path(path)` cru, resolvido contra o diretório de TRABALHO — e um
        # EDL com caminho relativo (que o `render.py` aceita de propósito) fazia
        # `src.exists()` dar falso, o mapa de fala não ser medido, e TODA
        # fronteira reportar folga 999,0: "pode cortar em qualquer lugar". O
        # arquivo inteiro existe para responder essa pergunta, e a resposta
        # errada era a otimista, sem nada denunciando.
        src = Path(path)
        if not src.is_absolute():
            src = (edit / src).resolve()
        cache = tdir / f"{src.stem}.json"
        if not cache.exists():
            continue
        data = json.loads(cache.read_text())
        words_by_src[key] = [w for w in (data.get("words") or []) if w.get("type") == "word"]
        if src.exists():
            regions_by_src[key] = speech_regions(src, noise_floor_for(src))
        else:
            print(f"aviso: não achei a fonte {key} em {src} — as folgas deste "
                  f"trecho saem como 999 (sem medição), não como medida",
                  file=sys.stderr)

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
            fixed = fix_for(fixes, key, ws, w["text"])
            out.append({
                # o texto CORRIGIDO, igual ao que a legenda vai queimar. O
                # `srcStart`/`srcEnd` abaixo continuam sendo os da FONTE: é por
                # eles que uma correção nova casa, e é o que o editor manda de
                # volta no payload.
                "text": w["text"] if fixed is None else fixed,
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
        # UMA CORREÇÃO NÃO MEXE NO EDL, e o cache do painel era chaveado só pelo
        # mtime do EDL — então corrigir uma palavra deixava o painel servindo a
        # versão anterior indefinidamente. O consumidor (`preview_server._words`)
        # compara as duas chaves.
        "fixMtime": (lambda f: f.stat().st_mtime if f.exists() else 0.0)(
            edit / "transcripts" / "corrections.json"),
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

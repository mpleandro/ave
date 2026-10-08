#!/usr/bin/env python3
"""O cache de segmentos do render: a chave, e a atomicidade.

    uv run python tests/segmentos.py

O QUE ESTE ARQUIVO GUARDA.

O `render.py` apagava a pasta de segmentos inteira a cada render, e a razão
estava documentada: o `segments.json` era montado por GLOB da pasta, e um
segmento velho entrava na soma — medido, um EDL de 3 trechos sobre um 4º
segmento antigo deu 9,23s para um vídeo de 7,57s, renderizando limpo e com todo
overlay fora de lugar. Aquele consumidor não existe mais (o compose lê o
`jcut_timeline` do `edl.json`) e a montagem usa os caminhos EXPLÍCITOS do plano,
nunca um glob. Então o nome passou a carregar uma chave de conteúdo e o trecho
que não mudou reaproveita o próprio arquivo.

O defeito que os testes de chave existem para não deixar voltar:

  **O índice no nome.** A primeira versão nomeava `seg_{i:02d}_{fonte}_{chave}`,
  e remover um trecho desloca o índice de todos os seguintes: num EDL de 5,
  apagar o 2º reaproveitava 1 de 4 — na edição mais comum que existe. Sem o
  índice, 4 de 4. É o caso `remover_trecho_nao_muda_os_outros` aqui embaixo.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL / "helpers"))

import render as R  # noqa: E402

FALHAS: list[str] = []


def confere(nome: str, obtido, esperado) -> None:
    if obtido == esperado:
        print(f"  ok   {nome}")
    else:
        print(f"  FALHA {nome}\n         esperado: {esperado!r}\n         obtido:   {obtido!r}")
        FALHAS.append(nome)


tmp = Path(tempfile.mkdtemp())
fonte = tmp / "fonte.mp4"
subprocess.run(
    ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
     "-i", "testsrc2=size=320x180:rate=30:duration=6",
     "-f", "lavfi", "-i", "sine=frequency=200:duration=6",
     "-c:v", "libx264", "-preset", "ultrafast", "-crf", "35",
     "-c:a", "aac", "-shortest", str(fonte)], check=True)

BASE = dict(source=fonte, t_in=1.0, t_out=3.0, grade_declarado="",
            gain_db=0.0, tier="proxy", streams="v",
            keep_resolution=False, target_fps=None)


def k(**mudanca) -> str:
    return R.chave_segmento(**{**BASE, **mudanca})


print("a chave é estável quando nada muda")
confere("duas chamadas iguais dão a mesma chave", k(), k())

print("\ne muda quando QUALQUER entrada muda")
for campo, valor in [("t_in", 1.001), ("t_out", 3.5), ("grade_declarado", "auto"),
                     ("gain_db", 1.5), ("tier", "final"), ("streams", "a"),
                     ("keep_resolution", True), ("target_fps", 24)]:
    confere(f"muda com {campo}", k(**{campo: valor}) != k(), True)

print("\ne com o CONTEÚDO da fonte — reexportar invalida")
outra = tmp / "outra.mp4"
subprocess.run(
    ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
     "-i", "testsrc2=size=320x180:rate=30:duration=6",
     "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
     "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
     "-c:a", "aac", "-shortest", str(outra)], check=True)
confere("fonte diferente dá chave diferente", k(source=outra) != k(), True)

print("\nremover um trecho não muda a chave dos outros — o defeito do índice")
# As chaves dos trechos SOBREVIVENTES têm de ser as mesmas antes e depois da
# remoção, senão eles reextraem sem ter mudado.
ranges = [(0.0, 1.0), (1.5, 2.5), (3.0, 4.0), (4.5, 5.5)]
antes = [R.chave_segmento(**{**BASE, "t_in": a, "t_out": b}) for a, b in ranges]
sobrevivem = [R.chave_segmento(**{**BASE, "t_in": a, "t_out": b})
              for a, b in ranges[:1] + ranges[2:]]
confere("remover_trecho_nao_muda_os_outros",
        sobrevivem, [antes[0], antes[2], antes[3]])

print("\nversão do produtor na chave")
# A primeira versão deste teste era `("v1" in doc) or True` — sempre verdadeiro,
# ou seja, teste nenhum com aparência de teste. Agora ele mexe na constante e
# exige que a chave mude: é a única forma de provar que subir a versão realmente
# invalida os segmentos de ontem.
antes_v = k()
_orig = R.SEG_VERSAO
R.SEG_VERSAO = "v2"
try:
    confere("subir SEG_VERSAO invalida a chave", k() != antes_v, True)
finally:
    R.SEG_VERSAO = _orig
confere("e voltar restaura a chave", k(), antes_v)

print("\natomicidade — um nome final significa arquivo completo")
saida = tmp / "seg_teste_v.mp4"
R.extrair_atomico(fonte, 1.0, 1.0, "", saida, proxy=True, streams="v")
confere("o arquivo final existe", saida.exists(), True)
confere("nenhum .part sobrou", list(tmp.glob("*.part*")), [])
confere("e é legível pelo ffprobe",
        subprocess.run(["ffprobe", "-v", "error", str(saida)]).returncode, 0)

# Uma extração que FALHA não pode deixar o nome final ocupado, senão o render
# seguinte reaproveitaria um arquivo quebrado para sempre.
alvo = tmp / "seg_falha_v.mp4"
try:
    R.extrair_atomico(tmp / "nao-existe.mp4", 0.0, 1.0, "", alvo, proxy=True, streams="v")
except subprocess.CalledProcessError:
    pass
confere("extração falha NÃO cria o nome final", alvo.exists(), False)

print()
if FALHAS:
    raise SystemExit(f"{len(FALHAS)} falha(s): {', '.join(FALHAS)}")
print("todas passaram")

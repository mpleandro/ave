#!/usr/bin/env python3
"""O cache de derivados, testado sem mídia e sem rede.

    uv run python tests/derivados.py

Um cache errado não falha: ele responde. É por isso que este arquivo existe e
por que ele testa INVALIDAÇÃO mais do que acerto — o defeito que o `derivado.py`
foi escrito para não repetir é "gera uma vez, nunca invalida", e as três
instâncias dele neste repositório (segmentos apagados por glob, `cut_mapped` e
`captions.json` com guarda `if not exists`, o dict de piso de ruído que morria
com o processo) todas responderam com dados velhos sem acusar nada.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL / "helpers"))

import derivado as D  # noqa: E402

FALHAS: list[str] = []


def confere(nome: str, obtido, esperado) -> None:
    if obtido == esperado:
        print(f"  ok   {nome}")
    else:
        print(f"  FALHA {nome}\n         esperado: {esperado!r}\n         obtido:   {obtido!r}")
        FALHAS.append(nome)


tmp = Path(tempfile.mkdtemp())
os.environ["AVE_DERIVADOS"] = str(tmp / "cache")
os.environ.pop("AVELIN_SEM_CACHE", None)

entrada = tmp / "fonte.bin"
entrada.write_bytes(b"a" * 4096)

chamadas = {"n": 0}


def produtor():
    chamadas["n"] += 1
    return {"valor": 42, "chamada": chamadas["n"]}


def pedir(**kw):
    return D.derivado("teste", [entrada], kw.pop("params", {"p": 1}),
                      kw.pop("versao", "1"), produtor, **kw)


print("acerto e reuso")
confere("primeira chamada produz", pedir()["chamada"], 1)
confere("segunda chamada NÃO produz", pedir()["chamada"], 1)
confere("o produtor rodou uma vez só", chamadas["n"], 1)

print("\ninvalidação — o que este arquivo existe para garantir")
confere("parâmetro diferente reproduz", pedir(params={"p": 2})["chamada"], 2)
confere("versão diferente reproduz", pedir(versao="2")["chamada"], 3)
# A FÓRMULA mudar sem a entrada mudar é o caso que os caches ad-hoc erram: o
# arquivo velho continua válido pela entrada e inválido pelo código.
confere("volta ao par original e reusa", pedir()["chamada"], 1)

entrada.write_bytes(b"b" * 4096)   # mesmo TAMANHO, conteúdo diferente
confere("conteúdo diferente no mesmo tamanho reproduz", pedir()["chamada"], 4)

entrada.write_bytes(b"b" * 8192)   # tamanho diferente
confere("tamanho diferente reproduz", pedir()["chamada"], 5)

print("\nsaída de emergência e casos de borda")
os.environ["AVELIN_SEM_CACHE"] = "1"
antes = chamadas["n"]
pedir(); pedir()
confere("AVELIN_SEM_CACHE=1 sempre produz", chamadas["n"] - antes, 2)
os.environ["AVELIN_SEM_CACHE"] = "0"
confere("AVELIN_SEM_CACHE=0 não desliga", D.desligado(), False)
os.environ.pop("AVELIN_SEM_CACHE")

# Entrada ausente: sem impressão não há chave, então não há o que cachear. Não
# pode explodir — o chamador decide o que fazer com a falta do arquivo.
ausente = tmp / "nao-existe.bin"
antes = chamadas["n"]
D.derivado("teste", [ausente], {"p": 1}, "1", produtor)
confere("entrada ausente produz direto, sem cachear", chamadas["n"] - antes, 1)

print("\nfalha do produtor NÃO é cacheada")


def produtor_que_falha():
    raise RuntimeError("ffmpeg morreu")


try:
    D.derivado("falha", [entrada], {}, "1", produtor_que_falha)
    confere("a exceção sobe", False, True)
except RuntimeError:
    confere("a exceção sobe", True, True)
confere("nada foi gravado para 'falha'", list(D.raiz().glob("falha-*.json")), [])

print("\ncache corrompido se refaz em vez de explodir")
# O ARQUIVO EXATO daquela chave, não um qualquer do glob. A primeira versão
# disto pegava `next(iter(glob(...)))` — e como o teste acima já criou várias
# entradas com parâmetros, versões e conteúdos diferentes, ele corrompia o
# arquivo de OUTRA chave: a busca então achava o seu próprio arquivo intacto,
# não reproduzia nada, e o teste passava ou falhava conforme a ordem do glob.
# Um teste instável é pior que nenhum, porque ensina a ignorar a falha.
alvo = D.raiz() / f"teste-{D.chave('teste', [entrada], {'p': 1}, '1')}.json"
assert alvo.exists(), "a entrada de cache desta chave deveria existir aqui"
alvo.write_text("{isto não é json")
antes = chamadas["n"]
D.derivado("teste", [entrada], {"p": 1}, "1", produtor)
confere("arquivo ilegível dispara nova produção", chamadas["n"] - antes, 1)

print("\nlimpar")
confere("limpar('teste') apaga só os de teste", D.limpar("teste") > 0, True)
confere("e não sobrou nenhum 'teste'", list(D.raiz().glob("teste-*.json")), [])

print()
if FALHAS:
    raise SystemExit(f"{len(FALHAS)} falha(s): {', '.join(FALHAS)}")
print("todas passaram")

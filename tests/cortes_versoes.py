#!/usr/bin/env python3
"""Versões de um corte: sem respiros e gancho puxado.

    uv run python tests/cortes_versoes.py

O que este arquivo guarda:

  **A emenda do respiro é a do Avelin.** `variantes.aplicar_respiros` repete
  `render.expand_breaths` (pedaço termina em at + keep − pad, o próximo começa
  em to − pad); se as duas divergirem, o "sem respiros" da galeria e o do
  editor deixam de ser o mesmo corte — caso `respiros_como_o_render`.

  **A legenda segue a montagem.** Palavra cujo meio cai num vão removido some;
  a frase do gancho puxado aparece duas vezes (abre o vídeo e volta no lugar).
"""
from __future__ import annotations

import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL / "helpers"))

import render as R  # noqa: E402
from cortes import variantes as VR  # noqa: E402

FALHAS: list[str] = []


def confere(nome: str, obtido, esperado) -> None:
    if obtido == esperado:
        print(f"  ok  {nome}")
    else:
        FALHAS.append(nome)
        print(f"FALHA {nome}: obtido {obtido!r}, esperado {esperado!r}")


def respiros_como_o_render():
    marcas = [{"at": 12.0, "to": 13.2, "keep": 0.25}, {"at": 20.0, "to": 20.9, "keep": 0.3}]
    nosso = VR.aplicar_respiros(10.0, 30.0, marcas)
    edl = {"ranges": [{"source": "x", "start": 10.0, "end": 30.0, "breaths": marcas}]}
    R.expand_breaths(edl)
    deles = [(r["start"], r["end"]) for r in edl["ranges"]]
    confere("mesmos trechos que render.expand_breaths",
            [(round(a, 3), round(b, 3)) for a, b in nosso], [(round(a, 3), round(b, 3)) for a, b in deles])
    confere("respiro menor que o piso é ignorado",
            VR.aplicar_respiros(0, 10, [{"at": 2, "to": 2.1, "keep": 0.15}]), [(0, 10)])


def plano_das_versoes():
    c = {"respiros": [{"at": 12.0, "to": 13.2, "keep": 0.25}],
         "fala": [{"tipo": "muleta", "texto": "né", "de": 18.0, "ate": 18.4}],
         "variantes": {"gancho": {"trecho": [21.0, 23.0]}}}
    jan = (10.0, 30.0)
    confere("original é a janela", VR.plano(c, "original", jan), [(10.0, 30.0)])
    confere("gancho vem antes do corte inteiro", VR.plano(c, "gancho", jan)[0], (21.0, 23.0))
    confere("só respiros tira só o respiro", len(VR.plano(c, "respiros", jan)), 2)
    fl = VR.plano(c, "falhas", jan)
    confere("só erros de fala tira só a muleta", len(fl), 2)
    confere("a muleta some do trecho", any(a < 18.2 < b for a, b in fl), False)
    confere("as três peças juntas", len(VR.plano(c, "gancho+respiros+falhas", jan)), 4)
    confere("chave antiga ainda vale", VR.plano(c, "fala_limpa", jan), VR.plano(c, "respiros+falhas", jan))
    confere("chave canônica, em ordem", VR.chave({"falhas", "gancho"}), "gancho+falhas")
    confere("nome da versão", VR.nome("respiros+falhas"), "Sem respiros + erros de fala corrigidos")
    confere("remoções sobrepostas viram uma só",
            VR.remover(0, 10, [], [{"de": 2, "ate": 3}, {"de": 2.5, "ate": 4}]), [(0, 2), (4, 10)])
    try:
        VR.plano({"respiros": []}, "gancho", jan)
        confere("sem gancho isolado, recusa", False, True)
    except ValueError:
        confere("sem gancho isolado, recusa", True, True)


def legenda_segue_a_montagem():
    # palavras com tempo relativo ao início da janela (a = 10)
    ws = [{"w": "Antes", "s": 0.5, "e": 1.0}, {"w": "sumiu", "s": 2.4, "e": 2.6},
          {"w": "gancho", "s": 11.2, "e": 11.8}, {"w": "fim", "s": 15.0, "e": 15.5}]
    segs = [(21.0, 22.0), (10.0, 12.2), (13.0, 30.0)]       # gancho + corte com respiro
    out = VR.remapear(ws, 10.0, segs, fps=30)
    nomes = [w["w"] for w in out]
    confere("palavra no vão removido some", "sumiu" in nomes, False)
    confere("frase do gancho aparece duas vezes", nomes.count("gancho"), 2)
    confere("gancho abre o vídeo", out[0]["w"] == "gancho" and out[0]["s"] < 1.0, True)
    confere("ordem de tempo crescente", [w["s"] for w in out] == sorted(w["s"] for w in out), True)
    confere("duração em quadros inteiros", round(VR.duracao([(0, 1.01)], 30) * 30, 6), 31.0)


def transcricao_marcada():
    c = {"respiros": [{"at": 11.0, "to": 12.4, "keep": 0.3}],
         "fala": [{"tipo": "muleta", "texto": "né", "de": 12.95, "ate": 13.45}]}
    ws = [{"w": "Antes", "s": 0.0, "e": 0.5}, {"w": "da", "s": 0.6, "e": 1.0},
          {"w": "pausa", "s": 2.4, "e": 2.9}, {"w": "né", "s": 3.0, "e": 3.4},
          {"w": "fim.", "s": 3.5, "e": 4.0}]
    tok = VR.transcricao(c, ws, 10.0)
    palavras = [t["w"] for t in tok if t["t"] == "w"]
    confere("texto completo, nada some", palavras, ["Antes", "da", "pausa", "né", "fim."])
    confere("a muleta é marcada como erro de fala", [t["w"] for t in tok if "falha" in t], ["né"])
    pausas = [t for t in tok if t["t"] == "p"]
    confere("a pausa longa aparece com a duração", [t["dur"] for t in pausas], [1.4])
    confere("e é marcada como respiro, com o que fica", (pausas[0].get("respiro"), pausas[0].get("fica")), (0, 0.3))


def fala_limpa_conservadora():
    from cortes import fala as FL
    ws = lambda t, pausa_em=None: [
        {"w": x, "s": i * 0.4 + (0.5 if pausa_em is not None and i >= pausa_em else 0),
         "e": i * 0.4 + 0.3 + (0.5 if pausa_em is not None and i >= pausa_em else 0)}
        for i, x in enumerate(t.split())]
    achou = lambda t, **k: [(h["tipo"], h["texto"]) for h in FL.detectar(ws(t, **k))]
    confere("gaguejo de função sai", achou("então eu eu tô fazendo isso"), [("gaguejo", "eu")])
    confere("'e é' não é gaguejo (acento)", achou("futebol, e é assim que você"), [])
    confere("ênfase com vírgula fica", achou("não, não, eu prefiro fundo"), [])
    confere("'por que que' fica", achou("por que que eu falava isso"), [])
    confere("ênfase num fôlego só fica", achou("a Marvel não era nada não era nada e aí"), [])
    confere("recomeço com pausa sai", achou("você quer um plano quer um plano de verdade", pausa_em=4),
            [("gaguejo", "quer um plano")])
    confere("muleta no meio sai", achou("você vai né criar um conteúdo"), [("muleta", "né")])
    confere("'ah' imitando alguém fica", achou("as pessoas vão dizer, ah, usa essa"), [])
    confere("conferência: gaguejo que sobrou reprova",
            FL.soa_limpo(["aqui", "eu", "eu", "to"], ["aqui"], ["eu", "to", "fazendo"], ["eu"]), False)
    confere("conferência: emenda limpa aprova",
            FL.soa_limpo(["aqui", "eu", "to", "fazendo"], ["aqui"], ["eu", "to", "fazendo"], ["eu"]), True)


if __name__ == "__main__":
    for caso in (respiros_como_o_render, plano_das_versoes, legenda_segue_a_montagem,
                 transcricao_marcada, fala_limpa_conservadora):
        print(caso.__name__)
        caso()
    if FALHAS:
        raise SystemExit(f"\n{len(FALHAS)} falha(s): {', '.join(FALHAS)}")
    print("\ntudo certo")

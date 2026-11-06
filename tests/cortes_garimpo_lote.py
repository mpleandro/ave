#!/usr/bin/env python3
"""Garimpo de cortes: o LOTE que o avaliador lê e a validação das notas.

    uv run python tests/cortes_garimpo_lote.py

O que este arquivo guarda:
  - o lote mostra quem fala só onde muda, o ⚡PICO, a fala sem texto (!!)
    debaixo da frase certa, [cauda]/[live] sem ▶/■, e o ■✂ da cauda colada;
  - sem elenco nada de nome aparece (rótulo inventado é pior que nenhum);
  - nota ANTIGA (sem os campos novos) continua válida — o `notas.json` de
    lives já avaliadas não pode quebrar;
  - os campos novos, quando vêm, são conferidos (payoff, referencias_live,
    pico), e o que não recusa vira aviso.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL / "helpers"))

from cortes import sinais_texto as T  # noqa: E402

FALHAS: list[str] = []
CFG = json.loads((SKILL / "helpers" / "cortes" / "config.json").read_text())


def confere(nome: str, obtido, esperado) -> None:
    if obtido == esperado:
        print(f"  ok  {nome}")
    else:
        FALHAS.append(nome)
        print(f"FALHA {nome}: obtido {obtido!r}, esperado {esperado!r}")


def frase(s, e, texto, **extra):
    return {"s": s, "e": e, "texto": texto, "n": len(texto.split()), "fecha_ponto": texto[-1] in ".?!",
            "pausa_antes": 0.5, "pausa_depois": 0.5, "ws": [], "apara": None, **extra}


def pneu():
    frs = [frase(0.0, 1.4, "Pode imaginar a loucura?"),
           frase(1.3, 3.4, "Um dia eu não tive dinheiro pra trocar o pneu de um Gol."),
           frase(3.8, 6.0, "Hoje, eu troco o pneu de um avião a jato."),
           frase(6.9, 8.2, "Eu não tinha onde morar."),
           frase(8.6, 10.0, "pai, fala..."),
           frase(15.3, 21.0, "pai, fala pra eles que você é diferente deles."),
           frase(20.7, 22.1, "Eu era pobre, filho!"),
           frase(22.6, 23.6, "É verdade ou não é?"),
           frase(24.0, 31.4, "Aos 30 anos eu não tinha onde comer, é verdade ou não é?",
                 cauda={"e": 29.9, "vao": 0.03, "n": 5, "tirou": "é verdade ou não é?",
                        "texto": "Aos 30 anos eu não tinha onde comer.", "ultima": "comer,"})]
    c = {"id": "c3177", "start": 0.0, "end": 31.4, "dur": 31.4, "frases": [0, len(frs) - 1],
         "texto": " ".join(f["texto"] for f in frs)}
    anot = {"elenco": True,
            "quem": {0: "Paulo", 1: "Paulo", 2: "Paulo", 3: "Paulo", 4: "Paulo", 5: "Julia", 6: "Paulo",
                     7: "Paulo", 8: "Paulo"},
            "picos": {6: 7.2}, "falas": [["Paulo", 0.0, 16.5], ["Julia", 16.5, 21.0], ["Paulo", 21.0, 31.4]],
            "alertas": [{"tipo": "interjeicao", "texto": "fala de Julia no meio (16.5–21.0s)"},
                        {"tipo": "lacuna", "de": 9.3, "ate": 15.3, "voz": 4.4,
                         "texto": "fala sem texto 9.3–15.3s (4.4s de voz)"}]}
    return frs, c, anot


def lote_mostra_o_que_o_texto_esconde():
    frs, c, anot = pneu()
    p = T.pedido(c, frs, CFG, anot)
    ls = T.linhas(p)
    confere("cabeçalho de falas", ls[0], "falas: Paulo 0.0–16.5 · Julia 16.5–21.0 · Paulo 21.0–31.4\n")
    confere("cabeçalho de alertas", ls[1].startswith("alertas: fala de Julia no meio"), True)
    linha = {int(x.split("]")[0][1:]): x for x in ls if x.startswith("[")}
    confere("nome na primeira frase", "{Paulo} Pode imaginar" in linha[0], True)
    confere("nome só quando muda", "{" in linha[1], False)
    confere("Júlia marcada", "{Julia} pai, fala pra eles" in linha[5], True)
    confere("volta ao Paulo marcada", "{Paulo} Eu era pobre" in linha[6], True)
    confere("pico na frase certa", ("⚡PICO +7dB" in linha[6], "PICO" in linha[1]), (True, False))
    i4 = ls.index(linha[4])
    confere("!! logo depois da frase do buraco", ls[i4 + 1].strip().startswith("!! 9.3–15.3s: 4.4s de fala sem texto"),
            True)
    confere("cauda sem ▶ nem ■", ("[cauda]" in linha[7], "■" in linha[7], "▶" in linha[7]), (True, False, False))
    confere("cauda colada: ■✂ com o fim limpo",
            '(■✂ sem "é verdade ou não é?": Aos 30 anos eu não tinha onde comer.)' in linha[8], True)
    confere("o prompt inteiro monta (rubrica sem chave solta)", "## Lote 1" in T.prompt([p], {}), True)
    confere("a rubrica explica pico, payoff e live",
            all(k in T.prompt([p], {}) for k in ("⚡PICO", "payoff", "## Referências da live", "{Nome}")), True)

    sem = T.linhas(T.pedido(c, frs, CFG, {**anot, "quem": {}, "falas": [], "elenco": False}))
    confere("sem elenco: nenhum nome", any("{" in x for x in sem), False)
    confere("sem anotação: o lote de antes", "{" in "".join(T.linhas(T.pedido(c, frs, CFG))), False)


def nota(**extra):
    dims = {k: {"nota": 70, "motivo": "m"} for k in T.DIMENSOES}
    return {"inicio": 1, "fim": 6, "aparar_conector": False, "dimensoes": dims, "titulo_sugerido": "t",
            "frase_gancho": "", "motivo": "m", "ruido": False,
            "gancho": {"tipo": "tem", "padrao": "contraste",
                       "frase": "Um dia eu não tive dinheiro pra trocar o pneu de um Gol."}, **extra}


def validar_campos_novos():
    frs, c, anot = pneu()
    frs[5]["e"] = 21.0
    c = {**c, "dur": 31.4}
    p = T.pedido(c, frs, {**CFG, "candidatos": {**CFG["candidatos"], "dur_min_s": 15}}, anot)
    confere("nota antiga (sem campos novos) vale", T.validar(nota(), p), [])
    confere("payoff dentro do corte vale", T.validar(nota(payoff=6), p), [])
    confere("payoff fora do corte é erro", bool(T.validar(nota(payoff=8), p)), True)
    confere("corte que segue muito depois do payoff é erro", bool(T.validar(nota(payoff=2), p)), True)
    confere("uma frase depois do payoff vale", T.validar(nota(payoff=5), p), [])
    confere("referencias_live malformada é erro", bool(T.validar(nota(referencias_live="3"), p)), True)
    confere("pico malformado é erro", bool(T.validar(nota(pico={"k": 6, "uso": "talvez"}), p)), True)
    confere("pico certo vale", T.validar(nota(pico={"k": 6, "uso": "puxar", "motivo": "m"}), p), [])
    av = T.avisos(nota(), p)
    confere("pico tardio com gancho 'tem' sem justificar vira aviso", any("⚡PICO em [6]" in a for a in av), True)
    confere("justificado, sem aviso", T.avisos(nota(pico={"k": 6, "uso": "ignorar", "motivo": "m"}), p), [])
    av = T.avisos(nota(referencias_live=[3]), p)
    confere("live no meio com completude alta vira aviso", any("completude" in a for a in av), True)


if __name__ == "__main__":
    for caso in (lote_mostra_o_que_o_texto_esconde, validar_campos_novos):
        print(caso.__name__)
        caso()
    if FALHAS:
        raise SystemExit(f"\n{len(FALHAS)} falha(s): {', '.join(FALHAS)}")
    print("\ntudo certo")

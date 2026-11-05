#!/usr/bin/env python3
"""Garimpo de cortes: as PONTAS do corte, limpas sem modelo nenhum.

    uv run python tests/cortes_garimpo_bordas.py

O que este arquivo guarda, com os casos da live Mentoria Mil Milionários
(2026-11), em que 5 de 48 cortes da galeria terminavam numa cauda de live:

  **Cauda e logística não são borda.** "É isso.", "é verdade ou não é?",
  "Quem tá entendendo isso, gente?", "Posso continuar?" — nenhuma janela
  começa ou termina nelas, e a borda que a avaliação puser nelas recua para a
  frase limpa vizinha. No meio do corte, "é isso" não se toca.

  **Nunca abaixo da duração mínima.** Se tirar a cauda deixa o corte curto
  demais, ela fica.

  **Fala curta de outra pessoa na borda sai; no meio, não.** Pergunta de outra
  pessoa no INÍCIO fica — pergunta → resposta é abertura boa.

  **Cauda colada só sai ouvida.** "E nós pagamos o preço, é verdade ou não é?"
  termina no vale de energia entre "preço" e "é" só se a escuta confirmar —
  ou, sem escuta, se houver silêncio de verdade ali.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL / "helpers"))

import garimpo_cortes as G  # noqa: E402
from cortes import autocontencao as A  # noqa: E402
from cortes import bordas as B  # noqa: E402
from cortes import candidatos as C  # noqa: E402

FALHAS: list[str] = []
CFG = json.loads((SKILL / "helpers" / "cortes" / "config.json").read_text())


def confere(nome: str, obtido, esperado) -> None:
    if obtido == esperado:
        print(f"  ok  {nome}")
    else:
        FALHAS.append(nome)
        print(f"FALHA {nome}: obtido {obtido!r}, esperado {esperado!r}")


def frase(s, e, texto, ponto=True, antes=0.5, depois=0.5, **extra):
    ws, n = [], len(texto.split())
    for k, w in enumerate(texto.split()):
        ws.append({"w": w, "s": s + (e - s) * k / n, "e": s + (e - s) * (k + 1) / n})
    return {"s": s, "e": e, "texto": texto, "n": n, "fecha_ponto": ponto,
            "pausa_antes": antes, "pausa_depois": depois, "ws": ws, "apara": None, **extra}


def trecho(textos: list[str], dur: float = 6.0) -> list[dict]:
    """Frases de `dur` segundos (1s de folga entre elas), fechadas em ponto."""
    return [frase(k * (dur + 1), k * (dur + 1) + dur, t) for k, t in enumerate(textos)]


def janela(frs: list[dict], i: int, j: int) -> dict:
    jan = frs[i:j + 1]
    return {"id": "c0001", "start": frs[i]["s"], "end": frs[j]["e"], "dur": frs[j]["e"] - frs[i]["s"],
            "frases": [i, j], "n_palavras": sum(f["n"] for f in jan),
            "borda": [frs[i]["pausa_antes"], frs[j]["pausa_depois"]],
            "abertura": frs[i]["texto"], "fechamento": frs[j]["texto"],
            "texto": " ".join(f["texto"] for f in jan)}


def lexico():
    for t in ("É isso.", "é verdade ou não é?", "Tá?", "gente?", "Então...", "Né?",
              "Quem tá entendendo isso, gente?", "É isso aí, pessoal."):
        confere(f"cauda: {t!r}", A.eh_cauda(t, CFG), True)
    for t in ("É isso que eu quero te mostrar.", "Vai ter aposentadoria daqui a 10 anos?",
              "Então o dinheiro vai embora.", "Eu era pobre, filho!"):
        confere(f"não é cauda: {t!r}", A.eh_cauda(t, CFG), False)
    for t in ("Posso continuar?", "Faltam dois minutos pra gente fechar.",
              "Escaneia o QR code aí na tela.", "Escreve aí no chat o seu número.",
              "Pegou a visão?"):
        confere(f"logística: {t!r}", A.eh_logistica(t, CFG), True)
    confere("frase longa com 'pegou a visão' é conteúdo",
            A.eh_logistica("E quem pegou a visão de que o dinheiro trabalha para ele saiu da "
                           "corrida dos ratos muito antes dos outros.", CFG), False)
    confere("cauda colada", A.cauda_colada("E nós pagamos o preço, é verdade ou não é?", CFG),
            "é verdade ou não é?")
    confere("vocativo não é cauda colada", A.cauda_colada("Quem aqui já passou por isso, gente?", CFG), None)
    confere("cabeça curta demais", A.cauda_colada("Sim, tá?", CFG), None)
    confere("referência à live", A.referencia_live("Manda aí no chat quem já fez isso.", CFG), True)
    confere("sem referência à live", A.referencia_live("O dinheiro entra e sai.", CFG), False)


def janelas_nao_terminam_em_cauda():
    cfg = {**CFG, "candidatos": {**CFG["candidatos"], "alvos_s": [30, 45]}}
    frs = trecho(["Um dia eu não tive dinheiro pra trocar o pneu.", "Hoje eu troco o pneu do avião.",
                  "Eu não tinha onde morar.", "Hoje eu tenho duas casas.", "É isso.",
                  "Posso continuar?", "O segredo é gastar menos do que ganha.", "Simples assim."])
    cs = C.gerar(frs, cfg)
    confere("há janelas", bool(cs), True)
    confere("nenhuma termina na cauda [4]", any(c["frases"][1] == 4 for c in cs), False)
    confere("nenhuma começa nem termina na logística [5]",
            any(5 in (c["frases"][0], c["frases"][1]) for c in cs), False)
    confere("a frase antes da cauda fecha", any(c["frases"][1] == 3 for c in cs), True)


def aparar_cauda_e_logistica():
    frs = trecho(["Um dia eu não tive dinheiro pra trocar o pneu.", "Hoje eu troco o pneu do avião.",
                  "Eu não tinha onde morar.", "E nós pagamos o preço.", "É isso, gente.", "Tá?"])
    r = B.aparar(janela(frs, 0, 5), frs, CFG)
    confere("fim recua para antes das duas caudas", r["frases"], [0, 3])
    confere("o que saiu fica registrado", [a["motivo"] for a in r["refinado"]["aparado"]], ["cauda"])
    confere("texto sem a cauda", r["texto"].endswith("pagamos o preço."), True)
    confere("fim no fim da frase limpa", r["end"], frs[3]["e"])

    curto = trecho(["Um dia eu não tive dinheiro pra trocar o pneu.", "Hoje eu troco o pneu do avião.",
                    "É isso."], dur=8.0)
    r = B.aparar(janela(curto, 0, 2), curto, CFG)
    confere("cauda fica se tirar deixa < dur_min", r["frases"], [0, 2])

    meio = trecho(["Um dia eu não tive dinheiro pra trocar o pneu.", "É isso.",
                   "Hoje eu troco o pneu do avião.", "Eu não tinha onde morar."])
    c = janela(meio, 0, 3)
    confere("'é isso' no meio não se toca", B.aparar(c, meio, CFG) is c, True)

    log = trecho(["Posso continuar?", "Um dia eu não tive dinheiro pra trocar o pneu.",
                  "Hoje eu troco o pneu do avião.", "Eu não tinha onde morar.", "Hoje eu tenho casa."])
    r = B.aparar(janela(log, 0, 4), log, CFG)
    confere("'Posso continuar?' no início sai", r["frases"], [1, 4])
    confere("início na frase seguinte", (r["start"], r["abertura"][:6]), (log[1]["s"], "Um dia"))
    confere("motivo logística", r["refinado"]["aparado"][0]["motivo"], "logistica")

    sem_fecho = trecho(["Um dia eu não tive dinheiro pra trocar o pneu.", "Hoje eu troco o pneu do avião.",
                        "Eu não tinha onde morar", "E nós pagamos o preço.", "É isso."])
    sem_fecho[3]["pausa_depois"] = 0.0          # "preço." colado na cauda: não é borda
    c = janela(sem_fecho, 0, 4)
    confere("sem borda limpa antes, a cauda fica", B.aparar(c, sem_fecho, CFG) is c, True)


def aparar_no_vale():
    """O c1338: "…no final do mês." emenda no "é isso." com 0,14s de silêncio
    (o piso de borda é 0,15s). Com vale de energia e escuta, o fim recua; sem
    escuta, a cauda fica."""
    frs = trecho(["Um dia eu não tive dinheiro pra trocar o pneu.", "Hoje eu troco o pneu do avião.",
                  "Eu não tinha onde morar.", "E ele continua com o mesmo saldo no final do mês.", "É isso."])
    frs[3]["pausa_depois"] = 0.14
    frs[4]["s"] = frs[3]["e"] + 0.14
    for w in frs[4]["ws"]:
        w["s"], w["e"] = w["s"] - 0.86, w["e"] - 0.86
    t = np.arange(0, 40, 0.021)
    db = np.full(t.size, -20.0)
    db[(t > frs[3]["e"] - 0.02) & (t < frs[4]["s"])] = -55.0
    c = janela(frs, 0, 4)
    confere("sem escuta, não corta no vale", B.aparar(c, frs, CFG, confirmar=lambda *_: None,
                                                    energia=(t, db, -30.0)) is c, True)
    ouvidos = []
    r = B.aparar(c, frs, CFG, confirmar=lambda *a: ouvidos.append(a) or True, energia=(t, db, -30.0))
    confere("ouvida limpa: fim no vale antes do 'É isso.'", (r["frases"], frs[3]["e"] - 0.05 < r["end"] < frs[4]["s"]),
            ([0, 3], True))
    confere("a escuta conferiu a última palavra certa", ouvidos[0][1:], ("mês.", "É isso."))
    confere("o que saiu fica registrado", r["refinado"]["aparado"][0]["texto"], "É isso.")


def aparar_outra_voz():
    textos = ["Um dia eu não tive dinheiro pra trocar o pneu.", "Hoje eu troco o pneu do avião.",
              "Eu não tinha onde morar.", "Hoje eu tenho duas casas.", "Que lindo, pai."]
    frs = trecho(textos, dur=5.0)
    quem = {0: "Paulo", 1: "Paulo", 2: "Paulo", 3: "Paulo", 4: "Julia"}
    r = B.aparar(janela(frs, 0, 4), frs, CFG, quem)
    confere("fala curta de outra pessoa no fim sai", r["frases"], [0, 3])
    confere("registrada com o nome", r["refinado"]["aparado"][0].get("quem"), "Julia")

    junto = trecho(textos[:4] + ["Diz alguma coisa pra mim.", "Que lindo, pai."], dur=5.0)
    r = B.aparar(janela(junto, 0, 5), junto, CFG, {**quem, 4: "Paulo", 5: "Julia"})
    confere("recua por cima da fala dela e da logística antes", r["frases"], [0, 3])

    longa = trecho(textos[:4] + ["E agora eu vou contar a minha parte da história toda."], dur=5.0)
    longa[4]["e"] = longa[4]["s"] + 9.0
    c = janela(longa, 0, 4)
    confere("fala LONGA de outra pessoa fica (o avaliador decide)", B.aparar(c, longa, CFG, quem) is c, True)

    perg = trecho(["Pai, como você saiu da dívida?"] + textos[:4], dur=5.0)
    quem_p = {0: "Julia", 1: "Paulo", 2: "Paulo", 3: "Paulo", 4: "Paulo"}
    c = janela(perg, 0, 4)
    confere("pergunta de outra pessoa no início fica", B.aparar(c, perg, CFG, quem_p) is c, True)
    perg[0]["texto"] = "Pai, fala pra eles."
    r = B.aparar(janela(perg, 0, 4), perg, CFG, quem_p)
    confere("fala curta (sem pergunta) no início sai", r["frases"], [1, 4])

    conversa = trecho(["Pai, conta como foi aquele ano.", "Eu não tinha nada.", "E você chorava todo dia?",
                       "Eu chorava.", "E hoje?", "Hoje eu tenho duas casas.", "Que lindo, pai."], dur=4.0)
    quem_c = {0: "Julia", 1: "Paulo", 2: "Julia", 3: "Paulo", 4: "Julia", 5: "Paulo", 6: "Julia"}
    c = janela(conversa, 0, 6)
    confere("quem conversa no corte não é cortado da borda", B.aparar(c, conversa, CFG, quem_c) is c, True)

    meio = trecho(textos[:2] + ["Pai, fala pra eles."] + textos[2:4], dur=5.0)
    quem_m = {0: "Paulo", 1: "Paulo", 2: "Julia", 3: "Paulo", 4: "Paulo"}
    c = janela(meio, 0, 4)
    confere("fala de outra pessoa no MEIO não se corta aqui", B.aparar(c, meio, CFG, quem_m) is c, True)


def cauda_colada():
    t = np.arange(0, 4, 0.021)
    db = np.full(t.size, -20.0)
    db[(t > 1.03) & (t < 1.09)] = -55.0          # o vale entre "preço," e "é"
    ws = [{"w": w, "s": s, "e": e} for w, s, e in
          (("E", 0.0, 0.1), ("nós", 0.12, 0.3), ("pagamos", 0.32, 0.7), ("o", 0.72, 0.78),
           ("preço,", 0.8, 1.08), ("é", 1.08, 1.2), ("verdade", 1.22, 1.6), ("ou", 1.62, 1.7),
           ("não", 1.72, 1.85), ("é?", 1.87, 2.0))]
    ca = C.aparavel_fim(ws, (t, db, -30.0), CFG)
    confere("cauda colada destacável", ca and ca["tirou"], "é verdade ou não é?")
    confere("ponto no vale", ca and 1.03 <= ca["e"] <= 1.09, True)
    confere("texto sem a cauda", ca and ca["texto"], "E nós pagamos o preço.")
    confere("sem vale não destaca", C.aparavel_fim(ws, (t, np.full(t.size, -20.0), -30.0), CFG), None)

    frs = trecho(["Um dia eu não tive dinheiro pra trocar o pneu.", "Hoje eu troco o pneu do avião.",
                  "Eu não tinha onde morar.", "E nós pagamos o preço, é verdade ou não é?"])
    fim = frs[3]["e"]
    frs[3]["cauda"] = {"e": fim - 1.0, "vao": 0.04, "n": 5, "tirou": "é verdade ou não é?",
                       "texto": "E nós pagamos o preço.", "ultima": "preço,"}
    c = janela(frs, 0, 3)
    r = B.aparar(c, frs, CFG, confirmar=lambda *_: True)
    confere("ouvida limpa: termina no vale", (r["end"], r["fechamento"]), (fim - 1.0, "E nós pagamos o preço."))
    confere("registra a cauda tirada", r["refinado"]["cauda"]["tirou"], "é verdade ou não é?")
    confere("borda do fim = o vão do vale", r["borda"][1], 0.04)
    confere("palavras do corte sem a cauda",
            [w["w"] for w in G.palavras_do_corte(frs, r)][-3:], ["pagamos", "o", "preço."])
    r = B.aparar(c, frs, CFG, confirmar=lambda *_: False)
    confere("escuta recusou: a cauda fica", (r["end"], r["refinado"]["cauda_mantida"]),
            (fim, "é verdade ou não é?"))
    r = B.aparar(c, frs, CFG, confirmar=lambda *_: None)
    confere("sem escuta e vão curto: fica", r["end"], fim)
    frs[3]["cauda"]["vao"] = 0.2
    r = B.aparar(c, frs, CFG, confirmar=lambda *_: None)
    confere("sem escuta com silêncio de verdade: sai", r["end"], fim - 1.0)


if __name__ == "__main__":
    for caso in (lexico, janelas_nao_terminam_em_cauda, aparar_cauda_e_logistica, aparar_no_vale,
                 aparar_outra_voz, cauda_colada):
        print(caso.__name__)
        caso()
    if FALHAS:
        raise SystemExit(f"\n{len(FALHAS)} falha(s): {', '.join(FALHAS)}")
    print("\ntudo certo")

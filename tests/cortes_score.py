#!/usr/bin/env python3
"""Garimpo de cortes: nota final, autocontenção, dedupe e exclusão de ruído.

    uv run python tests/cortes_score.py

O que este arquivo guarda:
  - a nota final é a combinação dos PESOS DO CONFIG (mudar o peso muda a nota —
    nada fixo no código);
  - autocontenção desconta o que só faz sentido com o vídeo inteiro em volta;
  - duas janelas com mais da metade em comum são a mesma ideia: fica a maior;
  - nota marcada como ruído (bastidor da live) é recusada se malformada e não
    é confundida com nota válida.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL / "helpers"))

from cortes import autocontencao as A  # noqa: E402
from cortes import bordas as B  # noqa: E402
from cortes import candidatos as C  # noqa: E402
from cortes import verificar as V  # noqa: E402
from cortes import score as S  # noqa: E402
from cortes import selecao as SEL  # noqa: E402
from cortes import sinais_texto as T  # noqa: E402

FALHAS: list[str] = []
CFG = json.loads((SKILL / "helpers" / "cortes" / "config.json").read_text())


def confere(nome: str, obtido, esperado) -> None:
    if obtido == esperado:
        print(f"  ok  {nome}")
    else:
        FALHAS.append(nome)
        print(f"FALHA {nome}: obtido {obtido!r}, esperado {esperado!r}")


def nota(g=80, f=60, v=70, c=50, p=40, tipo="tem", **extra):
    dims = {k: {"nota": x, "motivo": "m"} for k, x in
            zip(T.DIMENSOES, (g, f, v, c, p))}
    gancho = {"tipo": tipo, "padrao": "comando", "frase": "Parem de ser chatos.",
              "sugestoes": [{"texto": "Pare de postar o óbvio.", "padrao": "comando"}],
              "nota_se_puxar": 80}
    return {"inicio": 0, "fim": 4, "aparar_conector": False, "dimensoes": dims,
            "titulo_sugerido": "t", "frase_gancho": "", "motivo": "m", "gancho": gancho, **extra}


def pedido_falso():
    """O trecho do corte que abria em "Não sei quem tá aqui na aula": a frase
    forte é a [2], aos 8s, e só ela tem o conectivo destacável."""
    textos = ["Não sei quem tá aqui na aula no primeiro dia, tá?", "É só meu jeitinho gentil de ser.",
              "Mas parem de ser chatos.", "Se tá óbvio, muda.", "Não vai rolar."]
    ts = [0.0, 4.7, 8.2, 10.5, 30.0]
    fr = []
    for k, (tx, t) in enumerate(zip(textos, ts)):
        fr.append({"k": k, "t": t, "s": 100 + t, "e": 100 + t + 2, "texto": tx, "abre": True,
                   "apara": {"texto": "Parem de ser chatos.", "tirou": "Mas", "s": 108.5} if k == 2 else None,
                   "fecha": True})
    return {"frases": fr, "dur_min": 20}


def corte(audio=50.0, auto=100, motivos=()):
    sub = {"energia": 50, "variacao": 50, "ritmo": 50, "pausas": 50}
    return {"audio": {"nota": audio, "subscores": sub, "bruto": {
                "energia_db": 1.0, "variacao_db": 2.0, "ritmo_wps": 2.5, "ar_morto": 0.05}},
            "autocontencao": {"nota": auto, "motivos": list(motivos)}}


def janela(abertura, texto=None, fechamento="E é isso."):
    return {"abertura": abertura, "fechamento": fechamento,
            "texto": texto or f"{abertura} meio do trecho {fechamento}"}


def nota_final_segue_os_pesos():
    r = S.final(corte(audio=50, auto=100), nota(), CFG)
    w = CFG["pesos"]
    texto = sum(x * w["texto"][k] for k, x in zip(T.DIMENSOES, (80, 60, 70, 50, 40))) / sum(w["texto"].values())
    esperado = round((texto * w["final"]["texto"] + 50 * w["final"]["audio"] + 100 * w["final"]["autocontencao"])
                     / sum(w["final"].values()))
    confere("combinação ponderada", r["score_final"], esperado)
    confere("fica entre 0 e 100", 0 <= r["score_final"] <= 100, True)
    alt = copy.deepcopy(CFG)
    alt["pesos"]["final"] = {"texto": 0, "audio": 1, "autocontencao": 0}
    confere("peso vem do config", S.final(corte(audio=33), nota(), alt)["score_final"], 33)
    confere("subscores trazem motivo",
            all("motivo" in s for s in r["subscores"].values()), True)


def autocontencao_desconta():
    limpa = A.avaliar(janela("Vocês não estão aqui pra dar aula."), CFG)
    confere("abertura limpa = 100", limpa["nota"], 100)
    con = A.avaliar(janela("Então, o ponto é esse."), CFG)
    confere("conector desconta", con["nota"], 100 + CFG["autocontencao"]["conector"])
    confere("conector explica", "conector" in con["motivos"][0], True)
    ref = A.avaliar(janela("Como eu disse, ninguém lê."), CFG)
    confere("referência desconta", ref["nota"] < 100, True)
    mul = A.avaliar(janela("tá?"), CFG)
    confere("muleta solta desconta", mul["nota"] < 100, True)
    live = A.avaliar(janela("Hoje tem brinde.", "Hoje tem brinde. Ninguém mandou nada no chat."), CFG)
    confere("live desconta", live["nota"] < 100, True)
    prom = A.avaliar(janela("O segredo é simples.", fechamento="Já já eu vou te mostrar."), CFG)
    confere("promessa no fim desconta", prom["nota"], 100 + CFG["autocontencao"]["promessa"])


def dedupe_fica_o_maior():
    a = {"id": "a", "start": 0, "end": 40, "s": 70}
    b = {"id": "b", "start": 10, "end": 50, "s": 80}     # 30s de 40 em comum
    c = {"id": "c", "start": 35, "end": 75, "s": 60}     # 15s com b
    d = {"id": "d", "start": 100, "end": 130, "s": 10}
    top = SEL.podar([a, b, c, d], "s", 10)
    confere("sobreposição > 50% sai", [x["id"] for x in top], ["b", "c", "d"])
    confere("top N corta", len(SEL.podar([a, b, c, d], "s", 2)), 2)
    confere("sobreposição mede a menor", round(SEL.sobreposicao(a, b), 2), 0.75)


def validar_notas():
    p = pedido_falso()
    tarde = nota()                                        # início em [0], gancho aos 8s
    confere("gancho 'tem' que toca aos 8s é recusado",
            any("só toca aos" in e for e in T.validar(tarde, p)), True)
    no_gancho = nota(inicio=2, aparar_conector=True)       # o corte começa nele
    confere("começando no gancho, sem o 'Mas', passa", T.validar(no_gancho, p), [])
    confere("'puxar' com a frase no começo é recusado",
            bool(T.validar(nota(inicio=2, aparar_conector=True, tipo="puxar"), p)), True)
    confere("puxar com a frase adiante passa", T.validar(nota(tipo="puxar"), p), [])
    sem_previsao = nota(tipo="puxar")
    sem_previsao["gancho"]["nota_se_puxar"] = None
    confere("puxar sem a nota prevista é recusado", bool(T.validar(sem_previsao, p)), True)
    confere("aparar onde não há conectivo é recusado",
            bool(T.validar(nota(inicio=1, aparar_conector=True), p)), True)
    curto = nota(inicio=2, fim=3, aparar_conector=True)
    confere("corte abaixo da duração mínima é recusado",
            any("abaixo de" in e for e in T.validar(curto, p)), True)
    confere("ruído não booleano falha", bool(T.validar(nota(ruido="sim"), p)), True)
    confere("nota > 100 falha", bool(T.validar(nota(g=120), p)), True)
    sem = nota(tipo="regravar")
    sem["gancho"]["sugestoes"] = ["texto solto, sem padrão"]
    confere("sugestão sem padrão falha", bool(T.validar(sem, p)), True)


def conectivo_com_acento():
    import numpy as np
    ws = lambda t: [{"w": x, "s": float(i), "e": i + .5} for i, x in enumerate(t.split())]
    t = np.arange(0, 8, 0.021)
    fala = np.where((t % 1.0) < 0.5, -30.0, -60.0)          # voz em [i, i+0,5], respiro depois
    colado = np.full_like(t, -30.0)                          # voz sem respiro nenhum
    texto = lambda frase, db=fala: (C.aparavel(ws(frase), (t, db, -45.0)) or {}).get("texto")
    confere("'Mas' sai", texto("Mas parem de ser chatos"), "Parem de ser chatos")
    confere("'É' é verbo, não sai", texto("É raro vender pelo Reels"), None)
    confere("'Então,' sai", texto("Então, no Reels você usa"), "No Reels você usa")
    confere("sem respiro no áudio não sai", texto("Mas parem de ser", colado), None)
    ap = C.aparavel(ws("Mas parem de ser chatos"), (t, fala, -45.0))
    confere("ponto ~20ms antes da voz voltar (grade de 21ms)",
            abs(ap["pontos"][0] - 0.98) < 0.03, True)
    confere("verificação: ouvir o conectivo reprova", V.bate(["mas", "parem"], "Parem de ser", "Mas"), False)
    confere("verificação: ouvir a palavra certa aprova", V.bate(["parem", "de"], "Parem de ser", "Mas"), True)
    confere("verificação: ouvir palavra comida reprova", V.bate(["depois", "de"], "Eu descobri isso", "e"), False)


def bordas_comecam_no_gancho():
    frs = [{"s": 100 + 10 * i, "e": 108 + 10 * i, "texto": f"Frase {i}.", "n": 3, "fecha_ponto": True,
            "pausa_antes": .5, "pausa_depois": .5, "apara": None} for i in range(6)]
    frs[2]["apara"] = {"s": 120.4, "gap": .3, "tirou": "Mas", "texto": "Parem."}
    c = {"start": 100, "end": 158, "dur": 58, "frases": [0, 5], "texto": "", "abertura": "", "fechamento": ""}
    r = B.refinar(c, {"inicio": 2, "fim": 5, "aparar_conector": True}, frs, CFG)
    confere("start pula o conectivo", r["start"], 120.4)
    confere("abertura sem o conectivo", r["abertura"], "Parem.")
    confere("registra o que tirou", r["refinado"]["tirou"], "Mas")
    curto = B.refinar(c, {"inicio": 5, "fim": 5}, frs, CFG)
    confere("abaixo do mínimo, mantém o original", curto is c, True)


def ranking_comparativo():
    from cortes import ranking as RK
    cs = [{"id": "a", "score_final": 70, "variantes": {"original": {"score": 70}, "respiros": {"score": 72}}},
          {"id": "b", "score_final": 75, "variantes": {"original": {"score": 75}}}]
    r = {"ordem": [{"id": "a", "score": 90, "motivo": "m"}, {"id": "b", "score": 95, "motivo": "m"}]}
    confere("ranking válido", RK.validar(r, cs), [])
    out = RK.aplicar(r, [dict(c, variantes={k: dict(v) for k, v in c["variantes"].items()}) for c in cs])
    confere("a ordem do ranking manda", [c["id"] for c in out], ["a", "b"])
    confere("nota não sobe ao descer a lista", [c["score_final"] for c in out], [90, 90])
    confere("nota do lote guardada", out[0]["score_lote"], 70)
    confere("versões andam junto", out[0]["variantes"]["respiros"]["score"], 92)
    confere("faltar corte é erro", bool(RK.validar({"ordem": r["ordem"][:1]}, cs)), True)


if __name__ == "__main__":
    for caso in (nota_final_segue_os_pesos, autocontencao_desconta, dedupe_fica_o_maior,
                 validar_notas, conectivo_com_acento, bordas_comecam_no_gancho,
                 ranking_comparativo):
        print(caso.__name__)
        caso()
    if FALHAS:
        raise SystemExit(f"\n{len(FALHAS)} falha(s): {', '.join(FALHAS)}")
    print("\ntudo certo")

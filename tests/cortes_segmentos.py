#!/usr/bin/env python3
"""Estágio 1 do garimpo de cortes: onde uma janela pode começar e terminar.

    uv run python tests/cortes_segmentos.py

O que este arquivo guarda é a regra "nunca no meio de uma ideia", com os dois
defeitos que a primeira versão deixou passar numa fonte real de 70 min:

  **Pausa como começo de frase.** "elas resolveram a tensão uma temporada
  antes." abria corte só porque havia um respiro antes. Minúscula sem ponto na
  frase anterior é meio de frase — caso `respiro_no_meio_nao_abre`.

  **Ponto sem silêncio.** O Whisper pontua onde a voz não para; o corte sairia
  colado na palavra seguinte — caso `ponto_colado_nao_fecha`.
"""
from __future__ import annotations

import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL / "helpers"))

from cortes import candidatos as C  # noqa: E402

FALHAS: list[str] = []
CFG = {"candidatos": {"dur_min_s": 20, "dur_max_s": 90, "alvos_s": [30, 60],
                      "borda_min_s": 0.15}}


def confere(nome: str, obtido, esperado) -> None:
    if obtido == esperado:
        print(f"  ok  {nome}")
    else:
        FALHAS.append(nome)
        print(f"FALHA {nome}: obtido {obtido!r}, esperado {esperado!r}")


def frase(s, e, texto, ponto=True, antes=0.5, depois=0.5):
    return {"s": s, "e": e, "texto": texto, "n": len(texto.split()),
            "fecha_ponto": ponto, "pausa_antes": antes, "pausa_depois": depois}


def falas(n: int, passo: float = 10.0) -> list[dict]:
    """n frases de 9,5s, todas fechadas em ponto com silêncio dos dois lados."""
    return [frase(i * passo, i * passo + 9.5, f"Frase {i}.") for i in range(n)]


def duracoes_dentro_do_limite():
    cs = C.gerar(falas(30), CFG)
    confere("há janelas", bool(cs), True)
    confere("nenhuma < 20s ou > 90s", all(20 <= c["dur"] <= 90 for c in cs), True)
    confere("ids únicos", len({c["id"] for c in cs}), len(cs))
    confere("sem janela repetida", len({(c["start"], c["end"]) for c in cs}), len(cs))


def bordas_em_frase():
    frs = falas(12)
    cs = C.gerar(frs, CFG)
    inicios, fins = {f["s"] for f in frs}, {f["e"] for f in frs}
    confere("começa em início de frase", all(c["start"] in inicios for c in cs), True)
    confere("termina em fim de frase", all(c["end"] in fins for c in cs), True)


def respiro_no_meio_nao_abre():
    frs = falas(12)
    frs[2]["fecha_ponto"] = False                       # "...e aí," — respiro
    frs[3]["texto"] = "elas resolveram a tensão."       # continua minúscula
    cs = C.gerar(frs, CFG)
    confere("minúscula após vírgula não abre", any(c["frases"][0] == 3 for c in cs), False)
    frs[3]["texto"] = "Elas resolveram a tensão."
    cs = C.gerar(frs, CFG)
    confere("maiúscula com silêncio abre", any(c["frases"][0] == 3 for c in cs), True)


def ponto_colado_nao_fecha():
    frs = falas(12)
    frs[5]["pausa_depois"] = 0.0
    cs = C.gerar(frs, CFG)
    confere("ponto sem silêncio não fecha", any(c["frases"][1] == 5 for c in cs), False)
    frs[5]["fecha_ponto"], frs[5]["pausa_depois"] = False, 1.2   # "Isso não vai" + pausa
    cs = C.gerar(frs, CFG)
    confere("pausa longa sem ponto não fecha", any(c["frases"][1] == 5 for c in cs), False)


def virgula_sem_pausa_nao_fecha():
    frs = falas(12)
    frs[6]["fecha_ponto"], frs[6]["pausa_depois"] = False, 0.3
    cs = C.gerar(frs, CFG)
    confere("vírgula com pausa curta não fecha", any(c["frases"][1] == 6 for c in cs), False)


def reticencias_nao_fecham():
    confere("ponto fecha", C.fecha("perfil."), True)
    confere("pergunta fecha", C.fecha("saco?"), True)
    confere("aspas depois do ponto fecha", C.fecha('voz."'), True)
    confere("reticências não fecham", C.fecha("de..."), False)
    confere("reticência unicode não fecha", C.fecha("de…"), False)
    confere("vírgula não fecha", C.fecha("algo,"), False)


def alvo_mais_proximo():
    cs = C.gerar(falas(30), CFG)
    do_zero = sorted(c["dur"] for c in cs if c["start"] == 0)
    confere("um fim por alvo (30s, 60s)", do_zero, [29.5, 59.5])


if __name__ == "__main__":
    for caso in (duracoes_dentro_do_limite, bordas_em_frase, respiro_no_meio_nao_abre,
                 ponto_colado_nao_fecha, virgula_sem_pausa_nao_fecha, reticencias_nao_fecham,
                 alvo_mais_proximo):
        print(caso.__name__)
        caso()
    if FALHAS:
        raise SystemExit(f"\n{len(FALHAS)} falha(s): {', '.join(FALHAS)}")
    print("\ntudo certo")

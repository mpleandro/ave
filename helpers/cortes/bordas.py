"""Estágio 7 — refino de bordas: o corte começa NO gancho.

A avaliação escolhe, dentro da janela, a frase onde o corte começa (`inicio`) e
a frase onde termina (`fim`), e pode tirar o conectivo de abertura
(`aparar_conector`: "Mas parem de ser chatos." → "Parem de ser chatos."). Aqui
isso vira tempo — sempre numa fronteira com silêncio medido, nunca abaixo da
duração mínima.

O defeito que esta forma corrige: a versão anterior pedia "quantas frases
pular" e DEPOIS dava nota ao gancho, então a nota descrevia a frase forte do
trecho e o corte continuava abrindo no aquecimento — nota 76 de gancho para um
vídeo que começava em "Não sei quem tá aqui na aula no primeiro dia". Agora o
início é escolhido junto com a nota, e `sinais_texto.validar` recusa um gancho
"tem" cuja frase não toca nos primeiros segundos do corte final.
"""
from __future__ import annotations


def limites(c: dict, nota: dict, frs: list[dict]) -> tuple[int, int, float, dict | None]:
    """(frase inicial, frase final, start em segundos, apara) na fonte."""
    i0, _ = c["frases"]
    ni = i0 + nota.get("inicio", 0)
    nj = i0 + nota.get("fim", c["frases"][1] - i0)
    apara = frs[ni].get("apara") if nota.get("aparar_conector") else None
    start = apara["s"] if apara else frs[ni]["s"]
    return ni, nj, start, apara


def refinar(c: dict, nota: dict, frs: list[dict], cfg: dict) -> dict:
    i0, j0 = c["frases"]
    ni, nj, start, apara = limites(c, nota, frs)
    if (ni, nj) == (i0, j0) and not apara:
        return c
    dur = frs[nj]["e"] - start
    if nj < ni or dur < cfg["candidatos"]["dur_min_s"]:
        return c
    jan = frs[ni:nj + 1]
    abertura = apara["texto"] if apara else frs[ni]["texto"]
    textos = [abertura] + [f["texto"] for f in jan[1:]]
    palavras = sum(f["n"] for f in jan) - (len(apara["tirou"].split()) if apara else 0)
    return {**c, "start": round(start, 3), "end": round(frs[nj]["e"], 3),
            "dur": round(dur, 2), "frases": [ni, nj], "n_palavras": palavras,
            "borda": [round(apara["gap"] if apara else frs[ni]["pausa_antes"], 2),
                      round(frs[nj]["pausa_depois"], 2)],
            "abertura": abertura, "fechamento": frs[nj]["texto"],
            "texto": " ".join(textos),
            "refinado": {"inicio": ni - i0, "fim": nj - i0,
                         "tirou": apara["tirou"] if apara else None,
                         "original": [c["start"], c["end"]]}}

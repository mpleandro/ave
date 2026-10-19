"""Estágio 8 — dedupe e top N.

Duas janelas que dividem mais da metade da MENOR são a mesma ideia: fica a de
nota maior. A mesma regra do `hook_finder.podar`, aqui sobre cortes.
"""
from __future__ import annotations


def sobreposicao(a: dict, b: dict) -> float:
    """Fração da janela menor que a outra cobre."""
    inter = min(a["end"], b["end"]) - max(a["start"], b["start"])
    return max(0.0, inter) / min(a["end"] - a["start"], b["end"] - b["start"])


def podar(cands: list[dict], chave: str, top: int, limite: float = 0.5) -> list[dict]:
    escolhidos: list[dict] = []
    for c in sorted(cands, key=lambda c: -c[chave]):
        if all(sobreposicao(c, k) <= limite for k in escolhidos):
            escolhidos.append(c)
            if len(escolhidos) >= top:
                break
    return escolhidos

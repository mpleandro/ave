"""Estágio 2c — o pré-filtro barato: de milhares de janelas, as que valem leitura.

A avaliação de texto (estágio 3) é a cara: cada janela lida custa contexto. Então
antes dela entra uma nota sem modelo nenhum, e só as `finalistas` melhores —
já sem duplicatas — seguem.

A nota prévia junta três coisas:
- áudio          (sinais_audio) — energia, variação, ritmo, ar morto
- autocontenção  (autocontencao) — se sustenta sozinho
- gancho prévio  — os 3 primeiros segundos, pelos padrões das 6 anatomias de
                   references/hooks.md (os mesmos do hook_finder), pergunta,
                   número, "você"; mais um léxico de picos no trecho todo.

É ORDENAÇÃO, não julgamento: ela só decide quem é lido. Os pesos estão em
`pesos.prefiltro` do config.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hook_finder import ANATOMIAS, MULETAS, norm  # noqa: E402

from . import selecao

PICOS = re.compile(
    r"\b(nunca|ninguem|segredo|erro|errado|verdade|mentira|problema|dinheiro|milhao|"
    r"milhoes|mil reais|pior|melhor|odeio|amo|medo|vergonha|chorei|absurdo|ridiculo|"
    r"simples|ninguem fala|cuidado|para de|pare de|o que mata|morre|viral|"
    r"bilhao|faturar|faturamento|vender|vende|cliente)\b")
NUMERO = re.compile(r"\d|\b(dois|tres|cinco|sete|dez|cem|mil|milhao|metade)\b")


def primeiros_segundos(ws: list[dict], start: float, seg: float = 3.0) -> str:
    return " ".join(w["w"] for w in ws if start <= w["s"] < start + seg)


def gancho_previo(c: dict, abre3: str) -> tuple[float, list[str]]:
    t = norm(abre3)
    nota, tags = 40.0, []
    anat = [nome for _, nome, rx in ANATOMIAS if rx.search(t)]
    if anat:
        nota += 25
        tags += anat
    if "?" in abre3:
        nota += 12
        tags.append("pergunta")
    if NUMERO.search(t):
        nota += 6
        tags.append("número")
    if re.search(r"\bvoce\b", t):
        nota += 6
    nota -= 8 * len(MULETAS.findall(t))
    picos = len(PICOS.findall(norm(c["texto"])))
    nota += min(15, 3 * picos)
    return max(0.0, min(100.0, nota)), tags


def pontuar(cands: list[dict], audio: list[dict], auto: list[dict], ws: list[dict],
            cfg: dict) -> list[dict]:
    w = cfg["pesos"]["prefiltro"]
    tot = sum(w.values())
    out = []
    for c, a, s in zip(cands, audio, auto):
        g, tags = gancho_previo(c, primeiros_segundos(ws, c["start"]))
        nota = (a["nota"] * w["audio"] + s["nota"] * w["autocontencao"] + g * w["gancho"]) / tot
        out.append({**c, "previa": round(nota, 1),
                    "audio": a, "autocontencao": s,
                    "gancho_previo": {"nota": g, "tags": tags}})
    return out


def finalistas(pontuados: list[dict], cfg: dict) -> list[dict]:
    p = cfg["prefiltro"]
    vivos = [c for c in pontuados if c["autocontencao"]["nota"] >= p["autocontencao_min"]]
    return selecao.podar(vivos, "previa", p["finalistas"], p["sobreposicao_max"])

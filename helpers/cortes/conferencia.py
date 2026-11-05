"""CONFERÊNCIA DE ENQUADRAMENTO — o corte só vai para a galeria aprovado.

Nasceu de um pedido direto do usuário (2026-11): "não posso ter que ficar
corrigindo um a um". Cinco cortes seguidos chegaram com a faixa 9:16 na pessoa
errada ou em tela cheia, e cada um só foi descoberto assistindo.

Para cada meio segundo do plano (`enquadramento.plano`):
- QUEM FALA pela voz do elenco (`elenco.quem_fala`);
- QUEM ESTÁ NO CENTRO da faixa: o rosto mais perto do centro, identificado
  pela cor da roupa (`elenco.atribuir`);
- se o rosto está centrado (erro em fração da largura da faixa);
- trecho em "fit" (quadro inteiro) com gente na cena.

Reprova quando: falante errado > 1s somado, ou fit com gente > 0,5s, ou rosto
fora do centro (> 28% da largura) por > 1,5s. Sem elenco, só confere fit e
centro.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from . import elenco as EL
from . import enquadramento as EQ


def _x_em(tr: dict, t: float) -> float | None:
    if tr["modo"] != "crop":
        return None
    xs = tr.get("xs")
    if not xs:
        return float(tr["x"])
    T = [p[0] for p in xs]
    X = [p[1] for p in xs]
    return float(np.interp(t, T, X))


def conferir(video: Path, a: float, b: float, plano: dict | None = None) -> dict:
    pl = plano or EQ.plano(video, a, b)
    if pl.get("vertical"):
        return {"ok": True, "motivo": "fonte vertical"}
    cw = pl.get("cw") or int(pl["H"] * 9 / 16) // 2 * 2
    med = EQ._medir(video, a, b)
    el = EL.carregar(video)
    cenas = med["cenas"] + [med["dur"]]
    passo = EQ.PASSO
    nomes = EL.quem_fala(video, a, 0.0, b - a, el, passo) if el else []
    erros = {"falante": 0.0, "fit": 0.0, "fora": 0.0}
    cache: dict = {}
    marcas = []
    for k, s in enumerate(np.arange(0.0, b - a, passo)):
        t = a + s
        tr = next((x for x in pl["trechos"] if x["de"] - 1e-6 <= t < x["ate"] + 1e-6), None)
        if tr is None or tr["modo"] in ("dividida", "inteiro"):
            continue
        c0 = max(c for c in cenas[:-1] if c <= s + 1e-6)
        c1 = min(c for c in cenas if c > s + 1e-6)
        fs = [r for r in med["rostos"] if abs(r[0] - s) <= 0.15]
        if tr["modo"] == "fit":
            if fs:
                erros["fit"] += passo
                marcas.append((round(s, 1), "tela cheia com gente"))
            continue
        x = _x_em(tr, t)
        if x is None or not fs:
            continue
        centro = x + cw / 2
        perto = min(fs, key=lambda r: abs(r[1] - centro))
        desvio = abs(perto[1] - centro) / cw
        if desvio > 0.28:
            erros["fora"] += passo
            marcas.append((round(s, 1), f"rosto fora do centro ({desvio:.0%})"))
        n = nomes[k] if k < len(nomes) else None
        if el and n:
            chave = (c0, c1)
            if chave not in cache:
                cache[chave] = EQ._pessoas_elenco(med["rostos"], c0, c1, el)
            nomeados = cache[chave]
            if n in nomeados:
                xs_alvo = [q[1] for q in nomeados[n]["amostras"] if abs(q[0] - s) <= 0.3]
                if xs_alvo and abs(float(np.median(xs_alvo)) - centro) > 0.30 * cw:
                    erros["falante"] += passo
                    marcas.append((round(s, 1), f"fala {n}, faixa em outra pessoa"))
    ok = erros["falante"] <= 1.0 and erros["fit"] <= 0.5 and erros["fora"] <= 1.5
    return {"ok": ok, "erros": {k: round(v, 1) for k, v in erros.items()}, "marcas": marcas[:12]}

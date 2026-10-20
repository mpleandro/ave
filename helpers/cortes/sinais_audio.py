"""Estágio 2a — sinais de áudio de cada janela.

O que o transcrito não mostra: uma frase gritada e uma murmurada leem igual.
Quatro medidas, todas RELATIVAS — ao próprio falante e às outras janelas da
mesma fonte, nunca a um dB absoluto (o ganho do microfone mudaria a nota):

- energia   P75 dos quadros com voz, em dB contra a mediana do falante.
- variacao  desvio do nível segundo a segundo: fala que sobe e desce prende,
            fala chapada cansa.
- ritmo     palavras por segundo de janela.
- pausas    fração da janela em silêncio ≥ `ar_morto_s` — ar morto derruba
            retenção. Aqui MENOS é melhor.

Cada medida bruta vira percentil (0–100) entre todas as janelas da fonte, e a
nota de áudio é a média ponderada por `pesos.audio` do config.
"""
from __future__ import annotations

import numpy as np


def percentis(xs: list[float]) -> list[float]:
    """Posição de cada valor entre todos, 0–100. Empates dividem a posição."""
    a = np.asarray(xs, dtype=float)
    if a.size < 2:
        return [50.0] * a.size
    ordem = a.argsort(kind="mergesort")
    rank = np.empty(a.size)
    rank[ordem] = np.arange(a.size)
    # empates: média das posições
    _, inv, cont = np.unique(a, return_inverse=True, return_counts=True)
    soma = np.bincount(inv, weights=rank)
    rank = soma[inv] / cont[inv]
    return list(np.round(rank / (a.size - 1) * 100, 1))


def medir(cands: list[dict], times: np.ndarray, levels: np.ndarray, floor_db: float,
          sil: list[tuple[float, float]], cfg: dict) -> list[dict]:
    """Medidas brutas por janela (sem nota ainda)."""
    speech = levels[levels > floor_db]
    ref = float(np.percentile(speech, 75)) if speech.size else -30.0
    ar_morto = cfg["audio"]["ar_morto_s"]
    sil_a = np.asarray(sil) if sil else np.zeros((0, 2))
    out = []
    for c in cands:
        i0, i1 = np.searchsorted(times, [c["start"], c["end"]])
        lv = levels[i0:i1]
        voz = lv[lv > floor_db]
        energia = float(np.percentile(voz, 75)) - ref if voz.size else -20.0
        # variação: P75 por segundo, desvio entre os segundos com voz
        por_seg = []
        tt = times[i0:i1]
        for s in np.arange(c["start"], c["end"], 1.0):
            m = (tt >= s) & (tt < s + 1) & (lv > floor_db)
            if m.sum() >= 10:
                por_seg.append(np.percentile(lv[m], 75))
        variacao = float(np.std(por_seg)) if len(por_seg) > 2 else 0.0
        # ar morto: silêncios longos dentro da janela
        if sil_a.size:
            a = np.clip(sil_a[:, 0], c["start"], c["end"])
            b = np.clip(sil_a[:, 1], c["start"], c["end"])
            d = b - a
            morto = float(d[d >= ar_morto].sum())
        else:
            morto = 0.0
        out.append({"energia_db": round(energia, 2), "variacao_db": round(variacao, 2),
                    "ritmo_wps": round(c["n_palavras"] / c["dur"], 2),
                    "ar_morto": round(morto / c["dur"], 3)})
    return out


def populacao(medidas: list[dict]) -> dict[str, list[float]]:
    """As medidas brutas de todas as janelas, ordenadas — a régua dos percentis
    para pontuar depois uma janela que o refino de bordas encolheu."""
    return {k: sorted(m[k] for m in medidas)
            for k in ("energia_db", "variacao_db", "ritmo_wps", "ar_morto")}


def nota_contra(m: dict, pop: dict[str, list[float]], cfg: dict) -> dict:
    """A nota de UMA janela medida contra a população da fonte."""
    def pct(k):
        a = pop[k]
        if len(a) < 2:
            return 50.0
        lo, hi = np.searchsorted(a, m[k], "left"), np.searchsorted(a, m[k], "right")
        return round(float((lo + hi) / 2 / len(a) * 100), 1)
    sub = {"energia": pct("energia_db"), "variacao": pct("variacao_db"),
           "ritmo": pct("ritmo_wps"), "pausas": round(100 - pct("ar_morto"), 1)}
    w = cfg["pesos"]["audio"]
    return {"subscores": sub, "nota": round(sum(sub[k] * w[k] for k in w) / sum(w.values()), 1),
            "bruto": m}


def notas(medidas: list[dict], cfg: dict) -> list[dict]:
    """Percentis + nota de áudio ponderada."""
    pe = percentis([m["energia_db"] for m in medidas])
    pv = percentis([m["variacao_db"] for m in medidas])
    pr = percentis([m["ritmo_wps"] for m in medidas])
    pp = [100 - x for x in percentis([m["ar_morto"] for m in medidas])]
    w = cfg["pesos"]["audio"]
    tot = sum(w.values())
    out = []
    for m, e, v, r, p in zip(medidas, pe, pv, pr, pp):
        sub = {"energia": e, "variacao": v, "ritmo": r, "pausas": p}
        out.append({"subscores": sub, "nota": round(sum(sub[k] * w[k] for k in w) / tot, 1),
                    "bruto": m})
    return out


def respiros(start: float, end: float, sil: list[tuple[float, float]], cfg: dict) -> dict:
    """Quanto do corte é pausa que o Avelin tiraria (propose_breaths deixa um
    respiro curto em cada vão; aqui a mesma conta, só para estimar).

    É a ponte para a edição: a nota de ritmo diz que o trecho arrasta, isto diz
    quanto ele encolhe se passar pelo editor."""
    r = cfg["ritmo"]
    vaos = [min(b, end) - max(a, start) for a, b in sil if a < end and b > start]
    vaos = [v for v in vaos if v >= r["pausa_min_s"]]
    cortavel = sum(v - r["manter_s"] for v in vaos)
    dur = end - start
    return {"pausas": len(vaos), "pausa_s": round(sum(vaos), 1), "cortavel_s": round(cortavel, 1),
            "dur_apos": round(dur - cortavel, 1), "pct": round(cortavel / dur * 100) if dur else 0,
            "recomenda_avelin": cortavel >= r["recomendar_s"] and cortavel / dur >= r["recomendar_pct"]}

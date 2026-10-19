"""Estágio 6 — a nota de viralização, 0–100.

    final = texto·w_texto + áudio·w_audio + autocontenção·w_auto

com `texto` a média ponderada das cinco dimensões. Todos os pesos vêm de
`pesos` no config — nada fixo aqui. Cada parcela sai com o motivo, porque a
galeria mostra por que o corte recebeu aquela nota.
"""
from __future__ import annotations


def media(valores: dict[str, float], pesos: dict[str, float]) -> float:
    tot = sum(pesos.values())
    return sum(valores[k] * w for k, w in pesos.items()) / tot if tot else 0.0


def motivo_audio(a: dict) -> str:
    b, s = a["bruto"], a["subscores"]
    return (f"energia {b['energia_db']:+.1f} dB vs. sua média (p{s['energia']:.0f}), "
            f"variação p{s['variacao']:.0f}, {b['ritmo_wps']:.1f} palavras/s, "
            f"{b['ar_morto'] * 100:.0f}% de ar morto")


def final(c: dict, nota: dict, cfg: dict) -> dict:
    w = cfg["pesos"]
    dims = {k: v["nota"] for k, v in nota["dimensoes"].items()}
    texto = media(dims, w["texto"])
    auto = c["autocontencao"]
    partes = {"texto": texto, "audio": c["audio"]["nota"], "autocontencao": auto["nota"]}
    sub = {k: {"nota": v["nota"], "motivo": v["motivo"]} for k, v in nota["dimensoes"].items()}
    sub["audio"] = {"nota": c["audio"]["nota"], "motivo": motivo_audio(c["audio"])}
    sub["autocontencao"] = {"nota": auto["nota"],
                            "motivo": "; ".join(auto["motivos"]) or "se sustenta sozinho"}
    return {"score_final": round(media(partes, w["final"])), "score_texto": round(texto, 1),
            "subscores": sub}

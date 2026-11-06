"""Estágio 6 — a nota de viralização, 0–100.

    final = texto·w_texto + áudio·w_audio + autocontenção·w_auto

com `texto` a média ponderada das cinco dimensões. Todos os pesos vêm de
`pesos` no config — nada fixo aqui. Cada parcela sai com o motivo, porque a
galeria mostra por que o corte recebeu aquela nota.

ALERTAS (`sinais_audio.alertas`: fala de outra pessoa no meio, fala sem
texto, referência à live) descontam DEPOIS da média, em pontos, pelos pesos
de `alertas` no config — e de novo depois do ranking comparativo
(`aplicar_alertas`), porque `ranking.aplicar` SUBSTITUI a nota do lote: sem
isso o desconto sumia na primeira comparação.
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


def desconto(alertas: list[dict], cfg: dict) -> tuple[int, list[str]]:
    """(pontos a descontar, ≤ 0; os alertas que descontaram). Cada tipo tem o
    seu peso e o seu teto (`<tipo>_max`): três referências à live não valem
    o mesmo que três interjeições."""
    al = cfg.get("alertas") or {}
    por: dict[str, float] = {}
    motivos = []
    for a in alertas:
        v = al.get(a["tipo"], 0)
        if not v:
            continue
        por[a["tipo"]] = por.get(a["tipo"], 0) + v
        motivos.append(a["texto"])
    return round(sum(max(v, al.get(f"{k}_max", v)) for k, v in por.items())), motivos


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
    out = {"score_final": round(media(partes, w["final"])), "score_texto": round(texto, 1),
           "subscores": sub}
    d, mot = desconto(c.get("alertas") or [], cfg)
    if d:
        # vai no motivo da autocontenção: a galeria já mostra esse motivo, e o
        # alerta é isso — o corte depende de algo que quem assiste não tem
        out["score_final"] = max(0, out["score_final"] + d)
        out["desconto_alertas"] = d
        sub["autocontencao"]["motivo"] += f"; alertas {d}: " + "; ".join(mot)
    return out


def aplicar_alertas(cortes: list[dict], cfg: dict) -> list[dict]:
    """Depois do ranking: o desconto dos alertas de novo sobre a nota
    comparativa (e as versões, que andam junto), e a ordem refeita."""
    for c in cortes:
        d, _ = desconto(c.get("alertas") or [], cfg)
        if not d:
            continue
        c["score_final"] = max(0, c["score_final"] + d)
        c["desconto_alertas"] = d
        for v in (c.get("variantes") or {}).values():
            v["score"] = max(0, min(100, v["score"] + d))
    return sorted(cortes, key=lambda c: -c["score_final"])

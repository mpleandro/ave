"""Estágio 6b — ranking COMPARATIVO: todos os finalistas lidos juntos.

A avaliação de texto lê em lotes de 8, e a nota de um lote não conversa com a
do outro: um 75 do lote 1 e um 75 do lote 3 foram dados olhando vizinhos
diferentes. Na primeira fonte real os 10 cortes ficaram espremidos entre 69 e
79 — a galeria ordenava, mas a nota não dizia o quanto um era melhor que o
outro.

Aqui o avaliador vê TODOS os cortes que sobraram do dedupe de uma vez e devolve
a ordem e uma nota que ESPALHA (o melhor 85–95, o mediano por volta de 65, o
fraco abaixo de 50). A ideia é do SupoClip (rerank depois do dedupe); a
rubrica é a nossa. A nota comparativa substitui a do lote; a diferença é
somada às versões do corte, que continuam a subir ou descer a partir dela.
"""
from __future__ import annotations

import hashlib

RUBRICA = """\
Abaixo estão TODOS os cortes finalistas de um mesmo vídeo, já avaliados um a um
em lotes. Agora compare-os ENTRE SI e devolva a ordem final e uma nota de 0 a
100 para cada um.

Objetivo dos cortes: {objetivo}. Público: {publico}.

Critérios, nesta ordem de peso:
1. gancho — o que toca nos 3 primeiros segundos faz parar de rolar a tela?
2. se sustenta sozinho — quem não viu o resto do vídeo entende e se importa?
3. paga — o fim entrega o que o gancho prometeu?
4. especificidade e energia — exemplo concreto, número, cena; voz viva
5. compartilhável — "preciso mandar isso para alguém"

ESPALHE as notas: o melhor fica entre 85 e 95, o mediano por volta de 65, o
fraco abaixo de 50. Empate só quando forem mesmo equivalentes. A nota do lote
vem como referência — mude o quanto a comparação pedir. A ordem é a das notas
(a primeira é a maior).

Grave em {destino} um objeto JSON {{"{chave}": {{"ordem": [
  {{"id": "c0000", "score": 0, "motivo": "uma frase COMPARATIVA: por que
   está acima ou abaixo dos vizinhos"}}, …]}}}}, com TODOS os ids abaixo.

"""


def chave(cortes: list[dict]) -> str:
    return hashlib.sha1("|".join(sorted(c["chave_nota"] for c in cortes)).encode()).hexdigest()[:12]


def pedido(cortes: list[dict]) -> dict:
    return {"chave": chave(cortes), "cortes": cortes}


def prompt(pedidos: list[dict], contexto: dict) -> str:
    p = pedidos[0]
    partes = [RUBRICA.format(objetivo=contexto.get("objetivo") or "alcance",
                             publico=contexto.get("publico") or "deduza do próprio conteúdo",
                             destino=contexto.get("destino", "analise/ranking.json"),
                             chave=p["chave"])]
    for c in sorted(p["cortes"], key=lambda c: -c["score_final"]):
        partes.append(
            f"### {c['id']} · nota do lote {c['score_final']} · {c['dur']:.0f}s · "
            f"\"{c['titulo_sugerido']}\"\n"
            f"Primeiros 3s: {c.get('abertura_3s', '')}\n"
            f"Gancho: {c['gancho'].get('tipo')} · {c['motivo']}\n"
            f"Texto: {c['texto']}\n\n")
    return "".join(partes)


def validar(r: dict, cortes: list[dict]) -> list[str]:
    erros = []
    ordem = r.get("ordem") or []
    ids = [x.get("id") for x in ordem]
    faltam = {c["id"] for c in cortes} - set(ids)
    if faltam:
        erros.append(f"faltam ids no ranking: {sorted(faltam)}")
    if len(ids) != len(set(ids)):
        erros.append("id repetido no ranking")
    for x in ordem:
        if not isinstance(x.get("score"), (int, float)) or not 0 <= x["score"] <= 100:
            erros.append(f"{x.get('id')}: score fora de 0–100")
        if not x.get("motivo"):
            erros.append(f"{x.get('id')}: motivo vazio")
    return erros


def aplicar(r: dict, cortes: list[dict]) -> list[dict]:
    """Os cortes na ordem do ranking, com a nota comparativa. A nota é forçada a
    não subir ao descer a lista (a ordem manda, como no SupoClip), e a nota do
    lote fica guardada em `score_lote` — a tela mostra as duas."""
    por_id = {c["id"]: c for c in cortes}
    out, teto = [], 100
    for x in r["ordem"]:
        c = por_id.get(x["id"])
        if not c:
            continue
        nota = min(int(round(x["score"])), teto)
        teto = nota
        delta = nota - c["score_final"]
        c["score_lote"] = c["score_final"]
        c["score_final"] = nota
        c["motivo_ranking"] = x["motivo"]
        for v in (c.get("variantes") or {}).values():
            v["score"] = max(0, min(100, v["score"] + delta))
        out.append(c)
    return out

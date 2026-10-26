#!/usr/bin/env python3
"""Garimpo de CORTES — de um vídeo longo, os trechos com mais chance de viralizar.

    uv run python helpers/transcribe.py <video> --edit-dir "<pasta>/<stem>_cortes"
    uv run python helpers/garimpo_cortes.py <video>              # tudo o que der
    uv run python helpers/garimpo_cortes.py <video> prefiltro    # só até o estágio
    uv run python helpers/cortes_view.py <video>                 # a galeria

Estágios (um arquivo cada em helpers/cortes/), cada um grava
`<stem>_cortes/analise/<estagio>.json`:

  candidatos  janelas de 20–90s em fronteira de frase              (sem custo)
  prefiltro   áudio + autocontenção + gancho prévio → finalistas    (sem custo)
  avaliar     o modelo lê as finalistas → notas, título, gancho;
              depois score, refino de bordas, dedupe, top N, thumbs

Quando faltam notas, `avaliar` escreve `analise/para_avaliar.md` e sai com
código 2: o modelo da sessão lê, grava `analise/notas.json` e roda de novo.
Parâmetros e pesos: `helpers/cortes/config.json`, sobrescrevíveis por projeto
em `<stem>_cortes/cortes_config.json`.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cortes import autocontencao as A  # noqa: E402
from cortes import bordas as B  # noqa: E402
from cortes import candidatos as C  # noqa: E402
from cortes import fala as FL  # noqa: E402
from cortes import fonte as F  # noqa: E402
from cortes import legenda as L  # noqa: E402
from cortes import llm  # noqa: E402
from cortes import prefiltro as P  # noqa: E402
from cortes import ranking as RK  # noqa: E402
from cortes import score as S  # noqa: E402
from cortes import selecao as SEL  # noqa: E402
from cortes import sinais_audio as SA  # noqa: E402
from cortes import sinais_texto as T  # noqa: E402
from cortes import thumbs as TH  # noqa: E402
from cortes import variantes as VR  # noqa: E402
from cortes import verificar as V  # noqa: E402
from voice_levels import estimate_floor  # noqa: E402

ETAPAS = ("candidatos", "prefiltro", "avaliar")


def hms(t: float) -> str:
    return f"{int(t // 60):02d}:{int(t % 60):02d}"


class Fonte:
    """O que vários estágios leem — carregado uma vez, sob demanda."""

    def __init__(self, video: Path, trab: Path, cfg: dict):
        self.video, self.trab, self.cfg = video, trab, cfg
        self._ws = self._sil = self._frs = None

    @property
    def ws(self):
        if self._ws is None:
            self._ws = F.carregar_palavras(self.trab, self.video)
        return self._ws

    @property
    def sil(self):
        if self._sil is None:
            self._sil = F.silencios(self.video)
        return self._sil

    @property
    def frs(self):
        if self._frs is None:
            t, db = F.energia(self.video)
            # limiar de voz: 6 dB acima do piso da sala — o "Mas" dito baixinho
            # fica ~20 dB acima do piso, o respiro antes do verbo cai nele
            self._frs = C.montar_frases(self.ws, self.sil, (t, db, estimate_floor(db) + 6))
        return self._frs


def palavras_do_corte(frs: list[dict], c: dict) -> list[dict]:
    """O texto do corte palavra a palavra (tempo da fonte), sem o conectivo que
    o refino tirou — é o texto da legenda; o tempo dela vem de ouvir o corte."""
    i, j = c["frases"]
    ws = [{"w": w["w"], "s": w["s"], "e": w["e"]} for f in frs[i:j + 1] for w in f["ws"]]
    tirou = (c.get("refinado") or {}).get("tirou")
    return ws[len(tirou.split()):] if tirou else ws


def versoes(f: Fonte, c: dict, r: dict, nota: dict, pop: dict, energia, piso: float) -> None:
    """As versões do corte — toda combinação das peças disponíveis (gancho
    puxado, sem respiros, erros de fala corrigidos) —, cada uma com duração e
    score previstos. É esse score que a galeria passa a mostrar quando a
    pessoa aplica as recomendações.

    O score é recalculado, não chutado:
    - respiros/erros: o áudio é remedido no corte encurtado (ar morto, palavras
      por segundo) contra a MESMA régua de percentis da fonte;
    - gancho puxado: a nota de gancho vira a `nota_se_puxar` da avaliação.
    O resto da nota não muda."""
    a, b = VR.janela(c)
    marcas = VR.marcas_respiro(f.video, f.trab, a, b)
    limpeza = FL.limpar(f.video, c, (a, b), (energia[0], energia[1], piso + 6))
    fala = limpeza["aprovadas"]
    c["respiros"], c["fala"], c["fala_mantida"] = marcas, fala, limpeza["mantidas"]

    alinhadas = L.alinhar(c.get("palavras") or [], L.ouvir(f.video, a, b), b - a)
    c["transcricao"] = VR.transcricao(c, alinhadas, a)

    def audio(segs, sairam):
        dur = VR.duracao(segs)
        morto = sum(max(0.0, min(sb, y) - max(sa, x)) for sa, sb in f.sil for x, y in segs
                    if min(sb, y) - max(sa, x) >= f.cfg["audio"]["ar_morto_s"])
        bruto = {**r["audio"]["bruto"], "ritmo_wps": round((r["n_palavras"] - sairam) / dur, 2),
                 "ar_morto": round(morto / dur, 3)}
        return SA.nota_contra(bruto, pop, f.cfg)

    def score(aud=None, gancho=None):
        n = nota
        if gancho is not None:
            n = {**nota, "dimensoes": {**nota["dimensoes"],
                                       "gancho": {**nota["dimensoes"]["gancho"], "nota": gancho}}}
        return S.final({**r, "audio": aud or r["audio"]}, n, f.cfg)["score_final"]

    g = nota["gancho"]
    trecho = None
    if g["tipo"] == "puxar" and g.get("nota_se_puxar") is not None:
        trecho = VR.trecho_gancho(f.video, c, g["frase"], (a, b), energia)
    disponiveis = [p for p, ok in (("gancho", trecho), ("respiros", marcas), ("falhas", fala)) if ok]

    var = {"original": {"dur": round(b - a, 1), "score": c["score_final"]}}
    for m in range(1, 2 ** len(disponiveis)):
        ps = {p for i, p in enumerate(disponiveis) if m >> i & 1}
        corpo = VR.remover(a, b, marcas if "respiros" in ps else [], fala if "falhas" in ps else [])
        sairam = sum(len(t["texto"].split()) for t in fala) if "falhas" in ps else 0
        aud = audio(corpo, sairam) if ps & {"respiros", "falhas"} else None
        extra = (trecho[1] - trecho[0]) if "gancho" in ps else 0.0
        v = {"dur": round(VR.duracao(corpo) + extra, 1),
             "score": score(aud, g["nota_se_puxar"] if "gancho" in ps else None)}
        if "gancho" in ps:
            v["trecho"] = list(trecho)
        var[VR.chave(ps)] = v
    c["variantes"] = var
    c["pecas"] = {"gancho": {"score": var["gancho"]["score"]} if trecho else None,
                  "respiros": {"n": len(marcas)} if marcas else None,
                  "falhas": {"aprovadas": [t["texto"] for t in fala],
                             "tipos": FL.resumo(fala)} if fala else None}


def quantos_cortes(f: Fonte, dur_fonte: float) -> int:
    """`contexto.cortes`: um número fixo, ou "auto" — um corte a cada
    `por_minutos` de fonte, entre `min` e `max` (a proporção do SupoClip: uma
    hora de aula rende mais cortes bons que dez minutos)."""
    n = f.cfg["contexto"]["cortes"]
    if n != "auto":
        return int(n)
    a = f.cfg["ranking"]
    return max(a["min"], min(a["max"], round(dur_fonte / 60 / a["por_minutos"])))


def primeiros_3s(ws: list[dict]) -> str:
    """O que toca nos 3 primeiros segundos, contado pelas palavras DO CORTE.
    Pelo relógio da fonte não dá: os tempos de palavra chegam adiantados, e o
    "parem" de "Parem de ser chatos" ficava antes do início verificado — a
    tela mostrava "De ser chatos"."""
    return " ".join(w["w"] for w in ws if w["s"] - ws[0]["s"] < 3.0) if ws else ""


def etapa_candidatos(f: Fonte) -> None:
    cands = C.gerar(f.frs, f.cfg)
    p = F.salvar(f.trab, "candidatos", {"fonte": str(f.video), "n_frases": len(f.frs),
                                        "candidatos": cands})
    durs = sorted(c["dur"] for c in cands)
    print(f"[candidatos] {len(f.ws)} palavras · {len(f.frs)} frases · {len(cands)} janelas "
          f"(mediana {durs[len(durs) // 2] if durs else 0}s) → {p.name}")


def etapa_prefiltro(f: Fonte) -> None:
    cands = F.ler(f.trab, "candidatos")["candidatos"]
    times, levels = F.energia(f.video)
    floor_db = estimate_floor(levels)
    medidas = SA.medir(cands, times, levels, floor_db, f.sil, f.cfg)
    audio = SA.notas(medidas, f.cfg)
    auto = [A.avaliar(c, f.cfg) for c in cands]
    pont = P.pontuar(cands, audio, auto, f.ws, f.cfg)
    fin = P.finalistas(pont, f.cfg)
    descartados = sum(a["nota"] < f.cfg["prefiltro"]["autocontencao_min"] for a in auto)
    F.salvar(f.trab, "prefiltro", {"floor_db": floor_db, "populacao_audio": SA.populacao(medidas),
                                   "n_janelas": len(cands), "finalistas": fin})
    print(f"[prefiltro] {len(cands)} janelas · {descartados} reprovadas em autocontenção · "
          f"{len(fin)} finalistas sem sobreposição")
    for c in fin[:10]:
        motivos = "; ".join(c["autocontencao"]["motivos"]) or "ok"
        print(f"  {c['id']} {hms(c['start'])}–{hms(c['end'])} prévia {c['previa']:>5} · "
              f"áudio {c['audio']['nota']:>5} · auto {c['autocontencao']['nota']:>3} ({motivos}) · "
              f"gancho {c['gancho_previo']['nota']:.0f} {c['gancho_previo']['tags'] or ''}")
        print(f"      \"{c['abertura'][:90]}\"")
    if len(fin) > 10:
        print(f"  … e mais {len(fin) - 10}")


def etapa_avaliar(f: Fonte) -> None:
    pre = F.ler(f.trab, "prefiltro")
    fin = pre["finalistas"]
    pedidos = [T.pedido(c, f.frs, f.cfg) for c in fin]
    ctx = {**f.cfg["contexto"], "destino": str(f.trab / "analise" / "notas.json")}
    av = llm.provedor(f.cfg.get("avaliador", "sessao"), f.trab, T.prompt)
    try:
        notas = av.avaliar(pedidos, ctx)
    except llm.Pendente as e:
        print(f"[avaliar] {e.faltam} finalista(s) sem nota.\n"
              f"  leia   {e.arquivo}\n  grave  {e.destino}\n  e rode de novo esta etapa.")
        raise SystemExit(2)

    erros = {p["id"]: T.validar(notas[p["chave"]], p) for p in pedidos}
    erros = {k: v for k, v in erros.items() if v}
    if erros:
        for k, v in erros.items():
            print(f"  {k}: {'; '.join(v)}")
        raise SystemExit(f"[avaliar] {len(erros)} nota(s) fora do esquema — corrija notas.json")

    times, levels = F.energia(f.video)
    pop = pre["populacao_audio"]
    avaliados, contexto = [], {}
    for c, p in zip(fin, pedidos):
        nota = notas[p["chave"]]
        recusado = None
        if nota.get("aparar_conector"):
            # o ponto exato sem o conectivo é conferido ouvindo (verificar.py);
            # sem confirmação o conectivo fica — melhor um "Mas" que uma palavra comida
            ap = f.frs[c["frases"][0] + nota["inicio"]]["apara"]
            ponto = V.ponto_de_corte(f.video, ap)
            if ponto is None:
                nota, recusado = {**nota, "aparar_conector": False}, ap["tirou"]
            else:
                ap["s"] = ponto
        r = B.refinar(c, nota, f.frs, f.cfg)
        if recusado:
            r = {**r, "refinado": {**(r.get("refinado") or {}), "manteve": recusado}}
        if r is not c:   # janela mudou: áudio e autocontenção são remedidos
            m = SA.medir([r], times, levels, pre["floor_db"], f.sil, f.cfg)[0]
            r["audio"] = SA.nota_contra(m, pop, f.cfg)
            r["autocontencao"] = A.avaliar(r, f.cfg)
        sc = S.final(r, nota, f.cfg)
        contexto[c["id"]] = (r, nota)
        avaliados.append({
            **{k: r[k] for k in ("id", "start", "end", "dur", "frases", "n_palavras", "borda",
                                 "abertura", "fechamento", "texto")},
            **sc,
            "abertura_3s": primeiros_3s(palavras_do_corte(f.frs, r)),
            "palavras": palavras_do_corte(f.frs, r),
            "ritmo": SA.respiros(r["start"], r["end"], f.sil, f.cfg),
            "titulo_sugerido": nota["titulo_sugerido"], "frase_gancho": nota.get("frase_gancho", ""),
            "motivo": nota["motivo"], "gancho": nota["gancho"],
            "refinado": r.get("refinado"), "previa": c["previa"],
            "ruido": bool(nota.get("ruido", False)), "chave_nota": p["chave"]})

    # Ruído (bastidor da live) e nota abaixo do mínimo não entram na galeria.
    # duas réguas: a do LOTE (entra na comparação) e a da GALERIA (nota_min,
    # sobre a nota comparativa, aplicada depois do ranking)
    validos = [c for c in avaliados
               if not c["ruido"] and c["score_final"] >= f.cfg["selecao"]["nota_min_lote"]]
    excluidos = len(avaliados) - len(validos)
    finalistas = SEL.podar(validos, "score_final", f.cfg["ranking"]["max"],
                           f.cfg["prefiltro"]["sobreposicao_max"])

    # ranking comparativo: todos os finalistas lidos juntos (ranking.py)
    pedido = RK.pedido(finalistas)
    av_r = llm.provedor(f.cfg.get("avaliador", "sessao"), f.trab, RK.prompt,
                        ("para_ranquear.md", "ranking.json"))
    try:
        rk = av_r.avaliar([pedido], {**f.cfg["contexto"],
                                     "destino": str(f.trab / "analise" / "ranking.json")})[pedido["chave"]]
    except llm.Pendente as e:
        print(f"[avaliar] notas ok · falta o ranking comparativo de {len(finalistas)} finalistas.\n"
              f"  leia   {e.arquivo}\n  grave  {e.destino}\n  e rode de novo esta etapa.")
        raise SystemExit(2)
    erros = RK.validar(rk, finalistas)
    if erros:
        raise SystemExit("[avaliar] ranking fora do esquema: " + "; ".join(erros))

    n = quantos_cortes(f, float(times[-1]))
    por_id = {c["id"]: c for c in finalistas}
    # abaixo da nota mínima (pela nota COMPARATIVA) nem entra: não gasta o
    # processamento das versões (respiros, fala, gancho, capa) num corte que
    # não vai para a tela
    top = [por_id[x["id"]] for x in rk["ordem"]
           if x["id"] in por_id and x["score"] >= f.cfg["selecao"]["nota_min"]][:n]
    # a escuta local (conferir conectivo, gancho e erros de fala ouvindo) se
    # instala aqui na primeira vez; fora do Apple Silicon ela não existe, e
    # cada estágio que ouve cai para o caminho seguro (ver os módulos)
    import instalar  # noqa: PLC0415
    if instalar.disponivel("escuta")[0]:
        instalar.garantir("escuta")
    for c in top:   # versões na escala do lote; o ranking desloca tudo junto
        r, nota = contexto[c["id"]]
        versoes(f, c, r, nota, pop, (times, levels), pre["floor_db"])
    top = [c for c in RK.aplicar(rk, top) if c["score_final"] >= f.cfg["selecao"]["nota_min"]]
    TH.gerar(f.video, top, f.trab / "analise" / "thumbs")
    for k, c in enumerate(top, 1):
        c["rank"] = k
    F.salvar(f.trab, "selecao", {"fonte": str(f.video), "avaliados": len(avaliados),
                                 "excluidos": excluidos, "cortes": top})
    print(f"[avaliar] {len(avaliados)} avaliados · {excluidos} excluídos (ruído ou nota do lote < "
          f"{f.cfg['selecao']['nota_min_lote']}) · galeria: nota comparativa ≥ "
          f"{f.cfg['selecao']['nota_min']} → {len(top)} cortes")
    for c in top:
        print(f"  #{c['rank']:<2} {c['score_final']:>3}  {hms(c['start'])}–{hms(c['end'])} "
              f"({c['dur']:.0f}s) {c['titulo_sugerido']}  [gancho: {c['gancho']['tipo']}]")


def main() -> None:
    ap = argparse.ArgumentParser(description="Garimpa cortes virais de um vídeo longo.")
    ap.add_argument("video", type=Path)
    ap.add_argument("etapa", nargs="?", choices=ETAPAS, default="avaliar",
                    help="roda até este estágio (padrão: tudo)")
    ap.add_argument("--so", action="store_true", help="roda só o estágio pedido")
    ap.add_argument("--trabalho", type=Path, help="padrão: <pasta do vídeo>/<stem>_cortes")
    a = ap.parse_args()
    video = a.video.resolve()
    trab = (a.trabalho or F.pasta_trabalho(video)).resolve()
    f = Fonte(video, trab, F.config(trab))
    fazer = {"candidatos": etapa_candidatos, "prefiltro": etapa_prefiltro,
             "avaliar": etapa_avaliar}
    alvo = ETAPAS.index(a.etapa)
    for i, nome in enumerate(ETAPAS[:alvo + 1]):
        if a.so and i < alvo:
            continue
        fazer[nome](f)


if __name__ == "__main__":
    main()

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

POR FRASE (só nas finalistas, para o lote do avaliador) — o que o texto não
mostra e a live Mil Milionários (2026-11) provou que muda o corte:

- QUEM FALA (`falantes`, `quem_frase`, `turnos`): com `<stem>_cortes/elenco.json`
  a voz de cada meio segundo vira um nome (`elenco.quem_fala`). No "pneu do
  Gol" (9689–9721s) a Júlia fala de 16,5 a 21s no meio da história do Paulo, e
  o avaliador, lendo só o texto, não tinha como saber. Sem elenco, nada é
  marcado — um rótulo inventado seria pior que nenhum: agrupar vozes sem saber
  quantas há (`voz.diarizar` pede o N) parte UMA voz em duas numa janela de um
  falante só, e cada pedaço viraria uma "interjeição" falsa.
- PICO DE VOZ (`niveis_frase`, `marcar_picos`): P90 dos quadros com voz da
  frase contra a MEDIANA DO FALANTE nas finalistas. "Eu era pobre, filho!"
  fica +7 dB acima do resto do corte, e foi o gancho que o usuário escolheu à
  mão; a avaliação de texto tinha escolhido "Um dia eu não tive dinheiro…".
  Pelo falante, não pela fonte: o microfone de mão da Júlia fica 3,3 dB abaixo
  da média e ela pareceria sempre "sem energia".
- LACUNA DE TRANSCRIÇÃO (`lacunas`): ≥ 2s entre INÍCIOS de palavra com ≥ 1,2s
  de voz dentro — a fala existe e o texto não. A ideia da densidade do
  `transcript_audit.py`: o Whisper estica o fim da palavra por cima do buraco,
  então só o início da palavra é confiável. No mesmo corte ele engoliu ~5s do
  Paulo ("duas mansões…") e escreveu "pai, fala..." no lugar.
- ALERTAS (`alertas`): o que disso pesa contra o corte final — fala curta de
  outra pessoa (no meio; na borda, menos pergunta no início), lacuna e
  referência à live. `score.desconto` dá o peso.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter

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


# --------------------------------------------------------------- por frase

BLOCO_FALA_S = 30.0   # quem fala é medido (e guardado) em blocos fixos da fonte


def _quadro(times: np.ndarray) -> float:
    return float(np.median(np.diff(times[:2000]))) if len(times) > 1 else 0.021


def niveis_frase(f: dict, times: np.ndarray, levels: np.ndarray, limiar: float) -> tuple[float | None, float]:
    """(P90 dos quadros com voz em dB, segundos com voz) da frase."""
    i0, i1 = np.searchsorted(times, [f["s"], f["e"]])
    lv = levels[i0:i1]
    voz = lv[lv > limiar]
    return (round(float(np.percentile(voz, 90)), 2) if voz.size else None,
            round(voz.size * _quadro(times), 2))


def lacunas(ws: list[dict], times: np.ndarray, levels: np.ndarray, limiar: float,
            cfg: dict) -> list[dict]:
    """Trechos com fala e sem palavra: ≥ `lacuna_vao_s` entre os INÍCIOS de duas
    palavras vizinhas e ≥ `lacuna_voz_s` de voz depois da primeira (ela mesma
    conta no máximo `palavra_max_s` — o Whisper estica o fim dela por cima)."""
    sc = cfg["sinais"]
    q = _quadro(times)
    out = []
    for w0, w1 in zip(ws, ws[1:]):
        if w1["s"] - w0["s"] < sc["lacuna_vao_s"]:
            continue
        a = w0["s"] + min(max(0.0, w0["e"] - w0["s"]), sc["palavra_max_s"])
        i0, i1 = np.searchsorted(times, [a, w1["s"]])
        voz = float((levels[i0:i1] > limiar).sum()) * q
        if voz < sc["lacuna_voz_s"]:
            continue
        if out and out[-1]["ate"] == round(w0["s"], 2):
            # palavra solta no meio do buraco ("…fala… [8s] …pai,") é o mesmo buraco:
            # a densidade do trecho todo é que está errada, não dois trechos
            out[-1]["ate"], out[-1]["voz"] = round(w1["s"], 2), round(out[-1]["voz"] + voz, 1)
            out[-1]["palavras"] += 1
            continue
        out.append({"de": round(w0["s"], 2), "ate": round(w1["s"], 2),
                    "voz": round(voz, 1), "depois_de": w0["w"], "palavras": 1})
    return out


def assinatura_elenco(el: dict) -> str:
    return hashlib.sha1(json.dumps([[p["nome"], p["voz"]] for p in el["pessoas"]]).encode()).hexdigest()[:12]


def falantes(video, a: float, b: float, el: dict, passo: float) -> list[tuple[float, str | None]]:
    """[(instante na fonte, nome | None)] a cada `passo` em [a, b].

    Em blocos fixos de BLOCO_FALA_S, cada um em cache (`derivado`): o refino de
    bordas e outra rodada com outras finalistas reaproveitam o que já foi
    ouvido. Medido: ~25 ms por passo de 0,5s; 90 finalistas ≈ 4 min na
    primeira vez."""
    import sys  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from derivado import derivado  # noqa: PLC0415

    from . import elenco as EL  # noqa: PLC0415
    ass = assinatura_elenco(el)
    out: list[tuple[float, str | None]] = []
    b0 = math.floor(a / BLOCO_FALA_S) * BLOCO_FALA_S
    while b0 < b:
        # `quem_fala` ouve 0,75s antes do passo; no bloco 0 isso cairia antes do 0
        c0 = max(b0, 0.75)
        rot = derivado("falantes_garimpo", [Path(video)],
                       {"de": c0, "ate": b0 + BLOCO_FALA_S, "passo": passo, "elenco": ass}, "1",
                       lambda c0=c0, b0=b0: EL.quem_fala(Path(video), 0.0, c0, b0 + BLOCO_FALA_S, el, passo))
        for k, q in enumerate(rot):
            t = c0 + k * passo
            if a - passo / 2 <= t <= b + passo / 2:
                out.append((round(t, 2), q))
        b0 += BLOCO_FALA_S
    return out


def quem_frase(passos: list[tuple[float, str | None]], s: float, e: float,
               maioria: float) -> str | None:
    """O nome de quem fala a frase: a maioria (≥ `maioria`) dos passos com voz
    reconhecida dentro dela; "?" quando dividida; None sem voz reconhecida.
    Frase mais curta que um passo fica com o passo mais perto (até 0,5s)."""
    rot = [q for t, q in passos if s <= t <= e and q]
    if not rot:
        perto = [(abs(t - (s + e) / 2), q) for t, q in passos if q and abs(t - (s + e) / 2) <= 0.5]
        return min(perto)[1] if perto else None
    nome, n = Counter(rot).most_common(1)[0]
    return nome if n / len(rot) >= maioria else "?"


def turnos(passos: list[tuple[float, str | None]], passo: float, min_passos: int) -> list[list]:
    """[[nome, de, até]] — trechos contínuos de uma voz. Passo sem voz
    reconhecida não quebra o turno; turno com menos de `min_passos` passos é
    engolido pelo vizinho (a janela de 1,5s do `quem_fala` borra ±0,75s, e um
    passo solto é mais provável erro que fala). Na Mil Milionários, com 2
    passos 30 das 94 "interjeições" tinham ≤ 1,5s — o borrão da janela; com 3
    (o padrão do config), 4 de 63."""
    rot = [(t, q) for t, q in passos if q]
    runs: list[list] = []
    for t, q in rot:
        if runs and runs[-1][0] == q:
            runs[-1][2] = t
            runs[-1][3] += 1
        else:
            runs.append([q, t, t, 1])
    mudou = True
    while mudou and len(runs) > 1:
        mudou = False
        for k, r in enumerate(runs):
            if r[3] >= min_passos:
                continue
            viz = k - 1 if k > 0 else k + 1
            v = runs[viz]
            v[1], v[2], v[3] = min(v[1], r[1]), max(v[2], r[2]), v[3] + r[3]
            del runs[k]
            mudou = True
            break
        k = 1
        while k < len(runs):            # vizinhos com a mesma voz viram um turno
            if runs[k][0] == runs[k - 1][0]:
                runs[k - 1][2], runs[k - 1][3] = runs[k][2], runs[k - 1][3] + runs[k][3]
                del runs[k]
            else:
                k += 1
    out = []
    for k, (q, t0, t1, _) in enumerate(runs):
        de = (runs[k - 1][2] + t0) / 2 if k else t0 - passo / 2
        ate = (t1 + runs[k + 1][1]) / 2 if k + 1 < len(runs) else t1 + passo / 2
        out.append([q, round(de, 2), round(ate, 2)])
    return out


def principal(tur: list[list], a: float, b: float) -> str | None:
    """Quem mais fala em [a, b]."""
    tempo: Counter = Counter()
    for q, de, ate in tur:
        tempo[q] += max(0.0, min(ate, b) - max(de, a))
    return tempo.most_common(1)[0][0] if tempo and tempo.most_common(1)[0][1] > 0 else None


def falas_curtas(tur: list[list], a: float, b: float, max_s: float) -> list[dict]:
    """As falas de OUTRA pessoa (não a principal) de até `max_s` dentro de
    [a, b], com o lado: "meio" (a principal fala antes e depois), "inicio" ou
    "fim" (encostada na borda)."""
    p = principal(tur, a, b)
    out = []
    for q, de, ate in tur:
        de_, ate_ = max(de, a), min(ate, b)
        if q == p or ate_ - de_ <= 0 or ate_ - de_ > max_s:
            continue
        lado = "inicio" if de_ <= a + 0.5 else "fim" if ate_ >= b - 0.5 else "meio"
        out.append({"quem": q, "de": round(de_, 2), "ate": round(ate_, 2), "lado": lado,
                    "principal": p})
    return out


def marcar_picos(niveis: list[tuple[int, str | None, float | None, float]],
                 ref: dict[str | None, float], cfg: dict) -> dict[int, float]:
    """{índice da frase: dB acima da mediana do falante} das frases de PICO da
    janela: ≥ `pico_db` acima da mediana de quem fala, ≥ `pico_janela_db`
    acima da mediana das frases da própria janela (senão um trecho todo
    gritado marcaria tudo) e entre as `pico_top` mais altas — o lote só fala
    do que se destaca. `niveis` = [(índice, quem, P90, segundos com voz)];
    `ref` = mediana por falante, com a geral em `ref[None]`.

    Calibrado nas 90 finalistas da Mil Milionários: com 4 dB / 3 dB, 55 das 90
    janelas tinham PICO — marca em toda janela não diz nada; com 5 / 5, 26 de
    90, e no "pneu do Gol" só "Eu era pobre, filho!" (+6,9 dB) continua."""
    sc = cfg["sinais"]
    vals = [v for _, _, v, _ in niveis if v is not None]
    if len(vals) < 3:
        return {}
    med_j = float(np.median(vals))
    cand = []
    for g, quem, v, voz in niveis:
        if v is None or voz < sc["pico_voz_min_s"]:
            continue
        d = v - ref.get(quem, ref[None])
        if d >= sc["pico_db"] and v - med_j >= sc["pico_janela_db"]:
            cand.append((d, g))
    return {g: round(d, 1) for d, g in sorted(cand, reverse=True)[:sc["pico_top"]]}


def referencias(niveis: list[tuple[int, str | None, float | None, float]], min_frases: int = 8) -> dict:
    """Mediana do P90 por falante (com ≥ `min_frases` frases) e a geral em None."""
    por: dict = {}
    for _, q, v, _ in niveis:
        if v is not None:
            por.setdefault(q, []).append(v)
    tudo = [v for vs in por.values() for v in vs]
    ref = {q: float(np.median(vs)) for q, vs in por.items() if q not in (None, "?") and len(vs) >= min_frases}
    ref[None] = float(np.median(tudo)) if tudo else 0.0
    return ref


def anotar(fin: list[dict], frs: list[dict], video, energia, cfg: dict, el: dict | None) -> dict:
    """O que o lote do avaliador mostra por frase, para as finalistas:

        {"elenco": bool, "passo": s, "passos": {id: [(t, nome)]},
         "quem": {frase: nome | "?" | None}, "nivel": {frase: (P90, voz_s)},
         "ref": {nome: mediana do P90, None: geral}}

    Quem fala só com elenco (`el`); sem ele `quem` e `passos` ficam vazios e
    o pico é medido contra a mediana geral das frases das finalistas."""
    t, db, limiar = energia
    sc = cfg["sinais"]
    passo = sc["passo_fala_s"]
    an = {"elenco": bool(el), "passo": passo, "passos": {}, "quem": {}, "nivel": {}, "ref": {}}
    gs = sorted({g for c in fin for g in range(c["frases"][0], c["frases"][1] + 1)})
    if el:
        for c in fin:
            ps = falantes(video, c["start"], c["end"], el, passo)
            an["passos"][c["id"]] = ps
            for g in range(c["frases"][0], c["frases"][1] + 1):
                if g not in an["quem"]:
                    an["quem"][g] = quem_frase(ps, frs[g]["s"], frs[g]["e"], sc["frase_maioria"])
    for g in gs:
        an["nivel"][g] = niveis_frase(frs[g], t, db, limiar)
    an["ref"] = referencias([(g, an["quem"].get(g), *an["nivel"][g]) for g in gs])
    return an


def picos(c: dict, an: dict, cfg: dict) -> dict[int, float]:
    """{frase (índice na fonte): dB acima do normal de quem fala} na janela `c`."""
    i, j = c["frases"]
    return marcar_picos([(g, an["quem"].get(g), *an["nivel"][g]) for g in range(i, j + 1)
                         if g in an["nivel"]], an["ref"], cfg)


def falas(c: dict, an: dict, cfg: dict) -> list[list]:
    """Os turnos de voz dentro da janela `c`, em segundos DO CORTE."""
    a, b = c["start"], c["end"]
    ps = [(t, q) for t, q in an["passos"].get(c["id"], []) if a - an["passo"] <= t <= b + an["passo"]]
    if not ps:
        return []
    out = []
    for q, de, ate in turnos(ps, an["passo"], cfg["sinais"]["turno_min_passos"]):
        de, ate = max(de, a), min(ate, b)
        if ate > de:
            out.append([q, round(de - a, 1), round(ate - a, 1)])
    return out


def alertas(c: dict, frs: list[dict], an: dict, energia, cfg: dict) -> list[dict]:
    """Os defeitos que o texto esconde, na janela `c` (tempos DO CORTE):

    - interjeicao  fala curta (≤ `alertas.interjeicao_max_s`, somando tudo o
                   que ela fala no corte) de outra pessoa no meio — o "pai,
                   fala pra eles…" da Júlia no "pneu do Gol";
                   encostada na borda também conta, menos pergunta no início
                   (pergunta → resposta é abertura boa: anúncios #1 e #2).
                   Fala LONGA de outra pessoa não é alerta: é conversa, e o
                   lote já mostra os turnos (`falas:`) para o avaliador julgar
    - lacuna       fala sem texto: o transcrito engoliu algo
    - referencia_live  frase que aponta para o chat, o QR, a própria live"""
    from . import autocontencao as A  # noqa: PLC0415
    t, db, limiar = energia
    a, b = c["start"], c["end"]
    i, j = c["frases"]
    al = cfg["alertas"]
    out: list[dict] = []
    tur = falas(c, an, cfg)
    if tur:
        total: Counter = Counter()
        for q, de, ate in tur:
            total[q] += ate - de
        for x in falas_curtas([[q, de + a, ate + a] for q, de, ate in tur], a, b, al["interjeicao_max_s"]):
            de, ate = x["de"] - a, x["ate"] - a
            if total[x["quem"]] > al["interjeicao_max_s"]:
                continue        # conversa (fala mais que isso no corte), não interjeição
            fala = " ".join(f["texto"] for f in frs[i:j + 1] if x["de"] <= (f["s"] + f["e"]) / 2 <= x["ate"])
            if x["lado"] == "inicio" and "?" in fala:
                continue
            onde = {"meio": "no meio", "inicio": "no início", "fim": "no fim"}[x["lado"]]
            out.append({"tipo": "interjeicao", "quem": x["quem"], "lado": x["lado"],
                        "de": round(de, 1), "ate": round(ate, 1),
                        "texto": f"fala de {x['quem']} {onde} ({de:.1f}–{ate:.1f}s)"})
    ws = [w for f in frs[i:j + 1] for w in f["ws"] if a - 0.05 <= w["s"] <= b]
    for g in lacunas(ws, t, db, limiar, cfg):
        de, ate = g["de"] - a, g["ate"] - a
        out.append({"tipo": "lacuna", "de": round(de, 1), "ate": round(ate, 1), "voz": g["voz"],
                    "texto": f"fala sem texto {de:.1f}–{ate:.1f}s ({g['voz']:.1f}s de voz)"})
    for k, f in enumerate(frs[i:j + 1]):
        if A.referencia_live(f["texto"], cfg):
            out.append({"tipo": "referencia_live", "k": k,
                        "texto": f"[live] \"{f['texto'][:60]}\""})
    return out

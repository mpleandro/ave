"""Detector unificado de erros de fala + EDL proposto + roteiro.

Uma passada determinística sobre o transcrito VAD-first (transcribe_local.py)
que entrega:

  <edit>/defeitos.json       o que cortar e o que perguntar, com borda acústica
  <edit>/edl_proposto.json   EDL inicial (schema do edl.json), já sem os cortes
                             de confiança alta e com os respiros do ritmo
  <edit>/roteiro.md          o texto final linha a linha, ~~riscado~~ o que sai,
                             [?N] o que depende do usuário

O modelo REVISA o roteiro e responde às perguntas; não escreve o EDL do zero.
Reaproveita as heurísticas já medidas no repo: `detect_restarts` (retake:
idêntica / truncada / semântica), `cortes/fala.py` (gaguejo colado, muletas,
GAGUEJO_1, pausa de recomeço) e `propose_breaths.RITMOS` (classes de silêncio).

Uso:
  uv run python helpers/fala_limpa.py <edit> [--fonte <video>] [--ritmo equilibrado]
  uv run python helpers/fala_limpa.py <edit> --aplicar respostas.json
      respostas.json = {"3": "cortar", "7": "manter"}  (id → decisão)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import unicodedata
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import detect_restarts as DR
from propose_breaths import RITMO_PADRAO, RITMOS

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".wav", ".m4a", ".mp3"}
MULETAS = {"ne", "tipo", "ahn", "hum", "hmm", "uh", "eh", "ee", "eee"}
GAGUEJO_1 = {"eu", "o", "a", "de", "e", "um", "uma", "se", "no", "na", "pra", "pro",
             "do", "da", "em", "ele", "ela", "voce", "isso", "esse", "essa", "ta"}
PAUSA_RECOMECO = 0.30     # entre as cópias: separa recomeço de ênfase
# Pronomes e dêiticos que o detect_restarts conta como conteúdo e aqui não:
# "se você" × "se você" é coincidência de língua, não retake.
SEM_CONTEUDO_EXTRA = {"voce", "ele", "ela", "eles", "elas", "isso", "esse", "essa", "aqui",
                      "ai", "la", "hoje", "agora", "ta", "tem", "entao"}
VAO_MULETA = 0.06         # muleta só sai isolada por um vão de cada lado
BORDA_BUSCA = 0.05        # ± em volta da borda: ponto de menor energia
CORTE_MIN = 0.08
CONF_AUTO = 0.8           # confiança a partir da qual o corte entra sozinho no EDL
SR = 16000


# --------------------------------------------------------------------------- #
# util
# --------------------------------------------------------------------------- #

def norm(t: str) -> str:
    t = unicodedata.normalize("NFD", t.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]", "", t)


def _final(txt: str) -> bool:
    """Pontuação de FIM de frase (não reticência: reticência é fala abortada)."""
    return bool(re.search(r"[.?!](?!\.)$", txt.strip())) and not txt.strip().endswith("...")


def _conteudo(ng: list[str]) -> int:
    return sum(1 for w in ng if w not in DR.FUNCIONAIS and w not in DR.MULETAS and w not in SEM_CONTEUDO_EXTRA)


def _reticencia(txt: str) -> bool:
    return txt.strip().endswith(("...", "…"))


def palavras(words: list[dict]) -> list[dict]:
    out = []
    for i, w in enumerate(words):
        if w.get("type", "word") != "word":
            continue
        txt = (w.get("text") or w.get("word") or "").strip()
        n = norm(txt)
        if not txt or not n:
            continue
        out.append({"i": len(out), "t": float(w["start"]), "fim": float(w["end"]),
                    "txt": txt, "n": n, "arquivo": "fonte"})
    return out


# --------------------------------------------------------------------------- #
# detecção
# --------------------------------------------------------------------------- #

def _gaguejos(ws: list[dict]) -> list[dict]:
    """N-grama (1–4) repetido imediatamente. Primeira cópia sai."""
    out = []
    k = 0
    while k < len(ws):
        achou = False
        for n in (4, 3, 2, 1):
            a, b = ws[k:k + n], ws[k + n:k + 2 * n]
            if len(b) < n or [x["n"] for x in a] != [x["n"] for x in b]:
                continue
            # pontuação de FIM dentro da primeira cópia = duas frases, não gaguejo
            if any(_final(x["txt"]) for x in a) or any(_final(x["txt"]) for x in b[:-1]):
                continue
            if n == 1 and (a[0]["n"] not in GAGUEJO_1 or a[0]["n"] == "que"):
                continue
            pausa = b[0]["t"] - a[-1]["fim"]
            # repetição de CONTEÚDO num fôlego só é ênfase ("não era nada não
            # era nada"); recomeço tem a pausa (ou a reticência) de quem parou
            if n > 1 and DR._conteudo([x["n"] for x in a]) and pausa < PAUSA_RECOMECO \
                    and not _reticencia(a[-1]["txt"]):
                continue
            out.append({"tipo": "gaguejo", "i": a[0]["i"], "j": a[-1]["i"],
                        "texto": " ".join(x["txt"] for x in a), "confianca": 0.9,
                        "acao": "cortar"})
            k += n
            achou = True
            break
        if not achou:
            k += 1
    return out


def _muletas(ws: list[dict]) -> list[dict]:
    out = []
    for k in range(1, len(ws) - 1):
        w = ws[k]
        bruto = w["txt"].lower().strip(",.?!;:")
        if w["n"] in MULETAS or bruto in ("é...", "é…"):
            antes = w["t"] - ws[k - 1]["fim"]
            depois = ws[k + 1]["t"] - w["fim"]
            if antes >= VAO_MULETA or depois >= VAO_MULETA or _reticencia(w["txt"]):
                out.append({"tipo": "muleta", "i": k, "j": k, "texto": w["txt"],
                            "confianca": 0.8, "acao": "cortar"})
    return out


def _retakes(ws: list[dict]) -> list[dict]:
    fs = DR.frases(ws)
    out = []
    for h in DR.achar(fs):
        c = DR.classificar(h)
        a, b = c["versao_A"], c["versao_B"]
        idx = [w["i"] for w in ws if a["t"] <= w["t"] <= a["fim"]]
        if not idx:
            continue
        ng = h["ngrama"].split()
        conteudo = _conteudo(ng)
        na, nb = h["a"]["n"], h["b"]["n"]
        classe, conf, acao = c["classe"], 0.5, "perguntar"
        i0, j0 = idx[0], idx[-1]
        if classe == "identica":
            conf, acao = 0.95, "cortar_primeira"
        elif classe == "truncada":
            conf, acao = 0.85, "cortar_primeira"
        # TRUNCADA POR RETICÊNCIA: A começa igual a B, para no meio (reticência
        # do Whisper = fala abortada) e B é a versão completa. O
        # detect_restarts só chama truncada quando A morre em palavra
        # funcional; "…como eu estava dedicando..." morre em conteúdo e caía
        # em "perguntar" — é o retake mais óbvio que existe.
        elif (h["mesmo_inicio"] and _reticencia(a["texto"]) and len(nb) > len(na)
              and conteudo >= 1 and len(ng) >= 2):
            classe, conf, acao = "truncada", 0.85, "cortar_primeira"
        # RETOMADA: o n-grama é o FIM de A e o COMEÇO de B ("…alguém que não
        # estava... | que não estava disposto…"): a pessoa parou e retomou
        # da última palavra. Sai só o fim de A, nunca a frase inteira.
        elif (len(ng) >= 2 and conteudo >= 1 and na[-len(ng):] == ng and nb[:len(ng)] == ng
              and (b["t"] - a["fim"]) <= 3.0):
            classe, conf, acao = "retomada", 0.85, "cortar"
            i0 = j0 - len(ng) + 1
        # par que só compartilha funcionais ("se você", "que a") é coincidência
        # de língua, não vale uma pergunta ao usuário
        elif conteudo == 0:
            out.append({"tipo": "retake", "classe": "coincidencia", "i": i0, "j": j0,
                        "texto": " ".join(w["txt"] for w in ws[i0:j0 + 1]), "confianca": 0.9,
                        "acao": "manter", "ngrama_dr": h["ngrama"],
                        "motivo": "só palavras funcionais em comum — coincidência de língua, não retake"})
            continue
        item = {"tipo": "retake", "classe": classe, "i": i0, "j": j0,
                "texto": " ".join(w["txt"] for w in ws[i0:j0 + 1]),
                "confianca": conf, "acao": acao, "ngrama_dr": h["ngrama"]}
        if acao == "perguntar":
            item["versao_B"] = b["texto"]
            item["pergunta"] = (f"\"{a['texto']}\" e depois \"{b['texto']}\": "
                                f"é retake (cortar a primeira) ou repetição de propósito (manter)?")
        out.append(item)
    for q in DR.quase_repeticoes(fs):
        idx = [w["i"] for w in ws if q.get("t", -1) <= w["t"] <= q.get("fim", -1)]
        if idx:
            out.append({"tipo": "quase", "i": idx[0], "j": idx[-1], "texto": q.get("texto", ""),
                        "confianca": 0.5, "acao": "perguntar",
                        "pergunta": f"\"{q.get('texto', '')}\" parece correção no meio da frase — cortar a primeira versão?"})
    return out


def _hits_brutos(ws: list[dict]) -> list[dict]:
    return [DR.classificar(h) | {"_h": h} for h in DR.achar(DR.frases(ws))]


def pares_no_corte(ws: list[dict], edl: dict, itens: list[dict]) -> list[dict]:
    """Reinícios que só existem DEPOIS do corte (duas falas distantes na fonte
    que a montagem pôs lado a lado). Devolve itens `perguntar` novos, ou
    decisões automáticas quando o par só tem uma palavra de conteúdo."""
    cortadas: list[dict] = []
    t = 0.0
    for r in edl.get("ranges", []):
        a, b = float(r["start"]), float(r["end"])
        for w in ws:
            if a <= w["t"] and w["fim"] <= b:
                cortadas.append({**w, "t": t + (w["t"] - a), "fim": t + (w["fim"] - a),
                                 "t_fonte": w["t"], "corte": r["start"]})
        t += b - a
    vistos = {h.get("ngrama_dr") for h in itens}
    novos = []
    for c in _hits_brutos(cortadas):
        if c["classe"] != "semantica" or c["ngrama"] in vistos:
            continue
        ng = c["ngrama"].split()
        a = c["versao_A"]
        src = [w for w in cortadas if a["t"] - 1e-3 <= w["t"] <= a["fim"] + 1e-3]
        if not src:
            continue
        i0, j0 = src[0]["i"], src[-1]["i"]
        if _conteudo(ng) <= 1 and len(ng) <= 3:
            novos.append({"tipo": "retake", "classe": "tema", "i": i0, "j": j0, "ngrama_dr": c["ngrama"],
                          "texto": " ".join(w["txt"] for w in ws[i0:j0 + 1]), "confianca": 0.7,
                          "acao": "manter", "motivo": "repetição de tema em trechos distintos da fonte; "
                          "só uma palavra de conteúdo em comum"})
        else:
            novos.append({"tipo": "retake", "classe": "semantica_corte", "i": i0, "j": j0,
                          "ngrama_dr": c["ngrama"], "texto": " ".join(w["txt"] for w in ws[i0:j0 + 1]),
                          "versao_B": c["versao_B"]["texto"], "confianca": 0.5, "acao": "perguntar",
                          "pergunta": f"depois do corte, \"{a['texto']}\" fica colado em "
                                      f"\"{c['versao_B']['texto']}\" — soa repetido? (cortar a primeira / manter)"})
    return novos


def triagem(itens: list[dict], decisoes: dict[str, str]) -> list[dict]:
    """Entradas para triagem.json: uma decisão por n-grama julgado."""
    out = []
    for h in itens:
        ng = h.get("ngrama_dr")
        if not ng:
            continue
        d = decisoes.get(str(h["id"]))
        if d == "cortar" or (d is None and h["acao"].startswith("cortar")):
            dec, quem = "remover", "usuario" if d else "fala_limpa"
            motivo = h.get("motivo") or f"{h.get('classe', h['tipo'])}: fica a última versão"
        elif d == "manter" or (d is None and h["acao"] == "manter"):
            dec, quem = "manter", "usuario" if d else "fala_limpa"
            motivo = h.get("motivo") or "mantida pelo usuário"
        else:
            continue   # pergunta ainda aberta: o portão deve acusar
        out.append({"ngrama": ng, "t": None, "decisao": dec, "motivo": motivo, "quem": quem,
                    "t_fonte": h["t"]})
    return out


def _fragmentos(ws: list[dict]) -> list[dict]:
    """Frase curta que morre em reticência e é refeita logo em seguida
    ("porque... Eles iam..." → "Isso porque essas diquinhas…"). O detect_restarts
    exige n-grama comum de 2 palavras; aqui basta UMA palavra de conteúdo em
    comum nas primeiras 6 da frase seguinte, com a pausa curta entre as duas."""
    fs = DR.frases(ws)
    out = []
    for a, b in zip(fs, fs[1:]):
        if len(a["n"]) > 5 or not _reticencia(a["texto"]) or (b["t"] - a["fim"]) > 2.0:
            continue
        ca = {w for w in a["n"] if _conteudo([w])}
        cb = {w for w in b["n"][:6] if _conteudo([w])}
        if not ca or not (ca & cb) or len(b["n"]) <= len(a["n"]):
            continue
        idx = [w["i"] for w in ws if a["t"] <= w["t"] <= a["fim"]]
        if idx:
            out.append({"tipo": "retake", "classe": "fragmento", "i": idx[0], "j": idx[-1],
                        "texto": a["texto"], "confianca": 0.8, "acao": "cortar_primeira"})
    return out


def detectar(words: list[dict], vad: list[tuple[float, float]] | None = None) -> list[dict]:
    """Itens de corte/pergunta sobre a lista de palavras (schema Scribe)."""
    ws = palavras(words)
    itens = _retakes(ws) + _fragmentos(ws) + _gaguejos(ws) + _muletas(ws)
    # sem sobreposição: o item mais longo em cada palavra vence
    usados: set[int] = set()
    out = []
    for h in sorted(itens, key=lambda h: (h["i"], -(h["j"] - h["i"]))):
        r = set(range(h["i"], h["j"] + 1))
        if r & usados:
            continue
        usados |= r
        h["t"] = round(ws[h["i"]]["t"], 3)
        h["fim"] = round(ws[h["j"]]["fim"], 3)
        h["palavras"] = [h["i"], h["j"]]
        out.append(h)
    out.sort(key=lambda h: h["t"])
    for k, h in enumerate(out, 1):
        h["id"] = k
    return out


# --------------------------------------------------------------------------- #
# borda acústica
# --------------------------------------------------------------------------- #

def _rms_db(mono: np.ndarray, a: float, b: float) -> float:
    seg = mono[max(0, int(a * SR)):max(0, int(b * SR))]
    if seg.size == 0:
        return -120.0
    return 20.0 * float(np.log10(np.sqrt(np.mean(seg * seg)) + 1e-9))


def borda(mono: np.ndarray | None, t: float, busca: float = BORDA_BUSCA, janela: float = 0.01) -> float:
    """Instante de menor energia em [t−busca, t+busca]. Sem áudio, devolve t."""
    if mono is None:
        return round(t, 3)
    a, b = max(0.0, t - busca), t + busca
    melhor, melhor_db = t, 1e9
    x = a
    while x + janela <= b:
        db = _rms_db(mono, x, x + janela)
        if db < melhor_db:
            melhor, melhor_db = x + janela / 2, db
        x += janela / 2
    return round(melhor, 3)


def bordas_do_item(mono: np.ndarray | None, ws: list[dict], h: dict) -> tuple[float, float]:
    """[início, fim] do corte: FOLGA curta de cada lado, não a pausa inteira.

    Cortar no meio do vão deixava meia pausa antes e meia depois; emendadas,
    viravam 2,8 s de ar morto na junção (medido). Aqui o corte começa logo
    depois da palavra anterior (até 0,30 s, no ponto mais silencioso) e termina
    logo antes da próxima (até 0,30 s antes dela): o que sobra na emenda é da
    ordem do respiro que o ritmo preserva, não a soma de duas pausas."""
    ini = ws[h["i"]]
    fim = ws[h["j"]]
    ant_fim = ws[h["i"] - 1]["fim"] if h["i"] > 0 else max(0.0, ini["t"] - 0.1)
    prox_t = ws[h["j"] + 1]["t"] if h["j"] + 1 < len(ws) else fim["fim"] + 0.1
    # início: entre ant_fim+0.05 e min(ant_fim+0.30, ini−0.02)
    lo, hi = ant_fim + 0.05, max(ant_fim + 0.05, min(ant_fim + 0.30, ini["t"] - 0.02))
    x = borda(mono, (lo + hi) / 2, busca=max(0.01, (hi - lo) / 2)) if mono is not None else hi
    # fim: entre max(fim+0.02, prox−0.30) e prox−0.03
    lo2, hi2 = max(fim["fim"] + 0.02, prox_t - 0.30), max(fim["fim"] + 0.02, prox_t - 0.03)
    y = borda(mono, (lo2 + hi2) / 2, busca=max(0.01, (hi2 - lo2) / 2)) if mono is not None else lo2
    if y - x < CORTE_MIN:
        y = x + CORTE_MIN
    return round(x, 3), round(y, 3)


# --------------------------------------------------------------------------- #
# respiros (silêncios) e EDL
# --------------------------------------------------------------------------- #

def _classe_vao(ws: list[dict], at: float) -> str:
    ant = None
    for w in ws:
        if w["fim"] <= at + 0.05:
            ant = w
        else:
            break
    if ant is None:
        return "respiracao"
    txt = ant["txt"]
    # O PONTO FINAL de uma região isolada é sintético: o Whisper fecha cada
    # pedaço com ".", então "." num vão entre regiões não diz nada sobre
    # retórica — classificá-lo assim preservava TODA pausa (medido: 16 vãos de
    # 0,5–1,4 s, todos "retórica", 2 encurtados). Retórica é só `?!…`; o ponto
    # cai no meio-termo (respiração), que é o erro que não estraga nada.
    # Reticência numa região isolada é fala que PAROU ("Gastava muito tempo
    # em..."), não pausa dramática: vira hesitação, que o ritmo encurta.
    if txt.endswith(("...", "…")):
        return "hesitacao"
    if re.search(r"[?!]$|—$", txt):
        return "retorica"
    if re.search(r"[,;:.]$", txt):
        return "respiracao"
    return "hesitacao"


def respiros(ws: list[dict], vad: list[tuple[float, float]], ritmo: str) -> list[dict]:
    """Vãos entre regiões VAD classificados; keep por perfil. `None` = não encurta."""
    perfil = RITMOS[ritmo]
    out = []
    for (s1, e1), (s2, e2) in zip(vad, vad[1:]):
        vao = s2 - e1
        classe = _classe_vao(ws, e1)
        regra = perfil.get(classe)
        item = {"at": round(e1, 3), "to": round(s2, 3), "classe": classe, "dur": round(vao, 3)}
        if regra and vao >= regra[0]:
            item["keep"] = regra[1]
        out.append(item)
    return out


def contar_ritmos(ws: list[dict], vad: list[tuple[float, float]]) -> dict:
    res = {}
    for r in RITMOS:
        rs = [b for b in respiros(ws, vad, r) if "keep" in b]
        res[r] = {"respiros": len(rs), "segundos": round(sum(b["dur"] - b["keep"] for b in rs), 1)}
    return res


def _duracao(fonte: Path) -> float | None:
    import subprocess
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                              "stream=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(fonte)],
                             capture_output=True, text=True, check=True).stdout.strip()
        if not out or out == "N/A":
            out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                  "-of", "default=noprint_wrappers=1:nokey=1", str(fonte)],
                                 capture_output=True, text=True, check=True).stdout.strip()
        return float(out)
    except Exception:  # noqa: BLE001
        return None


def montar_edl(fonte: Path, ws: list[dict], vad: list[tuple[float, float]], itens: list[dict],
               decisoes: dict[str, str], ritmo: str, mono: np.ndarray | None,
               grade: str = "") -> dict:
    """Um range por trecho contínuo entre cortes; respiros como `breaths` (intenção)."""
    dur = _duracao(fonte)
    cortes: list[tuple[float, float, int]] = []
    for h in itens:
        d = decisoes.get(str(h["id"]))
        sai = (d == "cortar") or (d is None and h["acao"].startswith("cortar") and h["confianca"] >= CONF_AUTO)
        if sai:
            x, y = bordas_do_item(mono, ws, h)
            cortes.append((x, y, h["id"]))
    cortes.sort()
    inicio = vad[0][0] if vad else ws[0]["t"]
    fim_total = vad[-1][1] if vad else ws[-1]["fim"]
    if dur:
        fim_total = min(fim_total, dur - 0.20)   # o vídeo pode acabar antes do áudio; o snap de frame empurra o fim ≤1 frame
    ranges = []
    cur = max(0.0, inicio - 0.05)
    motivo = "início"
    for x, y, hid in cortes:
        if x - cur >= CORTE_MIN:
            ranges.append((cur, x, motivo))
        cur = max(cur, y)
        motivo = f"depois do corte #{hid}"
    if fim_total + 0.05 - cur >= CORTE_MIN:
        ranges.append((cur, (fim_total + 0.05) if not dur else min(fim_total + 0.05, dur - 0.15), motivo))
    brs = respiros(ws, vad, ritmo)
    stem = fonte.stem
    out_ranges = []
    for a, b, motivo in ranges:
        dentro = [w["txt"] for w in ws if a <= w["t"] and w["fim"] <= b]
        quote = " ".join(dentro) if len(dentro) <= 16 else " ".join(dentro[:8]) + " … " + " ".join(dentro[-8:])
        br = [{"at": r["at"], "to": r["to"], "keep": r["keep"]} for r in brs
              if "keep" in r and a < r["at"] and r["to"] < b]
        rng = {"source": stem, "start": round(a, 3), "end": round(b, 3),
               "quote": quote, "reason": motivo}
        if br:
            rng["breaths"] = br
        out_ranges.append(rng)
    total = sum(r["end"] - r["start"] for r in out_ranges) - sum(
        (b["to"] - b["at"] - b["keep"]) for r in out_ranges for b in r.get("breaths", []))
    return {"version": 1, "sources": {stem: str(fonte)}, "grade": grade, "ritmo": ritmo,
            "ranges": out_ranges, "total_duration_s": round(total, 2),
            "_gerado_por": "fala_limpa.py"}


def roteiro_md(ws: list[dict], itens: list[dict], decisoes: dict[str, str], ritmos: dict) -> str:
    marca: dict[int, tuple[str, int]] = {}
    for h in itens:
        d = decisoes.get(str(h["id"]))
        if d == "manter" or (d is None and h["acao"] == "manter"):
            continue
        sai = (d == "cortar") or (d is None and h["acao"].startswith("cortar") and h["confianca"] >= CONF_AUTO)
        for k in range(h["i"], h["j"] + 1):
            marca[k] = ("sai" if sai else "duvida", h["id"])
    linhas = ["# Roteiro proposto", "",
              "~~riscado~~ sai do corte · **[?N]** depende da sua resposta (ver perguntas no fim)", ""]
    for f in DR.frases(ws):
        toks = []
        for w in ws:
            if not (f["t"] <= w["t"] <= f["fim"]):
                continue
            m = marca.get(w["i"])
            if m and m[0] == "sai":
                toks.append(f"~~{w['txt']}~~")
            elif m:
                toks.append(f"**[?{m[1]}]**{w['txt']}")
            else:
                toks.append(w["txt"])
        linhas.append(f"- `[{f['t']:06.2f}-{f['fim']:06.2f}]` " + " ".join(toks))
    perguntas = [h for h in itens if h["acao"] == "perguntar" and decisoes.get(str(h["id"])) is None]
    if perguntas:
        linhas += ["", "## Perguntas", ""]
        for h in perguntas:
            linhas.append(f"- **[?{h['id']}]** ({h['t']:.1f}s) {h.get('pergunta', h['texto'])}")
    cortes = [h for h in itens if h["acao"].startswith("cortar") and decisoes.get(str(h["id"])) != "manter"]
    if cortes:
        linhas += ["", "## Cortes automáticos", ""]
        for h in cortes:
            linhas.append(f"- #{h['id']} {h['tipo']} ({h['t']:.1f}s): \"{h['texto']}\"")
    linhas += ["", "## Ritmo (respiros encurtados / segundos que saem)", ""]
    for r, v in ritmos.items():
        linhas.append(f"- {r}: {v['respiros']} respiros, −{v['segundos']}s")
    return "\n".join(linhas) + "\n"


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _achar_fonte(edit: Path, stem: str) -> Path | None:
    for p in sorted(edit.parent.iterdir()):
        if p.is_file() and p.stem == stem and p.suffix.lower() in VIDEO_EXTS:
            return p
    return None


def _carregar_mono(fonte: Path) -> np.ndarray | None:
    try:
        import transcribe_local as TL
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "a.wav"
            TL.extrair_wav(fonte, wav)
            return TL.carregar_mono(wav)
    except Exception as exc:  # noqa: BLE001
        print(f"aviso: sem áudio para borda acústica ({exc}); usando carimbos", file=sys.stderr)
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Erros de fala → defeitos.json + edl_proposto.json + roteiro.md")
    ap.add_argument("edit", type=Path)
    ap.add_argument("--fonte", type=Path, default=None, help="vídeo/áudio da fonte (padrão: acha pelo stem)")
    ap.add_argument("--ritmo", default=RITMO_PADRAO, choices=list(RITMOS))
    ap.add_argument("--aplicar", type=Path, default=None, help="respostas.json {id: cortar|manter}")
    ap.add_argument("--grade", default="")
    ap.add_argument("--sem-audio", action="store_true", help="não mede borda (teste)")
    args = ap.parse_args()
    edit = args.edit.resolve()
    tdir = edit / "transcripts"
    trans = sorted(p for p in tdir.glob("*.json") if p.name not in
                   {"corrections.json", "cut_mapped.json", "cut.json"} and not p.name.startswith(".")
                   and not p.stem.endswith((".raw", ".prev")))
    if not trans:
        sys.exit(f"nenhum transcrito em {tdir}")
    if len(trans) > 1:
        print(f"aviso: {len(trans)} transcritos; usando o primeiro ({trans[0].name})", file=sys.stderr)
    tj = trans[0]
    d = json.loads(tj.read_text())
    vadp = tdir / "vad" / tj.name
    if vadp.exists():
        vad = [tuple(x) for x in json.loads(vadp.read_text())["regioes"]]
    elif d.get("_vad"):
        vad = [tuple(x) for x in d["_vad"]]
    else:
        sys.exit("sem regiões VAD: transcreva com transcribe_local.py (backend local)")
    fonte = args.fonte or _achar_fonte(edit, tj.stem)
    if fonte is None:
        sys.exit(f"fonte '{tj.stem}' não encontrada em {edit.parent}; passe --fonte")
    decisoes = json.loads(args.aplicar.read_text()) if args.aplicar else {}
    if (edit / "defeitos.json").exists() and args.aplicar:
        prev = json.loads((edit / "defeitos.json").read_text()).get("decisoes", {})
        decisoes = {**prev, **decisoes}

    ws = palavras(d["words"])
    itens = detectar(d["words"], vad)
    mono = None if args.sem_audio else _carregar_mono(fonte)
    for h in itens:
        h["borda"] = list(bordas_do_item(mono, ws, h))
    ritmos = contar_ritmos(ws, vad)
    edl = montar_edl(fonte, ws, vad, itens, decisoes, args.ritmo, mono, args.grade)
    # o que a MONTAGEM cria: duas falas distantes que ficaram lado a lado
    novos = pares_no_corte(ws, edl, itens)
    if novos:
        for k, h in enumerate(novos, len(itens) + 1):
            h["id"] = k
            h["t"] = round(ws[h["i"]]["t"], 3)
            h["fim"] = round(ws[h["j"]]["fim"], 3)
            h["borda"] = list(bordas_do_item(mono, ws, h))
        itens = sorted(itens + novos, key=lambda h: h["t"])
        edl = montar_edl(fonte, ws, vad, itens, decisoes, args.ritmo, mono, args.grade)
    (edit / "triagem.json").write_text(json.dumps(triagem(itens, decisoes), indent=1, ensure_ascii=False))
    (edit / "defeitos.json").write_text(json.dumps(
        {"fonte": str(fonte), "ritmos": ritmos, "decisoes": decisoes, "itens": itens},
        indent=1, ensure_ascii=False))
    (edit / "edl_proposto.json").write_text(json.dumps(edl, indent=1, ensure_ascii=False))
    (edit / "roteiro.md").write_text(roteiro_md(ws, itens, decisoes, ritmos))
    auto = [h for h in itens if h["acao"].startswith("cortar") and h["confianca"] >= CONF_AUTO]
    perg = [h for h in itens if h["acao"] == "perguntar" and decisoes.get(str(h["id"])) is None]
    print(f"defeitos: {len(itens)} itens — {len(auto)} cortes automáticos, {len(perg)} perguntas; "
          f"EDL com {len(edl['ranges'])} trechos, {edl['total_duration_s']}s ({args.ritmo}: "
          f"{ritmos[args.ritmo]['respiros']} respiros, −{ritmos[args.ritmo]['segundos']}s)")
    print(f"  {edit / 'roteiro.md'}")
    return 2 if perg else 0


if __name__ == "__main__":
    sys.exit(main())

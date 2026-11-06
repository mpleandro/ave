"""Estágio 1 — janelas candidatas a corte.

Um corte começa onde uma ideia começa e termina onde ela fecha. Então a unidade
não é o segundo, é a FRASE (`hook_finder.frases`: pontuação final OU pausa
medida ≥ 0,45s — a pausa vem do áudio, porque o Whisper estica a palavra por
cima dela).

- INÍCIO válido: a frase vem depois de um ponto final ou começa em maiúscula,
  E tem silêncio medido ≥ `borda_min_s` antes. Uma frase que só "abriu" porque
  o falante respirou no meio de uma vírgula não abre corte.
- FIM válido: a frase fecha com . ? ! e silêncio ≥ `borda_min_s` depois. Pausa
  sem pontuação não fecha — é o falante pensando no meio do raciocínio.
- BORDA RUIM nunca é borda de janela: cauda de live ("É isso.", "É verdade ou
  não é?", "Quem tá entendendo isso, gente?") e logística da transmissão (QR
  code, chat, "posso continuar?") — `autocontencao.borda_ruim`. A janela que
  terminaria nela termina na frase limpa de antes. Na live Mil Milionários
  (2026-11) 5 de 48 cortes da galeria terminavam numa cauda.
- CAUDA COLADA ("E nós pagamos o preço, é verdade ou não é?") não vira frase
  própria — mudar a segmentação mudaria o índice de toda frase da fonte, e as
  janelas já gravadas (`frases: [i, j]`) apontariam para outro texto. Ela fica
  como PONTO DE FIM opcional da frase (`cauda`), o espelho do conectivo de
  abertura: o vale de energia entre "preço" e "é", que `bordas.aparar` usa
  depois de conferir OUVINDO (`fala.fim_sem_cauda`).

A janela desliza de frase em frase (todo início válido é tentado, então as
janelas se sobrepõem) e, para cada início, fica o fim válido mais perto de cada
duração-alvo (`alvos_s`, dentro de [dur_min_s, dur_max_s]). Uma fonte de uma
hora dá alguns milhares de janelas — o pré-filtro, barato, é quem as reduz.
Aqui nada é julgado: só se garante que nenhuma corta uma ideia ao meio.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hook_finder import borda, frases, norm  # noqa: E402

from . import autocontencao as A

FINAL = ".?!"
# A cauda colada sai sem escuta só com silêncio de verdade entre as duas (o
# mesmo piso de borda do silencedetect); com escuta, basta o vale de energia.
VAO_CAUDA_SEGURO = 0.15


def fecha(palavra: str) -> bool:
    """. ? ! fecham; reticências não — "A gente tava falando aqui de..." é a
    fala morrendo no meio, não uma ideia terminada."""
    p = palavra.rstrip("\"')»”")
    return p[-1:] in FINAL and not p.endswith(("...", "…"))


def montar_frases(ws: list[dict], sil: list[tuple[float, float]], energia=None,
                  cfg: dict | None = None) -> list[dict]:
    """Frases com as bordas medidas e o tipo de fechamento. Com `energia`
    (times, db, limiar de voz), também onde o conectivo de abertura sai e —
    com `cfg`, que tem o léxico — onde a cauda colada no fim sai."""
    out = []
    for f in frases(ws, sil):
        s, e = f[0]["s"], f[-1]["e"]
        out.append({
            "s": s, "e": e,
            "texto": " ".join(w["w"] for w in f),
            "n": len(f),
            "fecha_ponto": fecha(f[-1]["w"]),
            "pausa_antes": borda(sil, s, "antes"),
            "pausa_depois": borda(sil, e, "depois"),
            "ws": f,
            "apara": aparavel(f, energia),
            "cauda": aparavel_fim(f, energia, cfg),
        })
    return out


def ponto_de_fim(ultima: dict, cauda0: dict, energia, ate: float | None = None) -> tuple[float, float] | None:
    """(ponto, vão) entre a última palavra do conteúdo e a primeira da cauda:
    o meio do vale de energia mais fundo, ou None se a voz não desce.

    A busca vai de 60% da última palavra até 0,3s depois do início da cauda,
    porque o tempo de palavra erra para os dois lados: no c0197 o transcrito
    pôs "preço" e "é" colados em 1587,35, e a escuta local ouviu "preço"
    acabar em 1587,22 e "É" começar em 1587,34 — o vale (−51 dB) estava em
    1587,32–1587,36. `vão` é quanto do vale fica abaixo do limiar de voz.

    `ate` (o fim da cauda no transcrito) fecha a busca: com cauda de UMA
    sílaba ("…ficarem tranquilos, tá?") os 0,3s passavam do "tá" e o vale mais
    fundo era o silêncio DEPOIS dele — a escuta recusou os 5 casos assim da
    Mil Milionários (ouviu "tá?" antes do ponto), e a cauda ficava."""
    t, db, limiar = energia
    a = ultima["s"] + 0.6 * max(0.0, ultima["e"] - ultima["s"])
    b = cauda0["s"] + 0.3 if ate is None else min(cauda0["s"] + 0.3, ate)
    m = (t >= a) & (t <= b)
    tt, dd = t[m], db[m]
    if not len(tt):
        return None
    runs: list[list[int]] = []
    for k, v in enumerate(dd < limiar + 6):
        if not v:
            continue
        if runs and runs[-1][1] == k - 1:
            runs[-1][1] = k
        else:
            runs.append([k, k])
    if not runs:
        return None
    # o mais fundo; empate, o mais tardio (o vale dentro da palavra vem antes)
    i, j = min(runs, key=lambda r: (float(dd[r[0]:r[1] + 1].min()), -r[0]))
    if float(dd[i:j + 1].min()) > limiar + 3:
        return None
    quadro = float(tt[1] - tt[0]) if len(tt) > 1 else 0.021
    ponto = (float(tt[i]) + float(tt[j]) + quadro) / 2
    vao = float((dd[i:j + 1] < limiar).sum()) * quadro
    return round(ponto, 3), round(vao, 3)


def aparavel_fim(f: list[dict], energia, cfg: dict | None) -> dict | None:
    """Se a frase fecha com uma confirmação colada depois da vírgula ("…o
    preço, é verdade ou não é?"): onde o corte PODE terminar sem ela.

    {"e": ponto, "vao": s, "n": palavras da cauda, "tirou": "é verdade ou não
    é?", "texto": "E nós pagamos o preço.", "ultima": "preço,"}. Quem decide
    se sai é `bordas.aparar`: ouvindo, ou só com silêncio de verdade."""
    if energia is None or cfg is None or not f or not fecha(f[-1]["w"]):
        return None
    cauda = A.cauda_colada(" ".join(w["w"] for w in f), cfg)
    if not cauda:
        return None
    n = len(cauda.split())
    cab, cau = f[:-n], f[-n:]
    if not cab or not cab[-1]["w"].endswith(","):
        return None
    pv = ponto_de_fim(cab[-1], cau[0], energia, cau[-1]["e"])
    if pv is None:
        return None
    texto = " ".join(w["w"] for w in cab).rstrip(",") + "."
    return {"e": pv[0], "vao": pv[1], "n": n, "tirou": cauda, "texto": texto,
            "ultima": cab[-1]["w"]}


# Conectivo que abre a frase e pode sair sozinho: "Mas parem de ser chatos." vira
# "Parem de ser chatos." — o gancho começa no verbo, não no "mas" que responde
# a algo que o corte não mostra.
#
# O ponto de corte sai da ENERGIA do áudio, não dos tempos de palavra. Medido
# numa fonte real: o Groq pôs o "Mas" em 3018,50–3018,72 e o "parem" em
# 3018,77, mas a voz diz "Mas" em 3018,77–3018,92 e "parem" em 3019,05 — 0,27s
# de deslocamento. Cortar pelos tempos de palavra entregava "Mas parem…" (o
# Whisper ouviu o "Mas" no arquivo exportado). E o vão entre os dois (0,1s) é
# curto demais para o silencedetect, que mede a partir de 0,12s.
APARAVEIS = {"mas", "e", "então", "aí", "daí", "porque", "pois", "bom", "olha",
             "tipo", "cara", "só que", "e aí", "e então", "agora"}
VAO_MIN = 0.05        # respiro mínimo entre o conectivo e a palavra seguinte
QUADRO_MIN = 0.04     # um vão de um quadro de 21ms é ruído, não respiro


def _norm(w: str) -> str:
    """Minúsculo e sem pontuação, MAS com acento: sem acento "É" (verbo) vira
    "e" (conectivo), e "É raro vender pelo Reels" virava "Raro vender…"."""
    return re.sub(r"[^\w\s]", "", w.lower()).strip()


def trechos_de_voz(t, db, limiar: float, a: float, b: float) -> list[tuple[float, float]]:
    """Trechos com voz entre a e b, juntando buracos menores que QUADRO_MIN."""
    import numpy as np  # noqa: PLC0415
    m = (t >= a) & (t <= b)
    tt, vv = t[m], db[m] > limiar
    out: list[list[float]] = []
    for x, v in zip(tt, vv):
        if not v:
            continue
        if out and x - out[-1][1] <= QUADRO_MIN:
            out[-1][1] = float(x)
        else:
            out.append([float(x), float(x)])
    return [(s, e + 0.021) for s, e in out] if np.any(vv) else []


def aparavel(f: list[dict], energia) -> dict | None:
    """Se a frase abre com um conectivo destacável: os pontos onde o corte PODE
    começar sem ele.

    `energia` = (times, db, limiar de voz). Cada vão de voz ≥ VAO_MIN depois do
    primeiro trecho com voz, até pouco depois de onde a transcrição põe a
    palavra seguinte, é um candidato (20ms antes da voz voltar). Qual deles é o
    certo não dá para saber pela energia — "só | que | não" tem dois vãos, e o
    "e" de "e eu descobri" sai emendado sem vão nenhum —, então quem escolhe é
    `verificar.ponto_de_corte`, ouvindo, e só para os cortes que vão à galeria."""
    if energia is None:
        return None
    t, db, limiar = energia
    for n in (2, 1):
        if len(f) <= n + 1:
            continue
        cab = " ".join(_norm(w["w"]) for w in f[:n])
        if cab not in APARAVEIS:
            continue
        voz = trechos_de_voz(t, db, limiar, f[0]["s"] - 0.15, f[n]["s"] + 0.8)
        pontos = [round(voz[k + 1][0] - min(0.02, (voz[k + 1][0] - voz[k][1]) / 2), 3)
                  for k in range(len(voz) - 1) if voz[k + 1][0] - voz[k][1] >= VAO_MIN]
        if not pontos:
            return None
        resto = " ".join(w["w"] for w in f[n:])
        return {"s": pontos[0], "pontos": pontos, "gap": 0.0,
                "tirou": " ".join(w["w"] for w in f[:n]),
                "texto": resto[:1].upper() + resto[1:]}
    return None


def borda_ruim(f: dict, cfg: dict) -> str | None:
    """"cauda" | "logistica" | None — a frase não abre nem fecha janela.
    Guardado na frase: o gerador pergunta o mesmo para cada par (início, fim)."""
    if "_borda" not in f:
        f["_borda"] = A.borda_ruim(f["texto"], cfg) if cfg.get("autocontencao", {}).get("cauda") else None
    return f["_borda"]


def inicio_ok(frs: list[dict], i: int, cfg: dict) -> bool:
    """Pausa sozinha não abre ideia: "elas resolveram a tensão…" depois de um
    respiro é o meio de uma frase. Abre quem vem depois de ponto ou começa em
    maiúscula — e, nos dois casos, com silêncio medido antes, senão o corte
    leva a cauda da palavra anterior."""
    if i == 0:
        return True
    abre = frs[i - 1]["fecha_ponto"] or frs[i]["texto"][:1].isupper()
    return abre and frs[i]["pausa_antes"] >= cfg["candidatos"]["borda_min_s"]


def fim_ok(frs: list[dict], j: int, cfg: dict) -> bool:
    """Fim só em . ? ! com silêncio depois — pausa sozinha não fecha: numa fonte
    real, "Então," e "Isso não vai" fechavam janela porque o falante parou para
    pensar; ponto sem silêncio é o falante emendando."""
    return frs[j]["fecha_ponto"] and frs[j]["pausa_depois"] >= cfg["candidatos"]["borda_min_s"]


def gerar(frs: list[dict], cfg: dict) -> list[dict]:
    """As janelas. `inicio_ok`/`fim_ok` são a regra do ÁUDIO (o lote mostra
    ▶ e ■ por ela); aqui entra também a do TEXTO — borda ruim não é borda."""
    c = cfg["candidatos"]
    dmin, dmax, alvos = c["dur_min_s"], c["dur_max_s"], c["alvos_s"]
    abre = [inicio_ok(frs, i, cfg) and not borda_ruim(frs[i], cfg) for i in range(len(frs))]
    fecha_ = [fim_ok(frs, j, cfg) and not borda_ruim(frs[j], cfg) for j in range(len(frs))]

    def inicio_ok_(i: int) -> bool:
        return abre[i]

    def fim_ok_(j: int) -> bool:
        return fecha_[j]

    vistos: set[tuple[int, int]] = set()
    out: list[dict] = []
    for i in range(len(frs)):
        if not inicio_ok_(i):
            continue
        fins = []
        for j in range(i, len(frs)):
            dur = frs[j]["e"] - frs[i]["s"]
            if dur > dmax:
                break
            if dur >= dmin and fim_ok_(j):
                fins.append((j, dur))
        for alvo in alvos:
            if not fins:
                break
            j, _ = min(fins, key=lambda x: abs(x[1] - alvo))
            if (i, j) in vistos:
                continue
            vistos.add((i, j))
            jan = frs[i:j + 1]
            out.append({
                "start": round(frs[i]["s"], 3),
                "end": round(frs[j]["e"], 3),
                "dur": round(frs[j]["e"] - frs[i]["s"], 2),
                "frases": [i, j],
                "n_palavras": sum(f["n"] for f in jan),
                "fim": "ponto" if frs[j]["fecha_ponto"] else "pausa",
                "borda": [round(frs[i]["pausa_antes"], 2), round(frs[j]["pausa_depois"], 2)],
                "abertura": frs[i]["texto"],
                "fechamento": frs[j]["texto"],
                "texto": " ".join(f["texto"] for f in jan),
            })
    out.sort(key=lambda x: (x["start"], x["end"]))
    for k, x in enumerate(out, 1):
        x["id"] = f"c{k:04d}"
    return out

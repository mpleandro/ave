"""Emit caption-dinamico.json for the DINAMICO caption style (shortform Phase 2).

O dinâmico é o primo ACUMULATIVO do editorial, mapeado quadro a quadro de um
vídeo de referência (Vd-1.mp4, 2026-08-19). O que o separa dos irmãos:

- O bloco é CENTRAL e diagramado inteiro; as palavras são REVELADAS no tempo da
  fala, sem reflow — a linha nunca se move para receber a palavra seguinte.
- A sans chega APAGADA e ACENDE quando a próxima palavra cai (`litMs`). A última
  palavra conectiva de uma deixa fica apagada de vez (papel `dim`) — na
  referência, "month" nunca acende.
- O acento serif itálico entra LETRA A LETRA vindo da direita/baixo, com escala
  1.42 assentando — não a palavra inteira crescendo (o `serifIn` do editorial).
- Um algarismo solto ("2", "5 mil", "1 milhão") vira `figure` da DEIXA: pendura
  gigante à esquerda do bloco e o texto encolhe para dar altura a ele.

Input is the transcript of the FINAL cut (same as captions_words.py) so word
times are already on the output timeline.

Usage:
    python helpers/caption_style_dinamico.py \
        --transcript <edit>/transcripts/cut.json \
        -o <edit>/hyperframes/caption-dinamico.json

Shares word loading, normalisation and the pause/emphasis word lists with
caption_style.py (the stacked director), like caption_style_editorial.py does.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Irmão deste arquivo — mesmo motivo documentado no caption_style_editorial.py.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from caption_style import (  # noqa: E402  (irmão, resolvido na linha acima)
    EMPH,
    NEG,
    PAUSE_MS,
    STOP,
    load_words,
    norm,
    strip_p,
)

# A referência acumula até 3 linhas de 2-3 palavras — deixas mais longas que as
# do empilhado, como no editorial.
MAX_WORDS = 8
MAX_PER_LINE = 3
MAX_LINE_CHARS = 18
MAX_LINES = 3

SENT_END = (".", "!", "?", "…")

# Palavra-unidade que viaja JUNTO do algarismo na figure: "5 mil", "2 milhões".
FIG_UNITS = {"mil", "milhao", "milhoes", "bilhao", "bilhoes", "k", "%"}

# Sem próxima palavra para acender a atual, ela acende sozinha depois deste
# tanto — na referência "funnels" (última da oração) acende, "month" (conectiva
# final) não. O papel decide; isto é só o relógio.
LIT_SELF_MS = 350


def is_num(t: str) -> bool:
    """A standalone figure — '2', '20%', '3.000'. These hang beside the block."""
    s = strip_p(t).replace("%", "").replace(".", "").replace(",", "")
    return bool(s) and s.isdigit()


def content_score(w: dict) -> int:
    """How much this word wants to be the accent of its cue. 0 = never."""
    t = norm(w["text"])
    if not t or t in STOP or t in NEG:
        return 0
    if is_num(w["text"]):
        return 0  # numbers become the cue figure, never the serif accent
    return (len(t) + 6) if t in EMPH else len(t)


def group_cues(words: list[dict]) -> list[list[dict]]:
    """Break on a real pause, on sentence punctuation, or at MAX_WORDS."""
    cues: list[list[dict]] = []
    cur: list[dict] = []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        brk = (
            nxt is None
            or (nxt["startMs"] - w["endMs"] > PAUSE_MS)
            or w["text"].endswith(SENT_END)
            or len(cur) >= MAX_WORDS
        )
        if brk:
            cues.append(cur)
            cur = []
    merged: list[list[dict]] = []
    for cw in cues:
        lone_stop = len(cw) == 1 and norm(cw[0]["text"]) in STOP
        if lone_stop and merged and len(merged[-1]) < MAX_WORDS:
            merged[-1].append(cw[0])
        else:
            merged.append(cw)
    return merged


def extract_figure(ws: list[dict]) -> tuple[list[dict], dict | None]:
    """Pull the first standalone number (plus its unit word) out as the figure.

    A figure needs TEXT beside it — a cue that would be left empty keeps the
    number as an ordinary word instead.
    """
    for i, w in enumerate(ws):
        if not is_num(w["text"]):
            continue
        take = [w]
        if i + 1 < len(ws) and norm(ws[i + 1]["text"]) in FIG_UNITS:
            take.append(ws[i + 1])
        rest = [x for x in ws if x not in take]
        if not rest:
            return ws, None
        text = " ".join(strip_p(t["text"]) or t["text"] for t in take)
        return rest, {"text": text, "fromMs": take[0]["startMs"]}
    return ws, None


def assign_roles(ws: list[dict], is_sentence_end: bool) -> tuple[list[str], int]:
    """One serif accent per cue; connectives that CLOSE the cue stay dim."""
    scores = [content_score(w) for w in ws]
    # a referência acentua o payoff — o fim da oração leva a serif quando tem peso
    if is_sentence_end and scores[-1] >= 5:
        accent_i = len(ws) - 1
    else:
        accent_i = max(range(len(ws)), key=lambda i: (scores[i], i)) if any(scores) else -1
    if accent_i >= 0 and scores[accent_i] == 0:
        accent_i = -1

    roles: list[str] = []
    for i, w in enumerate(ws):
        t = norm(w["text"])
        if i == accent_i:
            roles.append("serifAcc")
        elif i == len(ws) - 1 and (t in STOP or len(strip_p(w["text"])) <= 2):
            roles.append("dim")   # conectiva final nunca acende ("month")
        else:
            roles.append("base")

    # Uma serif BRANCA de variedade quando a deixa tem um segundo conteúdo longo
    # — mesma razão do editorial: sem ela toda deixa fica idêntica.
    if accent_i >= 0:
        for i, w in enumerate(ws):
            if roles[i] == "base" and len(norm(w["text"])) >= 8 and i != accent_i:
                roles[i] = "serif"
                break
    return roles, accent_i


def build_lines(ws: list[dict], accent_i: int) -> list[list[dict]]:
    """Fill lines by width; the serif accent starts a line when it can."""
    lines: list[list[dict]] = [[]]
    chars = 0
    for i, w in enumerate(ws):
        wl = len(strip_p(w["text"]))
        cur = lines[-1]
        wants_break = (
            cur
            and len(lines) < MAX_LINES
            and (
                len(cur) >= MAX_PER_LINE
                or chars + wl > MAX_LINE_CHARS
                or (i == accent_i and len(cur) >= 2)
            )
        )
        if wants_break:
            lines.append([w])
            chars = wl
        else:
            cur.append(w)
            chars += wl
    return [ln for ln in lines if ln]


def build_cues(words: list[dict]) -> list[dict]:
    groups = group_cues(words)
    out: list[dict] = []
    for ci, cw in enumerate(groups):
        sent_end = cw[-1]["text"].endswith(SENT_END)
        ws, figure = extract_figure(cw)
        roles, accent_i = assign_roles(ws, sent_end)
        lines = build_lines(ws, accent_i)

        # o relógio do ACENDER: a palavra sans acende quando a PRÓXIMA cai;
        # a última acende sozinha (LIT_SELF_MS), salvo o papel dim
        starts = [w["startMs"] for w in ws]
        idx = 0
        jlines = []
        for ln in lines:
            jl = []
            for w in ln:
                role = roles[idx]
                item = {
                    "text": w["text"], "role": role,
                    "fromMs": w["startMs"], "toMs": w["endMs"],
                }
                if role == "base":
                    nxt = starts[idx + 1] if idx + 1 < len(starts) else None
                    item["litMs"] = nxt if nxt is not None else w["startMs"] + LIT_SELF_MS
                jl.append(item)
                idx += 1
            jlines.append(jl)

        nxt_start = groups[ci + 1][0]["startMs"] if ci + 1 < len(groups) else None
        gap_after = (nxt_start - cw[-1]["endMs"]) if nxt_start is not None else 9999
        cue = {
            "i": ci,
            "startMs": cw[0]["startMs"],
            "endMs": cw[-1]["endMs"],
            "exit": "fade" if gap_after > PAUSE_MS else "abrupt",
            "lines": jlines,
        }
        if figure:
            cue["figure"] = figure
        out.append(cue)

    # gapless: hold each cue until the next one starts when the gap is small
    for k in range(len(out)):
        lastto = max(w["toMs"] for ln in out[k]["lines"] for w in ln)
        if k + 1 < len(out):
            nxt = out[k + 1]["startMs"]
            out[k]["endMs"] = nxt if (nxt - lastto) <= 700 else min(lastto + 400, nxt)
        else:
            out[k]["endMs"] = lastto + 600
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="→ caption-dinamico.json (dinamico caption style)")
    ap.add_argument("--transcript", type=Path, required=True, help="Transcript of the final preview.mp4")
    ap.add_argument("-o", "--output", type=Path, required=True, help="Output caption-dinamico.json path")
    ap.add_argument("--lang", default="pt", help="Language hint for accent/connective lists (default pt)")
    args = ap.parse_args()

    words = load_words(args.transcript.resolve())
    cues = build_cues(words)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(cues, ensure_ascii=False), encoding="utf-8")

    tally: dict[str, int] = {}
    figs = 0
    for c in cues:
        figs += 1 if c.get("figure") else 0
        for ln in c["lines"]:
            for w in ln:
                tally[w["role"]] = tally.get(w["role"], 0) + 1
    roles = " ".join(f"{k}:{v}" for k, v in sorted(tally.items()))
    print(f"{args.output} — {len(cues)} cues from {len(words)} words | {roles} | figures:{figs}")


if __name__ == "__main__":
    main()

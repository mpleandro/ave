"""Emit caption-editorial.json for the EDITORIAL caption style (shortform Phase 2).

The editorial style (src/EditorialCaptions.tsx) is role-driven: inside one cue a
word is either CONTEXT (small, light, grey), STRESS (semibold, white), SERIF (
garamond italic, white or accent), PUNCH (semibold, accent, glowing) or NUM (
garamond italic, accent, oversized). The contrast between a dimmed connective and
a large accented content word IS the style — flatten the roles and it stops
reading as anything.

Each role also picks its own entry animation, because the two are not independent:
a serif word grows from 0.8, a number explodes from scale 0, a punch blooms out of
blur. The template only plays what this file assigns.

Input is the transcript of the FINAL cut (same as captions_words.py) so
word times are already on the output timeline.

Usage:
    python helpers/caption_style_editorial.py \
        --transcript <edit>/transcripts/cut.json \
        -o <edit>/hyperframes/caption-editorial.json
    # optional: --lang pt (default) tunes the accent/connective word lists

Shares its word loading, normalisation and cue grouping with caption_style.py —
the stacked director. Only the LINE building and the role/animation assignment
differ, and those are the whole difference between the two looks.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# `caption_style.py` É irmão deste arquivo — importe-o COMO irmão. Antes saía
# daqui um `sys.path.insert` apontando para `~/.claude/skills/edvid/helpers`,
# herança de quando este arquivo morava num overlay FORA daquele repo. Dentro
# deste fork aquilo virou atalho para OUTRA skill: se as listas de palavras
# pt-BR daqui divergirem, a versão do outro repo entra no lugar e o estilo sai
# diferente, sem erro nenhum. Conferido na troca: os dois arquivos ainda batem,
# então o defeito nunca chegou a aparecer — que é o que o tornava difícil de ver.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from caption_style import (  # noqa: E402  (irmão, resolvido na linha acima)
    EMPH,
    ENDBREAK,
    NEG,
    PAUSE_MS,
    STOP,
    load_words,
    norm,
    strip_p,
)

# Editorial cues run longer than stacked ones: the reference look is 2-3 lines of
# 2-3 words, not a vertical stack of single words.
MAX_WORDS = 7
MAX_PER_LINE = 3
MAX_LINE_CHARS = 18
MAX_LINES = 3

SENT_END = (".", "!", "?", "…")

ROLE_ANIM = {
    "ctx": "fade",
    "stress": "fade",
    "serif": "serifIn",
    "serifAcc": "serifIn",
    "punch": "glow",
    "num": "pop",
}


def is_num(t: str) -> bool:
    """A standalone figure — '2', '20%', '3.000'. These carry the pop entry."""
    s = strip_p(t).replace("%", "").replace(".", "").replace(",", "")
    return bool(s) and s.isdigit()


def content_score(w: dict) -> int:
    """How much this word wants to be the accent of its cue. 0 = never."""
    t = norm(w["text"])
    if not t or t in STOP or t in NEG:
        return 0
    if is_num(w["text"]):
        return 0  # numbers get their own role, not the serif accent
    return (len(t) + 6) if t in EMPH else len(t)


def group_cues_editorial(words: list[dict]) -> list[list[dict]]:
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
    # a lone connective cannot hold the screen — fold it into the previous cue
    merged: list[list[dict]] = []
    for cw in cues:
        lone_stop = len(cw) == 1 and norm(cw[0]["text"]) in STOP
        if lone_stop and merged and len(merged[-1]) < MAX_WORDS:
            merged[-1].append(cw[0])
        else:
            merged.append(cw)
    return merged


def build_lines(ws: list[dict], accent_i: int) -> list[list[dict]]:
    """Fill lines by width, but let the accent word START a line when it can.

    The reference look leans on that: the garamond word carries the line rather
    than sitting mid-sentence, which is what makes it read as a deliberate accent
    instead of a font that changed by accident.
    """
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


def assign_roles(ws: list[dict], is_sentence_end: bool) -> tuple[list[str], int]:
    """One accent per cue. Everything else is context or stress."""
    scores = [content_score(w) for w in ws]
    accent_i = max(range(len(ws)), key=lambda i: scores[i]) if any(scores) else -1
    if accent_i >= 0 and scores[accent_i] == 0:
        accent_i = -1

    roles: list[str] = []
    for i, w in enumerate(ws):
        t = norm(w["text"])
        if is_num(w["text"]):
            roles.append("num")
        elif i == accent_i:
            roles.append("serifAcc")
        # EMPH first: the short-word rule would grey out "IA", "5G", "R$" — words
        # that are short but carry the whole sentence.
        elif t in EMPH:
            roles.append("stress")
        elif t in STOP or len(strip_p(w["text"])) <= 2:
            roles.append("ctx")
        else:
            roles.append("stress")

    # The last word of a sentence, when it is a content word and not already the
    # accent, is the punch — it is where the line lands.
    if is_sentence_end and roles and roles[-1] == "stress" and content_score(ws[-1]) >= 5:
        roles[-1] = "punch"

    # A white (non-accent) serif adds variety when the cue has a second long
    # content word. Without it every cue looks identical after a few seconds.
    if accent_i >= 0:
        for i, w in enumerate(ws):
            if roles[i] == "stress" and len(norm(w["text"])) >= 8 and i != accent_i:
                roles[i] = "serif"
                break
    return roles, accent_i


def build_cues(words: list[dict]) -> list[dict]:
    groups = group_cues_editorial(words)
    out: list[dict] = []
    for ci, cw in enumerate(groups):
        sent_end = cw[-1]["text"].endswith(SENT_END)
        roles, accent_i = assign_roles(cw, sent_end)
        lines = build_lines(cw, accent_i)

        idx = 0
        jlines = []
        for ln in lines:
            jl = []
            for w in ln:
                role = roles[idx]
                anim = ROLE_ANIM[role]
                # the typewriter is reserved for a serif word that CLOSES a
                # sentence — it is a landing, and it reads as one only there
                if role in ("serif", "serifAcc") and sent_end and w is cw[-1]:
                    anim = "type"
                jl.append({
                    "text": w["text"], "role": role, "anim": anim,
                    "fromMs": w["startMs"], "toMs": w["endMs"],
                })
                idx += 1
            jlines.append(jl)

        nxt_start = groups[ci + 1][0]["startMs"] if ci + 1 < len(groups) else None
        gap_after = (nxt_start - cw[-1]["endMs"]) if nxt_start is not None else 9999
        out.append({
            "i": ci,
            "startMs": cw[0]["startMs"],
            "endMs": cw[-1]["endMs"],
            "exit": "fade" if gap_after > PAUSE_MS else "abrupt",
            "lines": jlines,
        })

    # gapless: hold each cue until the next one starts when the gap is small, so
    # the frame is never briefly empty mid-sentence
    for k in range(len(out)):
        lastto = max(w["toMs"] for ln in out[k]["lines"] for w in ln)
        if k + 1 < len(out):
            nxt = out[k + 1]["startMs"]
            out[k]["endMs"] = nxt if (nxt - lastto) <= 700 else min(lastto + 400, nxt)
        else:
            out[k]["endMs"] = lastto + 600
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="→ caption-editorial.json (editorial caption style)")
    ap.add_argument("--transcript", type=Path, required=True, help="Transcript of the final preview.mp4")
    ap.add_argument("-o", "--output", type=Path, required=True, help="Output caption-editorial.json path")
    ap.add_argument("--lang", default="pt", help="Language hint for accent/connective lists (default pt)")
    args = ap.parse_args()

    words = load_words(args.transcript.resolve())
    cues = build_cues(words)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(cues, ensure_ascii=False), encoding="utf-8")

    tally: dict[str, int] = {}
    for c in cues:
        for ln in c["lines"]:
            for w in ln:
                tally[w["role"]] = tally.get(w["role"], 0) + 1
    roles = " ".join(f"{k}:{v}" for k, v in sorted(tally.items()))
    print(f"{args.output} — {len(cues)} cues from {len(words)} words | {roles}")


if __name__ == "__main__":
    main()

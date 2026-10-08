"""Pack all Scribe transcripts in <edit>/transcripts/ into one readable markdown.

Groups word-level entries into phrase-level lines, breaking on any silence
>= 0.5s OR speaker change. Each phrase gets a [start-end] prefix. This is
the PRIMARY artifact the editor sub-agent reads to pick cuts — it fits one
hour of takes in a tenth the tokens of raw Scribe JSON and gives
word-boundary precision from text alone.

Output: <edit>/takes_packed.md

**`--por-palavra` — a segunda vista, palavra a palavra.** O limiar de 0,5s que
agrupa as frases é generoso demais para engasgo e respiro: uma hesitação de
0,2s, uma palavra repetida colada ("que que", "e e"), ou uma pausa de 0,3s no
meio do raciocínio somem dentro da mesma frase empacotada — o texto lê
perfeito e o silêncio real fica invisível. `--por-palavra` lista CADA palavra
com a folga antes dela (do token `spacing`, a mesma fonte que `--fix-times`
corrige — nunca a diferença entre dois carimbos de palavra, que estica por
cima do silêncio) e marca:
  ⏸  folga ≥ --gap-min (hesitação/respiro candidato)
  ↻  a mesma palavra repetida colada (engasgo candidato)
Não substitui `transcript_audit.py` (esse pega fala ENGOLIDA, sem texto
nenhum) nem `detect_restarts.py` (frase inteira refeita) — é o meio-termo:
toda palavra que TEM texto, na resolução onde um engasgo aparece.

Output: <edit>/takes_packed_palavras.md

Usage:
    python helpers/pack_transcripts.py --edit-dir <edit_dir>
    python helpers/pack_transcripts.py --edit-dir <edit_dir> --silence-threshold 0.5
    python helpers/pack_transcripts.py --edit-dir <edit_dir> --por-palavra --gap-min 0.15
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def format_time(seconds: float) -> str:
    """Format a time in seconds as "NNN.NN" with fixed 6-char width for alignment."""
    return f"{seconds:06.2f}"


def format_duration(seconds: float) -> str:
    """Format a duration as "Ms" or "Mm SSs"."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    m = int(seconds // 60)
    s = seconds - m * 60
    return f"{m}m {s:04.1f}s"


def group_into_phrases(
    words: list[dict],
    silence_threshold: float = 0.5,
) -> list[dict]:
    """Walk a Scribe word list, break into phrases on silence >= threshold
    OR speaker change. Returns list of {start, end, text, speaker_id}.

    Scribe `words` entries have types 'word', 'spacing', or 'audio_event'.
    We keep 'word' and 'audio_event' content in phrase text. 'spacing'
    entries carry the silence information via their start/end times.
    """
    phrases: list[dict] = []
    current_words: list[dict] = []
    current_start: float | None = None
    current_speaker: str | None = None

    def flush() -> None:
        nonlocal current_words, current_start, current_speaker
        if not current_words:
            return
        text_parts: list[str] = []
        for w in current_words:
            t = w.get("type", "word")
            raw = (w.get("text") or "").strip()
            if not raw:
                continue
            if t == "audio_event":
                if not raw.startswith("("):
                    raw = f"({raw})"
            text_parts.append(raw)
        if not text_parts:
            current_words = []
            current_start = None
            current_speaker = None
            return
        text = " ".join(text_parts)
        text = text.replace(" ,", ",").replace(" .", ".").replace(" ?", "?").replace(" !", "!")
        end_time = current_words[-1].get("end", current_words[-1].get("start", current_start or 0.0))
        phrases.append({
            "start": current_start,
            "end": end_time,
            "text": text,
            "speaker_id": current_speaker,
        })
        current_words = []
        current_start = None
        current_speaker = None

    prev_end: float | None = None

    for w in words:
        t = w.get("type", "word")
        if t == "spacing":
            # spacing entries mark the gaps between words; if the gap is long,
            # flush the current phrase.
            start = w.get("start")
            end = w.get("end")
            if start is not None and end is not None:
                gap = end - start
                if gap >= silence_threshold:
                    flush()
            continue

        # 'word' or 'audio_event'
        start = w.get("start")
        if start is None:
            continue
        speaker = w.get("speaker_id")

        # Flush on speaker change
        if current_speaker is not None and speaker is not None and speaker != current_speaker:
            flush()

        # Flush on a long gap from the previous kept token
        if prev_end is not None and start - prev_end >= silence_threshold:
            flush()

        if current_start is None:
            current_start = start
            current_speaker = speaker
        current_words.append(w)
        prev_end = w.get("end", start)

    flush()
    return phrases


def _norm(text: str) -> str:
    """Normaliza uma palavra pra comparar engasgo: minúscula, sem pontuação
    de borda ("que," e "que" são a mesma palavra dita duas vezes coladas)."""
    return text.strip().lower().strip(".,!?;:…()“”\"'")


def group_into_words(words: list[dict]) -> tuple[list[dict], bool]:
    """Walk a word list into one entry per spoken token (word/audio_event),
    with `gap_before` = the duration of the `spacing` entry that precedes it.

    Usa o SPACING medido, nunca `start_atual - end_anterior`: depois de
    `transcribe.py --repair-spacing` (ou num transcrito novo, que já nasce
    assim) é o token de spacing que carrega o silêncio REAL — o carimbo da
    palavra ainda estica por cima dele (Hard Rule 15). Sem spacing algum
    (transcrito velho, nunca reparado), cai para a diferença de carimbos e
    avisa no chamador — melhor um número otimista que nenhum.
    """
    out: list[dict] = []
    pending_gap = 0.0
    prev_end: float | None = None
    saw_spacing = False
    for w in words:
        t = w.get("type", "word")
        if t == "spacing":
            saw_spacing = True
            start, end = w.get("start"), w.get("end")
            if start is not None and end is not None:
                pending_gap = max(pending_gap, end - start)
            continue
        raw = (w.get("text") or "").strip()
        if not raw:
            continue
        start = w.get("start")
        if start is None:
            continue
        end = w.get("end", start)
        gap = pending_gap if saw_spacing else max(0.0, start - (prev_end or start))
        out.append({
            "start": start, "end": end, "text": raw,
            "type": t, "speaker_id": w.get("speaker_id"),
            "gap_before": gap,
        })
        pending_gap = 0.0
        prev_end = end
    return out, saw_spacing


def render_words_markdown(
    entries: list[tuple[str, list[dict]]], gap_min: float,
) -> tuple[str, int, int]:
    """(markdown, total_engasgos, total_respiros)."""
    lines = ["# Transcrição palavra a palavra", ""]
    lines.append(
        f"Uma linha por palavra. ⏸ = folga ≥ {gap_min:.2f}s antes dela "
        "(respiro/hesitação candidato); ↻ = mesma palavra repetida colada "
        "(engasgo candidato). Complementa `takes_packed.md`, não substitui — "
        "aqui a resolução é a palavra, lá é a frase."
    )
    lines.append("")
    total_engasgos = total_respiros = 0
    for name, tokens in entries:
        lines.append(f"## {name}  ({len(tokens)} palavras)")
        if not tokens:
            lines.append("  _no speech detected_")
            lines.append("")
            continue
        prev_norm = None
        for tok in tokens:
            flags = []
            if tok["gap_before"] >= gap_min:
                flags.append(f"⏸{tok['gap_before']:.2f}")
                total_respiros += 1
            cur_norm = _norm(tok["text"])
            if cur_norm and cur_norm == prev_norm:
                flags.append("↻")
                total_engasgos += 1
            prev_norm = cur_norm
            flag_str = f"  {' '.join(flags)}" if flags else ""
            spk = tok.get("speaker_id")
            spk_str = str(spk)[len("speaker_"):] if spk and str(spk).startswith("speaker_") else (spk or "")
            spk_tag = f" S{spk_str}" if spk_str else ""
            lines.append(f"  {format_time(tok['start'])}{spk_tag}{flag_str}  {tok['text']}")
        lines.append("")
    return "\n".join(lines), total_engasgos, total_respiros


def pack_one_file(json_path: Path, silence_threshold: float) -> tuple[str, float, list[dict]]:
    """Return (header_name, duration, phrases) for one transcript file."""
    data = json.loads(json_path.read_text())
    words = data.get("words", [])
    phrases = group_into_phrases(words, silence_threshold)
    if phrases:
        duration = phrases[-1]["end"] - phrases[0]["start"]
    else:
        duration = 0.0
    return json_path.stem, duration, phrases


def render_markdown(entries: list[tuple[str, float, list[dict]]], silence_threshold: float) -> str:
    lines: list[str] = []
    lines.append("# Packed transcripts")
    lines.append("")
    lines.append(f"Phrase-level, grouped on silences ≥ {silence_threshold:.1f}s or speaker change.")
    lines.append("Use `[start-end]` ranges to address cuts in the EDL.")
    lines.append("")
    for name, duration, phrases in entries:
        lines.append(f"## {name}  (duration: {format_duration(duration)}, {len(phrases)} phrases)")
        if not phrases:
            lines.append("  _no speech detected_")
            lines.append("")
            continue
        for p in phrases:
            spk = p.get("speaker_id")
            if spk is not None:
                # Scribe returns IDs like "speaker_0" — strip the prefix for readability
                spk_str = str(spk)
                if spk_str.startswith("speaker_"):
                    spk_str = spk_str[len("speaker_"):]
                spk_tag = f" S{spk_str}"
            else:
                spk_tag = ""
            lines.append(f"  [{format_time(p['start'])}-{format_time(p['end'])}]{spk_tag} {p['text']}")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Pack Scribe transcripts into takes_packed.md")
    ap.add_argument("--edit-dir", type=Path, required=True, help="Edit directory containing transcripts/")
    ap.add_argument(
        "--silence-threshold",
        type=float,
        default=0.5,
        help="Break phrases on silences >= this (seconds). Default 0.5.",
    )
    ap.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        help="Output path (default: <edit-dir>/takes_packed.md)",
    )
    ap.add_argument(
        "--por-palavra",
        action="store_true",
        help="Também escreve takes_packed_palavras.md — uma linha por palavra, "
             "com folga medida e marcação de engasgo/respiro (ver docstring).",
    )
    ap.add_argument(
        "--gap-min",
        type=float,
        default=0.15,
        help="Folga mínima (s) pra marcar ⏸ no --por-palavra. Default 0.15.",
    )
    ap.add_argument(
        "--output-palavras",
        type=Path,
        default=None,
        help="Output do --por-palavra (default: <edit-dir>/takes_packed_palavras.md)",
    )
    args = ap.parse_args()

    edit_dir = args.edit_dir.resolve()
    transcripts_dir = edit_dir / "transcripts"
    if not transcripts_dir.is_dir():
        sys.exit(f"no transcripts directory at {transcripts_dir}")

    # Skip AppleDouble/dotfiles (e.g. ._name.json) que o macOS cria em
    # exFAT/rede — são metadado binário, não transcrito. E skip os arquivos
    # DERIVADOS que também moram em transcripts/: `corrections.json` é uma
    # lista (`.get` quebra), `cut_mapped.json`/`cut.json` são o transcrito do
    # CORTE (Hard Rule 14) — empacotá-los aqui duplicaria o texto da fonte no
    # takes_packed.md, que é a vista da FONTE, antes do EDL existir.
    _DERIVADOS = {"corrections.json", "cut_mapped.json", "cut.json"}
    json_files = sorted(
        p for p in transcripts_dir.glob("*.json")
        if not p.name.startswith(".") and p.name not in _DERIVADOS
    )
    if not json_files:
        sys.exit(f"no .json files in {transcripts_dir}")

    entries = [pack_one_file(p, args.silence_threshold) for p in json_files]
    markdown = render_markdown(entries, args.silence_threshold)

    out_path = args.output or (edit_dir / "takes_packed.md")
    out_path.write_text(markdown, encoding="utf-8")

    total_phrases = sum(len(e[2]) for e in entries)
    total_duration = sum(e[1] for e in entries)
    kb = out_path.stat().st_size / 1024
    print(f"packed {len(entries)} transcripts → {out_path}")
    print(f"  {total_phrases} phrases, {format_duration(total_duration)} total runtime")
    print(f"  {kb:.1f} KB")

    if args.por_palavra:
        word_entries = []
        sem_spacing = []
        for p in json_files:
            data = json.loads(p.read_text())
            tokens, saw_spacing = group_into_words(data.get("words", []))
            word_entries.append((p.stem, tokens))
            if not saw_spacing and tokens:
                sem_spacing.append(p.stem)
        words_md, n_engasgos, n_respiros = render_words_markdown(word_entries, args.gap_min)
        words_path = args.output_palavras or (edit_dir / "takes_packed_palavras.md")
        words_path.write_text(words_md, encoding="utf-8")
        total_words = sum(len(t) for _, t in word_entries)
        kb2 = words_path.stat().st_size / 1024
        print(f"\npalavra a palavra → {words_path}  ({kb2:.1f} KB)")
        print(f"  {total_words} palavras, {n_respiros} respiro(s) ⏸, {n_engasgos} engasgo(s) ↻")
        if sem_spacing:
            print(f"  aviso: sem spacing medido em {', '.join(sem_spacing)} — "
                  f"rode transcribe.py --repair-spacing antes de confiar na folga")


if __name__ == "__main__":
    main()

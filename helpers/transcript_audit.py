#!/usr/bin/env python3
"""Onde a transcrição MENTE — o portão que falta antes de escrever o EDL.

O Whisper não erra dizendo bobagem; ele erra dizendo algo plausível. As duas
falhas que importam aqui não deixam rastro NO TEXTO:

  1. **Ele engole repetição.** O locutor gagueja, refaz a frase, e a saída traz
     UMA passada só, limpa, com um buraco de tempo entre duas palavras vizinhas.
     Medido na série "170 Questões": 2,2s de fala refeita sumiram entre `ou` e
     `os`, e o parágrafo lia perfeito. Quem lê o `takes_packed.md` não tem como
     saber que faltou — e por isso a gaguejada foi para o vídeo entregue.
  2. **Ele troca palavra por palavra.** "trabalhar" virou "avaliar" (uma palavra
     que existe em outro ponto do mesmo vídeo). A frase continua gramatical.

Nenhum detector de texto pega isso, porque o texto está bem. O que pega:

  A. **DENSIDADE ACÚSTICA** — quanta fala existe versus quantas palavras foram
     transcritas naquele trecho. É física, não linguagem: uma região de fala de
     1,8s com UMA palavra dentro tem fala não transcrita, ponto.
  B. **DISCORDÂNCIA ENTRE DUAS PASSADAS** — o projeto já transcreve duas vezes
     (as fontes na Fase 1, o corte na Fase 2) e as duas erram em lugares
     DIFERENTES. Onde discordam, uma delas está errada. Custa zero de API.
  C. **RECONFERÊNCIA DIRIGIDA** (`--recheck`) — transcrever de novo SÓ a janela
     suspeita, isolada. Sem o contexto em volta o modelo não tem para onde
     suavizar, e a repetição aparece. Segundos de áudio, não o vídeo inteiro.

Por que o vão entre palavras NÃO serve de detector: o Whisper estica o fim da
palavra pelo silêncio. No caso medido, `ou` começa em 31,36 e termina em 33,5 —
o buraco de 2,2s fica DENTRO da palavra e o vão aparente é zero. Foi a primeira
versão deste arquivo e ela achava 0,00s de fala sem texto num trecho onde havia
uma frase inteira. Por isso a densidade é medida por região acústica, contando
só os INÍCIOS de palavra.

**RODE NAS FONTES, NÃO NO `cut.mp4`.** O corte passa por `loudnorm`, que nesta
série levantou +23 dB — o room tone sobe acima do limiar e o detector de fala
para de separar as pausas. Uma pausa longa no meio de uma frase vira "região
contínua com poucas palavras" e sai como suspeita. Aconteceu: 1,52s entre
`você` e `deve` acusaram no corte, e a reconferência isolada mostrou que não há
palavra nenhuma ali — é pausa. Na fonte, sem loudnorm, a mesma janela não
acusa. Quando a suspeita vier do corte, confirme com `--recheck` antes de
mexer em qualquer coisa.

Uso:
    uv run python helpers/transcript_audit.py <edit-dir>
    uv run python helpers/transcript_audit.py <edit-dir> --recheck
"""
from __future__ import annotations

import argparse
import difflib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HELPERS = Path(__file__).resolve().parent
sys.path.insert(0, str(HELPERS))

# Uma região de fala abaixo desta fração da densidade MEDIANA do próprio
# locutor tem fala a mais do que texto. Fração, não valor absoluto: cada pessoa
# fala num ritmo, e um limiar fixo acusaria o locutor pausado inteiro.
DENSITY_FRACTION = 0.55
MIN_REGION = 0.60          # regiões curtas têm densidade instável; ignore
PAD = 0.35                 # folga ao recortar a janela para reconferir


def sh(args: list[str]) -> str:
    return subprocess.run(args, capture_output=True, text=True).stdout


def speech_regions(video: Path, noise: float, min_silence: float = 0.25):
    out = []
    for line in sh([sys.executable, str(HELPERS / "speech_regions.py"), str(video),
                    f"--noise={noise:.0f}dB", "--min-silence", str(min_silence)]).splitlines():
        p = line.replace("->", " ").split()
        if len(p) >= 2:
            try:
                out.append((float(p[0]), float(p[1])))
            except ValueError:
                pass
    return out


def noise_floor_for(video: Path) -> float:
    """Limiar no MEIO entre o piso de ruído e a mediana de fala DESTA gravação.

    Mesma calibração do `cut_words.py`, e pelo mesmo motivo: o default do
    detector fica ACIMA da fala em gravações baixas, e aí toda região some.
    """
    floor = med = None
    for line in sh([sys.executable, str(HELPERS / "voice_levels.py"), str(video)]).splitlines():
        if "noise floor:" in line:
            floor = float(line.split("noise floor:")[1].split("dBFS")[0])
        if "median speech:" in line:
            med = float(line.split("median speech:")[1].split("dBFS")[0])
    return round((floor + med) / 2) if (floor is not None and med is not None
                                        and floor < med) else -33.0


def words_of(path: Path) -> list[dict]:
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    return [w for w in (data.get("words") or []) if w.get("type") == "word"]


def norm(t: str) -> str:
    return t.lower().strip(" .,;:!?…\"'")


# ---------------------------------------------------------------- densidade

def density_flags(video: Path, words: list[dict]) -> list[dict]:
    """Regiões de fala com poucas palavras para o tamanho que têm."""
    noise = noise_floor_for(video)
    regs = speech_regions(video, noise)
    starts = [float(w["start"]) for w in words]

    rows = []
    for a, b in regs:
        dur = b - a
        if dur < MIN_REGION:
            continue
        # tolerância à esquerda: o Whisper ADIANTA o início, então a primeira
        # palavra de uma região costuma cair alguns décimos antes dela
        n = sum(1 for s in starts if a - 0.20 <= s < b)
        rows.append({"start": a, "end": b, "dur": dur, "n": n, "dens": n / dur})
    if not rows:
        return []

    med = sorted(r["dens"] for r in rows)[len(rows) // 2]
    flags = []
    for r in rows:
        if r["dens"] < med * DENSITY_FRACTION:
            r["median"] = med
            r["why"] = "densidade"
            flags.append(r)
    return flags


# ------------------------------------------------------------- discordância

def map_through_edl(edit: Path) -> list[dict]:
    """Palavras das FONTES na linha de tempo de SAÍDA, pelo EDL.

    Usa o `jcut_timeline` que o `render.py` grava — ele é a posição real de cada
    trecho na saída. Somar as durações dos ranges dá quase a mesma coisa e erra
    exatamente onde o J-cut sobrepõe, que é onde ninguém olha.
    """
    edl = json.loads((edit / "edl.json").read_text())
    tl = edl.get("jcut_timeline") or []
    tdir = edit / "transcripts"

    src = {}
    for key, p in edl.get("sources", {}).items():
        src[key] = words_of(tdir / f"{Path(p).stem}.json")

    out, cursor = [], 0.0
    for i, r in enumerate(edl.get("ranges", [])):
        a, b = float(r["start"]), float(r["end"])
        off = float(tl[i]["start"]) if i < len(tl) and "start" in tl[i] else cursor
        for w in src.get(r["source"], []):
            s = float(w["start"])
            if a <= s < b:
                out.append({"start": round(off + s - a, 3),
                            "end": round(off + min(float(w["end"]), b) - a, 3),
                            "text": w["text"], "source": r["source"],
                            "srcStart": round(s, 3)})
        cursor += b - a
    return out


def disagreements(mapped: list[dict], cut: list[dict]) -> list[dict]:
    """Onde as duas passadas divergem. Cada divergência é uma das duas errada."""
    A, B = [norm(w["text"]) for w in mapped], [norm(w["text"]) for w in cut]
    sm = difflib.SequenceMatcher(None, A, B)
    flags = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        # a janela em tempo de SAÍDA, ancorada no que existir dos dois lados
        lo = mapped[i1]["start"] if i1 < len(mapped) else (cut[j1]["start"] if j1 < len(cut) else 0)
        hi = mapped[i2 - 1]["end"] if i2 > i1 else (cut[j2 - 1]["end"] if j2 > j1 else lo)
        if j2 > j1:
            hi = max(hi, cut[j2 - 1]["end"])
            lo = min(lo, cut[j1]["start"])
        flags.append({"start": float(lo), "end": float(hi), "why": "discordância",
                      "op": op,
                      "fonte": " ".join(w["text"] for w in mapped[i1:i2]),
                      "corte": " ".join(w["text"] for w in cut[j1:j2])})
    return flags


# -------------------------------------------------------------- reconferência

def recheck(video: Path, start: float, end: float, lang: str | None) -> str:
    """Transcreve SÓ esta janela, isolada. É aqui que a repetição reaparece:
    sem o contexto em volta o modelo não tem para onde suavizar."""
    from transcribe import load_api_key, transcribe_one  # noqa: E402

    a, b = max(0.0, start - PAD), end + PAD
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        clip = tmp / f"w_{int(a * 1000):07d}.mp4"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{a:.3f}",
                        "-i", str(video), "-t", f"{b - a:.3f}",
                        "-c:v", "copy", "-c:a", "copy", str(clip)],
                       capture_output=True)
        if not clip.exists():
            return "(não consegui recortar)"
        try:
            out = transcribe_one(clip, tmp, load_api_key(), language=lang, verbose=False)
        except Exception as exc:                      # rede, cota, chave
            return f"(reconferência falhou: {exc})"
        return " ".join(w["text"] for w in words_of(out)) or "(nada)"


# --------------------------------------------------------------------- main

def merge(flags: list[dict]) -> list[dict]:
    """Junta janelas que se tocam — os dois detectores acham o mesmo defeito
    por caminhos diferentes, e reportar duas vezes só faz o usuário conferir
    duas vezes."""
    flags = sorted(flags, key=lambda f: f["start"])
    out: list[dict] = []
    for f in flags:
        if out and f["start"] <= out[-1]["end"] + 0.25:
            out[-1]["end"] = max(out[-1]["end"], f["end"])
            out[-1]["why"] = f"{out[-1]['why']} + {f['why']}"
            for k in ("fonte", "corte", "n", "dens", "median"):
                if k in f and k not in out[-1]:
                    out[-1][k] = f[k]
        else:
            out.append(dict(f))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edit", type=Path)
    ap.add_argument("--recheck", action="store_true",
                    help="transcreve de novo cada janela suspeita, isolada")
    ap.add_argument("--language", default="pt")
    ap.add_argument("-o", "--out", type=Path, help="grava o relatório em JSON")
    args = ap.parse_args()

    edit = args.edit.expanduser().resolve()
    edl_path = edit / "edl.json"
    cut = edit / "cut.mp4"

    report: list[dict] = []

    # --- Fase 1: cada FONTE, por densidade. É o portão que interessa, porque
    # roda ANTES de o EDL existir — a gaguejada tem de aparecer enquanto ainda
    # dá para cortá-la de graça.
    if edl_path.exists():
        edl = json.loads(edl_path.read_text())
        for key, p in edl.get("sources", {}).items():
            src = Path(p)
            words = words_of(edit / "transcripts" / f"{src.stem}.json")
            if not src.exists() or not words:
                continue
            fl = density_flags(src, words)
            print(f"\n{src.name} — {len(words)} palavras, {len(fl)} janela(s) suspeita(s)")
            for f in merge(fl):
                near = " ".join(w["text"] for w in words
                                if f["start"] - 1.2 <= float(w["start"]) < f["end"] + 1.2)
                print(f"  {f['start']:7.2f} → {f['end']:7.2f}  "
                      f"{f['n']} palavra(s) em {f['dur']:.2f}s "
                      f"({f['dens']:.2f}/s vs mediana {f['median']:.2f}/s)")
                print(f"      texto em volta: …{near[:90]}…")
                if args.recheck:
                    print(f"      isolada diz:    {recheck(src, f['start'], f['end'], args.language)}")
                f["file"] = src.name
                report.append(f)

    # --- Fase 2: as duas passadas, uma contra a outra. Zero de API.
    if edl_path.exists() and (edit / "transcripts" / "cut.json").exists():
        mapped = map_through_edl(edit)
        cutw = words_of(edit / "transcripts" / "cut.json")
        dis = disagreements(mapped, cutw)
        sim = difflib.SequenceMatcher(
            None, [norm(w["text"]) for w in mapped],
            [norm(w["text"]) for w in cutw]).ratio()
        print(f"\ncorte: fonte mapeada {len(mapped)} palavras × cut.json {len(cutw)} — "
              f"{sim * 100:.1f}% iguais, {len(dis)} divergência(s)")
        for f in dis:
            print(f"  {f['start']:7.2f} → {f['end']:7.2f}  [{f['op']}]")
            print(f"      fonte: {f['fonte'] or '(nada)'}")
            print(f"      corte: {f['corte'] or '(nada)'}")
            if args.recheck and cut.exists():
                print(f"      isolada diz: {recheck(cut, f['start'], f['end'], args.language)}")
            f["file"] = "cut.mp4"
            report.append(f)

    if not report:
        print("\nnenhuma janela suspeita — a transcrição cobre a fala")
    else:
        print(f"\n{len(report)} janela(s) para conferir. "
              f"Cada uma é fala sem texto, ou texto sem fala.")
    if args.out:
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(f"→ {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

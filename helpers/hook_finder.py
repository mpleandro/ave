#!/usr/bin/env python3
"""Garimpo de GANCHO — que trecho JÁ GRAVADO segura os primeiros 3 segundos.

    uv run python helpers/hook_finder.py <edit>
    uv run python helpers/hook_finder.py <edit> --top 12 --json
    uv run python helpers/hook_finder.py <edit> --fonte C0103

O gerador de hooks de roteiro (references/hooks.md) escreve frases que ALGUÉM
VAI GRAVAR. Aqui o vídeo já foi gravado: o gancho falado não se inventa, se
ENCONTRA. A frase mais forte quase nunca é a primeira que a pessoa disse — ela
aquece, contextualiza, e a tese aparece no segundo 20. Puxar essa frase para a
frente (cold open) é o movimento de edição de maior retorno num short.

O QUE ESTE HELPER FAZ É MEDIR, NÃO JULGAR. Ele lê o transcrito em cache de cada
fonte de fala, corta em frases (pontuação + pausa medida) e janelas de 1–2
frases, e devolve para cada candidato os sinais que o transcrito sozinho não
mostra:

- **borda limpa** — silêncio MEDIDO antes e depois (speech_regions). Cold open
  só funciona se a frase sai inteira, sem a cauda da anterior.
- **energia** — nível da frase contra a mediana do PRÓPRIO falante (dB). Ênfase
  é ouvida; o transcrito lê igual uma frase gritada e uma murmurada.
- **ritmo** — palavras/s contra a mediana do falante.
- **independência** — começa com conector ("então", "e aí", "isso", "porque")?
  Então depende do que veio antes e não abre vídeo nenhum.
- **sinais de anatomia** — padrões de texto que sugerem uma das 6 anatomias de
  references/hooks.md (clássica, POV, loop aberto, contraste, erro invisível).
  A anatomia 6 (comando visual) não está no áudio: é decisão de edição.
- **defeito conhecido** — sobrepõe uma repetição CONFIRMADA no
  `defeitos_audio.json`? Gancho com gaguejo é o pior lugar do vídeo para ele.

A nota é só para ORDENAR a leitura. O julgamento semântico (a frase paga o que
promete? é a tese do vídeo?) é do modelo lendo o top-N, e a escolha é do
usuário — gancho é *o que o vídeo diz*, e isso se confirma (Principle 9).

Grava `<edit>/hook_candidatos.json` (dado de máquina: não leia, use o stdout).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from speech_regions import measured_silences  # noqa: E402
from voice_levels import estimate_floor, phrase_level, rms_timeline  # noqa: E402

VIDEO_EXT = (".mp4", ".mov", ".m4v", ".mkv", ".MP4", ".MOV", ".M4V", ".MKV")

# Abaixo disto não há gancho, há interjeição; acima, já não cabe nos 3 primeiros
# segundos nem com um corte no meio.
MIN_DUR, MAX_DUR = 0.9, 7.0
IDEAL = (1.4, 4.5)
SENTENCE_GAP = 0.45      # pausa medida que fecha frase mesmo sem pontuação
CLEAN_EDGE = 0.20        # silêncio mínimo de cada lado para sair inteira

# Conector no começo = a frase responde a algo que veio antes.
CONECTORES = (
    "e", "entao", "ai", "dai", "porque", "pois", "isso", "isto", "esse", "essa",
    "ele", "ela", "eles", "elas", "tambem", "alem", "que", "ou seja", "inclusive",
    "por isso", "so que", "e ai", "e entao", "mas", "como eu disse", "enfim",
)
MULETAS = re.compile(r"\b(ne|tipo assim|tipo|eee+|aham|hum+|ahn|basicamente|enfim)\b")

# Padrões por anatomia (texto normalizado: minúsculo, sem acento).
ANATOMIAS = [
    (1, "classica", re.compile(
        r"^(pare|para|chega|esquece|nunca mais|faz isso|faca isso|olha isso)\b")),
    (2, "pov", re.compile(
        r"\b(voce abre|voce passa|voce fica|voce posta|voce grava|voce senta|"
        r"voce acorda|voce olha|sabe quando|quando voce|voce ja)\b")),
    (3, "loop_aberto", re.compile(
        r"\b(descobri|ninguem (te )?(conta|fala|diz)|o segredo|"
        r"nao e o que voce (pensa|imagina)|tem um detalhe|a verdade e|"
        r"o que ninguem)\b")),
    (4, "contraste", re.compile(
        r"(\bde\b.{2,40}\bpara\b.{2,40}\d)|(\d.{2,40}\bpara\b.{2,40}\d)|"
        r"\bantes\b.{2,60}\bdepois\b")),
    (5, "erro_invisivel", re.compile(
        r"\b(nao e culpa|nao e (por )?falta|o erro|o problema (nao )?e|"
        r"o que (te )?trava|nao e que|voce nao .{2,40} porque)\b|"
        r"^(o|a|os|as|seu|sua)?\s*\w+( \w+)?\s+nao (e|esta|ta|sao|estao|tao|funciona)\b|"
        r"\bvoce que (esta|ta|e)\b")),
]


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s?]", " ", s)).strip()


# --------------------------------------------------------------------------- #

def retomada(t: str, n: int = 3) -> bool:
    """Algum trigrama se repete? É a assinatura de quem começou e recomeçou."""
    toks = t.replace("?", " ").split()
    grams = [" ".join(toks[i:i + n]) for i in range(len(toks) - n + 1)]
    return len(grams) != len(set(grams))


def fontes_de_fala(edit: Path, so: list[str] | None) -> dict[str, Path]:
    """stem → vídeo. O EDL manda quando existe; senão, o transcrito em cache
    casado com o arquivo de mesmo nome na pasta de vídeos."""
    out: dict[str, Path] = {}
    edl_p = edit / "edl.json"
    if edl_p.exists():
        try:
            for v in (json.loads(edl_p.read_text()).get("sources") or {}).values():
                out[Path(v).stem] = Path(v)
        except json.JSONDecodeError:
            pass
    tdir = edit / "transcripts"
    for t in sorted(tdir.glob("*.json")) if tdir.exists() else []:
        if t.stem in out or t.stem.startswith("cut"):
            continue
        for ext in VIDEO_EXT:
            cand = edit.parent / f"{t.stem}{ext}"
            if cand.exists():
                out[t.stem] = cand
                break
    out = {k: v for k, v in out.items() if (tdir / f"{k}.json").exists()}
    if so:
        out = {k: v for k, v in out.items() if k in so or v.name in so}
    return out


def palavras(edit: Path, stem: str) -> list[dict]:
    data = json.loads((edit / "transcripts" / f"{stem}.json").read_text())
    out = []
    for w in data.get("words") or []:
        if w.get("type", "word") != "word":
            continue
        txt = (w.get("word") or w.get("text") or "").strip()
        if not txt:
            continue
        try:
            out.append({"w": txt, "s": float(w["start"]), "e": float(w["end"])})
        except (KeyError, TypeError, ValueError):
            continue
    return out


def frases(ws: list[dict], silencios: list[tuple[float, float]]) -> list[list[dict]]:
    """Fecha frase na pontuação final OU numa pausa MEDIDA ≥ SENTENCE_GAP.
    A pausa vem do áudio porque o Whisper estica a palavra por cima dela."""
    def pausa_depois(t: float) -> float:
        for a, b in silencios:
            if a <= t + 0.08 and b > t:
                return b - max(a, t)
        return 0.0

    out, cur = [], []
    for w in ws:
        cur.append(w)
        if w["w"][-1:] in ".?!" or pausa_depois(w["e"]) >= SENTENCE_GAP:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def borda(silencios, t: float, lado: str) -> float:
    """Silêncio medido encostado em t (antes ou depois). 0 = colado em fala."""
    for a, b in silencios:
        if lado == "antes" and a - 0.10 <= t <= b + 0.10 and a < t:
            return min(t, b) - a
        if lado == "depois" and a - 0.10 <= t <= b + 0.10 and b > t:
            return b - max(a, t)
    return 0.0


def defeitos(edit: Path, stem: str) -> list[tuple[float, float]]:
    p = edit / "defeitos_audio.json"
    if not p.exists():
        return []
    try:
        entry = json.loads(p.read_text()).get(stem)
    except json.JSONDecodeError:
        return []
    achados = entry.get("achados", []) if isinstance(entry, dict) else (entry or [])
    out = []
    for d in achados:
        if not d.get("confirmado") or d.get("aceito"):
            continue
        for occ in (d.get("occ1"), d.get("occ2")):
            if occ:
                out.append((float(occ[0]), float(occ[1])))
        if not d.get("occ1") and "t" in d:
            out.append((float(d["t"]), float(d.get("fim", d["t"] + 2))))
    return out


# --------------------------------------------------------------------------- #

def avaliar(stem, src, ws, sil, times, levels, floor_db, med_db, med_wps, dur_fonte, defs):
    fr = frases(ws, sil)
    janelas = [fr[i:i + n] for n in (1, 2) for i in range(len(fr) - n + 1)]
    out = []
    for jan in janelas:
        w = [x for f in jan for x in f]
        s, e = w[0]["s"], w[-1]["e"]
        dur = e - s
        if not (MIN_DUR <= dur <= MAX_DUR):
            continue
        texto = " ".join(x["w"] for x in w)
        t = norm(texto)
        pontos, sinais = 0.0, []

        # independência
        if any(t == c or t.startswith(c + " ") for c in CONECTORES):
            pontos -= 20
            sinais.append("depende do anterior")
        # bordas medidas
        antes, depois = borda(sil, s, "antes"), borda(sil, e, "depois")
        limpa = antes >= CLEAN_EDGE and depois >= CLEAN_EDGE
        pontos += 10 * (antes >= CLEAN_EDGE) + 10 * (depois >= CLEAN_EDGE)
        if not limpa:
            sinais.append(f"borda colada ({antes:.2f}s|{depois:.2f}s)")
        # energia e ritmo contra o próprio falante
        m = (times >= s) & (times <= e)
        lvl = phrase_level(levels[m], floor_db) if m.any() else None
        d_db = (lvl - med_db) if lvl is not None else 0.0
        pontos += float(np.clip(d_db * 4, -12, 12))
        wps = len(w) / dur
        d_wps = wps / med_wps - 1 if med_wps else 0.0
        pontos += float(np.clip(d_wps * 10, -5, 5))
        # texto
        anat = [(n, nome) for n, nome, rx in ANATOMIAS if rx.search(t)]
        pontos += 18 if anat else 0
        if "?" in texto:
            pontos += 8
            sinais.append("pergunta")
        if re.search(r"\d", texto) or re.search(
                r"\b(dois|tres|cinco|sete|dez|cem|mil|milhao|metade)\b", t):
            pontos += 6
            sinais.append("número")
        if re.search(r"\bvoce\b", t):
            pontos += 5
        # retomada DENTRO da janela ("quer um plano... quer um plano"): o
        # transcrito às vezes guarda as duas passadas, e gancho gaguejado morre
        if retomada(t):
            pontos -= 25
            sinais.append("retomada dentro do trecho")
        mul = len(MULETAS.findall(t))
        if mul:
            pontos -= 8 * mul
            sinais.append(f"{mul} muleta(s)")
        # duração
        if IDEAL[0] <= dur <= IDEAL[1]:
            pontos += 8
        elif dur > 6:
            pontos -= 8
        # defeito confirmado no áudio
        if any(min(e, b) - max(s, a) > 0.1 for a, b in defs):
            pontos -= 40
            sinais.append("REPETIÇÃO CONFIRMADA no áudio")
        pos = s / dur_fonte if dur_fonte else 0.0
        out.append({
            "fonte": stem, "src": str(src), "start": round(s, 3), "end": round(e, 3),
            "dur": round(dur, 2), "texto": texto, "nota": round(pontos, 1),
            "anatomias": [f"{n}:{nome}" for n, nome in anat],
            "energia_db": round(d_db, 1), "ritmo": round(d_wps * 100),
            "borda": [round(antes, 2), round(depois, 2)], "borda_limpa": limpa,
            "posicao": round(pos, 2), "cold_open": pos > 0.15, "sinais": sinais,
        })
    return out


def podar(cands: list[dict], top: int) -> list[dict]:
    """Uma janela por trecho: duas candidatas que se sobrepõem mais da metade
    são a mesma ideia — fica a de nota maior."""
    escolhidos: list[dict] = []
    for c in sorted(cands, key=lambda c: -c["nota"]):
        dup = any(c["fonte"] == k["fonte"] and
                  min(c["end"], k["end"]) - max(c["start"], k["start"]) >
                  0.5 * min(c["dur"], k["dur"]) for k in escolhidos)
        if not dup:
            escolhidos.append(c)
        if len(escolhidos) >= top:
            break
    return escolhidos


def main() -> None:
    ap = argparse.ArgumentParser(description="Garimpa os melhores trechos gravados para gancho.")
    ap.add_argument("edit", type=Path, help="pasta <videos_dir>/edit")
    ap.add_argument("--top", type=int, default=8)
    ap.add_argument("--fonte", action="append", help="limita a esta(s) fonte(s) (stem ou nome)")
    ap.add_argument("--json", action="store_true", help="imprime o JSON em vez da tabela")
    a = ap.parse_args()

    edit = a.edit.resolve()
    fontes = fontes_de_fala(edit, a.fonte)
    if not fontes:
        sys.exit("nenhuma fonte com transcrito em cache — rode transcribe_batch.py antes")

    todos: list[dict] = []
    for stem, src in fontes.items():
        ws = palavras(edit, stem)
        if len(ws) < 3:
            continue
        sil = measured_silences(src)
        times, levels = rms_timeline(src)
        floor_db = estimate_floor(levels)
        speech = levels[levels > floor_db]
        med_db = float(np.percentile(speech, 75)) if speech.size else -30.0
        fala = sum(x["e"] - x["s"] for x in ws)
        med_wps = len(ws) / fala if fala else 0.0
        todos += avaliar(stem, src, ws, sil, times, levels, floor_db, med_db,
                         med_wps, float(times[-1]), defeitos(edit, stem))

    best = podar(todos, a.top)
    (edit / "hook_candidatos.json").write_text(
        json.dumps({"candidatos": best}, ensure_ascii=False, indent=2))
    if a.json:
        print(json.dumps(best, ensure_ascii=False, indent=2))
        return

    print(f"{len(todos)} janelas em {len(fontes)} fonte(s) · top {len(best)} "
          f"(nota só ordena — leia o texto e julgue)\n")
    for i, c in enumerate(best, 1):
        tags = ", ".join(c["anatomias"] + c["sinais"]) or "—"
        onde = "COLD OPEN" if c["cold_open"] else "já no início"
        print(f"#{i}  nota {c['nota']:>5}  {c['fonte']} {c['start']:.2f}–{c['end']:.2f}s "
              f"({c['dur']}s) · energia {c['energia_db']:+.1f}dB · ritmo {c['ritmo']:+d}% "
              f"· {onde}")
        print(f"    \"{c['texto']}\"")
        print(f"    {tags}\n")


if __name__ == "__main__":
    main()

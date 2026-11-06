"""Regressão do motor local (transcribe_local + fala_limpa) contra a verdade medida.

  uv run python tests/fala_limpa_regressao.py            # roda tudo (≈1 min)
  uv run python tests/fala_limpa_regressao.py --json /tmp/t.json   # reusa transcrito

Falha se:
  - faltar qualquer repetição de `repeticoes` (n-grama presente `vezes` vezes
    dentro de t ± tol, no TRANSCRITO);
  - houver palavra dentro de `silencios_obrigatorios`;
  - `fala_limpa.py` (quando existir) acusar um `falsos_positivos_proibidos`.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "helpers"))


def norm(t: str) -> str:
    t = unicodedata.normalize("NFD", t.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9 ]", "", t).strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", type=Path, default=None, help="transcrito já gerado (pula a transcrição; só com --esperado)")
    ap.add_argument("--esperado", type=Path, default=None, help="uma fixture; padrão: todas em tests/fixtures/audio/")
    args = ap.parse_args()
    if args.esperado is None:
        rcs = [um(e, None) for e in sorted((RAIZ / "tests/fixtures/audio").glob("*.esperado.json"))]
        return 1 if any(rcs) else 0
    return um(args.esperado, args.json)


def um(esperado_p: Path, tj: Path | None) -> int:
    esperado = json.loads(esperado_p.read_text())
    print(f"== {esperado_p.name}")
    fonte = RAIZ / esperado["fonte"]
    if not fonte.exists():
        print(f"FALHA: fixture ausente {fonte} — gere com ffmpeg (ver PLANO_EXECUCAO.md B0)")
        return 1

    if tj is None:
        tj = Path(f"/tmp/ave_regressao_{esperado_p.stem}.json")
        r = subprocess.run([sys.executable, str(RAIZ / "helpers/transcribe_local.py"), str(fonte),
                            "-o", str(tj), "-q"], capture_output=True, text=True)
        if r.returncode != 0:
            print("FALHA: transcribe_local.py saiu com erro\n" + r.stderr[-2000:])
            return 1
    d = json.loads(tj.read_text())
    words = [w for w in d["words"] if w.get("type") == "word"]
    toks = [(norm(w["text"]), float(w["start"])) for w in words]
    toks = [t for t in toks if t[0]]
    falhas: list[str] = []

    # 1. repetições esperadas presentes no texto
    for r in esperado["repeticoes"]:
        n = norm(r["ngrama"]).split()
        k = len(n)
        achados = [toks[i][1] for i in range(len(toks) - k + 1)
                   if [t[0] for t in toks[i:i + k]] == n and abs(toks[i][1] - r["t"]) <= r["tol"]]
        if len(achados) < r["vezes"]:
            falhas.append(f"repetição ausente: '{r['ngrama']}' ×{r['vezes']} perto de {r['t']}s "
                          f"(achei {len(achados)}: {achados})")

    # 2. nenhuma palavra em silêncio obrigatório
    for a, b in esperado["silencios_obrigatorios"]:
        dentro = [(t, s) for t, s in toks if a <= s <= b]
        if dentro:
            falhas.append(f"palavras em silêncio {a}-{b}s: {dentro[:6]}")

    # 3. falsos positivos proibidos (no texto e, se existir, no fala_limpa)
    for fp in esperado["falsos_positivos_proibidos"]:
        n = norm(fp["ngrama"])
        if any(t == n and abs(s - fp["t"]) <= fp["tol"] for t, s in toks):
            falhas.append(f"falso positivo no texto: '{fp['ngrama']}' perto de {fp['t']}s")
    fl = RAIZ / "helpers/fala_limpa.py"
    if fl.exists():
        try:
            import fala_limpa
            vad = d.get("_vad") or []
            itens = fala_limpa.detectar(d["words"], [tuple(x) for x in vad])
            for fp in esperado["falsos_positivos_proibidos"]:
                n = norm(fp["ngrama"])
                for it in itens:
                    if norm(it.get("texto", "")) == n and abs(it["t"] - fp["t"]) <= fp["tol"]:
                        falhas.append(f"fala_limpa acusou falso positivo '{fp['ngrama']}' em {it['t']}s")
            for r in esperado["repeticoes"]:
                n = norm(r["ngrama"])
                acao_ok = (lambda it, a=r.get("acao"): it["acao"] == a) if r.get("acao") else (lambda it: it["acao"].startswith("cortar"))
                hits = [it for it in itens if (n in norm(it.get("texto", "")) or norm(it.get("texto", "")) in n)
                        and abs(it["t"] - r["t"]) <= r["tol"] and acao_ok(it)]
                if r.get("corte", True) and not hits:
                    falhas.append(f"fala_limpa não acusou '{r['ngrama']}' ({r.get('acao', 'cortar')}) perto de {r['t']}s")
                if not r.get("corte", True) and hits:
                    falhas.append(f"fala_limpa propôs cortar frase legítima '{r['ngrama']}' em {hits[0]['t']}s")
        except Exception as exc:  # noqa: BLE001
            falhas.append(f"fala_limpa quebrou: {exc!r}")

    if falhas:
        print("FALHA")
        for f in falhas:
            print("  -", f)
        return 1
    print(f"OK — {len(words)} palavras; {len(esperado['repeticoes'])} repetições presentes; "
          f"silêncios limpos; sem falsos positivos")
    return 0


if __name__ == "__main__":
    sys.exit(main())

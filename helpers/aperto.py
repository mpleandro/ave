#!/usr/bin/env python3
"""APERTO — o último passo do EDL antes do render: bordas até a VOZ medida.

    uv run python helpers/aperto.py <edit> [--ritmo equilibrado] [--so-checar]

Nasceu de um short de 2:22 (2026-11-08) que chegou ao usuário com quatro
defeitos que nenhum auditor acusou, todos visíveis só assistindo:

1. **Silêncio no começo e no fim de cada trecho.** A borda acústica escolhe o
   ponto de MENOR ENERGIA na folga entre duas palavras — correto para não
   cortar palavra, mas numa folga de 1,2s ela deixa até 0,6s de nada de cada
   lado. Somado ao respiro do J-cut, cada emenda virava uma pausa audível e,
   em vídeo de fala para rede social, um rosto olhando para o lado enquanto
   lê o próximo trecho. Aqui a borda anda até a voz: início no primeiro
   quadro acima do limiar calibrado (−LEAD), fim no último acima do piso
   (+TRAIL, que guarda o decaimento da sílaba).

2. **Pausa longa DENTRO do trecho.** O usuário marcou duas e esclareceu:
   "limpar espaços é o vídeo todo, não só as marcações". Silêncio interno
   maior que `MAXP[ritmo]` vira emenda deixando `KEEP[ritmo]`.

3. **Ruído antes da 1ª palavra (pigarro, estalo, respiração forte).** O
   Whisper cola o ruído na palavra seguinte e a ESTICA: "Mas" carimbado
   379,90–381,00 com o pigarro em 380,2–380,5 e a voz real em 380,9. O
   detector de região vê energia e chama de fala; o transcrito diz que a
   palavra está ali; nada acusa. Assinatura medida: 1ª palavra do trecho com
   duração muito acima do que as letras dela pedem E duas ou mais rajadas de
   energia separadas por silêncio dentro do carimbo. A voz é a ÚLTIMA rajada.

4. **Trecho baixo no meio de trechos normais.** O `verify_cut` já acusava
   (LOW-LEVEL) e pedia `gain_db` à mão; aqui ele já sai dimensionado:
   (mediana dos trechos − nível do trecho − 1 dB), teto de +8 dB.

O que NÃO se toca: trecho com `"manual": true`, borda digitada à mão
(`jcut_*_frames` no range) e respiros pedidos (`breaths[]` seguem com o
pedaço que os contém). O aperto só ENCOLHE um trecho, nunca o estende — então
não pode recolar nada que o `fala_limpa` tirou.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

SR, FR = 16000, 160          # 10 ms por quadro de energia
LEAD, TRAIL = 0.03, 0.07     # antes da voz / depois do último quadro com voz
MAXP = {"conservador": 0.40, "equilibrado": 0.20, "agressivo": 0.15}
KEEP = {"conservador": 0.15, "equilibrado": 0.08, "agressivo": 0.06}
GANHO_MIN_DB, GANHO_TETO_DB = 3.0, 8.0


def envelope_db(src: str) -> np.ndarray:
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", src, "-vn", "-ac", "1", "-ar", str(SR),
                          "-f", "s16le", "-"], capture_output=True, check=True).stdout
    x = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768
    x = x[: len(x) // FR * FR].reshape(-1, FR)
    rms = np.sqrt(np.convolve((x ** 2).mean(1), np.ones(3) / 3, "same"))
    return 20 * np.log10(rms + 1e-9)


def limiares(src: str) -> tuple[float, float]:
    """(ON, OFF): ON = limiar calibrado − 2 dB (onde a voz começa);
    OFF = 1,5 dB acima do piso (onde o decaimento termina). Mesma régua de todo
    o pipeline (Hard Rule 16b) — `cut_words.levels_for`."""
    from cut_words import levels_for, noise_floor_for  # noqa: PLC0415
    thr = noise_floor_for(Path(src))
    floor, _ = levels_for(Path(src))
    off = (floor + 1.5) if floor is not None else thr - 4
    return thr - 2.0, min(off, thr - 1.0)


def runs(db: np.ndarray, i: int, j: int, lim: float) -> list[tuple[int, int]]:
    """Rajadas acima de `lim` dentro de [i, j) em quadros."""
    v = db[i:j] > lim
    out, k = [], 0
    while k < len(v):
        if v[k]:
            a = k
            while k < len(v) and v[k]:
                k += 1
            out.append((i + a, i + k))
        k += 1
    return out


def palavras(edit: Path, src: str) -> list[dict]:
    p = edit / "transcripts" / f"{Path(src).stem}.json"
    try:
        return [w for w in json.loads(p.read_text())["words"] if w.get("type", "word") == "word"]
    except (OSError, KeyError, json.JSONDecodeError):
        return []


def ruido_na_cabeca(r: dict, ws: list[dict], db: np.ndarray, on: float, off: float) -> float | None:
    """Novo início se a 1ª palavra do trecho é um carimbo esticado sobre ruído."""
    s0 = float(r["start"])
    w = next((w for w in ws if float(w["end"]) > s0 + 0.02), None)
    if not w:
        return None
    ws_, we = max(float(w["start"]), s0), float(w["end"])
    letras = len(w["text"].strip(" .,;:!?…"))
    if we - ws_ < max(0.5, 0.12 * letras + 0.25):
        return None                          # a duração cabe na palavra
    rs = [(a, b) for a, b in runs(db, int(ws_ * 100), int(we * 100) + 1, on)]
    # rajadas separadas por ≥ 0,12 s de silêncio (abaixo do piso)
    grupos = []
    for a, b in rs:
        if grupos and a - grupos[-1][1] < 12:
            grupos[-1] = (grupos[-1][0], b)
        else:
            grupos.append((a, b))
    if len(grupos) < 2:
        return None
    novo = grupos[-1][0] / 100 - LEAD
    return novo if novo > s0 + 0.1 else None


def apertar(edl: dict, edit: Path, ritmo: str = "equilibrado") -> tuple[dict, list[str]]:
    maxp, keep = MAXP.get(ritmo, MAXP["equilibrado"]), KEEP.get(ritmo, KEEP["equilibrado"])
    cache: dict[str, tuple] = {}
    notas: list[str] = []
    novos: list[dict] = []
    for idx, r in enumerate(edl.get("ranges", [])):
        src = edl["sources"][r["source"]]
        if src not in cache:
            cache[src] = (envelope_db(src), *limiares(src), palavras(edit, src))
        db, on, off, ws = cache[src]
        if r.get("manual"):
            novos.append(r)
            continue
        s, e = float(r["start"]), float(r["end"])
        nc = ruido_na_cabeca(r, ws, db, on, off) if "jcut_lead_frames" not in r else None
        if nc:
            notas.append(f"trecho {idx}: ruído antes da 1ª palavra — início {s:.2f} → {nc:.2f}")
            s = nc
        i, j = int(s * 100), int(e * 100)
        voz = np.nonzero(db[i:j] > on)[0]
        if not len(voz):
            novos.append(r)
            continue
        cauda = np.nonzero(db[i:j] > off)[0]
        s1 = max(s, (i + voz[0]) / 100 - LEAD) if "jcut_lead_frames" not in r else s
        e1 = min(e, (i + cauda[-1] + 1) / 100 + TRAIL) if "jcut_tail_frames" not in r else e
        if s1 - s > 0.05 or e - e1 > 0.05:
            notas.append(f"trecho {idx}: borda até a voz — {s:.2f}–{e:.2f} → {s1:.2f}–{e1:.2f}")
        # pausas internas
        pecas, cur, k, mudo = [], s1, int(s1 * 100), 0
        while k < int(e1 * 100):
            if db[k] < off:
                mudo += 1
            else:
                if mudo / 100 > maxp:
                    fim = (k - mudo) / 100 + keep / 2
                    pecas.append((cur, fim))
                    notas.append(f"trecho {idx}: pausa interna {mudo / 100:.2f}s → {keep:.2f}s em {(k - mudo) / 100:.2f}")
                    cur = k / 100 - keep / 2
                mudo = 0
            k += 1
        pecas.append((cur, e1))
        for n, (a, b) in enumerate(pecas):
            if b - a < 0.08:
                continue
            p = dict(r, start=round(float(a), 3), end=round(float(b), 3))
            if len(pecas) > 1:
                # o `quote` é conferido pelo portão contra o conteúdo do trecho:
                # copiado inteiro em cada pedaço, todo pedaço reprovaria
                txt = " ".join(w["text"] for w in ws if a - 0.05 <= float(w["start"]) < b - 0.02)
                # pedaço sem palavra transcrita (respiro, ruído, fala que o
                # Whisper não ouviu) não herda a citação do trecho inteiro
                p["quote"] = txt
                p.pop("jcut_lead_frames", None) if n else None
                p.pop("jcut_tail_frames", None) if n < len(pecas) - 1 else None
                br = [x for x in r.get("breaths", []) if a <= float(x["at"]) and float(x["to"]) <= b]
                if br:
                    p["breaths"] = br
                else:
                    p.pop("breaths", None)
            novos.append(p)
    # ganho por trecho
    nivel = []
    for r in novos:
        db = cache[edl["sources"][r["source"]]][0]
        seg = db[int(float(r["start"]) * 100):int(float(r["end"]) * 100)]
        lin = 10 ** (seg / 20)
        nivel.append(20 * np.log10(np.sqrt(np.mean(lin ** 2)) + 1e-9) if len(seg) else None)
    validos = [v for v in nivel if v is not None]
    med = float(np.median(validos)) if validos else 0.0
    for r, v in zip(novos, nivel):
        if v is None or r.get("gain_db") or float(r["end"]) - float(r["start"]) < 0.5:
            continue
        if med - v > GANHO_MIN_DB:
            r["gain_db"] = float(round(min(med - v - 1.0, GANHO_TETO_DB), 1))
            notas.append(f"trecho {r['start']:.2f}: {v - med:+.1f} dB vs mediana → gain_db {r['gain_db']:+.1f}")
    out = dict(edl, ranges=novos)
    out.pop("jcut_timeline", None)  # posições antigas não valem mais; o render reescreve
    out["total_duration_s"] = round(sum(float(r["end"]) - float(r["start"]) for r in novos), 2)
    out["aperto"] = {"ritmo": ritmo, "maxp": maxp, "keep": keep}
    return out, notas


def bordas_com_voz(edl: dict, margem: float = 0.03) -> list[tuple[int, str, float, float]]:
    """O portão da palavra cortada: um trecho cujo fim (ou início) ainda tem voz
    na FONTE corta uma sílaba — independe do render, então pega o defeito antes
    dele. (Foi como "processá-los" saiu "processar" no corte, 2026-11-08.)"""
    cache: dict[str, tuple] = {}
    achados = []
    for i, r in enumerate(edl.get("ranges", [])):
        src = edl["sources"][r["source"]]
        if src not in cache:
            cache[src] = (envelope_db(src), *limiares(src))
        db, on, _off = cache[src]
        s, e = float(r["start"]), float(r["end"])
        fim = float(np.max(db[int((e - margem) * 100):max(int(e * 100), int((e - margem) * 100) + 1)]))
        ini = float(db[int(s * 100)])        # o PRIMEIRO quadro: voz já alta ali = entrou no meio da palavra
        if fim > on:
            achados.append((i, "fim", e, fim))
        if ini > on + 6:   # começo com voz alta = entrou no meio da palavra
            achados.append((i, "início", s, ini))
    return achados


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("edit", type=Path)
    ap.add_argument("--ritmo", default="equilibrado", choices=list(MAXP))
    ap.add_argument("--so-checar", action="store_true", help="só o portão da palavra cortada")
    a = ap.parse_args()
    p = a.edit / "edl.json"
    edl = json.loads(p.read_text())
    if not a.so_checar:
        edl, notas = apertar(edl, a.edit, a.ritmo)
        p.write_text(json.dumps(edl, ensure_ascii=False, indent=1))
        print(f"aperto ({a.ritmo}): {len(edl['ranges'])} trechos, {edl['total_duration_s']}s")
        for n in notas[:40]:
            print("  " + n)
        if len(notas) > 40:
            print(f"  … +{len(notas) - 40}")
    achados = bordas_com_voz(edl)
    for i, lado, t, v in achados:
        print(f"  BORDA COM VOZ trecho {i} ({lado} {t:.2f}s, {v:.0f} dBFS) — corta sílaba")
    return 1 if achados else 0


if __name__ == "__main__":
    sys.exit(main())

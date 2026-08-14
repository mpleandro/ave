#!/usr/bin/env python3
"""Escolhe a variante de accent por janela de legenda, medindo o fundo.

Por que existe: `#FF6B1A` não passa em WCAG sobre qualquer plano. Medido no
corte TallisGomes, a mesma laranja dá 2.49:1 sobre uma camiseta branca e sobra
de contraste sobre a parede escura. O `avelin.json` já prevê metade disso
("accentSoft em reserva para um plano escuro demais para #FF6B1A sentar em
cima"); o caso do plano CLARO a marca ainda não previa, e é o que mais reprova.

O que ele NÃO faz: inventar cor. As candidatas saem todas da paleta da marca —
a decisão é qual das laranjas existentes, nunca uma nova.

Uma passada de ffmpeg amostra a FAIXA DA LEGENDA (não o frame inteiro: o fundo
que importa é o que fica atrás do texto) em thumbnails minúsculas, e cada janela
recebe a média das amostras que caem dentro dela.

    uv run python helpers/backdrop_luma.py cut.mp4 windows.json -o accents.json

`windows.json` é uma lista de {"start": s, "end": s} em segundos do corte.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

# Candidatas — todas da paleta Avelin. Ordem = preferência quando empatam:
# a laranja canônica primeiro, para só sair dela quando o contraste obriga.
CANDIDATES = ["accent", "accentHover", "accentDark", "accentSoft"]

SAMPLE_FPS = 4.0   # amostras por segundo
SAMPLE_W, SAMPLE_H = 24, 8   # thumbnail por amostra; média, não detalhe
WCAG_MIN = 3.0     # texto grande (>=24px bold) — a régua do checker do HyperFrames


def _linear(c: float) -> float:
    """Canal sRGB 0..1 para linear (a curva, não um gamma 2.2 aproximado)."""
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(r: int, g: int, b: int) -> float:
    return (0.2126 * _linear(r / 255)
            + 0.7152 * _linear(g / 255)
            + 0.0722 * _linear(b / 255))


def contrast_ratio(l1: float, l2: float) -> float:
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def sample_band(video: Path, top_frac: float, height_frac: float,
                left_frac: float, width_frac: float) -> list[tuple[float, float]]:
    """Retorna [(tempo_s, luminancia)] amostrando só a faixa da legenda.

    Uma passada só. Recortar ANTES de escalar é o que torna a medida honesta:
    escalar o frame inteiro dilui o fundo do texto no resto da imagem, e é
    justamente o fundo do texto que decide a legibilidade.
    """
    vf = (f"crop=iw*{width_frac}:ih*{height_frac}:iw*{left_frac}:ih*{top_frac},"
          f"fps={SAMPLE_FPS},scale={SAMPLE_W}:{SAMPLE_H}")
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(video), "-vf", vf,
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True, check=True,
    )
    raw = proc.stdout
    per = SAMPLE_W * SAMPLE_H * 3
    out: list[tuple[float, float]] = []
    for i in range(len(raw) // per):
        px = raw[i * per:(i + 1) * per]
        # média em sRGB antes de linearizar: queremos a cor média que o olho vê
        # atrás do texto, não a média das luminâncias de pixels isolados.
        n = SAMPLE_W * SAMPLE_H
        r = sum(px[0::3]) / n
        g = sum(px[1::3]) / n
        b = sum(px[2::3]) / n
        out.append((i / SAMPLE_FPS, relative_luminance(int(r), int(g), int(b))))
    return out


def pick_accent(bg_luma: float, palette: dict) -> tuple[str, float]:
    """A laranja canônica se ela serve; a melhor alternativa só quando não serve.

    A primeira versão disto escolhia a candidata de MAIOR contraste e trocou o
    accent em 103 de 103 janelas — accentSoft, sendo a mais clara, ganha quase
    sempre. Isso não é adaptar, é abandonar a cor da marca. A regra do
    avelin.json é de reserva, não de otimização: `#FF6B1A` é a cor, e as outras
    existem para o plano em que ela não senta.
    """
    def ratio_of(name: str) -> float:
        return contrast_ratio(relative_luminance(*hex_to_rgb(palette[name])), bg_luma)

    canonical = CANDIDATES[0]
    if canonical in palette:
        r = ratio_of(canonical)
        if r >= WCAG_MIN:
            return canonical, r

    best_name, best_ratio = canonical, ratio_of(canonical) if canonical in palette else -1.0
    for name in CANDIDATES[1:]:
        if name not in palette:
            continue
        r = ratio_of(name)
        if r > best_ratio + 1e-9:
            best_name, best_ratio = name, r
    return best_name, best_ratio


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", type=Path)
    ap.add_argument("windows", type=Path, help='JSON: [{"start":s,"end":s}, ...]')
    ap.add_argument("-o", "--output", type=Path, required=True)
    ap.add_argument("--brand", type=Path,
                    default=Path(__file__).resolve().parent.parent / "brand" / "avelin.json")
    # Faixa medida, em frações do frame. O default cobre a banda de legenda
    # short-form (bottom:430px + ~2 linhas de 76px em 1920 de altura).
    ap.add_argument("--top", type=float, default=0.70)
    ap.add_argument("--height", type=float, default=0.14)
    ap.add_argument("--left", type=float, default=0.07)
    ap.add_argument("--width", type=float, default=0.86)
    args = ap.parse_args()

    palette = json.loads(args.brand.read_text())["palette"]
    windows = json.loads(args.windows.read_text())
    samples = sample_band(args.video, args.top, args.height, args.left, args.width)
    if not samples:
        sys.exit("nenhuma amostra extraída — confira o vídeo e a faixa")

    results = []
    switched = 0
    for w in windows:
        s, e = float(w["start"]), float(w["end"])
        inside = [lum for t, lum in samples if s <= t < e]
        if not inside:  # janela mais curta que o passo de amostragem
            inside = [min(samples, key=lambda tl: abs(tl[0] - (s + e) / 2))[1]]
        luma = sum(inside) / len(inside)
        name, ratio = pick_accent(luma, palette)
        if name != CANDIDATES[0]:
            switched += 1
        results.append({
            "start": round(s, 3), "end": round(e, 3),
            "bgLuma": round(luma, 4),
            "accent": name, "accentHex": palette[name],
            "ratio": round(ratio, 2), "passes": ratio >= WCAG_MIN,
        })

    args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    failing = [r for r in results if not r["passes"]]
    worst = min(results, key=lambda r: r["ratio"]) if results else None
    print(f"{len(results)} janelas · {len(samples)} amostras "
          f"({SAMPLE_FPS:g}/s na faixa {args.top:.2f}–{args.top + args.height:.2f})")
    print(f"  trocaram de accent: {switched}")
    print(f"  abaixo de {WCAG_MIN:g}:1 mesmo na melhor variante: {len(failing)}")
    if worst:
        print(f"  pior janela: {worst['ratio']}:1 em {worst['start']}s "
              f"com {worst['accent']}")
    print(f"  → {args.output}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Mede largura de texto com a MESMA fonte que o renderer vai usar.

Por que isso é um helper e não uma conta: a referência de short-form diz que as
linhas de legenda agrupam por LARGURA MEDIDA, limitadas por `maxWords`, nunca
por contagem de palavras — "inteligência" e "de" não podem obedecer à mesma
regra. Um agrupamento por contagem erra em toda palavra longa.

A fonte lida é o `.woff2` que o HyperFrames baixou e cacheou em
`~/.cache/hyperframes/fonts/`, que é literalmente o arquivo que o Chrome
headless vai usar no render. Medir com outra cópia da "mesma" fonte é como
medir com a fonte fallback: dá um número plausível e errado.

O Google Fonts serve cada peso em VÁRIOS arquivos (subsets: latin, latin-ext,
cyrillic…), então um único arquivo não cobre "ã", "ç" e "ê" ao mesmo tempo.
Aqui todos os subsets do peso pedido são carregados e consultados em ordem.

    uv run python helpers/text_measure.py "inteligência" --family "Open Sans" \
        --weight 700 --size 76
"""
from __future__ import annotations

import argparse
import functools
import sys
from pathlib import Path

FONT_CACHE = Path.home() / ".cache" / "hyperframes" / "fonts"


def slug(family: str) -> str:
    return family.strip().lower().replace(" ", "-")


def warm_cache(family: str, weight: int = 400, italic: bool = False) -> None:
    """Faz o HyperFrames baixar a família, montando uma página mínima que a pede.

    O cache só se enche quando o compilador do HyperFrames processa uma
    composição que referencia a fonte. Sem isto haveria ordem obrigatória
    ("renderize antes de medir"), que é uma pegadinha para quem chama o
    compositor pela primeira vez num projeto com fonte nova. Quem precisa da
    fonte é este helper, então é ele que sabe buscá-la.
    """
    import subprocess
    import tempfile

    style = "ital@1" if italic else f"wght@{weight}"
    fam = family.replace(" ", "+")
    href = (f"https://fonts.googleapis.com/css2?family={fam}:"
            f"{'ital,wght@1,' + str(weight) if italic else 'wght@' + str(weight)}&display=swap")
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        (d / "package.json").write_text('{"name":"warm","private":true,"type":"module"}')
        (d / "hyperframes.json").write_text('{"paths":{"blocks":"compositions"}}')
        (d / "index.html").write_text(
            f'<!doctype html><html><head><meta charset="UTF-8">'
            f'<link href="{href}" rel="stylesheet"></head><body>'
            f'<div id="root" data-composition-id="warm" data-start="0" data-duration="1" '
            f'data-width="64" data-height="64" data-no-timeline>'
            f'<div class="clip" data-start="0" data-duration="1" data-track-index="0" '
            f'style="font-family:\'{family}\';font-weight:{weight};'
            f'{"font-style:italic;" if italic else ""}">Aa</div></div></body></html>'
        )
        subprocess.run(
            ["npx", "--yes", "hyperframes@0.7.109", "check"],
            cwd=d, capture_output=True,
            env={**__import__("os").environ, "HYPERFRAMES_SKIP_SKILLS": "1"},
        )


def font_files(family: str, weight: int = 400, italic: bool = False) -> list[Path]:
    """Todos os subsets do peso/estilo pedido, do cache do HyperFrames."""
    d = FONT_CACHE / slug(family)
    if not d.is_dir():
        warm_cache(family, weight, italic)
    if not d.is_dir():
        raise FileNotFoundError(
            f"fonte '{family}' não está no cache do HyperFrames ({d}) e a tentativa "
            f"de baixá-la falhou.\nConfira o nome da família como o Google Fonts a "
            f"escreve, ou rode um `hyperframes check` na composição que a usa."
        )
    style = "italic" if italic else "normal"
    hits = sorted(d.glob(f"{weight}-{style}-*.woff2"))
    if not hits:
        have = sorted({p.name.split("-")[0] + "-" + p.name.split("-")[1] for p in d.glob("*.woff2")})
        raise FileNotFoundError(
            f"'{family}' não tem o corte {weight}-{style} no cache. Disponíveis: {', '.join(have)}"
        )
    return hits


@functools.lru_cache(maxsize=32)
def _tables(family: str, weight: int, italic: bool):
    """(upem, [(cmap, hmtx)]) para cada subset, na ordem de preferência.

    O arquivo chamado `700-normal-*.woff2` NÃO é necessariamente estático. O
    Google Fonts serve Open Sans como fonte VARIÁVEL: eixo `wght` de 300 a 800
    com default 400. Ler `hmtx` direto dali devolve os avanços do peso 400
    enquanto o browser instancia o 700 — medido, isso dava "inteligência" a
    402px contra 433px renderizados, 7% a MENOS, e para o lado perigoso (a
    linha estoura o safeWidth em vez de sobrar). Nome de arquivo não é metadado
    de peso; quem manda é o fvar. Por isso instanciamos no eixo antes de medir.
    """
    from fontTools.ttLib import TTFont
    from fontTools.varLib.instancer import instantiateVariableFont

    out, upem = [], None
    for p in font_files(family, weight, italic):
        f = TTFont(str(p))
        if "fvar" in f:
            axes = {a.axisTag: a for a in f["fvar"].axes}
            if "wght" in axes:
                a = axes["wght"]
                target = min(max(float(weight), a.minValue), a.maxValue)
                f = instantiateVariableFont(f, {"wght": target}, inplace=True,
                                            updateFontNames=False)
        upem = upem or f["head"].unitsPerEm
        out.append((f.getBestCmap(), f["hmtx"].metrics))
    return upem, out


def measure(text: str, family: str, size_px: float,
            weight: int = 400, italic: bool = False,
            letter_spacing_em: float = 0.0) -> float:
    """Largura em px de `text`, somando avanços de glifo.

    Soma de avanços ignora kerning, então o número sai levemente LARGO — o que
    é o erro seguro: uma linha nunca estoura o `safeWidth` por causa disso, no
    máximo cabe uma palavra a menos do que caberia.
    """
    upem, subsets = _tables(family, weight, italic)
    total = 0.0
    missing = 0
    for ch in text:
        adv = None
        for cmap, hmtx in subsets:
            gname = cmap.get(ord(ch))
            if gname and gname in hmtx:
                adv = hmtx[gname][0]
                break
        if adv is None:
            missing += 1
            # espaço como aproximação: some largura em vez de fingir zero
            adv = next((h[c[ord(" ")]][0] for c, h in subsets if ord(" ") in c), upem // 3)
        total += adv
    width = total * size_px / upem
    if letter_spacing_em:
        width += letter_spacing_em * size_px * len(text)
    return width


def group_by_width(words: list[dict], family: str, size_px: float, safe_width: float,
                   max_words: int, weight: int = 400, italic: bool = False,
                   space_em: float = 0.16) -> list[list[dict]]:
    """Agrupa palavras em linhas por largura medida, com `max_words` como TETO.

    Cada item precisa de "text". A largura do espaço entre palavras vem de
    `space_em` (o mesmo valor do CSS `margin` entre spans), senão a conta aqui e
    o layout no browser discordam justamente nas linhas cheias.

    Uma palavra sozinha mais larga que `safe_width` fica sozinha na linha: não
    há agrupamento que a salve, e quebrá-la seria pior.
    """
    lines: list[list[dict]] = []
    cur: list[dict] = []
    cur_w = 0.0
    gap = space_em * size_px
    for w in words:
        ww = measure(w["text"], family, size_px, weight, italic)
        add = ww if not cur else ww + gap
        if cur and (len(cur) >= max_words or cur_w + add > safe_width):
            lines.append(cur)
            cur, cur_w = [w], ww
        else:
            cur.append(w)
            cur_w += add
    if cur:
        lines.append(cur)
    return lines


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("text", nargs="+")
    ap.add_argument("--family", default="Open Sans")
    ap.add_argument("--weight", type=int, default=400)
    ap.add_argument("--italic", action="store_true")
    ap.add_argument("--size", type=float, default=76)
    args = ap.parse_args()

    try:
        for t in args.text:
            w = measure(t, args.family, args.size, args.weight, args.italic)
            print(f"{w:8.1f}px  {args.family} {args.weight}"
                  f"{' italic' if args.italic else ''} @{args.size:g}px  “{t}”")
    except FileNotFoundError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()

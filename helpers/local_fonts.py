#!/usr/bin/env python3
"""As fontes INSTALADAS nesta máquina, indexadas para a headline.

Por que isto existe: o catálogo do Google cobre bem o genérico e não cobre a
MARCA de ninguém. Quem edita tem a fonte da própria identidade instalada —
Gotham, D-DIN, a tipografia do cliente — e nenhuma delas passa pelo Google.
Sem este índice, escolher a fonte da marca era impossível e a headline saía
sempre com cara de template.

O que torna isto viável, e é a parte não óbvia: **o render roda em Chrome NESTA
máquina**, e o Chrome resolve `font-family: 'Gotham'` pelo nome, direto do
sistema. Então nem a prévia nem o render precisam do arquivo. Quem precisa dele
é a MEDIÇÃO (`text_measure`), que é local e abre o `hmtx` — e é por isso que o
índice guarda o caminho.

O PREÇO, e ele tem de estar escrito: um projeto que usa fonte local **não
renderiza igual em outra máquina**. O arquivo não viaja no `edit-data.json`.
Para algo que precise sobreviver à troca de máquina, ou se usa o catálogo do
Google, ou se põe o arquivo em `assets/styles/fonts/` (ver o LEIA-ME de lá).

Índice em `~/.avelin/localfonts.json`, refeito quando as pastas mudam.

Uso:
    uv run python helpers/local_fonts.py [--rebuild] [--grep <trecho>]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

INDEX = Path.home() / ".avelin" / "localfonts.json"
FONT_DIRS = [
    Path("/Library/Fonts"),
    Path.home() / "Library" / "Fonts",
    Path("/System/Library/Fonts"),
    Path("/System/Library/Fonts/Supplemental"),
]
EXTS = {".ttf", ".otf", ".ttc", ".otc"}

# Famílias do sistema que não são para desenhar headline: ícones, símbolos,
# interfaces do próprio macOS. Deixá-las na lista enche o seletor de opções que
# ninguém vai escolher e algumas nem têm alfabeto latino.
IGNORAR_PREFIXO = (
    "system font", ".", "apple color emoji", "apple symbols", "zapf dingbats",
    "webdings", "wingdings", "notdef", "lastresort", "hiragino", "pingfang",
    "heiti", "songti", "kaiti", "yuppy", "hannotate", "hanzipen", "libian",
    "weibei", "wawati", "xingkai", "baoli", "yasuo",
)


def _sig() -> str:
    """Assinatura das pastas: quantos arquivos e quando mudaram.

    Refazer o índice a cada abertura custaria dois segundos toda vez; nunca
    refazer deixaria a fonte recém-instalada invisível para sempre. A
    assinatura resolve os dois — muda quando alguém instala ou remove algo.
    """
    partes = []
    for d in FONT_DIRS:
        try:
            n = sum(1 for p in d.iterdir() if p.suffix.lower() in EXTS)
            partes.append(f"{d}:{n}:{int(d.stat().st_mtime)}")
        except OSError:
            partes.append(f"{d}:-")
    return "|".join(partes)


def _faces(path: Path) -> list[dict]:
    """(família, peso, itálico) de cada face do arquivo.

    `lazy=True` porque só interessam as tabelas `name` e `OS/2`: com elas o
    índice inteiro sai em ~2s para 2600 arquivos, contra minutos abrindo tudo.
    """
    import logging
    from fontTools.ttLib import TTFont, TTCollection
    # Fontes velhas trazem carimbo de data fora da faixa e o fontTools avisa em
    # stderr, uma linha por arquivo. Num índice de 2600 arquivos isso é ruído
    # que some com o log do servidor — e não é problema nenhum: a data não é
    # lida para nada aqui.
    logging.getLogger("fontTools").setLevel(logging.ERROR)
    out: list[dict] = []
    try:
        if path.suffix.lower() in (".ttc", ".otc"):
            col = TTCollection(str(path), lazy=True)
            fontes = list(col.fonts)
        else:
            fontes = [TTFont(str(path), lazy=True, fontNumber=0)]
    except Exception:
        return out
    for f in fontes:
        try:
            nm = f["name"]
            # nameID 16 é a família TIPOGRÁFICA ("Gotham"); a 1 é a família de
            # menu, que quebra os pesos em famílias separadas ("Gotham Black").
            # Sem preferir a 16, uma família de 8 pesos vira 8 famílias de um.
            fam = nm.getDebugName(16) or nm.getDebugName(1)
            if not fam:
                continue
            w = 400
            italic = False
            if "OS/2" in f:
                os2 = f["OS/2"]
                w = int(getattr(os2, "usWeightClass", 400) or 400)
                italic = bool(getattr(os2, "fsSelection", 0) & 1)
            if not italic and "head" in f:
                italic = bool(f["head"].macStyle & 2)
            out.append({"fam": fam.strip(), "w": max(100, min(w, 950)),
                        "i": italic, "p": str(path)})
        except Exception:
            continue
        finally:
            try:
                f.close()
            except Exception:
                pass
    return out


def build() -> dict:
    fams: dict[str, dict] = {}
    for d in FONT_DIRS:
        if not d.is_dir():
            continue
        for p in sorted(d.iterdir()):
            if p.suffix.lower() not in EXTS:
                continue
            for face in _faces(p):
                nome = face["fam"]
                if nome.lower().startswith(IGNORAR_PREFIXO):
                    continue
                e = fams.setdefault(nome, {"faces": []})
                # Um peso/estilo já visto não entra de novo: a mesma família
                # costuma existir em duas pastas, e a lista dobraria.
                if any(x["w"] == face["w"] and x["i"] == face["i"] for x in e["faces"]):
                    continue
                e["faces"].append({"w": face["w"], "i": face["i"], "p": face["p"]})
    for e in fams.values():
        e["faces"].sort(key=lambda x: (x["i"], x["w"]))
    data = {"builtAt": time.time(), "sig": _sig(),
            "families": dict(sorted(fams.items(), key=lambda kv: kv[0].lower()))}
    try:
        INDEX.parent.mkdir(parents=True, exist_ok=True)
        tmp = INDEX.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False))
        tmp.replace(INDEX)
    except OSError:
        pass
    return data


def load(rebuild: bool = False) -> dict:
    """O índice, refeito só quando as pastas mudaram."""
    if not rebuild:
        try:
            d = json.loads(INDEX.read_text())
            if d.get("sig") == _sig():
                return d
        except (OSError, json.JSONDecodeError):
            pass
    return build()


def find(family: str, weight: int = 400, italic: bool = False) -> Path | None:
    """O arquivo do corte pedido — ou o mais próximo que a família tem.

    O mais próximo e não um erro: uma família local raramente tem os nove
    pesos, e o layout pede 900 sem saber disso. Cair para o 700 desenha certo;
    morrer aqui pararia a composição por um detalhe que o usuário não escolheu.
    """
    e = load().get("families", {}).get(family)
    if not e or not e["faces"]:
        return None
    mesmos = [f for f in e["faces"] if f["i"] == italic] or e["faces"]
    melhor = min(mesmos, key=lambda f: abs(f["w"] - weight))
    p = Path(melhor["p"])
    return p if p.is_file() else None


def catalog() -> list[dict]:
    """O que o seletor mostra: família + pesos disponíveis, sem os caminhos.

    Sem os caminhos de propósito — o navegador resolve a fonte pelo NOME (é
    assim que `font-family: Helvetica` sempre funcionou), então mandar o
    caminho seria expor a árvore de arquivos do usuário sem nenhum uso.
    """
    fam = load().get("families", {})
    return [{"n": n, "w": sorted({f["w"] for f in e["faces"]}), "k": "local"}
            for n, e in fam.items() if e["faces"]]


def main() -> int:
    ap = argparse.ArgumentParser(description="Índice das fontes instaladas")
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--grep", default="")
    args = ap.parse_args()
    t0 = time.time()
    d = load(rebuild=args.rebuild)
    fams = d["families"]
    print(f"{len(fams)} famílias em {time.time() - t0:.1f}s  →  {INDEX}")
    for n, e in fams.items():
        if args.grep and args.grep.lower() not in n.lower():
            continue
        pesos = ",".join(str(w) for w in sorted({f["w"] for f in e["faces"]}))
        print(f"  {n:44s} {pesos}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

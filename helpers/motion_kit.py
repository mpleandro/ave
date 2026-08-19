#!/usr/bin/env python3
"""Motion Kit — o vocabulário de layout/movimento dos Broll Overlays, APRENDIDO.

    uv run python helpers/motion_kit.py --mostrar
    uv run python helpers/motion_kit.py --validar ~/.avelin/motion/kit.json

A DIVISÃO DE CAMADAS, que é o ponto:

  · O repositório entrega o MECANISMO e um kit default (assets/motion/
    default.json — vermelho/preto, tipografia genérica). É o que um usuário
    novo recebe ao clonar.
  · O kit de CADA usuário vive FORA do clone, em ~/.avelin/motion/kit.json —
    mesma razão de preferencias.json e brand.json: é gosto aprendido de meses,
    não configuração, e não pode morrer num `git clean` nem subir num push.
  · As CORES herdam da marca: ~/.avelin/brand.json (accent/deep) vence o que o
    kit declarar. Um kit aprendido de um site antigo não prende o usuário à
    paleta daquela época — a marca é a fonte da verdade da cor; o kit, da FORMA
    e do MOVIMENTO.

COMO UM KIT NASCE (o "aprendizado"): o usuário aponta uma pasta de referências
(landing pages, CSS, SVGs, screenshots, sites) e a IA destila — paleta, papéis
tipográficos, formas (raios, molduras, pills), sombras, e os NÚMEROS do
movimento (staggers, durações, easings, loops) — neste JSON. O designkit.md de
uma LP é o caso ideal; na falta dele, lê-se o CSS/SVG cru. O kit gravado é o
contrato: a composição só consome números, nunca reinterpreta a referência.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
KIT_USUARIO = Path.home() / ".avelin" / "motion" / "kit.json"
KIT_DEFAULT = SKILL_DIR / "assets" / "motion" / "default.json"
BRAND = Path.home() / ".avelin" / "brand.json"

OBRIGATORIAS = ("cores", "fontes", "texto", "formas", "motion")


def _ler(p: Path) -> dict | None:
    try:
        return json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def carregar_kit() -> dict:
    """O kit ativo: o do usuário quando existe e é válido, senão o default.

    Depois de escolhido, as cores da MARCA (brand.json) sobrescrevem
    accent/deep — herança pedida pelo protocolo do usuário (2026-08-19).
    """
    kit = _ler(KIT_USUARIO)
    if kit is None or any(k not in kit for k in OBRIGATORIAS):
        if kit is not None:
            print(f"  aviso: kit do usuário inválido ({KIT_USUARIO}) — usando o default",
                  file=sys.stderr)
        kit = _ler(KIT_DEFAULT) or {}
    brand = _ler(BRAND) or {}
    cores = kit.setdefault("cores", {})
    if brand.get("accent"):
        cores["accent"] = brand["accent"]
    if brand.get("deep"):
        cores["deep"] = brand["deep"]
    return kit


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mostrar", action="store_true",
                    help="imprime o kit ATIVO já resolvido com a marca")
    ap.add_argument("--validar", type=Path, default=None,
                    help="confere um kit.json e diz o que falta")
    args = ap.parse_args()

    if args.validar:
        d = _ler(args.validar)
        if d is None:
            sys.exit(f"não consegui ler {args.validar}")
        faltam = [k for k in OBRIGATORIAS if k not in d]
        if faltam:
            sys.exit(f"faltam seções: {', '.join(faltam)}")
        print(f"kit '{d.get('name', '?')}' válido")
        return

    kit = carregar_kit()
    fonte = "usuário" if _ler(KIT_USUARIO) else "default"
    print(f"kit ativo: {kit.get('name', '?')} ({fonte})")
    print(json.dumps(kit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

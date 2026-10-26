#!/usr/bin/env python3
"""LEGENDAS PRIVADAS — estilos de legenda que moram fora do repositório.

Um estilo de legenda pode ser de UMA pessoa: o look da marca dela, o formato
que ela desenvolveu e não quer distribuir. Ele mora em
`~/.avelin/legendas/<id>/`, ao lado do `brand.json` e dos estilos salvos, e
nunca entra no clone — o que o repositório tem é só este mecanismo, que não
sabe nada de nenhum estilo em particular.

Uma pasta de estilo:

    ~/.avelin/legendas/<id>/
        legenda.json   {"id", "nome", "descricao", "css", "js", "motor"}
        <css>          a aparência (copiada para <projeto>/styles/legpriv-<id>.css)
        <js>           animação do render E a prévia da galeria:
                       window.AVE_LEGPRIV[<id>] = {buildTimeline(root, gsap, tl), demo(host, ctx)}
        <motor>.py     montar(data, palavras, duracao, accent, W, H, events) -> dict
                       {"markup", "gfont"?} — o compositor só encaixa o que volta

O editor lista os estilos (`/api/legendas-privadas`), carrega a folha e o
script (`/legpriv/<id>/<arquivo>`) e os mostra PRIMEIRO na galeria de
legendas, com a borda laranja dos estilos pessoais.

    legendas_privadas.py            # lista o que existe
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

DIR = Path.home() / ".avelin" / "legendas"


def listar() -> list[dict]:
    """Os estilos privados válidos (com legenda.json legível), por nome."""
    out = []
    if not DIR.is_dir():
        return out
    for p in sorted(DIR.iterdir()):
        meta = carregar(p.name)
        if meta:
            out.append(meta)
    return out


def carregar(sid: str) -> dict | None:
    if not sid or "/" in sid or sid.startswith("."):
        return None
    f = DIR / sid / "legenda.json"
    try:
        meta = json.loads(f.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    meta["id"] = sid
    meta.setdefault("nome", sid)
    return meta


def ids() -> set[str]:
    return {m["id"] for m in listar()}


def motor(sid: str):
    """O módulo Python que monta a marcação do estilo."""
    meta = carregar(sid) or {}
    f = DIR / sid / meta.get("motor", "compor.py")
    if not f.exists():
        raise SystemExit(f"legenda privada '{sid}': motor {f} não existe")
    spec = importlib.util.spec_from_file_location(f"legpriv_{sid}", f)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(Path(__file__).resolve().parent))   # o motor pode importar helpers
    spec.loader.exec_module(mod)
    return mod


def copiar(sid: str, proj: Path) -> tuple[str, str]:
    """Copia folha e script para <proj>/styles/ e devolve os nomes publicados."""
    meta = carregar(sid) or {}
    dst = Path(proj) / "styles"
    dst.mkdir(parents=True, exist_ok=True)
    css, js = f"legpriv-{sid}.css", f"legpriv-{sid}.js"
    shutil.copyfile(DIR / sid / meta.get("css", "estilo.css"), dst / css)
    shutil.copyfile(DIR / sid / meta.get("js", "estilo.js"), dst / js)
    return css, js


if __name__ == "__main__":
    for m in listar():
        print(f"{m['id']:<14} {m['nome']}  — {m.get('descricao', '')}")
    if not DIR.is_dir():
        print(f"(nenhuma — {DIR} não existe)")

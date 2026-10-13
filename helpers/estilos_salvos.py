#!/usr/bin/env python3
"""ESTILOS SALVOS — o padrão de uma série, com nome, reaplicado num clique.

Um vídeo entregue e aprovado carrega dezenas de decisões que o próximo da mesma
série quer repetir: formato, headline, legenda, cores, fontes, posições,
elementos, as opções da moldura explicativa. O `estilo.json` lembra só a ÚLTIMA
escolha (um espaço, sobrescrito a cada envio); isto guarda VÁRIAS, com o nome
que o usuário deu — "Reels Vértuz", "Aulas do curso X".

Mora em `~/.avelin/estilos_salvos.json`, fora do clone e do projeto, pela razão
da marca: é de quem edita, não do vídeo. A aba Estilo mostra cada um como o
primeiro cartão da seção Formato, com borda laranja e o nome; clicar aplica
tudo. Quem SALVA é a IA, depois da entrega, perguntando (AskUserQuestion) —
ver SKILL.md, "Estilos salvos".

    estilos_salvos.py salvar <edit> --nome "Reels Vértuz"
    estilos_salvos.py listar
    estilos_salvos.py remover --nome "Reels Vértuz"
    estilos_salvos.py igual <edit>      # já existe um salvo idêntico? (exit 0 = sim)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

ARQ = Path.home() / ".avelin" / "estilos_salvos.json"
# o que um estilo É — conteúdo (texto da headline, pergunta da caixinha, cenas)
# fica de fora: muda a cada vídeo
CHAVES = ("edit", "headline", "captions", "accent", "capColor", "textColor",
          "fontMain", "fontAccent", "capFont", "capDy", "hookDx", "hookDy",
          "hookScale", "elements")


def carregar() -> list[dict]:
    try:
        return json.loads(ARQ.read_text()).get("estilos", [])
    except (OSError, json.JSONDecodeError):
        return []


def gravar(lista: list[dict]) -> None:
    ARQ.parent.mkdir(parents=True, exist_ok=True)
    tmp = ARQ.with_suffix(".tmp")
    tmp.write_text(json.dumps({"estilos": lista}, ensure_ascii=False, indent=2))
    tmp.replace(ARQ)


def slug(nome: str) -> str:
    s = unicodedata.normalize("NFD", nome.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-") or "estilo"


def do_projeto(edit: Path) -> dict:
    """O estilo ENTREGUE: o edit-data (o que foi renderizado) vence o state."""
    st = json.loads((edit / "state.json").read_text()) if (edit / "state.json").exists() else {}
    dp = edit / "hyperframes" / "edit-data.json"
    d = json.loads(dp.read_text()) if dp.exists() else {}
    s = dict(st.get("style") or {})
    hook, caps = d.get("hook") or {}, d.get("captions") or {}
    s.update({k: v for k, v in {
        "edit": d.get("editStyle"),
        "headline": hook.get("style"),
        "captions": caps.get("style"),
        "accent": d.get("accent"),
        "capColor": caps.get("color"),
        "textColor": hook.get("color"),
        "fontMain": hook.get("fontMain"),
        "fontAccent": hook.get("fontAccent"),
        "capFont": caps.get("fontMain"),
    }.items() if v})
    if d.get("elements"):
        s["elements"] = {**(s.get("elements") or {}), **d["elements"]}
    estilo = {k: s[k] for k in CHAVES if k in s and s[k] not in (None, "")}
    out = {"style": estilo}
    ex = d.get("explicativo") or {}
    if (estilo.get("elements") or {}).get("explicativo") or ex:
        out["explicativo"] = {k: ex[k] for k in ("base", "cabecaVaza", "fundo") if k in ex}
    if st.get("ritmo"):
        out["ritmo"] = st["ritmo"]
    return out


def _assinatura(e: dict) -> str:
    return json.dumps({"style": e.get("style"), "explicativo": e.get("explicativo")},
                      sort_keys=True, ensure_ascii=False)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("salvar")
    s.add_argument("edit", type=Path)
    s.add_argument("--nome", required=True)
    sub.add_parser("listar")
    r = sub.add_parser("remover")
    r.add_argument("--nome", required=True)
    i = sub.add_parser("igual")
    i.add_argument("edit", type=Path)
    args = ap.parse_args()

    lista = carregar()
    if args.cmd == "listar":
        formatos = ("caixinha", "brollOverlay", "noticia", "animTexto", "anim3d", "explicativo")
        for e in lista:
            st = e["style"]
            fmt = next((k for k, v in (st.get("elements") or {}).items() if v and k in formatos),
                       st.get("edit"))
            print(f"{e['nome']}  ({e['id']}) — formato {fmt} · headline {st.get('headline')}"
                  f" · legenda {st.get('captions')} · {st.get('accent')}")
        if not lista:
            print("nenhum estilo salvo")
        return
    if args.cmd == "remover":
        resto = [e for e in lista if e["nome"] != args.nome and e["id"] != slug(args.nome)]
        if len(resto) == len(lista):
            sys.exit(f"não achei '{args.nome}'")
        gravar(resto)
        print(f"removido: {args.nome}")
        return
    novo = do_projeto(args.edit.resolve())
    if args.cmd == "igual":
        ig = next((e for e in lista if _assinatura(e) == _assinatura(novo)), None)
        print(ig["nome"] if ig else "")
        sys.exit(0 if ig else 1)
    nome = args.nome.strip()
    entrada = {"id": slug(nome), "nome": nome, "criado": time.strftime("%Y-%m-%d %H:%M"),
               "origem": json.loads((args.edit / "state.json").read_text()).get("project", "")
               if (args.edit / "state.json").exists() else "", **novo}
    # mesmo nome = atualização (o usuário refinou o padrão), não duplicata
    lista = [e for e in lista if e["id"] != entrada["id"]] + [entrada]
    gravar(lista)
    st = entrada["style"]
    print(f"salvo: {nome} — formato {st.get('edit')} · headline {st.get('headline')} · "
          f"legenda {st.get('captions')} · destaque {st.get('accent')}")


if __name__ == "__main__":
    main()

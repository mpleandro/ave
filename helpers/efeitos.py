#!/usr/bin/env python3
"""EFEITOS — o motor único dos efeitos de vídeo da Fase 2 short-form.

Nasceu da referência "17 video effects claude can create" (2026-10-15). Em vez
de uma chave solta por efeito, um motor só: `edit-data.json → efeitos[]`, cada
entrada com `tipo`, ancorada na FALA (frase de início/fim, palavra do item) ou
em tempo. A aparência mora em `assets/styles/efeitos.css`, a animação em
`efeitos.js`, os números em `variants.json → efeitos`; quem monta o HTML é
`efeitos_compose.py`.

Quatro papéis, quatro lugares no editor:

  * EFEITOS (camada própria) — ilustram o que está sendo dito:
      checklist · chartGrow · phoneMockup · uiWorld
  * MOVIMENTO (camada "Movimento & tracking") — câmera:
      zoomPunch (zoom digital na frase de efeito) · zoomThrough (zoom que
      atravessa o corte)
  * GANCHO (camada Headline, "Efeito do gancho") — os primeiros segundos:
      frameBreak · coverStory · headlineWall · couchWall · orbit · vertigo
      (`edit-data.json → ganchoEfeito`)
  * FORMATO de vídeo inteiro: fundoTrocado · caderno

A REGRA DO FORMATO (pedido do usuário, 2026-10-15): efeito AUTOMÁTICO só entra
quando o formato escolhido o prevê — `variants.json → efeitos.formatos`. O
formato "Nenhum" (`limpa`) não prevê nada. Quando prevê, entra sem perguntar:
quem decide se fica é o usuário, removendo no editor.

    efeitos.py candidatos <edit>        # a fala, com os efeitos que cada frase pede
    efeitos.py validar <edit> [--gravar]  # resolve frase→tempo, aplica a regra do formato
    efeitos.py permitidos <edit>        # o que o formato atual deixa entrar

Uma entrada:

    {"tipo": "checklist", "de": "primeiro ela", "ate": "mudar a rota",
     "titulo": "o que ela disse",
     "itens": [{"texto": "Cansou da internet", "palavra": "internet"}, ...]}
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HELPERS = Path(__file__).resolve().parent
sys.path.insert(0, str(HELPERS))
import explicativo as X  # noqa: E402  (palavras, _achar, _norm, frases, rosto)

SKILL = HELPERS.parent
VARIANTS = json.loads((SKILL / "assets" / "styles" / "variants.json").read_text())

# camada → onde o efeito mora no editor; recorte → precisa da pessoa recortada
CATALOGO: dict[str, dict] = {
    "checklist":   {"camada": "efeitos",   "nome": "Checklist"},
    "chartGrow":   {"camada": "efeitos",   "nome": "Gráfico crescendo"},
    "phoneMockup": {"camada": "efeitos",   "nome": "Celular na tela"},
    "uiWorld":     {"camada": "efeitos",   "nome": "Mundo de interface", "recorte": "atras"},
    "zoomPunch":   {"camada": "movimento", "nome": "Zoom digital"},
    "zoomThrough": {"camada": "movimento", "nome": "Zoom através do corte"},
}
GANCHOS: dict[str, dict] = {
    "frameBreak":   {"nome": "Quebra de moldura", "recorte": "fgr"},
    "coverStory":   {"nome": "Capa de revista", "recorte": "atras", "substituiHook": True},
    "headlineWall": {"nome": "Parede de manchetes", "recorte": "atras", "substituiHook": True},
    "couchWall":    {"nome": "Parede de vídeos", "recorte": "atras"},
    "orbit":        {"nome": "Órbita", "recorte": "atras"},
    "vertigo":      {"nome": "Vertigo", "bake": True},
}
# formatos de vídeo inteiro que recortam a pessoa do começo ao fim
FORMATOS_RECORTE = {"fundoTrocado": "Fundo trocado", "caderno": "Caderno"}

MAX_ITENS = 5
MAX_BARRAS = 7


def formato_de(data: dict) -> str:
    """O formato escolhido na aba — um só (ver EDIT_ELEMENTS no app.js)."""
    els = data.get("elements") or {}
    for fid in ("ilustrado", "brollOverlay", "animTexto", "anim3d", "explicativo",
                *FORMATOS_RECORTE):
        if els.get(fid):
            return fid
    return data.get("editStyle") or "limpa"


def permitidos(data: dict) -> list[str]:
    """Efeitos AUTOMÁTICOS que o formato prevê. "Nenhum" não prevê nada."""
    return list((VARIANTS["efeitos"]["formatos"]).get(formato_de(data), []))


# desmarcados por padrão no editor (pedido do usuário, 2026-10-15): sem a
# chave no dado, NÃO entram — os outros continuam entrando sozinhos
DESLIGADOS_POR_PADRAO = {"zoomThrough"}


def ligados(data: dict) -> list[str]:
    """Os que o formato prevê E o usuário não desligou na camada."""
    els = data.get("elements") or {}
    return [t for t in permitidos(data) if els.get(t, t not in DESLIGADOS_POR_PADRAO)]


# ---------------------------------------------------------------- resolução

def _tempo(ws, frase, desde, ate=1e9, fim=False):
    return X._achar(ws, frase, desde, ate, fim=fim)


def resolver(data: dict, ws: list[dict], duracao: float) -> tuple[list[dict], list[str], list[str]]:
    """Entradas de `efeitos[]` com `start`/`end` resolvidos + (erros, avisos).

    A FRASE vence o tempo gravado (mesma regra do explicativo): o tempo é
    derivado dela, e um efeito editado com o tempo antigo no dado entraria no
    lugar errado. Entradas que o formato não prevê SAEM, com aviso — a regra
    do formato vale até para efeito escrito à mão."""
    vivos = set(ligados(data))
    out, erros, avisos = [], [], []
    for n, e in enumerate(data.get("efeitos") or [], 1):
        e = json.loads(json.dumps(e))
        tipo = e.get("tipo")
        nome = f"efeito {n} ({tipo})"
        if tipo not in CATALOGO:
            erros.append(f"{nome}: tipo não existe ({', '.join(CATALOGO)})")
            continue
        if tipo not in vivos:
            motivo = ("desligado na camada" if tipo in permitidos(data)
                      else f"o formato '{formato_de(data)}' não prevê este efeito")
            avisos.append(f"{nome}: fora — {motivo}")
            continue
        if "de" in e:
            t = _tempo(ws, e["de"], 0)
            if t is None:
                erros.append(f"{nome}: não achei \"{e['de']}\" na fala")
                continue
            e["start"] = t
        if "ate" in e:
            t = _tempo(ws, e["ate"], e.get("start", 0), fim=True)
            if t is None:
                erros.append(f"{nome}: não achei \"{e['ate']}\" na fala")
                continue
            e["end"] = t
        if "palavra" in e and "start" not in e:
            t = _tempo(ws, e["palavra"], 0)
            if t is None:
                erros.append(f"{nome}: não achei \"{e['palavra']}\" na fala")
                continue
            e["start"] = t
        if tipo == "zoomThrough":
            if "at" not in e and "start" not in e:
                erros.append(f"{nome}: precisa de `at` (o instante do corte)")
                continue
            e["at"] = round(float(e.get("at", e.get("start"))), 3)
            out.append(e)
            continue
        if "start" not in e:
            erros.append(f"{nome}: precisa de start/end, de/ate ou palavra")
            continue
        if "end" not in e:
            e["end"] = e["start"] + float(VARIANTS["efeitos"]["duracaoPadrao"].get(tipo, 3.0))
        e["start"] = round(float(e["start"]), 3)
        e["end"] = round(min(float(e["end"]), duracao), 3)
        if e["end"] - e["start"] < 0.3:
            erros.append(f"{nome}: {e['end'] - e['start']:.2f}s no ar — curto demais")
            continue
        itens = e.get("itens") or []
        if tipo == "checklist":
            if not itens:
                erros.append(f"{nome}: checklist sem `itens`")
                continue
            if len(itens) > MAX_ITENS:
                erros.append(f"{nome}: {len(itens)} itens — no máximo {MAX_ITENS}")
        if tipo == "chartGrow":
            vals = e.get("valores") or []
            if not vals:
                erros.append(f"{nome}: gráfico sem `valores`")
                continue
            if len(vals) > MAX_BARRAS:
                erros.append(f"{nome}: {len(vals)} barras — no máximo {MAX_BARRAS}")
        # itens, bolhas e peças: cada um entra na PALAVRA que o cita
        for it in itens + (e.get("mensagens") or []):
            if isinstance(it, dict) and it.get("palavra"):
                t = _tempo(ws, it["palavra"], e["start"] - 0.3, e["end"])
                if t is None:
                    avisos.append(f"{nome}: não achei \"{it['palavra']}\" dentro do efeito — "
                                  f"o item entra em sequência")
                else:
                    it["at"] = round(t + 0.05, 3)
        out.append(e)
    # DOIS EFEITOS DA MESMA CAMADA NÃO SE ENCAVALAM — disputariam a mesma tela.
    # Movimento convive com conteúdo (um mexe a câmera, o outro desenha).
    conteudo = sorted((e for e in out if CATALOGO[e["tipo"]]["camada"] == "efeitos"),
                      key=lambda e: e["start"])
    for a, b in zip(conteudo, conteudo[1:]):
        if b["start"] < a["end"] - 1e-3:
            erros.append(f"{a['tipo']} ({a['start']:.2f}–{a['end']:.2f}s) e {b['tipo']} "
                         f"({b['start']:.2f}s) se encavalam — um efeito de conteúdo por vez")
    return out, erros, avisos


def gancho(data: dict) -> dict | None:
    """O efeito do gancho resolvido: janela [0, fim do gancho]."""
    g = data.get("ganchoEfeito") or {}
    tipo = g.get("tipo")
    if not tipo:
        return None
    if tipo not in GANCHOS:
        raise SystemExit(f"efeito de gancho '{tipo}' não existe ({', '.join(GANCHOS)})")
    hk = data.get("hook") or {}
    fim = float(g.get("end") or (hk.get("endSec") if hk.get("enabled") else None)
                or VARIANTS["efeitos"]["ganchoPadrao"])
    return {**g, "start": round(float(g.get("start", 0.0)), 3), "end": round(fim, 3)}


def janelas_recorte(data: dict, itens: list[dict], duracao: float) -> list[tuple[float, float, bool]]:
    """(início, fim, fundoNovo) de cada trecho que precisa da pessoa recortada.

    `atras` mantém a cor da gravação (a pessoa volta para o MESMO fundo, com o
    gráfico no meio); `fgr` é cor descontaminada, para quando o fundo muda."""
    out = []
    for e in itens:
        modo = CATALOGO.get(e["tipo"], {}).get("recorte")
        if modo and e.get("atras", True):
            out.append((e["start"], e["end"], modo == "fgr"))
    g = gancho(data)
    if g:
        modo = GANCHOS[g["tipo"]].get("recorte")
        if modo:
            out.append((g["start"], g["end"], modo == "fgr"))
    fmt = formato_de(data)
    if fmt in FORMATOS_RECORTE:
        out.append((0.0, round(duracao, 3), True))
    return out


# ---------------------------------------------------------------- automáticos

def frases_de_efeito(ws: list[dict]) -> list[dict]:
    """Frases curtas e isoladas — "Trambicagem." "É incoerente." "Egoísmo." —
    o desfecho de uma ideia. É onde o zoom digital entra: punch na frase que
    fecha, nunca no meio de uma explicação."""
    out = []
    fs = X.frases(ws)
    for i, f in enumerate(fs):
        n = len(f["texto"].split())
        antes = fs[i - 1]["end"] if i else -9
        txt = f["texto"].strip()
        # frase INTEIRA: começa em maiúscula e fecha com pontuação. "Ou" solto
        # por uma pausa no meio de "ou seja" é respiro, não desfecho.
        inteira = txt[:1].isupper() and re.search(r"[.!?…]$", txt)
        forte = any(len(X._norm(w)) >= 5 for w in txt.split())
        if (1 <= n <= 4 and inteira and forte and f["start"] - antes >= 0.25
                and f["end"] - f["start"] <= 2.2):
            out.append({"start": round(f["start"], 3),
                        "end": round(max(f["end"] + 0.35, f["start"] + 0.9), 3),
                        "texto": f["texto"]})
    return out


def automaticos(data: dict, ws: list[dict], segs: list[dict], duracao: float) -> list[dict]:
    """Movimento que o motor posiciona SOZINHO quando o formato prevê e não há
    entrada escrita à mão do mesmo tipo: zoom digital nas frases de efeito,
    zoom através nos cortes de verdade (junções do EDL). Conteúdo (checklist,
    gráfico, celular) não: o texto dele é escrita, e quem escreve é o agente."""
    vivos = set(ligados(data))
    manuais = {e.get("tipo") for e in (data.get("efeitos") or [])}
    cfg = VARIANTS["efeitos"]
    out = []
    if "zoomPunch" in vivos and "zoomPunch" not in manuais:
        ultimo = -99.0
        for f in frases_de_efeito(ws):
            if f["start"] < float((data.get("hook") or {}).get("endSec", 0)) + 0.5:
                continue                      # o gancho é dele
            if f["start"] - ultimo < cfg["zoomPunch"]["intervaloMinimo"]:
                continue
            out.append({"tipo": "zoomPunch", "start": f["start"], "end": min(f["end"], duracao),
                        "auto": True})
            ultimo = f["start"]
    if "zoomThrough" in vivos and "zoomThrough" not in manuais:
        ultimo = -99.0
        for s in segs[1:]:
            at = float(s["start"])
            if at < 1.0 or at > duracao - 1.0 or at - ultimo < cfg["zoomThrough"]["intervaloMinimo"]:
                continue
            out.append({"tipo": "zoomThrough", "at": round(at, 3), "auto": True})
            ultimo = at
    return out


# ---------------------------------------------------------------- CLI

APPS = r"\b(app|aplicativo|celular|instagram|whatsapp|tiktok|youtube|mensagem|notificacao|direct|dm|story|stories)\b"
SOFTWARE = r"\b(ia|inteligencia artificial|ferramenta|software|site|plataforma|sistema|automacao|chatgpt|claude|programa)\b"


def cmd_candidatos(args) -> None:
    edit = args.edit.resolve()
    data = _data(edit)
    print(f"formato: {formato_de(data)} · efeitos automáticos previstos: "
          f"{', '.join(ligados(data)) or 'nenhum'}\n")
    for f in X.frases(X.palavras(edit)):
        t = X._norm(f["texto"], virgula=True)
        tags = []
        if any(re.search(rx, t) for g, rx in X.GATILHOS if g == "lista"):
            tags.append("checklist")
        if any(re.search(rx, t) for g, rx in X.GATILHOS if g == "numero"):
            tags.append("chartGrow")
        if re.search(APPS, t):
            tags.append("phoneMockup")
        if re.search(SOFTWARE, t):
            tags.append("uiWorld")
        tags = [x for x in tags if x in ligados(data)]
        marca = f"  ← {', '.join(tags)}" if tags else ""
        print(f"[{f['start']:6.2f}–{f['end']:6.2f}] {f['texto']}{marca}")
    if "zoomPunch" in ligados(data):
        print("\nfrases de efeito (zoom digital automático):")
        for f in frases_de_efeito(X.palavras(edit)):
            print(f"  [{f['start']:6.2f}] {f['texto']}")


def _data(edit: Path) -> dict:
    p = edit / "hyperframes" / "edit-data.json"
    return json.loads(p.read_text()) if p.exists() else {}


def cmd_validar(args) -> None:
    edit = args.edit.resolve()
    data = _data(edit)
    dur = X.sonda(edit / "preview.mp4")[2]
    itens, erros, avisos = resolver(data, X.palavras(edit), dur)
    for e in itens:
        quando = (f"{e['at']:6.2f}s" if "at" in e and e["tipo"] == "zoomThrough"
                  else f"{e['start']:6.2f}–{e['end']:6.2f}s")
        print(f"  {quando}  {e['tipo']:<12} {e.get('titulo') or e.get('texto') or ''}")
    for a in avisos:
        print(f"  aviso: {a}")
    for x in erros:
        print(f"  ERRO: {x}")
    g = gancho(data)
    if g:
        print(f"  gancho: {g['tipo']} {g['start']:.2f}–{g['end']:.2f}s")
    if erros:
        sys.exit(1)
    if args.gravar:
        p = edit / "hyperframes" / "edit-data.json"
        d = json.loads(p.read_text())
        d["efeitos"] = [e for e in itens if not e.get("auto")] + \
            [e for e in (d.get("efeitos") or []) if e.get("tipo") not in ligados(d)]
        p.write_text(json.dumps(d, ensure_ascii=False, indent=2))
        print(f"gravado: {p}")


def cmd_permitidos(args) -> None:
    data = _data(args.edit.resolve())
    print(json.dumps({"formato": formato_de(data), "permitidos": permitidos(data),
                      "ligados": ligados(data)}, ensure_ascii=False))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for nome in ("candidatos", "validar", "permitidos"):
        p = sub.add_parser(nome)
        p.add_argument("edit", type=Path)
        if nome == "validar":
            p.add_argument("--gravar", action="store_true")
    args = ap.parse_args()
    {"candidatos": cmd_candidatos, "validar": cmd_validar,
     "permitidos": cmd_permitidos}[args.cmd](args)


if __name__ == "__main__":
    main()

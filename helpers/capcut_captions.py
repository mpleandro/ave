#!/usr/bin/env python3
"""Lê os modelos de legenda do CapCut instalado e descreve o que cada um FAZ.

Para que serve: o usuário navega o catálogo do CapCut, baixa os modelos de que
gosta, e aponta quais quer no Avelin. Este helper transforma o pacote baixado —
que é JSON, mas JSON de motor de render, com cor em float e o visual inteiro
espremido numa string de `richText` — numa descrição legível: cor em hexa,
contorno, caixa alta, itálico, fundo, e o COMPORTAMENTO (palavra a palavra?
quantas linhas? realça palavra-chave?).

O QUE É COPIADO E O QUE NÃO É, porque a distinção importa:
  · COPIADO: os PARÂMETROS — tamanho, cor, largura de contorno, cantos, tempo
    de animação. Número medido de um arquivo do próprio usuário, na máquina
    dele. É a mesma leitura que um editor faz olhando a tela, só que exata.
  · NÃO COPIADO: os arquivos de FONTE proprietários do CapCut (as `ZY*`) e o
    JavaScript de animação deles. A fonte é licenciada para aquele produto e o
    JS é código de terceiro. O look é reconstruído com as nossas famílias (o
    catálogo do Google + as instaladas na máquina) e a nossa animação em CSS.

Uso:
    uv run python helpers/capcut_captions.py                 # lista os modelos
    uv run python helpers/capcut_captions.py --id 7577…      # um, detalhado
    uv run python helpers/capcut_captions.py --novos 20      # os últimos baixados
    uv run python helpers/capcut_captions.py --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# O CapCut do macOS guarda os efeitos baixados aqui. O caminho passa pelo
# container do app, e não pela pasta `~/Movies/CapCut` que aparece no Finder —
# essa é um atalho e não contém o cache de efeitos.
CACHE = (Path.home() / "Library/Containers/com.lemon.lvoverseas/Data/Movies"
         / "CapCut/User Data/Cache/effect")


def _hex(c) -> str:
    """Cor do CapCut (floats 0–1, às vezes com alfa) → hexadecimal."""
    if not isinstance(c, (list, tuple)) or len(c) < 3:
        return ""
    return "#" + "".join(f"{max(0, min(255, round(float(x) * 255))):02X}" for x in c[:3])


def _alpha(c) -> float:
    return round(float(c[3]), 3) if isinstance(c, (list, tuple)) and len(c) > 3 else 1.0


def parse_rich(rt: str) -> dict:
    """O `richText` é o visual inteiro numa string de marcação própria.

    Vale mais que os campos soltos ao lado dele: é o que o motor REALMENTE
    aplica, e alguns campos do `text_params` ficam com valor de fábrica mesmo
    quando o modelo pinta outra coisa.
    """
    out: dict = {}
    m = re.search(r"<outline color=\(([\d.,\s]+)\)\s*width=([\d.]+)", rt or "")
    if m:
        out["contorno"] = _hex([float(x) for x in m.group(1).split(",")])
        out["contornoLargura"] = float(m.group(2))
    m = re.search(r"<color=\(([\d.,\s]+)\)", rt or "")
    if m:
        out["cor"] = _hex([float(x) for x in m.group(1).split(",")])
    m = re.search(r"<size=([\d.]+)", rt or "")
    if m:
        out["tamanho"] = float(m.group(1))
    # A SOMBRA é uma tag separada, e vários modelos usam SÓ ela (sem contorno).
    # Sem ler isto, um modelo de sombra projetada saía descrito como "texto
    # branco e nada mais" — que é o oposto do que ele parece na tela.
    m = re.search(r"<shadow color=\(([\d.,\s-]+)\)\s*offset=\(([\d.,\s-]+)\)"
                  r"(?:\s*diffuse=([\d.-]+))?(?:\s*angle=([\d.-]+))?", rt or "")
    if m:
        cor = [float(x) for x in m.group(1).split(",")]
        out["sombra"] = _hex(cor)
        out["sombraAlfa"] = _alpha(cor)
        out["sombraOffset"] = [round(float(x), 4) for x in m.group(2).split(",")]
        if m.group(3):
            out["sombraDifusao"] = float(m.group(3))
        if m.group(4):
            out["sombraAngulo"] = float(m.group(4))
    m = re.search(r'<font id="([^"]*)"', rt or "")
    if m and m.group(1):
        out["fonteId"] = m.group(1)
    out["negrito"] = "<b>" in (rt or "")
    return out


def ler(pkg: Path) -> dict | None:
    """Um pacote de modelo → descrição. `None` se não for modelo de texto."""
    conteudo = pkg / "content.json"
    if not conteudo.is_file():
        return None
    try:
        d = json.loads(conteudo.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    filhos = d.get("children") or []
    if not filhos:
        return None
    c = filhos[0]
    tp = c.get("text_params") or {}
    cp = c.get("caption_params") or {}
    anims = c.get("anims") or []
    rich = parse_rich(tp.get("richText", ""))

    info = {
        "id": pkg.parent.name,
        "pasta": str(pkg),
        # sem `<color=>` no richText o preenchimento é o PADRÃO (branco) — e
        # dizer "?" fazia a lista parecer ilegível quando na verdade é branco
        "cor": rich.get("cor") or _hex(tp.get("textColor")) or "#FFFFFF",
        "corPadrao": not rich.get("cor"),
        "sombra": rich.get("sombra"),
        "sombraAlfa": rich.get("sombraAlfa"),
        "sombraOffset": rich.get("sombraOffset"),
        "sombraAngulo": rich.get("sombraAngulo"),
        "tamanho": rich.get("tamanho"),
        "negrito": rich.get("negrito") or bool(tp.get("boldValue")),
        "contorno": rich.get("contorno"),
        "contornoLargura": rich.get("contornoLargura"),
        "italicoGraus": tp.get("italicDegree") or 0,
        "caixaAlta": tp.get("capital") == "upper",
        "entreletras": tp.get("letterSpacing") or 0,
        "entrelinhas": tp.get("lineSpacing") or 0,
        "fonteId": rich.get("fonteId"),
        # o "canvas" é a tarja/caixa atrás do texto
        "temTarja": bool(tp.get("canvas")),
        "tarjaCor": _hex(tp.get("canvasColor")) if tp.get("canvas") else None,
        "tarjaAlfa": _alpha(tp.get("canvasColor")) if tp.get("canvas") else None,
        "tarjaCantos": tp.get("canvasRoundRadiusScale") if tp.get("canvasRoundCorner") else 0,
        # comportamento da legenda — é isto que separa karaokê de bloco estático
        "unidade": cp.get("unit_type"),           # "word" = palavra a palavra
        "linhasPorTela": cp.get("max_lines_per_page"),
        "palavrasPorLinha": cp.get("max_units_per_line") or None,
        "realcaPalavraChave": bool(cp.get("enable_keyword")),
        "animacao": (anims[0].get("anim_type") if anims else None),
        "animacaoDuracao": (anims[0].get("duration") if anims else None),
    }
    return info


def nome_do_draft(effect_id: str) -> str | None:
    """O nome legível do modelo, que só existe nos PROJETOS.

    O pacote baixado não guarda o nome que aparece no catálogo — ele vive no
    `draft_info.json` de quem aplicou o modelo. Sem isto a lista sai só com
    números, e apontar "quero esse" fica impossível.
    """
    base = Path.home() / "Movies/CapCut/User Data/Projects/com.lveditor.draft"
    if not base.is_dir():
        return None
    for d in base.glob("*/draft_info.json"):
        try:
            j = json.loads(d.read_text())
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
        for t in (j.get("materials", {}).get("text_templates") or []):
            if str(t.get("effect_id")) == str(effect_id) and t.get("name"):
                return t["name"]
    return None


def varrer() -> list[dict]:
    """Todo recurso de texto no cache, dos TRÊS tipos, do mais novo ao mais velho."""
    if not CACHE.is_dir():
        return []
    achados = []
    for d in sorted(CACHE.iterdir()):
        if not d.is_dir():
            continue
        try:
            tipo, alvo = classificar(d)
        except OSError:
            continue
        if tipo == "outro" or alvo is None:
            continue
        item: dict = {"id": d.name, "tipo": tipo, "pasta": str(alvo.parent)}
        if tipo == "modelo":
            info = ler(alvo.parent)
            if not info:
                continue
            item.update(info)
            item["tipo"] = "modelo"
        elif tipo == "animacao":
            item["faixas"] = parse_ae(alvo)
        elif tipo == "estilo":
            item.update(parse_style(alvo))
        try:
            item["baixadoEm"] = alvo.stat().st_mtime
        except OSError:
            item["baixadoEm"] = 0
        item["id"] = d.name
        achados.append(item)
    achados.sort(key=lambda x: x["baixadoEm"], reverse=True)
    return achados


def descreve(i: dict) -> str:
    """Uma linha em português dizendo o que o modelo É."""
    bits = []
    if i["unidade"] == "word":
        bits.append("palavra a palavra (karaokê)")
    elif i["linhasPorTela"]:
        bits.append(f"{i['linhasPorTela']} linha(s) por tela")
    if i["realcaPalavraChave"]:
        bits.append("realça palavra-chave")
    if i["caixaAlta"]:
        bits.append("CAIXA ALTA")
    if i["negrito"]:
        bits.append("negrito")
    if i["italicoGraus"]:
        bits.append(f"itálico {i['italicoGraus']}°")
    if i["contorno"]:
        bits.append(f"contorno {i['contorno']} ({i['contornoLargura']})")
    if i["temTarja"]:
        bits.append(f"tarja {i['tarjaCor']}")
    if i.get("sombra"):
        bits.append(f"sombra {i['sombra']} @{i.get('sombraAngulo', 0)}°")
    if i["animacao"]:
        bits.append(f"anim {i['animacao']} {i['animacaoDuracao']}s")
    return " · ".join(bits) or "sem parâmetros legíveis"


# ==========================================================================
# OS OUTROS DOIS TIPOS DE RECURSO
# ==========================================================================
# O catálogo do CapCut mistura três coisas que o usuário vê como "legenda", e
# elas moram em arquivos diferentes:
#   · MODELO de texto      content.json   → o look completo + comportamento
#   · ANIMAÇÃO de legenda  AEData.lua     → keyframes no formato do After Effects
#   · EFEITO de estilo     effectStyle.json → preenchimento, sombras, contornos
# Ler só o primeiro deixava de fora justamente o que dá vida à legenda.


def _grupos(txt: str) -> list[str]:
    """Os `{...}` de PRIMEIRO nível de um trecho, por balanceamento.

    Por balanceamento e não por regex porque os trechos NÃO têm aridade fixa:
    um `ADBE_Scale_0_1` traz 12 alças e dois grupos de valores; um
    `ADBE_Position_0_0` traz 4 alças, QUATRO grupos de valores e mais dois
    campos no fim. Uma regex com a forma de um deles devolve zero no outro — e
    o sintoma é "keyframes não legíveis" num arquivo que está perfeitamente
    legível.
    """
    out, nivel, ini = [], 0, None
    for i, ch in enumerate(txt):
        if ch == "{":
            if nivel == 0:
                ini = i + 1
            nivel += 1
        elif ch == "}":
            nivel -= 1
            if nivel == 0 and ini is not None:
                out.append(txt[ini:i])
                ini = None
    return out


def _nums(txt: str) -> list[float]:
    return [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?(?:e-?\d+)?", txt)]


def parse_ae(path: Path) -> dict:
    """Keyframes do After Effects (`AEData.lua`) → tempos, valores e bezier.

    O formato é posicional e sem documentação. Cada trecho começa com as ALÇAS
    da curva, depois os QUADROS (início, fim), depois os valores.

    As alças vêm em quantidade variável, e a leitura muda com ela:
      · 12 números = QUATRO pontos de controle × TRÊS eixos, guardados por
        ponto. O bezier de um eixo se lê em COLUNA — `(p1[eixo], p2[eixo],
        p3[eixo], p4[eixo])`. Ler em linha produz curvas sem sentido que
        parecem plausíveis, que é o pior tipo de erro aqui.
      · 4 números = o bezier já pronto, `(x1, y1, x2, y2)`.
    """
    txt = path.read_text(errors="ignore")
    faixas: dict[str, list] = {}
    for m in re.finditer(r'\["([A-Za-z_0-9]+)"\]\s*=\s*', txt):
        nome = m.group(1)
        resto = txt[m.end():]
        corpo = _grupos(resto)
        if not corpo:
            continue
        trechos = []
        for seg in _grupos(corpo[0]):
            partes = _grupos(seg)
            if len(partes) < 3:
                continue
            alcas = _nums(partes[0])
            quadros = _nums(partes[1])
            valores = [_nums(g) for g in _grupos(partes[2])] or [_nums(partes[2])]
            if len(quadros) < 2 or len(valores) < 2:
                continue
            if len(alcas) >= 12:
                bez = [alcas[0], alcas[3], alcas[6], alcas[9]]
            elif len(alcas) >= 4:
                bez = alcas[:4]
            else:
                bez = [0.25, 0.1, 0.25, 1.0]   # o padrão do AE
            trechos.append({"quadros": quadros[:2],
                            "bezier": [round(x, 4) for x in bez],
                            "de": valores[0], "para": valores[1]})
        if trechos:
            faixas[nome] = trechos
    return faixas


# O AE numera as propriedades por camada (`ADBE_Position_1_0_1`), então o
# rótulo sai do PREFIXO — uma tabela de nomes exatos erraria em toda camada
# que não fosse a primeira.
AE_PREFIXOS = [("ADBE_Scale", "escala"), ("ADBE_Opacity", "opacidade"),
               ("ADBE_Position", "posição"), ("ADBE_Rotate", "rotação"),
               ("ADBE_Anchor", "âncora")]


def ae_nome(prop: str) -> str:
    for pre, nome in AE_PREFIXOS:
        if prop.startswith(pre):
            return nome
    return prop


def descreve_anim(faixas: dict, fps: float = 30.0) -> list[str]:
    linhas = []
    for prop, trechos in faixas.items():
        nome = ae_nome(prop)
        for t in trechos:
            t0, t1 = [q / fps * 1000 for q in t["quadros"][:2]]
            de = t["de"][0] if t["de"] else "?"
            para = t["para"][0] if t["para"] else "?"
            b = ", ".join(f"{x:g}" for x in t["bezier"])
            linhas.append(f"{nome}: {t0:.0f}→{t1:.0f}ms  {de:g}→{para:g}  cubic-bezier({b})")
    return linhas


def parse_style(path: Path) -> dict:
    """`effectStyle.json` — preenchimento, sombras e contornos de um efeito."""
    try:
        d = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict = {}
    fill = (d.get("fill") or {}).get("content") or {}
    tipo = fill.get("render_type")
    if tipo == "gradient":
        g = fill.get("gradient") or {}
        out["preenchimento"] = "degradê " + " → ".join(_hex(c) for c in (g.get("color") or []))
        out["degradeAngulo"] = g.get("angle")
    elif fill.get("solid"):
        out["preenchimento"] = _hex(fill["solid"].get("color"))
    sombras = []
    for sh in (d.get("shadows") or []):
        c = ((sh.get("content") or {}).get("solid") or {}).get("color")
        sombras.append({"cor": _hex(c), "alfa": round(float(sh.get("alpha", 1)), 3),
                        "angulo": round(float(sh.get("angle", 0)), 1),
                        "distancia": sh.get("distance"), "suavizacao": sh.get("smoothing")})
    if sombras:
        out["sombras"] = sombras
    contornos = []
    for st in (d.get("strokes") or []):
        c = ((st.get("content") or {}).get("solid") or {}).get("color")
        contornos.append({"cor": _hex(c), "largura": st.get("width")})
    if contornos:
        out["contornos"] = contornos
    return out


def classificar(pasta: Path) -> tuple[str, Path | None]:
    """Que TIPO de recurso é este pacote."""
    for sub in [pasta, *[p for p in pasta.iterdir() if p.is_dir()]] if pasta.is_dir() else []:
        if (sub / "effectStyle.json").is_file():
            return "estilo", sub / "effectStyle.json"
        ae = sub / "modules" / "AEData.lua"
        if ae.is_file():
            return "animacao", ae
        if (sub / "content.json").is_file():
            return "modelo", sub / "content.json"
    return "outro", None


def main() -> int:
    ap = argparse.ArgumentParser(description="Modelos de legenda do CapCut instalado")
    ap.add_argument("--id", default="", help="detalha um modelo pelo id do efeito")
    ap.add_argument("--novos", type=int, default=0, help="só os N últimos baixados")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not CACHE.is_dir():
        print(f"cache de efeitos do CapCut não encontrado em {CACHE}", file=sys.stderr)
        return 1
    itens = varrer()
    if args.id:
        itens = [i for i in itens if i["id"] == args.id]
    elif args.novos:
        itens = itens[:args.novos]

    if args.json:
        print(json.dumps(itens, ensure_ascii=False, indent=2))
        return 0

    rot = {"modelo": "MODELO", "animacao": "ANIMAÇÃO", "estilo": "ESTILO"}
    print(f"{len(itens)} recurso(s) de legenda em {CACHE}\n")
    for i in itens:
        nome = nome_do_draft(i["id"]) or ""
        cab = f"[{rot.get(i['tipo'], i['tipo'])}] {i['id']}"
        print(f"{cab}  {nome or '(sem nome — aplique num projeto do CapCut para nomear)'}")
        if i["tipo"] == "modelo":
            marca = " (padrão)" if i.get("corPadrao") else ""
            print(f"   cor {i['cor']}{marca} · corpo {i['tamanho'] or '?'}")
            print(f"   {descreve(i)}")
        elif i["tipo"] == "animacao":
            for l in descreve_anim(i.get("faixas") or {}):
                print(f"   {l}")
            if not i.get("faixas"):
                print("   (keyframes não legíveis neste pacote)")
        elif i["tipo"] == "estilo":
            if i.get("preenchimento"):
                ang = f" @{i['degradeAngulo']:g}°" if i.get("degradeAngulo") is not None else ""
                print(f"   preenchimento: {i['preenchimento']}{ang}")
            for sh in (i.get("sombras") or [])[:3]:
                print(f"   sombra {sh['cor']} alfa {sh['alfa']} ângulo {sh['angulo']}°")
            for st in (i.get("contornos") or [])[:3]:
                print(f"   contorno {st['cor']} largura {st['largura']}")
        if args.id:
            print(f"   pasta: {i['pasta']}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

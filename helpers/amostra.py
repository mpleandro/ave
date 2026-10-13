#!/usr/bin/env python3
"""A AMOSTRA DA FASE 2 — 8 a 15 segundos renderizados antes do vídeo inteiro.

O render da Fase 2 é o passo caro desta skill (quadro a quadro, minutos), e até
aqui o primeiro lugar em que o usuário via o estilo aplicado de verdade era o
vídeo COMPLETO. A aba Estilo mostra legenda e headline ao vivo, mas não mostra o
que é sob medida — gráficos em `compositions/`, tela dividida, B-roll, a
Animação em Texto e a 3D — e é exatamente isso que mais custa refazer.

Então a Fase 2 compõe o vídeo inteiro (a composição é barata) e renderiza só uma
janela representativa. Três peças:

  1. `escolher_janela()` — a janela que mais mostra do estilo: pontua cada clipe
     da composição pelo que ele É (gráfico sob medida > inserção/tela dividida >
     efeito sonoro > linha de legenda), soma a variedade de tipos e encaixa as
     bordas em fim/começo de fala. Nunca corta um gráfico sob medida ao meio
     pela ESQUERDA: a timeline interna dele começaria do zero no meio da cena.

  2. `gerar_html()` — o `amostra.html`, a mesma composição deslocada para a
     janela. O renderizador não tem "renderize de S a E"; os clipes são
     posicionados pelo `data-start` e a animação pela timeline GSAP. Os dois
     precisam andar juntos:
       * no ARQUIVO os `data-start` já vêm deslocados (é o que o renderizador e
         o motor de mídia leem) e a mídia que começa antes da janela ganha
         `data-media-start`;
       * mas os construtores de estilo (`karaoke.js`, `split.js`…) leem o
         `data-start` para montar tweens em tempo ABSOLUTO — então um script
         devolve os tempos originais só enquanto eles montam a timeline, e a
         timeline é embrulhada num `tweenFromTo(S, E)`. Tempo 0 da amostra =
         tempo S do vídeo, nos dois relógios.

  3. `costurar()` — a amostra colada sobre o corte limpo, na MESMA posição. O
     editor mede tudo pela linha do tempo do vídeo inteiro; um arquivo de 12s
     no player faria o ponteiro, as marcações e a legenda da prévia mentirem.
     Fora da janela o espectador vê o corte; dentro, a Fase 2.

Uso direto (o normal é o `phase2.py` chamar):

    amostra.py <proj_hyperframes> --janela          # só diz qual janela escolheria
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

MINIMO, ALVO, MAXIMO = 8.0, 12.0, 15.0
# Abaixo disto o vídeo inteiro É a amostra: renderizar 12s de um corte de 18s
# economiza quase nada e obriga o usuário a aprovar duas vezes.
VALE_A_PENA = 20.0

_TAG = re.compile(r"<(\w+)(\s[^>]*?\bdata-start=\"[^\"]*\"[^>]*)>", re.S)
_ATTR = lambda nome: re.compile(r'\b' + re.escape(nome) + r'="([^"]*)"')


def _attr(attrs: str, nome: str) -> str | None:
    m = _ATTR(nome).search(attrs)
    return m.group(1) if m else None


def _set(attrs: str, nome: str, valor: str) -> str:
    if _ATTR(nome).search(attrs):
        return _ATTR(nome).sub(f'{nome}="{valor}"', attrs, count=1)
    return f'{attrs} {nome}="{valor}"'


def _corpo(html: str) -> tuple[int, int]:
    """Faixa do HTML onde moram os clipes: do <body> ao script da timeline.

    Os scripts podem conter `data-start="` em string; reescrever ali dentro
    quebraria o JS sem o `check` perceber."""
    ini = html.find("<body")
    fim = html.find("window.__timelines")
    fim = html.rfind("<script", 0, fim) if fim > 0 else len(html)
    return max(ini, 0), fim


def clipes(html: str) -> list[dict]:
    a, b = _corpo(html)
    out = []
    for m in _TAG.finditer(html, a, b):
        tag, attrs = m.group(1).lower(), m.group(2)
        try:
            s = float(_attr(attrs, "data-start") or 0)
            d = float(_attr(attrs, "data-duration") or 0)
        except ValueError:
            continue
        out.append({"tag": tag, "attrs": attrs, "start": s, "end": s + d,
                    "id": _attr(attrs, "id") or "", "cls": _attr(attrs, "class") or "",
                    "sub": _attr(attrs, "data-composition-src"),
                    "root": _attr(attrs, "id") == "root"})
    return out


def _tipo(c: dict, total: float) -> str | None:
    if c["root"]:
        return None
    if c["sub"]:
        return "grafico"
    if c["tag"] == "audio":
        return None if c["id"].startswith("a-roll") or (c["end"] - c["start"]) >= 0.9 * total else "sfx"
    if c["tag"] == "video" and (c["end"] - c["start"]) >= 0.9 * total:
        return None                       # o próprio corte
    if "cap" in c["cls"] or "cue" in c["cls"]:
        return "legenda"
    if (c["end"] - c["start"]) >= 0.9 * total:
        return None                       # camada que cobre o vídeo todo não distingue janela
    # a CLASSE nomeia o que o espectador vê (ave-split-win, ave-insert, hl-…)
    nome = (c["cls"].split() or [c["tag"]])[0]
    return "visual:" + nome


PESO = {"grafico": 6.0, "sfx": 0.3, "legenda": 0.15}


def escolher_janela(html: str, total: float, minimo: float = MINIMO,
                    alvo: float = ALVO, maximo: float = MAXIMO) -> tuple[float, float, str]:
    cs = [dict(c, tipo=_tipo(c, total)) for c in clipes(html)]
    cs = [c for c in cs if c["tipo"]]
    graficos = [c for c in cs if c["tipo"] == "grafico"]
    falas = sorted((c["start"], c["end"]) for c in cs if c["tipo"] == "legenda")

    # bordas candidatas: começo e fim de linha de legenda (= de fala) e o começo
    # de cada clipe visual. Sem legenda, uma grade de meio segundo.
    starts = {0.0} | {round(s, 3) for s, _ in falas} \
        | {round(max(0.0, c["start"] - 0.4), 3) for c in cs if c["tipo"] != "legenda"}
    ends = {round(e, 3) for _, e in falas} | {round(total, 3)}
    if not falas:
        grade = [i * 0.5 for i in range(int(total / 0.5) + 1)]
        starts |= set(grade)
        ends |= set(grade)
    starts = sorted(s for s in starts if s < total - minimo + 1e-6) or [0.0]
    ends = sorted(ends)

    melhor = None
    for s in starts:
        # gráfico sob medida cortado pela esquerda começaria a cena do zero
        if any(g["start"] < s - 1e-3 < g["end"] for g in graficos):
            continue
        for e in ends:
            if e - s < minimo - 1e-6:
                continue
            if e - s > maximo + 1e-6:
                break
            pts, tipos = 0.0, set()
            for c in cs:
                ov = min(e, c["end"]) - max(s, c["start"])
                if ov <= 0:
                    continue
                frac = ov / max(c["end"] - c["start"], 1e-3)
                pts += PESO.get(c["tipo"], 3.0) * frac
                if c["tipo"] != "legenda":
                    tipos.add(c["tipo"])
            pts += 2.0 * len(tipos) - 0.05 * abs((e - s) - alvo)
            if melhor is None or pts > melhor[0] + 1e-9:
                melhor = (pts, s, e, sorted(tipos))
    if melhor is None:
        e = min(total, alvo)
        return 0.0, e, "início do vídeo (não achei janela melhor)"
    _, s, e, tipos = melhor
    nomes = [t.split(":", 1)[-1] for t in tipos]
    motivo = ("mostra " + ", ".join(nomes)) if nomes else "trecho de fala com legenda"
    return s, e, motivo


def alinhar(S: float, E: float, fps: float) -> tuple[float, float]:
    """Janela na grade de quadros. Medido: começar em 26,85s a 30fps (quadro
    805,5) deixava a timeline meio quadro à frente do vídeo — a câmera dinâmica
    saía levemente deslocada em relação ao render completo."""
    return round(S * fps) / fps, round(E * fps) / fps


def fps_de(html: str, padrao: float = 30.0) -> float:
    m = re.search(r'data-fps="([0-9.]+)"', html)
    return float(m.group(1)) if m else padrao


def gerar_html(html: str, S: float, E: float) -> str:
    D = E - S
    a, b = _corpo(html)
    partes, cursor, raiz = [], a, "main"

    def novo(m: re.Match) -> str:
        nonlocal raiz
        tag, attrs = m.group(1), m.group(2)
        s = float(_attr(attrs, "data-start") or 0)
        d = float(_attr(attrs, "data-duration") or 0)
        if _attr(attrs, "id") == "root":
            raiz = _attr(attrs, "data-composition-id") or raiz
            return f"<{tag}{_set(attrs, 'data-duration', f'{D:.3f}')}>"
        ns, ne = s - S, s + d - S
        midia = tag.lower() in ("video", "audio")
        if ne <= 0 or ns >= D:
            # fora da janela. Mídia sai do ar (o motor de áudio a mixaria);
            # o resto continua no DOM porque os construtores o procuram por
            # id, e um getElementById nulo derruba a timeline inteira.
            # Antes OU depois, vai para DEPOIS do fim: o runtime não esconde
            # clipe de `data-start` negativo — medido, as legendas que já
            # tinham passado apareceram todas empilhadas no primeiro quadro.
            if midia:
                # mídia fora da janela SAI da amostra: empurrada para depois do
                # fim, o extrator ainda exige quadros dela e aborta o render
                # (medido: o recorte da cabeça de 0–16s numa amostra de 22–35s,
                # "captured 0 of expected 489 frames")
                return f"<{tag}{_set(attrs, 'data-ave-fora', '1')}>"
            ns, ne = D + 1.0, D + 1.0 + d
        elif ns < 0:
            if midia:
                ms = float(_attr(attrs, "data-media-start") or 0)
                attrs = _set(attrs, "data-media-start", f"{ms - ns:.3f}")
            ns = 0.0
        ne = min(ne, D) if ns < D else ne
        if not midia:
            attrs = _set(attrs, "data-ave-t0", f"{s:.3f}")
            attrs = _set(attrs, "data-ave-d0", f"{d:.3f}")
        attrs = _set(attrs, "data-start", f"{ns:.3f}")
        attrs = _set(attrs, "data-duration", f"{max(ne - ns, 0.001):.3f}")
        return f"<{tag}{attrs}>"

    for m in _TAG.finditer(html, a, b):
        partes.append(html[cursor:m.start()])
        partes.append(novo(m))
        cursor = m.end()
    corpo = "".join(partes) + html[cursor:b]
    corpo = re.sub(r'<(video|audio)\b[^>]*data-ave-fora="1"[^>]*>\s*</\1>', "", corpo)

    antes = """<script>
  /* AMOSTRA: os construtores leem data-start em tempo ABSOLUTO do vídeo
     inteiro. Devolve os tempos originais só enquanto eles montam a timeline. */
  document.querySelectorAll('[data-ave-t0]').forEach(function (el) {
    el.setAttribute('data-ave-ts', el.getAttribute('data-start'));
    el.setAttribute('data-ave-ds', el.getAttribute('data-duration'));
    el.setAttribute('data-start', el.getAttribute('data-ave-t0'));
    el.setAttribute('data-duration', el.getAttribute('data-ave-d0'));
  });
</script>
"""
    resto = html[b:]
    fecha = resto.find("</script>") + len("</script>")
    depois = f"""
<script>
  /* AMOSTRA: tempo 0 daqui = tempo {S:.3f} do vídeo inteiro. */
  (function () {{
    var tl = window.__timelines["{raiz}"];
    var o = gsap.timeline({{ paused: true }});
    o.add(tl.tweenFromTo({S:.3f}, {E:.3f}, {{ ease: 'none' }}), 0);
    window.__timelines["{raiz}"] = o;
    document.querySelectorAll('[data-ave-ts]').forEach(function (el) {{
      el.setAttribute('data-start', el.getAttribute('data-ave-ts'));
      el.setAttribute('data-duration', el.getAttribute('data-ave-ds'));
    }});
  }})();
</script>"""
    return html[:a] + corpo + antes + resto[:fecha] + depois + resto[fecha:]


def costurar(corte: Path, amostra: Path, S: float, E: float, out: Path) -> None:
    """Cola a amostra sobre o corte limpo, na posição S, imagem e som."""
    # O som é EMENDADO, não mixado: `volume=enable` decide por bloco de áudio
    # (~21ms), e nesse bloco corte e amostra tocavam juntos — medido, pico 1,0
    # cravado na emenda. `atrim` é exato na amostra; 10ms de fade apagam o clique.
    D = E - S
    f = 0.01
    fc = (f"[1:v]setpts=PTS-STARTPTS+{S}/TB[s];"
          f"[0:v][s]overlay=enable='between(t,{S},{E})':eof_action=pass[v];"
          f"[0:a]atrim=0:{S},asetpts=PTS-STARTPTS,afade=t=out:st={max(S - f, 0)}:d={f}[a0];"
          f"[1:a]atrim=0:{D},asetpts=PTS-STARTPTS,afade=t=in:d={f},"
          f"afade=t=out:st={max(D - f, 0)}:d={f}[a1];"
          f"[0:a]atrim={E},asetpts=PTS-STARTPTS,afade=t=in:d={f}[a2];"
          f"[a0][a1][a2]concat=n=3:v=0:a=1[a]")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(corte), "-i", str(amostra),
                    "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                    "-movflags", "+faststart", str(out)], check=True)


def duracao(html: str) -> float:
    for c in clipes(html):
        if c["root"]:
            return c["end"]
    return max((c["end"] for c in clipes(html)), default=0.0)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("proj", type=Path, help="<edit>/hyperframes")
    ap.add_argument("--janela", action="store_true", help="só mostra a janela escolhida")
    ap.add_argument("--gerar", metavar="S-E", help="escreve amostra.html para essa janela")
    args = ap.parse_args()
    html = (args.proj / "index.html").read_text()
    total = duracao(html)
    if args.gerar:
        S, E = (float(x) for x in args.gerar.split("-"))
        motivo = "janela pedida"
    else:
        S, E, motivo = escolher_janela(html, total)
    S, E = alinhar(S, E, fps_de(html))
    print(json.dumps({"inicio": S, "fim": E, "motivo": motivo, "total": total},
                     ensure_ascii=False))
    if not args.janela:
        (args.proj / "amostra.html").write_text(gerar_html(html, S, E))


if __name__ == "__main__":
    main()

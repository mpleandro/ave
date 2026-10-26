"""A legenda de um corte — SEPARADA do vídeo.

O download padrão é o corte limpo. A legenda sai como arquivo à parte (.srt,
para Avelin, CapCut, Premiere ou qualquer editor) e, só quando pedido, também
queimada num segundo MP4. Quem vai finalizar a edição em outro lugar leva o
vídeo limpo e escolhe a estrutura de legenda lá.

TEXTO e TEMPO vêm de fontes diferentes, de propósito:

- o TEXTO é o do transcrito da fonte (Groq), que acerta o vocabulário: o
  Whisper local ouviu "no rios você não vende" onde o Groq tem "No Reels";
- o TEMPO é do Whisper local rodando no áudio do PRÓPRIO corte, porque os
  tempos de palavra do Groq chegaram a estar 0,27s adiantados — na legenda
  isso é a palavra acendendo antes de ser dita.

As duas sequências são casadas palavra a palavra (difflib); palavra do Groq
sem par herda o tempo por interpolação entre as vizinhas casadas.

O karaokê queimado imita o `karaoke` do Avelin (assets/styles/karaoke.css):
Poppins Black 76px, até 3 palavras numa linha, 430px acima da base — dentro da
área segura do vertical (area_segura.py) —, a palavra dita na cor de destaque.
O tamanho no config é 104, não 76: o libass mede a fonte pela altura da LINHA
(ascendente + descendente, ~1,4 em na Poppins) e o CSS pelo em — 80 no .ass
saiu do tamanho de ~57px de CSS.
"""
from __future__ import annotations

import difflib
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from derivado import derivado  # noqa: E402
from hook_finder import norm  # noqa: E402

MODELO = "mlx-community/whisper-large-v3-turbo"
FINAL = ".?!"

# PALAVRA DE FORÇA: número, dinheiro, absoluto, conflito — o que o olho deve
# pegar mesmo fora da vez dela (a ideia do SupoClip, com léxico em português).
# Sai numa cor SECUNDÁRIA, para não competir com a palavra que está sendo dita.
FORCA = re.compile(
    r"^(\d[\d.,%]*|mil|milh[aã]o|milh[oõ]es|bilh[aã]o|cem|dez|metade|dobro|"
    r"nunca|ningu[eé]m|sempre|tudo|nada|segredo|erro|errado|errada|verdade|mentira|"
    r"dinheiro|reais|rico|pobre|gr[aá]tis|vender|vende|venda|viral|viralizar|bombar|"
    r"pare|parem|chato|chatos|chata|pior|melhor|maior|problema|medo|raiva|"
    r"proibido|nunca|jamais|absurdo|morre|mata)$", re.I)


def forca(w: str) -> bool:
    return bool(FORCA.match(re.sub(r"[^\w%]", "", w)))


def _tok(w: str) -> str:
    return norm(w).replace("?", "").strip()


def ouvir(video: Path, a: float, b: float) -> list[dict]:
    """Palavras do trecho [a, b] da fonte, com tempo relativo a `a`."""
    # sem a escuta local (Windows, Mac Intel): a legenda fica com os tempos do
    # transcrito — `alinhar` sem nada ouvido devolve esses. Fora do cache: um
    # "não ouvi" guardado sobreviveria à instalação da escuta.
    try:
        import mlx_whisper  # noqa: F401, PLC0415
    except ImportError:
        return []

    def medir():
        import mlx_whisper  # noqa: PLC0415
        with tempfile.TemporaryDirectory() as d:
            wav = Path(d) / "a.wav"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{a:.3f}", "-i", str(video),
                            "-t", f"{b - a:.3f}", "-vn", "-ac", "1", "-ar", "16000", str(wav)],
                           check=True)
            r = mlx_whisper.transcribe(str(wav), path_or_hf_repo=MODELO, language="pt",
                                       word_timestamps=True, condition_on_previous_text=False)
        return [{"w": w["word"].strip(), "s": round(float(w["start"]), 3),
                 "e": round(float(w["end"]), 3)}
                for s in r.get("segments", []) for w in s.get("words", []) if w["word"].strip()]
    return derivado("legenda_ouvida", [video], {"a": round(a, 3), "b": round(b, 3),
                                                 "modelo": MODELO}, "1", medir)


def alinhar(texto: list[dict], ouvido: list[dict], dur: float) -> list[dict]:
    """Palavras do transcrito (`texto`, tempos da fonte) com o tempo do `ouvido`
    (relativo ao corte). Sem casamento suficiente, mantém o tempo do texto."""
    if not texto:
        return []
    g, o = [_tok(w["w"]) for w in texto], [_tok(w["w"]) for w in ouvido]
    sm = difflib.SequenceMatcher(None, g, o, autojunk=False)
    par: dict[int, int] = {}
    for bloco in sm.get_matching_blocks():
        for k in range(bloco.size):
            par[bloco.a + k] = bloco.b + k
    if len(par) < 0.4 * len(texto):
        t0 = texto[0]["s"]
        return [{"w": w["w"], "s": max(0.0, w["s"] - t0), "e": max(0.0, w["e"] - t0)} for w in texto]

    out: list[dict | None] = [None] * len(texto)
    for i, j in par.items():
        out[i] = {"w": texto[i]["w"], "s": ouvido[j]["s"], "e": ouvido[j]["e"]}
    # buracos: interpola entre as âncoras vizinhas, proporcional ao tamanho
    i = 0
    while i < len(out):
        if out[i] is not None:
            i += 1
            continue
        k = i
        while k < len(out) and out[k] is None:
            k += 1
        ini = out[i - 1]["e"] if i > 0 else 0.0
        fim = out[k]["s"] if k < len(out) else dur
        pesos = [max(1, len(texto[x]["w"])) for x in range(i, k)]
        passo = max(0.0, fim - ini) / sum(pesos)
        t = ini
        for x, p in zip(range(i, k), pesos):
            out[x] = {"w": texto[x]["w"], "s": round(t, 3), "e": round(t + p * passo, 3)}
            t += p * passo
        i = k
    return out  # type: ignore[return-value]


def fecha(w: str) -> bool:
    """. ? ! fecham a frase; reticências não — "e você... lê ele depois" é a
    mesma frase continuando, e não ganha maiúscula nem quebra de bloco."""
    p = w.rstrip("\"')»”")
    return p[-1:] in FINAL and not p.endswith(("...", "…"))


def capitalizar(ws: list[dict]) -> list[dict]:
    """Maiúscula no começo do corte e depois de . ? ! — o transcrito traz
    "parem de ser chatos." em minúscula quando a frase começou depois de pausa."""
    out, sobe = [], True
    for w in ws:
        txt = w["w"]
        if sobe and txt:
            txt = txt[0].upper() + txt[1:]
        out.append({**w, "w": txt})
        sobe = fecha(txt)
    return out


def agrupar(ws: list[dict], max_palavras: int, max_chars: int, pausa: float = 0.35,
            virgula_min: int = 0) -> list[list[dict]]:
    """Blocos de legenda: fecham no fim de frase, numa pausa, no limite — e na
    vírgula só quando o bloco já tem `virgula_min` caracteres (senão sobra
    "poxa," sozinho num bloco de meio segundo)."""
    grupos, cur = [], []
    for k, w in enumerate(ws):
        cur.append(w)
        texto = " ".join(x["w"] for x in cur)
        prox = ws[k + 1] if k + 1 < len(ws) else None
        fim = (fecha(w["w"])
               or (w["w"].endswith(",") and len(texto) >= virgula_min)
               or len(cur) >= max_palavras
               or (prox and len(texto) + 1 + len(prox["w"]) > max_chars)
               or (prox and prox["s"] - w["e"] > pausa))
        if fim:
            grupos.append(cur)
            cur = []
    if cur:
        grupos.append(cur)
    return grupos


def colar_curtos(grupos: list[list[dict]], max_chars: int) -> list[list[dict]]:
    """Bloco de até 2 palavras gruda no anterior quando cabe e não há pausa."""
    out: list[list[dict]] = []
    for g in grupos:
        if out and len(g) <= 2 and not fecha(out[-1][-1]["w"]) \
                and g[0]["s"] - out[-1][-1]["e"] < 0.4 \
                and len(" ".join(x["w"] for x in out[-1] + g)) <= max_chars:
            out[-1] = out[-1] + g
        else:
            out.append(g)
    return out


def _ts_srt(t: float) -> str:
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def srt(ws: list[dict], dur: float) -> str:
    """Blocos de frase, até 9 palavras / 42 caracteres — o formato que editor
    de vídeo espera (o karaokê de 3 palavras é coisa do vídeo queimado)."""
    grupos = colar_curtos(agrupar(capitalizar(ws), 9, 42, pausa=0.7, virgula_min=24), 42)
    linhas = []
    for n, g in enumerate(grupos, 1):
        prox = grupos[n][0]["s"] if n < len(grupos) else dur
        fim = min(max(g[-1]["e"], g[0]["s"] + 0.6), prox, dur)
        linhas.append(f"{n}\n{_ts_srt(g[0]['s'])} --> {_ts_srt(fim)}\n"
                      f"{' '.join(w['w'] for w in g)}\n")
    return "\n".join(linhas)


def _ts_ass(t: float) -> str:
    cs = int(round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def _cor_ass(hex_rgb: str) -> str:
    h = hex_rgb.lstrip("#")
    return f"&H00{h[4:6]}{h[2:4]}{h[0:2]}".upper()


def linhas_balanceadas(texto: str, max_chars: int) -> list[str]:
    """Quebra em linhas de tamanho parecido: entre todas as divisões em n linhas
    (n o mínimo que cabe em `max_chars`), a que deixa a linha mais longa menor.
    O título lê como bloco — nunca "churrasco" sozinho embaixo."""
    from itertools import combinations  # noqa: PLC0415
    ps = texto.split()
    n = max(1, min(len(ps), -(-len(texto) // max_chars)))
    melhor = None
    for cortes in combinations(range(1, len(ps)), n - 1):
        lim = (0, *cortes, len(ps))
        ls = [" ".join(ps[lim[i]:lim[i + 1]]) for i in range(n)]
        nota = max(len(x) for x in ls)
        if melhor is None or nota < melhor[0]:
            melhor = (nota, ls)
    return melhor[1] if melhor else [texto]


def ass(ws: list[dict], dur: float, cfg: dict, titulo: str | None = None) -> str:
    """Karaokê: um evento por palavra dita, o bloco inteiro na tela e a palavra
    da vez na cor de destaque. Sem escala na palavra ativa: num bloco
    centralizado ela empurraria as vizinhas a cada troca."""
    c = cfg["legenda"]
    grupos = agrupar(capitalizar(ws), c["max_palavras"], c["max_chars"], virgula_min=6)
    cab = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{c['fonte']},{c['tamanho']},{_cor_ass(c['cor'])},{_cor_ass(c['cor'])},&H64000000,&H8C000000,0,0,0,0,100,100,-1,0,1,3,4,2,130,130,{c['base_px']},1

Style: Titulo,{c['fonte']},{(c.get('titulo') or {}).get('tamanho', 72)},{_cor_ass(c['cor'])},{_cor_ass(c['cor'])},&H1A3A1F0B,&H00000000,0,0,0,0,100,100,-1,0,3,18,0,8,140,140,{(c.get('titulo') or {}).get('topo_px', 270)},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    eventos = []
    destaque = _cor_ass(c["destaque"])
    segunda = _cor_ass(c["destaque_secundario"])
    for n, g in enumerate(grupos):
        prox = grupos[n + 1][0]["s"] if n + 1 < len(grupos) else dur
        # o bloco fica até o próximo, se o vão for curto — piscar entre blocos cansa
        fim_bloco = prox if prox - g[-1]["e"] < 0.6 else g[-1]["e"] + 0.25
        for k, w in enumerate(g):
            ini = w["s"] if k else g[0]["s"]
            fim = g[k + 1]["s"] if k + 1 < len(g) else fim_bloco
            if fim <= ini:
                continue
            texto = " ".join(
                f"{{\\c{destaque}}}{x['w']}{{\\r}}" if x is w
                else f"{{\\c{segunda}}}{x['w']}{{\\r}}" if forca(x["w"]) else x["w"] for x in g)
            eventos.append(f"Dialogue: 0,{_ts_ass(ini)},{_ts_ass(min(fim, dur))},Cap,,0,0,0,,{texto}")
    t = c.get("titulo") or {}
    if titulo and t.get("ativo"):
        # o título do gancho no topo, logo abaixo da área segura (area_segura.py:
        # 250px de interface + folga), nos primeiros segundos — palavra de força
        # na cor de destaque
        linhas = linhas_balanceadas(titulo, t["max_chars"])
        txt = "\\N".join(" ".join(f"{{\\c{destaque}}}{w}{{\\r}}" if forca(w) else w
                                   for w in ln.split()) for ln in linhas)
        fim = min(dur, t["ate_s"])
        eventos.append(f"Dialogue: 1,{_ts_ass(0.12)},{_ts_ass(fim)},Titulo,,0,0,0,,"
                       f"{{\\fad(160,240)}}{txt}")
    return cab + "\n".join(eventos) + "\n"

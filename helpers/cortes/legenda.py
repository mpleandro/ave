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
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from derivado import derivado  # noqa: E402
from hook_finder import norm  # noqa: E402
from cortes import headline as H  # noqa: E402

MODELO = "mlx-community/whisper-large-v3-turbo"
FINAL = ".?!"
# os modelos do popup "Com legenda" (tela de cortes) — lidos também pela prévia
MODELOS = json.loads((Path(__file__).resolve().parent / "modelos_legenda.json").read_text())

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


def _cor_ass(hex_rgb: str, alfa: str = "00") -> str:
    h = hex_rgb.lstrip("#")
    return f"&H{alfa}{h[4:6]}{h[2:4]}{h[0:2]}".upper()


def _hex(v, padrao: str) -> str:
    return v.upper() if isinstance(v, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", v) else padrao


def _clarear(hex_rgb: str, k: float = 0.45) -> str:
    """A cor secundária das palavras de força: a principal puxada para o branco,
    para nunca competir com a palavra que está sendo dita."""
    h = hex_rgb.lstrip("#")
    rgb = [int(h[i:i + 2], 16) for i in (0, 2, 4)]
    return "#" + "".join(f"{round(x + (255 - x) * k):02X}" for x in rgb)


def normalizar_estilo(estilo: dict | None) -> dict:
    """As escolhas do popup completadas pelo padrão. Id desconhecido volta ao
    padrão; ids de versões anteriores viram os de agora, para o estilo salvo
    no perfil continuar abrindo: a legenda da V1 ("caixa", "serifada"…) vira
    (tipo, visual), e a headline que era (entrada, visual) vira (layout, entrada)."""
    e = {**MODELOS["padrao"], **(estilo or {})}
    antigo = MODELOS["antigos"]["legenda"].get(e["legenda"])
    if antigo and e["legenda"] not in MODELOS["legendas"]:
        e["legenda"], e["legenda_visual"] = antigo
    if e["legenda"] not in MODELOS["legendas"]:
        e["legenda"] = MODELOS["padrao"]["legenda"]
    if e["legenda_visual"] not in MODELOS["visuais_legenda"]:
        e["legenda_visual"] = MODELOS["padrao"]["legenda_visual"]
    visual = e.pop("titulo_visual", None)
    if e["titulo"] in MODELOS["antigos"]["titulo_entrada"]:
        e["entrada"] = MODELOS["antigos"]["titulo_entrada"][e["titulo"]]
        e["titulo"] = visual or MODELOS["padrao"]["titulo"]
    if e["titulo"] not in MODELOS["titulos"]:
        e["titulo"] = MODELOS["padrao"]["titulo"]
    if e["entrada"] not in MODELOS["entradas"]:
        e["entrada"] = MODELOS["padrao"]["entrada"]
    return e


def com_estilo(cfg: dict, estilo: dict | None) -> dict:
    """O config com as escolhas do popup por cima: tipo e visual da legenda,
    tipo e visual da headline, posições (px na referência 1080×1920), cor
    principal e de fundo. O que o modelo não diz fica como está no config."""
    e = normalizar_estilo(estilo)
    tipo, vis = MODELOS["legendas"][e["legenda"]], MODELOS["visuais_legenda"][e["legenda_visual"]]
    escala = tipo.get("escala", 1)
    c = dict(cfg["legenda"])
    c.update(fonte=vis["fonte"], tamanho=round(vis["tamanho"] * escala), negrito=vis.get("negrito", False),
             maiusculas=vis.get("maiusculas", False), caixa=vis.get("caixa", False),
             contorno=vis["contorno"], sombra=vis["sombra"],
             modo=tipo["modo"], pop=tipo.get("pop", False), forca=tipo.get("forca", True),
             linhas=tipo.get("linhas", 1), max_palavras=tipo["max_palavras"],
             max_chars=round(tipo["max_chars"] * vis.get("largura", 1) / escala))
    principal = _hex(e.get("cor_principal"), c["destaque"])
    if principal != c["destaque"].upper():
        c["destaque_secundario"] = _clarear(principal)
    c["destaque"] = principal
    c["cor_fundo"] = _hex(e.get("cor_fundo"), MODELOS["padrao"]["cor_fundo"])
    c["base_px"] = int(min(1700, max(60, float(e.get("base_px") or c["base_px"]))))
    tt = MODELOS["titulos"][e["titulo"]]
    t = dict(c.get("titulo") or {})
    if e["titulo"] == "nenhum":
        t["ativo"] = False
    else:
        lay = tt.get("layout", "texto")
        t.update({k: v for k, v in tt.items() if k not in ("grupo", "nome", "descricao", "dica", "css", "peso")},
                 ativo=True, layout=lay, entrada=e["entrada"], cor_fundo=c["cor_fundo"],
                 inteiro=bool(e.get("titulo_inteiro")) and lay not in ("capa", "aspas"),
                 topo_px=int(min(1600, max(40, float(e.get("topo_px") or t.get("topo_px", 270))))))
    c["titulo"] = t
    return {**cfg, "legenda": c}


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


def _quebras(g: list[dict], linhas: int, max_chars: int) -> set[int]:
    """Em bloco de 2 linhas: depois de qual palavra entra a quebra. Só quebra se o
    bloco passa de meia largura, e no ponto que deixa as duas linhas parecidas."""
    if linhas < 2 or len(g) < 2:
        return set()
    tam = [len(w["w"]) for w in g]
    total = sum(tam) + len(g) - 1
    if total <= 0.55 * max_chars:
        return set()
    melhor = min(range(1, len(g)), key=lambda k: max(sum(tam[:k]) + k - 1, sum(tam[k:]) + len(g) - k - 1))
    return {melhor - 1}


CINZA = "&H00A0968C"   # o "apagado" do Foco: cinza-aço, como o `foco` do editor


def _tags(c: dict, i: int, a: int | None, w: str, cores: tuple[str, str]) -> str:
    """O override da palavra `i` com a palavra `a` sendo dita, por modo."""
    destaque, segunda = cores
    modo, f = c.get("modo", "karaoke"), c.get("forca", True) and forca(w)
    if modo == "karaoke":
        return f"\\c{destaque}" if i == a else f"\\c{segunda}" if f else ""
    if modo == "estatico":
        return f"\\c{destaque}" if f else ""
    if modo == "foco":
        return "" if i == a else f"\\c{CINZA}"
    if modo == "progressivo":
        return f"\\c{destaque}" if i <= a else ""
    if modo == "maquina":
        return "\\alpha&HFF&" if i > a else f"\\c{destaque}" if i == a else ""
    if modo == "vazado":
        return f"\\c{destaque}" if i == a else f"\\1a&HFF&\\3c&HFFFFFF&\\3a&H00&\\bord{max(3, c.get('contorno', 3))}"
    if modo == "neon":
        return f"\\c{segunda}\\3c{destaque}\\3a&H00&\\bord4\\blur8" if i == a else ""
    return ""   # marca: o texto fica branco, a tarja é outra camada


def _juntar(g: list[dict], quebras: set[int], fn) -> str:
    partes = []
    for i, w in enumerate(g):
        tag = fn(i, w["w"])
        partes.append(f"{{{tag}}}{w['w']}{{\\r}}" if tag else w["w"])
        partes.append("\\N" if i in quebras else " ")
    return "".join(partes[:-1])


def ass(ws: list[dict], dur: float, cfg: dict, titulo: str | None = None) -> str:
    """Karaokê: um evento por palavra dita, o bloco inteiro na tela e a palavra
    da vez na cor de destaque. Sem escala na palavra ativa: num bloco
    centralizado ela empurraria as vizinhas a cada troca.

    O `modo` (modelos_legenda.json) troca o que cada palavra pinta (`_tags`);
    `estatico` sai um evento por bloco. As caixas são CAMADAS por baixo do
    texto, com o mesmo texto invisível (BorderStyle 3: o libass pinta a caixa
    com a OutlineColour): a do bloco (visual `caixa`) e a tarja da palavra
    dita (modo `marca`, a OutlineColour ligada só nela). Nos estilos das caixas
    letra E caixa nascem invisíveis: o reset depois de cada palavra devolve o
    estilo, e o espaço ou a quebra que vêm em seguida não podem acender caixa."""
    c = cfg["legenda"]
    t = c.get("titulo") or {}
    ws = capitalizar(ws)
    if c.get("maiusculas"):
        ws = [{**w, "w": w["w"].upper()} for w in ws]
    grupos = agrupar(ws, c["max_palavras"], c["max_chars"], virgula_min=6)
    modo = c.get("modo", "karaoke")
    negrito = -1 if c.get("negrito") else 0
    caixa, marca = bool(c.get("caixa")), modo == "marca"
    camada = 2 if caixa or marca else 0
    destaque = _cor_ass(c["destaque"])
    segunda = _cor_ass(c["destaque_secundario"])
    fonte = f"{c['fonte']},{c['tamanho']},{_cor_ass(c['cor'])},{_cor_ass(c['cor'])}"
    fim_estilo = f"2,130,130,{c['base_px']},1"
    borda = "&H00000000,&H00000000,{n},0,0,0,100,100,-1,0,1,0,0" if caixa else \
        f"&H64000000,&H8C000000,{negrito},0,0,0,100,100,-1,0,1,{c.get('contorno', 3)},{c.get('sombra', 4)}"
    estilos = [f"Style: Cap,{fonte},{borda.format(n=negrito)},{fim_estilo}"]
    if caixa:
        estilos.append(f"Style: CapBox,{c['fonte']},{c['tamanho']},&HFF000000,&HFF000000,{_cor_ass(c['cor_fundo'])},&H00000000,{negrito},0,0,0,100,100,-1,0,"
                       f"3,{c.get('contorno', 16)},0,{fim_estilo}")
    if marca:
        estilos.append(f"Style: Marca,{c['fonte']},{c['tamanho']},&HFF000000,&HFF000000,{_cor_ass(c['destaque'], 'FF')},&H00000000,{negrito},0,0,0,100,100,-1,0,3,10,0,{fim_estilo}")

    fundo_t = t.get("cor_fundo")
    caixa_t = t.get("caixa", "fundo")
    neg_t = -1 if t.get("negrito") else 0
    if caixa_t == "principal":
        letra_t, borda_t = _cor_ass(fundo_t or "#000000"), f"{destaque},&H00000000,{neg_t},0,0,0,100,100,-1,0,3"
    elif caixa_t == "fundo":
        cx = _cor_ass(fundo_t, "1A") if fundo_t else "&H1A3A1F0B"
        letra_t, borda_t = _cor_ass(c["cor"]), f"{cx},&H00000000,{neg_t},0,0,0,100,100,-1,0,3"
    else:
        letra_t, borda_t = _cor_ass(c["cor"]), f"&H00000000,&H8C000000,{neg_t},0,0,0,100,100,-1,0,1"
    entrada, lay = t.get("entrada", "fade"), t.get("layout", "texto")
    desenho = t.get("ativo") and lay not in ("texto", "capa")
    if desenho:
        estilos += H.ESTILOS
    if t.get("ativo") and lay == "capa":
        estilos.append("Style: Capa,Arial,20,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1")
    cab = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{chr(10).join(estilos)}

Style: Titulo,{t.get('fonte', c['fonte'])},{t.get('tamanho', 72)},{letra_t},{letra_t},{borda_t},{t.get('contorno', 18)},{t.get('sombra', 0)},8,140,140,{t.get('topo_px', 270)},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    eventos = []
    cores = (destaque, segunda)
    pop = "{\\fscx70\\fscy70\\t(0,110,\\fscx112\\fscy112)\\t(110,220,\\fscx100\\fscy100)}" if c.get("pop") else ""

    def ev(camada_: int, ini: float, fim: float, estilo: str, texto: str) -> None:
        eventos.append(f"Dialogue: {camada_},{_ts_ass(ini)},{_ts_ass(min(fim, dur))},{estilo},,0,0,0,,{texto}")

    for n, g in enumerate(grupos):
        prox = grupos[n + 1][0]["s"] if n + 1 < len(grupos) else dur
        # o bloco fica até o próximo, se o vão for curto — piscar entre blocos cansa
        fim_bloco = prox if prox - g[-1]["e"] < 0.6 else g[-1]["e"] + 0.25
        if fim_bloco <= g[0]["s"]:
            continue
        qb = _quebras(g, c.get("linhas", 1), c["max_chars"])
        if caixa:
            ev(0, g[0]["s"], fim_bloco, "CapBox", _juntar(g, qb, lambda i, w: ""))
        if modo == "estatico":
            ev(camada, g[0]["s"], fim_bloco, "Cap", pop + _juntar(g, qb, lambda i, w: _tags(c, i, None, w, cores)))
            continue
        for k, w in enumerate(g):
            ini = w["s"] if k else g[0]["s"]
            fim = g[k + 1]["s"] if k + 1 < len(g) else fim_bloco
            if fim <= ini:
                continue
            if marca:
                ev(1, ini, fim, "Marca", _juntar(g, qb, lambda i, _w, k=k: "\\3a&H00&" if i == k else ""))
            ev(camada, ini, fim, "Cap", _juntar(g, qb, lambda i, w_, k=k: _tags(c, i, k, w_, cores)))

    titulo = re.sub(r"[{}\\]", "", titulo or "").strip()
    if titulo and t.get("ativo"):
        # o título do gancho no topo, logo abaixo da área segura (area_segura.py:
        # 250px de interface + folga), nos primeiros segundos — palavra de força
        # na cor de destaque. Quebra de linha digitada no popup manda.
        if t.get("maiusculas") and not desenho:
            titulo = titulo.upper()
        linhas = ([ln.strip() for ln in titulo.splitlines() if ln.strip()] if "\n" in titulo
                  else linhas_balanceadas(titulo, t["max_chars"]))
        realce = t.get("forca", True)
        txt = "\\N".join(" ".join(f"{{\\c{destaque}}}{w}{{\\r}}" if realce and forca(w) else w
                                   for w in ln.split()) for ln in linhas)
        fim = dur if t.get("inteiro") else min(dur, t["ate_s"])
        topo = t.get("topo_px", 270)
        if desenho:
            def quebra(tx: str, mc: int) -> list[str]:
                return ([x.strip() for x in tx.splitlines() if x.strip()] if "\n" in tx
                        else linhas_balanceadas(tx, mc))
            evs = H.layout(lay, quebra, titulo, topo, c["destaque"], fundo_t or "#000000", forca)
            eventos += H.montar(evs, 0.12, fim, entrada, _ts_ass)
        elif lay == "capa":
            # cold open: a tela na cor de fundo cobre tudo (legenda inclusive) e
            # devolve o vídeo saindo em fade
            ev(3, 0, fim, "Capa", f"{{\\an7\\pos(0,0)\\c{_cor_ass(fundo_t or '#000000')}\\fad(0,260)\\p1}}"
                                  "m 0 0 l 1080 0 1080 1920 0 1920{\\p0}")
            ev(4, 0, fim, "Titulo", f"{{\\an5\\pos(540,960)\\fad(0,260)}}{txt}")
        elif entrada == "desliza":
            ev(1, 0.12, fim, "Titulo", f"{{\\an8\\move(540,{topo - 140},540,{topo},0,280)\\fad(120,240)}}{txt}")
        elif entrada == "pop":
            ev(1, 0.12, fim, "Titulo", f"{{\\an8\\pos(540,{topo})\\fscx60\\fscy60\\t(0,150,\\fscx108\\fscy108)"
                                       f"\\t(150,280,\\fscx100\\fscy100)\\fad(0,240)}}{txt}")
        else:
            ev(1, 0.12, fim, "Titulo", f"{{\\fad(160,240)}}{txt}")
    return cab + "\n".join(eventos) + "\n"

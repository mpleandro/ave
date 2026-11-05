"""Estágio 7 — refino de bordas: o corte começa NO gancho.

A avaliação escolhe, dentro da janela, a frase onde o corte começa (`inicio`) e
a frase onde termina (`fim`), e pode tirar o conectivo de abertura
(`aparar_conector`: "Mas parem de ser chatos." → "Parem de ser chatos."). Aqui
isso vira tempo — sempre numa fronteira com silêncio medido, nunca abaixo da
duração mínima.

O defeito que esta forma corrige: a versão anterior pedia "quantas frases
pular" e DEPOIS dava nota ao gancho, então a nota descrevia a frase forte do
trecho e o corte continuava abrindo no aquecimento — nota 76 de gancho para um
vídeo que começava em "Não sei quem tá aqui na aula no primeiro dia". Agora o
início é escolhido junto com a nota, e `sinais_texto.validar` recusa um gancho
"tem" cuja frase não toca nos primeiros segundos do corte final.

Depois do refino, `aparar` limpa as pontas sem modelo nenhum — roda também
sobre um `notas.json` antigo: cauda de live ("é isso.", "é verdade ou não
é?"), logística ("posso continuar?", QR code), fala curta de outra pessoa
encostada na borda e a cauda colada na última frase, conferida ouvindo.
"""
from __future__ import annotations


def limites(c: dict, nota: dict, frs: list[dict]) -> tuple[int, int, float, dict | None]:
    """(frase inicial, frase final, start em segundos, apara) na fonte."""
    i0, _ = c["frases"]
    ni = i0 + nota.get("inicio", 0)
    nj = i0 + nota.get("fim", c["frases"][1] - i0)
    apara = frs[ni].get("apara") if nota.get("aparar_conector") else None
    start = apara["s"] if apara else frs[ni]["s"]
    return ni, nj, start, apara


def refinar(c: dict, nota: dict, frs: list[dict], cfg: dict) -> dict:
    i0, j0 = c["frases"]
    ni, nj, start, apara = limites(c, nota, frs)
    if (ni, nj) == (i0, j0) and not apara:
        return c
    dur = frs[nj]["e"] - start
    if nj < ni or dur < cfg["candidatos"]["dur_min_s"]:
        return c
    jan = frs[ni:nj + 1]
    abertura = apara["texto"] if apara else frs[ni]["texto"]
    textos = [abertura] + [f["texto"] for f in jan[1:]]
    palavras = sum(f["n"] for f in jan) - (len(apara["tirou"].split()) if apara else 0)
    return {**c, "start": round(start, 3), "end": round(frs[nj]["e"], 3),
            "dur": round(dur, 2), "frases": [ni, nj], "n_palavras": palavras,
            "borda": [round(apara["gap"] if apara else frs[ni]["pausa_antes"], 2),
                      round(frs[nj]["pausa_depois"], 2)],
            "abertura": abertura, "fechamento": frs[nj]["texto"],
            "texto": " ".join(textos),
            "refinado": {"inicio": ni - i0, "fim": nj - i0,
                         "tirou": apara["tirou"] if apara else None,
                         "original": [c["start"], c["end"]]}}


# ------------------------------------------------------------------ aparar

def _dur(frs: list[dict], i: int, j: int) -> float:
    return frs[j]["e"] - frs[i]["s"]


def _principal(quem: dict, frs: list[dict], i: int, j: int) -> str | None:
    """Quem mais fala em frs[i..j], pela duração das frases com nome."""
    tempo: dict[str, float] = {}
    for g in range(i, j + 1):
        q = quem.get(g)
        if q and q != "?":
            tempo[q] = tempo.get(q, 0.0) + _dur(frs, g, g)
    return max(tempo, key=tempo.get) if tempo else None


def aparar(r: dict, frs: list[dict], cfg: dict, quem: dict | None = None,
           confirmar=None, energia=None) -> dict:
    """Tira das BORDAS do corte, sem modelo nenhum, o que a avaliação deixou:

    1. cauda de live e logística da transmissão na ponta ("É isso.", "Quem tá
       entendendo isso, gente?", "Posso continuar?") — a borda recua para a
       frase limpa vizinha (`candidatos.borda_ruim`);
    2. fala CURTA (≤ `alertas.interjeicao_max_s`) de outra pessoa encostada na
       borda, se ela não fala mais que isso no resto do corte (quem conversa
       no trecho não é interjeição) — no fim sempre; no início só se não for
       pergunta, porque pergunta → resposta abre bem (anúncios #1 e #2);
    3. a cauda colada na última frase ("…pagamos o preço, é verdade ou não
       é?"), no vale de energia, se `confirmar(ponto, última palavra, cauda)`
       ouvir o corte limpo — sem escuta (None), só com silêncio de verdade.

    Nunca abaixo de `dur_min_s` e sempre numa borda que o áudio aceita
    (`candidatos.inicio_ok`/`fim_ok`) — ou, no fim, no vale de energia entre
    a frase limpa e a cauda, conferido ouvindo, quando a fala emenda: no
    c1338 "…o mesmo saldo no final do mês." tem 0,14s de silêncio antes do
    "é isso." (o piso de borda é 0,15s) e sem isso a cauda ficava. O que saiu fica em `refinado.aparado`
    (a galeria mostra; dá para desfazer). Fala de outra pessoa no MEIO não se
    corta aqui — é alerta (`sinais_audio.alertas`); emendar o meio é edição."""
    from . import candidatos as C  # noqa: PLC0415
    i0, j0 = r["frases"]
    ni, nj = i0, j0
    dmin = cfg["candidatos"]["dur_min_s"]
    max_s = (cfg.get("alertas") or {}).get("interjeicao_max_s", 6.0)
    quem = quem or {}
    aparado: list[dict] = []

    def s_de(i: int) -> float:
        return r["start"] if i == i0 else frs[i]["s"]

    def fim_limpo(k: int) -> bool:
        return C.fim_ok(frs, k, cfg) and not C.borda_ruim(frs[k], cfg) and frs[k]["e"] - s_de(ni) >= dmin

    def inicio_limpo(k: int) -> bool:
        return (C.inicio_ok(frs, k, cfg) and not C.borda_ruim(frs[k], cfg)
                and (vale[0] if vale else frs[nj]["e"]) - frs[k]["s"] >= dmin)

    def fim_no_vale(k: int) -> tuple[float, float] | None:
        """(ponto, vão) quando frs[k] fecha em ponto mas emenda na cauda: o vale
        entre as duas, se a escuta confirma (sem escuta, não — 0,14s de vão
        medido não garante que a sílaba seguinte fica fora)."""
        f, g = frs[k], frs[k + 1]
        # só quando EMENDA (sem o silêncio da borda): com silêncio, quem decide é
        # `fim_ok` e a duração mínima — o vale no meio do silêncio esticaria o
        # corte com ar para passar do mínimo (o "quem diz sim?" do c0838)
        if (energia is None or confirmar is None or not f["fecha_ponto"] or C.borda_ruim(f, cfg)
                or f["pausa_depois"] >= cfg["candidatos"]["borda_min_s"]
                or not f.get("ws") or not g.get("ws")):
            return None
        pv = C.ponto_de_fim(f["ws"][-1], g["ws"][0], energia)
        if pv is None or pv[0] - s_de(ni) < dmin or pv[0] <= f["ws"][-1]["s"]:
            return None
        if k not in vales:
            vales[k] = pv if confirmar(pv[0], f["ws"][-1]["w"], g["texto"]) else None
        return vales[k]

    def tira(lado: str, motivo: str, de: int, ate: int, **extra) -> None:
        aparado.append({"lado": lado, "motivo": motivo,
                        "texto": " ".join(frs[g]["texto"] for g in range(de, ate + 1)), **extra})

    vales: dict[int, tuple[float, float] | None] = {}
    vale = None
    mudou = True
    while mudou and nj > ni:
        mudou = False
        k = nj
        while k > ni and C.borda_ruim(frs[k], cfg):
            k -= 1
        if k < nj and fim_limpo(k):
            tira("fim", C.borda_ruim(frs[nj], cfg), k + 1, nj)
            nj, mudou, vale = k, True, None
            continue
        if k < nj and fim_no_vale(k):
            tira("fim", C.borda_ruim(frs[nj], cfg), k + 1, nj)
            nj, mudou, vale = k, True, fim_no_vale(k)
            continue
        k = ni
        while k < nj and C.borda_ruim(frs[k], cfg):
            k += 1
        if k > ni and inicio_limpo(k):
            tira("inicio", C.borda_ruim(frs[ni], cfg), ni, k - 1)
            ni, mudou = k, True
            continue
        p = _principal(quem, frs, ni, nj)
        if not p:
            break

        def outra(g: int) -> bool:
            return quem.get(g) not in (None, "?", p)

        def avulsa(de: int, ate: int) -> bool:
            """A fala [de..ate] é de quem só aparece ali (≤ max_s no resto do
            corte) — interjeição, não alguém que conversa no trecho. No c1171
            o Paulo fecha com "essa é a riqueza aos olhos dos muito pobres."
            depois de falar 14s no mesmo corte: é conversa, fica."""
            nomes = {quem.get(g) for g in range(de, ate + 1)}
            resto = sum(_dur(frs, g, g) for g in range(ni, nj + 1)
                        if not de <= g <= ate and quem.get(g) in nomes)
            return resto <= max_s
        # a borda recua por cima da fala da outra pessoa E da cauda/logística
        # que ficar logo antes dela ("diz alguma coisa pra mim." + a Júlia no c0734)
        r_ = nj
        while r_ > ni and outra(r_):
            r_ -= 1
        k = r_
        while k > ni and C.borda_ruim(frs[k], cfg):
            k -= 1
        if r_ < nj and _dur(frs, r_ + 1, nj) <= max_s and avulsa(r_ + 1, nj) and fim_limpo(k):
            tira("fim", "outra_voz", k + 1, nj, quem=quem.get(nj))
            nj, mudou, vale = k, True, None
            continue
        r_ = ni
        while r_ < nj and outra(r_):
            r_ += 1
        k = r_
        while k < nj and C.borda_ruim(frs[k], cfg):
            k += 1
        if (r_ > ni and _dur(frs, ni, r_ - 1) <= max_s and avulsa(ni, r_ - 1) and inicio_limpo(k)
                and not any("?" in frs[g]["texto"] for g in range(ni, r_))):
            tira("inicio", "outra_voz", ni, k - 1, quem=quem.get(ni))
            ni, mudou = k, True

    fim_t, fechamento, n_cauda, borda_fim = frs[nj]["e"], frs[nj]["texto"], 0, frs[nj]["pausa_depois"]
    if vale:
        fim_t, borda_fim = vale
    extra_ref: dict = {}
    ca = None if vale else frs[nj].get("cauda")
    if ca and ca["e"] - s_de(ni) >= dmin:
        ok = confirmar(ca["e"], ca["ultima"], ca["tirou"]) if confirmar else None
        if ok is None:
            ok = ca["vao"] >= C.VAO_CAUDA_SEGURO
        if ok:
            fim_t, fechamento, n_cauda, borda_fim = ca["e"], ca["texto"], ca["n"], ca["vao"]
            aparado.append({"lado": "fim", "motivo": "cauda_colada", "texto": ca["tirou"]})
            extra_ref["cauda"] = {"tirou": ca["tirou"], "n": ca["n"]}
        else:
            extra_ref["cauda_mantida"] = ca["tirou"]

    if not aparado:
        # nada saiu: a janela é a mesma (quem chama não remede); só fica
        # anotado que a cauda colada ficou por não dar para cortar limpo
        return {**r, "refinado": {**(r.get("refinado") or {}), **extra_ref}} if extra_ref else r
    ref = dict(r.get("refinado") or {})
    orig_i0 = i0 - ref.get("inicio", 0)
    tirou = ref.get("tirou") if ni == i0 else None
    start = r["start"] if ni == i0 else frs[ni]["s"]
    abertura = r["abertura"] if ni == i0 else frs[ni]["texto"]
    if ni == nj:
        textos = [fechamento if n_cauda else abertura]
    else:
        textos = [abertura] + [f["texto"] for f in frs[ni + 1:nj]] + [fechamento]
    palavras = (sum(f["n"] for f in frs[ni:nj + 1]) - (len(tirou.split()) if tirou else 0) - n_cauda)
    return {**r, "start": round(start, 3), "end": round(fim_t, 3), "dur": round(fim_t - start, 2),
            "frases": [ni, nj], "n_palavras": palavras,
            "borda": [r["borda"][0] if ni == i0 else round(frs[ni]["pausa_antes"], 2), round(borda_fim, 2)],
            "abertura": abertura, "fechamento": fechamento, "texto": " ".join(textos),
            "refinado": {**ref, "inicio": ni - orig_i0, "fim": nj - orig_i0, "tirou": tirou,
                         "original": ref.get("original") or [r["start"], r["end"]],
                         "aparado": aparado, **extra_ref}}

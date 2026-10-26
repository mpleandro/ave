"""Fala limpa — tirar do corte o que é falha de fala, não conteúdo.

Três tipos, do mais seguro ao mais delicado:

- FRASE REFEITA — a régua do Avelin (`detect_restarts`): tentativa TRUNCADA
  que a pessoa recomeçou ("Se eu perguntar aqui, por exemplo, não… / Se eu
  perguntar aqui…") e repetição IDÊNTICA (fica a última). A classe SEMÂNTICA —
  mesma ideia, outras palavras — fica de fora: qual tomada vale é de quem
  assina o vídeo, e paralelismo também é figura de linguagem.
- GAGUEJO — a mesma palavra ou trecho dito duas vezes, sem pontuação no meio
  ("eu eu tô"; "quer um plano… quer um plano"). Fica a segunda. Com vírgula
  ("não, não, eu prefiro") é ênfase e não se toca; "que que" também não — "por
  que que" é português; e trecho com palavra de conteúdo repetido NUM FÔLEGO
  SÓ ("a Marvel não era nada não era nada") é ênfase — só sai se houver a
  pausa de quem recomeçou.
- MULETA — "né", "tipo", "ahn", "é…", no meio da fala. Sai só se a emenda,
  ouvida, soar como o texto sem ela — colada demais na vizinha, a conferência
  ouve a sílaba comida e recusa.

Nada sai sem ser OUVIDO depois: cada remoção é montada num trecho de ~3s em
volta da emenda, transcrita pelo Whisper local, e só fica se o que se ouve é
o texto esperado sem a falha. Os tempos são os OUVIDOS no corte
(`legenda.alinhar`), assentados no quadro de menor energia do vão — o tempo do
transcrito já chegou 0,27s adiantado nesta série.
"""
from __future__ import annotations

import difflib
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import detect_restarts as DR  # noqa: E402
from derivado import derivado  # noqa: E402

from . import legenda as L

# já normalizadas. "ah" NÃO entra: nesta série ele é quase sempre a pessoa
# imitando alguém ("as pessoas vão dizer: ah, usa essa") — interjeição, não muleta
MULETAS = {"ne", "tipo", "ahn", "hum", "hmm", "uh", "eh", "ee", "eee"}
GAGUEJO_1 = {"eu", "o", "a", "de", "e", "um", "uma", "é", "se", "no", "na", "pra", "pro",
             "do", "da", "em", "ele", "ela", "você", "isso", "esse", "essa", "tá"}
CONTEXTO_S = 1.6       # quanto de fala em volta da emenda se ouve para conferir
PAUSA_RECOMECO = 0.30  # pausa entre as cópias que separa recomeço de ênfase


def _n(w: str) -> str:
    return DR.norm(w)


def _igual(w: str) -> str:
    """Comparação de GAGUEJO: minúsculo e sem pontuação, mas COM acento — sem
    acento "e é assim" (conjunção + verbo) parecia um "e e" gaguejado."""
    return re.sub(r"[^\w]", "", w.lower())


def _pontuada(w: str) -> bool:
    return bool(re.search(r"[,.;:?!…]$", w.strip()))


def detectar(ws: list[dict]) -> list[dict]:
    """[{tipo, i, j, texto}] — palavras i..j (inclusive) a remover."""
    achados: list[dict] = []

    # 1. frase refeita (régua do Avelin), por frase medida
    dr = [{"t": w["s"], "fim": w["e"], "txt": w["w"], "n": _n(w["w"]), "k": k}
          for k, w in enumerate(ws)]
    fs = DR.frases(dr)
    ordem = {id(f): n for n, f in enumerate(fs)}
    for h in DR.achar(fs):
        c = DR.classificar(h)
        if c["acao"] not in ("remover_A", "fica_a_ultima"):
            continue
        # só a tentativa COLADA na que vale: o detector pareia frases até 12s
        # longe, e tirar uma frase do meio do raciocínio quebra o fluxo
        if ordem.get(id(h["b"]), -1) != ordem.get(id(h["a"]), -9) + 1:
            continue
        a = h["a"]
        ks = [w["k"] for w in dr if a["t"] - 1e-6 <= w["t"] <= a["fim"] + 1e-6]
        if ks:
            achados.append({"tipo": "frase refeita", "i": ks[0], "j": ks[-1],
                            "texto": " ".join(ws[k]["w"] for k in ks)})

    # 2. gaguejo colado: n-grama repetido logo em seguida, sem pontuação no meio
    k = 0
    while k < len(ws):
        for n in (3, 2, 1):
            a, b = ws[k:k + n], ws[k + n:k + 2 * n]
            if len(b) < n or [_igual(x["w"]) for x in a] != [_igual(x["w"]) for x in b]:
                continue
            if any(_pontuada(x["w"]) for x in a):
                continue
            if n == 1 and (a[0]["w"].lower().strip(",.") not in GAGUEJO_1 or _n(a[0]["w"]) == "que"):
                continue
            # repetição com palavra de CONTEÚDO dita num fôlego só é ênfase
            # ("a Marvel não era nada não era nada"); gaguejo de verdade
            # ("quer um plano… quer um plano") tem a pausa de quem recomeçou
            if n > 1 and DR._conteudo([_n(x["w"]) for x in a]) and b[0]["s"] - a[-1]["e"] < PAUSA_RECOMECO:
                continue
            achados.append({"tipo": "gaguejo", "i": k, "j": k + n - 1,
                            "texto": " ".join(x["w"] for x in a)})
            k += n
            break
        else:
            k += 1

    # 3. muleta isolada (o respiro em volta é conferido em `intervalo`)
    for k, w in enumerate(ws):
        bruto = w["w"].lower().strip(",.?!;:")
        if _n(w["w"]) in MULETAS or bruto in ("é...", "é…") or w["w"].lower() in ("é...", "é…"):
            if 0 < k < len(ws) - 1:
                achados.append({"tipo": "muleta", "i": k, "j": k, "texto": w["w"]})

    # sem sobreposição: o primeiro achado de cada palavra vale
    usados: set[int] = set()
    out = []
    for h in sorted(achados, key=lambda h: (h["i"], -(h["j"] - h["i"]))):
        r = set(range(h["i"], h["j"] + 1))
        if r & usados or h["i"] == 0 or h["j"] >= len(ws) - 1:
            continue
        usados |= r
        out.append(h)
    return out


def _vao(t, db, de: float, ate: float) -> tuple[float, float]:
    """(instante de menor energia, energia) em [de, ate]."""
    import numpy as np  # noqa: PLC0415
    m = (t >= de) & (t <= ate)
    if not m.any():
        return (de + ate) / 2, 0.0
    k = int(np.argmin(db[m]))
    return float(t[m][k]), float(db[m][k])


def intervalo(ws: list[dict], h: dict, a: float, energia) -> tuple[float, float] | None:
    """O trecho da fonte que sai: do vão antes da palavra i ao vão depois da j."""
    t, db, limiar = energia
    ant, ini, fim, prox = ws[h["i"] - 1], ws[h["i"]], ws[h["j"]], ws[h["j"] + 1]
    x, ex = _vao(t, db, a + ant["e"] - 0.05, a + ini["s"] + 0.05)
    y, ey = _vao(t, db, a + fim["e"] - 0.05, a + prox["s"] + 0.05)
    if y - x < 0.08:
        return None
    # Muleta colada na vizinha não é recusada aqui: quem decide é ouvir a
    # emenda (`soa_limpo`). Recusar pela energia barrava o "né" de "todo feito
    # pra, né, toda produção", que sai limpo — o vão é curto, mas existe.
    return round(x, 3), round(y, 3)


def ouvir_emenda(video: Path, x: float, y: float) -> list[str]:
    import mlx_whisper  # noqa: PLC0415
    with tempfile.TemporaryDirectory() as d:
        w = Path(d) / "e.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y",
                        "-ss", f"{x - CONTEXTO_S:.3f}", "-t", f"{CONTEXTO_S:.3f}", "-i", str(video),
                        "-ss", f"{y:.3f}", "-t", f"{CONTEXTO_S:.3f}", "-i", str(video),
                        "-filter_complex", "[0:a][1:a]concat=n=2:v=0:a=1[a]", "-map", "[a]",
                        "-ac", "1", "-ar", "16000", str(w)], check=True)
        r = mlx_whisper.transcribe(str(w), path_or_hf_repo=L.MODELO, language="pt",
                                   condition_on_previous_text=False)
    return [_n(x) for x in r["text"].split() if _n(x)]


def _conta(seq: list[str], alvo: list[str]) -> int:
    n = len(alvo)
    return sum(1 for i in range(len(seq) - n + 1) if seq[i:i + n] == alvo) if n else 0


def soa_limpo(ouvido: list[str], antes: list[str], depois: list[str], tirado: list[str]) -> bool:
    """O que se ouve na emenda bate com antes+depois e não traz a falha.

    A falha é contada, não procurada: no gaguejo "eu eu tô" o "eu" que fica é
    legítimo, então o que reprova é ouvir o trecho MAIS vezes do que o texto
    limpo tem — não ouvi-lo."""
    if not ouvido or not antes or not depois:
        return False
    esperado = antes + depois
    if difflib.SequenceMatcher(None, ouvido, esperado).ratio() < 0.7:
        return False
    if _conta(ouvido, tirado) > _conta(esperado, tirado):
        return False
    return depois[0] in ouvido and antes[-1] in ouvido


def limpar(video: Path, c: dict, janela: tuple[float, float], energia) -> dict:
    """{"aprovadas": [{tipo, texto, de, ate}], "mantidas": [{tipo, texto, motivo}]}.

    As mantidas aparecem na tela: uma falha detectada e deixada no corte tem de
    dizer por quê — senão parece que a limpeza nem rodou."""
    a, b = janela

    # sem a escuta local nada sai: cortar sem ouvir a emenda é o risco que esta
    # limpeza existe para não correr. Fora do cache, pelo mesmo motivo da legenda.
    try:
        import mlx_whisper  # noqa: F401, PLC0415
    except ImportError:
        return {"aprovadas": [], "mantidas": []}

    def medir():
        ws = L.alinhar(c.get("palavras") or [], L.ouvir(video, a, b), b - a)
        aprovadas, mantidas = [], []
        for h in detectar(ws):
            iv = intervalo(ws, h, a, energia)
            if not iv:
                mantidas.append({"tipo": h["tipo"], "texto": h["texto"],
                                 "motivo": "colada na palavra vizinha — cortar ali comeria sílaba"})
                continue
            x, y = iv
            antes = [_n(w["w"]) for w in ws if a + w["e"] <= x + 0.05 and a + w["s"] >= x - CONTEXTO_S]
            depois = [_n(w["w"]) for w in ws if a + w["s"] >= y - 0.05 and a + w["e"] <= y + CONTEXTO_S]
            tirado = [_n(w["w"]) for w in ws[h["i"]:h["j"] + 1]]
            if soa_limpo(ouvir_emenda(video, x, y), antes, depois, tirado):
                aprovadas.append({"tipo": h["tipo"], "texto": h["texto"], "de": x, "ate": y})
            else:
                mantidas.append({"tipo": h["tipo"], "texto": h["texto"],
                                 "motivo": "a emenda sem ela não soou limpa"})
        return {"aprovadas": aprovadas, "mantidas": mantidas}

    return derivado("fala_limpa", [video], {"a": round(a, 3), "b": round(b, 3),
                                            "palavras": len(c.get("palavras") or []),
                                            "versao": 3}, "1", medir)


def resumo(remocoes: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in remocoes:
        out[r["tipo"]] = out.get(r["tipo"], 0) + 1
    return out

"""Versões de um corte — o mesmo trecho, reprocessado.

    original                    [(a, b)]
    respiros                    (a, b) com o ar morto encurtado
    falhas                      (a, b) sem os erros de fala (fala.py)
    gancho                      [frase do gancho] + (a, b)  — cold open
    gancho+respiros+falhas …    qualquer combinação das três PEÇAS

Uma versão é um conjunto de peças, e a chave é a lista delas na ordem de
PECAS, unida por "+". Cada peça é uma recomendação que a tela aplica ou desfaz
sozinha.

Cada versão é uma lista de TRECHOS DA FONTE tocados em sequência; o render,
a legenda e o import para o Avelin leem a mesma lista, então os três
concordam sobre onde cada palavra cai.

ERROS DE FALA (frase refeita, gaguejo, muleta) estão em `fala.py`.
RESPIROS usa a régua do PRÓPRIO Avelin
— `propose_breaths.avaliar`, perfil equilibrado: hesitação, respiração e pausa
retórica tratadas diferente, limiar calibrado na fonte, segunda opinião pela
média de dB do vão — e a emenda do `render.expand_breaths` (o pedaço termina em
at + keep − pad, o próximo começa em to − pad). Assim o ritmo que sai daqui é
o mesmo que o editor daria.

GANCHO PUXADO repete a frase de gancho antes do 0:00: ela abre o vídeo e volta
no lugar dela, com o contexto. A borda da frase sai do tempo OUVIDO (Whisper
local, `legenda.ouvir`), assentada no quadro de menor energia por perto, e é
conferida ouvindo — o tempo do transcrito já chegou 0,27s adiantado.
"""
from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from derivado import derivado  # noqa: E402

from . import legenda as L
from . import verificar as V

RITMO = "equilibrado"
EDGE_PAD = 0.030      # render.BREATH_EDGE_PAD
PECAS = ("gancho", "respiros", "falhas")
NOME_PECA = {"gancho": "gancho puxado", "respiros": "sem respiros", "falhas": "erros de fala corrigidos"}
# chaves de antes da separação em peças (aplicadas.json antigo)
ANTIGAS = {"fala_limpa": "respiros+falhas", "gancho_fala_limpa": "gancho+respiros+falhas",
           "sem_respiros": "respiros", "gancho_sem_respiros": "gancho+respiros"}


def pecas(versao: str) -> set[str]:
    versao = ANTIGAS.get(versao, versao)
    return set() if versao in ("", "original") else set(versao.split("+"))


def chave(ps) -> str:
    return "+".join(p for p in PECAS if p in ps) or "original"


def nome(versao: str) -> str:
    ps = pecas(versao)
    if not ps:
        return "Original"
    txt = " + ".join(NOME_PECA[p] for p in PECAS if p in ps)
    return txt[0].upper() + txt[1:]


def janela(c: dict) -> tuple[float, float]:
    """O trecho exato da fonte que vira arquivo. A borda ganha metade do
    silêncio medido, até 0,1s antes e 0,15s depois: cortar no carimbo exato da
    palavra come a cauda dela, e o silêncio medido garante que a folga não pega
    a frase vizinha. Toda versão, legenda e import partem DESTA janela — é o
    que mantém tudo sincronizado."""
    antes, depois = (c.get("borda") or [0, 0])[:2]
    return max(0.0, c["start"] - min(0.10, antes / 2)), c["end"] + min(0.15, depois / 2)


# ------------------------------------------------------------------ respiros

def marcas_respiro(video: Path, trab: Path, a: float, b: float) -> list[dict]:
    """[{at, to, keep}] — o que o Avelin encurtaria dentro de (a, b)."""
    def medir():
        from propose_breaths import avaliar  # noqa: PLC0415
        edl = {"sources": {video.stem: str(video)},
               "ranges": [{"source": video.stem, "start": a, "end": b}]}
        ranges, _, _ = avaliar(trab, edl, RITMO, verbose=False)
        return ranges[0].get("breaths", []) if ranges else []
    return derivado("respiros_corte", [video], {"a": round(a, 3), "b": round(b, 3),
                                                 "ritmo": RITMO}, "1", medir)


def remover(a: float, b: float, marcas: list[dict], fala: list[dict]) -> list[tuple[float, float]]:
    """A janela menos o que sai: o miolo de cada respiro (a mesma emenda de
    `render.expand_breaths`) e cada falha de fala aprovada ouvindo."""
    tirar = [(m["at"] + max(0.0, m.get("keep", 0.15) - EDGE_PAD), m["to"] - EDGE_PAD)
             for m in marcas if m["to"] - m["at"] > m.get("keep", 0.15) and a < m["at"] < m["to"] < b]
    tirar += [(f["de"], f["ate"]) for f in fala if a < f["de"] < f["ate"] < b]
    tirar.sort()
    juntos: list[list[float]] = []
    for x, y in tirar:
        if juntos and x <= juntos[-1][1]:
            juntos[-1][1] = max(juntos[-1][1], y)
        else:
            juntos.append([x, y])
    segs, cur = [], a
    for x, y in juntos:
        if x - cur > 0.04:
            segs.append((cur, x))
        cur = y
    segs.append((cur, b))
    return segs


def aplicar_respiros(a: float, b: float, marcas: list[dict]) -> list[tuple[float, float]]:
    """A mesma expansão de `render.expand_breaths`."""
    segs, cur = [], a
    for m in sorted(marcas, key=lambda x: x["at"]):
        at, to, keep = m["at"], m["to"], m.get("keep", 0.15)
        if not (cur < at < to < b) or to - at <= keep:
            continue
        segs.append((cur, at + max(0.0, keep - EDGE_PAD)))
        cur = to - EDGE_PAD
    segs.append((cur, b))
    return segs


# ------------------------------------------------------------------ gancho

def _local(tokens: list[str], alvo: list[str]) -> int | None:
    n = len(alvo)
    for i in range(len(tokens) - n + 1):
        if tokens[i:i + n] == alvo:
            return i
    # casamento frouxo: as 4 primeiras palavras bastam para achar o começo
    cab = alvo[:4]
    for i in range(len(tokens) - len(cab) + 1):
        if tokens[i:i + len(cab)] == cab:
            return i
    return None


def _assentar(t, db, alvo: float, antes: float, depois: float) -> float:
    """O quadro de menor energia em [alvo − antes, alvo + depois]."""
    import numpy as np  # noqa: PLC0415
    m = (t >= alvo - antes) & (t <= alvo + depois)
    if not m.any():
        return alvo
    return float(t[m][int(np.argmin(db[m]))])


def trecho_gancho(video: Path, c: dict, frase: str, janela: tuple[float, float],
                  energia) -> tuple[float, float] | None:
    """Onde a frase de gancho está na fonte, conferido ouvindo. None se não
    der para isolá-la com segurança — aí o botão não aparece."""
    from .candidatos import APARAVEIS, _norm  # noqa: PLC0415
    a, b = janela
    palavras = c.get("palavras") or []
    alinhadas = L.alinhar(palavras, L.ouvir(video, a, b), b - a)
    toks = [L._tok(w["w"]) for w in alinhadas]
    alvo = [L._tok(w) for w in frase.split()]
    i = _local(toks, alvo)
    if i is None:
        return None
    # o conectivo de abertura sai também aqui: "então quando você resolve…"
    # vira "Quando você resolve…" no cold open
    for n in (2, 1):
        if " ".join(_norm(w["w"]) for w in alinhadas[i:i + n]) in APARAVEIS and len(alvo) > n + 2:
            i += n
            alvo = alvo[n:]
            break
    j = min(len(alinhadas) - 1, i + len(alvo) - 1)
    t, db = energia
    ini = _assentar(t, db, a + alinhadas[i]["s"], 0.12, 0.02)
    fim = _assentar(t, db, a + alinhadas[j]["e"], 0.02, 0.25)
    esperado = " ".join(w["w"] for w in alinhadas[i:j + 1])
    for tentativa in (ini, ini - 0.06, ini + 0.06):
        try:
            ouvido = V._ouvir(video, tentativa)
        except ImportError:
            return None   # sem a escuta local o gancho não é puxado às cegas
        if V.bate(ouvido, esperado, ""):
            return round(tentativa, 3), round(fim, 3)
    return None


# ------------------------------------------------------------------ plano

def plano(c: dict, variante: str, janela: tuple[float, float]) -> list[tuple[float, float]]:
    a, b = janela
    ps = pecas(variante)
    corpo = remover(a, b, (c.get("respiros") or []) if "respiros" in ps else [],
                    (c.get("fala") or []) if "falhas" in ps else [])
    if "gancho" in ps:
        g = (c.get("variantes") or {}).get("gancho", {}).get("trecho")
        if not g:
            raise ValueError("este corte não tem gancho para puxar")
        return [tuple(g)] + corpo
    return corpo


def duracao(segs: list[tuple[float, float]], fps: float = 30.0) -> float:
    return sum(math.ceil((b - a) * fps) / fps for a, b in segs)


def remapear(palavras_rel: list[dict], a: float, segs: list[tuple[float, float]],
             fps: float = 30.0) -> list[dict]:
    """Palavras (tempo relativo a `a`) → tempo do vídeo montado. Palavra cujo
    meio cai num vão removido some; a do gancho aparece duas vezes."""
    out, base = [], 0.0
    for sa, sb in segs:
        for w in palavras_rel:
            s, e = w["s"] + a, w["e"] + a
            if sa <= (s + e) / 2 < sb:
                out.append({"w": w["w"], "s": round(base + max(s, sa) - sa, 3),
                            "e": round(base + min(e, sb) - sa, 3)})
        base += math.ceil((sb - sa) * fps) / fps
    return out


def _dimensoes(video: Path) -> tuple[int, int]:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height", "-of", "csv=p=0", str(video)],
                       capture_output=True, text=True).stdout.strip().split(",")
    return int(r[0]), int(r[1])


def render(video: Path, segs: list[tuple[float, float]], destino: Path,
           ass: Path | None = None, fps: float = 30.0, zoom: dict | None = None,
           quadro: dict | None = None) -> None:
    """Concatena os trechos com 8ms de fade no áudio em cada emenda (sem
    estalo) e a duração de cada trecho arredondada para quadros inteiros —
    o mesmo motivo do `render.snap_ranges_to_frames`: vídeo em quadros
    inteiros e áudio em amostras deixam a imagem escorregar a cada emenda.

    QUADRO (enquadramento.plano): fonte horizontal vira 9:16 — cada trecho é
    partido nas trocas de enquadramento (quem fala, corte de câmera) e cada
    pedaço ganha o seu filtro (faixa na pessoa, ou quadro inteiro sobre fundo
    desfocado). Sem quadro, a fonte já é vertical e passa como está.

    ZOOM ALTERNADO: com mais de um trecho, um sim, um não, o quadro aproxima
    `zoom.fator` em torno do alvo da câmera — é o `zoomCuts` do Avelin, e é o
    que faz a emenda no meio de uma tomada parecer corte de câmera e não pulo
    (jump cut). O fator é o menor do ciclo do Avelin (1,10): sobe o bastante
    para a emenda ler como intenção sem cortar o enquadramento."""
    from . import enquadramento as EQ  # noqa: PLC0415
    W, H = _dimensoes(video)
    if quadro and not quadro.get("vertical"):
        pedacos = []
        for k, (sa, sb) in enumerate(segs):
            pedacos += [(x0, x1, t, k) for x0, x1, t in EQ.recortar([(sa, sb)], quadro)]
        OW, OH = 1080, 1920
    else:
        pedacos = [(sa, sb, None, k) for k, (sa, sb) in enumerate(segs)]
        OW, OH = W, H
    entradas, filtros, rotulos = [], [], []
    for n, (sa, sb, tr, k) in enumerate(pedacos):
        d = math.ceil((sb - sa) * fps) / fps
        entradas += ["-ss", f"{sa:.3f}", "-t", f"{d:.4f}", "-i", str(video)]
        base = f"[{n}:v]setpts=PTS-STARTPTS"
        if tr is not None:
            base += "," + EQ.filtro(tr, W, H, (OW, OH), str(n))
        if zoom and len(segs) > 1 and k % 2 == 1:
            z = zoom["fator"]
            zw, zh = int(OW * z) // 2 * 2, int(OH * z) // 2 * 2
            x0 = int((zw - OW) * zoom["alvo_x"])
            y0 = int((zh - OH) * zoom["alvo_y"])
            base += f",scale={zw}:{zh}:flags=lanczos,crop={OW}:{OH}:{x0}:{y0}"
        filtros.append(f"{base},setsar=1[v{n}]")
        filtros.append(f"[{n}:a]asetpts=PTS-STARTPTS,afade=t=in:d=0.008,"
                       f"afade=t=out:st={max(0.0, d - 0.008):.4f}:d=0.008[a{n}]")
        rotulos.append(f"[v{n}][a{n}]")
    filtros.append(f"{''.join(rotulos)}concat=n={len(pedacos)}:v=1:a=1[v][a]")
    saida_v = "[v]"
    if ass:
        filtros.append(f"[v]ass={ass}[vs]")
        saida_v = "[vs]"
    tmp = destino.with_suffix(".tmp.mp4")
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *entradas,
                    "-filter_complex", ";".join(filtros), "-map", saida_v, "-map", "[a]",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
                    "-r", f"{fps:g}", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
                    str(tmp)], check=True)
    tmp.rename(destino)


def transcricao(c: dict, alinhadas: list[dict], a: float) -> list[dict]:
    """O texto do corte como a tela o mostra: TODAS as palavras e as pausas
    longas, cada uma marcada com a peça que a tira (`respiro`, `falha`). A tela
    risca o que sai na versão aplicada e sublinha o que pode sair.

    Tempo das palavras: o OUVIDO no corte (`alinhadas`, relativo a `a`) — é com
    ele que as remoções foram medidas, então palavra e remoção concordam."""
    marcas = c.get("respiros") or []
    falhas = c.get("fala") or []
    out: list[dict] = []
    for k, w in enumerate(alinhadas):
        s, e = a + w["s"], a + w["e"]
        meio = (s + e) / 2
        f = next((i for i, x in enumerate(falhas) if x["de"] <= meio <= x["ate"]), None)
        out.append({"t": "w", "w": w["w"], **({"falha": f} if f is not None else {})})
        if k + 1 < len(alinhadas):
            prox = a + alinhadas[k + 1]["s"]
            if prox - e < 0.5:
                continue
            r = next((i for i, m in enumerate(marcas)
                      if min(m["to"], prox + 0.2) - max(m["at"], e - 0.2) > 0.5 * (m["to"] - m["at"])), None)
            p = {"t": "p", "dur": round(prox - e, 1)}
            if r is not None:
                p.update({"respiro": r, "fica": round(marcas[r].get("keep", 0.15), 2)})
            out.append(p)
    return out

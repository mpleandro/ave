#!/usr/bin/env python3
"""Tela de CORTES — ver, ouvir, melhorar e baixar os trechos garimpados.

    uv run python helpers/cortes_view.py "<video>" [--port 4830]

Uma tela à parte do editor (assets/preview/ é imutável): a galeria dos cortes
pela nota de viralização, cada um tocando direto do vídeo ORIGINAL.

No corte aberto:
  - VERSÕES (cortes/variantes.py): original, fala limpa (sem respiros e sem
    falhas de fala, com zoom alternado nas emendas), gancho puxado (cold open)
    e as duas juntas — cada uma com o score previsto. Aplicar uma reprocessa o
    corte (com aviso), o player passa a tocá-la e o score da galeria passa a
    ser o dela (`analise/aplicadas.json`).
  - DOWNLOADS da versão escolhida: o vídeo limpo (padrão), o .srt separado e,
    só se pedido, um segundo MP4 com o karaokê queimado (cortes/legenda.py).
  - EDITAR NO AVELIN: um projeto do Avelin por vídeo longo, reaproveitado a
    cada corte, sem cópia de vídeo (ver `importar_avelin`).

Tudo o que sai fica em `<stem>_cortes/`, com os tempos do corte no nome —
pedir de novo reaproveita o arquivo.
"""
from __future__ import annotations

import argparse
import os
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unicodedata
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cortes import fonte as F  # noqa: E402
from cortes import enquadramento as EQ  # noqa: E402
from cortes import legenda as L  # noqa: E402
from cortes import variantes as VR  # noqa: E402

SKILL = Path(__file__).resolve().parent.parent
PAGINA = SKILL / "assets" / "cortes" / "index.html"
ICONE = SKILL / "assets" / "preview" / "avelin-icon.png"
ESTAGIOS = ("selecao", "candidatos")   # do mais avançado ao mais cru

VIDEO: Path
TRAB: Path
FPS = 30.0
_TRAVAS: dict[str, threading.Lock] = {}
# o que está rodando AGORA, por corte — a página pergunta por isso, então o
# carregando sobrevive a recarregar, fechar e reabrir a aba
_TRABALHOS: dict[str, list[str]] = {}
_TRAVA = threading.Lock()


def slug(s: str, n: int = 40) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:n].strip("-") or "corte"


def duracao(video: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(video)], capture_output=True, text=True)
    try:
        return float(out.stdout.strip())
    except ValueError:
        return 0.0


def cortes() -> dict:
    for nome in ESTAGIOS:
        if (TRAB / "analise" / f"{nome}.json").exists():
            d = F.ler(TRAB, nome)
            return {"estagio": nome, "cortes": d.get("cortes") or d.get("candidatos") or []}
    return {"estagio": None, "cortes": []}


class Recusa(Exception):
    def __init__(self, msg: str, code: int = 400, **extra):
        super().__init__(msg)
        self.code, self.extra = code, extra


def base_nome(c: dict) -> str:
    # os tempos entram no nome: o refino de bordas muda o início de um corte de
    # mesmo id, e reaproveitar pelo id entregaria o recorte antigo
    marca = hashlib.sha1(f"{c['start']:.3f}-{c['end']:.3f}".encode()).hexdigest()[:6]
    return f"{c['id']}_{slug(c.get('titulo_sugerido') or c.get('abertura') or '')}_{marca}"


def normalizar(c: dict, versao: str) -> str:
    """A chave canônica da versão, só com as peças que este corte TEM — uma
    aplicada com o nome antigo (`fala_limpa`) num corte sem erro de fala vira
    `respiros`, em vez de sumir."""
    vs = c.get("variantes") or {}
    ps = {p for p in VR.pecas(versao) if any(p in VR.pecas(k) for k in vs)}
    return VR.chave(ps)


def nome_versao(c: dict, versao: str) -> str:
    return base_nome(c) + ("" if versao == "original" else f"_{versao.replace('+', '-')}")


def _trava(chave: str) -> threading.Lock:
    with _TRAVA:
        return _TRAVAS.setdefault(chave, threading.Lock())


def _plano(c: dict, versao: str) -> list[tuple[float, float]]:
    if versao != "original" and versao not in (c.get("variantes") or {}):
        raise Recusa(f"este corte não tem a versão {versao!r}")
    return VR.plano(c, versao, VR.janela(c))


def _baixados_path() -> Path:
    return TRAB / "analise" / "baixados.json"


def baixados() -> dict:
    """{id do corte: {"arquivos": [...], "em": epoch}} — o que já saiu da galeria
    pelo botão de baixar. A tela pinta a seta de verde para esses."""
    try:
        return json.loads(_baixados_path().read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def marcar_baixado(nome: str) -> None:
    ids = [c["id"] for c in cortes()["cortes"] if nome.startswith(c["id"] + "_")]
    if not ids:
        return
    cid = max(ids, key=len)
    with _TRAVA:
        d = baixados()
        r = d.setdefault(cid, {"arquivos": [], "em": 0})
        if nome not in r["arquivos"]:
            r["arquivos"].append(nome)
        r["em"] = int(__import__("time").time())
        _baixados_path().write_text(json.dumps(d, ensure_ascii=False, indent=1))


def edicao(c: dict) -> Path | None:
    """O corte EDITADO à mão (`<trabalho>/edicao/edicoes.json` → {id: arquivo}),
    quando existe. Ele vira a base de TODO download do corte — limpo, com
    legenda e .srt. Antes disso, "Com legenda" refazia o corte a partir da
    fonte e entregava a versão do garimpo: no "pneu do Gol" (2026-11) o arquivo
    legendado saiu sem o gancho novo, sem a transição e sem o CTA pedidos."""
    mapa = TRAB / "edicao" / "edicoes.json"
    try:
        rel = json.loads(mapa.read_text()).get(c["id"])
    except (OSError, json.JSONDecodeError):
        return None
    p = (mapa.parent / rel) if rel else None
    return p if p and p.exists() else None


def _palavras_editado(ed: Path) -> tuple[list[dict], float]:
    """Palavras OUVIDAS no próprio corte editado — a montagem é outra, então o
    transcrito do garimpo não serve."""
    d = duracao(ed)
    return L.ouvir(ed, 0.0, d), d


def palavras_da_versao(c: dict, versao: str) -> tuple[list[dict], float]:
    """A legenda da versão: texto do transcrito, tempo de ouvir o corte, e cada
    palavra levada para onde ela cai no vídeo montado."""
    ed = edicao(c)
    if ed and versao == "original":
        return _palavras_editado(ed)
    a, b = VR.janela(c)
    alinhadas = L.alinhar(c.get("palavras") or [], L.ouvir(VIDEO, a, b), b - a)
    segs = _plano(c, versao)
    return VR.remapear(alinhadas, a, segs, FPS), VR.duracao(segs, FPS)


def legenda_srt(c: dict, versao: str = "original") -> Path:
    destino = TRAB / f"{nome_versao(c, versao)}.srt"
    ed = edicao(c) if versao == "original" else None
    with _trava(destino.name):
        if not destino.exists() or (ed and destino.stat().st_mtime < ed.stat().st_mtime):
            ws, dur = palavras_da_versao(c, versao)
            destino.write_text(L.srt(ws, dur), encoding="utf-8")
    return destino


def descartar(c: dict, versao: str) -> None:
    """REPROCESSAR: apaga o que já foi gerado desta versão — vídeo, vídeo
    legendado e .srt — para a próxima chamada refazer do zero."""
    base = nome_versao(c, versao)
    nomes = [f"{base}.mp4", f"{base}.srt", *(p.name for p in TRAB.glob(f"{base}_legendado*.mp4"))]
    for nome in nomes:
        with _trava(nome):
            (TRAB / nome).unlink(missing_ok=True)


# a última escolha do popup "Com legenda" é do PERFIL, não do vídeo: vale para
# todo corte, de toda rodada, até a pessoa trocar. Mora em ~/.avelin, ao lado
# do brand.json — gosto de quem usa nunca entra no clone.
ESTILO_SALVO = Path.home() / ".avelin" / "cortes_legenda.json"
_PREVIAS: dict[str, bytes] = {}


def previa_titulo(estilo: dict, texto: str) -> bytes:
    """A headline do popup como PNG TRANSPARENTE de 540×960, desenhada pelo
    MESMO .ass do vídeo — a prévia não reimplementa layout nenhum em CSS. O
    filtro `ass` do ffmpeg pinta a cor mas não grava alfa, então a headline é
    renderizada sobre preto e sobre branco e o alfa sai da diferença:
    a = 1 - (branco - preto), cor = preto / a."""
    import numpy as np  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415
    chave = hashlib.sha1(json.dumps([estilo, texto], sort_keys=True).encode()).hexdigest()
    if chave in _PREVIAS:
        return _PREVIAS[chave]
    cfg = L.com_estilo(F.config(TRAB), estilo)
    with tempfile.TemporaryDirectory() as d:
        ass = Path(d) / "t.ass"
        ass.write_text(L.ass([], 6.0, cfg, texto or " "), encoding="utf-8")
        quadros = []
        for fundo in ("black", "white"):
            png = Path(d) / f"{fundo}.png"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c={fundo}:s=540x960:d=2",
                            "-vf", f"ass={ass}", "-ss", "1.2", "-frames:v", "1", str(png)], check=True)
            quadros.append(np.asarray(Image.open(png).convert("RGB"), dtype=np.float32))
    preto, branco = quadros
    alfa = np.clip(1 - (branco - preto).mean(axis=2) / 255, 0, 1)
    cor = np.where(alfa[..., None] > 0.004, preto / np.maximum(alfa[..., None], 0.004), 0)
    img = np.dstack([np.clip(cor, 0, 255), alfa * 255]).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(img, "RGBA").save(buf, "PNG", optimize=False)
    if len(_PREVIAS) > 64:
        _PREVIAS.clear()
    _PREVIAS[chave] = buf.getvalue()
    return _PREVIAS[chave]


def estilo_salvo() -> dict:
    """O último estilo escolhido no popup — ele reabre nele."""
    try:
        return L.normalizar_estilo(json.loads(ESTILO_SALVO.read_text()))
    except (OSError, json.JSONDecodeError):
        return L.normalizar_estilo(None)


def salvar_estilo(estilo: dict) -> None:
    ESTILO_SALVO.parent.mkdir(parents=True, exist_ok=True)
    ESTILO_SALVO.write_text(json.dumps(estilo, ensure_ascii=False, indent=1))


def exportar(c: dict, versao: str = "original", legendado: bool = False,
             estilo: dict | None = None) -> Path:
    """O corte na versão pedida. Sem legenda é o padrão; `legendado` gera um
    SEGUNDO arquivo com o karaokê queimado — o limpo continua existindo. Com
    `estilo` (o popup "Com legenda"), cada combinação é um arquivo próprio."""
    sufixo = ""
    if legendado:
        sufixo = "_legendado"
        if estilo:
            sufixo += "_" + hashlib.sha1(json.dumps(estilo, sort_keys=True).encode()).hexdigest()[:8]
    destino = TRAB / f"{nome_versao(c, versao)}{sufixo}.mp4"
    ed = edicao(c) if versao == "original" else None
    with _trava(destino.name):
        if ed:
            # o editado é a base: arquivo mais velho que ele é de outra montagem
            if destino.exists() and destino.stat().st_mtime >= ed.stat().st_mtime:
                return destino
            if not legendado:
                shutil.copy2(ed, destino)
                return destino
            ws, dur = _palavras_editado(ed)
            with tempfile.TemporaryDirectory() as d:
                ass = Path(d) / "legenda.ass"
                cfg = L.com_estilo(F.config(TRAB), estilo) if estilo else F.config(TRAB)
                texto = (estilo or {}).get("texto") or c.get("titulo_sugerido")
                ass.write_text(L.ass(ws, dur, cfg, texto), encoding="utf-8")
                tmp = destino.with_suffix(".tmp.mp4")
                subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(ed),
                                "-vf", f"ass={ass}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                                "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", str(tmp)],
                               check=True)
                tmp.rename(destino)
            return destino
        if destino.exists() and destino.stat().st_mtime >= valido_desde():
            return destino
        segs = _plano(c, versao)
        with tempfile.TemporaryDirectory() as d:
            ass = None
            if legendado:
                ws, dur = palavras_da_versao(c, versao)
                ass = Path(d) / "legenda.ass"
                cfg = L.com_estilo(F.config(TRAB), estilo) if estilo else F.config(TRAB)
                texto = (estilo or {}).get("texto") or c.get("titulo_sugerido")
                ass.write_text(L.ass(ws, dur, cfg, texto), encoding="utf-8")
            # fonte horizontal sai em pé, seguindo quem fala (enquadramento.py)
            quadro = None if EQ.vertical(VIDEO) else EQ.plano(VIDEO, *VR.janela(c))
            VR.render(VIDEO, segs, destino, ass, FPS, F.config(TRAB).get("zoom_cortes"), quadro)
        return destino


# ------------------------------------------------------------------ aplicadas

def score_versao(c: dict, versao: str) -> int:
    return ((c.get("variantes") or {}).get(normalizar(c, versao)) or {}).get("score", c["score_final"])


def aplicadas() -> dict[str, str]:
    """id → versão aplicada. Fica no disco para a galeria abrir já com o score
    e o vídeo da recomendação que a pessoa aceitou, mesmo depois de recarregar."""
    p = TRAB / "analise" / "aplicadas.json"
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return {}


def aplicar(c: dict, versao: str) -> None:
    _plano(c, versao)
    d = aplicadas()
    if versao == "original":
        d.pop(c["id"], None)
    else:
        d[c["id"]] = versao
    (TRAB / "analise" / "aplicadas.json").write_text(json.dumps(d, ensure_ascii=False, indent=2))


# ------------------------------------------------------------------ Avelin

def avelin_url() -> str | None:
    """O editor que está rodando agora (o servidor publica em ~/.avelin)."""
    try:
        url = json.loads((Path.home() / ".avelin" / "server.json").read_text())["url"]
        urllib.request.urlopen(f"{url}/api/state", timeout=2)
        return url
    except (OSError, ValueError, KeyError):
        return None


# ------------------------------------------------------------- modo corte

def _editor(garantir: bool = True) -> str:
    """URL do editor do Avelin — sobe um se nenhum estiver no ar."""
    url = avelin_url()
    if url or not garantir:
        return url
    import socket  # noqa: PLC0415
    import time  # noqa: PLC0415
    sk = socket.socket()
    sk.bind(("127.0.0.1", 0))
    porta = sk.getsockname()[1]
    sk.close()
    log = TRAB / "editor" / "servidor.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    subprocess.Popen([sys.executable, str(SKILL / "helpers" / "preview_server.py"), "--port", str(porta)],
                     stdout=open(log, "ab"), stderr=subprocess.STDOUT, start_new_session=True)
    for _ in range(60):
        time.sleep(0.25)
        url = avelin_url()
        if url:
            return url
    raise Recusa("não consegui abrir o editor do Avelin", 503)


def projeto_corte(c: dict) -> Path:
    return TRAB / "editor" / c["id"] / "edit"


def preparar_edicao(c: dict) -> dict:
    """O corte vira um projeto do Avelin JÁ APROVADO: `preview.mp4` é o corte
    pronto (em pé, enquadrado — não se refaz nada a partir da fonte), o texto
    da legenda é o MESMO da galeria (`cut_mapped.json`) e a aba Estilo abre
    sozinha. O vídeo base é congelado na primeira abertura: renderizar de novo
    parte dele, e não do resultado anterior (senão headline e legenda se
    empilhariam a cada rodada)."""
    edit = preparar_projeto(c)
    url = _editor()
    req = urllib.request.Request(f"{url}/api/open", method="POST",
                                 data=json.dumps({"path": str(edit)}).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10).read()
    except OSError as e:
        raise Recusa(f"o editor não abriu o corte: {e}", 502)
    return {"url": f"{url}/?modo=corte", "pasta": str(edit)}


def valido_desde() -> float:
    """Exportado mais velho que isto é de um enquadramento ultrapassado e é
    refeito (`analise/valido_desde`, epoch). Medido em 2026-11-05: o anúncio
    "Trabalho, trabalho…" saiu com o Paulo enquanto a Júlia falava porque a
    geração partiu de um arquivo feito antes da correção."""
    try:
        return float((TRAB / "analise" / "valido_desde").read_text().strip())
    except (OSError, ValueError):
        return 0.0


def preparar_projeto(c: dict) -> Path:
    """O projeto Avelin do corte (ver `preparar_edicao`), sem abrir editor."""
    edit = projeto_corte(c)
    (edit / "transcripts").mkdir(parents=True, exist_ok=True)
    base = edit / "preview.mp4"
    if base.exists() and base.stat().st_mtime < valido_desde():
        # base congelada ANTES da última correção do enquadramento: refaz o
        # projeto do corte em vez de gerar em cima de um quadro errado
        shutil.rmtree(edit)
        (edit / "transcripts").mkdir(parents=True, exist_ok=True)
    if not base.exists():
        src = exportar(c, "original")
        shutil.copy2(src, base)
        ws, _ = palavras_da_versao(c, "original")
        palavras = [{"type": "word", "text": w["w"], "start": float(w["s"]), "end": float(w["e"]),
                     "speaker_id": "speaker_0"} for w in ws]
        (edit / "transcripts" / "cut_mapped.json").write_text(json.dumps(
            {"words": palavras, "language_code": "por",
             "_source": "galeria de cortes — o mesmo texto do corte"}, ensure_ascii=False))
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=r_frame_rate", "-of", "csv=p=0", str(base)], capture_output=True, text=True)
        try:
            n, d = r.stdout.strip().split("/")
            fps = round(float(n) / float(d))
        except ValueError:
            fps = 30
        (edit / "state.json").write_text(json.dumps({
            "project": c.get("titulo_sugerido") or c["id"], "phase": 2, "video": "preview.mp4",
            "editData": "hyperframes/edit-data.json", "captions": "hyperframes/captions.json",
            "finalVideo": "final.mp4", "fps": fps, "awaitingStyle": True, "modoCorte": True,
            "message": "Corte da galeria — escolha o estilo e renderize",
            "origem": {"galeria": str(TRAB), "id": c["id"]}}, ensure_ascii=False, indent=2))
    return edit


# ------------------------------------------------- fila de geração (2º plano)
# "Adicionar legenda e elementos": o popup manda as escolhas no MESMO formato
# do editor (o `style-setup` que o app.js envia) e volta para a galeria na
# hora. Um trabalhador gera UM corte por vez (dois renders juntos deixam a
# máquina lenta e os dois demoram mais) com a Fase 2 do Avelin; o estado fica
# em `analise/fila.json`, então recarregar a página não perde nada.

class _TravaFila:
    """A trava da fila vale ENTRE PROCESSOS, não só entre threads: duas galerias
    abertas no mesmo projeto (uma esquecida numa porta, outra nova) dividem o
    `fila.json`, e cada uma tem o seu trabalhador. Sem o `flock`, as duas liam
    a fila no mesmo instante e pegavam o MESMO pedido. Sem `fcntl` (Windows),
    fica só a trava de thread — lá não há duas galerias no mesmo projeto."""
    def __init__(self):
        self._t = threading.Lock()
        self._fd = None

    def __enter__(self):
        self._t.acquire()
        try:
            import fcntl  # noqa: PLC0415
            self._fd = open(_fila_path().with_suffix(".lock"), "a")
            fcntl.flock(self._fd, fcntl.LOCK_EX)
        except (ImportError, OSError):
            self._fd = None
        return self

    def __exit__(self, *exc):
        if self._fd:
            self._fd.close()          # fechar solta o flock
            self._fd = None
        self._t.release()


def _vivo(pid) -> bool:
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, TypeError, ValueError):
        return False


_FILA_TRAVA = _TravaFila()
_FILA_SINAL = threading.Event()


def _fila_path() -> Path:
    return TRAB / "analise" / "fila.json"


def fila() -> list[dict]:
    try:
        return json.loads(_fila_path().read_text())
    except (OSError, json.JSONDecodeError):
        return []


def _fila_gravar(f: list[dict]) -> None:
    _fila_path().write_text(json.dumps(f, ensure_ascii=False, indent=1))


def enfileirar(c: dict, escolhas: dict | None, cta: str | None = None,
               versao: str = "original") -> dict:
    """Um pedido na fila: `escolhas` (o popup — Fase 2 do Avelin) e/ou `cta`
    (o fecho deste projeto, ver `ctas_projeto`). Um pedido IGUAL ainda na fila
    é trocado pelo novo; um diferente (outro CTA do mesmo corte) fica."""
    import time  # noqa: PLC0415
    tipo = (bool(escolhas), cta or "")
    with _FILA_TRAVA:
        f = [j for j in fila() if not (j["id"] == c["id"] and j["estado"] == "na fila"
                                       and (bool(j.get("escolhas")), j.get("cta") or "") == tipo)]
        job = {"id": c["id"], "titulo": c.get("titulo_sugerido"), "estado": "na fila",
               "escolhas": escolhas or None, "pedido": int(time.time())}
        if cta:
            job.update(cta=cta, versao=versao)
        f.append(job)
        _fila_gravar(f)
    _FILA_SINAL.set()
    return job


def _progresso(edit: Path) -> dict:
    try:
        return json.loads((edit / "progress.json").read_text())
    except (OSError, json.JSONDecodeError):
        return {}


_PALAVRAS: dict[str, dict] = {}


def palavras_corte(c: dict) -> dict:
    """As palavras do corte para a prévia ao vivo, `[{w, s, e}]` em segundos do
    próprio corte. Se o projeto do corte já existe, vale o `cut_mapped.json`
    dele — é EXATAMENTE o texto que a Fase 2 transforma em legenda (e, num
    corte já gerado, a versão editada à mão traria a legenda queimada de
    volta pela escuta). Senão, `palavras_da_versao(c, "original")`, a mesma
    origem que `preparar_projeto` grava. Guardadas em memória: a escuta é
    cacheada em disco, mas o alinhamento roda de novo a cada pedido."""
    tr = projeto_corte(c) / "transcripts" / "cut_mapped.json"
    if tr.exists():
        try:
            ws = json.loads(tr.read_text()).get("words") or []
            r = {"palavras": [{"w": w["text"], "s": w["start"], "e": w["end"]} for w in ws
                              if w.get("type", "word") == "word"], "origem": "projeto"}
            # a base LIMPA do projeto (o que a Fase 2 compõe): a prévia toca ela,
            # não o arquivo da galeria, que num corte já gerado tem legenda queimada
            if (projeto_corte(c) / "preview.mp4").exists():
                r["base"] = f"/previa-base/{c['id']}.mp4"
            return r
        except (OSError, json.JSONDecodeError, KeyError):
            pass
    if c["id"] not in _PALAVRAS:
        ws, dur = palavras_da_versao(c, "original")
        _PALAVRAS[c["id"]] = {"palavras": [{"w": w["w"], "s": w["s"], "e": w["e"]} for w in ws],
                              "dur": dur, "origem": "galeria"}
    return _PALAVRAS[c["id"]]


def _semear_edit_data(edit: Path, escolhas: dict) -> None:
    """Pré-responde as perguntas que a Fase 2 faria A UMA SESSÃO DE IA.

    Nesta porta não há chat: um `sys.exit` pedindo "leia a fala e decida"
    deixaria o trabalho em erro. Então, no lugar da IA:
      - EFEITOS DE CONTEÚDO (checklist, gráfico…): `efeitosRevisados` — o motor
        põe só os de movimento, que ele posiciona sozinho;
      - CTA sem momento: `momentoRevisado` — o CTA fecha o vídeo (é o mesmo
        padrão que a Fase 2 aplica quando a fala não tem chamada).
    O resto do edit-data (medidas, legendas) é da Fase 2 e fica intocado."""
    p = edit / "hyperframes" / "edit-data.json"
    try:
        data = json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        data = {}
    data["efeitosRevisados"] = True
    if ((escolhas.get("cta") or {}).get("modelo")):
        cta = data.setdefault("cta", {})
        if cta.get("start") is None and cta.get("momento") is None:
            cta["momentoRevisado"] = True
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def _gerar(c: dict, escolhas: dict) -> str:
    """Roda a Fase 2 do Avelin no projeto do corte com as escolhas do popup e
    registra o resultado como a versão editada do corte. Devolve o arquivo
    publicado na galeria (o que o botão Baixar entrega)."""
    edit = preparar_projeto(c)
    pedido = {"type": "style-setup", "rerender": (edit / "final.mp4").exists(), **escolhas}
    (edit / "preview_style.json").write_text(json.dumps(pedido, ensure_ascii=False, indent=2))
    _semear_edit_data(edit, escolhas)
    log = edit / "fase2.log"
    with open(log, "w") as fo:
        r = subprocess.run([sys.executable, str(SKILL / "helpers" / "phase2.py"), str(edit)],
                           stdout=fo, stderr=subprocess.STDOUT, cwd=str(SKILL))
    final = edit / "final.mp4"
    if r.returncode or not final.exists() or final.stat().st_mtime < log.stat().st_mtime - 1:
        cauda = [l for l in log.read_text(errors="ignore").splitlines() if l.strip()][-6:]
        raise RuntimeError(" / ".join(cauda)[-600:] or f"Fase 2 saiu com código {r.returncode}")
    estado_edicao(c)                       # registra em edicao/edicoes.json
    return exportar(c, "original").name    # o arquivo da galeria passa a ser o editado


# ------------------------------------------- CTA do projeto (fecho do vídeo)
# Um projeto pode trazer os PRÓPRIOS CTAs: trechos gravados da pessoa pedindo o
# clique (`edicao/_ctas/ctas.json` + os .mp4), montados no fim do corte pelo kit
# do projeto (`edicao/_kit/montar.py`, HyperFrames: botão dourado "Acesse
# agora", cursor e clique). Sem o ctas.json a galeria nem pergunta.

def ctas_projeto() -> dict | None:
    p = TRAB / "edicao" / "_ctas" / "ctas.json"
    try:
        d = json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    itens = [x for x in d.get("ctas") or [] if (p.parent / x.get("arquivo", "")).is_file()]
    if not itens:
        return None
    return {**d, "ctas": itens, "_pasta": p.parent}


def _fecho_pronto(cfg: dict, item: dict) -> Path:
    """O CTA com o botão JÁ MONTADO, uma vez por CTA (`_ctas/prontos/<id>.mp4`).
    Ele é igual em todo corte, então refazer a montagem (HyperFrames, ~1 min) a
    cada pedido era tempo jogado fora — pergunta do usuário, 2026-11-05. Refaz
    só quando o clipe, o ctas.json ou o kit mudam."""
    pasta = cfg["_pasta"]
    kit = (pasta / (cfg.get("kit") or "../_kit/montar.py")).resolve()
    if not kit.is_file():
        raise RuntimeError(f"não achei o kit de montagem ({kit})")
    clipe = pasta / item["arquivo"]
    destino = pasta / "prontos" / f"{item['id']}.mp4"
    fontes = [clipe, pasta / "ctas.json", kit]
    if destino.exists() and destino.stat().st_mtime >= max(f.stat().st_mtime for f in fontes):
        return destino
    with _trava(f"fecho-{item['id']}"):
        if destino.exists() and destino.stat().st_mtime >= max(f.stat().st_mtime for f in fontes):
            return destino
        work = pasta / "render" / f"_fecho_{item['id']}"
        if work.exists():
            shutil.rmtree(work)
        work.mkdir(parents=True)
        (work / "seg0.mp4").symlink_to(clipe)
        botao = cfg.get("botao") or {}
        (work / "spec.json").write_text(json.dumps({
            "titulo": f"CTA {item.get('nome', item['id'])}", "segs": ["seg0.mp4"],
            "cta": {"seg": 0, "texto": botao.get("texto", "Acesse agora"),
                    "sub": botao.get("sub", "CLIQUE NO LINK"),
                    "entra": item.get("entra", 0.25), "clique": item["clique"]}},
            ensure_ascii=False, indent=1))
        log = work / "montar.log"
        with open(log, "w") as fo:
            r = subprocess.run([sys.executable, str(kit), str(work)], stdout=fo,
                               stderr=subprocess.STDOUT, cwd=str(work))
        pronto = work / f"{work.name}.mp4"
        if r.returncode or not pronto.exists():
            cauda = [l for l in log.read_text(errors="ignore").splitlines() if l.strip()][-6:]
            raise RuntimeError(" / ".join(cauda)[-600:] or f"montagem do CTA saiu com código {r.returncode}")
        destino.parent.mkdir(exist_ok=True)
        shutil.copy2(pronto, destino)
        shutil.rmtree(work, ignore_errors=True)
    return destino


def _com_cta(c: dict, base: Path, cta_id: str, nome: str) -> str:
    """Corte + o CTA escolhido no fim, publicado como `<nome>_cta-<id>.mp4` —
    um arquivo à parte: o corte limpo continua o mesmo. A emenda é uma passada
    só de ffmpeg (segundos): o fecho já vem montado (`_fecho_pronto`)."""
    cfg = ctas_projeto()
    item = next((x for x in (cfg or {}).get("ctas", []) if x["id"] == cta_id), None)
    if not item:
        raise RuntimeError(f"CTA {cta_id!r} não existe neste projeto")
    fecho = _fecho_pronto(cfg, item)
    destino = TRAB / f"{nome}_cta-{cta_id}.mp4"
    tmp = destino.with_suffix(".tmp.mp4")
    # o corte pode vir em outro fps/tamanho (60 fps da fonte): normaliza os dois
    # lados e emenda com o filtro concat; volume medido no vídeo INTEIRO
    norm = "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,fps=30,setsar=1,format=yuv420p"
    fc = (f"[0:v]{norm}[v0];[1:v]{norm}[v1];"
          "[0:a]aresample=44100,aformat=channel_layouts=stereo[a0];"
          "[1:a]aresample=44100,aformat=channel_layouts=stereo[a1];"
          "[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a];"
          "[a]loudnorm=I=-14:TP=-1:LRA=11,aresample=44100[ao]")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(base), "-i", str(fecho),
                    "-filter_complex", fc, "-map", "[v]", "-map", "[ao]",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                    "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-movflags", "+faststart", str(tmp)],
                   check=True)
    tmp.replace(destino)
    return destino.name


def _marcar_job(job: dict, **campos) -> None:
    with _FILA_TRAVA:
        f = fila()
        for j in f:
            if j["id"] == job["id"] and j.get("pedido") == job["pedido"]:
                j.update(campos)
        _fila_gravar(f)


def _executar(c: dict, job: dict) -> str:
    """Escolhas do popup → Fase 2 (vira a versão editada do corte); CTA → o
    kit monta o fecho por cima da base (a Fase 2, se houve, senão o corte)."""
    arq = None
    if job.get("escolhas"):
        arq = _gerar(c, job["escolhas"])
    if not job.get("cta"):
        if not arq:
            raise RuntimeError("pedido vazio")
        return arq
    _marcar_job(job, fase="cta")
    if arq:
        base, nome = TRAB / arq, base_nome(c)
    else:
        versao = normalizar(c, job.get("versao") or "original")
        base, nome = exportar(c, versao), nome_versao(c, versao)
    return _com_cta(c, base, job["cta"], nome)


def _trabalhador() -> None:
    import time  # noqa: PLC0415
    while True:
        _FILA_SINAL.wait(5)
        _FILA_SINAL.clear()
        with _FILA_TRAVA:
            f = fila()
            # um "gerando" que sobrou de um servidor que MORREU volta para a fila;
            # o de outra galeria viva no mesmo projeto é dela (pegá-lo de volta
            # rodaria a mesma Fase 2 duas vezes na mesma pasta)
            for j in f:
                if j["estado"] == "gerando" and j.get("pid") != os.getpid() and not _vivo(j.get("pid")):
                    j["estado"] = "na fila"
            prox = next((j for j in f if j["estado"] == "na fila"), None)
            if prox:
                prox.update(estado="gerando", inicio=int(time.time()), pid=os.getpid())
            _fila_gravar(f)
        if not prox:
            continue
        c = next((x for x in cortes()["cortes"] if x["id"] == prox["id"]), None)
        try:
            if not c:
                raise RuntimeError("corte não encontrado")
            arq = _executar(c, prox)
            novo = {"estado": "pronto", "arquivo": arq, "url": f"/baixar/{arq}"}
        except Exception as e:  # noqa: BLE001
            novo = {"estado": "erro", "erro": str(e)}
        with _FILA_TRAVA:
            f = fila()
            for j in f:
                if j["id"] == prox["id"] and j.get("pedido") == prox["pedido"]:
                    j.update(novo, fim=int(time.time()))
            _fila_gravar(f)
        _FILA_SINAL.set()


def estado_edicao(c: dict) -> dict:
    """Pronto quando o `final.mp4` do projeto é mais novo que o vídeo base: aí
    ele vira a versão editada do corte na galeria (todo download sai dele)."""
    edit = projeto_corte(c)
    final, base = edit / "final.mp4", edit / "preview.mp4"
    prog = {}
    try:
        prog = json.loads((edit / "progress.json").read_text())
    except (OSError, json.JSONDecodeError):
        pass
    pronto = final.exists() and base.exists() and final.stat().st_mtime > base.stat().st_mtime
    if pronto:
        mapa = TRAB / "edicao" / "edicoes.json"
        mapa.parent.mkdir(parents=True, exist_ok=True)
        try:
            d = json.loads(mapa.read_text())
        except (OSError, json.JSONDecodeError):
            d = {}
        if d.get(c["id"]) != str(final):
            d[c["id"]] = str(final)
            mapa.write_text(json.dumps(d, ensure_ascii=False))
    return {"pronto": pronto, "progresso": prog.get("tasks") or prog}


def importar_avelin(c: dict, versao: str, forcar: bool = False) -> dict:
    """UM projeto do Avelin por vídeo longo — `<stem>_cortes/avelin/` —,
    reaproveitado a cada corte, sem cópia de vídeo nenhuma: o EDL aponta para
    a fonte original (o Avelin já guarda fonte por caminho absoluto) e já traz
    o corte montado — o gancho puxado como um trecho a mais na frente e os
    respiros como `breaths`, o formato que o render do Avelin expande.

    Ao importar o próximo corte, o `final.mp4` do anterior vai para
    `editados/` e o resto do `edit/` (renders, proxies, segmentos — centenas de
    MB) é apagado. Um corte ainda sem final não é apagado sem confirmação."""
    url = avelin_url()
    if not url:
        raise Recusa("O Avelin não está aberto. Abra o editor e tente de novo.", 503)
    segs_ok = _plano(c, versao)   # valida a versão antes de mexer em disco
    pasta, editados = TRAB / "avelin", TRAB / "editados"
    edit = pasta / "edit"
    origem = edit / "cortes_origem.json"
    if edit.exists():
        anterior = json.loads(origem.read_text()) if origem.exists() else {}
        final = edit / "final.mp4"
        if final.exists():
            editados.mkdir(exist_ok=True)
            shutil.move(str(final), editados / f"{anterior.get('nome', 'corte')}.mp4")
        elif anterior and not forcar:
            raise Recusa("outro corte em edição", 409, emEdicao=anterior.get("titulo"))
        shutil.rmtree(edit)
    (edit / "transcripts").mkdir(parents=True)

    a, b = VR.janela(c)
    stem = VIDEO.stem
    # a fatia do transcrito, nos tempos da fonte: o Avelin não paga outra
    # transcrição e não lê uma hora de texto para editar 30 segundos
    fonte = json.loads((TRAB / "transcripts" / f"{stem}.json").read_text())
    ws = [w for w in fonte.get("words", []) if a - 1.0 <= float(w["start"]) <= b + 1.0]
    (edit / "transcripts" / f"{stem}.json").write_text(json.dumps(
        {**{k: v for k, v in fonte.items() if k not in ("words", "text")},
         "text": " ".join(w["text"] for w in ws if w.get("type") == "word"), "words": ws},
        ensure_ascii=False))

    # o corte já montado: um range por trecho da versão. As emendas internas
    # (gancho → corte, respiro e falha removidos) vão com J-cut zerado — é o que
    # o `render.expand_breaths` faz com as emendas que ele cria: sem isso o áudio
    # do trecho seguinte puxaria de volta um pedaço do que foi tirado
    ranges = []
    ps = VR.pecas(versao)
    gancho = "gancho" in ps
    for k, (sa, sb) in enumerate(segs_ok):
        r = {"source": stem, "start": round(sa, 3), "end": round(sb, 3),
             "beat": "HOOK" if gancho and k == 0 else "CORTE"}
        if k == 0:
            r["quote"] = c["gancho"].get("frase", "") if gancho else c.get("abertura", "")
            r["reason"] = (f"garimpo de cortes: {c.get('titulo_sugerido', '')} "
                           f"({VR.nome(versao).lower()}, nota {score_versao(c, versao)})")
        if k > 0:
            r["jcut_lead_frames"] = 0
        if k < len(segs_ok) - 1:
            r["jcut_tail_frames"] = 0
        ranges.append(r)
    (edit / "edl.json").write_text(json.dumps(
        {"version": 1, "sources": {stem: str(VIDEO)}, "ranges": ranges},
        ensure_ascii=False, indent=2))

    g = c.get("gancho") or {}
    dicas = {"tem": "o gancho já abre o corte",
             "puxar": "o gancho JÁ FOI puxado para o início" if versao.startswith("gancho")
             else f"gancho a puxar: {g.get('instrucao', '')}",
             "regravar": "não há gancho no trecho; sugestões para gravar: "
             + " / ".join(s["texto"] if isinstance(s, dict) else s for s in g.get("sugestoes") or [])}
    brief = (f"Corte importado do garimpo de cortes: \"{c.get('titulo_sugerido', '')}\", "
             f"{a:.2f}–{b:.2f}s da fonte (que tem {duracao(VIDEO) / 60:.0f} min — trabalhe SÓ neste "
             f"trecho). O edl.json já traz o corte montado"
             + (", com o gancho puxado para o início" if gancho else "")
             + (", sem respiros" if "respiros" in ps else "")
             + (", sem os erros de fala (" + "; ".join(t["texto"] for t in c.get("fala") or []) + ")"
                if "falhas" in ps and c.get("fala") else "")
             + f". Formato vertical (short). Gancho: {dicas.get(g.get('tipo'), '')}. "
             "Siga a Fase 1 a partir deste EDL: revisar o corte, cor e aprovação.")
    (edit / "state.json").write_text(json.dumps({
        "project": c.get("titulo_sugerido") or c["id"], "phase": 1,
        "video": "preview_proxy.mp4", "edl": "edl.json",
        "message": "Corte importado do garimpo — preparando a Fase 1",
        "awaitingStyle": False, "awaitingStart": True, "sources": [str(VIDEO)],
        "brief": brief, "format": "short"}, ensure_ascii=False, indent=2))
    origem.write_text(json.dumps({"id": c["id"], "titulo": c.get("titulo_sugerido"),
                                  "versao": versao, "nome": nome_versao(c, versao),
                                  "trechos": [list(x) for x in segs_ok]},
                                 ensure_ascii=False, indent=2))

    req = urllib.request.Request(f"{url}/api/open", method="POST",
                                 data=json.dumps({"path": str(pasta)}).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10)
    except OSError as e:
        raise Recusa(f"o Avelin não abriu o projeto: {e}", 502)
    return {"url": url, "pasta": str(pasta)}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silencioso: o terminal é do usuário
        pass

    def _json(self, dados, code=200):
        b = json.dumps(dados, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _arquivo(self, p: Path, tipo: str, baixar: str | None = None):
        tam = p.stat().st_size
        ini, fim = 0, tam - 1
        rng = self.headers.get("Range")
        m = re.match(r"bytes=(\d*)-(\d*)", rng or "")
        if m:
            if m.group(1):
                ini = int(m.group(1))
                fim = int(m.group(2)) if m.group(2) else tam - 1
            else:
                ini = max(0, tam - int(m.group(2)))
            fim = min(fim, tam - 1)
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {ini}-{fim}/{tam}")
        else:
            self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(fim - ini + 1))
        if baixar:
            self.send_header("Content-Disposition", f"attachment; filename=\"{baixar}\"")
        self.end_headers()
        with p.open("rb") as f:
            f.seek(ini)
            falta = fim - ini + 1
            try:
                while falta > 0:
                    bloco = f.read(min(1 << 20, falta))
                    if not bloco:
                        break
                    self.wfile.write(bloco)
                    falta -= len(bloco)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def do_GET(self):
        path = unquote(urlparse(self.path).path)
        # ---- O CATÁLOGO DE ESTILOS DO EDITOR, servido aqui também ----
        # A galeria oferece as MESMAS escolhas do editor (assets/shared/estilos.js,
        # `window.AVE_ESTILOS`), e o módulo pede o que desenha pelos MESMOS
        # caminhos do preview_server.py: /shared/ (o módulo e a folha dele),
        # /styles/ (folhas, scripts, variants.json e fonts/ do render), /assets/
        # SÓ com o que as prévias usam (as PNGs do CTA, demos.js, a camada
        # local — o app do editor não sai daqui) e /api/localfonts. Outra árvore
        # de URLs seria uma segunda configuração a manter igual nos dois lados.
        # `no-store`: um estilos.js editado não pode vir do cache do navegador.
        if path == "/api/localfonts":
            try:
                import local_fonts
                return self._json({"families": local_fonts.catalog()})
            except Exception as exc:          # sem fontes locais, só as do Google
                return self._json({"families": [], "error": str(exc)[:200]})
        for pre, raiz, so in (("/shared/", SKILL / "assets" / "shared", None),
                              ("/styles/", SKILL / "assets" / "styles", None),
                              ("/assets/", SKILL / "assets" / "preview",
                               {"cta-card.png", "cta-simples.png", "demos.js", "styles.local.js"})):
            if path.startswith(pre):
                p = (raiz / path[len(pre):]).resolve()
                tipo = {".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
                        ".json": "application/json; charset=utf-8", ".png": "image/png",
                        ".ttf": "font/ttf", ".otf": "font/otf", ".woff": "font/woff",
                        ".woff2": "font/woff2"}.get(p.suffix.lower())
                if (not p.is_relative_to(raiz.resolve()) or not p.is_file() or not tipo
                        or (so and p.name not in so)):
                    return self.send_error(404)
                b = p.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", tipo)
                self.send_header("Content-Length", str(len(b)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(b)
                return
        if path in ("/", "/index.html"):
            return self._arquivo(PAGINA, "text/html; charset=utf-8")
        if path == "/icone.png":
            return self._arquivo(ICONE, "image/png")
        if path == "/media":
            return self._arquivo(VIDEO, "video/mp4")
        if path == "/api/titulo-previa.png":
            q = parse_qs(urlparse(self.path).query)
            try:
                estilo = json.loads(q.get("e", ["{}"])[0])
            except json.JSONDecodeError:
                estilo = {}
            b = previa_titulo(estilo if isinstance(estilo, dict) else {}, q.get("t", [""])[0][:400])
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(b)))
            self.send_header("Cache-Control", "max-age=3600")
            self.end_headers()
            self.wfile.write(b)
            return
        if path == "/api/legenda-modelos":
            return self._json({"modelos": L.MODELOS, "salvo": estilo_salvo(),
                               "forca": L.FORCA.pattern})
        if path == "/api/palavras":
            # a legenda AO VIVO do popup "Com legenda" precisa das palavras do
            # corte no tempo DELE (0 = início do corte), as mesmas que a Fase 2
            # vai queimar — ver `palavras_corte`
            q = parse_qs(urlparse(self.path).query)
            c = next((x for x in cortes()["cortes"] if x["id"] == (q.get("id") or [""])[0]), None)
            if not c:
                return self._json({"erro": "corte não encontrado"}, 404)
            try:
                return self._json(palavras_corte(c))
            except ImportError:
                return self._json({"palavras": [], "erro": "sem mlx-whisper"})
        if path == "/api/ctas":
            # os CTAs DESTE projeto; sem ctas.json, lista vazia — e a galeria não
            # pergunta (200 e não 404: um 404 sujaria o console de toda galeria)
            d = ctas_projeto()
            if not d:
                return self._json({"ctas": []})
            return self._json({"ctas": [{k: x.get(k) for k in ("id", "nome", "fala")} for x in d["ctas"]],
                               "botao": d.get("botao")})
        if path == "/api/marca":
            # cores e fontes do PROJETO (marca.json no trabalho): o popup parte delas
            try:
                return self._json(json.loads((TRAB / "marca.json").read_text()))
            except (OSError, json.JSONDecodeError):
                return self._json({})
        if path == "/api/fila":
            itens = fila()
            for j in itens:
                if j["estado"] == "gerando" and j.get("fase") != "cta" and j.get("escolhas"):
                    p = _progresso(TRAB / "editor" / j["id"] / "edit")
                    j["pct"], j["detalhe"] = p.get("pct"), p.get("detail") or p.get("label")
            return self._json({"fila": itens})
        if path == "/api/editar/estado":
            q = parse_qs(urlparse(self.path).query)
            c = next((x for x in cortes()["cortes"] if x["id"] == (q.get("id") or [""])[0]), None)
            if not c:
                return self._json({"erro": "corte não encontrado"}, 404)
            return self._json(estado_edicao(c))
        if path == "/api/processando":
            with _TRAVA:
                return self._json({k: v[-1] for k, v in _TRABALHOS.items() if v})
        if path == "/api/cortes":
            d = cortes()
            por_id = {c["id"]: c for c in d["cortes"]}
            ap = {k: normalizar(por_id[k], v) for k, v in aplicadas().items() if k in por_id}
            horiz = not EQ.vertical(VIDEO)
            # ?v=mtime: o arquivo refeito tem o MESMO nome, e sem o carimbo o
            # navegador seguia tocando o enquadramento antigo do cache
            exp = {c["id"]: f"/arquivo/{base_nome(c)}.mp4?v={int((TRAB / f'{base_nome(c)}.mp4').stat().st_mtime)}"
                   for c in d["cortes"] if horiz and (TRAB / f"{base_nome(c)}.mp4").exists()}
            for c in d["cortes"]:          # o editado à mão manda na duração mostrada
                ed = edicao(c)
                if ed:
                    # editado à mão: as versões do garimpo (gancho, respiros,
                    # falhas) refariam o corte a partir da fonte e jogariam a
                    # edição fora — só o original (o editado) fica na tela
                    c["editado"] = True
                    c["dur"] = round(duracao(ed), 1)
                    orig = (c.get("variantes") or {}).get("original") or {"score": c.get("score_final")}
                    c["variantes"] = {"original": {**orig, "dur": c["dur"]}}
                    c["pecas"] = {k: None for k in (c.get("pecas") or {})}
                    c["respiros"], c["fala"] = [], []
            d.update({"horizontal": horiz, "exportados": exp, "baixados": sorted(baixados()),
                      "video": VIDEO.name, "duracao": duracao(VIDEO), "pasta": str(TRAB),
                      "aplicadas": {k: v for k, v in ap.items()
                                    if v != "original" and not edicao(por_id[k])}})
            return self._json(d)
        if path.startswith("/previa-base/"):     # a base limpa do projeto do corte
            cid = Path(path[len("/previa-base/"):]).stem
            c = next((x for x in cortes()["cortes"] if x["id"] == cid), None)
            p = projeto_corte(c) / "preview.mp4" if c else None
            if p and p.exists():
                return self._arquivo(p, "video/mp4")
        if path.startswith("/thumb/"):
            p = TRAB / "analise" / "thumbs" / Path(path[len("/thumb/"):]).name
            if p.exists():
                return self._arquivo(p, "image/jpeg")
        if path.startswith("/arquivo/"):          # tocar no player, sem baixar
            p = TRAB / Path(path[len("/arquivo/"):]).name
            if p.exists() and p.suffix == ".mp4":
                return self._arquivo(p, "video/mp4")
        if path.startswith("/baixar/"):
            p = TRAB / Path(path[len("/baixar/"):]).name
            tipos = {".mp4": "video/mp4", ".srt": "application/x-subrip; charset=utf-8"}
            if p.exists() and p.suffix in tipos:
                marcar_baixado(p.name)
                return self._arquivo(p, tipos[p.suffix], baixar=p.name)
        self.send_error(404)

    def do_POST(self):
        path = urlparse(self.path).path
        corpo = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        c = next((x for x in cortes()["cortes"] if x["id"] == corpo.get("id")), None)
        if path in ("/api/exportar", "/api/avelin", "/api/aplicar", "/api/editar", "/api/gerar") and not c:
            return self._json({"erro": "corte não encontrado"}, 404)
        versao = normalizar(c, corpo.get("versao") or "original") if c else "original"
        rotulo = str(corpo.get("rotulo") or "Processando…")[:60]
        if c and path in ("/api/exportar", "/api/avelin"):
            with _TRAVA:
                _TRABALHOS.setdefault(c["id"], []).append(rotulo)
        try:
            if path == "/api/editar":
                return self._json(preparar_edicao(c))
            if path == "/api/gerar":
                cta = corpo.get("cta") or None
                if cta and not any(x["id"] == cta for x in (ctas_projeto() or {}).get("ctas", [])):
                    return self._json({"erro": f"CTA {cta!r} não existe neste projeto"}, 400)
                escolhas = corpo.get("escolhas") or None
                if not escolhas and not cta:
                    return self._json({"erro": "nada a gerar"}, 400)
                return self._json(enfileirar(c, escolhas, cta, versao))
            if path == "/api/avelin":
                return self._json(importar_avelin(c, versao, bool(corpo.get("forcar"))))
            if path == "/api/legenda-estilo":
                salvar_estilo({k: v for k, v in (corpo.get("estilo") or {}).items() if k != "texto"})
                return self._json({"ok": True})
            if path == "/api/aplicar":
                aplicar(c, versao)
                return self._json({"ok": True, "score": score_versao(c, versao)})
            if path == "/api/exportar":
                if corpo.get("refazer"):
                    descartar(c, versao)
                if corpo.get("formato") == "srt":
                    p = legenda_srt(c, versao)
                else:
                    legendado = corpo.get("formato") == "legendado"
                    estilo = corpo.get("estilo") if legendado and isinstance(corpo.get("estilo"), dict) else None
                    if estilo:
                        salvar_estilo({k: v for k, v in estilo.items() if k != "texto"})
                    p = exportar(c, versao, legendado=legendado, estilo=estilo)
                    # quem pediu para APLICAR não depende de a página continuar
                    # aberta até o fim: o servidor registra ao terminar
                    if corpo.get("aplicar"):
                        aplicar(c, versao)
                return self._json({"arquivo": p.name, "url": f"/baixar/{p.name}",
                                   "tocar": f"/arquivo/{p.name}"})
        except Recusa as e:
            return self._json({"erro": str(e), **e.extra}, e.code)
        except subprocess.CalledProcessError as e:
            return self._json({"erro": f"ffmpeg falhou ({e.returncode})"}, 500)
        except ImportError:
            return self._json({"erro": "a legenda precisa do mlx-whisper (uv sync)"}, 500)
        finally:
            if c and path in ("/api/exportar", "/api/avelin"):
                with _TRAVA:
                    lista = _TRABALHOS.get(c["id"], [])
                    if rotulo in lista:
                        lista.remove(rotulo)
        self.send_error(404)


def main() -> None:
    global VIDEO, TRAB
    ap = argparse.ArgumentParser(description="Tela de cortes: ver, ouvir e baixar.")
    ap.add_argument("video", type=Path)
    ap.add_argument("--trabalho", type=Path)
    ap.add_argument("--port", type=int, default=4830)
    a = ap.parse_args()
    VIDEO = a.video.resolve()
    TRAB = (a.trabalho or F.pasta_trabalho(VIDEO)).resolve()
    global FPS
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=r_frame_rate", "-of", "csv=p=0", str(VIDEO)],
                       capture_output=True, text=True).stdout.strip()
    try:
        n, d = r.split("/")
        FPS = float(n) / float(d)
    except ValueError:
        pass
    threading.Thread(target=_trabalhador, daemon=True, name="fila-geracao").start()
    # a galeria pede o módulo de estilos, as folhas, os scripts e as fontes do
    # render de uma vez: com a fila padrão (5) o macOS recusava conexões e os
    # cartões do motor `palavra` saíam vazios (ERR_CONNECTION_RESET no console)
    ThreadingHTTPServer.request_queue_size = 64
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    print(f"Avelin — cortes → http://127.0.0.1:{a.port}  ({VIDEO.name})", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()

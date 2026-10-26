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
import hashlib
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
from urllib.parse import unquote, urlparse

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


def palavras_da_versao(c: dict, versao: str) -> tuple[list[dict], float]:
    """A legenda da versão: texto do transcrito, tempo de ouvir o corte, e cada
    palavra levada para onde ela cai no vídeo montado."""
    a, b = VR.janela(c)
    alinhadas = L.alinhar(c.get("palavras") or [], L.ouvir(VIDEO, a, b), b - a)
    segs = _plano(c, versao)
    return VR.remapear(alinhadas, a, segs, FPS), VR.duracao(segs, FPS)


def legenda_srt(c: dict, versao: str = "original") -> Path:
    destino = TRAB / f"{nome_versao(c, versao)}.srt"
    with _trava(destino.name):
        if not destino.exists():
            ws, dur = palavras_da_versao(c, versao)
            destino.write_text(L.srt(ws, dur), encoding="utf-8")
    return destino


def descartar(c: dict, versao: str) -> None:
    """REPROCESSAR: apaga o que já foi gerado desta versão — vídeo, vídeo
    legendado e .srt — para a próxima chamada refazer do zero."""
    base = nome_versao(c, versao)
    for nome in (f"{base}.mp4", f"{base}_legendado.mp4", f"{base}.srt"):
        with _trava(nome):
            (TRAB / nome).unlink(missing_ok=True)


def exportar(c: dict, versao: str = "original", legendado: bool = False) -> Path:
    """O corte na versão pedida. Sem legenda é o padrão; `legendado` gera um
    SEGUNDO arquivo com o karaokê queimado — o limpo continua existindo."""
    destino = TRAB / f"{nome_versao(c, versao)}{'_legendado' if legendado else ''}.mp4"
    with _trava(destino.name):
        if destino.exists():
            return destino
        segs = _plano(c, versao)
        with tempfile.TemporaryDirectory() as d:
            ass = None
            if legendado:
                ws, dur = palavras_da_versao(c, versao)
                ass = Path(d) / "legenda.ass"
                ass.write_text(L.ass(ws, dur, F.config(TRAB), c.get("titulo_sugerido")), encoding="utf-8")
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
        if path in ("/", "/index.html"):
            return self._arquivo(PAGINA, "text/html; charset=utf-8")
        if path == "/icone.png":
            return self._arquivo(ICONE, "image/png")
        if path == "/media":
            return self._arquivo(VIDEO, "video/mp4")
        if path == "/api/processando":
            with _TRAVA:
                return self._json({k: v[-1] for k, v in _TRABALHOS.items() if v})
        if path == "/api/cortes":
            d = cortes()
            por_id = {c["id"]: c for c in d["cortes"]}
            ap = {k: normalizar(por_id[k], v) for k, v in aplicadas().items() if k in por_id}
            d.update({"video": VIDEO.name, "duracao": duracao(VIDEO), "pasta": str(TRAB),
                      "aplicadas": {k: v for k, v in ap.items() if v != "original"}})
            return self._json(d)
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
                return self._arquivo(p, tipos[p.suffix], baixar=p.name)
        self.send_error(404)

    def do_POST(self):
        path = urlparse(self.path).path
        corpo = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        c = next((x for x in cortes()["cortes"] if x["id"] == corpo.get("id")), None)
        if path in ("/api/exportar", "/api/avelin", "/api/aplicar") and not c:
            return self._json({"erro": "corte não encontrado"}, 404)
        versao = normalizar(c, corpo.get("versao") or "original") if c else "original"
        rotulo = str(corpo.get("rotulo") or "Processando…")[:60]
        if c and path in ("/api/exportar", "/api/avelin"):
            with _TRAVA:
                _TRABALHOS.setdefault(c["id"], []).append(rotulo)
        try:
            if path == "/api/avelin":
                return self._json(importar_avelin(c, versao, bool(corpo.get("forcar"))))
            if path == "/api/aplicar":
                aplicar(c, versao)
                return self._json({"ok": True, "score": score_versao(c, versao)})
            if path == "/api/exportar":
                if corpo.get("refazer"):
                    descartar(c, versao)
                if corpo.get("formato") == "srt":
                    p = legenda_srt(c, versao)
                else:
                    p = exportar(c, versao, legendado=corpo.get("formato") == "legendado")
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
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    print(f"Avelin — cortes → http://127.0.0.1:{a.port}  ({VIDEO.name})", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()

"""Avelin preview server — serves the standard editing interface + session media.

The interface app (assets/preview/) is IMMUTABLE and lives in the skill repo;
per-session it is fed by data only:
  - <edit>/state.json          written by the skill (phase, files, message)
  - <edit>/edl.json            the cut (segments shown/trimmed on the timeline)
  - <edit>/preview.mp4             current render (played + scrubbed)
  - <edit>/preview_edits.json  WRITTEN BY THE UI when the user saves timeline
                               adjustments — the skill reads, validates, applies
                               and re-renders. The UI never touches edl.json.
  - <edit>/preview_style.json  WRITTEN BY THE UI at the Fase 1 → Fase 2 gate:
                               editing style, caption style, edit elements.

Routes:
  /                     the app (from <skill>/assets/preview/)
  /assets/<file>        app files (css/js/logo)
  /styles/<file>        camada de estilo COMPARTILHADA com o render (assets/styles/)
  /media/<path>         files under --root (the edit dir) — Range supported
  /gen/waveform.json    min/max audio peaks of preview.mp4 (auto-(re)generated)
  /gen/words.json       transcrito DO CORTE com a folga medida de cada fronteira
  /gen/thumbs/<n>.jpg   timeline filmstrip thumbs (auto-generated, 1 per 2s)
  /api/state    GET     state.json + mtimes (UI polls this to hot-reload)
  /api/save     POST    body → <edit>/preview_edits.json (atomic), or
                        <edit>/preview_style.json when body.type=="style-setup"

Usage:
    uv run helpers/preview_server.py --root <videos_dir>/edit [--port 4820]
"""
from __future__ import annotations

import argparse
import array
import json
import re
import shutil
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import progress  # noqa: E402

APP_DIR = Path(__file__).resolve().parent.parent / "assets" / "preview"
# A CAMADA DE ESTILO COMPARTILHADA — as mesmas folhas que o render usa.
# Servi-las aqui é o que permite a prévia desenhar a legenda de verdade em vez
# de uma imitação: se houvesse uma cópia no editor, ela começaria igual e
# divergiria na primeira correção feita só de um lado.
STYLE_DIR = Path(__file__).resolve().parent.parent / "assets" / "styles"
PEAKS_PER_SEC = 40
THUMB_EVERY_S = 2.0
THUMB_HEIGHT = 90

MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".webp": "image/webp",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".mp3": "audio/mpeg",
    ".srt": "text/plain; charset=utf-8",
}

def _slug(text: str) -> str:
    """Nome de arquivo a partir do nome do projeto: sem acento, sem pontuação."""
    import unicodedata
    t = unicodedata.normalize("NFKD", text)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"[^A-Za-z0-9]+", "-", t).strip("-")
    return (t[:70] or "avelin").lower()


def _ascii_name(name: str) -> str:
    """Reserva ASCII do Content-Disposition — aspas quebrariam o cabeçalho."""
    return re.sub(r'[^A-Za-z0-9._-]', "_", _slug(name.rsplit(".", 1)[0])) + \
        ("." + name.rsplit(".", 1)[1] if "." in name else "")


# QUANDO ESTE PROCESSO SUBIU.
#
# O servidor serve os arquivos do app LENDO O DISCO a cada requisição, mas as
# ROTAS são código carregado na partida. Depois de atualizar a skill, o
# navegador recebe um app novo falando com um servidor velho — e o sintoma é
# um 404 cru numa funcionalidade que aparece na tela. Aconteceu com o botão
# Exportar: o botão existia, a rota não.
#
# Comparar a data dos arquivos com esta marca detecta isso sozinho, sem
# ninguém ter de manter um número de versão em dois lugares.
STARTED_AT = time.time()

_thumb_lock = threading.Lock()
_thumb_state: dict[str, float] = {}  # video path -> mtime generated


def _has_key(name: str) -> bool:
    """A chave EXISTE? Só isso — o valor nunca sai daqui.

    O editor precisa saber o que pode oferecer, e não pode saber o segredo:
    mandar a chave para o navegador a exporia em qualquer aba aberta e em
    qualquer captura de tela do usuário pedindo ajuda.
    """
    import os
    v = (os.environ.get(name) or "").strip()
    if v:
        return True
    env = Path(__file__).resolve().parent.parent / ".env"
    if not env.exists():
        return False
    for line in env.read_text().splitlines():
        line = line.strip()
        if line.startswith(f"{name}=") and line.split("=", 1)[1].strip():
            return True
    return False


def _deps() -> dict:
    """O que esta máquina TEM — para a interface poder pedir o que falta.

    Hoje a pessoa descobre cada dependência por mensagem de erro, uma de cada
    vez, e sempre no meio de um trabalho. Publicando o estado, a tela pode
    mostrar tudo de uma vez, na primeira rodada, com o que é obrigatório
    separado do que é opcional.

    `shutil.which` e não "tentar rodar": rodar o ffmpeg só para saber se ele
    existe custa um processo por poll, e o poll é de 2 em 2 segundos.
    """
    import shutil
    return {
        # sem estes, nada funciona
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "ffprobe": bool(shutil.which("ffprobe")),
        "uv": bool(shutil.which("uv")),
        # só a Fase 2 precisa
        "node": bool(shutil.which("node")),
        # o motor da Fase 2 resolve sozinho pelo npx; o cache é o sinal de que
        # ele já foi baixado uma vez (~365 MB, compartilhado entre projetos)
        "hyperframes": (Path.home() / ".cache" / "hyperframes").exists(),
    }


def _stale() -> bool:
    """Algum arquivo do app mudou DEPOIS que este processo subiu?"""
    watched = [Path(__file__).resolve(), APP_DIR / "app.js",
               APP_DIR / "app.css", APP_DIR / "index.html"]
    try:
        return max(f.stat().st_mtime for f in watched if f.exists()) > STARTED_AT
    except (OSError, ValueError):
        return False


def probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    ).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def gen_waveform(video: Path, out_json: Path) -> None:
    """Decode audio to mono s16 and store min/max peak pairs per bucket (0-100)."""
    rate = 8000
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(video), "-vn",
         "-ac", "1", "-ar", str(rate), "-f", "s16le", "-"],
        capture_output=True,
    ).stdout
    samples = array.array("h")
    samples.frombytes(raw[: len(raw) // 2 * 2])
    per_bucket = max(1, rate // PEAKS_PER_SEC)
    mins: list[int] = []
    maxs: list[int] = []
    for i in range(0, len(samples), per_bucket):
        chunk = samples[i:i + per_bucket]
        if not chunk:
            continue
        mins.append(round(min(chunk) / 32768 * 100))
        maxs.append(round(max(chunk) / 32768 * 100))
    out_json.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_json.with_suffix(".tmp")
    tmp.write_text(json.dumps({
        "peaksPerSec": PEAKS_PER_SEC,
        "duration": len(samples) / rate,
        "min": mins,
        "max": maxs,
        "srcMtime": video.stat().st_mtime,
    }))
    tmp.replace(out_json)


def gen_thumbs(video: Path, out_dir: Path) -> None:
    """Filmstrip thumbs: one small jpg every THUMB_EVERY_S seconds."""
    if out_dir.exists():
        shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(video),
         "-vf", f"fps=1/{THUMB_EVERY_S},scale=-2:{THUMB_HEIGHT}",
         "-q:v", "6", str(out_dir / "%04d.jpg")],
        check=False, capture_output=True,
    )
    (out_dir / "meta.json").write_text(json.dumps({
        "everySec": THUMB_EVERY_S,
        "count": len(list(out_dir.glob("*.jpg"))),
        "srcMtime": video.stat().st_mtime,
    }))


class Handler(BaseHTTPRequestHandler):
    root: Path  # set on the class by main()
    protocol_version = "HTTP/1.1"

    # ---- helpers ----
    def _hdr(self, code: int, ctype: str, length: int | None = None,
             extra: dict[str, str] | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Accept-Ranges", "bytes")
        if length is not None:
            self.send_header("Content-Length", str(length))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()

    def _json(self, obj: object, code: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode()
        self._hdr(code, "application/json; charset=utf-8", len(body))
        self.wfile.write(body)

    def _send_file(self, path: Path, download_as: str | None = None) -> None:
        """Static file with HTTP Range support (video scrubbing needs it).

        `download_as` liga o Content-Disposition: o mesmo arquivo que o <video>
        toca embutido é o que o botão Exportar baixa, e a única diferença é
        este cabeçalho.
        """
        if not path.is_file():
            self._json({"error": f"not found: {path.name}"}, 404)
            return
        size = path.stat().st_size
        ctype = MIME.get(path.suffix.lower(), "application/octet-stream")
        rng = self.headers.get("Range")
        start, end = 0, size - 1
        code = 200
        if rng:
            m = re.match(r"bytes=(\d*)-(\d*)", rng)
            if m:
                if m.group(1):
                    start = int(m.group(1))
                    if m.group(2):
                        end = min(int(m.group(2)), size - 1)
                elif m.group(2):  # suffix range: last N bytes
                    start = max(0, size - int(m.group(2)))
                code = 206
        length = end - start + 1
        extra = {"Content-Range": f"bytes {start}-{end}/{size}"} if code == 206 else {}
        if download_as:
            # RFC 6266: o filename* em UTF-8 carrega acento; o filename simples
            # fica de reserva para quem não lê o estendido.
            from urllib.parse import quote
            extra = dict(extra or {})
            extra["Content-Disposition"] = (
                f'attachment; filename="{_ascii_name(download_as)}"; '
                f"filename*=UTF-8''{quote(download_as)}")
        extra = extra or None
        self._hdr(code, ctype, length, extra)
        with open(path, "rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(1 << 16, remaining))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return
                remaining -= len(chunk)

    def _safe(self, base: Path, rel: str) -> Path | None:
        p = (base / rel.lstrip("/")).resolve()
        return p if str(p).startswith(str(base.resolve())) else None

    def _current_video(self) -> Path | None:
        state_p = self.root / "state.json"
        rel = "preview.mp4"
        if state_p.exists():
            try:
                rel = json.loads(state_p.read_text()).get("video") or rel
            except json.JSONDecodeError:
                pass
        p = self._safe(self.root, rel)
        return p if p and p.exists() else None

    # ---- routes ----
    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            self._send_file(APP_DIR / "index.html")
        elif path.startswith("/assets/"):
            p = self._safe(APP_DIR, path[len("/assets/"):])
            self._send_file(p) if p else self._json({"error": "bad path"}, 400)
        elif path.startswith("/styles/"):
            p = self._safe(STYLE_DIR, path[len("/styles/"):])
            self._send_file(p) if p else self._json({"error": "bad path"}, 400)
        elif path.startswith("/media/"):
            p = self._safe(self.root, path[len("/media/"):])
            self._send_file(p) if p else self._json({"error": "bad path"}, 400)
        elif path == "/gen/words.json":
            self._words()
        elif path == "/gen/waveform.json":
            self._waveform()
        elif path.startswith("/gen/thumbs/"):
            self._thumbs(path[len("/gen/thumbs/"):])
        elif path == "/api/state":
            self._state()
        elif path == "/download":
            self._download()
        else:
            self._json({"error": "unknown route"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] != "/api/save":
            self._json({"error": "unknown route"}, 404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._json({"error": "invalid JSON"}, 400)
            return
        body["savedAt"] = time.strftime("%Y-%m-%d %H:%M:%S")
        # The style pick goes to its own file. It is a one-time setup decision,
        # not a correction, and sharing preview_edits.json would make one save
        # clobber the other (they are written at different moments, by different
        # screens, and the skill consumes+deletes them independently).
        # A APROVAÇÃO tem arquivo próprio pela mesma razão: é decisão de FASE,
        # não correção. Compartilhando o preview_edits.json, aprovar apagaria
        # marcações ainda não lidas — e uma aprovação que chega no mesmo arquivo
        # que "conserte isto" é contraditória por construção.
        if body.get("type") == "approve-cut":
            name = "preview_approval.json"
        elif body.get("type") == "style-setup":
            name = "preview_style.json"
        else:
            name = "preview_edits.json"
        out = self.root / name
        tmp = out.with_suffix(".tmp")
        tmp.write_text(json.dumps(body, ensure_ascii=False, indent=2))
        tmp.replace(out)
        started = self._maybe_auto_apply(name)
        self._json({"ok": True, "file": str(out), "applying": started})

    def _maybe_auto_apply(self, name: str) -> bool:
        """Dispara o refazimento em segundo plano, quando ligado com --auto.

        Em segundo plano porque refazer um corte leva minutos, e a resposta do
        salvar não pode esperar: a interface travaria com o usuário achando que
        o clique não pegou. O andamento chega pelo state.json, que a interface
        já consulta sozinha.

        Só o que é mecânico dispara. As marcações escritas continuam sendo
        pedidos em texto — ninguém deve executá-las sem ler.
        """
        if not getattr(self.server, "auto_apply", False):
            return False
        # A APROVAÇÃO encadeia duas coisas, e nenhuma delas é a Fase 2.
        #
        # Aprovar é instantâneo — o que o usuário decidiu ali é "as tomadas estão
        # certas", nada mais. Mas duas consequências são mecânicas e não deviam
        # esperar alguém digitar:
        #   1. o encode em RESOLUÇÃO PLENA (a Fase 1 itera em proxy 720p);
        #   2. abrir a aba Estilo, que é onde o usuário determina os elementos.
        # Os dois em paralelo: escolher estilo não depende do encode terminar, e
        # o encode leva ~1min que sai de graça enquanto ele escolhe.
        #
        # A Fase 2 continua NÃO disparando. Ela consome escolhas que ainda não
        # existem, e rodá-la aqui gastaria tokens num estilo presumido — foi
        # exatamente o erro que originou este encadeamento.
        if name == "preview_approval.json":
            self._open_style_tab()
            return self._encode_full_res()
        script = "apply_edits.py" if name == "preview_edits.json" else "phase2.py"
        try:
            subprocess.Popen(
                [sys.executable, str(Path(__file__).resolve().parent / script),
                 str(self.root)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return True
        except OSError:
            return False

    def _download(self) -> None:
        """Exportar: o entregue, com nome que sobrevive fora desta pasta.

        Baixar `final.mp4` é inútil na pasta de Downloads de quem edita cinco
        vídeos por semana — em uma hora são cinco `final(3).mp4`. O nome sai do
        `project` do state, que é justamente a frase que identifica o vídeo.

        Sem `finalVideo` ainda, exporta o CORTE, marcado como corte no nome.
        Recusar o download porque a Fase 2 não rodou seria esconder um arquivo
        que existe e serve — o usuário pode querer o corte limpo.
        """
        state = {}
        try:
            state = json.loads((self.root / "state.json").read_text())
        except (OSError, json.JSONDecodeError):
            pass
        rel = state.get("finalVideo")
        kind = "final"
        if not rel or not (self.root / rel).exists():
            rel, kind = (state.get("video") or "preview.mp4"), "corte"
        p = self._safe(self.root, rel)
        if not p or not p.exists():
            self._json({"error": "nada para exportar ainda"}, 404)
            return
        base = _slug(state.get("project") or "avelin")
        self._send_file(p, download_as=f"{base}-{kind}{p.suffix}")

    def _patch_state(self, **kv) -> None:
        p = self.root / "state.json"
        try:
            cur = json.loads(p.read_text()) if p.exists() else {}
        except json.JSONDecodeError:
            return
        cur.update(kv)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(cur, ensure_ascii=False, indent=2))
        tmp.replace(p)

    def _open_style_tab(self) -> None:
        """Aprovou → a aba Estilo passa a pedir as escolhas, na hora.

        É o passo que fecha o fluxo. Sem ele o usuário aprova, não acontece
        nada visível, e alguém (o agente) acaba PRESUMINDO as escolhas para
        seguir — que foi o que aconteceu aqui e gastou render à toa.
        """
        self._patch_state(phase=1, awaitingStyle=True,
                          message="Corte aprovado — escolha os elementos na aba Estilo")

    def _encode_full_res(self) -> bool:
        """Reencoda o corte em resolução plena, em segundo plano, com progresso.

        A Fase 1 itera em proxy 720p porque 1080p em cada versão descartada é o
        que fazia a iteração doer. Aprovado o corte, o encode pleno é obrigatório
        e mecânico — não é decisão de ninguém, então não espera ninguém.
        """
        edl = self.root / "edl.json"
        out = self.root / "preview.mp4"
        if not edl.exists():
            return False

        def run() -> None:
            progress.begin(self.root, "encode",
                           "Encodando o corte em 1080p", ai=False)
            try:
                r = subprocess.run(
                    [sys.executable,
                     str(Path(__file__).resolve().parent / "render.py"),
                     str(edl), "-o", str(out), "--no-subtitles"],
                    capture_output=True, text=True)
                if r.returncode == 0:
                    progress.done(self.root, "Corte em 1080p pronto")
                else:
                    progress.fail(self.root,
                                  (r.stderr or "").strip()[-300:] or "o encode falhou")
            except OSError as exc:
                progress.fail(self.root, str(exc))

        threading.Thread(target=run, daemon=True).start()
        return True

    # ---- dynamic bits ----
    def _state(self) -> None:
        state_p = self.root / "state.json"
        state: dict = {}
        if state_p.exists():
            try:
                state = json.loads(state_p.read_text())
            except json.JSONDecodeError:
                state = {"error": "state.json inválido"}
        # attach small data files + mtimes so the UI hot-reloads on change
        mtimes: dict[str, float] = {}
        for key in ("video", "finalVideo", "edl", "captions", "editData"):
            rel = state.get(key)
            if not rel:
                continue
            p = self._safe(self.root, rel)
            if p and p.exists():
                mtimes[key] = p.stat().st_mtime
        edl = None
        rel = state.get("edl") or "edl.json"
        p = self._safe(self.root, rel)
        if p and p.exists():
            try:
                edl = json.loads(p.read_text())
            except json.JSONDecodeError:
                pass
        edits_p = self.root / "preview_edits.json"
        video = self._current_video()
        self._json({
            "state": state,
            "edl": edl,
            "mtimes": mtimes,
            "videoDuration": probe_duration(video) if video else 0,
            "hasPendingEdits": edits_p.exists(),
            # O QUE ESTÁ RODANDO AGORA. Vai no mesmo poll do state para a
            # interface não precisar de um segundo relógio — dois pollers com
            # períodos diferentes mostram estados de instantes diferentes, e a
            # barra fica discordando do texto ao lado dela.
            "progress": progress.read(self.root),
            # o app compara com o que ele mesmo é: servidor mais VELHO que os
            # arquivos servidos = funcionalidade na tela que a rota não atende
            "serverStale": _stale(),
            # o que a ferramenta PODE oferecer nesta máquina. Presença, não valor.
            "keys": {"groq": _has_key("GROQ_API_KEY"),
                     "elevenlabs": _has_key("ELEVENLABS_API_KEY"),
                     "pexels": _has_key("PEXELS_API_KEY"),
                     "google": _has_key("GOOGLE_API_KEY") and _has_key("GOOGLE_CSE_ID"),
                     "treblo": _has_key("TREBLO_API_KEY")},
            "deps": _deps(),
            "now": time.time(),
        })

    def _waveform(self) -> None:
        video = self._current_video()
        if not video:
            self._json({"error": "sem vídeo ainda"}, 404)
            return
        out = self.root / ".preview_cache" / "waveform.json"
        stale = True
        if out.exists():
            try:
                stale = json.loads(out.read_text()).get("srcMtime") != video.stat().st_mtime
            except json.JSONDecodeError:
                pass
        if stale:
            gen_waveform(video, out)
        self._send_file(out)

    def _words(self) -> None:
        """O transcrito do corte. Caro de gerar — roda detector de fala em cada
        fonte — então é cacheado pelo mtime do edl.json, que é exatamente o que
        muda quando o corte muda."""
        edl = self.root / "edl.json"
        if not edl.exists():
            self._json({"words": [], "error": "sem edl.json"}, 200)
            return
        out = self.root / ".preview_cache" / "words.json"
        stale = True
        if out.exists():
            try:
                stale = json.loads(out.read_text()).get("edlMtime") != edl.stat().st_mtime
            except json.JSONDecodeError:
                pass
        if stale:
            r = subprocess.run(
                [sys.executable, str(Path(__file__).resolve().parent / "cut_words.py"),
                 str(self.root), "-o", str(out)],
                capture_output=True, text=True,
            )
            if r.returncode != 0 or not out.exists():
                self._json({"words": [], "error": (r.stderr or "falhou")[-300:]}, 200)
                return
        self._send_file(out)

    def _thumbs(self, name: str) -> None:
        video = self._current_video()
        if not video:
            self._json({"error": "sem vídeo ainda"}, 404)
            return
        out_dir = self.root / ".preview_cache" / "thumbs"
        meta = out_dir / "meta.json"
        with _thumb_lock:
            stale = True
            if meta.exists():
                try:
                    stale = json.loads(meta.read_text()).get("srcMtime") != video.stat().st_mtime
                except json.JSONDecodeError:
                    pass
            if stale:
                gen_thumbs(video, out_dir)
        p = self._safe(out_dir, name)
        self._send_file(p) if p else self._json({"error": "bad path"}, 400)

    def log_message(self, fmt: str, *args: object) -> None:
        pass  # quiet


def main() -> None:
    ap = argparse.ArgumentParser(description="Avelin preview interface server")
    ap.add_argument("--root", type=Path, required=True, help="the session <edit> dir")
    ap.add_argument("--port", type=int, default=4820)
    ap.add_argument("--auto", action="store_true",
                    help="salvar no editor já refaz o corte / a Fase 2, "
                         "sem depender de alguém rodar um comando depois")
    args = ap.parse_args()

    root = args.root.resolve()
    if not root.exists():
        raise SystemExit(f"edit dir not found: {root}")
    if not (APP_DIR / "index.html").exists():
        raise SystemExit(f"app not found at {APP_DIR}")

    Handler.root = root
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    srv.auto_apply = args.auto
    modo = " · salvar já refaz" if args.auto else ""
    print(f"Avelin — editor → http://127.0.0.1:{args.port}  (root: {root}){modo}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()

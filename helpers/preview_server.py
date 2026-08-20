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
    uv run helpers/preview_server.py [--root <videos_dir>/edit] [--port 4820]

`--root` é OPCIONAL. Sem ele o editor abre na tela sem projeto — dropzone,
recentes e navegador de pastas — e a escolha acontece na interface
(`/api/projects`, `/api/browse`, `/api/drop`, `/api/upload`, `/api/open`,
`/api/close`). O projeto aberto é publicado em `~/.avelin/current.json`, que é
o ponteiro que o `watch_edits.py` segue.
"""
from __future__ import annotations

import argparse
import array
import json
import os
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


def helper_python() -> str:
    """O interpretador que os helpers precisam — não necessariamente este.

    O servidor é iniciado com `python3` (é o que o painel do harness executa), e
    até aqui ele repassava `sys.executable` para tudo que disparava. Só que os
    helpers dependem de pacotes que moram no `.venv` da skill: o `phase2.py`
    morria em um segundo com `ModuleNotFoundError: No module named 'fontTools'`,
    o erro ia para /dev/null, e a interface anunciava "✓ Enviado". O usuário viu
    um botão que não funciona; o que havia era um interpretador sem as
    dependências.

    Por isso a escolha do python é DO DESTINO, não da origem. Se o venv existe,
    é ele; se não, cai em `sys.executable`, que é o comportamento antigo — assim
    uma instalação sem venv continua funcionando como funcionava.
    """
    venv = Path(__file__).resolve().parent.parent / ".venv" / "bin" / "python"
    return str(venv) if venv.exists() else sys.executable

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
        # opcional: só quem traz fonte de URL precisa
        "ytdlp": bool(shutil.which("yt-dlp")),
    }


# ---- projetos ----
#
# O EDITOR ABRE VAZIO.
#
# Enquanto o `--root` era obrigatório, isto não era um aplicativo: era a janela
# de UMA pasta, decidida na linha de comando por quem subiu o processo. Abrir o
# endereço mostrava o último projeto que alguém tinha passado — no caso que
# originou esta mudança, um vídeo ENTREGUE meses antes, com legenda, trilha e
# tudo pronto, como se fosse o trabalho da vez. Não há como "fechar" o que
# nunca foi aberto, e a única forma de trocar de projeto era matar o servidor.
#
# Agora o root começa vazio e a escolha acontece na tela. Para escolher é
# preciso lembrar, e lembrar tem de sobreviver ao processo — que reinicia toda
# vez que a skill é atualizada — então a lista mora em disco, no HOME, e não em
# memória.
RECENTS = Path.home() / ".avelin" / "projects.json"
RECENTS_MAX = 24

# QUAL PROJETO ESTÁ ABERTO AGORA, publicado para fora do processo.
#
# O `watch_edits.py` é armado para UMA pasta, no instante em que a sessão
# começa. Enquanto o projeto era escolhido na linha de comando isso bastava;
# agora que a pessoa troca de projeto na tela, o vigia ficaria olhando a pasta
# anterior — ela salva uma marcação, vê "enviado", e o agente nunca recebe.
# Este arquivo é o ponteiro que ele segue.
CURRENT = Path.home() / ".avelin" / "current.json"

# ONDE O EDITOR ESTÁ ATENDENDO, para quem precisa dizer isso ao usuário.
#
# A porta é decidida na hora (o harness passa `$PORT`, e a 4820 costuma estar
# ocupada por outra sessão), então quem escreve a mensagem do chat não tem como
# saber a URL — e o usuário fica com uma ferramenta visual aberta que ele não
# consegue achar no navegador. O arquivo é o endereço publicado: qualquer
# agente, em qualquer turno, lê daqui em vez de adivinhar 4820.
SERVER = Path.home() / ".avelin" / "server.json"

# A MARCA DA PESSOA, e ela não pertence a um projeto.
#
# Cor de destaque e família tipográfica não mudam de vídeo para vídeo — são de
# QUEM faz, não do que está sendo feito. Enquanto viviam só no `state.json` de
# cada projeto, cada vídeo novo começava no laranja de fábrica e o usuário
# reescrevia o mesmo hexadecimal toda vez, às vezes errando um dígito e
# entregando dois laranjas parecidos em vídeos da mesma série.
#
# Fica no HOME, ao lado dos recentes: é a mesma natureza de dado — o que o
# aplicativo sabe sobre esta pessoa, não sobre este trabalho. O agente também
# escreve aqui quando descobre a marca (de um site, de um material de
# referência, de uma resposta no chat).
BRAND = Path.home() / ".avelin" / "brand.json"
BRAND_KEYS = ("accent", "textColor", "capColor", "fontMain", "fontAccent", "capFont")

# AS ESCOLHAS DE ESTILO, lembradas entre projetos. O `brand.json` já guardava a
# identidade (cor e letra); faltava o resto do que o usuário marca toda vez —
# o formato do corte, a headline, o estilo de legenda, os elementos ligados.
# Refazer as mesmas cinco escolhas em todo vídeo é trabalho que a ferramenta
# podia poupar, e a divisão entre os dois arquivos é de SIGNIFICADO: um diz
# quem ele é, o outro diz como ele costuma editar.
#
# Fora do clone, pela mesma razão do preferencias.json e do brand.json: gosto
# de meses não pode morrer num `git clean` nem subir para um repositório que
# outros clonam.
ESTILO = Path.home() / ".avelin" / "estilo.json"
ESTILO_KEYS = ("edit", "headline", "captions", "elements", "capDy")


def _set_root(p: Path | None) -> None:
    """Trocar de projeto é uma coisa só: o root e o ponteiro publicado."""
    Handler.root = p
    try:
        CURRENT.parent.mkdir(parents=True, exist_ok=True)
        tmp = CURRENT.with_suffix(".tmp")
        tmp.write_text(json.dumps({"root": str(p) if p else None,
                                   "at": time.time()}, ensure_ascii=False))
        tmp.replace(CURRENT)
    except OSError:
        pass


# O QUE JÁ FOI LIDO DO PONTEIRO. Só o mtime: reler o arquivo a cada poll de 2s
# seria trabalho à toa num arquivo que muda uma vez por hora.
_current_seen = {"mtime": 0.0}


def _follow_current() -> None:
    """O ponteiro no disco MANDA — inclusive quando não foi o servidor que o escreveu.

    `current.json` era só uma PUBLICAÇÃO de mão única: o servidor escrevia, o
    `watch_edits.py` lia. Quem trocasse de projeto escrevendo nele — um agente
    com pressa, um script — mexia no VIGIA e não no servidor: o watcher passava
    a seguir o projeto novo, a aba aberta continuava mostrando o antigo, e nada
    em tela dizia que os dois discordavam. O sintoma é cruel porque cada metade
    está certa sozinha: o chat fala do vídeo novo, a tela mostra "aguardando o
    primeiro render" do vídeo velho, e ninguém tem motivo para suspeitar.

    Seguir o arquivo faz o erro se corrigir sozinho no poll seguinte. Não
    substitui `/api/open` (que valida a pasta e ainda devolve o cartão do
    projeto), mas tira o desencontro de cima do usuário.
    """
    try:
        mt = CURRENT.stat().st_mtime
    except OSError:
        return
    if mt <= _current_seen["mtime"]:
        return
    _current_seen["mtime"] = mt
    try:
        raw = json.loads(CURRENT.read_text()).get("root")
    except (OSError, json.JSONDecodeError):
        return
    novo = Path(raw).resolve() if raw else None
    atual = Handler.root.resolve() if Handler.root else None
    if novo == atual:
        return                      # foi o próprio `_set_root` que acabou de escrever
    if novo is not None and not novo.is_dir():
        return                      # ponteiro para pasta que não existe: ignore
    # Sem `_set_root`: o arquivo já diz isto, e reescrevê-lo só geraria outro
    # mtime para o próximo poll examinar.
    Handler.root = novo
    if novo is not None:
        _recents_touch(novo)

# Onde procurar projetos que nunca foram abertos por aqui. O usuário tem
# projetos no disco de antes desta lista existir; sem a varredura a tela
# inicial nasceria vazia para quem mais tem trabalho feito.
SCAN_ROOTS = ("Movies", "Videos", "Desktop", "Documents")
SCAN_MAX_DEPTH = 6
SCAN_TTL_S = 60.0
# Pastas que um projeto tem aos milhares de arquivos dentro e onde nunca há
# outro projeto. Sem podar, a varredura entra em `clips_graded/` com 100
# extrações e em `node_modules`, e leva segundos em vez de milissegundos.
SCAN_SKIP = {
    "node_modules", "clips_graded", "clips_proxy", "transcripts", "renders",
    "hyperframes", "remotion", "verify", "pexels", "broll", "sfx", "film",
    "Library", "Photos Library.photoslibrary", "__pycache__", ".git",
}
_scan_cache: dict = {"at": 0.0, "items": []}


VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm", ".mts", ".mxf", ".m2ts"}

# Onde nasce um projeto cujo vídeo veio de fora (uma pasta de entrada, ou um
# arquivo que só existe como upload). Nunca a pasta de Downloads em si: um
# `~/Downloads/edit` fica órfão junto de mil arquivos que não são do projeto.
NEW_PROJECTS_DIR = Path.home() / "Movies" / "Avelin"
INBOX_DIRS = {Path.home() / "Downloads", Path.home() / "Desktop"}


def _locate_file(name: str, size: int) -> Path | None:
    """Achar no disco o arquivo que a pessoa arrastou.

    O navegador entrega o CONTEÚDO de um arquivo solto e esconde ONDE ele
    está — não há API que dê o caminho absoluto, é fronteira de segurança do
    navegador. Mas ele entrega nome e tamanho, e esse par identifica um vídeo
    com folga de sobra dentro do HOME de uma pessoa.

    Achando, o projeto usa o arquivo ONDE ELE ESTÁ: nada é copiado, e uma
    fonte de 5 GB não vira duas. Só quando isto falha é que vale subir os bytes.
    """
    import os
    for name_root in ("Movies", "Videos", "Desktop", "Documents", "Downloads"):
        base = Path.home() / name_root
        if not base.is_dir():
            continue
        base_depth = len(base.parts)
        for dirpath, dirnames, filenames in os.walk(base, onerror=lambda e: None):
            here = Path(dirpath)
            if len(here.parts) - base_depth >= SCAN_MAX_DEPTH + 2:
                dirnames[:] = []
                continue
            dirnames[:] = [d for d in dirnames
                           if not d.startswith(".") and d not in SCAN_SKIP]
            if name in filenames:
                cand = here / name
                try:
                    if cand.stat().st_size == size:
                        return cand
                except OSError:
                    pass
    return None


def _project_dir_for(video: Path) -> Path:
    """A pasta de vídeos de um arquivo — que é onde o `edit/` vai morar.

    Regra: o projeto nasce ao lado do vídeo, que é a convenção da skill
    (`<videos_dir>/edit/`). A exceção são as pastas de ENTRADA: um `edit/`
    dentro de Downloads não é um projeto, é lixo no meio da bagunça de todo
    mundo — de lá o vídeo é copiado para uma pasta de projeto de verdade.
    """
    # O vídeo JÁ ESTÁ dentro de um projeto — `base.mp4`, `cut.mp4`, `final.mp4`
    # e todo render vivem no `edit/`. Sem esta linha o projeto do projeto vira
    # um `edit/edit`, e isso não é hipótese: existe um no disco, criado assim.
    if video.parent.name == "edit":
        return video.parent.parent
    if video.parent in INBOX_DIRS:
        dest = NEW_PROJECTS_DIR / _slug(video.stem)
        dest.mkdir(parents=True, exist_ok=True)
        alvo = dest / video.name
        if not alvo.exists():
            # COPIAR, nunca mover. O arquivo é do usuário e ele pode estar
            # esperando encontrá-lo onde deixou.
            shutil.copy2(video, alvo)
        return dest
    return video.parent


def _is_project(p: Path) -> bool:
    """Uma pasta `edit` com `state.json` dentro É um projeto do Avelin."""
    try:
        return (p / "state.json").is_file()
    except OSError:
        return False


def _videos_in(d: Path) -> list[str]:
    """As fontes de uma pasta de projeto, pelo nome. Só o primeiro nível.

    Primeiro nível porque `edit/` está logo abaixo e é cheio de renders: uma
    varredura recursiva devolveria `preview_proxy.mp4` como se fosse material
    bruto do usuário.
    """
    try:
        return sorted(f.name for f in d.iterdir()
                      if f.is_file() and f.suffix.lower() in VIDEO_EXT)[:40]
    except OSError:
        return []


def _init_state(edit: Path, nome: str, sources: list[str]) -> None:
    """O state.json de um projeto que ACABOU de nascer.

    `awaitingStart` aqui é um estado de MILISSEGUNDOS, não uma tela: quem cria
    o projeto (dropzone, upload, navegador de pastas) chama `_auto_start` na
    sequência, que o desliga e dispara a Fase 1. A tela que perguntava formato
    e briefing entre o drop e o processamento foi removida — o corte segue o
    aspect ratio do material de origem, e formato ou briefing diferentes se
    pedem no chat. O flag continua existindo por dois motivos: é o que
    `_auto_start` lê para saber que o projeto nunca começou (inclusive
    projetos antigos parados nesse estado), e é o que impede um projeto JÁ
    andando de ser recortado ao ser reaberto.
    """
    st = edit / "state.json"
    if st.exists():
        return
    st.parent.mkdir(parents=True, exist_ok=True)
    st.write_text(json.dumps({
        "project": nome,
        "phase": 1,
        "video": "preview_proxy.mp4",
        "edl": "edl.json",
        "message": "Projeto criado — preparando a Fase 1",
        "awaitingStyle": False,
        "awaitingStart": True,
        "sources": sources,
    }, ensure_ascii=False, indent=2))


def _project_card(p: Path) -> dict:
    """O cartão que a tela inicial mostra. Nunca levanta — a lista de recentes
    envelhece junto com o disco, e um projeto renomeado ou num volume
    desmontado não pode derrubar a tela que serve para escolher outro."""
    card = {
        # O NOME ÚTIL É O DA PASTA DE CIMA. Todo projeto se chama `edit`, então
        # uma lista de dez fica com dez linhas idênticas.
        "name": p.parent.name or p.name,
        "path": str(p),
        "phase": None, "message": "", "mtime": 0.0, "exists": p.is_dir(),
    }
    try:
        st = json.loads((p / "state.json").read_text())
        card["name"] = str(st.get("project") or card["name"])
        card["phase"] = st.get("phase")
        card["message"] = str(st.get("message") or "")
        card["mtime"] = (p / "state.json").stat().st_mtime
    except (OSError, json.JSONDecodeError):
        pass
    return card


def _recents_read() -> list[str]:
    try:
        data = json.loads(RECENTS.read_text())
        return [str(x) for x in data.get("recent", [])]
    except (OSError, json.JSONDecodeError):
        return []


def _recents_touch(p: Path) -> None:
    """Abriu → vai para o topo. Sem duplicata, e sem crescer para sempre."""
    keep = [str(p)] + [x for x in _recents_read() if x != str(p)]
    try:
        RECENTS.parent.mkdir(parents=True, exist_ok=True)
        tmp = RECENTS.with_suffix(".tmp")
        tmp.write_text(json.dumps({"recent": keep[:RECENTS_MAX]},
                                  ensure_ascii=False, indent=2))
        tmp.replace(RECENTS)
    except OSError:
        pass  # sem lista é pior, mas não é motivo para não abrir o projeto


def _scan_projects(force: bool = False) -> list[str]:
    """Projetos no disco que a lista de recentes ainda não conhece.

    Cacheada por tempo: a tela inicial faz poll de 2 em 2 segundos e uma
    varredura por poll transformaria a escolha de projeto num busy-loop de I/O.
    """
    import os
    now = time.time()
    if not force and now - _scan_cache["at"] < SCAN_TTL_S:
        return _scan_cache["items"]
    found: list[str] = []
    for name in SCAN_ROOTS:
        base = Path.home() / name
        if not base.is_dir():
            continue
        base_depth = len(base.parts)
        for dirpath, dirnames, filenames in os.walk(base, onerror=lambda e: None):
            here = Path(dirpath)
            if len(here.parts) - base_depth >= SCAN_MAX_DEPTH:
                dirnames[:] = []
                continue
            dirnames[:] = [d for d in dirnames
                           if not d.startswith(".") and d not in SCAN_SKIP]
            if here.name == "edit" and "state.json" in filenames:
                found.append(str(here))
                # Um projeto não contém outro. Descer daqui só encontraria as
                # pastas de trabalho — e num caso real, um `edit/edit` vazio.
                dirnames[:] = []
    _scan_cache.update(at=now, items=found)
    return found


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
    # NENHUM projeto aberto é o estado inicial legítimo, não um erro de partida.
    # Por isso `None` e não uma pasta qualquer: um root-padrão inventado faria
    # o editor abrir mostrando um projeto que ninguém escolheu, que é
    # exatamente o defeito que o estado vazio existe para corrigir.
    root: Path | None = None
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

    def _no_project(self) -> bool:
        """Rota que só faz sentido dentro de um projeto, sem projeto aberto.

        Responde 409 e não 404: o caminho existe, o que falta é contexto. A
        diferença importa para o app, que trata 404 como "ainda não gerado" e
        continua tentando.
        """
        if self.root:
            return False
        self._json({"error": "nenhum projeto aberto", "noProject": True}, 409)
        return True

    def _current_video(self) -> Path | None:
        if not self.root:
            return None
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
            if self._no_project():
                return
            p = self._safe(self.root, path[len("/media/"):])
            self._send_file(p) if p else self._json({"error": "bad path"}, 400)
        elif path == "/gen/words.json":
            self._no_project() or self._words()
        elif path == "/gen/waveform.json":
            self._no_project() or self._waveform()
        elif path.startswith("/gen/thumbs/"):
            self._no_project() or self._thumbs(path[len("/gen/thumbs/"):])
        elif path == "/api/state":
            self._state()
        elif path == "/api/projects":
            self._projects()
        elif path == "/api/browse":
            self._browse()
        elif path == "/api/brand":
            self._brand_get()
        elif path == "/api/estilo":
            self._estilo_get()
        elif path == "/api/localfonts":
            self._localfonts()
        elif path == "/download":
            self._no_project() or self._download()
        else:
            self._json({"error": "unknown route"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        route = self.path.split("?", 1)[0]
        if route == "/api/upload":
            return self._upload()
        if route in ("/api/open", "/api/close", "/api/drop", "/api/brand", "/api/start"):
            try:
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length) or b"{}")
            except (ValueError, json.JSONDecodeError):
                self._json({"error": "invalid JSON"}, 400)
                return
            if route == "/api/open":
                return self._open(body)
            if route == "/api/drop":
                return self._drop(body)
            if route == "/api/brand":
                return self._brand_put(body)
            if route == "/api/start":
                return self._start(body)
            return self._close()
        if route != "/api/save":
            self._json({"error": "unknown route"}, 404)
            return
        if self._no_project():
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
            self._estilo_lembrar(body)
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
        # EXECUTAR É O PADRÃO, e a razão é que o consentimento já foi colhido.
        #
        # Isto exigia `--auto`, e o lançamento documentado no SKILL.md não passa
        # a flag. Então o clique gravava o pedido, devolvia `applying: false` e
        # NADA rodava: a entrega dependia de uma sessão do Claude estar atachada
        # ao `watch_edits.py` para ler a notificação e executar. Quando não há
        # sessão — e não há, na maior parte do tempo em que alguém mexe no
        # editor — o botão é um no-op com toast de sucesso.
        #
        # O medo original era gastar tokens e minutos sem querer. Mas a tela já
        # pergunta antes ("O pedido vai para a IA e consome tokens, além de
        # alguns minutos de render. Tem certeza?"), e honrar um "sim" não é
        # atropelar ninguém — é o contrário de fingir que se atendeu.
        #
        # `--no-auto` restaura o comportamento de só gravar o pedido, para quem
        # trabalha com uma sessão de IA no circuito e prefere que ela decida.
        if getattr(self.server, "auto_apply", True) is False:
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
        return self._spawn_helper(script)

    def _spawn_helper(self, script: str) -> bool:
        """Dispara um helper em segundo plano — e VÊ como ele terminou.

        O que havia aqui era `stdout=DEVNULL, stderr=DEVNULL` seguido de
        `return True`. As duas metades erram junto: `Popen` bem-sucedido só diz
        que o processo COMEÇOU, e com a saída no lixo ninguém descobre que ele
        morreu. Resultado medido neste projeto: o `phase2.py` quebrava em um
        segundo por dependência faltando, a interface respondia "✓ Enviado — a
        IA foi avisada", e o usuário concluía, com razão, que o botão não
        funcionava.

        Agora a saída vai para um log ao lado do projeto e uma thread espera o
        processo. Falha vira `progress.fail()`, que é o canal que a interface já
        lê a cada poll — o mesmo que o `progress.py` criou justamente para que
        "processando…" não ficasse na tela para sempre quando algo morre.

        A thread é daemon e o filho tem sessão própria: se o servidor cair, o
        trabalho continua; só o relato se perde.
        """
        logs = self.root / ".preview_cache"
        try:
            logs.mkdir(parents=True, exist_ok=True)
        except OSError:
            logs = self.root
        log = logs / f"run-{Path(script).stem}.log"
        try:
            fh = open(log, "w")
        except OSError:
            fh = subprocess.DEVNULL
        try:
            proc = subprocess.Popen(
                [helper_python(), str(Path(__file__).resolve().parent / script),
                 str(self.root)],
                stdout=fh, stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except OSError:
            if fh not in (None, subprocess.DEVNULL):
                fh.close()
            return False

        root, nome = self.root, Path(script).stem

        def aguardar() -> None:
            código = proc.wait()
            if fh not in (None, subprocess.DEVNULL):
                try:
                    fh.close()
                except OSError:
                    pass
            if código == 0:
                return
            cauda = ""
            try:
                cauda = log.read_text(errors="replace").strip().splitlines()[-1][:200]
            except (OSError, IndexError):
                pass
            progress.fail(root, f"{nome} falhou (código {código})"
                                + (f": {cauda}" if cauda else "")
                                + f" — log em {log.name}")

        threading.Thread(target=aguardar, daemon=True).start()
        return True

    def _download(self) -> None:
        """Exportar: o entregue, com nome que sobrevive fora desta pasta.

        Baixar `final.mp4` é inútil na pasta de Downloads de quem edita cinco
        vídeos por semana — em uma hora são cinco `final(3).mp4`. O nome sai do
        `project` do state, que é justamente a frase que identifica o vídeo.

        Sem `finalVideo` ainda, exporta o CORTE, marcado como corte no nome.
        Recusar o download porque a Fase 2 não rodou seria esconder um arquivo
        que existe e serve — o usuário pode querer o corte limpo.
        """
        # EXPORTAR DURANTE UM RENDER entrega arquivo pela metade: o ffmpeg
        # escreve o final.mp4 NO LUGAR, e um download no meio sai truncado com
        # o Content-Length de um arquivo que ainda está crescendo — medido em
        # 2026-08-19 ("Tive um erro ao exportar", com um render de 83s
        # reescrevendo o arquivo no mesmo instante). Recusar com nome é melhor
        # que servir vídeo corrompido; o botão do app mostra esta mensagem.
        prog = progress.read(self.root) or {}
        if prog.get("state") == "running" and prog.get("task") in ("fase2", "encode"):
            self._json({"error": "render em andamento — exporte quando a barra de progresso terminar"}, 409)
            return
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

    # ---- fontes instaladas ----
    def _localfonts(self) -> None:
        """As famílias instaladas nesta máquina, para o seletor da headline.

        O catálogo do Google cobre o genérico e não cobre a MARCA de ninguém —
        a tipografia da identidade do usuário está no computador dele. Funciona
        porque o render roda em Chrome aqui e o Chrome resolve a família pelo
        NOME; só a medição precisa do arquivo, e disso cuida o `text_measure`.

        A primeira chamada indexa (~1,5s para 2600 arquivos); as seguintes leem
        o índice cacheado. Vai sem os caminhos — o navegador não tem uso para
        eles e mandá-los exporia a árvore de arquivos do usuário à toa.
        """
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            import local_fonts
            self._json({"families": local_fonts.catalog()})
        except Exception as exc:
            # sem fontes locais o editor continua inteiro, só com o Google
            self._json({"families": [], "error": str(exc)[:200]})

    # ---- a marca ----
    def _brand_get(self) -> None:
        try:
            d = json.loads(BRAND.read_text())
        except (OSError, json.JSONDecodeError):
            d = {}
        self._json({k: d[k] for k in BRAND_KEYS if k in d})

    def _brand_put(self, body: dict) -> None:
        """Guarda só as chaves conhecidas — o corpo vem do navegador, e gravar o
        que ele mandar transformaria este arquivo em depósito de qualquer coisa
        que um dia passe pelo payload de estilo."""
        try:
            cur = json.loads(BRAND.read_text())
        except (OSError, json.JSONDecodeError):
            cur = {}
        for k in BRAND_KEYS:
            v = body.get(k)
            if isinstance(v, str) and v.strip():
                cur[k] = v.strip()
        try:
            BRAND.parent.mkdir(parents=True, exist_ok=True)
            tmp = BRAND.with_suffix(".tmp")
            tmp.write_text(json.dumps(cur, ensure_ascii=False, indent=2))
            tmp.replace(BRAND)
        except OSError as exc:
            self._json({"error": str(exc)}, 500)
            return
        self._json({"ok": True, "brand": cur})

    def _estilo_get(self) -> None:
        try:
            d = json.loads(ESTILO.read_text())
        except (OSError, json.JSONDecodeError):
            d = {}
        self._json({k: d[k] for k in ESTILO_KEYS if k in d})

    def _estilo_lembrar(self, body: dict) -> None:
        """Guarda as escolhas do envio de estilo para o PRÓXIMO projeto.

        Gravado aqui, no servidor, e não por uma chamada a mais do navegador:
        a lembrança tem de acontecer no mesmo ato em que a escolha é enviada.
        Como pedido separado, ela falharia sozinha — e o modo de falhar seria
        silencioso, com o usuário descobrindo semanas depois que nada estava
        sendo lembrado.

        Só as chaves conhecidas, como no brand: o corpo vem do navegador, e
        gravar o que ele mandar transformaria isto em depósito.
        """
        cur: dict = {}
        try:
            cur = json.loads(ESTILO.read_text())
        except (OSError, json.JSONDecodeError):
            cur = {}
        for k in ESTILO_KEYS:
            if k in body:
                cur[k] = body[k]
        cur["atualizado"] = time.strftime("%Y-%m-%d %H:%M:%S")
        try:
            ESTILO.parent.mkdir(parents=True, exist_ok=True)
            tmp = ESTILO.with_suffix(".tmp")
            tmp.write_text(json.dumps(cur, ensure_ascii=False, indent=2))
            tmp.replace(ESTILO)
        except OSError:
            # lembrar é conforto, não contrato: um disco cheio não pode
            # derrubar o envio do estilo, que é o que o usuário veio fazer
            pass

    # ---- escolha de projeto ----
    def _projects(self) -> None:
        """O que a tela inicial oferece: recentes primeiro, achados depois.

        Duas listas separadas e não uma só ordenada por data. Um recente é uma
        escolha que a pessoa já fez; um achado é um palpite do programa. Fundir
        as duas faria o palpite competir de igual para igual com a memória, e
        no disco de quem edita há dezenas de achados para meia dúzia de
        recentes.
        """
        recent = [_project_card(Path(p)) for p in _recents_read()]
        vistos = {c["path"] for c in recent}
        found = [_project_card(Path(p)) for p in _scan_projects()
                 if p not in vistos]
        found.sort(key=lambda c: c["mtime"], reverse=True)
        self._json({
            "recent": [c for c in recent if c["exists"]],
            "found": found,
            # de onde partir quando a pessoa quiser navegar
            "home": str(Path.home()),
        })

    def _browse(self) -> None:
        """Navegar o disco pelo navegador.

        Precisa existir porque a página NÃO consegue entregar um caminho
        absoluto: `<input webkitdirectory>` dá os nomes dos arquivos e esconde
        onde eles estão, e o servidor precisa exatamente do que o navegador
        esconde. Então quem lista as pastas é este lado.
        """
        from urllib.parse import parse_qs, urlparse
        q = parse_qs(urlparse(self.path).query)
        raw = (q.get("path") or [str(Path.home())])[0]
        here = Path(raw).expanduser()
        if not here.is_dir():
            here = Path.home()
        here = here.resolve()
        dirs = []
        try:
            for d in sorted(here.iterdir(), key=lambda x: x.name.lower()):
                if not d.is_dir() or d.name.startswith("."):
                    continue
                dirs.append({
                    "name": d.name, "path": str(d),
                    # a pasta É um projeto, ou CONTÉM um: as duas se abrem, e
                    # marcá-las poupa a navegação de um nível inteiro
                    "isProject": _is_project(d),
                    "hasProject": _is_project(d / "edit"),
                })
        except OSError as exc:
            self._json({"error": str(exc)}, 400)
            return
        self._json({
            "path": str(here),
            "parent": None if here.parent == here else str(here.parent),
            "dirs": dirs,
        })

    def _open(self, body: dict) -> None:
        """Abrir um projeto — o `--root` de antes, agora em tempo de execução.

        Aceita a pasta `edit` ou a pasta de VÍDEOS que a contém, porque quem
        navega chega pelo nome do vídeo e não pelo `edit` lá dentro. Com
        `create`, uma pasta de vídeos sem `edit` vira um projeto novo: é o
        único jeito de começar um trabalho sem voltar ao terminal.
        """
        raw = str(body.get("path") or "").strip()
        if not raw:
            self._json({"error": "sem caminho"}, 400)
            return
        p = Path(raw).expanduser()
        if not p.is_dir():
            self._json({"error": f"pasta não encontrada: {p}"}, 404)
            return
        p = p.resolve()
        alvo = p if _is_project(p) else None
        if alvo is None and _is_project(p / "edit"):
            alvo = (p / "edit").resolve()
        if alvo is None:
            # pasta `edit` já existente, ainda sem state.json, conta como
            # projeto começado — recusá-la mandaria a pessoa criar um "novo"
            # por cima do que ela já tem
            if p.name == "edit" or (p / "edit").is_dir():
                alvo = (p if p.name == "edit" else p / "edit").resolve()
            elif body.get("create"):
                # Criar é DISPARAR: sem a tela de início, um projeto novo vai
                # direto para a Fase 1 — e uma pasta sem vídeo não tem o que
                # cortar. Recusar aqui explica antes; criar e falhar depois
                # deixaria um projeto vazio parado numa tela de espera.
                if not _videos_in(p):
                    self._json({"error": "não achei nenhum vídeo nesta pasta — "
                                         "coloque o arquivo nela primeiro"}, 400)
                    return
                alvo = (p / "edit").resolve()
                try:
                    alvo.mkdir(parents=True, exist_ok=True)
                except OSError as exc:
                    self._json({"error": str(exc)}, 400)
                    return
            else:
                self._json({"error": "essa pasta não tem um projeto do Avelin",
                            "canCreate": True}, 404)
                return
        # Pasta nova (ou `edit` sem state): o projeto nasce aqui, igualzinho ao
        # que a dropzone monta. Sem isto, quem entra pelo navegador de pastas
        # cai num projeto sem state nenhum, que é a tela que não sabe dizer o
        # que fazer em seguida.
        _init_state(alvo, alvo.parent.name or alvo.name, _videos_in(alvo.parent))
        _set_root(alvo)
        _recents_touch(alvo)
        # Projeto que nunca começou (recém-nascido ou parado de uma versão com
        # a tela de início) vai direto para a Fase 1; um em andamento passa reto.
        self._auto_start()
        self._json({"ok": True, "path": str(alvo), "project": _project_card(alvo)})

    def _close(self) -> None:
        _set_root(None)
        self._json({"ok": True})

    # O DISPARO da Fase 1. A tela que perguntava formato e briefing entre o
    # drop e o processamento foi removida: soltar o vídeo monta o projeto E
    # começa o corte na mesma batida, seguindo o aspect ratio do material de
    # origem (`format: "auto"`). Formato ou briefing diferentes se pedem no
    # chat — o watcher está sempre ouvindo.
    #
    # `preview_request.json` continua sendo o canal — o mesmo arquivo que o
    # watch_edits.py já vigia. `/api/start` sobrevive como rota para scripts,
    # mas o caminho normal é `_auto_start`, chamado por quem cria o projeto.
    FORMATS = {"short", "long", "auto"}

    def _begin_phase1(self, brief: str = "", fmt: str = "auto") -> str | None:
        """Escreve o `preview_request.json` e marca o começo no state.
        Devolve a mensagem de erro, ou None quando disparou."""
        state: dict = {}
        try:
            state = json.loads((self.root / "state.json").read_text())
        except (OSError, json.JSONDecodeError):
            pass
        pasta = self.root.parent
        sources = [str(s) for s in (state.get("sources") or [])]
        if not sources:
            sources = _videos_in(pasta)
        if not sources:
            return "não achei nenhum vídeo nesta pasta"
        # Os nomes gravados são relativos à pasta de vídeos; um caminho absoluto
        # (fonte que ficou fora da pasta) passa direto.
        def _abs(s: str) -> str:
            p = Path(s)
            return str(p if p.is_absolute() else (pasta / p))

        (self.root / "preview_request.json").write_text(json.dumps({
            "type": "new-project",
            "videosDir": str(pasta),
            "source": _abs(sources[0]),
            "sources": [_abs(s) for s in sources],
            "brief": brief,
            "format": fmt,
            "at": time.time(),
        }, ensure_ascii=False, indent=2))
        self._patch_state(
            awaitingStart=False,
            startedAt=time.time(),
            brief=brief,
            format=fmt,
            message="Fase 1 — gerando os cortes",
        )
        return None

    def _auto_start(self) -> None:
        """Projeto que nunca começou → Fase 1, sem perguntar.

        Só age sobre `awaitingStart` ligado — um projeto em andamento (state
        sem o flag) passa intocado, então reabrir ou arrastar de novo um
        trabalho pronto continua sendo só abrir. Também destrava projetos
        antigos que ficaram parados na tela de início que não existe mais.
        """
        try:
            st = json.loads((self.root / "state.json").read_text())
        except (OSError, json.JSONDecodeError):
            return
        if not st.get("awaitingStart"):
            return
        err = self._begin_phase1(str(st.get("brief") or ""),
                                 str(st.get("format") or "auto"))
        if err:
            # Sem fonte não há o que cortar; o recado fica no lugar da tela.
            self._patch_state(message=f"{err} — coloque o vídeo na pasta e reabra o projeto")

    def _start(self, body: dict) -> None:
        if self._no_project():
            return
        brief = str(body.get("brief") or "").strip()[:2000]
        fmt = str(body.get("format") or "auto")
        if fmt not in self.FORMATS:
            fmt = "auto"
        err = self._begin_phase1(brief, fmt)
        if err:
            self._json({"error": err}, 400)
            return
        self._json({"ok": True})

    def _adopt(self, video: Path) -> None:
        """Vídeo no disco → projeto aberto. O caminho comum das duas entradas.

        Escreve o `state.json` inicial porque um projeto sem ele não é um
        projeto: não aparece na lista de recentes na próxima vez, e o app não
        tem o que mostrar no cabeçalho. É também o recado que a skill lê para
        saber que há trabalho parado esperando a Fase 1.
        """
        pasta = _project_dir_for(video)
        edit = pasta / "edit"
        edit.mkdir(parents=True, exist_ok=True)
        # ARRASTAR UM VÍDEO DE UM PROJETO QUE JÁ EXISTE É ABRIR ELE, e nada
        # mais. Pedir a Fase 1 aqui mandaria recortar um trabalho pronto — e o
        # arquivo que mais convida a ser arrastado é justamente o render que
        # está na pasta do projeto acabado. O guarda é o `awaitingStart` que
        # o `_auto_start` exige: um state em andamento não o tem.
        #
        # Um projeto NOVO, por outro lado, dispara a Fase 1 aqui mesmo — não
        # existe mais tela entre o drop e o processamento. O corte segue o
        # aspect ratio da fonte; formato e briefing se pedem no chat.
        _init_state(edit, pasta.name,
                    [(pasta / video.name).name if (pasta / video.name).exists()
                     else str(video)])
        _set_root(edit.resolve())
        _recents_touch(Handler.root)
        self._auto_start()
        _scan_cache["at"] = 0.0  # o projeto é novo; a varredura cacheada não o tem
        self._json({"ok": True, "path": str(Handler.root),
                    "project": _project_card(Handler.root)})

    def _drop_dir(self, body: dict) -> None:
        """Arrastou uma PASTA. Mesmo problema, mesma solução.

        Uma pasta solta também chega sem caminho — só o nome e os nomes do que
        tem dentro. O nome sozinho é fraco (há `Broll` em três projetos), então
        o desempate é a lista de filhos: a pasta certa é a que contém os
        arquivos que o navegador acabou de enumerar.
        """
        import os
        name = str(body.get("name") or "").strip()
        entries = {str(x) for x in (body.get("entries") or [])}
        if not name:
            self._json({"error": "sem nome de pasta"}, 400)
            return
        melhor, melhor_nota = None, -1
        for name_root in ("Movies", "Videos", "Desktop", "Documents", "Downloads"):
            base = Path.home() / name_root
            if not base.is_dir():
                continue
            base_depth = len(base.parts)
            for dirpath, dirnames, _f in os.walk(base, onerror=lambda e: None):
                here = Path(dirpath)
                if len(here.parts) - base_depth >= SCAN_MAX_DEPTH + 2:
                    dirnames[:] = []
                    continue
                dirnames[:] = [d for d in dirnames
                               if not d.startswith(".") and d not in SCAN_SKIP]
                if name not in dirnames:
                    continue
                cand = here / name
                try:
                    nota = len(entries & {c.name for c in cand.iterdir()})
                except OSError:
                    continue
                if nota > melhor_nota:
                    melhor, melhor_nota = cand, nota
        if melhor is None:
            self._json({"error": f"não achei a pasta “{name}” no seu disco",
                        "notFound": True}, 404)
            return
        self._open({"path": str(melhor), "create": True})

    def _drop(self, body: dict) -> None:
        if body.get("kind") == "dir":
            return self._drop_dir(body)
        """Arrastou um vídeo: tenta resolver SEM transferir os bytes."""
        name = str(body.get("name") or "").strip()
        size = int(body.get("size") or 0)
        if not name:
            self._json({"error": "sem nome de arquivo"}, 400)
            return
        if Path(name).suffix.lower() not in VIDEO_EXT:
            self._json({"error": f"{Path(name).suffix or 'esse arquivo'} não é vídeo"}, 415)
            return
        found = _locate_file(name, size) if size else None
        if not found:
            # A resposta é uma INSTRUÇÃO, não um erro: o app sobe o arquivo e
            # tenta de novo pela outra porta.
            self._json({"needUpload": True})
            return
        self._adopt(found)

    def _upload(self) -> None:
        """Recebe o vídeo que não estava no disco — corpo cru, direto para o arquivo.

        Cru e não multipart: o corpo é um vídeo inteiro e um parser de
        multipart o carregaria na memória para devolver a mesma coisa. Aqui os
        bytes vão do socket para o disco em blocos, então o tamanho do arquivo
        não é o tamanho da RAM usada.
        """
        from urllib.parse import parse_qs, urlparse
        q = parse_qs(urlparse(self.path).query)
        name = (q.get("name") or [""])[0].strip()
        name = Path(name).name  # nunca deixe o nome virar caminho
        if not name or Path(name).suffix.lower() not in VIDEO_EXT:
            self._json({"error": "nome de vídeo inválido"}, 400)
            return
        try:
            total = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            total = 0
        if total <= 0:
            self._json({"error": "corpo vazio"}, 400)
            return
        dest_dir = NEW_PROJECTS_DIR / _slug(Path(name).stem)
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            alvo = dest_dir / name
            tmp = alvo.with_suffix(alvo.suffix + ".part")
            with open(tmp, "wb") as f:
                restante = total
                while restante > 0:
                    bloco = self.rfile.read(min(1 << 20, restante))
                    if not bloco:
                        break
                    f.write(bloco)
                    restante -= len(bloco)
            if restante > 0:
                tmp.unlink(missing_ok=True)
                self._json({"error": "transferência interrompida"}, 400)
                return
            tmp.replace(alvo)
        except OSError as exc:
            self._json({"error": str(exc)}, 500)
            return
        self._adopt(alvo)

    # ---- dynamic bits ----
    def _state(self) -> None:
        # O poll é o único relógio desta aplicação — é aqui que o ponteiro
        # escrito por fora é percebido, e é o que faz a aba se corrigir sozinha.
        _follow_current()
        if not self.root:
            # O ESTADO VAZIO É UM ESTADO, e responde 200. Devolver erro aqui
            # faria o poll do app tratar "nenhum projeto aberto" como servidor
            # com problema — e a tela inicial é justamente onde o app funciona.
            self._json({
                "noProject": True,
                "state": {}, "edl": None, "mtimes": {}, "videoDuration": 0,
                "hasPendingEdits": False, "progress": None,
                "serverStale": _stale(),
                "keys": {"groq": _has_key("GROQ_API_KEY"),
                         "elevenlabs": _has_key("ELEVENLABS_API_KEY"),
                         "pexels": _has_key("PEXELS_API_KEY"),
                         "google": _has_key("GOOGLE_API_KEY") and _has_key("GOOGLE_CSE_ID"),
                         "treblo": _has_key("TREBLO_API_KEY")},
                "deps": _deps(),
                "now": time.time(),
            })
            return
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
            "noProject": False,
            "root": str(self.root),
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
    # OPCIONAL de propósito. Sem ele o editor abre vazio e a pessoa escolhe na
    # tela — que é como um aplicativo se comporta. Com ele, a sessão da skill
    # continua abrindo direto no projeto de que ela já sabe o caminho.
    ap.add_argument("--root", type=Path, default=None,
                    help="abre já neste <edit> dir (a skill passa; sem isto, "
                         "o editor abre vazio)")
    ap.add_argument("--port", type=int, default=4820)
    # PADRÃO LIGADO. Ver o comentário em `_maybe_auto_apply`: com o disparo
    # opcional, o botão de enviar era um no-op sempre que não havia sessão de IA
    # atachada, que é a maior parte do tempo.
    ap.add_argument("--auto", action="store_true", default=True,
                    help="(padrão) salvar no editor já refaz o corte / a Fase 2")
    ap.add_argument("--no-auto", action="store_false", dest="auto",
                    help="só grava o pedido e espera uma sessão de IA executar")
    # ABRIR NO NAVEGADOR. Existe para quem NÃO tem o painel de preview do
    # harness — agente no terminal, máquina nova, sessão por SSH local. Sem
    # isto, a ferramenta visual sobe e o usuário fica com uma URL para colar à
    # mão justamente no momento em que ele queria só olhar.
    ap.add_argument("--open", action="store_true", dest="open_browser",
                    help="abre o editor no navegador padrão assim que subir")
    args = ap.parse_args()

    if not (APP_DIR / "index.html").exists():
        raise SystemExit(f"app not found at {APP_DIR}")

    root = None
    if args.root is not None:
        root = args.root.resolve()
        if not root.exists():
            raise SystemExit(f"edit dir not found: {root}")
        _recents_touch(root)

    _set_root(root)
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    srv.auto_apply = args.auto
    url = f"http://127.0.0.1:{args.port}"
    # PUBLICA O ENDEREÇO antes de servir. Ver o comentário em SERVER: sem isto,
    # quem escreve no chat não sabe a porta e o usuário não acha a própria tela.
    try:
        SERVER.parent.mkdir(parents=True, exist_ok=True)
        tmp = SERVER.with_suffix(".tmp")
        tmp.write_text(json.dumps({
            "url": url, "port": args.port, "pid": os.getpid(),
            "root": str(root) if root else None, "at": time.time(),
        }, ensure_ascii=False))
        tmp.replace(SERVER)
    except OSError:
        pass
    modo = " · salvar já refaz" if args.auto else ""
    onde = f"  (root: {root})" if root else "  (sem projeto — escolha na tela)"
    print(f"Avelin — editor → {url}{onde}{modo}", flush=True)
    if args.open_browser:
        # Numa thread: `webbrowser.open` pode bloquear enquanto o navegador
        # inicia, e o primeiro pedido do próprio navegador chega antes de
        # `serve_forever` — o editor abriria numa página de erro.
        import webbrowser
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    srv.serve_forever()


if __name__ == "__main__":
    main()

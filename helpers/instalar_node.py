"""Instala o Node.js do editor — só se o computador não tiver um que sirva.

  python helpers/instalar_node.py            # instala agora, mostrando o progresso
  python helpers/instalar_node.py --fundo    # dispara em segundo plano e volta na hora
  python helpers/instalar_node.py --status   # o que está acontecendo (JSON)

Por que existe: ver nodebin.py. Resumo — a Fase 2 precisa de Node >= 22, e o
instalador oficial pede a senha de administrador. Aqui o binário OFICIAL do
nodejs.org é baixado, conferido pelo SHASUMS256.txt do próprio nodejs.org e
desempacotado em ~/.avelin/node/<versão>, com `current` apontando para ele.

Regras:
  · Node >= 22 no computador → não faz nada. Nunca instala um segundo por cima.
  · Node antigo (18, 20) → instala o do editor AO LADO, sem trocar o da pessoa.
  · Nenhum Node → instala e, fora do Windows, linka node/npm/npx em
    ~/.local/bin (a mesma pasta onde o install.sh põe o uv e o ffmpeg), para o
    agente achar o Node também fora dos helpers.

Por que em segundo plano: o Node só serve à Fase 2. Esperar o download dele
seguraria o corte, que não usa Node nenhum. O progresso vai para
~/.avelin/node/estado.json; o servidor do editor lê esse arquivo a cada poll e
a checklist da tela troca de "instalando… 40%" para ✓ sozinha.

Só biblioteca padrão + requests (já dependência do projeto): roda com o python
da .venv direto, SEM `uv run`, para não disputar a trava do ambiente com o
`uv sync`/`uv run` que a pessoa usa enquanto isto baixa.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nodebin  # noqa: E402

# A linha do Node que o motor da Fase 2 usa no dia a dia. Fixar a linha (e
# pegar a última versão DENTRO dela) evita estrear uma LTS recém-lançada,
# cujos módulos nativos (sharp, onnxruntime-node) às vezes chegam depois.
LINHA = int(os.environ.get("AVE_NODE_LINHA", "24"))
DIST = "https://nodejs.org/dist"
BASE = nodebin.BASE
LOG = BASE / "instalar.log"
TRAVA = BASE / "instalando.lock"
LOCAL_BIN = Path.home() / ".local" / "bin"


def publicar(etapa: str, **extra) -> None:
    BASE.mkdir(parents=True, exist_ok=True)
    dado = {"etapa": etapa, "pid": os.getpid(), "at": time.time(), **extra}
    tmp = nodebin.ESTADO.with_suffix(".tmp")
    tmp.write_text(json.dumps(dado, ensure_ascii=False))
    tmp.replace(nodebin.ESTADO)


def alvo() -> tuple[str, str]:
    """(plataforma do nodejs.org, extensão do pacote)."""
    m = platform.machine().lower()
    arq = "arm64" if m in ("arm64", "aarch64") else "x64"
    if sys.platform == "darwin":
        return f"darwin-{arq}", "tar.gz"
    if nodebin.WIN:
        return f"win-{arq}", "zip"
    return f"linux-{arq}", "tar.gz"


def ultima_da_linha(sess) -> str:
    r = sess.get(f"{DIST}/index.json", timeout=30)
    r.raise_for_status()
    for rel in r.json():                         # vem do mais novo para o mais velho
        if nodebin.major(rel["version"]) == LINHA:
            return rel["version"]
    raise RuntimeError(f"nenhuma versão {LINHA}.x no nodejs.org")


def baixar(sess, url: str, destino: Path) -> None:
    with sess.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length") or 0)
        feito, ultimo = 0, 0.0
        with open(destino, "wb") as f:
            for bloco in r.iter_content(chunk_size=1 << 16):
                f.write(bloco)
                feito += len(bloco)
                agora = time.time()
                if total and agora - ultimo > 0.5:
                    publicar("baixando", progresso=round(feito / total, 3))
                    ultimo = agora


def conferir(sess, versao: str, nome: str, arquivo: Path) -> None:
    r = sess.get(f"{DIST}/{versao}/SHASUMS256.txt", timeout=30)
    r.raise_for_status()
    esperado = next((l.split()[0] for l in r.text.splitlines() if l.endswith("  " + nome)), None)
    if not esperado:
        raise RuntimeError(f"{nome} não está no SHASUMS256.txt")
    h = hashlib.sha256()
    with open(arquivo, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    if h.hexdigest() != esperado:
        raise RuntimeError("o arquivo baixado não confere com o checksum oficial")


def extrair(arquivo: Path, destino: Path) -> Path:
    destino.mkdir(parents=True, exist_ok=True)
    if arquivo.name.endswith(".zip"):
        with zipfile.ZipFile(arquivo) as z:
            z.extractall(destino)
    else:
        with tarfile.open(arquivo) as t:
            try:
                t.extractall(destino, filter="data")
            except TypeError:                    # Python sem o filtro (< 3.10.12)
                t.extractall(destino)
    dentro = [p for p in destino.iterdir() if p.is_dir()]
    if len(dentro) != 1:
        raise RuntimeError("pacote do Node com formato inesperado")
    return dentro[0]


def apontar_current(pasta: Path) -> None:
    atual = BASE / "current"
    if nodebin.WIN:
        # symlink no Windows pede modo desenvolvedor; uma junção não pede.
        if atual.exists():
            subprocess.run(["cmd", "/c", "rmdir", str(atual)], check=False)
        subprocess.run(["cmd", "/c", "mklink", "/J", str(atual), str(pasta)], check=True,
                       capture_output=True)
        return
    tmp = BASE / "current.tmp"
    if tmp.is_symlink() or tmp.exists():
        tmp.unlink()
    tmp.symlink_to(pasta.name)
    tmp.replace(atual)                           # troca atômica


def linkar_local_bin() -> list[str]:
    """Só quando a pessoa não tinha Node nenhum: põe node/npm/npx em
    ~/.local/bin. Com um Node antigo dela no PATH, linkar aqui mudaria o
    `node` de outros projetos dela — e isso o editor não faz."""
    if nodebin.WIN or nodebin.do_sistema():
        return []
    LOCAL_BIN.mkdir(parents=True, exist_ok=True)
    feitos = []
    for nome in ("node", "npm", "npx"):
        origem = nodebin.pasta_bin(BASE / "current") / nome
        link = LOCAL_BIN / nome
        if link.exists() and not link.is_symlink():
            continue                             # arquivo de outra pessoa/programa: não mexe
        if link.is_symlink():
            link.unlink()
        link.symlink_to(origem)
        feitos.append(str(link))
    return feitos


def limpar_antigas(manter: Path) -> None:
    for p in BASE.iterdir():
        if p.is_dir() and not p.is_symlink() and p.name.startswith("node-v") and p != manter:
            shutil.rmtree(p, ignore_errors=True)


def instalar() -> int:
    est = nodebin.estado()
    if est["ok"]:
        print(f"Node.js {est['versao']} ({est['origem']}) já serve — nada a fazer.")
        return 0
    BASE.mkdir(parents=True, exist_ok=True)
    # Uma instalação por vez: o install.sh roda de novo para atualizar, e duas
    # escritas no mesmo `current` deixariam o link apontando para meia pasta.
    try:
        fd = os.open(TRAVA, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
    except FileExistsError:
        try:
            pid = int(TRAVA.read_text().strip() or 0)
        except (OSError, ValueError):
            pid = 0
        if nodebin._vivo(pid):
            print("Já há uma instalação do Node.js em andamento.")
            return 0
        TRAVA.unlink(missing_ok=True)
        return instalar()
    try:
        import requests
        sess = requests.Session()
        sess.headers["User-Agent"] = "ave-instalador"
        publicar("baixando", progresso=0)
        versao = ultima_da_linha(sess)
        plat, ext = alvo()
        nome = f"node-{versao}-{plat}.{ext}"
        print(f"Baixando Node.js {versao} ({plat})…", flush=True)
        with tempfile.TemporaryDirectory(dir=BASE) as tmpd:
            arquivo = Path(tmpd) / nome
            baixar(sess, f"{DIST}/{versao}/{nome}", arquivo)
            publicar("conferindo", progresso=1)
            conferir(sess, versao, nome, arquivo)
            publicar("extraindo", progresso=1)
            pasta = extrair(arquivo, Path(tmpd) / "x")
            final = BASE / pasta.name
            if final.exists():
                shutil.rmtree(final)
            shutil.move(str(pasta), str(final))
        apontar_current(final)
        links = linkar_local_bin()
        exe = nodebin.privado()
        v = nodebin.versao(str(exe)) if exe else None
        if nodebin.major(v) < nodebin.MIN_MAJOR:
            raise RuntimeError("o Node.js instalado não respondeu")
        limpar_antigas(final)
        publicar("pronto", versao=v, links=links)
        print(f"Node.js {v} pronto em {final}", flush=True)
        return 0
    except Exception as exc:  # noqa: BLE001 — sem rede, disco cheio… vira estado na tela
        publicar("erro", erro=str(exc)[:300])
        print(f"Não consegui instalar o Node.js: {exc}", file=sys.stderr, flush=True)
        return 1
    finally:
        TRAVA.unlink(missing_ok=True)


def em_segundo_plano() -> int:
    """Dispara a si mesmo desligado deste processo e volta na hora."""
    if nodebin.estado()["ok"]:
        print("Node.js já serve — nada a instalar.")
        return 0
    BASE.mkdir(parents=True, exist_ok=True)
    log = open(LOG, "ab")
    kw: dict = {"stdin": subprocess.DEVNULL, "stdout": log, "stderr": log, "close_fds": True}
    if nodebin.WIN:
        kw["creationflags"] = 0x00000008 | 0x00000200   # DETACHED_PROCESS | NEW_PROCESS_GROUP
    else:
        kw["start_new_session"] = True
    p = subprocess.Popen([sys.executable, str(Path(__file__).resolve())], **kw)
    # publica já, com o pid do FILHO, para a tela não mostrar "falta" no meio
    # segundo antes de ele subir (e não dar a instalação por morta: este
    # processo sai agora)
    nodebin.ESTADO.write_text(json.dumps({"etapa": "baixando", "progresso": 0, "pid": p.pid,
                                          "at": time.time()}))
    print(f"Node.js: instalando em segundo plano (registro em {LOG}).")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Instala o Node.js do editor, se o computador não tiver um que sirva")
    ap.add_argument("--fundo", action="store_true", help="instala em segundo plano e volta na hora")
    ap.add_argument("--status", action="store_true", help="mostra o estado em JSON")
    args = ap.parse_args()
    if args.status:
        print(json.dumps(nodebin.estado(), ensure_ascii=False, indent=1))
        return 0
    return em_segundo_plano() if args.fundo else instalar()


if __name__ == "__main__":
    sys.exit(main())

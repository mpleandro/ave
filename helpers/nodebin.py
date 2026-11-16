"""Node.js sem instalador de sistema: o do computador quando serve, senão o do editor.

O motor da Fase 2 (`npx hyperframes@0.7.109`) exige Node >= 22 (campo
`engines` do pacote, conferido em 2026-11-12). Até aqui o Node era o único
programa que a instalação não trazia: o `.pkg` do Mac e o `.msi` do Windows
pedem a senha de administrador, e a promessa da instalação é não pedir.

A saída é a mesma do ffmpeg (ver ffbin.py): o binário OFICIAL do nodejs.org,
desempacotado numa pasta do usuário (`~/.avelin/node/`), sem tocar no sistema.
O `instalar_node.py` baixa; este módulo decide qual Node usar:

  1. há `node` no PATH, versão >= 22, e não é o nosso?  → usa esse, nada muda;
  2. senão, há o do editor em ~/.avelin/node/current?   → põe a pasta dele NA
     FRENTE do PATH deste processo (e dos filhos, que herdam o ambiente);
  3. senão → nenhum; a Fase 2 avisa, a Fase 1 segue.

Um Node antigo da pessoa (18, 20) NÃO é trocado nem apagado: o do editor só
fica na frente dentro dos processos do editor.

Chame `garantir()` antes de rodar `npx`/`node`. `estado()` é o que a
conferência e o servidor do editor mostram (inclui a instalação em andamento).
"""
from __future__ import annotations

import functools
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

MIN_MAJOR = 22
BASE = Path.home() / ".avelin" / "node"
ESTADO = BASE / "estado.json"
WIN = sys.platform.startswith("win")


def pasta_bin(raiz: Path) -> Path:
    """Onde ficam node/npm/npx dentro de uma distribuição oficial."""
    return raiz if WIN else raiz / "bin"


def privado() -> Path | None:
    """O executável do Node do editor, se já foi instalado."""
    exe = pasta_bin(BASE / "current") / ("node.exe" if WIN else "node")
    return exe if exe.is_file() else None


def _e_nosso(caminho: str) -> bool:
    try:
        return Path(caminho).resolve().is_relative_to(BASE.resolve())
    except (OSError, ValueError):
        return False


@functools.lru_cache(maxsize=8)
def _versao_cache(exe: str, mtime: float) -> str | None:
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=10).stdout.strip()
        return out or None
    except (OSError, subprocess.TimeoutExpired):
        return None


def versao(exe: str) -> str | None:
    """`v24.11.1`, sondado uma vez por binário (o servidor pergunta a cada 2 s)."""
    try:
        mtime = os.stat(exe).st_mtime
    except OSError:
        return None
    return _versao_cache(exe, mtime)


def major(v: str | None) -> int:
    try:
        return int((v or "").lstrip("v").split(".")[0])
    except ValueError:
        return 0


def do_sistema() -> tuple[str, str | None] | None:
    """(caminho, versão) do Node que a pessoa já tinha — ignora o nosso."""
    for d in os.environ.get("PATH", "").split(os.pathsep):
        if not d:
            continue
        exe = shutil.which("node", path=d)
        if exe and not _e_nosso(exe):
            return exe, versao(exe)
    return None


def sistema_serve() -> bool:
    s = do_sistema()
    return bool(s) and major(s[1]) >= MIN_MAJOR


def ler_instalacao() -> dict | None:
    """O que o `instalar_node.py` publicou. Um processo que morreu no meio
    (máquina dormiu, Ctrl+C) não pode ficar "instalando" para sempre."""
    try:
        d = json.loads(ESTADO.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if d.get("etapa") in ("baixando", "conferindo", "extraindo"):
        if not _vivo(d.get("pid")) or time.time() - d.get("at", 0) > 600:
            d["etapa"] = "erro"
            d["erro"] = "a instalação do Node.js foi interrompida"
    return d


def _vivo(pid) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    if WIN:
        try:
            out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                                 capture_output=True, text=True, timeout=5).stdout
            return str(pid) in out
        except (OSError, subprocess.TimeoutExpired):
            return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def garantir() -> str:
    """Deixa um Node >= 22 na frente do PATH. Devolve de onde ele veio:
    'sistema', 'avelin' ou 'nenhum'."""
    if sistema_serve():
        return "sistema"
    exe = privado()
    if exe is None:
        return "nenhum"
    d = str(exe.parent)
    partes = os.environ.get("PATH", "").split(os.pathsep)
    if not partes or partes[0] != d:
        os.environ["PATH"] = os.pathsep.join([d] + [p for p in partes if p != d])
    return "avelin"


def estado() -> dict:
    """Para a conferência e para a checklist do editor.

    {ok, versao, origem, instalando, etapa, progresso, erro}"""
    s = do_sistema()
    if s and major(s[1]) >= MIN_MAJOR:
        return {"ok": True, "versao": s[1], "origem": "sistema", "instalando": False}
    exe = privado()
    if exe is not None:
        v = versao(str(exe))
        if major(v) >= MIN_MAJOR:
            return {"ok": True, "versao": v, "origem": "avelin", "instalando": False}
    inst = ler_instalacao() or {}
    etapa = inst.get("etapa")
    rel = {"ok": False, "versao": s[1] if s else None, "origem": "nenhum",
           "instalando": etapa in ("baixando", "conferindo", "extraindo"),
           "etapa": etapa, "progresso": inst.get("progresso")}
    if rel["instalando"]:
        rel["erro"] = "instalando em segundo plano"
    elif etapa == "erro":
        rel["erro"] = inst.get("erro") or "a instalação do Node.js falhou"
    elif s:
        rel["erro"] = f"Node {s[1]} é antigo; a Fase 2 precisa do {MIN_MAJOR} ou mais"
    else:
        rel["erro"] = "Node.js não encontrado"
    return rel


if __name__ == "__main__":
    print(json.dumps({"garantir": garantir(), **estado()}, ensure_ascii=False, indent=1))

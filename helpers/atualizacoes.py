#!/usr/bin/env python3
"""ATUALIZAÇÕES — o Avelin avisa quando tem versão nova no GitHub.

Quem usa o Avelin não fica olhando o repositório. Sem este aviso, uma correção
publicada há três semanas continua faltando na máquina da pessoa até ela
lembrar de pedir "atualiza o Avelin" — e ela só lembra depois de esbarrar no
defeito que já estava resolvido.

    uv run python helpers/atualizacoes.py           # confere (respeita a frequência)
    uv run python helpers/atualizacoes.py --agora   # busca no GitHub agora
    uv run python helpers/atualizacoes.py --json    # para máquina

Roda no início de toda rodada (ver SKILL.md, Setup). Duas partes, com custos
diferentes:

  · BUSCAR no GitHub (`git fetch`) — rede, alguns segundos. Acontece uma vez
    por semana por padrão; `AVE_ATUALIZACOES=rodada` no `.env` busca a cada
    rodada, `nunca` desliga tudo.
  · COMPARAR com o que já foi buscado — local, instantâneo. Acontece SEMPRE:
    a busca semanal achou novidade, e toda rodada seguinte lembra até a pessoa
    atualizar. Uma linha, nunca bloqueia o trabalho.

Sem novidade, sem rede ou fora de um clone git, não imprime nada e sai 0 — o
aviso é para quando há algo a dizer. Nunca atualiza sozinho: atualizar é
decisão da pessoa, e o `git pull` está em install.md ("Keeping the skill
current").

Também confere o ffmpeg: o 9 é a versão em que a skill é testada. Abaixo
dele tudo segue funcionando (≥ 4.x basta) — é recomendação, não bloqueio.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

AVE = Path(__file__).resolve().parent.parent
ESTADO = AVE / ".ave-atualizacoes.json"
RAMO = "origin/main"
SEMANA = 7 * 24 * 3600
FFMPEG_RECOMENDADO = 9


def _frequencia() -> str:
    """`rodada`, `semanal` (padrão) ou `nunca` — env vence o `.env`."""
    valor = os.environ.get("AVE_ATUALIZACOES", "")
    if not valor and (AVE / ".env").exists():
        for linha in (AVE / ".env").read_text(encoding="utf-8").splitlines():
            if linha.strip().startswith("AVE_ATUALIZACOES="):
                valor = linha.split("=", 1)[1].strip().strip("\"'")
    valor = valor.lower()
    return valor if valor in ("rodada", "semanal", "nunca") else "semanal"


def _git(*args: str, timeout: float = 10) -> str | None:
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")  # nunca parar pedindo senha
    try:
        r = subprocess.run(["git", "-C", str(AVE), *args], capture_output=True,
                           text=True, timeout=timeout, env=env)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def _ler_estado() -> dict:
    try:
        return json.loads(ESTADO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _buscar(forcar: bool) -> bool:
    """`git fetch` quando venceu o prazo. True se buscou com sucesso agora."""
    freq = _frequencia()
    estado = _ler_estado()
    vencido = time.time() - estado.get("ultima_busca", 0) >= SEMANA
    if not (forcar or freq == "rodada" or vencido):
        return False
    # sem rede ou GitHub fora: segue com o que já foi buscado, sem reclamar
    if _git("fetch", "--quiet", "origin", "main", timeout=20) is None:
        return False
    estado["ultima_busca"] = time.time()
    try:
        ESTADO.write_text(json.dumps(estado), encoding="utf-8")
    except OSError:
        pass
    return True


def _ffmpeg() -> dict | None:
    try:
        r = subprocess.run(["ffmpeg", "-hide_banner", "-version"],
                           capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.search(r"ffmpeg version n?(\d+)\.(\d+)", r.stdout)
    if not m:  # build do git (N-12345-g…): não dá para afirmar nada
        return None
    major = int(m.group(1))
    return {"versao": f"{m.group(1)}.{m.group(2)}", "major": major,
            "abaixo_do_recomendado": major < FFMPEG_RECOMENDADO}


def verificar(forcar: bool = False) -> dict:
    out: dict = {"frequencia": _frequencia(), "ffmpeg": _ffmpeg()}
    if out["frequencia"] == "nunca" or _git("rev-parse", "--git-dir") is None:
        out["repo"] = None
        return out
    out["buscou_agora"] = _buscar(forcar)
    if _git("rev-parse", "--verify", "--quiet", RAMO) is None:
        out["repo"] = None
        return out

    atras = int(_git("rev-list", "--count", f"HEAD..{RAMO}") or 0)
    frente = int(_git("rev-list", "--count", f"{RAMO}..HEAD") or 0)
    novidades = []
    if atras:
        log = _git("log", "--no-merges", "--format=%h\t%cs\t%s",
                   f"HEAD..{RAMO}") or ""
        novidades = [dict(zip(("commit", "data", "titulo"), l.split("\t", 2)))
                     for l in log.splitlines() if l.count("\t") >= 2]
    mudou = (_git("diff", "--name-only", f"HEAD...{RAMO}") or "").splitlines() if atras else []
    out["repo"] = {
        "ramo_local": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "atras": atras,
        "a_frente": frente,
        "novidades": novidades,
        # `uv sync` depois do pull — instalar.py não pega pacote novo da base
        "precisa_sync": any(f in ("pyproject.toml", "uv.lock") for f in mudou),
        # mudança local não comitada ou ramo divergente: o `pull --ff-only`
        # pode recusar, e quem atualiza precisa saber ANTES de tentar
        "mudancas_locais": bool(_git("status", "--porcelain", "--untracked-files=no")),
        "divergiu": bool(atras and frente),
    }
    return out


def _texto(r: dict) -> str:
    linhas = []
    repo = r.get("repo")
    if repo and repo["atras"]:
        # merges entram em `atras` mas não na lista — contar o que se lista
        n = len(repo["novidades"]) or repo["atras"]
        linhas.append(f"Avelin: {n} {'atualização nova' if n == 1 else 'atualizações novas'}"
                      f" no GitHub ({RAMO}).")
        for c in repo["novidades"][:15]:
            linhas.append(f"  · {c['data']}  {c['titulo']}")
        if len(repo["novidades"]) > 15:
            linhas.append(f"  · … e mais {len(repo['novidades']) - 15}")
        if repo["precisa_sync"]:
            linhas.append("  depois do pull: uv sync --inexact (mudaram as dependências)")
        if repo["divergiu"]:
            linhas.append(f"  atenção: o ramo local ({repo['ramo_local']}) tem "
                          f"{repo['a_frente']} commit(s) que o {RAMO} não tem — "
                          "o pull --ff-only vai recusar")
        elif repo["mudancas_locais"]:
            linhas.append("  atenção: há mudanças locais não comitadas — confira antes do pull")
    ff = r.get("ffmpeg")
    if ff and ff["abaixo_do_recomendado"]:
        linhas.append(f"ffmpeg {ff['versao']}: funciona, mas o recomendado é o "
                      f"{FFMPEG_RECOMENDADO} (brew upgrade ffmpeg / "
                      "winget upgrade Gyan.FFmpeg)")
    return "\n".join(linhas)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--agora", action="store_true",
                    help="buscar no GitHub agora, ignorando a frequência")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    r = verificar(forcar=a.agora)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    elif (t := _texto(r)):
        print(t)
    sys.exit(0)


if __name__ == "__main__":
    main()

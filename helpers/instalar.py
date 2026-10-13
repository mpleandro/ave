#!/usr/bin/env python3
"""INSTALAÇÃO GRADUAL — cada efeito instala o que precisa, na primeira vez.

A instalação base do Avelin é leve (corte, cor, legenda, Fase 2). O que é
pesado ou específico vira um RECURSO que se instala sozinho no momento em que
o usuário pede o efeito que depende dele — nunca antes, e nunca exigindo que
quem escolheu na tela abra um terminal.

    uv run python helpers/instalar.py status            # o que está pronto e o que falta
    uv run python helpers/instalar.py recorte           # instala (se faltar) e confere
    uv run python helpers/instalar.py recorte --check   # só confere (exit 0 = pronto)

Do código:

    import instalar
    instalar.garantir("recorte")        # instala se faltar; True quando pronto
    instalar.reexecutar_com("escuta")   # instala e reinicia o PRÓPRIO script

Os recursos:

  recorte  — torch + Robust Video Matting (~2 GB): cabeça vazando o card, teste
             de recorte de 5s, elemento atrás do apresentador
  anim3d   — MediaPipe + Depth Anything (~2,5 GB): formato "Animação em 3D"
  escuta   — mlx-whisper + modelo turbo (~1,6 GB, só Apple Silicon): ouvir o
             corte atrás de repetição — o portão da Fase 1
  link     — yt-dlp (~10 MB): editar a partir de um link (YouTube, Instagram…)

Três regras, cada uma com um defeito por trás (herdadas do instalar_anim3d):
  1. `uv sync --extra X --inexact`: sem `--inexact`, instalar um extra
     DESINSTALA os outros — pedir 3D apagava o recorte.
  2. Modelos baixados AQUI, com uma linha dizendo o que é — um download de
     1 GB no meio de um render parece travamento.
  3. Conferência num processo NOVO: pacote recém-instalado no mesmo
     interpretador pode carregar pela metade.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

HELPERS = Path(__file__).resolve().parent
SKILL = HELPERS.parent
REGISTRO = Path.home() / ".avelin" / "instalados.json"
APPLE_SILICON = sys.platform == "darwin" and platform.machine() == "arm64"


def _baixar_rvm(py: str) -> None:
    # o torch.hub guarda o repositório e o peso em ~/.cache/torch/hub — uma vez
    _rodar([py, "-c", "import torch; torch.hub.load('PeterL1n/RobustVideoMatting', "
                      "'mobilenetv3', trust_repo=True)"],
           "baixando o modelo de recorte (Robust Video Matting, ~15 MB)")


def _baixar_whisper(py: str) -> None:
    sys.path.insert(0, str(HELPERS))
    modelo = "mlx-community/whisper-large-v3-turbo"
    _rodar([py, "-c", f"from huggingface_hub import snapshot_download; "
                      f"snapshot_download({modelo!r})"],
           "baixando o modelo de escuta (whisper-large-v3-turbo, ~1,6 GB)")


RECURSOS: dict[str, dict] = {
    "recorte": {
        "nome": "Recorte do apresentador",
        "para": "cabeça vazando o card, teste de recorte, elemento atrás do apresentador",
        "tamanho": "~2 GB", "extra": "matting",
        "confere": "import torch, torchvision",
        "depois": _baixar_rvm,
    },
    "anim3d": {
        "nome": "Animação em 3D",
        "para": "o formato Animação em 3D (rastreio de mãos, profundidade)",
        "tamanho": "~2,5 GB", "delega": "instalar_anim3d",
    },
    "escuta": {
        "nome": "Escuta local do corte",
        "para": "ouvir o corte atrás de frase repetida (portão da Fase 1)",
        "tamanho": "~1,6 GB", "extra": "escuta",
        "confere": "import mlx_whisper",
        "depois": _baixar_whisper,
        "so_apple": True,
    },
    "link": {
        "nome": "Baixar de link",
        "para": "editar a partir de um link (YouTube, Instagram, TikTok…)",
        "tamanho": "~10 MB", "extra": "link",
        "confere": "import yt_dlp",
    },
}


def say(msg: str) -> None:
    print(f"[instalar] {msg}", flush=True)


def python_do_projeto() -> str:
    venv = SKILL / ".venv" / "bin" / "python"
    return str(venv) if venv.exists() else sys.executable


def achar_uv() -> str | None:
    for c in (shutil.which("uv"), str(Path.home() / ".local/bin/uv"),
              "/opt/homebrew/bin/uv", "/usr/local/bin/uv"):
        if c and Path(c).exists():
            return c
    return None


def _rodar(cmd: list, o_que: str) -> None:
    say(o_que + "…")
    env = {**os.environ, "HF_HUB_DISABLE_PROGRESS_BARS": "1"}
    r = subprocess.run(cmd, cwd=SKILL, env=env)
    if r.returncode != 0:
        raise RuntimeError(f"falhou: {o_que}")


def disponivel(rid: str) -> tuple[bool, str]:
    r = RECURSOS[rid]
    if r.get("so_apple") and not APPLE_SILICON:
        return False, f"{r['nome']} só roda em Mac com Apple Silicon"
    return True, ""


def pronto(rid: str) -> bool:
    r = RECURSOS[rid]
    if r.get("delega"):
        mod = __import__(r["delega"])
        st = mod.status(mod.python_do_projeto())
        return bool(st.get("pacotes") and st.get("modelos_mediapipe"))
    if not disponivel(rid)[0]:
        return False
    py = python_do_projeto()
    ok = subprocess.run([py, "-c", r["confere"]], capture_output=True).returncode == 0
    if ok and rid == "recorte":
        hub = Path.home() / ".cache" / "torch" / "hub"
        ok = any(hub.glob("PeterL1n_RobustVideoMatting*"))
    return ok


def _registrar(rid: str, ok: bool, segundos: float) -> None:
    try:
        reg = json.loads(REGISTRO.read_text())
    except (OSError, json.JSONDecodeError):
        reg = {}
    reg[rid] = {"ok": ok, "quando": time.strftime("%Y-%m-%d %H:%M"),
                "segundos": round(segundos)}
    REGISTRO.parent.mkdir(parents=True, exist_ok=True)
    REGISTRO.write_text(json.dumps(reg, ensure_ascii=False, indent=2))


def garantir(rid: str, progresso=None) -> bool:
    """Instala o recurso se faltar e confere num processo novo.

    `progresso(texto)` (opcional) recebe as etapas — é como a Fase 2 mostra na
    tela de carregamento que está instalando, e não travada."""
    if rid not in RECURSOS:
        raise SystemExit(f"recurso desconhecido: {rid} ({', '.join(RECURSOS)})")
    r = RECURSOS[rid]
    ok, motivo = disponivel(rid)
    if not ok:
        say(motivo)
        return False
    if pronto(rid):
        return True
    aviso = f"{r['nome']}: primeira vez — instalando {r['tamanho']} (uma vez só)"
    say(aviso)
    if progresso:
        progresso(f"instalando {r['nome'].lower()} — primeira vez, {r['tamanho']}")
    t0 = time.time()
    if r.get("delega"):
        sys.path.insert(0, str(HELPERS))
        ok = __import__(r["delega"]).garantir()
        _registrar(rid, ok, time.time() - t0)
        return ok
    py = python_do_projeto()
    try:
        uv = achar_uv()
        if uv:
            _rodar([uv, "sync", "--extra", r["extra"], "--inexact"],
                   f"instalando pacotes (uv sync --extra {r['extra']} --inexact)")
        else:
            _rodar([py, "-m", "pip", "install", "-e", f".[{r['extra']}]"],
                   "uv não encontrado — instalando com pip")
        if r.get("depois"):
            r["depois"](py)
    except RuntimeError as e:
        say(str(e))
        _registrar(rid, False, time.time() - t0)
        return False
    ok = pronto(rid)
    _registrar(rid, ok, time.time() - t0)
    say(f"{r['nome']}: pronto ✓ ({time.time() - t0:.0f}s)" if ok
        else f"{r['nome']}: instalado, mas a conferência falhou — veja as linhas acima")
    return ok


def reexecutar_com(rid: str) -> None:
    """Para um script que descobriu, ao importar, que falta o recurso: instala e
    se REINICIA num processo novo (regra 3) com os mesmos argumentos."""
    if not garantir(rid):
        raise SystemExit(f"{RECURSOS[rid]['nome']} não ficou pronto — "
                         f"rode: uv run python helpers/instalar.py {rid}")
    os.execv(python_do_projeto(), [python_do_projeto(), *sys.argv])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("recurso", choices=["status", *RECURSOS])
    ap.add_argument("--check", action="store_true", help="só confere; exit 0 se pronto")
    a = ap.parse_args()
    if a.recurso == "status":
        for rid, r in RECURSOS.items():
            disp, motivo = disponivel(rid)
            est = "pronto" if pronto(rid) else ("indisponível" if not disp else "não instalado")
            print(f"  {rid:<8} {est:<14} {r['tamanho']:<9} {r['nome']} — {r['para']}"
                  + (f"  ({motivo})" if motivo else ""))
        return
    if a.check:
        ok = pronto(a.recurso)
        print("pronto" if ok else "não instalado")
        sys.exit(0 if ok else 1)
    sys.exit(0 if garantir(a.recurso) else 1)


if __name__ == "__main__":
    main()

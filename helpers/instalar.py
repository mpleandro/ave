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
  enquadramento — MediaPipe + 3 modelos pequenos (~100 MB): o garimpo de cortes
             deixa o vídeo horizontal em pé seguindo quem está falando

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


MODELOS = Path.home() / ".avelin" / "modelos"
# (arquivo, endereço oficial, sha256, para que serve — em linguagem simples)
MODELOS_ENQUADRAMENTO = [
    ("face_detection_yunet_2023mar.onnx",
     "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/"
     "face_detection_yunet/face_detection_yunet_2023mar.onnx",
     "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4", "o detector de rostos"),
    ("face_landmarker.task",
     "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/"
     "float16/1/face_landmarker.task",
     "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff", "o leitor de boca (quem está falando)"),
    ("wespeaker_resnet34.onnx",
     "https://huggingface.co/Wespeaker/wespeaker-voxceleb-resnet34-LM/resolve/main/"
     "voxceleb_resnet34_LM.onnx",
     "7bb2f06e9df17cdf1ef14ee8a15ab08ed28e8d0ef5054ee135741560df2ec068", "o reconhecedor de vozes"),
]


def _baixar_modelos_enquadramento(py: str) -> None:
    """Baixa o que falta e confere o sha256 — arquivo corrompido ou trocado no
    caminho não entra: um modelo errado detectaria rosto errado em silêncio."""
    import hashlib  # noqa: PLC0415
    import urllib.request  # noqa: PLC0415
    MODELOS.mkdir(parents=True, exist_ok=True)
    for nome, url, sha, o_que in MODELOS_ENQUADRAMENTO:
        alvo = MODELOS / nome
        if alvo.exists() and hashlib.sha256(alvo.read_bytes()).hexdigest() == sha:
            continue
        say(f"baixando {o_que}…")
        tmp = alvo.with_suffix(".parcial")
        urllib.request.urlretrieve(url, tmp)
        if hashlib.sha256(tmp.read_bytes()).hexdigest() != sha:
            tmp.unlink(missing_ok=True)
            raise RuntimeError(f"o arquivo de {o_que} chegou diferente do esperado")
        tmp.rename(alvo)


def _modelos_ok() -> bool:
    return all((MODELOS / nome).exists() for nome, *_ in MODELOS_ENQUADRAMENTO)


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
    "enquadramento": {
        "nome": "Enquadramento vertical",
        "para": "vídeo deitado vira em pé seguindo quem está falando (garimpo de cortes)",
        "tamanho": "~100 MB", "extra": "enquadramento",
        "confere": "import mediapipe, cv2; cv2.FaceDetectorYN",
        "depois": _baixar_modelos_enquadramento,
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
    if ok and rid == "enquadramento":
        ok = _modelos_ok()
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

"""Confere a instalação sem rede e sem chave — e prepara o que falta.

  uv run python helpers/doctor.py             # ✓/✗ de cada peça, exit 1 se faltar algo da Fase 1
  uv run python helpers/doctor.py --preparar  # baixa ffmpeg estático (se preciso) e o modelo de voz
  uv run python helpers/doctor.py --json

O que confere:
  ffmpeg/ffprobe (com zscale, deesser, loudnorm) · VAD (Silero/onnx) · Whisper
  local (transcreve 2 s de áudio sintético de verdade, não só importa) ·
  Node ≥ 18 (Fase 2) · permissões do Claude Code (allowlist sugerida).

Nenhuma chave de API é conferida: nenhuma é obrigatória. Groq/ElevenLabs
só servem como reserva em máquina sem transcrição local.
"""
from __future__ import annotations

import argparse
import json
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

HELPERS = Path(__file__).resolve().parent
SKILL = HELPERS.parent
sys.path.insert(0, str(HELPERS))

ALLOWLIST = [
    "Bash(uv run python helpers/*)",
    "Bash(uv run --directory ~/.claude/skills/ave python helpers/*)",
    "Bash(ffmpeg *)", "Bash(ffprobe *)",
    "Bash(git -C ~/.claude/skills/ave pull --ff-only)",
    "Bash(curl -s localhost:4820/*)",
]


def _ok(cond: bool) -> str:
    return "✓" if cond else "✗"


def checar_ffmpeg() -> dict:
    import ffbin
    origem = ffbin.garantir()
    ff, fp = ffbin.caminhos()
    r: dict = {"ok": False, "origem": origem, "ffmpeg": ff}
    if origem == "nenhum" or not shutil.which(ff):
        r["erro"] = "ffmpeg não encontrado — rode `doctor.py --preparar` (baixa o estático, sem brew)"
        return r
    try:
        v = subprocess.run([ff, "-version"], capture_output=True, text=True, timeout=10).stdout.splitlines()[0]
        filtros = subprocess.run([ff, "-hide_banner", "-filters"], capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.TimeoutExpired, IndexError) as exc:
        r["erro"] = f"ffmpeg não responde: {exc}"
        return r
    m = re.search(r"ffmpeg version n?(\d+)\.(\d+)", v)
    r["versao"] = m.group(0).split()[-1] if m else "?"
    faltam = [f for f in ("zscale", "deesser", "loudnorm", "silencedetect") if f" {f} " not in filtros]
    r["faltam"] = faltam
    r["ok"] = not faltam and (not m or int(m.group(1)) >= 5)
    if faltam:
        r["erro"] = f"ffmpeg sem {', '.join(faltam)} — rode `doctor.py --preparar`"
    return r


def checar_vad() -> dict:
    try:
        import numpy as np
        import torch
        from silero_vad import get_speech_timestamps, load_silero_vad
        m = load_silero_vad(onnx=True)
        sr = 16000
        t = np.arange(sr * 2) / sr
        tom = (0.3 * np.sin(2 * np.pi * 220 * t) * (np.sin(2 * np.pi * 3 * t) > 0)).astype("float32")
        ts = get_speech_timestamps(torch.from_numpy(tom), m, sampling_rate=sr)
        return {"ok": True, "regioes_no_teste": len(ts)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "erro": f"{type(exc).__name__}: {exc}"[:200]}


def checar_whisper(transcrever: bool = True) -> dict:
    import transcribe_local as TL
    r: dict = {"ok": False, "apple_silicon": TL._APPLE_SILICON}
    if not TL.disponivel():
        r["erro"] = "motor local não instalado — rode `uv sync --inexact` na pasta do Avelin"
        return r
    modelo_dir = Path.home() / ".cache" / "huggingface" / "hub"
    tem_modelo = any(modelo_dir.glob("models--mlx-community--whisper-large-v3-turbo")) if TL._APPLE_SILICON \
        else any(modelo_dir.glob("models--Systran--faster-whisper-large-v3-turbo")) or \
        any(modelo_dir.glob("models--*large-v3-turbo*"))
    r["modelo_baixado"] = bool(tem_modelo)
    if not tem_modelo:
        r["erro"] = "modelo de voz ainda não baixado (~1,6 GB) — rode `doctor.py --preparar`"
        return r
    if not transcrever:
        r["ok"] = True
        return r
    try:
        import numpy as np
        sr = 16000
        t = np.arange(int(sr * 1.5)) / sr
        seg = (0.05 * np.sin(2 * np.pi * 180 * t)).astype("float32")
        motor = TL.Motor(language="pt", verbose=False)
        motor.transcrever(seg)   # só precisa não explodir; tom puro vira "" ou lixo
        r["ok"] = True
        r["motor"] = motor.nome
    except Exception as exc:  # noqa: BLE001
        r["erro"] = f"{type(exc).__name__}: {exc}"[:200]
    return r


def checar_node() -> dict:
    node = shutil.which("node")
    if not node:
        return {"ok": False, "erro": "Node.js não encontrado — a Fase 2 (legendas, gráficos) precisa dele: nodejs.org (LTS)"}
    try:
        v = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=10).stdout.strip()
        major = int(v.lstrip("v").split(".")[0])
        return {"ok": major >= 18, "versao": v,
                **({} if major >= 18 else {"erro": f"Node {v} é antigo; precisa 18+"})}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "erro": str(exc)[:200]}


def checar_permissoes() -> dict:
    p = Path.home() / ".claude" / "settings.json"
    try:
        d = json.loads(p.read_text()) if p.exists() else {}
    except json.JSONDecodeError:
        d = {}
    allow = set((d.get("permissions") or {}).get("allow") or [])
    faltam = [a for a in ALLOWLIST if a not in allow]
    return {"ok": not faltam, "faltam": faltam, "arquivo": str(p)}


def preparar() -> int:
    """Baixa o que o doctor acusa: ffmpeg estático e o modelo de voz."""
    import ffbin
    if ffbin.garantir() != "sistema":
        print("· ffmpeg: usando a build completa que vem pelo pip (sem brew)")
        est = ffbin.estatico()
        if est:
            bin_dir = Path.home() / ".local" / "bin"
            bin_dir.mkdir(parents=True, exist_ok=True)
            for src in est:
                dst = bin_dir / Path(src).name
                if not shutil.which(Path(src).name) or dst.is_symlink():
                    try:
                        dst.unlink(missing_ok=True)
                        dst.symlink_to(src)
                    except OSError:
                        pass
            print(f"  linkado em {bin_dir} (ffmpeg, ffprobe)")
    import transcribe_local as TL
    if TL._APPLE_SILICON:
        print("· modelo de voz (whisper-large-v3-turbo, ~1,6 GB) — uma vez só")
        from huggingface_hub import snapshot_download
        snapshot_download(TL.MODELO_MLX)
    else:
        print("· modelo de voz (faster-whisper large-v3-turbo) — uma vez só")
        from faster_whisper import WhisperModel
        WhisperModel(TL.MODELO_FW, compute_type="int8")
    print("pronto.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Confere a instalação do Avelin (sem rede, sem chave)")
    ap.add_argument("--preparar", action="store_true", help="baixa ffmpeg estático e o modelo de voz")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--rapido", action="store_true", help="não transcreve áudio de teste")
    args = ap.parse_args()
    if args.preparar:
        return preparar()
    rel = {
        "ffmpeg": checar_ffmpeg(),
        "vad": checar_vad(),
        "whisper": checar_whisper(transcrever=not args.rapido),
        "node": checar_node(),
        "permissoes": checar_permissoes(),
        "plataforma": f"{sys.platform}/{platform.machine()}",
    }
    fase1_ok = rel["ffmpeg"]["ok"] and rel["vad"]["ok"] and rel["whisper"]["ok"]
    rel["fase1_ok"] = fase1_ok
    if args.json:
        print(json.dumps(rel, ensure_ascii=False, indent=1))
        return 0 if fase1_ok else 1
    print("Avelin — conferência da instalação\n")
    f = rel["ffmpeg"]
    print(f"  {_ok(f['ok'])} ffmpeg {f.get('versao', '')} ({f.get('origem')})" + (f" — {f['erro']}" if f.get("erro") else ""))
    v = rel["vad"]
    print(f"  {_ok(v['ok'])} detector de voz (Silero VAD)" + (f" — {v['erro']}" if v.get("erro") else ""))
    w = rel["whisper"]
    print(f"  {_ok(w['ok'])} transcrição local {w.get('motor', '')}" + (f" — {w['erro']}" if w.get("erro") else ""))
    n = rel["node"]
    print(f"  {_ok(n['ok'])} Node.js {n.get('versao', '')} (só a Fase 2)" + (f" — {n['erro']}" if n.get("erro") else ""))
    p = rel["permissoes"]
    print(f"  {_ok(p['ok'])} permissões do Claude Code" + ("" if p["ok"] else " — para menos pedidos de aprovação, adicione em "
          f"{p['arquivo']} → permissions.allow:"))
    if not p["ok"]:
        for a in p["faltam"]:
            print(f"        {json.dumps(a)}")
    print()
    print("Fase 1 pronta: " + ("SIM" if fase1_ok else "NÃO — rode `uv run python helpers/doctor.py --preparar`"))
    if not n["ok"]:
        print("Fase 2 (legendas e gráficos) espera o Node.js; a Fase 1 funciona sem ele.")
    return 0 if fase1_ok else 1


if __name__ == "__main__":
    sys.exit(main())

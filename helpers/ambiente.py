"""Sinais de ambiente que vários helpers precisam ler do mesmo jeito.

AVE_OFFLINE=1 (ambiente ou .env na raiz do Avelin): nenhuma chamada de rede —
sem Groq/ElevenLabs, sem `git fetch`, sem Pexels/Treblo. O que tem versão local
roda; o que não tem diz que está offline em vez de tentar e esperar o timeout.
"""
from __future__ import annotations

import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def _env(nome: str) -> str:
    v = os.environ.get(nome, "")
    if v:
        return v
    try:
        for linha in (RAIZ / ".env").read_text().splitlines():
            if linha.strip().startswith(f"{nome}="):
                return linha.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


def offline() -> bool:
    return _env("AVE_OFFLINE").strip().lower() not in ("", "0", "false", "nao", "não")

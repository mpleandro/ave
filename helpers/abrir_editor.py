"""Abre o editor no navegador — reaproveitando o que já estiver no ar.

  python helpers/abrir_editor.py          # usado no fim do install.sh / install.ps1

Por que existe: a instalação terminava com um texto ("entre na pasta, abra o
agente…") e a pessoa ainda não tinha visto a ferramenta. Agora ela termina com
o editor aberto, na tela inicial (dropzone + checklist), e a checklist mostra
ao vivo o que ainda está chegando em segundo plano — hoje, o Node.js.

  · já há um editor respondendo (~/.avelin/server.json)? → só abre a URL dele;
  · senão → sobe o preview_server.py desligado deste processo, numa porta
    livre a partir da 4820, com `--open` (ele mesmo abre o navegador).

`AVE_SEM_EDITOR=1` pula (testes, CI, máquina sem tela).
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

HELPERS = Path(__file__).resolve().parent
SERVER = Path.home() / ".avelin" / "server.json"
LOG = Path.home() / ".avelin" / "editor.log"


def no_ar() -> str | None:
    try:
        url = json.loads(SERVER.read_text())["url"]
    except (OSError, KeyError, json.JSONDecodeError):
        return None
    try:
        with urllib.request.urlopen(f"{url}/api/state", timeout=2) as r:
            return url if r.status == 200 else None
    except OSError:
        return None


def porta_livre(inicio: int = 4820) -> int:
    for p in range(inicio, inicio + 40):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    raise RuntimeError("nenhuma porta livre entre 4820 e 4859")


def main() -> int:
    if os.environ.get("AVE_SEM_EDITOR") == "1":
        return 0
    url = no_ar()
    if url:
        webbrowser.open(url)
        print(f"Editor aberto: {url}")
        return 0
    porta = porta_livre()
    LOG.parent.mkdir(parents=True, exist_ok=True)
    log = open(LOG, "ab")
    kw: dict = {"stdin": subprocess.DEVNULL, "stdout": log, "stderr": log, "close_fds": True}
    if sys.platform.startswith("win"):
        kw["creationflags"] = 0x00000008 | 0x00000200   # DETACHED_PROCESS | NEW_PROCESS_GROUP
    else:
        kw["start_new_session"] = True
    subprocess.Popen([sys.executable, str(HELPERS / "preview_server.py"),
                      "--port", str(porta), "--open"], **kw)
    url = f"http://127.0.0.1:{porta}"
    for _ in range(30):                          # até 6 s para o servidor responder
        time.sleep(0.2)
        if no_ar() == url:
            break
    print(f"Editor aberto: {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

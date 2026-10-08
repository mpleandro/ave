#!/usr/bin/env python3
"""A edição de legenda no editor, dirigida por navegador de verdade.

    uv run python tests/ui_legenda.py

PULA SOZINHO se o Playwright ou o Chromium não estiverem instalados — não é
dependência da skill, é ferramenta de teste.

POR QUE ESTE ARQUIVO EXISTE, e por que ele não podia ser um teste de unidade:
os dois defeitos que ele pegou eram invisíveis no código e silenciosos na tela.

  1. **`dblclick` nunca disparava.** O handler de `pointerdown` do painel termina
     em `preventDefault()` — precisa, para o arraste não selecionar texto da
     página — e pela spec de Pointer Events isso suprime os eventos de mouse de
     compatibilidade, `dblclick` incluído. O campo simplesmente não abria, sem
     UM erro de console. A detecção do duplo clique virou contagem de intervalo
     dentro do próprio `pointerdown`.
  2. **O botão de enviar ficava desabilitado.** A trava (`has`) somava corte,
     inserções, marcações e estilo — não correção. `dirtyCount()` já devolvia 2
     e o botão continuava apagado: a correção era impossível de enviar pela
     interface, com todo o backend funcionando.

Nenhum dos dois aparece em teste de unidade, porque os dois vivem na fronteira
entre o navegador e o código. Daí o navegador.
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("playwright não instalado — pulando (não é dependência da skill)")
    raise SystemExit(0)

FALHAS: list[str] = []


def confere(nome: str, obtido, esperado) -> None:
    if obtido == esperado:
        print(f"  ok   {nome}")
    else:
        print(f"  FALHA {nome}\n         esperado: {esperado!r}\n         obtido:   {obtido!r}")
        FALHAS.append(nome)


def porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def projeto() -> Path:
    """Um <edit> com vídeo real curto — o painel mede fala na fonte."""
    d = Path(tempfile.mkdtemp())
    (d / "transcripts").mkdir()
    video = d / "fonte.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
         "-i", "testsrc2=size=320x180:rate=30:duration=8",
         "-f", "lavfi", "-i", "sine=frequency=180:duration=8",
         "-c:v", "libx264", "-preset", "ultrafast", "-crf", "35",
         "-c:a", "aac", "-shortest", str(video)],
        check=True)
    palavras = ["comece", "a", "trabalhar", "na", "Avelim", "hoje", "porque",
                "a", "Avelim", "cresce"]
    (d / "transcripts" / "fonte.json").write_text(json.dumps({"words": [
        {"type": "word", "text": t, "start": round(0.5 + i * 0.5, 3),
         "end": round(0.5 + i * 0.5 + 0.3, 3)}
        for i, t in enumerate(palavras)]}))
    (d / "edl.json").write_text(json.dumps({
        "sources": {"A": "fonte.mp4"},
        "ranges": [{"source": "A", "start": 0.2, "end": 6.0, "beat": "abertura"}],
        "jcut_timeline": [{"audio_start_in_output": 0.0}],
    }))
    (d / "state.json").write_text(json.dumps(
        {"phase": "fase1", "video": "fonte.mp4", "fps": 30, "message": "teste"}))
    return d


edit = projeto()
porta = porta_livre()
srv = subprocess.Popen(
    [sys.executable, str(SKILL / "helpers" / "preview_server.py"),
     "--root", str(edit), "--port", str(porta), "--no-auto"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(40):
        try:
            with socket.create_connection(("127.0.0.1", porta), timeout=0.3):
                break
        except OSError:
            time.sleep(0.25)

    erros: list[str] = []
    with sync_playwright() as pw:
        try:
            b = pw.chromium.launch()
        except Exception as e:                      # noqa: BLE001
            print(f"chromium indisponível ({e.__class__.__name__}) — pulando")
            raise SystemExit(0)
        pg = b.new_page()
        pg.on("pageerror", lambda e: erros.append(str(e)))
        pg.on("dialog", lambda d: d.accept())
        pg.goto(f"http://127.0.0.1:{porta}/", wait_until="networkidle")
        time.sleep(1.5)
        pg.evaluate("setView('tx')")
        pg.wait_for_selector(".tw", timeout=20000)

        print("o campo abre — defeito 1")
        pg.query_selector('.tw[data-i="2"]').dblclick()
        pg.wait_for_selector(".tw-edit", timeout=5000)
        confere("o campo nasce com o texto atual",
                pg.eval_on_selector(".tw-edit", "e => e.value"), "trabalhar")
        confere("o botão 'todas' existe", pg.query_selector(".tw-all") is not None, True)

        print("\ncorrigir")
        pg.fill(".tw-edit", "avaliar")
        pg.keyboard.press("Enter")
        time.sleep(0.4)
        confere("o painel mostra o texto NOVO (Regra 14)",
                pg.eval_on_selector('.tw[data-i="2"]', "e => e.textContent"), "avaliar")
        confere("a palavra é marcada como corrigida",
                pg.eval_on_selector('.tw[data-i="2"]', "e => e.classList.contains('fixed')"), True)
        confere("e NÃO como riscada — corrigir não é cortar",
                pg.eval_on_selector('.tw[data-i="2"]', "e => e.classList.contains('cut')"), False)

        print("\ncorreção global")
        pg.query_selector('.tw[data-i="4"]').dblclick()
        pg.wait_for_selector(".tw-edit", timeout=5000)
        pg.click(".tw-all")
        pg.fill(".tw-edit", "Avelin")
        pg.keyboard.press("Enter")
        time.sleep(0.4)
        confere("a global tem marca visual própria",
                pg.eval_on_selector('.tw[data-i="4"]', "e => e.classList.contains('fixed-all')"), True)

        print("\ndesfazer com campo vazio")
        pg.query_selector('.tw[data-i="2"]').dblclick()
        pg.wait_for_selector(".tw-edit", timeout=5000)
        pg.fill(".tw-edit", "")
        pg.keyboard.press("Enter")
        time.sleep(0.4)
        confere("volta ao original", pg.eval_on_selector('.tw[data-i="2"]', "e => e.textContent"),
                "trabalhar")
        # e volta a corrigir, para o envio ter as duas
        pg.query_selector('.tw[data-i="2"]').dblclick()
        pg.wait_for_selector(".tw-edit", timeout=5000)
        pg.fill(".tw-edit", "avaliar")
        pg.keyboard.press("Enter")
        time.sleep(0.4)

        print("\no botão de enviar — defeito 2")
        confere("habilitado só com correção",
                pg.eval_on_selector("#setupGo", "e => e.disabled"), False)
        confere("não é o caminho CARO (não refaz o corte)",
                pg.evaluate("styleDirty() || edlDirty() || insertsDirty()"), False)
        confere("o rótulo diz aplicar, não enviar para a IA",
                pg.eval_on_selector("#setupGo", "e => e.textContent.trim()"), "Aplicar correções")

        print("\no payload")
        pg.click("#setupGo")
        time.sleep(1.5)
        confere("o estado local é limpo depois do envio",
                pg.evaluate("S.fixWords.size"), 0)
        b.close()

    salvo = json.loads((edit / "preview_edits.json").read_text())
    corr = salvo.get("corrections") or []
    confere("duas correções gravadas", len(corr), 2)
    pontual = next((c for c in corr if c["from"] == "trabalhar"), {})
    glob = next((c for c in corr if c["from"] == "Avelim"), {})
    confere("a pontual carrega srcStart", "srcStart" in pontual, True)
    confere("a global NÃO carrega srcStart", "srcStart" in glob, False)
    confere("o formato é o do corrections.json, sem tradução",
            sorted(pontual), ["from", "source", "srcStart", "text"])
    confere("nenhum erro de página", erros, [])
finally:
    srv.terminate()
    srv.wait(timeout=10)

print()
if FALHAS:
    raise SystemExit(f"{len(FALHAS)} falha(s): {', '.join(FALHAS)}")
print("todas passaram")

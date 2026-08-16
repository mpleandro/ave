#!/usr/bin/env python3
"""O que está acontecendo AGORA — o canal que a interface lê enquanto espera.

O problema que isto resolve: entre clicar e ver, esta ferramenta some por
minutos. Um encode de corte leva ~1min, uma Fase 2 leva ~2min, e no meio disso a
tela fica igualzinha a uma tela travada. O usuário não tem como distinguir
"processando" de "meu clique não pegou" — e a diferença entre as duas é a única
coisa que ele quer saber.

Contrato: UM arquivo, `<edit>/progress.json`, sempre com o estado corrente.
Quem trabalha escreve; a interface lê no mesmo poll que já faz do state.json.

    from progress import begin, step, done, fail
    begin(edit, "encode", "Encodando o corte em 1080p", ai=False)
    step(edit, pct=40, detail="segmento 5 de 12")
    done(edit, "Corte pronto — 57,2s")

`ai=True` marca os passos que gastam TOKEN, e a interface pinta diferente. Não é
enfeite: o usuário pediu para saber quando a IA está trabalhando, porque é o
único custo dele que não é tempo.

Três decisões que parecem detalhe e não são:

  * **`startedAt` sempre**, para a interface mostrar quanto TEMPO já passou. Uma
    barra sem tempo decorrido não distingue lento de travado, que é justamente a
    dúvida.
  * **`pct` é opcional e pode faltar.** Metade dos passos aqui não sabe a própria
    duração (uma chamada de API não tem progresso). Fingir uma barra que anda
    sozinha é pior que assumir "sem previsão" — a barra falsa some a informação
    de que ninguém sabe quanto falta.
  * **Falhar também é progresso.** `fail()` deixa a mensagem no arquivo em vez de
    apagar. Um canal que só reporta sucesso deixa a tela em "processando…" para
    sempre quando o processo morre, que é exatamente quando o usuário mais
    precisa saber.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

NAME = "progress.json"


def _path(edit: Path | str) -> Path:
    return Path(edit) / NAME


def _write(edit: Path | str, data: dict) -> None:
    """Grava atômico: a interface lê num poll independente e leria pela metade.

    Um JSON truncado no meio do poll aparece como 'estado inválido' na tela, e o
    usuário vê um erro que não existe.
    """
    p = _path(edit)
    tmp = p.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False))
        tmp.replace(p)
    except OSError:
        pass          # progresso nunca derruba o trabalho que ele descreve


def read(edit: Path | str) -> dict | None:
    p = _path(edit)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def begin(edit: Path | str, task: str, label: str, *,
          ai: bool = False, total: int | None = None) -> None:
    _write(edit, {
        "task": task,
        "label": label,
        "state": "running",
        "ai": bool(ai),
        "pct": None,
        "detail": "",
        "total": total,
        "startedAt": time.time(),
        "pid": os.getpid(),
    })


def step(edit: Path | str, *, pct: float | None = None,
         detail: str = "", label: str | None = None) -> None:
    cur = read(edit) or {}
    if cur.get("state") != "running":
        return                      # não ressuscita um passo já encerrado
    if pct is not None:
        cur["pct"] = max(0.0, min(100.0, float(pct)))
    if detail:
        cur["detail"] = detail
    if label:
        cur["label"] = label
    _write(edit, cur)


def done(edit: Path | str, label: str | None = None) -> None:
    cur = read(edit) or {}
    cur.update({"state": "done", "pct": 100.0,
                "endedAt": time.time(), "detail": ""})
    if label:
        cur["label"] = label
    _write(edit, cur)


def fail(edit: Path | str, message: str) -> None:
    cur = read(edit) or {}
    cur.update({"state": "failed", "endedAt": time.time(), "detail": message})
    _write(edit, cur)


def clear(edit: Path | str) -> None:
    try:
        _path(edit).unlink()
    except OSError:
        pass

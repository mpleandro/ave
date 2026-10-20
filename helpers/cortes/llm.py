"""Quem avalia o texto — atrás de UMA interface, para o provedor ser trocável.

    av = provedor("sessao", trabalho)
    notas = av.avaliar(pedidos, contexto)    # {chave: nota}

Hoje o avaliador é a própria sessão do Claude que opera o Avelin (é assim que
o resto da skill funciona: quem julga o texto é o modelo lendo, não uma API).
O lote vira `analise/para_avaliar.md`; o modelo lê e grava as notas em
`analise/notas.json`; a próxima chamada encontra as notas e segue.

Um provedor de API (Grok, Claude, Groq…) entra como outra classe com o mesmo
`avaliar` — monta o prompt de `sinais_texto.prompt`, chama, devolve o mesmo
dicionário — e o resto do módulo não muda.

O CACHE é o próprio `notas.json`, por chave de conteúdo (hash do texto da
janela): reprocessar o vídeo não reavalia o que já tem nota, e uma janela cujo
texto mudou ganha chave nova em vez de herdar uma nota que não é dela.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Protocol


class Pendente(Exception):
    """Há janelas sem nota: o lote foi escrito e espera avaliação."""

    def __init__(self, faltam: int, arquivo: Path, destino: Path):
        super().__init__(f"{faltam} janela(s) esperando avaliação em {arquivo}")
        self.faltam, self.arquivo, self.destino = faltam, arquivo, destino


class Avaliador(Protocol):
    def avaliar(self, pedidos: list[dict], contexto: dict) -> dict[str, dict]: ...


class Sessao:
    """O modelo da sessão lê um arquivo e escreve outro."""

    def __init__(self, trabalho: Path, prompt: Callable[[list[dict], dict], str],
                 arquivos: tuple[str, str] = ("para_avaliar.md", "notas.json")):
        self.lote = trabalho / "analise" / arquivos[0]
        self.notas = trabalho / "analise" / arquivos[1]
        self.prompt = prompt

    def ler(self) -> dict[str, dict]:
        return json.loads(self.notas.read_text()) if self.notas.exists() else {}

    def avaliar(self, pedidos: list[dict], contexto: dict) -> dict[str, dict]:
        feitas = self.ler()
        faltam = [p for p in pedidos if p["chave"] not in feitas]
        if faltam:
            self.lote.parent.mkdir(parents=True, exist_ok=True)
            self.lote.write_text(self.prompt(faltam, contexto))
            raise Pendente(len(faltam), self.lote, self.notas)
        self.lote.unlink(missing_ok=True)
        return {p["chave"]: feitas[p["chave"]] for p in pedidos}


PROVEDORES = {"sessao": Sessao}


def provedor(nome: str, trabalho: Path, prompt, arquivos: tuple[str, str] | None = None) -> Avaliador:
    if nome not in PROVEDORES:
        raise SystemExit(f"provedor de avaliação desconhecido: {nome} ({', '.join(PROVEDORES)})")
    return PROVEDORES[nome](trabalho, prompt, *([arquivos] if arquivos else []))

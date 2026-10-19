#!/usr/bin/env python3
"""Legenda dos cortes: texto do transcrito, tempo de ouvir o corte.

    uv run python tests/cortes_legenda.py

O que este arquivo guarda, com os casos reais que motivaram cada regra:

  **O texto vem do Groq, o tempo do Whisper local.** O local ouviu "no rios
  você não vende" onde o transcrito tem "No Reels"; o transcrito tinha o "Mas"
  0,27s adiantado. Casando as duas sequências, a legenda fica com a palavra
  certa no instante certo — caso `texto_do_groq_tempo_do_ouvido`.

  **Reticências não fecham frase.** "e você... lê ele depois" virava um bloco
  "você..." e um "Lê" em maiúscula no meio da frase.

  **Vírgula não deixa palavra sozinha.** "poxa," num bloco de meio segundo.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL / "helpers"))

from cortes import legenda as L  # noqa: E402

FALHAS: list[str] = []
CFG = json.loads((SKILL / "helpers" / "cortes" / "config.json").read_text())


def confere(nome: str, obtido, esperado) -> None:
    if obtido == esperado:
        print(f"  ok  {nome}")
    else:
        FALHAS.append(nome)
        print(f"FALHA {nome}: obtido {obtido!r}, esperado {esperado!r}")


def ws(texto: str, t0: float = 0.0, passo: float = 0.4) -> list[dict]:
    return [{"w": w, "s": round(t0 + i * passo, 3), "e": round(t0 + i * passo + 0.3, 3)}
            for i, w in enumerate(texto.split())]


def texto_do_groq_tempo_do_ouvido():
    groq = ws("No Reels, você não vende, tá?", t0=1000.0)          # tempo da fonte
    ouvido = ws("no rios você não vende tá", t0=0.27)              # tempo do corte
    out = L.alinhar(groq, ouvido, 3.0)
    confere("texto é o do transcrito", [w["w"] for w in out], [w["w"] for w in groq])
    confere("palavra casada leva o tempo ouvido", out[2]["s"], ouvido[2]["s"])
    confere("palavra sem par ('Reels') cai entre as vizinhas",
            out[0]["e"] <= out[1]["s"] <= out[2]["s"], True)
    sem_par = L.alinhar(groq, ws("nada a ver com isso aqui"), 3.0)
    confere("sem casamento, mantém o tempo do texto (relativo)", sem_par[0]["s"], 0.0)


def reticencias_e_maiusculas():
    out = L.capitalizar(ws("parem de ser chatos. se você... lê ele depois."))
    confere("começo do corte em maiúscula", out[0]["w"], "Parem")
    confere("depois do ponto, maiúscula", out[4]["w"], "Se")
    confere("depois de reticências, não", out[6]["w"], "lê")


def blocos_sem_palavra_solta():
    frase = ws("Lê ele depois e fala, poxa, tá muito óbvio, muda.")
    blocos = L.colar_curtos(L.agrupar(frase, 9, 42, pausa=0.7, virgula_min=24), 42)
    textos = [" ".join(w["w"] for w in b) for b in blocos]
    confere("nenhum bloco de uma palavra com vírgula", any(t in ("poxa,", "fala,") for t in textos), False)
    confere("todo bloco cabe em 42 caracteres", all(len(t) <= 42 for t in textos), True)
    karaoke = L.agrupar(frase, 3, 16, virgula_min=6)
    confere("karaokê: até 3 palavras", max(len(b) for b in karaoke) <= 3, True)


def srt_e_ass():
    frase = ws("Parem de ser chatos. Se você vai criar um conteúdo, muda.")
    s = L.srt(frase, 6.0)
    confere("srt começa no bloco 1", s.splitlines()[0], "1")
    confere("srt com tempo no formato do padrão", s.splitlines()[1], "00:00:00,000 --> 00:00:01,500")
    a = L.ass(frase, 6.0, CFG)
    destaque = L._cor_ass(CFG["legenda"]["destaque"])
    confere("ass destaca a palavra da vez", f"{{\\c{destaque}}}Parem{{\\r}}" in a, True)
    confere("ass dentro da área segura (acima dos 320px da base)",
            CFG["legenda"]["base_px"] >= 330, True)
    confere("cor ASS é BGR", L._cor_ass("#FF522D"), "&H002D52FF")


def destaques_e_titulo():
    confere("número é palavra de força", L.forca("100"), True)
    confere("'parem' é palavra de força", L.forca("parem,"), True)
    confere("palavra comum não", L.forca("conteúdo"), False)
    confere("título balanceado, sem palavra sozinha",
            L.linhas_balanceadas("Seu Reels compete com gatinhos e churrasco", 18),
            ["Seu Reels compete", "com gatinhos", "e churrasco"])
    frase = ws("Você vende por ser chato. E é isso.")
    a = L.ass(frase, 6.0, CFG, "Você vende por ser chato.")
    seg = L._cor_ass(CFG["legenda"]["destaque_secundario"])
    confere("palavra de força fora da vez sai na cor secundária", f"{{\\c{seg}}}chato.{{\\r}}" in a, True)
    titulo = [l for l in a.splitlines() if ",Titulo," in l]
    confere("título queimado no topo", len(titulo), 1)
    confere("título some até 4s", titulo[0].split(",")[2], "0:00:04.00")
    sem = L.ass(frase, 6.0, CFG)
    confere("sem título pedido, sem título", ",Titulo," in sem.split("[Events]")[1], False)


if __name__ == "__main__":
    for caso in (texto_do_groq_tempo_do_ouvido, reticencias_e_maiusculas,
                 blocos_sem_palavra_solta, srt_e_ass, destaques_e_titulo):
        print(caso.__name__)
        caso()
    if FALHAS:
        raise SystemExit(f"\n{len(FALHAS)} falha(s): {', '.join(FALHAS)}")
    print("\ntudo certo")

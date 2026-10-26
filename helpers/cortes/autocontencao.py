"""Estágio 2b — o trecho se sustenta sozinho?

Um corte é visto por quem NÃO assistiu ao resto. Então perde ponto o que só faz
sentido com o vídeo inteiro em volta:

- ABERTURA que responde a algo anterior: conector ("então", "e aí", "porque"),
  referência sem antecedente ("isso", "como eu disse", "aquele"), ou muleta
  sozinha ("tá?", "né?") — começa no meio da conversa.
- FECHAMENTO que deixa conta aberta: promessa que o corte não paga ("já já eu
  mostro", "vou te mostrar") ou virada para o próximo assunto ("agora vamos").
- MEIO preso ao contexto da gravação: interação com a live ("o chat", "comenta
  aí") e dependência de tela ("olha aqui", "nesse slide") — num corte vertical
  sem o slide, a frase aponta para o nada.

A nota começa em 100 e cada achado desconta; o motivo de cada desconto vai
junto, porque a tela de cortes mostra por que o trecho perdeu ponto.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hook_finder import CONECTORES, norm  # noqa: E402

REFERENCIAS = (
    "como eu disse", "como eu falei", "como falei", "como eu te falei", "voltando",
    "lembra que", "lembra do", "lembra da", "aquilo", "aquele", "aquela", "naquele",
    "naquela", "daquele", "daquela", "disso", "nisso", "desse", "dessa", "nesse",
    "nessa", "esse ai", "essa ai", "isso ai", "o mesmo", "a mesma", "tambem",
)
MULETAS_SOLTAS = {"ta", "ne", "ok", "beleza", "certo", "entendeu", "cara", "ah", "o",
                  "oh", "sim", "nao", "pois", "tipo", "bom", "olha", "gente", "ai"}
LIVE = re.compile(r"\b(chat|comenta(m)? ai|me (fala|falem|conta) ai|manda(m)? ai|"
                  r"quem (ta|esta) (ai|assistindo)|da(m)? um like|galera (do|que ta)|"
                  r"pergunta (do|da) \w+|respondendo (o|a) \w+|brinde|cade|ninguem (mandou|respondeu|ta me)|"
                  r"(agora )?(voce|vc) responde|vou mandar (pra|para|so)|"
                  r"(o|a) \w+ (falou|perguntou|respondeu|mandou) (aqui|ai|no))\b")
TELA = re.compile(r"\b(olha aqui|aqui o|ta vendo (aqui|isso|ai)|voces (estao|tao) vendo|"
                  r"(nesse|neste|no) slide|(nessa|na) tela|esse grafico|aqui embaixo|"
                  r"aqui em cima|deixa eu (mostrar|abrir|compartilhar|ver se|achar)|"
                  r"(pera|espera) ai|cade o|esse aqui o|tao vendo|ta vendo minha)\b")
PROMESSA = re.compile(r"\b(ja ja|daqui a pouco|(vou|vamos) (te |lhes )?mostrar|vamos ver|"
                      r"na proxima|depois eu|mais pra frente|ja vou)\b")
VIRADA = ("entao vamos", "agora vamos", "vamos para", "vamos pra", "bora", "proximo",
          "partiu", "seguindo", "vamos la")


def avaliar(c: dict, cfg: dict) -> dict:
    p = cfg["autocontencao"]
    ab, fe, tx = norm(c["abertura"]), norm(c["fechamento"]), norm(c["texto"])
    descontos: list[tuple[int, str]] = []

    con = next((k for k in CONECTORES if ab == k or ab.startswith(k + " ")), None)
    if con:
        descontos.append((p["conector"], f"abre com conector \"{con}\""))
    ref = next((k for k in REFERENCIAS if ab == k or ab.startswith(k + " ")
                or f" {k} " in f" {' '.join(ab.split()[:4])} "), None)
    if ref and not con:
        descontos.append((p["referencia"], f"abre com referência sem antecedente \"{ref}\""))
    toks = ab.replace("?", "").split()
    if toks and len(toks) <= 2 and all(t in MULETAS_SOLTAS for t in toks):
        descontos.append((p["muleta"], f"abre com muleta solta \"{c['abertura']}\""))
    elif c["abertura"][:1].islower() and not con and not ref:
        descontos.append((p["minuscula"], "abre em minúscula (provável continuação)"))

    n_live = len(LIVE.findall(tx))
    if n_live:
        descontos.append((max(p["live"] * n_live, p["live_max"]),
                          f"interação com a live ({n_live}×)"))
    n_tela = len(TELA.findall(tx))
    if n_tela:
        descontos.append((max(p["tela"] * n_tela, p["tela_max"]),
                          f"depende do que está na tela ({n_tela}×)"))

    if PROMESSA.search(fe):
        descontos.append((p["promessa"], "fecha prometendo algo que o corte não mostra"))
    if any(fe == k or fe.startswith(k + " ") for k in VIRADA):
        descontos.append((p["virada"], "fecha virando para o próximo assunto"))

    nota = max(0, min(100, 100 + sum(d for d, _ in descontos)))
    return {"nota": nota, "motivos": [m for _, m in descontos]}

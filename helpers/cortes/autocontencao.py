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

BORDA RUIM (`borda_ruim`) é outra coisa: uma frase que NÃO pode ser a primeira
nem a última do corte, decidido antes de qualquer nota. Duas famílias, com os
léxicos no config (`autocontencao.cauda`, `logistica`, `logistica_curta`):

- CAUDA — confirmação que fecha a fala ao vivo e não paga nada: "é isso.",
  "é verdade ou não é?", "tá?", "gente?", "quem tá entendendo isso, gente?".
  Na live da Mentoria Mil Milionários (2026-11) 5 de 48 cortes da galeria
  terminavam numa delas (c1338 "é isso.", c1318 "quem tá entendendo isso,
  gente?", c0838 "quem diz sim?"), e 1.000 das 3.390 janelas terminavam numa
  frase de até 5 palavras. Casa a frase INTEIRA (≤ `cauda_max_palavras`), então
  "é isso" no meio de uma frase de conteúdo não conta.
- LOGÍSTICA da live — QR code, chat, "faltam 2 minutos", "posso continuar?",
  checkout: aponta para o que só existe na transmissão. As fortes valem em
  qualquer frase; as fracas ("pegou a visão?", "quem diz sim?") só em frase
  curta, porque soltas numa frase longa costumam ser retórica de conteúdo.
"""
from __future__ import annotations

import re
import sys
from functools import lru_cache
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
# "posso continuar", "quem tá entendendo", "faltam N minutos", QR code e print
# entraram depois da auditoria da live Mil Milionários: o avaliador marcou 38 de
# 90 finalistas como ruído e esta regex pegava 1 delas (e 1 de 52 de conteúdo)
LIVE = re.compile(r"\b(chat|comenta(m)? ai|me (fala|falem|conta) ai|manda(m)? ai|"
                  r"quem (ta|esta) (ai|assistindo)|da(m)? um like|galera (do|que ta)|"
                  r"pergunta (do|da) \w+|respondendo (o|a) \w+|brinde|cade|ninguem (mandou|respondeu|ta me)|"
                  r"(agora )?(voce|vc) responde|vou mandar (pra|para|so)|"
                  r"(o|a) \w+ (falou|perguntou|respondeu|mandou) (aqui|ai|no)|"
                  r"(posso|vou) continuar|quem (ta|esta) entendendo|falta(m)? \w+ minutos|"
                  r"qr ?code|escaneie|tir(a|e|em|ar|arem)( o| um| esse)? print|escreve(m)? ai|"
                  r"link (fixado|na tela|na bio)|check ?out|levanta(m)? a mao)\b")
TELA = re.compile(r"\b(olha aqui|aqui o|ta vendo (aqui|isso|ai)|voces (estao|tao) vendo|"
                  r"(nesse|neste|no) slide|(nessa|na) tela|esse grafico|aqui embaixo|"
                  r"aqui em cima|deixa eu (mostrar|abrir|compartilhar|ver se|achar)|"
                  r"(pera|espera) ai|cade o|esse aqui o|tao vendo|ta vendo minha)\b")
PROMESSA = re.compile(r"\b(ja ja|daqui a pouco|(vou|vamos) (te |lhes )?mostrar|vamos ver|"
                      r"na proxima|depois eu|mais pra frente|ja vou)\b")
VIRADA = ("entao vamos", "agora vamos", "vamos para", "vamos pra", "bora", "proximo",
          "partiu", "seguindo", "vamos la")


@lru_cache(maxsize=64)
def _rx(padroes: tuple[str, ...]) -> re.Pattern | None:
    return re.compile("|".join(f"(?:{p})" for p in padroes)) if padroes else None


def _toks(texto: str) -> list[str]:
    return norm(texto).replace("?", " ").split()


def eh_cauda(texto: str, cfg: dict) -> bool:
    """A frase inteira é uma confirmação de live ("é isso.", "tá?", "gente?")."""
    a = cfg.get("autocontencao") or {}
    rx = _rx(tuple(a.get("cauda") or ()))
    toks = _toks(texto)
    return bool(rx and toks and len(toks) <= a.get("cauda_max_palavras", 8)
                and rx.fullmatch(" ".join(toks)))


def eh_logistica(texto: str, cfg: dict) -> bool:
    a = cfg.get("autocontencao") or {}
    t = " ".join(_toks(texto))
    forte = _rx(tuple(a.get("logistica") or ()))
    if forte and re.search(rf"\b(?:{forte.pattern})\b", t):
        return True
    fraca = _rx(tuple(a.get("logistica_curta") or ()))
    return bool(fraca and len(t.split()) <= a.get("logistica_curta_max_palavras", 10)
                and re.search(rf"\b(?:{fraca.pattern})\b", t))


def borda_ruim(texto: str, cfg: dict) -> str | None:
    """"cauda" | "logistica" | None — se a frase não serve de borda de corte."""
    if eh_cauda(texto, cfg):
        return "cauda"
    if eh_logistica(texto, cfg):
        return "logistica"
    return None


def referencia_live(texto: str, cfg: dict) -> bool:
    """A frase aponta para o que só existe na transmissão (chat, QR code,
    "posso continuar?", "quem tá entendendo?") — o lote marca [live], e no
    meio do corte ela vira alerta (`alertas.referencia_live`): quem assiste o
    corte não tem chat nem QR na tela."""
    return bool(LIVE.search(norm(texto))) or eh_logistica(texto, cfg)


def cauda_colada(texto: str, cfg: dict) -> str | None:
    """A confirmação grudada depois da última vírgula ("E nós pagamos o preço,
    é verdade ou não é?") — o texto dela, ou None. Só o léxico curto de
    confirmação (`cauda_colada`): vocativo ("…, gente?") fica, porque nele a
    entonação da pergunta inteira cai no vocativo."""
    if "," not in texto:
        return None
    cab, cauda = texto.rsplit(",", 1)
    rx = _rx(tuple((cfg.get("autocontencao") or {}).get("cauda_colada") or ()))
    toks = _toks(cauda)
    if not rx or not toks or len(_toks(cab)) < 3 or not rx.fullmatch(" ".join(toks)):
        return None
    return cauda.strip()


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

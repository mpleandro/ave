#!/usr/bin/env python3
"""A camada de correção de texto, testada sem tocar em vídeo.

    uv run python tests/correcoes.py

POR QUE ESTE TESTE EXISTE SEPARADO DO `regressao.py`.

O `regressao.py` precisa de um vídeo real, da voz de alguém e do critério de
defeito dessa pessoa — por isso as fixtures dele não sobem para o repositório.
Este arquivo testa a outra metade: o mapeamento FONTE → CORTE → TEXTO, que é
aritmética sobre JSON e não depende de material nenhum. Então ele roda em toda
máquina, em menos de um segundo, e pode ser exigido antes de qualquer commit.

O DEFEITO QUE ELE GUARDA, e que era real quando foi escrito:

`cut_transcript.py` aplicava `corrections.json` e `cut_words.py` não. O primeiro
alimenta a LEGENDA QUEIMADA, o segundo alimenta o PAINEL QUE O USUÁRIO LÊ. A
Regra 14 do SKILL.md promete, em letras maiúsculas, que os dois textos são o
mesmo — e a promessa era falsa no instante em que existisse uma correção:

    PAINEL : comece a trabalhar na Avelim
    LEGENDA: comece a avaliar   na Avelin

Passava invisível porque correções eram raras e escritas à mão pelo agente. Com
um campo de edição na interface, o primeiro usuário a corrigir uma palavra veria
a palavra errada continuar na tela e concluiria que o recurso não funciona.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL / "helpers"))

from cut_transcript import build as build_legenda, fix_for  # noqa: E402
from cut_words import build as build_painel  # noqa: E402

FALHAS: list[str] = []


def confere(nome: str, obtido, esperado) -> None:
    if obtido == esperado:
        print(f"  ok   {nome}")
    else:
        print(f"  FALHA {nome}\n         esperado: {esperado!r}\n         obtido:   {obtido!r}")
        FALHAS.append(nome)


def projeto(fixes: list[dict] | None) -> Path:
    """Um <edit> mínimo: uma fonte, um range, sem mídia.

    `fixes=None` NÃO grava o arquivo de correções, e a distinção importa: um
    `corrections.json` com `[]` existe e tem mtime, então ele precisa invalidar
    o cache quando ganhar conteúdo. "Sem arquivo" e "arquivo vazio" são estados
    diferentes para a chave do cache, e iguais para o texto de saída.
    """
    d = Path(tempfile.mkdtemp())
    (d / "transcripts").mkdir()
    palavras = [("comece", 1.0, 1.4), ("a", 1.45, 1.5), ("trabalhar", 1.55, 2.1),
                ("na", 2.2, 2.35), ("Avelim", 2.4, 2.9), ("hoje", 3.6, 4.0),
                ("na", 4.1, 4.25), ("Avelim", 4.3, 4.8)]
    (d / "transcripts" / "src1.json").write_text(json.dumps({"words": [
        {"type": "word", "text": t, "start": a, "end": b} for t, a, b in palavras]}))
    (d / "edl.json").write_text(json.dumps({
        "sources": {"A": "src1.mp4"},
        "ranges": [{"source": "A", "start": 0.5, "end": 5.0, "beat": "abertura"}],
        "jcut_timeline": [{"audio_start_in_output": 0.0}],
    }))
    if fixes is not None:
        (d / "transcripts" / "corrections.json").write_text(json.dumps(fixes))
    return d


def texto(saida: dict) -> str:
    return " ".join(w["text"] for w in saida["words"])


PONTUAL = {"source": "A", "srcStart": 1.55, "from": "trabalhar", "text": "avaliar"}
GLOBAL = {"source": "A", "from": "Avelim", "text": "Avelin"}

print("fix_for — a régua, isolada")
# `from` é o que torna a correção uma correção. Sem ele o TEMPO sozinho pega a
# palavra vizinha: "a" começa em 1.45 e "trabalhar" em 1.55, dentro dos ±0,15s.
confere("casa a palavra certa", fix_for([PONTUAL], "A", 1.55, "trabalhar"), "avaliar")
confere("NÃO pinta a vizinha dentro da tolerância",
        fix_for([PONTUAL], "A", 1.45, "a"), None)
confere("ignora outra fonte", fix_for([PONTUAL], "B", 1.55, "trabalhar"), None)
confere("tolera imprecisão no srcStart", fix_for([PONTUAL], "A", 1.62, "trabalhar"), "avaliar")
confere("recusa fora da tolerância", fix_for([PONTUAL], "A", 3.00, "trabalhar"), None)
confere("global casa sem srcStart", fix_for([GLOBAL], "A", 99.9, "Avelim"), "Avelin")
confere("corrigir para vazio devolve '' e não None",
        fix_for([{"source": "A", "from": "hoje", "text": ""}], "A", 3.6, "hoje"), "")

print("\npainel e legenda — a promessa da Regra 14")
d = projeto([PONTUAL, GLOBAL])
legenda = texto(build_legenda(d))
painel = texto(build_painel(d))
esperado = "comece a avaliar na Avelin hoje na Avelin"
confere("legenda aplica pontual + global", legenda, esperado)
confere("painel aplica pontual + global", painel, esperado)
confere("painel e legenda são o MESMO texto", painel, legenda)

print("\nchave do cache do painel")
# Uma correção não toca no edl.json. Sem `fixMtime` o painel servia o texto
# velho para sempre, e o usuário via a palavra errada sobreviver ao conserto.
saida = build_painel(d)
confere("fixMtime presente", "fixMtime" in saida, True)
confere("fixMtime não é zero quando há correções", saida["fixMtime"] > 0, True)
sem_arquivo = build_painel(projeto(None))
confere("fixMtime é zero sem arquivo de correção", sem_arquivo["fixMtime"], 0.0)
confere("sem correção o texto sai cru", texto(sem_arquivo),
        "comece a trabalhar na Avelim hoje na Avelim")
vazio = build_painel(projeto([]))
confere("arquivo vazio tem mtime (invalida quando ganhar conteúdo)",
        vazio["fixMtime"] > 0, True)

print("\naplicar_correcoes — o merge que o editor dispara")
from apply_edits import aplicar_correcoes  # noqa: E402

d2 = projeto([{"source": "A", "srcStart": 99.0, "from": "antiga", "text": "preservada"}])
# derivados que o phase2 gera com guarda `if not exists` e nunca invalida
(d2 / "transcripts" / "cut_mapped.json").write_text('{"words": []}')
(d2 / "hyperframes").mkdir()
(d2 / "hyperframes" / "captions.json").write_text('{"words": []}')

log, fase2 = aplicar_correcoes(d2, [PONTUAL, GLOBAL])
salvas = json.loads((d2 / "transcripts" / "corrections.json").read_text())
confere("a correção anterior sobrevive ao merge",
        any(c["from"] == "antiga" for c in salvas), True)
confere("as duas novas entraram", len(salvas), 3)
confere("pontuais vêm antes das globais (fix_for para na 1ª que casa)",
        [("srcStart" in c) for c in salvas], [True, True, False])
confere("cut_mapped.json foi invalidado",
        (d2 / "transcripts" / "cut_mapped.json").exists(), False)
confere("captions.json foi invalidado",
        (d2 / "hyperframes" / "captions.json").exists(), False)
confere("avisa que a Fase 2 já tinha rodado", fase2, True)

# Corrigir a MESMA palavra outra vez troca, não empilha: duas correções casando
# a mesma palavra fariam `fix_for` devolver a primeira e ignorar a segunda —
# painel mostrando uma coisa, vídeo queimando outra.
log, _ = aplicar_correcoes(d2, [{**PONTUAL, "srcStart": 1.552, "text": "v2"}])
salvas = json.loads((d2 / "transcripts" / "corrections.json").read_text())
confere("re-corrigir troca em vez de empilhar", len(salvas), 3)
confere("e vale a correção nova",
        next(c["text"] for c in salvas if c["from"] == "trabalhar"), "v2")

log, _ = aplicar_correcoes(d2, [{"source": "A", "from": "", "text": "x"},
                                {"source": "A", "from": "y"}])
confere("correção sem `from` ou sem `text` é rejeitada",
        sum(1 for l in log if "incompleta" in l), 2)

d3 = projeto(None)
log, fase2 = aplicar_correcoes(d3, [GLOBAL])
confere("sem Fase 2 rodada, não avisa render", fase2, False)
confere("cria o arquivo quando não existia",
        len(json.loads((d3 / "transcripts" / "corrections.json").read_text())), 1)

print()
if FALHAS:
    raise SystemExit(f"{len(FALHAS)} falha(s): {', '.join(FALHAS)}")
print("todas passaram")

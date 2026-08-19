#!/usr/bin/env python3
"""Acha FRASE REFEITA — o defeito que o transcrito mostra e o editor ignora.

    uv run python helpers/detect_restarts.py <edit-dir>
    uv run python helpers/detect_restarts.py <edit-dir> --edl        # sobre o corte pronto
    uv run python helpers/detect_restarts.py <edit-dir> --json

POR QUE ISTO EXISTE, e por que é código e não julgamento:

Num take de 51s desta série, quatro frases refeitas foram para o corte final.
Todas as quatro estavam escritas, em português, no `takes_packed.md` que o
editor leu — "E sim a distribuição" seguido de "E sim o terreno onde eu coloco",
"Hoje o McDonald's não é um negócio de hambúrguer" seguido de "Hoje o McDonald's
não ganha dinheiro com hambúrguer". Não foi falha de percepção: o EDL chegou a
escrever `"reason": "corte limpo antes da tentativa truncada"` e mesmo assim
manteve a tentativa truncada, cortando no meio de uma palavra.

Pedir mais cuidado a um modelo é a correção que não se pode verificar. Esta se
verifica.

A UNIDADE AQUI É A FRASE, NÃO A PALAVRA. A primeira versão deste helper
comparava índices de palavra e recortava "versão A" e "versão B" por aritmética
(`ws[a:b]`), o que produzia trechos que atravessavam emendas e texto sem sentido
— e o mesmo reinício aparecia quatro vezes, uma por n-grama. Frase é a unidade
certa, e ela só passou a existir de verdade quando o `spacing` virou silêncio
MEDIDO no áudio (ver `transcribe.py:_apply_measured_spacing`): antes disso o
Whisper entregava tudo grudado e não havia fronteira em que se apoiar.

AS TRÊS REGRAS, nesta ordem (a ordem é a decisão inteira):

  1. TRUNCADA  — a primeira versão morre numa palavra funcional ("é um negócio
     DE"). Ninguém termina frase em preposição: aquilo é tomada abortada, não
     escolha editorial. → REMOVE sozinho.
  2. IDÊNTICA  — as duas versões são a mesma sequência de palavras. Não há o que
     escolher. → FICA A ÚLTIMA.
  3. SEMÂNTICA — mesma ideia, palavras diferentes. Qual tomada fica é de quem
     assina o vídeo. → PERGUNTA.

E O FALSO POSITIVO, que é o motivo de a regra 3 não decidir sozinha: repetição
também é figura de linguagem. "com um sistema impecável" / "Um sistema eficiente"
casa no n-grama e PARECE anáfora. Nenhuma regra de string separa anáfora de
refação; isso é significado.

**MAS JULGAR NÃO É DESCARTAR.** Este helper marcou aquele par exato, o modelo
julgou "anáfora deliberada", descartou sem mostrar, e o usuário ouviu o vídeo e
disse que era repetição — dele, que escreveu e gravou a frase. O modelo não tem
como saber a intenção de quem falou; só quem falou sabe.

Então a regra 3 é: **o modelo RECOMENDA, o usuário DECIDE.** Todo hit semântico
sobe marcado `precisa_julgamento: true` e vai para a tela com as duas versões e
os dois tempos — inclusive os que o modelo acha que são anáfora, com a
recomendação dita. Descartar calado é a única saída que não existe.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

# Janela em que uma repetição ainda é "reinício". Além disso é retomada de tema,
# normal em vídeo longo e não é defeito.
JANELA_S = 12.0
# Fronteira de frase. Mais fino que o 0.5s do pack_transcripts de propósito: um
# reinício rápido cabe numa pausa de 0.4s, e aqui interessa achar, não resumir.
PAUSA_FRASE = 0.35
MIN_NGRAMA = 2   # duas palavras iguais já é sinal; abaixo disso é ruído

# Palavra em que nenhuma frase termina. Uma versão que morre aqui está truncada,
# e truncada não é escolha editorial — é tomada abortada.
FUNCIONAIS = {
    "de", "do", "da", "dos", "das", "e", "ou", "que", "com", "em", "para", "pra",
    "por", "o", "a", "os", "as", "um", "uma", "uns", "umas", "no", "na", "nos",
    "nas", "ao", "aos", "num", "numa", "meu", "minha", "seu", "sua", "se", "mas",
    "quando", "onde", "como", "pro", "ate", "sobre", "entre", "sem", "mais",
    "muito", "ja", "nao", "eh", "ser", "vai", "tem",
}


def norm(t: str) -> str:
    t = unicodedata.normalize("NFD", t.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]", "", t)


# --------------------------------------------------------------------------- #
# leitura

def _palavras(edit: Path) -> list[dict]:
    """Palavras da fonte, em ORDEM DE LEITURA, com o tempo da fonte.

    Ordem de leitura e não ordem de relógio: os tempos do Whisper não são
    monotônicos (medido: 'hambúrguer' 40.10–40.48 sobrepõe 'É' 40.02–40.96), e
    ordenar por tempo embaralha a frase.
    """
    out: list[dict] = []
    for p in sorted(q for q in (edit / "transcripts").glob("*.json")
                    if not q.name.startswith(".")):
        for w in json.loads(p.read_text()).get("words", []):
            if w.get("type") != "word":
                continue
            txt = (w.get("text") or "").strip()
            if txt and norm(txt):
                out.append({"t": float(w["start"]), "fim": float(w["end"]),
                            "txt": txt, "n": norm(txt)})
    return out


def _palavras_do_corte(edit: Path) -> list[dict]:
    """Palavras que SOBRAM no corte, remapeadas para o tempo do output.

    É a passada que pega repetição atravessando emenda: dois ranges escolhidos
    em momentos diferentes dizendo a mesma coisa. Na fonte isso é invisível,
    porque lá as duas versões estão longe uma da outra.
    """
    edl = json.loads((edit / "edl.json").read_text())
    todas = _palavras(edit)
    out: list[dict] = []
    base = 0.0
    for idx, r in enumerate(edl.get("ranges", [])):
        ini, fim = float(r["start"]), float(r["end"])
        for w in todas:
            # centro dentro do range: a borda pode ter aparado a palavra, e
            # exigir contenção total descartaria a primeira/última de cada trecho
            centro = (w["t"] + w["fim"]) / 2
            if ini - 1e-6 <= centro <= fim + 1e-6:
                out.append({**w, "t": base + (w["t"] - ini),
                            "fim": base + (w["fim"] - ini),
                            "beat": r.get("beat", ""), "corte": idx})
        base += fim - ini
    return out


def frases(ws: list[dict]) -> list[dict]:
    """Agrupa palavras em frases, quebrando na pausa MEDIDA entre elas.

    Depois da correção do `spacing`, o vão entre duas palavras é de novo um
    número verdadeiro — antes era sempre 0.00 e nenhum agrupamento era possível.
    """
    out: list[dict] = []
    cur: list[dict] = []
    for w in ws:
        # EMENDA TAMBÉM É FRONTEIRA DE FRASE. Depois do corte a pausa entre dois
        # trechos deixa de existir por construção — foi ela que se removeu — e
        # agrupar só por vão faria o corte inteiro virar uma frase só.
        troca_de_trecho = bool(cur) and cur[-1].get("corte") != w.get("corte")
        if cur and (troca_de_trecho or w["t"] - cur[-1]["fim"] >= PAUSA_FRASE):
            out.append(_fechar(cur))
            cur = []
        cur.append(w)
    if cur:
        out.append(_fechar(cur))
    return out


def _fechar(cur: list[dict]) -> dict:
    return {
        "t": cur[0]["t"], "fim": cur[-1]["fim"],
        "texto": " ".join(w["txt"] for w in cur),
        "n": [w["n"] for w in cur],
        "beat": cur[0].get("beat"),
    }


# --------------------------------------------------------------------------- #
# detecção

def _maior_ngrama_comum(a: list[str], b: list[str]) -> list[str]:
    """O maior trecho de palavras que as duas frases têm em comum."""
    melhor: list[str] = []
    for i in range(len(a)):
        for j in range(i + len(melhor) + 1, len(a) + 1):
            alvo = a[i:j]
            if any(b[k:k + len(alvo)] == alvo for k in range(len(b) - len(alvo) + 1)):
                if len(alvo) > len(melhor):
                    melhor = alvo
            else:
                break
    return melhor


def quase_repeticoes(fs: list[dict]) -> list[dict]:
    """Paráfrase ADJACENTE dentro de uma frase — a repetição que muda uma palavra.

    "e saber disso e entender isso" passou por todas as camadas de string:
    o n-grama exige repetição literal (o verbo mudou) e o detector de frases
    compara frases entre si (a dupla mora dentro de UMA). O usuário ouviu e
    chamou de repetição — e quantas vezes o vídeo diz algo é decisão dele.

    A heurística: duas janelas ADJACENTES de n palavras onde (a) sobram iguais
    n-1 das n, OU (b) a primeira palavra é igual e a última divide sufixo de 4+
    letras ("disso"/"isso"). É deliberadamente larga: cada acerto vira PERGUNTA
    com timestamp, nunca corte automático — paralelismo também é figura de
    linguagem, e quem sabe a intenção é quem gravou.
    """
    hits = []
    for f in fs:
        ws = f["n"]
        for n in (3, 2):
            for i in range(len(ws) - 2 * n + 1):
                a, b = ws[i:i + n], ws[i + n:i + 2 * n]
                if a == b:
                    continue          # literal é do detector principal
                iguais = sum(1 for x, y in zip(a, b) if x == y)
                sufixo = len(a[-1]) >= 4 and len(b[-1]) >= 4 and a[-1][-4:] == b[-1][-4:]
                if iguais >= n - 1 or (a[0] == b[0] and sufixo):
                    hits.append({
                        "classe": "quase", "acao": "perguntar",
                        "precisa_julgamento": True,
                        "ngrama": f"{' '.join(a)} ~ {' '.join(b)}",
                        "palavras_iguais": iguais, "mesmo_inicio": a[0] == b[0],
                        "delta": 0.0,
                        "versao_A": {"t": round(f["t"], 2), "fim": round(f["fim"], 2),
                                     "texto": " ".join(a), "beat": f.get("beat")},
                        "versao_B": {"t": round(f["t"], 2), "fim": round(f["fim"], 2),
                                     "texto": " ".join(b), "beat": f.get("beat")},
                    })
                    break
            else:
                continue
            break
    return hits


def achar(fs: list[dict]) -> list[dict]:
    """Pares de frases próximas que repetem um trecho. Uma entrada por par."""
    hits: list[dict] = []
    for i, a in enumerate(fs):
        for b in fs[i + 1:]:
            if b["t"] - a["fim"] > JANELA_S:
                break
            comum = _maior_ngrama_comum(a["n"], b["n"])
            if len(comum) < MIN_NGRAMA:
                continue
            prefixo = comum == a["n"][:len(comum)] and comum == b["n"][:len(comum)]
            hits.append({
                "ngrama": " ".join(comum),
                "palavras_iguais": len(comum),
                "mesmo_inicio": prefixo,
                "delta": round(b["t"] - a["t"], 2),
                "a": a, "b": b,
            })
    # um reinício por frase B: fica o par com mais palavras em comum
    # Uma entrada por evento: cada frase entra em no máximo um par, senão o mesmo
    # reinício sai quatro vezes, uma por n-grama que casou.
    melhores: list[dict] = []
    usadas: set[float] = set()
    for h in sorted(hits, key=lambda x: -x["palavras_iguais"]):
        if h["a"]["t"] in usadas or h["b"]["t"] in usadas:
            continue
        usadas.add(h["a"]["t"]); usadas.add(h["b"]["t"])
        melhores.append(h)
    return sorted(melhores, key=lambda h: h["a"]["t"])


def classificar(h: dict) -> dict:
    a, b = h["a"], h["b"]
    ultima_txt = a["texto"].split()[-1] if a["texto"] else ""
    termina_em_pontuacao = bool(re.search(r"[.?!…]$", ultima_txt))
    ultima = norm(ultima_txt)

    # TRUNCADA exige que B REINICIE o que A começou. Terminar em palavra
    # funcional não basta: num EDL os ranges partem frases no meio de propósito
    # ("…Isso explica muito" | "porque você ganha…"), e a régua antiga acusava a
    # continuação legítima como tomada abortada — bloqueando o corte certo.
    if ultima in FUNCIONAIS and not termina_em_pontuacao and h["mesmo_inicio"]:
        classe, acao, julgar = "truncada", "remover_A", False
    elif a["n"] == b["n"]:
        classe, acao, julgar = "identica", "fica_a_ultima", False
    else:
        classe, acao, julgar = "semantica", "perguntar", True

    return {
        "classe": classe, "acao": acao, "precisa_julgamento": julgar,
        "ngrama": h["ngrama"], "palavras_iguais": h["palavras_iguais"],
        "mesmo_inicio": h["mesmo_inicio"], "delta": h["delta"],
        "versao_A": {"t": round(a["t"], 2), "fim": round(a["fim"], 2),
                     "texto": a["texto"], "beat": a.get("beat")},
        "versao_B": {"t": round(b["t"], 2), "fim": round(b["fim"], 2),
                     "texto": b["texto"], "beat": b.get("beat")},
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Acha frase refeita (reinício de tomada)")
    ap.add_argument("edit", type=Path)
    ap.add_argument("--edl", action="store_true",
                    help="olha o corte resultante do edl.json (pega repetição que "
                         "atravessa emenda) em vez da fonte inteira")
    ap.add_argument("--json", action="store_true", help="saída para o pipeline")
    args = ap.parse_args()

    edit = args.edit.resolve()
    if not (edit / "transcripts").is_dir():
        sys.exit(f"sem transcripts/ em {edit}")
    if args.edl and not (edit / "edl.json").exists():
        sys.exit(f"sem edl.json em {edit}")

    ws = _palavras_do_corte(edit) if args.edl else _palavras(edit)
    fs = frases(ws)
    hits = [classificar(h) for h in achar(fs)] + quase_repeticoes(fs)

    if args.json:
        print(json.dumps({"escopo": "edl" if args.edl else "fonte",
                          "total": len(hits), "hits": hits},
                         ensure_ascii=False, indent=2))
        return

    onde = "no CORTE (tempo de output)" if args.edl else "na FONTE (tempo de origem)"
    if not hits:
        print(f"nenhum reinício {onde}.")
        return
    rot = {"truncada": "TRUNCADA  → remove a versão A sozinho",
           "identica": "IDÊNTICA  → fica a última",
           "semantica": "SEMÂNTICA → PERGUNTAR (pode ser anáfora — precisa julgamento)",
           "quase": "QUASE-REPETIÇÃO (paralelismo) → PERGUNTAR"}
    print(f"{len(hits)} candidato(s) a frase refeita — {onde}\n")
    for h in hits:
        marca = "início igual" if h["mesmo_inicio"] else "trecho igual"
        print(f"  [{h['classe'].upper()}] {marca}: \"{h['ngrama']}\" "
              f"({h['palavras_iguais']} palavras, Δ{h['delta']}s)")
        print(f"      {rot[h['classe']]}")
        print(f"     A {h['versao_A']['t']:7.2f}s  {h['versao_A']['texto']}")
        print(f"     B {h['versao_B']['t']:7.2f}s  {h['versao_B']['texto']}")
        print()
    n_j = sum(1 for h in hits if h["precisa_julgamento"])
    print(f"{len(hits) - n_j} resolvido(s) por regra, {n_j} precisa(m) de julgamento.")
    if n_j:
        print("Para cada SEMÂNTICA: é a mesma ideia dita duas vezes (refação → vira "
              "pergunta ao usuário) ou repetição de propósito (anáfora → descarta)?")


if __name__ == "__main__":
    main()

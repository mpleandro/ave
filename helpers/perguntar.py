#!/usr/bin/env python3
"""O que perguntar ao usuário, em português de gente — e o que NÃO perguntar.

    uv run python helpers/perguntar.py <edit-dir>
    uv run python helpers/perguntar.py <edit-dir> --contexto "Fome de Poder"
    uv run python helpers/perguntar.py <edit-dir> --json

DUAS REGRAS DURAS, e as duas nasceram de defeito observado.

1. A PERGUNTA NUNCA MOSTRA UM NÚMERO. "hesitação de 0,38s abaixo do limiar
   agressivo 0,35" é verdade e é inútil: descreve o instrumento, não a escolha.
   Quem edita decide por som e por ritmo, então a pergunta mostra o ÁUDIO (um
   timestamp para clicar no editor que já está no ar) e a CONSEQUÊNCIA.

2. UMA PERGUNTA POR CLASSE, NÃO POR OCORRÊNCIA. Um take de 60s tem sete
   respiros. Sete perguntas idênticas não são cuidado, são um formulário — e a
   pessoa responde a terceira no automático. Uma pergunta com dois ou três
   exemplos clicáveis decide as sete.

E o silêncio também é resposta: o que a preferência já sabe com confiança ALTA
não vira pergunta nenhuma. É o `preferencias.py` que decide isso, e é por isso
que este helper encolhe a cada vídeo em vez de repetir o mesmo interrogatório
para sempre.

TETO POR PROJETO. Se sobrarem mais perguntas que o teto, ordena por IMPACTO
(quanto tempo aquilo custa no vídeo) e pergunta só as que mudam alguma coisa. O
resto entra no resumo como decisão tomada pelo padrão — dito, não escondido.
Um portão que faz vinte perguntas é um portão que a pessoa aprende a pular.

Saída legível para o modelo conduzir a conversa, ou `--json` para o pipeline.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HELPERS = Path(__file__).resolve().parent
sys.path.insert(0, str(HELPERS))

from preferencias import ALTA, BAIXA, carregar, consultar  # noqa: E402
from speech_regions import measured_silences  # noqa: E402

TETO_PADRAO = 4

ROTULO = {"hesitacao": "gaguejo", "respiracao": "respiro", "retorica": "pausa de efeito"}


def _mmss(t: float) -> str:
    return f"{int(t // 60)}:{t % 60:05.2f}"


def _palavras(edit: Path) -> list[dict]:
    out: list[dict] = []
    for p in sorted(q for q in (edit / "transcripts").glob("*.json")
                    if not q.name.startswith(".")):
        for w in json.loads(p.read_text()).get("words", []):
            if w.get("type") == "word" and (w.get("text") or "").strip():
                out.append(w)
    return out


def _classificar(palavras: list[dict], at: float) -> tuple[str, str]:
    try:
        from propose_breaths import classificar  # noqa: PLC0415
        return classificar(palavras, at)
    except Exception:
        return "respiracao", ""


def _mapa_saida(edit: Path):
    """(fonte→output, dentro_do_corte). Perguntar sobre trecho já cortado é ruído."""
    edl = json.loads((edit / "edl.json").read_text())
    segs, base = [], 0.0
    for r in edl.get("ranges", []):
        ini, fim = float(r["start"]), float(r["end"])
        segs.append((ini, fim, base))
        base += fim - ini

    def conv(t: float):
        for ini, fim, b in segs:
            if ini - 1e-6 <= t <= fim + 1e-6:
                return b + (t - ini)
        return None
    return conv


# --------------------------------------------------------------------------- #

def levantar_respiros(edit: Path, formato: str, contexto: str | None) -> dict:
    """Todo vão dentro do corte, classificado, com o veredito da preferência."""
    edl = json.loads((edit / "edl.json").read_text())
    fontes = list((edl.get("sources") or {}).values())
    if not fontes:
        return {"aplicar": [], "informar": [], "perguntar": {}}
    video = Path(fontes[0])
    if not video.exists():
        return {"aplicar": [], "informar": [], "perguntar": {}}

    palavras = _palavras(edit)
    conv = _mapa_saida(edit)
    prefs = carregar()

    baldes: dict[str, list[dict]] = {}
    for a, b in measured_silences(video):
        out = conv(a)
        if out is None:
            continue                      # já ficou fora do corte
        dur = b - a
        classe, antes = _classificar(palavras, a)
        baldes.setdefault(classe, []).append(
            {"fonte": round(a, 2), "saida": round(out, 2), "dur": round(dur, 2),
             "depois_de": antes})

    aplicar, informar, perguntar = [], [], {}
    for classe, vaos in baldes.items():
        r = consultar(prefs, formato, classe, contexto)
        alvo = [v for v in vaos if v["dur"] >= r["limiar"]]
        if not alvo:
            continue
        pacote = {"classe": classe, "vaos": alvo,
                  "ganho_s": round(sum(v["dur"] for v in alvo), 2), **r}
        if r["confianca"] == ALTA:
            aplicar.append(pacote)        # sabe o bastante: faz e não comenta
        elif r["confianca"] == BAIXA:
            perguntar[classe] = pacote    # nunca viu: pergunta
        else:
            informar.append(pacote)       # sabe o suficiente: faz e avisa
    return {"aplicar": aplicar, "informar": informar, "perguntar": perguntar}


def levantar_reinicios(edit: Path) -> dict:
    """Chama o detect_restarts nos dois escopos e separa por ação."""
    saida = {"remover": [], "ultima": [], "perguntar": []}
    for escopo in ("--edl", None):
        cmd = [sys.executable, str(HELPERS / "detect_restarts.py"), str(edit), "--json"]
        if escopo:
            cmd.append(escopo)
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            hits = json.loads(r.stdout).get("hits", []) if r.returncode == 0 else []
        except Exception:
            hits = []
        for h in hits:
            h["escopo"] = "corte" if escopo else "fonte"
            if h["classe"] == "truncada":
                saida["remover"].append(h)
            elif h["classe"] == "identica":
                saida["ultima"].append(h)
            else:
                saida["perguntar"].append(h)
    return saida


# --------------------------------------------------------------------------- #
# a redação

def frase_respiro(p: dict) -> dict:
    n = len(p["vaos"])
    rot = ROTULO.get(p["classe"], p["classe"])
    exemplos = sorted(p["vaos"], key=lambda v: -v["dur"])[:3]
    if p["classe"] == "retorica":
        texto = (f"Você faz {n} pausa{'s' if n > 1 else ''} depois de encerrar a frase — "
                 "dá peso, mas segura o vídeo.")
        opcoes = ["Encurta, quero mais ritmo", "Encurta só as mais longas",
                  "Deixa, a pausa é de propósito"]
    elif p["classe"] == "hesitacao":
        texto = (f"Em {n} ponto{'s' if n > 1 else ''} você para no meio da frase e retoma. "
                 "É o tipo de coisa que ninguém sente falta.")
        opcoes = ["Tira todos", "Tira só os mais longos", "Deixa como está"]
    else:
        texto = (f"Você faz {n} pausinha{'s' if n > 1 else ''} curta{'s' if n > 1 else ''} "
                 "pra respirar. Em vídeo curto isso costuma pesar.")
        opcoes = ["Tira todas, quero seco", "Tira só as maiores", "Deixa, é minha cadência"]
    return {
        "tipo": "respiros", "classe": p["classe"], "rotulo": rot,
        "pergunta": texto, "opcoes": opcoes,
        "ouca_em": [_mmss(v["saida"]) for v in exemplos],
        "impacto_s": p["ganho_s"], "quantidade": n,
    }


def frase_reinicio(h: dict) -> dict:
    a, b = h["versao_A"], h["versao_B"]
    return {
        "tipo": "duplicado",
        "pergunta": "Você disse essa frase duas vezes. Qual fica?",
        "opcoes": [f"Fica a B — {b['texto'][:70]}",
                   f"Fica a A — {a['texto'][:70]}",
                   "Ficam as duas"],
        "ouca_em": [_mmss(a["t"]), _mmss(b["t"])],
        "impacto_s": round(a["fim"] - a["t"], 2),
        "escopo": h.get("escopo"),
    }


def montar(edit: Path, formato: str, contexto: str | None, teto: int) -> dict:
    resp = levantar_respiros(edit, formato, contexto)
    rein = levantar_reinicios(edit)

    perguntas = [frase_respiro(p) for p in resp["perguntar"].values()]
    # IMPACTO manda: o que custa mais tempo de vídeo pergunta primeiro.
    perguntas.sort(key=lambda q: -q["impacto_s"])

    cortadas = perguntas[teto:]
    return {
        "perguntas": perguntas[:teto],
        "nao_perguntadas": cortadas,
        # NÃO VAI DIRETO AO USUÁRIO. Repetição de trecho é sinal de string, e
        # string não distingue frase refeita de anáfora: "com um sistema
        # impecável" / "Um sistema eficiente" casa no detector e é figura de
        # linguagem, que cortada estraga o texto. Levar isso ao usuário como
        # "qual fica?" seria transferir a ele um trabalho que é de julgamento —
        # e ensiná-lo a desconfiar das perguntas. O modelo tria primeiro; só o
        # que sobrar vira pergunta, com a redação de `frase_reinicio`.
        "triagem_do_modelo": [
            {**frase_reinicio(h), "candidato": h,
             "decidir": "é a mesma ideia dita duas vezes (vira pergunta) "
                        "ou repetição de propósito (descarta)?"}
            for h in rein["perguntar"]
        ],
        "aplicar_calado": resp["aplicar"],
        "aplicar_informando": resp["informar"],
        "remover_truncadas": rein["remover"],
        "fica_a_ultima": rein["ultima"],
    }


def imprimir(plano: dict) -> None:
    aut = plano["aplicar_calado"]
    inf = plano["aplicar_informando"]
    tru = plano["remover_truncadas"]
    ult = plano["fica_a_ultima"]

    if tru or ult or aut or inf:
        print("RESOLVIDO SEM PERGUNTAR")
        for h in tru:
            print(f"  · tomada abortada removida: \"{h['versao_A']['texto'][:60]}\"")
        for h in ult:
            print(f"  · frase repetida igual, fica a última: \"{h['ngrama']}\"")
        for p in aut:
            print(f"  · {len(p['vaos'])} {ROTULO[p['classe']]}(s) — seu padrão "
                  f"(confiança alta, {p['amostras']} amostras)")
        for p in inf:
            print(f"  · {len(p['vaos'])} {ROTULO[p['classe']]}(s) removido(s) pelo seu padrão "
                  f"— {p['ganho_s']:.1f}s a menos. Diga se preferir manter.")
        print()

    tri = plano.get("triagem_do_modelo") or []
    if tri:
        print(f"TRIAGEM DO MODELO ({len(tri)}) — decidir ANTES de mostrar ao usuário")
        print("  repetição de trecho não distingue frase refeita de anáfora.")
        print("  Para cada uma: mesma ideia dita duas vezes → vira pergunta; "
              "repetição de propósito → descarta.\n")
        for i, q in enumerate(tri, 1):
            c = q["candidato"]
            print(f"  {i}. \"{c['ngrama']}\"  ({c['escopo']}, Δ{c['delta']}s)")
            print(f"     A {c['versao_A']['t']:7.2f}s  {c['versao_A']['texto'][:80]}")
            print(f"     B {c['versao_B']['t']:7.2f}s  {c['versao_B']['texto'][:80]}")
        print()

    qs = plano["perguntas"]
    if not qs:
        print("NADA A PERGUNTAR DIRETO (fora a triagem acima)." if tri else "NADA A PERGUNTAR.")
    else:
        print(f"PERGUNTAR ({len(qs)}):\n")
        for i, q in enumerate(qs, 1):
            print(f"  {i}. {q['pergunta']}")
            print(f"     ouça em: {', '.join(q['ouca_em'])}")
            for o in q["opcoes"]:
                print(f"     ▸ {o}")
            print()

    if plano["nao_perguntadas"]:
        print(f"NÃO PERGUNTADO (teto do projeto): {len(plano['nao_perguntadas'])} item(ns) "
              "de menor impacto — resolvidos pelo padrão:")
        for q in plano["nao_perguntadas"]:
            print(f"  · {q['pergunta'][:70]} ({q['impacto_s']:.1f}s)")


def main() -> None:
    ap = argparse.ArgumentParser(description="O que perguntar ao usuário sobre este corte")
    ap.add_argument("edit", type=Path)
    ap.add_argument("--formato", default="shortform", choices=["shortform", "longform"])
    ap.add_argument("--contexto", default=None)
    ap.add_argument("--teto", type=int, default=TETO_PADRAO)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    edit = args.edit.resolve()
    if not (edit / "edl.json").exists():
        sys.exit(f"sem edl.json em {edit}")

    plano = montar(edit, args.formato, args.contexto, args.teto)
    if args.json:
        print(json.dumps(plano, ensure_ascii=False, indent=2))
    else:
        imprimir(plano)


if __name__ == "__main__":
    main()

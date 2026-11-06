"""Proposta de SELEÇÃO: do corte limpo ao corte curto, guiado pela tese e pelo alvo.

  uv run python helpers/selecao.py <edit> --alvo 60 --tese "conselho de graça sai caro; mentoria é o caminho"
  uv run python helpers/selecao.py <edit> --alvo 60 --tese "..." --manter 3,5 --tirar 7

Separa "limpar" (uma vez, automático — fala_limpa.py) de "escolher" (barato,
quantas vezes quiser): os blocos saem do corte LIMPO já em cache, e trocar a
seleção é remontar o EDL com peças prontas. O render reaproveita segmentos.

Como escolhe (heurística; o modelo revisa em `selecao.md`):
  · bloco = frase(s) contínua(s) do corte limpo, separadas por pausa ≥ 0,6 s,
    no máximo ~12 s;
  · nota = afinidade com a TESE (palavras de conteúdo em comum) + gancho
    (abertura forte no primeiro quinto) + fechamento (chamada no último
    quinto) + densidade de fala − redundância com bloco já escolhido;
  · enche o alvo em ordem de nota, SEMPRE com um gancho e um fechamento, e
    devolve em ordem cronológica.

Saídas em <edit>/: `selecao.json`, `edl_selecao.json` (schema do edl.json,
subconjunto do corte limpo, respiros preservados), `selecao.md` (todos os
blocos com nota, ✔/✘ e motivo — é o que o modelo e o usuário leem), e uma
seção "Seleção" acrescentada ao `roteiro.md`.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fala_limpa as FL

PAUSA_BLOCO = 0.6
BLOCO_MAX_S = 12.0
STOP = set(["a", "o", "os", "as", "um", "uma", "uns", "umas", "de", "do", "da", "dos", "das", "em", "no", "na", "nos", "nas", "e", "ou", "que", "se", "por", "para", "pra", "pro", "com", "sem", "ao", "aos", "mas", "como", "quando", "onde", "mais", "muito", "ja", "nao", "eh", "ser", "vai", "tem", "ta", "voce", "ele", "ela", "eles", "elas", "isso", "esse", "essa", "aqui", "ai", "la", "hoje", "agora", "entao", "tipo", "ne", "bom", "assim", "cara", "gente", "coisa", "coisas", "ate", "so", "sua", "seu", "meu", "minha", "nem", "porque", "pode", "poder", "vou", "vai", "foi", "era", "estava", "esta", "estao", "sao", "tinha", "ter", "tudo", "todo", "toda", "nada", "algo", "alguem", "outro", "outra", "mesmo", "mesma", "ainda", "depois", "antes", "tambem", "muito", "pouco", "bem", "mal", "la", "ali", "aquele", "aquela", "isso"])
CTA = {"faca", "responda", "siga", "comenta", "compartilha", "salva", "clica", "manda", "pergunta",
       "quer", "quero", "precisa", "lembre", "pensa", "imagina"}


def norm(t: str) -> str:
    t = unicodedata.normalize("NFD", t.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]", "", t)


def stem(w: str) -> str:
    w = norm(w)
    for suf in ("mente", "inhos", "inhas", "inho", "inha", "ando", "endo", "indo", "ados", "adas", "ado",
                "ada", "ava", "avam", "aram", "eram", "iam", "oes", "res", "s"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[:-len(suf)]
    return w


def conteudo(txt: str) -> set[str]:
    return {stem(w) for w in re.findall(r"[\wÀ-ú]+", txt) if norm(w) and norm(w) not in STOP and len(norm(w)) > 2}


# --------------------------------------------------------------------------- #
# blocos a partir do corte limpo

def blocos_do_corte(ws: list[dict], edl_limpo: dict) -> list[dict]:
    ranges = [(float(r["start"]), float(r["end"])) for r in edl_limpo["ranges"]]
    out: list[dict] = []
    for a, b in ranges:
        cur: list[dict] = []
        for w in ws:
            if not (a <= w["t"] and w["fim"] <= b + 0.05):
                continue
            if cur and (w["t"] - cur[-1]["fim"] >= PAUSA_BLOCO or w["fim"] - cur[0]["t"] > BLOCO_MAX_S):
                out.append({"ini": cur[0]["t"], "fim": cur[-1]["fim"], "range": (a, b), "palavras": cur})
                cur = []
            cur.append(w)
        if cur:
            out.append({"ini": cur[0]["t"], "fim": cur[-1]["fim"], "range": (a, b), "palavras": cur})
    for k, bl in enumerate(out, 1):
        bl["id"] = k
        bl["texto"] = " ".join(w["txt"] for w in bl["palavras"])
        bl["dur"] = round(bl["fim"] - bl["ini"], 2)
        bl["conteudo"] = conteudo(bl["texto"])
    return out


def pontuar(blocos: list[dict], tese: str) -> None:
    alvo = conteudo(tese)
    n = len(blocos)
    med_dens = sorted(len(b["palavras"]) / max(b["dur"], 0.3) for b in blocos)[n // 2] if n else 3.0
    for i, b in enumerate(blocos):
        afin = len(b["conteudo"] & alvo) / max(1, min(len(alvo), 6))
        pos = i / max(1, n - 1)
        dens = (len(b["palavras"]) / max(b["dur"], 0.3)) / max(med_dens, 0.1)
        cta = len({norm(w["txt"]).strip() for w in b["palavras"]} & CTA) > 0
        pergunta = b["texto"].strip().endswith("?")
        gancho = (pos <= 0.2) * (1.0 + 0.5 * pergunta + 1.0 * afin)
        fecho = (pos >= 0.8) * (0.6 + 1.0 * cta + 1.0 * afin)
        b["sinais"] = {"afinidade": round(afin, 2), "gancho": round(gancho, 2), "fecho": round(fecho, 2),
                       "densidade": round(dens, 2), "cta": cta}
        b["nota"] = round(3.0 * afin + gancho + fecho + 0.5 * min(dens, 1.3) - 0.3 * (b["dur"] > 10), 2)


def redundante(b: dict, escolhidos: list[dict]) -> dict | None:
    """Mesmo conteúdo já dito por um bloco escolhido. Exige ≥4 palavras de
    conteúdo em comum: um fecho curto ("meu conselho é, faça a mentoria") repete
    as palavras do gancho de propósito e não é redundância."""
    for e in escolhidos:
        comum = b["conteudo"] & e["conteudo"]
        if len(comum) >= 4 and len(comum) / max(1, len(b["conteudo"])) >= 0.6:
            return e
    return None


def selecionar(blocos: list[dict], alvo_s: float, manter: set[int], tirar: set[int]) -> list[dict]:
    if alvo_s <= 0:
        for b in blocos:
            b["fica"], b["motivo"] = b["id"] not in tirar, "corte limpo completo" if b["id"] not in tirar else "tirado pelo usuário"
        return blocos
    for b in blocos:
        b["fica"], b["motivo"] = False, ""
    escolhidos: list[dict] = []
    total = 0.0
    n = len(blocos)
    # obrigatórios: o que o usuário mandou manter, o melhor gancho, o melhor fecho
    obrig = [b for b in blocos if b["id"] in manter]
    cand_g = [b for b in blocos[: max(1, n // 5)] if b["id"] not in tirar]
    cand_f = [b for b in blocos[-max(1, n // 5):] if b["id"] not in tirar]
    if cand_g:
        obrig.append(max(cand_g, key=lambda b: b["sinais"]["gancho"] + b["nota"]))
    if cand_f:
        obrig.append(max(cand_f, key=lambda b: b["sinais"]["fecho"] + b["nota"]))
    for b in obrig:
        if not b["fica"]:
            b["fica"], b["motivo"] = True, ("mantido pelo usuário" if b["id"] in manter else
                                           ("gancho" if b in cand_g else "fechamento"))
            escolhidos.append(b); total += b["dur"]
    for b in sorted(blocos, key=lambda x: -x["nota"]):
        if b["fica"] or b["id"] in tirar:
            if b["id"] in tirar:
                b["motivo"] = "tirado pelo usuário"
            continue
        r = redundante(b, escolhidos)
        if r:
            b["motivo"] = f"redundante com o bloco {r['id']}"
            continue
        if total + b["dur"] > alvo_s * 1.08:
            b["motivo"] = b["motivo"] or "não coube no alvo"
            continue
        if b["sinais"]["afinidade"] == 0 and b["nota"] < 1.0:
            b["motivo"] = "fora da tese"
            continue
        # farrapo: bloco < 1,5 s só entra colado a um vizinho já escolhido
        if b["dur"] < 1.5 and not any(abs(e["ini"] - b["fim"]) < 1.0 or abs(b["ini"] - e["fim"]) < 1.0
                                      for e in escolhidos):
            b["motivo"] = "trecho solto, curto demais"
            continue
        b["fica"], b["motivo"] = True, "dentro da tese"
        escolhidos.append(b); total += b["dur"]
    for b in blocos:
        if not b["fica"] and not b["motivo"]:
            b["motivo"] = "fora da tese"
    return blocos


# --------------------------------------------------------------------------- #
# saída

def montar_edl(edl_limpo: dict, blocos: list[dict], mono) -> dict:
    """Subconjunto do corte limpo: um range por bloco escolhido (bordas
    acústicas nas pausas), respiros do corte limpo preservados dentro dele."""
    out = []
    ficam = [b for b in blocos if b["fica"]]
    for k, b in enumerate(ficam):
        a, z = b["range"]
        prev_fim = ficam[k - 1]["fim"] if k and ficam[k - 1]["range"] == b["range"] else None
        ini = b["ini"] - 0.12
        if prev_fim is not None and ficam[k - 1]["fim"] >= b["ini"] - PAUSA_BLOCO - 0.01:
            ini = (prev_fim + b["ini"]) / 2       # blocos contíguos: emenda no meio da pausa
        fim = b["fim"] + 0.18
        ini, fim = max(a, ini), min(z, fim)
        if mono is not None:
            ini = FL.borda(mono, ini, busca=0.05)
            fim = FL.borda(mono, fim, busca=0.06)
        # junta com o range anterior quando é continuação direta
        if out and out[-1]["source"] == next(iter(edl_limpo["sources"])) and ini - out[-1]["end"] <= 0.02:
            out[-1]["end"] = round(fim, 3)
            out[-1]["quote"] += " " + b["texto"][:60]
            out[-1]["blocos"].append(b["id"])
            continue
        rng = {"source": next(iter(edl_limpo["sources"])), "start": round(ini, 3), "end": round(fim, 3),
               "quote": b["texto"][:120], "reason": f"bloco {b['id']}: {b['motivo']}", "blocos": [b["id"]]}
        if k == 0:
            rng["beat"] = "HOOK"
        out.append(rng)
    # respiros do corte limpo que caem dentro
    for r in out:
        br = [x for lr in edl_limpo.get("_ranges_com_respiros") or edl_limpo["ranges"]
              for x in (lr.get("breaths") or []) if r["start"] < float(x["at"]) and float(x["to"]) < r["end"]]
        if br:
            r["breaths"] = br
    total = sum(r["end"] - r["start"] for r in out) - sum(
        float(b["to"]) - float(b["at"]) - float(b["keep"]) for r in out for b in r.get("breaths", []))
    return {"version": 1, "sources": edl_limpo["sources"], "grade": edl_limpo.get("grade", ""),
            "ritmo": edl_limpo.get("ritmo"), "ranges": out, "total_duration_s": round(total, 2),
            "_gerado_por": "selecao.py"}


def selecao_md(blocos: list[dict], alvo_s: float, tese: str, total: float) -> str:
    L = [f"# Seleção proposta — alvo {alvo_s:.0f}s, resultado {total:.1f}s", "", f"**Tese:** {tese}", "",
         "✔ fica · ✘ sai. Para mudar: `selecao.py <edit> --manter 3,5 --tirar 7` (ou diga no chat).", ""]
    for b in blocos:
        m = "✔" if b["fica"] else "✘"
        L.append(f"- {m} **{b['id']}** `[{b['ini']:06.1f}-{b['fim']:06.1f}]` {b['dur']:4.1f}s · nota {b['nota']:.1f} "
                 f"· {b['motivo']}\n  {b['texto'][:160]}")
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Seleção de blocos do corte limpo guiada pela tese")
    ap.add_argument("edit", type=Path)
    ap.add_argument("--alvo", type=float, default=60.0, help="duração alvo em s (0 = completo)")
    ap.add_argument("--tese", default="", help="a ideia do vídeo em uma frase")
    ap.add_argument("--manter", default="", help="ids de blocos que ficam (ex.: 3,5)")
    ap.add_argument("--tirar", default="", help="ids de blocos que saem")
    ap.add_argument("--edl", type=Path, default=None, help="corte limpo (padrão: edl_proposto.json)")
    ap.add_argument("--fonte", type=Path, default=None)
    ap.add_argument("--sem-audio", action="store_true")
    args = ap.parse_args()
    edit = args.edit.resolve()
    edl_p = args.edl or (edit / "edl_proposto.json")
    if not edl_p.exists():
        sys.exit(f"sem corte limpo em {edl_p} — rode fala_limpa.py antes")
    edl_limpo = json.loads(edl_p.read_text())
    stem_fonte = next(iter(edl_limpo["sources"]))
    tj = edit / "transcripts" / f"{stem_fonte}.json"
    ws = FL.palavras(json.loads(tj.read_text())["words"])
    fonte = args.fonte or Path(edl_limpo["sources"][stem_fonte])
    mono = None if args.sem_audio else FL._carregar_mono(fonte)

    blocos = blocos_do_corte(ws, edl_limpo)
    pontuar(blocos, args.tese)
    manter = {int(x) for x in args.manter.split(",") if x.strip()}
    tirar = {int(x) for x in args.tirar.split(",") if x.strip()}
    selecionar(blocos, args.alvo, manter, tirar)
    edl = montar_edl(edl_limpo, blocos, mono)
    (edit / "edl_selecao.json").write_text(json.dumps(edl, indent=1, ensure_ascii=False))
    (edit / "selecao.json").write_text(json.dumps(
        {"alvo": args.alvo, "tese": args.tese, "manter": sorted(manter), "tirar": sorted(tirar),
         "blocos": [{k: v for k, v in b.items() if k not in ("palavras", "conteudo", "range")} for b in blocos]},
        indent=1, ensure_ascii=False))
    md = selecao_md(blocos, args.alvo, args.tese, edl["total_duration_s"])
    (edit / "selecao.md").write_text(md)
    rp = edit / "roteiro.md"
    if rp.exists():
        txt = rp.read_text().split("\n## Seleção")[0].rstrip() + "\n\n## Seleção\n\n" + md.split("\n", 2)[2]
        rp.write_text(txt)
    ficam = [b for b in blocos if b["fica"]]
    print(f"seleção: {len(ficam)}/{len(blocos)} blocos, {edl['total_duration_s']}s (alvo {args.alvo:.0f}s) — "
          f"{edit / 'selecao.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

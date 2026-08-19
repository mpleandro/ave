#!/usr/bin/env python3
"""Os defeitos que já escaparam uma vez, virados em teste.

    uv run python tests/regressao.py                      # roda todas as fixtures
    uv run python tests/regressao.py --so fome-de-poder   # uma só
    uv run python tests/regressao.py --criar <edit-dir> --nome <slug> \\
        --defeitos "3.21-6.07:gaguejo, 8.77-9.47:respiro, 29.42-32.43:duplicado"

POR QUE AS FIXTURES NÃO SOBEM PARA O REPOSITÓRIO.

Uma fixture aponta para um vídeo na máquina de alguém, com a voz e as palavras
dessa pessoa, e descreve o que ELA considera defeito. As três coisas são dela:
o material, a fala e o critério. Um repositório que outros clonam não é lugar
para nenhuma das três — e um critério de corte importado de outro criador não
testa nada útil, porque o ponto em que um respiro incomoda muda de canal para
canal, como muda a régua que o `preferencias.py` aprende.

Então o repo entrega o MECANISMO e um exemplo anônimo. Cada usuário cria as
suas com `--criar`, elas ficam em `tests/fixtures/` (ignorado pelo git) e
crescem à medida que ele encontra defeito novo. É a mesma divisão que o repo já
faz com `templates/` — "cada um constrói o seu" — e a mesma razão pela qual as
preferências moram em `~/.avelin/`.

O QUE O TESTE EXIGE, e por que não é "removeu".

Para cada defeito da fixture, o pipeline tem de fazer UMA das duas:

    REMOVER   — o trecho não está mais no corte, e
    LEVANTAR  — está no corte, mas apareceu como pergunta ou como falha de portão.

Exigir remoção seria errado: metade dos dez defeitos originais é decisão
editorial (qual tomada fica), e uma ferramenta que decide isso sozinha é
exatamente o que produziu o problema. O que não se aceita é o terceiro caso —
sobreviver EM SILÊNCIO, que foi como os dez chegaram ao usuário.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
HELPERS = RAIZ.parent / "helpers"
FIXTURES = RAIZ / "fixtures"

TOL = 0.60   # casamento de timestamp, em segundos


def _rodar(args: list[str], timeout: int = 900) -> tuple[int, str]:
    r = subprocess.run([sys.executable, *args], capture_output=True,
                       text=True, timeout=timeout)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def _mapa_proxy_para_fonte(edit: Path):
    """No corte ANTIGO o defeito foi anotado em tempo de proxy; a fonte é a
    âncora estável, porque o corte muda a cada iteração e o material não."""
    edl = json.loads((edit / "edl.json").read_text())
    segs, base = [], 0.0
    for r in edl.get("ranges", []):
        ini, fim = float(r["start"]), float(r["end"])
        segs.append((base, base + (fim - ini), ini))
        base += fim - ini

    def conv(t: float):
        for a, b, ini in segs:
            if a - 1e-6 <= t <= b + 1e-6:
                return ini + (t - a)
        return None
    return conv


def _fracao_no_corte(edit: Path, a: float, b: float) -> float:
    """Quanto da FAIXA do defeito sobreviveu ao corte, de 0 a 1.

    Ancorar no ponto inicial não serve: o defeito 15.76–17.85 foi removido quase
    inteiro pelo corte novo e sobraram 0,03s do começo dele dentro de um range.
    Pelo ponto, isso conta como sobrevivente e o teste acusa uma regressão que
    não existe. Um defeito é uma DURAÇÃO de vídeo ruim, então é a duração que se
    mede.
    """
    if b <= a:
        b = a + 0.01
    edl = json.loads((edit / "edl.json").read_text())
    dentro = 0.0
    for r in edl.get("ranges", []):
        lo, hi = max(a, float(r["start"])), min(b, float(r["end"]))
        if hi > lo:
            dentro += hi - lo
    return dentro / (b - a)


# Abaixo disto o defeito foi praticamente removido — o resto é borda.
SOBROU_MIN = 0.35


def _tempos_citados(texto: str) -> list[float]:
    """Todo timestamp que apareceu na saída dos portões, em segundos."""
    ts = [float(m) for m in re.findall(r"(\d+\.\d{1,2})s", texto)]
    for m, s in re.findall(r"(\d+):(\d{2}\.\d{2})", texto):
        ts.append(int(m) * 60 + float(s))
    return ts


def rodar_fixture(fx: dict) -> dict:
    edit = Path(fx["edit"]).expanduser()
    if not (edit / "edl.json").exists():
        return {"nome": fx["nome"], "erro": f"sem edl.json em {edit}"}

    # o que o pipeline tem a dizer sobre este corte, hoje
    _, saida_portao = _rodar([str(HELPERS / "portao_fase1.py"), str(edit), "--pular-render"])
    cmd = [str(HELPERS / "perguntar.py"), str(edit), "--formato", fx.get("formato", "shortform")]
    if fx.get("contexto"):
        cmd += ["--contexto", fx["contexto"]]
    _, saida_perg = _rodar(cmd)
    levantados = _tempos_citados(saida_portao + "\n" + saida_perg)

    conv = _mapa_proxy_para_fonte(edit) if fx.get("proxy_do_corte_original") else None
    resultados = []
    for d in fx["defeitos"]:
        fonte = d.get("fonte_ini")
        if fonte is None:
            fonte = conv(d["proxy_ini"]) if conv else d["proxy_ini"]
        if fonte is None:
            resultados.append({**d, "veredito": "fora do corte", "ok": True})
            continue

        dur = d.get("proxy_fim", d["proxy_ini"]) - d["proxy_ini"]
        frac = _fracao_no_corte(edit, fonte, fonte + max(dur, 0.05))
        if frac < SOBROU_MIN:
            resultados.append({**d, "fonte": round(fonte, 2),
                               "veredito": f"REMOVIDO ({(1 - frac) * 100:.0f}% fora)",
                               "ok": True})
            continue
        perto = any(abs(t - fonte) <= TOL + dur for t in levantados)
        resultados.append({**d, "fonte": round(fonte, 2),
                           "veredito": "LEVANTADO" if perto else "SOBREVIVEU EM SILÊNCIO",
                           "ok": perto})
    return {"nome": fx["nome"], "resultados": resultados,
            "ok": all(r["ok"] for r in resultados)}


def criar(edit: Path, nome: str, defeitos: str, formato: str,
          contexto: str | None) -> Path:
    itens = []
    for parte in defeitos.split(","):
        parte = parte.strip()
        if not parte:
            continue
        faixa, _, tipo = parte.partition(":")
        a, _, b = faixa.partition("-")
        itens.append({"proxy_ini": float(a), "proxy_fim": float(b),
                      "tipo": (tipo or "defeito").strip()})
    edl = json.loads((edit / "edl.json").read_text())
    fx = {
        "nome": nome,
        "edit": str(edit),
        "fontes": list((edl.get("sources") or {}).values()),
        "formato": formato,
        "contexto": contexto,
        # Congela o mapa do corte em que os defeitos foram VISTOS. Sem isto, o
        # primeiro re-corte move todos os timestamps e a fixture passa a apontar
        # para o lugar errado — um teste que mente é pior que teste nenhum.
        "proxy_do_corte_original": [
            {"start": r["start"], "end": r["end"]} for r in edl.get("ranges", [])
        ],
        "defeitos": itens,
    }
    conv = _mapa_proxy_para_fonte(edit)
    for d in fx["defeitos"]:
        f = conv(d["proxy_ini"])
        if f is not None:
            d["fonte_ini"] = round(f, 2)
    FIXTURES.mkdir(parents=True, exist_ok=True)
    p = FIXTURES / f"{nome}.json"
    p.write_text(json.dumps(fx, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def main() -> None:
    ap = argparse.ArgumentParser(description="Regressão dos defeitos já observados")
    ap.add_argument("--so", default=None)
    ap.add_argument("--criar", type=Path, metavar="EDIT_DIR")
    ap.add_argument("--nome")
    ap.add_argument("--defeitos", help='"3.21-6.07:gaguejo, 8.77-9.47:respiro"')
    ap.add_argument("--formato", default="shortform")
    ap.add_argument("--contexto", default=None)
    args = ap.parse_args()

    if args.criar:
        if not args.nome or not args.defeitos:
            sys.exit("--criar exige --nome e --defeitos")
        p = criar(args.criar.resolve(), args.nome, args.defeitos,
                  args.formato, args.contexto)
        print(f"fixture criada: {p}")
        print("  (tests/fixtures/ é ignorado pelo git — ela é sua, não do repositório)")
        return

    if not FIXTURES.is_dir():
        print("nenhuma fixture ainda. Crie a primeira com --criar.")
        print("  o repositório não traz as suas: material, voz e critério são de quem edita.")
        return

    arqs = sorted(q for q in FIXTURES.glob("*.json")
                  if not q.name.startswith(".") and (not args.so or args.so in q.stem))
    if not arqs:
        print("nenhuma fixture casou.")
        return

    falhou = False
    for a in arqs:
        r = rodar_fixture(json.loads(a.read_text()))
        if r.get("erro"):
            print(f"[ERRO] {r['nome']}: {r['erro']}")
            falhou = True
            continue
        marca = "PASSOU" if r["ok"] else "FALHOU"
        print(f"[{marca}] {r['nome']}")
        for d in r["resultados"]:
            sinal = "  ok " if d["ok"] else "  ** "
            print(f"{sinal}{d.get('proxy_ini', '?'):>6}s ({d['tipo']:10s}) "
                  f"fonte {d.get('fonte', '—')}  →  {d['veredito']}")
        falhou = falhou or not r["ok"]
        print()
    sys.exit(1 if falhou else 0)


if __name__ == "__main__":
    main()

"""CONFERÊNCIA DE ENQUADRAMENTO — o corte só vai para a galeria aprovado.

Nasceu de um pedido direto do usuário (2026-11): "não posso ter que ficar
corrigindo um a um". Cinco cortes seguidos chegaram com a faixa 9:16 na pessoa
errada ou em tela cheia, e cada um só foi descoberto assistindo.

Para cada meio segundo do plano (`enquadramento.plano`):
- QUEM FALA pela voz do elenco (`elenco.quem_fala`);
- QUEM ESTÁ NO CENTRO da faixa: o rosto mais perto do centro, identificado
  pela cor da roupa (`elenco.atribuir`);
- se o rosto está centrado (erro em fração da largura da faixa);
- trecho em "fit" (quadro inteiro) com gente na cena.

- faixa 9:16 sobre um COMPARTILHAMENTO DE TELA: o fundo fixo da transmissão
  (`enquadramento._fundo_da_tela`, com os retângulos de uma "dividida" do
  próprio plano) no ar enquanto o plano mostra uma faixa — o slide cortado
  ao meio. Só se mede quando o plano tem alguma "dividida".

Reprova quando: falante errado > 1s somado, ou fit com gente > 0,5s, ou rosto
fora do centro (> 28% da largura) por > 1,5s, ou faixa sobre tela
compartilhada > 1s. Sem elenco, só confere fit, centro e tela.

As cenas são as mesmas do plano (`enquadramento._cenas`: cortes secos no quadro
exato e fusões) — com as do `_medir` só, uma fusão juntava dois planos numa
"cena" e a identidade de quem está na faixa se misturava entre eles.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from . import elenco as EL
from . import enquadramento as EQ


def _x_em(tr: dict, t: float) -> float | None:
    if tr["modo"] != "crop":
        return None
    xs = tr.get("xs")
    if not xs:
        return float(tr["x"])
    T = [p[0] for p in xs]
    X = [p[1] for p in xs]
    return float(np.interp(t, T, X))


def conferir(video: Path, a: float, b: float, plano: dict | None = None) -> dict:
    pl = plano or EQ.plano(video, a, b)
    if pl.get("vertical"):
        return {"ok": True, "motivo": "fonte vertical"}
    cw = pl.get("cw") or int(pl["H"] * 9 / 16) // 2 * 2
    med = EQ._medir(video, a, b)
    el = EL.carregar(video)
    cenas = EQ._cenas(video, a, b, med["cenas"]) + [med["dur"]]
    passo = EQ.PASSO
    nomes = EL.quem_fala(video, a, 0.0, b - a, el, passo) if el else []
    erros = {"falante": 0.0, "fit": 0.0, "fora": 0.0, "tela": 0.0}
    cache: dict = {}
    marcas = []
    tela = _tela_no_ar(video, a, b, pl)
    centragem: list[float] = []
    for k, s in enumerate(np.arange(0.0, b - a, passo)):
        t = a + s
        tr = next((x for x in pl["trechos"] if x["de"] - 1e-6 <= t < x["ate"] + 1e-6), None)
        if tr is None or tr["modo"] in ("dividida", "inteiro"):
            continue
        if tr["modo"] == "crop" and tela is not None and tela[min(len(tela) - 1, int(round(s * 30)))]:
            erros["tela"] += passo
            marcas.append((round(s, 1), "faixa sobre tela compartilhada"))
            continue
        c0 = max(c for c in cenas[:-1] if c <= s + 1e-6)
        c1 = min(c for c in cenas if c > s + 1e-6)
        fs = [r for r in med["rostos"] if abs(r[0] - s) <= 0.15]
        if tr["modo"] == "fit":
            if fs:
                erros["fit"] += passo
                marcas.append((round(s, 1), "tela cheia com gente"))
            continue
        x = _x_em(tr, t)
        if x is None or not fs:
            continue
        centro = x + cw / 2
        perto = min(fs, key=lambda r: abs(r[1] - centro))
        desvio = abs(perto[1] - centro) / cw
        # o rosto de quem está na faixa às vezes não é detectado neste quadro
        # (perfil, microfone na frente): vale onde ele esteve há pouco
        quem = tr.get("pessoa")
        if el and isinstance(quem, str):
            # centragem FINA (não reprova): o rosto de quem a faixa segue, neste
            # quadro, contra o centro — mede o atraso da câmera atrás de quem anda
            chave = (c0, c1)
            if chave not in cache:
                cache[chave] = EQ._pessoas_elenco(med["rostos"], c0, c1, el)
            am = [q[1] for q in cache[chave].get(quem, {}).get("amostras", []) if abs(q[0] - s) <= 0.051]
            if am:
                # o que a faixa não alcança (rosto a menos de meia faixa da
                # borda do quadro) não é atraso: mede até onde ela pode ir
                alvo = min(max(am[0], cw / 2), pl["W"] - cw / 2)
                centragem.append(abs(alvo - centro) / cw)
        if desvio > 0.28 and el and isinstance(quem, str):
            chave = (c0, c1)
            if chave not in cache:
                cache[chave] = EQ._pessoas_elenco(med["rostos"], c0, c1, el)
            am = [q[1] for q in cache[chave].get(quem, {}).get("amostras", []) if abs(q[0] - s) <= 1.5]
            if am and min(abs(v - centro) for v in am) / cw <= 0.28:
                desvio = 0.0
        if desvio > 0.28:
            erros["fora"] += passo
            marcas.append((round(s, 1), f"rosto fora do centro ({desvio:.0%})"))
        n = nomes[k] if k < len(nomes) else None
        # meio segundo em volta de uma TROCA de enquadramento é a própria
        # virada (a voz nova começa um instante antes do corte de imagem) —
        # não é falante errado
        perto_troca = any(abs(t - x["de"]) <= 0.5 for x in pl["trechos"]) and \
            any(abs(t - x["ate"]) <= 0.5 for x in pl["trechos"])
        if el and n and not perto_troca:
            chave = (c0, c1)
            if chave not in cache:
                cache[chave] = EQ._pessoas_elenco(med["rostos"], c0, c1, el)
            nomeados = cache[chave]
            if n in nomeados:
                xs_alvo = [q[1] for q in nomeados[n]["amostras"] if abs(q[0] - s) <= 0.3]
                if xs_alvo and abs(float(np.median(xs_alvo)) - centro) > 0.30 * cw:
                    erros["falante"] += passo
                    marcas.append((round(s, 1), f"fala {n}, faixa em outra pessoa"))
    ok = erros["falante"] <= 1.0 and erros["fit"] <= 0.5 and erros["fora"] <= 1.5 and erros["tela"] <= 1.0
    cg = np.array(centragem)
    return {"ok": ok, "erros": {k: round(v, 1) for k, v in erros.items()}, "marcas": marcas[:12],
            "centragem": {"n": len(cg), "media": round(float(cg.mean()), 4) if len(cg) else None,
                          "acima_10": int((cg > 0.10).sum()), "acima_20": int((cg > 0.20).sum())}}


def _tela_no_ar(video: Path, a: float, b: float, pl: dict) -> np.ndarray | None:
    """[quadro a 30/s] o fundo de alguma "dividida" do plano está no ar."""
    dv = [x for x in pl["trechos"] if x["modo"] == "dividida"]
    if not dv:
        return None
    Q = EQ._miniaturas(video, a, b, 30).astype(np.float32)
    if not len(Q):
        return None
    no_ar = np.zeros(len(Q), bool)
    for x in dv:
        i0, i1 = int((x["de"] - a) * 30), int((x["ate"] - a) * 30)
        ref = list(range(max(0, i0), min(len(Q), i1), 15)) or [min(len(Q) - 1, max(0, i0))]
        dif = EQ._fundo_da_tela(Q, x, ref, pl["W"], pl["H"])
        if (dif[ref] < EQ.FUNDO_DIF).mean() >= 0.8:
            no_ar |= dif < EQ.FUNDO_DIF
    return no_ar

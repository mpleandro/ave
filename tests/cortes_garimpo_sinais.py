#!/usr/bin/env python3
"""Garimpo de cortes: o que o texto esconde — quem fala, pico de voz, fala sem
texto — e o desconto que isso dá na nota.

    uv run python tests/cortes_garimpo_sinais.py

Tudo com dados sintéticos (passos de voz, níveis em dB, palavras), no formato
que `sinais_audio` recebe do elenco e do RMS da fonte. Os números dos casos
vêm do "pneu do Gol" (9689–9721s da live Mil Milionários): a Júlia fala de
16,5 a 21s no meio da história do Paulo; "Eu era pobre, filho!" fica +7 dB
acima do resto; o Whisper engoliu ~5s entre "fala..." e "pai,".
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL / "helpers"))

from cortes import ranking as RK  # noqa: E402
from cortes import score as S  # noqa: E402
from cortes import sinais_audio as SA  # noqa: E402

FALHAS: list[str] = []
CFG = json.loads((SKILL / "helpers" / "cortes" / "config.json").read_text())
Q = 0.021


def confere(nome: str, obtido, esperado) -> None:
    if obtido == esperado:
        print(f"  ok  {nome}")
    else:
        FALHAS.append(nome)
        print(f"FALHA {nome}: obtido {obtido!r}, esperado {esperado!r}")


def passos(*trechos: tuple[str | None, float, float], passo: float = 0.5):
    """[(t, nome)] a cada `passo` nos trechos [(nome, de, até)]."""
    out = []
    for q, de, ate in trechos:
        out += [(round(float(t), 2), q) for t in np.arange(de, ate, passo)]
    return out


def quem_fala():
    ps = passos(("Paulo", 0, 16.5), ("Julia", 16.5, 21.0), ("Paulo", 21.0, 31.5))
    confere("frase toda do Paulo", SA.quem_frase(ps, 1.3, 3.4, 0.6), "Paulo")
    confere("frase toda da Júlia", SA.quem_frase(ps, 16.6, 20.9, 0.6), "Julia")
    confere("frase dividida é '?'", SA.quem_frase(ps, 14.0, 19.0, 0.6), "?")
    confere("frase curta pega o passo mais perto", SA.quem_frase(ps, 17.05, 17.2, 0.6), "Julia")
    confere("sem voz reconhecida é None", SA.quem_frase(passos((None, 0, 5)), 1, 3, 0.6), None)

    tur = SA.turnos(ps, 0.5, 2)
    confere("três turnos", [q for q, _, _ in tur], ["Paulo", "Julia", "Paulo"])
    confere("troca no meio entre os passos", (tur[0][2], tur[1][2]), (16.25, 20.75))
    solto = passos(("Paulo", 0, 10), ("Julia", 10, 10.5), ("Paulo", 10.5, 20))
    confere("passo solto é engolido (a janela de 1,5s borra)", [q for q, _, _ in SA.turnos(solto, 0.5, 2)],
            ["Paulo"])
    confere("passo sem voz não quebra o turno",
            [q for q, _, _ in SA.turnos(passos(("Paulo", 0, 5), (None, 5, 6), ("Paulo", 6, 10)), 0.5, 2)],
            ["Paulo"])

    curtas = SA.falas_curtas(tur, 0.0, 31.4, 6.0)
    confere("a Júlia é fala curta no meio", [(x["quem"], x["lado"]) for x in curtas], [("Julia", "meio")])
    fim = SA.turnos(passos(("Paulo", 0, 25), ("Julia", 25, 30)), 0.5, 2)
    confere("encostada no fim", [x["lado"] for x in SA.falas_curtas(fim, 0.0, 30.0, 6.0)], ["fim"])
    longa = SA.turnos(passos(("Paulo", 0, 20), ("Julia", 20, 35), ("Paulo", 35, 50)), 0.5, 2)
    confere("fala longa não é curta", SA.falas_curtas(longa, 0.0, 50.0, 6.0), [])


def picos_por_falante():
    ref = {"Paulo": -15.0, "Julia": -20.0, None: -16.0}
    niv = [(0, "Paulo", -15.2, 1.3), (1, "Paulo", -14.7, 2.0), (2, "Paulo", -13.0, 1.9),
           (3, "Paulo", -16.8, 1.2), (4, "Julia", -20.4, 4.8), (5, "Paulo", -8.0, 1.4),
           (6, "Paulo", -11.7, 0.9), (7, "Paulo", -18.8, 0.8)]
    confere("só 'Eu era pobre, filho!' (+7 dB) é pico", SA.marcar_picos(niv, ref, CFG), {5: 7.0})
    confere("+2 dB não é pico", SA.marcar_picos([(0, "Paulo", -13.0, 2.0)] + niv[:4], ref, CFG), {})
    julia = [(0, "Julia", -20.1, 2.0), (1, "Julia", -19.8, 2.0), (2, "Julia", -20.3, 2.0),
             (3, "Julia", -14.5, 2.0)]
    confere("Júlia +5,5 dB acima do normal DELA é pico (mesmo abaixo do Paulo)",
            SA.marcar_picos(julia, ref, CFG), {3: 5.5})
    confere("Júlia no normal dela não é pico nem 'sem energia'", SA.marcar_picos(julia[:3], ref, CFG), {})
    gritado = [(k, "Paulo", -9.0, 2.0) for k in range(6)]
    confere("trecho todo gritado não marca tudo", SA.marcar_picos(gritado, ref, CFG), {})
    confere("frase com pouca voz não é pico",
            SA.marcar_picos(niv[:5] + [(5, "Paulo", -8.0, 0.2)], ref, CFG), {})
    r = SA.referencias([(k, "Paulo", -15.0 + k * 0.1, 1.0) for k in range(9)] + [(20, "Julia", -20.0, 1.0)])
    confere("referência por falante só com ≥ 8 frases", ("Paulo" in r, "Julia" in r, None in r), (True, False, True))


def energia(dur: float, voz: list[tuple[float, float]]):
    t = np.arange(0, dur, Q)
    db = np.full(t.size, -60.0)
    for a, b in voz:
        db[(t >= a) & (t < b)] = -20.0
    return t, db, -40.0


def lacunas():
    ws = [{"w": w, "s": s_, "e": s_ + 0.3} for w, s_ in
          (("Eu", 7.0), ("não", 7.4), ("tinha", 7.8), ("onde", 8.2), ("morar.", 8.6))]
    ws += [{"w": "fala...", "s": 9.3, "e": 15.0}, {"w": "pai,", "s": 15.3, "e": 15.6},
           {"w": "fala", "s": 15.7, "e": 16.0}]
    t, db, lim = energia(32, [(7.0, 16.0)])
    out = SA.lacunas(ws, t, db, lim, CFG)
    confere("fala sem texto entre 'fala...' e 'pai,'", [(x["de"], x["ate"]) for x in out], [(9.3, 15.3)])
    confere("voz medida depois da palavra esticada", out and 4.5 <= out[0]["voz"] <= 5.3, True)
    t, db, lim = energia(32, [(7.0, 10.0), (15.3, 16.0)])
    confere("o mesmo vão em silêncio não é lacuna", SA.lacunas(ws, t, db, lim, CFG), [])
    ralo = [{"w": "a", "s": 0.0, "e": 0.2}, {"w": "b", "s": 3.0, "e": 3.2}, {"w": "c", "s": 6.0, "e": 6.2},
            {"w": "d", "s": 6.3, "e": 6.5}]
    t, db, lim = energia(10, [(0, 6.5)])
    out = SA.lacunas(ralo, t, db, lim, CFG)
    confere("palavra solta no buraco: um trecho só", [(x["de"], x["ate"], x["palavras"]) for x in out],
            [(0.0, 6.0, 2)])


def alertas_da_janela():
    textos = [("Pode imaginar a loucura?", 0.0, 1.4), ("Um dia eu não tive dinheiro.", 1.3, 3.4),
              ("Hoje eu troco o pneu de um avião.", 3.8, 6.0), ("Eu não tinha onde morar.", 6.9, 8.2),
              ("pai, fala...", 8.6, 10.0), ("pai, fala pra eles que você é diferente.", 15.3, 21.0),
              ("Eu era pobre, filho!", 20.7, 22.1), ("Manda aí no chat quem já passou fome.", 22.6, 25.0),
              ("Aos 30 anos eu não tinha onde comer.", 27.2, 31.4)]
    frs = []
    for txt, s, e in textos:
        n = len(txt.split())
        ws = [{"w": w, "s": s + (e - s) * k / n, "e": s + (e - s) * (k + 1) / n} for k, w in enumerate(txt.split())]
        if txt == "pai, fala...":
            ws[-1]["e"] = 15.0                 # o Whisper esticou "fala..." por cima do buraco
        frs.append({"s": s, "e": e, "texto": txt, "n": n, "ws": ws})
    c = {"id": "c3177", "start": 0.0, "end": 31.4, "frases": [0, len(frs) - 1]}
    an = {"elenco": True, "passo": 0.5,
          "passos": {"c3177": passos(("Paulo", 0, 16.5), ("Julia", 16.5, 21.0), ("Paulo", 21.0, 31.5))}}
    # voz só onde há frase — e no buraco de 10 a 15,3s, a fala que o Whisper engoliu
    voz = energia(32, [(s, e) for _, s, e in textos] + [(10.0, 15.3)])
    al = SA.alertas(c, frs, an, voz, CFG)
    tipos = sorted(a["tipo"] for a in al)
    confere("interjeição, lacuna e live", tipos, ["interjeicao", "lacuna", "referencia_live"])
    ij = next(a for a in al if a["tipo"] == "interjeicao")
    confere("interjeição da Júlia no meio", (ij["quem"], ij["lado"], ij["de"], ij["ate"]),
            ("Julia", "meio", 16.2, 20.8))
    confere("falas da janela", [q for q, _, _ in SA.falas(c, an, CFG)], ["Paulo", "Julia", "Paulo"])
    sem = SA.alertas(c, frs, {"elenco": False, "passo": 0.5, "passos": {}}, voz, CFG)
    confere("sem elenco: sem alerta de voz, o resto fica", sorted(a["tipo"] for a in sem),
            ["lacuna", "referencia_live"])

    conv = {"id": "v", "start": 0.0, "end": 31.4, "frases": [0, len(frs) - 1]}
    an_v = {"elenco": True, "passo": 0.5,
            "passos": {"v": passos(("Paulo", 0, 6), ("Julia", 6, 10), ("Paulo", 10, 16), ("Julia", 16, 20),
                                   ("Paulo", 20, 31.5))}}
    confere("quem conversa no corte (8s somados) não é interjeição",
            [a for a in SA.alertas(conv, frs, an_v, voz, CFG) if a["tipo"] == "interjeicao"], [])

    perg = {"id": "q", "start": 0.0, "end": 31.4, "frases": [0, len(frs) - 1]}
    an_q = {"elenco": True, "passo": 0.5, "passos": {"q": passos(("Julia", 0, 3.0), ("Paulo", 3.0, 31.5))}}
    confere("pergunta de outra pessoa no início não é alerta",
            [a for a in SA.alertas(perg, frs, an_q, voz, CFG) if a["tipo"] == "interjeicao"],
            [])


def desconto_na_nota():
    al = [{"tipo": "interjeicao", "texto": "a"}, {"tipo": "interjeicao", "texto": "b"},
          {"tipo": "interjeicao", "texto": "c"}, {"tipo": "lacuna", "texto": "d"},
          {"tipo": "desconhecido", "texto": "e"}]
    d, mot = S.desconto(al, CFG)
    confere("interjeição com teto (−10) + lacuna (−8)", d, -18)
    confere("tipo sem peso no config não desconta", "e" in mot, False)
    dims = {k: {"nota": 70, "motivo": "m"} for k in ("gancho", "fluxo", "valor", "completude", "picos")}
    base = {"audio": {"nota": 70, "bruto": {"energia_db": 0, "ritmo_wps": 2, "ar_morto": 0},
                      "subscores": {"energia": 50, "variacao": 50}},
            "autocontencao": {"nota": 70, "motivos": []}}
    limpo = S.final(base, {"dimensoes": dims}, CFG)
    sujo = S.final({**base, "alertas": al}, {"dimensoes": dims}, CFG)
    confere("alerta desconta da nota do lote", limpo["score_final"] - sujo["score_final"], 18)
    confere("motivo do desconto na autocontenção", "alertas -18" in sujo["subscores"]["autocontencao"]["motivo"], True)

    cortes = [{"id": "a", "score_final": 80, "alertas": al, "variantes": {"original": {"score": 80}}},
              {"id": "b", "score_final": 80, "alertas": [], "variantes": {"original": {"score": 80}}}]
    r = {"ordem": [{"id": "a", "score": 80, "motivo": "m"}, {"id": "b", "score": 80, "motivo": "m"}]}
    out = S.aplicar_alertas(RK.aplicar(r, cortes), CFG)
    confere("depois do ranking o corte com alerta desce", [c["id"] for c in out], ["b", "a"])
    confere("e as versões andam junto", out[1]["variantes"]["original"]["score"], 62)
    p = RK.prompt([RK.pedido([{**c, "chave_nota": c["id"], "titulo_sugerido": "t", "abertura_3s": "x",
                               "gancho": {"tipo": "tem"}, "motivo": "m", "texto": "t", "dur": 30,
                               "falas": [["Paulo", 0, 16], ["Julia", 16, 21], ["Paulo", 21, 31]],
                               "picos": [{"texto": "Eu era pobre, filho!", "db": 7.0, "t": 20.6}]}
                              for c in cortes])], {})
    confere("o ranking vê os alertas", "Alertas" in p and "Falas: Paulo" in p and "Pico:" in p, True)


if __name__ == "__main__":
    for caso in (quem_fala, picos_por_falante, lacunas, alertas_da_janela, desconto_na_nota):
        print(caso.__name__)
        caso()
    if FALHAS:
        raise SystemExit(f"\n{len(FALHAS)} falha(s): {', '.join(FALHAS)}")
    print("\ntudo certo")

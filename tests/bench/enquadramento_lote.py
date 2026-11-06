"""Régua do enquadramento em lote: plano + conferência em todos os cortes de uma
galeria e soma dos segundos com defeito. Uso:

    uv run python tests/bench/enquadramento_lote.py <video> [--ids a,b,c] [--saida x.json]

Imprime por corte e o total: falante errado, tela cheia com gente, rosto fora
do centro, faixa sobre tela compartilhada, reprovados — e a centragem fina
(desvio médio do rosto seguido contra o centro da faixa, em fração da faixa;
não reprova, mede o atraso da câmera). Lê <stem>_cortes/analise/janelas.json
(id, a, b)."""
import argparse, json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "helpers"))
from cortes import enquadramento as EQ, conferencia as CF  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("video", type=Path)
ap.add_argument("--ids")
ap.add_argument("--saida", type=Path)
a = ap.parse_args()
V = a.video.resolve()
T = V.parent / f"{V.stem}_cortes"
jan = json.loads((T / "analise/janelas.json").read_text())
if a.ids:
    quer = set(a.ids.split(","))
    jan = [j for j in jan if j["id"] in quer]
tot = {"falante": 0.0, "fit": 0.0, "fora": 0.0, "tela": 0.0}
cg = {"n": 0, "soma": 0.0, "acima_10": 0, "acima_20": 0}
res, ruins = {}, []
for j in jan:
    t0 = time.time()
    try:
        r = CF.conferir(V, j["a"], j["b"], EQ.plano(V, j["a"], j["b"]))
    except Exception as e:  # noqa: BLE001
        r = {"ok": False, "erro": repr(e), "erros": {}}
    for k in tot:
        tot[k] += (r.get("erros") or {}).get(k, 0.0)
    c = r.get("centragem") or {}
    if c.get("n"):
        cg["n"] += c["n"]
        cg["soma"] += c["media"] * c["n"]
        cg["acima_10"] += c["acima_10"]
        cg["acima_20"] += c["acima_20"]
    if not r.get("ok"):
        ruins.append(j["id"])
    res[j["id"]] = {"titulo": j["titulo"], **r}
    print(f"{j['id']:<10} ok={r.get('ok')} {r.get('erros')} {round(time.time()-t0)}s", flush=True)
resumo = {"cortes": len(jan), "reprovados": len(ruins), "lista_reprovados": ruins,
          "segundos": {k: round(v, 1) for k, v in tot.items()},
          "centragem": {"passos": cg["n"], "desvio_medio": round(cg["soma"] / max(1, cg["n"]), 4),
                        "acima_10%": round(cg["acima_10"] / max(1, cg["n"]), 4),
                        "acima_20%": round(cg["acima_20"] / max(1, cg["n"]), 4)}}
print("RESUMO", json.dumps(resumo, ensure_ascii=False), flush=True)
if a.saida:
    a.saida.write_text(json.dumps({"resumo": resumo, "cortes": res}, ensure_ascii=False, indent=1, default=float))

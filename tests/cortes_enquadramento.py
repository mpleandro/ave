"""Enquadramento 9:16 — os defeitos que o usuário apontou na live da Mentoria
Mil Milionários (2026-11) viram régua:

1. trancos: a faixa saltava em degraus a cada 0,5s (x fixo por passo);
2. a faixa saiu do Paulo (falando, andando para a câmera) para a Júlia, que
   só reagia ao fundo — a nota da boca era relativa ao próprio desvio de cada
   pessoa, e quem passa a cena calada tinha base baixa.
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "helpers"))
from cortes import enquadramento as EQ  # noqa: E402

falhas = 0


def ok(cond, nome):
    global falhas
    print(("  ok  " if cond else "  FALHA  ") + nome)
    falhas += 0 if cond else 1


rng = np.random.default_rng(7)
ts = np.arange(0, 20, 0.1)
voz = np.abs(np.sin(ts * 7.0)) * (rng.random(len(ts)) * 0.5 + 0.5)


def envelope(t0, t1):
    m = (ts >= t0) & (ts < t1)
    return float(voz[m].mean()) if m.any() else 0.0


# Paulo: maxilar acompanha a voz, base alta; anda de x=600 a x=900
paulo = {"x": 750.0, "tam": 120.0, "amostras": [
    (float(t), 600 + 15 * t, 120.0, float(0.05 + 0.25 * v), 0.1) for t, v in zip(ts, voz)]}
# Júlia: calada quase o tempo todo, e reage (boca mexe sem seguir a voz) dos 12 aos 16s
jul = {"x": 1500.0, "tam": 80.0, "amostras": [
    (float(t), 1500.0, 80.0, float(0.01 + (0.2 * rng.random() if 12 <= t < 16 else 0.003 * rng.random())), 0.05)
    for t in ts]}

print("quem fala")
serie = EQ._falante_boca([paulo, jul], envelope, 0.0, 20.0, 0.0)
ok(all(i == 0 for _, i in serie), "reação da Júlia não tira a faixa do Paulo")

print("câmera suave")
cw = 606
faixa = lambda cx: int(min(max(0, cx - cw / 2), 1920 - cw))  # noqa: E731
xs = EQ._trajeto(paulo, 0.0, 20.0, faixa, 0.0)
saltos = [abs(b[1] - a[1]) / max(1e-3, b[0] - a[0]) for a, b in zip(xs, xs[1:])]
ok(max(saltos) < 120, f"faixa desliza (maior velocidade {max(saltos):.0f}px/s < 120)")
ok(abs(xs[-1][1] - faixa(900)) < 60, "a faixa acompanha quem anda")
# o defeito real: versão "sem respiros" = dezenas de pedaços; cada um levava o
# caminho inteiro aninhado e o ffmpeg recusava ("Missing ')' or too many args")
import subprocess  # noqa: E402
longo = EQ._trajeto(paulo, 0.0, 20.0, faixa, 0.0) * 1
falhou = []
for t0 in np.arange(0.0, 19.0, 1.3):
    e = EQ.x_expr(longo, float(t0), float(t0) + 1.0)
    r = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=gray:s=1920x1080:r=30:d=1",
                        "-vf", f"crop=606:1080:'{e}':0", "-f", "null", "-"], capture_output=True, text=True)
    if r.returncode:
        falhou.append((round(float(t0), 1), r.stderr[:120]))
ok(not falhou, f"ffmpeg aceita a expressão em todo pedaço ({falhou[:1]})")
ok(EQ.x_expr([[5.0, 300], [9.0, 300]], 5.0) == "300", "trajeto parado vira número fixo")

print("\ntudo certo" if not falhas else f"\n{falhas} falha(s)")
sys.exit(1 if falhas else 0)

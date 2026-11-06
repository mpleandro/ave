"""Enquadramento 9:16 — os defeitos que o usuário apontou na live da Mentoria
Mil Milionários (2026-11) viram régua:

1. trancos: a faixa saltava em degraus a cada 0,5s (x fixo por passo);
2. a faixa saiu do Paulo (falando, andando para a câmera) para a Júlia, que
   só reagia ao fundo — a nota da boca era relativa ao próprio desvio de cada
   pessoa, e quem passa a cena calada tinha base baixa;
3. fusão (dissolve) entre planos não virava troca de cena: a faixa deslizava
   do falante no plano velho até ele no plano novo;
4. a identidade pela cor da roupa decidida quadro a quadro trocava as pessoas
   quando a luz mudava (Camila clareada virava "Júlia"; Camila atrás da Júlia
   tinha o tronco da Júlia);
5. o compartilhamento de tela só era achado onde havia rosto na janelinha:
   buracos de faixa 9:16 cortando o slide no meio da tela.
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

print("troca de cena por fusão")


def _textura(seed, n=1):
    """Imagem 64×36 com manchas (ruído desfocado, contraste de cena real)."""
    import cv2  # noqa: PLC0415
    g = cv2.GaussianBlur(np.random.default_rng(seed).random((36, 64 * n, 3)).astype(np.float32), (0, 0), 2.0)
    return ((g - g.mean()) / g.std() * 60 + 128).clip(0, 255)


A_, B_ = _textura(1), _textura(2)
fps = 30.0
alfa = np.clip((np.arange(90) - 37) / 15.0, 0, 1)           # fusão de 0,5s centrada em 1,5s
fusao = np.stack([(1 - x) * A_ + x * B_ for x in alfa])
ev = EQ._fusoes(fusao.reshape(len(fusao), -1), fps)
ok(len(ev) == 1 and abs(ev[0][0] - 1.5) <= 0.1, f"fusão de 0,5s vira UMA troca no meio dela ({ev})")
seco = np.stack([A_ if k < 45 else B_ for k in range(90)])
ev = EQ._fusoes(seco.reshape(len(seco), -1), fps)
ok(len(ev) == 1 and abs(ev[0][0] - 1.5) <= 1 / 30 + 1e-6, f"corte seco cai no quadro exato ({ev})")
largo = _textura(5, 2)
pan = np.stack([largo[:, k // 2:k // 2 + 64] for k in range(90)])      # panorâmica de 45px em 3s
ev = EQ._fusoes(pan.reshape(len(pan), -1), fps)
ok(not ev, f"panorâmica não é troca de cena ({ev})")
selo = np.stack([A_.copy() for _ in range(90)])
for k in range(45, 90):
    selo[k, 2:14, 2:14] = 255 - selo[k, 2:14, 2:14]                    # QR code que entra num canto
ev = EQ._fusoes(selo.reshape(len(selo), -1), fps)
ok(not ev, f"selo num canto não é troca de cena ({ev})")
# corte seco visto a 10 quadros/s chega até 0,1s atrasado: o plano acerta no quadro de 60p
Q60 = np.stack([A_ if k < 97 else B_ for k in range(180)]).astype(np.uint8)
orig_mini = EQ._miniaturas
EQ._miniaturas = lambda v, a, b, fps=60: Q60
cen = EQ._cenas_agora(Path("x"), 0.0, 3.0, [0.0, 1.7])
EQ._miniaturas = orig_mini
ok(cen == [0.0, round(97 / 60, 3)], f"corte seco no quadro exato de 60p ({cen})")

print("identidade por rastro")
from cortes import elenco as EL  # noqa: E402
el = {"pessoas": [{"nome": "Paulo", "_cor": np.array([35.5, 129.0, 122.5], np.float32)},
                  {"nome": "Julia", "_cor": np.array([145.5, 132.0, 143.0], np.float32)},
                  {"nome": "Camila", "_cor": np.array([82.5, 136.0, 144.5], np.float32)}]}
ok(EL.distancia([50, 141, 137], el["pessoas"][2]["_cor"]) < EL.distancia([50, 141, 137], el["pessoas"][0]["_cor"]),
   "oliva na sombra (L 50) ainda é a Camila, não o azul-marinho do Paulo")
# "De 0 a 10": a panorâmica leva a Camila para a luz (L 95 → 125) enquanto a
# Júlia sai pela esquerda; depois a Camila fica sozinha, com cor de Júlia
ros = []
for k in range(150):
    t = round(k * 0.1, 2)
    clara = 95 + min(30, 30 * t)
    ros.append([t, 1384 - 30 * t, 260, 95, None, None, [clara, 135, 148]])
    if t < 2.4:
        ros.append([t, 946 - 375 * t, 260, 95, None, None, [150, 130, 144]])
pe = EQ._pessoas_elenco(ros, 0.0, 15.0, el)
cam = [q[1] for q in pe.get("Camila", {}).get("amostras", []) if q[0] > 10]
ok(cam and all(x > 900 for x in cam), "a Camila sozinha e clareada continua Camila")
ok(all(x < 1000 for _, x, *_ in pe.get("Julia", {}).get("amostras", [])), "a Júlia é só quem saiu pela esquerda")
# Camila ATRÁS da Júlia: o tronco abaixo do rosto dela é a blusa da Júlia
ros = []
for k in range(60):
    t = round(k * 0.1, 2)
    ros.append([t, 865, 250, 100, None, None, [137, 135, 146]])
    ros.append([t, 996, 260, 160, None, None, [155, 133, 144]])
pe = EQ._pessoas_elenco(ros, 0.0, 6.0, el)
ok(pe.get("Julia", {}).get("x") == 996 and pe.get("Camila", {}).get("x") == 865,
   "dois troncos creme: a da frente é a Júlia, a de trás a Camila")
# rosto de passagem (3 quadros, cor da Camila) não toma o nome do close dela
ros = [[round(k * 0.1, 2), 950, 260, 200, None, None, [109, 136, 148]] for k in range(140)]
ros += [[round(9.9 + k * 0.1, 2), 650, 300, 150, None, None, [80, 137, 145]] for k in range(3)]
pe = EQ._pessoas_elenco(ros, 0.0, 14.0, el)
ok(len(pe.get("Camila", {}).get("amostras", [])) >= 140, "rosto de 3 quadros não rouba o nome do close")

print("compartilhamento de tela pelo fundo")
W, H = 1920, 1080
lay = {"tela": [47, 203, 1208, 674], "cam": [1314, 320, 574, 442]}
fundo = _textura(9)
Q = []
for k in range(240):                                   # 8s a 30/s: câmera 0–2s, tela 2–7s, câmera 7–8s
    if 60 <= k < 210:
        f = fundo.copy()
        f[6:29, 1:41] = _textura(100 + k // 30)[6:29, 1:41]    # o slide troca a cada segundo
        f[10:26, 43:63] = _textura(200 + k)[10:26, 43:63]      # a janelinha mexe sempre
    else:
        f = _textura(300 + k // 15)
    Q.append(f)
Q = np.stack(Q).astype(np.uint8)
EQ._miniaturas = lambda v, a, b, fps=60: Q
fx = EQ._estender_telas([(100 + 4.0, 100 + 5.0, lay, [4.5])], Path("x"), 100.0, 8.0, W, H, [1.9, 7.0])
EQ._miniaturas = orig_mini
ok(len(fx) == 1 and abs(fx[0][0] - 101.9) < 1e-6 and abs(fx[0][1] - 107.0) < 1e-6,
   f"a tela achada em 4–5s vai de 1,9s (fusão) a 7s, mesmo sem rosto ({[(round(x0, 2), round(x1, 2)) for x0, x1, _ in fx]})")

# trecho LONGO num plano só (33s): o caminho inteiro virava ~110 termos e o
# ffmpeg recusava o filtro ("Failed to configure input pad") — sete cortes
import subprocess as _sp  # noqa: E402
longo33 = [[0.3 * k, int(800 + 120 * np.sin(k / 9))] for k in range(115)]
e33 = EQ.x_expr(longo33, 0.0, 34.0)
r33 = _sp.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=gray:s=1920x1080:r=30:d=1",
               "-vf", f"crop=606:1080:'{e33}':0", "-f", "null", "-"], capture_output=True)
ok(r33.returncode == 0, "trecho de 33s num plano só: o ffmpeg aceita o caminho")

print("\ntudo certo" if not falhas else f"\n{falhas} falha(s)")
sys.exit(1 if falhas else 0)

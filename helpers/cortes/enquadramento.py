"""Enquadramento vertical de fonte HORIZONTAL — quem está falando, no centro.

Fonte já vertical passa direto. Horizontal vira 9:16 recortando uma faixa da
altura inteira (em 1920×1080, 607px de largura), e a pergunta é onde pôr a
faixa. A resposta, por cena:

- ninguém em quadro (slide, print, tela) → o quadro INTEIRO sobre o mesmo quadro
  ampliado e desfocado ("fit"): cortar um slide pela metade não serve a ninguém;
- uma pessoa → a faixa nela;
- duas ou mais que cabem juntas na faixa → a faixa no meio delas;
- duas ou mais que não cabem → a faixa em QUEM ESTÁ FALANDO, com corte seco a
  cada troca de turno.

QUEM FALA — primeiro pela VOZ (`voz.py`: impressão de voz WeSpeaker e
agrupamento, que diz QUANDO cada um fala), depois pela BOCA, que só decide
QUAL rosto é qual voz, somando todos os turnos. A primeira versão decidia pela
boca quadro a quadro e errou o começo do podcast de teste inteiro: o apresentador lia
a pergunta de cabeça baixa, sem lábios visíveis, e a faixa ficou no convidado.
O que a boca mede:
1. rosto: YuNet (OpenCV) a 10 quadros/s; os rostos viram pessoas pela posição.
   Fica de fora o que não é gente: rosto pequeno ou de baixa confiança (os
   bonecos da estante de um podcast) e rosto que aparece só às vezes (a
   propaganda no telão do fundo). Medido numa fonte real: sem esse filtro,
   eram 4 "pessoas" para 2.
2. boca: a abertura do maxilar (blendshape `jawOpen` do MediaPipe
   FaceLandmarker). Fala é o maxilar ACOMPANHANDO o áudio: a correlação dele
   com a energia da voz, numa janela de 2s — descontado o SORRISO (blendshapes
   de sorriso), porque quem ri ouvindo também mexe a boca no ritmo do áudio.
   Medir movimento de pixel errava mais: quem gesticula e olha para baixo
   lendo "mexe" o rosto inteiro.
3. dedução: com voz no ar e o rosto VISÍVEL calado, fala o outro — o rosto de
   perfil ou de cabeça baixa perde os lábios em 2 de cada 3 quadros, e é
   justamente quem mais fala num podcast.
4. histerese: a faixa só troca de pessoa depois de 1,5s seguidos do outro
   falando — reação de meio segundo vira pisca-pisca.

A ideia de ligar voz e boca é do SupoClip (lá com diarização do AssemblyAI);
aqui a voz é só a energia do áudio, e a dedução do rosto calado cobre o que a
diarização cobriria.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from derivado import derivado  # noqa: E402

from . import voz as VZ

MODELOS = Path.home() / ".avelin" / "modelos"
YUNET = MODELOS / "face_detection_yunet_2023mar.onnx"
LANDMARKER = MODELOS / "face_landmarker.task"
FPS = 10
PASSO = 0.5            # resolução das decisões de quem fala
TROCA_S = 1.2          # turno mais curto que isso não troca a faixa (vira pisca-pisca)
CENA_DIF = 28.0        # diferença média (0–255) entre quadros reduzidos = corte de câmera


def dimensoes(video: Path) -> tuple[int, int]:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height", "-of", "csv=p=0", str(video)],
                       capture_output=True, text=True).stdout.strip().split(",")
    return int(r[0]), int(r[1])


def vertical(video: Path) -> bool:
    w, h = dimensoes(video)
    return w / h <= 9 / 16 + 0.02


def _quadros(video: Path, a: float, b: float, W: int, H: int):
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-ss", f"{a:.3f}", "-t", f"{b - a:.3f}",
                          "-i", str(video), "-vf", f"fps={FPS}", "-f", "rawvideo",
                          "-pix_fmt", "bgr24", "-"], stdout=subprocess.PIPE)
    n = W * H * 3
    k = 0
    while True:
        buf = p.stdout.read(n)
        if len(buf) < n:
            break
        yield k / FPS, np.frombuffer(buf, np.uint8).reshape(H, W, 3)
        k += 1


def _envelope(video: Path, a: float, b: float):
    au = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{a:.3f}", "-t", f"{b - a:.3f}",
                         "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                        capture_output=True).stdout
    x = np.frombuffer(au, np.int16).astype(np.float64)
    return lambda t0, t1: float(np.sqrt((x[int(max(0, t0) * 16000):int(t1 * 16000)] ** 2).mean() + 1e-9))


def _medir(video: Path, a: float, b: float) -> dict:
    """Uma passada: rostos, lábios e cortes de cena, a 10 quadros/s."""
    import cv2  # noqa: PLC0415
    import mediapipe as mp  # noqa: PLC0415
    from mediapipe.tasks.python import BaseOptions, vision  # noqa: PLC0415

    W, H = dimensoes(video)
    esc = 960 / W
    det = cv2.FaceDetectorYN.create(str(YUNET), "", (960, int(H * esc)), 0.6, 0.3, 50)
    lm = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(LANDMARKER)), num_faces=1,
        output_face_blendshapes=True))
    rostos, cenas, ant = [], [0.0], None
    for t, fr in _quadros(video, a, b, W, H):
        mini = cv2.resize(cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY), (32, 18)).astype(np.float32)
        if ant is not None and np.abs(mini - ant).mean() > CENA_DIF:
            cenas.append(t)
        ant = mini
        _, fs = det.detect(cv2.resize(fr, (960, int(H * esc))))
        for f in (fs if fs is not None else []):
            if f[14] < 0.85:
                continue
            x, y, w, h = (float(v) / esc for v in f[:4])
            s = 1.8 * max(w, h)
            cx, cy = x + w / 2, y + h / 2
            x0, y0 = int(max(0, cx - s / 2)), int(max(0, cy - s / 2))
            x1, y1 = int(min(W, x0 + s)), int(min(H, y0 + s))
            ab = sorriso = None
            if x1 - x0 > 20 and y1 - y0 > 20:
                crop = np.ascontiguousarray(cv2.cvtColor(cv2.resize(fr[y0:y1, x0:x1], (256, 256)),
                                                         cv2.COLOR_BGR2RGB))
                r = lm.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=crop))
                if r.face_landmarks and r.face_blendshapes:
                    bs = {c.category_name: c.score for c in r.face_blendshapes[0]}
                    ab = bs.get("jawOpen", 0.0)
                    sorriso = (bs.get("mouthSmileLeft", 0.0) + bs.get("mouthSmileRight", 0.0)) / 2
            rostos.append([round(t, 2), round(cx, 1), round(cy, 1), round(w, 1),
                           None if ab is None else round(ab, 5),
                           None if sorriso is None else round(sorriso, 4)])
    return {"W": W, "H": H, "dur": b - a, "rostos": rostos, "cenas": cenas}


def _pessoas(rostos: list, t0: float, t1: float, n_amostras: int) -> list[dict]:
    """Rostos de uma cena agrupados por posição; só o que é gente (ver topo)."""
    tr: list[dict] = []
    for t, cx, cy, w, ab, sorriso in rostos:
        if not t0 <= t < t1:
            continue
        p = min(tr, key=lambda q: abs(q["x"] - cx), default=None)
        if p is None or abs(p["x"] - cx) > max(120.0, 2.5 * w):
            p = {"x": cx, "y": cy, "amostras": []}
            tr.append(p)
        p["x"] = 0.8 * p["x"] + 0.2 * cx
        p["amostras"].append((t, cx, w, ab, sorriso))
    if not tr:
        return []
    tam = {id(p): float(np.median([s[2] for s in p["amostras"]])) for p in tr}
    maior = max(tam.values())
    reais = [p for p in tr if len(p["amostras"]) > 0.4 * n_amostras and tam[id(p)] >= 0.6 * maior]
    for p in reais:
        p["x"] = float(np.median([s[1] for s in p["amostras"]]))
        p["tam"] = tam[id(p)]
    return sorted(reais, key=lambda p: p["x"])


def _nota_boca(pessoas: list[dict], envelope, grade, a: float) -> np.ndarray:
    """[pessoa, ponto da grade]: maxilar acompanhando a voz, sorriso descontado
    (NaN onde o rosto não deu lábios)."""
    nota = []
    for p in pessoas:
        am = [(t, ab, sr) for t, _, _, ab, sr in p["amostras"] if ab is not None]
        tt = np.array([x[0] for x in am]) if am else np.zeros(0)
        aa = np.array([x[1] for x in am]) if am else np.zeros(0)
        ss = np.array([x[2] for x in am]) if am else np.zeros(0)
        en = np.array([envelope(a + t - 0.05, a + t + 0.05) for t in tt]) if len(tt) else np.zeros(0)
        col = []
        for s in grade:
            m = (tt >= s - 1.0) & (tt < s + 1.0)
            if m.sum() < 8 or aa[m].std() < 1e-4:
                col.append(np.nan)
                continue
            # quem SORRI ouvindo é descontado: numa fonte real, o convidado
            # rindo de braços cruzados mexia a boca no ritmo do áudio
            col.append(float(np.corrcoef(aa[m], en[m])[0, 1]) * float(aa[m].std())
                       * max(0.0, 1.0 - 1.5 * float(ss[m].mean())))
        nota.append(col)
    return np.array(nota, dtype=float)


def _falante(pessoas: list[dict], envelope, c0: float, c1: float, a: float,
             diar: list[tuple[float, int]]) -> list[tuple[float, int]]:
    """[(t, pessoa)] a cada PASSO. QUANDO cada um fala vem da voz (`voz.diarizar`);
    a boca só decide QUAL rosto é qual voz — somada em todos os turnos de cada
    voz, onde o sinal fraco quadro a quadro vira uma decisão firme."""
    from itertools import permutations  # noqa: PLC0415
    grade = np.arange(c0, c1, PASSO)
    if len(grade) == 0:
        return []
    tv = np.array([t for t, _ in diar]) if diar else np.zeros(0)
    voz_g = []
    for s in grade:
        k = int(np.argmin(np.abs(tv - s))) if len(tv) else -1
        voz_g.append(diar[k][1] if k >= 0 and abs(tv[k] - s) <= 0.75 else None)
    nota = _nota_boca(pessoas, envelope, grade, a)
    vozes = sorted({v for v in voz_g if v is not None})
    S = np.zeros((len(pessoas), max(1, len(vozes))))
    for j, v in enumerate(vozes):
        dela = np.array([x == v for x in voz_g])
        outras = np.array([x is not None and x != v for x in voz_g])
        for i in range(len(pessoas)):
            d = nota[i][dela]
            o = nota[i][outras]
            md = np.nanmean(d) if np.isfinite(d).any() else 0.0
            mo = np.nanmean(o) if np.isfinite(o).any() else 0.0
            S[i, j] = md - mo
    # a atribuição voz→pessoa que mais explica as bocas (todas as permutações)
    melhor, mapa = -np.inf, {}
    for perm in permutations(range(len(pessoas)), min(len(pessoas), len(vozes))):
        tot = sum(S[perm[j], j] for j in range(len(perm)))
        if tot > melhor:
            melhor, mapa = tot, {vozes[j]: perm[j] for j in range(len(perm))}
    bruto = [mapa.get(v) if v is not None else None for v in voz_g]
    # sem voz: mantém quem estava; turno menor que TROCA_S é absorvido
    cur = next((x for x in bruto if x is not None), 0)
    cheio = []
    for x in bruto:
        cur = x if x is not None else cur
        cheio.append(cur)
    precisa = int(round(TROCA_S / PASSO))
    runs, k = [], 0
    while k < len(cheio):
        j = k
        while j < len(cheio) and cheio[j] == cheio[k]:
            j += 1
        runs.append([cheio[k], k, j])
        k = j
    for r in range(len(runs)):
        if runs[r][2] - runs[r][1] < precisa and len(runs) > 1:
            runs[r][0] = runs[r - 1][0] if r > 0 else runs[r + 1][0]
    out = [0] * len(cheio)
    for pessoa, i0, i1 in runs:
        out[i0:i1] = [pessoa] * (i1 - i0)
    return [(float(s), int(x)) for s, x in zip(grade, out)]


def plano(video: Path, a: float, b: float) -> dict:
    """{"vertical": bool, "W", "H", "trechos": [{de, ate, modo, x}]} em tempo da
    FONTE. `modo`: "crop" (faixa com a borda esquerda em `x`) ou "fit"."""
    W, H = dimensoes(video)
    if W / H <= 9 / 16 + 0.02:
        return {"vertical": True, "W": W, "H": H, "trechos": [{"de": a, "ate": b, "modo": "inteiro"}]}
    import instalar  # noqa: PLC0415
    if not instalar.garantir("enquadramento"):
        raise RuntimeError("o enquadramento vertical não pôde ser instalado")

    def calcular():
        med = _medir(video, a, b)
        cw = int(H * 9 / 16) // 2 * 2
        env = _envelope(video, a, b)
        cenas = med["cenas"] + [med["dur"]]
        diar = None   # só se alguma cena tiver gente que não cabe junta
        trechos = []
        for c0, c1 in zip(cenas, cenas[1:]):
            n = max(1, int((c1 - c0) * FPS))
            pes = _pessoas(med["rostos"], c0, c1, n)
            faixa = lambda cx: int(min(max(0, cx - cw / 2), W - cw))  # noqa: E731
            if not pes:
                trechos.append({"de": a + c0, "ate": a + c1, "modo": "fit"})
            elif len(pes) == 1 or pes[-1]["x"] - pes[0]["x"] + pes[-1]["tam"] < cw * 0.9:
                meio = (pes[0]["x"] + pes[-1]["x"]) / 2
                trechos.append({"de": a + c0, "ate": a + c1, "modo": "crop", "x": faixa(meio)})
            else:
                if diar is None:
                    diar = VZ.diarizar(VZ.audio(video, a, b), max(2, len(pes)))
                for t, i in _falante(pes, env, c0, c1, a, diar):
                    x = faixa(pes[i]["x"])
                    if trechos and trechos[-1]["modo"] == "crop" and trechos[-1]["x"] == x \
                            and abs(trechos[-1]["ate"] - (a + t)) < 1e-6:
                        trechos[-1]["ate"] = a + min(t + PASSO, c1)
                    else:
                        trechos.append({"de": a + t, "ate": a + min(t + PASSO, c1), "modo": "crop",
                                        "x": x, "pessoa": i})
        if trechos:
            trechos[0]["de"], trechos[-1]["ate"] = a, b
        return {"vertical": False, "W": W, "H": H, "cw": cw, "trechos": trechos}

    return derivado("enquadramento", [video], {"a": round(a, 3), "b": round(b, 3), "versao": 3},
                    "1", calcular)


def filtro(trecho: dict, W: int, H: int, saida=(1080, 1920), rot: str = "0") -> str:
    """O filtro de vídeo de um trecho: faixa recortada, ou o quadro inteiro
    sobre o mesmo quadro ampliado e desfocado."""
    ow, oh = saida
    if trecho["modo"] == "inteiro":
        return f"scale={ow}:{oh}:force_original_aspect_ratio=decrease,pad={ow}:{oh}:(ow-iw)/2:(oh-ih)/2"
    if trecho["modo"] == "crop":
        cw = int(H * 9 / 16) // 2 * 2
        return f"crop={cw}:{H}:{trecho['x']}:0,scale={ow}:{oh}:flags=lanczos"
    return (f"split[f{rot}][b{rot}];[b{rot}]scale={ow}:{oh}:force_original_aspect_ratio=increase,"
            f"crop={ow}:{oh},gblur=sigma=30,eq=brightness=-0.08[bb{rot}];[f{rot}]scale={ow}:-2[ff{rot}];"
            f"[bb{rot}][ff{rot}]overlay=0:(H-h)/2")


def recortar(segs: list[tuple[float, float]], pl: dict) -> list[tuple[float, float, dict]]:
    """Cada trecho da versão partido nas trocas de enquadramento."""
    out = []
    for sa, sb in segs:
        for t in pl["trechos"]:
            x0, x1 = max(sa, t["de"]), min(sb, t["ate"])
            if x1 - x0 > 1e-3:
                out.append((x0, x1, t))
    return out

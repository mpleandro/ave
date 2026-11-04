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
    """Rostos de uma cena viram PESSOAS por rastreio quadro a quadro: dois rostos no
    mesmo quadro nunca são a mesma pessoa, e cada rosto segue o rastro mais
    próximo dentro de ~1 largura de rosto. Fica de fora o que não é gente: rosto
    pequeno ou que aparece pouco (boneco da estante, propaganda no telão).

    Medido no "Dinheiro não é sujo": agrupar por posição na cena inteira, com
    tolerância de 2,5 rostos, fundia a apresentadora de branco (x≈800) com o
    homem ao lado (x≈1050), e a presença mínima de 40% da cena descartava quem
    fala só no começo e sai — ela abria o corte falando e a faixa ia para outra
    pessoa."""
    por_t: dict = {}
    for r in rostos:
        if t0 <= r[0] < t1:
            por_t.setdefault(r[0], []).append(r)
    tr: list[dict] = []
    for t in sorted(por_t):
        fs = por_t[t]
        vivos = [k for k, p in enumerate(tr) if t - p["ult"] <= 2.0]
        pares = sorted((abs(tr[k]["x"] - f[1]), k, n) for k in vivos for n, f in enumerate(fs))
        usados_t, usados_f = set(), set()
        for d, k, n in pares:
            if k in usados_t or n in usados_f or d > max(40.0, 0.6 * fs[n][3]):
                continue
            usados_t.add(k)
            usados_f.add(n)
            p, f = tr[k], fs[n]
            p["x"] = f[1]
            p["ult"] = t
            p["amostras"].append((f[0], f[1], f[3], f[4], f[5]))
        for n, f in enumerate(fs):
            if n not in usados_f:
                tr.append({"x": f[1], "y": f[2], "ult": t, "amostras": [(f[0], f[1], f[3], f[4], f[5])]})
    if not tr:
        return []
    tam = {id(p): float(np.median([s[2] for s in p["amostras"]])) for p in tr}
    maior = max(tam.values())
    minimo = min(max(15, int(0.4 * n_amostras)), 15)    # 1,5s em quadro já é gente
    reais = [p for p in tr if len(p["amostras"]) >= minimo and tam[id(p)] >= 0.6 * maior]
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
        en = np.array([envelope(t - 0.05, t + 0.05) for t in tt]) if len(tt) else np.zeros(0)
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
             diar: list[tuple[float, int]], mudos=None, idx_fora: int = -1) -> list[tuple[float, int]]:
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
        # quem fala de FORA do quadro costuma dar uma frase curta ("Dinheiro não é sujo."):
        # absorver o turno dele é exatamente o erro que o usuário apontou
        if runs[r][2] - runs[r][1] < precisa and len(runs) > 1 \
                and not pessoas[runs[r][0]].get("fora"):
            runs[r][0] = runs[r - 1][0] if r > 0 else runs[r + 1][0]
    out = [0] * len(cheio)
    for pessoa, i0, i1 in runs:
        out[i0:i1] = [pessoa] * (i1 - i0)
    if mudos:
        for k, s_ in enumerate(grade):
            if round(float(s_), 2) in mudos:
                out[k] = idx_fora
    return [(float(s), int(x)) for s, x in zip(grade, out)]


def _x_local(p: dict, t: float) -> float:
    """Onde a pessoa está em t (mediana dos rostos em ±1s): quem anda ou gesticula
    é seguido, em vez de ficar na posição média da cena inteira."""
    xs = [cx for tt, cx, *_ in p["amostras"] if abs(tt - t) <= 1.0]
    return float(np.median(xs)) if len(xs) >= 3 else float(p["x"])


def _passos_fora(pes: list[dict], envelope, c0: float, c1: float, a: float) -> set:
    """Passos (em s, arredondados) em que HÁ voz e nenhuma boca visível se mexe:
    quem fala está fora do quadro. A boca parada é relativa à própria pessoa
    (desvio na janela de ±0,5s contra o desvio dela na cena inteira)."""
    grade = np.arange(c0, c1, PASSO)
    base = []
    for p in pes:
        ab = np.array([s_[3] for s_ in p["amostras"] if s_[3] is not None])
        base.append(float(ab.std()) if len(ab) > 10 else None)
    if any(b_ is None for b_ in base):
        return set()
    en = np.array([envelope(s_ - 0.25, s_ + 0.25) for s_ in grade])
    if not len(en):
        return set()
    limiar_voz = float(np.percentile(en, 40))
    out = set()
    for k, s_ in enumerate(grade):
        if en[k] < limiar_voz:
            continue
        parado = True
        for p, b_ in zip(pes, base):
            ab = [x[3] for x in p["amostras"] if x[3] is not None and abs(x[0] - s_) <= 0.5]
            if len(ab) < 4 or float(np.std(ab)) >= 0.35 * b_:
                parado = False
                break
        if parado:
            out.add(round(float(s_), 2))
    return out


def _falante_boca(pes: list[dict], envelope, c0: float, c1: float, a: float) -> list[tuple[float, int]]:
    """[(t, pessoa)] a cada PASSO, pela boca; `len(pes)` = alguém fora do quadro."""
    grade = np.arange(c0, c1, PASSO)
    if len(grade) == 0:
        return []
    base = []
    for p in pes:
        ab = np.array([x[3] for x in p["amostras"] if x[3] is not None])
        base.append(float(ab.std()) if len(ab) > 10 else 0.0)
    ok = [i for i, b_ in enumerate(base) if b_ > 0.005]        # jawOpen travado ~0 = landmarker sem lábios
    quebrados = [i for i, b_ in enumerate(base) if b_ <= 0.005]
    en = np.array([envelope(s_ - 0.25, s_ + 0.25) for s_ in grade])
    lim = 0.12 * float(np.percentile(en, 75))
    cur, bruto = ok[0] if ok else 0, []
    for k, s_ in enumerate(grade):
        if en[k] >= lim:
            z = {}
            for i in ok:
                ab = [x[3] for x in pes[i]["amostras"] if x[3] is not None and abs(x[0] - s_) <= 0.4]
                if len(ab) >= 3:
                    z[i] = float(np.std(ab)) / base[i]
            melhor = max(z, key=z.get) if z else None
            if melhor is not None and z[melhor] >= 0.4:
                cur = melhor
            elif z or k < 3:
                cur = -1          # voz e ninguém mexendo a boca: decide pela duração
        bruto.append(cur)
    # incerto: turno longo é de quem tem o rosto sem lábios medidos; curto, de fora do quadro
    k = 0
    while k < len(bruto):
        j = k
        while j < len(bruto) and bruto[j] == bruto[k]:
            j += 1
        if bruto[k] == -1:
            # quem fala FORA do quadro não pode ser centrado (não está na imagem):
            # o corte fica na pessoa mais próxima em vez de mostrar parede vazia
            if quebrados and j - k >= 8:
                dono = quebrados[0]
            else:
                dono = bruto[k - 1] if k > 0 else -2   # pausa do falante: ele fica; no início, o próximo
            bruto[k:j] = [dono] * (j - k)
        k = j
    if bruto and bruto[0] == -2:
        prox = next((x for x in bruto if x >= 0), ok[0] if ok else 0)
        bruto = [prox if x == -2 else x for x in bruto]
    # turno curto é absorvido (pisca-pisca), menos o de quem está fora do quadro
    precisa = int(round(TROCA_S / PASSO))
    runs, k = [], 0
    while k < len(bruto):
        j = k
        while j < len(bruto) and bruto[j] == bruto[k]:
            j += 1
        runs.append([bruto[k], k, j])
        k = j
    for r in range(len(runs)):
        curto = runs[r][2] - runs[r][1] < precisa
        if runs[r][0] == len(pes):
            curto = runs[r][2] - runs[r][1] < 2     # fora do quadro: 1s já vale
        if curto and len(runs) > 1:
            runs[r][0] = runs[r - 1][0] if r > 0 else runs[r + 1][0]
    out = [0] * len(bruto)
    for pessoa, i0, i1 in runs:
        out[i0:i1] = [pessoa] * (i1 - i0)
    return [(float(s_), int(x)) for s_, x in zip(grade, out)]


def _layout_tela(video: Path, t: float, cx: float, cy: float, W: int, H: int) -> dict | None:
    """Os dois retângulos de um compartilhamento de tela: a JANELA DA CÂMERA (o
    menor contorno que contém os rostos pequenos) e a TELA (o maior retângulo
    que não a cobre). Medido na live "Enriqueça": slide 1220×686 à esquerda,
    câmera 581×448 à direita, com borda verde nos dois."""
    import cv2  # noqa: PLC0415
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1",
                          "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], capture_output=True).stdout
    if len(raw) < W * H * 3:
        return None
    fr = np.frombuffer(raw[:W * H * 3], np.uint8).reshape(H, W, 3)
    e = cv2.dilate(cv2.Canny(cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY), 40, 120), np.ones((3, 3), np.uint8))
    cs, _ = cv2.findContours(e, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    cams, telas = [], []
    for c in cs:
        x, y, w, h = cv2.boundingRect(c)
        if w * h < 0.01 * W * H or w > 0.9 * W:
            continue
        if x < cx < x + w and y < cy < y + h:
            cams.append((x, y, w, h))
        ap = cv2.approxPolyDP(c, 0.02 * cv2.arcLength(c, True), True)
        if len(ap) == 4 and cv2.contourArea(c) / (w * h) > 0.85 and w * h >= 0.1 * W * H:
            telas.append((x, y, w, h))
    if not cams:
        return None
    cam = min(cams, key=lambda r: r[2] * r[3])
    telas = [r for r in telas if not (r[0] < cx < r[0] + r[2] and r[1] < cy < r[1] + r[3])]
    if not telas:
        return None
    tela = max(telas, key=lambda r: r[2] * r[3])
    ins = lambda r, k=6: [r[0] + k, r[1] + k, r[2] - 2 * k, r[3] - 2 * k]  # noqa: E731  sem a borda
    return {"tela": ins(tela), "cam": ins(cam)}


def _vazios_viram_fit(trechos: list[dict], rostos: list, a: float, dur: float,
                      video: Path | None = None, W: int = 1920, H: int = 1080) -> list[dict]:
    """Trecho SEM rosto nenhum (≥1,5s) vira "fit" — o quadro inteiro sobre ele
    mesmo ampliado e desfocado — mesmo DENTRO de uma cena.

    Medido no "Até quando você vai tolerar isso?": o compartilhamento de tela
    (slide escuro sobre estúdio escuro) não passa no detector de corte de cena,
    então a faixa de 9:16 continuava na posição da última pessoa e cortava o
    slide ao meio."""
    import bisect  # noqa: PLC0415
    # rosto PEQUENO não conta: no compartilhamento de tela a câmera vira uma
    # janelinha ao lado do slide, e os rostos dela (~1/4 do tamanho) seguem
    # sendo detectados o tempo todo
    if not rostos:
        return trechos
    larg = float(np.percentile([r[3] for r in rostos], 75))
    ts = sorted(r[0] for r in rostos if r[3] >= 0.5 * larg)
    grade = np.arange(0, dur, PASSO)
    vaz = []
    for s_ in grade:
        i = bisect.bisect_left(ts, s_ - 0.6)
        vaz.append(not (i < len(ts) and ts[i] <= s_ + 0.6))
    faixas, k = [], 0
    while k < len(vaz):
        j = k
        while j < len(vaz) and vaz[j] == vaz[k]:
            j += 1
        if vaz[k] and (j - k) * PASSO >= 1.5:
            faixas.append((a + k * PASSO, a + min(j * PASSO, dur)))
        k = j
    if not faixas:
        return trechos
    out = []
    for tr in trechos:
        pedacos = [(tr["de"], tr["ate"])]
        for f0, f1 in faixas:
            novos = []
            for p0, p1 in pedacos:
                if f1 <= p0 or f0 >= p1:
                    novos.append((p0, p1))
                    continue
                if p0 < f0:
                    novos.append((p0, f0))
                if f1 < p1:
                    novos.append((f1, p1))
            pedacos = novos
        out += [{**tr, "de": p0, "ate": p1} for p0, p1 in pedacos if p1 - p0 > 1e-6]
    for f0, f1 in faixas:
        # compartilhamento de tela COM a janelinha da câmera ao lado: tela em
        # cima, apresentadores embaixo (pedido do usuário). Sem janelinha, ou
        # sem achar os dois retângulos, cai no quadro inteiro desfocado.
        peq = [r for r in rostos if f0 - a <= r[0] < f1 - a and r[3] < 0.5 * larg]
        lay = None
        if video is not None and len(peq) >= 5:
            cx = float(np.median([r[1] for r in peq]))
            cy = float(np.median([r[2] for r in peq]))
            lay = _layout_tela(video, (f0 + f1) / 2, cx, cy, W, H)
        if lay:
            out.append({"de": f0, "ate": f1, "modo": "dividida", **lay})
        else:
            out.append({"de": f0, "ate": f1, "modo": "fit"})
    return sorted(out, key=lambda t: t["de"])


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
            elif len(pes) == 1:
                trechos.append({"de": a + c0, "ate": a + c1, "modo": "crop", "x": faixa(pes[0]["x"])})
            else:
                # REGRA DO USUÁRIO: o sujeito que fala fica SEMPRE no centro — mesmo
                # quando duas pessoas cabem juntas na faixa (centrar no meio delas
                # deixava as duas fora do centro).
                # quem fala = quem MEXE A BOCA no ritmo da voz (jawOpen); rosto cujo
                # landmarker não funciona (jawOpen travado em 0) só é escolhido quando
                # há voz e ninguém mais mexe a boca; voz sem boca nenhuma = fora do quadro
                lado = 0 if np.mean([p["x"] for p in pes]) > W / 2 else W
                fora = {"x": float(lado), "amostras": [], "tam": 0.0, "fora": True}
                pes_f = pes + [fora]
                serie = _falante_boca(pes, env, c0, c1, a)
                prev_x = {}
                for t, i in serie:
                    p = pes_f[i]
                    alvo = p["x"] if p.get("fora") else _x_local(p, t)
                    x = faixa(alvo)
                    ant = prev_x.get(i)
                    if ant is not None and abs(ant - x) < 70:   # histerese: não balança com o gesto
                        x = ant
                    prev_x[i] = x
                    if trechos and trechos[-1]["modo"] == "crop" and trechos[-1]["x"] == x \
                            and abs(trechos[-1]["ate"] - (a + t)) < 1e-6:
                        trechos[-1]["ate"] = a + min(t + PASSO, c1)
                    else:
                        trechos.append({"de": a + t, "ate": a + min(t + PASSO, c1), "modo": "crop",
                                        "x": x, "pessoa": i})
        trechos = _vazios_viram_fit(trechos, med["rostos"], a, med["dur"], video, W, H)
        if trechos:
            trechos[0]["de"], trechos[-1]["ate"] = a, b
        return {"vertical": False, "W": W, "H": H, "cw": cw, "trechos": trechos}

    return derivado("enquadramento", [video], {"a": round(a, 3), "b": round(b, 3), "versao": 20},
                    "1", calcular)


def filtro(trecho: dict, W: int, H: int, saida=(1080, 1920), rot: str = "0") -> str:
    """O filtro de vídeo de um trecho: faixa recortada, ou o quadro inteiro
    sobre o mesmo quadro ampliado e desfocado."""
    ow, oh = saida
    if trecho["modo"] == "inteiro":
        return f"scale={ow}:{oh}:force_original_aspect_ratio=decrease,pad={ow}:{oh}:(ow-iw)/2:(oh-ih)/2"
    if trecho["modo"] == "dividida":
        # tela em cima, câmera embaixo, as duas na largura toda, sobre o quadro desfocado
        tx, ty, tw, th = trecho["tela"]
        cx, cy, cw_, ch = trecho["cam"]
        h1 = int(round(ow * th / tw / 2)) * 2
        h2 = int(round(ow * ch / cw_ / 2)) * 2
        gap = 24
        y1 = max(0, (oh - h1 - h2 - gap) // 2)
        y2 = y1 + h1 + gap
        r = rot
        return (f"split=3[f{r}][t{r}][c{r}];[f{r}]scale={ow}:{oh}:force_original_aspect_ratio=increase,"
                f"crop={ow}:{oh},gblur=sigma=30,eq=brightness=-0.12[bb{r}];"
                f"[t{r}]crop={tw}:{th}:{tx}:{ty},scale={ow}:{h1}:flags=lanczos[tt{r}];"
                f"[c{r}]crop={cw_}:{ch}:{cx}:{cy},scale={ow}:{h2}:flags=lanczos[cc{r}];"
                f"[bb{r}][tt{r}]overlay=0:{y1}[x{r}];[x{r}][cc{r}]overlay=0:{y2}")
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

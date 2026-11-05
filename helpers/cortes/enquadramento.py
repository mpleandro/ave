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
FUSAO_DIF = 30.0       # diferença RMS (0–255, 64×36) mínima entre as pontas de uma fusão
FUSAO_RES = 0.15       # resíduo máximo do modelo "fusão" (fração da diferença entre as pontas)
FUNDO_DIF = 12.0       # fundo do compartilhamento de tela a menos que isto da referência = tela ainda no ar
FALA_MIN = 0.004       # correlação maxilar×voz × amplitude abaixo disto = ninguém fala em quadro
SUAVE_TAU = 0.35       # s — constante do filtro que faz a câmera DESLIZAR atrás do rosto
SUAVE_ZONA = 16        # px — o rosto anda menos que isto e a câmera não se mexe


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
    """Uma passada: rostos, lábios, cor da roupa e cortes de cena, a 10 quadros/s.
    Guardada no cache de derivados: o plano e a conferência usam a mesma."""
    return derivado("enquadramento_medida", [video], {"a": round(a, 3), "b": round(b, 3), "versao": 2},
                    "1", lambda: _medir_agora(video, a, b))


def _medir_agora(video: Path, a: float, b: float) -> dict:
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
            from . import elenco as EL  # noqa: PLC0415
            rostos.append([round(t, 2), round(cx, 1), round(cy, 1), round(w, 1),
                           None if ab is None else round(ab, 5),
                           None if sorriso is None else round(sorriso, 4),
                           EL.cor_tronco(fr, cx, cy, w, h)])
    return {"W": W, "H": H, "dur": b - a, "rostos": rostos, "cenas": cenas}


def _miniaturas(video: Path, a: float, b: float, fps: int = 60) -> np.ndarray:
    """O trecho inteiro em 64×36 a `fps` quadros/s — 1s de decodificação para 25s
    de fonte 1080p60 (medido), barato o bastante para olhar cada quadro."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", str(video),
                          "-vf", f"fps={fps},scale=64:36", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                         capture_output=True).stdout
    n = len(raw) // (64 * 36 * 3)
    return np.frombuffer(raw[:n * 64 * 36 * 3], np.uint8).reshape(n, 36, 64, 3)


def _fusoes(X: np.ndarray, fps: float) -> list[tuple[float, float]]:
    """[(t do MEIO da fusão, resíduo)] — fusões (dissolves) entre dois planos.

    Por que não basta a diferença entre quadros vizinhos: numa fusão de 0,5s
    cada quadro muda 1/15 do total e nenhum passa de CENA_DIF. Medido nos 73
    trechos da live da Mentoria Mil Milionários (2026-11): 41 fusões conferidas
    a olho — câmera↔compartilhamento de tela e câmera↔câmera — que o detector
    de corte seco não via. Sem o corte, a faixa deslizava do lugar do falante
    no plano velho até o lugar dele no plano novo e cada cena misturava gente
    dos dois. Este teste acha 37 das 41, sem nenhuma troca falsa.

    O teste é o próprio modelo da fusão: no meio dela, cada quadro é uma MISTURA
    das duas pontas, F = (1−α)·A + α·B. Para cada meia-duração L (0,1 a 0,6s) e
    cada instante, mede-se quanto da imagem a melhor mistura NÃO explica. Uma
    panorâmica ou alguém andando também mudam muito a imagem, mas o quadro do
    meio é a imagem DESLOCADA, não a mistura — o resíduo fica alto. Nos 73
    trechos: fusões e cortes com resíduo < 0,15 (a maioria < 0,10); a panorâmica
    seguindo a Camila no "100 mil" (0–6s) dá 0,33–0,40. Ficam de fora 4 das 41:
    três fusões feitas COM a câmera em movimento (o quadro do meio é mistura E
    deslocamento) e uma entrada de tela em que a imagem da câmera ENCOLHE até a
    janelinha — essa a `_estender_telas` acerta pelo fundo."""
    n = len(X)
    cand = []
    for L in (3, 6, 9, 12, 18):
        if n <= 2 * L + 1:
            continue
        D = X[2 * L:] - X[:-2 * L]                       # D[i−L] = X[i+L] − X[i−L]
        nD = np.sqrt((D * D).mean(1))
        for k in np.where(nD >= FUSAO_DIF)[0]:
            d = D[k]
            # a troca tem de cobrir o quadro: um selo/QR code que some num canto
            # ou o corte DENTRO da janelinha da câmera de um compartilhamento
            # mexem só ali (medido: 4 dos 7 falsos nos 73 trechos)
            if (np.abs(d).reshape(-1, 3).max(1) > 25).mean() < 0.3:
                continue
            i = int(k) + L
            M = X[i - L + 1:i + L] - X[i - L]
            al = (M @ d) / float(d @ d)
            res = float(np.sqrt(((M - al[:, None] * d[None]) ** 2).mean(1)).mean() / nD[k])
            # a mistura tem de ATRAVESSAR a janela: com o corte seco caindo
            # exatamente na ponta, todo o miolo é o plano velho parado (α≈0) e
            # o resíduo sai baixo sem haver troca nenhuma ali dentro
            if res < FUSAO_RES and al.min() < 0.3 and al.max() > 0.7:
                # o instante da troca é onde a mistura passa da metade: o meio
                # da fusão — ou o quadro do corte seco que caiu dentro da janela
                # longa (sem isso, um corte seco visto com L=0,6s saía 0,57s
                # antes do lugar, medido no "Se você não faz dinheiro")
                meio = int(np.argmax(al >= 0.5)) if (al >= 0.5).any() else len(al) // 2
                cand.append((res, (i - L + 1 + meio) / fps, L))
    out: list[tuple[float, float]] = []
    for res, t, _ in sorted(cand):                       # melhor primeiro; um por evento
        if all(abs(t - u) > 0.6 for u, _ in out):
            # uma janela CURTA no miolo da fusão também é mistura perfeita e
            # põe o meio onde ela estiver; a mais longa quase tão boa cobre a
            # fusão inteira e acha o meio dela (sintético de 0,5s: 0,12s de erro
            # pela melhor, 0 pela mais longa)
            viz = [c for c in cand if abs(c[1] - t) <= 0.6 and c[0] <= res + 0.03]
            Lmax = max(c[2] for c in viz)
            t = float(np.median([c[1] for c in viz if c[2] == Lmax]))
            out.append((round(t, 3), round(res, 3)))
    return sorted(out)


def _cenas(video: Path, a: float, b: float, cortes: list[float]) -> list[float]:
    """Início de cada cena (s, relativo a `a`): os cortes secos do `_medir` (a 10
    quadros/s) acertados para o quadro exato, mais as fusões.

    O acerto existe porque a 10 quadros/s o corte cai até 0,1s DEPOIS do
    primeiro quadro do plano novo — 6 quadros de 60p mostrando o plano novo
    com a faixa do velho, um tranco a cada troca de câmera."""
    return derivado("enquadramento_cenas", [video],
                    {"a": round(a, 3), "b": round(b, 3), "cortes": [round(c, 2) for c in cortes], "versao": 2},
                    "1", lambda: _cenas_agora(video, a, b, cortes))


def _cenas_agora(video: Path, a: float, b: float, cortes: list[float]) -> list[float]:
    Q = _miniaturas(video, a, b, 60)
    if len(Q) < 8:
        return [0.0]
    X = Q.reshape(len(Q), -1).astype(np.float32)
    d = np.r_[0.0, np.sqrt(((X[1:] - X[:-1]) ** 2).mean(1))]
    secos = []
    for t in cortes[1:]:
        # o plano novo começou em (t − 0,1s, t]: o quadro de 60p que mais muda ali
        j0, j1 = max(1, int(round((t - 0.15) * 60))), min(len(X) - 1, int(round((t + 0.05) * 60)))
        j = j0 + int(np.argmax(d[j0:j1 + 1])) if j1 >= j0 else int(round(t * 60))
        secos.append(round(j / 60, 3))
    fus = [t for t, _ in _fusoes(X[::2], 30.0) if all(abs(t - s) > 0.6 for s in secos)]
    out = [0.0]
    for t in sorted(set(secos) | set(fus)):
        if t - out[-1] >= 2 / 60:
            out.append(t)
    return out


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
            p["amostras"].append((f[0], f[1], f[3], f[4], f[5], f[6] if len(f) > 6 else None))
        for n, f in enumerate(fs):
            if n not in usados_f:
                tr.append({"x": f[1], "y": f[2], "ult": t,
                           "amostras": [(f[0], f[1], f[3], f[4], f[5], f[6] if len(f) > 6 else None)]})
    if not tr:
        return []
    tam = {id(p): float(np.median([s[2] for s in p["amostras"]])) for p in tr}
    maior = max(tam.values())
    # 1,5s em quadro já é gente — mas numa cena MAIS CURTA que isso ninguém
    # chegaria a 15 amostras e a cena inteira virava quadro inteiro ("fit").
    # Medido no "Preguiça de levantar do sofá" (2026-11): plano de 1,3s com o
    # Paulo falando, 35 rostos detectados, zero pessoas. O piso acompanha a cena.
    minimo = min(15, max(4, int(0.5 * n_amostras)))
    reais = [p for p in tr if len(p["amostras"]) >= minimo and tam[id(p)] >= 0.6 * maior]
    for p in reais:
        p["x"] = float(np.median([s[1] for s in p["amostras"]]))
        p["tam"] = tam[id(p)]
        cores = [s[5] for s in p["amostras"] if len(s) > 5 and s[5] is not None]
        p["cor"] = [float(v) for v in np.median(cores, 0)] if cores else None
    return sorted(reais, key=lambda p: p["x"])


def _nota_boca(pessoas: list[dict], envelope, grade, a: float) -> np.ndarray:
    """[pessoa, ponto da grade]: maxilar acompanhando a voz, sorriso descontado
    (NaN onde o rosto não deu lábios)."""
    nota = []
    for p in pessoas:
        am = [(t, ab, sr) for t, _, _, ab, sr, *_ in p["amostras"] if ab is not None]
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
    # FALA = maxilar ACOMPANHANDO a voz (correlação com o envelope × amplitude),
    # sorriso descontado. A versão anterior media o desvio do maxilar contra o
    # PRÓPRIO desvio da pessoa na cena: quem passa a cena calada tem base baixa,
    # e qualquer reação dela virava nota alta — medido na live da Mentoria Mil
    # Milionários (2026-11): Paulo andando para a câmera falando, e a faixa pulou
    # para a Júlia, que só reagia ao fundo.
    def fala(i, s_):
        am = [(x[0], x[3], x[4] or 0.0) for x in pes[i]["amostras"]
              if x[3] is not None and abs(x[0] - s_) <= 1.0]
        if len(am) < 6:
            return None
        aa = np.array([x[1] for x in am])
        ee = np.array([envelope(x[0] - 0.05, x[0] + 0.05) for x in am])
        if aa.std() < 1e-4 or ee.std() < 1e-9:
            return 0.0
        r = float(np.corrcoef(aa, ee)[0, 1])
        return max(0.0, r) * float(aa.std()) * max(0.0, 1.0 - 1.5 * float(np.mean([x[2] for x in am])))

    cur, bruto = ok[0] if ok else 0, []
    for k, s_ in enumerate(grade):
        if en[k] >= lim:
            z = {i: v for i in ok if (v := fala(i, s_)) is not None}
            melhor = max(z, key=z.get) if z else None
            if melhor is not None and z[melhor] >= FALA_MIN:
                # quem já fala só perde a faixa para uma boca CLARAMENTE mais
                # ligada à voz — empate fica com quem está
                if cur in z and cur != melhor and z[melhor] < 1.5 * z[cur]:
                    melhor = cur
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
        elif r in (0, len(runs) - 1):
            # na BORDA da janela a correlação de ±1s fica truncada (metade dela
            # é silêncio fora do trecho) e a troca é quase sempre ruído: medido
            # no "pneu do Gol", 1,1s finais na Júlia com o Paulo fechando a frase
            curto = runs[r][2] - runs[r][1] < 2 * precisa + 1
        if curto and len(runs) > 1:
            runs[r][0] = runs[r - 1][0] if r > 0 else runs[r + 1][0]
    out = [0] * len(bruto)
    for pessoa, i0, i1 in runs:
        out[i0:i1] = [pessoa] * (i1 - i0)
    return [(float(s_), int(x)) for s_, x in zip(grade, out)]


RASTRO_FOLGA = 0.6     # s — rosto que some mais que isto começa rastro novo
RASTRO_VEL = 300.0     # px/s — quanto um rosto pode andar no buraco entre detecções


def _rastros(por_t: dict) -> list[list]:
    """Rostos ligados quadro a quadro pela POSIÇÃO: cada rosto segue o rastro vivo
    mais perto (dois rostos do mesmo quadro nunca no mesmo rastro). Um rastro é
    UM rosto contínuo — a mesma pessoa do começo ao fim, mesmo que a roupa mude
    de cor com a luz. O limite cresce com o buraco: na panorâmica do "De 0 a
    10" a Camila anda ~35px por quadro de 0,1s e some por até 0,4s."""
    tr: list[dict] = []
    for t in sorted(por_t):
        fs = por_t[t]
        vivos = [k for k, p in enumerate(tr) if 0 < t - p["ult"] <= RASTRO_FOLGA]
        pares = sorted((abs(tr[k]["x"] - f[1]), k, n) for k in vivos for n, f in enumerate(fs))
        usados_t, usados_f = set(), set()
        for d, k, n in pares:
            p, f = tr[k], fs[n]
            lim = max(40.0, 0.6 * f[3]) + RASTRO_VEL * max(0.0, t - p["ult"] - 0.1)
            # tamanho muito diferente = outro rosto passando perto (frente/fundo)
            if k in usados_t or n in usados_f or d > lim or not (0.6 <= f[3] / p["w"] <= 1.65):
                continue
            usados_t.add(k)
            usados_f.add(n)
            p.update(x=f[1], w=f[3], ult=t)
            p["fs"].append(f)
        for n, f in enumerate(fs):
            if n not in usados_f:
                tr.append({"x": f[1], "w": f[3], "ult": t, "fs": [f]})
    return [p["fs"] for p in tr]


def _nomes_rastros(rs: list[list], gente: list[dict], cor_max: float) -> dict[int, int]:
    """Rastro → pessoa do elenco (índice), escolhidos JUNTOS: a combinação de
    menor custo somado, com custo de cada rastro = distância MEDIANA da cor do
    tronco (`elenco.distancia`) × √(amostras) e "ninguém" valendo `cor_max`;
    dois rastros que aparecem juntos (≥3 quadros e ≥40% do menor) nunca ganham
    o mesmo nome.

    Por que junto e não "o mais parecido primeiro": no anúncio "De 22 mil por
    12x de R$ 297" (2026-11) a Camila está atrás da Júlia e o tronco abaixo do
    rosto dela É a blusa creme da Júlia — os dois rostos davam "Júlia" (5 e 4).
    Um a um, a Camila levava o nome e a Júlia ficava sem ninguém; juntos,
    Camila+Júlia (19+4) custa menos que Júlia+ninguém (5+45). Por que
    √(amostras): o close de 14s não pode perder o nome para um rosto de 3
    quadros mais parecido, mas os 2,4s da Júlia passando ao lado da Camila (4
    pedaços) têm de pesar contra os 20s em que a Camila, sozinha e clareada
    pela luz, empata com a Júlia. Rastro de menos de 5 amostras escolhe depois,
    com o que sobrou."""
    import itertools  # noqa: PLC0415
    from . import elenco as EL  # noqa: PLC0415
    if not rs:
        return {}
    custo = []
    for fs in rs:
        D = np.array([[EL.distancia(f[6], p["_cor"]) for p in gente] for f in fs])
        custo.append(np.median(D, 0))
    ts = [{f[0] for f in fs} for fs in rs]
    juntos = {(i, j) for i in range(len(rs)) for j in range(len(rs)) if i != j
              and len(ts[i] & ts[j]) >= max(3, 0.4 * min(len(ts[i]), len(ts[j])))}
    longos = [i for i, fs in enumerate(rs) if len(fs) >= 5]
    dono: dict[int, int] = {}

    def opcoes(i):
        return [q for q in range(len(gente)) if custo[i][q] <= cor_max] + [-1]

    def preco(i, q):
        return (cor_max if q < 0 else float(custo[i][q])) * np.sqrt(len(rs[i]))

    # componentes de rastros que se cruzam: cada uma resolvida por inteiro
    vistos: set = set()
    for i in longos:
        if i in vistos:
            continue
        comp, pilha = [], [i]
        while pilha:
            k = pilha.pop()
            if k in vistos:
                continue
            vistos.add(k)
            comp.append(k)
            pilha += [j for j in longos if (k, j) in juntos and j not in vistos]
        if len(comp) <= 8:
            melhor, escolha = np.inf, None
            for qs in itertools.product(*[opcoes(k) for k in comp]):
                if any(qa >= 0 and qa == qb and (ka, kb) in juntos
                       for (ka, qa), (kb, qb) in itertools.combinations(zip(comp, qs), 2)):
                    continue
                tot = sum(preco(k, q) for k, q in zip(comp, qs))
                if tot < melhor:
                    melhor, escolha = tot, qs
            for k, q in zip(comp, escolha):
                if q >= 0:
                    dono[k] = q
        else:
            # cena com muitos pedaços (raro): o mais parecido primeiro
            for c_, k, q in sorted((float(custo[k][q]), k, q) for k in comp for q in opcoes(k) if q >= 0):
                if k not in dono and not any(dono.get(j) == q for j in comp if (k, j) in juntos):
                    dono[k] = q
    for i in sorted((i for i in range(len(rs)) if len(rs[i]) < 5), key=lambda i: -len(rs[i])):
        livres = [q for q in opcoes(i) if q >= 0 and not any(dono.get(j) == q for j in dono if (i, j) in juntos)]
        if livres:
            dono[i] = min(livres, key=lambda q: custo[i][q])
    return dono


def _pessoas_elenco(rostos: list, c0: float, c1: float, el: dict) -> dict[str, dict]:
    """Cada pessoa do elenco como UM rastro, pela cor da roupa — decidida por
    RASTRO de rosto contínuo (`_rastros`), não quadro a quadro.

    Por que não quadro a quadro (a versão anterior, que existia porque o
    rastreio por posição parte a pessoa em pedaços quando a câmera da live se
    move — no "Você é endividado" a Camila virou 3 rastros): a cor do tronco
    muda dentro do mesmo plano e cada quadro decidia sozinho. Medido na live da
    Mentoria Mil Milionários (2026-11):
    - "De 0 a 10": a panorâmica leva a Camila (vestido oliva) para a luz, o L
      do tronco sobe de 95 para 133 e ela fica MAIS PERTO da cor da Júlia
      (creme) que da própria — sozinha no quadro virava "Júlia", e a faixa
      seguia a Júlia saindo pela esquerda enquanto a Camila falava;
    - "Doar é hábito": o Paulo levanta a mão na frente da camisa (L 33 → 64) e,
      no plano aberto, a Camila sentada na sombra (L 48) fica mais "azul-
      marinho" que ele — os dois trocavam de nome e a faixa ia para ela.
    Num rastro a identidade não muda, e os nomes saem juntos (`_nomes_rastros`):
    a Júlia, inconfundível ao lado, fica com "Júlia" — e a Camila, mesmo clara,
    só pode ser a Camila. Os pedaços de uma pessoa partida pela câmera em
    movimento não aparecem juntos, então cada um ganha o nome pela própria
    cor, como antes. Conferido a olho em 438 rastros da live (37.932 rostos):
    nome certo em 91,8% dos rostos quadro a quadro, 98,2% por rastro."""
    from . import elenco as EL  # noqa: PLC0415
    por_t: dict = {}
    for r in rostos:
        if c0 <= r[0] < c1 and len(r) > 6 and r[6] is not None:
            por_t.setdefault(r[0], []).append(r)
    rs = _rastros(por_t)
    gente = el["pessoas"]
    am: dict[str, list] = {}
    for i, q in _nomes_rastros(rs, gente, EL.COR_MAX).items():
        for f in rs[i]:
            am.setdefault(gente[q]["nome"], []).append((f[0], f[1], f[3], f[4], f[5], f[6]))
    return {n: {"x": float(np.median([q[1] for q in v])), "tam": float(np.median([q[2] for q in v])),
                "amostras": sorted(v), "nome": n}
            for n, v in am.items() if len(v) >= 3}


def _trechos_elenco(nomeados: dict[str, dict], video: Path, a: float, c0: float, c1: float,
                    el: dict, faixa) -> list[dict]:
    """Os trechos de uma cena guiados pelo elenco: a cada passo, quem fala pela
    voz; pausa e voz incerta seguem com quem falava; o começo da cena antes da
    primeira voz fica com quem fala primeiro; troca de menos de 1s é absorvida."""
    from . import elenco as EL  # noqa: PLC0415
    grade = list(np.arange(c0, c1, PASSO))
    if not grade:
        return []
    nomes = EL.quem_fala(video, a, c0, c1, el, PASSO)
    tempos = {n: np.array([q[0] for q in p["amostras"]]) for n, p in nomeados.items()}

    def visivel(n, t, folga=0.9):
        tt = tempos.get(n)
        return tt is not None and len(tt) and float(np.min(np.abs(tt - t))) <= folga

    def quem_aparece(t):
        vis = [n for n in nomeados if visivel(n, t)]
        return max(vis, key=lambda n: len(nomeados[n]["amostras"])) if vis else None

    primeiro = next((n for n in nomes if n in nomeados), None) \
        or max(nomeados, key=lambda n: len(nomeados[n]["amostras"]))
    cur, serie = primeiro, []
    for k, t in enumerate(grade):
        n = nomes[k] if k < len(nomes) else None
        if n in nomeados and visivel(n, t):
            cur = n
        elif not visivel(cur, t, 2.0):
            # quem fala NÃO aparece nesta cena (a câmera da live está em outra
            # pessoa): a faixa fica em quem está visível, nunca num lugar vazio.
            # Medido no "Rico ama fazer": Paulo falando fora do quadro e a
            # faixa num ponto onde não havia ninguém.
            cur = quem_aparece(t) or cur
        serie.append(cur)
    # troca curta (< 1s) volta para o vizinho: pisca-pisca não é corte
    runs, k = [], 0
    while k < len(serie):
        j = k
        while j < len(serie) and serie[j] == serie[k]:
            j += 1
        runs.append([serie[k], k, j])
        k = j
    for r in range(len(runs)):
        if runs[r][2] - runs[r][1] < 2 and len(runs) > 1:
            runs[r][0] = runs[r - 1][0] if r > 0 else runs[r + 1][0]
    out = []
    for nome, i0, i1 in runs:
        t0, t1 = grade[i0], min(grade[i1 - 1] + PASSO, c1)
        if out and out[-1]["pessoa"] == nome and abs(out[-1]["ate"] - (a + t0)) < 1e-6:
            xs = _trajeto(nomeados[nome], out[-1]["de"] - a, t1, faixa, a)
            out[-1].update(ate=a + t1, xs=xs, x=xs[0][1])
            continue
        xs = _trajeto(nomeados[nome], t0, t1, faixa, a)
        out.append({"de": a + t0, "ate": a + t1, "modo": "crop", "x": xs[0][1], "xs": xs, "pessoa": nome})
    if out:
        out[0]["de"], out[-1]["ate"] = a + c0, a + c1
    return out


def _falante_elenco(pes: list[dict], serie: list, video: Path, a: float, c0: float, c1: float,
                    el: dict, nomeados: dict[str, dict], base: int) -> list[tuple[float, int]]:
    """A série de quem fala refeita pela VOZ do elenco, apontando para o rastro
    da PESSOA (`nomeados`, índices a partir de `base` em `pes_f`). Onde a voz
    não decide fica o que a boca disse; pausa segue com quem falava; turno de
    um passo some (pisca-pisca)."""
    from . import elenco as EL  # noqa: PLC0415
    ordem = list(nomeados)
    nomes = EL.quem_fala(video, a, c0, c1, el, PASSO)
    out, ultimo = [], None
    for k, (t, i) in enumerate(serie):
        n = nomes[k] if k < len(nomes) else None
        if n in nomeados:
            ultimo = base + ordem.index(n)
            out.append((t, ultimo))
        elif n is None and ultimo is not None:
            out.append((t, ultimo))
        else:
            out.append((t, i))
    for k in range(1, len(out) - 1):
        if out[k][1] != out[k - 1][1] and out[k - 1][1] == out[k + 1][1]:
            out[k] = (out[k][0], out[k - 1][1])
    return out

def _layout_tela(video: Path, t: float, cx: float, cy: float, W: int, H: int,
                 fr: np.ndarray | None = None) -> dict | None:
    """Os dois retângulos de um compartilhamento de tela: a JANELA DA CÂMERA (o
    menor contorno que contém os rostos pequenos) e a TELA (o maior retângulo
    que não a cobre). Medido na live "Enriqueça": slide 1220×686 à esquerda,
    câmera 581×448 à direita, com borda verde nos dois. `fr` = o quadro já
    decodificado (senão busca o quadro em `t`)."""
    import cv2  # noqa: PLC0415
    if fr is None:
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


def _janela_camera(video: Path, t: float, cx: float, cy: float, tela: list, W: int, H: int) -> list | None:
    """A JANELA de vídeo inteira do compartilhamento de tela: o MAIOR retângulo
    com moldura que contém o rosto e não invade o slide. O `_layout_tela` fica
    com o MENOR contorno em volta do rosto — que às vezes é a janela, às vezes
    só o recorte da pessoa: no "100 mil" (2026-11) a dividida mostrava 357×358
    de uma janela de 583×446 e, quando a Júlia entrou, o recorte caiu no vão
    entre as duas."""
    import cv2  # noqa: PLC0415
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1",
                          "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], capture_output=True).stdout
    if len(raw) < W * H * 3:
        return None
    fr = np.frombuffer(raw[:W * H * 3], np.uint8).reshape(H, W, 3)
    e = cv2.dilate(cv2.Canny(cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY), 40, 120), np.ones((3, 3), np.uint8))
    cs, _ = cv2.findContours(e, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    tx, ty, tw, th = tela
    melhor = None
    for c in cs:
        x, y, w, h = cv2.boundingRect(c)
        if not (0.03 * W * H <= w * h <= 0.35 * W * H) or not (x < cx < x + w and y < cy < y + h):
            continue
        ap = cv2.approxPolyDP(c, 0.02 * cv2.arcLength(c, True), True)
        # a moldura da janela tem canto arredondado e funde com o que está
        # dentro: medido 10–11 vértices e preenchimento 0,75–0,88 — exigir
        # 4 vértices (como o slide) nunca a achava
        if len(ap) > 12 or cv2.contourArea(c) / (w * h) < 0.7 or not (1.0 <= w / h <= 2.0):
            continue
        if x < tx + tw and tx < x + w and y < ty + th and ty < y + h:   # invade o slide
            continue
        if melhor is None or w * h > melhor[2] * melhor[3]:
            melhor = (x, y, w, h)
    return [melhor[0] + 6, melhor[1] + 6, melhor[2] - 12, melhor[3] - 12] if melhor else None


def _fundo_da_tela(Q: np.ndarray, lay: dict, ref: list[int], W: int, H: int) -> np.ndarray:
    """Diferença média (0–255) de cada miniatura 64×36 para o FUNDO do
    compartilhamento de tela — o que fica fora do slide e da janela da câmera.

    O fundo é a arte fixa da transmissão (na live da Mentoria Mil Milionários,
    o redemoinho laranja e o selo do programa): dentro do compartilhamento ele
    fica a 0–2 do quadro de referência, por mais que o slide troque e a janela
    da câmera mude de plano; fora dele, num plano de câmera, a 60–100. Medido
    em 9 cortes com tela (2026-11): os valores do meio (10–57) são só os
    quadros da própria fusão de entrada ou saída."""
    m = np.ones((36, 64), bool)
    for x, y, w, h in (lay["tela"], lay["cam"]):
        # a moldura e um pixel de folga ficam fora: a borda verde muda de tom
        m[max(0, int((y - 12) * 36 / H) - 1):int(np.ceil((y + h + 12) * 36 / H)) + 1,
          max(0, int((x - 12) * 64 / W) - 1):int(np.ceil((x + w + 12) * 64 / W)) + 1] = False
    if m.mean() < 0.15:
        return np.full(len(Q), np.inf)
    R = np.median(Q[ref], 0)
    return np.abs(Q - R)[:, m].mean((1, 2))


def _telas_divididas(trechos: list[dict], rostos: list, a: float, dur: float,
                     video: Path, W: int, H: int, cenas: list[float] | None = None) -> list[dict]:
    """Compartilhamento de tela detectado PELO LAYOUT, segundo a segundo: um
    retângulo grande (o slide) ao lado de uma janela que contém os rostos.
    Esses trechos viram "dividida" — slide inteiro em cima, janela de vídeo
    inteira embaixo, sem seguir rosto (pedido do usuário, 2026-11).

    Existe porque as duas portas antigas falhavam juntas na live da Mentoria Mil
    Milionários: a entrada do slide é uma transição ANIMADA (nenhum quadro
    passa de CENA_DIF, então não há corte de cena) e o slide ocupava 70% do
    corte — o "rosto pequeno" do `_vazios_viram_fit` é relativo aos rostos do
    próprio corte, e ali o pequeno era a maioria."""
    if not rostos:
        return trechos
    # um quadro por segundo (0,5s, 1,5s, …) numa decodificação só: uma busca
    # por quadro custava 0,28s × 3 rostos × cada segundo — 37 dos 45s do plano
    # de um corte de 33s (medido, 2026-11). O `fps=1` a partir de `a` entrega o
    # quadro de a + k + 0,483s (conferido quadro a quadro contra a busca);
    # começar em a + 0,5 dava a + k + 0,983.
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-ss", f"{a:.3f}", "-t", f"{dur:.3f}",
                          "-i", str(video), "-vf", "fps=1", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                         stdout=subprocess.PIPE)
    marcas = []
    for s in np.arange(0.5, dur, 1.0):
        buf = p.stdout.read(W * H * 3)
        fr = np.frombuffer(buf, np.uint8).reshape(H, W, 3) if len(buf) == W * H * 3 else None
        fs = [r for r in rostos if abs(r[0] - s) < 0.3]
        lay = None
        for f in (fs[:3] if fr is not None else []):
            lay = _layout_tela(video, a + s, f[1], f[2], W, H, fr)
            if lay:
                tw, th = lay["tela"][2:]
                cw_, ch = lay["cam"][2:]
                if tw * th < 0.2 * W * H or cw_ * ch > 0.3 * W * H:
                    lay = None
                else:
                    break
        marcas.append((float(s), lay))
    p.stdout.close()
    p.wait()
    faixas, k = [], 0
    while k < len(marcas):
        if marcas[k][1] is None:
            k += 1
            continue
        j = k
        while j < len(marcas) and marcas[j][1] is not None:
            j += 1
        if j - k >= 2:
            # o layout mais comum da faixa (a janela da câmera às vezes pega um contorno maior)
            lays = [m[1] for m in marcas[k:j]]
            # a janela da câmera às vezes sai como um contorno MENOR (o rosto, um
            # detalhe dentro dela); a janela de verdade é a maior que apareceu
            cam = max(lays, key=lambda L: L["cam"][2] * L["cam"][3])["cam"]
            tela = max(lays, key=lambda L: L["tela"][2] * L["tela"][3])["tela"]
            # a janela inteira: o maior retângulo com moldura em volta dos rostos,
            # procurado em vários instantes da faixa (pessoas entram e saem)
            janelas = []
            for s_, _ in marcas[k:j][::max(1, (j - k) // 6)]:
                for f in [r for r in rostos if abs(r[0] - s_) < 0.3][:2]:
                    jn = _janela_camera(video, a + s_, f[1], f[2], tela, W, H)
                    if jn:
                        janelas.append(jn)
            if janelas:
                jn = max(janelas, key=lambda r: r[2] * r[3])
                if jn[2] * jn[3] > cam[2] * cam[3]:
                    cam = jn
            f0 = a + max(0.0, marcas[k][0] - 0.5)
            f1 = a + min(dur, marcas[j - 1][0] + 0.5)
            faixas.append((f0, f1, {"tela": tela, "cam": cam}, [m[0] for m in marcas[k:j]]))
        k = j
    if not faixas:
        return trechos
    faixas = _estender_telas(faixas, video, a, dur, W, H, cenas or [])
    # sobra de menos de 0,25s entre a tela e o trecho vizinho vira tela: o
    # corte abaixo descarta pedaço curto, e sem isso ficava um buraco no plano
    bordas = sorted({t["de"] for t in trechos} | {t["ate"] for t in trechos})
    ajust = []
    for f0, f1, lay in faixas:
        f0 = next((x for x in bordas if f0 - 0.25 < x <= f0), f0)
        f1 = next((x for x in reversed(bordas) if f1 <= x < f1 + 0.25), f1)
        ajust.append((f0, f1, lay))
    faixas = ajust
    out = []
    for tr in trechos:
        pedacos = [(tr["de"], tr["ate"])]
        for f0, f1, _ in faixas:
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
        out += [{**tr, "de": p0, "ate": p1} for p0, p1 in pedacos if p1 - p0 > 0.25]
    out += [{"de": f0, "ate": f1, "modo": "dividida", **lay} for f0, f1, lay in faixas]
    return sorted(out, key=lambda t: t["de"])


def _estender_telas(faixas: list, video: Path, a: float, dur: float, W: int, H: int,
                    cenas: list[float]) -> list[tuple[float, float, dict]]:
    """Cada compartilhamento de tela achado pelo layout (que depende de ACHAR
    ROSTO na janelinha, a cada segundo) estendido pelo FUNDO (`_fundo_da_tela`)
    até onde a tela de fato vai, quadro a quadro, com a borda no meio da fusão.

    Medido na live da Mentoria Mil Milionários (2026-11): a janela da câmera
    mostra o palco aberto, os rostos ficam pequenos demais para o detector e o
    layout "some" — no "De 0 a 10, você sabe fazer dinheiro?" 0–3s e 9–15s
    do compartilhamento saíram como faixa 9:16 cortando o slide; no "Ganha
    mais, gasta mais" a tela entra aos 29,4s e a dividida só começava aos 31s;
    no "O que é liberdade financeira" um buraco de 3s no meio da tela."""
    fps = 30
    Q = _miniaturas(video, a, a + dur, fps).astype(np.float32)
    if len(Q) < fps:
        return [(f0, f1, lay) for f0, f1, lay, _ in faixas]
    dono = np.full(len(Q), -1)
    for n, (f0, f1, lay, sementes) in sorted(enumerate(faixas), key=lambda e: -(e[1][1] - e[1][0])):
        ref = [min(len(Q) - 1, int(round(s_ * fps))) for s_ in sementes]
        dif = _fundo_da_tela(Q, lay, ref, W, H)
        igual = dif < FUNDO_DIF
        # o fundo tem de bater nas próprias sementes; senão (fundo animado, outro
        # tipo de layout) fica a faixa achada pelo layout, como antes
        if igual[ref].mean() < 0.8:
            i0, i1 = int((f0 - a) * fps), int(np.ceil((f1 - a) * fps))
            dono[i0:i1][dono[i0:i1] < 0] = n
            continue
        # buraco de menos de 0,5s dentro da tela (o slide anima por cima da
        # moldura, um clarão) não interrompe a tela
        ix = np.where(igual)[0]
        for p_, q_ in zip(ix, ix[1:]):
            if 1 < q_ - p_ <= fps // 2:
                igual[p_:q_] = True
        dono[igual & (dono < 0)] = n
    out, k = [], 0
    while k < len(dono):
        j = k
        while j < len(dono) and dono[j] == dono[k]:
            j += 1
        if dono[k] >= 0 and j - k >= fps:
            t0 = 0.0 if k == 0 else k / fps
            t1 = dur if j >= len(dono) else j / fps
            # a borda cai no meio da fusão (o fundo só passa no limiar a ~1/8
            # dela) ou no corte seco: a cena mais perto, se houver uma a ≤0,5s
            t0 = min(cenas, key=lambda c: abs(c - t0)) if t0 > 0 and cenas and \
                min(abs(c - t0) for c in cenas) <= 0.5 else t0
            t1 = min(cenas, key=lambda c: abs(c - t1)) if t1 < dur and cenas and \
                min(abs(c - t1) for c in cenas) <= 0.5 else t1
            if t1 - t0 >= 0.5:
                out.append((a + round(t0, 3), a + round(t1, 3), faixas[dono[k]][2]))
        k = j
    return out


def _vazios_viram_fit(trechos: list[dict], rostos: list, a: float, dur: float,
                      video: Path | None = None, W: int = 1920, H: int = 1080,
                      cenas: list[float] | None = None) -> list[dict]:
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
            f0, f1 = k * PASSO, min(j * PASSO, dur)
            # com rosto valendo ±0,6s, a grade marca o vazio 0,6–1,1s DEPOIS de
            # ele começar e 0,1–0,6s ANTES de acabar: havendo troca de plano
            # nesse intervalo, a borda vai para ela (sem isso, até 1s do slide
            # numa faixa 9:16)
            ini = [c for c in (cenas or []) if f0 - 1.2 <= c <= f0 + 0.2]
            fim = [c for c in (cenas or []) if f1 - 0.2 <= c <= f1 + 0.7]
            f0 = ini[0] if ini and f0 > 0 else f0
            f1 = fim[-1] if fim and f1 < dur else f1
            if f1 - f0 >= 1.0:
                faixas.append((a + f0, a + f1))
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
        elif f1 - f0 <= 3.0 and any(tr["modo"] == "crop" and tr["ate"] > f0 and tr["de"] < f1
                                     for tr in trechos):
            # rosto sumiu POUCO tempo (virou de perfil, abaixou a cabeça): a
            # pessoa continua ali — mantém a faixa que a cena já dava a ela em
            # vez de abrir o quadro inteiro. Medido no "Preguiça de levantar do
            # sofá" (2026-11): o Paulo de perfil virou 1,3s de tela cheia bem
            # no gancho.
            out += [{**tr, "de": max(tr["de"], f0), "ate": min(tr["ate"], f1)}
                    for tr in trechos if tr["ate"] > f0 and tr["de"] < f1]
        elif len(peq) >= 5:
            # rostos PEQUENOS sem layout de tela = plano ABERTO do palco, não
            # janelinha de câmera: as pessoas estão lá, longe. Virar "fit" aqui
            # tirava a faixa de quem fala — medido no "Você não é rico, você é
            # endividado" (2026-11): Camila e Júlia num plano aberto depois de
            # um close viraram quadro inteiro por 6,5s. Devolve os trechos
            # originais (faixa no falante) desse intervalo.
            out += [{**tr, "de": max(tr["de"], f0), "ate": min(tr["ate"], f1)}
                    for tr in trechos if tr["ate"] > f0 and tr["de"] < f1]
        else:
            out.append({"de": f0, "ate": f1, "modo": "fit"})
    return sorted(out, key=lambda t: t["de"])


def _trajeto(p: dict, t0: float, t1: float, faixa, a: float) -> list[list[float]]:
    """O caminho da faixa atrás de UMA pessoa, [[t da fonte, x], …] a cada 0,25s:
    zona morta de SUAVE_ZONA px (gesto não move a câmera) e depois um filtro de
    ida e volta com constante SUAVE_TAU (desliza, sem atraso de fase). O render
    interpola entre os pontos — a faixa nunca salta dentro de um turno."""
    am = sorted((s[0], s[1]) for s in p["amostras"] if t0 - 1.0 <= s[0] <= t1 + 1.0)
    dt = 0.1
    grade = np.arange(t0, t1 + 1e-6, dt)
    if len(am) < 3 or len(grade) < 2:
        x = faixa(p["x"])
        return [[round(a + t0, 3), x], [round(a + t1, 3), x]]
    tt = np.array([x[0] for x in am])
    cx = np.array([x[1] for x in am])
    bruto = np.array([float(np.median(cx[np.abs(tt - s) <= 0.5])) if np.any(np.abs(tt - s) <= 0.5)
                      else float(np.interp(s, tt, cx)) for s in grade])
    alvo = np.array([faixa(v) for v in bruto], dtype=float)
    seg = alvo.copy()                       # zona morta
    for k in range(1, len(seg)):
        seg[k] = seg[k - 1] if abs(alvo[k] - seg[k - 1]) < SUAVE_ZONA else alvo[k]
    al = dt / (SUAVE_TAU + dt)              # ida e volta: sem atraso
    f = seg.copy()
    for k in range(1, len(f)):
        f[k] = f[k - 1] + al * (seg[k] - f[k - 1])
    for k in range(len(f) - 2, -1, -1):
        f[k] = f[k + 1] + al * (f[k] - f[k + 1])
    pts = [[round(a + float(s), 3), int(round(v))] for s, v in zip(grade[::3], f[::3])]
    if pts[-1][0] < round(a + t1, 3):
        pts.append([round(a + t1, 3), int(round(f[-1]))])
    return pts


def _simplificar(pts: list, tol: float = 2.0, teto: int = 40) -> list:
    """Tira do caminho os pontos que a reta entre os vizinhos já descreve (erro
    ≤ `tol` px) e, se ainda sobrar demais, espaça até `teto` pontos. Trecho
    longo num plano só (33s no "Você trabalha e o dinheiro nunca é seu") virava
    ~110 termos e o ffmpeg recusava o filtro inteiro ("Failed to configure
    input pad") — sete cortes não saíam."""
    if len(pts) <= 2:
        return pts

    def dp(i, j):
        (ta, xa), (tb, xb) = pts[i], pts[j]
        pior, k_pior = 0.0, None
        for k in range(i + 1, j):
            t, x = pts[k]
            lin = xa + (xb - xa) * ((t - ta) / (tb - ta) if tb > ta else 0)
            if abs(x - lin) > pior:
                pior, k_pior = abs(x - lin), k
        if k_pior is None or pior <= tol:
            return [i, j]
        return dp(i, k_pior)[:-1] + dp(k_pior, j)
    keep = dp(0, len(pts) - 1)
    out = [pts[k] for k in keep]
    while len(out) > teto:
        out = out[::2] + ([out[-1]] if len(out) % 2 == 0 else [])
    return out


def x_expr(xs: list, t0: float, t1: float | None = None) -> str:
    """A expressão de x do `crop` para um pedaço [t0, t1] da fonte (o pedaço
    passa por setpts=PTS-STARTPTS, então t do filtro = fonte − t0).

    Só entram os pontos do PRÓPRIO pedaço, numa SOMA de trechos (sem `if`
    aninhado). A primeira versão aninhava o caminho inteiro em cada pedaço: a
    versão "sem respiros" parte o corte em dezenas de pedaços, e o ffmpeg
    recusava a expressão ("Missing ')' or too many args") — o corte não saía."""
    pts = [(round(t - t0, 3), int(x)) for t, x in xs]
    pts = _simplificar(pts)
    if t1 is not None:
        fim = t1 - t0
        dentro = [k for k, (t, _) in enumerate(pts) if -0.5 <= t <= fim + 0.5]
        if dentro:
            k0, k1 = max(0, dentro[0] - 1), min(len(pts), dentro[-1] + 2)
            pts = pts[k0:k1]
        else:
            x = int(round(float(np.interp(fim / 2, [t for t, _ in pts], [x for _, x in pts]))))
            return str(x)
    if len({x for _, x in pts}) == 1:
        return str(pts[0][1])
    termos = [f"lt(t,{pts[0][0]})*{pts[0][1]}"]
    for (ta, xa), (tb, xb) in zip(pts, pts[1:]):
        if tb - ta < 1e-3:
            continue
        lerp = f"{xa}" if xa == xb else f"({xa}+({xb - xa})*(t-({ta}))/{round(tb - ta, 3)})"
        termos.append(f"gte(t,{ta})*lt(t,{tb})*{lerp}")
    termos.append(f"gte(t,{pts[-1][0]})*{pts[-1][1]}")
    return "+".join(termos)


def plano(video: Path, a: float, b: float) -> dict:
    """{"vertical": bool, "W", "H", "trechos": [{de, ate, modo, x}]} em tempo da
    FONTE. `modo`: "crop" (faixa com a borda esquerda em `x`) ou "fit"."""
    W, H = dimensoes(video)
    if W / H <= 9 / 16 + 0.02:
        return {"vertical": True, "W": W, "H": H, "trechos": [{"de": a, "ate": b, "modo": "inteiro"}]}
    import instalar  # noqa: PLC0415
    if not instalar.garantir("enquadramento"):
        raise RuntimeError("o enquadramento vertical não pôde ser instalado")

    from . import elenco as EL  # noqa: PLC0415
    el = EL.carregar(video)

    def calcular():
        med = _medir(video, a, b)
        cw = int(H * 9 / 16) // 2 * 2
        env = _envelope(video, a, b)
        cortes = _cenas(video, a, b, med["cenas"])
        cenas = cortes + [med["dur"]]
        diar = None   # só se alguma cena tiver gente que não cabe junta
        trechos = []
        for c0, c1 in zip(cenas, cenas[1:]):
            n = max(1, int((c1 - c0) * FPS))
            pes = _pessoas(med["rostos"], c0, c1, n)
            faixa = lambda cx: int(min(max(0, cx - cw / 2), W - cw))  # noqa: E731
            # COM ELENCO, toda cena com gente segue QUEM FALA pela voz, no rastro
            # da pessoa montado pela cor da roupa — inclusive cena de uma pessoa
            # só: o rastreio por posição partia o Paulo andando/de perfil em
            # pedaços curtos, o piso de amostras os descartava e a faixa ficava
            # num rosto que passou pelo quadro (medido no "19%": 112% fora).
            nomeados = _pessoas_elenco(med["rostos"], c0, c1, el) if el else {}
            if nomeados:
                trechos += _trechos_elenco(nomeados, video, a, c0, c1, el, faixa)
                continue
            if not pes:
                trechos.append({"de": a + c0, "ate": a + c1, "modo": "fit"})
            elif len(pes) == 1:
                xs = _trajeto(pes[0], c0, c1, faixa, a)
                trechos.append({"de": a + c0, "ate": a + c1, "modo": "crop", "x": xs[0][1], "xs": xs})
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
                if el:
                    nomeados = _pessoas_elenco(med["rostos"], c0, c1, el)
                    if nomeados:
                        base = len(pes_f)
                        pes_f = pes_f + list(nomeados.values())
                        serie = _falante_elenco(pes, serie, video, a, c0, c1, el, nomeados, base)
                # um trecho por TURNO (não por passo de 0,5s): dentro do turno a
                # câmera desliza atrás do rosto (`xs`); só a troca de falante é
                # corte seco. A versão anterior emitia um x fixo a cada passo com
                # histerese de 70px — cada degrau virava um tranco na imagem.
                k = 0
                while k < len(serie):
                    j = k
                    while j < len(serie) and serie[j][1] == serie[k][1]:
                        j += 1
                    i = serie[k][1]
                    t0, t1 = serie[k][0], min(serie[j - 1][0] + PASSO, c1)
                    p = pes_f[i]
                    if p.get("fora"):
                        x = faixa(p["x"])
                        trechos.append({"de": a + t0, "ate": a + t1, "modo": "crop", "x": x, "pessoa": i})
                    else:
                        xs = _trajeto(p, t0, t1, faixa, a)
                        trechos.append({"de": a + t0, "ate": a + t1, "modo": "crop", "x": xs[0][1],
                                        "xs": xs, "pessoa": i})
                    k = j
        trechos = _vazios_viram_fit(trechos, med["rostos"], a, med["dur"], video, W, H, cortes)
        trechos = _telas_divididas(trechos, med["rostos"], a, med["dur"], video, W, H, cortes)
        if trechos:
            trechos[0]["de"], trechos[-1]["ate"] = a, b
        return {"vertical": False, "W": W, "H": H, "cw": cw, "trechos": trechos}

    import hashlib  # noqa: PLC0415
    chave_el = hashlib.sha1(EL.caminho(video).read_bytes()).hexdigest()[:10] if el else ""
    return derivado("enquadramento", [video], {"a": round(a, 3), "b": round(b, 3), "versao": 40,
                                               "elenco": chave_el},
                    "1", calcular)


def filtro(trecho: dict, W: int, H: int, saida=(1080, 1920), rot: str = "0",
           t0: float | None = None, t1: float | None = None) -> str:
    """O filtro de vídeo de um trecho: faixa recortada, ou o quadro inteiro
    sobre o mesmo quadro ampliado e desfocado. `t0` = início do PEDAÇO na
    fonte; com ele, a faixa de um trecho com `xs` desliza em vez de ficar fixa."""
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
        x = trecho["x"]
        if trecho.get("xs") and t0 is not None:
            x = f"'{x_expr(trecho['xs'], t0, t1)}'"
        return f"crop={cw}:{H}:{x}:0,scale={ow}:{oh}:flags=lanczos"
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

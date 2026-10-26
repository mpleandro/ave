"""Quem fala quando — diarização pela VOZ, sem serviço externo.

O transcrito não diz quem é quem, e decidir pela boca quadro a quadro falha
justamente com quem mais fala num podcast: de perfil, de cabeça baixa lendo, o
rosto perde os lábios em 2 de cada 3 quadros (medido). A voz não tem esse
problema. Aqui:

1. voz no ar: energia do áudio em quadros de 100ms;
2. impressão da voz: WeSpeaker ResNet34 (treinado no VoxCeleb, ONNX publicado
   pelos autores), rodando pelo `cv2.dnn` do próprio OpenCV — sem dependência
   nova. Entra fbank de 80 bandas no padrão Kaldi (25ms/10ms, pré-ênfase 0,97,
   Hamming, média removida), sai um vetor de 256;
3. agrupamento em N vozes (N = pessoas em cena): k-means esférico começando
   pelos vetores mais distantes;
4. suavização: mediana de 5 janelas, turno mínimo de 1s.

Medido no podcast de teste: as duas vozes ficaram a 0,20 de similaridade (vozes
iguais dariam ~1) e os turnos bateram com a conversa. 60s de áudio em 2s.

Qual voz é qual ROSTO quem decide é `enquadramento`, somando a boca de cada
rosto ao longo de todos os turnos de cada voz.
"""
from __future__ import annotations

import subprocess
from functools import lru_cache
from pathlib import Path

import numpy as np

MODELO = Path.home() / ".avelin" / "modelos" / "wespeaker_resnet34.onnx"
JANELA, PASSO_J = 1.5, 0.5


def audio(video: Path, a: float, b: float) -> np.ndarray:
    au = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{a:.3f}", "-t", f"{b - a:.3f}",
                         "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                        capture_output=True).stdout
    return np.frombuffer(au, np.int16).astype(np.float32)   # escala int16, como o Kaldi


@lru_cache(maxsize=1)
def _bancos(n=80, nfft=512, sr=16000, lo=20.0, hi=8000.0) -> np.ndarray:
    m = lambda f: 1127 * np.log(1 + f / 700)  # noqa: E731
    pts = np.linspace(m(lo), m(hi), n + 2)
    mf = m(np.fft.rfftfreq(nfft, 1 / sr))
    fb = np.zeros((n, len(mf)))
    for i in range(n):
        l, c, r = pts[i], pts[i + 1], pts[i + 2]
        fb[i] = np.clip(np.minimum((mf - l) / (c - l), (r - mf) / (r - c)), 0, None)
    return fb


def fbank(sig: np.ndarray) -> np.ndarray:
    n = 1 + (len(sig) - 400) // 160
    if n <= 0:
        return np.zeros((0, 80), np.float32)
    idx = np.arange(400)[None, :] + 160 * np.arange(n)[:, None]
    f = sig[idx].astype(np.float64)
    f -= f.mean(1, keepdims=True)
    f = np.concatenate([f[:, :1], f[:, 1:] - 0.97 * f[:, :-1]], 1) * np.hamming(400)
    p = np.abs(np.fft.rfft(f, 512)) ** 2
    return np.log(np.maximum(p @ _bancos().T, 1.19e-7)).astype(np.float32)


@lru_cache(maxsize=1)
def _rede():
    import cv2  # noqa: PLC0415
    return cv2.dnn.readNetFromONNX(str(MODELO))


def impressao(sig: np.ndarray) -> np.ndarray:
    F = fbank(sig)
    F -= F.mean(0)
    net = _rede()
    net.setInput(F[None])
    e = net.forward()[0]
    return e / (np.linalg.norm(e) + 1e-9)


def diarizar(x: np.ndarray, n: int) -> list[tuple[float, int]]:
    """[(centro da janela em s, voz 0..n-1)] nas janelas com voz."""
    q = np.array([np.sqrt((x[i:i + 1600] ** 2).mean() + 1e-9) for i in range(0, max(0, len(x) - 1600), 1600)])
    if not len(q):
        return []
    db = 20 * np.log10(q / 32768)
    voz = db > np.percentile(db, 30)
    T, E = [], []
    dur = len(x) / 16000
    for s in np.arange(0, max(0.0, dur - JANELA), PASSO_J):
        i0, i1 = int(s * 10), int((s + JANELA) * 10)
        if voz[i0:i1].mean() < 0.6:
            continue
        T.append(s + JANELA / 2)
        E.append(impressao(x[int(s * 16000):int((s + JANELA) * 16000)]))
    if len(E) < n:
        return [(t, 0) for t in T]
    E = np.array(E)
    # começa pelos mais distantes entre si (farthest-point), depois k-means esférico
    C = [E[int(np.argmin(E @ E.mean(0)))]]
    while len(C) < n:
        C.append(E[int(np.argmin(np.max(E @ np.array(C).T, 1)))])
    C = np.array(C)
    for _ in range(25):
        lab = np.argmax(E @ C.T, 1)
        C = np.array([E[lab == k].mean(0) if (lab == k).any() else C[k] for k in range(n)])
        C /= np.linalg.norm(C, axis=1, keepdims=True)
    lab = np.array([np.bincount(lab[max(0, k - 2):k + 3], minlength=n).argmax() for k in range(len(lab))])
    return list(zip(T, (int(v) for v in lab)))

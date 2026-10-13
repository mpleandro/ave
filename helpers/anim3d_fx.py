#!/usr/bin/env python3
"""Efeitos de pixel da "Animação em 3D" — gerados do PRÓPRIO corte, quadro a quadro.

    uv run python helpers/anim3d_fx.py <edit> --plano anim3d_plano.json
    uv run python helpers/anim3d_fx.py <edit> --fx maos --start 25.4 --end 28.2 -o maos.mp4

O que a referência do estilo faz e nenhum CSS faz: o fundo vira mapa de
profundidade, a pessoa é recortada com contorno de luz, o quadro vira nuvem de
pontos que gira, o vídeo vira dois painéis (fundo e você) separados no espaço, as
mãos ganham esqueleto. Cada um destes é um efeito sobre os PIXELS do corte e
precisa de visão computacional — por isso nasce aqui, em Python, e não na
composição.

Cinco efeitos (`--fx`):

  profundidade  Depth Anything V2 → tinta/papel por distância + isolinhas na cor
                de destaque + régua PERTO/LONGE. Entra varrendo de cima.
  recorte       MediaPipe selfie segmenter → fundo escurecido e desfocado, você
                nítido com contorno de luz e a etiqueta "CAMADA 01 · VOCÊ".
  nuvem         profundidade → nuvem de pontos com a cor do quadro, câmera
                orbitando e voltando.
  painel        recorte → fundo e pessoa em DOIS painéis que se separam em
                profundidade enquanto a câmera gira; piso em grade.
  maos          MediaPipe HandLandmarker + FaceLandmarker → 21 pontos por mão
                com ossos, cantoneiras no rosto e etiquetas com a confiança.

TRÊS DECISÕES, cada uma com o defeito que evita:

  1. O primeiro e o último quadro de toda janela são o quadro ORIGINAL (o efeito
     entra e sai por rampa). O efeito é gravado DENTRO de uma cópia do corte
     (`--plano` → `preview_fx.mp4`), não por cima dele na composição: a câmera
     dinâmica (zoom nos cortes, aproximação) e a legenda continuam passando por
     cima sem salto na emenda. Um overlay solto ficaria fora da câmera e a
     janela "pularia" de enquadramento no primeiro quadro.
  2. A profundidade é normalizada pelos percentis da JANELA inteira, não por
     quadro: normalizar quadro a quadro faz o mapa pulsar de brilho a cada
     gesto, porque a mão que entra muda o "mais perto" do quadro.
  3. Paleta da MARCA (`~/.avelin/brand.json`): tinta, papel e a cor de destaque.
     Nada de gradiente frio — o kit Ignis o proíbe fora da linha NOVA, e uma
     marca sem kit herda a mesma regra por padrão sensato.

O plano (`--plano`) é uma lista de janelas no relógio do CORTE:
    {"base": "preview.mp4", "saida": "preview_fx.mp4",
     "janelas": [{"fx": "profundidade", "start": 9.0, "end": 11.6, "rotulo": "..."}]}
"""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

os.environ.setdefault("GLOG_minloglevel", "2")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

MODELOS = Path.home() / ".avelin" / "modelos" / "mediapipe"
FPS = 30
# Margem lateral dos rótulos: a câmera dinâmica da Fase 2 (zoom nos cortes,
# aproximação) aproxima até ~1,2× e corta ~100 px de cada lado. Rótulo a 60 px
# da borda saía decepado ("ROFUNDIDADE") — medido no primeiro render.
MARGEM = 190


# ---------------------------------------------------------------- marca/fontes
def _hex(h: str) -> np.ndarray:
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.float32)


def marca() -> dict:
    try:
        b = json.loads((Path.home() / ".avelin" / "brand.json").read_text())
    except (OSError, json.JSONDecodeError):
        b = {}
    return {
        "accent": _hex(b.get("accent") or "#FF522D"),
        "tinta": _hex("#050505"),
        "carvao": _hex(((b.get("fogo") or {}).get("char")) or "#2A120A"),
        "papel": _hex("#F3EDE8"),
        "nucleo": _hex(((b.get("fogo") or {}).get("core")) or "#FFF7DA"),
    }


def fonte(familia: str, peso: int, tam: int) -> ImageFont.FreeTypeFont:
    try:
        idx = json.loads((Path.home() / ".avelin" / "localfonts.json").read_text())
        fam = (idx.get("families") or idx).get(familia) or {}
        faces = [f for f in fam.get("faces", []) if not f.get("i")]
        if faces:
            f = min(faces, key=lambda f: abs(f["w"] - peso))
            return ImageFont.truetype(f["p"], tam)
    except Exception:
        pass
    return ImageFont.load_default(size=tam)


# ---------------------------------------------------------------- vídeo
def dims(video: Path) -> tuple[int, int]:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                          "-show_entries", "stream=width,height", "-of", "csv=p=0",
                          str(video)], capture_output=True, text=True).stdout.strip()
    w, h = out.split(",")[:2]
    return int(w), int(h)


def ler(video: Path, start: float, end: float) -> list[np.ndarray]:
    w, h = dims(video)
    n = round((end - start) * FPS)
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-i", str(video),
         "-frames:v", str(n), "-vf", f"fps={FPS}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True).stdout
    q = np.frombuffer(raw, np.uint8)
    k = len(q) // (w * h * 3)
    return [q[i * w * h * 3:(i + 1) * w * h * 3].reshape(h, w, 3) for i in range(k)]


def gravar(frames: list[np.ndarray], out: Path) -> None:
    h, w = frames[0].shape[:2]
    p = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{w}x{h}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-crf", "14",
         "-preset", "medium", "-pix_fmt", "yuv420p", "-color_primaries", "bt709",
         "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "tv", str(out)],
        stdin=subprocess.PIPE)
    for f in frames:
        p.stdin.write(np.ascontiguousarray(f, np.uint8).tobytes())
    p.stdin.close()
    p.wait()


# ---------------------------------------------------------------- tempo
def rampa(i: int, n: int, ent: float = 0.4, sai: float = 0.35) -> float:
    """0 no primeiro e no último quadro, 1 no miolo — com easing suave."""
    t = i / FPS
    dur = n / FPS
    a = min(1.0, t / ent) if ent > 0 else 1.0
    b = min(1.0, (dur - t - 1 / FPS) / sai) if sai > 0 else 1.0
    x = max(0.0, min(a, b))
    return x * x * (3 - 2 * x)


def ease(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return 0.5 - 0.5 * math.cos(math.pi * x)


# ---------------------------------------------------------------- visão
_DEPTH = None


def profundidades(frames: list[np.ndarray]) -> list[np.ndarray]:
    """1 = perto, 0 = longe, normalizado pela JANELA (ver decisão 2)."""
    global _DEPTH
    if _DEPTH is None:
        import torch
        from transformers import pipeline
        dev = "mps" if torch.backends.mps.is_available() else "cpu"
        _DEPTH = pipeline("depth-estimation",
                          model="depth-anything/Depth-Anything-V2-Small-hf", device=dev)
    crus = []
    for f in frames:
        small = Image.fromarray(f).resize((f.shape[1] // 2, f.shape[0] // 2))
        d = _DEPTH(small)["predicted_depth"].squeeze().float().cpu().numpy()
        crus.append(cv2.resize(d, (f.shape[1], f.shape[0]), interpolation=cv2.INTER_LINEAR))
    pilha = np.stack(crus)
    lo, hi = np.percentile(pilha, 2), np.percentile(pilha, 99.5)
    out, ema = [], None
    for d in crus:
        x = np.clip((d - lo) / max(1e-6, hi - lo), 0, 1)
        ema = x if ema is None else 0.6 * ema + 0.4 * x   # tira o tremor
        out.append(ema)
    return out


def mascaras(frames: list[np.ndarray]) -> list[np.ndarray]:
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions, vision
    seg = vision.ImageSegmenter.create_from_options(vision.ImageSegmenterOptions(
        base_options=BaseOptions(model_asset_path=str(MODELOS / "selfie_segmenter.tflite")),
        running_mode=vision.RunningMode.VIDEO, output_confidence_masks=True))
    out, ema = [], None
    for i, f in enumerate(frames):
        r = seg.segment_for_video(mp.Image(image_format=mp.ImageFormat.SRGB,
                                           data=np.ascontiguousarray(f)), int(i * 1000 / FPS))
        m = r.confidence_masks[0].numpy_view().astype(np.float32)
        m = m[..., 0] if m.ndim == 3 else m
        m = cv2.GaussianBlur(m, (0, 0), 2.0)
        ema = m if ema is None else 0.55 * ema + 0.45 * m
        out.append(np.clip(ema, 0, 1))
    seg.close()
    return out


def pontos_maos_rosto(frames: list[np.ndarray]):
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions, vision
    VM = vision.RunningMode.VIDEO
    mh = vision.HandLandmarker.create_from_options(vision.HandLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(MODELOS / "hand_landmarker.task")),
        running_mode=VM, num_hands=2, min_hand_detection_confidence=0.4,
        min_tracking_confidence=0.4))
    mf = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(MODELOS / "face_landmarker.task")),
        running_mode=VM))
    res = []
    for i, f in enumerate(frames):
        im = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(f))
        ts = int(i * 1000 / FPS)
        h, w = f.shape[:2]
        rh = mh.detect_for_video(im, ts)
        rf = mf.detect_for_video(im, ts)
        maos = [([(p.x * w, p.y * h) for p in lm], hd[0].score)
                for lm, hd in zip(rh.hand_landmarks, rh.handedness)]
        rosto = None
        if rf.face_landmarks:
            xs = [p.x * w for p in rf.face_landmarks[0]]
            ys = [p.y * h for p in rf.face_landmarks[0]]
            rosto = (min(xs), min(ys), max(xs), max(ys))
        res.append((maos, rosto))
    mh.close()
    mf.close()
    return res


# ---------------------------------------------------------------- desenho
def brilho(camada: np.ndarray, raio: float) -> np.ndarray:
    """Camada RGB float (0..255) → ela mesma + halo desfocado (luz, não figura)."""
    return camada + cv2.GaussianBlur(camada, (0, 0), raio) * 1.6


def chip(draw: ImageDraw.ImageDraw, xy, texto: str, cor, f, alfa: float = 1.0) -> None:
    x, y = xy
    l, t, r, b = draw.textbbox((0, 0), texto, font=f)
    pad = 14
    draw.rounded_rectangle((x, y, x + r - l + 2 * pad, y + b - t + 2 * pad), radius=10,
                           fill=(8, 8, 8, int(190 * alfa)),
                           outline=(255, 255, 255, int(60 * alfa)), width=2)
    draw.text((x + pad - l, y + pad - t), texto, font=f, fill=(*cor, int(255 * alfa)))


def sobrepor(frame: np.ndarray, rgba: Image.Image) -> np.ndarray:
    a = np.asarray(rgba).astype(np.float32)
    al = a[..., 3:4] / 255.0
    return frame.astype(np.float32) * (1 - al) + a[..., :3] * al


# ---------------------------------------------------------------- efeitos
def fx_profundidade(frames, rot, M):
    deps = profundidades(frames)
    n, (h, w) = len(frames), frames[0].shape[:2]
    acc = M["accent"]
    fm = fonte("DM Mono", 500, 30)
    fg = fonte("Montserrat", 800, 44)
    out = []
    for i, (f, d) in enumerate(zip(frames, deps)):
        a = rampa(i, n, ent=0.55, sai=0.4)
        g = d[..., None] ** 1.25
        base = M["tinta"] * (1 - g) + M["papel"] * g
        # isolinhas: o "relevo" do quarto, na cor de destaque
        fr = (d * 14.0) % 1.0
        iso = np.clip(1 - np.minimum(fr, 1 - fr) / 0.045, 0, 1)[..., None]
        base = base * (1 - 0.85 * iso) + acc * 0.85 * iso
        # entra VARRENDO de cima: a linha de varredura é a luz que acende
        frente = int(h * min(1.0, (i / FPS) / 0.55)) if a < 1 and i < n / 2 else h
        mix = np.zeros((h, 1, 1), np.float32)
        mix[:frente] = 1.0
        if i >= n / 2:
            mix[:] = a
        orig = f.astype(np.float32)
        q = orig * (1 - mix) + base * mix
        if 0 < frente < h:
            lin = np.zeros((h, w, 3), np.float32)
            lin[max(0, frente - 3):frente + 3] = acc
            q = q + cv2.GaussianBlur(lin, (0, 0), 14) * 1.8 + lin
        # régua PERTO/LONGE com o marcador na distância do rosto
        if a > 0.05:
            img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            dr = ImageDraw.Draw(img)
            x0, y0, y1 = MARGEM, 560, 1240
            dr.line((x0, y0, x0, y1), fill=(255, 255, 255, int(150 * a)), width=3)
            for k in range(6):
                yy = y0 + (y1 - y0) * k / 5
                dr.line((x0, yy, x0 + 22, yy), fill=(255, 255, 255, int(150 * a)), width=2)
            dr.text((x0, y0 - 52), "LONGE", font=fm, fill=(255, 255, 255, int(200 * a)))
            dr.text((x0, y1 + 16), "PERTO", font=fm, fill=(255, 255, 255, int(200 * a)))
            perto = float(np.percentile(d[h // 5:h // 2, w // 4:3 * w // 4], 90))
            ym = y0 + (y1 - y0) * perto
            dr.ellipse((x0 - 11, ym - 11, x0 + 11, ym + 11), fill=(*acc.astype(int), int(255 * a)))
            metros = 0.45 + (1 - perto) * 1.5   # escala de quarto: rosto ~0,6–1 m
            dr.text((x0 + 40, ym - 26), f"{metros:.2f} m".replace(".", ","), font=fg,
                    fill=(255, 255, 255, int(255 * a)))
            if rot:
                chip(dr, (MARGEM, 300), rot, tuple(acc.astype(int)), fm, a)
            q = sobrepor(q, img)
        out.append(np.clip(q, 0, 255).astype(np.uint8))
    return out


def fx_recorte(frames, rot, M):
    ms = mascaras(frames)
    n, (h, w) = len(frames), frames[0].shape[:2]
    acc = M["accent"]
    fm = fonte("DM Mono", 500, 28)
    fb = fonte("Montserrat", 800, 46)
    out = []
    for i, (f, m) in enumerate(zip(frames, ms)):
        a = rampa(i, n)
        orig = f.astype(np.float32)
        cinza = orig.mean(axis=2, keepdims=True)
        fundo = cv2.GaussianBlur(orig * 0.35 + cinza * 0.15, (0, 0), 7)
        m3 = m[..., None]
        q = orig * m3 + fundo * (1 - m3)
        # contorno: a borda da máscara vira luz
        dur = (m > 0.5).astype(np.uint8)
        borda = cv2.morphologyEx(dur, cv2.MORPH_GRADIENT, np.ones((5, 5), np.uint8)).astype(np.float32)
        lin = borda[..., None] * acc
        q = q + brilho(lin, 12) * 0.9
        q = orig * (1 - a) + q * a
        if a > 0.05:
            img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            dr = ImageDraw.Draw(img)
            ys, xs = np.nonzero(dur[: h * 2 // 3])
            if len(xs):
                ox, oy = int(np.percentile(xs, 92)), int(np.percentile(ys, 40))
                tx, ty = min(w - MARGEM - 290, ox + 70), max(260, oy - 260)
                dr.line((ox, oy, tx + 20, ty + 120), fill=(*acc.astype(int), int(230 * a)), width=3)
                dr.ellipse((ox - 8, oy - 8, ox + 8, oy + 8), fill=(*acc.astype(int), int(255 * a)))
                dr.rounded_rectangle((tx, ty, tx + 280, ty + 118), radius=12,
                                     fill=(8, 8, 8, int(200 * a)),
                                     outline=(255, 255, 255, int(70 * a)), width=2)
                dr.text((tx + 20, ty + 16), "CAMADA 01", font=fm, fill=(255, 255, 255, int(170 * a)))
                dr.text((tx + 20, ty + 52), rot or "VOCÊ", font=fb, fill=(255, 255, 255, int(255 * a)))
            q = sobrepor(q, img)
        out.append(np.clip(q, 0, 255).astype(np.uint8))
    return out


def _grade_piso(h, w, acc, alfa, giro=0.0):
    img = np.zeros((h, w, 3), np.float32)
    hz = int(h * 0.62)
    cx = w / 2 + giro * 260
    for k in range(-12, 13):
        x_b = w / 2 + k * 170
        cv2.line(img, (int(cx), hz), (int(x_b), h), (255, 255, 255), 1, cv2.LINE_AA)
    for k in range(1, 12):
        y = hz + (h - hz) * (k / 11) ** 1.8
        cv2.line(img, (0, int(y)), (w, int(y)), (255, 255, 255), 1, cv2.LINE_AA)
    return img * 0.10 * alfa


def fx_nuvem(frames, rot, M):
    deps = profundidades(frames)
    n, (h, w) = len(frames), frames[0].shape[:2]
    acc = M["accent"]
    fm = fonte("DM Mono", 500, 30)
    passo = 4
    vv, uu = np.mgrid[0:h:passo, 0:w:passo]
    npts = vv.size
    f_len = 1500.0
    out = []
    for i, (fr, d) in enumerate(zip(frames, deps)):
        a = rampa(i, n, ent=0.45, sai=0.45)
        t = i / max(1, n - 1)
        ang = math.radians(26) * math.sin(math.pi * ease(t)) * (1 if t < 0.5 else 1) \
            - math.radians(8) * math.sin(2 * math.pi * ease(t))
        z = 1.0 + (1 - d[vv, uu]) * 2.4 * a      # em a=0 tudo no mesmo plano → quadro original
        X = (uu - w / 2) / f_len * z
        Y = (vv - h / 2) / f_len * z
        piv = 1.0 + 1.2 * a
        Xr = X * math.cos(ang) + (z - piv) * math.sin(ang)
        Zr = -X * math.sin(ang) + (z - piv) * math.cos(ang) + piv
        px = (Xr / Zr * f_len + w / 2).astype(np.int32)
        py = (Y / Zr * f_len + h / 2).astype(np.int32)
        cor = fr[vv, uu].astype(np.float32)
        ordem = np.argsort(-Zr, axis=None)
        px, py, cor = px.ravel()[ordem], py.ravel()[ordem], cor.reshape(-1, 3)[ordem]
        tela = (M["tinta"] * np.ones((h, w, 3), np.float32)) + _grade_piso(h, w, acc, a, ang)
        ok = (px >= 0) & (px < w - passo) & (py >= 0) & (py < h - passo)
        for dy in range(passo - 1):
            for dx in range(passo - 1):
                tela[py[ok] + dy, px[ok] + dx] = cor[ok]
        orig = fr.astype(np.float32)
        q = orig * (1 - a) + tela * a
        if a > 0.05:
            img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            dr = ImageDraw.Draw(img)
            chip(dr, (MARGEM, 300), rot or "RECONSTRUÇÃO 3D", tuple(acc.astype(int)), fm, a)
            chip(dr, (MARGEM, 380), f"NUVEM · {npts:,} PONTOS".replace(",", "."), (255, 255, 255), fm, a)
            q = sobrepor(q, img)
        out.append(np.clip(q, 0, 255).astype(np.uint8))
    return out


def _proj_painel(w, h, ang, zoff, esc, D=2.2, f_len=None):
    """Cantos de um painel w×h (em z=zoff, escala esc) girado em Y, projetados."""
    f_len = f_len or D * w / 1.0
    cs = []
    for (sx, sy) in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        x, y = sx * 0.5 * esc, sy * 0.5 * esc * h / w
        z = zoff
        xr = x * math.cos(ang) + z * math.sin(ang)
        zr = -x * math.sin(ang) + z * math.cos(ang) + D
        cs.append((xr / zr * f_len + w / 2, y / zr * f_len + h / 2))
    return np.float32(cs)


def fx_painel(frames, rot, M):
    ms = mascaras(frames)
    n, (h, w) = len(frames), frames[0].shape[:2]
    acc = M["accent"]
    fm = fonte("DM Mono", 500, 28)
    src = np.float32([(0, 0), (w, 0), (w, h), (0, h)])
    out = []
    for i, (f, m) in enumerate(zip(frames, ms)):
        a = rampa(i, n, ent=0.5, sai=0.5)
        t = ease(i / max(1, n - 1))
        ang = math.radians(34) * math.sin(math.pi * t) * a - math.radians(10) * math.sin(2 * math.pi * t) * a
        esc = 1.0 - 0.30 * a
        sep = 0.22 * a
        orig = f.astype(np.float32)
        fundo = cv2.GaussianBlur(orig, (0, 0), 3) * (1 - m[..., None] * 0.85)
        tela = M["tinta"] * np.ones((h, w, 3), np.float32) + _grade_piso(h, w, acc, a, ang)
        for camada, z, alfa_m in ((fundo, sep, None), (orig, -sep, m)):
            dst = _proj_painel(w, h, ang, z, esc)
            H = cv2.getPerspectiveTransform(src, dst)
            img = cv2.warpPerspective(camada, H, (w, h), flags=cv2.INTER_LINEAR)
            al = np.ones((h, w), np.float32) if alfa_m is None else alfa_m
            alw = cv2.warpPerspective(al, H, (w, h), flags=cv2.INTER_LINEAR)[..., None]
            if alfa_m is None:
                alw = alw * (0.92 if a > 0.05 else 1.0)
            tela = tela * (1 - alw) + img * alw
            # aresta do painel: linha fina acesa
            borda = np.zeros((h, w, 3), np.float32)
            cv2.polylines(borda, [dst.astype(np.int32)], True,
                          tuple(float(c) for c in (acc if alfa_m is None else M["nucleo"])), 2, cv2.LINE_AA)
            tela = tela + brilho(borda, 8) * 0.5 * a
        q = orig * (1 - a) + tela * a
        if a > 0.2:
            img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            dr = ImageDraw.Draw(img)
            chip(dr, (MARGEM, 300), rot or "CAMADAS 3D", tuple(acc.astype(int)), fm, a)
            chip(dr, (MARGEM, 1250), "CAMADA 01 · FUNDO", (255, 255, 255), fm, a)
            chip(dr, (w - MARGEM - 330, 1320), "CAMADA 02 · VOCÊ", (255, 255, 255), fm, a)
            q = sobrepor(q, img)
        out.append(np.clip(q, 0, 255).astype(np.uint8))
    return out


OSSOS = [(0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8), (5, 9), (9, 10),
         (10, 11), (11, 12), (9, 13), (13, 14), (14, 15), (15, 16), (13, 17), (17, 18),
         (18, 19), (19, 20), (0, 17)]


def fx_maos(frames, rot, M):
    det = pontos_maos_rosto(frames)
    n, (h, w) = len(frames), frames[0].shape[:2]
    acc = M["accent"]
    nuc = M["nucleo"]
    fm = fonte("DM Mono", 500, 26)
    out = []
    for i, (f, (maos, rosto)) in enumerate(zip(frames, det)):
        a = rampa(i, n, ent=0.3, sai=0.3)
        orig = f.astype(np.float32)
        q = orig * (1 - 0.22 * a)
        lin = np.zeros((h, w, 3), np.float32)
        for pts, _ in maos:
            for p1, p2 in OSSOS:
                cv2.line(lin, tuple(map(int, pts[p1])), tuple(map(int, pts[p2])),
                         tuple(float(c) for c in acc), 4, cv2.LINE_AA)
        q = q + brilho(lin, 9) * 0.8 * a
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        dr = ImageDraw.Draw(img)
        for k, (pts, sc) in enumerate(maos):
            for (x, y) in pts:
                dr.ellipse((x - 7, y - 7, x + 7, y + 7), fill=(*nuc.astype(int), int(255 * a)))
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            lx = min(max(MARGEM, min(xs) - 10), w - MARGEM - 420)
            ly = max(260, min(ys) - 110)
            chip(dr, (lx, ly), f"MÃO {k + 1:02d} · 21 PONTOS · {sc:.2f}".replace(".", ","),
                 (255, 255, 255), fm, a)
        if rosto:
            x0, y0, x1, y1 = rosto
            L = 46
            for (cx, cy, sx, sy) in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x1, y1, -1, -1), (x0, y1, 1, -1)):
                dr.line((cx, cy, cx + sx * L, cy), fill=(255, 255, 255, int(230 * a)), width=4)
                dr.line((cx, cy, cx, cy + sy * L), fill=(255, 255, 255, int(230 * a)), width=4)
            chip(dr, (min(x1 + 16, w - MARGEM - 200), y0), "ROSTO · 0,99", (255, 255, 255), fm, a)
        if rot:
            chip(dr, (MARGEM, 300), rot, tuple(acc.astype(int)), fm, a)
        q = sobrepor(q, img)
        out.append(np.clip(q, 0, 255).astype(np.uint8))
    return out


EFEITOS = {"profundidade": fx_profundidade, "recorte": fx_recorte, "nuvem": fx_nuvem,
           "painel": fx_painel, "maos": fx_maos}


# ---------------------------------------------------------------- plano
def gerar(edit: Path, base: Path, j: dict, M: dict, pasta: Path) -> Path:
    out = pasta / f"fx_{j['fx']}_{j['start']:.2f}.mp4"
    frames = ler(base, j["start"], j["end"])
    print(f"  {j['fx']:<13} {j['start']:6.2f}–{j['end']:6.2f}s  ({len(frames)} quadros)", flush=True)
    gravar(EFEITOS[j["fx"]](frames, j.get("rotulo", ""), M), out)
    return out


def assar(base: Path, clipes: list[tuple[Path, float, float]], saida: Path) -> None:
    """Grava os efeitos DENTRO de uma cópia do corte (decisão 1). Áudio copiado."""
    args = ["ffmpeg", "-v", "error", "-y", "-i", str(base)]
    filt, cur = [], "[0:v]"
    for k, (clip, s, e) in enumerate(clipes, start=1):
        args += ["-itsoffset", f"{s:.3f}", "-i", str(clip)]
        nxt = f"[v{k}]"
        filt.append(f"{cur}[{k}:v]overlay=eof_action=pass:enable='between(t,{s:.3f},{e - 0.001:.3f})'{nxt}")
        cur = nxt
    args += ["-filter_complex", ";".join(filt), "-map", cur, "-map", "0:a?",
             "-c:v", "libx264", "-crf", "14", "-preset", "medium", "-pix_fmt", "yuv420p",
             "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
             "-color_range", "tv", "-c:a", "copy", str(saida)]
    subprocess.run(args, check=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("edit", type=Path)
    ap.add_argument("--plano", type=Path, help="JSON com as janelas (relativo ao edit)")
    ap.add_argument("--fx", choices=sorted(EFEITOS))
    ap.add_argument("--start", type=float)
    ap.add_argument("--end", type=float)
    ap.add_argument("--rotulo", default="")
    ap.add_argument("-o", "--out", type=Path)
    a = ap.parse_args()
    edit = a.edit.resolve()
    M = marca()
    pasta = edit / "fx3d"
    pasta.mkdir(exist_ok=True)
    if a.fx:
        frames = ler(edit / "preview.mp4", a.start, a.end)
        gravar(EFEITOS[a.fx](frames, a.rotulo, M), a.out or pasta / f"fx_{a.fx}.mp4")
        return
    plano = json.loads((edit / a.plano if not a.plano.is_absolute() else a.plano).read_text())
    base = edit / plano.get("base", "preview.mp4")
    clipes = [(gerar(edit, base, j, M, pasta), j["start"], j["end"]) for j in plano["janelas"]]
    saida = edit / plano.get("saida", "preview_fx.mp4")
    print(f"  assando {len(clipes)} efeito(s) em {saida.name}…", flush=True)
    assar(base, clipes, saida)
    print(f"pronto: {saida}")


if __name__ == "__main__":
    main()

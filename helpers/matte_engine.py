#!/usr/bin/env python3
"""MOTOR DE RECORTE — o mesmo RVM, no acelerador que a máquina tiver.

O modelo continua o Robust Video Matting (mobilenetv3 = `rvm`, resnet50 =
`rvm-hq`). O que muda é ONDE ele roda, escolhido sozinho por máquina:

  coreml  Mac Apple Silicon — RVM convertido para CoreML com a resolução
          FIXA do vídeo (Neural Engine + GPU). Convertido uma vez por
          resolução e guardado em ~/.avelin/modelos/rvm/coreml/.
  onnx    Qualquer máquina — onnxruntime (já vem na base, ~15 MB de modelo).
          Windows: DirectML (qualquer placa DX12: NVIDIA, AMD, Intel) ou CUDA;
          sem placa, CPU.
  torch   Legado (PyTorch MPS/CUDA) — só quando os outros faltam ou quando
          AVE_RECORTE_BACKEND=torch.

Medido em 2026-11-16 (MacBook Air M3, 1080x1920, mobilenetv3, em REGIME —
sem o aquecimento, que num trecho de 4s é metade do tempo e enganou a 1ª
medição):

  torch MPS  23,7 fps   (o motor antigo — rápido, mas ~2 GB de instalação)
  coreml     22,4 fps   IoU 0,986 vs torch, mesma tremulação; aquece devagar
  onnx CPU   16,6 fps   alfa IDÊNTICO ao torch; zero instalação extra
  onnx CoreML-EP  pior que a CPU: recusa os Resize/Slice dinâmicos do RVM e
                  fatia o grafo — por isso fica fora da lista no Mac
  resnet50: onnx CPU 3,3 fps — no Mac o rvm-hq quer torch ou coreml

Decodificar (250 fps), preparar (380) e codificar a máscara (200) não são
gargalo: o tempo é o modelo. NINGUÉM precisa rodar nada: o primeiro recorte
numa máquina (ou depois de o ambiente mudar — torch instalado, DirectML que
entrou) mede sozinho os motores disponíveis em ~3s do próprio vídeo, em regime,
e grava; daí em diante a ordem segue essa medição.

A SAÍDA é leve (alternativa 3): a máscara em H.264 cinza (CRF 8, faixa cheia:
erro médio de 1/255 na borda, ~0,4 MB/s) e, quando a pessoa vai para um fundo
NOVO, a cor descontaminada (`fgr`) em H.264 comum. O ProRes 4444 com alfa
(15–50 MB/s medidos) só nasce quando a composição em CAMADAS do HyperFrames precisa dele
(`derivar_alfa`) — o VP9 com alfa NÃO serve: o libvpx desta build zera o alfa
em silêncio (medido de novo em 2026-11-16).

    python helpers/matte_engine.py info                       # o que roda aqui
    python helpers/matte_engine.py preparar 1080 1920 [--hq]  # converte o CoreML antes
    python helpers/matte_engine.py bench <video> [--dur 5]    # remede tudo (diagnóstico)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import queue
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np

HELPERS = Path(__file__).resolve().parent
MODELOS = Path.home() / ".avelin" / "modelos" / "rvm"
URL = "https://github.com/PeterL1n/RobustVideoMatting/releases/download/v1.0.0/"
ONNX = {  # variante → (arquivo, sha256)
    "mobilenetv3": ("rvm_mobilenetv3_fp32.onnx",
                    "88d4531297118f595bf2fd60f6f566aec2e559393802d1f436c380f0cbbd2828"),
    "resnet50": ("rvm_resnet50_fp32.onnx",
                 "25db300fcb6ee27f941a1b52c97856e8d1f13c7f35817f81a612f89af0e8a85c"),
}
MAC_ARM = sys.platform == "darwin" and platform.machine() == "arm64"
WINDOWS = sys.platform == "win32"
MASCARA_CRF = 8          # medido: erro médio 1/255 na borda; 16 já borra o cabelo
COR_CRF = 14


def variante(motor: str) -> str:
    return "resnet50" if motor in ("rvm-hq", "resnet50") else "mobilenetv3"


def razao(W: int, H: int) -> float:
    """downsample_ratio do RVM: lado maior ~512px (o mesmo do motor antigo)."""
    return min(512 / max(W, H), 1.0)


def say(msg: str) -> None:
    print(f"[recorte] {msg}", flush=True)


# ---------------------------------------------------------------- modelos

def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def modelo_onnx(var: str) -> Path:
    """Baixa (uma vez, conferindo o sha256) o RVM em ONNX oficial."""
    nome, sha = ONNX[var]
    p = MODELOS / nome
    if p.exists():
        return p
    MODELOS.mkdir(parents=True, exist_ok=True)
    say(f"baixando o modelo de recorte {nome} (uma vez só)")
    import requests
    tmp = p.with_suffix(".part")
    with requests.get(URL + nome, stream=True, timeout=60) as r:
        r.raise_for_status()
        with tmp.open("wb") as f:
            for b in r.iter_content(1 << 20):
                f.write(b)
    if _sha(tmp) != sha:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"{nome}: sha256 não confere — download corrompido")
    tmp.rename(p)
    return p


def _tem(mod: str) -> bool:
    import importlib.util
    return importlib.util.find_spec(mod) is not None


def caminho_coreml(var: str, W: int, H: int) -> Path:
    return MODELOS / "coreml" / f"rvm_{var}_{W}x{H}_fp16.mlpackage"


_CONVERTER = r'''
import sys, torch, coremltools as ct
var, W, H, ds, out = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), float(sys.argv[4]), sys.argv[5]
m = torch.hub.load("PeterL1n/RobustVideoMatting", var, trust_repo=True, verbose=False).eval()
class Fixo(torch.nn.Module):
    def __init__(s, m): super().__init__(); s.m = m
    def forward(s, src, r1, r2, r3, r4): return s.m(src, r1, r2, r3, r4, downsample_ratio=ds)
src = torch.rand(1, 3, H, W)
with torch.no_grad():
    _, _, *rec = m(src, downsample_ratio=ds)
formas = [tuple(r.shape) for r in rec]
with torch.no_grad():
    tr = torch.jit.trace(Fixo(m).eval(), (src, *[torch.zeros(f) for f in formas]), check_trace=False)
ml = ct.convert(tr, convert_to="mlprogram", compute_precision=ct.precision.FLOAT16,
                minimum_deployment_target=ct.target.macOS13,
                inputs=[ct.TensorType("src", shape=src.shape)]
                       + [ct.TensorType(f"r{i+1}i", shape=f) for i, f in enumerate(formas)],
                outputs=[ct.TensorType(n) for n in ("fgr", "pha", "r1o", "r2o", "r3o", "r4o")])
ml.save(out)
'''


def coreml_pronto(var: str, W: int, H: int) -> bool:
    return MAC_ARM and _tem("coremltools") and caminho_coreml(var, W, H).exists()


def coreml_convertivel() -> bool:
    return MAC_ARM and _tem("coremltools") and _tem("torch")


def preparar_coreml(var: str, W: int, H: int) -> Path:
    """Converte o RVM para CoreML nesta resolução (uma vez; ~30s). Precisa de
    torch + coremltools só AGORA — rodar depois precisa só do coremltools."""
    out = caminho_coreml(var, W, H)
    if out.exists():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    say(f"preparando o recorte acelerado para {W}x{H} ({var}) — uma vez por resolução")
    tmp = out.with_name(out.stem + ".tmp.mlpackage")
    shutil.rmtree(tmp, ignore_errors=True)
    r = subprocess.run([sys.executable, "-c", _CONVERTER, var, str(W), str(H),
                        str(razao(W, H)), str(tmp)], capture_output=True, text=True)
    if r.returncode != 0 or not tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)
        raise RuntimeError("conversão CoreML falhou:\n" + r.stderr[-1500:])
    tmp.rename(out)
    return out


# ---------------------------------------------------------------- motores

class _Coreml:
    nome = "coreml"

    def __init__(self, var, W, H):
        import coremltools as ct
        p = caminho_coreml(var, W, H) if coreml_pronto(var, W, H) else preparar_coreml(var, W, H)
        self.m = ct.models.MLModel(str(p), compute_units=ct.ComputeUnit.ALL)
        forma = {i.name: tuple(i.type.multiArrayType.shape)
                 for i in self.m.get_spec().description.input}
        self.rec = {k: np.zeros(forma[k], np.float32) for k in ("r1i", "r2i", "r3i", "r4i")}
        self.detalhe = "Neural Engine + GPU (fp16)"

    def __call__(self, rgb):
        src = (rgb.astype(np.float32) * (1 / 255)).transpose(2, 0, 1)[None]
        o = self.m.predict({"src": src, **self.rec})
        self.rec = {f"r{i}i": o[f"r{i}o"] for i in range(1, 5)}
        return o["fgr"][0], o["pha"][0, 0]


def provedores_onnx() -> list:
    """Ordem por plataforma. No Mac o CoreML-EP fica DE FORA: medido mais
    lento que a CPU (recusa os Resize dinâmicos do RVM e fatia o grafo)."""
    import onnxruntime as ort
    tem = set(ort.get_available_providers())
    ordem = ["DmlExecutionProvider", "CUDAExecutionProvider"] if not sys.platform == "darwin" else []
    return [p for p in ordem if p in tem] + ["CPUExecutionProvider"]


class _Onnx:
    nome = "onnx"

    def __init__(self, var, W, H):
        import onnxruntime as ort
        so = ort.SessionOptions()
        so.log_severity_level = 3
        provs = provedores_onnx()
        if "DmlExecutionProvider" in provs:
            # DirectML exige estas duas (documentação do onnxruntime-directml)
            so.enable_mem_pattern = False
            so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        self.s = ort.InferenceSession(str(modelo_onnx(var)), so, providers=provs)
        self.detalhe = self.s.get_providers()[0].replace("ExecutionProvider", "")
        self.rec = [np.zeros((1, 1, 1, 1), np.float32)] * 4
        self.ds = np.array([razao(W, H)], np.float32)

    def __call__(self, rgb):
        src = (rgb.astype(np.float32) * (1 / 255)).transpose(2, 0, 1)[None]
        fgr, pha, *self.rec = self.s.run(None, {
            "src": src, "r1i": self.rec[0], "r2i": self.rec[1], "r3i": self.rec[2],
            "r4i": self.rec[3], "downsample_ratio": self.ds})
        return fgr[0], pha[0, 0]


class _Torch:
    nome = "torch"

    def __init__(self, var, W, H):
        os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
        import warnings
        warnings.filterwarnings("ignore", message="The given NumPy array is not writable")
        import torch
        self.t = torch
        dev = "mps" if torch.backends.mps.is_available() else \
            "cuda" if torch.cuda.is_available() else "cpu"
        self.dev = dev
        self.m = torch.hub.load("PeterL1n/RobustVideoMatting", var, trust_repo=True,
                                verbose=False).eval().to(dev)
        self.rec = [None] * 4
        self.ds = razao(W, H)
        self.detalhe = dev

    def __call__(self, rgb):
        t = self.t
        with t.no_grad():
            src = t.from_numpy(np.ascontiguousarray(rgb)).to(self.dev).permute(2, 0, 1) \
                .float().div(255)[None]
            fgr, pha, *self.rec = self.m(src, *self.rec, downsample_ratio=self.ds)
            return fgr[0].cpu().numpy(), pha[0, 0].cpu().numpy()


MOTORES = {"coreml": _Coreml, "onnx": _Onnx, "torch": _Torch}


MEDICAO = Path.home() / ".avelin" / "recorte_bench.json"


def _medido() -> dict:
    try:
        return json.loads(MEDICAO.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


AQUECE = 15        # quadros descartados da medição: o 1º trecho é aquecimento


def _ambiente() -> str:
    """O que muda a resposta de "qual motor é mais rápido aqui". Mudou (instalou
    o torch, o DirectML entrou, outra máquina com o mesmo ~/.avelin) → a medição
    antiga não vale e o próximo recorte mede de novo, sozinho."""
    return (f"{sys.platform}-{platform.machine()} onnx={provedores_onnx()[0]} "
            f"torch={_tem('torch')}")


def _candidatos(var: str, W: int, H: int) -> list[str]:
    """Os motores que dá para medir JÁ, sem custo de preparo (o CoreML só se já
    convertido nesta resolução — converter leva ~30s e fica para quando a
    medição mostrar que vale)."""
    c = ["onnx"] + (["torch"] if _tem("torch") else [])
    if MAC_ARM and coreml_pronto(var, W, H):
        c.append("coreml")
    return c


def medir(video: Path, var: str, *, start: float = 0.0, dur: float = 3.0,
          motores: list[str] | None = None) -> dict:
    """fps EM REGIME de cada motor no MESMO trecho do vídeo; grava em MEDICAO.
    Sem o aquecimento: num trecho curto ele domina e inverte a ordem (foi o
    que fez a 1ª medição prometer um CoreML 3x mais rápido que não existia)."""
    import tempfile
    W, H, _, _ = sonda(video)
    antes = os.environ.get("AVE_RECORTE_BACKEND")
    fps, res = {}, {}
    try:
        for nome in motores or _candidatos(var, W, H):
            os.environ["AVE_RECORTE_BACKEND"] = nome
            with tempfile.TemporaryDirectory() as td:
                try:
                    r = recortar(video, Path(td) / "m.mp4", motor=var, start=start, dur=dur)
                    fps[nome] = r["fps_regime"] or r["fps"]
                    res[nome] = f"{fps[nome]} fps ({r['detalhe']})"
                except Exception as e:  # noqa: BLE001 — motor quebrado = fora da ordem
                    fps[nome] = 0.0
                    res[nome] = f"indisponível: {str(e).splitlines()[0][:100]}"
    finally:
        if antes is None:
            os.environ.pop("AVE_RECORTE_BACKEND", None)
        else:
            os.environ["AVE_RECORTE_BACKEND"] = antes
    tudo = _medido()
    tudo[var] = {**fps, "em": time.strftime("%Y-%m-%d %H:%M"), "ambiente": _ambiente()}
    MEDICAO.parent.mkdir(parents=True, exist_ok=True)
    MEDICAO.write_text(json.dumps(tudo, ensure_ascii=False, indent=2))
    return res


def _medir_se_preciso(video: Path, var: str, W: int, H: int, start: float) -> None:
    """Primeiro recorte nesta máquina (ou depois de o ambiente mudar): mede os
    motores disponíveis, uma vez, sem ninguém pedir. Com um só motor não há o
    que escolher; com AVE_RECORTE_BACKEND, quem chamou já escolheu."""
    if os.environ.get("AVE_RECORTE_BACKEND", "").strip():
        return
    med = _medido().get(var) or {}
    if med.get("ambiente") == _ambiente():
        return
    cand = _candidatos(var, W, H)
    if len(cand) < 2:
        return
    say(f"primeiro recorte neste ambiente — medindo {', '.join(cand)} (uma vez, ~20s)")
    res = medir(video, var, start=start, motores=cand)
    say("medido: " + " · ".join(f"{k} {v}" for k, v in res.items())
        + f" → usando {ordem(var, W, H)[0]}")


def ordem(var: str, W: int, H: int) -> list[str]:
    """Do mais rápido ao mais garantido, NESTA máquina.

    Com `bench` já rodado, manda a medição (fps reais desta máquina). Sem ela,
    a ordem padrão — que veio da medição no M3: em regime, coreml 22,4 fps ≈
    torch MPS 23,7 > onnx CPU 16,6. Então no Mac o torch, quando instalado,
    vem primeiro (não paga a conversão de ~30s por resolução); o coreml entra
    quando já está convertido; o onnx é o piso que roda em qualquer lugar.
    Fora do Mac: onnx com DirectML/CUDA, que é a aceleração sem 2 GB de torch."""
    forcado = os.environ.get("AVE_RECORTE_BACKEND", "").strip().lower()
    if forcado in MOTORES:
        return [forcado]
    possiveis = ["onnx"]
    if _tem("torch"):
        possiveis.append("torch")
    if MAC_ARM and (coreml_pronto(var, W, H) or coreml_convertivel()):
        possiveis.append("coreml")
    med = _medido().get(var) or {}
    if med and med.get("ambiente") == _ambiente():
        return sorted(possiveis, key=lambda b: -float(med.get(b, 0)))
    if MAC_ARM:
        padrao = ["torch", "coreml", "onnx"]
        if not coreml_pronto(var, W, H):
            padrao = ["torch", "onnx", "coreml"]   # converter é caro: só se nada mais
    else:
        acelera = any(p != "CPUExecutionProvider" for p in provedores_onnx())
        padrao = ["onnx", "torch"] if acelera else ["torch", "onnx"]
    return [b for b in padrao if b in possiveis]


def abrir(motor: str, W: int, H: int):
    var = variante(motor)
    erros = []
    for nome in ordem(var, W, H):
        try:
            m = MOTORES[nome](var, W, H)
            say(f"motor: {nome} ({m.detalhe}) · {var} · {W}x{H}")
            return m
        except Exception as e:  # noqa: BLE001 — cai para o próximo motor
            erros.append(f"{nome}: {e}")
            say(f"{nome} indisponível ({str(e).splitlines()[0][:120]}) — tentando o próximo")
    raise RuntimeError("nenhum motor de recorte rodou:\n  " + "\n  ".join(erros))


# ---------------------------------------------------------------- vídeo

def sonda(video: Path) -> tuple[int, int, float, float]:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height,r_frame_rate:format=duration", "-of", "json",
                        str(video)], capture_output=True, text=True, check=True)
    j = json.loads(r.stdout)
    s = j["streams"][0]
    n, d = (s["r_frame_rate"].split("/") + ["1"])[:2]
    return int(s["width"]), int(s["height"]), float(n) / float(d), float(j["format"]["duration"])


def _janela(start: float, dur: float | None, fps: float) -> tuple[list[str], list[str]]:
    """Busca por QUADRO, não por segundo: o primeiro é round(start*fps) — a
    convenção do motor antigo (cv2 POS_FRAMES), a que casa com o a-roll.
    `-ss` exato na fronteira de quadro é frágil: com o start_time de 0,021s
    do preview, `-ss 4.4` caiu no quadro 133 em vez do 132 (medido) — por
    isso o meio quadro de folga. A duração vira contagem de quadros."""
    k = int(round(start * fps))
    ss = ["-ss", f"{(k - 0.5) / fps:.6f}"] if k > 0 else []
    return ss, (["-frames:v", str(int(round(dur * fps)))] if dur else [])


def _encoder(out: Path, W: int, H: int, fps: float, fmt: str) -> subprocess.Popen:
    """Máscara: cinza em faixa CHEIA (0–255 de verdade). Cor: H.264 comum."""
    if fmt == "gray":
        cod = ["-c:v", "libx264", "-preset", "veryfast", "-crf", str(MASCARA_CRF),
               "-pix_fmt", "gray", "-color_range", "pc"]
    else:
        cod = ["-c:v", "libx264", "-preset", "veryfast", "-crf", str(COR_CRF),
               "-pix_fmt", "yuv420p"]
    out.parent.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", fmt,
                             "-s", f"{W}x{H}", "-r", f"{fps}", "-i", "-", *cod,
                             "-movflags", "+faststart", str(out)], stdin=subprocess.PIPE)


def recortar(video: Path, mascara: Path, *, motor: str = "rvm", start: float = 0.0,
             dur: float | None = None, cor: Path | None = None) -> dict:
    """Pessoa → `mascara` (H.264 cinza) e, se pedido, `cor` (fgr descontaminado).

    Decodificar, inferir e codificar correm em paralelo (fila de 8 quadros):
    o modelo nunca espera o ffmpeg."""
    W, H, fps, total = sonda(video)
    ss, tt = _janela(start, dur, fps)
    dec = subprocess.Popen(["ffmpeg", "-v", "error", *ss, "-i", str(video), *tt, "-an",
                            "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    fila: queue.Queue = queue.Queue(maxsize=8)
    tam = W * H * 3

    def ler():
        while True:
            b = dec.stdout.read(tam)
            if len(b) < tam:
                fila.put(None)
                return
            fila.put(np.frombuffer(b, np.uint8).reshape(H, W, 3))

    _medir_se_preciso(video, variante(motor), W, H, start)
    threading.Thread(target=ler, daemon=True).start()
    m = abrir(motor, W, H)
    em = _encoder(mascara, W, H, fps, "gray")
    ec = _encoder(cor, W, H, fps, "rgb24") if cor else None
    n_previsto = int(round((dur if dur else total - start) * fps))
    n, t0, t_reg = 0, time.time(), None
    try:
        while (rgb := fila.get()) is not None:
            if n == AQUECE:
                t_reg = time.time()
            fgr, pha = m(rgb)
            em.stdin.write((np.clip(pha, 0, 1) * 255 + 0.5).astype(np.uint8).tobytes())
            if ec:
                ec.stdin.write((np.clip(fgr, 0, 1).transpose(1, 2, 0) * 255 + 0.5)
                               .astype(np.uint8).tobytes())
            n += 1
            if n % 60 == 0:
                say(f"  {n}/{n_previsto} quadros · {n / (time.time() - t0):.1f} fps")
    finally:
        for e in (em, ec):
            if e:
                e.stdin.close()
                e.wait()
        dec.wait()
    seg = time.time() - t0
    say(f"recortados {n} quadros em {seg:.1f}s ({n / max(seg, 1e-6):.1f} fps, {m.nome})")
    reg = (n - AQUECE) / max(time.time() - t_reg, 1e-6) if t_reg and n > AQUECE else None
    return {"quadros": n, "segundos": round(seg, 1), "backend": m.nome, "detalhe": m.detalhe,
            "fps": round(n / max(seg, 1e-6), 1),
            "fps_regime": round(reg, 1) if reg else None}


def derivar_alfa(cor_ou_fonte: Path, mascara: Path, out: Path, *, start: float = 0.0,
                 dur: float | None = None) -> Path:
    """ProRes 4444 com alfa = cor × máscara, para a composição em CAMADAS do
    HyperFrames (o renderer só reconhece alfa por pix_fmt yuva* ou alpha_mode).
    `start/dur` recortam a FONTE (a máscara já começa na janela)."""
    ss, tt = _janela(start, dur, sonda(cor_ou_fonte)[2])
    tmp = out.with_name(out.stem + ".tmp" + out.suffix)
    # `tt` (-frames:v) é opção de SAÍDA: vai depois do -map, nunca entre os -i
    subprocess.run(["ffmpeg", "-v", "error", "-y", *ss, "-i", str(cor_ou_fonte),
                    "-i", str(mascara), "-filter_complex",
                    "[1:v]format=gray[m];[0:v][m]alphamerge,format=yuva444p10le[v]",
                    "-map", "[v]", *tt, "-an", "-shortest", "-c:v", "prores_ks",
                    "-profile:v", "4444", "-pix_fmt", "yuva444p10le", "-qscale:v", "6",
                    str(tmp)], check=True)
    tmp.replace(out)
    return out


def garantir_alfa(pasta: Path, nome: str) -> Path:
    """O `.mov` com alfa de uma janela do manifesto — gerado AGORA, da máscara,
    se ainda não existe (ou se a máscara é mais nova). Quem compõe em camadas
    chama isto; quem compõe no ffmpeg nunca paga o ProRes."""
    out = pasta / nome
    man = pasta / "recorte.json"
    j = ((json.loads(man.read_text()) if man.exists() else {}).get("janelas") or {}).get(nome) or {}
    if not j.get("mascara"):
        return out                      # janela antiga / motor hyperframes: o .mov é o original
    mascara = pasta / j["mascara"]
    if out.exists() and out.stat().st_mtime >= mascara.stat().st_mtime:
        return out
    say(f"gerando o alfa para a composição em camadas: {nome}")
    if j.get("cor"):
        return derivar_alfa(pasta / j["cor"], mascara, out)
    return derivar_alfa(Path(j["fonte"]), mascara, out, start=float(j["inicio"]),
                        dur=float(j["fim"]) - float(j["inicio"]))


def compor_fundo(fundo: Path, cor: Path, mascara: Path, out: Path, *, W: int, H: int,
                 fps: float, dur: float) -> Path:
    """ALTERNATIVA 5 — pessoa (cor descontaminada × máscara) sobre o fundo novo,
    tudo no ffmpeg, num MP4 OPACO comum. Sem alfa no navegador: o HyperFrames
    recebe esse vídeo como o próprio a-roll. Imagem vira vídeo parado; vídeo
    curto entra em loop; o fundo cobre o quadro (cover) e é cortado no centro."""
    img = fundo.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")
    entrada = (["-loop", "1", "-framerate", f"{fps}", "-t", f"{dur:.3f}", "-i", str(fundo)] if img
               else ["-stream_loop", "-1", "-t", f"{dur:.3f}", "-i", str(fundo)])
    fc = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
          f"fps={fps},format=yuv420p,setsar=1[bg];"
          f"[2:v]format=gray[m];[1:v][m]alphamerge[p];"
          f"[bg][p]overlay=shortest=1:format=auto,format=yuv420p[v]")
    tmp = out.with_name(out.stem + ".tmp" + out.suffix)
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", *entrada, "-i", str(cor), "-i", str(mascara),
                    "-filter_complex", fc, "-map", "[v]", "-an", "-c:v", "libx264",
                    "-preset", "veryfast", "-crf", "14", "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart", str(tmp)], check=True)
    tmp.replace(out)
    return out


# ---------------------------------------------------------------- CLI

def info() -> dict:
    import onnxruntime as ort
    d = {"plataforma": f"{sys.platform} {platform.machine()}",
         "onnxruntime": ort.__version__, "provedores_onnx": provedores_onnx(),
         "coremltools": _tem("coremltools"), "torch": _tem("torch"),
         "modelos_onnx": [n for n, _ in ONNX.values() if (MODELOS / n).exists()],
         "coreml_cache": sorted(p.name for p in (MODELOS / "coreml").glob("*.mlpackage"))
         if (MODELOS / "coreml").exists() else []}
    for var in ONNX:
        d[f"ordem_{var}_1080x1920"] = ordem(var, 1080, 1920)
    return d


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("info")
    p = sub.add_parser("preparar")
    p.add_argument("W", type=int)
    p.add_argument("H", type=int)
    p.add_argument("--hq", action="store_true")
    b = sub.add_parser("bench")
    b.add_argument("video", type=Path)
    b.add_argument("--dur", type=float, default=5.0)
    b.add_argument("--hq", action="store_true")
    a = ap.parse_args()
    if a.cmd == "info":
        print(json.dumps(info(), ensure_ascii=False, indent=2))
    elif a.cmd == "preparar":
        modelo_onnx(variante("rvm-hq" if a.hq else "rvm"))
        if MAC_ARM:
            print(preparar_coreml(variante("rvm-hq" if a.hq else "rvm"), a.W, a.H))
    else:
        # o mesmo que o 1º recorte faz sozinho; aqui inclui o CoreML (converte
        # se preciso) para comparar tudo
        var = variante("rvm-hq" if a.hq else "rvm")
        print(json.dumps(medir(a.video, var, dur=a.dur, motores=list(MOTORES)),
                         ensure_ascii=False, indent=2))
        print(f"gravado em {MEDICAO} — a ordem agora: {ordem(var, 1080, 1920)}")


if __name__ == "__main__":
    main()

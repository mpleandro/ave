"""ELENCO — quem é quem num vídeo com pessoas FIXAS (live, podcast, mesa).

Por que existe: decidir quem fala pela BOCA falha com microfone de mão. Na live
da Mentoria Mil Milionários (2026-11) Camila e Júlia falam com o microfone
colado nos lábios; o landmarker não vê a boca delas e a faixa ia para o Paulo,
que mexia a boca ao lado. Erro apontado pelo usuário em quatro cortes seguidos.

O elenco resolve com dois sinais que o microfone não esconde:
- VOZ — impressão WeSpeaker (`voz.impressao`) média de trechos em que se SABE
  quem fala: diz QUEM fala a cada meio segundo;
- COR DA ROUPA — Lab médio do tronco logo abaixo do rosto: diz QUAL rosto é
  essa pessoa. A atribuição rosto↔pessoa é feita por cena, todos de uma vez
  (permutação de menor distância), então luz mais escura numa cena não troca
  ninguém de lugar: o mais claro continua o mais claro.

Arquivo: `<trabalho>/elenco.json`. Sem ele o enquadramento segue pela boca,
como sempre. Criar (com trechos conferidos):

    uv run python -m cortes.elenco criar <video> elenco_ref.json

`elenco_ref.json`: {"pessoas": [{"nome": "Paulo", "voz": [[a, b], …],
"cor": [[t, x_aproximado], …]}, …]}
"""
from __future__ import annotations

import itertools
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

from . import voz as VZ

VOZ_MARGEM = 0.04     # vantagem mínima da melhor voz sobre a segunda
VOZ_MIN = 0.30        # similaridade mínima para acreditar na voz
COR_MAX = 70.0        # distância Lab acima disto: o rosto não é dessa pessoa


def caminho(video: Path) -> Path:
    return video.parent / f"{video.stem}_cortes" / "elenco.json"


def carregar(video: Path) -> dict | None:
    p = caminho(video)
    try:
        d = json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    for pe in d.get("pessoas", []):
        pe["_voz"] = np.array(pe["voz"], dtype=np.float32)
        pe["_cor"] = np.array(pe["cor"], dtype=np.float32)
    return d if d.get("pessoas") else None


def cor_tronco(fr: np.ndarray, cx: float, cy: float, w: float, h: float) -> list[float] | None:
    """Lab (OpenCV, 0–255) médio do tronco logo abaixo do rosto."""
    import cv2  # noqa: PLC0415
    H, W = fr.shape[:2]
    x0, x1 = int(max(0, cx - 0.6 * w)), int(min(W, cx + 0.6 * w))
    y0, y1 = int(min(H - 1, cy + 0.9 * h)), int(min(H, cy + 2.2 * h))
    if y1 - y0 < 4 or x1 - x0 < 4:
        return None
    m = fr[y0:y1, x0:x1].reshape(-1, 3).mean(0).astype(np.uint8)
    return [float(v) for v in cv2.cvtColor(m[None, None, :], cv2.COLOR_BGR2LAB)[0, 0]]


def _embeddings(video: Path, a: float, b: float, janela: float = 1.5, passo: float = 0.75):
    x = VZ.audio(video, a, b)
    out = []
    for s in np.arange(0, max(0.0, (b - a) - janela), passo):
        seg = x[int(s * 16000):int((s + janela) * 16000)]
        if len(seg) < 8000 or np.sqrt((seg ** 2).mean()) < 300:
            continue
        out.append((a + s + janela / 2, VZ.impressao(seg)))
    return out


def quem_fala(video: Path, a: float, c0: float, c1: float, el: dict, passo: float) -> list[str | None]:
    """Nome de quem fala em cada passo de [c0, c1) (relativo a `a`), ou None."""
    nomes = [p["nome"] for p in el["pessoas"]]
    M = np.array([p["_voz"] for p in el["pessoas"]])
    x = VZ.audio(video, a + c0 - 0.75, a + c1 + 0.75)
    out = []
    for s in np.arange(c0, c1, passo):
        i0 = int((s - c0) * 16000)
        seg = x[i0:i0 + 24000]                       # 1,5s centrada no passo
        if len(seg) < 12000 or np.sqrt((seg ** 2).mean()) < 300:
            out.append(None)
            continue
        sim = M @ VZ.impressao(seg)
        o = np.argsort(sim)[::-1]
        ok = sim[o[0]] >= VOZ_MIN and (len(o) < 2 or sim[o[0]] - sim[o[1]] >= VOZ_MARGEM)
        out.append(nomes[o[0]] if ok else None)
    return out


def atribuir(pes: list[dict], el: dict) -> dict[str, int]:
    """nome → índice do rosto na cena, pela cor da roupa (todos de uma vez)."""
    cores = [p.get("cor") for p in pes]
    idx = [i for i, c in enumerate(cores) if c is not None]
    if not idx:
        return {}
    gente = el["pessoas"]
    melhor, custo = {}, float("inf")
    k = min(len(idx), len(gente))
    for faces in itertools.permutations(idx, k):
        for quem in itertools.permutations(range(len(gente)), k):
            d = [float(np.linalg.norm(np.array(cores[f]) - gente[q]["_cor"])) for f, q in zip(faces, quem)]
            if max(d) > COR_MAX:
                continue
            if sum(d) < custo:
                custo, melhor = sum(d), {gente[q]["nome"]: f for f, q in zip(faces, quem)}
    return melhor


def criar(video: Path, ref: dict) -> dict:
    import cv2  # noqa: PLC0415
    from . import enquadramento as EQ  # noqa: PLC0415
    W, H = EQ.dimensoes(video)
    det = cv2.FaceDetectorYN.create(str(EQ.YUNET), "", (960, int(H * 960 / W)), 0.6, 0.3, 50)
    pessoas = []
    for pe in ref["pessoas"]:
        E = [e for a, b in pe["voz"] for _, e in _embeddings(video, a, b)]
        v = np.mean(E, 0)
        v /= np.linalg.norm(v)
        cores = []
        for t, xh in pe["cor"]:
            raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1",
                                  "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], capture_output=True).stdout
            fr = np.frombuffer(raw[:W * H * 3], np.uint8).reshape(H, W, 3)
            esc = 960 / W
            _, fs = det.detect(cv2.resize(fr, (960, int(H * esc))))
            cand = []
            for f in (fs if fs is not None else []):
                x, y, w, h = (float(q) / esc for q in f[:4])
                c = cor_tronco(fr, x + w / 2, y + h / 2, w, h)
                if c:
                    cand.append((abs(x + w / 2 - xh), c))
            if cand:
                cores.append(min(cand)[1])
        pessoas.append({"nome": pe["nome"], "voz": [round(float(q), 6) for q in v],
                        "cor": [round(float(q), 1) for q in np.median(cores, 0)],
                        "amostras_voz": len(E), "amostras_cor": len(cores)})
    d = {"pessoas": pessoas, "ref": ref}
    caminho(video).write_text(json.dumps(d, ensure_ascii=False))
    return d


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "criar":
        d = criar(Path(sys.argv[2]), json.loads(Path(sys.argv[3]).read_text()))
        for p in d["pessoas"]:
            print(p["nome"], "voz:", p["amostras_voz"], "cor:", p["cor"], f"({p['amostras_cor']} quadros)")
    else:
        sys.exit(__doc__)

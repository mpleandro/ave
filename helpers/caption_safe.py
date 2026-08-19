#!/usr/bin/env python3
"""A FAIXA SEGURA DA LEGENDA — medida no rosto, não escolhida no olho.

    uv run python helpers/caption_safe.py <edit> [--aplicar] [--json]

Por que existe: um estilo de legenda traz uma altura de fábrica (o `offsetY` do
`variants.json`), e essa altura é uma média de material nenhum. No PV a legenda
`dinamico` nasce a 47% da altura e o queixo do apresentador está a 51,6% —
resultado: texto em cima da boca, que é o defeito que o usuário viu antes de
qualquer instrumento acusar.

O que se mede, em amostras ao longo do corte (Haar frontal, o mesmo detector do
`face_track.py`):
  · a linha do QUEIXO — não o centro do rosto: o que a legenda não pode invadir
    é a borda de baixo da cabeça, e ela varia quando a pessoa se inclina;
  · o percentil 90, e não o máximo: um quadro isolado de detecção duvidosa
    empurraria a legenda para o rodapé em todo vídeo.

E o teto de baixo é o RODAPÉ DA PLATAFORMA (~13% no Reels/TikTok/Shorts): a
legenda tem de caber ENTRE o queixo e a interface do app. Quando os dois limites
se cruzam — rosto baixo demais no quadro — não existe posição boa, e isso é dito
em vez de resolvido em silêncio.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

MARGEM = 0.022          # respiro entre o queixo e o topo da legenda (≈42px em 1920)
RODAPE_PLATAFORMA = 0.13  # faixa de baixo tomada pela interface do Instagram/TikTok
# altura do bloco por estilo, em fração da altura do quadro (medida nos renders)
BLOCO = {"dinamico": 0.17, "editorial": 0.16, "stacked": 0.20, "scatter": 0.18,
         "karaoke": 0.08, "simples": 0.08, "serifada": 0.08, "classica": 0.11,
         "pop": 0.09, "popLinha": 0.09, "popBloco": 0.11, "revelar": 0.09}


def medir(video: Path, amostras: int = 40) -> dict:
    import cv2
    cap = cv2.VideoCapture(str(video))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    casc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    queixos: list[float] = []
    for i in range(0, n, max(1, n // amostras)):
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ok, fr = cap.read()
        if not ok:
            continue
        g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
        fs = casc.detectMultiScale(g, 1.15, 5, minSize=(120, 120))
        if len(fs) == 0:
            continue
        x, y, w, h = max(fs, key=lambda f: f[2] * f[3])
        queixos.append((y + h) / H)
    cap.release()
    if not queixos:
        return {"rosto": False}
    queixos.sort()
    p90 = queixos[min(len(queixos) - 1, int(len(queixos) * 0.9))]
    return {"rosto": True, "amostras": len(queixos), "queixoP90": round(p90, 4),
            "queixoMediana": round(queixos[len(queixos) // 2], 4)}


def faixa(medida: dict, estilo: str) -> dict:
    bloco = BLOCO.get(estilo, 0.14)
    teto_baixo = 1.0 - RODAPE_PLATAFORMA - bloco      # topo máximo antes de a legenda entrar no rodapé
    if not medida.get("rosto"):
        return {"offsetY": round(min(0.62, teto_baixo), 3), "motivo": "sem rosto detectado — faixa padrão baixa"}
    piso = medida["queixoP90"] + MARGEM               # topo mínimo para não invadir o queixo
    if piso > teto_baixo:
        return {"offsetY": round(teto_baixo, 3), "conflito": True,
                "motivo": (f"queixo em {medida['queixoP90']:.3f} não deixa espaço acima do rodapé "
                           f"({teto_baixo:.3f}) — legenda no limite de baixo; considere reenquadrar")}
    return {"offsetY": round(piso, 3), "motivo": (f"queixo p90 {medida['queixoP90']:.3f} + margem "
                                                  f"{MARGEM} (bloco {bloco} · rodapé {RODAPE_PLATAFORMA})")}


def caixa_bate_no_rosto(video, top_px: int, altura_px: int = 320) -> dict:
    """A CAIXINHA COBRE A CABEÇA? — o usuário pediu para perguntar quando cobrir.

    Mede o TOPO da cabeça (não o queixo, como a legenda: o que a caixinha invade
    é a testa) e devolve o veredito com uma sugestão de topo alternativo, para a
    pergunta ao usuário já vir com saída — pergunta sem alternativa é só um aviso
    disfarçado.
    """
    import cv2
    cap = cv2.VideoCapture(str(video))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    casc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    topos = []
    for i in range(0, n, max(1, n // 30)):
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ok, fr = cap.read()
        if not ok:
            continue
        g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
        fs = casc.detectMultiScale(g, 1.15, 5, minSize=(120, 120))
        if len(fs):
            x, y, w, h = max(fs, key=lambda f: f[2] * f[3])
            topos.append(y / H)
    cap.release()
    if not topos:
        return {"rosto": False}
    topos.sort()
    p10 = topos[max(0, int(len(topos) * 0.1))]      # a cabeça mais ALTA do corte
    fundo_caixa = (top_px + altura_px) / H
    bate = fundo_caixa > p10
    # sugestão: subir a caixa até o fundo dela encostar no topo da cabeça
    sugerido = max(90, int(p10 * H) - altura_px - 24)
    return {"rosto": True, "topoCabecaP10": round(p10, 4), "fundoCaixa": round(fundo_caixa, 4),
            "bate": bate, "sugestaoTopPx": sugerido}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edit", type=Path)
    ap.add_argument("--aplicar", action="store_true", help="grava captions.offsetY no edit-data.json")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    edit = args.edit.resolve()
    video = edit / "preview.mp4"
    if not video.exists():
        sys.exit(f"não achei o corte em {video}")
    dp = edit / "hyperframes" / "edit-data.json"
    data = json.loads(dp.read_text()) if dp.exists() else {}
    estilo = (data.get("captions") or {}).get("style", "karaoke")

    medida = medir(video)
    rec = faixa(medida, estilo)
    if args.json:
        print(json.dumps({**medida, **rec, "estilo": estilo}, ensure_ascii=False))
    else:
        if medida.get("rosto"):
            print(f"rosto em {medida['amostras']} amostras · queixo mediana "
                  f"{medida['queixoMediana']:.3f} · p90 {medida['queixoP90']:.3f}")
        else:
            print("nenhum rosto detectado no corte")
        print(f"estilo {estilo} → offsetY {rec['offsetY']}  ({rec['motivo']})")
    if args.aplicar and dp.exists():
        data.setdefault("captions", {})["offsetY"] = rec["offsetY"]
        dp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        print(f"  aplicado em {dp.name}")


if __name__ == "__main__":
    main()

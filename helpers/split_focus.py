#!/usr/bin/env python3
"""Onde está o rosto — e, com isso, como enquadrar cada janela de tela dividida.

    uv run python helpers/split_focus.py <edit-dir>
    uv run python helpers/split_focus.py <edit-dir> --margem 40 --aplicar
    uv run python helpers/split_focus.py <edit-dir> --relatorio

O DEFEITO QUE ISTO EXISTE PARA MATAR: a faixa cobrindo o rosto.

Os pares `zoom`/`focusY` do `variants.json` vieram do projeto de origem desta
skill, onde o comentário que os acompanha diz, com todas as letras:

    "MEASURE THE SOURCE before trusting these numbers: ffmpeg a frame out of
     cut.mp4, read the hair-top and chin y... The values below fit a head ~660px
     tall starting at y 455."

Eles foram herdados sem essa medição. Num take desta série o cabelo começa em
y≈38 e o rosto tem ~800px — 420px acima do que os números pressupõem — então
tudo entre 38 e 400 caía atrás da faixa: testa, olhos e metade do nariz.

E o mecanismo que mediria isso estava desligado justamente onde é necessário: o
`face_track.py` só roda quando NÃO há tela dividida, sob a justificativa de que
"a tela dividida fixa o rosto por conta própria". Ela fixa numa posição — só não
sabia em qual.

A GEOMETRIA, depois que o `split.js` passou a montar o quadro inteiro em vez de
recortá-lo com `object-fit: cover` (o cover descartava 375px em cima e embaixo
ANTES do transform, e nenhum foco recupera pixel que não é desenhado):

    y_saída = topo_janela + (y_fonte − focusY) · zoom

Invertendo para o que se quer — o topo do cabelo pousando `margem` pixels abaixo
da costura:

    focusY = cabelo − margem / zoom

NADA AQUI É CONSTANTE DE UM VÍDEO. A medida sai do material, por JANELA e não
por projeto: num corte multi-take a cabeça se move — medido, ~170px entre
tomadas — e um valor único corta as tomadas altas e deixa vão sob a costura nas
baixas. O `variants.json` continua sendo o ponto de partida para quando não há
rosto detectável; o que ele deixa de ser é a palavra final.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HELPERS = Path(__file__).resolve().parent

# Folga entre a costura e o topo do cabelo. Zero encosta a cabeça na faixa, que
# lê como corte; muito mais que isso empurra o rosto para fora do quadro embaixo.
MARGEM_PADRAO = 40.0
# Teto de aproximação. Acima disto a imagem começa a mostrar o grão da fonte, e
# um rosto nítido mal enquadrado é melhor que um rosto borrado bem enquadrado.
ZOOM_MAX = 2.0
# Quantos quadros amostrar dentro de cada janela. A cabeça se mexe enquanto a
# pessoa fala; a mediana de alguns quadros é mais estável que um só.
AMOSTRAS = 5


def _cascade():
    import cv2
    return cv2.CascadeClassifier(
        os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml"))


def medir_cabeca(video: Path, t0: float, t1: float, n: int = AMOSTRAS):
    """(topo_do_cabelo, altura_do_rosto) medianos na janela, ou None.

    O topo do CABELO e não o da caixa: o Haar acha a região dos olhos/boca e
    corta o crânio. 35% da altura da caixa acima dela é a aproximação que o
    `face_track.py` já usa nesta skill para a linha dos olhos.
    """
    import cv2
    import statistics
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        return None
    casc = _cascade()
    topos, alturas = [], []
    for k in range(n):
        t = t0 + (t1 - t0) * (k + 0.5) / n
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, fr = cap.read()
        if not ok:
            continue
        g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
        caixas = casc.detectMultiScale(g, 1.1, 5, minSize=(120, 120))
        if len(caixas) == 0:
            continue
        x, y, w, h = max(caixas, key=lambda b: b[2] * b[3])
        topos.append(max(0.0, y - h * 0.35))
        alturas.append(float(h))
    cap.release()
    if not topos:
        return None
    return statistics.median(topos), statistics.median(alturas)


def enquadrar(cabelo: float, rosto_h: float, src_w: int, src_h: int,
              win_w: int, win_h: int, zoom_base: float,
              margem: float) -> tuple[float, float, str]:
    """(zoom, focusY, nota) para o cabelo pousar `margem` abaixo da costura.

    O modelo é o que o `split.css` sempre descreveu e o `split.js` passou a
    cumprir: o elemento é o QUADRO INTEIRO vezes o zoom, deslocado para que a
    linha `focusY` da fonte encoste no topo da janela.

        y_saída = topo_janela + (y_fonte − focusY) · zoom

    Invertendo para o alvo:  focusY = cabelo − margem / zoom

    (A versão anterior deste arquivo resolvia a equação errada, a do `object-fit:
    cover`, e por isso pedia focusY negativo de centenas de pixels — a conta
    tentava revelar um pixel que o cover já havia descartado.)

    Dois limites, os dois duros, porque violá-los abre tarja preta:
        focusY ≥ 0                       (não revelar acima do primeiro quadro)
        focusY ≤ altura_fonte − janela/zoom   (nem abaixo do último)
    """
    nota = ""

    # DUAS RESTRIÇÕES, e a ordem entre elas é a decisão inteira.
    #
    # A primeira tentativa aqui subia o zoom até abrir a folga pedida sob a
    # costura. Num take com o cabelo em y=11 isso exigia zoom 3,66; limitado a
    # 2,0, o resultado foi um rosto de 806px virando 1612px numa janela de
    # 1170 — folga perfeita no topo e o queixo fora do quadro. Ganhou-se a
    # margem e perdeu-se a cara.
    #
    # Então: CABER vence FOLGA. O zoom é escolhido para o rosto inteiro caber na
    # janela, e a margem fica com o que a geometria permitir — dita em voz alta
    # quando sai menor que a pedida. Um enquadramento sem folga ainda mostra a
    # pessoa; um com folga e sem queixo, não.
    zoom_cabe = (win_h - margem) / rosto_h if rosto_h > 1e-6 else zoom_base
    # Piso 1.0: abaixo disso o elemento fica mais estreito que a janela e abre
    # tarja nas laterais, porque a largura também é `fonte × zoom`.
    piso = max(1.0, win_w / src_w)
    zoom = max(piso, min(zoom_base, zoom_cabe, ZOOM_MAX))
    if zoom < zoom_base - 1e-6:
        nota = (f"zoom baixou de {zoom_base:.2f} para {zoom:.2f} — com mais que isso "
                f"o rosto ({rosto_h:.0f}px) não cabe na janela de {win_h:.0f}px")

    focus = cabelo - margem / zoom
    teto = src_h - win_h / zoom
    focus = max(0.0, min(focus, teto))

    folga = (cabelo - focus) * zoom
    if folga < margem - 1:
        extra = (f"folga de {folga:.0f}px em vez de {margem:.0f}: o cabelo está a "
                 f"y={cabelo:.0f} da fonte e não há quadro acima dele para revelar")
        nota = f"{nota}; {extra}" if nota else extra

    return round(zoom, 4), round(focus, 2), nota


def resolver(edit: Path, margem: float, verbose: bool = True) -> list[dict]:
    dados = json.loads((edit / "hyperframes" / "edit-data.json").read_text())
    inserts = dados.get("splitInserts") or []
    if not inserts:
        return []

    variants = json.loads((HELPERS.parent / "assets" / "styles" / "variants.json").read_text())
    corte = edit / dados.get("_video", "preview.mp4")
    if not corte.exists():
        corte = edit / "preview.mp4"
    if not corte.exists():
        raise SystemExit(f"corte não encontrado em {edit}")

    import cv2
    cap = cv2.VideoCapture(str(corte))
    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()

    out = []
    for it in inserts:
        lay = variants["split"].get(it.get("layout", "top"))
        if lay is None:
            continue
        band = lay["band"]
        win_h = src_h - band
        t0, t1 = float(it.get("start", 0)), float(it.get("end", 0))
        med = medir_cabeca(corte, t0, t1)
        if med is None:
            out.append({"start": t0, "end": t1, "ok": False,
                        "motivo": "nenhum rosto detectado na janela — "
                                  "fica o padrão do variants.json"})
            continue
        cabelo, altura = med
        zoom, focus, nota = enquadrar(cabelo, altura, src_w, src_h, src_w, win_h,
                                      float(lay["zoom"]), margem)
        out.append({"start": t0, "end": t1, "ok": True,
                    "cabelo": round(cabelo, 1), "rosto_h": round(altura, 1),
                    "zoom": zoom, "focusY": focus,
                    "zoom_antigo": lay["zoom"], "focus_antigo": lay["focusY"],
                    "nota": nota})
    return out


def aplicar(edit: Path, medidas: list[dict]) -> int:
    p = edit / "hyperframes" / "edit-data.json"
    dados = json.loads(p.read_text())
    n = 0
    for it, m in zip(dados.get("splitInserts") or [], medidas):
        if not m.get("ok"):
            continue
        it["zoom"], it["focusY"] = m["zoom"], m["focusY"]
        n += 1
    p.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    return n


def main() -> None:
    ap = argparse.ArgumentParser(description="Enquadra cada janela de tela dividida pelo rosto medido")
    ap.add_argument("edit", type=Path)
    ap.add_argument("--margem", type=float, default=MARGEM_PADRAO,
                    help=f"folga entre a costura e o topo do cabelo (padrão {MARGEM_PADRAO:.0f}px)")
    ap.add_argument("--aplicar", action="store_true", help="grava no edit-data.json")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    edit = args.edit.resolve()
    medidas = resolver(edit, args.margem)
    if args.json:
        print(json.dumps(medidas, ensure_ascii=False, indent=2))
    else:
        if not medidas:
            print("nenhuma janela de tela dividida neste projeto.")
            return
        print(f"{len(medidas)} janela(s) — margem pedida {args.margem:.0f}px\n")
        for m in medidas:
            faixa = f"{m['start']:6.2f}–{m['end']:6.2f}s"
            if not m.get("ok"):
                print(f"  {faixa}  {m['motivo']}")
                continue
            print(f"  {faixa}  cabelo y={m['cabelo']:.0f} rosto {m['rosto_h']:.0f}px  →  "
                  f"zoom {m['zoom_antigo']}→{m['zoom']}  focusY {m['focus_antigo']}→{m['focusY']}")
            if m["nota"]:
                print(f"              {m['nota']}")
    if args.aplicar:
        n = aplicar(edit, medidas)
        print(f"\n{n} janela(s) gravada(s) em hyperframes/edit-data.json")


if __name__ == "__main__":
    main()

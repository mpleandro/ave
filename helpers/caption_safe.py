#!/usr/bin/env python3
"""A FAIXA SEGURA DA LEGENDA — medida no rosto, não escolhida no olho.

    uv run python helpers/caption_safe.py <edit> [--aplicar] [--json]

Por que existe: um estilo de legenda traz uma altura de fábrica (o `bottom` ou o
`offsetY` do `variants.json`), e essa altura é uma média de material nenhum. No
PV a legenda `dinamico` nasce a 47% da altura e o queixo do apresentador está a
51,6% — resultado: texto em cima da boca, que é o defeito que o usuário viu
antes de qualquer instrumento acusar.

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

TRÊS COISAS QUE ESTAVAM ERRADAS AQUI, e que valem como regra (19/08/2026):

1. **Um número, quatro significados.** Cada estilo é ancorado de um jeito —
   px do fundo, fração até o topo do bloco, fração até o CENTRO, deslocamento a
   partir do meio do quadro — e este arquivo escrevia `offsetY` para todos
   tratando-o como topo. Resultado: o editorial e o disperso eram corrigidos
   pela METADE de um bloco (continuavam na boca) e o empilhado receberia um
   centro em 1,04 — o bloco inteiro fora do quadro. Agora a âncora é dado
   (`variants.styles.<id>.ancora`) e a conversão é explícita em `valor_para()`.

2. **As alturas eram o dobro.** A tabela à mão dizia 0.08 para o karaokê; o
   bloco mede 0.040 no render. Agora são MEDIDAS (`blocoMedido: true`), o que
   importa porque é a altura que decide se cabe entre o queixo e o rodapé.

3. **Corrigir sempre é pior que corrigir quando precisa.** Uma legenda de rodapé
   com o rosto no meio do quadro já está certa, e reposicioná-la "para aplicar a
   regra" só a aproximaria da cabeça. A medição responde onde o bloco está, se
   isso invade queixo ou rodapé, e só então para onde ele vai.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

MARGEM = 0.022          # respiro entre o queixo e o topo da legenda (≈42px em 1920)
RODAPE_PLATAFORMA = 0.13  # faixa de baixo tomada pela interface do Instagram/TikTok
ALTURA = 1920

# A ALTURA DO BLOCO E A ÂNCORA vêm do `variants.json`, onde moram os outros
# números dos estilos. Estavam aqui, numa tabela à mão, e o preço foi duplo:
# as alturas eram o dobro das reais (karaokê a 0.08 quando o bloco mede 0.040,
# medido no render) e a ÂNCORA nem existia — os quatro estilos cobertos têm
# três significados diferentes para o mesmo número, e este arquivo tratava
# todos como "topo do bloco". Ver `_ancoras_readme` no variants.json.
VARIANTS = json.loads(
    (Path(__file__).resolve().parent.parent / "assets" / "styles" / "variants.json").read_text())
ESTILOS = VARIANTS["styles"]
RODAPE_PADRAO = VARIANTS["bottom"]


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


def geometria(estilo: str) -> dict:
    """Onde o bloco DESTE estilo está hoje, em frações da altura do quadro.

    Converte a âncora de cada estilo — que são quatro coisas diferentes — em um
    par (topo, fundo) comparável. É o que faltava para a medição do rosto poder
    falar de todos os estilos na mesma língua.
    """
    st = ESTILOS.get(estilo) or {}
    bloco = st.get("bloco") or 0.09
    anc = st.get("ancora", "rodape")
    if anc == "rodape":
        fundo = 1.0 - (st.get("bottom", RODAPE_PADRAO) / ALTURA)
        topo = fundo - bloco
    elif anc == "topo":
        topo = st.get("offsetY", 0.47)
        fundo = topo + bloco
    elif anc == "centroDelta":
        centro = 0.5 + st.get("offsetY", 0.0)
        topo, fundo = centro - bloco / 2, centro + bloco / 2
    else:  # centro
        centro = st.get("offsetY")
        if centro is None:
            centro = (st.get("pal") or {}).get("centro", 0.5)
        topo, fundo = centro - bloco / 2, centro + bloco / 2
    return {"bloco": bloco, "ancora": anc, "topo": topo, "fundo": fundo,
            "medido": bool(st.get("blocoMedido"))}


def valor_para(estilo: str, topo: float, bloco: float) -> tuple[str, float]:
    """O número que ESTE estilo lê, para o bloco começar em `topo`.

    Devolve (chave do edit-data, valor). A chave muda com a âncora: quem senta
    no rodapé é movido por `paddingBottom` em px, e escrever `offsetY` para ele
    não teria efeito nenhum — silenciosamente.
    """
    anc = (ESTILOS.get(estilo) or {}).get("ancora", "rodape")
    if anc == "rodape":
        return "paddingBottom", round((1.0 - (topo + bloco)) * ALTURA)
    if anc == "topo":
        return "offsetY", round(topo, 4)
    if anc == "centroDelta":
        return "offsetY", round(topo + bloco / 2 - 0.5, 4)
    return "offsetY", round(topo + bloco / 2, 4)


def faixa(medida: dict, estilo: str) -> dict:
    """A posição segura, e — o ponto — SÓ quando a de fábrica não é.

    Uma legenda de rodapé com o rosto no meio do quadro já está certa; mexer
    nela para "aplicar a regra" só a aproximaria da cabeça. Então a medição
    responde três coisas e não uma: onde o bloco está, se isso invade o queixo
    ou o rodapé da plataforma, e — só nesse caso — para onde ele vai.
    """
    g = geometria(estilo)
    bloco = g["bloco"]
    fundo_max = 1.0 - RODAPE_PLATAFORMA
    topo_max = fundo_max - bloco

    if not medida.get("rosto"):
        # sem medida não há correção: o padrão do estilo é o melhor palpite que
        # existe, e sobrescrevê-lo com um número inventado seria pior que nada
        return {**g, "mexer": False,
                "motivo": "nenhum rosto detectado — a posição de fábrica fica"}

    topo_min = medida["queixoP90"] + MARGEM
    invade_rosto = g["topo"] < topo_min
    invade_rodape = g["fundo"] > fundo_max
    if not invade_rosto and not invade_rodape:
        return {**g, "mexer": False,
                "motivo": (f"bloco em {g['topo']:.3f}–{g['fundo']:.3f} já está abaixo do "
                           f"queixo ({medida['queixoP90']:.3f}) e acima do rodapé "
                           f"({fundo_max:.3f})")}

    conflito = topo_min > topo_max
    topo = topo_max if conflito else max(topo_min, min(g["topo"], topo_max))
    chave, valor = valor_para(estilo, topo, bloco)
    motivo = (f"queixo p90 {medida['queixoP90']:.3f} + margem {MARGEM}" if invade_rosto
              else f"bloco entrava no rodapé da plataforma ({fundo_max:.3f})")
    out = {**g, "mexer": True, "topoNovo": round(topo, 4), "chave": chave, "valor": valor,
           "motivo": motivo}
    if conflito:
        out["conflito"] = True
        out["motivo"] = (f"queixo em {medida['queixoP90']:.3f} não deixa espaço acima do "
                         f"rodapé ({fundo_max:.3f}) — legenda no limite de baixo, "
                         f"ainda encostando na cabeça; considere reenquadrar")
    return out


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
        alt = "medida" if rec.get("medido") else "estimada"
        print(f"estilo {estilo} · âncora {rec['ancora']} · bloco {rec['bloco']} ({alt}) "
              f"· {rec['topo']:.3f}–{rec['fundo']:.3f}")
        if rec["mexer"]:
            print(f"  → {rec['chave']} = {rec['valor']}  ({rec['motivo']})")
        else:
            print(f"  → nada a mexer  ({rec['motivo']})")
    if args.aplicar and dp.exists() and rec["mexer"]:
        data.setdefault("captions", {})[rec["chave"]] = rec["valor"]
        dp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        print(f"  aplicado em {dp.name}")


if __name__ == "__main__":
    main()

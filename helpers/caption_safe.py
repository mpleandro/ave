#!/usr/bin/env python3
"""A FAIXA SEGURA DA LEGENDA — medida no rosto, não escolhida no olho.

    uv run python helpers/caption_safe.py <edit> [--aplicar] [--json]
    uv run python helpers/caption_safe.py <edit> --caixinha [--aplicar]
    uv run python helpers/caption_safe.py <edit> --headline [--aplicar]

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


def geometria(estilo: str, ajuste: dict | None = None) -> dict:
    """Onde o bloco DESTE estilo está hoje, em frações da altura do quadro.

    Converte a âncora de cada estilo — que são quatro coisas diferentes — em um
    par (topo, fundo) comparável. É o que faltava para a medição do rosto poder
    falar de todos os estilos na mesma língua.

    `ajuste` sobrepõe chaves do catálogo (`bottom`, `offsetY`) — é por onde a
    checagem da HEADLINE pergunta onde a legenda está DE VERDADE neste
    projeto, com o `paddingBottom`/`offsetY` que a medição ou a mão já
    escreveram no edit-data, e não onde o catálogo a poria.
    """
    st = {**(ESTILOS.get(estilo) or {}), **(ajuste or {})}
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


def caixa_bate_no_rosto(video, top_px: int, altura_px: int = 320,
                        start: float = 0.0, end: float | None = None) -> dict:
    """A CAIXINHA COBRE A CABEÇA? — o usuário pediu para perguntar quando cobrir.

    Mede o TOPO da cabeça (não o queixo, como a legenda: o que a caixinha invade
    é a testa) e devolve o veredito com uma sugestão de topo alternativo, para a
    pergunta ao usuário já vir com saída — pergunta sem alternativa é só um aviso
    disfarçado.

    `start`/`end` (segundos) escopam a amostragem para a JANELA em que a
    caixinha aparece — não o vídeo inteiro. Importa quando `zoomAuto`/
    `zoomCuts` está ligado: a câmera dinâmica aperta o enquadramento em
    cortes que podem estar bem depois de a caixinha já ter saído de tela, e
    medir o vídeo inteiro sugeriria uma posição mais alta do que o
    necessário, ou pior, deixaria passar um aperto que acontece justamente
    DENTRO da janela da caixinha (medido: o aperto real ficava em ~76-86s,
    fora dos primeiros segundos que uma amostragem só-do-início cobriria).
    """
    import cv2
    cap = cv2.VideoCapture(str(video))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    n_total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    f0 = max(0, int(start * fps))
    f1 = n_total if end is None else min(n_total, int(end * fps))
    n = max(1, f1 - f0)
    casc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    topos = []
    for i in range(f0, f1, max(1, n // 30)):
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
    p10 = topos[max(0, int(len(topos) * 0.1))]      # a cabeça mais ALTA na janela
    fundo_caixa = (top_px + altura_px) / H
    bate = fundo_caixa > p10
    # sugestão: subir a caixa até o fundo dela encostar no topo da cabeça
    sugerido = max(90, int(p10 * H) - altura_px - 24)
    return {"rosto": True, "topoCabecaP10": round(p10, 4), "fundoCaixa": round(fundo_caixa, 4),
            "bate": bate, "sugestaoTopPx": sugerido}


def _altura_estimada_caixinha() -> int:
    """Estimativa de altura total do adesivo (px), pelo pior caso — 2 linhas
    de pergunta. `faixaAltura` cobre só a faixa escura; o corpo branco soma
    padding dos dois lados mais a altura das linhas de texto."""
    cx = VARIANTS.get("caixinha", {})
    return round(cx.get("faixaAltura", 132) + cx.get("corpoPadding", 44) * 2
                + cx.get("corpoTamanho", 47) * cx.get("corpoEntrelinha", 1.28) * 2)


# ─────────────────────────────────────────────────────────────────────────────
# A HEADLINE TAMBÉM NÃO PODE CAIR SOBRE O ROSTO (pedido do usuário, 14/10/2026:
# "ela só cuida da legenda e da Caixinha; a headline nunca foi incluída").
#
# A headline do gancho é o primeiro texto que o espectador lê, e nasce no ALTO
# do quadro (`top` 190–360px no catálogo) — exatamente a faixa onde mora a
# testa de quem grava em plano médio. A legenda olha o queixo, a caixinha olha
# a testa; a headline, que é um bloco de várias linhas no meio dessa zona,
# precisa olhar OS DOIS: o que ela não pode cobrir é o rosto inteiro, do topo
# da cabeça ao queixo.
#
# Quem participa: só as headlines que ficam POR CIMA do vídeo — as bandas
# antigas (`.ave-hook`) e as cartelas com `cheia: false` (fita, jornal,
# terminal, …). A cartela de TELA CHEIA não entra: ela É o quadro (a chapa
# cobre o vídeo inteiro enquanto está no ar) e o `top` não a move — o bloco
# dela é centrado por flex, com margens próprias.
# ─────────────────────────────────────────────────────────────────────────────

# Folga de ALTURA além das linhas, em px de 1920, por família de desenho. É
# estimativa (como a da caixinha), não medida de render: as linhas saem da
# MESMA conta do compositor (`hl_fit`/`hl_ks`), e o que sobra — o padding das
# peças (fita 38×2, cartão 44+50, painel 34×2, chapa 34×2, balão 40×2, folha
# da notícia 54+62 + barra) e as tarjas das bandas — fica num teto generoso,
# porque errar para MAIS só afasta a headline do rosto; errar para menos a
# deixaria encostar nele.
HL_FOLGA_BANDA = 0.25     # × corpo: tarja/caixa/descendentes das bandas antigas
HL_FOLGA_PECA = 120       # px: padding da peça (fita, cartão, painel, balão…)
HL_FOLGA_OLHO = 70        # px: a sobrancelha (`ct-olho`) quando existe
HL_FOLGA_CAIXA = 60       # px: banda com caixa por trás (`card`: padding 28×2)


def geometria_headline(data: dict) -> dict:
    """Onde o bloco da headline está, em px de quadro — pela MESMA conta do
    compositor, não por uma segunda tabela que envelheceria longe dele.

    Reproduz os passos de `hook_markup()` em `compose_shortform.py` que mexem
    em posição e tamanho: o `top` (do edit-data, senão do catálogo), o piso da
    área segura do topo, o arrasto do editor (`dy`/`scale`) e o corpo medido
    das linhas (`hl_fit`/`hl_ks`). Devolve `{"pula": motivo}` quando a
    headline não é coisa que se mova contra o rosto.
    """
    import compose_shortform as cs
    import area_segura

    hook = data.get("hook") or {}
    if not hook.get("enabled"):
        return {"pula": "headline desligada"}
    style_id = hook.get("style", "card")
    h = VARIANTS["headlines"].get(style_id)
    if h is None:
        return {"pula": f"estilo de headline '{style_id}' não existe"}
    # TELA CHEIA: a chapa cobre o vídeo, não há rosto atrás — EXCETO quando o
    # projeto a deixou transparente: `semFundo` (sem a chapa), ou a capa
    # desfocada com `semBlur` (a chapa dela É o desfoque; a `ct-fundo` nem é
    # emitida para quem tem `blur`). Aí o texto passa a ficar direto sobre o
    # vídeo, e o rosto volta a importar. Achado no primeiro teste desta
    # regra: "5 conteudos para autoridade" usa `capa_blur` + `semFundo` +
    # `semBlur` + `posicao: centro` — o texto inteiro no meio do quadro.
    pecas = h.get("pecas") or []
    transparente = bool(hook.get("semFundo")) or ("blur" in pecas and hook.get("semBlur"))
    if h.get("cheia") and ("svg" in pecas or not transparente):
        return {"pula": f"'{style_id}' é cartela de tela cheia — cobre o vídeo, não há rosto atrás"}
    H = int(data.get("height", ALTURA))
    end = float(hook.get("endSec", 4.0))
    # Tela dividida no ar durante o gancho: quem decide a altura é o layout
    # (`split.<layout>.hookTop`, na costura) — mexer no `hook.top` não teria
    # efeito nenhum, e dizer "movi" seria mentira.
    for it in (data.get("splitInserts") or []):
        if float(it.get("start", 0)) < end:
            return {"pula": "tela dividida durante o gancho — a altura é a do layout"}

    h = {**h, **{k: hook[k] for k in ("cap", "safeW", "paint", "weights", "sizes") if k in hook}}
    h = cs._hl_seguro(h, data)
    if h.get("heroMid") and hook.get("hero") is not None:
        h["heroIndex"] = hook["hero"]
    if h.get("heroMid") and hook.get("lineK"):
        h["lineK"] = hook["lineK"]
    fonts = {"main": hook.get("fontMain") or VARIANTS["headlineFamily"],
             "accent": hook.get("fontAccent") or VARIANTS["headlineAccentFamily"]}

    extra = 0.0
    if h.get("motor") == "cartela":
        partes = cs.cartela_slots(hook, h)
        linhas = ([partes["titulo"]] if h.get("linhaUnica") and "/" not in partes["titulo"]
                  else cs.hl_lines(partes["titulo"], h))
        linhas = [x for x in linhas if x] or [""]
        if h.get("pecas"):
            extra += HL_FOLGA_PECA
        if partes["olho"]:
            extra += HL_FOLGA_OLHO
        if partes["meta"]:
            extra += HL_FOLGA_OLHO * len(partes["meta"])
    else:
        linhas = [x for x in (hook.get("lines") or []) if x]
        if len(linhas) <= 1:
            linhas = cs.hl_lines(linhas[0] if linhas else (hook.get("text") or ""), h)
        linhas = [x for x in linhas if x]
    if not linhas or not any(linhas):
        return {"pula": "headline sem texto"}
    linhas = [x.upper() if cs.hl_is_upper(i, len(linhas), h) else x
              for i, x in enumerate(linhas)]
    size = cs.hl_fit(linhas, h, fonts)
    ks = cs.hl_ks(linhas, h)
    if h.get("motor") != "cartela":
        if h.get("heroLast"):
            ks[-1] = cs.hl_hero_size(linhas, h, fonts) / size
        extra += HL_FOLGA_BANDA * size
        if any(c in (h.get("paint") or {}) for c in ("box", "tagBox", "heroBox")):
            extra += HL_FOLGA_CAIXA

    if h.get("cheia"):
        # Tela cheia transparente NÃO TEM `top`: o bloco é posto por flex em
        # cartela.css — no alto com `padding-top: 170px` (o padrão do
        # `semFundo`, "para não cobrir o rosto") ou centrado com `posicao:
        # "centro"` (padding 120px dos dois lados, logo centro = meio do
        # quadro). Também não se arrasta (`dy`/`scale` não valem para ela). A
        # checagem aqui só INFORMA: a saída é trocar a `posicao`, ligar o fundo
        # ou escolher outro estilo, e as três são escolhas de desenho do
        # usuário — não se resolvem escrevendo um número.
        altura = sum(ks) * size * float(h["lh"]) + extra
        topo = (H - altura) / 2 if hook.get("posicao") == "centro" else 170.0
        return {"estilo": style_id, "linhas": len(linhas), "corpo": round(size, 1),
                "topoPx": round(topo), "alturaPx": round(altura),
                "fundoPx": round(topo + altura), "end": end, "H": H, "fixa": True}

    top = float(hook.get("top", h["top"]))
    if area_segura.vale(data):
        top = max(top, area_segura.topo_minimo(H))
    # O arrasto do editor: `hook_markup` escreve `--hl-top: (top - dy)/k` e a
    # folha multiplica por `--hl-scale: k`, então o topo real é `top - dy` e
    # só a ALTURA cresce com a escala.
    k = min(1.6, max(0.5, float(hook.get("scale") or 1)))
    topo = top - float(hook.get("dy") or 0)
    altura = (sum(ks) * size * float(h["lh"]) + extra) * k
    return {"estilo": style_id, "linhas": len(linhas), "corpo": round(size, 1),
            "topoPx": round(topo), "alturaPx": round(altura), "fundoPx": round(topo + altura),
            "end": end, "H": H}


def rosto_na_janela(video, start: float = 0.0, end: float | None = None,
                    amostras: int = 30) -> dict:
    """Topo da cabeça (p10 — a mais ALTA) E queixo (p90 — o mais BAIXO) numa
    janela do corte. A legenda só precisa do queixo e a caixinha só do topo;
    a headline precisa do rosto inteiro, porque o bloco dela pode cair em
    cima dele por qualquer um dos dois lados. Mesmo detector, mesmos
    percentis, mesma razão: um quadro de detecção duvidosa não decide."""
    import cv2
    cap = cv2.VideoCapture(str(video))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    n_total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    f0 = max(0, int(start * fps))
    f1 = n_total if end is None else min(n_total, int(end * fps))
    n = max(1, f1 - f0)
    casc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    topos: list[float] = []
    queixos: list[float] = []
    for i in range(f0, f1, max(1, n // amostras)):
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ok, fr = cap.read()
        if not ok:
            continue
        g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY)
        fs = casc.detectMultiScale(g, 1.15, 5, minSize=(120, 120))
        if len(fs):
            x, y, w, h = max(fs, key=lambda f: f[2] * f[3])
            topos.append(y / H)
            queixos.append((y + h) / H)
    cap.release()
    if not topos:
        return {"rosto": False}
    topos.sort()
    queixos.sort()
    return {"rosto": True, "amostras": len(topos),
            "topoCabecaP10": round(topos[max(0, int(len(topos) * 0.1))], 4),
            "queixoP90": round(queixos[min(len(queixos) - 1, int(len(queixos) * 0.9))], 4)}


def _topo_legenda(data: dict) -> float | None:
    """Onde a legenda começa NESTE projeto (fração), com o ajuste do edit-data
    — inclusive o que a própria medição do queixo acabou de escrever. É o
    chão da headline quando ela tem de descer para baixo do rosto: as duas
    não podem disputar a mesma faixa."""
    caps = data.get("captions") or {}
    if not caps.get("enabled", True):
        return None
    ajuste = {}
    if "paddingBottom" in caps:
        ajuste["bottom"] = caps["paddingBottom"]
    if "offsetY" in caps:
        ajuste["offsetY"] = caps["offsetY"]
    return geometria(caps.get("style", "karaoke"), ajuste)["topo"]


def headline_bate_no_rosto(video, data: dict) -> dict:
    """A HEADLINE COBRE O ROSTO? E, se cobre, para onde ela vai.

    Mede o rosto só na JANELA em que a headline está no ar — do 0 ao
    `hook.endSec`, no tempo do corte, o mesmo relógio da composição (a
    headline nasce em `data-start="0"`). Medir o vídeo inteiro deixaria um
    aperto da câmera dinâmica lá no minuto 1 decidir onde fica um texto que
    saiu de cena aos 4 segundos — o mesmo erro corrigido na caixinha.

    A ordem das saídas é a do desenho: a headline é um texto do ALTO, então a
    primeira tentativa é ACIMA da cabeça, se couber abaixo da área segura do
    topo (interface do app). Não cabendo, ABAIXO do queixo, se couber acima
    da legenda e do rodapé da plataforma. Não cabendo em nenhum dos dois, NÃO
    se resolve em silêncio: `conflito` sai com o motivo, e a posição fica a de
    fábrica para o usuário decidir (reenquadrar, encurtar o texto, uma
    cartela de tela cheia, ou `hook.top` à mão).
    """
    import area_segura

    g = geometria_headline(data)
    if g.get("pula"):
        return {"mexer": False, "pula": True, "motivo": g["pula"]}
    H = g["H"]
    rosto = rosto_na_janela(video, 0.0, g["end"])
    base = {**g, **rosto}
    if not rosto.get("rosto"):
        return {**base, "mexer": False,
                "motivo": "nenhum rosto detectado na janela da headline — a posição de fábrica fica"}

    margem = MARGEM * H
    cabeca = rosto["topoCabecaP10"] * H
    queixo = rosto["queixoP90"] * H
    topo, fundo, altura = g["topoPx"], g["fundoPx"], g["alturaPx"]
    # O TESTE é sem folga, como o da caixinha (`fundo > topo da cabeça`): só
    # conta como "cobre" o bloco que entra de fato no retângulo do rosto. A
    # folga (`MARGEM`) vale para ONDE ele vai, não para decidir se sai — com
    # ela no teste, um bloco a 20px da testa virava conflito sem estar em
    # cima de nada.
    if fundo <= cabeca or topo >= queixo:
        return {**base, "mexer": False,
                "motivo": (f"headline em {topo}–{fundo}px fica fora do rosto "
                           f"({cabeca:.0f}–{queixo:.0f}px)")}

    if g.get("fixa"):
        return {**base, "mexer": False, "conflito": True,
                "motivo": (f"a cartela '{g['estilo']}' está sem chapa (semFundo/semBlur) e "
                           f"o texto ({topo}–{fundo}px) cobre o rosto "
                           f"({cabeca:.0f}–{queixo:.0f}px) — ela não tem `top` para mover; "
                           f"troque `hook.posicao` (alto/centro), devolva o fundo "
                           f"ou use uma headline de banda")}

    teto = area_segura.topo_minimo(H) if area_segura.vale(data) else 0.0
    acima = cabeca - margem - altura
    if acima >= teto:
        return {**base, "mexer": True, "lado": "acima", "sugestaoTopPx": round(acima),
                "motivo": (f"headline ({topo}–{fundo}px) cobria o rosto "
                           f"({cabeca:.0f}–{queixo:.0f}px) → sobe para acima da cabeça")}

    chao = H - (area_segura.base_minima(H) if area_segura.vale(data) else RODAPE_PLATAFORMA * H)
    leg = _topo_legenda(data)
    if leg is not None:
        chao = min(chao, leg * H - margem)
    abaixo = queixo + margem
    if abaixo + altura <= chao:
        return {**base, "mexer": True, "lado": "abaixo", "sugestaoTopPx": round(abaixo),
                "motivo": (f"headline ({topo}–{fundo}px) cobria o rosto "
                           f"({cabeca:.0f}–{queixo:.0f}px) e não cabe acima da cabeça "
                           f"(área segura em {teto:.0f}px) → desce para abaixo do queixo")}

    return {**base, "mexer": False, "conflito": True,
            "motivo": (f"a headline ({altura}px de altura) cobre o rosto "
                       f"({cabeca:.0f}–{queixo:.0f}px) e não cabe nem acima da cabeça "
                       f"(sobram {max(0, cabeca - margem - teto):.0f}px abaixo da área "
                       f"segura) nem entre o queixo e a legenda/rodapé "
                       f"(sobram {max(0, chao - abaixo):.0f}px) — posição atual "
                       f"mantida; considere encurtar o texto, uma cartela de tela "
                       f"cheia, reenquadrar ou `hook.top` à mão")}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edit", type=Path)
    ap.add_argument("--aplicar", action="store_true", help="grava captions.offsetY no edit-data.json")
    ap.add_argument("--caixinha", action="store_true",
                    help="checa a Caixinha de perguntas contra o rosto (em vez da legenda)")
    ap.add_argument("--headline", action="store_true",
                    help="checa a headline do gancho contra o rosto (em vez da legenda)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    edit = args.edit.resolve()
    video = edit / "preview.mp4"
    if not video.exists():
        sys.exit(f"não achei o corte em {video}")
    dp = edit / "hyperframes" / "edit-data.json"
    data = json.loads(dp.read_text()) if dp.exists() else {}

    if args.caixinha:
        cx = data.get("questionBox") or {}
        if not cx.get("pergunta"):
            sys.exit("sem questionBox.pergunta — nada para checar")
        top_px = int(cx.get("top", VARIANTS.get("caixinha", {}).get("topoPadrao", 300)))
        altura_px = _altura_estimada_caixinha()
        start = float(cx.get("start", 0.0))
        end = cx.get("end")
        rec = caixa_bate_no_rosto(video, top_px, altura_px, start=start,
                                  end=float(end) if end is not None else None)
        if args.json:
            print(json.dumps(rec, ensure_ascii=False))
        elif not rec.get("rosto"):
            print("nenhum rosto detectado na janela da caixinha")
        elif rec["bate"]:
            print(f"  caixinha bate na cabeça (topo da cabeça a {rec['topoCabecaP10']:.3f}, "
                  f"caixinha desce até {rec['fundoCaixa']:.3f}) → sugestão: top={rec['sugestaoTopPx']}px")
        else:
            print(f"  nada a mexer — caixinha (fundo {rec['fundoCaixa']:.3f}) não invade "
                  f"a cabeça (topo {rec['topoCabecaP10']:.3f})")
        if args.aplicar and dp.exists() and rec.get("rosto") and rec["bate"]:
            data.setdefault("questionBox", {})["top"] = rec["sugestaoTopPx"]
            dp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
            print(f"  aplicado em {dp.name}")
        return

    if args.headline:
        hook = data.get("hook") or {}
        rec = headline_bate_no_rosto(video, data)
        # VALOR POSTO À MÃO VENCE A MEDIÇÃO, como em toda regra desta família:
        # `hook.top` escrito no edit-data, ou `hook.dy` vindo do arrasto no
        # editor, é decisão de alguém — a medição só informa.
        manual = "top" in hook or "dy" in hook
        if args.json:
            print(json.dumps({**rec, "manual": manual}, ensure_ascii=False))
        elif rec.get("pula"):
            print(f"  headline: nada a checar ({rec['motivo']})")
        else:
            if rec.get("rosto"):
                print(f"  headline {rec['estilo']} · {rec['linhas']} linha(s) · corpo "
                      f"{rec['corpo']} · bloco {rec['topoPx']}–{rec['fundoPx']}px (estimado) "
                      f"· rosto {rec['topoCabecaP10']:.3f}–{rec['queixoP90']:.3f} "
                      f"em {rec['amostras']} amostras até {rec['end']:.1f}s")
            if rec.get("mexer"):
                print(f"  → hook.top = {rec['sugestaoTopPx']}  ({rec['motivo']})")
            elif rec.get("conflito"):
                print(f"  ATENÇÃO — headline sem posição boa: {rec['motivo']}")
            else:
                print(f"  → nada a mexer  ({rec['motivo']})")
            if manual and rec.get("mexer"):
                print("  posição da headline posta à mão (hook.top/dy) — não sobrescrevo")
        if args.aplicar and dp.exists() and rec.get("mexer") and not manual:
            data.setdefault("hook", {})["top"] = rec["sugestaoTopPx"]
            dp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
            print(f"  aplicado em {dp.name}")
        return

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

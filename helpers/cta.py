#!/usr/bin/env python3
"""CTA DE FECHAMENTO — a última camada da aba Estilo.

    uv run python helpers/cta.py preparar [--card <mov>] [--simples <mov>]
    uv run python helpers/cta.py foto <edit> <imagem>
    uv run python helpers/cta.py foto <edit> --quadro <segundos>

Três modelos, escolhidos na aba CTA do editor e gravados em `edit-data.json →
cta`:

| id                  | o que o espectador vê                                  | foto |
|---------------------|--------------------------------------------------------|------|
| `siga-perfil`       | cápsula escura no topo que abre a partir da foto,      | sim  |
|                     | "Siga o perfil" + @, cursor aperta "Seguir"            |      |
| `instagram-card`    | o ícone do Instagram vira um cartão com foto, @ e      | sim  |
|                     | "Seguir → Seguindo", e fecha                           |      |
| `instagram-simples` | só o botão "Seguir → Seguindo"                         | não  |

O `siga-perfil` nasceu sob medida no "Mais viral, mais raso" (2026-10-13) e
virou modelo: mesmo HTML, com foto, @ e cor de destaque como variáveis.

O CARD VEM DE UM VÍDEO EM CHROMAKEY, e não pode ser usado como veio por dois
motivos. O verde não sai com `blend` (README dos overlays, Hard Rule 16) — tem
de virar alfa. E a foto e o @ do autor estavam GRAVADOS no vídeo: qualquer
outro usuário entregaria o rosto e o nome de outra pessoa. `preparar` resolve
os dois de uma vez, e só uma vez, no asset da biblioteca:

  1. tira o verde (alfa de verdade, WebM VP9 `yuva420p`);
  2. mede, quadro a quadro, o círculo da foto, a faixa do @ e o miolo preto do
     cartão — a foto cresce na entrada, pulsa no clique e desce no fechamento,
     e o @ entra digitado;
  3. pinta de PRETO a foto e o @ gravados (o miolo do cartão já é preto, então
     o buraco não aparece);
  4. grava o mapa em `assets/cta/instagram-card.json`.

Na composição, a foto do usuário e o @ dele entram em HTML por cima, nas
posições do mapa. Nada é queimado com ffmpeg no vídeo do projeto (Hard Rule
10): o que se processou aqui foi o ASSET, uma vez, para a biblioteca.

A FOTO é do projeto, não da biblioteca: `hyperframes/cta/perfil.png`. Chega
pelo editor (subir arquivo, capturar o quadro do vídeo, colar um print) ou por
`cta.py foto`. Sem ela, os dois modelos que pedem foto são RECUSADOS pela Fase 2
— entregar o cartão com um buraco no lugar do rosto lê como render quebrado.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
CTA_DIR = SKILL / "assets" / "cta"
OVERLAYS = SKILL / "assets" / "overlays"

# `clique` é o segundo, DENTRO do modelo, em que o botão é apertado — é ele que
# se alinha com a palavra "segue/siga" da fala. `largura` é a fração da largura
# do quadro; `topo`, a borda de cima em fração da altura.
MODELOS = {
    "siga-perfil": {"nome": "Siga o perfil", "foto": True, "duracao": 5.8,
                    "clique": 5.08, "html": "siga-perfil.html"},
    "instagram-card": {"nome": "Instagram Card", "foto": True, "duracao": 4.96,
                       "clique": 2.54, "html": "instagram-card.html",
                       "video": "instagram-card.webm", "audio": "instagram-card.mp3",
                       "largura": 0.52, "topo": 0.12},
    "instagram-simples": {"nome": "Instagram Simples", "foto": False, "duracao": 3.0,
                          "clique": 1.33, "video": "ig_follow.mov",
                          "audio": "instagram-simples.mp3",
                          "largura": 0.5, "topo": 0.72},
    # RECUO PARA O APP (Pull-Back Reveal, motor de efeitos 2026-10-15): o vídeo
    # recua para dentro de uma janela de editor e um cartão de seguir é clicado.
    # Mexe no `#vidwin` da composição principal — por isso quem monta é o
    # efeitos_compose.py, não uma sub-composição daqui. A foto é opcional.
    "revelarApp": {"nome": "Recuo para o app", "foto": False, "duracao": 4.2,
                   "clique": 2.6, "motor": "efeitos"},
}

# Palavras que pedem o clique. Raiz e não lista fechada: "segue", "siga",
# "seguir", "sigam", "me segue" — a fala muda, o verbo não.
CLIQUE_RE = re.compile(r"^(segu|sig[ao])", re.I)

FOTO_REL = "cta/perfil.png"

# CHAMADAS para ação — onde um CTA pode cair (pedido do usuário, 2026-10-15:
# "alguns acontecem no meio do vídeo; a IA precisa interpretar onde está sendo
# feita a chamada"). A lista só ACHA candidatas; quem decide qual é a chamada de
# verdade é a IA lendo a fala, e grava `cta.momento` (o segundo da palavra).
CHAMADA_RE = re.compile(
    r"\b(me segue|segue|siga|seguir|sigam|comenta|comente|comentar|comentem|salva|salve|salvar|"
    r"compartilha|compartilhe|manda (?:pra|para|esse)|marca (?:alguem|um amigo|uma amiga|quem)|"
    r"link (?:na|da) bio|clica|clique|toca|toque|inscreva|inscrever|sininho|deixa (?:seu|o) like|"
    r"curte|curta|arrasta|chama no direct|me chama)\b")


def chamadas(edit: Path) -> list[dict]:
    """Frases da fala com cara de chamada, com o segundo da palavra-gatilho."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import explicativo as X
    ws = X.palavras(edit)
    out = []
    for f in X.frases(ws):
        t = X._norm(f["texto"])
        m = CHAMADA_RE.search(t)
        if not m:
            continue
        at = X._achar(ws, m.group(1), f["start"] - 0.05, f["end"] + 0.05)
        out.append({"start": round(f["start"], 2), "end": round(f["end"], 2),
                    "momento": round(at if at is not None else f["start"], 2),
                    "gatilho": m.group(1), "texto": f["texto"]})
    return out


def foto_do_projeto(proj: Path) -> Path | None:
    p = proj / FOTO_REL
    return p if p.exists() else None


# ---------------------------------------------------------------- preparar

VERDE = "0x21FD00"   # medido no canto do ig_follow_profile.mov (BGR 0,253,33)


def _medir_card(frames: list[Path]) -> list[dict]:
    """O mapa do card: círculo da foto, faixa do @ e miolo, por quadro.

    A foto é o maior componente REDONDO de pixels não-pretos e pouco saturados
    (o anel em volta é saturado e fica de fora; o vão preto entre os dois os
    separa). `minEnclosingCircle` dá o círculo, e ele bate em ±0,5px nos
    quadros parados — medido.
    """
    import cv2
    import numpy as np

    mapa = []
    for p in frames:
        a = cv2.imread(str(p))
        b, g, r = (a[..., i].astype(int) for i in range(3))
        mx = a.max(-1).astype(int)
        mn = a.min(-1).astype(int)
        sat = (mx - mn) / np.maximum(mx, 1)
        verde = (g > 150) & (r < 120) & (b < 120)
        preto = mx < 18
        q: dict = {"miolo": None, "foto": None, "arroba": None}
        linhas = np.where(preto.sum(1) > 40)[0]
        colunas = np.where(preto.sum(0) > 40)[0]
        if len(linhas) > 10 and len(colunas) > 10:
            q["miolo"] = [int(colunas[0]), int(linhas[0]), int(colunas[-1]), int(linhas[-1])]
        anel = (sat > 0.55) & (mx > 90)
        m = ((mx > 14) & ~verde & ~anel).astype(np.uint8)
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        n, lab, st, _ = cv2.connectedComponentsWithStats(m, 8)
        melhor = None
        for i in range(1, n):
            x, y, w, h, area = st[i]
            if area < 150 or w > 300 or h > 300:
                continue
            if area / (np.pi * (max(w, h) / 2) ** 2) < 0.6 or abs(w - h) > 0.25 * max(w, h):
                continue
            if melhor is None or area > melhor[1]:
                melhor = (i, area)
        if melhor and q["miolo"]:
            ys, xs = np.where(lab == melhor[0])
            (cx, cy), raio = cv2.minEnclosingCircle(np.stack([xs, ys], 1).astype(np.float32))
            q["foto"] = [round(float(cx), 1), round(float(cy), 1), round(float(raio), 1)]
            # O @: branco/azul (selo) numa faixa logo abaixo da foto e acima do
            # botão. O topo do botão vem do primeiro azul cheio abaixo da foto.
            azul_cheio = (b > 200) & (r < 60)
            base = int(cy + raio)
            fundo_botao = q["miolo"][3]
            for y in range(base + 10, q["miolo"][3]):
                if azul_cheio[y].sum() > 100:
                    fundo_botao = y
                    break
            cinza_botao = (np.abs(b - g) < 10) & (b > 30) & (b < 80)
            for y in range(base + 10, fundo_botao):
                if cinza_botao[y].sum() > 100:
                    fundo_botao = y
                    break
            branco = (mx > 150) & (sat < 0.3)
            selo = (b > 180) & (r < 90) & (g > 90)
            y0, y1 = base + 12, min(base + 110, fundo_botao - 3)
            faixa = np.zeros_like(branco)
            x0m, _, x1m, _ = q["miolo"]
            faixa[y0:y1, x0m:x1m] = (branco | selo)[y0:y1, x0m:x1m]
            rr = np.where(faixa.sum(1) > 0)[0]
            cc = np.where(faixa.sum(0) > 0)[0]
            if len(rr):
                q["arroba"] = [int(cc[0]), int(rr[0]), int(cc[-1]), int(rr[-1])]
        mapa.append(q)
    return mapa


def _pintar(frames: list[Path], mapa: list[dict]) -> None:
    """Apaga a foto e o @ gravados, quadro a quadro, com o preto do miolo."""
    import cv2
    import numpy as np

    for p, q in zip(frames, mapa):
        a = cv2.imread(str(p))
        if q["foto"]:
            cx, cy, r = q["foto"]
            cv2.circle(a, (round(cx), round(cy)), int(r + 2), (0, 0, 0), -1, cv2.LINE_AA)
        if q["arroba"]:
            x0, y0, x1, y1 = q["arroba"]
            a[y0 - 4:y1 + 5, x0 - 6:x1 + 7] = 0
        # FECHAMENTO: a foto desce e é cortada pela borda do miolo, e nesse
        # pedaço ela deixa de ser redonda e o detector a perde. Tudo o que for
        # claro e pouco saturado abaixo do letreiro, dentro do miolo, é resto
        # de foto ou de @ — vai para o preto também.
        if q["miolo"] and not q["foto"]:
            x0, y0, x1, y1 = q["miolo"]
            mx = a.max(-1).astype(int)
            sat = (mx - a.min(-1).astype(int)) / np.maximum(mx, 1)
            corte = y0 + int(0.42 * (y1 - y0))
            zona = np.zeros(mx.shape, bool)
            zona[corte:y1 + 1, x0:x1 + 1] = True
            a[zona & (mx > 14) & (sat < 0.6)] = 0
        cv2.imwrite(str(p), a)


def _fps(src: Path) -> str:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                          "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0",
                          str(src)], capture_output=True, text=True).stdout.strip()
    return out or "24000/1001"


def preparar_card(src: Path, tmp: Path) -> None:
    frames_dir = tmp / "card"
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vsync", "0",
                    str(frames_dir / "%04d.png")], check=True)
    frames = sorted(frames_dir.glob("*.png"))
    mapa = _medir_card(frames)
    # O @ final, quando o cartão está parado: é a caixa que o @ do usuário
    # ocupa por inteiro, e a referência para medir quanto da digitação já
    # apareceu em cada quadro.
    parados = [q["arroba"] for q in mapa if q["arroba"] and q["foto"]
               and abs(q["foto"][2] - 94.6) < 0.6]
    final = max(parados, key=lambda c: (c[2] - c[0], -c[1])) if parados else None
    _pintar(frames, mapa)
    fps = _fps(src)
    CTA_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        "ffmpeg", "-v", "error", "-y", "-framerate", fps, "-i", str(frames_dir / "%04d.png"),
        "-vf", f"chromakey={VERDE}:0.16:0.06,despill=type=green,format=yuva420p",
        "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-auto-alt-ref", "0",
        "-b:v", "0", "-crf", "24", "-row-mt", "1",
        str(CTA_DIR / "instagram-card.webm")], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vn",
                    "-c:a", "libmp3lame", "-q:a", "3", str(CTA_DIR / "instagram-card.mp3")],
                   check=True)
    num, den = (int(x) for x in fps.split("/"))
    doc = {
        "_leia": "gerado por helpers/cta.py preparar — não edite à mão",
        "origem": src.name, "fps": round(num / den, 4), "largura": 544, "altura": 890,
        "arrobaFinal": final, "quadros": mapa,
    }
    (CTA_DIR / "instagram-card.json").write_text(json.dumps(doc, separators=(",", ":")))
    print(f"  card: {len(frames)} quadros, verde fora, foto e @ apagados → "
          f"{CTA_DIR / 'instagram-card.webm'}")


def preparar_simples(src: Path) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vn",
                    "-c:a", "libmp3lame", "-q:a", "3", str(CTA_DIR / "instagram-simples.mp3")],
                   check=True)
    dest = OVERLAYS / "ig_follow.mov"
    if src.resolve() != dest.resolve():
        shutil.copy2(src, dest)
    print(f"  simples: áudio extraído; vídeo em {dest}")


# ---------------------------------------------------------------- foto

def gravar_foto(edit: Path, origem: Path | None, quadro: float | None) -> Path:
    """Foto quadrada 600×600, recortada no centro (ou no rosto, se achar)."""
    import cv2

    proj = edit / "hyperframes"
    dest = proj / FOTO_REL
    dest.parent.mkdir(parents=True, exist_ok=True)
    if quadro is not None:
        state = {}
        try:
            state = json.loads((edit / "state.json").read_text())
        except (OSError, json.JSONDecodeError):
            pass
        video = edit / (state.get("video") or "preview.mp4")
        cap = cv2.VideoCapture(str(video))
        cap.set(cv2.CAP_PROP_POS_MSEC, quadro * 1000)
        ok, img = cap.read()
        if not ok:
            sys.exit(f"não consegui ler o quadro {quadro}s de {video}")
    else:
        img = cv2.imread(str(origem))
        if img is None:
            sys.exit(f"não consegui abrir a imagem {origem}")
    img = recortar_rosto(img)
    cv2.imwrite(str(dest), img)
    return dest


def recortar_rosto(img):
    """Quadrado em volta do rosto (Haar, o mesmo do caption_safe), ou o centro.

    Um quadro de vídeo vertical é 9:16; recortado no centro, o círculo pegaria
    o peito. Com rosto achado, o quadrado é ~3× a altura dele, com a cabeça
    um pouco acima do meio — é o enquadramento de foto de perfil.
    """
    import cv2

    h, w = img.shape[:2]
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    casc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    fs = casc.detectMultiScale(g, 1.15, 5, minSize=(max(40, w // 12),) * 2)
    if len(fs):
        x, y, fw, fh = max(fs, key=lambda f: f[2] * f[3])
        lado = int(min(w, h, fh * 3.1))
        cx, cy = x + fw / 2, y + fh / 2 + fh * 0.25
    else:
        lado = min(w, h)
        cx, cy = w / 2, h / 2
    x0 = int(min(max(0, cx - lado / 2), w - lado))
    y0 = int(min(max(0, cy - lado / 2), h - lado))
    return cv2.resize(img[y0:y0 + lado, x0:x0 + lado], (600, 600), interpolation=cv2.INTER_AREA)


# ---------------------------------------------------------------- compor

def momento_clique(words: list[dict], duration: float) -> float | None:
    """O ÚLTIMO "segue/siga" da fala — o pedido de seguir costuma fechar o vídeo."""
    for w in reversed(words):
        txt = re.sub(r"[^\wà-ú]", "", str(w.get("text", "")).lower())
        if CLIQUE_RE.match(txt):
            t = (w.get("startMs", 0) + w.get("endMs", w.get("startMs", 0))) / 2000
            if t < duration:
                return t
    return None


def topo_simples(data: dict, larg_pct: float, W: int, H: int) -> float:
    """O botão do Simples fica LOGO ACIMA da legenda, medida neste projeto.

    Uma altura fixa não serve: a legenda muda de lugar por estilo e pela
    medição do queixo, e no "Mais viral, mais raso" os 72% de fábrica caíram em
    cima dela (legenda a ~75%). O botão ocupa a faixa de 30% a 70% da altura do
    arquivo (544×272); a borda de baixo dele vai a 2% acima do topo da legenda.
    Sem legenda, vale o padrão do modelo.
    """
    padrao = MODELOS["instagram-simples"]["topo"]
    try:
        import caption_safe
        cap = caption_safe._topo_legenda(data)
    except Exception:  # noqa: BLE001 — sem medição, o padrão serve
        cap = None
    if cap is None:
        return padrao
    alt = (larg_pct / 100) * W * (272 / 544) / H
    return max(0.05, min(padrao, cap - 0.02 - 0.70 * alt))


def _esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def montar(data: dict, proj: Path, duration: float, words: list[dict],
           events: list, track_bespoke: int, track_overlay: int,
           track_audio: int, W: int = 1080, H: int = 1920) -> tuple[str, list[str]]:
    """Devolve o HTML do CTA para o index e os avisos.

    Recusa nunca acontece aqui: a Fase 2 já barrou (phase2.check_cta) o modelo
    que pede foto sem foto. Se chegar assim mesmo — compose rodado à mão —, o
    CTA fica de fora com aviso, em vez de sair com um buraco no lugar do rosto.
    """
    cta = data.get("cta") or {}
    mid = cta.get("modelo")
    if not mid or mid not in MODELOS:
        return "", []
    m = MODELOS[mid]
    if m.get("motor") == "efeitos":
        return "", []             # montado pelo efeitos_compose.py
    avisos: list[str] = []
    dur = m["duracao"]
    if m["foto"] and not foto_do_projeto(proj):
        return "", [f"  aviso: CTA '{m['nome']}' sem foto em {FOTO_REL} — não vai aparecer"]
    arroba = (cta.get("arroba") or "").strip()
    if m["foto"] and not arroba:
        avisos.append(f"  aviso: CTA '{m['nome']}' sem @ — entra só a foto")
    arroba_txt = arroba.lstrip("@")

    # QUANDO: `start` dado vence; senão, o clique cai no último "segue/siga";
    # senão, o CTA termina junto com o vídeo.
    if cta.get("start") is not None:
        st = float(cta["start"])
    elif cta.get("momento") is not None:
        # O MOMENTO DA CHAMADA, escolhido pela IA lendo a fala: o clique do
        # botão cai nele — no meio do vídeo, se a chamada é no meio
        st = float(cta["momento"]) - m["clique"]
        st = min(st, duration - dur)
    else:
        t = momento_clique(words, duration)
        st = (t - m["clique"]) if t is not None else (duration - dur)
        # CABER INTEIRO vence cair em cima da palavra: um "segue" no último
        # segundo cortaria o fechamento do cartão no meio, e um CTA que some
        # sem fechar lê como render quebrado. O clique adianta o que faltar.
        st = min(st, duration - dur)
    st = max(0.0, min(st, duration - 0.5))
    en = min(st + dur, duration)
    if en - st < dur - 0.05:
        avisos.append(f"  aviso: CTA cortado pelo fim do vídeo ({en - st:.2f}s de {dur}s)")
    cta["_start"], cta["_end"] = round(st, 3), round(en, 3)

    blocos = []
    if mid == "instagram-simples":
        src = OVERLAYS / m["video"]
        dest = proj / "overlays" / m["video"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists() or dest.stat().st_mtime < src.stat().st_mtime:
            shutil.copy2(src, dest)
        larg = float(cta.get("width", m["largura"] * 100))
        top = cta.get("top")
        if top is None:
            top = topo_simples(data, larg, W, H) * 100
        top = float(top)
        blocos.append(
            f'  <video id="cta-simples" class="clip" src="overlays/{m["video"]}" muted playsinline '
            f'data-start="{st:.3f}" data-duration="{en - st:.3f}" '
            f'data-track-index="{track_overlay + 30}" '
            f'style="position:absolute;left:{float(cta.get("left", 50)):.2f}%;top:{top:.2f}%;'
            f'width:{larg:.2f}%;transform:translateX(-50%);pointer-events:none"></video>')
    else:
        comp = proj / "compositions"
        comp.mkdir(parents=True, exist_ok=True)
        html = (CTA_DIR / m["html"]).read_text()
        # a foto mora em `cta/` na raiz e TAMBÉM ao lado da composição: o
        # caminho de mídia de uma sub-composição resolve a partir da raiz no
        # render, e a cópia ao lado mantém o arquivo abrível sozinho
        foto = proj / FOTO_REL
        shutil.copy2(foto, comp / "cta-perfil.png")
        accent = data.get("accent") or "#ff3b30"
        subs = {"{{FOTO}}": FOTO_REL, "{{ARROBA}}": _esc(arroba_txt),
                "{{ACCENT}}": accent, "{{CLIQUE}}": f"{m['clique']:.3f}",
                "{{DURACAO}}": f"{en - st:.3f}"}
        if mid == "instagram-card":
            for k in ("video",):
                s, d = CTA_DIR / m[k], proj / "cta" / m[k]
                d.parent.mkdir(parents=True, exist_ok=True)
                if not d.exists() or d.stat().st_mtime < s.stat().st_mtime:
                    shutil.copy2(s, d)
            larg = float(cta.get("width", m["largura"] * 100)) / 100 * W
            esc_ = larg / 544
            left = float(cta.get("left", 50)) / 100 * W - larg / 2
            top = float(cta.get("top", m["topo"] * 100)) / 100 * H
            mapa = json.loads((CTA_DIR / "instagram-card.json").read_text())
            subs.update({"{{VIDEO}}": f"cta/{m['video']}", "{{ESCALA}}": f"{esc_:.4f}",
                         "{{LEFT}}": f"{left:.1f}", "{{TOP}}": f"{top:.1f}",
                         "{{MAPA}}": json.dumps(mapa, separators=(",", ":")),
                         "{{SELO}}": "" if cta.get("verificado", True) else "display:none;"})
        for k, v in subs.items():
            html = html.replace(k, v)
        gid = f"cta_{mid.replace('-', '_')}"
        html = html.replace("{{ID}}", gid)
        (comp / f"{gid}.html").write_text(html)
        blocos.append(
            f'  <div id="cta-comp" class="clip" data-start="{st:.3f}" '
            f'data-duration="{en - st:.3f}" data-track-index="{track_bespoke + 30}" '
            f'data-composition-id="{gid}" data-composition-src="compositions/{gid}.html"></div>')

    if m.get("audio") and (CTA_DIR / m["audio"]).exists() and cta.get("som", True):
        d = proj / "cta" / m["audio"]
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(CTA_DIR / m["audio"], d)
        blocos.append(
            f'  <audio id="cta-som" src="cta/{m["audio"]}" data-start="{st:.3f}" '
            f'data-duration="{en - st:.3f}" data-track-index="{track_audio + 30}" '
            f'data-volume="{float(cta.get("volume", 0.8)):.2f}"></audio>')
    elif mid == "siga-perfil":
        # a cápsula não traz som próprio: o whoosh de entrada é o mesmo dos
        # gráficos sob medida — um gráfico que aparece mudo lê como falha
        events.append((st, "hook"))
    return "\n".join(blocos), avisos


# ---------------------------------------------------------------- cli

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("preparar", help="regenera assets/cta a partir dos .mov de origem")
    p.add_argument("--card", type=Path, default=OVERLAYS / "ig_follow_profile.mov")
    p.add_argument("--simples", type=Path, default=OVERLAYS / "ig_follow.mov")
    p.add_argument("--tmp", type=Path, default=Path("/tmp/ave-cta"))
    c = sub.add_parser("momentos", help="lista as chamadas para ação da fala, com o segundo")
    c.add_argument("edit", type=Path)
    f = sub.add_parser("foto", help="grava a foto do CTA no projeto")
    f.add_argument("edit", type=Path)
    f.add_argument("imagem", type=Path, nargs="?")
    f.add_argument("--quadro", type=float, help="usa o quadro deste segundo do corte")
    a = ap.parse_args()
    if a.cmd == "preparar":
        preparar_card(a.card, a.tmp)
        preparar_simples(a.simples)
    elif a.cmd == "momentos":
        cs = chamadas(a.edit.resolve())
        if not cs:
            print("nenhuma chamada para ação na fala — o CTA fecha o vídeo "
                  "(grave cta.momentoRevisado: true)")
        for c in cs:
            print(f"[{c['start']:6.2f}–{c['end']:6.2f}] momento {c['momento']:6.2f}s "
                  f"({c['gatilho']})  {c['texto']}")
    else:
        if a.imagem is None and a.quadro is None:
            sys.exit("passe uma imagem ou --quadro <segundos>")
        print(gravar_foto(a.edit.resolve(), a.imagem, a.quadro))


if __name__ == "__main__":
    main()

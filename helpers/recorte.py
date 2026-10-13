#!/usr/bin/env python3
"""RECORTE DO APRESENTADOR — teste de 5s antes, alfa aprovado reaproveitado depois.

Recorte de fundo (pessoa sobre transparência) é a técnica desta skill que mais
falha de um jeito que só aparece ASSISTINDO: halo em volta do cabelo, borda que
treme, mão que some num gesto rápido. E é cara: processar o vídeo inteiro para
descobrir isso no fim é o retrabalho que o teste existe para evitar.

Por isso o caminho tem três passos, e o primeiro é OPCIONAL — quem decide se
quer o teste é o usuário (pergunta com `AskUserQuestion`, ver SKILL.md):

    recorte.py teste <edit> [--motor rvm|rvm-hq|hyperframes|ambos|todos] [--inicio S] [--dur 5]
    recorte.py aprovar <edit> --motor rvm
    recorte.py processar <edit> --inicio S --fim E [--fundo-novo]

`teste` escolhe sozinho os 5s com MAIS MOVIMENTO (cabelo, mãos, ombros — onde o
recorte erra), sem atravessar emenda; recorta com o(s) motor(es); compõe o
resultado sobre fundo CLARO e ESCURO lado a lado (halo escuro some no escuro e
aparece no claro, e vice-versa — um fundo só esconde metade dos defeitos); e
MEDE, para a revisão não depender só do olho:

  * tremulação — o alfa muda na borda onde a imagem NÃO mudou (borda viva);
  * corpo sumindo — a área da pessoa cai de um quadro para o outro;
  * manchas soltas — pedaços de fundo recortados como se fossem pessoa;
  * borda larga — faixa semitransparente grossa, que vira halo do fundo antigo.

Os números ORDENAM a conversa; a decisão é de quem assiste. Reprovado não se
esconde com brilho: corrige-se pequeno no mesmo trecho, regrava-se, ou o
formato fica com moldura e fundo (sem fingir recorte com um retângulo).

`processar` só usa o motor APROVADO e guarda cada janela em
`edit/recorte/fg_<motor>_<S>_<E>.mov`: mudar texto, posição ou tempo do
lettering NUNCA reprocessa o recorte — o arquivo existente é reaproveitado.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HELPERS = Path(__file__).resolve().parent
SKILL = HELPERS.parent
HF = ["npx", "--yes", "hyperframes@0.7.109"]
ENV = {**os.environ, "HYPERFRAMES_SKIP_SKILLS": "1"}
MEDIR_W = 360                       # largura de medição (1080/3)
CLARO, ESCURO = "0xEDEDED", "0x111111"

# Limiares calibrados em material real (ver SKILL.md, "Recorte"). A escala de
# borda é em px de um quadro de 1080 de largura.
# Calibrados no primeiro teste real (Carrossel, pessoa sentada gesticulando),
# com a revisão visual ao lado: RVM limpo na cabeça com leve tremulação no
# cabelo/ombro (0,073 → atenção); HyperFrames com a CADEIRA entrando e saindo
# do recorte (0,109; 21 quadros perdendo pessoa sem movimento → reprovado).
LIMITES = {
    "tremulacao": (0.06, 0.10),     # média |Δalfa| na borda onde a imagem não mudou
    "sumindo": (1, 4),              # quadros perdendo >0,5% da pessoa SEM movimento
    "manchas": (0.002, 0.01),       # fração do quadro em pedaços fora da pessoa
    "borda_px": (6.0, 10.0),        # largura média da faixa semitransparente
}


def pasta(edit: Path) -> Path:
    d = edit / "recorte"
    d.mkdir(parents=True, exist_ok=True)
    return d


def manifesto(edit: Path) -> dict:
    p = pasta(edit) / "recorte.json"
    return json.loads(p.read_text()) if p.exists() else {}


def gravar_manifesto(edit: Path, m: dict) -> None:
    (pasta(edit) / "recorte.json").write_text(json.dumps(m, ensure_ascii=False, indent=2))


def fonte(edit: Path) -> Path:
    for nome in ("preview.mp4", "preview_proxy.mp4"):
        if (edit / nome).exists():
            return edit / nome
    sys.exit(f"não achei o corte em {edit} (preview.mp4)")


def sonda(video: Path) -> tuple[int, int, float, float]:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height,r_frame_rate:format=duration", "-of", "json",
                        str(video)], capture_output=True, text=True, check=True)
    j = json.loads(r.stdout)
    s = j["streams"][0]
    n, d = (s["r_frame_rate"].split("/") + ["1"])[:2]
    return int(s["width"]), int(s["height"]), float(n) / float(d), float(j["format"]["duration"])


def ler(video: Path, w: int, fmt: str, *, ss: float = 0, t: float | None = None,
        fps: float | None = None) -> np.ndarray:
    W, H, _, _ = sonda(video)
    h = int(round(H * w / W / 2) * 2)
    ch = {"gray": 1, "rgba": 4}[fmt]
    vf = f"scale={w}:{h}" + (f",fps={fps}" if fps else "")
    cmd = ["ffmpeg", "-v", "error"]
    if ss:
        cmd += ["-ss", str(ss)]
    cmd += ["-i", str(video)]
    if t:
        cmd += ["-t", str(t)]
    cmd += ["-vf", vf, "-f", "rawvideo", "-pix_fmt", fmt, "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, h, w, ch) if ch > 1 else \
        np.frombuffer(raw, np.uint8).reshape(-1, h, w)


# ---------------------------------------------------------------- a janela

def escolher_janela(video: Path, dur: float = 5.0) -> tuple[float, str]:
    """Os `dur` segundos com mais movimento, sem emenda dentro."""
    fps = 10.0
    g = ler(video, 96, "gray", fps=fps).astype(np.float32) / 255
    if len(g) < dur * fps + 2:
        return 0.0, "o corte inteiro (curto)"
    d = np.abs(np.diff(g, axis=0)).mean(axis=(1, 2))           # energia por par
    corte = d > max(0.08, np.percentile(d, 99) * 0.9)          # troca de plano
    n = int(dur * fps)
    melhor, ini = -1.0, 0
    for i in range(0, len(d) - n):
        if corte[i:i + n].any():
            continue
        e = float(d[i:i + n].sum())
        if e > melhor:
            melhor, ini = e, i
    if melhor < 0:
        return 0.0, "sem trecho de 5s sem emenda — usei o começo"
    return ini / fps, "o trecho de 5s com mais movimento (mãos, cabeça), sem emenda"


# ---------------------------------------------------------------- os motores

def recortar(motor: str, video: Path, S: float, dur: float, out: Path,
             fgr: bool = False) -> float:
    if motor in ("rvm", "rvm-hq"):
        # INSTALAÇÃO GRADUAL: o recorte precisa do torch + RVM (~2 GB), que não
        # vêm na base. Instala aqui, na primeira vez em que alguém o pede.
        sys.path.insert(0, str(HELPERS))
        import instalar
        if not instalar.garantir("recorte"):
            sys.exit("o recurso de recorte não ficou pronto — "
                     "rode: uv run python helpers/instalar.py recorte")
    t0 = time.time()
    if motor in ("rvm", "rvm-hq"):
        # rvm-hq = RVM resnet50: a "correção pequena" quando o rvm sai com atenção
        modelo = ["--model", "resnet50"] if motor == "rvm-hq" else []
        modelo += ["--fgr"] if fgr else []
        subprocess.run([sys.executable, str(HELPERS / "person_matte.py"), str(video),
                        "-o", str(out), "--start", str(S), "--duration", str(dur), *modelo],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif motor == "hyperframes":
        # o CLI processa o arquivo inteiro: recorta a janela antes
        tmp = out.with_suffix(".janela.mp4")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(S), "-t", str(dur),
                        "-i", str(video), "-an", "-c:v", "libx264", "-crf", "14", str(tmp)],
                       check=True)
        subprocess.run(HF + ["remove-background", str(tmp), "-o", str(out)], env=ENV,
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        tmp.unlink(missing_ok=True)
    else:
        sys.exit(f"motor desconhecido: {motor}")
    return time.time() - t0


# ---------------------------------------------------------------- a medição

def medir(matte: Path, video: Path, S: float, dur: float) -> dict:
    """Mede em duas regiões. O VEREDITO sai de cabeça, ombros e mãos — é onde o
    efeito vive (cabeça vazando a moldura, texto atrás do ombro) e onde o olho
    procura defeito. O corpo inteiro vem como informação: medido no primeiro
    teste, o RVM deixou cabeça e mãos limpas e sumiu com as PERNAS; num
    enquadramento até a cintura isso não aparece, num corpo inteiro reprova."""
    a = ler(matte, MEDIR_W, "rgba")[..., 3].astype(np.float32) / 255
    src = ler(video, MEDIR_W, "gray", ss=S, t=dur).astype(np.float32) / 255
    n = min(len(a), len(src))
    a, src = a[:n], src[:n]
    ys = np.nonzero((a > 0.5).mean(axis=0) > 0.3)[0]          # linhas da pessoa (estável)
    topo, base = (int(ys.min()), int(ys.max())) if len(ys) else (0, a.shape[1])
    corte = topo + int(0.55 * (base - topo))                   # cabeça + ombros + mãos
    sup = _medir(a[:, :corte], src[:, :corte])
    todo = _medir(a, src)
    sup["veredito"] = veredito(sup)
    todo["veredito"] = veredito(todo)
    return {**sup, "corpo_inteiro": todo, "regiao": f"0–{corte / a.shape[1]:.0%} do quadro"}


def _medir(a: np.ndarray, src: np.ndarray) -> dict:
    import cv2
    n = len(a)
    k = np.ones((5, 5), np.uint8)
    fg = a > 0.5
    escala = 1080 / MEDIR_W

    trem, sumindo, manchas, borda = [], 0, [], []
    for i in range(n):
        f8 = fg[i].astype(np.uint8)
        # manchas: tudo que não é o maior pedaço de pessoa
        num, lab, stats, _ = cv2.connectedComponentsWithStats(f8, 8)
        if num > 2:
            areas = sorted(stats[1:, cv2.CC_STAT_AREA], reverse=True)
            manchas.append(sum(x for x in areas[1:] if x > 40) / f8.size)
        else:
            manchas.append(0.0)
        cont, _ = cv2.findContours(f8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        perim = sum(len(c) for c in cont)
        parcial = ((a[i] > 0.05) & (a[i] < 0.95)).sum()
        if perim > 0:
            borda.append(parcial / perim * escala)
        if i == 0:
            continue
        faixa = (cv2.dilate(f8, k) ^ cv2.erode(f8, k)).astype(bool)
        parado = np.abs(src[i] - src[i - 1]) < 0.02
        sel = faixa & parado
        if sel.sum() > 50:
            trem.append(float(np.abs(a[i] - a[i - 1])[sel].mean()))
        # CORPO SUMINDO = era pessoa, deixou de ser, e a imagem ali (e em volta)
        # NÃO mudou. Queda de ÁREA não serve: uma mão que sai da região de
        # medição derruba a área sem defeito nenhum (medido: 8 falsos alarmes).
        ds = np.abs(src[i] - src[i - 1])
        mov = cv2.dilate((ds > 0.04).astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool)
        perdeu = (a[i - 1] > 0.5) & (a[i] < 0.3) & ~mov
        if perdeu.sum() > 0.005 * max(fg[i - 1].sum(), 1):
            sumindo += 1
    m = {
        "tremulacao": round(float(np.mean(trem)) if trem else 0.0, 4),
        "tremulacao_p95": round(float(np.percentile(trem, 95)) if trem else 0.0, 4),
        "sumindo": int(sumindo),
        "manchas": round(float(np.percentile(manchas, 95)), 4),
        "borda_px": round(float(np.median(borda)) if borda else 0.0, 2),
        "quadros": int(n),
    }
    return m


def veredito(m: dict) -> dict:
    out = {}
    for chave, (atencao, reprova) in LIMITES.items():
        v = m[chave]
        out[chave] = "reprovado" if v >= reprova else "atenção" if v >= atencao else "ok"
    pior = "reprovado" if "reprovado" in out.values() else \
        "atenção" if "atenção" in out.values() else "ok"
    out["geral"] = pior
    return out


# ---------------------------------------------------------------- a revisão

def revisao(matte: Path, out_mp4: Path, out_png: Path) -> None:
    """Claro | escuro lado a lado (vídeo) + 3 quadros com zoom na cabeça (folha)."""
    W, H, fps, dur = sonda(matte)
    w = 540
    h = int(round(H * w / W / 2) * 2)
    fc = (f"[0:v]scale={w}:{h},split=2[m1][m2];"
          f"color=c={CLARO}:s={w}x{h}:r={fps}[c];color=c={ESCURO}:s={w}x{h}:r={fps}[e];"
          f"[c][m1]overlay=shortest=1[l];[e][m2]overlay=shortest=1[r];[l][r]hstack=2[v]")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(matte), "-filter_complex", fc,
                    "-map", "[v]", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
                    str(out_mp4)], check=True)
    # folha: 3 instantes; em cada um, claro|escuro inteiros + zoom 2x no topo
    # da cabeça sobre os dois fundos (onde o halo do cabelo mora)
    linhas = []
    tmpdir = out_png.parent
    for j, t in enumerate((dur * 0.2, dur * 0.5, dur * 0.85)):
        q = tmpdir / f".q{j}.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", str(out_mp4),
                        "-frames:v", "1", str(q)], check=True)
        linhas.append(q)
    zooms = []
    for j, t in enumerate((dur * 0.2, dur * 0.5, dur * 0.85)):
        rgba = ler(matte, w, "rgba", ss=t, t=0.05)[0]
        ys, xs = np.nonzero(rgba[..., 3] > 128)
        if len(ys) == 0:
            cx, cy = w // 2, h // 4
        else:
            cy = int(ys.min() + 0.12 * (ys.max() - ys.min()))
            cx = int(np.median(xs[ys < ys.min() + 0.25 * (ys.max() - ys.min())]))
        cw, chh = w // 2, h // 4
        x0 = max(0, min(w - cw, cx - cw // 2))
        y0 = max(0, min(h - chh, cy - chh // 2))
        # zoom 2x da cabeça, sobre o claro (z1) e sobre o escuro (z2)
        z2 = tmpdir / f".z{j}e.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(linhas[j]), "-vf",
                        f"crop={cw}:{chh}:{x0 + w}:{y0},scale={w}:-2:flags=neighbor",
                        str(z2)], check=True)
        z1 = tmpdir / f".z{j}c.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(linhas[j]), "-vf",
                        f"crop={cw}:{chh}:{x0}:{y0},scale={w}:-2:flags=neighbor",
                        str(z1)], check=True)
        zz = tmpdir / f".zz{j}.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(z1), "-i", str(z2),
                        "-filter_complex", "hstack=2", str(zz)], check=True)
        zooms.append(zz)
    cols = []
    for j in range(3):
        c = tmpdir / f".c{j}.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(linhas[j]), "-i", str(zooms[j]),
                        "-filter_complex", "vstack=2", str(c)], check=True)
        cols.append(c)
    subprocess.run(["ffmpeg", "-v", "error", "-y", *sum((["-i", str(c)] for c in cols), []),
                    "-filter_complex", "hstack=3,scale=2160:-2", str(out_png)], check=True)
    for p in tmpdir.glob(".*.png"):
        p.unlink(missing_ok=True)


# ---------------------------------------------------------------- comandos

def cmd_teste(args) -> None:
    edit = args.edit.resolve()
    video = fonte(edit)
    if args.inicio is not None:
        S, motivo = float(args.inicio), "janela pedida"
    else:
        S, motivo = escolher_janela(video, args.dur)
    motores = ["rvm", "rvm-hq", "hyperframes"] if args.motor == "todos" else \
        ["rvm", "hyperframes"] if args.motor == "ambos" else [args.motor]
    print(f"teste de recorte: {S:.2f}–{S + args.dur:.2f}s — {motivo}")
    m = manifesto(edit)
    m.setdefault("testes", [])
    for motor in motores:
        out = pasta(edit) / f"teste_{motor}.mov"
        seg = recortar(motor, video, S, args.dur, out)
        med = medir(out, video, S, args.dur)
        rev = pasta(edit) / f"teste_{motor}_revisao.mp4"
        folha = pasta(edit) / f"teste_{motor}_folha.png"
        revisao(out, rev, folha)
        reg = {"motor": motor, "inicio": round(S, 3), "dur": args.dur, "motivo": motivo,
               "segundos": round(seg, 1), "metricas": med, "matte": out.name,
               "revisao": rev.name, "folha": folha.name, "em": time.strftime("%Y-%m-%d %H:%M")}
        m["testes"] = [t for t in m["testes"] if t["motor"] != motor] + [reg]
        v = med["veredito"]
        print(f"\n  [{motor}] {seg:.0f}s de processamento · geral: {v['geral'].upper()}")
        print(f"    tremulação {med['tremulacao']} ({v['tremulacao']}) · "
              f"corpo sumindo {med['sumindo']} quadro(s) ({v['sumindo']}) · "
              f"manchas {med['manchas']} ({v['manchas']}) · "
              f"borda {med['borda_px']}px ({v['borda_px']})")
        print(f"    revisão: {rev}\n    folha:   {folha}")
    gravar_manifesto(edit, m)


def cmd_aprovar(args) -> None:
    edit = args.edit.resolve()
    m = manifesto(edit)
    teste = next((t for t in m.get("testes", []) if t["motor"] == args.motor), None)
    m["aprovado"] = {"motor": args.motor, "em": time.strftime("%Y-%m-%d %H:%M"),
                     "teste": teste and {k: teste[k] for k in ("inicio", "dur", "metricas")}}
    gravar_manifesto(edit, m)
    print(f"recorte aprovado com {args.motor} — `processar` reaproveita esta escolha")


def cmd_processar(args) -> None:
    edit = args.edit.resolve()
    video = fonte(edit)
    m = manifesto(edit)
    motor = args.motor or (m.get("aprovado") or {}).get("motor")
    if not motor:
        sys.exit("nenhum recorte aprovado — rode `teste` e `aprovar`, ou passe --motor "
                 "(o usuário dispensou o teste)")
    S, E = float(args.inicio), float(args.fim)
    # `--fundo-novo`: a pessoa vai sobre OUTRO fundo (cabeça vazando a moldura) —
    # cor descontaminada, arquivo próprio. Sem ele, a cor da fonte: certo para o
    # efeito "atrás do apresentador", que mantém o fundo original.
    suf = "_fgr" if args.fundo_novo and motor.startswith("rvm") else ""
    out = pasta(edit) / f"fg_{motor}_{S:.2f}_{E:.2f}{suf}.mov"
    # REAPROVEITA: mudar lettering não refaz o recorte. Só a fonte mais nova
    # que o arquivo (corte refeito) o invalida.
    if out.exists() and out.stat().st_mtime > video.stat().st_mtime:
        print(f"reaproveitado: {out}")
        return
    seg = recortar(motor, video, S, E - S, out, fgr=bool(suf))
    m.setdefault("janelas", {})[out.name] = {"motor": motor, "inicio": S, "fim": E,
                                             "fundoNovo": bool(suf), "segundos": round(seg, 1)}
    gravar_manifesto(edit, m)
    print(f"recortado em {seg:.0f}s: {out}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("teste")
    t.add_argument("edit", type=Path)
    t.add_argument("--motor", choices=["rvm", "rvm-hq", "hyperframes", "ambos", "todos"],
                   default="rvm")
    t.add_argument("--inicio", type=float)
    t.add_argument("--dur", type=float, default=5.0)
    a = sub.add_parser("aprovar")
    a.add_argument("edit", type=Path)
    a.add_argument("--motor", choices=["rvm", "rvm-hq", "hyperframes"], required=True)
    p = sub.add_parser("processar")
    p.add_argument("edit", type=Path)
    p.add_argument("--inicio", type=float, required=True)
    p.add_argument("--fim", type=float, required=True)
    p.add_argument("--motor", choices=["rvm", "rvm-hq", "hyperframes"])
    p.add_argument("--fundo-novo", action="store_true",
                   help="a pessoa vai sobre outro fundo (cor descontaminada)")
    args = ap.parse_args()
    {"teste": cmd_teste, "aprovar": cmd_aprovar, "processar": cmd_processar}[args.cmd](args)


if __name__ == "__main__":
    main()

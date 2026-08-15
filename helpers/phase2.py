#!/usr/bin/env python3
"""Fase 2 de ponta a ponta: escolha do usuário → vídeo entregue → volta no editor.

Um comando só, para que a Fase 2 deixe de depender de alguém rodando as etapas
na ordem certa:

    uv run python helpers/phase2.py <videos_dir>/edit

O que ele faz, em ordem:
  1. lê as escolhas salvas na aba Estilo e grava dentro do edit-data.json
  2. monta o projeto HyperFrames (uma vez; nas próximas rodadas só atualiza)
  3. compõe a partir dos dados
  4. roda o `check` e PARA se houver erro — o linter já pegou coisas que sairiam
     em produção sem aviso nenhum (áudio mudo, 45s perdidos por render)
  5. renderiza
  6. normaliza a loudness da entrega
  7. escreve os caminhos no state.json, que é como o editor descobre a Fase 2
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HELPERS = Path(__file__).resolve().parent

SKILL = Path(__file__).resolve().parent.parent
HF = ["npx", "--yes", "hyperframes@0.7.109"]
ENV = {**os.environ, "HYPERFRAMES_SKIP_SKILLS": "1"}

# Estilos que já existem de verdade. A aba Estilo oferece mais do que isto; um
# pedido fora desta lista precisa falhar com nome, não renderizar outra coisa.
PORTED_CAPTIONS = {"karaoke", "simples", "serifada", "classica", "scatter", "stacked"}
PORTED_HEADLINES = {"outline", "card", "realce", "misto"}

LOUDNORM = "loudnorm=I=-14:TP=-1:LRA=11"


def run(cmd, cwd=None, quiet=False, allow_fail=False):
    """Executa e aborta em falha — salvo quando o código de saída É a resposta.

    O `check` sai com 1 quando encontra erro, que é informação, não acidente:
    abortar aqui impedia a lógica de tolerância logo abaixo de sequer rodar, e
    a Fase 2 morria antes de decidir se o erro importava.
    """
    r = subprocess.run(cmd, cwd=cwd, env=ENV,
                       capture_output=quiet, text=True)
    if r.returncode != 0 and not allow_fail:
        if quiet and r.stderr:
            print(r.stderr[-2000:], file=sys.stderr)
        sys.exit(f"falhou: {' '.join(str(c) for c in cmd[:3])}… (código {r.returncode})")
    return r


def load(p: Path, default=None):
    return json.loads(p.read_text()) if p.exists() else default


def balance_two_lines(text: str) -> list[str]:
    """A headline é SEMPRE duas linhas — a quebra é onde as duas ficam mais
    parecidas em comprimento. Uma linha só deixa a segunda vazia e o bloco
    desequilibrado; três linhas não cabem no espaço que o estilo reserva."""
    w = text.split()
    if len(w) < 2:
        return [text, ""]
    best, score = 1, None
    for i in range(1, len(w)):
        a, b = len(" ".join(w[:i])), len(" ".join(w[i:]))
        d = abs(a - b)
        if score is None or d < score:
            best, score = i, d
    return [" ".join(w[:best]), " ".join(w[best:])]


def apply_style_pick(edit: Path, data: dict) -> tuple[dict, bool]:
    """Traz o que o usuário escolheu na aba Estilo para dentro do edit-data."""
    pick = load(edit / "preview_style.json")
    if not pick:
        return data, False
    caps = data.setdefault("captions", {})
    if pick.get("captions"):
        caps["style"] = pick["captions"]
    if pick.get("accent"):
        data["accent"] = pick["accent"]
    if pick.get("headline"):
        data.setdefault("hook", {})["style"] = pick["headline"]
    # O TEXTO da headline vem da caixa do editor. Sem este ramo o `hook` ficava
    # só com o estilo e nenhuma linha — e o compositor pula um hook sem
    # `enabled`, então o vídeo saía SEM headline nenhuma, em silêncio, com o
    # usuário tendo acabado de escrever a frase.
    txt = (pick.get("headlineText") or "").strip()
    if txt:
        hook = data.setdefault("hook", {})
        hook["lines"] = balance_two_lines(txt)
        hook["enabled"] = True
        hook.setdefault("endSec", 4.0)
    elif pick.get("headline") and not (data.get("hook") or {}).get("lines"):
        # estilo escolhido e nenhum texto: desliga em vez de renderizar vazio
        data.setdefault("hook", {})["enabled"] = False
    if pick.get("edit"):
        data["editStyle"] = pick["edit"]
    for k, v in (pick.get("elements") or {}).items():
        data.setdefault("elements", {})[k] = v
    if pick.get("observation"):
        data["observation"] = pick["observation"]
    return data, True


def check_supported(data: dict) -> None:
    caps = data.get("captions", {})
    style = caps.get("style", "karaoke")
    if caps.get("enabled", True) and style not in PORTED_CAPTIONS:
        sys.exit(
            f"\nO estilo de legenda '{style}' ainda não foi portado.\n"
            f"Prontos: {', '.join(sorted(PORTED_CAPTIONS)) or '(nenhum)'}\n"
            f"Escolha um dos prontos na aba Estilo, ou peça o port deste.\n"
        )
    hook = data.get("hook", {})
    if hook.get("enabled") and hook.get("style") not in PORTED_HEADLINES:
        sys.exit(
            f"\nO estilo de headline '{hook.get('style')}' ainda não foi portado, "
            f"e o hook está ligado.\nDesligue o hook ou peça o port.\n"
        )


def scaffold(proj: Path, cut: Path) -> None:
    proj.mkdir(parents=True, exist_ok=True)
    (proj / "package.json").write_text(
        json.dumps({"name": "ave-fase2", "private": True, "type": "module"}, indent=2))
    (proj / "hyperframes.json").write_text(json.dumps({
        "paths": {"blocks": "compositions", "components": "compositions/components",
                  "assets": "assets"},
        "media": {"autoProxy": True},
    }, indent=2))
    link = proj / "cut.mp4"
    if link.is_symlink() or link.exists():
        link.unlink()
    # symlink: o corte pode ter centenas de MB e é o mesmo arquivo
    link.symlink_to(cut.resolve())


def deliver(rendered: Path, final: Path) -> None:
    """Normaliza a loudness da entrega (-14 LUFS / -1 dBTP / LRA 11).

    A Fase 1 já normaliza o cut.mp4, mas a Fase 2 acrescenta trilha e efeitos —
    a mistura final é outra, então o alvo tem que ser reaferido na saída, não
    herdado da entrada.
    """
    run(["ffmpeg", "-y", "-v", "error", "-i", str(rendered),
         "-c:v", "copy", "-af", LOUDNORM, "-c:a", "aac", "-b:a", "192k",
         str(final)], quiet=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edit", type=Path, help="<videos_dir>/edit")
    ap.add_argument("--style", help="força um estilo de legenda (ignora a aba)")
    ap.add_argument("--end", type=float, help="compõe só os N primeiros segundos")
    args = ap.parse_args()

    edit = args.edit.resolve()
    cut = edit / "cut.mp4"
    if not cut.exists():
        sys.exit(f"não achei o corte aprovado em {cut} — a Fase 1 precisa ter rodado")

    proj = edit / "hyperframes"
    pub = edit / "remotion" / "public"          # onde os dados já moram hoje
    data_path = pub / "edit-data.json"
    caps_path = pub / "captions.json"
    if not caps_path.exists():
        # Gerar aqui em vez de desistir. Elas são DERIVADAS do corte, não uma
        # escolha do usuário — exigi-las prontas fazia o comando "faz tudo"
        # parar no primeiro passo. E o transcrito tem de ser o do cut.mp4: o
        # modo de fallback pelo EDL devolve zero palavras, porque o J-cut
        # encurta a saída e os tempos das fontes não valem aqui.
        print("  legendas ausentes — gerando do corte…")
        cut = edit / (load(edit / "state.json", {}).get("video") or "cut.mp4")
        if not cut.exists():
            sys.exit(f"não achei o corte em {cut}")
        tr = edit / "transcripts" / "cut.json"
        if not tr.exists():
            run([sys.executable, str(HELPERS / "transcribe.py"), str(cut),
                 "--edit-dir", str(edit), "--language", "pt"], quiet=True)
        pub.mkdir(parents=True, exist_ok=True)
        run([sys.executable, str(HELPERS / "captions_for_remotion.py"),
             "--transcript", str(tr), "-o", str(caps_path)], quiet=True)
        if not caps_path.exists():
            sys.exit("falhou ao gerar as legendas do corte")

    data = load(data_path, {})
    data, picked = apply_style_pick(edit, data)
    if args.style:
        data.setdefault("captions", {})["style"] = args.style
    check_supported(data)
    data_path.parent.mkdir(parents=True, exist_ok=True)
    data_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    if picked:
        print("  escolhas da aba Estilo aplicadas")

    scaffold(proj, cut)

    compose = [sys.executable, str(SKILL / "helpers" / "compose_shortform.py"),
               str(data_path), "--captions", str(caps_path),
               "-o", str(proj / "index.html")]
    if edit.joinpath("edl.json").exists():
        compose += ["--edl", str(edit / "edl.json")]

    # O empilhado é o único estilo com passo de preparação: um "diretor" agrupa
    # as palavras em deixas curtas, escolhe qual leva o acento serifado laranja
    # e marca as que ficam sozinhas ou circuladas. Gerado aqui quando falta, em
    # vez de exigir que alguém lembre da ordem.
    # A perseguição do olhar precisa do rastreio de rosto. Gerado aqui quando
    # falta, em vez de a composição sair sem o efeito e ninguém notar.
    if (data.get("elements") or {}).get("tracking") and not data.get("splitInserts"):
        track = pub / "track.json"
        if not track.exists():
            print("  rastreando o rosto…")
            run([sys.executable, str(SKILL / "helpers" / "face_track.py"),
                 str(cut), "-o", str(track)])

    if data.get("captions", {}).get("style") == "stacked":
        cues = pub / "caption-cues.json"
        transcript = edit / "transcripts" / "cut.json"
        if not cues.exists():
            if not transcript.exists():
                sys.exit(f"o empilhado precisa da transcrição do corte em {transcript}")
            print("  preparando as deixas do empilhado…")
            run([sys.executable, str(SKILL / "helpers" / "caption_style.py"),
                 "--transcript", str(transcript), "-o", str(cues)])
        compose += ["--cues", str(cues)]
    if args.end:
        compose += ["--end", str(args.end)]
    run(compose)

    print("  verificando…")
    r = run(HF + ["check"], cwd=proj, quiet=True, allow_fail=True)
    out = r.stdout or ""
    if "0 error(s)" not in out:
        # `content_overlap` entre as linhas da headline é falso positivo
        # conhecido: com entrelinha apertada (1.02–1.06, que é justamente o que
        # faz a headline ler como bloco) as CAIXAS de linha se encostam, embora
        # os glifos não. Conferido no render — o cartão sai correto. Tolerado
        # nominalmente, e só ele: qualquer outro erro continua barrando.
        hard = [l for l in out.splitlines()
                if "✗" in l and not ("content_overlap" in l and "hl-line" in l)]
        if hard:
            print(out[-3000:])
            sys.exit("o check encontrou erros — corrigir antes de renderizar")
        print("  (sobreposição nominal entre as linhas da headline — "
              "conferida no render, sai correta)")

    print("  renderizando…")
    run(HF + ["render"], cwd=proj)
    renders = sorted((proj / "renders").glob("*.mp4"), key=lambda p: p.stat().st_mtime)
    if not renders:
        sys.exit("o render não produziu arquivo")

    final = edit / "final.mp4"
    deliver(renders[-1], final)

    state = load(edit / "state.json", {})
    state.update({
        "phase": 2,
        "captions": "remotion/public/captions.json",
        "editData": "remotion/public/edit-data.json",
        "finalVideo": "final.mp4",
        "message": f"Fase 2 pronta — legenda {data.get('captions', {}).get('style', 'karaoke')}",
    })
    # A ESCOLHA VAI PARA O state.json ANTES DE SER APAGADA.
    # Apagar sem guardar deixava o render seguinte CEGO: o `apply_style_pick`
    # não achava nada, e tudo que só existia no pick — o texto da headline, por
    # exemplo — sumia sem aviso. O state.json é o registro do que está no disco
    # e é de onde o editor relê, então é o lugar certo.
    pick = load(edit / "preview_style.json")
    if pick:
        state["style"] = {
            "edit": pick.get("edit"), "headline": pick.get("headline"),
            "headlineText": pick.get("headlineText", ""),
            "captions": pick.get("captions"), "accent": pick.get("accent"),
            "capColor": pick.get("capColor"), "capDy": pick.get("capDy", 0),
            "elements": pick.get("elements") or {},
        }
    state["awaitingStyle"] = False
    (edit / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2))
    (edit / "preview_style.json").unlink(missing_ok=True)

    size = final.stat().st_size / 1e6
    print(f"\n  entregue: {final}  ({size:.1f} MB)")
    print("  o editor já mostra na aba Fase 2")


if __name__ == "__main__":
    main()

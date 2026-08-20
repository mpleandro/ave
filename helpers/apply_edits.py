#!/usr/bin/env python3
"""Aplica os cortes que o usuário ajustou no editor, sem passar por mim.

    uv run python helpers/apply_edits.py <videos_dir>/edit

Divisão de trabalho, que é o ponto deste helper:
  - MECÂNICO (arrastar borda de trecho, remover trecho): aplica sozinho, refaz
    o corte e confere. Não exige julgamento — exige exatidão.
  - MARCAÇÕES escritas ("tira essa repetição", "esse trecho ficou seco"): NÃO
    são aplicadas aqui. Ficam guardadas e são mostradas, porque cada uma é um
    pedido em linguagem natural que precisa de leitura.

Antes disso, salvar no editor só registrava a intenção: alguém tinha que ler o
arquivo e agir. Agora o que é determinístico anda sozinho.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
HELPERS = SKILL / "helpers"

TOL = 1e-3  # casamento de bordas em segundos


def load(p: Path, default=None):
    return json.loads(p.read_text()) if p.exists() else default


def same(a: float, b: float) -> bool:
    return abs(float(a) - float(b)) < TOL


def apply_to_edl(edl: dict, payload_edl: dict) -> tuple[dict, list[str]]:
    """Aplica remoções e mudanças de borda PRESERVANDO os campos por range.

    Não substitui a lista de ranges pela que o editor mandou: aquela carrega só
    source/start/end/beat, e o range original pode ter `grade` (matching de
    câmera B), `gain_db` ou `jcut_lead_frames`. Sobrescrever perderia tudo isso
    em silêncio. Então casamos cada edição contra o range original e mexemos só
    nos tempos.
    """
    log: list[str] = []
    ranges = list(edl.get("ranges", []))

    for rm in payload_edl.get("removed", []):
        hit = next((r for r in ranges
                    if r["source"] == rm["source"]
                    and same(r["start"], rm["start"]) and same(r["end"], rm["end"])), None)
        if hit is None:
            log.append(f"  ! não achei o trecho removido em {rm['source']} "
                       f"{rm['start']:.3f}-{rm['end']:.3f} — ignorado")
            continue
        ranges.remove(hit)
        log.append(f"  − removido {rm['source']} {rm['start']:.3f}-{rm['end']:.3f}"
                   + (f"  ({rm['beat']})" if rm.get("beat") else ""))

    for ch in payload_edl.get("changes", []):
        f, t = ch["from"], ch["to"]
        hit = next((r for r in ranges
                    if r["source"] == ch["source"]
                    and same(r["start"], f["start"]) and same(r["end"], f["end"])), None)
        if hit is None:
            log.append(f"  ! não achei o trecho alterado em {ch['source']} "
                       f"{f['start']:.3f}-{f['end']:.3f} — ignorado")
            continue
        ds, de = t["start"] - f["start"], t["end"] - f["end"]
        hit["start"], hit["end"] = t["start"], t["end"]
        # Borda posta à mão manda no J-cut daquela junção. Sem isto, a entrada
        # de imagem chega alguns quadros depois do ponto escolhido e o áudio
        # termina antes dele, porque o aparo automático mede o silêncio
        # disponível — e quanto ele apara muda conforme onde a pessoa cortou.
        # O corte então sai num lugar que ninguém escolheu.
        if abs(ds) > TOL:
            hit["jcut_lead_frames"] = 0
        if abs(de) > TOL:
            hit["jcut_tail_frames"] = 0
        log.append(f"  ~ {ch['source']} {f['start']:.3f}→{t['start']:.3f} "
                   f"({ds:+.3f}s)  {f['end']:.3f}→{t['end']:.3f} ({de:+.3f}s)")

    edl["ranges"] = ranges
    return edl, log


def regions_for(video: Path, start: float, end: float) -> list[tuple[float, float]]:
    r = subprocess.run(
        [sys.executable, str(HELPERS / "speech_regions.py"), str(video),
         "--start", str(max(0.0, start - 1.0)), "--end", str(end + 1.0)],
        capture_output=True, text=True,
    )
    out = []
    for line in r.stdout.splitlines():
        parts = line.replace("-", " ").split()
        nums = [p for p in parts if p.replace(".", "", 1).isdigit()]
        if len(nums) >= 2:
            out.append((float(nums[0]), float(nums[1])))
    return out


def warn_clipped_edges(edl: dict, edit: Path, payload_edl: dict) -> list[str]:
    """Avisa quando uma borda nova cai DENTRO da fala.

    A vontade do usuário vence — ele viu o quadro e decidiu. Mas cortar no meio
    de uma palavra é o defeito que mais se ouve num corte, e ele é fácil de
    cometer arrastando de olho. Então dizemos, e seguimos.
    """
    warns = []
    for ch in payload_edl.get("changes", []):
        src = edl.get("sources", {}).get(ch["source"])
        if not src:
            continue
        path = Path(src)
        if not path.is_absolute():
            path = (edit / src).resolve()
        if not path.exists():
            continue
        for label, t in (("entrada", ch["to"]["start"]), ("saída", ch["to"]["end"])):
            for a, b in regions_for(path, t, t):
                if a + 0.02 < t < b - 0.02:
                    warns.append(f"  ⚠ a {label} nova de {ch['source']} em {t:.3f}s cai "
                                 f"dentro da fala ({a:.2f}–{b:.2f}s) — pode cortar palavra")
                    break
    return warns


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edit", type=Path)
    ap.add_argument("--draft", action="store_true", help="render rápido para conferir corte")
    ap.add_argument("--no-render", action="store_true", help="só aplica no edl, não renderiza")
    args = ap.parse_args()

    edit = args.edit.resolve()
    edits_path = edit / "preview_edits.json"
    payload = load(edits_path)
    if not payload:
        sys.exit("nada salvo no editor — nenhum preview_edits.json")

    notes = payload.get("notes") or []
    # O PEDIDO EM TEXTO ("Alterações extras") viaja em `request`, não em notes.
    # Ignorá-lo sumia com a mensagem: o toast dizia "✓ Enviado", este script
    # dizia "nada a aplicar" e apagava o arquivo — medido em 2026-08-19, com o
    # usuário perguntando se o pedido tinha chegado. Vira nota pendente, que o
    # watcher anuncia como qualquer outra.
    pedido = (payload.get("request") or "").strip()
    if pedido:
        notes = list(notes) + [{"text": pedido, "request": True}]
    # PALAVRAS RISCADAS e RESPIROS também são pedidos que exigem leitura (o
    # corte é na FONTE, com a folga medida — não nos tempos do Whisper), e eles
    # sofriam a mesma corrida que criou o pending_notes.json: este script não
    # os aplica, apagava o preview_edits.json em ~100ms, e o watcher (sonda de
    # 2s) nunca via o arquivo. O usuário via "✓ Enviado" e remarcava tudo.
    # Viram pendências marcadas por `kind`, que o watcher sabe anunciar.
    notes = list(notes)
    for w in payload.get("cutWords") or []:
        notes.append({**w, "kind": "word"})
    for b in payload.get("cutBreaths") or []:
        notes.append({**b, "kind": "breath"})
    has_edl = bool(payload.get("edl"))
    has_data = bool(payload.get("editData"))

    if has_edl:
        edl_path = edit / "edl.json"
        edl = load(edl_path)
        if not edl:
            sys.exit(f"não achei o edl.json em {edit}")
        before = len(edl.get("ranges", []))
        edl, log = apply_to_edl(edl, payload["edl"])
        warns = warn_clipped_edges(edl, edit, payload["edl"])

        # backup antes de escrever: o corte aprovado é trabalho do usuário
        (edit / "edl.prev.json").write_text(json.dumps(load(edl_path), ensure_ascii=False, indent=2))
        edl_path.write_text(json.dumps(edl, ensure_ascii=False, indent=2))

        print(f"cortes: {before} → {len(edl['ranges'])} trechos")
        for l in log:
            print(l)
        for w in warns:
            print(w)
        print("  (o edl anterior ficou salvo como edl.prev.json)")

    if has_data:
        # A raiz do projeto HyperFrames é o destino único dos dados. O
        # `remotion/public` legado só é respeitado enquanto ainda for o que
        # existe no disco — o `phase2.py` o adota na primeira rodada.
        pub = edit / "hyperframes"
        legacy = edit / "remotion" / "public"
        if not (pub / "edit-data.json").exists() and (legacy / "edit-data.json").exists():
            pub = legacy
        pub.mkdir(parents=True, exist_ok=True)
        dp = pub / "edit-data.json"
        data = load(dp, {})
        for k, v in payload["editData"].items():
            if v not in (None, []):
                data[k] = v
        dp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        print("posições de inserts/hook atualizadas")

    state = load(edit / "state.json", {})

    if has_edl and not args.no_render:
        # O RENDER SEGUE O TIER DA FASE. `state.video` diz o que o editor está
        # mostrando: na Fase 1 é o preview_proxy.mp4, e é NELE que a iteração
        # acontece (720p/veryfast, 3,2× mais barato por segmento — a regra que o
        # SKILL.md já mandava e este script ignorava, pagando o encode 1080p
        # full-length a cada save). Escrever no arquivo do state também conserta
        # o preview: renderizar sempre em preview.mp4 deixava a tela — que serve
        # o state.video — mostrando o corte ANTIGO depois de aplicar.
        # Pós-aprovação o state aponta preview.mp4 e o render volta a ser final,
        # porque é sobre ele que a Fase 2 compõe.
        out_name = state.get("video") or "preview.mp4"
        out_video = edit / out_name
        proxy_iter = "proxy" in Path(out_name).name
        print(f"\nrefazendo o corte… ({'proxy 720p' if proxy_iter else '1080p final'})")
        cmd = [sys.executable, str(HELPERS / "render.py"), str(edit / "edl.json"),
               "-o", str(out_video)]
        if args.draft:
            cmd.append("--draft")
        elif proxy_iter:
            cmd.append("--proxy")
        r = subprocess.run(cmd)
        if r.returncode != 0:
            sys.exit("o render falhou — o edl novo está salvo, o corte antigo continua no lugar")
        print("\nconferindo…")
        subprocess.run([sys.executable, str(HELPERS / "verify_cut.py"),
                        str(edit / "edl.json"), str(out_video)])

    state["message"] = ("Corte atualizado a partir do editor"
                        if has_edl else state.get("message", ""))
    (edit / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2))

    if notes:
        (edit / "pending_notes.json").write_text(json.dumps(notes, ensure_ascii=False, indent=2))
        print(f"\n{len(notes)} pendência(s) — estas NÃO foram aplicadas, "
              f"porque são pedidos que precisam de leitura:")
        for n in notes:
            if n.get("request"):
                print(f'  [pedido em texto] {n["text"]}')
            elif n.get("kind") == "word":
                print(f'  [palavra riscada] "{n.get("text")}" '
                      f'({n.get("source")} {n.get("srcStart")}–{n.get("srcEnd")})')
            elif n.get("kind") == "breath":
                print(f'  [respiro] entre "{n.get("afterWord")}" e "{n.get("beforeWord")}" '
                      f'{n.get("dur")}s → {n.get("keep")}s')
            else:
                print(f'  [{n["renderedStart"]:.2f}–{n["renderedEnd"]:.2f}s] {n["text"]}')
        print("  guardadas em pending_notes.json")

    edits_path.unlink(missing_ok=True)
    if not has_edl and not has_data and not notes:
        print("nada a aplicar")


if __name__ == "__main__":
    main()

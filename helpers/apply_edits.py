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
sys.path.insert(0, str(HELPERS))

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


def aplicar_correcoes(edit: Path, novas: list[dict]) -> tuple[list[str], bool]:
    """Funde as correções de texto em `transcripts/corrections.json`.

    É MERGE, não substituição: o arquivo é o acúmulo de tudo que já foi
    consertado, e um save do editor que trouxesse só a correção da vez apagaria
    as anteriores — que já estão queimadas em vídeos entregues.

    A CHAVE DE DEDUPLICAÇÃO é (fonte, srcStart, palavra original). Corrigir duas
    vezes a mesma palavra troca a correção em vez de empilhar duas, senão o
    `fix_for` devolveria a primeira que casasse e a segunda seria ignorada — com
    o painel mostrando o texto novo e o vídeo queimando o velho, que é
    exatamente o defeito que esta série de mudanças foi consertar.

    Correção GLOBAL (sem `srcStart`) tem chave própria, então ela conviva com
    correções pontuais da mesma palavra: a pontual é mais específica e o
    `fix_for` a encontra primeiro se estiver antes na lista — por isso as
    pontuais são gravadas ANTES das globais.

    Os tempos são da FONTE, não da saída. É o que torna a correção imune a
    mudança de corte: remover um trecho não desloca `srcStart`, então uma
    correção feita antes continua casando depois.
    """
    caminho = edit / "transcripts" / "corrections.json"
    atuais = load(caminho, []) or []

    def chave(c: dict) -> tuple:
        st = c.get("srcStart")
        return (c.get("source"), None if st is None else round(float(st), 2),
                (c.get("from") or "").lower().strip(" .,;:!?"))

    por_chave = {chave(c): c for c in atuais}
    log: list[str] = []
    for c in novas:
        if not c.get("from") or c.get("text") is None or not c.get("source"):
            log.append(f"  ! correção incompleta, ignorada: {c}")
            continue
        limpa = {"source": c["source"], "from": c["from"], "text": c["text"]}
        if c.get("srcStart") is not None:
            limpa["srcStart"] = round(float(c["srcStart"]), 3)
        k = chave(limpa)
        verbo = "~ trocada" if k in por_chave else "+ nova"
        por_chave[k] = limpa
        alcance = "(todas as ocorrências)" if "srcStart" not in limpa else \
                  f"em {limpa['srcStart']:.2f}s"
        log.append(f"  {verbo}: \"{c['from']}\" → \"{c['text']}\" {alcance}")

    # pontuais primeiro: mais específicas, e `fix_for` para na primeira que casa
    ordenadas = sorted(por_chave.values(), key=lambda c: ("srcStart" not in c,
                                                          c["source"],
                                                          c.get("srcStart", 0.0)))
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(ordenadas, ensure_ascii=False, indent=2))

    # OS DERIVADOS DA LEGENDA PRECISAM MORRER AQUI, e este é o passo que uma
    # implementação ingênua esquece. `cut_mapped.json` e `captions.json` são
    # gerados com guarda `if not exists` (phase2.py) e nunca invalidados: sem
    # apagá-los, a correção é ignorada EM SILÊNCIO — o comando termina limpo e a
    # palavra errada continua queimada. O painel se cura sozinho, porque a chave
    # do cache dele já inclui o mtime deste arquivo.
    fase2_ja_rodou = False
    for derivado in (edit / "transcripts" / "cut_mapped.json",
                     edit / "hyperframes" / "captions.json",
                     edit / "remotion" / "public" / "captions.json"):
        if derivado.exists():
            derivado.unlink()
            log.append(f"  − {derivado.name} invalidado (será regerado)")
            if derivado.name == "captions.json":
                fase2_ja_rodou = True
    return log, fase2_ja_rodou


def _borda_acustica(video: Path, t: float, busca: float) -> float:
    """Ponto de menor energia em volta de `t` (fala_limpa.borda); sem áudio, t."""
    try:
        import fala_limpa as FL  # noqa: PLC0415
        import transcribe_local as TL  # noqa: PLC0415
        import tempfile  # noqa: PLC0415
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "a.wav"
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{max(0.0, t - 1.0):.3f}", "-t", "2.0",
                            "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
                            str(wav)], check=True)
            mono = TL.carregar_mono(wav)
        return round(max(0.0, t - 1.0) + FL.borda(mono, min(1.0, t), busca=busca), 3)
    except Exception:  # noqa: BLE001
        return round(t, 3)


def aplicar_marcas(edl: dict, edit: Path, cut_words: list[dict], cut_breaths: list[dict]) -> list[str]:
    """Palavras riscadas e respiros marcados no editor → ranges e `breaths`.

    Eram PEDIDOS que só uma sessão de IA atachada lia (watch_edits), e o
    servidor apagava o preview_edits.json logo depois de rodar este script —
    com ninguém atachado, sumiam. Agora são mecânicos: uma palavra riscada vira
    um corte na borda acústica (dentro da folga medida que o editor já manda),
    e um respiro marcado vira `breaths` no range, que o render.py já entende.
    """
    log: list[str] = []
    sources = edl.get("sources", {})

    def fonte(key: str) -> Path | None:
        src = sources.get(key)
        if not src:
            return None
        p = Path(src)
        return p if p.is_absolute() else (edit / src).resolve()

    # respiros primeiro: eles não mudam os índices dos ranges
    for b in cut_breaths or []:
        try:
            ri = int(b["range"]); at = float(b["srcFrom"]); to = float(b["srcTo"])
            keep = float(b.get("keep") or 0.15)
        except (KeyError, TypeError, ValueError):
            continue
        if ri >= len(edl["ranges"]) or to <= at:
            continue
        r = edl["ranges"][ri]
        if not (float(r["start"]) < at and to < float(r["end"])):
            log.append(f"  ! respiro {at:.2f}–{to:.2f} fora do trecho {ri} — ignorado")
            continue
        br = r.setdefault("breaths", [])
        if not any(abs(float(x["at"]) - at) < 0.05 for x in br):
            br.append({"at": round(at, 3), "to": round(to, 3), "keep": round(keep, 3)})
            log.append(f"  respiro {at:.2f}–{to:.2f}s → fica {keep:.2f}s (trecho {ri})")

    # palavras riscadas: do último para o primeiro, para os índices não andarem
    cortes = []
    for w in cut_words or []:
        try:
            ri = int(w["range"]); s0 = float(w["srcStart"]); e0 = float(w["srcEnd"])
        except (KeyError, TypeError, ValueError):
            continue
        if ri >= len(edl["ranges"]):
            continue
        gb = float(w.get("gapBefore") or 0); ga = float(w.get("gapAfter") or 0)
        vid = fonte(edl["ranges"][ri]["source"])
        x = _borda_acustica(vid, s0 - min(gb, 0.12) / 2, busca=max(0.02, min(gb, 0.12) / 2)) if vid else s0
        y = _borda_acustica(vid, e0 + min(ga, 0.12) / 2, busca=max(0.02, min(ga, 0.12) / 2)) if vid else e0
        if y - x < 0.06:
            y = x + 0.06
        cortes.append((ri, x, y, w.get("text", ""), gb, ga))
    for ri, x, y, txt, gb, ga in sorted(cortes, key=lambda c: (c[0], c[1]), reverse=True):
        r = edl["ranges"][ri]
        a, b = float(r["start"]), float(r["end"])
        if not (a <= x and y <= b):
            log.append(f"  ! \"{txt}\" ({x:.2f}–{y:.2f}) fora do trecho {ri} — ignorado")
            continue
        base = {k: v for k, v in r.items() if k not in ("start", "end", "breaths", "quote")}
        br = r.get("breaths") or []
        novos = []
        if x - a >= 0.08:
            novos.append({**base, "start": a, "end": round(x, 3),
                          "breaths": [z for z in br if float(z["to"]) < x] or None,
                          "reason": f"{r.get('reason', '')} | riscado no editor: \"{txt}\"".strip(" |")})
        if b - y >= 0.08:
            novos.append({**base, "start": round(y, 3), "end": b,
                          "breaths": [z for z in br if float(z["at"]) > y] or None})
        for n in novos:
            if n.get("breaths") is None:
                n.pop("breaths", None)
        edl["ranges"][ri:ri + 1] = novos
        aviso = "  ⚠ sem folga medida — a emenda pode cair na fala" if (not gb and not ga) else ""
        log.append(f"  \"{txt}\" riscada → corte {x:.2f}–{y:.2f}s no trecho {ri}{aviso}")
    if cortes or cut_breaths:
        edl["total_duration_s"] = round(sum(float(r["end"]) - float(r["start"]) for r in edl["ranges"]), 3)
    return log


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
    has_marcas = bool(payload.get("cutWords") or payload.get("cutBreaths"))
    has_edl = bool(payload.get("edl")) or has_marcas
    has_data = bool(payload.get("editData"))
    has_fix = bool(payload.get("corrections"))

    if has_edl:
        edl_path = edit / "edl.json"
        edl = load(edl_path)
        if not edl:
            sys.exit(f"não achei o edl.json em {edit}")
        before = len(edl.get("ranges", []))
        log, warns = [], []
        if payload.get("edl"):
            edl, log = apply_to_edl(edl, payload["edl"])
            warns = warn_clipped_edges(edl, edit, payload["edl"])
        if has_marcas:
            log += aplicar_marcas(edl, edit, payload.get("cutWords") or [], payload.get("cutBreaths") or [])

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

    if has_fix:
        log, fase2_ja_rodou = aplicar_correcoes(edit, payload["corrections"])
        print(f"texto: {len(payload['corrections'])} correção(ões) do editor")
        for l in log:
            print(l)
        if fase2_ja_rodou:
            # DIZER O PREÇO. A Fase 2 queima o texto quadro a quadro, então uma
            # palavra corrigida depois dela custa um render inteiro — e é melhor
            # o usuário saber disso agora do que descobrir esperando.
            print("  a Fase 2 já tinha rodado: a legenda é queimada, então o "
                  "texto novo só aparece\n    depois de `phase2.py <edit>` de novo")

    # CORREÇÃO DE TEXTO NÃO REFAZ O CORTE. A imagem e o som são os mesmos; só o
    # que está escrito muda. Refazer aqui custaria minutos por uma palavra.
    if has_edl and not args.no_render:
        print("\nrefazendo o corte…")
        # O ALVO É O RENDER QUE O USUÁRIO ESTÁ VENDO. Na Fase 1 é o proxy
        # (state.json.video = preview_proxy.mp4); refazer só o preview.mp4
        # deixava o portão e a escuta conferindo um proxy VELHO contra o EDL
        # novo. Depois da aprovação o alvo é o pleno.
        st = load(edit / "state.json", {}) or {}
        alvo = "preview_proxy.mp4" if str(st.get("video", "")).endswith("preview_proxy.mp4") else "preview.mp4"
        cmd = [sys.executable, str(HELPERS / "render.py"), str(edit / "edl.json"),
               "-o", str(edit / alvo), "--no-subtitles"]
        if alvo == "preview_proxy.mp4":
            cmd.append("--proxy")
        if args.draft:
            cmd.append("--draft")
        r = subprocess.run(cmd)
        if r.returncode != 0:
            sys.exit("o render falhou — o edl novo está salvo, o corte antigo continua no lugar")
        # o outro render descreve um corte que não existe mais
        outro = "preview.mp4" if alvo == "preview_proxy.mp4" else "preview_proxy.mp4"
        (edit / outro).unlink(missing_ok=True)
        print("\nconferindo…")
        subprocess.run([sys.executable, str(HELPERS / "verify_cut.py"),
                        str(edit / "edl.json"), str(edit / alvo)])

    state = load(edit / "state.json", {})
    state["message"] = ("Corte atualizado a partir do editor"
                        if has_edl else state.get("message", ""))
    (edit / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2))

    if notes:
        (edit / "pending_notes.json").write_text(json.dumps(notes, ensure_ascii=False, indent=2))
        print(f"\n{len(notes)} marcação(ões) escrita(s) — estas NÃO foram aplicadas, "
              f"porque são pedidos em texto e precisam de leitura:")
        for n in notes:
            if n.get("request"):
                print(f'  [pedido em texto] {n["text"]}')
            else:
                print(f'  [{n["renderedStart"]:.2f}–{n["renderedEnd"]:.2f}s] {n["text"]}')
        print("  guardadas em pending_notes.json")

    edits_path.unlink(missing_ok=True)
    if not has_edl and not has_data and not has_fix and not notes:
        print("nada a aplicar")


if __name__ == "__main__":
    main()

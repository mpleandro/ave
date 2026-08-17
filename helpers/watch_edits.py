#!/usr/bin/env python3
"""Emit one event per save from the preview UI.

Two files, both written by the UI and neither able to reach the chat on its own:
  - preview_edits.json — timeline adjustments and correction markers
  - preview_style.json — the Fase 1 → Fase 2 gate: editing style, caption style,
    edit elements

Run this under the Monitor tool so every save notifies the session automatically:

    Monitor(command="python3 <skill>/helpers/watch_edits.py '<edit>'",
            description="marcações do preview", persistent=True)

Each stdout line is one notification. Stays quiet while nothing changes.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path


# O PROJETO ABERTO AGORA, publicado pelo servidor. Ver preview_server.CURRENT.
CURRENT = Path.home() / ".avelin" / "current.json"


def current_root() -> Path | None:
    try:
        r = json.loads(CURRENT.read_text()).get("root")
        return Path(r) if r else None
    except (OSError, json.JSONDecodeError):
        return None


def request_digest(p: Path) -> str:
    """UM PROJETO NOVO CHEGOU PELA DROPZONE — é o `/ave <pasta>` sem o terminal.

    O editor cria a pasta e registra a fonte; transcrever, cortar e graduar é
    trabalho de agente. Sem este aviso o projeto nasceria e ficaria parado, com
    o usuário achando que largar o vídeo tinha começado alguma coisa.
    """
    try:
        d = json.loads(p.read_text())
    except (OSError, json.JSONDecodeError) as e:
        return f"preview_request.json ilegível ({e.__class__.__name__})"
    return "\n".join([
        "🎬 PROJETO NOVO pela dropzone do editor — COMECE A FASE 1.",
        f"   pasta de vídeos: {d.get('videosDir', '?')}",
        f"   fonte: {d.get('source', '?')}",
        "   O caminho normal da skill, do começo: ffprobe + transcrever,",
        "   pack_transcripts, transcript_audit (--fix-times), voice_levels,",
        "   detect_color, conversar a estratégia, EDL, proxy, e MOSTRAR.",
        "   Depois apague o preview_request.json.",
    ])


def digest(p: Path) -> str:
    try:
        d = json.loads(p.read_text())
    except (OSError, json.JSONDecodeError) as e:
        return f"preview_edits.json ilegível ({e.__class__.__name__}) — peça ao usuário para salvar de novo"

    parts: list[str] = []
    # O PEDIDO ESCRITO vem primeiro. Ele é a única parte que não se deduz do
    # resto do arquivo: marcações e cortes têm números, um pedido tem só o
    # texto — e um aviso que diz "ajustes salvos" sem mostrá-lo faz o agente
    # ir ler o arquivo para descobrir o que foi pedido, ou pior, não ir.
    req = (d.get("request") or "").strip()
    if req:
        parts.append(f'  PEDIDO: "{req}"')
    notes = d.get("notes") or []
    for i, n in enumerate(notes, 1):
        start, end = n.get("start", 0), n.get("end", 0)
        fase = n.get("phase", 1)
        parts.append(f'  {i}. [{fmt(start)} → {fmt(end)}] (fase {fase}) {n.get("text", "").strip()}')

    edl = d.get("edl") or {}
    n_ch = len(edl.get("changes") or [])
    n_rm = len(edl.get("removed") or [])
    ed = d.get("editData") or {}
    palavras = d.get("cutWords") or []
    respiros = d.get("cutBreaths") or []

    # As palavras riscadas e os respiros são PEDIDOS, e chegam com a folga já
    # medida — listá-los é o que impede que virem "o usuário mexeu em algo".
    if palavras:
        parts.append(f"  palavras riscadas ({len(palavras)}) — corte na fonte, "
                     f"não nos tempos do Whisper:")
        for w in palavras:
            folga = f"folga {w.get('gapBefore', 0):.2f}s/{w.get('gapAfter', 0):.2f}s"
            apertado = "  ⚠ SEM FOLGA — a emenda cai dentro da fala" if (
                not w.get("gapBefore") and not w.get("gapAfter")) else ""
            parts.append(f'    · "{w.get("text")}" [{w.get("source")} '
                         f'{w.get("srcStart")}–{w.get("srcEnd")}] {folga}{apertado}')
    if respiros:
        ganho = sum(float(b.get("trim") or 0) for b in respiros)
        parts.append(f"  respiros a ENCURTAR ({len(respiros)}, −{ganho:.1f}s no total).")
        parts.append("    Encurtar, NÃO remover: cada um mantém o piso `keep`. "
                     "Zerar o silêncio deixa a fala metralhada.")
        for b in respiros:
            parts.append(f'    · entre "{b.get("afterWord")}" e "{b.get("beforeWord")}" '
                         f'[{b.get("source")} {b.get("srcFrom")}–{b.get("srcTo")}] '
                         f'{b.get("dur")}s → {b.get("keep")}s (−{b.get("trim")}s)')

    head = []
    if req:
        head.append("1 pedido escrito")
    if notes:
        head.append(f"{len(notes)} marcação(ões)")
    if n_ch:
        head.append(f"{n_ch} take(s) reajustado(s)")
    if n_rm:
        head.append(f"{n_rm} take(s) removido(s)")
    if palavras:
        head.append(f"{len(palavras)} palavra(s) riscada(s)")
    if respiros:
        head.append(f"{len(respiros)} respiro(s) a encurtar")
    if ed:
        head.append("inserts/gancho movidos")
    if not head:
        head.append("ajustes salvos")

    out = [f"AJUSTES DO PREVIEW ({d.get('savedAt', '')}) — {', '.join(head)}. Aplique-os."]
    out += parts
    return "\n".join(out)


def style_digest(p: Path) -> str:
    """The gate choice: what Fase 2 should be built as."""
    try:
        d = json.loads(p.read_text())
    except (OSError, json.JSONDecodeError) as e:
        return f"preview_style.json ilegível ({e.__class__.__name__}) — peça ao usuário para salvar de novo"

    els = d.get("elementNames") or [
        k for k, v in (d.get("elements") or {}).items() if v
    ]
    head = (
        "TROCA DE ESTILO NO PREVIEW ({}) — REFAÇA a Fase 2 assim:"
        if d.get("rerender")
        else "ESTILO ESCOLHIDO NO PREVIEW ({}) — monte a Fase 2 assim:"
    ).format(d.get("savedAt", ""))
    out = [
        head,
        f'  · tipo de edição: {d.get("editName") or d.get("edit")}',
        f'  · headline: {d.get("headlineName") or d.get("headline")}',
        f'  · legenda: {d.get("captionsName") or d.get("captions")}',
    ]
    # Only worth reporting when the chosen styles actually paint an accent —
    # naming a colour that nothing uses reads as an instruction to go find a
    # place for it.
    accent = d.get("accent")
    if accent:
        if d.get("accentUsed"):
            name = d.get("accentName") or accent
            label = f"{name} ({accent})" if name.lower() != str(accent).lower() else accent
            out.append(f"  · cor de destaque: {label}")
        else:
            out.append("  · cor de destaque: não se aplica (os estilos escolhidos não usam destaque)")
    out.append(f'  · elementos: {", ".join(els) if els else "nenhum"}')
    # everything NOT chosen is an instruction too — it is what must stay out
    off = [k for k, v in (d.get("elements") or {}).items() if not v]
    if off:
        out.append(f'  · fora: {", ".join(off)}')
    if (d.get("note") or "").strip():
        out.append(f'  · observação do usuário: {d["note"].strip()}')
    return "\n".join(out)


def fmt(t: float) -> str:
    m, s = divmod(max(0.0, float(t)), 60)
    return f"{int(m)}:{s:05.2f}"


def notes_digest(p: Path) -> str:
    """As marcações escritas que o apply_edits separou por não poder aplicá-las."""
    try:
        notes = json.loads(p.read_text())
    except (OSError, json.JSONDecodeError) as e:
        return f"pending_notes.json ilegível ({e.__class__.__name__})"
    if not notes:
        return ""
    out = [f"MARCAÇÕES AGUARDANDO LEITURA ({len(notes)}) — o corte mecânico já foi aplicado:"]
    for n in notes:
        a = fmt(n.get("renderedStart", n.get("start", 0)))
        b = fmt(n.get("renderedEnd", n.get("end", 0)))
        out.append(f"· [{a} → {b}] {(n.get('text') or '').strip()}")
    return "\n".join(out)


def approval_digest(p: Path) -> str:
    """A APROVAÇÃO DO CORTE — o portão de fase, vindo do botão da interface."""
    try:
        d = json.loads(p.read_text())
    except (OSError, json.JSONDecodeError) as e:
        return f"preview_approval.json ilegível ({e.__class__.__name__})"
    nota = (d.get("note") or "").strip()
    out = [f"✅ CORTE APROVADO pelo usuário ({d.get('savedAt', '')}).",
           "   Agora, nesta ordem:",
           "   1. encode o corte final UMA vez:  render.py edl.json -o preview.mp4 --no-subtitles",
           "   2. aponte state.json.video para preview.mp4 (é o que destranca as camadas do render)",
           "   3. regenere segments.json a partir dos segmentos FINAIS",
           "   4. só então abra a aba Estilo (awaitingStyle: true)",
           "   Depois apague o preview_approval.json."]
    if nota:
        out.insert(1, f'   com observação: "{nota}"')
    return "\n".join(out)


def targets(root: Path) -> dict:
    return {
        root / "preview_edits.json": digest,
        root / "preview_style.json": style_digest,
        # TERCEIRO ALVO, e ele existe por causa de uma corrida real.
        # Com o servidor em --auto, o apply_edits.py dispara no mesmo instante
        # do salvamento, move as marcações escritas para cá e APAGA o
        # preview_edits.json. Entre duas sondagens o arquivo aparece e some, e o
        # aviso nunca sai: o usuário vê "enviado", o agente não recebe nada, e
        # os dois lados acham que a bola está com o outro. Vigiar o arquivo de
        # destino fecha a corrida — quem chegar primeiro, avisa.
        root / "pending_notes.json": notes_digest,
        # A aprovação: arquivo próprio, para não ser apagada junto com as
        # marcações quando o apply_edits consome o preview_edits.json.
        root / "preview_approval.json": approval_digest,
        # O projeto nascido na dropzone.
        root / "preview_request.json": request_digest,
    }


def main() -> int:
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    root = Path(arg).expanduser().resolve() if arg else current_root()
    if root is None:
        print("👀 Vigiando o editor — nenhum projeto aberto ainda.", flush=True)

    watched: dict = targets(root) if root else {}
    # a file already sitting there at startup means it is pending — say so once
    last: dict[Path, float | None] = {}
    for target, fn in watched.items():
        last[target] = target.stat().st_mtime if target.exists() else None
        if last[target] is not None:
            print(fn(target), flush=True)

    while True:
        # O VIGIA SEGUE O EDITOR. Antes ele era amarrado à pasta passada na
        # partida; agora a pessoa troca de projeto na própria tela, e sem isto
        # ele continuaria olhando o projeto anterior — ela salva, vê "enviado",
        # e o aviso nunca chega.
        #
        # Ponteiro NULO não desarma nada: nulo significa "tela inicial", e um
        # servidor desligado ou um ponteiro velho zerariam a vigilância de um
        # projeto que ainda está sendo trabalhado.
        novo = current_root()
        if novo is not None and novo != root:
            root = novo
            watched = targets(root)
            # Os pendentes do projeto NOVO são anunciados na entrada, como na
            # partida — quem troca de projeto quer saber o que ficou aberto lá.
            last = {}
            print(f"📁 PROJETO ABERTO NO EDITOR: {root}", flush=True)
            for target, fn in watched.items():
                last[target] = target.stat().st_mtime if target.exists() else None
                if last[target] is not None:
                    print(fn(target), flush=True)

        for target, fn in watched.items():
            try:
                cur = target.stat().st_mtime if target.exists() else None
            except OSError:
                cur = None
            if cur is not None and cur != last.get(target):
                last[target] = cur
                time.sleep(0.15)  # let the atomic replace settle before reading
                print(fn(target), flush=True)
            elif cur is None:
                last[target] = None  # applied and deleted — re-arm for the next save
        time.sleep(2)


if __name__ == "__main__":
    raise SystemExit(main())

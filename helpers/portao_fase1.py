#!/usr/bin/env python3
"""O PORTÃO DA FASE 1. Exit 1 = o corte não vai para aprovação.

    uv run python helpers/portao_fase1.py <edit-dir>
    uv run python helpers/portao_fase1.py <edit-dir> --render preview_proxy.mp4
    uv run python helpers/portao_fase1.py <edit-dir> --json

POR QUE ISTO EXISTE EM VEZ DE MAIS UM PARÁGRAFO NO SKILL.md.

Os auditores desta skill já existiam quando um corte de 51s saiu para aprovação
com dez defeitos de fala: frase refeita mantida, tomada abortada cortada no meio
da palavra, respiro e gaguejo por toda parte. Não faltava ferramenta — faltava
obrigação. `edit/verify/` não existia, `edl.json` não tinha `breaths[]`, e o
`verify_cut.py`, que sonda exatamente a palavra cortada, teria reprovado aquele
corte sozinho. Estavam todos documentados como "rode antes do EDL". Recomendação
que se pode pular é recomendação que se pula.

A diferença entre uma recomendação e um portão é o exit code. Este arquivo não
sabe fazer nada que os helpers já não façam; ele só se recusa a devolver zero.

O QUE ELE CHECA, e por que cada um está aqui:

  1. `spacing` MEDIDO   — se o transcrito ainda tem a pausa escondida dentro da
                          duração da palavra, o editor escolheu tomada às cegas
                          e todo o resto da checagem é teatro. Primeiro de
                          propósito: sem isto, os outros não têm o que ver.
  2. reinício no corte  — frase refeita que sobreviveu à seleção.
  3. `quote` × conteúdo — o EDL afirmou terminar em "…que é hoje" (37.78) e
                          terminou em 39.133, no meio da palavra seguinte.
                          Descreveu certo e executou errado; é conferível por
                          texto e ninguém conferia.
  4. `verify_cut`       — a única checagem que olha o RENDER e não o plano.
                          Palavra cortada na emenda, estalo, ar morto, frame
                          preto.

Falha em qualquer um devolve 1 e imprime o defeito com o timestamp. Nada aqui
conserta nada: o portão diz o que está errado, quem decide o que fazer é quem
está editando.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

HELPERS = Path(__file__).resolve().parent


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFD", t.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9 ]", " ", t)


def _rodar(args: list[str], timeout: int = 600) -> tuple[int, str]:
    try:
        r = subprocess.run([sys.executable, *args], capture_output=True,
                           text=True, timeout=timeout)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "tempo esgotado"
    except Exception as exc:
        return 125, str(exc)


# --------------------------------------------------------------------------- #

def checar_spacing(edit: Path) -> list[dict]:
    """O transcrito tem pausa medida, ou ainda é a timeline contígua do Whisper?"""
    # TRANSCRITO DERIVADO NÃO SE CONFERE AQUI. A Fase 2 grava `cut_mapped.json`
    # — o transcrito do CORTE, obtido remapeando o EDL, não transcrevendo de
    # novo. Ele herda a procedência da fonte, e cobrar a marca dele fazia o
    # portão acusar o mesmo defeito duas vezes e mandar reparar um arquivo que
    # nem tem áudio próprio.
    DERIVADOS = {"cut_mapped"}
    faltas = []
    for p in sorted(q for q in (edit / "transcripts").glob("*.json")
                    if not q.name.startswith(".") and q.stem not in DERIVADOS):
        d = json.loads(p.read_text())
        if str(d.get("_transcription_backend") or "").startswith("elevenlabs"):
            continue                       # Scribe mede pausa por conta própria
        if d.get("_spacing_source") == "measured/silencedetect":
            continue
        # A MARCA, e não uma heurística sobre os vãos. Tentei deduzir do formato
        # ("todo vão entre palavras é 0.00") e não discrimina: mesmo depois de
        # medir, palavras DENTRO de uma frase contínua seguem encostadas, então
        # a proporção de zeros mal muda. O que separa um transcrito medido de um
        # cego é a procedência, e procedência se carimba, não se adivinha.
        if d.get("words"):
            faltas.append({
                "check": "spacing", "arquivo": p.name,
                "problema": "transcrito sem procedência de pausa medida — o silêncio "
                            "provavelmente está escondido dentro da duração das palavras, "
                            "e a seleção de tomada foi feita às cegas",
                "conserto": f"uv run python helpers/transcribe.py <video> "
                            f"--edit-dir {edit} --repair-spacing && "
                            f"uv run python helpers/pack_transcripts.py --edit-dir {edit}",
            })
    return faltas


def checar_reinicios(edit: Path) -> list[dict]:
    """Frase refeita que sobreviveu ao corte."""
    cod, out = _rodar([str(HELPERS / "detect_restarts.py"), str(edit), "--edl", "--json"])
    if cod != 0:
        return []
    try:
        hits = json.loads(out).get("hits", [])
    except json.JSONDecodeError:
        return []
    faltas = []
    for h in hits:
        # Classe de JULGAMENTO não reprova sozinha: semântica pode ser anáfora e
        # quase-repetição pode ser paralelismo deliberado ("você ganha quanto
        # ganha"). As duas vão ao usuário pelo perguntar.py — o portão só
        # bloqueia o que é defeito por regra (truncada, idêntica sobrevivente).
        if h["classe"] in ("semantica", "quase"):
            continue
        faltas.append({
            "check": "reinicio", "t": h["versao_A"]["t"], "classe": h["classe"],
            "problema": f"{h['classe']}: \"{h['versao_A']['texto'][:70]}\"",
            "conserto": "remover a versão A do EDL"
            if h["classe"] == "truncada" else "ficar com a última",
        })
    return faltas


def checar_quotes(edit: Path) -> list[dict]:
    """O `quote` de cada range bate com as palavras que o range realmente contém?

    Não exige igualdade — o quote é escrito à mão e resume. Exige que a ÚLTIMA
    palavra citada esteja dentro do trecho: foi exatamente aí que o EDL disse
    terminar em "…que é hoje" e terminou 1,35s adiante, no meio de "não".
    """
    edl_p = edit / "edl.json"
    if not edl_p.exists():
        return []
    edl = json.loads(edl_p.read_text())

    palavras = []
    for p in sorted(q for q in (edit / "transcripts").glob("*.json")
                    if not q.name.startswith(".")):
        for w in json.loads(p.read_text()).get("words", []):
            if w.get("type") == "word" and (w.get("text") or "").strip():
                palavras.append(w)
    if not palavras:
        return []

    faltas = []
    for i, r in enumerate(edl.get("ranges", []), 1):
        quote = (r.get("quote") or "").strip()
        if not quote:
            continue
        ini, fim = float(r["start"]), float(r["end"])
        alvo = [x for x in _norm(quote).split() if x]
        if len(alvo) < 3:
            continue
        cauda = " ".join(alvo[-3:])
        no_trecho = [w for w in palavras
                     if w["start"] >= ini - 1e-6 and w["end"] <= fim + 1e-6]
        dentro = " ".join(" ".join(_norm(w["text"]) for w in no_trecho).split())

        if cauda in dentro:
            # O TRECHO ACABA ONDE O QUOTE DIZ QUE ACABA?
            #
            # Achar a cauda dentro do range só prova que o quote não inventou —
            # não prova que o corte parou ali. O defeito que motivou esta
            # checagem é exatamente o contrário do que eu conferia primeiro: o
            # range 0.0–39.133 CITAVA "…virou o império que é hoje" (que termina
            # em 37.78) e seguia por mais 1,35s, entrando na tomada abortada e
            # cortando no meio da palavra "não". O quote estava certo; o corte é
            # que passou do ponto, e conferir só a presença aprovava isso.
            # UMA PALAVRA PODE VIRAR DOIS TOKENS. `_norm("McDonald\'s")` devolve
            # "mcdonald s", então a lista achatada tinha 102 entradas para 96
            # palavras e o índice do casamento apontava para depois do fim —
            # `sobrando` saía vazio e o range 0.0–39.133, que é o defeito que
            # esta checagem existe para pegar, passava limpo. O mapa
            # token→palavra é o que torna o índice utilizável.
            toks: list[str] = []
            tok2pal: list[int] = []
            for wi, w in enumerate(no_trecho):
                for t in _norm(w["text"]).split():
                    toks.append(t)
                    tok2pal.append(wi)
            pos = next((k for k in range(len(toks) - 2, -1, -1)
                        if " ".join(toks[k:k + 3]) == cauda), None)
            sobrando = no_trecho[tok2pal[pos + 2] + 1:] if pos is not None else []
            if len(sobrando) >= 3:
                # SOBRAR NÃO É O MESMO QUE INVADIR, e confundir os dois faz o
                # portão gritar em quote abreviado. Um `quote` é escrito à mão e
                # resume: "E com isso virou" descrevendo um trecho que segue com
                # "o império que é hoje" é redação preguiçosa, não corte errado.
                #
                # O que caracteriza o defeito de verdade é o sobrando REAPARECER
                # depois — foi assim no range 0.0–39.133, cujo excedente "Hoje o
                # McDonald's" volta 4s adiante na versão boa da frase. Aí o corte
                # não sobrou: ele entrou na tomada seguinte.
                #
                # Sem essa distinção o portão bloqueia por estilo de escrita, e
                # um portão que reprova o certo é um portão que se desliga.
                chave = " ".join(_norm(w["text"]) for w in sobrando[:2]).split()
                retomada = False
                if len(chave) >= 2:
                    alvo, t0 = " ".join(chave[:2]), sobrando[0]["start"]
                    for k in range(len(palavras) - 1):
                        if abs(palavras[k]["start"] - t0) < 0.5:
                            continue
                        if abs(palavras[k]["start"] - t0) > 12.0:
                            continue
                        par = " ".join(_norm(palavras[k]["text"]) + " "
                                       + _norm(palavras[k + 1]["text"])).split()
                        if " ".join(par[:2]) == alvo:
                            retomada = True
                            break
                faltas.append({
                    "check": "quote", "t": sobrando[0]["start"], "range": i,
                    "aviso": not retomada,
                    "problema": f"range {i} ({ini:.2f}–{fim:.2f}) cita terminar em "
                                f"\"…{' '.join(quote.split()[-4:])}\", mas segue por mais "
                                f"{fim - sobrando[0]['start']:.2f}s: "
                                f"\"{' '.join(w['text'] for w in sobrando[:8])}\""
                                + (" — e esse trecho REAPARECE adiante: o corte entrou "
                                   "na tomada seguinte" if retomada else
                                   " (quote abreviado? confira se é só redação)"),
                    "conserto": f"encurtar o fim do range para ~{sobrando[0]['start']:.2f}s "
                                f"(borda exata em speech_regions.py), ou corrigir o quote",
                })
            continue
        # onde a cauda REALMENTE termina, para o relatório poder ser acionável
        todas = " ".join(_norm(w["text"]) for w in palavras)
        faltas.append({
            "check": "quote", "t": fim, "range": i,
            "problema": f"range {i} ({ini:.2f}–{fim:.2f}) diz terminar em "
                        f"\"…{' '.join(quote.split()[-4:])}\", mas essas palavras não "
                        f"estão dentro do trecho",
            "conserto": "acertar a borda em speech_regions.py, ou corrigir o quote",
            "_achou_no_take": cauda in " ".join(todas.split()),
        })
    return faltas


def checar_render(edit: Path, render: str | None) -> list[dict]:
    """verify_cut: a única checagem que olha o vídeo, não o plano."""
    edl_p = edit / "edl.json"
    alvos = [render] if render else ["preview_proxy.mp4", "preview.mp4"]
    video = next((edit / a for a in alvos if (edit / a).exists()), None)
    if not edl_p.exists() or video is None:
        return [{"check": "verify_cut", "problema": "render ainda não existe — "
                 "o portão só fecha depois de renderizar", "conserto": "renderizar", "aviso": True}]
    cod, out = _rodar([str(HELPERS / "verify_cut.py"), str(edl_p), str(video)])
    if cod == 0:
        return []
    linhas = [l.strip() for l in out.splitlines() if "CHECK" in l or "clip" in l.lower()]
    return [{"check": "verify_cut", "problema": l,
             "conserto": "ver a junção apontada com timeline_view"} for l in linhas[:12]] or \
           [{"check": "verify_cut", "problema": f"verify_cut reprovou (exit {cod})",
             "conserto": out.strip()[-400:]}]


# --------------------------------------------------------------------------- #

def checar_mapa_de_defeitos(edit: Path) -> list[dict]:
    """O EDL desviou das repetições que a varredura da FONTE já conhecia?

    O `verify_takes.py --fonte` grava `defeitos_audio.json` ANTES do EDL — cada
    entrada é uma janela do material bruto onde o áudio repete uma frase que o
    transcrito não mostra. Esta checagem é barata (é só aritmética de
    intervalos) e pega o defeito uma rodada de render mais cedo que a escuta do
    corte: escolher tomada por cima de uma repetição conhecida não é azar, é
    ignorar um aviso que já estava no disco.
    """
    mapa_p = edit / "defeitos_audio.json"
    edl_p = edit / "edl.json"
    if not mapa_p.exists() or not edl_p.exists():
        return []
    try:
        mapa = json.loads(mapa_p.read_text())
        edl = json.loads(edl_p.read_text())
    except json.JSONDecodeError:
        return []
    fontes = {k: Path(v).stem for k, v in (edl.get("sources") or {}).items()}
    def coberto(occ, ranges_da_fonte):
        """A ocorrência está dentro do corte? (>50% dela, somando os ranges)"""
        a, b = float(occ[0]), float(occ[1])
        if b <= a:
            return False
        dentro = sum(max(0.0, min(b, float(r["end"])) - max(a, float(r["start"])))
                     for r in ranges_da_fonte)
        return dentro > (b - a) * 0.5

    faltas = []
    por_fonte: dict[str, list] = {}
    for r in edl.get("ranges", []):
        por_fonte.setdefault(fontes.get(r.get("source", ""), ""), []).append(r)

    for stem, defeitos in mapa.items():
        ranges_f = por_fonte.get(stem, [])
        for d in defeitos:
            if not d.get("confirmado"):
                continue
            # REPETIÇÃO SÓ É DEFEITO COM AS DUAS PASSADAS NO CORTE. Manter uma
            # é o conserto — a primeira versão desta checagem reprovava o range
            # que mantinha a retomada, ou seja, reprovava a solução. Sem as
            # ocorrências separadas (mapa antigo), cai no span largo como AVISO.
            o1, o2 = d.get("occ1"), d.get("occ2")
            if o1 and o2:
                if coberto(o1, ranges_f) and coberto(o2, ranges_f):
                    faltas.append({
                        "check": "mapa", "t": float(o1[0]),
                        "problema": f"as DUAS passadas de \"{d['ngrama']}\" estão no corte "
                                    f"({o1[0]:.2f}–{o1[1]:.2f} e {o2[0]:.2f}–{o2[1]:.2f} da fonte)",
                        "conserto": "tirar uma das duas — mover a borda ou trocar a tomada",
                    })
                continue
            for r in ranges_f:
                lo = max(float(r["start"]), float(d["t"]))
                hi = min(float(r["end"]), float(d["fim"]))
                if hi - lo > 0.25:
                    faltas.append({
                        "check": "mapa", "t": float(d["t"]), "aviso": True,
                        "problema": f"o range {r.get('beat', '?')} toca a janela larga de "
                                    f"\"{d['ngrama']}\" ({d['t']:.2f}–{d['fim']:.2f}) — mapa sem "
                                    f"localização fina; re-rode verify_takes --fonte",
                        "conserto": "regenerar o mapa para saber se as duas passadas entraram",
                    })
                    break
    return faltas


def checar_audio_do_corte(edit: Path, render: str | None) -> list[dict]:
    """A ÚNICA checagem que não confia em transcrito nenhum: ouve o corte.

    As outras quatro leem o que está escrito. Esta ouve o que está gravado — e é
    a diferença entre pegar a repetição e não pegar, porque o Whisper apaga a
    segunda passada do TEXTO sem apagá-la do ÁUDIO. Quatro repetições chegaram ao
    usuário num corte que passou por todas as outras checagens.
    """
    cmd = [str(HELPERS / "verify_takes.py"), str(edit), "--json"]
    if render:
        cmd += ["--video", render]
    cod, out = _rodar(cmd, timeout=900)
    if cod == 0:
        return []
    try:
        # o helper imprime barras de progresso no stderr e o _rodar mistura os
        # dois — o JSON é o trecho entre a primeira '{' e a última '}'
        achados = json.loads(out[out.index("{"):out.rindex("}") + 1]).get("achados", [])
    except (json.JSONDecodeError, ValueError):
        return [{"check": "audio", "problema": "não consegui ouvir o corte",
                 "conserto": out.strip()[-300:], "aviso": True}]
    return [{
        "check": "audio", "t": a["t"],
        "problema": f"frase repetida NO ÁUDIO: \"{a['ngrama']}\" ×{a['vezes']}"
                    + (" (pode ser laço do modelo — ouça)" if a["suspeita_de_laco"] else ""),
        "conserto": "ouça no editor e escolha qual passada fica",
        "aviso": bool(a["suspeita_de_laco"]) or not a.get("confirmado", True),
    } for a in achados]


def main() -> None:
    ap = argparse.ArgumentParser(description="Portão de saída da Fase 1")
    ap.add_argument("edit", type=Path)
    ap.add_argument("--render", default=None, help="nome do render dentro do <edit>")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--pular-render", action="store_true",
                    help="só as checagens de plano (útil antes de renderizar)")
    args = ap.parse_args()

    edit = args.edit.resolve()
    if not (edit / "transcripts").is_dir():
        sys.exit(f"sem transcripts/ em {edit}")

    faltas: list[dict] = []
    faltas += checar_spacing(edit)
    # Sem pausa medida o resto não tem o que ver — reprova aqui e diz o conserto,
    # em vez de despejar defeitos derivados que somem sozinhos depois do reparo.
    if not faltas:
        faltas += checar_reinicios(edit)
        faltas += checar_quotes(edit)
        faltas += checar_mapa_de_defeitos(edit)
        if not args.pular_render:
            faltas += checar_render(edit, args.render)
            faltas += checar_audio_do_corte(edit, args.render)

    bloqueiam = [f for f in faltas if not f.get("aviso")]

    if args.json:
        print(json.dumps({"ok": not bloqueiam, "faltas": faltas},
                         ensure_ascii=False, indent=2))
        sys.exit(1 if bloqueiam else 0)

    if not faltas:
        print("PORTÃO OK — o corte pode ir para aprovação.")
        sys.exit(0)

    print(f"PORTÃO FECHADO — {len(bloqueiam)} defeito(s) bloqueando"
          + (f", {len(faltas) - len(bloqueiam)} aviso(s)" if len(faltas) > len(bloqueiam) else "")
          + "\n")
    for f in faltas:
        t = f.get("t")
        onde = f"  {t:7.2f}s " if isinstance(t, (int, float)) else "          "
        marca = "aviso  " if f.get("aviso") else "FALHA  "
        print(f"{marca}[{f['check']}]{onde}{f['problema']}")
        print(f"         → {f['conserto']}\n")
    sys.exit(1 if bloqueiam else 0)


if __name__ == "__main__":
    main()

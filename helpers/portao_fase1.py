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
        # NEM TODO .json EM transcripts/ É UM TRANSCRITO. O `corrections.json`
        # mora aqui (é o registro de onde o transcrito errou) e é uma LISTA —
        # `d.get(...)` nele levanta AttributeError e derruba o portão inteiro.
        # Filtrar por TIPO e não por nome: o próximo arquivo auxiliar que
        # alguém puser aqui não pode voltar a quebrar isto.
        if not isinstance(d, dict):
            continue
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
    sources = edl.get("sources", {})

    palavras = []
    for p in sorted(q for q in (edit / "transcripts").glob("*.json")
                    if not q.name.startswith(".")):
        d = json.loads(p.read_text())
        if not isinstance(d, dict):
            continue                 # corrections.json é lista — ver checar_spacing
        for w in d.get("words", []):
            if w.get("type") == "word" and (w.get("text") or "").strip():
                # `arquivo` é o stem do transcrito de origem — um EDL com mais
                # de uma fonte tem relógios independentes que se sobrepõem (o
                # gancho e o vídeo final começam os dois perto de 0s), e sem
                # esta marca uma palavra do arquivo errado casa por pura
                # coincidência de tempo com o range de outra fonte.
                palavras.append({**w, "arquivo": p.stem})
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
        src_path = sources.get(r.get("source"))
        src_stem = Path(src_path).stem if src_path else None
        no_trecho = [w for w in palavras
                     if (src_stem is None or w["arquivo"] == src_stem)
                     and w["start"] >= ini - 1e-6 and w["end"] <= fim + 1e-6]
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


_DEADAIR_RE = re.compile(r"(\d+\.\d+)[-–](\d+\.\d+)s.*CHECK-DEADAIR")


def _resolvidas(edit: Path) -> list[dict]:
    """Janelas de densidade que um humano JÁ ouviu isolada e registrou.

    Sem isto o portão vira uma parede que se aprende a atravessar. A checagem
    de densidade acusa "há fala aqui que ninguém transcreveu" — e isso pode ser
    duas coisas MUITO diferentes: um defeito no CORTE (gaguejo que vai ao ar)
    ou um defeito no TRANSCRITO (o áudio está ótimo, o texto é que perdeu a
    frase). O instrumento não separa as duas; só ouvir separa.

    Ouvida a janela, a resposta tem de ficar em algum lugar — senão o portão
    reprova o mesmo trecho em toda rodada, o operador aprende que aquele
    bloqueio é ruído, e no dia em que for real ele passa batido. O registro
    mora no `corrections.json`, que já é o arquivo de "onde o transcrito errou
    e o que é verdade", com `kind: "densidade"` e o texto que a passada isolada
    ouviu — a EVIDÊNCIA junto da dispensa, nunca um "ignore isto" pelado.

        [{"source": "<stem da fonte>", "srcStart": 5.23, "srcEnd": 8.42,
          "kind": "densidade",
          "heard": "Bom, vamos categorizar nossas atividades…",
          "note": "conferido isolado 2x — áudio íntegro, o transcrito é que perdeu a cabeça"}]
    """
    p = edit / "transcripts" / "corrections.json"
    if not p.exists():
        return []
    try:
        todas = json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    return [c for c in todas
            if isinstance(c, dict) and c.get("kind") == "densidade"
            and c.get("heard")]          # sem o que se ouviu, não é resolução


def checar_transcricao(edit: Path) -> list[dict]:
    """FALA QUE O TRANSCRITO NÃO ESCREVEU — o auditor que faltava no portão.

    O `transcript_audit.py` está documentado como Hard Rule 15 ("RODE ANTES DE
    ESCREVER O EDL") desde que existe, e o portão nunca o chamou. Ficou como as
    outras recomendações que viraram este arquivo: sempre presente na
    documentação, sempre ausente na hora em que o defeito passa.

    Ele mede duas coisas, e as duas custam ffmpeg, não API:

      · **carimbo esticado** — o Whisper estende o fim da palavra por cima da
        pausa seguinte. BLOQUEIA: o conserto é mecânico (`--fix-times`), é
        idempotente, e é esse carimbo que vira legenda queimada na Fase 2.
      · **densidade baixa** — região de fala com poucas palavras dentro, isto é,
        fala que ninguém transcreveu. Aqui o critério é mais fino do que
        "achou": só BLOQUEIA quando a janela suspeita cai DENTRO de um range do
        EDL. Fora dele o áudio não entra no vídeo, e reprovar por isso ensinaria
        a ignorar o portão — que é como um portão morre.
    """
    edl_p = edit / "edl.json"
    if not edl_p.exists():
        return []
    rel = edit / ".preview_cache" / "transcript_audit.json"
    rel.parent.mkdir(parents=True, exist_ok=True)
    cod, out = _rodar([str(HELPERS / "transcript_audit.py"), str(edit),
                       "-o", str(rel)], timeout=900)
    if not rel.exists():
        return [{"check": "transcricao", "aviso": True,
                 "problema": "não consegui auditar a transcrição",
                 "conserto": out.strip()[-300:] or f"exit {cod}"}]
    try:
        achados = json.loads(rel.read_text())
    except json.JSONDecodeError:
        return []

    # As janelas do EDL, por arquivo de fonte — é contra elas que a densidade
    # decide se o defeito ENTRA no vídeo ou só existe no material bruto.
    try:
        edl = json.loads(edl_p.read_text())
    except json.JSONDecodeError:
        return []
    stems = {k: Path(v).stem for k, v in (edl.get("sources") or {}).items()}
    janelas: dict[str, list[tuple[float, float]]] = {}
    for r in edl.get("ranges", []):
        stem = stems.get(r.get("source", ""), "")
        janelas.setdefault(stem, []).append((float(r["start"]), float(r["end"])))

    def no_corte(arquivo: str, a: float, b: float) -> bool:
        stem = Path(arquivo or "").stem
        return any(min(b, e) - max(a, ini) > 0.05
                   for ini, e in janelas.get(stem, []))

    resolvidas = _resolvidas(edit)
    faltas = []
    for f in achados:
        ini, fim = float(f.get("start", 0)), float(f.get("end", 0))
        arq = f.get("file", "")
        if "word" in f:            # carimbo esticado
            faltas.append({
                "check": "transcricao", "t": ini,
                "problema": f"{f['word']!r} carimbada em {f.get('dur', 0):.2f}s com "
                            f"{f.get('excess', 0):.2f}s de silêncio dentro "
                            f"({arq})",
                "conserto": f"uv run python helpers/transcript_audit.py {edit} --fix-times",
            })
        elif "dens" in f:          # fala sem texto
            if any(Path(c.get("source", "")).stem == Path(arq or "").stem
                   and min(fim, float(c.get("srcEnd", 0))) - max(ini, float(c.get("srcStart", 0))) > 0.05
                   for c in resolvidas):
                continue               # já ouvida isolada e registrada — ver _resolvidas
            dentro = no_corte(arq, ini, fim)
            faltas.append({
                "check": "transcricao", "t": ini, "aviso": not dentro,
                "problema": f"{f.get('n', 0)} palavra(s) em {f.get('dur', 0):.2f}s de fala "
                            f"({f.get('dens', 0):.2f}/s vs mediana {f.get('median', 0):.2f}/s)"
                            + (" — DENTRO do corte" if dentro else " — fora do corte"),
                "conserto": "ouça a janela isolada: "
                            f"transcript_audit.py {edit} --recheck",
            })
        else:                      # divergência entre as duas passadas
            faltas.append({
                "check": "transcricao", "t": ini, "aviso": True,
                "problema": f"fonte e corte discordam aqui: "
                            f"{(f.get('fonte') or '(nada)')[:40]!r} × "
                            f"{(f.get('corte') or '(nada)')[:40]!r}",
                "conserto": "resolva com uma TERCEIRA passada isolada (--recheck), "
                            "nunca escolhendo um lado por preferência",
            })
    return faltas


def checar_triagem(edit: Path) -> list[dict]:
    """TODA DÚVIDA FOI RESOLVIDA ANTES DE RENDERIZAR?

    Regra do usuário (2026-08-27), e ela nasceu de um corte entregue com três
    defeitos que ele ouviu e eu não: *"antes de renderizar a fase 1, pergunta
    para o usuário tudo o que tiver dúvida, para não ter que consertar e gerar
    de novo depois"*.

    A aritmética que a justifica: descobrir DEPOIS custa uma rodada de portão
    (~5 min) mais um re-render (~1 min) mais a atenção de quem já tinha
    aprovado. Descobrir ANTES custa uma pergunta. E não é hipotético — dois dos
    três defeitos daquele corte estavam numa lista de 60 candidatos que o
    `detect_restarts` me entregou e eu classifiquei como ruído SEM OUVIR
    nenhum, que é exatamente o veredito sem medição que a Hard Rule 18 proíbe.

    O que esta checagem cobra é só isto: cada repetição da classe SEMÂNTICA que
    sobreviveu ao corte tem uma decisão registrada em `triagem.json` — removida,
    mantida, ou perguntada e respondida — com o motivo junto. Não cobra a
    decisão CERTA (ninguém sabe a intenção de quem falou além dele); cobra que
    alguém tenha olhado.

        [{"ngrama": "acabam surgindo do", "t": 57.19, "decisao": "remover",
          "motivo": "duas versões da mesma frase; fica a segunda",
          "quem": "usuario"}]

    A classe `quase` fica de fora do bloqueio de propósito: das 7 que ela achou
    neste corte, 7 eram prosa normal ("e urgente ~ e importante"). Bloquear por
    ela ensinaria a forçar o portão, que é como um portão morre.
    """
    edl_p = edit / "edl.json"
    if not edl_p.exists():
        return []
    cod, out = _rodar([str(HELPERS / "detect_restarts.py"), str(edit), "--edl", "--json"])
    try:
        hits = json.loads(out[out.index("{"):out.rindex("}") + 1]).get("hits", [])
    except (json.JSONDecodeError, ValueError):
        return []
    pendentes = [h for h in hits if h.get("classe") == "semantica"]
    if not pendentes:
        return []

    tri = edit / "triagem.json"
    try:
        decididos = json.loads(tri.read_text()) if tri.exists() else []
    except json.JSONDecodeError:
        decididos = []

    def resolvido(h: dict) -> bool:
        ng = str(h.get("ngrama", "")).strip().lower()
        t = float(h.get("versao_A", {}).get("t", -1))
        for d in decididos:
            if str(d.get("ngrama", "")).strip().lower() != ng:
                continue
            # tempo por PROXIMIDADE: o relógio do corte muda a cada re-render,
            # e a decisão é sobre a frase, não sobre o instante
            if d.get("t") is None or abs(float(d["t"]) - t) <= 2.0:
                return True
        return False

    faltam = [h for h in pendentes if not resolvido(h)]
    if not faltam:
        return []
    return [{
        "check": "triagem", "t": float(h["versao_A"]["t"]),
        "problema": f"repetição sem decisão: \"{h['ngrama']}\" "
                    f"(Δ{h.get('delta', 0)}s) — "
                    f"\"{h['versao_A']['texto'][:44]}\" × "
                    f"\"{h['versao_B']['texto'][:44]}\"",
        "conserto": "ouça, decida (ou pergunte ao usuário) e registre em triagem.json",
    } for h in faltam[:10]]


def checar_render(edit: Path, render: str | None) -> list[dict]:


    """verify_cut: a única checagem que olha o vídeo, não o plano.

    CHECK-DEADAIR não distingue ar morto de verdade de uma pausa retórica que
    o usuário já ouviu e decidiu manter (`propose_breaths.py` já faz essa
    classificação; o humano pode discordar dela nos dois sentidos). Sem uma
    forma de registrar "já revisei, é assim mesmo", o portão volta a bloquear
    a cada render por um silêncio que ninguém considera defeito — mesma razão
    do `aceito` em `checar_mapa_de_defeitos`. `ar_morto_aceito` no EDL é essa
    marca: pares [ini, fim] em tempo de OUTPUT (o que `verify_cut` imprime),
    casados por sobreposição — não por igualdade exata, porque o silêncio
    medido varia meio quadro entre renders do mesmo corte.
    """
    edl_p = edit / "edl.json"
    alvos = [render] if render else ["preview_proxy.mp4", "preview.mp4"]
    video = next((edit / a for a in alvos if (edit / a).exists()), None)
    if not edl_p.exists() or video is None:
        return [{"check": "verify_cut", "problema": "render ainda não existe — "
                 "o portão só fecha depois de renderizar", "conserto": "renderizar", "aviso": True}]
    cod, out = _rodar([str(HELPERS / "verify_cut.py"), str(edl_p), str(video)])
    if cod == 0:
        return []
    aceitos = []
    try:
        aceitos = json.loads(edl_p.read_text()).get("ar_morto_aceito") or []
    except json.JSONDecodeError:
        pass
    def aceito(linha: str) -> bool:
        m = _DEADAIR_RE.search(linha)
        if not m:
            return False
        a, b = float(m.group(1)), float(m.group(2))
        return any(min(b, float(hi)) - max(a, float(lo)) > 0 for lo, hi in aceitos)
    linhas = [l.strip() for l in out.splitlines()
              if ("CHECK" in l or "clip" in l.lower()) and not aceito(l)]
    return [{"check": "verify_cut", "problema": l,
             "conserto": "ver a junção apontada com timeline_view"} for l in linhas[:12]] or \
           ([{"check": "verify_cut", "problema": f"verify_cut reprovou (exit {cod})",
             "conserto": out.strip()[-400:]}] if not aceitos else [])


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

    for stem, entry in mapa.items():
        # `entry` é o achado direto (mapa antigo) ou {"fp":.., "achados":[..]}
        # (formato com cache por fonte, ver `impressao_digital` em
        # verify_takes.py) — os dois convivem porque um mapa gravado antes
        # desta mudança continua legível.
        defeitos = entry.get("achados", []) if isinstance(entry, dict) else entry
        ranges_f = por_fonte.get(stem, [])
        for d in defeitos:
            if not d.get("confirmado"):
                continue
            if d.get("aceito"):
                # Repetição CONFIRMADA no áudio, mas um humano já ouviu e decidiu
                # que é intencional (anáfora/definição, não retomada) — a Hard
                # Rule que criou este checador também diz que o modelo nunca
                # resolve isso sozinho, só recomenda; uma vez que o usuário
                # decidiu, o portão não pode voltar a bloquear a cada render.
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


def pode_pular_a_escuta(edit: Path) -> bool:
    """Dá para NÃO ouvir o render? Só quando não existe emenda para ouvir.

    A versão anterior desta função perguntava outra coisa — "o mapa da fonte
    cobre todas as fontes e está limpo?" — e usava a resposta para pular a
    escuta do corte. O raciocínio tinha um buraco que só aparece escrito:

      o mapa da fonte prova que o EDL DESVIOU das repetições que existiam no
      material bruto. Ele não sabe nada sobre as que a MONTAGEM cria.

    Duas ocorrências distantes na fonte não são repetição nenhuma lá; emendadas
    lado a lado por um corte, viram. É o caso das várias tomadas da mesma CTA
    gravadas em sequência: cada uma sozinha é limpa, e escolher duas por engano
    produz um eco que nenhum mapa de fonte previu. A escuta do render é a ÚNICA
    checagem que enxerga a emenda, então ela não pode ser pulada por um
    argumento que fala da fonte.

    O que autoriza pular, e só isto: **não haver emenda**. Um EDL de trecho
    único não tem junção onde uma duplicação possa nascer, e aí a escuta do
    render responderia exatamente o que a varredura da fonte já respondeu.
    """
    edl_p = edit / "edl.json"
    if not edl_p.exists():
        return False
    try:
        edl = json.loads(edl_p.read_text())
    except json.JSONDecodeError:
        return False
    if len(edl.get("ranges", [])) > 1:
        return False        # tem emenda → tem o que ouvir
    # sem emenda, ainda exige que a fonte tenha sido ouvida alguma vez
    mapa_p = edit / "defeitos_audio.json"
    if not mapa_p.exists():
        return False
    try:
        mapa = json.loads(mapa_p.read_text())
    except json.JSONDecodeError:
        return False
    fontes = {Path(v).stem for v in (edl.get("sources") or {}).values()}
    return fontes.issubset(mapa.keys())


def checar_audio_do_corte(edit: Path, render: str | None) -> list[dict]:
    """A ÚNICA checagem que não confia em transcrito nenhum: ouve o corte.

    As outras quatro leem o que está escrito. Esta ouve o que está gravado — e é
    a diferença entre pegar a repetição e não pegar, porque o Whisper apaga a
    segunda passada do TEXTO sem apagá-la do ÁUDIO. Quatro repetições chegaram ao
    usuário num corte que passou por todas as outras checagens.
    """
    # A DECISÃO DO USUÁRIO TEM DE SOBREVIVER AO PRÓXIMO RENDER.
    #
    # Hard Rule 18 manda PERGUNTAR quando o detector acusa repetição: anáfora e
    # gaguejo são a mesma string e só quem falou sabe a diferença. Mas perguntar
    # uma vez e esquecer é pior que não perguntar — o portão reprova o mesmo
    # "um incêndio ×2" em toda rodada, o usuário responde "é a definição" toda
    # vez, e na terceira ele aprende a clicar em "Aprovar mesmo assim" sem ler.
    # Aí o portão perdeu o poder de barrar a repetição que É defeito.
    #
    # `repeticao_aceita` no EDL é a memória: n-gramas que o dono da voz já ouviu
    # e declarou deliberados. Casa por TEXTO e não por tempo, porque o tempo de
    # output muda a cada re-render e a decisão é sobre a frase, não sobre o
    # relógio. Mesma ideia do `aceito` em checar_mapa_de_defeitos.
    try:
        aceitas = {str(x).strip().lower()
                   for x in (json.loads((edit / "edl.json").read_text())
                             .get("repeticao_aceita") or [])}
    except (OSError, json.JSONDecodeError):
        aceitas = set()
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
    } for a in achados if str(a["ngrama"]).strip().lower() not in aceitas]


def _impressao(edit: Path, render: str | None) -> dict | None:
    """O que o veredito DESCREVE: este render + este EDL, por tamanho e mtime.

    Sem isto o portão é honesto e insuportável. Ele leva ~4 min (a escuta do
    render transcreve ~170 janelas curtas), e roda duas vezes seguidas pelo
    caminho normal: uma quando eu confiro antes de mostrar, outra quando o
    usuário clica em "Aprovar corte". A segunda responde exatamente a mesma
    pergunta sobre exatamente os mesmos bytes — e o usuário fica 4 min olhando
    uma barra por uma resposta que já estava no disco.

    A chave é o par (render, EDL): o render porque é o que se ouve, e o EDL
    porque é onde moram as ACEITAÇÕES (`ar_morto_aceito`, `repeticao_aceita`)
    — registrar uma decisão tem de invalidar o veredito na hora, senão o
    portão continuaria reprovando o que o usuário acabou de dispensar.
    """
    alvos = [render] if render else ["preview_proxy.mp4", "preview.mp4"]
    vid = next((edit / a for a in alvos if (edit / a).exists()), None)
    edl = edit / "edl.json"
    if vid is None or not edl.exists():
        return None
    def fp(q: Path) -> list:
        st = q.stat()
        return [q.name, st.st_size, round(st.st_mtime, 3)]
    return {"render": fp(vid), "edl": fp(edl)}


def _veredito_cacheado(edit: Path, imp: dict | None) -> dict | None:
    if not imp:
        return None
    p = edit / ".preview_cache" / "portao.json"
    try:
        d = json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return d if d.get("impressao") == imp else None


def _gravar_veredito(edit: Path, imp: dict | None, ok: bool, faltas: list) -> None:
    if not imp:
        return
    p = edit / ".preview_cache" / "portao.json"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"impressao": imp, "ok": ok, "faltas": faltas},
                                ensure_ascii=False))
    except OSError:
        pass          # cache nunca derruba o portão que ele acelera


def main() -> None:


    ap = argparse.ArgumentParser(description="Portão de saída da Fase 1")
    ap.add_argument("edit", type=Path)
    ap.add_argument("--render", default=None, help="nome do render dentro do <edit>")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--pular-render", action="store_true",
                    help="só as checagens de plano (útil antes de renderizar)")
    ap.add_argument("--forcar", action="store_true",
                    help="ignora o veredito em cache e reconfere do zero")
    ap.add_argument("--sempre-ouvir", action="store_true",
                    help="roda `checar_audio_do_corte` mesmo quando o mapa da "
                         "fonte já prova o EDL limpo (rede de segurança extra, "
                         "ao custo de repetir uma varredura cara — ver abaixo)")
    args = ap.parse_args()

    edit = args.edit.resolve()
    if not (edit / "transcripts").is_dir():
        sys.exit(f"sem transcripts/ em {edit}")

    # VEREDITO FRESCO SE REUSA. Só o caminho COMPLETO (com render) entra no
    # cache: o `--pular-render` responde outra pergunta (só o plano), e servir
    # um ao outro diria "conferido" sobre um render que ninguém ouviu.
    imp = None if args.pular_render else _impressao(edit, args.render)
    if not args.forcar:
        pronto = _veredito_cacheado(edit, imp)
        if pronto is not None:
            faltas = pronto.get("faltas", [])
            bloqueiam = [f for f in faltas if not f.get("aviso")]
            if args.json:
                print(json.dumps({"ok": not bloqueiam, "faltas": faltas,
                                  "cache": True}, ensure_ascii=False, indent=2))
            elif not bloqueiam:
                print("PORTÃO OK — o corte pode ir para aprovação. (veredito em cache: "
                      "nem o render nem o EDL mudaram desde a última conferência)")
            else:
                print(f"PORTÃO FECHADO — {len(bloqueiam)} defeito(s) bloqueando "
                      "(veredito em cache)\n")
                for f in faltas:
                    t = f.get("t")
                    onde = f"  {t:7.2f}s " if isinstance(t, (int, float)) else "          "
                    print(f"{'aviso  ' if f.get('aviso') else 'FALHA  '}[{f['check']}]{onde}{f['problema']}")
            sys.exit(1 if bloqueiam else 0)

    faltas: list[dict] = []
    faltas += checar_spacing(edit)
    # Sem pausa medida o resto não tem o que ver — reprova aqui e diz o conserto,
    # em vez de despejar defeitos derivados que somem sozinhos depois do reparo.
    if not faltas:
        faltas += checar_reinicios(edit)
        faltas += checar_triagem(edit)
        faltas += checar_transcricao(edit)
        faltas += checar_quotes(edit)
        faltas_mapa = checar_mapa_de_defeitos(edit)
        faltas += faltas_mapa
        if not args.pular_render:
            faltas += checar_render(edit, args.render)
            # A VARREDURA DO RENDER (`checar_audio_do_corte`) é a ÚNICA
            # checagem que ouve a EMENDA — ver `pode_pular_a_escuta`, que
            # explica por que o mapa da fonte não pode autorizar o pulo. Ela é
            # cara (minutos) e é o preço de não entregar um eco.
            if args.sempre_ouvir or faltas_mapa or not pode_pular_a_escuta(edit):
                faltas += checar_audio_do_corte(edit, args.render)

    bloqueiam = [f for f in faltas if not f.get("aviso")]
    _gravar_veredito(edit, imp, not bloqueiam, faltas)

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

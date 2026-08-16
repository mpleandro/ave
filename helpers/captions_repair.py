#!/usr/bin/env python3
"""Recupera a fala que o MAPEAMENTO do EDL não conseguiu legendar.

O buraco que este helper fecha
------------------------------
A legenda sai das FONTES deslocadas pelo EDL (Hard Rule 14) — nunca de uma
segunda transcrição do corte. Isso está certo e continua valendo. Mas o
mapeamento é por TEMPO, e existe um caso em que o tempo da fonte mente de um
jeito que nenhum remapeamento resolve:

    o locutor erra, refaz a frase, e o Whisper entrega UMA passada limpa.

As duas tentativas viram um texto só, e esse texto fica com os carimbos da
tentativa que veio PRIMEIRO. O EDL corta a tentativa abortada — corretamente —
e as palavras de abertura da tomada que FICOU são jogadas fora junto, porque os
carimbos delas caem antes do início do range. O áudio tem as palavras; a
legenda não. Nada acusa: o transcrito lê perfeito, o corte está certo, o
`verify_cut` não vê defeito nenhum, e o usuário descobre assistindo.

Medido no #29, duas vezes no mesmo vídeo:
  · saída 24,47s — "Então VOCÊ QUER A SEGURANÇA DA VIDA CORPORATIVA ou os
    ganhos": 7 palavras sem legenda, enterradas sob um "ou" de 2,22s.
  · saída 41,38s — "EU TENHO A VISÃO QUE VOCÊ deve evitar": 5 palavras sem
    legenda, com "você" carimbada 1,52s na fonte.

Como ele acha
-------------
Duas assinaturas, ambas medidas no transcrito JÁ MAPEADO:
  · palavra esticada (>0,7s) — o carimbo cobriu fala que não foi escrita;
  · vão entre palavras (>0,8s) — pode ser pausa real ou fala perdida.

Como ele confirma
-----------------
Transcrevendo a janela do RENDER **isolada**, e aqui a forma da janela é o que
separa diagnóstico de alucinação (lição registrada no project.md do #29):

  · a janela COMEÇA na emenda do `jcut_timeline` imediatamente anterior. Janela
    que começa no meio de uma frase faz o modelo COMPLETAR a frase familiar a
    partir do pedaço cortado na borda, e ele inventa o que não está lá.
  · a janela é LONGA (>= 6s). Curta demais e sobra contexto de menos.

O que ele NÃO faz, e por quê
----------------------------
Não troca a janela inteira pela passada isolada. A primeira versão fazia isso e
estava errada por dois motivos, os dois medidos no #29:

  · as janelas se SOBREPÕEM (quatro suspeitos caíram na mesma emenda 41,333) e
    cada uma "recuperava" as mesmas palavras, uma por cima da outra;
  · trocar tudo significa aceitar a segunda passada onde ela também erra. Na
    mesma janela em que ela recupera 5 palavras certas, ela escreve
    "se É a opção" onde a fonte tem "se HÁ a opção" — 30 palavras boas
    trocadas para ganhar 5 é exatamente o que a Hard Rule 14 proíbe.

Então a enxertia é CIRÚRGICA: das palavras isoladas entram só as que caem
DENTRO do vão (ou dentro do carimbo esticado). Todo o resto do mapeamento fica
intacto, com o texto e os tempos que já tinha. As janelas são unidas antes de
transcrever, então cada trecho do corte é ouvido uma vez só.

    uv run python helpers/captions_repair.py <edit> [--apply]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HELPERS = Path(__file__).resolve().parent

ESTICADA = 0.70     # s — carimbo que cobriu fala não escrita
VAO = 0.80          # s — silêncio entre palavras que merece conferência
JANELA_MIN = 6.0    # s — janela curta alucina; ver docstring
FOLGA = 0.05        # s — tolerância nas bordas ao casar palavra com janela


def seg(w: dict) -> tuple[float, float]:
    """(início, fim) em segundos, aceitando os dois formatos que circulam."""
    if "startMs" in w:
        return w["startMs"] / 1000, w["endMs"] / 1000
    return float(w.get("start", 0)), float(w.get("end", 0))


def texto(w: dict) -> str:
    return str(w.get("text") or w.get("word") or "").strip()


def carregar(p: Path) -> list[dict]:
    d = json.loads(p.read_text())
    return (d.get("words") or []) if isinstance(d, dict) else d


def regravar(p: Path, original: str, palavras: list[dict]) -> None:
    """Grava mantendo a FORMA do arquivo original.

    O `cut_mapped.json` é um objeto com `words` dentro (mais os campos que a
    transcrição trouxe); as legendas são uma lista pura. Desembrulhar na leitura
    e gravar a lista destrói o invólucro — e o `phase2.py` faz
    `json.loads(...).get("words")`, então ele morre com AttributeError na
    rodada seguinte, longe daqui.
    """
    d = json.loads(original)
    if isinstance(d, dict):
        d["words"] = palavras
        p.write_text(json.dumps(d, ensure_ascii=False, indent=1))
    else:
        p.write_text(json.dumps(palavras, ensure_ascii=False, indent=1))


def suspeitos(words: list[dict]) -> list[tuple[str, float, float, str]]:
    """Trechos a conferir, como (tipo, início, fim, motivo)."""
    out = []
    for w in words:
        a, b = seg(w)
        if b - a > ESTICADA:
            out.append(("esticada", a, b, f'"{texto(w)}" esticada {b - a:.2f}s'))
    for x, y in zip(words, words[1:]):
        _, fim = seg(x)
        ini, _ = seg(y)
        if ini - fim > VAO:
            out.append(("vão", fim, ini,
                        f'vão de {ini - fim:.2f}s entre "{texto(x)}" e "{texto(y)}"'))
    return sorted(out, key=lambda s: s[1])


def unir(janelas: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Funde janelas que se tocam — cada trecho do corte é ouvido UMA vez.

    Sem isto, quatro suspeitos atrás da mesma emenda viram quatro transcrições
    da mesma janela, e cada uma tenta enxertar as mesmas palavras por cima da
    anterior.
    """
    unidas: list[list[float]] = []
    for a, b in sorted(janelas):
        if unidas and a <= unidas[-1][1]:
            unidas[-1][1] = max(unidas[-1][1], b)
        else:
            unidas.append([a, b])
    return [(a, b) for a, b in unidas]


def emenda_antes(t: float, junctions: list[float]) -> float:
    """A emenda do J-cut imediatamente anterior a `t` — onde a janela começa."""
    anteriores = [j for j in junctions if j <= t + FOLGA]
    return max(anteriores) if anteriores else 0.0


def transcrever(video: Path, ini: float, dur: float, lang: str) -> list[dict]:
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        clip = td / "janela.m4a"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{ini:.3f}",
                        "-t", f"{dur:.3f}", "-i", str(video),
                        "-c:a", "aac", "-b:a", "128k", "-vn", str(clip)], check=True)
        r = subprocess.run([sys.executable, str(HELPERS / "transcribe.py"), str(clip),
                            "--edit-dir", str(td), "--language", lang],
                           capture_output=True, text=True)
        saida = td / "transcripts" / "janela.json"
        if not saida.exists():
            print(f"    (transcrição falhou: {r.stderr.strip()[-160:]})", file=sys.stderr)
            return []
        palavras = carregar(saida)
    # de relativo à janela para absoluto na linha de tempo do corte
    fora = []
    for w in palavras:
        a, b = seg(w)
        if texto(w):
            fora.append({"text": texto(w), "start": round(ini + a, 3),
                         "end": round(ini + b, 3)})
    return fora


def no_formato(w: dict, molde: dict) -> dict:
    """Reescreve a palavra ouvida no formato do arquivo que a recebe.

    O mapeado usa `start`/`end` em segundos e as legendas usam `startMs`; um
    arquivo com os dois formatos misturados atravessa este helper (que lê os
    dois) e quebra no próximo, que lê um só.
    """
    saida = {k: v for k, v in molde.items() if k not in
             ("text", "word", "start", "end", "startMs", "endMs")}
    saida["text" if "text" in molde else "word"] = texto(w)
    return por_tempo(saida, *seg(w))


def por_tempo(w: dict, a: float, b: float) -> dict:
    """Grava (início, fim) no formato que a palavra já usa."""
    if "startMs" in w or "endMs" in w:
        w["startMs"], w["endMs"] = round(a * 1000), round(b * 1000)
    else:
        w["start"], w["end"] = round(a, 3), round(b, 3)
    return w


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edit", type=Path)
    ap.add_argument("--mapped", type=Path, default=None)
    ap.add_argument("--video", type=Path, default=None)
    ap.add_argument("--language", default="pt")
    ap.add_argument("--apply", action="store_true",
                    help="grava o resultado; sem isto só relata")
    a = ap.parse_args()

    edit = a.edit.expanduser().resolve()
    mapped = a.mapped or edit / "transcripts" / "cut_mapped.json"
    video = a.video or edit / "preview.mp4"
    if not mapped.exists():
        sys.exit(f"não achei o transcrito mapeado em {mapped}")
    if not video.exists():
        sys.exit(f"não achei o corte em {video}")

    original = mapped.read_text()
    words = carregar(mapped)
    if not words:
        sys.exit(f"{mapped.name} não tem palavras — rode o cut_transcript.py antes")
    edl = json.loads((edit / "edl.json").read_text()) if (edit / "edl.json").exists() else {}
    junctions = sorted(
        t.get("audio_start_in_output", t.get("video_start_in_output", 0))
        for t in (edl.get("jcut_timeline") or [])) or [0.0]
    fim_video = max(seg(w)[1] for w in words)

    # A janela começa na emenda em que a tomada NOVA entra, e para um vão essa
    # emenda é a que cai DENTRO dele — a fala recomeça ali. Medido no #29: a
    # mesma janela começando 0,8s antes (no fim da tomada anterior) fez a
    # passada ouvir "Então, a visão que" no lugar de "Eu tenho a visão que
    # você", que é o que a fonte e a passada ancorada na emenda dizem.
    def inicio(tipo: str, ini: float, fim: float) -> float:
        return emenda_antes(fim if tipo == "vão" else ini, junctions)

    alvos = suspeitos(words)
    print(f"{len(words)} palavras mapeadas · {len(alvos)} trecho(s) suspeito(s)")

    # NÃO se fundem janelas. Fundir parece economia e destrói a âncora: no #29 a
    # janela de 41,333 (onde a tomada nova entra) foi fundida com uma de 35,867,
    # e a passada voltou a ouvir "Então, a visão que" em vez de "Eu tenho a
    # visão que você". Cada suspeito ouve a SUA janela; o cache evita repetir a
    # mesma sem mexer em onde ela começa.
    cache: dict[tuple[float, float], list[dict]] = {}

    def ouvir(jan_ini: float, jan_fim: float) -> list[dict]:
        chave = (round(jan_ini, 3), round(jan_fim, 3))
        if chave not in cache:
            print(f"    ouvindo isolado {jan_ini:.3f}–{jan_fim:.3f} ({jan_fim - jan_ini:.1f}s)")
            cache[chave] = transcrever(video, jan_ini, jan_fim - jan_ini, a.language)
        return cache[chave]

    def dentro_de(palavras: list[dict], lo: float, hi: float) -> list[dict]:
        """Palavras ouvidas que ENCOSTAM no trecho.

        A folga na ponta de cima não é enfeite: no #29 o "você" de "Eu tenho a
        visão que você" tinha o meio 10ms depois do fim do vão, e sem ela a
        legenda saía "Eu tenho a visão que deve evitar", sem sujeito. Alargar
        até sobreposição simples é o outro extremo — aí entram palavras
        vizinhas que já estão no mapeamento.
        """
        return [w for w in palavras if lo - 0.02 <= sum(seg(w)) / 2 <= hi + 0.03]

    def duplica(w: dict, ini_s: float, fim_s: float) -> bool:
        """A ouvida repete uma palavra que o mapeamento MANTÉM?

        A palavra que encosta na borda do vão (o "empreendedora." que termina
        exatamente onde o buraco começa) é ouvida de novo pela passada isolada.
        Enxertá-la duplica a palavra na tela — o defeito que a correção
        introduziria enquanto conserta o outro.
        """
        a, b = seg(w)
        nu = texto(w).lower().strip(".,?!:;")
        for x in words:
            xa, xb = seg(x)
            if xa >= ini_s - FOLGA and xb <= fim_s + FOLGA:
                continue                      # essa sai de qualquer jeito
            # Folga larga de propósito: um encosto de poucos ms na vizinha não é
            # duplicata, é borda — e é aparada depois. No #29 o "você" de "Eu
            # tenho a visão que você" encostava 30ms em "deve", dava empate
            # exato contra metade da duração e sumia por arredondamento.
            if min(b, xb) - max(a, xa) > 0.6 * (b - a):
                return True
            # Mesma palavra ENCOSTADA, sem sobrepor: o "empreendedora?" que
            # termina exatamente onde o vão começa é ouvido de novo do outro
            # lado da fronteira. Sobreposição é zero e a duplicata é real.
            if nu and nu == texto(x).lower().strip(".,?!:;") and max(a - xb, xa - b) < 0.4:
                return True
        return False

    enxertos: list[tuple[float, float, list[dict], str]] = []
    for tipo, ini_s, fim_s, motivo in alvos:
        print(f"\n  {ini_s:7.3f}–{fim_s:7.3f}  {motivo}")
        jan_ini = inicio(tipo, ini_s, fim_s)
        jan_fim = min(max(fim_s, jan_ini + JANELA_MIN), fim_video + 0.5)
        achado = [w for w in dentro_de(ouvir(jan_ini, jan_fim), ini_s, fim_s)
                  if not duplica(w, ini_s, fim_s)]
        if not achado:
            print("    a passada isolada não ouviu fala aqui — pausa real, mantido")
            continue
        # Um carimbo esticado só é defeito se ESCONDER fala: uma palavra longa de
        # verdade ("intraempreendedor") devolve uma palavra só, e aí não se mexe.
        if tipo == "esticada" and len(achado) < 2:
            print(f"    palavra longa de verdade ({len(achado)} palavra ouvida) — mantido")
            continue
        print(f"    RECUPERA {len(achado)}: {' '.join(texto(w) for w in achado)[:120]!r}")
        enxertos.append((ini_s, fim_s, achado, tipo))

    if not enxertos:
        print("\nnada a reparar.")
        return 0

    # Enxertia cirúrgica: tira do mapeamento só o que está DENTRO do trecho
    # defeituoso (no vão não há nada; na esticada sai a palavra que escondia a
    # fala) e põe as ouvidas no lugar. Tudo em volta fica como estava.
    saida = list(words)
    for ini_s, fim_s, achado, tipo in sorted(enxertos, key=lambda e: -e[0]):
        saida = [w for w in saida
                 if not (seg(w)[0] >= ini_s - FOLGA and seg(w)[1] <= fim_s + FOLGA)]
        # Apara contra as vizinhas que ficam. Duas passadas do mesmo áudio não
        # concordam no milissegundo, e uma legenda que começa antes de a anterior
        # acabar dispara sobreposição no `check` da composição.
        conv = [no_formato(w, words[0]) for w in achado]
        antes = [seg(w)[1] for w in saida if seg(w)[1] <= ini_s + FOLGA]
        depois = [seg(w)[0] for w in saida if seg(w)[0] >= fim_s - FOLGA]
        piso, teto = (max(antes) if antes else 0.0), (min(depois) if depois else 1e9)
        for w in conv:
            a_, b_ = seg(w)
            por_tempo(w, max(a_, piso), min(b_, teto))
        saida += [w for w in conv if seg(w)[1] > seg(w)[0]]
    saida.sort(key=lambda w: seg(w)[0])
    # Monotonicidade, por último e sobre TUDO. Aparar contra as vizinhas que
    # ficam não basta: entre duas palavras do próprio enxerto ainda sobra o
    # desacordo de poucos ms entre as duas passadas, e uma legenda que começa
    # antes de a anterior terminar vira `overlapping_clips_same_track` — o
    # mesmo portão que já barrou os efeitos sonoros nesta sessão.
    colados = 0
    for x, y in zip(saida, saida[1:]):
        if seg(y)[0] < seg(x)[1]:
            por_tempo(x, seg(x)[0], seg(y)[0])
            colados += 1
    if colados:
        print(f"  {colados} borda(s) encostada(s) para não sobrepor")

    ganho_total = len(saida) - len(words)
    print(f"\n{len(enxertos)} enxerto(s) · {len(words)} → {len(saida)} palavras "
          f"(+{ganho_total})")
    if not a.apply:
        print("(simulação — rode com --apply para gravar)")
        return 0
    bruto = mapped.with_suffix(".pre-repair.json")
    if not bruto.exists():
        bruto.write_text(original)          # o arquivo INTEIRO, não só as palavras
        print(f"  original guardado em {bruto.name}")
    regravar(mapped, original, saida)
    print(f"  gravado: {mapped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""OUVE O CORTE PRONTO e acusa frase repetida — sem confiar em transcrito nenhum.

    uv run python helpers/verify_takes.py <edit> [--video preview_proxy.mp4]
    uv run python helpers/verify_takes.py <edit> --json

POR QUE ISTO EXISTE, e por que o `detect_restarts.py` não bastava.

O `detect_restarts.py` procura repetição no TRANSCRITO. Isso o deixa cego
exatamente onde a repetição mais importa: o Whisper **engole a segunda passada**.
Ele não erra o texto — ele escreve um texto limpo do qual a repetição foi
removida, e nada no arquivo diz que faltou alguma coisa.

Medido neste projeto, no corte que foi entregue para aprovação:

  · o `takes_packed.md` mostrava duas frases que se emendavam perfeitamente
      [000.24-004.28] …chamado McDonald's. Isso explica muito
      [006.08-008.85] porque você ganha quanto ganha no trabalho.
  · o ÁUDIO do corte, na mesma passagem, diz:
      "chamado McDonald's. Isso explica muito, ISSO EXPLICA MUITO, porque você ganha"

Transcrever o corte inteiro de novo NÃO resolve: com o contexto na mão o modelo
suaviza outra vez e devolve a versão limpa. Foi verificado — a passada completa
sobre o corte renderizado saiu sem nenhuma das repetições que o usuário ouviu.

O QUE FUNCIONA É JANELA CURTA E ISOLADA. Sem contexto em volta o modelo não tem
para onde completar, e a segunda passada reaparece. E a LARGURA importa: uma
repetição de três palavras aparece numa janela de 2,4s e some numa de 6s;
"isso explica muito" precisa de 4s para caber duas vezes. Por isso a varredura
usa várias larguras e fica com a menor janela em que cada achado apareceu — a
menor é a mais específica sobre onde o defeito está.

CUSTA UMA VARREDURA LOCAL, não uma chamada de API: mlx-whisper roda na máquina,
de graça e offline. Num corte de 40s são ~50 janelas em cerca de um minuto — o
preço de não entregar gaguejo é esse.

FALSO POSITIVO CONHECIDO: em janela muito curta o Whisper às vezes entra em laço
e repete a última frase três, quatro vezes. Um achado com 3+ repetições
seguidas numa janela de 2,4s é suspeito de laço; ele sai marcado, não descartado
— quem ouve decide, e um aviso a mais custa menos que um gaguejo entregue.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

MODELO = "mlx-community/whisper-large-v3-turbo"
# Três larguras, do específico ao contextual. Ver o cabeçalho: a repetição curta
# só cabe na janela pequena, a longa só cabe na grande.
LARGURAS = ((2.4, 1.2), (4.0, 2.0), (6.0, 3.0))
NGRAMAS = (4, 3, 2)


def norm(t: str) -> list[str]:
    t = unicodedata.normalize("NFD", t.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9 ]", " ", t).split()


def repeticao(ws: list[str]) -> tuple[str, int] | None:
    """O maior n-grama que aparece DUAS VEZES SEGUIDAS, e quantas vezes seguidas."""
    for n in NGRAMAS:
        for i in range(len(ws) - 2 * n + 1):
            if ws[i:i + n] != ws[i + n:i + 2 * n]:
                continue
            vezes = 2
            j = i + 2 * n
            while ws[j:j + n] == ws[i:i + n]:
                vezes += 1
                j += n
            return " ".join(ws[i:i + n]), vezes
    return None


def _dur(p: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", str(p)], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def varrer(video: Path, tmp: Path, modelo: str = MODELO) -> list[dict]:
    try:
        import mlx_whisper
    except ImportError:
        raise SystemExit(
            "mlx-whisper não está instalado — é ele que ouve o corte.\n"
            "  uv pip install mlx-whisper   (Apple Silicon; local, grátis, offline)")

    wav = tmp / "corte.wav"
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-i", str(video), "-ac", "1", "-ar", "16000", str(wav)], check=True)
    dur = _dur(wav)
    janela = tmp / "_j.wav"

    achados: dict[str, dict] = {}
    for larg, passo in LARGURAS:
        t = 0.0
        while t < dur:
            subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                            "-ss", f"{t:.2f}", "-t", f"{larg:.2f}", "-i", str(wav),
                            str(janela)], check=True)
            r = mlx_whisper.transcribe(str(janela), path_or_hf_repo=modelo,
                                       language="pt", verbose=False)
            txt = " ".join(s["text"].strip() for s in r["segments"])
            achado = repeticao(norm(txt))
            if achado:
                ng, vezes = achado
                # fica a MENOR janela em que apareceu: é a mais específica
                if ng not in achados or larg < achados[ng]["janela"]:
                    achados[ng] = {"ngrama": ng, "t": round(t, 2), "janela": larg,
                                   "vezes": vezes, "texto": txt, "vistas": 0,
                                   "suspeita_de_laco": vezes >= 3 and larg <= 2.4}
                achados[ng]["vistas"] = achados[ng].get("vistas", 0) + 1
            t += passo

    # CONFIRMAÇÃO. Janela isolada às vezes ALUCINA a repetição — medido: uma
    # emenda limpa ("…McDonald's. Um sistema eficiente…") saiu como "um sistema,
    # um sistema" numa única janela de 6s, enquanto a extração direta do trecho
    # era limpa. O anticorpo é o mesmo princípio do achado: se a repetição é
    # real, ela reaparece numa janela DESLOCADA; se era artefato do enquadre,
    # não. Achado visto uma vez só e não reproduzido vira aviso, não falha.
    for a in achados.values():
        if a["vistas"] >= 2:
            a["confirmado"] = True
            continue
        ini = max(0.0, a["t"] - 0.8)
        subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                        "-ss", f"{ini:.2f}", "-t", f"{a['janela'] + 1.6:.2f}",
                        "-i", str(wav), str(janela)], check=True)
        r = mlx_whisper.transcribe(str(janela), path_or_hf_repo=modelo,
                                   language="pt", verbose=False)
        ws = norm(" ".join(s["text"].strip() for s in r["segments"]))
        rep2 = repeticao(ws)
        a["confirmado"] = bool(rep2 and rep2[0] == a["ngrama"])

    # LOCALIZAÇÃO. A janela diz "tem repetição aqui dentro", mas 'aqui dentro'
    # tem 4–6s — e um teste de sobreposição contra uma janela dessa largura não
    # decide nada (foi assim que um range com a repetição DENTRO passou pelo
    # mapa). Para cada confirmado, re-transcreve a janela com tempo por palavra
    # e aperta as bordas para a primeira palavra da primeira ocorrência até a
    # última da segunda.
    for a in achados.values():
        if not a.get("confirmado"):
            continue
        subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                        "-ss", f"{a['t']:.2f}", "-t", f"{a['janela']:.2f}",
                        "-i", str(wav), str(janela)], check=True)
        r = mlx_whisper.transcribe(str(janela), path_or_hf_repo=modelo,
                                   language="pt", word_timestamps=True, verbose=False)
        palavras = [(w["word"], w["start"], w["end"])
                    for seg in r["segments"] for w in seg.get("words", [])]
        alvo = a["ngrama"].split()
        n = len(alvo)
        toks = [norm(w)[0] if norm(w) else "" for w, _, _ in palavras]
        for i in range(len(toks) - 2 * n + 1):
            if toks[i:i + n] == alvo and toks[i + n:i + 2 * n] == alvo:
                a["t_fino"] = round(a["t"] + palavras[i][1], 2)
                a["fim_fino"] = round(a["t"] + palavras[i + 2 * n - 1][2], 2)
                # AS DUAS PASSADAS, SEPARADAS. Repetição é defeito quando as
                # duas estão no corte — manter UMA é justamente o conserto. O
                # teste de sobreposição precisa das duas para perguntar a coisa
                # certa; com um span único ele reprovava o range que mantinha a
                # retomada, isto é, reprovava a solução.
                a["occ1"] = [round(a["t"] + palavras[i][1], 2),
                             round(a["t"] + palavras[i + n - 1][2], 2)]
                a["occ2"] = [round(a["t"] + palavras[i + n][1], 2),
                             round(a["t"] + palavras[i + 2 * n - 1][2], 2)]
                break
    return sorted(achados.values(), key=lambda a: a["t"])


def main() -> None:
    ap = argparse.ArgumentParser(description="Ouve o corte pronto e acusa frase repetida")
    ap.add_argument("edit", type=Path)
    ap.add_argument("--video", default=None,
                    help="nome do render dentro do <edit> (padrão: proxy, senão preview.mp4)")
    ap.add_argument("--fonte", type=Path, default=None,
                    help="varre uma FONTE bruta (antes do EDL) e grava o mapa em "
                         "<edit>/defeitos_audio.json — é o modo que transforma o "
                         "detector de portão em insumo da seleção de tomadas")
    ap.add_argument("--modelo", default=MODELO)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    edit = args.edit.resolve()

    if args.fonte:
        # O MODO QUE MUDA O MOMENTO. Como portão, este detector só rejeita um
        # corte já feito; varrendo a FONTE, o mapa de repetições existe ANTES de
        # alguém escolher tomada, e o EDL é escrito desviando delas. Rejeitar no
        # fim custa uma rodada inteira de render; desviar no começo custa nada.
        fonte = args.fonte.resolve()
        if not fonte.exists():
            sys.exit(f"fonte não encontrada: {fonte}")
        tmp = edit / ".preview_cache" / "ouvir"
        tmp.mkdir(parents=True, exist_ok=True)
        achados = varrer(fonte, tmp, args.modelo)
        conf = [a for a in achados if a.get("confirmado")]
        mapa_p = edit / "defeitos_audio.json"
        mapa = {}
        if mapa_p.exists():
            try:
                mapa = json.loads(mapa_p.read_text())
            except json.JSONDecodeError:
                mapa = {}
        mapa[fonte.stem] = [{"t": a.get("t_fino", a["t"]),
                             "fim": a.get("fim_fino", round(a["t"] + a["janela"], 2)),
                             "occ1": a.get("occ1"), "occ2": a.get("occ2"),
                             "ngrama": a["ngrama"], "vezes": a["vezes"],
                             "confirmado": a["confirmado"]} for a in achados]
        mapa_p.write_text(json.dumps(mapa, ensure_ascii=False, indent=2), encoding="utf-8")
        if args.json:
            print(json.dumps({"fonte": fonte.name, "achados": achados},
                             ensure_ascii=False, indent=2))
        else:
            print(f"{fonte.name}: {len(conf)} repetição(ões) confirmada(s) no áudio"
                  + (f", {len(achados) - len(conf)} não confirmada(s)" if len(achados) > len(conf) else ""))
            for a in achados:
                marca = "" if a.get("confirmado") else "  [não confirmado]"
                print(f"   {a['t']:6.2f}–{a['t'] + a['janela']:6.2f}s  \"{a['ngrama']}\" ×{a['vezes']}{marca}")
            print(f"\nmapa gravado em {mapa_p.name} — o EDL deve DESVIAR destas janelas, "
                  "e o portão confere se desviou.")
        return

    alvos = [args.video] if args.video else ["preview_proxy.mp4", "preview.mp4"]
    video = next((edit / a for a in alvos if (edit / a).exists()), None)
    if video is None:
        sys.exit(f"nenhum render encontrado em {edit} — renderize antes de ouvir")

    tmp = edit / ".preview_cache" / "ouvir"
    tmp.mkdir(parents=True, exist_ok=True)
    achados = varrer(video, tmp, args.modelo)

    confirmados = [a for a in achados if a.get("confirmado")]
    if args.json:
        print(json.dumps({"video": video.name, "total": len(achados),
                          "achados": achados}, ensure_ascii=False, indent=2))
        sys.exit(1 if confirmados else 0)

    if not achados:
        print(f"{video.name}: nenhuma frase repetida no áudio do corte.")
        sys.exit(0)

    print(f"{video.name}: {len(achados)} frase(s) repetida(s) NO ÁUDIO — "
          f"o transcrito não mostra nenhuma delas\n")
    for a in achados:
        marca = "  (3+ seguidas em janela curta — pode ser laço do modelo, ouça)" \
            if a["suspeita_de_laco"] else ""
        if not a.get("confirmado"):
            marca += "  [NÃO CONFIRMADO na janela deslocada — provável artefato]"
        print(f"  {a['t']:6.2f}s  \"{a['ngrama']}\" ×{a['vezes']}{marca}")
        print(f"          {a['texto'][:130]}")
    print("\nCada uma é uma tomada refeita que sobreviveu ao corte. "
          "Ouça no editor e decida qual passada fica.")
    sys.exit(1)


if __name__ == "__main__":
    main()

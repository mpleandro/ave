#!/usr/bin/env python3
"""Encurta o ar morto DENTRO de cada trecho do EDL — a limpeza automática.

    uv run python helpers/propose_breaths.py <edit-dir> [--ritmo equilibrado] [--apply]
    uv run python helpers/propose_breaths.py <edit-dir> --comparar   # os três perfis

Cortar no silêncio resolve o ar morto ENTRE tomadas. O que sobra é o de dentro:
a pausa que a pessoa faz no meio do próprio raciocínio, que nenhuma escolha de
tomada remove porque ela está no meio da tomada escolhida. Num vídeo curto é o
que mais custa retenção, e é o tipo de trabalho que ninguém deveria fazer à mão.

NEM TODO SILÊNCIO É AR MORTO, e essa é a decisão inteira deste arquivo.

Um limiar único de duração trata igual duas coisas opostas: a pausa depois de
uma pergunta — que é o vídeo respirando de propósito, e cortada mata o beat — e
a pausa no meio de uma oração, que é hesitação e não faz falta a ninguém.
Enquanto a régua era só "acima de 0,60s", encurtar ficava entre RÍGIDO demais
(tira o suspense junto com o ar) e ABERTO demais (deixa hesitação porque o
limiar era alto). Então a régua tem três dimensões:

  1. PAUSA — quanto tempo, medido no áudio.
  2. dB — o limiar do que conta como silêncio, CALIBRADO na fonte (o ponto médio
     entre o piso de ruído e a mediana da voz). Um limiar fixo de −33 dBFS chama
     de silêncio a voz de quem fala a −41, que é o caso de metade dos projetos
     desta série. E o mesmo número serve de segunda opinião: se o pico DENTRO do
     vão chega perto da mediana da voz, tem alguém falando ali — não se encosta.
  3. CONTEXTO — o que o transcrito diz imediatamente ANTES do vão:
       · termina em `? ! … .` → RETÓRICA: pergunta no ar, remate, suspense.
       · termina em `, ; :`   → RESPIRAÇÃO: a vírgula falada, natural e encurtável.
       · sem pontuação        → HESITAÇÃO: parou no meio da frase; é ar morto.

**O contexto decide SE encurta; a BORDA continua sendo acústica.** Essa divisão
não é estilo: os tempos de palavra do Whisper esticam pelo silêncio adiante, e
já custaram palavra cortada neste projeto. Ler a PONTUAÇÃO do transcrito é
seguro (é texto, não tempo); tirar dele o instante do corte, não.

Os três perfis existem porque o ponto certo é do usuário, não da ferramenta —
um take de vendas quer ar, um Reels de retenção não quer nenhum. Rode
`--comparar` e faça a pergunta com os números na mão.

**`--min-speech 0` na chamada do detector não é detalhe: é o que impede este
helper de comer palavra.** Ver `speech_regions()` abaixo.

Sem `--apply` só relata; com `--apply` escreve `breaths[]` nos ranges do
edl.json (o anterior fica em edl.prev.json). O `render.py` expande cada respiro
em dois trechos e FIXA a emenda que criou — sem isso o J-cut comeria o piso.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

HELPERS = Path(__file__).resolve().parent
sys.path.insert(0, str(HELPERS))
from cut_words import levels_for  # noqa: E402  (irmão; o limiar já é medido lá)

EDGE = 0.02          # tolerância ao casar borda de região com borda de trecho
# Quanto o pico dentro do vão pode chegar perto da mediana da VOZ antes de o vão
# deixar de ser silêncio. 8 dB é a distância entre "room tone" e "alguém falando
# baixo" no material desta série — abaixo disso, é fala e não se toca.
VOZ_MARGEM_DB = 8.0
# Sem transcrito, todo vão entra como RESPIRAÇÃO: é o meio-termo dos três, e
# errar para o meio é o único erro que não estraga nem o ritmo nem a fala.
CLASSE_PADRAO = "respiracao"

# (limiar para encurtar, piso que fica) por classe. `None` = não se toca.
RITMOS: dict[str, dict[str, tuple[float, float] | None]] = {
    # Só o indefensável. Pausa retórica é intocável, e o piso é generoso.
    "conservador": {"hesitacao": (0.70, 0.35), "respiracao": (0.90, 0.45),
                    "retorica": None},
    # O padrão: tira hesitação com folga, encurta respiração, e só mexe na
    # retórica quando ela vira espera (1,4s de pergunta no ar não é suspense,
    # é o vídeo parado).
    "equilibrado": {"hesitacao": (0.50, 0.25), "respiracao": (0.60, 0.30),
                    "retorica": (1.40, 0.70)},
    # Retenção acima de tudo — Reels curto, cada décimo conta.
    "agressivo": {"hesitacao": (0.35, 0.18), "respiracao": (0.45, 0.22),
                  "retorica": (0.90, 0.45)},
}
RITMO_PADRAO = "equilibrado"

CLASSE_ROTULO = {"hesitacao": "hesitação", "respiracao": "respiração",
                 "retorica": "retórica"}


def speech_regions(video: Path, start: float, end: float, noise_db: float) -> list[tuple[float, float]]:
    """Regiões de fala acústica dentro de [start, end], via o helper que existe.

    **`--min-speech 0` não é detalhe: é o que impede este helper de comer
    palavra.** O `speech_regions.py` descarta região de fala mais curta que o
    piso — uma limpeza que faz sentido para quem LÊ o inventário e é veneno
    para quem procura SILÊNCIO. Numa rajada ("Como que você", "tá? Então,
    sim,") as palavras têm 0,10–0,14s e as pausas 0,13s: com o piso de 0,15s as
    palavras somem da lista, as pausas em volta se juntam, e o que sobra é um
    "silêncio" de 0,6s que nunca existiu. Encurtá-lo para 0,3s apaga a rajada
    inteira do render — palavras e tudo.

    Medido: numa rajada de 1,21s (fala 0,30 · 0,13 · 0,12 · 0,13 · 0,10 · 0,13
    · 0,30), o piso padrão devolvia duas regiões e um vão de 0,61s; com o piso
    zerado devolve as quatro regiões e vãos de 0,13s — abaixo de qualquer
    limiar, nada a encurtar. Foi esse vão fantasma que comeu 11 dos 24 respiros
    de um take.

    A assimetria manda no valor: uma região de fala a mais só impede um
    encurtamento (ar sobrando, dois cliques para resolver); uma região a menos
    apaga fala (refazer o corte). Na dúvida, qualquer som conta como fala.
    """
    r = subprocess.run(
        [sys.executable, str(HELPERS / "speech_regions.py"), str(video),
         "--start", str(max(0.0, start)), "--end", str(end),
         f"--noise={noise_db:.0f}dB", "--min-silence", "0.12", "--min-speech", "0"],
        capture_output=True, text=True,
    )
    out: list[tuple[float, float]] = []
    for line in r.stdout.splitlines():
        parts = line.replace("->", " ").replace("-", " ").split()
        nums = [p for p in parts if p.replace(".", "", 1).isdigit()]
        if len(nums) >= 2:
            out.append((float(nums[0]), float(nums[1])))
    return out


def peak_db(video: Path, a: float, b: float) -> float:
    """Pico dentro da janela, em dBFS. −99 quando não há nada."""
    r = subprocess.run(
        ["ffmpeg", "-v", "info", "-ss", f"{a:.3f}", "-t", f"{max(0.01, b - a):.3f}",
         "-i", str(video), "-vn", "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    m = re.search(r"max_volume:\s*(-?[\d.]+) dB", r.stderr)
    return float(m.group(1)) if m else -99.0


def gaps_inside(regions: list[tuple[float, float]], a: float, b: float,
                min_dur: float) -> list[tuple[float, float]]:
    """Silêncios INTERNOS ao trecho, acima do limiar.

    Só o que está entre duas falas. O silêncio que encosta na borda do trecho
    não entra: aquele é a folga do corte, e mexer nele é assunto do J-cut e do
    pad de borda — dois donos no mesmo silêncio é como um deles some.
    """
    dentro = [(s, e) for s, e in regions if e > a + EDGE and s < b - EDGE]
    dentro.sort()
    out = []
    for (s1, e1), (s2, _e2) in zip(dentro, dentro[1:]):
        dur = s2 - e1
        if dur >= min_dur and e1 > a + EDGE and s2 < b - EDGE:
            out.append((round(e1, 3), round(s2, 3)))
    return out


def carregar_palavras(edit: Path, src: Path) -> list[dict]:
    """As palavras da fonte, se houver transcrito. Só o TEXTO é usado daqui."""
    cache = edit / "transcripts" / f"{src.stem}.json"
    if not cache.exists():
        return []
    try:
        data = json.loads(cache.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    palavras = [w for w in (data.get("words") or []) if w.get("type") == "word"]
    palavras.sort(key=lambda w: float(w.get("start") or 0))
    return palavras


# O carimbo de FIM do Whisper se estica pelo silêncio adiante, então a palavra
# que fecha a fala antes do vão pode "terminar" bem depois do começo dele. A
# tolerância é generosa de propósito: aqui só se procura QUAL palavra é, para
# ler a pontuação dela — nenhum tempo daqui vira borda de corte.
CTX_TOL = 0.45


def classificar(palavras: list[dict], at: float) -> tuple[str, str]:
    """Que tipo de silêncio começa em `at`, pela pontuação de quem veio antes."""
    if not palavras:
        return CLASSE_PADRAO, ""
    ant = None
    for w in palavras:
        if float(w.get("start") or 0) <= at + CTX_TOL:
            ant = w
        else:
            break
    if ant is None:
        return CLASSE_PADRAO, ""
    txt = str(ant.get("text") or "").strip()
    if re.search(r"[?!…]$|\.$|—$", txt):
        return "retorica", txt
    if re.search(r"[,;:]$", txt):
        return "respiracao", txt
    if not txt:
        return CLASSE_PADRAO, ""
    return "hesitacao", txt


def avaliar(edit: Path, edl: dict, ritmo: str, verbose: bool = True) -> tuple[list[dict], int, float]:
    """Roda a régua inteira sobre o EDL. Devolve (ranges com marcas, total, ganho)."""
    regra = RITMOS[ritmo]
    sources = edl.get("sources", {})
    niveis: dict[str, tuple[float, float]] = {}   # cache por fonte
    relatorio: list[dict] = []
    total, ganho = 0, 0.0

    for r in edl.get("ranges", []):
        src = sources.get(r["source"])
        if not src:
            continue
        path = Path(src)
        if not path.is_absolute():
            path = (edit / src).resolve()
        if not path.exists():
            if verbose:
                print(f"  ! fonte ausente para {r['source']} — pulado")
            continue

        if str(path) not in niveis:
            piso, mediana = levels_for(path)
            # Sem medida confiável, o limiar antigo (−33) e uma mediana
            # impossível de alcançar: na dúvida, mede-se menos e corta-se menos.
            limiar = round((piso + mediana) / 2) if (piso is not None and mediana is not None
                                                     and piso < mediana) else -33.0
            niveis[str(path)] = (limiar, mediana if mediana is not None else 0.0)
        limiar, mediana = niveis[str(path)]

        palavras = carregar_palavras(edit, path)
        a, b = float(r["start"]), float(r["end"])
        regioes = speech_regions(path, a, b, limiar)
        # O menor limiar entre as classes ativas — filtra o grosso antes de
        # medir dB vão a vão, que é a parte cara.
        ativos = [v[0] for v in regra.values() if v]
        if not ativos:
            continue
        marcas, linhas = [], []
        for at, to in gaps_inside(regioes, a, b, min(ativos)):
            classe, palavra = classificar(palavras, at)
            faixa = regra[classe]
            dur = to - at
            if faixa is None:
                linhas.append((at, dur, classe, palavra, "preservado (retórica)"))
                continue
            lim, keep = faixa
            if dur < lim:
                # A retórica preservada APARECE. Um silêncio deliberado que
                # sobrevive em silêncio faz o usuário achar que a ferramenta
                # não o viu — e a próxima coisa que ele faz é apertar o ritmo
                # inteiro para pegar um vão que estava preservado de propósito.
                if classe == "retorica":
                    linhas.append((at, dur, classe, palavra, "preservado (retórica)"))
                continue
            if dur - keep <= 0.02:
                continue
            pico = peak_db(path, at, to)
            if mediana and pico >= mediana - VOZ_MARGEM_DB:
                # segunda opinião: tem fala aqui dentro, o detector é que errou
                linhas.append((at, dur, classe, palavra,
                               f"preservado — pico {pico:.0f} dBFS (voz ~{mediana:.0f})"))
                continue
            marcas.append({"at": at, "to": to, "keep": keep})
            ganho += dur - keep
            total += 1
            linhas.append((at, dur, classe, palavra, f"→ {keep:.2f}s"))

        if linhas and verbose:
            beat = r.get("beat") or r["source"]
            print(f"  {beat}:")
            for at, dur, classe, palavra, o_que in linhas:
                ctx = f' após "{palavra}"' if palavra else ""
                print(f"    {at:7.2f}s  {dur:4.2f}s  {CLASSE_ROTULO[classe]:<10}{ctx:<24} {o_que}")
        r["breaths"] = marcas
        if not marcas:
            r.pop("breaths", None)
        relatorio.append(r)

    return relatorio, total, ganho


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edit", type=Path)
    ap.add_argument("--ritmo", choices=sorted(RITMOS), default=RITMO_PADRAO,
                    help=f"perfil de ritmo (padrão {RITMO_PADRAO}) — pergunte ao usuário")
    ap.add_argument("--comparar", action="store_true",
                    help="mede os três perfis e não escreve nada; é o que alimenta a pergunta")
    ap.add_argument("--apply", action="store_true", help="escreve no edl.json")
    args = ap.parse_args()

    edit = args.edit.resolve()
    edl_path = edit / "edl.json"
    if not edl_path.exists():
        sys.exit(f"não achei o edl.json em {edit}")

    if args.comparar:
        # Cada perfil sobre uma cópia limpa: `avaliar` escreve `breaths` no dict.
        print("perfil         respiros   tempo economizado")
        for nome in ("conservador", "equilibrado", "agressivo"):
            edl = json.loads(edl_path.read_text())
            _, total, ganho = avaliar(edit, edl, nome, verbose=False)
            print(f"  {nome:<12} {total:>5}      −{ganho:.1f}s")
        print("\nnenhum foi aplicado — escolha com o usuário e rode com "
              "--ritmo <perfil> --apply")
        return 0

    edl = json.loads(edl_path.read_text())
    print(f"ritmo: {args.ritmo}")
    _, total, ganho = avaliar(edit, edl, args.ritmo)

    if not total:
        print("nenhum silêncio encurtável neste ritmo — nada a fazer")
        return 0

    print(f"\n{total} respiro(s), −{ganho:.1f}s no total (ritmo {args.ritmo})")
    if args.apply:
        (edit / "edl.prev.json").write_text(
            json.dumps(json.loads(edl_path.read_text()), ensure_ascii=False, indent=2))
        edl_path.write_text(json.dumps(edl, ensure_ascii=False, indent=2))
        print("escrito no edl.json (anterior em edl.prev.json) — refaça o render")
    else:
        print("nada foi escrito — rode com --apply para aplicar")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

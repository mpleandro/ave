"""Estágio 3 — sinais de texto: o julgamento que nenhuma métrica faz.

Cada finalista do pré-filtro é lido e recebe, de 0 a 100 e com o porquê:

- gancho      o que TOCA nos 3 primeiros segundos do corte final interrompe e
              orienta? (modelo interromper → orientar → pagar, `ganchos.md`)
- fluxo       a ideia anda (setup → desenvolvimento → virada) ou dá voltas?
- valor       quem assiste sai com algo: emoção, ou algo prático para usar
- completude  faz sentido sozinho e PAGA o que o gancho prometeu
- picos       emoção, conflito, revelação, frase citável

E o desenho do corte: em que frase começa (`inicio`), em que frase termina
(`fim`), se o conectivo de abertura sai (`aparar_conector`), o título e o
DIAGNÓSTICO DO GANCHO — `tem` (já segura), `puxar` (cold open: a frase forte
precisa vir antes do contexto) ou `regravar` (não há gancho; sugestões no
padrão de um dos 8 de `ganchos.md`).

A primeira versão dava nota ao gancho e só depois decidia o início, e as duas
coisas se descolaram: nota 76 de gancho para um corte que abria em "Não sei
quem tá aqui na aula". Agora `validar()` confere a posição: gancho `tem` cuja
frase não toca nos primeiros segundos do corte final é recusado.

O LOTE TAMBÉM MOSTRA O QUE O TEXTO ESCONDE (live Mil Milionários, 2026-11, o
"pneu do Gol" em 9689–9721s — os três defeitos num corte só):
- quem fala ({Nome} na frase, `falas:` no cabeçalho): a Júlia interrompe o
  Paulo de 16,5 a 21s e o avaliador, lendo só texto, não tinha como saber;
- ⚡PICO: "Eu era pobre, filho!" sai +7 dB acima do resto — foi o gancho que o
  usuário escolheu à mão; a avaliação de texto tinha escolhido outra frase;
- !! fala sem texto: o Whisper engoliu ~5s do Paulo ("duas mansões…") e
  escreveu "pai, fala..." no lugar;
- [cauda] e [live] nas frases que não servem de borda ou que só existem na
  transmissão, e ■✂ onde a cauda colada sai sozinha (`bordas.aparar`).

A CHAVE continua a do texto da janela, de propósito: as notas antigas foram
dadas ao MESMO texto e continuam valendo — o que mudou (aparar bordas, alertas)
roda por cima delas sem modelo. Os campos novos da nota (`payoff`,
`referencias_live`, `pico`) são opcionais; para reavaliar com o lote novo,
apague a nota do `notas.json`.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hook_finder import norm  # noqa: E402

from . import autocontencao as A
from . import candidatos as C

DIMENSOES = ("gancho", "fluxo", "valor", "completude", "picos")
TIPOS_GANCHO = ("tem", "puxar", "regravar")
PADROES = ("pergunta", "contraste", "promessa", "confissao", "loop", "lista", "visual",
           "hipotese", "erro_invisivel", "pov", "comando", "nenhum")
JANELA_GANCHO_S = 3.5   # "nos 3 primeiros segundos", com a folga de uma sílaba
USOS_PICO = ("inicio", "puxar", "ignorar")
DEPOIS_PAYOFF_S = 4.0   # o corte pode respirar uma frase depois do payoff, não mais
GANCHOS_MD = Path(__file__).resolve().parent / "ganchos.md"


def chave(c: dict) -> str:
    return hashlib.sha1(f"{c['start']:.2f}|{c['end']:.2f}|{c['texto']}".encode()).hexdigest()[:12]


def pedido(c: dict, frs: list[dict], cfg: dict, anot: dict | None = None) -> dict:
    """O trecho como o avaliador o lê: cada frase com o tempo e se pode abrir
    ou fechar o corte — a escolha do início precisa respeitar o áudio.

    `anot` (opcional, do `sinais_audio`): {"quem": {frase: nome}, "picos":
    {frase: dB}, "falas": [[nome, de, até]], "alertas": [...], "elenco": bool}.
    `abre`/`fecha` continuam a regra do áudio (a validação de notas antigas
    depende dela); `borda` diz quando o TEXTO não serve de borda."""
    i, j = c["frases"]
    an = anot or {}
    quem, picos = an.get("quem") or {}, an.get("picos") or {}
    out = []
    for k, f in enumerate(frs[i:j + 1]):
        g = i + k
        ap, ca = f.get("apara"), f.get("cauda")
        out.append({"k": k, "t": round(f["s"] - c["start"], 1), "s": f["s"], "e": f["e"],
                    "texto": f["texto"],
                    "abre": k == 0 or C.inicio_ok(frs, g, cfg),
                    "apara": {"texto": ap["texto"], "tirou": ap["tirou"], "s": ap["s"]} if ap else None,
                    "fecha": C.fim_ok(frs, g, cfg),
                    "borda": C.borda_ruim(f, cfg),
                    "live": A.referencia_live(f["texto"], cfg) if cfg.get("autocontencao", {}).get("logistica") else False,
                    "cauda": {"tirou": ca["tirou"], "texto": ca["texto"]} if ca else None,
                    "quem": quem.get(g), "pico": picos.get(g)})
    return {"id": c["id"], "chave": chave(c), "start": c["start"], "end": c["end"],
            "dur": c["dur"], "texto": c["texto"], "frases": out,
            "dur_min": cfg["candidatos"]["dur_min_s"],
            "elenco": bool(an.get("elenco")), "falas": an.get("falas") or [],
            "alertas": an.get("alertas") or []}


RUBRICA = """\
Você avalia trechos de um vídeo longo como CORTES VERTICAIS independentes
(Reels/TikTok/Shorts). Quem assiste não viu o resto do vídeo.

Objetivo dos cortes: {objetivo}. Público: {publico}.

Leia antes o guia de ganchos (abaixo do lote de instruções). Em resumo: os 3
primeiros segundos precisam INTERROMPER e ORIENTAR, e o resto do corte PAGA.

## 1. Desenhe o corte
Cada frase do trecho vem marcada:
  ▶  pode abrir o corte (silêncio medido antes, começa uma ideia)
  ▶✂ pode abrir tirando o conectivo — mostra o texto sem ele
  ■  pode fechar o corte (ponto final com silêncio depois)
  ■✂ fecha, e a confirmação colada no fim ("…, é verdade ou não é?") sai
     sozinha — o texto entre parênteses é como o corte termina
E o que o texto não mostra, medido no áudio:
  {{Nome}}      quem fala a partir desta frase (só quando muda; `falas:` no
              cabeçalho resume o trecho). Sem elenco da live, não vem.
  ⚡PICO +7dB  a voz desta frase fica 7 dB acima do normal DE QUEM FALA — é
              onde a emoção está, e o texto sozinho não mostra.
  !!          fala sem texto: o transcrito engoliu um trecho; o texto em volta
              pode estar errado — não baseie gancho, título nem nota nele.
  [cauda]     confirmação de live ("é isso.", "é verdade ou não é?", "tá?")
  [live]      aponta para o que só existe na transmissão (chat, QR code,
              "posso continuar?", "quem tá entendendo?")
  alertas:    o que pesa contra o corte; já desconta na nota automaticamente.
Escolha `inicio` (k de uma frase ▶ ou ▶✂; com ▶✂ use "aparar_conector": true)
e `fim` (k de uma frase ■). O corte final precisa ter ≥ {dur_min}s.
COMECE NO GANCHO: se as primeiras frases são aquecimento ("não sei quem tá
aqui", "gente", "deixa eu…"), mova o início para a frase forte. Se há ⚡PICO
depois dos 3s e a frase se sustenta sozinha, comece nela (`inicio`) ou puxe-a
(gancho `puxar`) — e diga em `pico` o que fez e por quê.
TERMINE NO PAYOFF: a última frase É a conclusão, o número, a virada, a frase
citável — não uma confirmação ([cauda]), não um convite à live ([live]), não
outro assunto. `payoff` = o k da frase que paga o gancho; `fim` fica nela ou
na seguinte. [cauda] e [live] sem ▶ nem ■ saem sozinhos da borda depois;
[live] com ▶/■ é você quem tira (mova `inicio`/`fim`).
OUTRA PESSOA FALANDO ({{Nome}} diferente no meio): só fica se a fala dela é
parte da história (pergunta que o principal responde, reação que reforça).
Senão, desenhe o corte sem ela ou desconte em fluxo e completude.

## Referências da live
O corte vai para quem NÃO está na live. O que aponta para a transmissão —
"posso continuar?", "quem tá entendendo, gente?", nome de quem escreveu no
chat, QR code, link, checkout, "faltam 2 minutos", "aula de hoje", "segundo
dia", "como eu falei" — quebra o corte. Na borda: mova `inicio`/`fim`. No meio:
liste os k em `referencias_live` e desconte em completude (no máximo 65).

## 2. Dê as notas — do corte JÁ DESENHADO
0 a 100, com um motivo curto e concreto que cite o texto:
- gancho: SÓ o que toca nos primeiros 3s a partir de `inicio`. Interrompe?
  Orienta (sobre o quê, para quem)? Não dê nota a uma frase que vem depois.
- fluxo: a ideia progride (setup → desenvolvimento → virada) sem voltas?
- valor: quem assiste ganha algo — emoção forte ou algo prático?
- completude: faz sentido sozinho E paga o que o gancho prometeu? Payoff
  claro DENTRO do corte sobe; fim em confirmação, promessa ("já já eu
  mostro") ou referência à live desce.
- picos: emoção, conflito, revelação ou frase citável?
Calibre: 50 é mediano; 80+ só para o que você postaria sem pensar duas vezes;
abaixo de 30 é inutilizável. Use a escala inteira.

## 3. Diagnostique o gancho
- "tem": a frase de abertura do corte final já é o gancho. gancho.frase = ela.
- "puxar": a frase forte está mais adiante e o que vem antes é contexto que o
  corte PRECISA (senão, mova o início em vez de puxar). gancho.frase = a frase
  exata; gancho.instrucao = "Puxe a frase de 0:12 (…) para o início" — tempo
  contado a partir do início do corte final.
  gancho.nota_se_puxar = a nota de gancho (0–100) que o corte teria com essa
  frase repetida antes do 0:00 — é o "subir score" da galeria.
- "regravar": não há gancho no trecho. gancho.sugestoes = 2–3 objetos
  {{"texto": "…", "padrao": "<padrão>"}}, escritos a partir DESTE corte (≤ 12
  palavras, falável em 3s), cada um seguindo a fórmula do padrão.
- gancho.padrao: o padrão do gancho como ele ficou (um de: {padroes}).

## 4. O resto
- titulo_sugerido: até 60 caracteres, a legenda de capa do corte.
- frase_gancho: a frase mais forte do corte, copiada EXATAMENTE.
- motivo: 1–2 frases — por que este corte funciona (ou não) como um todo.
- ruido: true quando o trecho é majoritariamente BASTIDOR da gravação — chat,
  brinde, procurar algo na tela, conversa com aluno sem conteúdo. Ruído é
  EXCLUÍDO da galeria, não importa a nota.

Grave em {destino} um objeto JSON {{chave: nota}}, mantendo as notas que já
estão lá:
{{"inicio": 0, "fim": 0, "aparar_conector": false, "payoff": 0,
  "referencias_live": [],
  "pico": {{"k": 0, "uso": "inicio|puxar|ignorar", "motivo": ""}},
  "dimensoes": {{"gancho": {{"nota": 0, "motivo": ""}}, "fluxo": {{…}},
    "valor": {{…}}, "completude": {{…}}, "picos": {{…}}}},
  "titulo_sugerido": "", "frase_gancho": "", "motivo": "", "ruido": false,
  "gancho": {{"tipo": "tem|puxar|regravar", "padrao": "", "frase": "",
             "instrucao": "", "sugestoes": [], "nota_se_puxar": null}}}}
(`pico` só quando o trecho tem ⚡PICO; sem ⚡PICO, omita.)
"""


def prompt(pedidos: list[dict], contexto: dict, lote: int = 8) -> str:
    partes = [RUBRICA.format(objetivo=contexto.get("objetivo") or "alcance",
                             publico=contexto.get("publico") or "deduza do próprio conteúdo",
                             destino=contexto.get("destino", "analise/notas.json"),
                             dur_min=pedidos[0]["dur_min"] if pedidos else 20,
                             padroes=", ".join(PADROES)),
              "\n---\n\n", GANCHOS_MD.read_text(), "\n---\n"]
    for n in range(0, len(pedidos), lote):
        partes.append(f"\n## Lote {n // lote + 1}\n")
        for p in pedidos[n:n + lote]:
            partes.append(f"\n### {p['id']} · chave `{p['chave']}` · {p['dur']:.0f}s "
                          f"({p['start']:.1f}–{p['end']:.1f}s na fonte)\n")
            partes.extend(linhas(p))
    return "".join(partes)


def linhas(p: dict) -> list[str]:
    """As linhas de UM trecho no lote (cabeçalho de falas e alertas, e uma
    linha por frase com as marcas)."""
    out = []
    fal = p.get("falas") or []
    if len({q for q, _, _ in fal}) > 1:
        out.append("falas: " + " · ".join(f"{q} {de:.1f}–{ate:.1f}" for q, de, ate in fal) + "\n")
    if p.get("alertas"):
        out.append("alertas: " + " · ".join(a["texto"] for a in p["alertas"]) + "\n")
    lac = [a for a in p.get("alertas") or [] if a["tipo"] == "lacuna"]
    varios = len({q for q, _, _ in fal}) > 1
    antes = None
    fr = p["frases"]
    for f in fr:
        ruim = f.get("borda")
        abre = "▶✂" if f["apara"] and not ruim else "▶ " if f["abre"] and not ruim else "  "
        marca = abre + ("■" if f["fecha"] and not ruim else " ")
        quem = f.get("quem")
        tag = ""
        if varios and quem and quem != antes:
            tag = f"{{{quem}}} "
        if quem:
            antes = quem
        linha = f"[{f['k']}] {f['t']:>5.1f}s {marca} {tag}{f['texto']}"
        if f["apara"] and not ruim:
            linha += f"   (✂ sem \"{f['apara']['tirou']}\": {f['apara']['texto']})"
        if f.get("cauda") and f["fecha"] and not ruim:
            linha += f"   (■✂ sem \"{f['cauda']['tirou']}\": {f['cauda']['texto']})"
        if f.get("pico") is not None:
            linha += f"   ⚡PICO {f['pico']:+.0f}dB"
        if ruim:
            linha += "   [cauda]" if ruim == "cauda" else "   [live]"
        elif f.get("live"):
            linha += "   [live]"
        out.append(linha + "\n")
        prox = fr[f["k"] + 1]["t"] if f["k"] + 1 < len(fr) else float("inf")
        for a in lac:
            if f["t"] - 0.05 <= a["de"] < prox - 0.05:
                out.append(f"      !! {a['de']:.1f}–{a['ate']:.1f}s: {a['voz']:.1f}s de fala sem texto — "
                           f"o transcrito engoliu algo aqui; o texto em volta pode estar errado\n")
    return out


def _t_inicio(n: dict, p: dict) -> float:
    f = p["frases"][n.get("inicio", 0)]
    return f["apara"]["s"] if n.get("aparar_conector") and f["apara"] else f["s"]


def onde(frase: str, p: dict, desde: int = 0) -> float | None:
    """Em que segundo da FONTE a frase começa — o início da frase do trecho onde
    o começo dela cai — ou None se ela não está no trecho."""
    cab = " ".join(norm(frase).replace("?", "").split()[:6])
    if not cab:
        return None
    texto, spans = "", []
    for f in p["frases"][desde:]:
        ini = len(texto)
        texto += norm(f["texto"]).replace("?", "") + " "
        spans.append((ini, f["s"]))
    pos = texto.find(cab)
    if pos < 0:
        return None
    return [s for ini, s in spans if ini <= pos][-1]


def validar(n: dict, p: dict) -> list[str]:
    erros = []
    fr = p["frases"]
    ini, fim = n.get("inicio"), n.get("fim")
    if not isinstance(ini, int) or not 0 <= ini < len(fr):
        return [f"inicio inválido: {ini!r}"]
    if not isinstance(fim, int) or not ini <= fim < len(fr):
        return [f"fim inválido: {fim!r}"]
    if n.get("aparar_conector") and not fr[ini]["apara"]:
        erros.append(f"aparar_conector na frase [{ini}], que não tem conectivo destacável")
    if not n.get("aparar_conector") and not fr[ini]["abre"]:
        erros.append(f"inicio [{ini}] não pode abrir o corte (sem ▶)")
    if not fr[fim]["fecha"]:
        erros.append(f"fim [{fim}] não pode fechar o corte (sem ■)")
    t0 = _t_inicio(n, p)
    if fr[fim]["e"] - t0 < p["dur_min"]:
        erros.append(f"corte final com {fr[fim]['e'] - t0:.1f}s, abaixo de {p['dur_min']}s")

    dims = n.get("dimensoes") or {}
    for d in DIMENSOES:
        v = (dims.get(d) or {}).get("nota")
        if not isinstance(v, (int, float)) or not 0 <= v <= 100:
            erros.append(f"{d}.nota fora de 0–100: {v!r}")
        if not (dims.get(d) or {}).get("motivo"):
            erros.append(f"{d}.motivo vazio")

    g = n.get("gancho") or {}
    tipo = g.get("tipo")
    if tipo not in TIPOS_GANCHO:
        erros.append(f"gancho.tipo inválido: {tipo!r}")
    if g.get("padrao") not in PADROES:
        erros.append(f"gancho.padrao inválido: {g.get('padrao')!r}")
    if tipo in ("tem", "puxar"):
        if not g.get("frase"):
            erros.append(f"gancho {tipo} sem frase")
        else:
            t = onde(g["frase"], p, ini)
            if t is None or t > fr[fim]["e"]:
                erros.append(f"gancho.frase não está dentro do corte: {g['frase'][:50]!r}")
            elif tipo == "tem" and t - t0 > JANELA_GANCHO_S:
                erros.append(f"gancho 'tem' mas a frase só toca aos {t - t0:.1f}s do corte — "
                             f"mova o início para ela ou use 'puxar'")
            elif tipo == "puxar" and t - t0 <= JANELA_GANCHO_S:
                erros.append("gancho 'puxar' com a frase já no começo — é 'tem'")
    if tipo == "puxar":
        v = g.get("nota_se_puxar")
        if not isinstance(v, (int, float)) or not 0 <= v <= 100:
            erros.append(f"gancho puxar sem nota_se_puxar (0–100): {v!r}")
    if tipo == "regravar":
        sug = g.get("sugestoes") or []
        if not sug:
            erros.append("gancho regravar sem sugestões")
        for s in sug:
            if not isinstance(s, dict) or not s.get("texto") or s.get("padrao") not in PADROES:
                erros.append(f"sugestão sem texto/padrão: {s!r}")
            elif len(s["texto"].split()) > 12:
                erros.append(f"sugestão com mais de 12 palavras: {s['texto']!r}")
    for k in ("titulo_sugerido", "motivo"):
        if not n.get(k):
            erros.append(f"{k} vazio")
    if not isinstance(n.get("ruido", False), bool):
        erros.append(f"ruido deve ser true/false: {n.get('ruido')!r}")
    erros += _validar_novos(n, p, ini, fim)
    return erros


def _validar_novos(n: dict, p: dict, ini: int, fim: int) -> list[str]:
    """Os campos novos são OPCIONAIS (as notas antigas não têm), mas quando
    vêm têm de fazer sentido — senão o desenho que eles justificam é falso."""
    erros = []
    fr = p["frases"]
    pay = n.get("payoff")
    if pay is not None:
        if not isinstance(pay, int) or not ini <= pay <= fim:
            erros.append(f"payoff [{pay!r}] fora do corte [{ini}–{fim}]")
        elif fim - pay > 1 and fr[fim]["e"] - fr[pay]["e"] > DEPOIS_PAYOFF_S:
            erros.append(f"o corte segue {fr[fim]['e'] - fr[pay]['e']:.1f}s e {fim - pay} frases depois "
                         f"do payoff [{pay}] — feche nele (ou na seguinte)")
    rl = n.get("referencias_live")
    if rl is not None and (not isinstance(rl, list)
                           or not all(isinstance(k, int) and 0 <= k < len(fr) for k in rl)):
        erros.append(f"referencias_live deve ser uma lista de k do trecho: {rl!r}")
    pc = n.get("pico")
    if pc is not None:
        if (not isinstance(pc, dict) or not isinstance(pc.get("k"), int) or not 0 <= pc["k"] < len(fr)
                or pc.get("uso") not in USOS_PICO):
            erros.append(f"pico deve ser {{k, uso: {'|'.join(USOS_PICO)}, motivo}}: {pc!r}")
    return erros


def avisos(n: dict, p: dict) -> list[str]:
    """O que não recusa a nota, mas vale a pena reler: a regra pede e a nota
    (talvez antiga, de antes do lote marcar picos e live) não fez."""
    out = []
    fr = p["frases"]
    ini, fim = n.get("inicio", 0), n.get("fim", len(fr) - 1)
    t0 = _t_inicio(n, p)
    g = n.get("gancho") or {}
    tardios = [f for f in fr[ini:fim + 1] if f.get("pico") is not None and f["s"] - t0 > JANELA_GANCHO_S]
    if tardios and g.get("tipo") == "tem" and not n.get("pico"):
        f = tardios[0]
        out.append(f"⚡PICO em [{f['k']}] aos {f['s'] - t0:.1f}s (\"{f['texto'][:40]}\") e o gancho ficou "
                   f"'tem' sem dizer por quê (campo pico)")
    rl = [k for k in n.get("referencias_live") or [] if ini < k < fim]
    if rl and ((n.get("dimensoes") or {}).get("completude") or {}).get("nota", 0) > 65:
        out.append(f"referência à live no meio ({rl}) com completude acima de 65")
    for k in (ini, fim):
        if k in (n.get("referencias_live") or []):
            out.append(f"referência à live na borda [{k}] — mova inicio/fim")
    return out

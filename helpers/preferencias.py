#!/usr/bin/env python3
"""O que ESTE usuário costuma querer — aprendido, não configurado.

    uv run python helpers/preferencias.py --mostrar
    uv run python helpers/preferencias.py --consultar shortform hesitacao
    uv run python helpers/preferencias.py --aprender <edit-dir>
    uv run python helpers/preferencias.py --registrar <edit-dir> --classe respiracao \\
        --duracao 0.28 --decisao remover
    uv run python helpers/preferencias.py --reset

ONDE MORA, e por que fora do repositório:

    ~/.avelin/preferencias.json        (ou $AVE_PREFS)

Preferência não é configuração: é o resultado de meses de decisão de UMA pessoa
sobre o material DELA. Guardar isso dentro do clone significaria (a) versionar
o gosto de alguém num repositório que outros clonam e (b) perder tudo no
primeiro `git clean -xdf`. O repo já trata `templates/` assim — "cada um
constrói o seu" — e aqui a razão é mais forte, porque templates se refazem e
histórico de decisão não.

O repositório entrega o MECANISMO. O arquivo nasce vazio na primeira execução,
na máquina de quem usa, e nunca sobe.

CONTEXTO, não só formato. Os limiares vivem sob `shortform`/`longform` porque o
ritmo é outro, mas um mesmo usuário edita séries diferentes com padrões
diferentes — um canal de vendas quer ar, um de retenção não quer nenhum. Então
cada projeto pode declarar um `contexto` e ganhar a própria régua, caindo de
volta na do formato enquanto não tiver amostra própria.

A REGRA DE APRENDIZADO É EXPLICÁVEL, e isso não é modéstia técnica — é
requisito. Um número que o usuário não consegue auditar ele não consegue
discordar, e discordar é justamente o sinal que alimenta isto.

    limiar = ponto médio entre o MAIOR vão que ele manteve
             e o MENOR vão que ele removeu

Se as duas faixas se sobrepõem, a preferência é inconsistente naquela classe:
alarga a banda, derruba a confiança e volta a perguntar. Não se inventa um
número no meio de uma contradição.

CONFIANÇA GOVERNA A AUTONOMIA, e é isso que faz o modelo evoluir em vez de só
lembrar:

    < 5 amostras   baixa   usa o padrão e PERGUNTA
    5–15           média   aplica e INFORMA numa linha, desfazível
    > 15           alta    aplica calado, aparece só no resumo

E o caminho de volta existe: um `preview_edits.json` que contradiz um limiar de
confiança alta derruba a confiança para média. Discordar do usuário custa
autonomia à ferramenta — nunca o contrário.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

CLASSES = ("hesitacao", "respiracao", "retorica")
FORMATOS = ("shortform", "longform")

# Sem amostra própria, vale a régua que já existe no propose_breaths — o perfil
# "equilibrado". O padrão da ferramenta é o ponto de partida, não um concorrente.
PADRAO = {"hesitacao": 0.50, "respiracao": 0.60, "retorica": 1.40}

BAIXA, MEDIA, ALTA = "baixa", "media", "alta"
LIM_MEDIA, LIM_ALTA = 5, 15
# Teto do histórico. Serve para auditoria ("por que ele acha isso?"), não para
# arqueologia — e gosto muda, então amostra muito velha atrapalha mais que ajuda.
HIST_MAX = 400


def caminho() -> Path:
    env = os.environ.get("AVE_PREFS")
    return Path(env).expanduser() if env else Path.home() / ".avelin" / "preferencias.json"


def vazio() -> dict:
    return {
        "versao": 1,
        "atualizado": date.today().isoformat(),
        "shortform": {}, "longform": {}, "contextos": {},
        "duplicados": {"truncado": "remover", "identico": "ultima",
                       "semantico": "perguntar"},
        "observacoes": [],
        "historico": [],
    }


def carregar() -> dict:
    p = caminho()
    if not p.exists():
        return vazio()
    try:
        d = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return vazio()
    for k, v in vazio().items():
        d.setdefault(k, v)
    return d


def salvar(d: dict) -> Path:
    p = caminho()
    p.parent.mkdir(parents=True, exist_ok=True)
    d["atualizado"] = date.today().isoformat()
    d["historico"] = d.get("historico", [])[-HIST_MAX:]
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)
    return p


# --------------------------------------------------------------------------- #
# a régua

def _confianca(n: int) -> str:
    return ALTA if n > LIM_ALTA else (MEDIA if n >= LIM_MEDIA else BAIXA)


def recalcular(bucket: dict) -> dict:
    """Do histórico de uma classe para o limiar. A regra inteira mora aqui."""
    mantidos = [o["duracao"] for o in bucket.get("amostras_obs", []) if o["decisao"] == "manter"]
    removidos = [o["duracao"] for o in bucket.get("amostras_obs", []) if o["decisao"] == "remover"]
    n = len(mantidos) + len(removidos)
    bucket["amostras"] = n

    if not mantidos and not removidos:
        bucket.pop("cortar_acima_de", None)
        bucket["confianca"] = BAIXA
        return bucket

    maior_mantido = max(mantidos) if mantidos else None
    menor_removido = min(removidos) if removidos else None
    bucket["maior_mantido"] = maior_mantido
    bucket["menor_removido"] = menor_removido

    if maior_mantido is not None and menor_removido is not None:
        if maior_mantido < menor_removido:
            bucket["cortar_acima_de"] = round((maior_mantido + menor_removido) / 2, 3)
            bucket["confianca"] = _confianca(n)
            bucket.pop("inconsistente", None)
        else:
            # As faixas se cruzam: a mesma duração foi mantida numa vez e
            # removida noutra. Não há limiar honesto aqui — só mais pergunta.
            bucket["cortar_acima_de"] = round((maior_mantido + menor_removido) / 2, 3)
            bucket["confianca"] = BAIXA
            bucket["inconsistente"] = True
    elif menor_removido is not None:
        # Só remoções: o limiar fica logo abaixo da menor delas, sem extrapolar
        # para baixo do que se viu.
        bucket["cortar_acima_de"] = round(max(0.05, menor_removido - 0.02), 3)
        bucket["confianca"] = _confianca(n)
    else:
        bucket["cortar_acima_de"] = round(maior_mantido + 0.02, 3)
        bucket["confianca"] = _confianca(n)
    return bucket


def _bucket(d: dict, formato: str, classe: str, contexto: str | None) -> dict:
    if contexto:
        alvo = d["contextos"].setdefault(contexto, {}).setdefault(formato, {})
    else:
        alvo = d.setdefault(formato, {})
    return alvo.setdefault(classe, {"amostras": 0, "confianca": BAIXA, "amostras_obs": []})


def consultar(d: dict, formato: str, classe: str, contexto: str | None = None) -> dict:
    """O limiar que vale AGORA, e de onde ele veio.

    Contexto primeiro, formato depois, padrão da ferramenta por último — e a
    resposta diz qual dos três respondeu, porque um número sem procedência não
    se audita.
    """
    if contexto:
        b = (d.get("contextos", {}).get(contexto, {}).get(formato, {}) or {}).get(classe)
        if b and b.get("cortar_acima_de") is not None and b.get("confianca") != BAIXA:
            return {"limiar": b["cortar_acima_de"], "confianca": b["confianca"],
                    "amostras": b.get("amostras", 0), "origem": f"contexto:{contexto}"}
    b = (d.get(formato, {}) or {}).get(classe)
    if b and b.get("cortar_acima_de") is not None:
        return {"limiar": b["cortar_acima_de"], "confianca": b.get("confianca", BAIXA),
                "amostras": b.get("amostras", 0), "origem": formato}
    return {"limiar": PADRAO[classe], "confianca": BAIXA, "amostras": 0,
            "origem": "padrão da ferramenta"}


def registrar(d: dict, formato: str, classe: str, duracao: float, decisao: str,
              contexto: str | None = None, projeto: str = "") -> dict:
    """Uma observação. `decisao` é 'manter' ou 'remover'."""
    if classe not in CLASSES:
        raise ValueError(f"classe desconhecida: {classe}")
    if decisao not in ("manter", "remover"):
        raise ValueError("decisao deve ser 'manter' ou 'remover'")

    antes = consultar(d, formato, classe, contexto)
    obs = {"data": date.today().isoformat(), "projeto": projeto, "contexto": contexto,
           "formato": formato, "classe": classe, "duracao": round(float(duracao), 3),
           "decisao": decisao}
    d["historico"].append(obs)

    for ctx in ({None, contexto} if contexto else {None}):
        b = _bucket(d, formato, classe, ctx)
        b.setdefault("amostras_obs", []).append({"duracao": obs["duracao"], "decisao": decisao})
        recalcular(b)

    # DISCORDAR CUSTA AUTONOMIA. Se a ferramenta estava confiante e a decisão
    # nova contradiz o que ela teria feito, ela volta a perguntar. Sem este
    # ramo, um limiar de confiança alta se defenderia da própria correção —
    # quanto mais errado, mais calado.
    if antes["confianca"] == ALTA:
        teria_removido = duracao >= antes["limiar"]
        if teria_removido != (decisao == "remover"):
            b = _bucket(d, formato, classe, contexto)
            b["confianca"] = MEDIA
            b["contrariado_em"] = obs["data"]
    return d


# --------------------------------------------------------------------------- #
# aprender do que o usuário já fez à mão

def aprender_de_edits(d: dict, edit: Path, formato: str = "shortform",
                      contexto: str | None = None) -> tuple[int, list[str]]:
    """Lê `preview_edits.json` — o que o usuário corrigiu DEPOIS da entrega.

    É o sinal mais forte que existe, e estava sendo jogado fora: o editor grava
    o arquivo, o `apply_edits.py` aplica e ninguém guarda o que ele dizia. Cada
    trecho que o usuário encurtou à mão é uma frase que a ferramenta deveria ter
    encurtado sozinha; cada borda que ele NÃO tocou é um vão que ele aceitou.
    """
    p = edit / "preview_edits.json"
    if not p.exists():
        return 0, []
    try:
        payload = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return 0, []

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        from propose_breaths import classificar  # noqa: PLC0415
    except Exception:
        classificar = None

    edl_p = edit / "edl.json"
    orig = json.loads(edl_p.read_text()).get("ranges", []) if edl_p.exists() else []
    novos = (payload.get("edl") or {}).get("ranges", payload.get("ranges") or [])
    projeto = edit.parent.name

    linhas: list[str] = []
    n = 0
    for i, r in enumerate(novos):
        if i >= len(orig):
            break
        o = orig[i]
        # encolher a borda é REMOVER ar; alargar é DEVOLVER ar
        for lado, sinal in (("start", 1.0), ("end", -1.0)):
            delta = (float(r.get(lado, o[lado])) - float(o[lado])) * sinal
            if abs(delta) < 0.05:
                continue
            classe = "respiracao"
            if classificar:
                try:
                    classe = classificar([], float(o[lado]))[0]
                except Exception:
                    pass
            decisao = "remover" if delta > 0 else "manter"
            registrar(d, formato, classe, abs(delta), decisao, contexto, projeto)
            linhas.append(f"  trecho {i + 1} {lado}: {abs(delta):.2f}s → {decisao} ({classe})")
            n += 1
    return n, linhas


# --------------------------------------------------------------------------- #
# cli

def mostrar(d: dict) -> None:
    p = caminho()
    print(f"preferências: {p}{'' if p.exists() else '  (ainda não existe — nasce no primeiro registro)'}")
    print(f"atualizado: {d.get('atualizado', '—')}\n")
    for formato in FORMATOS:
        buckets = d.get(formato) or {}
        if not buckets:
            print(f"{formato}: (sem amostra — vale o padrão da ferramenta)")
            continue
        print(f"{formato}:")
        for classe in CLASSES:
            b = buckets.get(classe)
            if not b:
                print(f"   {classe:11s} —  padrão {PADRAO[classe]:.2f}s")
                continue
            lim = b.get("cortar_acima_de")
            inc = "  ⚠ inconsistente (voltou a perguntar)" if b.get("inconsistente") else ""
            faixa = ""
            if b.get("maior_mantido") is not None or b.get("menor_removido") is not None:
                faixa = (f"  [manteve até {b.get('maior_mantido', '—')}, "
                         f"removeu a partir de {b.get('menor_removido', '—')}]")
            print(f"   {classe:11s} corta acima de "
                  f"{('%.2fs' % lim) if lim is not None else '  —  '}"
                  f"   {b.get('amostras', 0):3d} amostras, confiança {b.get('confianca', BAIXA)}"
                  f"{faixa}{inc}")
        print()
    ctxs = d.get("contextos") or {}
    if ctxs:
        print("contextos com régua própria:", ", ".join(sorted(ctxs)))
    print("duplicados:", json.dumps(d.get("duplicados", {}), ensure_ascii=False))
    if d.get("observacoes"):
        print("observações:")
        for o in d["observacoes"]:
            print(f"   · {o}")
    print(f"\nhistórico: {len(d.get('historico', []))} decisões registradas")


def main() -> None:
    ap = argparse.ArgumentParser(description="Preferências de corte aprendidas deste usuário")
    ap.add_argument("--mostrar", action="store_true")
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--consultar", nargs=2, metavar=("FORMATO", "CLASSE"))
    ap.add_argument("--aprender", type=Path, metavar="EDIT_DIR")
    ap.add_argument("--registrar", type=Path, metavar="EDIT_DIR")
    ap.add_argument("--classe", choices=CLASSES)
    ap.add_argument("--duracao", type=float)
    ap.add_argument("--decisao", choices=["manter", "remover"])
    ap.add_argument("--formato", choices=FORMATOS, default="shortform")
    ap.add_argument("--contexto", default=None,
                    help="nome da série/canal — ganha régua própria, caindo no formato "
                         "enquanto não tiver amostra sua")
    args = ap.parse_args()

    if args.reset:
        p = caminho()
        if p.exists():
            p.unlink()
            print(f"apagado: {p}")
        else:
            print("nada a apagar")
        return

    d = carregar()

    if args.consultar:
        formato, classe = args.consultar
        r = consultar(d, formato, classe, args.contexto)
        print(f"{formato}/{classe}: corta acima de {r['limiar']:.2f}s "
              f"(confiança {r['confianca']}, {r['amostras']} amostras, via {r['origem']})")
        return

    if args.aprender:
        n, linhas = aprender_de_edits(d, args.aprender.resolve(),
                                      args.formato, args.contexto)
        if not n:
            print("nada a aprender (sem preview_edits.json ou sem borda alterada)")
            return
        print(f"{n} decisão(ões) aprendida(s) de {args.aprender}:")
        for l in linhas:
            print(l)
        print(f"gravado em {salvar(d)}")
        return

    if args.registrar is not None:
        if args.classe is None or args.duracao is None or args.decisao is None:
            sys.exit("--registrar exige --classe, --duracao e --decisao")
        registrar(d, args.formato, args.classe, args.duracao, args.decisao,
                  args.contexto, args.registrar.resolve().parent.name)
        r = consultar(d, args.formato, args.classe, args.contexto)
        print(f"registrado. {args.formato}/{args.classe} agora corta acima de "
              f"{r['limiar']:.2f}s (confiança {r['confianca']}, {r['amostras']} amostras)")
        salvar(d)
        return

    mostrar(d)


if __name__ == "__main__":
    main()

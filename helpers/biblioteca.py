#!/usr/bin/env python3
"""O ACERVO de quem edita — logo, trilha, efeito, LUT, vinheta — lembrado entre projetos.

    uv run python helpers/biblioteca.py --candidatos <edit-dir>
    uv run python helpers/biblioteca.py --registrar ~/Marca/logo.png --tipo logo \\
        --nome "Vértuz branco" --tags marca,claro --nota "só sobre fundo escuro"
    uv run python helpers/biblioteca.py --pasta ~/Music/"Own SFX"/riser --tipo sfx --papel riser
    uv run python helpers/biblioteca.py --listar [--tipo sfx] [--json]
    uv run python helpers/biblioteca.py --resolver --tipo sfx --papel riser [--json]
    uv run python helpers/biblioteca.py --usar <id> --projeto <edit-dir>
    uv run python helpers/biblioteca.py --esquecer <id>
    uv run python helpers/biblioteca.py --adotar-sfx     (migra o ~/.avelin/sfx.json antigo)

ONDE MORA, e por que fora do clone:

    ~/.avelin/biblioteca.json     índice     (ou $AVE_BIBLIOTECA)
    ~/.avelin/biblioteca/<tipo>/  os arquivos guardados por cópia

Pela mesma razão do `brand.json` e do `preferencias.json`: o logo de alguém não
é parte do repositório que outros clonam, e não pode morrer num `git clean`. E
não é parte do PROJETO tampouco — um asset que vive só dentro de `<edit>/` é um
asset que o próximo vídeo vai pedir de novo, na mão, ao usuário que já o deu uma
vez. O acervo é de QUEM edita, como a marca.

O QUE ELE GUARDA É MEDIDO, não declarado. Cada um dos três tipos tem um defeito
que só aparece tarde — no render, quando já custou minutos:

  logo/imagem  ALFA. Um PNG sem canal alfa por cima do vídeo desenha um
               RETÂNGULO branco. Medido no registro (`pix_fmt`), dito na hora.
  sfx          PICO e ATAQUE. O `click2.mp3` do pacote tem pico de −25 dB:
               inaudível sob fala. E o ataque mora DENTRO do arquivo (158 ms de
               silêncio no `caption-click`), então agendar no instante da deixa
               atrasa o som. `sfx.py` já mede as duas coisas; aqui elas ficam
               guardadas junto do arquivo, uma vez, em vez de a cada projeto.
  trilha       DURAÇÃO. Uma trilha mais curta que o corte volta ao início com
               emenda audível, e isso se sabe antes de escolher.

USO É O QUE VIRA PADRÃO, e é por isso que `--usar` existe. Contar quantas vezes
um item entrou num vídeo entregue é a única evidência honesta de que ele é o
padrão da casa — declarar "meu riser é este" é opinião de um dia. A régua é a
mesma do `preferencias.py`, e pela mesma razão (confiança governa autonomia):

    0–1 uso    PERGUNTA qual usar
    2 usos     usa e INFORMA numa linha, desfazível
    3+ usos    é o padrão daquele papel; entra calado

PASTA TAMBÉM É ITEM. Quem tem acervo de efeitos tem PASTA de acervo, não
arquivo avulso — obrigar a registrar 300 risers um a um seria trocar um
trabalho manual por outro. `--pasta` guarda o diretório com um papel, e o
`--resolver` procura lá dentro pelo nome quando nenhum item registrado serve.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

TIPOS = ("logo", "imagem", "sfx", "trilha", "vinheta", "lut", "fonte", "video", "outro")

# Extensões por tipo — só para adivinhar o tipo quando ele não foi dito.
POR_EXT = {
    ".png": "logo", ".svg": "logo", ".webp": "imagem", ".jpg": "imagem", ".jpeg": "imagem",
    ".mp3": "sfx", ".wav": "sfx", ".m4a": "trilha", ".aac": "trilha", ".flac": "trilha",
    ".mp4": "video", ".mov": "video", ".webm": "video",
    ".cube": "lut", ".ttf": "fonte", ".otf": "fonte", ".woff2": "fonte",
}
AUDIO = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
IMAGEM = {".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif"}
VIDEO = {".mp4", ".mov", ".webm", ".mkv"}

QUIET_DB = -12.0          # abaixo disso um efeito some sob a fala (medido no pacote)
USO_INFORMA, USO_CALADO = 2, 3

# Pastas do projeto que NÃO geram candidato: o que veio de busca se refaz por
# busca. Guardar uma foto do Pexels no acervo pessoal é guardar um atalho para
# um catálogo que já é público — e enche a biblioteca de coisa que ninguém
# escolheu.
BAIXADO = {"pexels", "web", "wikimedia", "google", "broll", "renders", "styles", "compositions"}


def caminho() -> Path:
    env = os.environ.get("AVE_BIBLIOTECA")
    return Path(env).expanduser() if env else Path.home() / ".avelin" / "biblioteca.json"


def acervo() -> Path:
    return caminho().parent / "biblioteca"


def carregar() -> dict:
    p = caminho()
    if not p.exists():
        return {"versao": 1, "itens": [], "pastas": []}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"versao": 1, "itens": [], "pastas": []}
    d.setdefault("itens", [])
    d.setdefault("pastas", [])
    return d


def salvar(d: dict) -> None:
    p = caminho()
    p.parent.mkdir(parents=True, exist_ok=True)
    d["_leiame"] = ("Acervo de assets DESTE usuário — fora do clone, como brand.json e "
                    "preferencias.json. O repo entrega o mecanismo; o conteúdo é de quem edita.")
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def sha1(p: Path, limite: int = 8 << 20) -> str:
    """Hash do começo do arquivo + tamanho. Trilha de 40 MB não precisa ser lida
    inteira para saber que já está guardada, e colisão nos primeiros 8 MB *com*
    o mesmo tamanho não acontece em acervo de pessoa."""
    h = hashlib.sha1()
    with p.open("rb") as f:
        h.update(f.read(limite))
    h.update(str(p.stat().st_size).encode())
    return h.hexdigest()[:16]


def _ffprobe(p: Path, entradas: str, fluxo: str = "v:0") -> str:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", fluxo,
         "-show_entries", entradas, "-of", "csv=p=0", str(p)],
        capture_output=True, text=True,
    )
    return r.stdout.strip()


def medir(p: Path) -> dict:
    """Os fatos que decidem se o asset serve — lidos do arquivo, nunca do nome."""
    ext = p.suffix.lower()
    m: dict = {"bytes": p.stat().st_size}
    if shutil.which("ffprobe") is None:
        return m

    if ext in AUDIO:
        dur = _ffprobe(p, "format=duration", "a:0") or _ffprobe(p, "format=duration", "a")
        try:
            m["duracao"] = round(float(dur.split(",")[0]), 2)
        except (ValueError, IndexError):
            pass
        try:                                   # pico e ataque: o sfx.py já sabe medir
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from sfx import probe               # type: ignore
            info = probe(str(p))
            m["pico_db"] = round(info["peak"], 1)
            m["ataque_s"] = round(info.get("lead", 0.0), 3)
            m["baixo"] = info["peak"] < QUIET_DB
        except Exception:
            pass
    elif ext in IMAGEM or ext in VIDEO:
        if ext == ".svg":
            return m                            # vetorial: não tem pixel para medir
        campos = _ffprobe(p, "stream=width,height,pix_fmt")
        partes = campos.split("\n")[0].split(",") if campos else []
        if len(partes) >= 3:
            try:
                m["largura"], m["altura"] = int(partes[0]), int(partes[1])
            except ValueError:
                pass
            pix = partes[2]
            m["pix_fmt"] = pix
            # ALFA: o defeito que só aparece no render. Lista explícita porque
            # "yuv420p" tem 'a' em lugar nenhum e "yuva420p" tem — mas um padrão
            # esperto sobre a string erra nos dois sentidos, e errar aqui é
            # prometer transparência que o render não tem.
            m["alfa"] = bool(re.search(r"(yuva|rgba|argb|abgr|bgra|gbra|pal8|ya8|ya16)", pix))
        if ext in VIDEO:
            dur = _ffprobe(p, "format=duration", "v:0")
            try:
                m["duracao"] = round(float(dur.split(",")[0]), 2)
            except (ValueError, IndexError):
                pass
    elif ext == ".cube":
        cab = p.read_text(errors="ignore")[:2000]
        t = re.search(r'TITLE\s+"([^"]+)"', cab)
        n = re.search(r"LUT_3D_SIZE\s+(\d+)", cab)
        if t:
            m["titulo"] = t.group(1)
        if n:
            m["tamanho"] = int(n.group(1))
    return m


def alerta(tipo: str, m: dict) -> list[str]:
    """O que dizer ao usuário AGORA, em vez de descobrir no render."""
    fora = []
    if tipo in ("logo", "imagem") and m.get("alfa") is False:
        fora.append("sem canal alfa — sobre o vídeo isto desenha um retângulo, "
                    "não um logo. Peça o PNG com fundo transparente.")
    if tipo in ("sfx", "vinheta") and m.get("baixo"):
        fora.append(f"pico de {m['pico_db']} dB — vai sumir sob a fala.")
    if tipo == "sfx" and m.get("ataque_s", 0) > 0.05:
        fora.append(f"o ataque está {int(m['ataque_s'] * 1000)} ms DENTRO do arquivo — "
                    "agende antes da deixa, não em cima dela.")
    if tipo == "logo" and m.get("largura", 9999) < 400:
        fora.append(f"só {m.get('largura')}px de largura — sobe borrado num quadro 1080.")
    return fora


def ident(nome: str, tipo: str, usados: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", nome.lower()).strip("-") or tipo
    base = f"{tipo}-{base}"[:48]
    i, cand = 2, base
    while cand in usados:
        cand, i = f"{base}-{i}", i + 1
    return cand


def registrar(args) -> int:
    orig = Path(args.registrar).expanduser()
    if not orig.exists():
        print(f"erro: não existe: {orig}", file=sys.stderr)
        return 1
    d = carregar()
    tipo = args.tipo or POR_EXT.get(orig.suffix.lower(), "outro")
    if tipo not in TIPOS:
        print(f"erro: --tipo deve ser um de {', '.join(TIPOS)}", file=sys.stderr)
        return 1

    h = sha1(orig)
    ja = next((it for it in d["itens"] if it.get("sha1") == h), None)
    if ja:   # mesmo arquivo, outro caminho: atualiza, não duplica
        for campo, valor in (("nome", args.nome), ("papel", args.papel), ("nota", args.nota)):
            if valor:
                ja[campo] = valor
        if args.tags:
            ja["tags"] = sorted(set(ja.get("tags", [])) | set(args.tags.split(",")))
        salvar(d)
        print(f"já estava no acervo: {ja['id']} → {ja['arquivo']}")
        return 0

    m = medir(orig)
    nome = args.nome or orig.stem
    it_id = ident(nome, tipo, {i["id"] for i in d["itens"]})

    if args.link:
        destino = orig                      # acervo grande fica onde está
        modo = "link"
    else:
        pasta = acervo() / tipo
        pasta.mkdir(parents=True, exist_ok=True)
        destino = pasta / f"{it_id}{orig.suffix.lower()}"
        shutil.copy2(orig, destino)
        modo = "copia"

    item = {
        "id": it_id, "tipo": tipo, "nome": nome,
        "papel": args.papel or None,
        "arquivo": str(destino), "modo": modo, "origem": str(orig),
        "sha1": h, "medido": m,
        "tags": sorted(set(args.tags.split(","))) if args.tags else [],
        "nota": args.nota or None,
        "adicionado": date.today().isoformat(),
        "usos": [],
    }
    d["itens"].append(item)
    salvar(d)

    print(f"guardado: {it_id}  ({tipo}{'/' + item['papel'] if item['papel'] else ''})")
    print(f"  {destino}" + ("   [no lugar, não copiado]" if modo == "link" else ""))
    if m:
        print("  medido: " + ", ".join(f"{k}={v}" for k, v in m.items() if k != "bytes"))
    for a in alerta(tipo, m):
        print(f"  ATENÇÃO: {a}")
    if args.projeto:
        usar(it_id, args.projeto)
    return 0


def pasta(args) -> int:
    p = Path(args.pasta).expanduser()
    if not p.is_dir():
        print(f"erro: não é uma pasta: {p}", file=sys.stderr)
        return 1
    d = carregar()
    reg = {"dir": str(p), "tipo": args.tipo or "sfx", "papel": args.papel or None}
    if any(x["dir"] == reg["dir"] and x.get("papel") == reg["papel"] for x in d["pastas"]):
        print("já registrada")
        return 0
    d["pastas"].append(reg)
    salvar(d)
    n = sum(1 for f in p.rglob("*") if f.is_file() and f.suffix.lower() in AUDIO | IMAGEM | VIDEO)
    print(f"pasta no acervo: {p}  ({reg['tipo']}"
          f"{'/' + reg['papel'] if reg['papel'] else ''}, {n} arquivos)")
    return 0


def usar(item_id: str, projeto: str) -> int:
    d = carregar()
    it = next((i for i in d["itens"] if i["id"] == item_id), None)
    if not it:
        print(f"erro: sem item '{item_id}'", file=sys.stderr)
        return 1
    it.setdefault("usos", []).append({"projeto": str(Path(projeto).expanduser()),
                                      "data": date.today().isoformat()})
    salvar(d)
    n = len(it["usos"])
    faixa = "padrão da casa" if n >= USO_CALADO else ("aplica e informa" if n >= USO_INFORMA
                                                      else "ainda pergunta")
    print(f"{item_id}: {n} uso(s) — {faixa}")
    return 0


def _linha(it: dict) -> str:
    m, n = it.get("medido", {}), len(it.get("usos", []))
    extra = []
    if "duracao" in m:
        extra.append(f"{m['duracao']}s")
    if "largura" in m:
        extra.append(f"{m['largura']}×{m['altura']}" + ("" if m.get("alfa") else " SEM ALFA"))
    if m.get("baixo"):
        extra.append(f"pico {m['pico_db']}dB BAIXO")
    return (f"  {it['id']:<34} {it['tipo']}"
            f"{'/' + it['papel'] if it.get('papel') else '':<10} "
            f"{n} uso(s)  {' · '.join(extra)}"
            + (f"\n      {it['nota']}" if it.get("nota") else ""))


def listar(args) -> int:
    d = carregar()
    itens = [i for i in d["itens"]
             if (not args.tipo or i["tipo"] == args.tipo)
             and (not args.papel or i.get("papel") == args.papel)]
    itens.sort(key=lambda i: (-len(i.get("usos", [])), i["id"]))
    if args.json:
        print(json.dumps({"itens": itens, "pastas": d["pastas"]}, ensure_ascii=False, indent=2))
        return 0
    if not itens and not d["pastas"]:
        print("acervo vazio — nada foi guardado ainda.")
        return 0
    for it in itens:
        print(_linha(it))
    for p in d["pastas"]:
        print(f"  [pasta] {p['dir']}  ({p['tipo']}{'/' + p['papel'] if p.get('papel') else ''})")
    return 0


def resolver(args) -> int:
    """O que usar, e com quanta autonomia. Nunca decide sozinho abaixo de 3 usos."""
    d = carregar()
    termos = set((args.tags or "").lower().split(",")) - {""}
    cand = []
    for it in d["itens"]:
        if args.tipo and it["tipo"] != args.tipo:
            continue
        if args.papel and it.get("papel") != args.papel:
            continue
        pontos = len(it.get("usos", [])) * 2
        alvo = f"{it['id']} {it['nome']} {' '.join(it.get('tags', []))}".lower()
        pontos += sum(3 for t in termos if t in alvo)
        cand.append((pontos, it))
    cand.sort(key=lambda c: -c[0])

    pastas = [p for p in d["pastas"]
              if (not args.tipo or p["tipo"] == args.tipo)
              and (not args.papel or p.get("papel") == args.papel)]
    arquivos = []
    for p in pastas:
        raiz = Path(p["dir"]).expanduser()
        if raiz.is_dir():
            arquivos += [str(f) for f in sorted(raiz.rglob("*"))
                         if f.is_file() and f.suffix.lower() in AUDIO | IMAGEM | VIDEO][:40]

    melhor = cand[0][1] if cand else None
    usos = len(melhor.get("usos", [])) if melhor else 0
    autonomia = "perguntar" if usos < USO_INFORMA else ("informar" if usos < USO_CALADO else "aplicar")
    saida = {
        "melhor": melhor, "usos": usos, "autonomia": autonomia,
        "outros": [c[1]["id"] for c in cand[1:6]],
        "pastas": [p["dir"] for p in pastas], "arquivos_na_pasta": arquivos,
    }
    if args.json:
        print(json.dumps(saida, ensure_ascii=False, indent=2))
        return 0
    if not melhor and not arquivos:
        print("nada no acervo para isso — é caso de perguntar ou de buscar fora.")
        return 1
    if melhor:
        print(f"{melhor['id']} → {melhor['arquivo']}  ({usos} uso(s), autonomia: {autonomia})")
        for a in alerta(melhor["tipo"], melhor.get("medido", {})):
            print(f"  ATENÇÃO: {a}")
    for f in arquivos[:10]:
        print(f"  [pasta] {f}")
    return 0


def candidatos(args) -> int:
    """O que ESTE projeto usou e o acervo não tem — a lista do que vale perguntar.

    Só o que o usuário TROUXE. O que o pipeline baixou (pexels/, web/) não entra:
    isso se acha de novo buscando, e perguntar sobre ele gasta a paciência que
    a pergunta que importa vai precisar."""
    edit = Path(args.candidatos).expanduser()
    raiz = edit / "hyperframes" if (edit / "hyperframes").is_dir() else edit
    d = carregar()
    conhecidos = {i.get("sha1") for i in d["itens"]}
    pacote = {f.name for f in (Path(__file__).resolve().parent.parent / "assets" / "sfx").glob("*")}

    achados = []
    for f in sorted(raiz.rglob("*")):
        if not f.is_file() or f.suffix.lower() not in AUDIO | IMAGEM | VIDEO | {".cube"}:
            continue
        rel = f.relative_to(raiz)
        if any(part in BAIXADO for part in rel.parts):
            continue
        if f.name in pacote:                     # efeito do pacote comum do repo
            continue
        if f.name in ("preview.mp4", "final.mp4", "preview_proxy.mp4"):
            continue
        h = sha1(f)
        if h in conhecidos:
            continue
        tipo = POR_EXT.get(f.suffix.lower(), "outro")
        if rel.parts[0] == "brand":
            tipo = "logo"
        elif f.name.startswith("trilha"):
            tipo = "trilha"
        elif rel.parts[0] == "sfx":
            tipo = "sfx"
        achados.append({"arquivo": str(f), "tipo": tipo, "sha1": h, "medido": medir(f)})

    if args.json:
        print(json.dumps({"candidatos": achados}, ensure_ascii=False, indent=2))
        return 0
    if not achados:
        print("nada novo — tudo o que este projeto usou já está no acervo (ou veio de busca).")
        return 0
    print(f"{len(achados)} asset(s) que o usuário trouxe e o acervo ainda não tem:")
    for a in achados:
        m = a["medido"]
        det = ", ".join(f"{k}={v}" for k, v in m.items() if k != "bytes")
        print(f"  [{a['tipo']}] {Path(a['arquivo']).name}   {det}")
    return 0


def esquecer(args) -> int:
    d = carregar()
    it = next((i for i in d["itens"] if i["id"] == args.esquecer), None)
    if not it:
        print(f"erro: sem item '{args.esquecer}'", file=sys.stderr)
        return 1
    d["itens"] = [i for i in d["itens"] if i["id"] != args.esquecer]
    salvar(d)
    guardado = Path(it["arquivo"])
    if it.get("modo") == "copia" and guardado.exists() and acervo() in guardado.parents:
        guardado.unlink()
        print(f"esquecido e apagado do acervo: {args.esquecer}")
    else:
        print(f"esquecido do índice: {args.esquecer} (o arquivo original ficou onde estava)")
    return 0


def adotar_sfx(args) -> int:
    """O `~/.avelin/sfx.json` veio antes desta biblioteca e guardava a mesma
    coisa pela metade: pastas de efeito com papel. Adotar é melhor que pedir de
    novo o que o usuário já disse uma vez."""
    velho = caminho().parent / "sfx.json"
    if not velho.exists():
        print("nada a adotar — não existe ~/.avelin/sfx.json")
        return 0
    v = json.loads(velho.read_text(encoding="utf-8"))
    d = carregar()
    papeis = {caminho_: papel for papel, caminho_ in (v.get("papeis") or {}).items()}
    n = 0
    for dir_ in v.get("dirs", []):
        if any(p["dir"] == dir_ for p in d["pastas"]):
            continue
        d["pastas"].append({"dir": dir_, "tipo": "sfx", "papel": papeis.get(dir_)})
        n += 1
    salvar(d)
    print(f"adotadas {n} pasta(s) do sfx.json antigo")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--registrar", metavar="ARQUIVO")
    ap.add_argument("--pasta", metavar="DIR")
    ap.add_argument("--listar", action="store_true")
    ap.add_argument("--resolver", action="store_true")
    ap.add_argument("--candidatos", metavar="EDIT_DIR")
    ap.add_argument("--usar", metavar="ID")
    ap.add_argument("--esquecer", metavar="ID")
    ap.add_argument("--adotar-sfx", action="store_true", dest="adotar_sfx")
    ap.add_argument("--tipo", choices=TIPOS)
    ap.add_argument("--papel", help="para que serve: riser, reveal, abertura, marca-dagua…")
    ap.add_argument("--nome")
    ap.add_argument("--tags", help="separadas por vírgula")
    ap.add_argument("--nota", help="a condição de uso que só o usuário sabe")
    ap.add_argument("--projeto", metavar="EDIT_DIR", help="registra o uso já no registro")
    ap.add_argument("--link", action="store_true",
                    help="não copia: guarda o caminho (acervo grande, pasta viva)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.registrar:
        return registrar(args)
    if args.pasta:
        return pasta(args)
    if args.candidatos:
        return candidatos(args)
    if args.usar:
        if not args.projeto:
            print("erro: --usar precisa de --projeto", file=sys.stderr)
            return 1
        return usar(args.usar, args.projeto)
    if args.esquecer:
        return esquecer(args)
    if args.adotar_sfx:
        return adotar_sfx(args)
    if args.resolver:
        return resolver(args)
    if args.listar or True:
        return listar(args)


if __name__ == "__main__":
    sys.exit(main())

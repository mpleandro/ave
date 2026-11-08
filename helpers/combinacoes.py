#!/usr/bin/env python3
"""COMBINAÇÕES — monta finais a partir de uma biblioteca de peças já prontas.

O caso: um anúncio gravado em partes intercambiáveis (gancho × corpo × CTA, ou
qualquer N partes) e a entrega é o produto cartesiano delas — 12 ganchos × 9
corpos × 9 CTAs = 972 finais. Legendar 972 vídeos é inviável; legendar 30 peças
e EMENDAR é minutos. Este helper é a emenda.

    uv run python helpers/combinacoes.py --pecas <dir> --saida <dir> --listar
    uv run python helpers/combinacoes.py --pecas <dir> --saida <dir> --todas \\
        --trilha musica.mp3 --nome "BF26_VID_{0}{1}{2}"
    uv run python helpers/combinacoes.py ... --so gancho01 gancho04      (filtra grupos)
    uv run python helpers/combinacoes.py ... --combo gancho01 corpo02 cta03 [--combo ...]
    uv run python helpers/combinacoes.py ... --lista combos.csv [--sobrescrever]

PEÇAS. `--pecas` aponta para uma pasta onde cada peça é `<nome>/final.mp4` (a
saída da Fase 2 rodada por peça) ou `<nome>.mp4`. O grupo de cada peça é o
prefixo alfabético do nome (`gancho01` → gancho, `cta08b` → cta); `--partes`
dá a ORDEM dos grupos na final (padrão: gancho corpo cta).

O QUE ELE GARANTE:
  · Vídeo em concat SEM recodificar — por isso confere antes que todas as peças
    têm o mesmo codec/resolução/fps/timebase (Fase 2 do mesmo encoder: têm).
    Peça divergente aborta o lote, em vez de sair uma final com a emenda quebrada.
  · Áudio: concat das peças + trilha única por baixo (volume, fade in, fade out
    terminando no fim da final) → loudnorm em 2 passadas (padrão −14 LUFS, −1 TP).
    A trilha é UMA para a final inteira — trilha por peça reiniciaria em cada emenda.
  · Nome previsível a partir dos códigos (`gancho01`→1, `cta08b`→8B) por um
    molde (`--nome`, campos {0} {1} {2}…). Códigos de largura variável colidem
    (gancho 1 + corpo 13 = gancho 11 + corpo 3 = "113"): o lote inteiro é
    checado ANTES de começar, e a colisão aborta listando os pares. Resolve-se
    com `--separar 11` (esses usam o molde `--nome-sep`, com separador) ou com
    um molde que já separa.
  · Escreve em `.part.mp4` e renomeia: lote interrompido não deixa final pela
    metade com nome de pronta. Final existente é pulada (retomável); `--sobrescrever`
    remonta.
  · Para antes de encher o disco (`--min-livre`, GB).
  · Manifesto CSV (arquivo, pasta, peças, duração); refazer substitui a linha.
"""
import argparse, csv, itertools, json, pathlib, re, shutil, subprocess, sys, tempfile


def dur(p):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                 "-of", "csv=p=0", str(p)], capture_output=True, text=True).stdout)


def assinatura(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=codec_name,profile,width,height,r_frame_rate,time_base,pix_fmt",
                        "-of", "json", str(p)], capture_output=True, text=True)
    return tuple(sorted(json.loads(r.stdout)["streams"][0].items()))


def grupo(n):
    m = re.match(r"([a-zA-Z]+)", n)
    return m.group(1).lower() if m else ""


def cod(n):
    m = re.match(r"[a-zA-Z_]+0*(\d+)([a-zA-Z]?)$", n)
    if not m:
        raise SystemExit(f"nome de peça sem número: {n}")
    return m.group(1) + m.group(2).upper()


class Lote:
    def __init__(s, a):
        s.a = a
        s.pecas = {}
        for p in sorted(pathlib.Path(a.pecas).iterdir()):
            f = p / "final.mp4" if p.is_dir() else p
            if f.exists() and f.suffix == ".mp4" and grupo(p.stem if p.is_file() else p.name) in a.partes:
                s.pecas[p.name if p.is_dir() else p.stem] = f
        s.saida = pathlib.Path(a.saida)
        s.csv = pathlib.Path(a.manifesto) if a.manifesto else s.saida / "combinacoes.csv"

    def grupos(s):
        return {g: [n for n in s.pecas if grupo(n) == g] for g in s.a.partes}

    def nome(s, combo):
        cs = [cod(n) for n in combo]
        molde = s.a.nome_sep if cs[0] in s.a.separar else s.a.nome
        return molde.format(*cs)

    def pasta(s, combo):
        if not s.a.pasta:
            return s.saida
        cs = [cod(n) for n in combo]
        return s.saida / s.a.pasta.format(*cs, g=[grupo(n).capitalize() for n in combo],
                                          n=[str(int(re.match(r"\d+", c).group())) for c in cs])

    def destino(s, combo):
        return s.pasta(combo) / f"{s.nome(combo)}.mp4"

    def checa(s, combos):
        vistos, ruins = {}, []
        for c in combos:            # pelo NOME, não pelo caminho: as finais acabam numa pasta só
            d = s.destino(c).name
            if d in vistos and vistos[d] != c:
                ruins.append((d, vistos[d], c))
            vistos[d] = c
        if ruins:
            for n, x, y in ruins[:20]:
                print(f"COLISÃO {n}: {'+'.join(x)}  ×  {'+'.join(y)}")
            raise SystemExit(f"{len(ruins)} colisões de nome — use --separar ou um --nome com separador")
        usadas = sorted({n for c in combos for n in c})
        falta = [n for n in usadas if n not in s.pecas]
        if falta:
            raise SystemExit(f"peças sem arquivo: {', '.join(falta)}")
        sig = {}
        for n in usadas:
            sig.setdefault(assinatura(s.pecas[n]), []).append(n)
        if len(sig) > 1:
            for k, ns in sig.items():
                print(dict(k), "→", ", ".join(ns))
            raise SystemExit("peças com vídeo diferente: o concat sem recodificar quebraria a emenda")

    def manifesto(s, combo, out, D):
        s.csv.parent.mkdir(parents=True, exist_ok=True)
        cab = ["arquivo", "pasta", *s.a.partes, "duracao_s"]
        linhas = list(csv.reader(s.csv.open())) if s.csv.exists() else [cab]
        linhas = [l for l in linhas if l[:2] != [out.name, out.parent.name]]
        linhas.append([out.name, out.parent.name, *combo, f"{D:.1f}"])
        with s.csv.open("w", newline="") as f:
            csv.writer(f).writerows(linhas)

    def junta(s, combo, refazer=False):
        a, out = s.a, s.destino(combo)
        if out.exists() and not refazer:
            return out, "já existe"
        out.parent.mkdir(parents=True, exist_ok=True)
        partes = [s.pecas[n] for n in combo]
        D = sum(dur(p) for p in partes)
        with tempfile.TemporaryDirectory() as td:
            lst = pathlib.Path(td) / "l.txt"
            lst.write_text("".join("file '{}'\n".format(str(p.resolve()).replace("'", r"'\''"))
                                   for p in partes))
            ins = ["-f", "concat", "-safe", "0", "-i", str(lst)]
            if a.trilha:
                ins += ["-i", a.trilha]
                mix = (f"[0:a]aresample=48000[v];[1:a]aresample=48000,atrim=0:{D:.3f},"
                       f"volume={a.vol},afade=t=in:d={a.fade_in},"
                       f"afade=t=out:st={max(0, D - a.fade_out):.3f}:d={a.fade_out}[m];"
                       f"[v][m]amix=inputs=2:normalize=0:duration=first")
            else:
                mix = "[0:a]aresample=48000"
            alvo = f"loudnorm=I={a.lufs}:TP={a.tp}:LRA=11"
            r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", *ins, "-filter_complex",
                                f"{mix},{alvo}:print_format=json[a]", "-map", "[a]", "-f", "null", "-"],
                               capture_output=True, text=True)
            m = json.loads(r.stderr[r.stderr.rindex("{"):r.stderr.rindex("}") + 1])
            ln = (f"{alvo}:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
                  f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:"
                  f"offset={m['target_offset']}:linear=true,aresample=48000[a]")
            tmp = out.with_suffix(".part.mp4")
            subprocess.run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", f"{mix},{ln}",
                            "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac",
                            "-b:a", "192k", "-movflags", "+faststart", str(tmp)], check=True)
            tmp.rename(out)
        s.manifesto(combo, out, D)
        return out, f"{D:.1f}s"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--pecas", required=True, help="pasta com <nome>/final.mp4 ou <nome>.mp4")
    ap.add_argument("--saida", required=True)
    ap.add_argument("--partes", nargs="+", default=["gancho", "corpo", "cta"])
    ap.add_argument("--nome", default="{0}_{1}_{2}", help="molde do arquivo; {0},{1}… = códigos")
    ap.add_argument("--nome-sep", default=None, help="molde para os códigos em --separar")
    ap.add_argument("--separar", nargs="*", default=[], help="códigos da 1ª parte que usam --nome-sep")
    ap.add_argument("--pasta", default="{g[0]} {n[0]}",
                    help="subpasta por final ('' = tudo junto); {g[i]} grupo, {n[i]} número, {i} código")
    ap.add_argument("--trilha"); ap.add_argument("--vol", type=float, default=0.10)
    ap.add_argument("--fade-in", type=float, default=0.8); ap.add_argument("--fade-out", type=float, default=3.0)
    ap.add_argument("--lufs", type=float, default=-14); ap.add_argument("--tp", type=float, default=-1)
    ap.add_argument("--min-livre", type=float, default=6, help="GB; o lote para abaixo disso")
    ap.add_argument("--manifesto")
    modo = ap.add_mutually_exclusive_group(required=True)
    modo.add_argument("--todas", action="store_true")
    modo.add_argument("--so", nargs="+", help="só estas peças nos grupos delas (ordem preservada)")
    modo.add_argument("--combo", nargs="+", action="append")
    modo.add_argument("--lista", help="arquivo com uma combinação por linha (peças separadas por vírgula; "
                      "aceita o manifesto, que tem as peças a partir da 3ª coluna)")
    ap.add_argument("--sobrescrever", action="store_true", help="remonta finais que já existem")
    ap.add_argument("--listar", action="store_true", help="só mostra o plano e checa colisões")
    a = ap.parse_args()
    a.nome_sep = a.nome_sep or a.nome.replace("}{", "}_{")
    s = Lote(a)
    G = s.grupos()
    if a.lista:
        combos = []
        for l in csv.reader(open(a.lista)):
            l = [x.strip() for x in l if x.strip()]
            if not l or l[0].startswith("#") or l[0] == "arquivo":
                continue
            ini = 0 if grupo(l[0]) in a.partes else 2          # linha do manifesto: pula arquivo,pasta
            combos.append(tuple(l[ini:ini + len(a.partes)]))
    elif a.combo:
        combos = [tuple(c) for c in a.combo]
    else:
        if a.so:
            for g in a.partes:
                esc = [n for n in a.so if grupo(n) == g]
                if esc:
                    G[g] = esc
        combos = list(itertools.product(*(G[g] for g in a.partes)))
    for c in combos:
        if len(c) != len(a.partes) or [grupo(n) for n in c] != list(a.partes):
            raise SystemExit(f"combinação fora da ordem --partes {' '.join(a.partes)}: {' + '.join(c)}")
    s.checa(combos)
    falta = [c for c in combos if a.sobrescrever or not s.destino(c).exists()]
    if a.listar:
        print(" · ".join(f"{g}: {len(G[g])}" for g in a.partes))
        print(f"{len(combos)} combinações, {len(falta)} a montar; sem colisão de nome")
        for c in combos[:5]:
            print(" ", s.destino(c).relative_to(s.saida), "←", " + ".join(c))
        if falta:
            seg = sum(dur(s.pecas[n]) for n in falta[0])
            mb = sum(s.pecas[n].stat().st_size for n in falta[0]) / 1e6
            livre = shutil.disk_usage(s.saida if s.saida.exists() else s.saida.parent).free / 1e9
            print(f"estimativa: ~{seg:.0f}s e ~{mb:.0f} MB cada → ~{len(falta) * seg / 60:.0f} min de vídeo, "
                  f"~{len(falta) * mb / 1e3:.1f} GB (livre: {livre:.0f} GB, para em {a.min_livre:g})")
        return
    for c in combos:
        livre = shutil.disk_usage(s.saida if s.saida.exists() else s.saida.parent).free / 1e9
        if livre < a.min_livre:
            print(f"PARADO: só {livre:.1f} GB livres (mínimo {a.min_livre}); próxima {'+'.join(c)}", flush=True)
            sys.exit(3)
        o, info = s.junta(c, a.sobrescrever)
        print(o.relative_to(s.saida), info, flush=True)


if __name__ == "__main__":
    main()

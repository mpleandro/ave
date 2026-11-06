"""FASE 1 EM UM COMANDO — da fonte ao proxy, com o roteiro para aprovar.

  uv run python helpers/fase1.py <pasta_ou_video> [--ritmo equilibrado] [--respostas r.json]

Encadeia, nesta ordem, o que o SKILL.md pedia ao modelo passo a passo:
  1. fontes da pasta (1 fonte de fala; com mais de uma, pare e decida papéis
     com `source_roles.py` — ver SKILL.md)
  2. `transcribe.py`  — local, VAD-first (sem chave); cacheado
  3. `pack_transcripts.py` — takes_packed.md (a vista de leitura)
  4. `detect_color.py`  — grade sem perguntar (só `confidence: low` pergunta)
  5. `fala_limpa.py`    — defeitos.json + edl_proposto.json + roteiro.md + triagem.json
  6. edl.json ← edl_proposto.json (o anterior vira edl.prev.json)
  7. `portao_fase1.py --pular-render`
  8. `render.py --proxy` → preview_proxy.mp4
  9. `verify_cut.py`
 10. state.json aponta para o proxy

Saída: um resumo curto (perguntas abertas, cortes automáticos, ritmos, URL do
editor). Exit 0 = proxy pronto para mostrar; exit 2 = há perguntas para o
usuário (o proxy já existe mesmo assim); exit 3 = precisa de decisão antes
(mais de uma fonte, cor incerta); exit 1 = erro.

Segunda rodada (depois das respostas): o mesmo comando com `--respostas`
reaplica o `fala_limpa` com as decisões e refaz o proxy.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

HELPERS = Path(__file__).resolve().parent
sys.path.insert(0, str(HELPERS))
import ffbin

ffbin.garantir()

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".webm", ".wav", ".m4a", ".mp3"}


def _py() -> str:
    return sys.executable


def _run(args: list[str], o_que: str, quiet: bool = False, timeout: int = 3600) -> tuple[int, str]:
    t0 = time.time()
    r = subprocess.run([_py(), *args], capture_output=True, text=True, timeout=timeout)
    out = (r.stdout or "") + (("\n" + r.stderr) if r.returncode != 0 else "")
    if not quiet:
        print(f"  · {o_que} ({time.time() - t0:.0f}s){'' if r.returncode == 0 else f' — exit {r.returncode}'}", flush=True)
    return r.returncode, out


def fontes_de(alvo: Path) -> tuple[Path, list[Path]]:
    if alvo.is_file():
        return alvo.parent, [alvo]
    vids = sorted(p for p in alvo.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTS
                  and not p.name.startswith("."))
    return alvo, vids


def main() -> int:
    ap = argparse.ArgumentParser(description="Fase 1 em um comando")
    ap.add_argument("alvo", type=Path, help="pasta com o vídeo, ou o vídeo")
    ap.add_argument("--edit-dir", type=Path, default=None)
    ap.add_argument("--fonte", type=Path, default=None, help="qual arquivo é a fala (com mais de um)")
    ap.add_argument("--ritmo", default="equilibrado", choices=["conservador", "equilibrado", "agressivo"])
    ap.add_argument("--respostas", type=Path, default=None, help="{id: cortar|manter} para as perguntas")
    ap.add_argument("--sem-proxy", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    alvo = args.alvo.resolve()
    if not alvo.exists():
        sys.exit(f"não achei {alvo}")
    pasta, vids = fontes_de(alvo)
    edit = (args.edit_dir or pasta / "edit").resolve()
    edit.mkdir(parents=True, exist_ok=True)
    rel: dict = {"edit": str(edit), "passos": []}

    # 1. fonte de fala
    if args.fonte:
        fonte = args.fonte.resolve()
    elif len(vids) == 1:
        fonte = vids[0]
    elif not vids:
        sys.exit(f"nenhum vídeo em {pasta}")
    else:
        print(f"{len(vids)} arquivos em {pasta} — decida o papel de cada um antes (source_roles.py) "
              f"e rode de novo com --fonte <a fala>.")
        _run([str(HELPERS / "source_roles.py"), str(pasta)], "source_roles", quiet=True)
        rc, out = _run([str(HELPERS / "source_roles.py"), str(pasta)], "papéis das fontes")
        print(out[-3000:])
        return 3
    rel["fonte"] = str(fonte)
    print(f"Fase 1 — {fonte.name} → {edit}")

    # 2. transcrição (local por padrão; cacheada)
    rc, out = _run([str(HELPERS / "transcribe.py"), str(fonte), "--edit-dir", str(edit), "--language", "pt"],
                   "transcrição")
    if rc != 0:
        print(out[-2000:])
        return 1
    # 2b. carimbo esticado: o Whisper estende o fim da palavra por cima da
    # pausa; o portão exige o aparo (mecânico, idempotente) — então ele roda aqui
    _run([str(HELPERS / "transcript_audit.py"), str(edit), "--fix-times"], "aparo de carimbos", quiet=True)
    # 3. vista de leitura
    _run([str(HELPERS / "pack_transcripts.py"), "--edit-dir", str(edit)], "takes_packed.md", quiet=True)

    # 4. cor
    grade = ""
    rc, out = _run([str(HELPERS / "detect_color.py"), str(fonte), "--json"], "perfil de cor")
    cor: dict = {}
    if rc == 0:
        try:
            cor = json.loads(out[out.index("{"):out.rindex("}") + 1])
        except (ValueError, json.JSONDecodeError):
            cor = {}
    rel["cor"] = {k: cor.get(k) for k in ("profile", "confidence", "grade") if k in cor}
    if cor.get("confidence") == "low":
        print(f"  cor incerta: {cor.get('profile')} — mostre `grade.py --candidates` e pergunte antes de seguir")
        rel["parar"] = "cor"
    elif str(cor.get("profile", "rec709")).lower() not in ("rec709", "normal", ""):
        grade = str(cor.get("grade") or "")

    # 5. defeitos de fala → EDL proposto + roteiro
    cmd = [str(HELPERS / "fala_limpa.py"), str(edit), "--fonte", str(fonte), "--ritmo", args.ritmo]
    if grade:
        cmd += ["--grade", grade]
    if args.respostas:
        cmd += ["--aplicar", str(args.respostas.resolve())]
    rc, out = _run(cmd, "erros de fala e roteiro")
    if rc not in (0, 2):
        print(out[-2000:])
        return 1
    rel["fala_limpa"] = out.strip().splitlines()[0] if out.strip() else ""
    defeitos = json.loads((edit / "defeitos.json").read_text())
    perguntas = [h for h in defeitos["itens"] if h["acao"] == "perguntar"
                 and defeitos.get("decisoes", {}).get(str(h["id"])) is None]
    cortes = [h for h in defeitos["itens"] if h["acao"].startswith("cortar")
              and defeitos.get("decisoes", {}).get(str(h["id"])) != "manter"]

    # 6. edl.json
    edl_p, prop = edit / "edl.json", edit / "edl_proposto.json"
    if edl_p.exists():
        shutil.copy(edl_p, edit / "edl.prev.json")
    shutil.copy(prop, edl_p)

    # 7. portão sem render
    rc, out = _run([str(HELPERS / "portao_fase1.py"), str(edit), "--pular-render", "--json"], "portão (plano)")
    try:
        portao = json.loads(out[out.index("{"):out.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        portao = {"ok": rc == 0, "bruto": out[-1500:]}
    rel["portao_plano"] = portao

    # 8. proxy
    proxy = edit / "preview_proxy.mp4"
    if not args.sem_proxy:
        rc, out = _run([str(HELPERS / "render.py"), str(edl_p), "-o", str(proxy), "--proxy", "--no-subtitles"],
                       "proxy 720p")
        if rc != 0:
            print(out[-2500:])
            return 1
        # 9. verificação numérica
        min_sil = {"conservador": 1.6, "equilibrado": 1.4, "agressivo": 0.9}[args.ritmo]
        rc, out = _run([str(HELPERS / "verify_cut.py"), str(edl_p), str(proxy), "--min-silence", f"{min_sil:.2f}"],
                       "verify_cut", quiet=True)
        rel["verify_cut"] = [ln for ln in out.splitlines() if "VERDICT" in ln or "FAIL" in ln][:6]
        # 10. estado
        st_p = edit / "state.json"
        try:
            st = json.loads(st_p.read_text()) if st_p.exists() else {}
        except json.JSONDecodeError:
            st = {}
        # relativo ao <edit>: é assim que o preview_server resolve (`_safe`)
        st.update({"video": proxy.name, "ritmo": args.ritmo,
                   "message": "Corte proposto pronto — leia o roteiro e responda às perguntas"})
        st_p.write_text(json.dumps(st, ensure_ascii=False, indent=2))

    # resumo
    url = ""
    try:
        url = json.loads((Path.home() / ".avelin" / "server.json").read_text()).get("url", "")
    except (OSError, json.JSONDecodeError):
        pass
    rel.update({"perguntas": perguntas, "cortes_automaticos": len(cortes),
                "ritmos": defeitos.get("ritmos", {}), "roteiro": str(edit / "roteiro.md"), "url": url})
    if args.json:
        print(json.dumps(rel, ensure_ascii=False, indent=1))
    else:
        print()
        print(f"Roteiro: {edit / 'roteiro.md'}")
        print(f"Cortes automáticos: {len(cortes)}  ·  ritmo {args.ritmo}: "
              + ", ".join(f"{k} {v['respiros']} respiros/−{v['segundos']}s" for k, v in defeitos.get("ritmos", {}).items()))
        if perguntas:
            print(f"Perguntas ao usuário ({len(perguntas)}):")
            for h in perguntas[:8]:
                print(f"  [?{h['id']}] ({h['t']:.1f}s) {h.get('pergunta', h['texto'])[:160]}")
        if not portao.get("ok", True):
            n = len(portao.get("defeitos", portao.get("faltas", []))) if isinstance(portao, dict) else "?"
            print(f"Portão (plano): {n} item(ns) — em geral são as perguntas acima; veja `portao_fase1.py {edit} --pular-render`")
        if rel.get("verify_cut"):
            print("verify_cut: " + " | ".join(rel["verify_cut"]))
        if not args.sem_proxy:
            print(f"Proxy: {proxy}")
        if url:
            print(f"Editor: {url}")
    if rel.get("parar"):
        return 3
    return 2 if perguntas else 0


if __name__ == "__main__":
    sys.exit(main())

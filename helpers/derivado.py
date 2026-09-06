#!/usr/bin/env python3
"""Cache de artefatos DERIVADOS, endereçado por conteúdo.

    from derivado import derivado
    dados = derivado("levels", [fonte], {"frame": 1024}, "1", lambda: medir(fonte))

O PROBLEMA QUE ISTO RESOLVE não é principalmente tempo — é o mesmo defeito
aparecendo em três lugares:

  1. `levels_for` (cut_words.py) spawna um interpretador e recupera dois floats
     fazendo split do console de outro programa. Cinco módulos o chamam, em
     cinco processos, e o único cache existente é um dict que morre com o
     processo. Medido: 0,8s por chamada numa fonte de 3 min.
  2. Os segmentos de vídeo são apagados inteiros a cada render, porque a
     alternativa — reaproveitar por glob — já produziu o defeito documentado em
     `extract_and_assemble_jcut`: um EDL de 3 trechos sobre um 4º segmento velho
     deu 9,23s para um vídeo de 7,57s, e todo overlay caiu no lugar errado.
  3. `cut_mapped.json` e `captions.json` são gerados com guarda `if not exists`
     e nunca invalidados, então uma correção de texto depois da Fase 2 é
     ignorada **em silêncio**.

São três instâncias de "gera uma vez, nunca invalida" — e a razão de existir uma
implementação só é que cada cache ad-hoc traz o mesmo bug de volta por um
caminho novo.

POR QUE A CHAVE NÃO É O HASH DO CONTEÚDO INTEIRO.

Era a intenção, e a medição a derrubou: sha256 custa 0,3s em 102 MB e 2,7s em
1 GB. Uma fonte 4K em LOG passa de 10 GB, o que daria 30s de hash para poupar
0,8s de análise. Então a assinatura é O(1) — tamanho + mtime em nanossegundos +
o primeiro e o último MB — e distingue qualquer reexportação ou arquivo
diferente, que é o caso real. Não distingue uma edição cirúrgica no meio de um
arquivo mantendo o tamanho, e é por isso que `AVELIN_SEM_CACHE=1` existe.

POR QUE MORA EM ~/.avelin E NÃO NO PROJETO.

A análise é da FONTE, não do corte. A mesma gravação usada em dois projetos tem
o mesmo piso de ruído nos dois, e um cache por projeto pagaria duas vezes por
uma medição que não depende do projeto. Mesma razão pela qual as preferências já
moram lá.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable

BORDA = 1 << 20   # 1 MB de cada ponta


def raiz() -> Path:
    env = os.environ.get("AVE_DERIVADOS")
    return Path(env).expanduser() if env else Path.home() / ".avelin" / "derivados"


def desligado() -> bool:
    """A saída de emergência. Uma suspeita de cache tem de se resolver com um
    comando, não com uma investigação — e quem depura precisa poder desligar
    tudo sem editar código."""
    return os.environ.get("AVELIN_SEM_CACHE", "").strip() not in ("", "0", "false")


def impressao(p: Path) -> str:
    """Assinatura de um arquivo em tempo constante. Ver o docstring do módulo."""
    st = p.stat()
    h = hashlib.sha256()
    h.update(f"{st.st_size}:{st.st_mtime_ns}".encode())
    with p.open("rb") as f:
        h.update(f.read(BORDA))
        if st.st_size > BORDA * 2:
            f.seek(-BORDA, os.SEEK_END)
            h.update(f.read(BORDA))
    return h.hexdigest()[:16]


def chave(nome: str, entradas: list[Path], params: dict, versao: str) -> str:
    """A chave é (entradas + parâmetros + versão do produtor).

    `versao` é o que faltava nos caches ad-hoc: quando a FÓRMULA muda — outro
    limiar, outra janela — o arquivo velho continua válido pela entrada e
    inválido pelo código, e sem a versão na chave ele sobrevive à mudança e
    responde com a matemática antiga. Suba a versão ao mexer no produtor.
    """
    h = hashlib.sha256()
    h.update(f"{nome}|{versao}|".encode())
    for p in entradas:
        h.update(f"{p.name}:{impressao(p)}|".encode())
    h.update(json.dumps(params, sort_keys=True, ensure_ascii=False).encode())
    return h.hexdigest()[:20]


def derivado(
    nome: str,
    entradas: list[Path],
    params: dict,
    versao: str,
    produtor: Callable[[], Any],
    *,
    forcar: bool = False,
) -> Any:
    """O derivado em cache, ou produzido e guardado agora.

    `produtor` devolve qualquer coisa serializável em JSON. Uma exceção dele
    sobe — um cache não deve transformar falha em resposta plausível, que é
    exatamente o que o `levels_for` fazia ao devolver −33,0 dBFS em silêncio
    quando o parse do stdout falhava.
    """
    if forcar or desligado() or any(not p.exists() for p in entradas):
        return produtor()

    k = chave(nome, entradas, params, versao)
    caminho = raiz() / f"{nome}-{k}.json"
    if caminho.exists():
        try:
            return json.loads(caminho.read_text())["dados"]
        except (json.JSONDecodeError, KeyError):
            caminho.unlink(missing_ok=True)   # corrompido: refaz

    dados = produtor()
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_suffix(".tmp")
    tmp.write_text(json.dumps({
        "dados": dados,
        "_nome": nome,
        "_versao": versao,
        "_params": params,
        "_entradas": [p.name for p in entradas],
    }, ensure_ascii=False))
    tmp.replace(caminho)   # atômico: dois renders paralelos não leem meio arquivo
    return dados


def limpar(nome: str | None = None) -> int:
    """Apaga os derivados. Sem `nome`, apaga todos. Devolve quantos."""
    d = raiz()
    if not d.exists():
        return 0
    alvos = list(d.glob(f"{nome}-*.json" if nome else "*.json"))
    for a in alvos:
        a.unlink(missing_ok=True)
    return len(alvos)


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Inspeciona e limpa o cache de derivados")
    ap.add_argument("--limpar", nargs="?", const="", metavar="NOME",
                    help="apaga tudo, ou só os de um nome")
    args = ap.parse_args()
    if args.limpar is not None:
        n = limpar(args.limpar or None)
        print(f"{n} derivado(s) apagado(s) de {raiz()}")
        return 0
    d = raiz()
    arquivos = sorted(d.glob("*.json")) if d.exists() else []
    print(f"{raiz()}  —  {len(arquivos)} derivado(s)")
    for a in arquivos:
        try:
            m = json.loads(a.read_text())
            print(f"  {m.get('_nome'):<12} v{m.get('_versao'):<4} "
                  f"{', '.join(m.get('_entradas') or [])}")
        except (json.JSONDecodeError, TypeError):
            print(f"  {a.name}  (ilegível)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

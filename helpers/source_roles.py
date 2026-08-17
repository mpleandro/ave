#!/usr/bin/env python3
"""O PAPEL DE CADA FONTE, medido do arquivo — antes de escrever o EDL.

A skill sempre teve a tabela de papéis (fala, multicam, insert, tela dividida,
B-roll, overlay) e nenhuma forma de DESCOBRIR qual é qual: quem decidia era o
agente no olho, e errar aqui custa o corte inteiro. Tratar uma multicam como
duas tomadas produz o mesmo trecho duas vezes; tratar um B-roll como fala manda
transcrever um plano de apoio; e um insert não reservado vira buraco descoberto
depois do portão de fase.

O QUE SEPARA MULTICAM DE B-ROLL É O ÁUDIO, não a imagem.

Duas câmeras apontadas para o mesmo momento gravam a MESMA voz. Os envelopes de
energia das duas são quase idênticos, deslocados pelo instante em que cada uma
começou a gravar — então correlacionar os envelopes dá duas coisas de uma vez: a
confirmação de que é o mesmo momento (a correlação) e o deslocamento entre elas
(o pico), que é exatamente o sync que a multicam precisa. Um B-roll não
correlaciona com nada, porque foi gravado noutra hora.

A imagem não serve para isso: duas câmeras no mesmo cômodo se parecem tanto
quanto uma câmera e o B-roll gravado no mesmo cômodo.

O que este helper NÃO faz: decidir. Ele mede e entrega a evidência para a
PERGUNTA ao usuário — uma gravação de tela pode ser insert, tela dividida ou
overlay, e o arquivo não diz qual. Ver a seção "Papel de cada fonte" no SKILL.md.

O QUE É MEDIDO E O QUE É PALPITE, porque confundir os dois aqui é caro:
  · MEDIDO — multicam, duplicata, tem áudio, duração, proporção, fps.
  · PALPITE — "isto é fala" versus "isto é apoio". O helper informa `áudio
    ativo` (energia acima do piso de ruído), que NÃO é o mesmo que fala:
    um clipe de estoque com um whoosh marcou 29%.

E FICA REGISTRADO O QUE NÃO FUNCIONOU, para ninguém tentar de novo: separar
fala de música/efeito pela modulação silábica (energia do envelope em 2–8 Hz)
foi implementado e MEDIDO neste material — as duas cabeças falantes deram 0,200
e 0,169, e o clipe de efeito sonoro deu 0,185, bem no meio delas. O teste não
separa; o que separa é perguntar.

Uso:
    uv run python helpers/source_roles.py <videos_dir> [--json] [--max-corr-s 240]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm", ".mts", ".mxf", ".m2ts"}
# Pastas de trabalho da própria skill. Um `clips_graded/` tem cem extrações do
# material que já está sendo analisado — varrê-lo transformaria três fontes em
# cento e três.
SKIP_DIRS = {"edit", "clips_graded", "clips_proxy", "renders", "verify",
             "hyperframes", "remotion", "transcripts", "pexels", "sfx"}

ENV_HZ = 50          # quadros por segundo do envelope (20ms) — resolução de sobra
                     # para casar duas câmeras: 20ms é meia sílaba
CORR_MIN_MULTICAM = 0.55   # acima disto, o mesmo momento
CORR_MIN_TALVEZ = 0.32     # entre os dois, ambíguo — vai para a pergunta
ATIVO_ALTO = 0.22    # fração do tempo com áudio acima do piso — candidata a fala
ATIVO_BAIXO = 0.06   # abaixo disto não há voz nenhuma para cortar
CURTO_S = 25.0       # ninguém grava uma tomada de cabeça falante em 25 segundos

# O NOME DA PASTA É EVIDÊNCIA, e é a mais forte que existe para separar apoio
# de tomada — porque é a única que carrega a INTENÇÃO de quem filmou. Nenhuma
# medida de áudio distingue um documentário narrado (apoio) de uma cabeça
# falante (tomada): as duas são voz contínua em 60% do tempo. A pasta
# `Broll/` distingue, e sem ela dois documentários do YouTube foram
# classificados como tomadas do usuário.
#
# Entra como evidência RELATADA, nunca como conclusão silenciosa: pasta é
# convenção de pessoa, e pessoas guardam arquivo no lugar errado.
PASTA_APOIO = {"broll", "b-roll", "b roll", "apoio", "stock", "footage",
               "flow", "insert", "inserts", "overlay", "graficos", "gráficos",
               "telas", "screen", "capturas"}
PASTA_FALA = {"aroll", "a-roll", "a roll", "takes", "tomadas", "camera",
              "câmera", "cam", "entrevista", "principal"}


def probe(p: Path) -> dict:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json",
         "-show_format", "-show_streams", str(p)],
        capture_output=True, text=True)
    try:
        d = json.loads(r.stdout)
    except json.JSONDecodeError:
        return {}
    v = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"), None)
    a = next((s for s in d.get("streams", []) if s.get("codec_type") == "audio"), None)
    if not v:
        return {}
    w, h = int(v.get("width") or 0), int(v.get("height") or 0)
    # A ROTAÇÃO É A ORIENTAÇÃO REAL. Celular grava 1920x1080 com matriz de
    # exibição de 90° — a proporção do arquivo diz paisagem e o vídeo é
    # retrato. Ler só width/height classifica errado a fonte principal.
    rot = 0
    for sd in v.get("side_data_list") or []:
        if "rotation" in sd:
            rot = abs(int(sd["rotation"])) % 180
    if rot == 90:
        w, h = h, w
    fps = 0.0
    try:
        num, den = (v.get("avg_frame_rate") or "0/1").split("/")
        fps = float(num) / float(den) if float(den) else 0.0
    except (ValueError, ZeroDivisionError):
        pass
    return {
        "w": w, "h": h, "fps": round(fps, 2),
        "dur": float(d.get("format", {}).get("duration") or 0),
        "audio": a is not None,
        "vcodec": v.get("codec_name", ""),
        "pix_fmt": v.get("pix_fmt", ""),
    }


def envelope(p: Path, max_s: float) -> np.ndarray | None:
    """Envelope de energia em dB, um valor a cada 20ms.

    dB e não amplitude linear: a correlação tem de casar a ESTRUTURA da fala
    (onde há voz, onde há pausa), e em linear os picos dominam a conta a ponto
    de duas gravações do mesmo momento com ganhos diferentes deixarem de casar.
    """
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-t", str(max_s), "-i", str(p),
         "-vn", "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
        capture_output=True)
    if not r.stdout:
        return None
    x = np.frombuffer(r.stdout[: len(r.stdout) // 2 * 2], dtype="<i2").astype(np.float32)
    if x.size < 8000:
        return None
    per = 8000 // ENV_HZ
    n = x.size // per
    if n < 10:
        return None
    rms = np.sqrt((x[: n * per].reshape(n, per) ** 2).mean(axis=1) + 1e-9)
    return 20 * np.log10(rms / 32768 + 1e-9)


def speech_ratio(env: np.ndarray) -> tuple[float, float]:
    """Quanto do tempo é fala, com o piso de ruído aprendido da própria gravação.

    Intermédias de Ridler-Calvard e não um percentil fixo: um percentil embute
    uma suposição sobre quanto do arquivo é fala, que é justamente o que está
    sendo medido. Uma fonte de B-roll é 100% "não fala" e uma tomada falada é
    80% fala — nenhum percentil serve para as duas.
    """
    t = env.mean()
    for _ in range(40):
        baixo, alto = env[env <= t], env[env > t]
        if not baixo.size or not alto.size:
            break
        novo = (baixo.mean() + alto.mean()) / 2
        if abs(novo - t) < 0.01:
            break
        t = novo
    fala = env > t + 3.0   # 3 dB acima do limiar: margem contra o ruído de sala
    return float(fala.mean()), float(t)


def correlate(a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    """Melhor casamento entre dois envelopes → (coeficiente, deslocamento em s).

    Correlação normalizada por FFT. O deslocamento positivo significa que `b`
    começou DEPOIS de `a` no mundo real.
    """
    a = a - a.mean()
    b = b - b.mean()
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na < 1e-6 or nb < 1e-6:
        return 0.0, 0.0
    n = 1 << int(np.ceil(np.log2(a.size + b.size)))
    c = np.fft.irfft(np.fft.rfft(a, n) * np.conj(np.fft.rfft(b, n)), n)
    c = np.concatenate([c[-(b.size - 1):], c[: a.size]])
    i = int(np.argmax(c))
    lag = i - (b.size - 1)
    # A normalização usa as normas INTEIRAS, o que subestima de propósito um
    # casamento entre trechos de tamanhos muito diferentes: um B-roll de 12s
    # não pode marcar 0.9 por casar com 12s de uma fonte de 9 minutos.
    return float(c[i] / (na * nb)), lag / ENV_HZ


def e_duplicata(a: dict, b: dict) -> bool:
    """O MESMO arquivo duas vezes, e não outro ângulo.

    Acontece o tempo todo: o export com e sem timecode, o original e a cópia, o
    proxy ao lado do original. Chamar isso de multicam faz o agente contar
    quatro câmeras onde há duas e oferecer ao usuário uma troca de ângulo que
    não muda um pixel — foi o que aconteceu na primeira versão deste helper,
    no projeto Fome de Poder.

    Correlação quase perfeita COM deslocamento zero E mesma duração: duas
    câmeras de verdade sempre começam a gravar em instantes diferentes, então o
    deslocamento zero é o que separa a cópia do ângulo.
    """
    c, lag = correlate(a["_env"], b["_env"])
    return c >= 0.98 and abs(lag) <= 0.08 and abs(a["dur"] - b["dur"]) <= 0.5


def _cadeia(p: Path, base: Path) -> list[str]:
    """Os nomes de pasta entre a raiz varrida e o arquivo, mais a própria raiz.

    A raiz entra porque rodar o helper direto em `Broll/` tem de ver o `Broll`;
    a cadeia inteira entra porque `Broll/Flow/clipe.mp4` é apoio pelo avô, não
    pelo pai.
    """
    nomes = [base.name]
    try:
        nomes += list(p.relative_to(base).parts[:-1])
    except ValueError:
        pass
    return [n.lower() for n in nomes]


def _apoio(p: Path, base: Path) -> bool:
    return any(n in PASTA_APOIO for n in _cadeia(p, base))


def _fala(p: Path, base: Path) -> bool:
    c = _cadeia(p, base)
    return any(n in PASTA_FALA for n in c) and not any(n in PASTA_APOIO for n in c)


def coletar(base: Path, prof: int = 2) -> list[Path]:
    """As fontes: a raiz e até dois níveis de subpastas.

    Dois e não um porque `Broll/Flow/` existe no material real — separar o
    estoque do resto do apoio é arranjo comum, e parar num nível deixaria esses
    arquivos invisíveis para a análise inteira.
    """
    achados: list[Path] = []

    def desce(d: Path, resta: int) -> None:
        for q in sorted(d.iterdir(), key=lambda x: x.name.lower()):
            if q.is_file() and q.suffix.lower() in VIDEO_EXT:
                achados.append(q)
            elif (q.is_dir() and resta > 0 and not q.name.startswith(".")
                  and q.name.lower() not in SKIP_DIRS):
                desce(q, resta - 1)

    desce(base, prof)
    return achados


def mmss(s: float) -> str:
    return f"{int(s) // 60}:{int(s) % 60:02d}"


def main() -> int:
    ap = argparse.ArgumentParser(description="Papel de cada fonte, medido do arquivo")
    ap.add_argument("videos_dir", type=Path)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--max-corr-s", type=float, default=240.0,
                    help="quanto de cada fonte entra na correlação (padrão 240s: "
                         "duas câmeras do mesmo take casam nos primeiros minutos, "
                         "e correlacionar uma aula de 1h inteira não melhora nada)")
    args = ap.parse_args()

    base = args.videos_dir.expanduser().resolve()
    if not base.is_dir():
        print(f"pasta não encontrada: {base}", file=sys.stderr)
        return 1
    arquivos = coletar(base)
    if not arquivos:
        print(f"nenhum vídeo em {base}", file=sys.stderr)
        return 1

    fontes = []
    for p in arquivos:
        info = probe(p)
        if not info:
            continue
        env = envelope(p, args.max_corr_s) if info["audio"] else None
        fala, piso = speech_ratio(env) if env is not None else (0.0, 0.0)
        fontes.append({
            "nome": p.stem, "path": str(p),
            # O caminho relativo inteiro, não só o pai: com dois níveis de
            # varredura, "[Flow/]" esconde que aquilo mora dentro de Broll/.
            "pasta": str(p.parent.relative_to(base)) if p.parent != base else "",
            **info, "fala": round(fala, 3), "piso_db": round(piso, 1),
            # O nome da pasta CONTENEDORA, mesmo quando ela é a raiz varrida:
            # rodar o helper direto em `Broll/` deixava `pasta` vazio e a
            # evidência saía como "guardada em /".
            "pastaNome": p.parent.name,
            "pastaApoio": _apoio(p, base),
            "pastaFala": _fala(p, base),
            "_env": env,
        })

    # A proporção MINORITÁRIA é sinal: numa pasta de vertical, o único
    # horizontal quase nunca é uma tomada — é gravação de tela, arte ou apoio.
    props = [round(f["w"] / f["h"], 2) if f["h"] else 0 for f in fontes]
    comum = max(set(props), key=props.count) if props else 0
    for f, pr in zip(fontes, props):
        f["proporcaoRara"] = bool(pr and comum and pr != comum)

    # ---- agrupamento por MOMENTO ----
    # Só entre fontes que TÊM fala. Dois B-rolls de ambiente da mesma sala
    # correlacionam pelo ruído do ar-condicionado, e isso não é multicam.
    #
    # GRUPO, não par. Encadear pares produz "side é ângulo de side_sem_tc, que
    # é ângulo de front_sem_tc" — três saltos para dizer que as quatro fontes
    # são o mesmo momento, e cada deslocamento medido contra um vizinho
    # diferente. Medido no projeto Fome de Poder, onde isso apareceu inteiro.
    # O que a multicam precisa é do deslocamento contra UMA referência.
    faladas = [f for f in fontes if f["_env"] is not None and f["fala"] >= ATIVO_BAIXO]
    for f in fontes:
        f["parDe"] = None
        f["corr"] = 0.0
        f["offset"] = 0.0
        f["grupo"] = None
        f["duplicataDe"] = None
    pai = {f["nome"]: f["nome"] for f in faladas}

    def raiz(n: str) -> str:
        while pai[n] != n:
            pai[n] = pai[pai[n]]
            n = pai[n]
        return n

    for i, a in enumerate(faladas):
        for bb in faladas[i + 1:]:
            c, _lag = correlate(a["_env"], bb["_env"])
            if c >= CORR_MIN_TALVEZ:
                pai[raiz(bb["nome"])] = raiz(a["nome"])

    grupos: dict[str, list] = {}
    for f in faladas:
        grupos.setdefault(raiz(f["nome"]), []).append(f)

    for membros in grupos.values():
        if len(membros) < 2:
            continue
        # A REFERÊNCIA é a mais longa; empate desempata pelo nome, para o
        # relatório ser estável entre rodadas — evidência que muda sozinha não
        # é evidência.
        # A REFERÊNCIA NÃO SAI SÓ DA DURAÇÃO. Medido no projeto 29: uma
        # gravação de tela de 994x1594 a 45fps casou 0,86 com a câmera — mesmo
        # momento, de verdade — e virou "a espinha" por ser dois segundos mais
        # longa que ela. A proporção fora do padrão do material entra na frente
        # da duração: a espinha de um vídeo é filmada no formato do vídeo.
        ordem = sorted(membros, key=lambda f: (f["proporcaoRara"], -f["dur"], f["nome"]))
        ref = ordem[0]
        # Os ÂNGULOS DISTINTOS já aceitos. Cada fonte nova é comparada com
        # eles, não só com a referência: `side_sem_tc` é duplicata de `side` e
        # multicam legítima de `front` ao mesmo tempo, então testar apenas
        # contra a referência a promoveria a um terceiro ângulo que não existe.
        angulos = [ref]
        for f in ordem:
            f["grupo"] = ref["nome"]
            if f is ref:
                continue
            # Contra a REFERÊNCIA, sempre — é o deslocamento que a multicam usa.
            c, lag = correlate(ref["_env"], f["_env"])
            f["parDe"], f["corr"], f["offset"] = ref["nome"], round(c, 3), round(lag, 2)
            gemeo = next((g for g in angulos if e_duplicata(g, f)), None)
            if gemeo is not None:
                f["duplicataDe"] = gemeo["nome"]
            else:
                angulos.append(f)

    # ---- papel provável ----
    for f in fontes:
        if f.get("duplicataDe"):
            f["papel"] = "duplicata"
        elif f["parDe"]:
            ref = next(g for g in fontes if g["nome"] == f["parDe"])
            formato_outro = (f["proporcaoRara"] != ref["proporcaoRara"]
                             or (f["w"], f["h"]) != (ref["w"], ref["h"]))
            if f["corr"] < CORR_MIN_MULTICAM:
                f["papel"] = "multicam?"
            elif formato_outro:
                # MESMO MOMENTO NÃO É MESMA COISA. Uma gravação de tela feita
                # enquanto a câmera rodava casa tão bem quanto uma segunda
                # câmera — e não é um ângulo: é insert, tela dividida ou
                # overlay, e só o usuário sabe qual.
                f["papel"] = "mesmo-momento"
            else:
                f["papel"] = "multicam"
        elif f["grupo"]:
            # A referência de um grupo multicam é a espinha por construção:
            # duas câmeras só apontam para alguém falando.
            f["papel"] = "fala"
        elif not f["audio"]:
            f["papel"] = "sem-audio"
        elif f["pastaApoio"]:
            # A pasta vence o áudio, e é o único lugar onde ela vence: um
            # documentário narrado guardado em `Broll/` mede exatamente como
            # uma cabeça falante e não é uma.
            f["papel"] = "apoio-pasta"
        elif f["dur"] <= CURTO_S:
            f["papel"] = "clipe-curto"
        elif f["fala"] < ATIVO_BAIXO:
            f["papel"] = "sem-fala"
        elif f["fala"] >= ATIVO_ALTO:
            f["papel"] = "fala?"
        else:
            f["papel"] = "pouca-fala"

    if args.json:
        print(json.dumps([{k: v for k, v in f.items() if k != "_env"} for f in fontes],
                         ensure_ascii=False, indent=2))
        return 0

    # MEDIDO em maiúscula, PALPITE com "?". A distinção existe para o agente
    # não apresentar um palpite ao usuário como se fosse leitura do arquivo.
    ROTULO = {
        "fala": "FALA — a espinha, entra como range do EDL",
        "multicam": "MULTICAM — mesmo momento, outro ângulo (NÃO é outra tomada)",
        "multicam?": "TALVEZ MULTICAM — correlação fraca, confirme",
        "mesmo-momento": ("MESMO MOMENTO, OUTRO FORMATO — casa com a câmera mas "
                          "não é um ângulo dela (gravação de tela?). Papel é do usuário."),
        "duplicata": "DUPLICATA — o MESMO arquivo, não outro ângulo. Use um só.",
        "fala?": "talvez FALA — áudio ativo e longa, mas isso não prova voz",
        "apoio-pasta": "talvez APOIO — está numa pasta de apoio (a pasta, não o áudio)",
        "clipe-curto": "talvez APOIO — curta demais para ser uma tomada",
        "sem-fala": "SEM VOZ — B-roll, insert ou tela dividida",
        "sem-audio": "SEM ÁUDIO — B-roll, insert ou overlay",
        "pouca-fala": "AMBÍGUA — pouco áudio ativo",
    }
    print(f"FONTES em {base}  ({len(fontes)})\n")
    for f in fontes:
        orient = "vertical" if f["h"] > f["w"] else "horizontal"
        onde = f"  [{f['pasta']}/]" if f["pasta"] else ""
        print(f"{f['nome']}{onde}")
        print(f"   {mmss(f['dur'])}  {f['w']}x{f['h']} {orient}  {f['fps']:g}fps  "
              f"áudio: {'sim' if f['audio'] else 'NÃO'}"
              + ("  · proporção diferente das outras" if f["proporcaoRara"] else ""))
        if f["audio"]:
            print(f"   áudio ativo em {f['fala'] * 100:.0f}% do tempo "
                  f"(energia acima do piso — NÃO é o mesmo que voz)")
        if f["pastaApoio"] or f["pastaFala"]:
            print(f"   guardada em {f['pastaNome']}/ — a pasta sugere "
                  f"{'apoio' if f['pastaApoio'] else 'tomada'}")
        if f.get("duplicataDe"):
            print(f"   idêntica a {f['duplicataDe']}")
        elif f["parDe"]:
            sinal = "+" if f["offset"] >= 0 else ""
            print(f"   casa com {f['parDe']}: correlação {f['corr']:.2f}, "
                  f"começa {sinal}{f['offset']:.2f}s depois dela")
        print(f"   → {ROTULO[f['papel']]}\n")

    # TUDO o que não foi medido vai para a pergunta. Multicam e duplicata são
    # leitura do arquivo; o resto é palpite, e palpite sobre o papel de uma
    # fonte é exatamente o que o portão de fase existe para não deixar passar.
    duvidas = [f for f in fontes if f["papel"] not in ("multicam", "duplicata", "fala")]
    if duvidas:
        print("PERGUNTE AO USUÁRIO (o arquivo não responde isto):")
        for f in duvidas:
            print(f"  · {f['nome']} ({mmss(f['dur'])}) — o que ele É no vídeo?")
        print("\n  Pergunte pelo USO, com as opções descritas pelo que o espectador")
        print("  vê — nunca pelos nomes da tabela. O que OCUPA TEMPO DE TELA")
        print("  (insert, tela dividida, B-roll) tem de ser RESERVADO na Fase 1.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Transcrição LOCAL, VAD-first — sem chave de API.

Por que existe (medido em 2026-11-06, fonte "conselho ou mentoria", 180 s):
o Whisper com o arquivo INTEIRO apaga do texto retakes e gaguejos que existem
no áudio ("uma dúvida, uma dúvida" virou uma; o retake da abertura sumiu). Não
é o motor nem a nuvem — Groq e mlx local erram igual — é o CONTEXTO: vendo a
frase inteira o decoder suaviza. Transcrever cada REGIÃO DE FALA isolada
devolve as repetições ("uma dúvida ×2", "passo a ×2", abertura ×2) em uma
passada de ~55 s, sem o `verify_takes --fonte` de 15 min.

E uma janela isolada sobre SILÊNCIO alucina (~200 tokens "h h h" em 4 s): por
isso o VAD vem primeiro — nada é transcrito fora de região de fala, e o
`defeitos_audio.json` deixa de "confirmar" repetições em trechos mudos.

Pipeline:
  ffmpeg → wav 16 kHz mono → Silero VAD (onnx, CPU, ~0,6 s/3 min) → regiões
  → pedaços ≤ MAX_S (cortados no ponto mais silencioso) → Whisper local por
  pedaço (mlx-whisper large-v3-turbo em Apple Silicon; faster-whisper fora)
  com prompt de disfluência e sem contexto anterior → guarda anti-alucinação
  → saída no MESMO schema do transcribe.py (Scribe: word/spacing/speaker_0)
  + transcripts/vad/<stem>.json com as regiões (o fala_limpa.py usa).

Uso:
  uv run python helpers/transcribe_local.py <fonte> --edit-dir <edit>
  uv run python helpers/transcribe_local.py <fonte.wav> -o /tmp/t.json
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
# ffmpeg completo garantido (o do sistema com zscale, ou o estático do pip) — ver ffbin.py
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ffbin  # noqa: E402
ffbin.garantir()

os.environ.setdefault("TQDM_DISABLE", "1")   # mlx-whisper imprime uma barra por pedaço

SR = 16000
MAX_S = 12.0                 # pedaço máximo enviado ao Whisper, isolado
PAD_REGIAO_S = 0.15          # palavra fora da região ± isto é alucinação
TOKENS_POR_S_MAX = 8.0       # pedaço com mais que isto é alucinação
REPETICAO_CURTA_MAX = 6      # ≥ N tokens iguais de 1–2 letras seguidos = lixo
MODELO_MLX = "mlx-community/whisper-large-v3-turbo"
MODELO_FW = "large-v3-turbo"
PROMPT_DISFLUENCIA = "Ahn, é, tipo, né, então... eu, eu acho que... quer dizer, hum."
_APPLE_SILICON = sys.platform == "darwin" and platform.machine() == "arm64"


# --------------------------------------------------------------------------- #
# disponibilidade
# --------------------------------------------------------------------------- #

def disponivel() -> bool:
    """True quando o VAD e um motor Whisper local importam nesta máquina."""
    try:
        import onnxruntime  # noqa: F401
        import silero_vad  # noqa: F401
        import soundfile  # noqa: F401
    except ImportError:
        return False
    if _APPLE_SILICON:
        try:
            import mlx_whisper  # noqa: F401
            return True
        except ImportError:
            return False
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


# --------------------------------------------------------------------------- #
# áudio
# --------------------------------------------------------------------------- #

def extrair_wav(fonte: Path, dest: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(fonte), "-vn",
         "-ac", "1", "-ar", str(SR), "-c:a", "pcm_s16le", str(dest)],
        check=True,
    )


def carregar_mono(wav: Path) -> np.ndarray:
    import soundfile as sf
    a, sr = sf.read(str(wav), dtype="float32")
    if a.ndim > 1:
        a = a.mean(axis=1)
    if sr != SR:
        raise ValueError(f"esperava {SR} Hz, veio {sr}")
    return np.ascontiguousarray(a, dtype=np.float32)


def regioes_de_fala(mono: np.ndarray, min_silencio_ms: int = 300,
                    pad_ms: int = 120) -> list[tuple[float, float]]:
    """Regiões [início, fim] em segundos onde o Silero VAD ouve voz."""
    import torch
    from silero_vad import get_speech_timestamps, load_silero_vad
    modelo = load_silero_vad(onnx=True)
    ts = get_speech_timestamps(
        torch.from_numpy(mono), modelo, sampling_rate=SR, return_seconds=True,
        min_silence_duration_ms=min_silencio_ms, speech_pad_ms=pad_ms,
    )
    return [(float(t["start"]), float(t["end"])) for t in ts]


def _rms_db(mono: np.ndarray, a: float, b: float) -> float:
    seg = mono[int(a * SR):int(b * SR)]
    if seg.size == 0:
        return -120.0
    r = float(np.sqrt(np.mean(seg * seg)) + 1e-9)
    return 20.0 * np.log10(r)


def ponto_mais_silencioso(mono: np.ndarray, a: float, b: float,
                          janela: float = 0.05) -> float:
    """Centro da janela de menor energia entre a e b."""
    if b - a <= janela:
        return (a + b) / 2
    melhor, melhor_db = (a + b) / 2, 1e9
    t = a
    while t + janela <= b:
        db = _rms_db(mono, t, t + janela)
        if db < melhor_db:
            melhor, melhor_db = t + janela / 2, db
        t += janela / 2
    return melhor


def fatiar(mono: np.ndarray, regioes: list[tuple[float, float]],
           max_s: float = MAX_S) -> list[tuple[float, float]]:
    """Regiões maiores que max_s viram pedaços cortados no ponto mais
    silencioso em ±1,5 s do múltiplo de max_s. Região curta fica inteira."""
    out: list[tuple[float, float]] = []
    for s, e in regioes:
        while e - s > max_s:
            alvo = s + max_s
            corte = ponto_mais_silencioso(mono, max(s + 2.0, alvo - 1.5), min(e - 1.0, alvo + 1.5))
            out.append((s, corte))
            s = corte
        out.append((s, e))
    return out


# --------------------------------------------------------------------------- #
# motor
# --------------------------------------------------------------------------- #

class Motor:
    """Carrega o modelo uma vez; transcreve pedaços isolados."""

    def __init__(self, language: str = "pt", verbose: bool = False):
        self.language = language
        self.verbose = verbose
        self.nome = ""
        self._fw = None
        if _APPLE_SILICON:
            import mlx_whisper  # noqa: F401
            self.nome = f"local-mlx/{MODELO_MLX.split('/')[-1]}"
        else:
            from faster_whisper import WhisperModel
            self._fw = WhisperModel(MODELO_FW, compute_type="int8")
            self.nome = f"local-faster/{MODELO_FW}"

    def transcrever(self, seg: np.ndarray) -> list[dict]:
        """Palavras {start,end,text} RELATIVAS ao início do pedaço."""
        prompt = PROMPT_DISFLUENCIA if self.language == "pt" else None
        if self._fw is None:
            import mlx_whisper
            r = mlx_whisper.transcribe(
                seg, path_or_hf_repo=MODELO_MLX, language=self.language,
                word_timestamps=True, condition_on_previous_text=False,
                initial_prompt=prompt, no_speech_threshold=0.5, verbose=None,
            )
            out = []
            for sg in r.get("segments", []):
                if sg.get("no_speech_prob", 0.0) > 0.6 and sg.get("avg_logprob", 0.0) < -1.0:
                    continue
                for w in sg.get("words", []):
                    out.append({"start": float(w["start"]), "end": float(w["end"]),
                                "text": str(w["word"]).strip()})
            return out
        segs, _info = self._fw.transcribe(
            seg, language=self.language, word_timestamps=True,
            condition_on_previous_text=False, initial_prompt=prompt,
            no_speech_threshold=0.5, vad_filter=False,
        )
        out = []
        for sg in segs:
            for w in (sg.words or []):
                out.append({"start": float(w.start), "end": float(w.end), "text": w.word.strip()})
        return out


# --------------------------------------------------------------------------- #
# guarda anti-alucinação
# --------------------------------------------------------------------------- #

_CURTA = re.compile(r"^[\W_]*[a-zà-ú]{1,2}[\W_]*$", re.IGNORECASE)


def guarda_alucinacao(palavras: list[dict], dur: float) -> list[dict]:
    """Descarta o que não pode ser fala real num pedaço de `dur` segundos."""
    if not palavras:
        return []
    if len(palavras) / max(dur, 0.5) > TOKENS_POR_S_MAX:
        return []
    out: list[dict] = []
    corrida: list[dict] = []

    def _fecha():
        nonlocal corrida
        if len(corrida) < REPETICAO_CURTA_MAX:
            out.extend(corrida)
        corrida = []

    for w in palavras:
        if w["start"] < -PAD_REGIAO_S or w["start"] > dur + PAD_REGIAO_S:
            continue
        n = w["text"].lower()
        if corrida and _CURTA.match(n) and n == corrida[-1]["text"].lower():
            corrida.append(w)
            continue
        _fecha()
        corrida.append(w)
    _fecha()
    return out


# --------------------------------------------------------------------------- #
# saída no schema Scribe
# --------------------------------------------------------------------------- #

def montar_saida(palavras: list[dict], language: str, backend: str) -> dict:
    words: list[dict] = []
    prev_end: float | None = None
    for w in palavras:
        s, e, txt = w["start"], w["end"], w["text"]
        if not txt:
            continue
        # "resolvê" + "-los": o tokenizador separa a ênclise; junta de volta
        if txt.startswith("-") and words and words[-1]["type"] == "word":
            words[-1]["text"] += txt
            words[-1]["end"] = round(max(words[-1]["end"], e), 3)
            prev_end = words[-1]["end"]
            continue
        if e <= s:
            e = s + 0.04
        if prev_end is not None and s > prev_end + 1e-3:
            words.append({"text": " ", "start": prev_end, "end": s,
                          "type": "spacing", "speaker_id": "speaker_0"})
        words.append({"text": txt, "start": round(s, 3), "end": round(e, 3),
                      "type": "word", "speaker_id": "speaker_0"})
        prev_end = e
    texto = " ".join(w["text"] for w in words if w["type"] == "word")
    return {
        "language_code": language,
        "language": language,
        "text": texto,
        "words": words,
        "_transcription_backend": backend,
        "_spacing_source": "measured/silero-vad",
    }


def transcrever_arquivo(fonte: Path, language: str = "pt", verbose: bool = True,
                        max_s: float = MAX_S) -> tuple[dict, list[tuple[float, float]]]:
    """Transcreve uma fonte (vídeo ou wav). Devolve (payload, regiões VAD)."""
    t0 = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "a.wav"
        extrair_wav(fonte, wav)
        mono = carregar_mono(wav)
    dur_total = len(mono) / SR
    regioes = regioes_de_fala(mono)
    pedacos = fatiar(mono, regioes, max_s=max_s)
    if verbose:
        print(f"  vad: {len(regioes)} regiões de fala, {len(pedacos)} pedaços "
              f"({sum(e - s for s, e in regioes):.0f}s de fala em {dur_total:.0f}s) "
              f"em {time.time() - t0:.1f}s", flush=True)
    motor = Motor(language=language, verbose=verbose)
    todas: list[dict] = []
    for i, (s, e) in enumerate(pedacos):
        seg = mono[int(s * SR):int(e * SR)]
        ws = guarda_alucinacao(motor.transcrever(seg), e - s)
        for w in ws:
            todas.append({"start": s + w["start"], "end": min(s + w["end"], e + PAD_REGIAO_S),
                          "text": w["text"]})
        if verbose and (i + 1) % 10 == 0:
            print(f"  {i + 1}/{len(pedacos)} pedaços", flush=True)
    todas.sort(key=lambda w: w["start"])
    payload = montar_saida(todas, language, motor.nome)
    if verbose:
        print(f"  {len([w for w in payload['words'] if w['type'] == 'word'])} palavras "
              f"em {time.time() - t0:.1f}s ({motor.nome})", flush=True)
    return payload, regioes


def gravar(fonte: Path, edit_dir: Path, language: str = "pt", verbose: bool = True,
           forcar: bool = False) -> Path:
    """Grava transcripts/<stem>.json e transcripts/vad/<stem>.json. Cacheado."""
    tdir = edit_dir / "transcripts"
    tdir.mkdir(parents=True, exist_ok=True)
    out = tdir / f"{fonte.stem}.json"
    if out.exists() and not forcar:
        if verbose:
            print(f"cached: {out.name}")
        return out
    payload, regioes = transcrever_arquivo(fonte, language=language, verbose=verbose)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    vdir = tdir / "vad"
    vdir.mkdir(exist_ok=True)
    (vdir / f"{fonte.stem}.json").write_text(json.dumps(
        {"fonte": fonte.name, "sr": SR, "regioes": [[round(s, 3), round(e, 3)] for s, e in regioes]},
        indent=1))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Transcrição local VAD-first (sem chave)")
    ap.add_argument("fonte", type=Path)
    ap.add_argument("--edit-dir", type=Path, default=None,
                    help="grava em <edit>/transcripts/ (padrão: <pasta da fonte>/edit)")
    ap.add_argument("-o", "--out", type=Path, default=None, help="grava só este JSON (sem cache)")
    ap.add_argument("--language", default="pt")
    ap.add_argument("--max-s", type=float, default=MAX_S)
    ap.add_argument("--forcar", action="store_true", help="ignora o cache")
    ap.add_argument("-q", "--quiet", action="store_true")
    args = ap.parse_args()
    fonte = args.fonte.resolve()
    if not fonte.exists():
        sys.exit(f"fonte não encontrada: {fonte}")
    if not disponivel():
        sys.exit("transcrição local indisponível: rode `uv sync --inexact` na pasta do Avelin")
    if args.out:
        payload, regioes = transcrever_arquivo(fonte, args.language, not args.quiet, args.max_s)
        payload["_vad"] = [[round(s, 3), round(e, 3)] for s, e in regioes]
        args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        print(f"saved: {args.out}")
        return
    edit = (args.edit_dir or fonte.parent / "edit").resolve()
    p = gravar(fonte, edit, args.language, not args.quiet, args.forcar)
    print(f"saved: {p}")


if __name__ == "__main__":
    main()

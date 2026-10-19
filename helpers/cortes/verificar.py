"""Conferir OUVINDO onde o corte começa quando o conectivo de abertura sai.

A energia do áudio diz onde há vãos de voz; não diz qual deles separa o "Mas"
do "parem". Os tempos de palavra também não: numa fonte real estavam 0,27s
adiantados, e o arquivo exportado começava em "Mas parem…". Medido numa
amostra de 13 conectivos, escolher o vão "mais perto" da fronteira da
transcrição errava 6 — cortava "Eu descobri isso" e começava em "depois de
seis", ou deixava o "que" de "só que".

Então cada ponto candidato, em ordem, é transcrito localmente (mlx-whisper,
sem custo) por 2,5s, e fica o primeiro cuja fala começa na palavra esperada —
e não no conectivo. Se nenhum serve, o conectivo fica: melhor um "Mas" no
corte do que uma palavra comida. Só roda para os cortes que vão à galeria.
"""
from __future__ import annotations

import difflib
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from derivado import derivado  # noqa: E402

from .candidatos import _norm

MODELO = "mlx-community/whisper-large-v3-turbo"


def _ouvir(video: Path, t: float) -> list[str]:
    import mlx_whisper  # noqa: PLC0415
    with tempfile.TemporaryDirectory() as d:
        wav = Path(d) / "a.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", str(video),
                        "-t", "2.5", "-vn", "-ac", "1", "-ar", "16000", str(wav)], check=True)
        r = mlx_whisper.transcribe(str(wav), path_or_hf_repo=MODELO, language="pt",
                                   word_timestamps=True, condition_on_previous_text=False)
    return [_norm(w["word"]) for s in r.get("segments", []) for w in s.get("words", [])]


def bate(ouvido: list[str], esperado: str, tirou: str) -> bool:
    tirou_ = _norm(tirou).split()
    if not ouvido or (tirou_ and ouvido[0] == tirou_[0]):
        return False
    alvo = _norm(esperado).split()[:2]
    return difflib.SequenceMatcher(None, " ".join(ouvido[:2]), " ".join(alvo)).ratio() >= 0.6


def ponto_de_corte(video: Path, apara: dict) -> float | None:
    """O primeiro ponto em que a fala começa na palavra certa, ou None."""
    def medir():
        try:
            import mlx_whisper  # noqa: F401, PLC0415
        except ImportError:
            return None
        for p in apara["pontos"]:
            if bate(_ouvir(video, p), apara["texto"], apara["tirou"]):
                return p
        return None
    return derivado("corte_conectivo", [video],
                    {"pontos": apara["pontos"], "texto": apara["texto"], "tirou": apara["tirou"]},
                    "1", medir)

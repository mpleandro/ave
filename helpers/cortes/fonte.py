"""O que todos os estágios leem da fonte: palavras, silêncios medidos e config.

A pasta de trabalho é `<pasta do vídeo>/<stem>_cortes/` — não um `edit/`, que
dentro de uma pasta com vários projetos faria a pasta inteira parecer um.

    <stem>_cortes/
      transcripts/<stem>.json   transcrito (transcribe.py --edit-dir aqui)
      analise/*.json            saída de cada estágio
      cortes_config.json        opcional: sobrescreve chaves do config padrão
      NN_<titulo>.mp4           o que foi exportado
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HELPERS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HELPERS))

from derivado import derivado  # noqa: E402
from hook_finder import palavras  # noqa: E402
from speech_regions import measured_silences  # noqa: E402

CONFIG_PADRAO = Path(__file__).resolve().parent / "config.json"


def pasta_trabalho(video: Path) -> Path:
    return video.parent / f"{video.stem}_cortes"


def _mesclar(base: dict, extra: dict) -> dict:
    out = dict(base)
    for k, v in extra.items():
        out[k] = _mesclar(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def config(trabalho: Path | None = None) -> dict:
    """O padrão do módulo, com o `cortes_config.json` do trabalho por cima."""
    cfg = json.loads(CONFIG_PADRAO.read_text())
    local = trabalho / "cortes_config.json" if trabalho else None
    if local and local.exists():
        cfg = _mesclar(cfg, json.loads(local.read_text()))
    return cfg


def carregar_palavras(trabalho: Path, video: Path) -> list[dict]:
    """[{w, s, e}] — só palavras, sem os tokens de espaçamento."""
    if not (trabalho / "transcripts" / f"{video.stem}.json").exists():
        sys.exit(f"sem transcrito: rode transcribe.py \"{video}\" --edit-dir \"{trabalho}\"")
    return palavras(trabalho, video.stem)


def silencios(video: Path) -> list[tuple[float, float]]:
    """Silêncios MEDIDOS no áudio, em cache por fonte: numa fonte de uma hora o
    silencedetect é uma passada inteira de ffmpeg, e todo estágio precisa dele."""
    dados = derivado("silencios", [video], {"min": 0.12}, "1",
                     lambda: [list(p) for p in measured_silences(video)])
    return [(float(a), float(b)) for a, b in dados]


def energia(video: Path):
    """(times, rms_dbfs) a ~21ms, em cache por fonte: é uma passada de astats
    no arquivo inteiro, e numa fonte de uma hora isso custa quase um minuto."""
    import numpy as np  # noqa: PLC0415
    from voice_levels import rms_timeline  # noqa: PLC0415

    def medir():
        t, lv = rms_timeline(video)
        return {"t": [round(float(x), 3) for x in t], "db": [round(float(x), 1) for x in lv]}

    d = derivado("rms", [video], {"frame": "astats"}, "1", medir)
    return np.asarray(d["t"]), np.asarray(d["db"])


def salvar(trabalho: Path, nome: str, dados) -> Path:
    p = trabalho / "analise" / f"{nome}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(dados, ensure_ascii=False, indent=2))
    return p


def ler(trabalho: Path, nome: str):
    return json.loads((trabalho / "analise" / f"{nome}.json").read_text())

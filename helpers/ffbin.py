"""ffmpeg sem brew: o do sistema quando serve, senão o estático que vem pelo pip.

O `ffmpeg` do Homebrew virou uma build enxuta sem `zscale` (o tone-map de HDR
que todo iPhone precisa), e a instalação pedia `ffmpeg-full` + `unlink` +
`link --force` — três aprovações e uma armadilha. O pacote `static-ffmpeg`
(pip) traz uma build completa por plataforma; medido em 2026-11-06 (arm64,
ffmpeg 7.0): tem `zscale`, `deesser`, `loudnorm`, `silencedetect` e
`videotoolbox`. Então a regra é:

  1. há `ffmpeg` no PATH com `zscale`?  → usa esse, nada muda;
  2. senão → põe a pasta do estático NA FRENTE do PATH deste processo (e dos
     filhos, que herdam o ambiente). Nenhum helper precisa saber o caminho.

Chame `garantir()` no início dos scripts que rodam ffmpeg/ffprobe. O
`install.sh` também linka os binários em ~/.local/bin, então na prática o
caso 2 só acontece em máquina onde o install não rodou.
"""
from __future__ import annotations

import functools
import os
import shutil
import subprocess
import sys
from pathlib import Path

FILTROS_NECESSARIOS = ("zscale", "loudnorm", "silencedetect")


@functools.lru_cache(maxsize=4)
def _tem_filtros(ffmpeg: str) -> bool:
    try:
        out = subprocess.run([ffmpeg, "-hide_banner", "-filters"], capture_output=True,
                             text=True, timeout=20).stdout
    except (OSError, subprocess.TimeoutExpired):
        return False
    return all(f" {f} " in out for f in FILTROS_NECESSARIOS)


def _sem_helpers_no_path():
    """Contexto: tira helpers/ do sys.path e o `progress` sombreado de sys.modules.

    `import static_ffmpeg` puxa `progress.bar`, e `helpers/progress.py` toma
    esse nome quando helpers/ está na frente do caminho."""
    import contextlib

    @contextlib.contextmanager
    def ctx():
        helpers = Path(__file__).resolve().parent
        salvo = list(sys.path)
        sombra = sys.modules.pop("progress", None)
        sys.path = [p for p in sys.path if p and Path(p).resolve() != helpers]
        try:
            yield
        finally:
            sys.path = salvo
            if sombra is not None:
                sys.modules["progress"] = sombra
    return ctx()


def estatico() -> tuple[str, str] | None:
    """(ffmpeg, ffprobe) do pacote static-ffmpeg, baixando na primeira vez."""
    import importlib.util
    spec = importlib.util.find_spec("static_ffmpeg")
    if spec is None or not spec.origin:
        return None
    base = Path(spec.origin).resolve().parent / "bin"
    for ff in sorted(base.glob("*/ffmpeg*")):
        if ff.name in ("ffmpeg", "ffmpeg.exe") and ff.is_file():
            fp = ff.with_name("ffprobe" + ff.suffix)
            if fp.is_file():
                return str(ff), str(fp)
    with _sem_helpers_no_path():
        try:
            from static_ffmpeg import run
            ff, fp = run.get_or_fetch_platform_executables_else_raise()
            return str(ff), str(fp)
        except Exception:  # noqa: BLE001 — sem rede
            return None


def garantir() -> str:
    """Deixa um ffmpeg completo na frente do PATH. Devolve de onde ele veio."""
    sistema = shutil.which("ffmpeg")
    if sistema and shutil.which("ffprobe") and _tem_filtros(sistema):
        return "sistema"
    est = estatico()
    if est is None:
        return "nenhum"
    pasta = str(Path(est[0]).parent)
    os.environ["PATH"] = pasta + os.pathsep + os.environ.get("PATH", "")
    return "estatico"


def caminhos() -> tuple[str, str]:
    garantir()
    return shutil.which("ffmpeg") or "ffmpeg", shutil.which("ffprobe") or "ffprobe"


if __name__ == "__main__":
    origem = garantir()
    ff, fp = caminhos()
    print(f"{origem}: {ff}")

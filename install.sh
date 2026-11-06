#!/usr/bin/env bash
# Avelin — instalação em um comando (macOS / Linux). Sem brew, sem sudo, sem chave.
#
#   bash install.sh                 # instala em ~/.claude/skills/ave
#   AVE_DIR=/outro/lugar bash install.sh
#   AVE_REPO=/caminho/local bash install.sh   # clona de outro repositório (testes)
#
# O que faz, nesta ordem: uv (instalador Python, sem sudo) → clona/atualiza o
# repositório → dependências Python (inclui ffmpeg completo e a transcrição
# local) → modelo de voz (~1,6 GB, uma vez) → conferência real (doctor.py).
# Node.js (só a Fase 2) é verificado e explicado, não instalado às escondidas.
set -euo pipefail

AVE="${AVE_DIR:-$HOME/.claude/skills/ave}"
REPO="${AVE_REPO:-https://github.com/mpleandro/ave}"
RAMO="${AVE_RAMO:-}"

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }

say "1/5  uv (instalador Python)"
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"
uv --version

say "2/5  Avelin em $AVE"
if [ -d "$AVE/.git" ]; then
  git -C "$AVE" pull --ff-only || echo "  (não consegui atualizar — seguindo com o que está aí)"
else
  mkdir -p "$(dirname "$AVE")"
  if [ -n "$RAMO" ]; then git clone --branch "$RAMO" "$REPO" "$AVE"; else git clone "$REPO" "$AVE"; fi
fi

say "3/5  dependências (Python, ffmpeg completo, transcrição local)"
uv sync --directory "$AVE" --inexact

say "4/5  ffmpeg e modelo de voz"
uv run --directory "$AVE" python helpers/doctor.py --preparar

say "5/5  conferência"
set +e
uv run --directory "$AVE" python helpers/doctor.py
RC=$?
set -e

cat <<EOF

Pronto. Para editar: entre na pasta com o vídeo e abra o seu agente (ex.: \`claude\`).
Diga "edita esse vídeo". Tudo sai em <pasta>/edit/.
EOF
exit $RC

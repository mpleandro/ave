#!/usr/bin/env bash
# Avelin — instalação em um comando (macOS / Linux). Sem brew, sem sudo, sem chave.
#
#   bash install.sh                 # instala em ~/.claude/skills/ave
#   AVE_DIR=/outro/lugar bash install.sh
#   AVE_REPO=/caminho/local bash install.sh   # clona de outro repositório (testes)
#
# O que faz, nesta ordem: uv (instalador Python, sem sudo) → clona/atualiza o
# repositório → dependências Python (inclui ffmpeg completo e a transcrição
# local) → Node.js em SEGUNDO PLANO, só se o computador não tiver um 22+ (o
# binário oficial do nodejs.org em ~/.avelin/node, sem sudo; um Node antigo da
# pessoa não é trocado) → modelo de voz (~1,6 GB, uma vez) → conferência real
# (doctor.py) → abre o editor no navegador. O Node segue baixando depois disso:
# a checklist do editor mostra o progresso e vira ✓ sozinha.
#
#   AVE_SEM_EDITOR=1 bash install.sh   # não abre o editor no fim (testes, CI)
set -euo pipefail

AVE="${AVE_DIR:-$HOME/.claude/skills/ave}"
REPO="${AVE_REPO:-https://github.com/mpleandro/ave}"
RAMO="${AVE_RAMO:-}"

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }

say "1/6  uv (instalador Python)"
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"
uv --version

say "2/6  Avelin em $AVE"
if [ -d "$AVE/.git" ]; then
  git -C "$AVE" pull --ff-only || echo "  (não consegui atualizar — seguindo com o que está aí)"
else
  mkdir -p "$(dirname "$AVE")"
  if [ -n "$RAMO" ]; then git clone --branch "$RAMO" "$REPO" "$AVE"; else git clone "$REPO" "$AVE"; fi
fi

say "3/6  dependências (Python, ffmpeg completo, transcrição local)"
uv sync --directory "$AVE" --inexact
PY="$AVE/.venv/bin/python"

say "4/6  Node.js (legendas e gráficos)"
# Em segundo plano: só a Fase 2 usa, e esperar o download dele seguraria o
# resto. Sem `uv run` de propósito — não disputa a trava do ambiente.
"$PY" "$AVE/helpers/instalar_node.py" --fundo || echo "  (não consegui iniciar — a conferência mostra o que falta)"

say "5/6  ffmpeg e modelo de voz"
uv run --directory "$AVE" python helpers/doctor.py --preparar

say "6/6  conferência"
set +e
uv run --directory "$AVE" python helpers/doctor.py
RC=$?
set -e

# O EDITOR APARECE no fim, na tela inicial (solte o vídeo + checklist). Só com
# a Fase 1 de pé: abrir uma ferramenta que não corta seria mostrar um erro.
if [ "$RC" -eq 0 ]; then
  "$PY" "$AVE/helpers/abrir_editor.py" || true
fi

cat <<EOF

Pronto. O editor abriu no navegador: solte um vídeo para começar.
Ou, no seu agente (Claude Code ou Codex), numa pasta com vídeos: "edita esse vídeo".
Tudo sai em <pasta>/edit/. Se o Node.js ainda estiver chegando, a checklist do
editor mostra o progresso — o corte já funciona sem ele.
EOF
exit $RC

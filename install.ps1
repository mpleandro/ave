# Avelin — instalação em um comando (Windows / PowerShell). Sem admin, sem chave.
#   powershell -ExecutionPolicy Bypass -File install.ps1
$ErrorActionPreference = "Stop"
$AVE = if ($env:AVE_DIR) { $env:AVE_DIR } else { "$env:USERPROFILE\.claude\skills\ave" }
$REPO = if ($env:AVE_REPO) { $env:AVE_REPO } else { "https://github.com/mpleandro/ave" }
$RAMO = $env:AVE_RAMO

Write-Host "`n1/6  uv (instalador Python)"
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}
uv --version

Write-Host "`n2/6  Avelin em $AVE"
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
  Write-Host "  git nao encontrado. Instale com:  winget install --id Git.Git -e  (sem admin), abra um PowerShell NOVO e rode este comando de novo."
  exit 1
}
if (Test-Path "$AVE\.git") { git -C $AVE pull --ff-only } else {
  New-Item -ItemType Directory -Force (Split-Path $AVE) | Out-Null
  if ($RAMO) { git clone --branch $RAMO $REPO $AVE } else { git clone $REPO $AVE }
}

Write-Host "`n3/6  dependências (Python, ffmpeg completo, transcrição local)"
uv sync --directory $AVE --inexact
$PY = "$AVE\.venv\Scripts\python.exe"

Write-Host "`n4/6  Node.js (legendas e graficos)"
# Em segundo plano, so se o computador nao tiver um Node 22+ (binario oficial em
# ~\.avelin\node, sem admin). Sem `uv run`: nao disputa a trava do ambiente.
& $PY "$AVE\helpers\instalar_node.py" --fundo

Write-Host "`n5/6  ffmpeg e modelo de voz"
uv run --directory $AVE python helpers/doctor.py --preparar

Write-Host "`n6/6  conferência"
uv run --directory $AVE python helpers/doctor.py
$RC = $LASTEXITCODE
# O editor aparece no fim (tela inicial + checklist), so com a Fase 1 de pe.
if ($RC -eq 0) { & $PY "$AVE\helpers\abrir_editor.py" }
Write-Host "`nPronto. O editor abriu no navegador: solte um video para comecar."
Write-Host "Ou, no seu agente (Claude Code ou Codex), numa pasta com videos: 'edita esse video'."
Write-Host "Se o Node.js ainda estiver chegando, a checklist do editor mostra o progresso."
exit $RC

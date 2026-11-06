# Avelin — instalação em um comando (Windows / PowerShell). Sem admin, sem chave.
#   powershell -ExecutionPolicy Bypass -File install.ps1
$ErrorActionPreference = "Stop"
$AVE = if ($env:AVE_DIR) { $env:AVE_DIR } else { "$env:USERPROFILE\.claude\skills\ave" }
$REPO = if ($env:AVE_REPO) { $env:AVE_REPO } else { "https://github.com/mpleandro/ave" }

Write-Host "`n1/5  uv (instalador Python)"
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}
uv --version

Write-Host "`n2/5  Avelin em $AVE"
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
  Write-Host "  git nao encontrado. Instale com:  winget install --id Git.Git -e  (sem admin), abra um PowerShell NOVO e rode este comando de novo."
  exit 1
}
if (Test-Path "$AVE\.git") { git -C $AVE pull --ff-only } else {
  New-Item -ItemType Directory -Force (Split-Path $AVE) | Out-Null
  git clone $REPO $AVE
}

Write-Host "`n3/5  dependências (Python, ffmpeg completo, transcrição local)"
uv sync --directory $AVE --inexact

Write-Host "`n4/5  ffmpeg e modelo de voz"
uv run --directory $AVE python helpers/doctor.py --preparar

Write-Host "`n5/5  conferência"
uv run --directory $AVE python helpers/doctor.py
Write-Host "`nPronto. Entre na pasta com o vídeo, abra o seu agente (ex.: claude) e diga 'edita esse vídeo'."

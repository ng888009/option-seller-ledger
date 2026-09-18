param(
  [switch]$Clean
)

$ErrorActionPreference = "Stop"
$project = Split-Path -Parent $PSScriptRoot
Set-Location $project
$env:appdata = Join-Path $env:TEMP "option-ledger-pyinstaller"
New-Item -ItemType Directory -Force -Path $env:appdata | Out-Null

if ($Clean) {
  Remove-Item -Recurse -Force -ErrorAction SilentlyContinue .\release-build, .\release-dist
}

if (-not (Test-Path ".\dist\client\index.html")) {
  npm.cmd run build
}
& .\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onedir --windowed `
  --name "option_seller_ledger" `
  --add-data "dist\client;ui" `
  --collect-all futu `
  --hidden-import futu `
  --distpath .\release-dist `
  --workpath .\release-build `
  desktop_entry.py

& .\.venv\Scripts\python.exe .\scripts\rename_release.py

Write-Host "Release created successfully."

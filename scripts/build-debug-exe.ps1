$ErrorActionPreference = "Stop"
$project = Split-Path -Parent $PSScriptRoot
Set-Location $project
$env:appdata = Join-Path $env:TEMP "option-ledger-pyinstaller"
New-Item -ItemType Directory -Force -Path $env:appdata | Out-Null
& .\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onedir --console `
  --name "option-ledger-debug" `
  --add-data "dist\client;ui" `
  --collect-all futu `
  --hidden-import futu `
  --distpath .\debug-dist `
  --workpath .\debug-build `
  desktop_entry.py

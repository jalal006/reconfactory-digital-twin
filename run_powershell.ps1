$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    python -m venv .venv
}

.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:RECONFACTORY_PUBLIC_URL = "http://127.0.0.1:8000"
Write-Host "Open $env:RECONFACTORY_PUBLIC_URL"
.\.venv\Scripts\python.exe scripts\run_factory.py --host 127.0.0.1 --port 8000

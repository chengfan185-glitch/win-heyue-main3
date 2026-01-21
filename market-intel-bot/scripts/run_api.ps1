# Run Market-Intel API (TopN feed) on Windows PowerShell
# Usage:
#   .\.venv\Scripts\Activate.ps1
#   .\scripts\run_api.ps1

$ErrorActionPreference = "Stop"

if (Test-Path .env) {
  Write-Host "Loading .env ..."
  Get-Content .env | ForEach-Object {
    if ($_ -match '^\s*#' -or $_ -match '^\s*$') { return }
    $kv = $_ -split '=',2
    if ($kv.Length -eq 2) {
      [System.Environment]::SetEnvironmentVariable($kv[0].Trim(), $kv[1].Trim(), 'Process')
    }
  }
}

python -m src.api_server

param(
  [string]$TargetBase = "http://10.131.12.157:50001",
  [int]$ListenPort = 55001
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$scriptPath = Join-Path $repoRoot "scripts\\windows_openai_forward.py"

if (-not (Test-Path $scriptPath)) {
  throw "Not found: $scriptPath"
}

Write-Host "Starting forwarder on 0.0.0.0:$ListenPort -> $TargetBase"

# Start detached so it keeps running.
$p = Start-Process -FilePath "py" -ArgumentList @(
  $scriptPath,
  "--listen-host","0.0.0.0",
  "--listen-port","$ListenPort",
  "--target-base",$TargetBase
) -PassThru -WindowStyle Hidden

Start-Sleep -Milliseconds 400

$listening = Get-NetTCPConnection -LocalPort $ListenPort -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $listening) {
  try { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue } catch {}
  throw "Forwarder did not start listening on port $ListenPort"
}

Write-Host "OK. PID=$($p.Id) Listening=$($listening.LocalAddress):$($listening.LocalPort)"
Write-Host ""
Write-Host "WSL should use: http://127.0.0.1:$ListenPort/v1"


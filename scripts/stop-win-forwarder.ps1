param(
  [int]$ListenPort = 55001
)

$ErrorActionPreference = "Stop"

$conn = Get-NetTCPConnection -LocalPort $ListenPort -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $conn) {
  Write-Host "No process is listening on port $ListenPort"
  exit 0
}

$pid = $conn.OwningProcess
Write-Host "Stopping PID=$pid on port $ListenPort"
Stop-Process -Id $pid -Force
Write-Host "Stopped."


#Requires -Version 5.1
<#
.SYNOPSIS
  Run OpenAI-compatible forwarder on Windows so WSL can reach an intranet model (10.x) via localhost.

.DESCRIPTION
  - Optional: inbound Windows Firewall rule for the listen port (needs Administrator).
  - Adds a shortcut under the current user's Startup folder so the forwarder runs at logon.
  - Can start the forwarder immediately.

  After setup, point DeerFlow config.yaml base_url to: http://127.0.0.1:<ListenPort>/v1

.PARAMETER ListenPort
  Default 55001 (matches config.yaml / start-win-forwarder.ps1).

.PARAMETER TargetBase
  Upstream API root without trailing path quirks, e.g. http://10.131.12.157:50001

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File .\scripts\setup-windows-model-forwarder.ps1 -RunNow

.EXAMPLE
  # Firewall rule (run PowerShell as Administrator):
  powershell -ExecutionPolicy Bypass -File .\scripts\setup-windows-model-forwarder.ps1 -RunNow
#>
param(
  [int]$ListenPort = 55001,
  [string]$TargetBase = "http://10.131.12.157:50001",
  [switch]$SkipFirewall,
  [switch]$SkipSchedule,
  [switch]$RunNow
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$starter = Join-Path $PSScriptRoot "start-win-forwarder.ps1"
if (-not (Test-Path $starter)) { throw "Missing: $starter" }

function Test-IsAdministrator {
  $id = [Security.Principal.WindowsIdentity]::GetCurrent()
  $p = New-Object Security.Principal.WindowsPrincipal($id)
  return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

# --- Firewall (optional; WSL -> Windows localhost often still needs inbound allow for 0.0.0.0 bind) ---
if (-not $SkipFirewall) {
  $ruleName = "DeerFlow model forwarder TCP $ListenPort"
  $existing = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
  if ($existing) {
    Write-Host "Firewall rule already exists: $ruleName"
  }
  elseif (Test-IsAdministrator) {
    New-NetFirewallRule -DisplayName $ruleName -Group "DeerFlow" `
      -Direction Inbound -Action Allow -Protocol TCP -LocalPort $ListenPort | Out-Null
    Write-Host "Created firewall rule: $ruleName"
  }
  else {
    Write-Warning @"
No administrator rights: skipped firewall rule. If WSL cannot connect to 127.0.0.1:$ListenPort,
open PowerShell as Administrator and run:
  New-NetFirewallRule -DisplayName '$ruleName' -Direction Inbound -Action Allow -Protocol TCP -LocalPort $ListenPort
"@
  }
}

# --- Startup folder shortcut (reliable; no admin; user can remove in shell:startup) ---
if (-not $SkipSchedule) {
  $startup = [Environment]::GetFolderPath("Startup")
  $lnkPath = Join-Path $startup "DeerFlow Model Forwarder.lnk"
  $arg = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$starter`" -TargetBase `"$TargetBase`" -ListenPort $ListenPort"
  $w = New-Object -ComObject WScript.Shell
  $sc = $w.CreateShortcut($lnkPath)
  $sc.TargetPath = "powershell.exe"
  $sc.Arguments = $arg
  $sc.WorkingDirectory = $repoRoot
  $sc.WindowStyle = 7
  $sc.Description = "Forward OpenAI-compatible API to intranet model for WSL (DeerFlow)"
  $sc.Save()
  Write-Host "Created startup shortcut: $lnkPath"
}

if ($RunNow) {
  Write-Host "Starting forwarder now..."
  & $starter -TargetBase $TargetBase -ListenPort $ListenPort
} else {
  Write-Host @"

Next steps:
  1) Start forwarder once (or sign out/in — Startup folder runs it automatically):
       powershell -ExecutionPolicy Bypass -File `"$starter`"
  2) In WSL: curl -sS http://127.0.0.1:$ListenPort/v1/models -H "Authorization: Bearer qwen35-demo-key"
  3) DeerFlow config.yaml base_url: http://127.0.0.1:$ListenPort/v1

If curl from WSL still fails, run this script from an elevated PowerShell for the firewall rule.
"@
}

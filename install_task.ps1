# Registers (or updates) the daily Windows Task Scheduler job for the
# Static Korea Index Tracker. Runs ~13:00 IST, after the 15:30 KST KRX close.
#
# Usage (normal PowerShell, no admin needed for a user task):
#   powershell -ExecutionPolicy Bypass -File .\install_task.ps1
#   powershell -ExecutionPolicy Bypass -File .\install_task.ps1 -Time "13:00" -Remove:$false

param(
  [string]$Time = "13:00",          # local (IST) trigger time
  [string]$TaskName = "KoreaIndexTracker",
  [switch]$Remove                    # pass -Remove to delete the task
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$bat  = Join-Path $here "run_daily.bat"

if ($Remove) {
  Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
  Write-Host "Removed scheduled task '$TaskName'."
  return
}

if (-not (Test-Path $bat)) { throw "run_daily.bat not found at $bat" }

$action  = New-ScheduledTaskAction -Execute $bat -WorkingDirectory $here
$trigger = New-ScheduledTaskTrigger -Daily -At $Time
# Run whether logged in or not is overkill; default runs as current user when logged on.
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
  -DontStopOnIdleEnd -ExecutionTimeLimit (New-TimeSpan -Hours 1)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
  -Settings $settings -Description "Daily KOSPI/KOSDAQ index constituent fetch (Naver)" -Force | Out-Null

Write-Host "Installed scheduled task '$TaskName' - daily at $Time (IST)."
Write-Host "Verify:  Get-ScheduledTask -TaskName $TaskName"
Write-Host "Run now: Start-ScheduledTask -TaskName $TaskName"

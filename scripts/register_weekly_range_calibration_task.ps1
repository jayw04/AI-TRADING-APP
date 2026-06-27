<#
.SYNOPSIS
  Register (or refresh) the "TradingWorkbench RangeCalibration Weekly" scheduled task.

.DESCRIPTION
  Creates a Windows Task Scheduler job that runs scripts/weekly_range_calibration_refresh.ps1
  every Friday at 16:30 local time (America/Chicago) -- after the trading week closes, and a day
  off the Saturday live-evidence task so the two never race on git. Runs in the current user's
  interactive context (inherits gh auth + git creds) and catches a missed run (StartWhenAvailable).
  Re-running this script re-registers the task idempotently.

  Until the daily auto-select has produced selections (first fire Mon 2026-06-29), the runner
  exits doing no git/PR -- so this can be registered now and stays silent until there is data.

  Run once, from any shell, on the host:
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts/register_weekly_range_calibration_task.ps1
#>

$ErrorActionPreference = 'Stop'

$TaskName = 'TradingWorkbench RangeCalibration Weekly'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Runner   = Join-Path $RepoRoot 'scripts\weekly_range_calibration_refresh.ps1'

if (-not (Test-Path $Runner)) { throw "runner not found at $Runner" }

$Action = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Runner`"" `
    -WorkingDirectory $RepoRoot

$Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Friday -At 4:30pm

$Principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive
$Settings  = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger `
    -Principal $Principal -Settings $Settings `
    -Description 'Weekly Range auto-select calibration report refresh -> docs-only PR (scripts/weekly_range_calibration_refresh.ps1). Skips silently until selections accrue.' `
    -Force | Out-Null

Write-Host "Registered '$TaskName': Fridays 16:30 local."
Get-ScheduledTask -TaskName $TaskName | Get-ScheduledTaskInfo | Format-List TaskName, NextRunTime, LastRunTime, LastTaskResult

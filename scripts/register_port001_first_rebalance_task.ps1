<#
.SYNOPSIS
  Register the one-shot "TradingWorkbench PORT001 FirstRebalance" scheduled task.

.DESCRIPTION
  Creates a Windows Task Scheduler job that runs scripts/port001_first_rebalance_check.ps1 ONCE,
  ~47 minutes after the Combined Book's first live paper rebalance (the strategy cron fires
  Mon 2026-06-29 14:00 UTC). The trigger is anchored to a UTC instant and converted to host
  local time, so it is correct regardless of the host timezone.

  This is the durability backstop for the in-session Claude post-rebalance task: it captures the
  first-rebalance evidence even if no Claude session is running on Monday. StartWhenAvailable
  catches a missed run (e.g. machine asleep at the fire time). The check is READ-ONLY.

  Run once, from any shell, on the host:
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts/register_port001_first_rebalance_task.ps1

  Remove it after the check has run (it is one-shot but Windows keeps the definition):
    Unregister-ScheduledTask -TaskName 'TradingWorkbench PORT001 FirstRebalance' -Confirm:$false
#>

$ErrorActionPreference = 'Stop'

$TaskName = 'TradingWorkbench PORT001 FirstRebalance'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Runner   = Join-Path $RepoRoot 'scripts\port001_first_rebalance_check.ps1'
if (-not (Test-Path $Runner)) { throw "runner not found at $Runner" }

# 14:47 UTC Mon 2026-06-29 (rebalance is 14:00 UTC) -> host local time.
$At = (Get-Date '2026-06-29T14:47:00Z').ToLocalTime()

$Action = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Runner`"" `
    -WorkingDirectory $RepoRoot

$Trigger = New-ScheduledTaskTrigger -Once -At $At

$Principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive
$Settings  = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 15) -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger `
    -Principal $Principal -Settings $Settings `
    -Description 'One-shot: capture the PORT-001 Combined Book first live paper rebalance evidence (read-only) ~47m after the Mon 2026-06-29 14:00 UTC rebalance. Backstop for the in-session Claude check.' `
    -Force | Out-Null

Write-Host "Registered one-shot '$TaskName' for $($At.ToString('yyyy-MM-dd HH:mm')) local."
Get-ScheduledTask -TaskName $TaskName | Get-ScheduledTaskInfo | Format-List TaskName, NextRunTime, LastRunTime, LastTaskResult

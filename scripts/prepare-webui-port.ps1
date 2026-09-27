param(
    [int]$Port = 8188,
    # Skip the confirmation prompt; still refuses to stop anything that is not this WebUI.
    [switch]$Restart
)

# Exit codes: 0 = port free, 1 = error / refused, 3 = user kept the running WebUI.
$ErrorActionPreference = "Stop"
$listenerPattern = "^\s*TCP\s+\S+:$Port\s+\S+\s+LISTENING\s+(\d+)\s*$"

function Get-PortOwners {
    @(netstat -ano -p tcp | Select-String $listenerPattern |
        ForEach-Object { [int]$_.Matches[0].Groups[1].Value } | Sort-Object -Unique)
}

try {
    $ownerPids = Get-PortOwners
    if ($ownerPids.Count -eq 0) {
        Write-Host "  Port $Port is free."
        exit 0
    }

    foreach ($ownerPid in $ownerPids) {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId = $ownerPid"
        $commandLine = if ($process) { [string]$process.CommandLine } else { "" }
        Write-Host "  PID ${ownerPid}: $(if ($process) { $process.Name } else { '(unknown)' })"
        Write-Host "    $commandLine"
        if ($commandLine -notmatch 'webui[\\/]server\.py') {
            Write-Host "  Port $Port is used by another program. It was NOT stopped."
            Write-Host "  Close it yourself, or start the WebUI on another port: py webui\server.py --port <n>"
            exit 1
        }
    }

    try {
        $status = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/status" -TimeoutSec 3
        if ($status.generation_in_progress) {
            Write-Host "  WARNING: the running WebUI is generating right now. Restarting cancels that job."
        }
    } catch {
        Write-Host "  (The running WebUI did not answer /api/status.)"
    }

    if (-not $Restart) {
        $answer = Read-Host "  A kimodo-motion WebUI is already running. Restart it? [y/N]"
        if ($answer -notmatch '^(y|yes)$') {
            Write-Host "  Keeping the running WebUI."
            exit 3
        }
    }

    foreach ($ownerPid in $ownerPids) {
        # /T also reaps the inference worker and pose-agent children the server owns.
        Write-Host "  Stopping WebUI PID $ownerPid and its child processes..."
        & taskkill.exe /PID $ownerPid /T /F | Out-Host
    }

    for ($i = 0; $i -lt 20 -and (Get-PortOwners).Count -gt 0; $i++) {
        Start-Sleep -Milliseconds 250
    }
    if ((Get-PortOwners).Count -gt 0) {
        throw "Port $Port was not released."
    }
    exit 0
} catch {
    Write-Error $_
    exit 1
}

param(
    [int]$Port = 8188
)

$ErrorActionPreference = "Stop"
$listenerPattern = "^\s*TCP\s+\S+:$Port\s+\S+\s+LISTENING\s+(\d+)\s*$"

try {
    $listeners = @(netstat -ano -p tcp | Select-String $listenerPattern)
    $ownerPids = @(
        $listeners |
            ForEach-Object { [int]$_.Matches[0].Groups[1].Value } |
            Sort-Object -Unique
    )

    foreach ($ownerPid in $ownerPids) {
        Write-Host "  PID ${ownerPid}: 포트 $Port 점유 프로세스를 종료합니다."
        Stop-Process -Id $ownerPid -Force
    }

    if ($ownerPids.Count -gt 0) {
        Start-Sleep -Milliseconds 500
    }

    $remaining = @(netstat -ano -p tcp | Select-String $listenerPattern)
    if ($remaining.Count -gt 0) {
        throw "포트 $Port 이(가) 해제되지 않았습니다."
    }
} catch {
    Write-Error $_
    exit 1
}


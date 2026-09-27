param(
    [switch]$CheckLauncher
)

$ErrorActionPreference = "Stop"
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
Set-Location -LiteralPath $repoRoot

Write-Host "============================================"
Write-Host "  kimodo-motion - local WebUI launcher"
Write-Host "============================================"
Write-Host

$python = & (Join-Path $PSScriptRoot "find-python.ps1") -RepoRoot $repoRoot
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($python)) {
    Write-Error @"
Python was not found.
Set runtime.python_executable in webui\config.json, or provide one of:
  runtime\python\python.exe
  .venv\Scripts\python.exe
"@
    exit 1
}
$python = [string]($python | Select-Object -Last 1)
Write-Host "Python: $python"
Write-Host

if ($CheckLauncher) {
    Write-Host "Launcher check: OK"
    exit 0
}

# Preflight first: a failing check must not cost the user a server that is still working.
Write-Host "[1/3] Running preflight checks..."
& $python "webui\server.py" --check
if ($LASTEXITCODE -ne 0) {
    throw "WebUI preflight failed. Nothing was stopped or started."
}

Write-Host
Write-Host "[2/3] Checking port 8188..."
& (Join-Path $PSScriptRoot "prepare-webui-port.ps1") -Port 8188
if ($LASTEXITCODE -eq 3) {
    Start-Process "http://127.0.0.1:8188/"
    Write-Host "Opened the running WebUI in the browser."
    exit 0
}
if ($LASTEXITCODE -ne 0) {
    throw "Port 8188 is not available. The new server was not started."
}

Write-Host
Write-Host "[3/3] Starting the WebUI in a visible console..."
$serverCommand = 'title kimodo-motion webui && "{0}" webui\server.py' -f $python
Start-Process -FilePath $env:ComSpec -ArgumentList @("/k", $serverCommand) -WorkingDirectory $repoRoot
Start-Sleep -Seconds 2
Start-Process "http://127.0.0.1:8188/"
Write-Host "Browser opened. Close the 'kimodo-motion webui' console to stop the server."

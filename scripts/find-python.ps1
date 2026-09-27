param(
    [Parameter(Mandatory = $true)]
    [string]$RepoRoot
)

$ErrorActionPreference = "SilentlyContinue"
$repoPath = [System.IO.Path]::GetFullPath($RepoRoot)
$candidates = [System.Collections.Generic.List[string]]::new()

function Add-PythonCandidate([string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path)) {
        return
    }
    $expanded = [Environment]::ExpandEnvironmentVariables($Path)
    if (-not [System.IO.Path]::IsPathRooted($expanded)) {
        $expanded = Join-Path $repoPath $expanded
    }
    $candidates.Add([System.IO.Path]::GetFullPath($expanded))
}

$configPath = Join-Path $repoPath "webui\config.json"
if (Test-Path -LiteralPath $configPath) {
    try {
        $config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
        Add-PythonCandidate $config.runtime.python_executable
    } catch {
        # server.py reports malformed application configuration separately.
    }
}

Add-PythonCandidate (Join-Path $repoPath "runtime\python\python.exe")
Add-PythonCandidate (Join-Path $repoPath ".venv\Scripts\python.exe")

foreach ($root in @(
    (Join-Path $env:LocalAppData "Programs\Python"),
    (Join-Path $env:ProgramFiles "Python"),
    (Join-Path ${env:ProgramFiles(x86)} "Python")
)) {
    if (Test-Path -LiteralPath $root) {
        Get-ChildItem -LiteralPath $root -Directory -Filter "Python*" |
            Sort-Object Name -Descending |
            ForEach-Object { Add-PythonCandidate (Join-Path $_.FullName "python.exe") }
    }
}

$pathPython = Get-Command python.exe -CommandType Application | Select-Object -First 1
if ($null -ne $pathPython) {
    Add-PythonCandidate $pathPython.Source
}

$launcher = Get-Command py.exe -CommandType Application | Select-Object -First 1
if ($null -ne $launcher) {
    $resolved = & $launcher.Source -c "import sys; print(sys.executable)" 2>$null
    if ($LASTEXITCODE -eq 0 -and $resolved) {
        Add-PythonCandidate ($resolved | Select-Object -Last 1)
    }
}

foreach ($candidate in $candidates | Select-Object -Unique) {
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
        continue
    }
    $resolved = & $candidate -c "import sys; print(sys.executable)" 2>$null
    if ($LASTEXITCODE -eq 0 -and $resolved) {
        Write-Output ([System.IO.Path]::GetFullPath(($resolved | Select-Object -Last 1)))
        exit 0
    }
}

exit 1


param(
    # Fetch and report what upstream/main would bring into motion/main. Changes nothing.
    [switch]$DryRun,
    # CMake build tree for the submodule. Default: vendor\kimodo.cpp\build
    [string]$BuildDir = "",
    # Extra ctest arguments (e.g. -E <regex>). Use only once the test baseline is known.
    [string[]]$CtestArgs = @()
)

# Follow the original kimodo.cpp (localai-org, remote "upstream") into the fork's
# integration branch motion/main, then re-pin the submodule in the root repo.
# Enforces README "kimodo.cpp fork and submodule" in order, and refuses instead of guessing:
#   1. fetch upstream -> checkout motion/main -> merge upstream/main   (merge, never rebase)
#   2. build + ctest                                                     (stop on failure)
#   3. git push origin motion/main
#   4. check the new commit is on origin/motion/main and descends from the current pin
#   5. commit the new submodule pointer in the root repo                 (root push is left to you)
# Merge conflicts are never resolved here - they are handed to a human.
# Re-running after a stop resumes: an unpushed merge or an uncommitted pointer is picked up.
#
# Exit codes: 0 = done or already up to date, 1 = error, 2 = refused (precondition),
#             3 = merge conflict or merge in progress (resolve, commit, re-run),
#             4 = build or tests failed (nothing was pushed)

$ErrorActionPreference = "Continue"   # native stderr (git progress) must not become a terminating error
$SubPath = "vendor/kimodo.cpp"
$UpstreamUrl = "https://github.com/localai-org/kimodo.cpp.git"
$Branch = "motion/main"

$root = (& git -C (Join-Path $PSScriptRoot "..") rev-parse --show-toplevel 2>$null)
if (-not $root) { Write-Host "Not inside the repository."; exit 1 }
$root = $root.Trim()
$sub = Join-Path $root $SubPath
if (-not $BuildDir) { $BuildDir = Join-Path $sub "build" }

$logDir = Join-Path $root "logs\follow-upstream"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = Join-Path $logDir ((Get-Date -Format "yyyyMMdd-HHmmss") + ".log")

function Write-Log([string]$Message) {
    $line = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $Message
    Write-Host $line
    Add-Content -Path $logFile -Value $line -Encoding UTF8
}

function Stop-With([int]$Code, [string]$Message) {
    Write-Log $Message
    Write-Log "exit $Code - log: $logFile"
    exit $Code
}

# Runs a native command, streams its output into the log, returns the exit code.
function Invoke-Logged([string]$Exe, [string[]]$Arguments) {
    Write-Log ("  > {0} {1}" -f $Exe, ($Arguments -join " "))
    & $Exe @Arguments 2>&1 | ForEach-Object { Write-Log ("    " + $_) }
    return $LASTEXITCODE
}

# Runs git quietly and returns trimmed stdout ($null on failure).
function Get-Git([string]$Dir, [string[]]$Arguments) {
    $out = & git -C $Dir @Arguments 2>$null
    if ($LASTEXITCODE -ne 0) { return $null }
    return (($out | Out-String).Trim())
}

function Test-Ancestor([string]$Dir, [string]$Older, [string]$Newer) {
    & git -C $Dir merge-base --is-ancestor $Older $Newer 2>$null
    return ($LASTEXITCODE -eq 0)
}

function Short([string]$Sha) { if ($Sha) { return $Sha.Substring(0, [Math]::Min(7, $Sha.Length)) } return "?" }

Write-Log "follow-upstream start - root $root - DryRun=$DryRun"

# ---- preconditions -------------------------------------------------------------------------
if (-not (Test-Path (Join-Path $sub ".git"))) {
    Stop-With 2 "Submodule $SubPath is not initialized. Run: git submodule update --init --recursive"
}
$oldPin = Get-Git $root @("rev-parse", "HEAD:$SubPath")
if (-not $oldPin) { Stop-With 1 "Cannot read the pinned submodule commit from the root HEAD." }
Write-Log "current pin $(Short $oldPin)"

$rootDirty = @(& git -C $root status --porcelain=v1 2>$null | Where-Object { $_ -and ($_.Substring(3) -ne $SubPath) })
if ($rootDirty.Count -gt 0) {
    Stop-With 2 ("Root working tree has other changes - commit or stash them first:`n  " + ($rootDirty -join "`n  "))
}

# A submodule's git dir is absolute (.git/modules/...), so ask git instead of building the path.
if (Get-Git $sub @("rev-parse", "-q", "--verify", "MERGE_HEAD")) {
    $conflicts = @(& git -C $sub diff --name-only --diff-filter=U 2>$null)
    Stop-With 3 ("A merge is in progress in $SubPath. Resolve it and commit, then re-run.`n  unresolved: " + ($conflicts -join ", "))
}
$subDirty = @(& git -C $sub status --porcelain=v1 --untracked-files=no 2>$null | Where-Object { $_ })
if ($subDirty.Count -gt 0) {
    Stop-With 2 ("$SubPath has uncommitted changes:`n  " + ($subDirty -join "`n  "))
}

$running = @(Get-Process -Name "kmd-generate" -ErrorAction SilentlyContinue)
if ($running.Count -gt 0 -and -not $DryRun) {
    # Building replaces kmd-generate.exe. Never stop a user process - ask the user to finish it.
    Stop-With 2 ("kmd-generate is running (PID " + (($running | ForEach-Object { $_.Id }) -join ", ") + "). Let it finish or stop it yourself, then re-run.")
}

$remotes = @(& git -C $sub remote 2>$null)
if ($remotes -notcontains "upstream") {
    Write-Log "adding remote upstream -> $UpstreamUrl (README: one-time step)"
    if ((Invoke-Logged "git" @("-C", $sub, "remote", "add", "upstream", $UpstreamUrl)) -ne 0) { Stop-With 1 "Could not add remote upstream." }
}

# ---- step 1: fetch, checkout motion/main, merge upstream/main ---------------------------------
Write-Log "[1/5] fetch upstream + origin"
if ((Invoke-Logged "git" @("-C", $sub, "fetch", "upstream")) -ne 0) { Stop-With 1 "git fetch upstream failed." }
if ((Invoke-Logged "git" @("-C", $sub, "fetch", "origin")) -ne 0) { Stop-With 1 "git fetch origin failed." }

$upstream = Get-Git $sub @("rev-parse", "upstream/main")
$originTip = Get-Git $sub @("rev-parse", "origin/$Branch")
if (-not $upstream -or -not $originTip) { Stop-With 1 "upstream/main or origin/$Branch is missing after fetch." }
Write-Log "upstream/main $(Short $upstream) - origin/$Branch $(Short $originTip)"

if ($DryRun) {
    $base = Get-Git $sub @("rev-parse", "--verify", "-q", "refs/heads/$Branch")
    if (-not $base) { $base = $originTip }
    $incoming = Get-Git $sub @("log", "--oneline", "$base..$upstream")
    if (-not $incoming) { Stop-With 0 "Dry run: $Branch already contains upstream/main - nothing to merge." }
    Write-Log "Dry run: upstream/main would bring these commits into $Branch ($(Short $base)):"
    $incoming -split "`n" | ForEach-Object { Write-Log "  $_" }
    Write-Log ("  " + (Get-Git $sub @("diff", "--shortstat", "$base...$upstream")))
    Stop-With 0 "Dry run: nothing was changed."
}

$current = Get-Git $sub @("symbolic-ref", "-q", "--short", "HEAD")
if ($current -and $current -ne $Branch) {
    Stop-With 2 "$SubPath is on branch '$current', not $Branch. Finish or park that work first - this script will not switch away from it."
}
if (-not $current) {
    # Detached (normal after 'git submodule update'): only move onto motion/main from a clean tree.
    if (Get-Git $sub @("rev-parse", "--verify", "-q", "refs/heads/$Branch")) {
        $rc = Invoke-Logged "git" @("-C", $sub, "checkout", $Branch)
    } else {
        $rc = Invoke-Logged "git" @("-C", $sub, "checkout", "-b", $Branch, "--track", "origin/$Branch")
    }
    if ($rc -ne 0) { Stop-With 1 "Could not check out $Branch." }
}

$local = Get-Git $sub @("rev-parse", "HEAD")
if ($local -ne $originTip) {
    if (Test-Ancestor $sub $local $originTip) {
        Write-Log "local $Branch is behind origin - fast-forwarding"
        if ((Invoke-Logged "git" @("-C", $sub, "merge", "--ff-only", "origin/$Branch")) -ne 0) { Stop-With 1 "Fast-forward failed." }
        $local = Get-Git $sub @("rev-parse", "HEAD")
    } elseif (Test-Ancestor $sub $originTip $local) {
        Write-Log "local $Branch is ahead of origin (unpushed work) - resuming:"
        (Get-Git $sub @("log", "--oneline", "origin/$Branch..HEAD")) -split "`n" | ForEach-Object { Write-Log "  $_" }
    } else {
        Stop-With 2 "Local $Branch and origin/$Branch have diverged. A human decides how to reconcile them."
    }
}
if (-not (Test-Ancestor $sub $oldPin $local)) {
    Stop-With 2 "The current pin $(Short $oldPin) is not an ancestor of $Branch $(Short $local). Refusing to move the pointer sideways."
}

if (Test-Ancestor $sub $upstream $local) {
    Write-Log "$Branch already contains upstream/main"
} else {
    Write-Log ("merging upstream/main: " + (Get-Git $sub @("rev-list", "--count", "HEAD..$upstream")) + " new commit(s)")
    if ((Invoke-Logged "git" @("-C", $sub, "merge", "--no-edit", "upstream/main")) -ne 0) {
        $conflicts = @(& git -C $sub diff --name-only --diff-filter=U 2>$null)
        Stop-With 3 ("Merge conflict - left for a human to resolve (not aborted, not auto-resolved).`n  files: " + ($conflicts -join ", ") + "`n  Resolve, 'git -C $SubPath commit', then re-run. To give up: git -C $SubPath merge --abort")
    }
    $local = Get-Git $sub @("rev-parse", "HEAD")
}

if ($local -eq $oldPin) { Stop-With 0 "Already up to date - $Branch = pin $(Short $oldPin). Nothing to do." }

# ---- step 2: build + ctest ------------------------------------------------------------------
Write-Log "[2/5] build + ctest ($BuildDir)"
if ((Invoke-Logged "cmake" @("-S", $sub, "-B", $BuildDir, "-G", "Visual Studio 17 2022", "-A", "x64", "-DKIMODO_BUILD_TESTS=ON", "-DKIMODO_ENABLE_VULKAN=ON")) -ne 0) {
    Stop-With 4 "CMake configure failed. Nothing was pushed."
}
if ((Invoke-Logged "cmake" @("--build", $BuildDir, "--config", "Release")) -ne 0) {
    Stop-With 4 "Build failed. Nothing was pushed. The merge stays local: git -C $SubPath log origin/$Branch..HEAD"
}
$listed = (& ctest --test-dir $BuildDir -C Release -N @CtestArgs 2>&1 | Out-String)
if ($listed -match "Total Tests:\s*0\b" -or $listed -notmatch "Total Tests:") {
    Stop-With 4 "ctest found no tests - a run with zero tests is not a pass. Check KIMODO_BUILD_TESTS."
}
if ((Invoke-Logged "ctest" (@("--test-dir", $BuildDir, "-C", "Release", "--output-on-failure") + $CtestArgs)) -ne 0) {
    Stop-With 4 "Tests failed. Nothing was pushed. The merge stays local: git -C $SubPath log origin/$Branch..HEAD"
}

# ---- step 3: push the fork branch ------------------------------------------------------------
Write-Log "[3/5] push origin $Branch"
if ((Invoke-Logged "git" @("-C", $sub, "push", "origin", $Branch)) -ne 0) { Stop-With 1 "git push origin $Branch failed." }
if ((Invoke-Logged "git" @("-C", $sub, "fetch", "origin")) -ne 0) { Stop-With 1 "git fetch origin failed after push." }

# ---- step 4: check before re-pinning -----------------------------------------------------------
Write-Log "[4/5] check $(Short $local) before re-pinning"
$containing = @(& git -C $sub branch -r --contains $local 2>$null | ForEach-Object { $_.Trim() })
if ($containing -notcontains "origin/$Branch") {
    Stop-With 2 "$(Short $local) is not on origin/$Branch. Refusing to pin a commit others cannot fetch."
}
if (-not (Test-Ancestor $sub $oldPin $local)) {
    Stop-With 2 "$(Short $local) does not descend from the current pin $(Short $oldPin). Refusing."
}
Write-Log "  on origin/${Branch}: yes - descends from $(Short $oldPin): yes"

# ---- step 5: root pointer commit ------------------------------------------------------------
Write-Log "[5/5] commit the submodule pointer in the root"
if ((Invoke-Logged "git" @("-C", $root, "add", $SubPath)) -ne 0) { Stop-With 1 "git add $SubPath failed." }
$staged = @(& git -C $root diff --cached --name-only 2>$null | Where-Object { $_ })
if ($staged.Count -ne 1 -or $staged[0] -ne $SubPath) {
    Stop-With 2 ("Refusing: the root commit would contain more than the pointer: " + ($staged -join ", "))
}
$msgFile = Join-Path $logDir "commit-msg.txt"
$message = "vendor: follow kimodo.cpp upstream $(Short $oldPin) -> $(Short $local) (upstream/main $(Short $upstream))"
[IO.File]::WriteAllText($msgFile, $message + "`n", (New-Object Text.UTF8Encoding $false))
if ((Invoke-Logged "git" @("-C", $root, "commit", "-F", $msgFile)) -ne 0) { Stop-With 1 "Root commit failed." }
Remove-Item $msgFile -ErrorAction SilentlyContinue

Write-Log ("root commit " + (Get-Git $root @("log", "--oneline", "-1")))
Stop-With 0 "Done. Review, then push the root yourself: git push origin main"

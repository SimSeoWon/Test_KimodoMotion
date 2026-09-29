# Scenario test for scripts/follow-upstream.ps1 - real git, shimmed cmake/ctest.
# Builds a throwaway sandbox under %TEMP% (upstream bare, fork bare, root with the submodule),
# never touches this repository or its submodule.
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\follow_upstream_test.ps1
# Exit code: number of failed checks.

$ErrorActionPreference = "Continue"
$script = (Resolve-Path (Join-Path $PSScriptRoot "..\follow-upstream.ps1")).Path
$T = Join-Path $env:TEMP ("fu-test-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
New-Item -ItemType Directory -Path $T | Out-Null
$env:GIT_AUTHOR_NAME = "t"; $env:GIT_AUTHOR_EMAIL = "t@t"
$env:GIT_COMMITTER_NAME = "t"; $env:GIT_COMMITTER_EMAIL = "t@t"
$script:fail = 0; $script:pass = 0

# No declared parameters: a declared -Dir would swallow git flags like -D by prefix match.
function G { $d = $args[0]; $rest = @($args | Select-Object -Skip 1); & git -C $d @rest 2>&1 | Out-Null; if ($LASTEXITCODE -ne 0) { throw "git failed in ${d}: $rest" } }
function Out-G { $d = $args[0]; $rest = @($args | Select-Object -Skip 1); return ((& git -C $d @rest 2>$null) | Out-String).Trim() }
function Check([string]$Name, [bool]$Cond, [string]$Detail = "") {
    if ($Cond) { $script:pass++; Write-Host "  ok   $Name" }
    else { $script:fail++; Write-Host "  FAIL $Name $Detail" }
}
function Run([string[]]$Extra = @()) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $R "scripts\follow-upstream.ps1") @Extra *> (Join-Path $T "last-run.txt")
    return $LASTEXITCODE
}
function Commit-File([string]$Dir, [string]$File, [string]$Text, [string]$Msg) {
    Set-Content -Path (Join-Path $Dir $File) -Value $Text -Encoding ASCII
    G $Dir add $File; G $Dir commit -q -m $Msg
}

# shims: cmake always succeeds unless FU_BUILD_FAIL=1; ctest reports FU_TESTS tests, fails if FU_TEST_FAIL=1
$shim = Join-Path $T "shim"; New-Item -ItemType Directory -Path $shim | Out-Null
Set-Content (Join-Path $shim "cmake.cmd") "@echo off`r`nif ""%FU_BUILD_FAIL%""==""1"" exit /b 1`r`nexit /b 0" -Encoding ASCII
Set-Content (Join-Path $shim "ctest.cmd") "@echo off`r`necho %* | find ""-N"" >nul && (echo Total Tests: %FU_TESTS% & exit /b 0)`r`nif ""%FU_TEST_FAIL%""==""1"" exit /b 1`r`nexit /b 0" -Encoding ASCII
$env:PATH = "$shim;$env:PATH"
$env:FU_TESTS = "3"; $env:FU_TEST_FAIL = "0"; $env:FU_BUILD_FAIL = "0"

try {
    # upstream (original) and fork (with motion/main = main + a local feature commit)
    $U = Join-Path $T "u-work"; G $T init -q -b main $U
    Commit-File $U "a.txt" "line1`r`nline2" "up: a"
    G $T clone -q --bare $U (Join-Path $T "upstream.git")
    G $U remote add origin (Join-Path $T "upstream.git")
    G $T clone -q --bare (Join-Path $T "upstream.git") (Join-Path $T "fork.git")
    $F = Join-Path $T "f-work"; G $T clone -q (Join-Path $T "fork.git") $F
    G $F checkout -q -b motion/main
    Commit-File $F "feature.txt" "local feature" "fork: feature"
    G $F push -q origin motion/main

    # root repo pinning the fork's motion/main, then a fresh recursive clone (detached submodule)
    $W = Join-Path $T "root-work"; G $T init -q -b main $W
    & git -C $W -c protocol.file.allow=always submodule add -q -b motion/main (Join-Path $T "fork.git") vendor/kimodo.cpp 2>&1 | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $W "scripts") | Out-Null
    Copy-Item $script (Join-Path $W "scripts\follow-upstream.ps1")
    Set-Content (Join-Path $W ".gitignore") "/logs/" -Encoding ASCII
    G $W add -A; G $W commit -q -m "root"
    G $T clone -q --bare $W (Join-Path $T "root.git")
    $R = Join-Path $T "root"
    & git -c protocol.file.allow=always clone -q --recurse-submodules (Join-Path $T "root.git") $R 2>&1 | Out-Null
    $S = Join-Path $R "vendor\kimodo.cpp"
    G $S remote add upstream (Join-Path $T "upstream.git")   # sandbox upstream (the script would add the GitHub one)
    $pin0 = Out-G $R rev-parse HEAD:vendor/kimodo.cpp
    $rootHead0 = Out-G $R rev-parse HEAD

    Write-Host "[1] upstream has nothing new"
    $rc = Run
    Check "exit 0" ($rc -eq 0) "rc=$rc"
    Check "no root commit" ((Out-G $R rev-parse HEAD) -eq $rootHead0)

    Write-Host "[2] dirty root is refused"
    Set-Content (Join-Path $R "stray.txt") "x" -Encoding ASCII
    $rc = Run; Check "exit 2" ($rc -eq 2) "rc=$rc"
    Remove-Item (Join-Path $R "stray.txt")

    Write-Host "[3] submodule on another branch is refused"
    G $S checkout -q -b feature
    $rc = Run; Check "exit 2" ($rc -eq 2) "rc=$rc"
    Check "left on its branch" ((Out-G $S symbolic-ref --short HEAD) -eq "feature")
    G $S checkout -q --detach $pin0; G $S branch -q -D feature

    Write-Host "[4] dry run reports and changes nothing"
    Commit-File $U "b.txt" "upstream new" "up: b"; G $U push -q origin main
    $rc = Run @("-DryRun")
    $out = Get-Content (Join-Path $T "last-run.txt") -Raw
    Check "exit 0" ($rc -eq 0) "rc=$rc"
    Check "lists the incoming commit" ($out -match "up: b")
    Check "submodule untouched" ((Out-G $S rev-parse HEAD) -eq $pin0)

    Write-Host "[5] zero tests is not a pass"
    $env:FU_TESTS = "0"
    $rc = Run; Check "exit 4" ($rc -eq 4) "rc=$rc"
    Check "fork not pushed" ((Out-G (Join-Path $T "fork.git") rev-parse motion/main) -eq $pin0)
    $env:FU_TESTS = "3"

    Write-Host "[6] failing tests stop before push (resume run)"
    $env:FU_TEST_FAIL = "1"
    $rc = Run; Check "exit 4" ($rc -eq 4) "rc=$rc"
    Check "fork still not pushed" ((Out-G (Join-Path $T "fork.git") rev-parse motion/main) -eq $pin0)
    Check "merge kept locally" ((Out-G $S rev-list --count origin/motion/main..HEAD) -ne "0")
    $env:FU_TEST_FAIL = "0"

    Write-Host "[7] resume completes: push, checks, pointer commit"
    $rc = Run
    $new = Out-G $S rev-parse HEAD
    Check "exit 0" ($rc -eq 0) "rc=$rc $(Get-Content (Join-Path $T 'last-run.txt') -Raw)"
    Check "fork motion/main pushed" ((Out-G (Join-Path $T "fork.git") rev-parse motion/main) -eq $new)
    Check "root pin moved to the merge" ((Out-G $R rev-parse HEAD:vendor/kimodo.cpp) -eq $new)
    Check "root commit has only the pointer" ((Out-G $R show --name-only --format= HEAD) -eq "vendor/kimodo.cpp")
    & git -C $S merge-base --is-ancestor $pin0 $new; Check "new pin descends from old" ($LASTEXITCODE -eq 0)
    Check "local feature kept (merge, not rebase)" (Test-Path (Join-Path $S "feature.txt"))
    Check "root not pushed" ((Out-G (Join-Path $T "root.git") rev-parse main) -eq $rootHead0)

    Write-Host "[8] conflict is handed to a human"
    G $F pull -q origin motion/main
    Commit-File $F "a.txt" "fork line`r`nline2" "fork: edit a"; G $F push -q origin motion/main
    Commit-File $U "a.txt" "upstream line`r`nline2" "up: edit a"; G $U push -q origin main
    $pin1 = Out-G $R rev-parse HEAD:vendor/kimodo.cpp
    $rc = Run; Check "exit 3" ($rc -eq 3) "rc=$rc"
    Check "merge left in progress (not aborted)" ([bool](Out-G $S rev-parse -q --verify MERGE_HEAD))
    $rc = Run; Check "re-run while unresolved: exit 3" ($rc -eq 3) "rc=$rc"
    Check "root pin unchanged" ((Out-G $R rev-parse HEAD:vendor/kimodo.cpp) -eq $pin1)
    G $S merge --abort
} catch {
    $script:fail++; Write-Host "  FAIL harness: $_"
} finally {
    Write-Host ("{0}/{1} passed - sandbox {2}" -f $script:pass, ($script:pass + $script:fail), $T)
    if ($script:fail -eq 0) { Remove-Item -Recurse -Force $T -ErrorAction SilentlyContinue }
}
exit $script:fail

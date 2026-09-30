# Scenario test for scripts/follow-upstream.ps1 - real git, shimmed cmake/ctest/smoke.
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

# shims: one compiled exe that plays the role named by its own file name. A .cmd shim cannot take
# the default ctest -E regex - cmd reads its '|' as a pipe.
#   cmake  - fails if FU_BUILD_FAIL=1; "--build <dir>" drops the smoke exe into <dir>\Release unless FU_NO_SMOKE_EXE=1
#   ctest  - "-N" reports FU_TESTS tests; a real run fails if FU_TEST_FAIL=1, exits 9 if <test-dir>\bin\Release
#            is not on PATH (the DLL dir), and writes its arguments to FU_CTEST_LOG
#   kimodo-generate-smoke - exit 1 if FU_SMOKE_FAIL=1 or the model file is missing; arguments to FU_SMOKE_LOG
$shim = Join-Path $T "shim"; New-Item -ItemType Directory -Path $shim | Out-Null
$fakeSrc = @'
using System; using System.IO; using System.Linq;
public static class Fake {
    static string Env(string n) { return Environment.GetEnvironmentVariable(n) ?? ""; }
    static string After(string[] a, string flag) { int i = Array.IndexOf(a, flag); return (i >= 0 && i + 1 < a.Length) ? a[i + 1] : null; }
    public static int Main(string[] a) {
        string self = System.Reflection.Assembly.GetEntryAssembly().Location;
        string role = Path.GetFileNameWithoutExtension(self);
        if (role == "cmake") {
            if (Env("FU_BUILD_FAIL") == "1") return 1;
            string dir = After(a, "--build");
            if (dir != null && Env("FU_NO_SMOKE_EXE") != "1") {
                string rel = Path.Combine(dir, "Release"); Directory.CreateDirectory(rel);
                File.Copy(self, Path.Combine(rel, "kimodo-generate-smoke.exe"), true);
            }
            return 0;
        }
        if (role == "ctest") {
            if (a.Contains("-N")) { Console.WriteLine("Total Tests: " + Env("FU_TESTS")); return 0; }
            if (Env("FU_TEST_FAIL") == "1") return 1;
            string dll = Path.Combine(After(a, "--test-dir") ?? "", "bin\\Release");
            if (!Env("PATH").Split(';').Contains(dll)) { Console.WriteLine("DLL dir not on PATH: " + dll); return 9; }
            File.WriteAllLines(Env("FU_CTEST_LOG"), a); return 0;
        }
        File.WriteAllLines(Env("FU_SMOKE_LOG"), a);
        if (Env("FU_SMOKE_FAIL") == "1" || a.Length != 2 || !File.Exists(a[0])) return 1;
        return 0;
    }
}
'@
$fakeExe = Join-Path $T "fake.exe"
Add-Type -TypeDefinition $fakeSrc -OutputAssembly $fakeExe -OutputType ConsoleApplication -ReferencedAssemblies "System.Core"
Copy-Item $fakeExe (Join-Path $shim "cmake.exe"); Copy-Item $fakeExe (Join-Path $shim "ctest.exe")
$env:PATH = "$shim;$env:PATH"
$env:FU_TESTS = "3"; $env:FU_TEST_FAIL = "0"; $env:FU_BUILD_FAIL = "0"; $env:FU_SMOKE_FAIL = "0"; $env:FU_NO_SMOKE_EXE = "0"
$env:FU_CTEST_LOG = Join-Path $T "ctest-args.txt"; $env:FU_SMOKE_LOG = Join-Path $T "smoke-args.txt"

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
    # default smoke model location (models/ is not committed - here it is just an untracked file)
    $model = Join-Path $S "models\kimodo-soma-rp-v1.1-f32.gguf"
    New-Item -ItemType Directory -Path (Split-Path $model) | Out-Null
    Set-Content $model "gguf" -Encoding ASCII

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

    Write-Host "[4] dry run reports and changes nothing (needs no smoke model)"
    Commit-File $U "b.txt" "upstream new" "up: b"; G $U push -q origin main
    Move-Item $model "$model.away"
    $rc = Run @("-DryRun")
    $out = Get-Content (Join-Path $T "last-run.txt") -Raw
    Check "exit 0" ($rc -eq 0) "rc=$rc"
    Check "lists the incoming commit" ($out -match "up: b")
    Check "submodule untouched" ((Out-G $S rev-parse HEAD) -eq $pin0)

    Write-Host "[4b] missing smoke model is refused before anything moves"
    $rc = Run
    $out = Get-Content (Join-Path $T "last-run.txt") -Raw
    Check "exit 2" ($rc -eq 2) "rc=$rc"
    Check "names the model" ($out -match "Smoke model not found")
    Check "submodule untouched" ((Out-G $S rev-parse HEAD) -eq $pin0)
    Check "no merge made" (-not (Out-G $S symbolic-ref -q --short HEAD))
    Move-Item "$model.away" $model

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

    Write-Host "[6b] failing smoke stops before push"
    $env:FU_SMOKE_FAIL = "1"
    $rc = Run; Check "exit 4" ($rc -eq 4) "rc=$rc"
    Check "says smoke failed" ((Get-Content (Join-Path $T "last-run.txt") -Raw) -match "Generate smoke failed")
    Check "fork still not pushed" ((Out-G (Join-Path $T "fork.git") rev-parse motion/main) -eq $pin0)
    $env:FU_SMOKE_FAIL = "0"

    Write-Host "[6c] smoke binary missing after build stops before push"
    Remove-Item -Recurse -Force (Join-Path $S "build") -ErrorAction SilentlyContinue
    $env:FU_NO_SMOKE_EXE = "1"
    $rc = Run; Check "exit 4" ($rc -eq 4) "rc=$rc"
    Check "says binary missing" ((Get-Content (Join-Path $T "last-run.txt") -Raw) -match "Smoke binary missing")
    Check "fork still not pushed" ((Out-G (Join-Path $T "fork.git") rev-parse motion/main) -eq $pin0)
    $env:FU_NO_SMOKE_EXE = "0"

    Write-Host "[7] resume completes: push, checks, pointer commit"
    Remove-Item $env:FU_CTEST_LOG, $env:FU_SMOKE_LOG -ErrorAction SilentlyContinue
    $rc = Run
    $new = Out-G $S rev-parse HEAD
    Check "exit 0" ($rc -eq 0) "rc=$rc $(Get-Content (Join-Path $T 'last-run.txt') -Raw)"
    $ctestArgs = @(Get-Content $env:FU_CTEST_LOG -ErrorAction SilentlyContinue)
    Check "ctest ran with the DLL dir on PATH and the baseline -E" (($ctestArgs -contains "-E") -and (($ctestArgs -join " ") -match "generate-smoke"))
    $smokeArgs = @(Get-Content $env:FU_SMOKE_LOG -ErrorAction SilentlyContinue)
    Check "smoke got the SOMA model and 30 joints" (($smokeArgs.Count -eq 2) -and ([IO.Path]::GetFullPath($smokeArgs[0]) -eq [IO.Path]::GetFullPath($model)) -and ($smokeArgs[1] -eq "30")) ($smokeArgs -join " | ")
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

<#
.SYNOPSIS
  텍스트 프롬프트로 UE5용 animation.glb를 생성한다.

.EXAMPLE
  .\scripts\generate-motion.ps1 -Prompt "a person walking forward enthusiastically and waving their right hand"

.EXAMPLE
  .\scripts\generate-motion.ps1 -Prompt "..." -Backend cpu   # 에디터 켜놓고도 안전하게
#>
param(
    [Parameter(Mandatory=$true)][string]$Prompt,
    [int]$FrameCount = 120,
    [int]$Steps = 50,
    [int]$Seed = 42,
    [string]$OutDir = "output_motion",
    [ValidateSet("vulkan","cpu")][string]$Backend = "vulkan",
    [string]$Model = "vendor\kimodo.cpp\models\kimodo-soma-rp-v1.1-f32.gguf",
    [string]$TextBundle = "vendor\kimodo.cpp\generated\llm2vec-text-bundle"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

# --- Vulkan/VRAM 안전장치: 에디터가 떠 있으면 경고 ---
if ($Backend -eq "vulkan") {
    $editor = Get-Process -Name "UnrealEditor*" -ErrorAction SilentlyContinue
    if ($editor) {
        Write-Warning "UnrealEditor가 실행 중입니다. Vulkan 백엔드는 RTX 3080 VRAM을 에디터와 나눠 씁니다."
        $answer = Read-Host "그래도 Vulkan으로 계속할까요? (y = 계속 / 아무 키 = 중단, -Backend cpu로 재실행 권장)"
        if ($answer -ne "y") {
            Write-Host "중단. 예: .\scripts\generate-motion.ps1 -Prompt '...' -Backend cpu"
            exit 1
        }
    }
}

if ($Backend -eq "cpu") {
    $env:KIMODO_BACKEND = "cpu"
} else {
    Remove-Item Env:\KIMODO_BACKEND -ErrorAction SilentlyContinue
}

# --- 빌드된 DLL을 PATH에 추가 ---
$buildBin = Join-Path $repoRoot "vendor\kimodo.cpp\build\bin\Release"
$buildRel = Join-Path $repoRoot "vendor\kimodo.cpp\build\Release"
$env:PATH = "$buildBin;$buildRel;$env:PATH"

$kmdGenerate = Join-Path $buildRel "kmd-generate.exe"
if (-not (Test-Path $kmdGenerate)) {
    throw "kmd-generate.exe가 없습니다 ($kmdGenerate). README의 빌드 단계를 먼저 실행하세요."
}

# --- 프롬프트 파일 생성 ---
$promptFile = Join-Path $repoRoot "prompt.txt"
$Prompt | Out-File -Encoding utf8 -NoNewline $promptFile

$outPath = Join-Path $repoRoot $OutDir
New-Item -ItemType Directory -Force -Path $outPath | Out-Null

Write-Host "[1/2] 모션 생성 중 ($Backend, ${FrameCount}프레임, ${Steps}스텝, seed=$Seed)..."
& $kmdGenerate $Model $TextBundle $promptFile $FrameCount $Steps $Seed "$outPath\"
if ($LASTEXITCODE -ne 0) { throw "kmd-generate.exe 실패 (exit $LASTEXITCODE)" }

Write-Host "[2/2] GLB로 내보내는 중..."
$glbPath = Join-Path $outPath "animation.glb"
py (Join-Path $repoRoot "vendor\kimodo.cpp\scripts\export_glb.py") --motion-dir $outPath --output $glbPath
if ($LASTEXITCODE -ne 0) { throw "export_glb.py 실패 (exit $LASTEXITCODE)" }

Write-Host "완료: $glbPath"
Write-Host "다음: UE5 Content Browser에 드래그 임포트 → Retarget Animations → SKM_Manny/SKM_Quinn"

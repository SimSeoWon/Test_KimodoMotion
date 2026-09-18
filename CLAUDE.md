# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

kimodo.cpp(NVIDIA Kimodo 텍스트→모션, C++/GGML 포팅판)로 UE5(`ModularStage`/`NS`)용
애니메이션을 뽑는 서브프로젝트. 뭐 하는 리포인지는 `README.md` 참고.

## [중요] 세션 시작 시 반드시 먼저 읽을 것

**`history/` 안에서 가장 최근 날짜 파일을 읽는다.** 지난 세션에서 뭘 만들었는지, 어떤
버그를 왜 겪었는지, 그 원인이 뭐였는지, 다음에 뭘 하기로 했는지가 거기 있다 — 안 읽으면
같은 API 이름을 잘못 추측하는 것 같은 삽질을 처음부터 반복하게 된다(실제로 이번 프로젝트
초반에 IK Retargeter op 이름을 두 번 잘못 추측했다).

작업이 끝나거나(사람이 확인·승인한 뒤) 중요한 결정을 내렸으면, `history/`에
`YYYY-MM-DD_<요약>.md`로 새 기록을 남긴다 — 형식은 기존 파일 아무거나 보고 따라 하면 된다.
trivial한 것(오탈자, 변수명 변경)은 안 남겨도 된다.

## 구조

- `vendor/kimodo.cpp/` — git submodule, kimodo.cpp 본체. 빌드 산출물(`build/`, `models/`,
  `generated/`)은 커밋 안 함.
- `scripts/generate-motion.ps1` — 프롬프트 → `animation.glb` 원클릭.
- `webui/` — 로컬 웹 UI (`py webui\server.py`, 표준 라이브러리만 사용). Stable Diffusion
  WebUI 식으로 파라미터를 채워 생성하고 결과 glb를 `model-viewer`로 바로 재생해서 보여준다.
  `server.py`가 `kmd-generate.exe`/`scripts/pretty_export_glb.py`를 직접 호출한다(ps1과
  기본 골격은 같은 파이프라인이나 export 단계만 미리보기용으로 다름 — 아래 참고). 결과물은
  `output_motion/generations/`에 쌓인다(gitignore 대상).
- `scripts/pretty_export_glb.py` — vendor의 `export_glb.py`(본마다 작은 큐브 메시)를
  건드리지 않고 `create_bone_mesh()`만 몽키패치해서 웹 미리보기용 메시로 바꾼다.
  `assets/mixamo_processed/ybot_soma30_bind.json`(있으면)을 우선 쓰고, 없는 조인트나
  파일 자체가 없으면 관절을 잇는 저폴리 캡슐로 채운다. **웹 UI 전용** —
  `generate-motion.ps1`/README의 UE5 임포트 경로는 그대로 vendor의 `export_glb.py`를
  쓴다(그쪽은 SOMA 메시를 쓰지 않고 IK Retargeter로 UE 마네킹 메시를 쓰므로 SOMA 쪽
  메시 모양은 상관없음).
- `assets/` — `mixamo_src/`(사용자가 mixamo.com에서 받은 원본 FBX)·`mixamo_processed/`
  (거기서 뽑은 바인딩 데이터) 전부 **git 미포함**(Mixamo 재배포 금지 라이선스, SOMA만 쓰고
  SMPL-X 뺀 것과 같은 이유). `extract_mixamo_soma30.py`는 Blender headless로 한 번만 돌려서
  Mixamo 메시를 SOMA30 조인트 인덱스·레스트 좌표계로 재배치해 뽑아내는 코드(git 포함,
  자세한 원리는 스크립트 docstring 참고). `_inspect_mixamo.py`는 다른 Mixamo 캐릭터로
  바꿀 때 본/버텍스그룹 이름을 확인하는 진단용.
- `KimodoTestbed/` — **로컬 전용 UE5.8 샌드박스, git에 안 올라간다**(`.gitignore` 참고,
  사용자 결정 2026-09-15). `NS`/`ModularStage`에 바로 실험하지 않고 여기서 UE5 임포트/리타겟
  자동화 코드를 먼저 검증한다. 새로 만든 코드가 아니라 "실험대"이므로 자유롭게 고치고
  되돌려도 된다.
- `history/` — 위 참고.

## 파이프라인 (전체 그림)

```
프롬프트 텍스트
   │  kmd-generate.exe (vendor/kimodo.cpp/build/Release, Vulkan or CPU)
   ▼
raw .f32 모션 스트림 (output_motion/)
   │  vendor/kimodo.cpp/scripts/export_glb.py
   ▼
animation.glb  — SOMA 30조인트, skinned
   │  KimodoTestbed 콘솔 커맨드 (Kimodo.ImportIK) 또는 UE5 드래그 임포트
   ▼
UE5 Mannequin(SKM_Manny/SKM_Quinn) 기준 AnimSequence
```

`generate-motion.ps1`은 앞 두 단계만 자동화한다. 세 번째 단계(UE5 임포트+리타겟)는
`KimodoTestbed/Source/KimodoTestbed/`에서 코드로 검증 중이고, 검증이 끝나면 `ModularStage`/`NS`로
옮긴다(README 참고 — 아직 이관 전).

## 빌드 / 실행 명령

**Python은 항상 `py`를 쓴다 — bare `python`은 Windows Store 스텁을 잡는다** (루트
`C:\Users\USER\CLAUDE.md` 참고).

```powershell
# 서브모듈 최초 체크아웃
git submodule update --init --recursive

# kimodo.cpp 빌드 (Vulkan)
cmake -S vendor\kimodo.cpp -B vendor\kimodo.cpp\build -G "Visual Studio 17 2022" -A x64 `
  -DKIMODO_BUILD_TESTS=OFF -DKIMODO_ENABLE_VULKAN=ON
cmake --build vendor\kimodo.cpp\build --config Release

# 모델 가중치 받기 (vendor/kimodo.cpp 안에서)
py scripts\download_gguf_weights.py --model soma-rp-v1.1

# 모션 생성 (원클릭)
.\scripts\generate-motion.ps1 -Prompt "a person walking forward enthusiastically and waving their right hand"
.\scripts\generate-motion.ps1 -Prompt "..." -Backend cpu   # 에디터 켜놓고도 안전하게

# 웹 UI (파라미터 폼 + glb 미리보기, http://127.0.0.1:8188/)
py webui\server.py

# (한 번만) Mixamo 캐릭터를 미리보기 메시로 쓰려면 — assets/mixamo_src/에 FBX를 둔 뒤
"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" --background --python assets\extract_mixamo_soma30.py
```

Blender는 2026-09-16에 winget(`BlenderFoundation.Blender`)으로 설치함 — headless
FBX 임포트/스킨 웨이트 추출 전용으로만 쓴다(UE5 파이프라인과는 무관).

`generate-motion.ps1`은 `UnrealEditor*` 프로세스가 떠 있으면 경고하고 계속할지 물을 뿐,
자동으로 CPU로 바꾸지 않는다 — VRAM을 에디터와 나눠 쓰게 됨을 사용자가 알고 승인해야 한다.
`KIMODO_TEXT_LAYER_CHUNK`(기본 8)로 텍스트 인코더 VRAM 사용량을 조절할 수 있다.

`KimodoTestbed/`의 UE5 콘솔 커맨드는 **정상 에디터 실행 + `-ExecCmds`**로만 호출한다(아래
"커맨드릿이 아니라 콘솔 커맨드" 참고):

```
UnrealEditor-Cmd.exe KimodoTestbed.uproject -ExecCmds="Kimodo.ImportIK GlbPath=<file.glb> TargetSkeletalMesh=/Game/... DestPath=/Game/KimodoAnimations, Quit" -abslog="<절대경로.log>"
```

`Quit` 콘솔 커맨드가 에디터 프로세스를 실제로 안 닫는 알려진 문제가 있다(미조사) — 작업
자체는 끝나 있으니 `taskkill`로 정리하면 된다. 에디터 창이 뜨니 사용자에게 미리 알릴 것.
**로그는 `-abslog=`로 파일에 직접 쓰게 한다** — 파이프(`| tail` 등)로 백그라운드 UE5 프로세스를
강제종료하면 flush 전에 로그가 통째로 날아간다.

## 아키텍처 — UE5 임포트/리타겟 (`KimodoTestbed/Source/KimodoTestbed/`)

- `KimodoImportLibrary.h/.cpp` — 실제 임포트+리타겟 로직. 커맨드릿과 콘솔 커맨드 양쪽에서
  재사용.
  - `Run()` — 레거시 리타게팅(`EditorAnimUtils::RetargetAnimations`, 에디터 "Retarget
    Animations" 우클릭 메뉴와 같은 함수). **폐기됨** — SOMA와 UE Mannequin은 본 이름이 전혀
    다르고(`Hips` vs `pelvis`), 본 방향(roll) 관례 차이 때문에 목처럼 회전 민감한 관절이
    깨진다.
  - `RunIK()` — 현재 쓰는 경로. `UIKRetargetBatchOperation::RunBatchRetarget` 기반, SOMA/Manny
    용 IK Rig를 코드로 만들고 `AutoMapChains(Exact)`로 체인을 이름 매칭한 뒤 배치 리타겟.
    포즈 기반이라 본 방향 차이에 더 강건함.
- `KimodoTestbed.cpp` — 모듈 `StartupModule()`에서 콘솔 커맨드 `Kimodo.Import`(레거시,
  `Run()` 호출) / `Kimodo.ImportIK`(현재 쓰는 경로, `RunIK()` 호출) 등록. 인자는
  `Key=Value` 토큰(`GlbPath=`, `TargetSkeletalMesh=`, `DestPath=`).
- `Commandlets/KimodoImportCommandlet.cpp` — `-run=KimodoImport`. **지금은 안 씀**: 커맨드릿
  모드(`-run=`)는 `-unattended` 유무와 무관하게 Slate를 초기화하지 않는데,
  `EditorAnimUtils::RetargetAnimations`가 Content Browser 갱신 경로를 건드리다
  `Assertion failed: CurrentApplication.IsValid() [SlateApplication.h:321]`로 크래시한다.
  → 정상 에디터 실행 + `-ExecCmds`(콘솔 커맨드)로 대체.

**미해결 이슈**: IK Retargeter로 다리는 정상 재생되지만 양팔이 반대 방향으로 꺾인다. 원인
추정은 SOMA가 완전한 T-포즈인 반면 Manny는 그렇지 않아서 팔꿈치처럼 굽힘 방향이 애매한
관절에서 반전이 생기는 것 — `UIKRetargeterController::SetRotationOffsetForRetargetPoseBone`로
SOMA 쪽 Source Retarget Pose를 보정하는 게 다음 시도. 자세한 경위는
`history/2026-09-15_testbed-import-retarget.md` 참고.

## 방법론 — 엔진 API를 추측하지 않는다

UE5 엔진 소스가 로컬에 있다(`C:\Program Files\Epic Games\UE_5.8\Engine\Source`,
`...\Engine\Plugins`). 문자열 기반 API(`AddRetargetOp(const FString)` 같은)나 정확한 이름
포맷이 필요한 API는 **추측하지 말고 먼저 grep해서 엔진이 그 API를 실제로 호출하는 곳을
찾아 같은 패턴을 그대로 베낀다** — 이번 프로젝트에서 IK Retargeter op 등록 문자열을 두 번
잘못 추측한 뒤에 정착한 방식.

Git Bash에서 UE5 콘텐츠 경로(`/Game/...`)를 다룰 때는 MSYS 경로 변환이 이를 POSIX 경로로
오인해 깨뜨린다 — `MSYS_NO_PATHCONV=1`로 막는다.

## WebUI 포즈 수정 규칙

- 포즈 작업은 별도 내장 프리셋을 고르는 기능이 아니다. 새 포즈를 생성하거나 사용자가
  명시적으로 저장한 포즈를 불러온 뒤, 현재 포즈에서 요청한 내용만 수정한다.
- `결정론적 자세`, 이름 기반 레시피, `마보` 같은 숨은 자세 분기나 자동 프리셋을 만들지
  않는다. 저장 포즈 로드는 사용자가 UI에서 명시적으로 실행할 때만 일어난다.
- 포즈 명령 입력, 현재 작업 포즈의 임시 정보, 이름과 저장 동작은 동일한 작업 포즈 행에
  속한다. 전역 명령이나 별도 상단 포즈 명령으로 취급하지 않는다.
- 좌표계는 X가 좌우(+X는 캐릭터 왼쪽), Y가 위, Z가 앞이다. 쿼터니언 순서는 x,y,z,w다.
  서 있는 캐릭터의 수평 방향 전환(yaw)은 Y축 회전이다. Z축 회전으로 발의 팔자 방향을
  표현하면 안 된다.
- 한국어 `팔자`는 양 발끝이 바깥쪽을 향하는 turnout/toes-out이다. `pigeon-toed`나
  toes-in으로 해석하면 안 된다. 왼발은 발끝 X가 발목보다 커지고, 오른발은 발끝 X가
  발목보다 작아져야 한다. 발목→발끝 수평 벡터로 실제 각도를 계산해 확인한다.
- 거리, 배수, 각도를 요약에 적었다면 반환 좌표와 쿼터니언이 실제로 그 값을 만들어야 한다.
  입력 스냅샷을 반올림한 정도의 변화는 포즈 수정으로 기록하지 않는다. `벌린다`는 요청의
  결과 발 간격이 입력보다 좁아지면 실패다.
- 위치 목표와 회전 목표는 서로 대체되지 않는다. 위치는 보폭·접점을, 회전은 방향을
  표현하므로 같은 관절 계통에 둘 다 필요하면 둘 다 보존한다.
- WebUI의 실제 포즈 LLM 경로는 `webui/pose_agent.py`의 현재 PoseAsset과 전신 스냅샷이다.
  결과 적용은 `webui/static/keypose-editor.mjs`, 영구 실행 로그는
  `webui/logs/YYYY-MM-DD/NNNN_pose_<id>.jsonl`에서 확인한다.
- `scripts/keypose_mcp.py`는 과거 타임라인 `STORE`와 프리셋 API를 조작하는 구형 MCP다.
  현재 작업 포즈의 권위 있는 상태가 아니며, 현 구조에 맞게 개편하기 전에는 포즈 LLM이
  사용한다고 가정하거나 활성화하지 않는다.
- 포즈 에이전트 모델은 최소 Sonnet을 사용한다. Haiku는 3D 좌표계, 쿼터니언 축, 상대 거리와
  실제 출력의 일관성을 안정적으로 처리하지 못했으므로 포즈 생성·수정에 사용하지 않는다.
  더 높은 모델은 허용하지만 `KIMODO_POSE_AGENT_MODEL`로 Sonnet 아래 모델을 지정해도 런타임이
  Sonnet으로 올린다.

## 이 기계(`.33`)에서 알아둘 것 — 루트 `CLAUDE.md`도 적용됨

`C:\Users\USER\CLAUDE.md`(이 기계 전체에 적용되는 문서)의 원칙도 그대로 따른다 — 특히
**사용자가 지금 작업 중일 수 있다**: UE5 에디터를 스크립트로 띄우기 전에 이미 열려있는
에디터가 사용자 본인 세션인지 확인한다(타 프로세스 강제종료 전 확인 — 이번 프로젝트에서
실제로 몇 번 물어봄). Vulkan 추론(`generate-motion.ps1`)도 마찬가지로 에디터가 떠 있으면
VRAM을 나눠 쓴다는 걸 감안.

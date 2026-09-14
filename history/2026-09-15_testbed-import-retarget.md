---
date: 2026-09-15
tags: [kimodo.cpp, UE5.8, IKRig, IKRetargeter, EditorAnimUtils, Interchange, commandlet, glTF]
status: in-progress
---

# kimodo.cpp → UE5 모션 파이프라인: 첫 세션

## 배경

`github.com/localai-org/kimodo.cpp`(NVIDIA Kimodo 텍스트→모션 diffusion 모델의 C++/GGML
포팅판)로 UE5(`ModularStage`, `NS`)용 애니메이션을 뽑는 서브프로젝트를 새로 시작했다.
`C:\Users\USER\Documents\kimodo-motion`에 별도 git 리포로 둔다 — 배포/공유 가능해야
한다는 게 사용자 결정이었다(완전 분리 폴더 대신 git 서브모듈 + `.gitignore`로).

## 만든 것

### 1. 생성 파이프라인 (안정적으로 동작 확인됨)

```
프롬프트 → kmd-generate.exe(Vulkan, RTX 3080) → raw .f32
        → export_glb.py → animation.glb (SOMA 30조인트, skinned)
```

`scripts/generate-motion.ps1`로 원클릭. `KIMODO_BACKEND=cpu`로 CPU 강제 가능(소스 확인,
`GGML_VK_DISABLE`이 아니었음 — 처음에 잘못 짚었다가 `src/ggml_weights.cpp`에서 확인 후 수정).

에디터가 켜져 있으면 Vulkan이 VRAM을 나눠 쓰니, 스크립트가 `UnrealEditor*` 프로세스를
감지해서 경고 후 확인받는다(자동으로 CPU로 안 바꿈).

### 2. UE5 임포트+리타겟 자동화 (`KimodoTestbed/`, git 미포함 로컬 샌드박스)

`NS`(사용자의 실제 프로젝트)에 바로 실험하지 않고, 빈 Third Person Blueprint 프로젝트를
새로 만들어 그 안에서 커맨드릿/콘솔 커맨드를 개발했다 — `NS`는 `Content/**` 쓰기 전에
동의가 필요한 프로젝트 규칙이 있어서다.

소스: `KimodoTestbed/Source/KimodoTestbed/`
- `KimodoImportLibrary.h/.cpp` — 실제 로직 (`Run`=레거시, `RunIK`=IK Retargeter)
- `KimodoTestbed.cpp` — 콘솔 커맨드 `Kimodo.Import` / `Kimodo.ImportIK` 등록
- `Commandlets/KimodoImportCommandlet.cpp` — `-run=KimodoImport` (레거시 경로 전용, 아래
  이유로 지금은 안 씀)

## 겪은 문제와 원인 (중요 — 다음에 같은 삽질 반복하지 않기 위해)

### 문제 1: 커맨드릿(`-run=`)은 Slate가 없어서 크래시

`EditorAnimUtils::RetargetAnimations`(레거시 리타겟, "Retarget Animations" 우클릭 메뉴가
쓰는 그 함수)를 `-run=KimodoImport` 커맨드릿으로 부르면, Manny/Quinn(같은 스켈레톤 공유)
쪽 Content Browser 갱신(썸네일 등으로 추정)을 건드리다가
`Assertion failed: CurrentApplication.IsValid() [SlateApplication.h:321]`로 크래시.

- `UnrealEditor-Cmd.exe`든 `UnrealEditor.exe -run=`이든 **`-run=커맨드릿` 자체가 Slate를
  초기화 안 한다** — `-unattended` 유무와 무관. 바이너리 문제가 아니라 커맨드릿 모드 자체의
  구조적 특성.
- **해결**: `-run=`을 버리고, 콘솔 커맨드(`IConsoleManager::RegisterConsoleCommand`)로
  바꿔서 **정상 에디터 실행 + `-ExecCmds="Kimodo.ImportIK ..., Quit"`**로 부른다. 정상
  에디터 실행은 Slate가 살아있어서 문제 없음.
- 부작용: `Quit` 콘솔 커맨드가 에디터를 안 닫는다(원인 미조사). 작업 자체는 끝나 있으니
  `taskkill`로 정리하면 됨. 화면에 창이 잠깐(또는 계속) 뜨니 작업 중인 사용자에게 미리
  알려야 함.

### 문제 2: 레거시 리타겟(`EditorAnimUtils::RetargetAnimations`) — 목이 꺾임

SOMA(kimodo.cpp)와 UE Mannequin은 **본 이름이 완전히 다르다** (`Hips` vs `pelvis` 등).
레거시 리타게팅은 UE Mannequin 계열처럼 같은 리그 혈통(본 이름 공유)에서 쓰라고 설계된
시스템으로 보인다 — 이름이 다른 스켈레톤 사이에 억지로 쓰면 본 방향(roll) 관례 차이가
그대로 드러나서 목처럼 회전 민감한 관절이 깨진다. **이 경로는 폐기, IK Retargeter로 전환.**

### 문제 3: IK Retargeter로 전환 — op 등록 문자열이 계속 실패

`UIKRetargeterController::AddRetargetOp(const FString)`는 내부적으로
`FindObject<UScriptStruct>(nullptr, *Name)`로 찾는데, **정확한 이름 포맷을 추측으로
못 맞혔다** — `"FIKRetargetPelvisMotionOp"`도, `F` 뗀 `"IKRetargetPelvisMotionOp"`도 둘 다
`LogIKRigEditor: Warning: Specified retarget op type was not found`로 실패.

op가 하나도 안 실리니 리타게터가 아무 것도 안 하고 기본 포�즈만 나왔다(사용자가 "팔 벌린
자세로 고정"이라고 본 게 이거). 압축 크기로도 확인됨: 정상 0.89MB 원본 대비 실패 버전
0.20~0.22MB.

- **해결**: 엔진 자체 소스(`IKRetargeterController.cpp`)를 읽어보니 내부에서는 전부
  **타입 오버로드**만 쓴다 — `AddRetargetOp(FIKRetargetPelvisMotionOp::StaticStruct())`.
  이걸로 바꾸니 바로 됨(2.25MB, 다리 정상 재생).
- **교훈**: 문자열 기반 API는 이름 포맷을 추측하지 말고, 엔진이 내부적으로 그 API를 실제
  호출하는 곳을 먼저 찾아서 같은 패턴을 그대로 베낀다.

### 문제 4 (미해결): IK Retargeter — 양팔 굽힘 방향이 반대로 꺾임

다리는 정상 재생되는데 양팔만 반대로 꺾인다(사용자 육안 확인). 유력 원인: **SOMA는 완전한
T-포즈**(export_glb.py의 `offsets`에서 `LeftArm`이 거의 순수 +X로 뻗어 있음 = 수평),
**Manny는 T-포즈가 아닌 기본 레퍼런스 포즈**. IK Retargeter가 기준 삼는 "Retarget Pose"를
안 맞춰주면, 굽힘 방향이 애매한 관절(팔의 팔꿈치처럼)에서 방향이 반전되는 게 잘 알려진
증상 — 다리는 굽힘 방향이 명확해서 이 문제에 덜 민감했던 것으로 보임.

고칠 API는 찾아뒀다:
```cpp
UIKRetargeterController::SetRotationOffsetForRetargetPoseBone(
    const FName& BoneName, const FQuat& RotationOffset, ERetargetSourceOrTarget::Source);
```
SOMA 쪽(Source) 팔 본에 회전 오프셋을 줘서 T-포즈를 Manny의 포즈 쪽으로 근사시키는 방향.
**축/각도는 3D라 코드로 맹목적으로 추측하면 여러 번 삽질할 위험** — 에디터에서 직접
Edit Pose 모드로 드래그해서 맞추는 게 더 빠를 수 있다는 논의까지 하고 세션이 끊김.
**다음 세션은 여기서부터 재개.**

## 방법론 메모 (다음에도 쓸 것)

- **UE5 엔진 소스가 로컬에 있다** (`C:\Program Files\Epic Games\UE_5.8\Engine\Source`,
  `...\Engine\Plugins`) — API를 추측하지 말고 항상 먼저 grep해서 실제 시그니처/내부
  사용처를 확인한다. 이번 세션에서 여러 번 이렇게 해서 맞는 API를 찾았다
  (`EditorAnimUtils.h`, `InterchangeManager.h`, `IKRigController.h`,
  `IKRetargeterController.h`, `IKRetargetBatchOperation.h`).
- **`| tail`로 파이프한 백그라운드 UE5 프로세스를 강제종료(taskkill)하면 로그가 통째로
  날아간다** (파이프가 EOF를 못 받아서 tail이 flush 안 함). `-abslog="<절대경로>"`로 UE5
  자체 로그를 파일에 직접 쓰게 하면 프로세스 상태와 무관하게 언제든 읽을 수 있다 — 이후로는
  이 방식을 쓴다.
- **Git Bash의 MSYS 경로 변환**이 `/Game/...` 같은 UE5 콘텐츠 경로를 POSIX 경로로 오인해서
  `C:/Program Files/Git/Game/...`로 망가뜨린다 — `MSYS_NO_PATHCONV=1`로 막아야 한다.
- Manny/Quinn 스켈레탈 메시 경로: `/Game/Characters/Mannequins/Meshes/SKM_Manny_Simple`
  (`.uasset` 확인함). 본 이름(`pelvis, spine_01..03, neck_01, head, clavicle_l/r,
  upperarm_l/r, lowerarm_l/r, hand_l/r, thigh_l/r, calf_l/r, foot_l/r`)은 표준 UE5 마네킹
  컨벤션을 그대로 가정해서 썼고 지금까지 다 매칭됐다 — 다만 한 번도 직접 덤프해서 확인한
  적은 없다.
- SOMA30 조인트 이름/부모 계층/레스트 오프셋 전체 목록: `vendor/kimodo.cpp/scripts/export_glb.py`
  의 `SKELETONS["soma30"]` 딕셔너리.

## 다음 세션에서 할 일 (우선순위 순)

1. **팔 굽힘 방향 반전 고치기** — `SetRotationOffsetForRetargetPoseBone`로 SOMA 쪽 Source
   Retarget Pose의 팔을 T-포즈에서 내려서 시도. 안 되면 에디터 Edit Pose 모드로 사용자가
   직접 눈으로 맞추는 것도 고려.
2. (사소) `Kimodo.ImportIK` 실행 후 `Quit`이 에디터를 안 닫는 문제 — 원인 미조사, 급하지 않음.
3. 다 되면: `NS`(또는 `ModularStage`)에 실제로 붙여보기 — `KimodoTestbed`에서 검증한 걸
   그대로 옮기되, `NS`는 `Content/**` 쓰기 전 동의 필요하다는 규칙을 지킬 것.

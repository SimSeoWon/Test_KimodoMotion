# kimodo-motion

텍스트 프롬프트로 UE5(`ModularStage`)용 애니메이션 모션을 뽑아내는 서브프로젝트.
[NVIDIA Kimodo](https://github.com/localai-org/kimodo.cpp)의 C++/GGML 포팅판을 엔진으로 쓴다.

이 리포 자체는 `ModularStage`와 별도로 관리한다 — 여기서 생성한 애니메이션을
필요할 때 `ModularStage`의 `Content/KimodoAnimations/`로 옮겨 쓴다.

## 파이프라인

```
프롬프트 텍스트
   │  kmd-generate.exe (build\Release\)
   ▼
raw .f32 모션 스트림 (output_motion\)
   │  scripts\export_glb.py (vendor/kimodo.cpp)
   ▼
animation.glb  — SOMA 30조인트, skinned, UE5 임포트 가능
   │  UE5 드래그 임포트 (Skeleton: None → SOMA 스켈레톤 자동 생성)
   ▼
animation_Anim  (SOMA 스켈레톤 기준 AnimSequence)
   │  우클릭 → Retarget Animations → Target: SKM_Manny / SKM_Quinn
   ▼
UE5 Mannequin AnimSequence — 바로 재생/몽타주화 가능
```

리타게팅은 Blender 경유 없이 **UE5 내장 리타게팅**으로 끝난다 — 자세한 단계는
`vendor/kimodo.cpp/docs/how_to_setup_with_unreal_in_windows.md` 참고.

## 진행 상황 (2026-09-15) — 다음 세션에서 이어갈 것

**`KimodoTestbed/`**(git에는 안 올림, 로컬 전용 UE5.8 샌드박스 — `NS`/`ModularStage`와 분리된
실험대)에 **임포트+리타겟을 헤드리스에 가깝게 자동화하는 커맨드릿/콘솔 커맨드**를 만들었다.
소스: `KimodoTestbed/Source/KimodoTestbed/`.

### 확인된 것
- `Kimodo.Import`(콘솔 커맨드, `KimodoTestbed.uproject`를 `-ExecCmds`로 정상 에디터 실행 —
  `-run=커맨드릿`은 Slate가 없어서 못 씀, 실측 확인) — 글TF 임포트 + **레거시**
  `EditorAnimUtils::RetargetAnimations` 리타겟. **목이 꺾이는 문제 있음** — SOMA/Manny
  본 이름이 완전히 달라서 레거시 시스템(이름 매칭 기반)엔 애초에 안 맞는 방식으로 보임.
- `Kimodo.ImportIK` — 같은 임포트 + **IK Retargeter**(`UIKRigController`로 SOMA/Manny용
  IK Rig 두 개를 코드로 생성 → 체인 이름 맞춰서 `AutoMapChains(Exact)` → `FIKRetargetPelvisMotionOp`
  + `FIKRetargetFKChainsOp` → `UIKRetargetBatchOperation::RunBatchRetarget`). **다리는 정상
  재생됨.** 압축 크기로 실동작 확인(빈 결과 0.2MB대 vs 실제 동작 2.25MB).
- **op 등록은 `AddRetargetOp(UScriptStruct*)` 타입 오버로드로만** — 문자열 오버로드는
  `FindObject(nullptr, Name)`라 이름 포맷(F 접두사 포함/제외 둘 다) 못 맞혀서 실패했었음
  (`FIKRetargetPelvisMotionOp::StaticStruct()`처럼 타입으로 넘길 것).

### 미해결 — 다음에 여기부터
- **`Kimodo.ImportIK` 결과도 양팔이 반대로 꺾인다** (다리는 정상). 유력 원인: SOMA는 완전한
  T-포즈, Manny는 T-포즈가 아닌 레퍼런스 포즈라 IK Retargeter의 "Retarget Pose"를 안 맞춰줘서
  생기는 전형적인 증상(굽힘 방향이 애매한 관절에서 터짐). 고칠 API는 찾아둠 —
  `UIKRetargeterController::SetRotationOffsetForRetargetPoseBone(BoneName, FQuat, ERetargetSourceOrTarget::Source)`.
  축/각도는 3D라 코드로 맹목적으로 추측하기보다 **에디터에서 직접 눈으로 보고 조정하는 게 더
  빠를 수 있음** — 사용자와 방법 논의 중 중단됨.
- `Kimodo.ImportIK` 실행 후 `-ExecCmds`의 `Quit`이 에디터를 안 닫는다(`-unattended` 넣어도).
  작업 자체(임포트+리타겟+저장)는 완료되니 치명적이진 않음 — 끝난 뒤 그냥 `taskkill`로 정리하는
  중. 원인 미조사.
- `-abslog="<path>"`로 로그를 파일로 직접 받는 게 `| tail`로 파이프하는 것보다 안전함
  (프로세스를 강제종료하면 파이프가 flush 안 돼서 로그가 통째로 날아감 — 실제로 한 번 겪음).

### 참고 — 이번 세션에서 검증한 UE5.8 API 위치
- `EditorAnimUtils::RetargetAnimations` — `Engine/Source/Editor/UnrealEd/Public/EditorAnimUtils.h`
- `UInterchangeManager::ImportAsset` — `Engine/Source/Runtime/Interchange/Engine/Public/InterchangeManager.h`
- `UIKRigController` / `UIKRetargeterController` / `UIKRetargetBatchOperation` —
  `Engine/Plugins/Animation/IKRig/Source/IKRigEditor/Public/{RigEditor,RetargetEditor}/`
- Manny/Quinn 스켈레탈 메시: `/Game/Characters/Mannequins/Meshes/SKM_Manny_Simple` — 본 이름은
  `pelvis, spine_01..03, neck_01, head, clavicle_l/r, upperarm_l/r, lowerarm_l/r, hand_l/r,
  thigh_l/r, calf_l/r, foot_l/r` (표준 UE5 마네킹 컨벤션, 실측 확인 안 함 — 코드에서 그대로
  가정해서 씀. 지금까지는 다 매칭됐으니 맞는 듯).
- SOMA30 조인트 이름/부모 계층: `vendor/kimodo.cpp/scripts/export_glb.py`의 `SKELETONS["soma30"]`.

## 모델

**SOMA RP v1.1**을 기본으로 쓴다 (NVIDIA Open Model License, 상용 이용 가능, ~8GB).
`SMPL-X RP v1`은 내부 R&D 전용 라이선스라 재배포 금지 — 쓰지 않는다.

## 빌드 (Windows, .33)

`vendor/kimodo.cpp`는 git submodule (pinned commit). 자체 GGML도 그 안에서 submodule로 물려있다.

```powershell
git submodule update --init --recursive

cmake -S vendor\kimodo.cpp -B vendor\kimodo.cpp\build -G "Visual Studio 17 2022" -A x64 `
  -DKIMODO_BUILD_TESTS=OFF -DKIMODO_ENABLE_VULKAN=ON
cmake --build vendor\kimodo.cpp\build --config Release
```

## 추론 백엔드: Vulkan (RTX 3080) — 단, 에디터가 켜져 있으면 무겁다

`.33`은 사용자의 작업 기계다 (`CLAUDE.md` 참고) — UE5 에디터가 떠 있는 동안 Vulkan으로
모션을 생성하면 VRAM을 나눠 쓰게 된다. `scripts/generate-motion.ps1`은 실행 전에
`UnrealEditor` 프로세스가 떠 있는지 확인하고 뜬 채면 경고만 하고 계속 진행 여부를 묻는다
(자동으로 CPU로 바꿔치기하지 않음 — 필요하면 `-Backend cpu`로 명시).

`KIMODO_TEXT_LAYER_CHUNK`(기본 8) 환경변수로 텍스트 인코더의 VRAM 사용량을 조절할 수 있다.
CPU로 강제하려면 `KIMODO_BACKEND=cpu` (스크립트의 `-Backend cpu`가 이걸 설정한다) — Vulkan
빌드에서도 이 값이 서 있으면 CPU 백엔드로 떨어진다.

## 모델 다운로드

```powershell
py scripts\download_gguf_weights.py --model soma-rp-v1.1   # (vendor/kimodo.cpp 안에서)
```

## 라이선스

- 포팅 코드: Apache-2.0 (`vendor/kimodo.cpp/LICENSE`)
- SOMA/G1 모델 가중치: NVIDIA Open Model License — 상용 가능
- SMPL-X 모델: 내부 R&D 전용, 재배포 금지 — **이 리포에서 다루지 않는다**

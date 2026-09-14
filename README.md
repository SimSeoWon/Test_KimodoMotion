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

## 진행 상황 / 작업 기록

세션별 진행 상황, 겪은 문제와 원인, 다음에 할 일은 **`history/`**에 있다 — 최신 파일부터
읽는다. 새 세션은 시작할 때 `history/`의 최신 기록을 먼저 읽을 것(`CLAUDE.md` 참고).

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

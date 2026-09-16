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

## 웹 UI

Stable Diffusion WebUI 식으로 파라미터(프롬프트/프레임 수/Steps/Seed/백엔드)를 채우고
Generate를 누르면 결과 `animation.glb`를 브라우저에서 바로 재생해서 보여주는 로컬 웹 서버.
외부 의존성 없이 Python 표준 라이브러리만 쓴다(Flask 등 불필요).

```powershell
py webui\server.py            # 기본 포트 8188
# 브라우저에서 http://127.0.0.1:8188/ 접속
```

`kmd-generate.exe`를 그대로 호출하고(내부적으로 `generate-motion.ps1`과 같은 파이프라인),
glb로 내보낼 때는 `export_glb.py`가 아니라 `scripts/pretty_export_glb.py`를 쓴다 — 원본은
관절마다 작은 큐브만 찍는 뼈대 시각화용 메시라 미리보기에 사람이 안 보여서, 웹 UI 전용으로
바꾼 버전이다(vendor 서브모듈은 안 건드림, UE5 임포트 경로는 그대로 원본을 씀 — 자세한
이유는 `CLAUDE.md` 참고). 실제 미리보기 메시는 두 단계로 구성:

1. **Mixamo 캐릭터 메시**(있으면 우선 사용) — `assets/mixamo_src/`에 사용자가 mixamo.com에서
   직접 받은 캐릭터(Y Bot 등, FBX·With Skin·T-pose)를 두면, `assets/extract_mixamo_soma30.py`
   (Blender headless, 한 번만 실행)가 그 메시를 SOMA30 레스트 좌표계로 재배치해서
   `assets/mixamo_processed/`에 바인딩 데이터를 뽑아둔다. **둘 다 git에 안 올라감** — Mixamo
   원본 재배포 금지 라이선스 때문(SOMA만 쓰고 SMPL-X 뺀 것과 같은 이유).
2. **캡슐 래그돌 폴백** — 위 바인딩 데이터가 없거나, Mixamo 표준 리그에 대응 본이 없는
   조인트(목/턱/눈)는 관절을 잇는 저폴리 캡슐로 채운다.

생성 결과는
`output_motion/generations/<타임스탬프>_<슬러그>/`에 `animation.glb` +
`meta.json`(프롬프트/파라미터/소요시간)으로 저장되고 히스토리에 쌓인다 — 전부 `.gitignore` 대상.
동시에 두 개 이상 생성이 돌지 않도록 서버가 직렬화한다. UnrealEditor가 떠 있는 상태에서
Vulkan 백엔드를 쓰면 상단에 경고 배너가 뜬다(자동으로 막지는 않음 — `generate-motion.ps1`과
같은 정책).

### 포징 모드와 AI 조작

웹 UI의 `포징 모드`를 열면 SOMA30 캐릭터의 골반·가슴·고개·양어깨·양팔꿈치·양손·양무릎·양발을
선택해 이동/회전 기즈모로 키포즈를 만들 수 있다. 부모 관절 회전은 순수 FK로 모든 자식에게
전파되고, 손·발·팔꿈치·무릎 이동은 뼈 길이를 유지하는 IK 보정으로 동작한다. 키포즈는 프레임별로
저장되며 Generate 요청 시 Kimodo의 희소 위치/회전 제약으로 전달된다. 단일 프롬프트와
스토리보드 구간 생성 모두 지원한다.

Claude Code는 저장소의 `.mcp.json`을 승인하면 `kimodo-keypose` 도구를 사용할 수 있다.
다른 MCP 클라이언트에는 다음 stdio 서버를 등록한다.

```powershell
py scripts\keypose_mcp.py
```

MCP 도구로 현재 포즈 조회, 키포즈 생성·복사·삭제, 13개 컨트롤 이동/회전, 포즈 프리셋
저장·타임라인 배치, undo/redo를
수행할 수 있다. AI나 HTTP API의 변경은 실행 중인 포징 UI에 자동 반영되며, 웹에서 만든
키포즈와 같은 `webui/keypose.py` schema 및 검증기를 공유한다.

## 모델 다운로드

```powershell
py scripts\download_gguf_weights.py --model soma-rp-v1.1   # (vendor/kimodo.cpp 안에서)
```

## 라이선스

- 포팅 코드: Apache-2.0 (`vendor/kimodo.cpp/LICENSE`)
- SOMA/G1 모델 가중치: NVIDIA Open Model License — 상용 가능
- SMPL-X 모델: 내부 R&D 전용, 재배포 금지 — **이 리포에서 다루지 않는다**

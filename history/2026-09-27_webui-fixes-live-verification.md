# WebUI 결함 수정 재검증 (W01~W09) — Codex 중단분 인수

- 날짜: 2026-09-27
- 경위: Codex가 [`2026-09-27_webui-wrapper-audit.md`](2026-09-27_webui-wrapper-audit.md)의 W01~W07을 고치던 중
  토큰 한도로 인계 없이 멈췄다. 사용자가 "모두 재검증"을 요청해 Claude가 diff 전체를 검토하고 라이브로 확인했다.
- 사용자 결정: 라이브 검증 진행(Vulkan GPU 사용), 골반 자동 고정 되돌리기, W08·W09는 검증 후 이어서 처리.

## 판정

| 항목 | 결과 | 확인 방법 |
|---|---|---|
| W01 상주 워커 중복 적재 | 해결 | 일반→부정 프롬프트→포즈→일반 실생성 4회, `kmd-generate` 최대 1개, VRAM 최대 ~6.0GB(기준 2.5GB) |
| W02 표시 캐릭터 비율 | 해결 + 부작용 수정 | 편집기가 `/api/tpose?model=capsule`(바인딩 없는 SOMA 원본, Hips `(0,0.988,0)`) 사용을 서버 로그로 확인 |
| W03 기록 복원 | 해결 | 헤드리스 Chrome: 폼을 99f/CFG7/seed5/부정 프롬프트로 어지럽힌 뒤 기록 클릭 → 60f/2/101/빈 값, 포즈 트랙도 기록대로 교체 |
| W04 프레임 범위 | 해결 | `frame_count=600` → 400 `프레임 수: 2~300` |
| W05 SOMA30 외 모델 | 해결 | GGUF 메타데이터에서 로컬 모델 `soma30` 판독, 미지원 모델은 선택 불가 |
| W06 공간·가중치 | 해결 | world·가중치 0/1만 허용. 저장된 「마보 자세」(world/1, 태그 없음)는 편집기에서 불러와지고 "기준 확인 필요" 표시, 타임라인 배치는 재저장 요구 |
| W07 기본 다운로드 | 해결 | 「모션 GLB」= `/outputs/<id>/animation.glb`, 「표시 캐릭터 GLB」= `/api/preview?...` 분리 |
| W08 런처 PID 강제종료 | **이번에 수정** | 아래 |
| W09 요청 출처 검사 | **이번에 수정** | 아래 |
| 배치·취소 | 해결 | API와 브라우저 둘 다: 3개 중 2번째 추론 중 취소 → 후보 1개 보존·재생, 워커 0개, 재시도 정상 |

## 골반 자동 고정을 되돌린 이유 (실측)

Codex는 손·발 위치 포즈에 골반 위치를 자동으로 붙이고(`keypose-editor.mjs`), 골반이 없으면 서버가 거부하게 했다.
C++ `build_pose_condition`(`vendor/kimodo.cpp/src/constraints.cpp`)은 손·발 위치를 루트 기준 XZ로 해석하고, 골반 제약이
없으면 루트를 0으로 둔다 — 편집기 캐릭터가 원점에 서 있으므로 기존 방식이 이미 맞았다. 골반을 넣으면 **전역 루트 XZ까지 고정**된다.

`a person walks forward`, 90f, seed 7, 60프레임 포즈:

| 조건 | 60프레임 루트 XZ |
|---|---|
| 포즈 없음 | (−0.01, 2.11) |
| 왼손만 | (−0.01, 2.11) — 루트 자유 |
| 왼손 + 골반 | (−0.03, −0.03) — **원점으로 끌려옴** |

→ 자동 추가와 서버 거부를 제거했다. 골반을 사용자가 직접 옮긴 경우에만 루트가 고정된다. 테스트
`test_hand_position_without_pelvis_leaves_root_free`로 고정.

## 별도로 확인된 한계 (이번 변경과 무관)

왼손 목표 `(0.3, 1.7, 0.2)`에 대해 실제 손 높이는 0.90m(제약 없음 0.87m). 제약 행은 `keypose_constraints.tsv`로 엔진까지
전달됐고(`persistent_worker=false`), 골반 포함 여부와 무관했다. 단일 프레임 희소 손 제약이 모델 조건만으로는 거의 반영되지
않는다 — 공식 구현의 제약 후처리(발 접촉 정보 필요, 현 `kmd-generate` 미출력)와의 비교가 다음 과제다.

## W09 — 변경 요청 출처 검사 (`webui/server.py` `_mutation_rejection`)

모든 POST에 적용: Host가 `127.0.0.1|localhost|[::1]:<port>`(또는 명시적 `--host`)가 아니면 403(DNS 리바인딩),
Origin이 있으면 같은 목록이어야 하며 아니면 403, `Content-Type: application/json`이 아니면 415(외부 페이지의 단순 요청은
CORS preflight를 강제당하고 서버는 허용하지 않는다). 유일하게 헤더가 없던 `/api/cancel` 호출도 JSON으로 바꿨다.
라이브: 같은 출처 200, 외부 Origin 403, text/plain 415, 리바인딩 Host 403, 폼 형식 기록 삭제 415. 테스트 `request_origin_test.py`.

## W08 — 런처 (`scripts/run-webui.ps1`, `scripts/prepare-webui-port.ps1`)

- preflight를 먼저 실행하고, 실패하면 아무것도 멈추거나 띄우지 않는다.
- 포트 소유자의 명령줄이 `webui\server.py`가 아니면 PID·명령줄을 보여주고 **종료하지 않고** 중단(exit 1).
- 이 WebUI면 생성 중인지 `/api/status`로 경고하고 `[y/N]` 확인. 거절하면 기존 서버를 브라우저로 연다(exit 3→0).
- 승인 시 `taskkill /T /F`로 추론 워커·포즈 에이전트 자식까지 회수. `-Restart`는 확인만 생략(다른 프로그램은 여전히 거부).
- 라이브: 더미 `http.server`(8199) → 거부·생존, 거절 → exit 3, `-Restart` → 서버와 자식 `claude.exe`·`kmd-generate.exe` 종료, VRAM 기준값 복귀.
- 메시지는 ASCII 영어로 바꿨다(기존 파일은 BOM 없는 UTF-8 한국어라 PowerShell 5.1에서 깨질 수 있었다).

## 테스트와 부산물

- Python 49개, Node 3개 통과.
- 라이브 검증으로 `output_motion/generations/`에 `20260927-11*` 테스트 결과 18개가 생겼다(git 밖). 사용자 요청으로 삭제했다. 그중 취소된 샘플 3개는 `meta.json` 없는 폴더만 남아 있었다 — 실패/취소 경로의 출력 폴더 정리가 후속 과제.
- `.codex-local/maps/process-map.md`의 "Launcher may replace an existing server" 문구는 이제 "이 WebUI일 때만 확인 후"로 바뀌었다(Codex 로컬 문서라 손대지 않음).

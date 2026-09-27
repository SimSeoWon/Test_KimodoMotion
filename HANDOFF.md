# Test_KimodoMotion 작업 인수인계

작성 기준: 2026-09-28 (Claude) · **목표는 NVIDIA Kimodo의 WebUI 래핑. 결함 W01~W09 해결, 포즈 편집기(표시 캐릭터 분리·해부학 검증 AI) 완료, 전부 커밋·push. 다음은 키포즈 기반 모션 생성 품질.**

이 파일은 Claude Code와 Codex가 이어받기 위한 현재 상태의 정본이다. 시작 시 이 파일부터 읽고 Git 상태는 다시 실측한다.
결정의 근거와 상세 검증은 `history/`에 남긴다.

## 최신 인계 — 2026-09-28 포즈 편집기 정비 (Claude)

### 이번 세션에서 끝난 것 (모두 `origin/main` 반영, 커밋 순)

| 커밋 | 내용 | 상세 |
|---|---|---|
| `6fa1609` | Codex 중단분(W01~W07) 재검증 + W08(런처)·W09(요청 출처 검사) 수정. 손·발 포즈의 골반 자동 고정은 **되돌림**(루트가 원점에 끌려옴) | [`history/2026-09-27_webui-fixes-live-verification.md`](history/2026-09-27_webui-fixes-live-verification.md) |
| `2a6ce66` | 취소·실패 샘플의 출력 폴더 삭제 | 같은 기록 후속 절 |
| `4717af8` | 미리보기·T포즈 캐시를 입력 지문(바인딩·내보내기 스크립트 크기·수정 시각)으로 무효화, `no-store` | 같은 기록 후속 절 |
| `a98333c` `90d9516` | 포즈 편집기: 표시 캐릭터 선택, **저장·IK·AI 스냅샷은 SOMA 기준 리그**, 반투명 기준 캡슐 매 프레임 동기화 | [`history/2026-09-27_pose-editor-display-vs-canonical.md`](history/2026-09-27_pose-editor-display-vs-canonical.md) |
| `6529c45` | 포즈 AI를 **해부학 각도 명령 + Python FK/IK/가동 범위 검증**으로 전환. 요청당 2분 안팎 → 5~9초 | [`history/2026-09-27_pose-anatomy-validator.md`](history/2026-09-27_pose-anatomy-validator.md) |

### 알아둘 구조 (새로 생긴 규칙)

- 포즈 AI: LLM은 `webui/pose_ops.py`의 `OPS_SCHEMA`(관절 각도 `set`/`add`, 골반·손발 `translate_m`, `turn_out_deg`, `keep_planted`)만 낸다.
  계산·검증은 `webui/pose_anatomy.py`, 범위 표·출처는 `webui/joint_limits.py`(AAOS 기준). 축·부호의 정본은 `webui/tests/pose_anatomy_test.py`.
  **명령은 전부 적용한 뒤 최종 자세만 검증**한다(사용자 지적: 순차 검증은 교착). 손발 이동은 편집 시작 위치 기준.
- Claude CLI 런타임은 둘: `POSE_CLI_RUNTIME`(각도 명령, `--effort low`, `KIMODO_POSE_AGENT_EFFORT`), `LEGACY_POSE_CLI_RUNTIME`(쿼터니언 방식, `bone_state` 없는 요청만).
- 편집기는 AI 요청에 `bone_state`(기준 리그 전체 뼈)를 보내고, 응답의 `bone_state`를 IK 재해석 없이 그대로 적용한다.
- 런처(`run-webui.bat`): preflight 먼저, 포트 주인이 이 WebUI일 때만 `[y/N]` 확인 후 자식까지 종료. 다른 프로그램은 건드리지 않는다.

### 실측 상태 (2026-09-28)

- `main` = `origin/main` = `6529c45`(+이 인계 커밋). 작업 트리 깨끗. 서브모듈 `88cbfbc` 변경 없음.
- 8188·8190 리스너 없음, `kmd-generate` 0개 — 세션 중 띄운 검증 서버는 모두 종료했다(사용자 서버는 그사이 사용자가 닫음).
- 테스트: Python 78개, Node 3개 통과.
- 브라우저 검증은 로컬 Chrome을 CDP 헤드리스로 띄워 했다(Claude in Chrome 확장은 다른 기기 브라우저에 붙어 있어 127.0.0.1에 닿지 않음). 스크립트는 저장소 밖.

### 사용자 쪽 진행 상황

- 링크드인 영상 준비 중: 포즈 편집기 + LLM 포즈 수정 흐름. 추천 포즈는 하체 중심(마보·런지·스쿼트) — 생성 모델이 손 위치 제약은 약하게 따른다.
- 게시글 초안(3단계 워크플로)을 함께 다듬었다. 게시 여부는 사용자 몫.

### 다음 작업 (제안, 미결정)

1. **포즈 검증 후속:** 기즈모로 직접 만든 포즈에 위반 경고 표시, 캐릭터별 유연성(`validate(flexibility=)`) UI, 근거 약한 값 보강(체중 부하 배굴 45°·흉요추·쇄골·과신전 −5°), 필요 시 MCP 노출.
2. **키포즈 반영 품질:** 단일 프레임 손 위치 제약이 거의 반영되지 않는다(목표 1.7m → 0.9m). 공식 `nv-tlabs/kimodo`의 제약·후처리와 비교 — 발 접촉 출력을 포크 `motion/main`에 추가할지는 사용자 결정.
3. 운영 개선: 결과 GLB 오류 표시, README/구형 MCP(`scripts/keypose_mcp.py`) 문서 정리.
4. Codex: `.codex-local/maps/process-map.md`의 "Launcher may replace an existing server" 문구를 새 런처 동작으로 갱신.

## 과거 상세 기록

- [2026-09-27 W01~W09 인계](docs/handoff/archive/HANDOFF_2026-09-27_w01-w09.md): 결함 수정·라이브 재검증 세부.
- [2026-09-27 Codex 중단분 대필 인계](docs/handoff/archive/HANDOFF_2026-09-27_codex-interrupted.md): Codex 미완 diff 요약.
- [2026-09-27 검증 보고 인계](docs/handoff/archive/HANDOFF_2026-09-27_audit.md): WebUI 래퍼 검증, W01~W09 결함 목록.
- [이전 2026-09-27 인계](docs/handoff/archive/HANDOFF_2026-09-27.md): 마네킹 미리보기, 포크 통합 브랜치, NS 후속 요청.
- 그 전 경위는 `history/`의 날짜별 기록을 참고한다.

## 인계 규칙 (Claude · Codex 공통)

- 시작: 이 파일 → 로컬 초기화 지침 → 최신 관련 `history/`. 작업 트리·서브모듈·프로세스는 새로 확인한다.
- 사용자가 결과를 확인했거나 중요한 결정을 내리면 경위를 `history/YYYY-MM-DD_<주제>.md`에 기록한다.
- 머리말과 최신 인계는 현재 상태로 **다시 쓴다**. 이전 본문은 `docs/handoff/archive/`에 보존한다. 같은 날짜 아카이브가 있으면 덮어쓰지 않고 구별되는 이름을 쓴다.
- 다음 할 일은 파일·검증·남은 사용자 결정을 구체적으로 적는다. 실측·추정·제안을 구분한다.
- 두 에이전트가 알아야 할 내용은 이 파일이나 `history/`에 둔다. `.codex-local/`·`.claude/`는 공용 인계 문서가 아니다.

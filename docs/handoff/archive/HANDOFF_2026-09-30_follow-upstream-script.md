# Test_KimodoMotion 작업 인수인계

작성 기준: 2026-09-30 (Claude, AX 마스터 세션) · **목표는 NVIDIA Kimodo의 WebUI 래핑. 이번에는 `kimodo.cpp` 원본 따라가기를 스크립트로 만들었다(AX `#694`). 실물 첫 실행은 아직이다. 그 앞의 포즈 편집기 정비 인계는 아카이브에 있다.**

이 파일은 Claude Code와 Codex가 이어받기 위한 현재 상태의 정본이다. 시작 시 이 파일부터 읽고 Git 상태는 다시 실측한다.
결정의 근거와 상세 검증은 `history/`에 남긴다.

## 최신 인계 — 2026-09-30 원본 따라가기 스크립트 (Claude, AX 마스터)

### 이번 세션에서 끝난 것

| 무엇 | 상세 |
|---|---|
| `scripts/follow-upstream.ps1` — README 따라가기 규칙을 순서대로 집행(merge → 빌드·ctest → 포크 push → 포인터 검사 → 루트 포인터 커밋), 어긋나면 거절, 충돌은 사람에게. `-DryRun` | [`history/2026-09-30_follow-upstream-script.md`](history/2026-09-30_follow-upstream-script.md) |
| `scripts/tests/follow_upstream_test.ps1` — 임시 샌드박스에서 실제 git, cmake/ctest 대역. `.33` 에서 **24/24 통과** | 같은 기록 |
| 스킬 `kimodo-follow-upstream` — Claude `.claude/skills/` · Codex `.agents/skills/` (같은 내용, 입구만) | 같은 기록 |
| README 「kimodo.cpp 포크와 서브모듈」에 스크립트 사용법 · `.gitignore` 에 `/logs/` | — |

### 알아둘 것

- **커밋 기준이 Gitea 다** (사용자 결정 2026-09-30): `gitea@192.168.0.57:Sim/KimodoMotion_WebUI.git`.
  `.33` 작업 클론은 `C:\Users\USER\Documents\KimodoMotion_WebUI`. 원래 클론 `Test_KimodoMotion`(GitHub)은 그대로 있다 — 두 곳이 갈라질 수 있다.
- 서브모듈 포크(`SimSeoWon/kimodo.cpp`, GitHub)는 그대로다. 스크립트가 push 하는 곳은 포크의 `motion/main` 이고, 루트 push 는 사람이 한다.
- 스크립트는 `KIMODO_BUILD_TESTS=ON` 으로 빌드한다. 테스트 0개 실행은 실패로 친다.

### 실측 상태 (2026-09-30 01:30)

- `main` = `origin/main`(Gitea) = 이 인계 커밋. 서브모듈 고정 `88cbfbc` 변경 없음.
- `.33` Gitea 클론: 서브모듈 초기화 완료(`kimodo.cpp` `88cbfbc` · `ggml` `8c63e70` v0.20.2) · `upstream` 원격 추가(스크립트) ·
  서브모듈은 `motion/main`(origin 추적) · **빌드 없음**. 원래 클론 `Test_KimodoMotion` 은 손대지 않았다.
- 실물 실행: `-DryRun` → *"motion/main already contains upstream/main"* · 실행 → *"Already up to date"* exit 0 (빌드 전에 끝남).
  **원본 `upstream/main` 은 아직 `5679ff1` 이다(09-27 과 같다) — 지금 따라갈 것이 없다.**

### 다음 작업

1. **원본이 움직이면 그때 처음으로 빌드·테스트까지 돈다.** 테스트를 켠 첫 전체 빌드라 오래 걸리고(`.33` 자원),
   모델 번들·패리티 픽스처가 필요한 테스트가 통과하는지 **아직 모른다** — 실패하면 스크립트가 exit 4 로 멈춘다.
   미리 재 둘지(기준선 빌드 1회), `-CtestArgs -E <regex>` 로 뺄지는 사용자 결정.
2. `CLAUDE.md` 「빌드 / 실행 명령」의 `-DKIMODO_BUILD_TESTS=OFF` 와 AGENTS.md 의 ON 이 다르다 — 맞출지 사용자 결정.
3. 이전 인계의 다음 작업(포즈 검증 후속 · 키포즈 반영 품질 · 운영 개선 · Codex 프로세스 맵 문구)은 그대로 열려 있다 —
   [`docs/handoff/archive/HANDOFF_2026-09-28_pose-editor.md`](docs/handoff/archive/HANDOFF_2026-09-28_pose-editor.md).

## 과거 상세 기록

- [2026-09-28 포즈 편집기 정비 인계](docs/handoff/archive/HANDOFF_2026-09-28_pose-editor.md): 포즈 AI 해부학 검증 전환, 표시·기준 리그 분리, 다음 작업 목록.
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

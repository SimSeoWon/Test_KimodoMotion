# Test_KimodoMotion 작업 인수인계

작성 기준: 2026-09-30 21:45 (Claude, AX 마스터 세션) · **목표는 NVIDIA Kimodo의 WebUI 래핑. 이번에는 `kimodo.cpp` 원본 따라가기 스크립트의 빌드·테스트 단계를 실측하고 기준선을 정했다(AX `#694`). 스크립트는 이제 끝까지 갈 수 있는 상태다 — 원본이 아직 움직이지 않아 전체 경로 실물은 아직이다.**

이 파일은 Claude Code와 Codex가 이어받기 위한 현재 상태의 정본이다. 시작 시 이 파일부터 읽고 Git 상태는 다시 실측한다.
결정의 근거와 상세 검증은 `history/`에 남긴다.

## 최신 인계 — 2026-09-30 따라가기 테스트 기준선 · SOMA 스모크 (Claude, AX 마스터)

### 이번 세션에서 끝난 것

| 무엇 | 상세 |
|---|---|
| 기준선 빌드 실측(`.33`) — 빌드 통과, ctest 16건 중 4건 통과. 실패는 DLL 경로(11) + 저장소에 없는 입력(SMPL-X GGUF · llm2vec fixture) | [`history/2026-09-30_follow-upstream-baseline.md`](history/2026-09-30_follow-upstream-baseline.md) |
| `scripts/follow-upstream.ps1` — ctest 앞 `build\bin\Release` PATH 추가 · 기본 `-CtestArgs` 가 입력 없는 11건 제외 · ctest 뒤 SOMA 생성 스모크(`-SmokeModel` · `-SmokeJoints 30`) · 모델 없으면 병합 전 exit 2 | 같은 기록 · 커밋 `4e89435` |
| 시나리오 테스트 — 대역을 컴파일 exe 로 교체(`-E` 정규식의 `\|` 를 cmd 가 파이프로 읽음). `.33` **36/36** | 같은 기록 |
| README 「테스트 기준선」 · 스킬 두 벌 종료 코드 표 | — |

### 알아둘 것

- **커밋 기준은 Gitea 다**: `gitea@192.168.0.57:Sim/KimodoMotion_WebUI.git`. `.33` 작업 클론은 `C:\Users\USER\Documents\KimodoMotion_WebUI`.
  원래 클론 `Test_KimodoMotion`(GitHub)은 그대로 있다 — 두 곳이 갈라질 수 있다.
- **기준선은 5건 + SOMA 스모크다** (사용자 결정 2026-09-30). constraints · capi · diffusion · converter · quantization-metrics.
  나머지 11건은 입력이 없어서 뺐다 — **통과한 적이 없는 테스트이지 깨진 테스트가 아니다.** `-CtestArgs @()` 로 16건 전부를 돌릴 수 있다.
- SMPL-X GGUF(`kimodo-smplx-rp-v1-f32.gguf`)는 원본 README 가 *"local-conversion only"* 라고 적은 모델이다(NVIDIA 내부 R&D 라이선스).
  `Test_KimodoMotion` 에도 없다. fixture 를 만드는 스크립트는 `scripts`·`docs`·`tests` 에서 찾지 못했다(`reference/` 는 안 봤다).
- `kimodo-generate-smoke` 의 관절 수 기본값은 22(SMPL-X)다 — SOMA 는 **30** 을 넘겨야 한다. 안 넘기면 오류 메시지 없이 rc=1.

### 실측 상태 (2026-09-30 21:39)

- `main` = `origin/main`(Gitea) = 이 인계 커밋. 서브모듈 고정 `88cbfbc` 변경 없음.
- `.33` Gitea 클론: `4e89435` 로 fast-forward · 작업 트리 깨끗 · **`vendor\kimodo.cpp\build\` 있음**(기준선 빌드, 테스트 켬) ·
  **SOMA 모델 복사함** `vendor\kimodo.cpp\models\kimodo-soma-rp-v1.1-f32.gguf`(1.1GB, `Test_KimodoMotion` 과 SHA256 일치, gitignore 대상).
- 스크립트 실물 실행: 모델 검사 통과 → *"Already up to date"* exit 0. **원본 `upstream/main` 은 아직 `5679ff1`** — 병합·빌드·스모크 단계는 원본이 움직여야 처음 돈다.
- 실물로 잰 것: 기본 `-E` 로 `.33` 빌드에서 ctest 5/5 · SOMA 스모크 30 관절 rc=0(1.1초, 두 번).

### 다음 작업

1. **원본이 움직이면** 스킬 `kimodo-follow-upstream`(드라이런 → 승인 → 실행). 병합 뒤 빌드·5건·스모크를 **처음으로 한 번에** 돈다 — 그 실행이 이 경로의 첫 실물이다.
2. [사용자 결정] SMPL-X 모델·fixture 로 기준선을 넓힐지(라이선스 판단 포함).
3. [사용자 결정] `CLAUDE.md` 「빌드 / 실행 명령」의 `-DKIMODO_BUILD_TESTS=OFF` 와 AGENTS.md·스크립트의 ON 이 다르다 — 맞출지.
4. 이전 인계의 다음 작업(포즈 검증 후속 · 키포즈 반영 품질 · 운영 개선 · Codex 프로세스 맵 문구)은 그대로 열려 있다 —
   [`docs/handoff/archive/HANDOFF_2026-09-28_pose-editor.md`](docs/handoff/archive/HANDOFF_2026-09-28_pose-editor.md).

## 과거 상세 기록

- [2026-09-30 따라가기 스크립트 인계](docs/handoff/archive/HANDOFF_2026-09-30_follow-upstream-script.md): 스크립트·스킬 작성, 첫 실물 실행(이미 최신).
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

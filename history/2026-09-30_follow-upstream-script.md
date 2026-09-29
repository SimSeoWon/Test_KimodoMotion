# 2026-09-30 — kimodo.cpp 원본 따라가기를 스크립트로 (Claude, AX 마스터 세션)

AX 일감 `#694`(Redmine `kimodo` 프로젝트). README 「kimodo.cpp 포크와 서브모듈」의 따라가기 절차가
산문으로만 있어서 단계를 건너뛸 수 있었다 — 2026-09-27 에 서브모듈이 `main` 으로 체크아웃된 채
커밋돼(`313e519`) 로컬 기능이 빠졌던 것이 그 부류다. 스크립트가 순서와 거절을 집행하게 했다.

## 사용자 결정

- 커밋 기준은 **Gitea** (`gitea@192.168.0.57:Sim/KimodoMotion_WebUI.git`). 작업 클론은
  `.33` `C:\Users\USER\Documents\KimodoMotion_WebUI`(Gitea 클론). 원래 클론 `Test_KimodoMotion`(GitHub)은 그대로 둔다.
- 작성은 AX 마스터가 하고 Gitea 로 push, 실측은 `.33` 에서.
- 스킬은 이 저장소 안에 — Claude `.claude/skills/`, Codex `.agents/skills/`. 본문은 입구만 두고 규칙은 README·스크립트에.
- 서브모듈 구조 유지 · rebase 금지(기존 README 규칙 그대로).

## 만든 것

- `scripts/follow-upstream.ps1` — ① fetch → `motion/main` → `merge upstream/main` ② 빌드 + `ctest`
  ③ `push origin motion/main` ④ 새 커밋이 `origin/motion/main` 에 있고 기존 고정 커밋의 자손인지 검사
  ⑤ 루트 포인터 커밋. 루트 push 는 하지 않는다.
  - 거절(2): 루트에 포인터 밖 변경 · 서브모듈에 미커밋 변경 · 서브모듈이 다른 브랜치 · 로컬/원격 `motion/main` 분기 ·
    기존 고정 커밋이 조상이 아님 · `kmd-generate` 실행 중(빌드가 exe 를 바꾼다 — 사용자 프로세스를 끄지 않는다)
  - 충돌(3): `merge --abort` 도 자동 해결도 하지 않고 넘긴다. 해결·커밋 뒤 다시 실행하면 **이어서** 한다
    (로컬이 원격보다 앞선 상태를 재개로 받는다)
  - 빌드·테스트 실패(4): push 전에 멈춘다. **테스트 0개도 실패다** — 기존 빌드는 `KIMODO_BUILD_TESTS=OFF` 라
    그대로 `ctest` 를 돌리면 0개 「통과」가 나온다. 그래서 스크립트는 `-DKIMODO_BUILD_TESTS=ON` 으로 구성한다
  - `-DryRun`: fetch 만 하고 들어올 커밋과 규모를 보여 준다
  - 로그: `logs\follow-upstream\<시각>.log` (`.gitignore` 에 `/logs/` 추가 — 안 하면 스크립트가 자기 로그 때문에
    「루트가 더럽다」며 자신을 거절한다)
  - 스크립트는 **ASCII 영문**이다 — Windows PowerShell 5.1 은 BOM 없는 UTF-8 `.ps1` 의 한글을 깨뜨린다
- `scripts/tests/follow_upstream_test.ps1` — `%TEMP%` 샌드박스(원본 bare · 포크 bare · 서브모듈을 문 루트)에서
  **실제 git** 으로 여덟 장면을 잰다. cmake/ctest 는 대역(`FU_BUILD_FAIL`·`FU_TEST_FAIL`·`FU_TESTS`).

## 검증

`.33` 에서 하네스 **24/24 통과** (git 2.53.0.windows.1, Windows PowerShell 5.1):
최신이면 0 · 더러운 루트 2 · 다른 브랜치 2(그 브랜치에 그대로 둔다) · 드라이런은 아무것도 안 바꾼다 ·
테스트 0개 4 · 테스트 실패 4(포크 push 없음, 병합은 로컬에 남음) · 재개 → push·포인터 커밋(포인터 한 줄만,
기존 고정의 자손, 로컬 기능 보존, 루트 push 없음) · 충돌 3(병합 진행 중으로 남김, 재실행도 3, 포인터 불변).

처음 돌렸을 때 잡힌 것 둘: 문자열 안 `$Branch:` 를 PowerShell 이 드라이브 범위 변수로 읽어 **스크립트가 파싱부터
실패**했다(→ `${Branch}:`), 하네스의 `-D` 가 함수 매개변수 `-Dir` 의 접두 일치로 먹혔다.

## 실물 실행 (.33 Gitea 클론, 01:30)

`git pull --ff-only`(작업 트리 깨끗 확인 뒤) → `git submodule update --init --recursive`(`kimodo.cpp` `88cbfbc` ·
`ggml` `8c63e70`) → `-DryRun`: `upstream` 원격을 추가하고 fetch, *"motion/main already contains upstream/main"* →
실행: 분리 상태를 `motion/main`(origin 추적)으로 옮기고 *"Already up to date"* exit 0. 루트 `git status` 빈 출력.
원본 `upstream/main` 은 `5679ff1` 그대로 — **지금은 따라갈 것이 없다.** 드라이런 설명을 「아무것도 안 바꾼다」에서
「브랜치·커밋은 안 바꾼다(원격이 없으면 추가하고 fetch)」로 고쳤다 — 실측이 그 문구를 반증했다.

## 남은 것

- **빌드·테스트 경로는 실물로 아직 안 돌았다**(원본이 움직여야 돈다). 서브모듈은 초기화했지만 Gitea 클론에는 빌드가
  없어서, 그때가 테스트를 켠 첫 전체 빌드다. 모델 번들·패리티 픽스처가 필요한
  테스트는 자동으로 받지 않으므로 **지금의 `ctest` 기준선이 전부 통과하는지부터** 재야 한다 — 이미 실패하는 테스트가
  있으면 스크립트가 매번 거기서 멈춘다(그때 `-CtestArgs -E <regex>` 를 쓸지는 사용자 결정).
- `CLAUDE.md` 「빌드 / 실행 명령」은 `-DKIMODO_BUILD_TESTS=OFF` 로 적혀 있다(AGENTS.md 는 ON). 손대지 않았다.

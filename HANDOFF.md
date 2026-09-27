# Test_KimodoMotion 작업 인수인계

작성 기준: 2026-09-27 · **UE 마네킹(Quinn) 미리보기 추출 완성(A-포즈→T-포즈 변환·텍스처 색, 웹 UI 에서 사용자 확인), Claude·Codex 공용
인수인계 도입, 9/19 세션의 미커밋 작업까지 모두 커밋** · 작업 트리 깨끗함.

이 파일은 Claude Code 와 Codex 가 같은 자리에서 이어받기 위한 **현재 상태의 정본**이다. 세션을 시작하면 이 파일부터
읽고, 끝낼 때 「최신 인계」를 갱신한다(규칙은 맨 아래 「인계 규칙」). 결정의 상세 경위는 `history/` 에 있다.

## 최신 인계 — 2026-09-27

### 시작점과 문서

- 이 리포가 무엇인지: `README.md`. 에이전트 규약: Claude 는 `CLAUDE.md`, Codex 는 `AGENTS.md`(+ 로컬 `.codex-local/INDEX.md`).
- 최신 결정 기록: [`history/2026-09-27_mannequin-apose-preview-report.md`](history/2026-09-27_mannequin-apose-preview-report.md) —
  마네킹을 미리보기·리타겟에 쓰기 위한 조사와 계획. 그 앞은 `history/2026-09-19_*.md` 3개(공식 데모 병합, 영구 진단 로그,
  미리보기 캐릭터 재생 설정).
- 이 작업을 요청한 쪽: `NS` 프로젝트(`C:\Users\USER\Documents\NS`)의 보법 발 애니메이션(NS 레드마인 #692). NS 는 캡슐만
  움직이는 스텝 구동기까지 구현했고(커밋 `119d40b`), 발 애니메이션용 스텝 클립을 이 리포에서 뽑으려 한다.

### 작업 트리 상태 (2026-09-27 실측)

- **미커밋 변경 없음.** 9/19 세션의 WebUI 작업은 `f41783e`(기능)·`99516b3`(테스트)로, 서브모듈 포인터는 위 절대로 `811eceb` 로 되돌렸고, 루트 서버 콘솔 로그 제외는 `7a90a0e` 로 커밋했다. 이번 차례의 마네킹·인계
  작업은 `af4f2d9`. `webui/tests` Python 테스트 31개 통과(2026-09-27).
- `vendor/kimodo.cpp` 안에 추적 안 되는 `demo-server.*.log` 가 있다(서브모듈 쪽 파일 — 루트에서 손대지 않았다).
- **`KimodoTestbed/` 가 비어 있다.** `CLAUDE.md` 가 설명하는 `KimodoImportLibrary.*`(`RunIK`) · `Kimodo.ImportIK` 소스가 이
  경로에 없다. git 밖(로컬 전용)이라 복구는 사용자 백업뿐이다 — 리타겟 작업 전에 행방을 묻는다.
- git 밖 산출물: `assets/mannequin_src/SKM_Quinn_Simple.FBX` · `T_Quinn_01_D.PNG` · `T_Quinn_02_D.PNG`(사용자가 NS 에서 내보냄) →
  `assets/mixamo_processed/quinn_simple_soma30_bind.json`.

### 서브모듈 포인터 — 한 번 잘못 커밋했다가 되돌렸다 (2026-09-27)

`313e519`(Claude 커밋)가 `vendor/kimodo.cpp` 를 `811eceb` → `5679ff1` 로 바꿨는데, `5679ff1` 은 `811eceb` 의 **부모**라 포크의
로컬 커밋(부정 프롬프트 CFG·포즈 제약 — WebUI 가 쓰는 기능)을 빼는 커밋이었다. 9/19 세션이 서브모듈을 `main` 으로 체크아웃해 둔
작업 트리를 조상 관계 확인 없이 커밋한 것이다. 사용자 결정으로 루트 커밋 하나로 되돌렸다 — 서브모듈을 포크 브랜치
`local/negative-prompt-cfg-and-pose-constraints`(`811eceb`)로 체크아웃하고, 포인터를 `811eceb` 로, `.gitmodules` URL 을 포크로
바꿨다(그 커밋은 포크에만 있다). 포크 쪽에는 새 커밋이 없다. 구조와 규칙은 `README.md` 「kimodo.cpp 포크와 서브모듈」.

### 이번에 확정·정리한 것

- **UE5 마네킹 레퍼런스 포즈는 A-포즈(위팔 수평 아래 52.9°, 실측), SOMA30·Y Bot 은 T-포즈.** 미리보기와 리타겟의 팔
  문제는 같은 원인(레스트 자세 불일치)을 공유한다.
- **마네킹 미리보기는 해결됐다.** Blender 에서 팔·다리 체인을 T-포즈로 편 뒤 추출하면 Kimodo 회전이 그대로 맞는다 —
  같은 모션을 Y Bot 과 Quinn 으로 렌더해 자세 일치를 확인했다. Simple 메시는 웨이트가 트위스트 본에 있고 FBX 에 LOD0~2 가
  함께 들어오는 점을 스크립트가 처리한다(보고서 「1번 결과」).
- 리타겟 팔 꺾임은 15일 기록의 「원본(SOMA) 쪽 보정」보다 **대상(Manny) 쪽 리타겟 포즈를 T-포즈로 맞추는 것**
  (`UIKRetargeterController::AutoAlignAllBones(Target)` 등, 5.8 헤더에서 실재 확인)을 먼저 시도할 가치가 있다.
- 마네킹 원본·가공물은 Mixamo 와 같이 **git 에 올리지 않는다**(보고서 「라이선스」).

### 다음 세션에서 할 일

0. [주의] **추출을 다시 돌리면 웹 UI 미리보기 캐시를 지운다** — `webui/static/tpose_<id>.glb` 와 생성 결과 폴더의
   `preview_v2_<id>.glb` 는 파일이 있으면 다시 만들지 않는다(`server.py` 의 `ensure_tpose_variant`·`ensure_preview_variant`).
   2026-09-27 에 색을 넣은 뒤에도 옛 회색 캐시가 보였다. 바인딩 파일 수정 시각으로 캐시를 무효화하도록 `server.py` 를
   고칠지는 사용자 결정을 기다린다.
1. 웹 UI 에서 Quinn 애니메이션과 색은 사용자가 확인했다(2026-09-27). Manny 도 원하면 NS 에서 `SKM_Manny_Simple` FBX 와
   `T_Manny_01_D`·`T_Manny_02_D` 를 `assets/mannequin_src/` 에 내보낸 뒤 같은 스크립트에 `--fbx` 로 돌리고 캐시를 지운다.
2. 사용자에게 두 가지를 확인한다 — ① 다음 범위(보고서 계획 2 리타겟 팔 꺾임 추천, 3 보법 프리셋, 4 루트 이동 보존),
   ② `KimodoTestbed` 소스의 행방(2번의 전제).
3. WebUI·UE 에디터·Claude 데몬 같은 실행 중 프로세스는 시작·종료 전에 PID 와 함께 승인을 받는다(`AGENTS.md`
   「Runtime Process Consent」, 보이는 콘솔로만).

## 과거 상세 기록

이 파일을 처음 만든 날이라 이전 인계본은 없다. 그 전의 경위는 `history/` 의 날짜별 기록에 있다. 이후 「최신 인계」를
교체할 때 이전 본문은 `docs/handoff/archive/HANDOFF_<날짜>.md` 로 옮긴다.

## 인계 규칙 (Claude · Codex 공통)

- **시작:** 이 파일 → 「시작점과 문서」가 가리키는 최신 `history/` 기록 순으로 읽는다. 작업 트리 상태는 적힌 내용을 믿지 말고
  `git status` 로 다시 확인한다(다른 에이전트가 그 사이에 바꿨을 수 있다).
- **끝:** 사용자가 결과를 확인했거나 중요한 결정을 내렸으면 —
  1. 결정의 경위는 `history/YYYY-MM-DD_<주제>.md` 에 남긴다(기존 규칙 그대로).
  2. 이 파일 머리말(작성 기준)과 「최신 인계」를 **현재 상태로 다시 쓴다.** 덧붙여 쌓지 않는다 — 길어지면 이전 본문을
     `docs/handoff/archive/HANDOFF_<날짜>.md` 로 옮기고 「과거 상세 기록」에서 링크한다.
  3. 「다음 세션에서 할 일」은 다른 에이전트가 맥락 없이 바로 시작할 수 있게 구체적으로(파일·명령·확인할 사람 결정) 적는다.
- 사실과 계획을 섞지 않는다 — 실측한 것은 날짜와 함께 「실측」으로, 추정은 「추정」으로 적는다.
- `.codex-local/`(Codex 로컬 메모리)과 `.claude/` 의 개인 설정은 인계 대상이 아니다. 두 에이전트가 모두 알아야 하는 것은
  이 파일이나 `history/` 에 적는다.

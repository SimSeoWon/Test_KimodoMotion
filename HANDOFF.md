# Test_KimodoMotion 작업 인수인계

작성 기준: 2026-09-27 · **UE 마네킹(Quinn) 미리보기 추출 완성(A-포즈→T-포즈 변환, 렌더로 확인), Claude·Codex 공용 인수인계 도입** ·
웹 UI·서버 코드는 바꾸지 않았다 · 2026-09-19 세션의 **미커밋 변경 14개 파일이 그대로 남아 있다**(아래 「작업 트리 상태」).

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

- **미커밋 변경 14개 파일** — 2026-09-19 세션(공식 데모 병합·영구 진단 로그)의 작업이다: `.gitignore` · `AGENTS.md` ·
  `history/2026-09-19_official-demo-feature-merge.md` · `history/2026-09-19_persistent-diagnostic-logs.md` · `run-webui.bat` ·
  `scripts/pretty_export_glb.py` · `webui/config.json` · `webui/diagnostic_log.py` · `webui/server.py` · `webui/static/app.js` ·
  `webui/static/index.html` · `webui/static/style.css` · `webui/tests/diagnostic_log_test.py`, 그리고 서브모듈 포인터
  `vendor/kimodo.cpp`(`811eceb` → `5679ff1`). 커밋 여부는 사용자가 정한다 — 에이전트가 임의로 커밋하거나 되돌리지 않는다.
- 9/19 세션의 추적 안 되는 파일: `history/2026-09-19_preview-character-playback.md` · `scripts/find-python.ps1`
  (커밋할 대상으로 보인다 — 사용자 확인), 로그 `demo-server.stderr.log` · `demo-server.stdout.log`(ignore 대상 후보).
- **`KimodoTestbed/` 가 비어 있다.** `CLAUDE.md` 가 설명하는 `KimodoImportLibrary.*`(`RunIK`) · `Kimodo.ImportIK` 소스가 이
  경로에 없다. git 밖(로컬 전용)이라 복구는 사용자 백업뿐이다 — 리타겟 작업 전에 행방을 묻는다.
- 이번 차례(2026-09-27)에 추가·수정한 것: `HANDOFF.md`(이 파일) · `history/2026-09-27_mannequin-apose-preview-report.md` ·
  `assets/extract_mannequin_soma30.py`(신규) · `.gitignore`(`assets/mannequin_src/` 제외 한 줄) · `CLAUDE.md`·`AGENTS.md`(인계 절).
  git 밖 산출물: `assets/mannequin_src/SKM_Quinn_Simple.FBX` · `T_Quinn_01_D.PNG` · `T_Quinn_02_D.PNG`(사용자가 NS 에서 내보냄, 색은 텍스처에서 샘플) →
  `assets/mixamo_processed/quinn_simple_soma30_bind.json`. 이번 변경만 따로 커밋했다(`.gitignore`·`AGENTS.md` 는 이번 줄만 —
  같은 파일의 9/19 변경은 작업 트리에 미커밋으로 남아 있다).

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
   2026-09-27 에 색을 넣은 뒤에도 옛 회색 캐시가 보였다. 바인딩 파일 수정 시각으로 캐시를 무효화하는 수정은 `server.py` 의
   미커밋 변경과 섞이지 않게 사용자 결정을 기다린다.
1. (2026-09-27 사용자 확인: 웹 UI 에서 Quinn 애니메이션과 색 정상) 웹 UI 를 사용자가 다시 띄우면(프로세스는 사용자 승인 뒤에만) 결과 재생의 캐릭터 선택기에 `SKM_Quinn_Simple` 이 뜨는지,
   재생이 렌더와 같은지 사용자와 확인한다. Manny 도 원하면 같은 스크립트에 `--fbx assets\mannequin_src\SKM_Manny_Simple.FBX`.
2. 사용자에게 두 가지를 확인한다 — ① 다음 범위(보고서 계획 2 리타겟 팔 꺾임 추천, 3 보법 프리셋, 4 루트 이동 보존),
   ② `KimodoTestbed` 소스의 행방(2번의 전제).
3. 미커밋 14개 파일은 이 작업과 섞지 않는다 — 새 작업은 새 파일 위주로 하고, 커밋할 때 범위를 나눠 사용자에게 확인한다.
4. WebUI·UE 에디터·Claude 데몬 같은 실행 중 프로세스는 시작·종료 전에 PID 와 함께 승인을 받는다(`AGENTS.md`
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

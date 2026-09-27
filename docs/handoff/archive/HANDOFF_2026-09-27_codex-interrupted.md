# Test_KimodoMotion 작업 인수인계

작성 기준: 2026-09-27 (Claude 대필) · **목표는 NVIDIA Kimodo의 WebUI 래핑. 검증 보고서 W01~W09 중 일부를 Codex가 고치다 토큰 소진으로 중단 — 코드 변경이 미커밋·미검수 상태로 남아 있다.**

이 파일은 Claude Code와 Codex가 이어받기 위한 현재 상태의 정본이다. 시작 시 이 파일부터 읽고 Git 상태는 다시 실측한다.
결정의 근거와 상세 검증은 `history/`에 남긴다.

## 최신 인계 — 2026-09-27 W01~W07 수정 도중 중단 (Codex → Claude 대필)

### 경위

- 직전 인계(검증 보고서 작성까지)는 [`docs/handoff/archive/HANDOFF_2026-09-27_audit.md`](docs/handoff/archive/HANDOFF_2026-09-27_audit.md). 보고서: [`history/2026-09-27_webui-wrapper-audit.md`](history/2026-09-27_webui-wrapper-audit.md).
- 그 뒤 Codex가 **추론 워커 중복 적재(W01)·포즈 제약 전달(W02/W06)·배치 생성 확장·기록 복원(W03)**을 고치기 시작했다. 5시간 한도를 소진해 인계서 없이 멈췄고, 사용자가 붙여 준 Codex 화면 로그와 `git diff`를 근거로 Claude가 이 인계를 대신 썼다.
- **사람 검수·브라우저 확인·실GPU 생성은 아직 없다.** 아래 「변경 내용」은 diff에서 읽은 것이고 동작 확인이 아니다.

### 변경 내용 (미커밋, diff 기준)

- 새 파일: `webui/generation_contract.py`(요청 정규화·키포즈→제약 행 컴파일·GGUF 골격 판별), `webui/generation_batch.py`(단일 배치 진행 상태·취소 이벤트), `webui/static/generation-form.mjs`(기록→폼 전체 복원, 배치 개수), 테스트 3개(`generation_contract_test.py`, `generation_pipeline_test.py`, `generation_form_test.mjs`).
- `server.py`
  - W01: 단발 추론 전에 `PERSISTENT_GENERATOR.close()`로 상주 워커를 **종료 대기 후** 실행. `stop_child_process()`로 terminate→kill 순서 정리, 워커 응답에 1800초 타임아웃.
  - 전역 `cancel_requested` → `BATCH_STATE.cancel_event`. 배치 취소·실패 시 이미 끝난 후보 보존(Codex 설명).
  - 배치: 프롬프트·포즈·설정 고정, seed만 바꿔 여러 후보. 결과 메타에 `batch_id/index/count/base_seed`, `skeleton`, `fps`.
  - W05: 모델 목록에 `skeleton`/`supported`; SOMA30 아닌 모델은 생성 거부, 기본 모델도 지원 모델 중에서 고름.
  - `gen_id`에 uuid 접미사, 출력 디렉터리 `exist_ok=False`. export 단계도 취소 가능.
- 포즈(W02/W06): `keypose.py` 기본 space `character`→`world`, 포즈에 `skeleton: soma30` 태그. `pose_agent.py` 스키마를 world·weight=1로 제한. `keypose-editor.mjs`는 위치 제약이 있으면 Hips 월드 위치를 pelvis 앵커로 추가, 태그 없는 옛 포즈는 「기준 확인 필요」로 표시하고 재저장 유도.
  - **[미확인] 에디터 표시 리그 자체를 canonical SOMA30 비율로 바꿨는지는 불명확하다.** Codex는 "생성 모델 기준으로 저장하도록 바꾸는 중"이라고 말한 직후 중단했다 — W02의 핵심이 끝났는지 먼저 확인할 것.
- W04: `index.html` 프레임 입력 2~300(30fps·10초), 스토리보드 안내. W07은 다운로드 링크 스타일만 보이며 해결 여부 미확인.
- **손대지 않은 것(diff에 없음)**: W08 런처 PID 종료, W09 변경 요청 출처 검사, 서브모듈.

### 검증 (2026-09-27 Claude 실측)

- `py -3.12 -m unittest discover -s webui/tests -p '*_test.py'` → **46개 통과**(Codex 로그상 한때 1개 실패였으나 이후 테스트 수정으로 해소).
- `node --test webui/tests/*.mjs` → **3개 통과**. `node --check` app.js·keypose-editor.mjs 통과.
- 공식 후처리 조사(Codex): `nv-tlabs/kimodo`의 후처리는 관절 회전·루트 위치 외에 **발 접촉 정보**가 필요한데 현재 `kmd-generate.exe`는 이를 출력하지 않는다. 연결하려면 C++ 쪽에서 먼저 보존해야 한다(미구현).

### 작업 트리·프로세스 (2026-09-27 실측)

- 루트 HEAD `aced544`(`main`), 위 변경 전부 미커밋. 서브모듈 `88cbfbc`, 변경 없음.
- 8188 포트 리스너 없음, `kmd-*`·`UnrealEditor` 프로세스 없음.
- `KimodoTestbed/` 비어 있음, 로컬 가중치·Quinn 바인딩 등 git 밖 자산은 이전 인계와 동일.

### 다음 작업

1. 이 diff를 검수한다 — 특히 W02(에디터가 canonical SOMA30 리그로 포즈를 만드는지), 배치 취소 시 후보 보존, 상주 워커 종료 후 VRAM 해제.
2. WebUI를 띄워 브라우저로 배치 생성·기록 복원·옛 포즈 불러오기를 확인한다(서버 기동은 사용자 승인 후, GPU 사용 시 에디터 여부 확인).
3. 사용자가 확인하면 커밋하고 `history/`에 기록한다. 이어서 W07·W08·W09.
4. 공식 후처리 연결 여부는 사용자 결정 — 발 접촉 출력을 C++ 포크(`motion/main`)에 추가해야 한다.

## 과거 상세 기록

- [2026-09-27 검증 보고 인계](docs/handoff/archive/HANDOFF_2026-09-27_audit.md): WebUI 래퍼 검증, W01~W09 결함 목록.
- [이전 2026-09-27 인계](docs/handoff/archive/HANDOFF_2026-09-27.md): 마네킹 미리보기, 포크 통합 브랜치, NS 후속 요청.
- 그 전 경위는 `history/`의 날짜별 기록을 참고한다.

## 인계 규칙 (Claude · Codex 공통)

- 시작: 이 파일 → 로컬 초기화 지침 → 최신 관련 `history/`. 작업 트리·서브모듈·프로세스는 새로 확인한다.
- 사용자가 결과를 확인했거나 중요한 결정을 내리면 경위를 `history/YYYY-MM-DD_<주제>.md`에 기록한다.
- 머리말과 최신 인계는 현재 상태로 **다시 쓴다**. 이전 본문은 `docs/handoff/archive/`에 보존한다. 같은 날짜 아카이브가 있으면 덮어쓰지 않고 구별되는 이름을 쓴다.
- 다음 할 일은 파일·검증·남은 사용자 결정을 구체적으로 적는다. 실측·추정·제안을 구분한다.
- 두 에이전트가 알아야 할 내용은 이 파일이나 `history/`에 둔다. `.codex-local/`·`.claude/`는 공용 인계 문서가 아니다.

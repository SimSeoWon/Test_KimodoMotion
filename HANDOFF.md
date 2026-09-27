# Test_KimodoMotion 작업 인수인계

작성 기준: 2026-09-27 (Claude) · **목표는 NVIDIA Kimodo의 WebUI 래핑. 검증 보고서 W01~W09 전부 수정·라이브 재검증 완료, 커밋함.**

이 파일은 Claude Code와 Codex가 이어받기 위한 현재 상태의 정본이다. 시작 시 이 파일부터 읽고 Git 상태는 다시 실측한다.
결정의 근거와 상세 검증은 `history/`에 남긴다.

## 최신 인계 — 2026-09-27 W01~W09 수정 완료·라이브 재검증

### 경위와 근거

- Codex가 W01~W07을 고치다 토큰 한도로 중단 → Claude가 diff 전체를 재검증하고 W08·W09까지 마쳤다.
- 상세 판정·실측 수치: [`history/2026-09-27_webui-fixes-live-verification.md`](history/2026-09-27_webui-fixes-live-verification.md).
  결함 원 목록: [`history/2026-09-27_webui-wrapper-audit.md`](history/2026-09-27_webui-wrapper-audit.md).
- 사용자 결정(이번 세션): 라이브 검증 진행, **골반 자동 고정 되돌리기**, W08·W09 이어서 처리.

### 현재 상태 (실측)

- W01~W09 모두 해결. 실GPU 생성(W01·배치·취소·포즈 제약 전달), 헤드리스 Chrome(W02·W03·W06·W07·취소 버튼), curl(W09), 실제 런처 실행(W08)으로 확인.
- Codex 변경 중 **손·발 위치 포즈에 골반 자동 추가 + 서버 거부는 제거했다** — 실측으로 걷기 중간 프레임 포즈에서 루트가 원점으로 끌려왔다(2.11m→−0.03m).
- 취소·실패한 샘플은 출력 폴더를 지운다(`run_generation` → `remove_output_dir`, 라이브 확인). 상세 로그는 진단 로그에 남는다.
- 미리보기·T포즈 캐시는 바인딩 JSON·내보내기 스크립트 2개의 크기·수정 시각 지문을 파일 이름에 넣는다(`preview_fingerprint`). 지문이 바뀌면 다시 만들고 같은 캐릭터의 옛 파일은 지운다. 응답은 `no-store`. 다른 캐릭터의 옛 파일(`tpose_ybot.glb` 등)은 그 캐릭터를 요청할 때 정리된다.
- 포즈 편집기는 표시 캐릭터를 고를 수 있다(사용자 결정). 저장은 항상 SOMA 캡슐 기준이고, 반투명 캡슐로 실제 저장 자세를 겹쳐 보여준다 — [`history/2026-09-27_pose-editor-display-vs-canonical.md`](history/2026-09-27_pose-editor-display-vs-canonical.md).
- 테스트: Python 53개, Node 3개 통과.
- **알려진 한계(이번 변경과 무관):** 단일 프레임 손 위치 제약이 거의 반영되지 않는다(목표 1.7m, 결과 0.9m). 공식 후처리는 발 접촉 정보가 필요한데 `kmd-generate`가 출력하지 않는다.
- 로컬 Claude in Chrome 확장은 다른 기기의 브라우저에 붙어 있어 `127.0.0.1:8188`에 닿지 않는다. 브라우저 검증은 이 PC의 Chrome을 CDP 헤드리스로 띄워 했다(스크립트는 세션 임시 폴더, 저장소 밖).

### 작업 트리·프로세스

- `aced544` 위에 한 커밋으로 반영: `webui/{server,keypose,pose_agent,generation_contract,generation_batch}.py`, `webui/static/{app.js,index.html,style.css,keypose-editor.mjs,generation-form.mjs}`, `scripts/{run-webui,prepare-webui-port}.ps1`, 테스트 4개(신규 `request_origin_test.py` 포함), 문서(`HANDOFF.md`, `history/` 2개, `docs/handoff/`).
- 서브모듈 `88cbfbc` 변경 없음.
- 검증용으로 띄운 서버·워커는 모두 종료했다. 8188 리스너 없음, `kmd-generate` 0개, VRAM 기준값(~2.5GB).
- 라이브 검증 결과 18개(`output_motion/generations/20260927-11*`)는 사용자 요청으로 삭제했다.

### 다음 작업

1. 런처 동작이 바뀌었다: 다른 프로그램은 종료하지 않고, 이 WebUI일 때만 `[y/N]` 확인 후 자식까지 종료한다. `.codex-local/maps/process-map.md`의 옛 문구는 Codex가 다음에 갱신한다.
2. 제약 품질: 공식 `nv-tlabs/kimodo`의 제약·후처리와 비교. 발 접촉 출력을 포크 `motion/main`에 추가할지는 사용자 결정.
3. 남은 운영 개선(보고서 §3): 결과 GLB 오류 표시, README/구형 MCP 문서 정리.

## 과거 상세 기록

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

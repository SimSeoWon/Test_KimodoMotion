# WebUI 포즈 LLM 서브 에이전트

- date: 2026-09-17
- status: implemented
- scope: 자연어 포즈 명령, 백그라운드 LLM 실행, revision 기반 3D 모델 갱신

## 결정

별도 데몬을 추가하지 않고 기존 `kimodo-motion WebUI` 서버를 포즈 에이전트 데몬으로 사용한다.
HTTP 요청 스레드는 LLM 완료를 기다리지 않는다. `PoseAgentDaemon`이 단일 백그라운드 작업을
실행하고 `queued → running → complete|failed` 상태와 revision을 보관한다.

## 흐름

1. 포즈 페이지가 자연어 명령, 현재 `PoseAsset`, 13개 제어점의 world transform 스냅샷을
   `POST /api/pose-agent/command`로 보낸다.
2. WebUI 데몬이 도구 권한이 없는 비대화식 Claude 서브 에이전트를 실행한다.
3. 출력은 제어점 화이트리스트를 가진 JSON schema로 제한하고 서버에서 다시 검증한다.
4. 브라우저는 `GET /api/pose-agent/state`를 750ms 간격으로 읽는다.
5. complete revision을 받으면 결과 포즈를 현재 Three.js 본에 적용하고 기즈모 보정을 이어간다.

## 수정 기록

`PoseAsset`은 현재 제어점뿐 아니라 `revision`과 `edits`를 가진다. 에이전트 명령이 끝날 때마다
명령문, 요약, 변경된 제어점 ID, 해당 제어점의 before/after 값, UTC 시각, 행위자(`llm`)를
새 revision으로 추가한다. 완료된 live pose는 `webui/pose_agent_state.json`에 저장하며 서버
재시작 후 복원한다. 포즈 페이지에는 최근 수정 기록 8건을 표시한다.

AI 완료 결과는 현재 편집 draft에만 반영한다. `이 포즈 저장`을 누를 때 비로소 controls와
요청/before/after 이력을 포함한 `PoseAsset` 전체를 포즈 프리셋 파일에 기록한다. 저장 전 서버를
재시작하면 draft는 복원하지 않는다. `새 포즈 / 초기화`는 현재 포즈의 관절 수정·이름·AI 요청
기록을 모두 지울지 확인한 뒤 새 ID와 빈 이력을 만들며, 저장된 다른 포즈는 삭제하지 않는다.
기존 저장 revision은 감사 기록이므로 수정은 다음 revision으로 남긴다.

## 안전 경계

- 동시에 하나의 포즈 작업만 실행한다.
- LLM에는 셸·파일 도구를 주지 않는다.
- 알 수 없는 제어점, 비정상 벡터, 잘못된 quaternion과 범위 밖 weight는 적용 전에 거부한다.
- PoseAsset의 수정 이력은 저장하지만 LLM 입력에는 현재 이름과 controls만 보내 누적 팽창을 막는다.
- 스냅샷도 current/rest transform만 보내고 structured-output schema는 공통 `$defs`를 재사용한다.
- LLM 프로세스 제한 시간은 90초이며 시간 초과 시 거대한 명령 문자열을 노출하지 않는다.
- 기본 모델은 대화형 응답이 빠른 Claude Haiku이며 `KIMODO_POSE_AGENT_MODEL`로 변경할 수 있다.

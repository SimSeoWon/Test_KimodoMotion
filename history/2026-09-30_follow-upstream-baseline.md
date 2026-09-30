# 2026-09-30 — 따라가기 스크립트의 테스트 기준선 · SOMA 생성 스모크 (Claude, AX 마스터 세션)

AX 일감 `#694`. 따라가기 스크립트(`history/2026-09-30_follow-upstream-script.md`)는 빌드·ctest 경로를 한 번도
돌려 보지 않은 채였다 — 원본이 움직여야 그 단계에 닿기 때문이다. 기준선 빌드를 한 번 돌려 쟀고,
그 결과 **지금 상태로는 원본이 움직일 때마다 2단계에서 반드시 exit 4 로 멈춘다**는 것이 드러났다.

## 기준선 실측 (`.33` Gitea 클론, 서브모듈 `88cbfbc`)

- configure·Release 빌드 통과(약 2분 20초 · 경고 44 · 오류 0). ctest **16건 중 4건 통과**.
- 실패는 세 겹이었다:
  1. `0xc0000135`(DLL 을 못 찾음) 11건 — 테스트 exe 는 `build/Release/`, ggml DLL 은 `build/bin/Release/` 에 생긴다.
     `bin/Release` 를 PATH 에 넣으면 로드는 된다.
  2. 그래도 되살아난 것은 `kimodo-capi-test` 1건뿐이다. 나머지 10건은 저장소에 없는 입력이 필요하다 —
     `models/kimodo-smplx-rp-v1-f32.gguf`(8건) · `generated/llm2vec-text-bundle` + `fixtures/llm2vec-real-prompt`(2건).
  3. `fixtures/smplx-zero-embedding/`(1건) — `fixtures/` 자체가 클론에 없다.
- 원래 클론 `Test_KimodoMotion` 에도 SMPL-X 모델과 fixture 는 없다(llm2vec 번들 14.5GB 와 SOMA 모델만 있다).
  SMPL-X GGUF 는 원본 README 가 *"local-conversion only"* 라고 적은 모델이고(NVIDIA 내부 R&D 라이선스), fixture 를
  만드는 스크립트는 `scripts`·`docs`·`tests` 에서 찾지 못했다.

## 사용자 결정

- **기준선 = 입력 없이 도는 5건 + SOMA 모델 생성 스모크** (「3번」). 따라가기가 지키려는 것은 「실제로 쓰는 모델이
  깨지지 않았나」이고, 그 모델이 SOMA 다.
- **스모크 모델은 파라미터로 받고, 없으면 거절한다** (「(가)」). 기본 경로는 이 클론의
  `vendor/kimodo.cpp/models/kimodo-soma-rp-v1.1-f32.gguf` — 사람이 한 번 둔다. 다른 클론의 경로를 기본값으로 박지 않는다.

## 바꾼 것

- `scripts/follow-upstream.ps1`
  - ctest 앞에서 `<BuildDir>\bin\Release` 를 이 프로세스의 PATH 앞에 붙인다.
  - `-CtestArgs` 기본값이 위 11건을 `-E` 로 뺀다. 넘기면 기본값을 대체한다(`-CtestArgs @()` = 16건 전부).
  - ctest 뒤에 `kimodo-generate-smoke.exe <SmokeModel> <SmokeJoints>` — 실패하거나 exe 가 없으면 exit 4(push 전).
  - `-SmokeModel`(기본 위 경로) · `-SmokeJoints`(기본 30). 모델이 없으면 **드라이런이 아닐 때 전제 단계에서** exit 2 —
    병합을 반쯤 해 두고 멈추지 않게 한다.
- `scripts/tests/follow_upstream_test.ps1` — cmake/ctest 대역을 `.cmd` 에서 **컴파일한 exe 하나**로 바꿨다.
  기본 `-E` 정규식의 `|` 를 cmd 가 파이프로 읽어 `.cmd` 대역이 깨지기 때문이다. 시나리오 추가: 모델 없음 거절(4b) ·
  스모크 실패(6b) · 스모크 exe 없음(6c) · 완주 때 PATH·`-E`·모델·관절 수 확인(7).
- README 「테스트 기준선」 · 스킬 두 벌(종료 코드 표).

## 검증

- 시나리오 테스트 `.33` **36/36**. PATH 보정 줄을 뺀 사본으로는 25/37 — 새 검사가 실제로 잡는다.
- 실물: 기본 `-E` 로 `.33` 빌드에서 ctest → **5건 전부 통과**. SOMA 스모크 30 관절 → rc=0 두 번(각 1.1초).
  관절 수를 주지 않으면(기본 22) rc=1 — 검사가 모델의 관절 수를 실제로 본다.

## 남은 것

- 모델을 Gitea 클론 `models/` 에 두는 일(1.1GB) — 두기 전까지 스크립트는 실행 시 exit 2 로 거절한다.
- SMPL-X 모델·fixture 를 마련해 기준선을 넓힐지는 사용자 결정(라이선스 판단 포함).

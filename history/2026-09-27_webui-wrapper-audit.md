# Kimodo WebUI 래퍼 검증

- 날짜: 2026-09-27
- 요청: 사용자가 목표를 **NVIDIA Kimodo를 WebUI로 래핑하는 것**으로 재확인하고 분석·개선점 검증을 요청했다.
- 대상: 루트 `aced544`, `vendor/kimodo.cpp` `88cbfbc` (`motion/main`), GGML `8c63e709`.
- 결과: 기존 테스트는 통과하지만 생성 경로·포즈 계약·재현성에 수정할 결함이 있다. 아래 구현 제안은 아직 채택/구현 전이다.
- 이번 변경: 보고서와 인수인계 문서만 작성. 애플리케이션·서브모듈 소스는 수정하지 않았다.

## 1. 목표와 현재 구조

현재는 `WebUI → 사용자 포크의 kimodo.cpp → GGML/Vulkan 또는 CPU` 구조다.
NVIDIA 공식 구현은 `nv-tlabs/kimodo`이며, `localai-org/kimodo.cpp`는 별도 C++ 포팅 프로젝트다.
README 첫 NVIDIA 링크가 포팅판을 가리키므로 두 저장소의 관계를 분명히 써야 한다.
NS/UE5는 생성 결과의 소비자다. 보법 F1 및 리타겟 요청은 유효하지만 WebUI의 목적 전체를 대신하지 않는다.

| 기능 | NVIDIA 공식 구현 | 현재 WebUI/포크 |
|---|---|---|
| 텍스트·연속 프롬프트 | 지원 | 지원; 상주/단발 호출의 허용 범위가 다름 |
| SOMA 스켈레톤 | 내부 예측 30관절, 공개 출력/표시 77관절 | 30관절; 이것 자체는 결함이 아님 |
| 모션 모델 | SOMA/G1/SMPL-X | 여러 종류를 선택 목록에 노출하지만 출력·포징은 SOMA30 전용 |
| 제약 | root2d 경로/웨이포인트, 전신, 손발 | 자체 희소 관절 제약 WIP; 공식 제약 구성과 동등성이 검증되지 않음 |
| 접지·제약 후처리 | 제공 | 현재 생성 경로에 없음 |
| 결과 | NPZ, SOMA BVH 등 | root/local rotation `.f32`, GLB, 자체 `meta.json` |
| 부정 프롬프트 | 포크 헤더에서 NVIDIA 공개 API 외 확장이라고 명시 | 자체 포크 기능, UI에 실험적 표시 |
| AI 포즈 편집 | 이번 비교의 핵심 요건 아님 | Claude CLI를 이용한 별도 확장 |

공식 근거:

- [NVIDIA 공식 저장소](https://github.com/nv-tlabs/kimodo)
- [C++ 포팅판의 지원 범위](https://github.com/localai-org/kimodo.cpp)
- [스켈레톤](https://research.nvidia.com/labs/sil/projects/kimodo/docs/key_concepts/skeleton.html)
- [제약과 후처리](https://research.nvidia.com/labs/sil/projects/kimodo/docs/key_concepts/constraints.html)
- [출력 형식](https://research.nvidia.com/labs/sil/projects/kimodo/docs/user_guide/output_formats.html)
- [생성 매개변수](https://research.nvidia.com/labs/sil/projects/kimodo/docs/user_guide/configuration.html)
- [사용 권장사항과 제한](https://research.nvidia.com/labs/sil/projects/kimodo/docs/key_concepts/limitations.html)

## 2. 우선 수정할 결함

### W01 · 높음 — 상주 모델을 둔 채 단발 추론을 추가 실행

- 근거: `webui/server.py:703`~711. 일반 생성은 상주 워커를 쓰지만 키포즈·부정 프롬프트·기본값과 다른 CFG는 `run_cancelable()`로 간다. 기존 워커를 해제하지 않는다.
- 재현: 일반 생성→부정 프롬프트의 모의 실행에서 단발 호출 1회, 상주 워커 `close()` 0회, 기존 워커는 살아 있었다.
- 영향: 모델/인코더가 두 프로세스에 중복 적재될 수 있다. 실제 VRAM 양과 OOM은 측정하지 않았다.
- 수정: 단발 실행 전 기존 워커 종료를 기다리거나 상주 프로토콜에 모든 요청 옵션을 전달한다. 하나의 계층이 프로세스를 소유해야 한다.
- 확인 기준: 일반→포즈→부정 프롬프트→일반 전환에서 추론 워커 하나 이하, 취소 후 재시도 가능.

### W02 · 높음 — 표시 캐릭터 비율이 포즈 작성 좌표에 들어감

- 근거: `webui/static/app.js:758`, `keypose-editor.mjs:183`, `:426`~438. 선택 캐릭터의 T포즈 GLB를 편집 스켈레톤으로 사용하고 월드 좌표를 저장한다.
- `scripts/pretty_export_glb.py:376`~382는 캐릭터 바인딩의 `offsets`로 뼈 길이를 바꾼다. `server.py:654`~667은 이 좌표를 canonical SOMA30으로 변환하지 않고 전달한다.
- 실측: 레스트 왼손 X는 SOMA 0.72361m / Quinn 0.69241m / Y Bot 0.73777m. 왼발목 Y는 0.04989m / 0.08014m / 0.10492m다.
- 영향: 같은 레스트 자세에서 포즈를 작성해도 표시 캐릭터에 따라 엔진의 위치 목표가 달라진다. 실제 생성된 접지·보폭 오차량은 추가 실추론이 필요하다.
- 수정: 제약은 모델의 canonical SOMA30 기준으로 저장하고 표시 캐릭터 변환을 명시한다. 캐릭터 전환 후 포즈 편집기는 처음 로드한 캐릭터를 계속 쓰는 상태도 정리한다.
- 확인 기준: 동일 canonical 포즈의 표시 캐릭터만 바꾸면 엔진 제약은 불변.

### W03 · 높음 — 히스토리에서 포즈·CFG를 제대로 복원하지 않음

- 근거: `webui/static/app.js:423`~455. `loadIntoForm()`은 `meta.keyposes`를 읽지 않고 현재 `animationKeyposes`를 유지한다. `meta.text_cfg == null`이면 현재 CFG도 유지한다.
- 재현: 현재 99프레임 포즈/CFG 7에서, 0프레임 포즈/기본 CFG의 기록을 불러와도 99프레임/7이었다. 실제 함수 본문을 Node VM에서 실행했다.
- 영향: 같은 기록·seed를 선택해도 다른 제약으로 생성한다. 포즈가 없는 기록도 이전 포즈가 섞인다.
- 수정: 모든 생성 조건을 하나의 요청 객체로 복원하고 없는 필드는 기본값/빈 상태로 초기화한다.
- 확인 기준: 현재 폼 상태와 무관하게 불러온 기록과 제출 요청이 일치.

### W04 · 중간 — 프레임 허용 범위가 호출 경로에 따라 다름

- 근거: `webui/static/index.html:64`는 1~600프레임 허용. 기본 요청은 `server.py:703`에서 상주 워커로 가고, `vendor/kimodo.cpp/src/generate.cpp:96`에서 단일 프롬프트도 sequence API를 쓴다. `src/model.cpp:177`은 2~300만 허용한다.
- 재현: 600프레임이 거부 없이 상주 워커의 한 구간으로 전달됐다. 엔진 거부 조건은 C++ 소스로 확인했다.
- 영향: UI의 301~600프레임이 기본 경로에서 실패하고, CFG 변경 시 다른 경로/범위를 사용한다.
- 수정: 공식 권장 제한인 프롬프트당 10초를 기준으로 UI/API를 통일하고 긴 모션은 구간 생성으로 안내한다. 서버에서 프레임·steps·유한 CFG·전환 길이를 미리 검증한다.

### W05 · 중간 — G1 등을 선택할 수 있지만 SOMA30으로만 내보냄

- 근거: `server.py:174`~208은 G1/SMPL-X GGUF도 노출한다. `scripts/pretty_export_glb.py:359`와 `webui/keypose.py`는 SOMA30 전용이다.
- 재현: G1 형태의 34관절·2프레임 회전 버퍼(1088바이트)를 실제 exporter에 전달하면 `unpack requires a buffer of 960 bytes`로 실패한다. G1 추론은 하지 않았다.
- 영향: 추가 모델 설치 후 추론이 끝나도 export가 실패하며 제약 관절 인덱스도 맞지 않는다. 현재 설치 모델은 SOMA RP v1.1 하나다.
- 수정: 검증된 모델만 노출하거나 모델별 skeleton/fps/제약/export 정보를 통해 전체 경로를 선택한다. 파일 이름만으로 지원을 판단하지 않는다.

### W06 · 중간 — 수락한 포즈 공간·가중치가 버려짐

- 근거: `webui/keypose.py:152`~164는 world/character/local, weight 0~4를 허용한다. `server.py:654`~667은 위치/회전만 TSV로 보낸다. C++ `pose_constraint`는 world 위치/회전만 표현한다.
- 재현: 같은 숫자의 world/weight=1과 local/weight=0이 완전히 같은 TSV로 변환됐다.
- 영향: 현재 수동 UI는 world/1이지만 저장 데이터·에이전트·외부 API가 전달하는 다른 의미를 실행 시 지키지 않는다.
- 수정: 공간 변환/가중치를 구현하거나 지원값만 허용하고 나머지는 오류로 반환한다.

### W07 · 중간 — 기본 다운로드가 표시 캐릭터의 미리보기임

- 근거: `webui/static/app.js:152`, `:517`이 `meta.glb_url` 대신 `/api/preview?...&model=...`를 다운로드 링크로 설정한다. 버튼은 `animation.glb 다운로드`다.
- 영향: 캐릭터 변경이 다운로드 메시·뼈 비율까지 바꾼다. canonical 모션 출력과 캐릭터 포함 GLB를 구분할 수 없다.
- 수정 제안: 기본 모션 출력은 canonical 결과를 제공하고 캐릭터 GLB는 별도 선택으로 표시한다. 원시 모션/메타데이터 또는 향후 NPZ/BVH도 묶음으로 제공한다.
- 이 항목은 파일 파손이 아닌, 코드와 래퍼 목적에서 확인한 출력 계약 문제다.

### W08 · 중간 — 런처가 포트 소유 PID를 무조건 종료

- 근거: `scripts/run-webui.ps1:32`~36 → `scripts/prepare-webui-port.ps1:17`~19. 8188 LISTENING PID에 `Stop-Process -Force`를 먼저 실행한다. preflight는 그 뒤다.
- 영향: 다른 프로그램이나 기존 생성 작업을 종료할 수 있다. 이후 preflight가 실패하면 기존 서비스만 끊긴다. 자식 추론 워커 회수도 보장하지 않는다.
- 수정: 사전 점검 후 포트가 사용 중이면 기존 서비스와 PID를 안내하고 명시적인 재시작 선택에만 소유권·자식을 확인해 종료한다.
- 소스 확인만 했다. 런처/종료 명령은 실행하지 않았다.

### W09 · 중간 — 변경 요청의 출처 검사가 없음

- 근거: `Handler._read_json_body()`/`do_POST()`에 Origin/Host와 JSON Content-Type 검증이 없다.
- 재현: 소켓 없이 핸들러를 호출했다. 외부 Origin, text/plain JSON 삭제 요청이 수락되어 **테스트 임시 결과 폴더**가 삭제됐다.
- 영향: 브라우저에서 로컬 주소로 요청을 보낼 수 있는 조건에서는 외부 페이지 요청을 서버가 구분하지 못한다. 최신 브라우저 로컬 네트워크 접근 정책에 따른 실제 도달 여부는 검증하지 않았다.
- 수정: 허용 Host/Origin과 변경 API의 Content-Type을 검사하고 필요시 세션 토큰을 사용한다.

## 3. 추가 결함과 운영 개선

| 항목 | 확인한 사실 | 제안 |
|---|---|---|
| 미리보기 캐시 | `server.py:247`, `:545`는 파일 존재만 검사. 바인딩 변경 후 재요청해도 exporter 호출은 총 1회 | 바인딩/내보내기 코드 버전을 캐시 키에 포함 |
| 인코더 기본값 | packed BF16 옵션은 파일 경로, default_encoder는 legacy 디렉터리. packed만 있는 임시 환경에서 기본값이 사용 가능 옵션에 없음 | 발견한 사용 가능 인코더에서 기본값 결정, 선택값에 맞춰 preflight |
| 결과 ID 충돌 | `server.py:639`는 초 단위 시간+slug. 시각 고정 모의 요청 2개가 같은 ID/폴더와 기록 1개로 합쳐짐 | UUID 등 고유 ID와 디렉터리 재사용 금지. 실발생 조건은 같은 초·slug의 빠른 연속 완료 |
| 취소·진행 복구 | 긴 HTTP 요청 하나, export는 current_process 미등록, 워커 stdout readline 무기한 대기, stderr DEVNULL | 작업 ID/단계 상태, timeout·취소·실패 로그, 새로고침 후 작업 조회 |
| 결과 GLB 오류 | 실제 결과의 viewer error 핸들러는 바로 return | 오류 메시지와 명시적인 폴백 |
| 설치/로컬 실행 | JS는 unpkg CDN, 도구/모델은 고정 Windows 경로 전제. README에 text bundle 준비 전체 순서가 없음 | 도구 설정·버전 점검·재현 가능한 설치 안내. 오프라인 목표라면 JS 번들 포함 |
| 구형 MCP 문서 | README는 현재 기능처럼 설명하나 CLAUDE.md는 현 작업 포즈의 권위 상태가 아니라고 명시 | PoseAsset/배치 API와 문서를 맞추고 구형 MCP 범위 표시 |

## 4. 구조 변경 제안

현재 C++ 엔진을 바로 폐기할 근거는 없다. Windows/Vulkan·양자화·상주 실행과 기존 포크 기능을 살리면서 공식 기능 지원 범위를 코드로 표현하는 방향을 권한다.

1. **요청/결과 계약 통일:** skeleton, fps, 모델/엔진 버전, 구간, seed, CFG, canonical 제약을 저장한다. 원본 모션·표시 캐릭터·출력 형식을 구분한다.
2. **엔진 어댑터:** 기존 C++ 호출부터 어댑터로 옮기고 기능 지원을 명시한다. 공식 Python은 품질/수치 비교 기준 경로로 먼저 검토한다. 즉시 두 엔진을 상시 운영해야 한다는 뜻은 아니다.
3. **작업 관리 분리:** 한 계층이 직렬화·모델 보유·취소·timeout·실패 기록을 책임지고 UI는 작업 ID로 조회한다.
4. **공식 제약/후처리 비교:** 현재 임의 관절 희소 마스크 WIP를 학습된 fullbody/end-effector/root2d와 비교한다. 공식 문서도 모델 출력만으로 정확한 제약 준수를 보장하지 않아 후처리를 제공한다.
5. **생성 왕복 테스트:** 기록→동일 요청, 캐릭터→동일 canonical 제약, 상주/단발 전환, 취소/재시도, 모델 불일치 거부, 버퍼/GLB 루트 궤적이 우선이다.

권장 순서: W01·W03·W04·W05·W08 실행 안정성 → W02·W06·W07 포즈/출력 계약 → 공식 제약·후처리 비교 및 작업 관리 구조.
W09는 로컬 서비스 변경 API 방어 수정에 포함한다.

## 5. 검증 범위와 한계

- `py -3.12 -m unittest discover -s webui/tests -p '*_test.py' -v`: **31개 통과**.
- `node --test webui/tests/keypose_fk_test.mjs`: **1개 테스트 파일 통과**(내부 FK/IK assertions 포함).
- Python은 샌드박스에서 런처가 설치 정보를 찾지 못해 승인된 실행으로 수행했다.
- 생성 분기는 실제 `_run_generation()`을 실행하되 프로세스/export는 mock, 파일은 임시 디렉터리만 사용했다. G1 버퍼 오류는 실제 vendor exporter로 확인했다.
- JS 히스토리는 실제 함수 본문과 DOM 대역을 Node VM에서 실행했다. 브라우저 검증은 아니다.
- 기존 테스트는 생성 프로세스 전환·기록 왕복·모델별 export를 검증하지 않아 위 결함이 있어도 통과한다.
- CMake의 `KIMODO_BUILD_TESTS=OFF`를 확인했다. 설정 변경이나 C++/Vulkan parity suite 실행은 하지 않았다.
- **실GPU 추론, NVIDIA Python과의 수치/품질 비교, UE 임포트, 실브라우저 E2E는 수행하지 않았다.** 그 경로의 합격 판정이 아니다.
- 서버·Claude·Unreal·상주 워커를 시작/종료하지 않았고 사용자 생성물·바인딩도 수정하지 않았다.
- 초기 상태는 `main...origin/main [ahead 1]`, `.claude/settings.local.json` 미추적, 서브모듈 추적 변경 없음. Git 전역 ignore 접근 권한 경고로 `.claude/` 표시는 실행 환경에 따라 다를 수 있다. 원격 fetch는 하지 않았다.

## 6. 후속 결정

사용자가 요청한 검증은 완료했다. 구현 범위는 아직 결정하지 않았다. 실행 안정성을 우선 고친 뒤 root2d/전신·손발 제약/후처리를 어느 수준까지 제공할지 정하는 순서를 제안한다.
NS F1·UE 리타겟은 소비자 검증 단계로 `docs/ns-animation-requests.md`를 계속 참고한다.

---
date: 2026-09-17
tags: [plan, webui, keypose, constraints, ik, threejs, soma30, storyboard, mcp, ai-tools]
status: done
confirmed-by-user: true
---

# 웹 UI 사용자 조작형 키포즈 편집기 계획

## 목표

스토리보드의 각 구간에 사용자가 직접 3D 키포즈를 배치하고, Kimodo가 텍스트 의미와
키포즈 제약을 함께 받아 키포즈 사이의 자연스러운 애니메이션을 생성하게 한다.

이미지 포즈 추출은 중심 기능이 아니다. 나중에 이미지에서 얻은 포즈를 **편집 가능한
초안**으로 가져오는 보조 입력으로 둔다. 사용자가 만든 키포즈와 이미지에서 가져온
키포즈는 이후 동일한 데이터 구조와 생성 경로를 사용한다.

## 사용자 경험

기본 흐름:

1. 스토리보드 구간을 추가하고 짧은 동작 프롬프트와 길이를 지정한다.
2. 타임라인에서 원하는 프레임을 선택해 `키포즈 추가`를 누른다.
3. 3D 뷰어에서 관절 회전 또는 손·발 IK 핸들을 움직인다.
4. 이 키포즈에서 제약할 항목과 강도를 선택한다.
5. 여러 키포즈를 배치한 뒤 생성한다.
6. Kimodo는 지정된 포즈를 통과하면서 구간 프롬프트에 맞는 중간 동작을 생성한다.

권장 UI 배치:

```text
┌──────────────────── 3D 포즈 편집기 ────────────────────┐
│      캐릭터 + 선택 관절 + 회전 기즈모/IK 핸들          │
└─────────────────────────────────────────────────────────┘
  0f        30f        60f        90f       120f
  ◆─────────◆──────────◆─────────────────────◆
 [준비]    [딛기]      [찌르기]               [회수]

 선택 키포즈: 60f
 [x] 몸통 방향  [x] 오른손 위치  [x] 양발 위치
 [ ] 머리 회전  [ ] 전체 관절     제약 강도: 1.5
```

키포즈 조작은 두 단계로 제공한다.

- 1차: FK 관절 회전. 관절 하나를 선택하고 로컬 회전을 기즈모로 편집한다.
- 2차: 손·발 IK 핸들. 목표 위치를 움직이면 팔·다리 관절이 따라오게 한다.

FK만으로도 전신 포즈를 표현할 수 있으므로 먼저 완성한다. IK는 사용성을 높이는 후속 단계다.

부모 관절 조작의 기본 규칙은 **순수 계층형 FK**로 확정한다. 부모의 월드 변환에 자식의
로컬 변환을 연속으로 곱하므로, 가슴을 돌리면 어깨·팔·머리가, 어깨를 돌리면 팔꿈치·손이,
골반을 돌리면 전신이 인형처럼 무조건 따라간다. 부모를 움직일 때 자식의 월드 위치를
자동으로 보존하는 역보정은 기본 동작에 넣지 않는다.

손·발 같은 말단의 위치를 유지하거나 더 조정할 필요가 있을 때만 사용자가 해당 말단을
선택해 IK 핸들을 움직인다. 즉 `FK로 큰 포즈 구성 → 필요한 말단만 IK로 보정` 순서이며,
IK가 켜져 있지 않은 말단은 항상 부모 계층을 그대로 따른다.

기본 포징 UI는 사용자가 지정한 다음 **11개 컨트롤**만 항상 표시한다. 나머지 SOMA30
관절은 고급 모드에서만 노출한다.

- 양발 (`left_foot`, `right_foot`)
- 골반 (`pelvis`)
- 가슴 (`chest`)
- 양어깨 (`left_shoulder`, `right_shoulder`)
- 양팔꿈치 (`left_elbow`, `right_elbow`)
- 양손 (`left_hand`, `right_hand`)
- 고개 (`head`)

각 컨트롤은 클릭 선택할 수 있고, 선택 후 이동/회전 기즈모와 local/world 좌표 모드를
바꿀 수 있다. 이동은 말단 IK 목표 또는 부분 포즈 제약, 회전은 해당 관절 방향 제약으로
해석한다. 이는 물리 래그돌이 아니라 Garry's Mod식 조작감을 가진 키포즈 저작 UI다.

### Claude/Codex 자연어 조작

직접 화면 클릭을 자동화하지 않는다. 편집기가 사용하는 동일한 키포즈 문서에 대해
구조화된 명령 계층을 만들고, 이를 로컬 API와 MCP 도구로 공개한다.

- 읽기: `get_pose_state`, `list_keyposes`, `get_control_schema`
- 편집: `create_keypose`, `move_control`, `rotate_control`, `set_constraint`
- 고수준 편집: `plant_foot`, `place_hands`, `look_at`, `mirror_pose`, `copy_keypose`
- 작업 관리: `preview_pose`, `undo_pose_edit`, `redo_pose_edit`
- 비용 있는 실행: `generate_motion`(사용자 확인 후 실행)

명령은 항상 undo 가능한 트랜잭션으로 기록한다. AI가 변경한 컨트롤은 UI에서 강조하고,
여러 키포즈 변경과 삭제·덮어쓰기·실제 생성은 변경 요약을 보여준 뒤 적용한다. Claude와
Codex는 같은 MCP 서버/JSON schema를 공유하므로 서로 만든 포즈도 동일하게 편집할 수 있다.

## 핵심 설계 결정

### 1. 이미지 임베딩을 모션 모델에 직접 주입하지 않는다

현재 Kimodo 포트가 받는 4096차원 조건은 LLM2Vec 텍스트 공간이다. 다른 이미지 인코더의
벡터를 같은 크기로 맞추는 것만으로는 의미 공간이 호환되지 않는다. 텍스트는 기존 인코더로,
자세는 Kimodo가 학습한 `observed`/`observed_mask` 제약으로 전달한다.

### 2. 키포즈는 전신 스냅샷이 아니라 희소 제약이다

매 키포즈에서 모든 관절을 강제로 고정하지 않는다. 사용자가 선택한 관절 위치·회전,
루트 위치·방향만 마스크에 넣고 나머지는 Kimodo가 해결하게 한다. 이미지 초안처럼 불확실한
입력은 관절별 신뢰도에 따라 마스크에서 제외할 수 있다.

### 3. UI 포즈와 모델 제약 표현을 분리한다

웹 UI의 저장 형식은 사람이 이해하기 쉬운 SOMA30 로컬 회전/루트 변환을 기준으로 한다.
생성 직전에 C++가 이를 Kimodo 내부 motion representation의 정규화된 `observed`와
`observed_mask`로 변환한다. UI가 `motion_dim` 배열 인덱스를 직접 알게 하지 않는다.

### 4. 제약 관통 검증을 3D 편집기보다 먼저 한다

뷰어 작업 전에 코드로 만든 단일 키포즈가 생성 결과의 지정 프레임에 실제 반영되는지
확인한다. 이 검증이 실패한 상태에서는 편집기 개발을 시작하지 않는다.

## 데이터 계약

웹 UI와 서버 사이의 초기 JSON 형식:

```json
{
  "frame": 60,
  "label": "찌르기",
  "root": {
    "position_xz": [0.0, 0.8],
    "heading": 0.0,
    "position_enabled": false,
    "heading_enabled": true
  },
  "joints": {
    "right_wrist": {
      "local_rotation_xyzw": [0.0, 0.0, 0.0, 1.0],
      "rotation_enabled": false,
      "world_position": [0.2, 1.2, 0.7],
      "position_enabled": true
    }
  },
  "constraint_weight": 1.5
}
```

저장 형식의 원칙:

- 관절 키는 SOMA30의 안정적인 이름을 사용한다.
- 회전은 GLB 및 현재 출력과 맞춰 `xyzw` 쿼터니언으로 저장한다.
- 편집기 내부 좌표와 Kimodo 좌표의 변환은 한 모듈에 모은다.
- 프레임은 전체 결과가 아니라 해당 스토리보드 구간 내부의 로컬 프레임이다.
- 비활성 제약은 값을 갖고 있어도 `observed_mask`에 포함하지 않는다.
- 형식에 `schema_version`을 추가해 이후 IK·이미지 신뢰도 필드를 확장할 수 있게 한다.

## 구현 단계

### Phase 0 — 기준 좌표와 표현 조사

목적: UI에서 보이는 포즈와 모델이 받는 제약이 동일한 자세를 의미하도록 좌표 계약을 확정한다.

- upstream Kimodo의 constraint 생성과 motion representation 변환을 기준으로 삼는다.
- SOMA30 관절 이름, 부모, rest offset을 단일 공유 데이터로 정리한다.
- 로컬 쿼터니언 → 글로벌 위치 FK와 역변환을 고정 테스트로 만든다.
- 웹 좌표계, GLB 좌표계, Kimodo의 Y-up/+Z-forward 좌표계를 문서화한다.
- T포즈와 비대칭 포즈 fixture로 좌우·전후·쿼터니언 순서를 검증한다.

완료 기준:

- C++와 웹에서 계산한 SOMA30 글로벌 관절 위치가 허용 오차 안에서 일치한다.
- T포즈, 오른팔 들기, 왼발 앞으로 내밀기 fixture가 뷰어와 export 결과에서 동일하다.

### Phase 1 — C++ 공개 제약 API

목적: UI 없이도 텍스트 + 키포즈로 모션을 생성할 수 있게 한다.

- 공개 타입 `pose_constraint`, `joint_constraint`, `constrained_prompt_segment`를 설계한다.
- `model::generate_text_constrained()`와 sequence 대응 API를 추가한다.
- 공개 키포즈를 정규화된 `observed`/`observed_mask`로 변환한다.
- 기존 `sample_motion_from_noise_conditioned()`를 일반 생성에서도 사용하게 연결한다.
- `constraint_cfg`를 실제 제약 분기에 전달한다.
- CLI에 JSON constraint 파일 입력을 추가한다.
- 범위, 중복 프레임, 잘못된 관절 이름, NaN을 명시적으로 거부한다.

테스트:

- 제약 없음이 기존 동일 seed 출력과 회귀 일치한다.
- 루트 heading, 손 위치, 전신 키포즈를 각각 독립적으로 테스트한다.
- 제약 강도 0과 기본값의 동작을 검증한다.
- sequence 구간 경계와 키포즈가 겹칠 때 continuity가 유지된다.

완료 기준:

- 고정 seed에서 제약한 손/발/루트가 목표 허용 오차를 만족한다.
- 제약을 끄면 기존 생성 결과가 바뀌지 않는다.

### Phase 2 — 서버 API와 저장

목적: 웹의 키포즈 문서를 안전하게 생성 프로세스까지 전달한다.

- `/api/generate`가 구간별 `keyposes`를 받게 한다.
- 서버에서 schema와 프레임/관절/수치 범위를 검증한다.
- 세션별 constraint JSON을 출력 디렉터리에 기록한다.
- `meta.json`에 키포즈와 schema version을 보존한다.
- 히스토리를 다시 불러오면 키포즈도 복구한다.
- 제약 파일을 `kmd-generate.exe`에 전달한다.

완료 기준:

- 숫자로 작성한 키포즈를 웹 요청으로 보내 생성하고, 히스토리에서 완전히 복원할 수 있다.

### Phase 3 — 3D FK 키포즈 편집기 MVP

목적: 사용자가 브라우저에서 직접 SOMA30 포즈를 만들 수 있게 한다.

- 현재 `<model-viewer>` 결과 재생 영역과 별도로 편집용 Three.js 캔버스를 둔다.
- `model-viewer` 내부 구현에 의존하지 않고 Three.js의 공개 scene/animation API를 사용한다.
- 캐릭터 선택, orbit camera, 관절 picking, 선택 강조를 구현한다.
- `TransformControls` 회전 기즈모로 로컬 관절 회전을 편집한다.
- 관절별 회전 제한은 우선 경고/색상 표시로 시작하고 강제 clamp는 후속 검토한다.
- 현재 포즈 초기화, 이전 키포즈 복제, 좌우 미러, 키포즈 저장/삭제를 제공한다.
- 타임라인 마커와 구간 로컬 프레임을 동기화한다.
- 키보드 접근과 undo/redo 스택을 포함한다.

완료 기준:

- 사용자가 준비/중간/마무리 포즈 세 개를 만들고 새로고침·히스토리 복원 후에도 수정할 수 있다.
- 생성된 모션이 세 키포즈를 지정한 순서와 시점으로 통과한다.

### Phase 4 — 손·발 IK와 부분 제약 UX

목적: 비전문 사용자가 관절을 하나씩 회전하지 않고 핵심 자세를 만들게 한다.

- 양손·양발·골반에 IK 핸들을 제공한다.
- 2-bone IK로 팔/다리를 먼저 지원하고 pole direction을 노출한다.
- 손발 position/rotation, 몸통 방향, 전체 포즈를 개별 토글한다.
- 키포즈 전체와 관절별 제약 강도를 구분한다.
- 발 고정과 지면 높이를 시각화한다.
- 과도하게 먼 목표, 관절 뒤집힘, 자기 교차 가능성을 경고한다.

완료 기준:

- 손과 발 핸들만으로 런지, 양손 뻗기, 한 발 들기 포즈를 구성할 수 있다.

### Phase 5 — 이미지 포즈 초안 가져오기

목적: 이미지에서 시작하되 자동 결과를 사용자가 검수·수정하게 한다.

- 이미지에서 2D 관절과 관절별 confidence를 추출한다.
- 인물 선택, 좌우 반전, 전후 방향을 확인하는 단계가 반드시 있다.
- 2D 포즈를 SOMA30 초기 포즈에 맞추되 깊이는 중립값 또는 사용자 조절값을 사용한다.
- 낮은 confidence 관절은 기본적으로 제약을 끈다.
- 가져온 포즈를 일반 키포즈와 같은 편집기로 연다.
- 캡션은 짧은 동작 의미 제안으로만 사용한다.

완료 기준:

- 자동 추출 실패가 생성 요청 실패로 이어지지 않고 수동 편집으로 계속 진행할 수 있다.

## 파일별 예상 변경 범위

`vendor/kimodo.cpp` 서브모듈 커밋:

- `include/kimodo/kimodo.hpp`: 공개 constraint 타입/API
- `include/kimodo/kimodo_capi.h`: 필요 시 C ABI
- `src/model.cpp`: 텍스트 인코딩과 conditioned sampler 연결
- `src/denoiser.hpp`, `src/denoiser.cpp`: 공개 경로에 필요한 검증/오케스트레이션
- 새 constraint 변환 소스와 집중 테스트
- `src/generate.cpp`: constraint JSON CLI 입력

루트 저장소 커밋:

- `webui/server.py`: schema 검증, 파일 기록, CLI 전달, history 복원
- `webui/static/index.html`: 편집기·타임라인·제약 패널
- `webui/static/app.js`: 키포즈 상태, 편집 명령, API payload
- `webui/static/style.css`: 편집기와 타임라인 레이아웃
- 필요 시 `webui/static/keypose-editor.js`: Three.js/SOMA30 전용 모듈
- 이미지 포즈는 별도 선택 의존성 및 스크립트로 격리

루트와 서브모듈 변경은 저장소 지침대로 논리적으로 분리해 커밋한다.

## 테스트 전략

가장 작은 테스트부터 다음 순서로 실행한다.

1. motion representation/FK 단위 테스트
2. constraint 변환 단위 테스트
3. conditioned sampling 고정 seed 테스트
4. CLI constraint JSON 통합 테스트
5. 서버 payload 검증 테스트
6. 브라우저 키포즈 저장/복원 테스트
7. 실제 Mixamo 프리뷰 캐릭터에서 시각 검증
8. `ctest --test-dir vendor\kimodo.cpp\build -C Release --output-on-failure`

정량 검증 항목:

- 제약 프레임의 관절 위치 오차
- 키포즈 전후 속도/가속도 불연속
- 발 접촉 구간의 foot sliding
- 같은 seed에서 제약 없음 회귀 일치
- 좌우 미러 결과의 대칭 오차

## 위험과 대응

- **좌표계 불일치**: UI를 먼저 만들지 않고 Phase 0 fixture로 차단한다.
- **강한 제약의 부자연스러운 결과**: 부분 마스크와 constraint CFG를 기본 UX로 제공한다.
- **키포즈 사이 시간 부족**: 이동 거리에 비해 프레임이 짧으면 생성 전에 경고한다.
- **회전 한계/관절 꺾임**: 초기에는 경고, 이후 skeleton별 limit preset을 추가한다.
- **Three.js CDN 의존성**: 버전을 고정하고 장기적으로 로컬 vendoring 여부를 결정한다.
- **Mixamo 메시와 SOMA30 불일치**: 편집 상태의 기준은 SOMA30이고 메시 바인딩은 표시 계층으로만 취급한다.
- **이미지 깊이 모호성**: 이미지 결과는 확정 제약이 아니라 수정 가능한 초안으로만 취급한다.
- **성능**: 편집은 브라우저 FK만 사용하고 Kimodo 추론은 Generate 시점에만 실행한다.

## 이번 범위에서 하지 않는 것

- 이미지 임베딩을 Kimodo 4096차원 텍스트 입력에 직접 혼합
- 매 프레임 수동 애니메이션 편집
- 물리 시뮬레이션 또는 충돌 회피
- 손가락/표정 편집(SOMA30 제어 범위 밖)
- 자동 이미지 포즈 추출을 수동 편집기보다 먼저 구현
- UE5 Control Rig 편집기를 웹에 그대로 복제

## 권장 첫 구현 라운드

첫 라운드는 Phase 0~2만 대상으로 한다. 즉, UI 없이 다음 한 가지를 증명한다.

> `60프레임에서 오른손을 앞쪽 목표 위치에 둔다`는 JSON 제약을 전달했을 때, 생성 결과의
> 해당 프레임 오른손이 목표 오차 범위 안에 들어오며 제약이 없는 기존 결과는 변하지 않는다.

이 수직 경로가 통과한 뒤 Phase 3의 웹 편집기를 시작한다. 첫 UI 버전은 FK 회전과 키포즈
세 개 저장/복원까지만 포함하고, IK와 이미지 가져오기는 별도 라운드로 유지한다.

## 진행 기록

### 2026-09-17 — 공용 키포즈 계약 착수

- 11개 기본 포징 컨트롤과 SOMA30 관절 인덱스 매핑을 `webui/keypose.py`에 정의했다.
- Y-up/+Z-forward/미터 좌표계, world/character/local 공간, select/move/rotate 모드를
  `/api/keypose-schema`로 공개했다.
- Claude/Codex가 공유할 AI 명령 이름도 같은 schema에서 조회할 수 있게 했다.
- 외부 키포즈 문서의 frame, control 이름, position, quaternion, space, weight를 검증하고
  쿼터니언 정규화와 프레임 정렬을 수행한다.
- `/api/keyposes/validate`를 추가해 웹 클라이언트와 향후 MCP 어댑터가 동일한 검증 경로를
  사용하게 했다.
- 단위 테스트 5개로 기본 컨트롤 중복, schema 복사 안전성, 정규화, 미등록 컨트롤,
  프레임 중복/범위 오류를 확인했다.

### 2026-09-17 — 순수 FK 연쇄 계산 고정

- 브라우저와 Node 테스트가 함께 쓰는 `webui/static/keypose-fk.mjs`를 추가했다.
- `world(child) = world(parent) × local(child)` 규칙으로 위치와 xyzw 쿼터니언을 루트부터
  연속 합성한다.
- 어깨를 Z축으로 90도 돌렸을 때 팔꿈치와 손이 각각 회전된 위치로 함께 이동하는 최소
  체인 테스트를 추가했다.
- 부모/자식 회전 누적과 부모가 자식보다 뒤에 나오는 잘못된 계층 거부도 검증한다.

### 2026-09-17 — 편집기·네이티브 제약·MCP 수직 경로 완성

- Three.js 편집기에서 T포즈 GLB의 실제 SOMA30 본과 11개 제어점을 로드한다.
- 클릭/버튼 선택, Q/W/E 선택·이동·회전, local/world 전환, 초기화, 프레임별 저장·삭제,
  undo/redo를 제공한다.
- 부모 회전은 순수 FK로 전파하고 손·발은 2-bone, 팔꿈치는 1-bone CCD IK로 위치를 보정한다.
- C++ 공개 API에 희소 world position/global rotation 제약을 추가하고 Kimodo의 정규화된
  `observed`/`observed_mask`로 변환한다.
- 단일 생성과 multi-prompt 스토리보드 모두 conditioned sampler를 사용하며, 구간 경계에서는
  기존 연속성 제약과 사용자 제약을 병합한다.
- 웹 서버가 키포즈 JSON/TSV/meta를 저장하고 CLI에 전달한다.
- revision 기반 로컬 명령 저장소와 dependency-free stdio MCP 서버를 추가했다. Claude/Codex와
  웹 UI가 같은 문서를 사용하고 변경 사항이 UI에 자동 반영된다.
- 단일 프롬프트 2프레임/1스텝과 2구간 스토리보드 4프레임/1스텝 CPU 생성으로
  `웹/서버 → CLI → conditioned sampler → GLB`를 끝까지 확인했다.
- 부모 FK 조작을 저장할 때 함께 움직인 하위 기본 컨트롤의 결과 위치·회전도 기록해,
  편집기에서 본 인형 자세와 실제 Kimodo 키포즈 제약이 어긋나지 않게 했다.
- 현재 포즈를 이름 있는 프리셋으로 저장하고 임의의 타임라인 프레임에 다시 배치할 수 있다.
  MCP에도 프리셋 목록/저장/배치 도구를 제공해 LLM이 만든 포즈를 반복 재사용한다.

### 2026-09-17 — 포징 모드 브라우저 로딩 수정

- import map을 모든 module script보다 먼저 선언해 Three.js bare import 해석 순서를 보장했다.
- Windows의 MIME 추론이 `.mjs`를 `text/plain`으로 보내던 문제를 고쳐
  `text/javascript; charset=utf-8`로 명시한다.
- 개발 중 이전 정적 파일이 남지 않도록 HTML/JS/CSS 응답에 `Cache-Control: no-store`를 붙였다.
- 동적 import 실패를 화면 상태 영역에도 표시해 빈 패널처럼 보이지 않게 했다.
- Edge headless에서 포징 버튼 클릭 후 패널 표시, 캔버스 생성, 편집기 준비 상태까지 확인했다.

### 2026-09-17 — 양 무릎 컨트롤 추가

- 기본 제어점을 13개로 확장하고 `left_knee`/`right_knee`를 SOMA30의
  `LeftShin`(23)/`RightShin`(27)에 연결했다.
- 무릎 이동은 부모 허벅지를 회전시키는 1-bone IK로 처리하며 회전 기즈모도 함께 제공한다.
- 웹 UI, 저장 문서, 프리셋, 에이전트/MCP와 네이티브 제약 변환은 기존 공용 schema를 통해
  별도 형식 변경 없이 새 무릎 제어점을 사용한다.

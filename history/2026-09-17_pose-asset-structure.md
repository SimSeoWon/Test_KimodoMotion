# 포즈 자산 구조체 정의

- date: 2026-09-17
- status: implemented
- scope: 단일 프레임 포즈 자산, 제어점 제약, 타임라인 배치 계약

## 구조

`PoseConstraint`는 이름 있는 제어점 하나의 선택적 world/character/local 위치와 회전,
가중치를 표현한다.

`PoseAsset`은 `id`, `name`, `controls`, `schema_version`을 가진다. 포즈는 재사용 가능한 단일
자세이므로 `frame`, `duration` 등 시간축 필드를 갖지 않는다.

`PosePlacement`는 `frame`, `pose_id`, `pose_name`, `controls`를 가진다. `controls`는 원본 포즈의
참조가 아니라 배치 시점의 스냅샷이다. 따라서 포즈 자산을 수정하거나 삭제해도 이미 작성한
애니메이션이 암묵적으로 변하지 않는다.

## 런타임 호환성

기존 네이티브 런타임이 받는 schema version 1 `keyposes` 문서는 유지한다.
`placements_to_keypose_document()`가 명시적 포즈 배치를 기존 문서로 변환한다.

기존 `{name, controls}` 포즈 프리셋은 로드 시 이름에서 안정적인 UUID를 유도해 자동 호환한다.
새로 저장하는 포즈는 UUID를 발급하고 구조체 전체를 저장한다.

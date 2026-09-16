---
date: 2026-09-17
tags: [blender, diagnostics, prompt-length, ue5-workflow, detached-mesh, forward-kinematics]
status: done
confirmed-by-user: true
---

# 발생: 긴 "사진 스타일" 프롬프트가 다리 관절을 이상하게 만듦 (파이프라인 버그 아님)

## 배경

사용자가 웹 UI로 만든 `animation.glb`(Mixamo 미리보기)를 언리얼에 바로 쓸 수 있는지 물어봄.
답하는 과정에서: (1) 웹 UI glb는 미리보기 전용이라 UE5엔 vendor 원본 `export_glb.py`로 뽑은
걸 써야 한다는 것, (2) Mixamo 캐릭터를 그대로 쓸 거면(SKM_Manny/Quinn 리타겟이 아니라)
`Kimodo.ImportIK` 파이프라인 자체가 필요 없고 그냥 드래그 임포트하면 된다는 것까지 정리함.
검증 삼아 사용자가 `C:\Users\USER\Downloads\animation.glb`를 Blender로 렌더해보자고 해서
실제로 돌려봤는데 — **오른발이 프레임 90~119쯤에서 몸에서 떨어져 따로 떠 있는** 진짜 결함을
발견함.

## 원인 조사 (Blender headless 여러 단계로 좁혀감)

1. 여러 각도(정면/측면 90°/뒤/위)로 다시 렌더 → 카메라 각도 문제(가림/착시) 아니고 실제
   3D 공간에서 분리된 것 확인.
2. `world_to_camera_view`로 30개 관절의 스크린 좌표를 정확히 계산해서 관찰된 블롭
   위치랑 대조 → **RightFoot/RightToeBase**로 특정(스크린 좌표가 거의 정확히 일치).
3. raw `local_rotations_xyzw.f32`에서 해당 구간 쿼터니언 확인 → **전부 정규화돼 있고
   프레임 간 부드럽게 변함**(NaN·튐 없음) — 원본 모델 출력 자체는 안 깨짐.
4. `ybot_soma30_bind.json`의 오프셋(좌우 대칭 확인) · 정점 그룹(같은 관절 내 3D 거리로
   봐도 별도 서브클러스터 없음, 전부 같은 Alpha_Surface 색상) · 메시 연결성(엣지 스트레치
   비율 최대 6배, 절대 길이는 무시할 수준 / bmesh 연결요소 분석으로도 Foot·Toe 전용의
   작은 분리된 섬 없음) — **export 파이프라인 쪽 데이터는 전부 정상**.
5. 직접 순정 파이썬으로 forward kinematics를 다시 구현해서 대조하려 했으나 Blender 결과랑
   안 맞음 — 좌표계/쿼터니언 합성 순서를 손으로 다시 구현하다 버그 냈을 가능성이 높아서
   **이 결과는 폐기**(Blender의 검증된 glTF 임포트+본 평가를 신뢰하는 쪽으로 결론).
6. **결정적 비교**: 같은 세션에서 사용자가 만든 단순한 프롬프트("a person jumping
   happily") 생성물을 똑같이 렌더 → **완전히 깨끗함**(발 떨어짐 없음). 같은 파이프라인,
   같은 코드로 만든 결과인데 프롬프트만 다름.

## 결론

문제의 프롬프트를 보니:

> "A dynamic action photograph capturing a male Wushu martial artist performing the
> traditional spear technique 'Lan Na Cha' (拦拿扎)... [카메라 앵글·조명·배경·의상까지
> 묘사한 1000자 이상의 사진 스타일 프롬프트]"

이건 텍스트→모션이 아니라 **텍스트→이미지(SD) 스타일 프롬프트**임 — Kimodo는
`PORTING.md` 기준 "a person walking forward" 같은 **짧은 동작 묘사**로 학습됨. 이런
학습 분포 밖(out-of-distribution) 프롬프트를 주면, 개별 쿼터니언은 수치적으로 멀쩡해도
(정규화·연속) 다리 자세 자체가 해부학적으로 이상하게 나올 수 있음(export 코드나
extraction 파이프라인 버그가 아니라 **모델 생성 품질 문제**).

**재현/해결**: 같은 캐릭터·백엔드로 프롬프트만 짧게 바꿔서
("a martial artist in a horse stance thrusting a spear forward with both hands")
재생성 → 6프레임(0/24/48/72/96/119) 전부 깨끗하게 확인됨
(`20260916-150242_a-martial-artist-in-a-horse-stance-thrus`, seed 147032599).

## 배운 것 — 다음 세션에서 재사용할 만함

- **프롬프트는 짧고 동작 중심으로.** 사진/영화 스타일 장문 프롬프트(카메라 앵글, 조명,
  의상 디테일 등)는 Kimodo가 학습 안 한 분포라 다리·손 같은 말단 관절이 깨질 수 있다.
  웹 UI에 이런 가이드를 프롬프트 필드 placeholder나 힌트로 추가하는 것도 고려할 만함
  (아직 안 함).
- **Blender headless 진단 순서**(이번에 정착한 패턴, 재사용 가능):
  1. 여러 프레임(최소 5~6개) 렌더로 눈으로 확인.
  2. 의심되면 여러 카메라 각도로 재렌더해서 "착시(가림) vs 실제 분리"부터 구분.
  3. `world_to_camera_view`로 관절 스크린 좌표 계산 → 관찰된 위치와 수치로 대조해서
     범인 관절을 특정(눈대중 마커 배치보다 훨씬 정확함).
  4. raw `.f32`(회전 정규화·연속성) → bind json 오프셋(좌우 대칭) → 정점 그룹 내부
     3D 거리(서브클러스터 여부) → 메시 연결성(엣지 스트레치 비율, bmesh 연결요소) 순으로
     "각 레이어가 개별적으로 멀쩡한지" 하나씩 배제해나가는 게 효율적이었음.
  5. **직접 순정 코드로 FK를 재구현해서 대조하는 건 이번엔 실패**(내 스크립트 버그 가능성
     이 더 높아 폐기) — Blender의 검증된 임포트/평가 파이프라인을 기준점으로 삼는 게 나음.
  6. 최종 확인은 "같은 코드, 다른(단순한) 입력"으로 대조군을 만들어 비교하는 것 —
     이게 결정적이었음(코드 문제였으면 대조군도 깨졌을 것).

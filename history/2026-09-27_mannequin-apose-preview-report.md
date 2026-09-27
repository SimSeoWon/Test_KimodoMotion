# UE 마네킹(A-포즈)을 미리보기·리타겟에 쓰기 위한 조사 보고서

- date: 2026-09-27
- status: 1번(마네킹 미리보기) 구현·렌더 확인, 2~4번 대기
- scope: 미리보기 메시, UE5 리타겟, NS 보법 애니메이션 연계
- 작성: Claude Code (NS 세션에서 조사)

## 배경

`NS` 프로젝트는 락온 교전의 보법 스텝 이동을 코드로 먼저 만들었다(NS 레드마인 #692, 커밋
`119d40b` — 캡슐만 움직이는 스텝 구동기). 다음 단계는 발 애니메이션을 이동 거리에 맞추는
것이고(Distance Matching), 이때 쓸 **스텝 클립**과 **스탠스 전환 전신 동작**을 Kimodo로 뽑는
방안을 검토했다. NS 캐릭터는 UE 마네킹 스켈레톤(`SKM_Manny_Simple` · `SKM_Quinn_Simple` ·
`SK_Mannequin`, 모두 NS `Content/Characters/Mannequins/Meshes/`)을 쓴다.

지금 이 리포의 두 경로는 모두 마네킹과 바로 맞지 않는다.

| 경로 | 현재 | 마네킹과의 문제 |
|---|---|---|
| 웹 UI 미리보기 | `assets/extract_mixamo_soma30.py` 가 Mixamo Y Bot 을 SOMA30 에 다시 묶는다 | 매핑 표가 `mixamorig:` 본 이름 전용이다. 마네킹 메시로 미리보기할 수 없다 |
| UE5 임포트·리타겟 | `Kimodo.ImportIK`(IK Retargeter 배치) | 양팔 굽힘 방향이 반대로 꺾이는 문제가 미해결이다(`2026-09-15_testbed-import-retarget.md` 문제 4) |

## 사실 확인

1. **UE5 마네킹의 레퍼런스 포즈는 A-포즈다.** Manny/Quinn 은 팔이 수평에서 약 45° 아래로
   내려간 자세가 스켈레톤 기준 자세다(엔진 기본 사양). 어깨·겨드랑이 스키닝이 평소 자세 근처에서
   덜 찌그러지도록 한 선택이다. [주의] 이 체크아웃에서 에셋을 직접 열어 각도를 잰 것은 아니다 —
   FBX 로 내보낸 뒤 Blender 에서 `upperarm_l` 의 레스트 방향을 재서 확인한다.
2. **SOMA30 은 T-포즈다.** `export_glb.py` 의 `offsets` 에서 `LeftArm` 이 거의 순수 +X(수평)다
   (15일 기록과 같은 관찰).
3. **Y Bot 은 T-포즈다.** 그래서 지금의 Mixamo 추출은 레스트 자세 변환 없이 SOMA 의 로컬
   회전을 그대로 입혀도 맞는다.
4. **UE 쪽 해법은 IK Retargeter 의 리타겟 포즈다.** 레퍼런스 포즈는 그대로 두고 리타겟 전용
   포즈를 따로 만든다. 엔진 5.8 `IKRetargeterController.h` 에 실재하는 API:
   `CreateRetargetPose(이름, Source|Target)` · `SetCurrentRetargetPose` ·
   `AutoAlignAllBones(Source|Target, ERetargetAutoAlignMethod)` · `AutoAlignBones` ·
   `SetRotationOffsetForRetargetPoseBone(본, 회전, Source|Target)` · `ResetRetargetPose` ·
   `SnapBoneToGround`.
5. **`KimodoTestbed/` 가 디스크에서 비어 있다(2026-09-27 실측).** `CLAUDE.md` 가 설명하는
   `KimodoImportLibrary.*`(`RunIK()`) · `Kimodo.ImportIK` 콘솔 커맨드 소스가 지금 이 경로에 없다.
   git 밖(로컬 전용)이라 복구 경로는 사용자 백업뿐이다. 리타겟 작업을 재개하기 전에 소스 위치를
   먼저 확인해야 한다.

## 분석

- Kimodo 가 내는 것은 **SOMA 레스트(T-포즈) 기준의 로컬 회전**이다. 레스트가 A-포즈인
  메시를 변환 없이 SOMA 관절에 묶으면, 같은 회전이 45° 내려간 팔에 더해져 팔이 몸통으로
  파고든다. 미리보기와 리타겟이 같은 원인(레스트 자세 불일치)을 공유한다.
- 15일 기록의 다음 시도는 「**SOMA(원본) 쪽** 리타겟 포즈의 팔을 내려 Manny 에 근사」였다.
  이번 조사로는 **Manny(대상) 쪽 리타겟 포즈를 T-포즈로 맞추는 것**(`AutoAlignAllBones(Target)`
  또는 대상 팔 본 `SetRotationOffsetForRetargetPoseBone`)이 UE 의 정석에 더 가깝다. 원본이
  이미 T-포즈이므로 대상을 원본에 맞추는 편이 오프셋을 한 곳에만 둔다. 두 방법 중 무엇이 팔
  꺾임을 없애는지는 실측으로 가린다.
- 미리보기도 같은 원리다 — Blender 에서 마네킹을 **T-포즈로 편 뒤 그 자세를 레스트로 적용**
  (Apply Pose as Rest Pose)하고 SOMA30 에 묶으면, Kimodo 회전을 Y Bot 과 같은 방식으로 입힐 수 있다.

## 계획

| # | 작업 | 산출물 | 선행 |
|---|---|---|---|
| 0 | 마네킹 FBX 내보내기 — NS 에디터에서 `SKM_Manny_Simple` 우클릭 → Asset Actions → Export → FBX | `assets/mannequin_src/SKM_Manny_Simple.fbx` | 사람(에디터) |
| 1 | 마네킹 추출 스크립트 — Y Bot 스크립트를 본 매핑만 바꿔 재사용하고, 추출 전에 팔을 T-포즈로 펴 레스트로 적용 | `assets/extract_mannequin_soma30.py` → `assets/mannequin_processed/*_soma30_bind.json`, 웹 UI 캐릭터 선택기에 마네킹 | 0 |
| 2 | 리타겟 팔 꺾임 — 대상(Manny) 리타겟 포즈 자동 정렬 시도, 안 되면 원본 쪽 보정과 비교 | `Kimodo.ImportIK` 수정, 팔 굽힘 방향 육안 확인 | Testbed 소스 확인 |
| 3 | 보법 프리셋 — 스리아시 전진·후진 한 발, 스탠스 전환 전신 동작의 프롬프트·키포즈 | 웹 UI 프롬프트/포즈 프리셋 | 1 |
| 4 | 루트 이동 보존 확인 — NS 의 Distance Matching 은 루트가 실제로 움직인 클립이 필요하다. 거리 커브는 UE 의 Distance Curve 모디파이어로 붙이므로 여기서는 루트 궤적 보존만 확인 | 확인 기록 | 2 |

**본 이름 매핑(초안, 1번에서 확정):** `pelvis`→Hips(0) · `spine_01`→Spine(1) · `spine_02`·`spine_03`→Spine1(2) ·
`spine_04`·`spine_05`→Spine2(3) · `neck_01`→Neck(4) · `neck_02`→Neck1 · `head`→Head(6) ·
`clavicle`·`upperarm`·`lowerarm`·`hand` → Shoulder·Arm·ForeArm·Hand · `thigh`·`calf`·`foot`·`ball` →
UpLeg·Leg·Foot·ToeBase. 트위스트 보정 본(`upperarm_twist_01_l` 등)은 부모 본으로 합친다.
손가락은 Y Bot 처럼 Hand 에 가중치를 모으고 위치는 원본 좌표를 쓴다. 인덱스는 스크립트의
`MIXAMO_TO_SOMA` 와 같은 SOMA30 순서를 따른다 — 숫자는 추출 스크립트 작성 때 `export_glb.py` 로 다시 확인한다.

## 1번 결과 — 마네킹 미리보기 (2026-09-27 구현)

`SKM_Quinn_Simple.FBX`(NS 플레이어 `BP_ThirdPersonCharacter` 가 쓰는 메시)를 Blender 5.2 로 실측한 사실:

- 위팔은 수평에서 **52.9°** 아래(A-포즈 확인), 아래팔은 앞으로 굽어 손이 몸 앞에 있다. 허벅지는 수직에서 약 2.7° 벌어져 있다.
- **정점 웨이트가 트위스트 본에 있다** — `upperarm_*`·`lowerarm_*`·`thigh_*`·`calf_*`·`spine_05` 에는 정점 그룹이 없고
  `*_twist_01/02_*` 에 있다. 본 이름 매핑 초안(위)만으로는 추출이 실패했을 것이다.
- 기본 FBX 내보내기에 **LOD0~2 가 모두 들어온다**(45,993 / 14,865 / 7,421 정점). 셋을 합치면 메시가 세 겹이 된다.
- 단위는 cm, 0.01 스케일 부모 아래에 있고 정면은 Blender -Y(= glTF +Z, SOMA 정면과 같다). `_l` 이 +X(SOMA 왼쪽과 같다).

`assets/extract_mannequin_soma30.py` 를 새로 만들었다(Mixamo 판과 출력 형식이 같다). 팔 체인(위팔·아래팔·손)을 수평 ±X,
다리 체인(허벅지·종아리)을 수직으로 포즈를 준 뒤 아마추어 변형이 적용된 메시와 포즈 본 위치를 레스트로 쓰고,
트위스트 본은 부모의 SOMA 조인트로, LOD0 만 쓴다. 결과 `assets/mixamo_processed/quinn_simple_soma30_bind.json`
(45,993 정점, 손 위치 x=0.692m — SOMA 0.724m) — 웹 UI 가 이 폴더를 캐릭터 목록으로 읽으므로 `server.py` 는 고치지 않았다.

**색:** UE 마네킹의 색은 머티리얼 파라미터가 아니라 디퓨즈 텍스처(`T_Quinn_01_D`·`T_Quinn_02_D`)에서 나온다 — FBX 에는
텍스처가 안 딸려 나가고(가져온 머티리얼은 기본 회색, 정점 색은 전부 검정), `MI_Quinn_01` 의 `Paint Tint` 도 회색 하나다.
사용자가 두 텍스처를 FBX 옆에 PNG 로 내보내면, 스크립트가 슬롯 이름(`MI_Quinn_01` → `T_Quinn_01_D.*`)으로 찾아 정점마다 UV 로
샘플해 정점 색(선형)으로 넣는다. 렌더에서 UE 와 같은 밝은 판·어두운 관절 두 톤이 나온다. 텍스처가 없으면 단색 회색이다.

**확인:** 같은 모션(`20260916-154847_lateral-stance…`)을 Y Bot 과 Quinn 으로 `pretty_export_glb.py` 내보내기 → Blender
Workbench 로 1·47·95 프레임 정면·측면 렌더. 두 캐릭터의 팔·다리 자세가 일치하고 팔이 몸통을 파고들지 않는다.
웹 UI 에서의 확인은 서버를 다시 띄울 때 사용자가 한다(실행 중 프로세스는 건드리지 않았다).

## 라이선스

에픽 마네킹은 언리얼 엔진 프로젝트에 쓰도록 제공되는 콘텐츠다. 로컬 미리보기에는 쓰되,
Mixamo 와 같은 이유로 **원본 FBX 와 가공 결과를 git 에 올리지 않는다** —
`assets/mannequin_src/` 를 `.gitignore` 에 추가했다(가공 결과는 이미 제외되는 `assets/mixamo_processed/` 에 쓴다).

## 결정 대기

- 2~4 진행 여부. 추천은 **2** — 리타겟 팔 꺾임이 풀려야 Kimodo 모션을 NS 에서 실제로 쓸 수 있다.
- `KimodoTestbed/` 소스의 행방(백업 여부).

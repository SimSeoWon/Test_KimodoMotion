---
date: 2026-09-16
tags: [webui, run-webui.bat, preflight, tpose, mixamo, multi-character, pretty_export_glb, extract_mixamo_soma30]
status: done
confirmed-by-user: partial
---

# 더블클릭 실행기 + 구동 전 점검 + T포즈 기본 미리보기 + 다중 Mixamo 캐릭터

`webui/` 자체(서버/파라미터 폼/model-viewer)는 이전 세션([[2026-09-16_webui]])에서 만들었고,
이번 세션은 "비프로그래머가 직접 켠다"는 요구사항에 맞춰 그 위에 실행기·점검·프리뷰를 더했다.

## 1. `run-webui.bat` — 더블클릭 실행기

`py webui\server.py`를 직접 치는 대신 더블클릭 한 번으로:
1. `py` 자체가 없으면 python.org 설치 안내를 보여주고 멈춤(비프로그래머 배려 — 사용자가
   "프로그래머가 아닌 사람이 써야 해서 파이썬을 물어본 거였어"라고 확인해준 요구사항).
2. `py webui\server.py --check`로 구동 가능 여부 점검, FAIL이 있으면 원인을 보여주고
   창을 유지(`pause`).
3. 통과하면 서버를 **별도 창(`start "kimodo-motion webui" /min ...`)으로 분리 실행** — 이
   배치파일(또는 그걸 띄운 콘솔)을 닫아도 서버는 안 죽는다("PC에 귀속되지 않도록"이라는
   요구사항을 "이 창을 닫아도 서버는 살아있다"로 해석). 잠깐 기다렸다 기본 브라우저로
   `http://127.0.0.1:8188/`를 자동으로 연다.
4. 서버를 끄려면 새로 뜬 "kimodo-motion webui" 창을 닫으면 됨.

**버그 하나 겪고 정착한 조합**: 배치파일 안에 한글 `echo`를 그냥 넣으면(테스트 하네스의
비대화형 콘솔에서) `chcp 65001`만 있어도, 없어도 전부 깨졌다(`'?' is not recognized...` 같은
글자 단위 파싱 오류). **UTF-8 BOM + CRLF 줄바꿈 + `chcp 65001` 세 가지가 같이 있어야** cmd.exe가
제대로 읽는다는 걸 최소 재현(`_diag_test.bat`)으로 확인 — LF만 쓰거나 BOM만 붙이는 건 안 됐다.
Write 도구는 기본 LF/무BOM으로 쓰므로, 파이썬으로 후처리(`\n`→`\r\n`, `\xef\xbb\xbf` 프리픽스)
해서 저장해야 함. 실측 확인: `cmd /c run-webui.bat` 끝까지 실행 → 점검 통과 → 서버가 별도
프로세스로 뜸 → `/api/status` 200 확인, 테스트 프로세스는 정리함.
**미확인**: 실제 더블클릭 시 브라우저 창이 뜨는지는 이 세션(원격 실행)에서 육안 확인 불가 —
사용자가 "웹UI 잘 나오네"로 확인해줌(2026-09-16).

## 2. `webui/server.py --check` — 구동 전 점검

`/api/status`에 필드 확장 + 콘솔 전용 `print_preflight()`:
- Vulkan: `%SystemRoot%\System32\vulkan-1.dll` 존재만 빠르게 확인(매번 `vulkaninfo` 실행은
  느려서 로더 DLL 존재로 대신함).
- Blender: `C:\Program Files\Blender Foundation\Blender 5.2\blender.exe` 고정 경로 +
  PATH 탐색. **Blender/Mixamo는 서버 실행 자체엔 필요 없음**(캡슐 폴백) — 사용자가
  "믹시모 리소스도 요구하자, 없으면 [안내해달라]"고 해서 FAIL이 아니라 WARN으로 두되
  리소스 구하는 3단계(mixamo.com에서 받기 → assets/mixamo_src/ → Blender 커맨드)를
  콘솔에 그대로 찍어주게 함.
- Python 라이브러리(pip)는 점검 대상에서 뺐다 — `webui/server.py` 자체가 표준 라이브러리만
  쓰도록 이미 설계돼 있어서(외부 의존성 없음) 점검할 게 없음. 점검 출력 맨 위에 그 사실을
  명시(비프로그래머가 "pip install 해야 하나" 헷갈리지 않게).

## 3. T포즈 기본 미리보기

생성 이력이 없어도 빈 화면 대신 서 있는 모델을 보여달라는 요청. `export_glb`류가 기대하는
raw 모션 입력(`root_positions.f32`/`local_rotations_xyzw.f32`)을 **항등 회전 2프레임**으로
직접 합성해서, 실제 생성과 똑같은 `pretty_export_glb.py` 경로(Mixamo 바인딩 우선, 없으면
캡슐)로 내보낸다 — 프리뷰 메시 로직을 두 벌 관리하지 않기 위함. `webui/static/tpose_<모델
id>.glb`에 캐시하고 한 번 만들면 재사용(서버 재시작마다 재생성 안 함). 서버 시작/`--check`
시 기본 캐릭터 것만 미리 만들어 첫 로드 지연을 없애고, 나머지 캐릭터는 콤보박스에서 고를 때
`/api/tpose?model=<id>`가 그때그때 만든다.

## 4. 여러 Mixamo 캐릭터 + 콤보박스

"믹시모 리소스도 여러 개를 선택할 수 있어야 하고, 콤보박스로 선택" 요청으로 단일
`ybot_soma30_bind.json` 하드코딩을 걷어냄:

- **`assets/extract_mixamo_soma30.py`**: `--fbx`/`--out` 인자 추가(Blender는 스크립트 인자를
  `--` 뒤에 받음). `--out` 생략 시 fbx 파일명을 슬러그화해서 자동 명명
  (`Warrior.fbx` → `warrior_soma30_bind.json`). 인자 없이 돌리면 기존 Y Bot 하드코딩과
  100% 동일하게 동작(하위호환). 메시 선택도 `Alpha_Surface`/`Alpha_Joints` 이름 고정을
  걷어내고 armature 아래 메시를 전부 자동으로 찾아 합치도록 일반화(정점 수 제일 많은 메시를
  `base_color` 기본값으로) — `MIXAMO_TO_SOMA`는 Mixamo 오토리거가 어느 캐릭터에나 똑같이
  붙이는 `mixamorig:` 본 이름 기준이라 그대로 재사용되고, 표준 리그가 아니면(매핑에 없는
  vertex group) 여전히 에러로 바로 멈춘다(추측 안 함). 출력 json에 `"label"` 필드 추가(웹
  UI 콤보박스 표시용, fbx 파일명 stem).
- **`scripts/pretty_export_glb.py`**: `--mixamo-bind <경로>`(특정 바인딩 강제) /
  `--mixamo-bind none`(있어도 무시하고 캡슐 강제) 추가. `create_bone_mesh` 콜백은 vendor
  시그니처가 고정이라 인자를 못 받으므로, 모듈 전역 `_selected_bind_path`를 `main()`이
  CLI 인자로 덮어쓰는 방식(생략 시 하위호환으로 `ybot_soma30_bind.json` 그대로 찾음).
- **`webui/server.py`**: `list_mixamo_models()`가 `assets/mixamo_processed/*_soma30_bind.json`을
  전부 스캔해서 `{id, label, bind}` 목록으로(캡슐은 항상 첫 항목). 새 라우트
  `GET /api/mixamo-models`(목록+기본값), `GET /api/tpose?model=<id>`(그 캐릭터 T포즈,
  없으면 즉석 생성 후 캐시). `run_generation()`이 `mixamo_model` 파라미터를 받아
  `pretty_export_glb.py --mixamo-bind`로 그대로 전달, `meta.json`에도 기록(히스토리
  카드 클릭 시 콤보박스도 그때 선택했던 캐릭터로 복원).
- **프런트**: 파라미터 폼에 "미리보기 캐릭터 (Mixamo)" `<select>` 추가. 페이지 로드 시
  `/api/mixamo-models`로 채우고 기본값의 T포즈를 `/api/tpose?model=...`로 표시. 실제
  생성 결과를 보고 있는 동안(`showingRealResult` 플래그)은 콤보박스를 바꿔도 뷰어를
  건드리지 않음 — 다음 Generate부터 반영.

## 검증

`py -m py_compile`로 문법 확인, `--check` 재실행(캐시 삭제 후)으로 `ybot`이 콤보박스 목록에
잡히는 것 확인, 서버 기동 후 `/api/mixamo-models`·`/api/tpose?model=ybot`(2.1MB)·
`?model=capsule`(54KB)·`?model=nonexistent`(캡슐로 안전 폴백)·쿼리 없음(기본값) 전부 curl로
200 확인. `POST /api/generate`를 `mixamo_model:"capsule"`로 한 번, 아예 안 보내고(하위호환)
한 번 — 둘 다 28초대에 정상 완료, 후자가 `mixamo_model: "ybot"`으로 자동 채워지는 것까지
확인. 테스트 산출물/서버 프로세스는 정리함.

**미확인(다음에 사용자가 브라우저로 볼 때 확인 필요)**: 콤보박스 UI 자체 동작(옵션 렌더링,
선택 시 T포즈 스왑)은 API 레벨까지만 확인했고 실제 브라우저 렌더링은 못 봄. 기존
`ybot_soma30_bind.json`은 `"label"` 필드 추가 전에 만들어진 파일이라 콤보박스에 "Y Bot"이
아니라 "ybot"(파일명 기반 폴백)으로 나온다 — Blender 커맨드를 한 번 더 돌리면 "Y Bot"으로
바뀌지만 지금 상태로도 동작엔 지장 없어서 굳이 재실행 안 함.

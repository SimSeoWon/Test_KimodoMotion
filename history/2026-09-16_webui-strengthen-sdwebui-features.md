---
date: 2026-09-16
tags: [webui, plan-mode, stable-diffusion-webui, storyboard, sequence, batch, cancel, presets, lora, cfg, negative-prompt, kimodo.cpp, denoiser, generate.cpp]
status: done
confirmed-by-user: partial
---

# 웹 UI "강화" — Stable Diffusion WebUI 대비 리서치 + Tier 1~3 구현

## 배경

[[2026-09-16_launcher-tpose-multichar]] 직후 사용자가 "로라처럼 좀더 강화시킬 수 있어?" →
"긍정/부정 프롬프트도" → "전신/상체/하체도" 식으로 기능을 계속 추가 요청. 요청이 빠르게
불어나서(LoRA·CFG·부정 프롬프트·신체 부위 편집 등) 무작정 다 만들기 전에 **Plan Mode로
전환해서 SD WebUI 대비 리서치부터 하고 범위를 정리**했다(사용자가 "일단 플랜을 작성할까
했어"로 명시적 요청). 플랜 파일은 `~/.claude/plans/deep-gathering-tiger.md`에 남아있음.

## 리서치 — 코드 + NVIDIA 공식 페이지 대조

`vendor/kimodo.cpp` 소스를 훑어서 "이미 있는데 안 쓰는 것"과 "아예 없는 것"을 구분했고,
사용자가 공유한 `research.nvidia.com/labs/sil/projects/kimodo/`를 WebFetch로 확인해서
어느 게 NVIDIA 공식 기능이고 어느 게 이 포팅판(kimodo.cpp)만의 내부 구현인지 대조함:

- **이미 있는데 완전히 안 쓰던 것**: `kmd-generate.exe --sequence`(멀티 프롬프트 타임라인,
  `generate.cpp:25`/`model::generate_text_sequence`) — NVIDIA 공식 "Sequence of Prompts"
  기능인데 웹 UI도 `generate-motion.ps1`도 연결이 안 돼 있었음. CFG(`text_cfg_weight`,
  `generate.cpp`에 2.0 하드코딩)도 마찬가지.
- **kimodo.cpp 자체 구현 디테일 (NVIDIA 공식 페이지엔 없음)**: LoRA 스케일(2.0 하드코딩,
  `llm_text_encoder.cpp:145`) — 학습 시점에 맞춰진 값이라 세게 돌린다고 항상 좋아지는 게
  아님. 부정 프롬프트도 NVIDIA 페이지엔 없고, CFG의 "unconditional" 브랜치가 항상
  텍스트=0벡터인 걸 이용해 새로 만들어야 하는 기능.
- **신체 부위 편집**: NVIDIA는 "End-Effector Constraints"(손/발 위치·회전 고정)와
  "Full Body Constraints"(특정 프레임 전신 포즈 고정)로 공식 지원 — 내가 처음 짐작한
  "상체/하체 영역 나누기"가 아니라 **키프레임/말단 고정** 개념. 코드상 `observed`/
  `observed_mask`(`denoiser.cpp`) 브랜치가 이미 있지만 `kmd-generate.exe` 경로에선 항상
  0이라 사실상 미사용. → **Tier 4로 보류**, 나중에 이 방향으로 다시 설계하기로 함.
- **적용 불가로 판정**: 프롬프트 강조 문법(`(word:1.3)`) — 텍스트 인코더가 LLM2Vec으로
  문장 전체를 4096차원 벡터 하나로 뭉개는 구조라 SD의 토큰별 크로스어텐션 개념이 없음.
  샘플러 선택도 `diffusion.cpp`에 DDIM(cosine schedule) 하나뿐이라 제외.

## 구현 — Tier 1 (웹 UI 레벨만, C++ 재빌드 불필요)

`webui/server.py`:
- **스토리보드 모드**: `run_generation()`이 `segments`(구간 리스트)가 오면 `--sequence`
  CLI 모드로 전환. 실제 생성 결과(20+20프레임 두 구간)까지 curl로 end-to-end 확인,
  `generated N frames` stdout을 정규식으로 파싱해서 `frame_count`를 실제값으로 기록(기존
  단일 모드에도 같이 적용 — 더 정확해짐).
- **배치 개수**: `do_POST`가 `batch_count`(최대 8)만큼 반복 호출, seed는 명시했으면
  +1씩 증가, 비웠으면 매번 새로 랜덤. `batch_count==1`이면 기존처럼 meta 하나만,
  아니면 `{"items":[...]}`로 응답(프런트 하위호환).
  - 이때 `run_generation()`을 배치 인자만 바꿔서 재사용하려고 매 반복 `dict(params)`로
    얕은 복사 후 `seed`만 덮어씀.
- **취소 버튼**: `subprocess.run` → `run_cancelable()`(Popen 핸들을 `current_process`
  전역에 잠깐 공개)로 교체. `/api/cancel`이 다른 스레드에서 `terminate()`. Windows라
  종료 코드로 "취소" vs "진짜 실패"를 구분 못 해서 `cancel_requested` 플래그를 따로 둠.
  실제로 280프레임/100스텝짜리 긴 생성을 걸어놓고 2초 뒤 취소 → `{"cancelled":true}` +
  `{"error":"생성이 취소되었습니다."}` 확인.
- **프롬프트 프리셋**: `webui/prompt_presets.json`(로컬 상태, `.gitignore` 추가) +
  `/api/presets`(GET/POST 저장/POST delete).

프런트(`index.html`/`app.js`/`style.css`): 프리셋 콤보박스, 스토리보드 토글(켜면
단일 프롬프트 패널을 구간 리스트로 교체), 배치 개수 필드, 취소 버튼.

## 구현 — Tier 2 (env var로 기존 파라미터 노출, 재빌드 1회)

`vendor/kimodo.cpp` 기존 패턴(`layer_chunk_size()`처럼 env var 읽고 기본값 폴백)을
그대로 따름:
- `llm_text_encoder.cpp`: `lora_scale()` 추가(`KIMODO_LORA_SCALE`, 기본 2.0, 0~10
  범위 검증), `layer_graph()`의 `ggml_scale(ctx, lora, 2.F)`를 교체.
- `generate.cpp`: `env_float()` 추가, 단일/시퀀스 두 호출부의 하드코딩된 `2.F, 2.F`를
  `env_float("KIMODO_TEXT_CFG", 2.F)`/`env_float("KIMODO_CONSTRAINT_CFG", 2.F)`로.
- `webui/server.py`: `lora_scale`/`text_cfg` 파라미터를 받아 `KIMODO_BACKEND`와 같은
  방식으로 env에 심음(안 주면 env var 자체를 안 심어서 기존 기본값 그대로).
- 프런트: "고급 옵션"에 CFG·LoRA 슬라이더 2개 + "NVIDIA 공식 기능 아님, 세게 돌린다고
  항상 좋아지지 않는다"는 안내 문구.

## 구현 — Tier 3 (부정 프롬프트, 새 기능·첨가식)

CFG 공식이 `uncond + w*(text-uncond)`인데, 지금까지 `uncond`가 항상 0벡터였던 걸
"부정 프롬프트로 인코딩한 텍스트"로 채우는 표준 diffusion negative-prompt 기법:

- `denoiser.hpp/.cpp`: `run_separated_cfg_denoiser`/`sample_motion_from_noise`/
  `run_separated_cfg_denoiser_conditioned`에 `std::span<const float> negative_embedding = {}`
  **트레일링 기본 인자**로 추가(기존 호출부는 그대로 컴파일됨). `run_separated_cfg_denoiser_
  conditioned` 안에서 branch 2(unconditional)의 `text` 슬롯을 `negative_embedding`이 있으면
  그 값으로 채움 — 없으면 기존과 완전히 동일(zero로 남음).
- `include/kimodo/kimodo.hpp`/`model.cpp`: `generate_text`/`generate_embedding`에도
  `negative_prompt`/`negative_embedding` **트레일링 기본 인자** 추가. `capi.cpp`(C ABI,
  `kimodo_generation_options` 구조체)는 **의도적으로 안 건드림** — `size` 필드로 정확히
  일치해야 하는 버전 검사라 구조체를 늘리면 외부 임베더가 깨질 수 있어서, 이번 기능은
  순수 C++ API(`generate.cpp`가 쓰는 경로)에만 추가.
- `generate.cpp`: 기존 8-arg 시그니처는 그대로 두고 **선택적 9번째 인자**(부정 프롬프트
  파일)로 완화(`argc != 8 && argc != 9`). `generate-motion.ps1`은 안 건드려도 계속 동작.
- `webui/server.py`: `negative_prompt`가 있으면 `negative_prompt.txt`를 써서 9번째
  인자로 전달. **스토리보드 모드 + 부정 프롬프트 조합은 명시적으로 거부**(`generate_text_
  sequence`엔 이 기능을 안 넣었음 — 조용히 무시하지 않고 에러 메시지로 알림).

## 빌드 + 검증

`cmake --build vendor/kimodo.cpp/build --config Release --target kmd-generate` 한 번으로
Tier 2+3 전부 반영(경고만 있고 에러 없음 — DLL 인터페이스 C4251, getenv C4996은 기존에도
있던 종류).

C++ 레벨 직접 검증(raw .f32 비교, `py` 스크립트로 NaN/finite + 값 차이 확인):
- 베이스라인(env var 없음) vs LoRA=1.0+CFG=3.5+부정프롬프트 동시 적용 → 2400개 중 2391개
  float가 달라짐, NaN 0개.
- 같은 시드·기본 LoRA/CFG에서 **부정 프롬프트만** 추가 → 2400개 중 2380개가 달라짐, NaN
  0개 — 부정 프롬프트 단독으로도 실제로 결과에 영향을 준다는 것까지 격리해서 확인.
- `KIMODO_LORA_SCALE=999`(범위 밖) → 크래시 없이 "KIMODO_LORA_SCALE must be a finite
  number in 0..10" 에러로 깔끔하게 종료 확인.

웹 UI 레벨에서도 curl로 재확인: `text_cfg`/`lora_scale`/`negative_prompt`를 준 생성,
스토리보드+부정프롬프트 조합 거부 메시지, 아무것도 안 준 완전 하위호환 경로(meta에
`lora_scale`/`text_cfg`/`negative_prompt`가 전부 `null`로 기록됨) 전부 확인.
마지막으로 `run-webui.bat` 실행기로 처음부터 끝까지(점검 → 서버 기동 → 브라우저 오픈
시도 → `/`·`/static/app.js`·`/api/mixamo-models` 200) 재확인. 테스트 산출물/프로세스는
매번 정리함.

## 정정 — LoRA 강도는 뺐음 (같은 세션, 사용자가 upstream 링크로 재확인 요청)

사용자가 `github.com/nv-tlabs/kimodo`(NVIDIA 원본)를 링크로 주면서 "그냥 있는 거 쓰는게
맞는거야?"라고 재확인 요청 → README를 WebFetch로 조사해서 CFG(`--cfg_type`/`--cfg_weight`,
"separated" 모드가 정확히 우리 `text_cfg`/`constraint_cfg`)와 멀티프롬프트(`prompt`가
"시퀀스"도 받음)는 공식 설계와 일치한다는 걸 재확인. 그 다음 사용자가 "소스코드 없이
실행파일만 설치한 거냐"고 물어서 `vendor/kimodo.cpp`(서드파티 C++/GGML 재구현,
`localai-org/kimodo.cpp`, NVIDIA 코드 복사 아님)가 완전한 소스임을 확인하다가
`PORTING.md`에서 **중요한 정정거리**를 발견함:

> Kimodo의 텍스트 인코더는 `Llama-3-8B` + **"supervised PEFT adapter"**(=LoRA)를 씀 —
> 이게 NVIDIA 원본의 실제 공식 아키텍처다.

즉 지난번 "LoRA는 공식 기능 아니고 포팅판이 만든 것"이라고 한 판정은 **절반만 맞았음**.
`ggml_scale(ctx, lora, 2.F)`의 2.0은 SD LoRA 가중치처럼 "세게 주면 스타일이 강해지는"
조절용 값이 아니라 **NVIDIA 원본 PyTorch 모델과 수치를 정확히 맞추는(parity) 데 필요한
고정값**이었음 — 학습된 PEFT adapter 자체의 스케일이라, 벗어나면 "덜 강한 스타일"이
아니라 텍스트 이해력 자체가 깨지는 방향. CFG(`text_cfg`)는 반대로 진짜 조절하라고
설계된 값이라 그대로 둠.

**수정**: 사용자가 "빼고 CFG는 그대로 둬"라고 확정 →
- `vendor/kimodo.cpp/src/llm_text_encoder.cpp`: `lora_scale()`/`KIMODO_LORA_SCALE` env var
  전부 제거, `layer_graph()`의 `linear` 람다를 원래 하드코딩 `2.F`로 되돌리고 주석으로
  "이건 조절용이 아니라 parity 고정값"이라고 남김.
  `cmake --build vendor/kimodo.cpp/build --config Release --target kmd-generate`로 재빌드.
- `webui/server.py`/`app.js`/`index.html`: `lora_scale` 파라미터·env var 설정·meta 필드·
  프런트 슬라이더(LoRA 강도) 전부 제거. `text_cfg`(프롬프트 강도/CFG)는 그대로 유지.
- 검증: 재빌드 후 `POST /api/generate`에 `text_cfg`를 줘서 정상 반영되는 것과, 응답
  meta에 더 이상 `lora_scale` 키가 없는 것을 curl로 확인. (중간에 이전 테스트용 서버
  프로세스가 안 죽고 남아있어서 재검증 결과가 한 번 헷갈렸음 — `tasklist`로 python.exe
  여러 개 떠있던 걸 발견하고 전부 정리한 뒤 재확인함. 로컬 서버 테스트할 때마다 이전
  프로세스가 남아있는지 먼저 확인하는 습관이 필요함.)

## 백로그 — DPM-Solver++ / Karras 스케줄 (사용자 요청, 2026-09-16)

사용자가 SD WebUI의 "카라스/오일러/DDIM" 같은 샘플러·스케줄 선택지를 물어봐서 설명하다가
"관련해 연구하는 거 없어?"라는 질문에 WebSearch로 확인:

- **StableMoFusion**(arxiv 2405.05691)이 모션 디퓨전에 DDPM/DDIM 대신 **DPM-Solver++**(2차
  수치해법) + **Karras Sigma** 스케줄을 적용해서 같은 스텝 수로 속도·품질을 개선했다고
  보고함. BioMoDiffuse 등에도 같은 기법이 쓰임.
- **NVIDIA Kimodo 원본과는 무관한 별도 연구** — kimodo.cpp는 원본 그대로 DDIM+코사인
  스케줄만 구현(`diffusion.cpp`). 이걸 가져오려면 DPM-Solver++ 수치해법 자체를 새로
  구현해야 해서 Tier 4급(또는 그 이상) 작업.
- **사용자 결정: 지금은 보류, 백로그로만 남김.** 나중에 다시 꺼낼 때 이 두 논문
  (StableMoFusion, Biomechanics-Guided Residual Approach — arxiv 2503.06151)부터
  참고할 것.

## 타임라인 UI (Deforum류 prompt schedule 시각화)

사용자가 SD 확장 도구(Deforum/AnimateDiff)의 "타임라인"(프레임 축에 프롬프트를 꽂아두고
드래그하는 UI)을 언급 — 이미 만든 "스토리보드 모드"가 개념적으로 같은 것(`--sequence`)임을
설명하고, "바로 추가해줘"로 확정.

**설계**: 드래그 리사이즈/재정렬까지 있는 풀 인터랙티브 타임라인 대신, **기존 리스트형
구간 편집(`segment-row`)을 그대로 소스 오브 트루스로 두고 그 위에 읽기 전용 시각화 바를
얹는** 방식을 택함 — 입력 로직을 두 군데(드래그 + 리스트)에 중복 구현할 필요가 없고,
테스트 안 된 드래그 상호작용이 깨질 위험도 없음.

- `webui/static/app.js`: `renderTimeline()` — `collectSegments()`로 현재 구간을 읽어
  프레임 수 비율대로 `flex-basis`를 나눈 색깔 블록을 그림. 블록 클릭 시 해당 `segment-row`로
  스크롤+포커스. `addSegmentRow()`가 각 입력 필드에 `input` 리스너를 달아 타이핑/프레임
  수 변경마다 자동 재렌더, 삭제 버튼도 재렌더를 트리거 — 별도 "적용" 버튼 없이 항상 최신
  상태를 반영.
- `index.html`/`style.css`: `#timeline-bar` + `.timeline-segment`(색깔 순환 6종) +
  `.timeline-segment.empty`(구간 없을 때 안내 문구).

## 브라우저 실측 검증 (claude-in-chrome, 같은 세션)

지금까지 새 프런트엔드 기능들을 API 레벨로만 확인하고 "실제 브라우저에서 본 적 없음"으로
남겨뒀었는데, 이번에 claude-in-chrome로 직접 열어서 확인함:
- 최초 로드: T포즈 프리뷰(Y Bot), 부정 프롬프트 필드, 프리셋 드롭다운, 히스토리 카드 전부
  정상 렌더, 콘솔 에러 0건.
- 스토리보드 모드 켜기 → 구간 2개짜리 타임라인 바 렌더 확인 → 구간1 프롬프트 입력+구간2
  프레임 180으로 변경+프롬프트 입력 → 타임라인 블록이 **실시간으로 텍스트/폭 전부 반영**
  (180프레임 블록이 60프레임 블록보다 3배 넓게) 확인.
  구간 추가(3번째 블록 생김) → 삭제(다시 2개로) → 정상. 타임라인 블록1 클릭 →
  실제로 구간1 입력창에 포커스 이동하는 것까지 확인.
- 스토리보드 모드 끄기 → 원래 단일 프롬프트 화면으로 깨끗하게 복귀.
- 고급 옵션 펼치기 → "프롬프트 강도 / CFG 2.0" 슬라이더만 있고 LoRA 슬라이더는 없는 것
  (앞서의 되돌리기 반영) 육안 확인.
전체 과정 콘솔 에러 0건. 테스트 탭/서버 프로세스 정리함.

## 남은 것

- **Tier 4(신체 부위 편집)는 별도 설계 논의 필요** — "End-Effector/Full-Body 키프레임
  고정" 방향으로, 고정하는 쪽에 어떤 포즈를 넣을지(T포즈 vs 직전 결과)부터 정해야 함.
  이번엔 손 안 댐.
- **백로그**: DPM-Solver++/Karras 스케줄 샘플러 추가(위 참고) — 사용자가 나중에 하자고 함.
- 배치·취소 버튼·프리셋 저장/삭제는 여전히 API 레벨까지만 확인(위 브라우저 검증에서는
  타임라인/CFG·LoRA 중심으로만 봄) — 다음에 마저 육안 확인하면 좋음.
  — 다음에 사용자가 열어보고 확인 필요.
- `ybot_soma30_bind.json`이 `"label"` 필드 추가 전에 만들어진 파일이라 콤보박스에
  "Y Bot" 대신 "ybot"으로 나오는 건 [[2026-09-16_launcher-tpose-multichar]]에서 이미
  기록한 기존 이슈, 동작엔 지장 없음.

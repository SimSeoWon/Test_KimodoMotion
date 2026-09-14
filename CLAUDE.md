# CLAUDE.md — kimodo-motion

kimodo.cpp(NVIDIA Kimodo 텍스트→모션, C++/GGML 포팅판)로 UE5(`ModularStage`/`NS`)용
애니메이션을 뽑는 서브프로젝트. 뭐 하는 리포인지는 `README.md` 참고.

## [중요] 세션 시작 시 반드시 먼저 읽을 것

**`history/` 안에서 가장 최근 날짜 파일을 읽는다.** 지난 세션에서 뭘 만들었는지, 어떤
버그를 왜 겪었는지, 그 원인이 뭐였는지, 다음에 뭘 하기로 했는지가 거기 있다 — 안 읽으면
같은 API 이름을 잘못 추측하는 것 같은 삽질을 처음부터 반복하게 된다(실제로 이번 프로젝트
초반에 IK Retargeter op 이름을 두 번 잘못 추측했다).

작업이 끝나거나(사람이 확인·승인한 뒤) 중요한 결정을 내렸으면, `history/`에
`YYYY-MM-DD_<요약>.md`로 새 기록을 남긴다 — 형식은 기존 파일 아무거나 보고 따라 하면 된다.
trivial한 것(오탈자, 변수명 변경)은 안 남겨도 된다.

## 구조

- `vendor/kimodo.cpp/` — git submodule, kimodo.cpp 본체. 빌드 산출물(`build/`, `models/`,
  `generated/`)은 커밋 안 함.
- `scripts/generate-motion.ps1` — 프롬프트 → `animation.glb` 원클릭.
- `KimodoTestbed/` — **로컬 전용 UE5.8 샌드박스, git에 안 올라간다**(`.gitignore` 참고,
  사용자 결정 2026-09-15). `NS`/`ModularStage`에 바로 실험하지 않고 여기서 UE5 임포트/리타겟
  자동화 코드를 먼저 검증한다. 새로 만든 코드가 아니라 "실험대"이므로 자유롭게 고치고
  되돌려도 된다.
- `history/` — 위 참고.

## 이 기계(`.33`)에서 알아둘 것 — 루트 `CLAUDE.md`도 적용됨

`C:\Users\USER\CLAUDE.md`(이 기계 전체에 적용되는 문서)의 원칙도 그대로 따른다 — 특히
**사용자가 지금 작업 중일 수 있다**: UE5 에디터를 스크립트로 띄우기 전에 이미 열려있는
에디터가 사용자 본인 세션인지 확인한다(타 프로세스 강제종료 전 확인 — 이번 프로젝트에서
실제로 몇 번 물어봄). Vulkan 추론(`generate-motion.ps1`)도 마찬가지로 에디터가 떠 있으면
VRAM을 나눠 쓴다는 걸 감안.

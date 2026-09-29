---
name: kimodo-follow-upstream
description: vendor/kimodo.cpp 를 원본(localai-org/kimodo.cpp main) 최신으로 따라간다 — 포크 motion/main 에 merge → 빌드·ctest → 포크 push → 포인터 검사 → 루트 포인터 커밋. "원본 따라가", "kimodo.cpp 업데이트", "upstream 반영", "서브모듈 최신화" 같은 요청에 쓴다.
---

# kimodo.cpp 원본 따라가기

절차는 **스크립트가 집행한다** — 손으로 단계를 밟지 않는다. 규칙의 정본은 `README.md`
「kimodo.cpp 포크와 서브모듈」이고, 스크립트는 그 순서를 지키며 어긋나면 **거절**한다.

1. 먼저 드라이런으로 무엇이 들어오는지 보여 준다 (아무것도 안 바꾼다):

       powershell -NoProfile -ExecutionPolicy Bypass -File scripts\follow-upstream.ps1 -DryRun

2. 사용자가 진행을 승인하면 실행한다. **빌드가 `kmd-generate.exe` 를 교체하므로** 그 프로세스가
   돌고 있으면 스크립트가 거절한다 — 사용자 프로세스를 끄지 않는다(AGENTS.md 「Runtime Process Consent」).

       powershell -NoProfile -ExecutionPolicy Bypass -File scripts\follow-upstream.ps1

3. 종료 코드대로 답한다:

   | 코드 | 뜻 | 할 일 |
   |---|---|---|
   | 0 | 끝났거나 이미 최신 | 루트 커밋을 보여 주고, **루트 push 는 사용자에게 묻는다** |
   | 2 | 전제 거절(더러운 트리·다른 브랜치·포인터 검사 실패·kmd-generate 실행 중) | 사유를 그대로 전하고 멈춘다 |
   | 3 | 병합 충돌 / 병합 진행 중 | **자동 해결하지 않는다.** 충돌 파일을 보여 주고 사람에게 넘긴다. 해결·커밋 뒤 다시 실행하면 이어서 한다 |
   | 4 | 빌드·테스트 실패 | 아무것도 push 되지 않았다. 병합은 로컬에만 있다 — 되돌릴지는 사람이 정한다 |
   | 1 | 그 밖의 오류 | 로그를 보여 준다 |

로그는 매 실행 `logs\follow-upstream\<시각>.log` 에 남는다(커밋 안 됨).
스크립트 검증은 `scripts\tests\follow_upstream_test.ps1`(임시 샌드박스 · 실제 git · cmake/ctest 대역).

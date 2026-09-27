# Repository Guidelines

## Session Handoff (Codex · Claude Code)

Read the root `HANDOFF.md` first in every session, before `history/`. It is the shared, committed source of truth for the current state when Codex and Claude Code take turns on this repository: working-tree status, pending user decisions, and the next concrete tasks. Re-check the working tree with `git status` instead of trusting the recorded state, since the other agent may have changed it. When you finish work the user has confirmed, or after an important decision, record the rationale in `history/YYYY-MM-DD_topic.md` and rewrite the "최신 인계" section of `HANDOFF.md` to describe the current state (do not append; move the previous body to `docs/handoff/archive/HANDOFF_<date>.md`). Anything both agents must know belongs in `HANDOFF.md` or `history/`, not in `.codex-local/` or `.claude/`.

## Local Agent Memory

At the start of every session, if `.codex-local/INDEX.md` exists, read it completely before taking repository actions and follow its required initialization route. This ignored directory contains workstation- and operator-specific memory and capability maps that must not be committed. Treat this repository as a trunk workspace whose local runtime state, submodules, generated assets, and user-managed processes must be rediscovered at initialization rather than assumed.

Before answering or acting on a user request, classify the request from the current conversation and check `.codex-local/INDEX.md` for a matching capability or conditional route. Load only the map required for that route (for example, skills, MCP, environment/toolchain, or long-running processes) and follow it before proposing an answer or taking action. This capability check also applies to conversational questions about what Codex can do; do not answer from memory when the local index routes that topic. Do not preload every conditional map, because the routing layer exists to keep unrelated instructions out of the context window.

## Project Structure & Module Organization

This repository turns text prompts into UE5-ready motion assets. `scripts/generate-motion.ps1` orchestrates inference and GLB export. The pinned `vendor/kimodo.cpp/` submodule contains the C++23/GGML runtime: public headers in `include/`, implementation in `src/`, tests in `tests/`, converters in `scripts/`, and bundled GGML sources in `ggml/`. `KimodoTestbed/` is an ignored, local UE5.8 sandbox; do not treat it as deliverable source. Generated weights, build trees, `prompt.txt`, and `output_motion/` are intentionally untracked. Read the newest note in `history/` before substantial work and add a dated `YYYY-MM-DD_topic.md` note after important decisions.

## kimodo.cpp Fork

`vendor/kimodo.cpp` tracks both the original repository (remote `origin`, localai-org) and the user's fork (remote `upstream`, SimSeoWon — also the root `.gitmodules` URL). The remote names are the reverse of the usual convention. The WebUI's negative-prompt CFG and keypose constraints exist only on the fork branch `local/negative-prompt-cfg-and-pose-constraints` (`811eceb`, `main` plus one commit); checking out `main` and rebuilding drops them. The root pins that branch commit and `.gitmodules` points at the fork. Before changing the submodule pointer, check that the new commit descends from the pinned one (`git merge-base --is-ancestor`). See `README.md` "kimodo.cpp 포크와 서브모듈" before changing the submodule pointer.

## Build, Test, and Development Commands

Initialize both nested submodules:

```powershell
git submodule update --init --recursive
```

Configure and build the Windows Vulkan runtime:

```powershell
cmake -S vendor\kimodo.cpp -B vendor\kimodo.cpp\build -G "Visual Studio 17 2022" -A x64 -DKIMODO_BUILD_TESTS=ON -DKIMODO_ENABLE_VULKAN=ON
cmake --build vendor\kimodo.cpp\build --config Release
ctest --test-dir vendor\kimodo.cpp\build -C Release --output-on-failure
```

Use `py`, not bare `python`, for repository scripts. Generate a motion with `./scripts/generate-motion.ps1 -Prompt "a person waving"`; pass `-Backend cpu` when GPU memory is constrained. Tests requiring model bundles or parity fixtures do not download them automatically.

## Runtime Process Consent

Before stopping, starting, restarting, replacing, or force-killing any server, daemon, WebUI, Claude, Unreal, or other long-running process, ask the user first and wait for explicit approval. This is not a prohibition: perform the process operation when the user approves it. Approval to edit code, run tests, or diagnose a problem does not imply approval to alter already-running processes. Report the relevant PID and intended operation when asking. Do not silently replace a user-started daemon with an agent-started daemon.

Run user-managed WebUIs and other interactive long-running processes in a visible console so the user can inspect and stop them. Never start them with `-WindowStyle Hidden` unless the user explicitly requests hidden execution.

## Coding Style & Naming Conventions

Match nearby code. C++ uses four-space indentation, C++23, `snake_case` functions and variables, and lowercase source filenames; public API lives under the `kimodo` namespace. Keep warnings clean under MSVC `/W4 /permissive-` and GCC/Clang `-Wall -Wextra -Wpedantic -Wconversion -Wshadow`. PowerShell parameters use `PascalCase`; local variables use `camelCase`. Follow Unreal naming conventions in testbed code, and verify unfamiliar UE5 APIs against installed engine source rather than guessing identifiers.

## Testing Guidelines

Add focused C++ tests as `tests/<feature>_test.cpp` and register them with CTest in `vendor/kimodo.cpp/CMakeLists.txt`. Name parity tests explicitly (`*_parity.cpp`). Run the smallest relevant test first with `ctest -R <name>`, then the full suite. Validate UE import/retarget changes in `KimodoTestbed` before moving them to another project.

## Commit & Pull Request Guidelines

Recent commits use short, imperative, scope-oriented subjects, often in Korean; describe the concrete outcome rather than the process. Keep root and submodule commits logically separate. Pull requests should summarize behavior, list tested commands/backends, link the issue, and include screenshots or logs for UE animation changes. Never commit model weights or generated motion. SOMA/G1 weights permit commercial use under their model terms; SMPL-X RP is internal-R&D-only and must not be redistributed.

# Repository Guidelines

## Project Structure & Module Organization

This repository turns text prompts into UE5-ready motion assets. `scripts/generate-motion.ps1` orchestrates inference and GLB export. The pinned `vendor/kimodo.cpp/` submodule contains the C++23/GGML runtime: public headers in `include/`, implementation in `src/`, tests in `tests/`, converters in `scripts/`, and bundled GGML sources in `ggml/`. `KimodoTestbed/` is an ignored, local UE5.8 sandbox; do not treat it as deliverable source. Generated weights, build trees, `prompt.txt`, and `output_motion/` are intentionally untracked. Read the newest note in `history/` before substantial work and add a dated `YYYY-MM-DD_topic.md` note after important decisions.

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

## Coding Style & Naming Conventions

Match nearby code. C++ uses four-space indentation, C++23, `snake_case` functions and variables, and lowercase source filenames; public API lives under the `kimodo` namespace. Keep warnings clean under MSVC `/W4 /permissive-` and GCC/Clang `-Wall -Wextra -Wpedantic -Wconversion -Wshadow`. PowerShell parameters use `PascalCase`; local variables use `camelCase`. Follow Unreal naming conventions in testbed code, and verify unfamiliar UE5 APIs against installed engine source rather than guessing identifiers.

## Testing Guidelines

Add focused C++ tests as `tests/<feature>_test.cpp` and register them with CTest in `vendor/kimodo.cpp/CMakeLists.txt`. Name parity tests explicitly (`*_parity.cpp`). Run the smallest relevant test first with `ctest -R <name>`, then the full suite. Validate UE import/retarget changes in `KimodoTestbed` before moving them to another project.

## Commit & Pull Request Guidelines

Recent commits use short, imperative, scope-oriented subjects, often in Korean; describe the concrete outcome rather than the process. Keep root and submodule commits logically separate. Pull requests should summarize behavior, list tested commands/backends, link the issue, and include screenshots or logs for UE animation changes. Never commit model weights or generated motion. SOMA/G1 weights permit commercial use under their model terms; SMPL-X RP is internal-R&D-only and must not be redistributed.

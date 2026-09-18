#!/usr/bin/env python3
"""kimodo-motion 로컬 웹 UI 서버 (표준 라이브러리만 사용, 외부 의존성 없음).

사용법:
    py webui\\server.py [--port 8188]

Stable Diffusion WebUI 식으로: 파라미터를 채우고 Generate를 누르면
kmd-generate.exe -> export_glb.py 파이프라인을 그대로 실행하고,
결과 animation.glb를 브라우저에서 바로(model-viewer) 재생해서 보여준다.
"""

import argparse
import base64
import json
import mimetypes
import os
import random
import re
import shutil
import socket
import struct
import subprocess
import sys
import threading
import time
import traceback
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

try:
    from keypose import KeyposeValidationError, get_keypose_schema, validate_keypose_document, validate_pose_asset
except ModuleNotFoundError:  # Allows `import webui.server` in tests as well as direct script launch.
    from webui.keypose import KeyposeValidationError, get_keypose_schema, validate_keypose_document, validate_pose_asset
try:
    from keypose_agent import STORE as KEYPOSE_STORE
except ModuleNotFoundError:
    from webui.keypose_agent import STORE as KEYPOSE_STORE
try:
    from pose_agent import POSE_AGENT, POSE_CLI_RUNTIME
    from diagnostic_log import DiagnosticRun
except ModuleNotFoundError:
    from webui.pose_agent import POSE_AGENT, POSE_CLI_RUNTIME
    from webui.diagnostic_log import DiagnosticRun

REPO_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "static"
GENERATIONS_DIR = REPO_ROOT / "output_motion" / "generations"

DEFAULT_MODEL = REPO_ROOT / "vendor" / "kimodo.cpp" / "models" / "kimodo-soma-rp-v1.1-f32.gguf"
DEFAULT_TEXT_BUNDLE = REPO_ROOT / "vendor" / "kimodo.cpp" / "generated" / "llm2vec-text-bundle"
BUILD_BIN = REPO_ROOT / "vendor" / "kimodo.cpp" / "build" / "bin" / "Release"
BUILD_REL = REPO_ROOT / "vendor" / "kimodo.cpp" / "build" / "Release"
KMD_GENERATE = BUILD_REL / "kmd-generate.exe"
# vendor의 export_glb.py를 몽키패치해서 "본마다 작은 큐브" 대신 사람 실루엣에 가까운
# 캡슐 래그돌 메시로 내보낸다(웹 미리보기 전용 — UE5 임포트 경로는 그대로 vendor 것을 씀).
EXPORT_GLB_PY = REPO_ROOT / "scripts" / "pretty_export_glb.py"
# assets/extract_mixamo_soma30.py가 캐릭터별로 떨궈두는 프리뷰 바인딩들(없으면 캡슐로 폴백
# — 필수 아님). 여러 캐릭터를 처리해두면 전부 웹 UI 콤보박스에 나온다(2026-09-17).
MIXAMO_PROCESSED_DIR = REPO_ROOT / "assets" / "mixamo_processed"
CAPSULE_MODEL_ID = "capsule"
# 한 번만 돌리는 assets/extract_mixamo_soma30.py용(웹 UI 실행 자체엔 불필요) — 있으면 경로 표시.
BLENDER_CANDIDATES = [
    Path(r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"),
]

# 생성 이력이 없을 때 빈 화면 대신 보여줄 T포즈 미리보기. 캐릭터별로 static/tpose_<id>.glb에 캐시.
TPOSE_SRC_DIR = REPO_ROOT / "webui" / "_tpose_src"  # 합성 입력(항등 회전) — 모든 캐릭터가 공유
TPOSE_NUM_JOINTS = 30  # vendor export_glb.SKELETONS["soma30"]["names"] 개수와 같아야 함

PRESETS_FILE = REPO_ROOT / "webui" / "prompt_presets.json"  # 사용자 로컬 상태, git 미포함
KEYPOSE_PRESETS_FILE = REPO_ROOT / "webui" / "keypose_presets.json"
DEFAULT_PRESETS = [
    {"name": "걷기+손흔들기", "prompt": "a person walking forward enthusiastically and waving their right hand"},
    {"name": "점프", "prompt": "a person jumping happily"},
]

# 사진 -> 짧은 캡션(프롬프트 초안). server.py 자신은 여전히 표준 라이브러리만 쓰지만, 이
# 스크립트는 별도 프로세스로 실행되고 자기 몫의 의존성(torch/transformers/pillow, CPU
# 전용 — GPU는 kimodo가 씀)을 따로 진다 — Blender 스크립트들과 같은 패턴.
CAPTION_SCRIPT = REPO_ROOT / "scripts" / "caption_image.py"
CAPTION_TMP_DIR = REPO_ROOT / "webui" / "_caption_tmp"

# 동시에 GPU/CPU 추론을 두 번 돌리지 않도록 직렬화한다 (generate-motion.ps1과 같은 전제).
generation_lock = threading.Lock()

# 지금 돌고 있는 kmd-generate.exe Popen(있으면) + 그게 취소돼서 죽은 건지 구분하는 플래그.
# generation_lock과 별도 락으로 보호 — /api/cancel은 생성 중인 스레드와 다른 스레드에서 온다.
current_process_lock = threading.Lock()
current_process = None
cancel_requested = False


def slugify(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return slug[:max_len] or "motion"


def is_editor_running() -> bool:
    try:
        out = subprocess.run(
            ["tasklist"], capture_output=True, text=True, timeout=10
        ).stdout
    except Exception:
        return False
    return "UnrealEditor" in out


def is_vulkan_available() -> bool:
    # kmd-generate.exe의 기본 backend=vulkan이 실제로 뜨려면 Vulkan 로더(GPU 드라이버가 심음)가
    # 필요 — vulkaninfo를 매번 실행하면 느려서, 로더 DLL 존재만 빠르게 확인하는 걸로 대신한다.
    system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    return (system_root / "System32" / "vulkan-1.dll").exists()


def caption_deps_available() -> bool:
    try:
        import importlib
        importlib.import_module("torch")
        importlib.import_module("transformers")
        importlib.import_module("PIL")
        return True
    except ImportError:
        return False


# 서버 프로세스 수명 동안 한 번만 확인(torch import는 느림) — 실행 중 바뀌지 않는 값이다.
CAPTION_DEPS_AVAILABLE = caption_deps_available()


def find_blender() -> Path | None:
    # webui 실행 자체엔 안 쓰지만(Mixamo 바인딩은 이미 assets/mixamo_processed/에 생성돼
    # 있음), 그 바인딩을 다시 뽑아야 할 때(assets/extract_mixamo_soma30.py) 필요하므로
    # 있는지만 확인해서 점검 결과에 보여준다.
    for candidate in BLENDER_CANDIDATES:
        if candidate.exists():
            return candidate
    found = shutil.which("blender")
    return Path(found) if found else None


def list_mixamo_models() -> list:
    """assets/mixamo_processed/*_soma30_bind.json을 전부 찾아 웹 UI 콤보박스용으로 돌려준다.
    캡슐(=Mixamo 안 씀)은 항상 첫 항목으로 넣어서, 바인딩이 하나도 없어도 최소 1개는 있게 한다."""
    items = [{"id": CAPSULE_MODEL_ID, "label": "저폴리 캡슐 (Mixamo 없음)", "bind": None}]
    if not MIXAMO_PROCESSED_DIR.exists():
        return items
    suffix = "_soma30_bind"
    for p in sorted(MIXAMO_PROCESSED_DIR.glob("*_soma30_bind.json")):
        model_id = p.stem[: -len(suffix)] if p.stem.endswith(suffix) else p.stem
        label = model_id
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            label = data.get("label") or model_id
        except Exception:
            pass
        items.append({"id": model_id, "label": label, "bind": str(p)})
    return items


def default_mixamo_model_id(models: list) -> str:
    for m in models:
        if m["id"] != CAPSULE_MODEL_ID:
            return m["id"]
    return CAPSULE_MODEL_ID


def resolve_mixamo_bind_arg(model_id: str, models: list) -> str:
    """pretty_export_glb.py의 --mixamo-bind에 그대로 넘길 문자열. 모르는 id는 안전하게 캡슐로."""
    for m in models:
        if m["id"] == model_id:
            return m["bind"] or "none"
    return "none"


def build_status() -> dict:
    blender = find_blender()
    models = list_mixamo_models()
    default_id = default_mixamo_model_id(models)
    return {
        "kmd_generate_exists": KMD_GENERATE.exists(),
        "model_exists": DEFAULT_MODEL.exists(),
        "text_bundle_exists": DEFAULT_TEXT_BUNDLE.exists(),
        "vulkan_available": is_vulkan_available(),
        "blender_available": blender is not None,
        "blender_path": str(blender) if blender else None,
        "mixamo_preview_available": default_id != CAPSULE_MODEL_ID,
        "mixamo_models": models,
        "tpose_preview_available": (STATIC_DIR / f"tpose_{default_id}.glb").exists(),
        "caption_available": CAPTION_DEPS_AVAILABLE,
        "editor_running": is_editor_running(),
        "generation_in_progress": generation_lock.locked(),
    }


def ensure_tpose_variant(model_id: str, bind_arg: str) -> Path:
    """generate 이력이 없어도 빈 화면 대신 보여줄 T포즈 glb를 캐릭터(model_id)별로 만든다.

    export_glb류가 기대하는 raw 모션 입력(root_positions.f32/local_rotations_xyzw.f32)을
    항등 회전으로 직접 합성해서, 실제 생성과 똑같은 pretty_export_glb.py 경로로 내보낸다 —
    프리뷰 메시 로직을 따로 두 벌 관리하지 않기 위함. 이미 있으면 다시 안 만든다.
    """
    out_path = STATIC_DIR / f"tpose_{model_id}.glb"
    if out_path.exists() or not EXPORT_GLB_PY.exists():
        return out_path
    try:
        TPOSE_SRC_DIR.mkdir(parents=True, exist_ok=True)
        num_frames = 2  # 애니메이션 트랙엔 최소 1프레임이 필요해서 항등값 2개로 채움
        root_bytes = struct.pack(f"<{num_frames * 3}f", *([0.0] * (num_frames * 3)))
        identity_quat = (0.0, 0.0, 0.0, 1.0)
        rot_flat = identity_quat * (num_frames * TPOSE_NUM_JOINTS)
        rot_bytes = struct.pack(f"<{len(rot_flat)}f", *rot_flat)
        (TPOSE_SRC_DIR / "root_positions.f32").write_bytes(root_bytes)
        (TPOSE_SRC_DIR / "local_rotations_xyzw.f32").write_bytes(rot_bytes)

        cmd = [
            sys.executable, str(EXPORT_GLB_PY),
            "--motion-dir", str(TPOSE_SRC_DIR), "--output", str(out_path),
            "--mixamo-bind", bind_arg,
        ]
        proc = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=60)
        if proc.returncode != 0 or not out_path.exists():
            sys.stderr.write(
                "[webui] T포즈 미리보기(%s) 생성 실패 (무시하고 계속 진행): %s\n"
                % (model_id, (proc.stderr or proc.stdout)[-2000:])
            )
    except Exception as exc:
        sys.stderr.write(f"[webui] T포즈 미리보기({model_id}) 생성 중 오류 (무시하고 계속 진행): {exc}\n")
    return out_path


def ensure_default_tpose_preview() -> None:
    """서버 시작/--check 시 기본 캐릭터의 T포즈만 미리 만들어둔다(첫 페이지 로드 지연 없게).
    다른 캐릭터는 웹 UI에서 콤보박스로 고를 때 /api/tpose가 그때그때 만든다."""
    models = list_mixamo_models()
    default_id = default_mixamo_model_id(models)
    ensure_tpose_variant(default_id, resolve_mixamo_bind_arg(default_id, models))


def print_preflight(status: dict) -> bool:
    """콘솔에 구동 가능 여부를 점검·출력한다. 치명적 문제가 있으면 False를 반환."""
    ok = True

    def line(mark: str, text: str) -> None:
        print(f"  [{mark}] {text}")

    print("[kimodo-motion] 구동 가능 여부 점검")
    print(f"  (Python은 웹 UI 서버 자체엔 표준 라이브러리만 쓰므로 pip 설치는 불필요)")

    if status["kmd_generate_exists"]:
        line("OK", f"kmd-generate.exe 있음 ({KMD_GENERATE})")
    else:
        line("FAIL", f"kmd-generate.exe 없음 ({KMD_GENERATE}) — README의 CMake 빌드 단계 먼저 실행")
        ok = False

    if status["model_exists"]:
        line("OK", f"모델 가중치 있음 ({DEFAULT_MODEL.name})")
    else:
        line("FAIL", f"모델 가중치 없음 ({DEFAULT_MODEL}) — download_gguf_weights.py로 먼저 받기")
        ok = False

    if status["text_bundle_exists"]:
        line("OK", "텍스트 인코더 번들 있음")
    else:
        line("FAIL", f"텍스트 인코더 번들 없음 ({DEFAULT_TEXT_BUNDLE})")
        ok = False

    if status["vulkan_available"]:
        line("OK", "Vulkan 런타임 감지됨 (vulkan-1.dll) — 기본 backend=vulkan 사용 가능")
    else:
        line("WARN", "Vulkan 런타임을 못 찾음 — GPU 드라이버 확인, 안 되면 backend를 cpu로 바꿔서 생성")

    if status["blender_available"]:
        line("OK", f"Blender 감지됨 ({status['blender_path']})")
    else:
        line("WARN", "Blender 없음 — Mixamo 프리뷰 메시를 다시 뽑을 순 없지만, 웹 UI 실행 자체엔 필요 없음")

    if status["mixamo_preview_available"]:
        labels = ", ".join(m["label"] for m in status["mixamo_models"] if m["id"] != CAPSULE_MODEL_ID)
        line("OK", f"Mixamo 프리뷰 메시 바인딩 있음 ({labels}) — 웹 UI에서 캐릭터 선택 가능")
    else:
        line("WARN", "Mixamo 프리뷰 메시 바인딩 없음 — 지금은 저폴리 캡슐로만 미리보기됩니다(생성 자체는 정상 동작).")
        print("        Y Bot 사람 메시로 보려면:")
        print("        1) mixamo.com 에서 캐릭터 \"Y Bot\" 을 \"With Skin\", T-pose로 내려받기(로그인 필요)")
        print(f"        2) 받은 Y Bot.fbx 를 {REPO_ROOT / 'assets' / 'mixamo_src'} 에 넣기")
        print("        3) Blender로 바인딩 뽑기:")
        if status["blender_available"]:
            print(f'           "{status["blender_path"]}" --background --python assets\\extract_mixamo_soma30.py')
        else:
            print("           (Blender도 같이 없음 — winget install BlenderFoundation.Blender 로 먼저 설치)")

    if status["caption_available"]:
        line("OK", "사진 캡션 기능 사용 가능 (torch/transformers/pillow 감지됨)")
    else:
        line("WARN", "사진 캡션 기능 의존성 없음 — 웹 UI 실행 자체엔 필요 없음(안 쓰면 무시해도 됨).")
        print('        쓰려면: py -m pip install torch --index-url https://download.pytorch.org/whl/cpu')
        print("               py -m pip install transformers pillow")

    if status["tpose_preview_available"]:
        line("OK", "T포즈 기본 미리보기 준비됨")
    else:
        line("WARN", "T포즈 기본 미리보기를 못 만듦 — 웹 UI를 열면 생성 이력이 없을 때 빈 화면으로 보입니다")

    if status["editor_running"]:
        line("WARN", "UnrealEditor 실행 중 — Vulkan 백엔드는 VRAM을 에디터와 나눠 씁니다")

    print()
    print("점검 결과: " + ("실행 가능" if ok else "실행 불가 — 위 [FAIL] 항목을 먼저 해결하세요"))
    return ok


def run_cancelable(cmd, **kwargs):
    """subprocess.run과 같은 반환값(CompletedProcess)을 주지만, /api/cancel이 다른 스레드에서
    current_process.terminate()를 부를 수 있게 Popen 핸들을 전역에 잠깐 공개해둔다."""
    global current_process
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, **kwargs)
    with current_process_lock:
        current_process = proc
    try:
        stdout, stderr = proc.communicate()
    finally:
        with current_process_lock:
            if current_process is proc:
                current_process = None
    return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)


def load_presets() -> list:
    if not PRESETS_FILE.exists():
        return list(DEFAULT_PRESETS)
    try:
        return json.loads(PRESETS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return list(DEFAULT_PRESETS)


def save_presets(items: list) -> None:
    PRESETS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PRESETS_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def load_saved_poses() -> list:
    if not KEYPOSE_PRESETS_FILE.exists():
        return []
    try:
        items = json.loads(KEYPOSE_PRESETS_FILE.read_text(encoding="utf-8"))
        if not isinstance(items, list):
            return []
        result = []
        for item in items:
            if not isinstance(item, dict):
                continue
            # Legacy presets had only name + controls. Derive a stable ID without
            # rewriting the user's local file during a read.
            candidate = {
                "schema_version": item.get("schema_version", 1),
                "id": item.get("id") or str(uuid.uuid5(uuid.NAMESPACE_URL, f"kimodo-pose:{item.get('name', '')}")),
                "name": item.get("name", ""),
                "controls": item.get("controls"),
                "revision": item.get("revision", 0),
                "edits": item.get("edits", []),
            }
            try:
                result.append(validate_pose_asset(candidate))
            except KeyposeValidationError:
                continue
        return result
    except Exception:
        return []


def save_saved_poses(items: list) -> None:
    KEYPOSE_PRESETS_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def run_caption(image_bytes: bytes, ext: str) -> str:
    if not CAPTION_DEPS_AVAILABLE:
        raise RuntimeError(
            "캡션 의존성이 설치돼 있지 않습니다. "
            "py -m pip install torch --index-url https://download.pytorch.org/whl/cpu && "
            "py -m pip install transformers pillow"
        )
    CAPTION_TMP_DIR.mkdir(parents=True, exist_ok=True)
    safe_ext = ext if ext.startswith(".") and len(ext) <= 5 and ext[1:].isalnum() else ".jpg"
    tmp_path = CAPTION_TMP_DIR / f"upload{safe_ext}"
    tmp_path.write_bytes(image_bytes)
    try:
        proc = subprocess.run(
            [sys.executable, str(CAPTION_SCRIPT), str(tmp_path)],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=120,
        )
    finally:
        tmp_path.unlink(missing_ok=True)
    if proc.returncode != 0:
        raise RuntimeError(f"캡션 추출 실패:\n{(proc.stderr or proc.stdout)[-2000:]}")
    return proc.stdout.strip()


def load_history() -> list:
    if not GENERATIONS_DIR.exists():
        return []
    items = []
    for meta_path in GENERATIONS_DIR.glob("*/meta.json"):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            items.append(meta)
        except Exception:
            continue
    items.sort(key=lambda m: m.get("created_at", ""), reverse=True)
    return items


FRAMES_STDOUT_RE = re.compile(r"generated (\d+) frames")


def _run_generation(params: dict, diagnostic: DiagnosticRun) -> dict:
    global cancel_requested
    with current_process_lock:
        cancel_requested = False

    prompt = (params.get("prompt") or "").strip()
    segments = params.get("segments") or []  # 스토리보드 모드: [{"prompt":str,"frame_count":int}, ...]
    sequence_mode = len(segments) >= 1

    if sequence_mode:
        if len(segments) > 16:
            raise ValueError("스토리보드는 최대 16구간까지 가능합니다.")
        for seg in segments:
            if not (seg.get("prompt") or "").strip():
                raise ValueError("스토리보드 각 구간의 프롬프트는 비워둘 수 없습니다.")
            if not (2 <= int(seg.get("frame_count", 0)) <= 300):
                raise ValueError("스토리보드 각 구간은 2~300프레임이어야 합니다.")
    elif not prompt:
        raise ValueError("prompt는 비워둘 수 없습니다.")

    transition_frames = int(params.get("transition_frames", 15))
    if sequence_mode and not (1 <= transition_frames <= 60):
        raise ValueError("전환 프레임은 1~60이어야 합니다.")

    frame_count = int(params.get("frame_count", 120))
    if sequence_mode:
        frame_count = sum(int(segment["frame_count"]) for segment in segments)
    keyposes_raw = params.get("keyposes")
    keyposes = validate_keypose_document(keyposes_raw, frame_count=frame_count) if keyposes_raw else None
    steps = int(params.get("steps", 50))
    seed_raw = params.get("seed", None)
    seed = int(seed_raw) if seed_raw not in (None, "", -1, "-1") else random.randint(0, 2_147_483_647)
    backend = params.get("backend", "vulkan")
    if backend not in ("vulkan", "cpu"):
        raise ValueError("backend는 vulkan/cpu 중 하나여야 합니다.")
    # 미입력이면 kmd-generate.exe의 기존 기본값(2.0)을 그대로 쓴다 — env var 자체를 안 심음.
    # (LoRA 강도는 조절용 파라미터가 아니라 NVIDIA 원본과 수치를 맞추는 고정값이라 뺐음 — PORTING.md 참고.)
    text_cfg = params.get("text_cfg")
    text_cfg = float(text_cfg) if text_cfg not in (None, "") else None
    negative_prompt = (params.get("negative_prompt") or "").strip()
    if sequence_mode and negative_prompt:
        raise ValueError("부정 프롬프트는 스토리보드 모드에서는 아직 지원하지 않습니다.")
    model = Path(params.get("model") or DEFAULT_MODEL)
    text_bundle = Path(params.get("text_bundle") or DEFAULT_TEXT_BUNDLE)
    mixamo_models = list_mixamo_models()
    mixamo_model = params.get("mixamo_model") or default_mixamo_model_id(mixamo_models)
    diagnostic.event("validated", settings={
        "sequence_mode": sequence_mode,
        "frame_count": frame_count,
        "steps": steps,
        "seed": seed,
        "backend": backend,
        "text_cfg": text_cfg,
        "negative_prompt": negative_prompt or None,
        "model": str(model),
        "text_bundle": str(text_bundle),
        "mixamo_model": mixamo_model,
        "keyposes": keyposes,
    })

    if not KMD_GENERATE.exists():
        raise RuntimeError(
            f"kmd-generate.exe가 없습니다 ({KMD_GENERATE}). README의 빌드 단계를 먼저 실행하세요."
        )
    if not model.exists():
        raise RuntimeError(f"모델 가중치가 없습니다 ({model}). download_gguf_weights.py로 먼저 받으세요.")

    ts = datetime.now(timezone.utc)
    slug_source = prompt if not sequence_mode else " -> ".join(s["prompt"].strip() for s in segments)
    gen_id = f"{ts.strftime('%Y%m%d-%H%M%S')}_{slugify(slug_source)}"
    out_dir = GENERATIONS_DIR / gen_id
    out_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["PATH"] = f"{BUILD_BIN};{BUILD_REL};" + env.get("PATH", "")
    if backend == "cpu":
        env["KIMODO_BACKEND"] = "cpu"
    else:
        env.pop("KIMODO_BACKEND", None)
    if text_cfg is not None:
        env["KIMODO_TEXT_CFG"] = str(text_cfg)
    else:
        env.pop("KIMODO_TEXT_CFG", None)

    if keyposes:
        constraint_path = out_dir / "keypose_constraints.tsv"
        constraint_lines = ["# frame joint pos px py pz rot qx qy qz qw"]
        for keypose in keyposes["keyposes"]:
            for control_id, constraint in keypose["controls"].items():
                definition = next(item for item in get_keypose_schema()["controls"] if item["id"] == control_id)
                position = constraint.get("position", [0.0, 0.0, 0.0])
                rotation = constraint.get("rotation_xyzw", [0.0, 0.0, 0.0, 1.0])
                constraint_lines.append(" ".join(map(str, [
                    keypose["frame"], definition["joint_index"], int("position" in constraint), *position,
                    int("rotation_xyzw" in constraint), *rotation,
                ])))
        constraint_path.write_text("\n".join(constraint_lines) + "\n", encoding="utf-8")
        env["KIMODO_CONSTRAINTS_FILE"] = str(constraint_path)
        (out_dir / "keyposes.json").write_text(
            json.dumps(keyposes, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        env.pop("KIMODO_CONSTRAINTS_FILE", None)

    start = time.time()

    if sequence_mode:
        gen_cmd = [
            str(KMD_GENERATE), str(model), str(text_bundle), "--sequence",
            str(transition_frames), str(steps), str(seed), str(out_dir) + "\\",
        ]
        for i, seg in enumerate(segments):
            seg_prompt_file = out_dir / f"segment_{i}_prompt.txt"
            seg_prompt_file.write_text(seg["prompt"].strip(), encoding="utf-8")
            gen_cmd += [str(int(seg["frame_count"])), str(seg_prompt_file)]
    else:
        prompt_file = out_dir / "prompt.txt"
        prompt_file.write_text(prompt, encoding="utf-8")
        gen_cmd = [
            str(KMD_GENERATE), str(model), str(text_bundle), str(prompt_file),
            str(frame_count), str(steps), str(seed), str(out_dir) + "\\",
        ]
        if negative_prompt:
            negative_prompt_file = out_dir / "negative_prompt.txt"
            negative_prompt_file.write_text(negative_prompt, encoding="utf-8")
            gen_cmd.append(str(negative_prompt_file))

    inference_started = time.monotonic()
    diagnostic.event("inference_started", command=gen_cmd, output_directory=str(out_dir))
    gen_proc = run_cancelable(gen_cmd, env=env, cwd=str(REPO_ROOT))
    diagnostic.event(
        "inference_finished",
        elapsed_seconds=round(time.monotonic() - inference_started, 3),
        returncode=gen_proc.returncode,
        stdout=gen_proc.stdout,
        stderr=gen_proc.stderr,
    )
    if gen_proc.returncode != 0:
        with current_process_lock:
            was_cancelled = cancel_requested
        if was_cancelled:
            raise RuntimeError("생성이 취소되었습니다.")
        raise RuntimeError(
            "kmd-generate.exe 실패 (exit %d)\n%s" % (
                gen_proc.returncode, (gen_proc.stderr or gen_proc.stdout)[-4000:]
            )
        )
    frames_match = FRAMES_STDOUT_RE.search(gen_proc.stdout or "")
    actual_frames = int(frames_match.group(1)) if frames_match else frame_count

    glb_path = out_dir / "animation.glb"
    export_cmd = [
        sys.executable, str(EXPORT_GLB_PY),
        "--motion-dir", str(out_dir), "--output", str(glb_path),
        "--mixamo-bind", resolve_mixamo_bind_arg(mixamo_model, mixamo_models),
    ]
    export_started = time.monotonic()
    diagnostic.event("export_started", command=export_cmd)
    export_proc = subprocess.run(export_cmd, cwd=str(REPO_ROOT),
                                  capture_output=True, text=True, timeout=300)
    diagnostic.event(
        "export_finished",
        elapsed_seconds=round(time.monotonic() - export_started, 3),
        returncode=export_proc.returncode,
        stdout=export_proc.stdout,
        stderr=export_proc.stderr,
        glb_exists=glb_path.exists(),
    )
    if export_proc.returncode != 0 or not glb_path.exists():
        raise RuntimeError(
            "export_glb.py 실패 (exit %d)\n%s" % (
                export_proc.returncode, (export_proc.stderr or export_proc.stdout)[-4000:]
            )
        )

    elapsed = round(time.time() - start, 1)

    meta = {
        "id": gen_id,
        "prompt": prompt if not sequence_mode else slug_source,
        "sequence_mode": sequence_mode,
        "segments": segments if sequence_mode else None,
        "transition_frames": transition_frames if sequence_mode else None,
        "frame_count": actual_frames,
        "steps": steps,
        "seed": seed,
        "backend": backend,
        "text_cfg": text_cfg,
        "negative_prompt": negative_prompt or None,
        "model": str(model),
        "text_bundle": str(text_bundle),
        "mixamo_model": mixamo_model,
        "keyposes": keyposes,
        "created_at": ts.isoformat(),
        "elapsed_sec": elapsed,
        "glb_url": f"/outputs/{gen_id}/animation.glb",
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def run_generation(params: dict) -> dict:
    diagnostic = DiagnosticRun("motion", {"params": params})
    started = time.monotonic()
    try:
        result = _run_generation(params, diagnostic)
        diagnostic.event("completed", elapsed_seconds=round(time.monotonic() - started, 3), meta=result)
        return result
    except Exception as exc:
        diagnostic.event(
            "failed",
            elapsed_seconds=round(time.monotonic() - started, 3),
            error=str(exc),
            traceback=traceback.format_exc(),
        )
        raise


class ExclusiveThreadingHTTPServer(ThreadingHTTPServer):
    """Refuse a second WebUI daemon on the same Windows port."""

    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class Handler(BaseHTTPRequestHandler):
    server_version = "kimodo-motion-webui/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("[webui] %s\n" % (fmt % args))

    def _send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str = None, cache_control: str = None):
        if not path.is_file():
            self._send_json({"error": "not found"}, 404)
            return
        ctype = content_type
        if ctype is None and path.suffix.lower() == ".mjs":
            ctype = "text/javascript; charset=utf-8"
        ctype = ctype or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        if cache_control:
            self.send_header("Cache-Control", cache_control)
        self.end_headers()
        self.wfile.write(data)

    def _safe_join(self, base: Path, rel: str) -> Path:
        candidate = (base / rel).resolve()
        base_resolved = base.resolve()
        if base_resolved not in candidate.parents and candidate != base_resolved:
            raise ValueError("path traversal blocked")
        return candidate

    def do_GET(self):
        path = unquote(self.path.split("?", 1)[0])
        try:
            if path == "/":
                self._send_file(
                    STATIC_DIR / "index.html", "text/html; charset=utf-8", "no-store"
                )
            elif path.startswith("/static/"):
                rel = path[len("/static/"):]
                self._send_file(self._safe_join(STATIC_DIR, rel), cache_control="no-store")
            elif path.startswith("/outputs/"):
                rel = path[len("/outputs/"):]
                self._send_file(self._safe_join(GENERATIONS_DIR, rel), "model/gltf-binary"
                                 if rel.endswith(".glb") else None)
            elif path == "/api/status":
                self._send_json(build_status())
            elif path == "/api/history":
                self._send_json({"items": load_history()})
            elif path == "/api/mixamo-models":
                models = list_mixamo_models()
                self._send_json({"items": models, "default": default_mixamo_model_id(models)})
            elif path == "/api/keypose-schema":
                self._send_json(get_keypose_schema())
            elif path == "/api/keyposes/state":
                self._send_json(KEYPOSE_STORE.state())
            elif path == "/api/pose-agent/state":
                self._send_json(POSE_AGENT.state())
            elif path in ("/api/poses", "/api/keypose-presets"):
                self._send_json({"items": load_saved_poses()})
            elif path == "/api/tpose":
                models = list_mixamo_models()
                query = parse_qs(urlsplit(self.path).query)
                model_id = (query.get("model") or [""])[0] or default_mixamo_model_id(models)
                glb_path = ensure_tpose_variant(model_id, resolve_mixamo_bind_arg(model_id, models))
                self._send_file(glb_path, "model/gltf-binary")
            elif path == "/api/presets":
                self._send_json({"items": load_presets()})
            else:
                self._send_json({"error": "not found"}, 404)
        except ValueError:
            self._send_json({"error": "invalid path"}, 400)
        except Exception as exc:
            self._send_json({"error": str(exc)}, 500)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def do_POST(self):
        path = unquote(self.path.split("?", 1)[0])

        if path == "/api/keyposes/validate":
            try:
                body = self._read_json_body()
                document = body.get("document", body)
                frame_count = body.get("frame_count") if "document" in body else None
                normalized = validate_keypose_document(document, frame_count=frame_count)
                self._send_json({"valid": True, "document": normalized})
            except (KeyposeValidationError, TypeError) as exc:
                self._send_json({"valid": False, "error": str(exc)}, 400)
            except Exception:
                self._send_json({"valid": False, "error": "invalid JSON body"}, 400)
            return

        if path == "/api/pose-agent/command":
            try:
                body = self._read_json_body()
                self._send_json(POSE_AGENT.submit(
                    body.get("instruction", ""),
                    body.get("pose"),
                    body.get("snapshot"),
                ), 202)
            except KeyposeValidationError as exc:
                self._send_json({"error": str(exc)}, 400)
            except Exception:
                self._send_json({"error": "포즈 에이전트 작업을 시작하지 못했습니다."}, 500)
            return

        if path == "/api/keyposes/command":
            try:
                body = self._read_json_body()
                self._send_json(KEYPOSE_STORE.command(body.get("name", ""), body.get("arguments", {})))
            except KeyposeValidationError as exc:
                self._send_json({"error": str(exc)}, 400)
            except Exception:
                self._send_json({"error": "invalid pose command"}, 400)
            return

        if path == "/api/keyposes/document":
            try:
                body = self._read_json_body()
                self._send_json(KEYPOSE_STORE.replace(body.get("document", body), body.get("frame_count")))
            except KeyposeValidationError as exc:
                self._send_json({"error": str(exc)}, 400)
            except Exception:
                self._send_json({"error": "invalid keypose document"}, 400)
            return

        if path in ("/api/poses", "/api/keypose-presets"):
            try:
                body = self._read_json_body()
                requested = body.get("pose", body)
                name = (requested.get("name") or "").strip()
                existing = next((item for item in load_saved_poses() if item.get("name") == name), None)
                candidate = {
                    "schema_version": requested.get("schema_version", 1),
                    "id": requested.get("id") or (existing or {}).get("id") or str(uuid.uuid4()),
                    "name": name,
                    "controls": requested.get("controls"),
                    "revision": requested.get("revision", 0),
                    "edits": requested.get("edits", []),
                }
                validated = validate_pose_asset(candidate)
                items = [item for item in load_saved_poses() if item.get("id") != validated["id"] and item.get("name") != name]
                items.append(validated)
                items.sort(key=lambda item: item["name"])
                save_saved_poses(items)
                self._send_json({"items": items})
            except KeyposeValidationError as exc:
                self._send_json({"error": str(exc)}, 400)
            except Exception:
                self._send_json({"error": "invalid pose"}, 400)
            return

        if path in ("/api/poses/delete", "/api/keypose-presets/delete"):
            try:
                body = self._read_json_body()
                name = (body.get("name") or "").strip()
                items = [item for item in load_saved_poses() if item.get("name") != name]
                save_saved_poses(items)
                self._send_json({"items": items})
            except Exception:
                self._send_json({"error": "invalid pose request"}, 400)
            return

        if path == "/api/cancel":
            global cancel_requested
            with current_process_lock:
                proc = current_process
                if proc is not None:
                    cancel_requested = True
            if proc is not None and proc.poll() is None:
                proc.terminate()
                self._send_json({"cancelled": True})
            else:
                self._send_json({"cancelled": False, "message": "실행 중인 생성이 없습니다."})
            return

        if path == "/api/caption":
            try:
                body = self._read_json_body()
            except Exception:
                self._send_json({"error": "invalid JSON body"}, 400)
                return
            image_b64 = body.get("image_base64") or ""
            if not image_b64:
                self._send_json({"error": "image_base64가 필요합니다."}, 400)
                return
            try:
                image_bytes = base64.b64decode(image_b64)
            except Exception:
                self._send_json({"error": "잘못된 base64 이미지입니다."}, 400)
                return
            try:
                caption = run_caption(image_bytes, body.get("ext") or ".jpg")
                self._send_json({"caption": caption})
            except Exception as exc:
                self._send_json({"error": str(exc)}, 500)
            return

        if path == "/api/presets":
            try:
                body = self._read_json_body()
            except Exception:
                self._send_json({"error": "invalid JSON body"}, 400)
                return
            name = (body.get("name") or "").strip()
            prompt = (body.get("prompt") or "").strip()
            if not name or not prompt:
                self._send_json({"error": "name과 prompt를 모두 입력하세요."}, 400)
                return
            items = [p for p in load_presets() if p.get("name") != name]
            items.append({"name": name, "prompt": prompt})
            save_presets(items)
            self._send_json({"items": items})
            return

        if path == "/api/presets/delete":
            try:
                body = self._read_json_body()
            except Exception:
                self._send_json({"error": "invalid JSON body"}, 400)
                return
            name = (body.get("name") or "").strip()
            items = [p for p in load_presets() if p.get("name") != name]
            save_presets(items)
            self._send_json({"items": items})
            return

        if path != "/api/generate":
            self._send_json({"error": "not found"}, 404)
            return

        try:
            params = self._read_json_body()
        except Exception:
            self._send_json({"error": "invalid JSON body"}, 400)
            return

        if not generation_lock.acquire(blocking=False):
            self._send_json({"error": "이미 다른 생성 작업이 진행 중입니다. 끝날 때까지 기다려주세요."}, 409)
            return
        try:
            batch_count = max(1, min(int(params.get("batch_count", 1) or 1), 8))
            base_seed = params.get("seed")
            metas = []
            for i in range(batch_count):
                iter_params = dict(params)
                if base_seed not in (None, "", -1, "-1"):
                    iter_params["seed"] = int(base_seed) + i
                else:
                    iter_params["seed"] = None
                metas.append(run_generation(iter_params))
            self._send_json(metas[0] if batch_count == 1 else {"items": metas})
        except ValueError as exc:
            self._send_json({"error": str(exc)}, 400)
        except Exception as exc:
            self._send_json({"error": str(exc)}, 500)
        finally:
            generation_lock.release()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8188)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--check", action="store_true",
                         help="서버를 띄우지 않고 구동 가능 여부만 점검하고 종료")
    args = parser.parse_args()

    if args.check:
        ensure_default_tpose_preview()
        sys.exit(0 if print_preflight(build_status()) else 1)

    GENERATIONS_DIR.mkdir(parents=True, exist_ok=True)
    ensure_default_tpose_preview()
    try:
        POSE_CLI_RUNTIME.start()
        print("포즈 LLM 서브 에이전트: 대기 중")
    except Exception as exc:
        print(f"포즈 LLM 서브 에이전트 시작 실패: {exc}")
    server = ExclusiveThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}/"
    print(f"kimodo-motion 웹 UI: {url}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        POSE_CLI_RUNTIME.stop()


if __name__ == "__main__":
    main()

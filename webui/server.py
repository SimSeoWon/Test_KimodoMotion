#!/usr/bin/env python3
"""kimodo-motion 로컬 웹 UI 서버 (표준 라이브러리만 사용, 외부 의존성 없음).

사용법:
    py webui\\server.py [--port 8188]

Stable Diffusion WebUI 식으로: 파라미터를 채우고 Generate를 누르면
kmd-generate.exe -> export_glb.py 파이프라인을 그대로 실행하고,
결과 animation.glb를 브라우저에서 바로(model-viewer) 재생해서 보여준다.
"""

import argparse
import json
import mimetypes
import os
import random
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

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

# 동시에 GPU/CPU 추론을 두 번 돌리지 않도록 직렬화한다 (generate-motion.ps1과 같은 전제).
generation_lock = threading.Lock()


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


def build_status() -> dict:
    return {
        "kmd_generate_exists": KMD_GENERATE.exists(),
        "model_exists": DEFAULT_MODEL.exists(),
        "text_bundle_exists": DEFAULT_TEXT_BUNDLE.exists(),
        "editor_running": is_editor_running(),
        "generation_in_progress": generation_lock.locked(),
    }


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


def run_generation(params: dict) -> dict:
    prompt = (params.get("prompt") or "").strip()
    if not prompt:
        raise ValueError("prompt는 비워둘 수 없습니다.")

    frame_count = int(params.get("frame_count", 120))
    steps = int(params.get("steps", 50))
    seed_raw = params.get("seed", None)
    seed = int(seed_raw) if seed_raw not in (None, "", -1, "-1") else random.randint(0, 2_147_483_647)
    backend = params.get("backend", "vulkan")
    if backend not in ("vulkan", "cpu"):
        raise ValueError("backend는 vulkan/cpu 중 하나여야 합니다.")
    model = Path(params.get("model") or DEFAULT_MODEL)
    text_bundle = Path(params.get("text_bundle") or DEFAULT_TEXT_BUNDLE)

    if not KMD_GENERATE.exists():
        raise RuntimeError(
            f"kmd-generate.exe가 없습니다 ({KMD_GENERATE}). README의 빌드 단계를 먼저 실행하세요."
        )
    if not model.exists():
        raise RuntimeError(f"모델 가중치가 없습니다 ({model}). download_gguf_weights.py로 먼저 받으세요.")

    ts = datetime.now(timezone.utc)
    gen_id = f"{ts.strftime('%Y%m%d-%H%M%S')}_{slugify(prompt)}"
    out_dir = GENERATIONS_DIR / gen_id
    out_dir.mkdir(parents=True, exist_ok=True)

    prompt_file = out_dir / "prompt.txt"
    prompt_file.write_text(prompt, encoding="utf-8")

    env = os.environ.copy()
    env["PATH"] = f"{BUILD_BIN};{BUILD_REL};" + env.get("PATH", "")
    if backend == "cpu":
        env["KIMODO_BACKEND"] = "cpu"
    else:
        env.pop("KIMODO_BACKEND", None)

    start = time.time()

    gen_cmd = [
        str(KMD_GENERATE), str(model), str(text_bundle), str(prompt_file),
        str(frame_count), str(steps), str(seed), str(out_dir) + "\\",
    ]
    gen_proc = subprocess.run(gen_cmd, env=env, cwd=str(REPO_ROOT),
                               capture_output=True, text=True, timeout=1800)
    if gen_proc.returncode != 0:
        raise RuntimeError(
            "kmd-generate.exe 실패 (exit %d)\n%s" % (
                gen_proc.returncode, (gen_proc.stderr or gen_proc.stdout)[-4000:]
            )
        )

    glb_path = out_dir / "animation.glb"
    export_cmd = [
        sys.executable, str(EXPORT_GLB_PY),
        "--motion-dir", str(out_dir), "--output", str(glb_path),
    ]
    export_proc = subprocess.run(export_cmd, cwd=str(REPO_ROOT),
                                  capture_output=True, text=True, timeout=300)
    if export_proc.returncode != 0 or not glb_path.exists():
        raise RuntimeError(
            "export_glb.py 실패 (exit %d)\n%s" % (
                export_proc.returncode, (export_proc.stderr or export_proc.stdout)[-4000:]
            )
        )

    elapsed = round(time.time() - start, 1)

    meta = {
        "id": gen_id,
        "prompt": prompt,
        "frame_count": frame_count,
        "steps": steps,
        "seed": seed,
        "backend": backend,
        "model": str(model),
        "text_bundle": str(text_bundle),
        "created_at": ts.isoformat(),
        "elapsed_sec": elapsed,
        "glb_url": f"/outputs/{gen_id}/animation.glb",
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


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

    def _send_file(self, path: Path, content_type: str = None):
        if not path.is_file():
            self._send_json({"error": "not found"}, 404)
            return
        ctype = content_type or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
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
                self._send_file(STATIC_DIR / "index.html", "text/html; charset=utf-8")
            elif path.startswith("/static/"):
                rel = path[len("/static/"):]
                self._send_file(self._safe_join(STATIC_DIR, rel))
            elif path.startswith("/outputs/"):
                rel = path[len("/outputs/"):]
                self._send_file(self._safe_join(GENERATIONS_DIR, rel), "model/gltf-binary"
                                 if rel.endswith(".glb") else None)
            elif path == "/api/status":
                self._send_json(build_status())
            elif path == "/api/history":
                self._send_json({"items": load_history()})
            else:
                self._send_json({"error": "not found"}, 404)
        except ValueError:
            self._send_json({"error": "invalid path"}, 400)
        except Exception as exc:
            self._send_json({"error": str(exc)}, 500)

    def do_POST(self):
        path = unquote(self.path.split("?", 1)[0])
        if path != "/api/generate":
            self._send_json({"error": "not found"}, 404)
            return

        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            params = json.loads(raw.decode("utf-8"))
        except Exception:
            self._send_json({"error": "invalid JSON body"}, 400)
            return

        if not generation_lock.acquire(blocking=False):
            self._send_json({"error": "이미 다른 생성 작업이 진행 중입니다. 끝날 때까지 기다려주세요."}, 409)
            return
        try:
            meta = run_generation(params)
            self._send_json(meta)
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
    args = parser.parse_args()

    GENERATIONS_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}/"
    print(f"kimodo-motion 웹 UI: {url}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

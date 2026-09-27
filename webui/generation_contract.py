"""Validated inputs for the SOMA30 runtime; no inference or file mutations."""

import math
import random
import struct
from copy import deepcopy
from pathlib import Path

try:
    from keypose import CONTROL_BY_ID, KeyposeValidationError, validate_keypose_document
except ModuleNotFoundError:
    from webui.keypose import CONTROL_BY_ID, KeyposeValidationError, validate_keypose_document

MAX_SEED = 2_147_483_647
MAX_BATCH_COUNT = 8


def integer(value, name, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError(f"{name}: {minimum}~{maximum} 범위의 정수를 입력하세요.")
    try:
        result = int(value)
    except ValueError:
        raise ValueError(f"{name}: 정수를 입력하세요.") from None
    if not minimum <= result <= maximum:
        raise ValueError(f"{name}: {minimum}~{maximum} 범위여야 합니다.")
    return result


def normalize_generation_request(params):
    if not isinstance(params, dict):
        raise ValueError("생성 요청은 JSON 객체여야 합니다.")
    result = deepcopy(params)
    result["batch_count"] = integer(params.get("batch_count", 1), "생성 개수", 1, MAX_BATCH_COUNT)
    result["steps"] = integer(params.get("steps", 50), "Steps", 1, 500)
    seed = params.get("seed")
    result["seed"] = (random.randint(0, MAX_SEED - result["batch_count"] + 1)
                      if seed in (None, "", -1, "-1")
                      else integer(seed, "Seed", 0, MAX_SEED))
    if result["seed"] + result["batch_count"] - 1 > MAX_SEED:
        raise ValueError("배치의 마지막 Seed가 최대값을 넘습니다. 시작 Seed를 낮춰주세요.")
    if params.get("backend", "vulkan") not in ("cpu", "vulkan"):
        raise ValueError("backend는 vulkan/cpu 중 하나여야 합니다.")
    cfg = params.get("text_cfg")
    if cfg in (None, ""):
        result["text_cfg"] = 2.0
    else:
        try:
            cfg = float(cfg) if not isinstance(cfg, bool) else float("nan")
        except (ValueError, TypeError):
            cfg = float("nan")
        if not math.isfinite(cfg) or not 0 <= cfg <= 20:
            raise ValueError("CFG는 0~20 범위의 유한한 숫자여야 합니다.")
        result["text_cfg"] = cfg
    for field in ("prompt", "negative_prompt"):
        value = params.get(field) or ""
        if not isinstance(value, str):
            raise ValueError(f"{field}는 문자열이어야 합니다.")
        result[field] = value.strip()
    segments = params.get("segments") or []
    if not isinstance(segments, list) or len(segments) > 16:
        raise ValueError("스토리보드는 최대 16구간의 목록이어야 합니다.")
    result["segments"] = []
    if segments:
        transition = integer(params.get("transition_frames", 15), "전환 프레임", 1, 60)
        for index, segment in enumerate(segments):
            if not isinstance(segment, dict) or not isinstance(segment.get("prompt"), str) or not segment["prompt"].strip():
                raise ValueError("각 구간의 프롬프트를 입력하세요.")
            frames = integer(segment.get("frame_count"), "구간 프레임", 2, 300)
            if len(segments) > 1 and frames <= transition:
                raise ValueError("전환 프레임은 모든 구간의 길이보다 짧아야 합니다.")
            result["segments"].append({"prompt": segment["prompt"].strip(), "frame_count": frames})
        result["transition_frames"] = transition
        result["frame_count"] = sum(s["frame_count"] for s in result["segments"])
        if result["negative_prompt"]:
            raise ValueError("부정 프롬프트는 스토리보드에서 아직 지원하지 않습니다.")
    else:
        if not result["prompt"]:
            raise ValueError("프롬프트를 입력하세요.")
        result["frame_count"] = integer(params.get("frame_count", 120), "프레임 수", 2, 300)
    if params.get("keyposes") is not None:
        result["keyposes"] = validate_keypose_document(params["keyposes"], result["frame_count"])
        rows = compile_keypose_constraints(result["keyposes"])
        if rows and len(segments) > 1:
            raise ValueError("포즈 제약은 현재 단일 구간에서 지원합니다. 구간 전환의 좌표 변환 검증 후 스토리보드에 제공할 예정입니다.")
    return result


def compile_keypose_constraints(document):
    """Compile only explicit canonical world-space targets; never discard semantics."""
    rows = []
    for keypose in document["keyposes"]:
        enabled = {name: value for name, value in keypose["controls"].items() if value["weight"] != 0}
        if not enabled:
            continue
        if keypose.get("skeleton") != "soma30":
            raise KeyposeValidationError("이전 캐릭터 기준 포즈입니다. 포즈 편집기에서 확인하고 다시 저장·배치하세요.")
        # Native hand/foot positions are read relative to the root in XZ; without a
        # pelvis target the root stays free, so no anchor is required here.
        for name, value in enabled.items():
            if value["space"] != "world":
                raise KeyposeValidationError(f"{name}: 현재 모션 생성은 world 공간만 지원합니다.")
            if value["weight"] != 1:
                raise KeyposeValidationError(f"{name}: 제약 가중치는 0(끄기) 또는 1만 지원합니다.")
            position = value.get("position", [0, 0, 0])
            rotation = value.get("rotation_xyzw", [0, 0, 0, 1])
            rows.append(" ".join(map(str, [keypose["frame"], CONTROL_BY_ID[name]["joint_index"],
                        int("position" in value), *position, int("rotation_xyzw" in value), *rotation])))
    return rows


def motion_skeleton(path: Path) -> str:
    """Read the scalar GGUF metadata accepted by the pinned native motion loader."""
    widths = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 1, 10: 8, 11: 8, 12: 8}
    with path.open("rb") as stream:
        def read(size):
            value = stream.read(size)
            if len(value) != size:
                raise ValueError("모션 GGUF 메타데이터가 손상됐습니다.")
            return value

        def string():
            size, = struct.unpack("<Q", read(8))
            if size > 1_048_576:
                raise ValueError("모션 GGUF 문자열이 너무 큽니다.")
            return read(size).decode("utf-8")

        magic, version, _tensors, count = struct.unpack("<4sIQQ", read(24))
        if magic != b"GGUF" or version not in (2, 3) or count > 100_000:
            raise ValueError("지원하지 않는 모션 GGUF입니다.")
        for _ in range(count):
            key = string()
            kind, = struct.unpack("<I", read(4))
            if kind == 8:
                value = string()
                if key == "kimodo.skeleton":
                    return value
            elif kind in widths:
                read(widths[kind])
            else:
                raise ValueError("지원하지 않는 모션 GGUF 메타데이터입니다.")
    raise ValueError("모션 GGUF에 스켈레톤 정보가 없습니다.")

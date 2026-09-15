#!/usr/bin/env python3
"""vendor/kimodo.cpp/scripts/export_glb.py 의 "본마다 작은 큐브" 메시 대신, 웹 UI
미리보기용 메시로 내보낸다.

assets/mixamo_processed/ybot_soma30_bind.json(assets/extract_mixamo_soma30.py로 한 번만
생성하는, Mixamo Y Bot 메시를 SOMA30 레스트 좌표계로 재배치한 정점/조인트 바인딩)이 있으면
그걸 쓰고, 없으면 관절을 잇는 저폴리 캡슐 래그돌로 대신한다. Mixamo 데이터에 대응이 없는
조인트(Neck1/Neck2/Jaw/LeftEye/RightEye — Mixamo 표준 리그엔 목/턱/눈 본이 따로 없음)는
Mixamo 메시를 쓸 때도 캡슐로 메운다.

vendor 서브모듈(핀 고정 커밋)은 건드리지 않는다 — export_glb 모듈을 그대로 import해서
create_bone_mesh()만 몽키패치하고, 애니메이션/스킨/역바인드행렬 등 나머지 로직은 전부
vendor 원본을 그대로 재사용한다. CLI 인자는 vendor 스크립트와 동일
(--motion-dir/--output/--model/--fps) — generate-motion.ps1/README의 UE5 임포트
파이프라인에는 영향 없음(그쪽은 SOMA 쪽 메시를 쓰지 않고 리타겟으로 UE 마네킹 메시를
쓰기 때문에 웹 미리보기 전용으로만 이 스크립트를 쓴다).

사용법은 vendor/kimodo.cpp/scripts/export_glb.py와 동일:
    py scripts\\pretty_export_glb.py --motion-dir output_motion --output output_motion\\animation.glb
"""

import argparse
import json
import math
import struct
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_VENDOR_SCRIPTS = _REPO_ROOT / "vendor" / "kimodo.cpp" / "scripts"
sys.path.insert(0, str(_VENDOR_SCRIPTS))
import export_glb  # noqa: E402  (vendor 모듈, 디스크상 파일은 안 건드림)

_MIXAMO_BIND_PATH = _REPO_ROOT / "assets" / "mixamo_processed" / "ybot_soma30_bind.json"
# Mixamo Y Bot 표준 리그엔 대응 본이 없어서 캡슐로 메우는 조인트(soma30 인덱스).
_CAPSULE_ONLY_JOINTS = {4, 5, 7, 8, 9}  # Neck1, Neck2, Jaw, LeftEye, RightEye

# soma30 고정 조인트 순서(0=Hips..29=RightToeBase, vendor의 SKELETONS["soma30"]["names"]와
# 같은 순서)에 대한 대략적인 반지름(인체 비례 근사). export_glb.create_bone_mesh()의
# 시그니처가 (global_pos, parents)뿐이라 이름을 못 받아서 인덱스로 고정했다 — 다른
# 스켈레톤이 추가되면 이 표도 같이 늘려야 한다(지금은 --model 선택지가 soma30뿐).
_RADII = [
    0.10, 0.09, 0.09, 0.10, 0.05, 0.045, 0.11, 0.03, 0.015, 0.015,  # Hips..RightEye
    0.05, 0.045, 0.04, 0.035, 0.015, 0.015, 0.05, 0.045, 0.04, 0.035,  # L/R Shoulder..HandMiddleEnd
    0.015, 0.015, 0.075, 0.055, 0.04, 0.03, 0.075, 0.055, 0.04, 0.03,  # ..LeftLeg..RightToeBase
]


def _sub(a, b):
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def _add(a, b):
    return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]


def _scale(a, s):
    return [a[0] * s, a[1] * s, a[2] * s]


def _length(a):
    return math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])


def _normalize(a):
    l = _length(a)
    if l < 1e-9:
        return [0.0, 1.0, 0.0]
    return _scale(a, 1.0 / l)


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def _capsule(vertices, joints, weights, indices, a, b, radius, joint_idx, sides=8):
    """a->b를 잇는 낮은 폴리곤 캡슐(원기둥 옆면 + 원뿔형 양끝 캡)을 추가한다.
    a==b면 양끝 캡이 뒤집힌 구 근사(관절 블롭)가 된다. 모든 정점은 joint_idx에
    100% 강체 스키닝(export_glb 원본과 같은 방식 — 부드러운 블렌딩은 안 함)."""
    u = _normalize(_sub(b, a))
    ref = [0.0, 0.0, 1.0] if abs(u[0]) > 0.9 else [1.0, 0.0, 0.0]
    right = _normalize(_cross(ref, u))
    forward = _cross(u, right)

    ring_offsets = []
    for i in range(sides):
        theta = 2.0 * math.pi * i / sides
        ring_offsets.append(_add(_scale(right, radius * math.cos(theta)), _scale(forward, radius * math.sin(theta))))

    base_idx = len(vertices)

    def emit(p):
        vertices.append(p)
        joints.append([joint_idx, 0, 0, 0])
        weights.append([1.0, 0.0, 0.0, 0.0])

    emit(_sub(a, _scale(u, radius)))                       # base_idx + 0 : apex_a
    for off in ring_offsets:
        emit(_add(a, off))                                 # base_idx + 1 .. sides : ring_a
    for off in ring_offsets:
        emit(_add(b, off))                                 # base_idx + 1+sides .. 2*sides : ring_b
    emit(_add(b, _scale(u, radius)))                        # base_idx + 1+2*sides : apex_b

    apex_a_i = base_idx
    ring_a = [base_idx + 1 + i for i in range(sides)]
    ring_b = [base_idx + 1 + sides + i for i in range(sides)]
    apex_b_i = base_idx + 1 + 2 * sides

    for i in range(sides):
        i2 = (i + 1) % sides
        indices.extend([apex_a_i, ring_a[i2], ring_a[i]])
        indices.extend([apex_b_i, ring_b[i], ring_b[i2]])
        indices.extend([ring_a[i], ring_b[i], ring_b[i2]])
        indices.extend([ring_a[i], ring_b[i2], ring_a[i2]])


def create_capsule_doll_mesh(global_pos, parents, joints_filter=None):
    """export_glb.create_bone_mesh() 대체(폴백) — 본마다 작은 큐브 대신, 관절을 잇는
    캡슐로 사람 실루엣에 가까운 미리보기 메시를 만든다. joints_filter를 주면 그 인덱스의
    조인트만 캡슐로 그린다(Mixamo 메시가 못 채우는 구멍만 메울 때 씀)."""
    vertices, joints, weights, indices = [], [], [], []
    target_indices = range(len(parents)) if joints_filter is None else joints_filter
    for i in target_indices:
        parent = parents[i]
        radius = _RADII[i] if i < len(_RADII) else 0.03
        if parent == -1:
            _capsule(vertices, joints, weights, indices, global_pos[i], global_pos[i], radius, i)
        else:
            _capsule(vertices, joints, weights, indices, global_pos[parent], global_pos[i], radius, i)
    return vertices, joints, weights, indices


def _load_mixamo_bind():
    if not _MIXAMO_BIND_PATH.exists():
        return None
    return json.loads(_MIXAMO_BIND_PATH.read_text(encoding="utf-8"))


# create_bone_mesh()의 반환 시그니처(vertices, joints, weights, indices)엔 색을 넣을 자리가
# 없어서(vendor 고정) 여기 사이드채널로 남겨두고, main()에서 후처리 단계(COLOR_0 주입)로
# 읽어간다. Y Bot은 갑옷 판(청록)과 관절 구(어두운 메탈릭 회색)의 재질이 서로 달라서
# 하나로 뭉개면 부정확하다 — 정점마다 원본 메시의 색을 그대로 들고 간다.
_last_vertex_colors = None


def create_preview_mesh(global_pos, parents):
    """export_glb.create_bone_mesh() 대체. Mixamo 바인딩 데이터가 있으면 그 메시를 쓰고
    (soma30 레스트 좌표계로 이미 재배치돼 있음 — assets/extract_mixamo_soma30.py 참고),
    거기 없는 조인트(목/턱/눈)만 캡슐로 채운다. 바인딩 데이터가 없으면 전부 캡슐로 그린다."""
    global _last_vertex_colors
    bind = _load_mixamo_bind()
    if bind is None:
        v, j, w, i = create_capsule_doll_mesh(global_pos, parents)
        _last_vertex_colors = [[0.75, 0.66, 0.58, 1.0]] * len(v)
        return v, j, w, i

    vertices = [list(p) for p in bind["vertices"]]
    joints = [[j, 0, 0, 0] for j in bind["joint_index"]]
    weights = [[1.0, 0.0, 0.0, 0.0] for _ in bind["joint_index"]]
    indices = list(bind["indices"])
    colors = [list(c) for c in bind.get("colors", [])] or [[0.75, 0.66, 0.58, 1.0]] * len(vertices)

    cap_v, cap_j, cap_w, cap_i = create_capsule_doll_mesh(
        global_pos, parents, joints_filter=sorted(_CAPSULE_ONLY_JOINTS))
    base = len(vertices)
    vertices.extend(cap_v)
    joints.extend(cap_j)
    weights.extend(cap_w)
    indices.extend(i + base for i in cap_i)
    colors.extend([bind.get("base_color", [0.75, 0.66, 0.58, 1.0])] * len(cap_v))

    _last_vertex_colors = colors
    return vertices, joints, weights, indices


export_glb.create_bone_mesh = create_preview_mesh


def _read_glb_chunks(data: bytes):
    magic, _version, _total_len = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF":
        raise ValueError("유효한 glb가 아닙니다")
    offset = 12
    json_len, _json_type = struct.unpack_from("<I4s", data, offset)
    offset += 8
    json_bytes = data[offset:offset + json_len]
    offset += json_len
    bin_len, _bin_type = struct.unpack_from("<I4s", data, offset)
    offset += 8
    bin_bytes = data[offset:offset + bin_len]
    return json.loads(json_bytes.decode("utf-8")), bytearray(bin_bytes)


def _write_glb_chunks(glb_path: Path, gltf: dict, bin_bytes: bytearray):
    new_json_bytes = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    while len(new_json_bytes) % 4 != 0:
        new_json_bytes += b" "
    while len(bin_bytes) % 4 != 0:
        bin_bytes += b"\x00"

    total_length = 12 + 8 + len(new_json_bytes) + 8 + len(bin_bytes)
    out = bytearray()
    out += struct.pack("<4sII", b"glTF", 2, total_length)
    out += struct.pack("<I4s", len(new_json_bytes), b"JSON")
    out += new_json_bytes
    out += struct.pack("<I4s", len(bin_bytes), b"BIN\x00")
    out += bin_bytes
    glb_path.write_bytes(bytes(out))


def _add_vertex_colors(glb_path: Path, colors):
    """이미 쓰여진 glb를 다시 열어 정점 색(COLOR_0)을 추가한다. Y Bot은 갑옷 판(청록)과
    관절 구(어두운 메탈릭 회색)의 실제 재질이 서로 다른데(2026-09-16, 사용자가 렌더 보고
    "조인트는 검은색인가봐"라고 확인해줌), 지금까지는 메시 전체를 재질 하나(청록)로
    뭉개서 관절도 청록색으로 나왔다. glTF는 COLOR_0가 있으면 baseColorFactor와 곱해서
    쓰므로, 재질의 baseColorFactor는 흰색으로 두고 정점 색으로만 실제 색을 낸다
    (_make_double_sided_skin_material이 colors 유무를 보고 처리)."""
    if not colors:
        return
    data = glb_path.read_bytes()
    gltf, bin_bytes = _read_glb_chunks(data)
    prim = gltf["meshes"][0]["primitives"][0]

    flat = []
    for c in colors:
        flat.extend((c[0], c[1], c[2], c[3] if len(c) > 3 else 1.0))
    color_bytes = struct.pack(f"<{len(flat)}f", *flat)
    while len(bin_bytes) % 4 != 0:
        bin_bytes.append(0)
    view_offset = len(bin_bytes)
    bin_bytes.extend(color_bytes)

    gltf["bufferViews"].append({
        "buffer": 0, "byteOffset": view_offset, "byteLength": len(color_bytes),
    })
    gltf["accessors"].append({
        "bufferView": len(gltf["bufferViews"]) - 1,
        "componentType": 5126, "count": len(colors), "type": "VEC4",
    })
    prim["attributes"]["COLOR_0"] = len(gltf["accessors"]) - 1
    gltf["buffers"][0]["byteLength"] = len(bin_bytes)

    _write_glb_chunks(glb_path, gltf, bin_bytes)


def _add_smooth_normals(glb_path: Path):
    """이미 쓰여진 glb를 다시 열어 부드러운 정점 법선(NORMAL)을 계산해 추가한다 —
    export_glb.py(벤더 원본)는 NORMAL 속성을 아예 안 넣는다. glTF 스펙상 없으면 뷰어가
    자동으로 계산해야 하지만 뷰어마다 처리가 달라(Blender 임포터는 문제없이 보였지만
    <model-viewer>가 그런다는 보장이 없음) — 뷰어에 맡기지 않고 직접 계산해서 넣는다.
    (2026-09-16: 실제로는 "조인트가 검게 나온다"는 사용자 보고의 원인이 이게 아니라
    재질이 하나로 뭉개진 것으로 밝혀졌지만 — 정점 법선을 직접 넣는 건 스펙 준수 차원에서
    맞는 방향이라 그대로 둠, `_add_vertex_colors` 참고.)"""
    data = glb_path.read_bytes()
    gltf, bin_bytes = _read_glb_chunks(data)

    prim = gltf["meshes"][0]["primitives"][0]
    if "NORMAL" in prim["attributes"]:
        return  # 이미 있음

    pos_acc = gltf["accessors"][prim["attributes"]["POSITION"]]
    idx_acc = gltf["accessors"][prim["indices"]]
    pv = gltf["bufferViews"][pos_acc["bufferView"]]
    iv = gltf["bufferViews"][idx_acc["bufferView"]]

    n = pos_acc["count"]
    pos_bytes = bytes(bin_bytes[pv["byteOffset"]:pv["byteOffset"] + pv["byteLength"]])
    positions = struct.unpack(f"<{n * 3}f", pos_bytes)
    idx_bytes = bytes(bin_bytes[iv["byteOffset"]:iv["byteOffset"] + iv["byteLength"]])
    indices = struct.unpack(f"<{idx_acc['count']}H", idx_bytes)

    normals = [[0.0, 0.0, 0.0] for _ in range(n)]
    for t in range(0, len(indices), 3):
        i0, i1, i2 = indices[t], indices[t + 1], indices[t + 2]
        p0 = positions[i0 * 3:i0 * 3 + 3]
        p1 = positions[i1 * 3:i1 * 3 + 3]
        p2 = positions[i2 * 3:i2 * 3 + 3]
        ux, uy, uz = p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]
        vx, vy, vz = p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2]
        # 정규화 안 한 크로스 곱 — 삼각형 넓이만큼 가중치가 실려서 자연스럽게 평균됨.
        nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
        for i in (i0, i1, i2):
            normals[i][0] += nx
            normals[i][1] += ny
            normals[i][2] += nz

    norm_flat = []
    for nx, ny, nz in normals:
        length = math.sqrt(nx * nx + ny * ny + nz * nz)
        if length < 1e-12:
            norm_flat.extend((0.0, 1.0, 0.0))
        else:
            norm_flat.extend((nx / length, ny / length, nz / length))

    normal_bytes = struct.pack(f"<{len(norm_flat)}f", *norm_flat)
    while len(bin_bytes) % 4 != 0:
        bin_bytes.append(0)
    view_offset = len(bin_bytes)
    bin_bytes.extend(normal_bytes)

    gltf["bufferViews"].append({
        "buffer": 0, "byteOffset": view_offset, "byteLength": len(normal_bytes),
    })
    gltf["accessors"].append({
        "bufferView": len(gltf["bufferViews"]) - 1,
        "componentType": 5126, "count": n, "type": "VEC3",
    })
    prim["attributes"]["NORMAL"] = len(gltf["accessors"]) - 1
    gltf["buffers"][0]["byteLength"] = len(bin_bytes)

    _write_glb_chunks(glb_path, gltf, bin_bytes)


def _make_double_sided_skin_material(glb_path: Path, base_color=None, has_vertex_colors=False):
    """이미 쓰여진 glb를 다시 열어 doubleSided 재질을 하나 추가한다 — 캡슐 옆면
    삼각형 감김 방향이 어느 한쪽에서 틀려도 안 보이는 면이 생기지 않도록 하는 안전장치.
    base_color를 안 주면(=Mixamo 데이터가 없어서 캡슐만 쓸 때) 살구색 기본값을 쓴다.
    has_vertex_colors=True면(=_add_vertex_colors로 COLOR_0을 이미 넣은 경우)
    baseColorFactor는 흰색으로 둔다 — glTF는 COLOR_0을 baseColorFactor와 곱하므로,
    여기서 또 색을 넣으면 이중으로 곱해져 색이 틀어진다."""
    data = glb_path.read_bytes()
    gltf, bin_bytes = _read_glb_chunks(data)

    factor = [1.0, 1.0, 1.0, 1.0] if has_vertex_colors else (
        list(base_color) if base_color else [0.75, 0.66, 0.58, 1.0])
    gltf["materials"] = [{
        "name": "KimodoPreviewDoll",
        "doubleSided": True,
        "pbrMetallicRoughness": {
            "baseColorFactor": factor,
            "metallicFactor": 0.0,
            "roughnessFactor": 0.9,
        },
    }]
    for primitive in gltf["meshes"][0]["primitives"]:
        primitive["material"] = 0

    _write_glb_chunks(glb_path, gltf, bin_bytes)


def main():
    parser = argparse.ArgumentParser(description="Export Kimodo motion to a preview GLB with a capsule-doll mesh")
    parser.add_argument("--motion-dir", default="output_motion")
    parser.add_argument("--output", default="output_motion/animation.glb")
    parser.add_argument("--model", default="soma30", choices=["soma30"])
    parser.add_argument("--fps", type=float, default=30.0)
    args = parser.parse_args()

    output_path = Path(args.output)

    bind = _load_mixamo_bind()
    if bind is not None and "offsets" in bind:
        # Mixamo 자체 본 길이로 SOMA30 offsets를 바꿔치기 — 메시(Mixamo 원본 좌표)와
        # 스켈레톤이 서로 다른 비율이면 관절 경계마다 이음매가 갈라져 보이는 문제가 있어서
        # (2026-09-16 실측), extract_mixamo_soma30.py가 이미 새 offsets를 계산해뒀다.
        export_glb.SKELETONS[args.model]["offsets"] = bind["offsets"]

    export_glb.convert_motion_to_glb(Path(args.motion_dir), output_path, skeleton_key=args.model, fps=args.fps)
    _add_smooth_normals(output_path)
    _add_vertex_colors(output_path, _last_vertex_colors)
    _make_double_sided_skin_material(
        output_path,
        base_color=bind.get("base_color") if bind else None,
        has_vertex_colors=bool(_last_vertex_colors),
    )


if __name__ == "__main__":
    main()

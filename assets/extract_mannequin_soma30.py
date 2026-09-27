"""Blender headless: UE5 마네킹(SKM_Quinn_Simple·SKM_Manny_Simple FBX)을 SOMA30 미리보기 바인딩으로 뽑는다.
Mixamo 판(`extract_mixamo_soma30.py`)과 출력 형식이 같다 — 웹 UI 캐릭터 선택기에 그대로 뜬다.
한 번만 돌리는 에셋 준비 스크립트다.

    "Blender 5.2\\blender.exe" --background --python assets\\extract_mannequin_soma30.py -- ^
        --fbx "assets\\mannequin_src\\SKM_Quinn_Simple.FBX"

`--out` 을 생략하면 `assets/mixamo_processed/<fbx 이름>_soma30_bind.json` 에 쓴다 — 웹 UI 서버가 그 폴더의
`*_soma30_bind.json` 을 캐릭터 목록으로 읽기 때문이다(폴더 이름은 역사적 이유로 mixamo 다).

**Mixamo 판과 다른 점 셋** (2026-09-27, SKM_Quinn_Simple.FBX 실측 — `history/2026-09-27_mannequin-apose-preview-report.md`):

1. **A-포즈를 T-포즈로 편다.** Kimodo 회전은 SOMA30 레스트(T-포즈) 기준이라, 레스트가 A-포즈인 메시에 그대로 입히면
   팔이 몸통으로 파고든다. 마네킹 위팔은 수평에서 약 53° 아래, 팔꿈치도 앞으로 굽어 있다. 그래서 추출 전에 팔 체인
   (위팔·아래팔·손)을 수평 ±X 로, 다리 체인(허벅지·종아리)을 수직 아래로 포즈를 준 뒤, 아마추어 변형이 적용된
   메시 좌표와 포즈 본 위치를 레스트로 쓴다(Apply Pose as Rest 와 같은 효과, 원본 파일은 안 건드림).
   회전은 현재 방향 → 목표 방향의 최소 회전이라 위팔은 앞뒤 축으로 들어 올려지고, 손바닥이 몸을 향하던 자세는
   아래를 향하게 된다 — SOMA30 의 T-포즈(엄지가 앞)와 같은 방향이다.
2. **웨이트가 트위스트 본에 있다.** Simple 메시는 `upperarm_l`·`lowerarm_l`·`thigh_l`·`calf_l`·`spine_05` 에
   정점 그룹이 없고, 대신 `*_twist_01/02_*` 에 웨이트가 있다. 트위스트 본은 부모 본의 SOMA 조인트로 보낸다.
3. **LOD 가 여러 개 들어온다.** 기본 FBX 내보내기는 LOD0~2 를 함께 넣는다. `_LOD0` 메시 하나만 쓴다(없으면 정점이
   가장 많은 메시).

**색**: UE 마네킹의 색은 머티리얼 인스턴스(`MI_Quinn_01`·`MI_Quinn_02`)의 디퓨즈 텍스처(`T_Quinn_01_D`·`T_Quinn_02_D`)에서
나온다. FBX 에는 텍스처가 딸려 나가지 않으므로, 사용자가 NS 에디터에서 텍스처를 FBX 와 같은 폴더에 내보내 두면
(`T_Quinn_01_D.tga` 등 — 슬롯 이름 `MI_<이름>_<번호>` → 파일 `T_<이름>_<번호>_D.*`) 정점마다 UV 로 텍스처를 샘플해
정점 색으로 넣는다(UV 이음매의 정점은 코너 평균). 텍스처가 없으면 단색 회색이다.

스파인은 마네킹 5마디를 SOMA 3마디(Spine1·Spine2·Chest)에 나눈다 — 조인트 위치는 높이가 가장 가까운 본
(spine_02·spine_03·spine_04)의 head 이고, 정점은 그 조인트 구간에 드는 본으로 보낸다(spine_01 은 Hips 구간,
spine_05 는 Chest 구간). SOMA30 에 대응이 없는 Jaw·LeftEye·RightEye 는 원본 오프셋을 둔다(Mixamo 판과 같다).
정점마다 웨이트가 가장 큰 본 하나에 강체로 묶는다(Mixamo 판과 같은 방식).
"""
import bpy
import json
import math
import re
import sys
from pathlib import Path

from mathutils import Matrix, Vector

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "kimodo.cpp" / "scripts"))
import export_glb  # noqa: E402  (vendor 모듈, 디스크상 파일은 안 건드림)


def _parse_script_args() -> dict:
    """Blender 는 자기 인자와 스크립트 인자를 `--` 로 구분해서 sys.argv 에 같이 넘긴다."""
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    out = {}
    it = iter(argv)
    for tok in it:
        if tok == "--fbx":
            out["fbx"] = next(it, None)
        elif tok == "--out":
            out["out"] = next(it, None)
    return out


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "character"


_args = _parse_script_args()
FBX_PATH = Path(_args["fbx"]) if _args.get("fbx") else REPO_ROOT / "assets" / "mannequin_src" / "SKM_Quinn_Simple.FBX"
if not FBX_PATH.is_absolute():
    FBX_PATH = REPO_ROOT / FBX_PATH
_stem = re.sub(r"^skm_", "", FBX_PATH.stem.lower())
OUT_PATH = Path(_args["out"]) if _args.get("out") else REPO_ROOT / "assets" / "mixamo_processed" / f"{_slugify(_stem)}_soma30_bind.json"

# SOMA30 순서: 0 Hips,1 Spine1,2 Spine2,3 Chest,4 Neck1,5 Neck2,6 Head,7 Jaw,8 LeftEye,9 RightEye,
# 10 LeftShoulder,11 LeftArm,12 LeftForeArm,13 LeftHand,14 LeftHandThumbEnd,15 LeftHandMiddleEnd,
# 16 RightShoulder,17 RightArm,18 RightForeArm,19 RightHand,20 RightHandThumbEnd,21 RightHandMiddleEnd,
# 22 LeftLeg,23 LeftShin,24 LeftFoot,25 LeftToeBase,26 RightLeg,27 RightShin,28 RightFoot,29 RightToeBase.
# 마네킹은 _l 이 +X(캐릭터 왼쪽)이고 SOMA30 도 +X 가 왼쪽이다.

# 정점 그룹(본) 이름 -> SOMA30 조인트.
BONE_TO_SOMA = {
    "pelvis": 0, "spine_01": 0,
    "spine_02": 1,
    "spine_03": 2,
    "spine_04": 3, "spine_05": 3,
    "neck_01": 4,
    "neck_02": 5,
    "head": 6,
}
for side, s in (("l", 0), ("r", 6)):
    BONE_TO_SOMA.update({
        f"clavicle_{side}": 10 + s,
        f"upperarm_{side}": 11 + s, f"upperarm_twist_01_{side}": 11 + s, f"upperarm_twist_02_{side}": 11 + s,
        f"lowerarm_{side}": 12 + s, f"lowerarm_twist_01_{side}": 12 + s, f"lowerarm_twist_02_{side}": 12 + s,
        f"hand_{side}": 13 + s,
    })
    # [DOC] 손가락은 Mixamo 판과 같이 손(Hand)에 강체로 묶는다 — SOMA30 엔 손가락 자유도가 없다.
    for finger in ("thumb", "index", "middle", "ring", "pinky"):
        for part in ("metacarpal", "01", "02", "03"):
            BONE_TO_SOMA[f"{finger}_{part}_{side}"] = 13 + s
for side, s in (("l", 0), ("r", 4)):
    BONE_TO_SOMA.update({
        f"thigh_{side}": 22 + s, f"thigh_twist_01_{side}": 22 + s, f"thigh_twist_02_{side}": 22 + s,
        f"calf_{side}": 23 + s, f"calf_twist_01_{side}": 23 + s, f"calf_twist_02_{side}": 23 + s,
        f"foot_{side}": 24 + s,
        f"ball_{side}": 25 + s,
    })

# SOMA30 조인트 -> 그 위치를 뽑을 마네킹 본("head" 또는 "tail"). tail 은 자식이 없는 마지막 손가락 마디의 끝이다.
SOMA_TO_BONE_POS = {
    0: ("pelvis", "head"), 1: ("spine_02", "head"), 2: ("spine_03", "head"), 3: ("spine_04", "head"),
    4: ("neck_01", "head"), 5: ("neck_02", "head"), 6: ("head", "head"),
}
for side, s in (("l", 0), ("r", 6)):
    SOMA_TO_BONE_POS.update({
        10 + s: (f"clavicle_{side}", "head"), 11 + s: (f"upperarm_{side}", "head"),
        12 + s: (f"lowerarm_{side}", "head"), 13 + s: (f"hand_{side}", "head"),
        14 + s: (f"thumb_03_{side}", "tail"), 15 + s: (f"middle_03_{side}", "tail"),
    })
for side, s in (("l", 0), ("r", 4)):
    SOMA_TO_BONE_POS.update({
        22 + s: (f"thigh_{side}", "head"), 23 + s: (f"calf_{side}", "head"),
        24 + s: (f"foot_{side}", "head"), 25 + s: (f"ball_{side}", "head"),
    })

# T-포즈로 펼 체인 — (본, 방향을 잴 끝 본). 부모부터 순서대로 편다(부모 회전이 자식에 전파된 뒤 자식을 잰다).
# 목표 방향은 Blender 좌표(Z-up)다: 왼팔 +X, 오른팔 -X, 다리 -Z.
STRAIGHTEN = [
    ("upperarm_l", "lowerarm_l", Vector((1, 0, 0))),
    ("lowerarm_l", "hand_l", Vector((1, 0, 0))),
    ("hand_l", "middle_01_l", Vector((1, 0, 0))),
    ("upperarm_r", "lowerarm_r", Vector((-1, 0, 0))),
    ("lowerarm_r", "hand_r", Vector((-1, 0, 0))),
    ("hand_r", "middle_01_r", Vector((-1, 0, 0))),
    ("thigh_l", "calf_l", Vector((0, 0, -1))),
    ("calf_l", "foot_l", Vector((0, 0, -1))),
    ("thigh_r", "calf_r", Vector((0, 0, -1))),
    ("calf_r", "foot_r", Vector((0, 0, -1))),
]


def _angle_below_horizontal(d: Vector) -> float:
    return math.degrees(math.atan2(-d.z, math.hypot(d.x, d.y)))


FALLBACK_COLOR = [0.62, 0.62, 0.66, 1.0]


def _srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def load_slot_textures(mesh_obj):
    """[DOC] 머티리얼 슬롯마다 FBX 옆의 디퓨즈 텍스처를 찾아 (너비, 높이, 픽셀 배열)로 돌려준다. 없으면 None."""
    textures = []
    for slot in mesh_obj.material_slots:
        name = slot.material.name if slot.material else ""
        m = re.match(r"MI_(.+)$", name)
        found = None
        if m:
            # [DOC] Manny 의 인스턴스는 `MI_Manny_01_New` 인데 텍스처는 `T_Manny_01_D` 다 — `_New` 접미사를 뗀 이름도 찾는다.
            stems = [m.group(1)] + ([m.group(1)[:-4]] if m.group(1).endswith("_New") else [])
            for stem in stems:
                for ext in (".tga", ".TGA", ".png", ".PNG", ".jpg", ".bmp"):
                    cand = FBX_PATH.parent / f"T_{stem}_D{ext}"
                    if cand.exists():
                        found = cand
                        break
                if found:
                    break
        if found is None:
            print(f"슬롯 {name}: 디퓨즈 텍스처 없음 — 단색")
            textures.append(None)
            continue
        img = bpy.data.images.load(str(found))
        w, h = img.size
        px = list(img.pixels[:])
        print(f"슬롯 {name}: {found.name} {w}x{h}")
        textures.append((w, h, px))
    return textures


def sample(texture, uv):
    w, h, px = texture
    x = min(max(int((uv[0] % 1.0) * w), 0), w - 1)
    y = min(max(int((uv[1] % 1.0) * h), 0), h - 1)
    i = (y * w + x) * 4
    return px[i], px[i + 1], px[i + 2]


def vertex_colors(mesh, textures):
    """[DOC] 정점 색(선형) — 코너(loop)마다 자기 폴리곤 슬롯의 텍스처를 UV 로 샘플해 정점별로 평균한다.
    텍스처 픽셀은 sRGB 로 저장된 값이라 glTF COLOR_0(선형)로 바꾼다."""
    n = len(mesh.vertices)
    acc = [[0.0, 0.0, 0.0, 0] for _ in range(n)]
    uv_layer = mesh.uv_layers.active
    if uv_layer is None or not any(textures):
        return [FALLBACK_COLOR] * n
    for poly in mesh.polygons:
        tex = textures[poly.material_index] if poly.material_index < len(textures) else None
        if tex is None:
            continue
        for li in poly.loop_indices:
            r, g, b = sample(tex, uv_layer.data[li].uv)
            a = acc[mesh.loops[li].vertex_index]
            a[0] += r; a[1] += g; a[2] += b; a[3] += 1
    out = []
    for r, g, b, cnt in acc:
        if cnt == 0:
            out.append(FALLBACK_COLOR)
        else:
            out.append([_srgb_to_linear(r / cnt), _srgb_to_linear(g / cnt), _srgb_to_linear(b / cnt), 1.0])
    return out


def straighten_to_tpose(arm_obj):
    """[DOC] 체인마다 (본 head → 끝 본 head) 방향을 목표 방향으로 돌리는 최소 회전을 포즈로 준다(아마추어 공간)."""
    pose = arm_obj.pose
    for bone_name, end_name, target in STRAIGHTEN:
        pb = pose.bones[bone_name]
        end = pose.bones[end_name]
        current = (end.head - pb.head)
        before = _angle_below_horizontal(current)
        rot = current.normalized().rotation_difference(target.normalized()).to_matrix().to_4x4()
        pivot = Matrix.Translation(pb.head)
        pb.matrix = pivot @ rot @ pivot.inverted() @ pb.matrix
        bpy.context.view_layer.update()
        after = _angle_below_horizontal(end.head - pb.head)
        print(f"straighten {bone_name}: 수평 아래 {before:6.1f}° -> {after:6.1f}°")


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(FBX_PATH))

    arm_obj = next((o for o in bpy.context.scene.objects if o.type == "ARMATURE"), None)
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if arm_obj is None or not meshes:
        raise RuntimeError("Armature 또는 메시를 찾지 못했다")
    lod0 = [o for o in meshes if o.name.endswith("_LOD0")]
    mesh_obj = lod0[0] if lod0 else max(meshes, key=lambda o: len(o.data.vertices))
    print(f"mesh: {mesh_obj.name} ({len(mesh_obj.data.vertices)} verts), 후보 {[o.name for o in meshes]}")

    straighten_to_tpose(arm_obj)

    def to_gltf_up(v):
        # Blender 는 Z-up, glTF(따라서 SOMA30 오프셋)는 Y-up — (x,y,z) -> (x,z,-y). 마네킹 FBX 는 정면이 -Y 라 +Z 가 된다.
        return (v.x, v.z, -v.y)

    # [DOC] 포즈를 준 뒤의 본 위치(월드, 미터 — FBX 의 0.01 스케일 부모가 matrix_world 에 들어 있다).
    pb = arm_obj.pose.bones
    mw = arm_obj.matrix_world
    head_world = {b.name: to_gltf_up(mw @ b.head) for b in pb}
    tail_world = {b.name: to_gltf_up(mw @ b.tail) for b in pb}

    soma_world = {}
    for idx, (bone, which) in SOMA_TO_BONE_POS.items():
        soma_world[idx] = (head_world if which == "head" else tail_world)[bone]

    skel = export_glb.SKELETONS["soma30"]
    parents = skel["parents"]
    offsets = [list(o) for o in skel["offsets"]]
    for idx, pos in soma_world.items():
        p = parents[idx]
        if p == -1:
            offsets[idx] = list(pos)
        elif p in soma_world:
            pp = soma_world[p]
            offsets[idx] = [pos[0] - pp[0], pos[1] - pp[1], pos[2] - pp[2]]

    # [DOC] 아마추어 변형이 적용된(T-포즈) 메시 좌표 — 정점 순서는 원본과 같다(아마추어 모디파이어는 토폴로지를 안 바꾼다).
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = mesh_obj.evaluated_get(depsgraph)
    eval_mesh = eval_obj.to_mesh()
    src = mesh_obj.data
    if len(eval_mesh.vertices) != len(src.vertices):
        raise RuntimeError("평가된 메시의 정점 수가 원본과 다르다 — 아마추어 외 모디파이어가 있다")

    group_names = [vg.name for vg in mesh_obj.vertex_groups]
    missing = sorted(set(group_names) - set(BONE_TO_SOMA))
    if missing:
        raise RuntimeError(f"BONE_TO_SOMA 에 없는 정점 그룹: {missing}")

    per_vertex_color = vertex_colors(src, load_slot_textures(mesh_obj))
    vertices, joint_index, colors, remap = [], [], [], {}
    for i, v in enumerate(src.vertices):
        if not v.groups:
            continue
        best = max(v.groups, key=lambda g: g.weight)
        remap[i] = len(vertices)
        vertices.append(list(to_gltf_up(eval_obj.matrix_world @ eval_mesh.vertices[i].co)))
        joint_index.append(BONE_TO_SOMA[group_names[best.group]])
        colors.append(per_vertex_color[i])

    indices = []
    src.calc_loop_triangles()
    for tri in src.loop_triangles:
        vs = tri.vertices
        if all(vi in remap for vi in vs):
            indices.extend([remap[vs[0]], remap[vs[1]], remap[vs[2]]])
    eval_obj.to_mesh_clear()

    # [DOC] 기본색은 정점 색 평균(텍스처가 없으면 단색 회색).
    base_color = [sum(c[k] for c in colors) / len(colors) for k in range(3)] + [1.0]
    xs, ys, zs = zip(*vertices)
    print(f"total vertices={len(vertices)} (그룹 없는 정점 {len(src.vertices) - len(vertices)}) indices={len(indices)}")
    print(f"bbox x=[{min(xs):.3f},{max(xs):.3f}] y=[{min(ys):.3f},{max(ys):.3f}] z=[{min(zs):.3f},{max(zs):.3f}]")
    for idx in (11, 13, 17, 19, 22, 24):
        print(f"joint {idx:2d} {skel['names'][idx]:>10}: {tuple(round(c, 3) for c in soma_world[idx])}")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps({
        "label": FBX_PATH.stem,
        "vertices": vertices,
        "joint_index": joint_index,
        "colors": colors,
        "indices": indices,
        "base_color": base_color,
        "offsets": offsets,
    }), encoding="utf-8")
    print(f"wrote {OUT_PATH}")


main()

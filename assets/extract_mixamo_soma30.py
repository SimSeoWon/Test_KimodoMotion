"""Blender headless: Y Bot.fbx의 스킨 메시(Alpha_Surface + Alpha_Joints)를 SOMA30 조인트
인덱스에 맞춰 뽑아내고, SOMA30의 본 길이(offsets)도 Mixamo 자체 비율로 바꿔치기한다.
한 번만 돌리는 에셋 준비 스크립트 — 매 생성마다 돌지 않는다.

**왜 offsets까지 바꾸는가** (2026-09-16, 첫 버전에서 몸통/팔/다리 이음매가 갈라져 보이는
문제를 겪고 나서 다시 설계함): 처음엔 정점을 "자기 본 기준 로컬 오프셋 + SOMA30 레스트
위치"로 재배치했는데, SOMA30과 Mixamo Y Bot의 실제 본 길이가 정확히 같지 않아서 두
정점이 서로 다른 본에 묶여 있으면(예: 가슴 쪽은 Chest에, 위팔은 LeftArm에) 각자 다른
양만큼 밀려서 관절 경계마다 메시가 갈라져 보였다(회전 없는 레스트 프레임에서도!). 그래서
방향을 바꿔: SOMA30의 조인트 계층(이름·부모·30개 순서)은 그대로 두고, **각 본의 로컬
오프셋(부모 대비 위치)만 Mixamo 자신의 실제 치수로 교체**한다 — 그러면 메시는 원래
Mixamo 아티스트가 그린 좌표를 그대로 쓰면 되고(재배치 계산 없음), 스켈레톤도 그 메시에
딱 맞아서 이음매가 안 생긴다. 목/턱/눈(Neck1/Neck2/Jaw/LeftEye/RightEye)처럼 Mixamo에
대응 본이 없는 5개만 SOMA30 원래 오프셋을 그대로 둔다(그 부위는 pretty_export_glb.py의
캡슐로 메움 — 눈에 덜 띄는 곳이라 감수).

Y Bot은 메시가 2개다 — `Alpha_Surface`(갑옷 판)와 `Alpha_Joints`(그 판 사이 틈을 메우는
구형 관절 메시). 2026-09-16 첫 버전엔 `Alpha_Surface`만 썼다가 어깨 등이 붕 떠 보이는
문제가 있었음 — 사용자가 "원본엔 그 틈에 구형 메시가 있다"고 지적해서 둘 다 합친다.

손가락도 처음엔 SOMA에 마커가 2개(ThumbEnd/MiddleEnd)뿐이라며 여러 손가락을 한 점으로
욱여넣었는데("재배치") 그러면 손가락 5개가 한 덩어리로 뭉친다 — 사용자가 지적. Hand(13)가
이미 Mixamo 치수 기준으로 정확히 놓이므로, 손가락도 그냥 원본 좌표 그대로 쓰면(재배치 안
함) Hand에 자연스럽게 붙어서 5개가 갈라져 보인다 — SOMA 조인트 인덱스(14/15/20/21)는
애니메이션 가중치용으로만 쓰고 위치는 재배치하지 않는다.

    "Blender 5.2\\blender.exe" --background --python assets\\extract_mixamo_soma30.py

여러 Mixamo 캐릭터를 웹 UI 콤보박스에서 고를 수 있게 하려면(2026-09-17), 인자 없이 돌리면
지금까지처럼 Y Bot을 처리하고, 다른 캐릭터는 `--fbx`/`--out`으로 지정한다(Blender는 스크립트
인자를 `--` 뒤에 받는다):

    "Blender 5.2\\blender.exe" --background --python assets\\extract_mixamo_soma30.py -- ^
        --fbx "assets\\mixamo_src\\Warrior.fbx" --out "assets\\mixamo_processed\\warrior_soma30_bind.json"

`--out`을 생략하면 fbx 파일 이름에서 자동으로 만든다(`Warrior.fbx` -> `warrior_soma30_bind.json`).
MIXAMO_TO_SOMA/SOMA_TO_MIXAMO_POS는 Mixamo 오토리거가 어느 캐릭터에나 똑같이 붙이는
`mixamorig:` 본 이름 기준이라 그대로 재사용되고, 메시(들)도 이름을 고정하지 않고 armature
아래 있는 걸 전부 자동으로 찾아 합친다(Y Bot처럼 갑옷 판+관절 구로 나뉜 캐릭터도, 메시가
하나뿐인 캐릭터도 둘 다 됨) — 단, vertex group이 MIXAMO_TO_SOMA에 없는 본을 쓰면(표준
Mixamo 휴머노이드 리그가 아니면) 바로 에러로 멈춘다(추측해서 뭉개지 않음).
"""
import bpy
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "kimodo.cpp" / "scripts"))
import export_glb  # noqa: E402  (vendor 모듈, 디스크상 파일은 안 건드림)


def _parse_script_args() -> dict:
    """Blender는 자기 인자와 스크립트 인자를 `--`로 구분해서 sys.argv에 같이 넘긴다."""
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


_script_args = _parse_script_args()
FBX_PATH = Path(_script_args["fbx"]) if _script_args.get("fbx") else REPO_ROOT / "assets" / "mixamo_src" / "Y Bot.fbx"
if _script_args.get("out"):
    OUT_PATH = Path(_script_args["out"])
elif _script_args.get("fbx"):
    OUT_PATH = REPO_ROOT / "assets" / "mixamo_processed" / f"{_slugify(FBX_PATH.stem)}_soma30_bind.json"
else:
    OUT_PATH = REPO_ROOT / "assets" / "mixamo_processed" / "ybot_soma30_bind.json"  # 하위호환(인자 없이 호출)

# 2026-09-16 Blender 5.2로 Y Bot.fbx를 실측 확인한 vertex group 이름 -> SOMA30 조인트 인덱스.
# SOMA30 순서: 0 Hips,1 Spine1,2 Spine2,3 Chest,4 Neck1,5 Neck2,6 Head,7 Jaw,8 LeftEye,
# 9 RightEye,10 LeftShoulder,11 LeftArm,12 LeftForeArm,13 LeftHand,14 LeftHandThumbEnd,
# 15 LeftHandMiddleEnd,16 RightShoulder,17 RightArm,18 RightForeArm,19 RightHand,
# 20 RightHandThumbEnd,21 RightHandMiddleEnd,22 LeftLeg,23 LeftShin,24 LeftFoot,
# 25 LeftToeBase,26 RightLeg,27 RightShin,28 RightFoot,29 RightToeBase.
MIXAMO_TO_SOMA = {
    "mixamorig:Hips": 0,
    "mixamorig:Spine": 1,
    "mixamorig:Spine1": 2,
    "mixamorig:Spine2": 3,
    "mixamorig:Neck": 4,  # Alpha_Joints에만 있는 그룹(Alpha_Surface엔 없음)
    "mixamorig:Head": 6,
    "mixamorig:LeftShoulder": 10,
    "mixamorig:LeftArm": 11,
    "mixamorig:LeftForeArm": 12,
    "mixamorig:LeftHand": 13,
    "mixamorig:RightShoulder": 16,
    "mixamorig:RightArm": 17,
    "mixamorig:RightForeArm": 18,
    "mixamorig:RightHand": 19,
    "mixamorig:LeftUpLeg": 22,
    "mixamorig:LeftLeg": 23,
    "mixamorig:LeftFoot": 24,
    "mixamorig:LeftToeBase": 25,
    "mixamorig:RightUpLeg": 26,
    "mixamorig:RightLeg": 27,
    "mixamorig:RightFoot": 28,
    "mixamorig:RightToeBase": 29,
}
# 손가락 체인(Thumb/Index/Middle/Ring/Pinky 1~3, 좌우)은 SOMA에 개별 대응이 없다.
# 처음엔 SOMA의 마커(*HandThumbEnd/*HandMiddleEnd)에 묶어봤는데, 그 마커는 진짜 손가락
# 관절이 아니라 이름만 있는 리프 마커라 모델이 주는 회전값이 실제 손가락 위치와 안 맞는
# 피벗이 되어, 회전이 걸릴 때마다 손가락들이 화면 밖으로 날아가버림(2026-09-16 렌더로
# 실측 확인 — 프레임 0/15는 우연히 덜 튀어서 괜찮아 보였을 뿐). SOMA30엔 애초에 손가락
# 전용 자유도가 없으니(그 마커 회전값 자체가 의미 없는 노이즈) 손(Hand)에 강체로
# 묶는다 — 손이 움직이는 대로만 같이 움직이고, 손가락 개별 애니메이션은 처음부터
# 없는 기능이라 잃을 것도 없다.
for side, hand_idx in (("Left", 13), ("Right", 19)):
    for finger in ("Thumb", "Index", "Middle", "Ring", "Pinky"):
        for i in (1, 2, 3, 4):
            MIXAMO_TO_SOMA[f"mixamorig:{side}Hand{finger}{i}"] = hand_idx

# soma_idx -> (Mixamo 본 이름, "head" 또는 "tail") — 그 조인트의 Mixamo 기준 절대 위치를
# 어디서 뽑을지. 몸통/팔/다리 체인은 같은 이름의 본 head. 손가락 끝 마커는 체인의 마지막
# 본(4번째, 메시 웨이트는 없지만 본 자체는 있음) tail을 손끝 근사치로 쓴다. 목은 Mixamo에
# Neck 하나뿐이라 Neck1=Neck.head, Neck2=Neck과 Head 사이 보간으로 근사한다(아래 별도 처리).
SOMA_TO_MIXAMO_POS = {
    0: ("mixamorig:Hips", "head"),
    1: ("mixamorig:Spine", "head"),
    2: ("mixamorig:Spine1", "head"),
    3: ("mixamorig:Spine2", "head"),
    6: ("mixamorig:Head", "head"),
    10: ("mixamorig:LeftShoulder", "head"),
    11: ("mixamorig:LeftArm", "head"),
    12: ("mixamorig:LeftForeArm", "head"),
    13: ("mixamorig:LeftHand", "head"),
    14: ("mixamorig:LeftHandThumb4", "tail"),
    15: ("mixamorig:LeftHandMiddle4", "tail"),
    16: ("mixamorig:RightShoulder", "head"),
    17: ("mixamorig:RightArm", "head"),
    18: ("mixamorig:RightForeArm", "head"),
    19: ("mixamorig:RightHand", "head"),
    20: ("mixamorig:RightHandThumb4", "tail"),
    21: ("mixamorig:RightHandMiddle4", "tail"),
    22: ("mixamorig:LeftUpLeg", "head"),
    23: ("mixamorig:LeftLeg", "head"),
    24: ("mixamorig:LeftFoot", "head"),
    25: ("mixamorig:LeftToeBase", "head"),
    26: ("mixamorig:RightUpLeg", "head"),
    27: ("mixamorig:RightLeg", "head"),
    28: ("mixamorig:RightFoot", "head"),
    29: ("mixamorig:RightToeBase", "head"),
}


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(FBX_PATH))

    arm_obj = None
    mesh_objs = {}
    for obj in bpy.context.scene.objects:
        if obj.type == "ARMATURE":
            arm_obj = obj
        if obj.type == "MESH":
            mesh_objs[obj.name] = obj
    if arm_obj is None or not mesh_objs:
        raise RuntimeError("Armature 또는 메시를 찾지 못했다")

    def to_gltf_up(v):
        # Blender는 Z-up, glTF(따라서 SOMA30 SKELETONS 오프셋)는 Y-up이다.
        # 표준 변환(Blender의 glTF 익스포터 "+Y Up"과 동일): (x,y,z) -> (x,z,-y).
        return (v.x, v.z, -v.y)

    def mix(a, b, t):
        return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)

    bone_head_world = {}
    bone_tail_world = {}
    for bone in arm_obj.data.bones:
        bone_head_world[bone.name] = to_gltf_up(arm_obj.matrix_world @ bone.head_local)
        bone_tail_world[bone.name] = to_gltf_up(arm_obj.matrix_world @ bone.tail_local)

    # SOMA30 조인트별 Mixamo 기준 "정답 위치"(Y-up, 월드). 27/30개를 채운다 — 나머지
    # 3개(Jaw, LeftEye, RightEye)는 Mixamo에 대응이 없어서 안 채움(SOMA30 원본 오프셋 유지).
    soma_world = {}
    for soma_idx, (bone_name, which) in SOMA_TO_MIXAMO_POS.items():
        table = bone_head_world if which == "head" else bone_tail_world
        soma_world[soma_idx] = table[bone_name]
    # Neck1/Neck2: Mixamo엔 목 본이 하나(Neck)뿐이라 Neck1=Neck.head,
    # Neck2=Neck.head와 Head.head 사이 60% 지점으로 근사(목이 아래쪽에 더 치우치게).
    neck_head = bone_head_world["mixamorig:Neck"]
    head_head = bone_head_world["mixamorig:Head"]
    soma_world[4] = neck_head
    soma_world[5] = mix(neck_head, head_head, 0.6)

    skel = export_glb.SKELETONS["soma30"]
    parents = skel["parents"]
    new_offsets = [list(o) for o in skel["offsets"]]  # 기본값: SOMA30 원본(Jaw/Eye 등에 남김)
    for soma_idx, pos in soma_world.items():
        p = parents[soma_idx]
        if p == -1:
            new_offsets[soma_idx] = list(pos)
        else:
            parent_pos = soma_world.get(p)
            if parent_pos is None:
                continue  # 부모가 Mixamo 미대응이면(이 리그에선 안 생김) 원본 유지
            new_offsets[soma_idx] = [pos[0] - parent_pos[0], pos[1] - parent_pos[1], pos[2] - parent_pos[2]]

    def get_base_color(obj):
        fallback = [0.75, 0.66, 0.58, 1.0]  # 못 찾으면 기존 살구색 폴백
        if not (obj and obj.data.materials and obj.data.materials[0]):
            return fallback
        mat = obj.data.materials[0]
        if not mat.use_nodes:
            return fallback
        for node in mat.node_tree.nodes:
            if node.type == "BSDF_PRINCIPLED":
                return list(node.inputs["Base Color"].default_value)
        return fallback

    # 메시가 여러 개인 캐릭터(Y Bot=갑옷 판+관절 구처럼)도, 하나뿐인 캐릭터도 다 되게
    # armature 아래 메시를 이름 고정 없이 전부 자동으로 찾아 하나로 합친다. 정점 수가
    # 제일 많은 메시(보통 몸통 본체)를 base_color 기본값으로 쓴다 — 하나로 뭉개지 않고
    # 정점마다 원본 메시의 색을 그대로 들고 간다(COLOR_0로 pretty_export_glb.py가 심음).
    mesh_items = sorted(mesh_objs.items(), key=lambda kv: -len(kv[1].data.vertices))
    mesh_colors = {name: get_base_color(obj) for name, obj in mesh_items}
    base_color = mesh_colors[mesh_items[0][0]]

    out_vertices = []
    out_joint_index = []
    out_colors = []
    indices = []

    # 모든 메시를 SOMA30 조인트에 매핑해서 하나로 합친다. Mixamo 원본 좌표를 그대로
    # 쓴다(재배치 없음) — offsets를 이미 Mixamo 치수로 바꿔놨으니 스켈레톤과 메시가
    # 서로 딱 맞는다(재배치하면 오히려 손가락처럼 여러 본이 한 점으로 뭉친다).
    for mesh_name, obj in mesh_items:
        mesh = obj.data
        group_names = [vg.name for vg in obj.vertex_groups]
        missing = sorted(set(group_names) - set(MIXAMO_TO_SOMA.keys()))
        if missing:
            raise RuntimeError(f"{mesh_name}: MIXAMO_TO_SOMA에 없는 vertex group: {missing}")

        mesh_mat = obj.matrix_world
        color = mesh_colors[mesh_name]
        remap = {}  # 이 메시 안에서: 원본 vertex index -> 출력 index (그룹 없는 정점은 스킵)
        for i, v in enumerate(mesh.vertices):
            if not v.groups:
                continue
            best = max(v.groups, key=lambda g: g.weight)
            bone_name = group_names[best.group]
            soma_idx = MIXAMO_TO_SOMA[bone_name]
            wp = to_gltf_up(mesh_mat @ v.co)

            remap[i] = len(out_vertices)
            out_vertices.append(list(wp))
            out_joint_index.append(soma_idx)
            out_colors.append(color)

        mesh.calc_loop_triangles()
        for tri in mesh.loop_triangles:
            vs = tri.vertices
            if all(vi in remap for vi in vs):
                indices.extend([remap[vs[0]], remap[vs[1]], remap[vs[2]]])
        print(f"{mesh_name}: {len(remap)}/{len(mesh.vertices)} vertices used, color={color}")

    xs = [p[0] for p in out_vertices]
    ys = [p[1] for p in out_vertices]
    zs = [p[2] for p in out_vertices]
    print(f"total vertices={len(out_vertices)} indices={len(indices)}")
    print(f"bbox x=[{min(xs):.3f},{max(xs):.3f}] y=[{min(ys):.3f},{max(ys):.3f}] "
          f"z=[{min(zs):.3f},{max(zs):.3f}]")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps({
        "label": FBX_PATH.stem,  # 웹 UI 콤보박스에 보여줄 이름 (예: "Y Bot")
        "vertices": out_vertices,
        "joint_index": out_joint_index,
        "colors": out_colors,
        "indices": indices,
        "base_color": base_color,
        "offsets": new_offsets,
    }), encoding="utf-8")
    print(f"wrote {OUT_PATH} (base_color={base_color})")


main()

"""Blender headless: Y Bot.fbx의 스킨 메시(Alpha_Surface)를 SOMA30 스켈레톤의 레스트
포즈 좌표계로 재배치해서 정점 위치 + SOMA30 조인트 인덱스(단일 지배 가중치)를 JSON으로
뽑아낸다. 한 번만 돌리는 에셋 준비 스크립트 — 매 생성마다 돌지 않는다.

각 정점은:
  1. Mixamo에서 가장 가중치가 높은 vertex group(=본)을 찾는다.
  2. 그 본의 월드 좌표 기준 로컬 오프셋(정점 - 본 head)을 구한다 — Mixamo 고유의
     체형/디테일은 이 오프셋에 보존됨.
  3. 그 본을 SOMA30 조인트 인덱스로 매핑(MIXAMO_TO_SOMA)하고, SOMA30의 레스트 글로벌
     위치 + 위 로컬 오프셋으로 최종 좌표를 만든다 — 즉 "로컬 모양은 유지하되 관절 피벗만
     SOMA30 배치로 옮긴다". 애니메이션 쪽(rotation-only 채널)과 어긋나지 않게 하려는 목적
     — export_glb.py의 IBM이 SOMA30 global_rest에서만 계산되기 때문에, 레스트 프레임의
     정점 좌표가 뭐든 그대로 보이지만(항등 변환) 관절이 회전하기 시작하면 피벗과 정점의
     상대 위치가 틀어질수록 왜곡이 커진다 — 그래서 상대 위치(로컬 오프셋)를 보존하는 것.

    "Blender 5.2\\blender.exe" --background --python assets\\extract_mixamo_soma30.py
"""
import bpy
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "vendor" / "kimodo.cpp" / "scripts"))
import export_glb  # noqa: E402  (vendor 모듈, 디스크상 파일은 안 건드림)

FBX_PATH = REPO_ROOT / "assets" / "mixamo_src" / "Y Bot.fbx"
OUT_PATH = REPO_ROOT / "assets" / "mixamo_processed" / "ybot_soma30_bind.json"

# 2026-09-16 Blender 5.2로 Y Bot.fbx를 실측 확인한 vertex group 이름 -> SOMA30 조인트 인덱스.
# SOMA30 순서: 0 Hips,1 Spine1,2 Spine2,3 Chest,4 Neck1,5 Neck2,6 Head,7 Jaw,8 LeftEye,
# 9 RightEye,10 LeftShoulder,11 LeftArm,12 LeftForeArm,13 LeftHand,14 LeftHandThumbEnd,
# 15 LeftHandMiddleEnd,16 RightShoulder,17 RightArm,18 RightForeArm,19 RightHand,
# 20 RightHandThumbEnd,21 RightHandMiddleEnd,22 LeftLeg,23 LeftShin,24 LeftFoot,
# 25 LeftToeBase,26 RightLeg,27 RightShin,28 RightFoot,29 RightToeBase.
# Mixamo에는 Neck1/Neck2/Jaw/LeftEye/RightEye에 대응하는 vertex group이 없다(목 부위는
# Spine2/Head 그룹이 이미 커버) — 그 5개 조인트는 이 매핑에 안 나오고, 대신
# pretty_export_glb.py의 캡슐 메시로 채운다.
MIXAMO_TO_SOMA = {
    "mixamorig:Hips": 0,
    "mixamorig:Spine": 1,
    "mixamorig:Spine1": 2,
    "mixamorig:Spine2": 3,
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
# 손가락 체인(Thumb/Index/Middle/Ring/Pinky 1~3, 좌우)은 SOMA에 개별 대응이 없으니
# 엄지는 ThumbEnd로, 나머지 네 손가락은 MiddleEnd로 뭉뚱그린다.
for side, thumb_end, other_end in (("Left", 14, 15), ("Right", 20, 21)):
    for finger, target in (("Thumb", thumb_end), ("Index", other_end), ("Middle", other_end),
                            ("Ring", other_end), ("Pinky", other_end)):
        for i in (1, 2, 3, 4):
            MIXAMO_TO_SOMA[f"mixamorig:{side}Hand{finger}{i}"] = target


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(FBX_PATH))

    arm_obj, mesh_obj = None, None
    for obj in bpy.context.scene.objects:
        if obj.type == "ARMATURE":
            arm_obj = obj
        if obj.type == "MESH" and obj.name == "Alpha_Surface":
            mesh_obj = obj
    if arm_obj is None or mesh_obj is None:
        raise RuntimeError("Armature 또는 Alpha_Surface 메시를 찾지 못했다")

    bone_head_world = {}
    for bone in arm_obj.data.bones:
        w = arm_obj.matrix_world @ bone.head_local
        bone_head_world[bone.name] = (w.x, w.y, w.z)

    skel = export_glb.SKELETONS["soma30"]
    soma_global_rest = export_glb.compute_global_rest_positions(skel["parents"], skel["offsets"])

    mesh = mesh_obj.data
    group_names = [vg.name for vg in mesh_obj.vertex_groups]
    missing = sorted(set(group_names) - set(MIXAMO_TO_SOMA.keys()))
    if missing:
        raise RuntimeError(f"MIXAMO_TO_SOMA에 없는 vertex group: {missing}")

    mesh_mat = mesh_obj.matrix_world
    out_vertices = []
    out_joint_index = []
    remap = {}  # 원본 vertex index -> 출력 index (그룹 없는 정점은 스킵)

    for i, v in enumerate(mesh.vertices):
        if not v.groups:
            continue
        best = max(v.groups, key=lambda g: g.weight)
        bone_name = group_names[best.group]
        soma_idx = MIXAMO_TO_SOMA[bone_name]

        wp = mesh_mat @ v.co
        bh = bone_head_world[bone_name]
        local_offset = (wp.x - bh[0], wp.y - bh[1], wp.z - bh[2])
        target = soma_global_rest[soma_idx]
        final = [target[0] + local_offset[0], target[1] + local_offset[1], target[2] + local_offset[2]]

        remap[i] = len(out_vertices)
        out_vertices.append(final)
        out_joint_index.append(soma_idx)

    mesh.calc_loop_triangles()
    indices = []
    for tri in mesh.loop_triangles:
        vs = tri.vertices
        if all(vi in remap for vi in vs):
            indices.extend([remap[vs[0]], remap[vs[1]], remap[vs[2]]])

    xs = [p[0] for p in out_vertices]
    ys = [p[1] for p in out_vertices]
    zs = [p[2] for p in out_vertices]
    print(f"vertices={len(out_vertices)} indices={len(indices)} "
          f"skipped={len(mesh.vertices) - len(out_vertices)}")
    print(f"bbox x=[{min(xs):.3f},{max(xs):.3f}] y=[{min(ys):.3f},{max(ys):.3f}] "
          f"z=[{min(zs):.3f},{max(zs):.3f}]")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps({
        "vertices": out_vertices,
        "joint_index": out_joint_index,
        "indices": indices,
    }), encoding="utf-8")
    print(f"wrote {OUT_PATH}")


main()

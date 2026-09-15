"""Blender headless 탐색용: Y Bot.fbx의 본 계층/이름과 메시 버텍스 그룹을 덤프한다.
    "Blender 5.2\\blender.exe" --background --python assets\\_inspect_mixamo.py
"""
import bpy
import sys
from pathlib import Path

fbx_path = Path(__file__).resolve().parent / "mixamo_src" / "Y Bot.fbx"

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=str(fbx_path))

arm_obj = None
mesh_objs = {}
for obj in bpy.context.scene.objects:
    print("OBJECT:", obj.name, obj.type)
    if obj.type == "ARMATURE":
        arm_obj = obj
    if obj.type == "MESH":
        mesh_objs[obj.name] = obj
mesh_obj = mesh_objs.get("Alpha_Surface")

print("\n--- ARMATURE BONES (name, parent, head_local, tail_local) ---")
if arm_obj:
    for bone in arm_obj.data.bones:
        parent = bone.parent.name if bone.parent else None
        h = bone.head_local
        t = bone.tail_local
        print(f"{bone.name}\tparent={parent}\thead=({h.x:.4f},{h.y:.4f},{h.z:.4f})\ttail=({t.x:.4f},{t.y:.4f},{t.z:.4f})")

print("\n--- MESH INFO (Alpha_Surface) ---")
if mesh_obj:
    print("vertex count:", len(mesh_obj.data.vertices))
    print("vertex groups:", [vg.name for vg in mesh_obj.vertex_groups])
    print("modifiers:", [(m.name, m.type) for m in mesh_obj.modifiers])
else:
    print("Alpha_Surface not found; have:", list(mesh_objs.keys()))

print("\nDONE")

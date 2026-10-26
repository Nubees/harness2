import sys
from pathlib import Path

# Add project directory to sys.path
sys.path.insert(0, str(Path(r"C:\Projects\Harnes2\Project_no2_Image_to_3d_Model")))
from omni_engine import sanitize_blender_script, inject_exports_dir, Omni3DEngine

# A script written like what the LLM will generate using the SOTA API:
llm_script = """
import bpy
from pathlib import Path
from mathutils import Vector

init_clean_scene()

exports_dir = Path(__file__).resolve().parent / "exports"
exports_dir.mkdir(parents=True, exist_ok=True)

# 1. Proportional volumes
bpy.ops.mesh.primitive_uv_sphere_add(radius=1.0, location=(0, 0, 1))
body = bpy.context.active_object
body.name = "Body"

bpy.ops.mesh.primitive_uv_sphere_add(radius=0.4, location=(0.5, -0.4, 0.8))
cheek = bpy.context.active_object
cheek.name = "Cheek"

# 2. Voxel remesh fusion
body = fuse_objects_voxel_remesh([cheek], body, voxel_size=0.035, smooth_factor=0.6, smooth_iters=3)

# 3. Dynamic Bézier flame plume
pts = [Vector((0, 0, 1.8)), Vector((0.2, 0.4, 2.2)), Vector((0.5, 0.8, 2.5))]
radii = [1.5, 0.8, 0.05]
flame = create_swept_spline_mesh("CrownFlame", pts, radii, bevel_depth=0.15)

# 4. Materials
body_mat = make_organic_pbr_material("BodyMat", "#FF5500", roughness=0.35, sss_weight=0.3, rim_hex="#FFAA00", rim_strength=2.0)
body.data.materials.append(body_mat)

flame_mat = make_organic_pbr_material("FlameMat", "#FFAA00", roughness=0.2, rim_hex="#FFFF55", rim_strength=4.0)
flame.data.materials.append(flame_mat)

# 5. Export
export_scene_models(exports_dir, "test_sota_model")
"""

out_dir = Path("test_sota_run")
out_dir.mkdir(exist_ok=True)
exports_dir = out_dir / "exports"

sanitized = sanitize_blender_script(llm_script)
sanitized = inject_exports_dir(sanitized, exports_dir)

script_file = out_dir / "test_script.py"
script_file.write_text(sanitized, encoding="utf-8")

engine = Omni3DEngine()
res = engine.execute_blender_script(script_file)

print(f"Blender Execution Success: {res['success']}")
print(f"Elapsed: {res['elapsed_sec']}s")
if not res['success']:
    print("BLENDER LOG:")
    print(res['output'])

# Check exported deliverables
for ext in ["glb", "obj", "stl", "fbx"]:
    files = list(exports_dir.glob(f"*.{ext}"))
    assert len(files) > 0, f"Missing export for {ext}!"
    print(f"Deliverable .{ext}: {files[0].name} ({round(files[0].stat().st_size / 1024, 1)} KB)")

print("\nPIPELINE VERIFICATION SUCCESSFUL: ALL DELIVERABLES GENERATED HEADLESSLY IN BLENDER 5.2 LTS!")

"""Standalone Integration Verification for TencentARC InstantMesh Gradio API.
"""

import json
import os
import sys
import time
from pathlib import Path

# Set up paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
IMG_PATH = PROJECT_ROOT / "Project_no2_Image_to_3d_Model" / "spaceman.png"
KEYS_FILE = PROJECT_ROOT / "Project_no2_Image_to_3d_Model" / "keys.json"
EXPORTS_DIR = PROJECT_ROOT / "Project_no2_Image_to_3d_Model" / "exports" / "instantmesh_test"
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

# Load HF token
token = None
if KEYS_FILE.is_file():
    try:
        keys_data = json.loads(KEYS_FILE.read_text(encoding="utf-8"))
        token = keys_data.get("hf_token") or (keys_data.get("hf_tokens", [None])[0])
    except Exception as e:
        print(f"Warning reading keys.json: {e}")

if not token:
    token = os.environ.get("HF_TOKEN")

# For testing, try anonymous / public community pool first or fallback if token quota exceeded
use_token = False
token_to_use = token if use_token else None

print(f"HF Token to use: {bool(token_to_use)}")
print(f"Input image: {IMG_PATH} (exists: {IMG_PATH.is_file()})")

from gradio_client import Client, handle_file

print("\n--- Connecting to TencentARC/InstantMesh ---")
t0 = time.time()
client = Client("TencentARC/InstantMesh", token=token_to_use, httpx_kwargs={"timeout": 300.0})
print(f"Connected in {time.time() - t0:.2f}s")
print(f"Client session_hash: {getattr(client, 'session_hash', 'N/A')}")
print(f"Client cookies: {getattr(client, 'cookies', 'N/A')}")

# Step 1: Preprocess
print("\n--- Step 1: Preprocessing Image ---")
t1 = time.time()
prep_out = client.predict(
    input_image=handle_file(str(IMG_PATH)),
    do_remove_background=True,
    api_name="/preprocess",
)
print(f"Preprocess completed in {time.time() - t1:.2f}s")
print(f"Preprocess output type: {type(prep_out)}")
print(f"Preprocess output: {prep_out}")

# Step 2: Generate Multiviews
print("\n--- Step 2: Generating Multi-views (/generate_mvs) ---")
# If prep_out is a dict, get the path, or handle_file if needed
prep_file_arg = prep_out
if isinstance(prep_out, dict) and "path" in prep_out:
    prep_file_arg = prep_out["path"]

t2 = time.time()
# Let's test with sample_steps=30 for faster test
mvs_out = client.predict(
    input_image=handle_file(prep_file_arg),
    sample_steps=30,
    sample_seed=42,
    api_name="/generate_mvs",
)
print(f"Generate MVS completed in {time.time() - t2:.2f}s")
print(f"Generate MVS output type: {type(mvs_out)}")
print(f"Generate MVS output: {mvs_out}")

# Step 3: Make 3D
print("\n--- Step 3: Synthesizing 3D Mesh (/make3d) ---")
t3 = time.time()
make3d_out = client.predict(
    api_name="/make3d",
)
print(f"Make 3D completed in {time.time() - t3:.2f}s")
print(f"Make 3D output type: {type(make3d_out)}")
print(f"Make 3D output: {make3d_out}")

# Inspect files
obj_out, glb_out = make3d_out
print(f"\nOBJ path: {obj_out} (exists: {Path(obj_out).is_file()}, size: {Path(obj_out).stat().st_size} bytes)")
print(f"GLB path: {glb_out} (exists: {Path(glb_out).is_file()}, size: {Path(glb_out).stat().st_size} bytes)")

# Copy to exports dir
import shutil
saved_obj = EXPORTS_DIR / "instantmesh.obj"
saved_glb = EXPORTS_DIR / "instantmesh.glb"
shutil.copy2(obj_out, saved_obj)
shutil.copy2(glb_out, saved_glb)
print(f"Saved OBJ to: {saved_obj}")
print(f"Saved GLB to: {saved_glb}")

# Verify with Blender 5.2
print("\n--- Verifying with Blender 5.2 LTS ---")
blender_exe = Path(r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
if blender_exe.is_file():
    blender_script = f'''
import bpy
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=r"{saved_glb}")
meshes = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']
total_verts = sum(len(m.data.vertices) for m in meshes)
total_polys = sum(len(m.data.polygons) for m in meshes)
print(f"BLENDER_VERIFY_GLB: mesh_count={{len(meshes)}} verts={{total_verts}} polys={{total_polys}}")

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.wm.obj_import(filepath=r"{saved_obj}")
meshes = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']
total_verts = sum(len(m.data.vertices) for m in meshes)
total_polys = sum(len(m.data.polygons) for m in meshes)
print(f"BLENDER_VERIFY_OBJ: mesh_count={{len(meshes)}} verts={{total_verts}} polys={{total_polys}}")
'''
    import subprocess
    res = subprocess.run(
        [str(blender_exe), "-b", "-P", "-"],
        input=blender_script,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    print("Blender output:")
    for line in res.stdout.splitlines():
        if "BLENDER_VERIFY" in line:
            print(f"  {line}")
else:
    print(f"Blender not found at {blender_exe}")

print("\nVerification Test Complete!")

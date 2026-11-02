"""End-to-End Verification of Stability AI Stable Fast 3D (SF3D)
Tests:
1. ZeroGPU connection with HF Token from keys.json
2. Transparent image flow (2-step)
3. Opaque image flow (3-step with rembg on ZeroGPU)
4. Blender 5.2 LTS export to GLB, OBJ, STL, FBX
"""

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROJECT_NO2 = PROJECT_ROOT / "Project_no2_Image_to_3d_Model"
KEYS_FILE = PROJECT_NO2 / "keys.json"
EXPORTS_DIR = PROJECT_NO2 / "exports" / "sf3d_test"
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
BLENDER_EXE = Path(r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")

# Load HF token
token = None
if KEYS_FILE.is_file():
    keys_data = json.loads(KEYS_FILE.read_text(encoding="utf-8"))
    token = keys_data.get("hf_token") or (keys_data.get("hf_tokens", [None])[0])

from gradio_client import Client, handle_file

print(f"Connecting to stabilityai/stable-fast-3d (Token: {token[:6] if token else 'None'}...)...")
client = Client("stabilityai/stable-fast-3d", token=token, httpx_kwargs={"timeout": 180.0})
print(f"Client session_hash: {client.session_hash}")

test_img = PROJECT_NO2 / "spaceman.png"
if not test_img.is_file():
    test_img = PROJECT_ROOT / "assets" / "logo.png"

print(f"Testing with image: {test_img} (exists: {test_img.is_file()})")
im = Image.open(test_img)
has_alpha = False
if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
    extrema = im.convert("RGBA").getchannel("A").getextrema()
    if extrema[0] < 255:
        has_alpha = True
print(f"Image has transparency: {has_alpha}")

# Step 1: /requires_bg_remove
t0 = time.time()
print("Stage 1: Calling /requires_bg_remove...")
res_bg = client.predict(
    image=handle_file(str(test_img)),
    fr=0.85,
    api_name="/requires_bg_remove",
)
print(f"Stage 1 completed in {time.time() - t0:.2f}s")

# Disable skip_components so we can pass all 7 arguments to fn_index 5
client._skip_components = False

# Step 2: If opaque, call 'Remove Background' first
if not has_alpha:
    t_rem = time.time()
    print("Stage 2a: Image is opaque, triggering ZeroGPU rembg (/run_button 'Remove Background')...")
    client.predict(
        "Remove Background",
        handle_file(str(test_img)),
        None,
        0.85,
        "None",
        -1,
        1024,
        fn_index=5,
    )
    print(f"Stage 2a completed in {time.time() - t_rem:.2f}s")

# Step 3: Run 3D generation
t_gen = time.time()
print("Stage 2b: Synthesizing UV-unwrapped 3D mesh (/run_button 'Run')...")
res_run = client.predict(
    "Run",
    handle_file(str(test_img)),
    None,
    0.85,
    "None",
    -1,
    1024,
    fn_index=5,
)
print(f"Stage 2b completed in {time.time() - t_gen:.2f}s (Total time: {time.time() - t0:.2f}s)")

# Extract GLB
glb_path = res_run[4]
if isinstance(glb_path, dict) and "value" in glb_path:
    glb_path = glb_path["value"]

dest_glb = EXPORTS_DIR / "model.glb"
shutil.copy2(glb_path, dest_glb)
print(f"Saved GLB: {dest_glb} ({dest_glb.stat().st_size:,} bytes)")

# Format conversion test
if BLENDER_EXE.is_file():
    print("\nStage 3: Headless Blender 5.2 LTS Conversion (GLB -> OBJ, STL, FBX)...")
    convert_script = f'''
import bpy
from pathlib import Path
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=r"{dest_glb.resolve()}")
bpy.ops.object.select_all(action='SELECT')
exports_dir = Path(r"{EXPORTS_DIR.resolve()}")
bpy.ops.wm.obj_export(filepath=str(exports_dir / "model.obj"))
bpy.ops.wm.stl_export(filepath=str(exports_dir / "model.stl"))
bpy.ops.export_scene.fbx(filepath=str(exports_dir / "model.fbx"))
meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
total_verts = sum(len(m.data.vertices) for m in meshes)
total_polys = sum(len(m.data.polygons) for m in meshes)
print(f"BLENDER_SUCCESS: meshes={{len(meshes)}} verts={{total_verts}} polys={{total_polys}}")
'''
    tmp_blend = EXPORTS_DIR / "convert.py"
    tmp_blend.write_text(convert_script, encoding="utf-8")
    proc = subprocess.run([str(BLENDER_EXE), "-b", "-P", str(tmp_blend)], stdout=subprocess.PIPE, text=True)
    for line in proc.stdout.splitlines():
        if "BLENDER_" in line:
            print(f"  {line}")

for fmt in ("glb", "obj", "stl", "fbx"):
    p = EXPORTS_DIR / f"model.{fmt}"
    print(f"Deliverable .{fmt}: {'EXISTS (' + str(p.stat().st_size) + ' bytes)' if p.is_file() else 'MISSING'}")

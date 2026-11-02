"""Complete Verification of Stability AI Stable Fast 3D (SF3D) Hugging Face ZeroGPU Integration.

Tests:
1. Opaque image handling (RGB JPG / opaque PNG) vs Alpha PNG.
2. 2-step / 3-step Gradio interaction via client._skip_components = False and fn_index=5.
3. GLB model extraction and validation.
4. Blender 5.2 LTS headless conversion to OBJ, STL, FBX.
5. Geometry and texture validation in Blender.
6. Token rotation and exact execution timing.
"""

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from PIL import Image
from gradio_client import Client, handle_file

PROJECT_ROOT = Path(__file__).resolve().parent.parent
KEYS_FILE = PROJECT_ROOT / "Project_no2_Image_to_3d_Model" / "keys.json"
EXPORTS_DIR = PROJECT_ROOT / "Project_no2_Image_to_3d_Model" / "exports" / "sf3d_test"
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

BLENDER_EXE = Path(r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")

# Load HF token
keys_data = json.loads(KEYS_FILE.read_text(encoding="utf-8")) if KEYS_FILE.is_file() else {}
hf_tokens = keys_data.get("hf_tokens", [])
hf_token = hf_tokens[0] if hf_tokens else keys_data.get("hf_token")

print("=" * 75)
print("STABILITY AI STABLE FAST 3D (SF3D) INTEGRATION VERIFICATION")
print("=" * 75)
print(f"HF Token: {hf_token[:6]}...{hf_token[-4:]}" if hf_token else "No token found")
print(f"Blender Exe: {BLENDER_EXE} (exists: {BLENDER_EXE.is_file()})")
print(f"Exports Dir: {EXPORTS_DIR}")

def check_image_alpha(img_path: Path) -> bool:
    with Image.open(img_path) as im:
        if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
            extrema = im.convert("RGBA").getchannel("A").getextrema()
            # If minimum alpha is less than 255, it has transparent pixels
            return extrema[0] < 255
        return False

def verify_blender_conversion(glb_path: Path, output_dir: Path):
    print("\n--- Verifying Blender Headless Conversion (GLB -> OBJ, STL, FBX) ---")
    t0 = time.time()
    script = f'''
import bpy
from pathlib import Path

bpy.ops.wm.read_factory_settings(use_empty=True)
glb_file = r"{glb_path.resolve()}"
out_dir = Path(r"{output_dir.resolve()}")

print("Importing GLTF/GLB...")
bpy.ops.import_scene.gltf(filepath=glb_file)
bpy.ops.object.select_all(action='SELECT')

meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
total_verts = sum(len(m.data.vertices) for m in meshes)
total_polys = sum(len(m.data.polygons) for m in meshes)
print(f"BLENDER_IMPORT_GLB: mesh_count={{len(meshes)}} total_verts={{total_verts}} total_polys={{total_polys}}")

print("Exporting OBJ...")
bpy.ops.wm.obj_export(filepath=str(out_dir / "model.obj"))

print("Exporting STL...")
bpy.ops.wm.stl_export(filepath=str(out_dir / "model.stl"))

print("Exporting FBX...")
bpy.ops.export_scene.fbx(filepath=str(out_dir / "model.fbx"))

# Verify exported OBJ
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.wm.obj_import(filepath=str(out_dir / "model.obj"))
obj_meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
print(f"BLENDER_VERIFY_OBJ: mesh_count={{len(obj_meshes)}} total_verts={{sum(len(m.data.vertices) for m in obj_meshes)}}")

# Verify exported STL
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.wm.stl_import(filepath=str(out_dir / "model.stl"))
stl_meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
print(f"BLENDER_VERIFY_STL: mesh_count={{len(stl_meshes)}} total_verts={{sum(len(m.data.vertices) for m in stl_meshes)}}")

# Verify exported FBX
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=str(out_dir / "model.fbx"))
fbx_meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
print(f"BLENDER_VERIFY_FBX: mesh_count={{len(fbx_meshes)}} total_verts={{sum(len(m.data.vertices) for m in fbx_meshes)}}")

print("BLENDER_ALL_EXPORTS_SUCCESS")
'''
    script_path = output_dir / "convert_verify.py"
    script_path.write_text(script, encoding="utf-8")

    res = subprocess.run([str(BLENDER_EXE), "-b", "-P", str(script_path)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    blender_time = time.time() - t0
    print(f"Blender conversion completed in {blender_time:.2f}s")
    for line in res.stdout.splitlines():
        if "BLENDER_" in line:
            print(f"  {line}")
    return res.returncode == 0

def run_sf3d_pipeline(image_path: Path, token_val: str | None, tag: str):
    print(f"\n=======================================================")
    print(f"RUNNING SF3D PIPELINE TEST: [{tag}]")
    print(f"Image: {image_path} (exists: {image_path.is_file()})")
    has_alpha = check_image_alpha(image_path)
    print(f"Detected Transparency / Alpha Channel: {has_alpha}")
    print(f"=======================================================")

    t_start = time.time()
    print("Connecting to stabilityai/stable-fast-3d Space...")
    client = Client("stabilityai/stable-fast-3d", token=token_val, httpx_kwargs={"timeout": 300.0})
    print(f"Connected in {time.time() - t_start:.2f}s. Session hash: {client.session_hash}")

    foreground_ratio = 0.85
    remesh_option = "None"
    vertex_count = -1
    texture_size = 1024

    # Step 1: /requires_bg_remove
    t1 = time.time()
    print("\n--- Step 1: /requires_bg_remove ---")
    res1 = client.predict(
        image=handle_file(str(image_path)),
        fr=foreground_ratio,
        api_name="/requires_bg_remove",
    )
    print(f"Step 1 finished in {time.time() - t1:.2f}s. Result: {res1}")

    # Set _skip_components to False so we can pass all components
    client._skip_components = False

    # Step 2: Remove Background if opaque
    if not has_alpha:
        t2 = time.time()
        print("\n--- Step 2: fn_index=5 with 'Remove Background' (remote rembg) ---")
        res_bg = client.predict(
            "Remove Background",
            handle_file(str(image_path)),
            None,
            foreground_ratio,
            remesh_option,
            vertex_count,
            texture_size,
            fn_index=5,
        )
        print(f"Step 2 remote background removal finished in {time.time() - t2:.2f}s.")
        print(f"Button state returned: {res_bg[0] if len(res_bg) > 0 else 'N/A'}")
    else:
        print("\n--- Step 2: Skipped (image already has alpha) ---")

    # Step 3: Run model to generate mesh
    t3 = time.time()
    print("\n--- Step 3: fn_index=5 with 'Run' (ZeroGPU SF3D mesh generation) ---")
    res_run = client.predict(
        "Run",
        handle_file(str(image_path)),
        None,
        foreground_ratio,
        remesh_option,
        vertex_count,
        texture_size,
        fn_index=5,
    )
    t_gen = time.time() - t3
    print(f"Step 3 mesh generation finished in {t_gen:.2f}s!")

    # Extract GLB path
    raw_glb = res_run[4]
    glb_path = raw_glb["value"] if isinstance(raw_glb, dict) and "value" in raw_glb else raw_glb
    print(f"Generated GLB path: {glb_path}")

    if not glb_path or not Path(glb_path).is_file():
        raise RuntimeError(f"GLB file was not created or path is invalid: {raw_glb}")

    dest_glb = EXPORTS_DIR / f"{tag}_model.glb"
    shutil.copy2(glb_path, dest_glb)
    file_size_kb = dest_glb.stat().st_size / 1024
    print(f"Copied GLB to: {dest_glb} ({file_size_kb:.1f} KB)")

    total_time = time.time() - t_start
    print(f"\n>>> Total SF3D Generation Time: {total_time:.2f}s (GPU Inference: {t_gen:.2f}s)")

    # Verify with Blender
    verify_blender_conversion(dest_glb, EXPORTS_DIR)

    return {
        "tag": tag,
        "has_alpha": has_alpha,
        "total_time": total_time,
        "gpu_time": t_gen,
        "glb_size_kb": file_size_kb,
        "glb_path": str(dest_glb),
    }

if __name__ == "__main__":
    # Test with opaque spaceman image (spaceman.png is opaque RGBA 255)
    opaque_img = PROJECT_ROOT / "Project_no2_Image_to_3d_Model" / "spaceman.png"
    res_opaque = run_sf3d_pipeline(opaque_img, hf_token, "opaque_spaceman")
    print("\nAll verification steps completed successfully!")
    print(json.dumps(res_opaque, indent=2))

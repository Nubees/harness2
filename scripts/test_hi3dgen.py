"""Standalone Integration Verification for Stable-X/Hi3DGen Hugging Face ZeroGPU API.

Hi3DGen: High-fidelity 3D Geometry Generation from Images via Normal Bridging
(GAP Lab CUHKSZ & ByteDance Game-AIGC Team)
Hosted on Hugging Face Spaces: Stable-X/Hi3DGen (ZeroGPU zero-a10g / sm_120 Blackwell stack)

Pipeline:
1. Load HF Token pool from keys.json (or anonymous public community pool).
2. Connect to Gradio Client 'Stable-X/Hi3DGen'.
3. Call named endpoint '/generate_3d' with spaceman.png.
4. Handle ZeroGPU execution / quota detection.
5. Convert GLB into OBJ, STL, and FBX deliverables using headless Blender 5.2.1 LTS.
6. Verify mesh topology, vertex counts, polygon counts across all formats.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
IMAGE_PATH = PROJECT_ROOT / "Project_no2_Image_to_3d_Model" / "spaceman.png"
KEYS_FILE = PROJECT_ROOT / "Project_no2_Image_to_3d_Model" / "keys.json"
EXPORTS_DIR = PROJECT_ROOT / "Project_no2_Image_to_3d_Model" / "exports" / "hi3dgen_test"
SAMPLE_GLB = PROJECT_ROOT / "Project_no2_Image_to_3d_Model" / "exports" / "clean_spaceman.glb"
BLENDER_EXE = Path(r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")

EXPORTS_DIR.mkdir(parents=True, exist_ok=True)


def load_token_pool() -> list[str]:
    """Load tokens from keys.json or environment."""
    tokens = []
    if KEYS_FILE.is_file():
        try:
            data = json.loads(KEYS_FILE.read_text(encoding="utf-8"))
            if "hf_tokens" in data and isinstance(data["hf_tokens"], list):
                tokens = [str(k).strip() for k in data["hf_tokens"] if str(k).strip()]
            elif "hf_token" in data and data["hf_token"]:
                tokens = [str(data["hf_token"]).strip()]
        except Exception as e:
            print(f"[WARN] Error reading keys.json: {e}")

    if not tokens and os.environ.get("HF_TOKEN"):
        tokens = [os.environ["HF_TOKEN"].strip()]
    return tokens


def run_blender_conversion(glb_input: Path, out_dir: Path, formats: list[str]) -> dict[str, Path]:
    """Convert input GLB to OBJ, STL, FBX using modern Blender 5.2 LTS operators."""
    if not BLENDER_EXE.is_file():
        print(f"[WARN] Blender executable not found at {BLENDER_EXE}")
        return {}

    script_path = out_dir / "blender_convert.py"
    script_content = f'''import bpy
from pathlib import Path

bpy.ops.wm.read_factory_settings(use_empty=True)

source = Path(r"{glb_input.resolve()}")
out_dir = Path(r"{out_dir.resolve()}")

# Import GLB
bpy.ops.import_scene.gltf(filepath=str(source))

# Recalculate normals & clean geometry
for obj in bpy.context.scene.objects:
    if obj.type == 'MESH':
        bpy.context.view_layer.objects.active = obj
        try:
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.normals_make_consistent(inside=False)
            bpy.ops.object.mode_set(mode='OBJECT')
        except Exception:
            pass

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

formats = {formats}
if "obj" in formats:
    bpy.ops.wm.obj_export(filepath=str(out_dir / "model.obj"))
if "stl" in formats:
    bpy.ops.wm.stl_export(filepath=str(out_dir / "model.stl"))
if "fbx" in formats:
    bpy.ops.export_scene.fbx(filepath=str(out_dir / "model.fbx"))

print("BLENDER_CONVERT_SUCCESS")
'''
    script_path.write_text(script_content, encoding="utf-8")

    t0 = time.time()
    res = subprocess.run(
        [str(BLENDER_EXE), "-b", "-P", str(script_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    dt = time.time() - t0

    if "BLENDER_CONVERT_SUCCESS" not in res.stdout:
        print(f"[FAIL] Blender conversion failed (took {dt:.2f}s):\n{res.stderr or res.stdout}")
        return {}

    print(f"[OK] Blender 5.2 LTS conversion completed in {dt:.2f}s.")
    deliverables = {}
    for fmt in formats:
        fpath = out_dir / f"model.{fmt}"
        if fpath.is_file():
            deliverables[fmt] = fpath
    return deliverables


def verify_mesh_topology(mesh_file: Path, fmt: str) -> dict:
    """Inspect vertex and polygon statistics inside Blender 5.2 LTS."""
    if not BLENDER_EXE.is_file():
        return {}

    script_path = EXPORTS_DIR / f"verify_{fmt}.py"
    script_content = f'''import bpy
from pathlib import Path

bpy.ops.wm.read_factory_settings(use_empty=True)
path = Path(r"{mesh_file.resolve()}")
fmt = "{fmt}"

if fmt == "glb":
    bpy.ops.import_scene.gltf(filepath=str(path))
elif fmt == "obj":
    bpy.ops.wm.obj_import(filepath=str(path))
elif fmt == "stl":
    bpy.ops.wm.stl_export # load check
    bpy.ops.wm.stl_import(filepath=str(path)) if hasattr(bpy.ops.wm, "stl_import") else bpy.ops.import_mesh.stl(filepath=str(path))
elif fmt == "fbx":
    bpy.ops.import_scene.fbx(filepath=str(path))

meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
total_verts = sum(len(m.data.vertices) for m in meshes)
total_polys = sum(len(m.data.polygons) for m in meshes)
print(f"VERIFY_STATS: meshes={{len(meshes)}} verts={{total_verts}} polys={{total_polys}}")
'''
    script_path.write_text(script_content, encoding="utf-8")

    res = subprocess.run(
        [str(BLENDER_EXE), "-b", "-P", str(script_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    stats = {"meshes": 0, "verts": 0, "polys": 0}
    for line in res.stdout.splitlines():
        if "VERIFY_STATS:" in line:
            parts = line.split("VERIFY_STATS:")[1].strip().split()
            for p in parts:
                k, v = p.split("=")
                stats[k] = int(v)
            break
    return stats


def test_hi3dgen_space(token: str | None, label: str) -> tuple[bool, Path | None, str]:
    """Test calling Stable-X/Hi3DGen with the specified token."""
    from gradio_client import Client, handle_file

    print(f"\n--- Testing Candidate: {label} ---")
    t0 = time.time()

    try:
        print("[1/3] Connecting to Gradio Space 'Stable-X/Hi3DGen'...")
        client = Client("Stable-X/Hi3DGen", token=token, httpx_kwargs={"timeout": 300.0})
        print(f"      Connected successfully in {time.time() - t0:.2f}s.")

        print(f"[2/3] Calling endpoint '/generate_3d' with {IMAGE_PATH.name}...")
        print("      Parameters: seed=0, ss_guidance=3.0, ss_steps=25, slat_guidance=3.0, slat_steps=6")
        gen_t0 = time.time()

        result = client.predict(
            image=handle_file(str(IMAGE_PATH)),
            seed=0,
            ss_guidance_strength=3.0,
            ss_sampling_steps=25,
            slat_guidance_strength=3.0,
            slat_sampling_steps=6,
            api_name="/generate_3d",
        )
        gen_dt = time.time() - gen_t0
        print(f"[3/3] Inference finished in {gen_dt:.2f}s!")
        print(f"      Result structure: {type(result)} length={len(result) if isinstance(result, (list, tuple)) else 'N/A'}")

        # Result is (examples, normal_bridge, 3d_model_preview, export_mesh)
        glb_path = None
        if isinstance(result, (list, tuple)) and len(result) >= 4:
            # Check export_mesh (index 3) or 3d_model_preview (index 2)
            for idx in [3, 2]:
                cand = result[idx]
                if cand and isinstance(cand, str) and Path(cand).is_file():
                    glb_path = Path(cand)
                    break
                elif cand and isinstance(cand, dict) and "path" in cand and Path(cand["path"]).is_file():
                    glb_path = Path(cand["path"])
                    break

            # Check if normal_image is returned
            normal_info = result[1]
            if normal_info:
                normal_path = None
                if isinstance(normal_info, str) and Path(normal_info).is_file():
                    normal_path = Path(normal_info)
                elif isinstance(normal_info, dict) and "path" in normal_info and Path(normal_info["path"]).is_file():
                    normal_path = Path(normal_info["path"])
                if normal_path:
                    dest_normal = EXPORTS_DIR / "normal.png"
                    shutil.copy2(normal_path, dest_normal)
                    print(f"      Saved normal bridge map to {dest_normal.name} ({dest_normal.stat().st_size:,} bytes)")

        if not glb_path or not glb_path.is_file():
            return False, None, f"No valid GLB returned in output: {result}"

        dest_glb = EXPORTS_DIR / "model.glb"
        shutil.copy2(glb_path, dest_glb)
        print(f"      Copied GLB to {dest_glb} ({dest_glb.stat().st_size:,} bytes)")
        return True, dest_glb, f"Success in {gen_dt:.2f}s"

    except Exception as exc:
        err = str(exc)
        print(f"      [ERROR] {err}")
        return False, None, err


def main():
    print("=" * 80)
    print("Hi3DGen Integration Verifier: Space 'Stable-X/Hi3DGen'")
    print("=" * 80)
    print(f"Input image: {IMAGE_PATH} (exists={IMAGE_PATH.is_file()})")
    print(f"Blender 5.2 LTS: {BLENDER_EXE} (exists={BLENDER_EXE.is_file()})")

    tokens = load_token_pool()
    candidates: list[tuple[str | None, str]] = []
    for i, tok in enumerate(tokens):
        masked = f"{tok[:6]}...{tok[-4:]}" if len(tok) > 10 else "***"
        candidates.append((tok, f"Configured HF Token #{i+1} ({masked})"))
    candidates.append((None, "Public Community Pool (Anonymous / token=None)"))

    live_success = False
    active_glb: Path | None = None
    results_summary = []

    for tok, label in candidates:
        ok, glb, msg = test_hi3dgen_space(tok, label)
        results_summary.append((label, ok, msg))
        if ok and glb:
            live_success = True
            active_glb = glb
            break

    print("\n" + "=" * 80)
    print("Live API Test Summary:")
    for lbl, ok, msg in results_summary:
        status_str = "[SUCCESS]" if ok else "[QUOTA/ERROR]"
        print(f"  {status_str} {lbl}: {msg}")
    print("=" * 80)

    # Conversion & Topology Verification
    target_glb = active_glb
    if not target_glb or not target_glb.is_file():
        print("\n[NOTE] Live generation hit ZeroGPU quota/queue limits. Falling back to sample GLB for Blender verification...")
        target_glb = SAMPLE_GLB
        # Copy to exports dir
        shutil.copy2(target_glb, EXPORTS_DIR / "model.glb")
        target_glb = EXPORTS_DIR / "model.glb"

    print(f"\n--- Blender 5.2 LTS Export & Conversion Pipeline ({target_glb.name}) ---")
    conv_results = run_blender_conversion(target_glb, EXPORTS_DIR, ["obj", "stl", "fbx"])
    conv_results["glb"] = target_glb

    print("\n--- Mesh Topology Inspection Across Deliverables ---")
    topology_table = []
    for fmt, path in conv_results.items():
        size_bytes = path.stat().st_size
        stats = verify_mesh_topology(path, fmt)
        topology_table.append((fmt.upper(), path.name, size_bytes, stats.get("verts", 0), stats.get("polys", 0)))

    print(f"{'FORMAT':<8} | {'FILENAME':<16} | {'SIZE (BYTES)':<14} | {'VERTICES':<10} | {'POLYGONS':<10}")
    print("-" * 65)
    for fmt, fname, size_b, v, p in topology_table:
        print(f"{fmt:<8} | {fname:<16} | {size_b:<14,} | {v:<10,} | {p:<10,}")
    print("-" * 65)

    print("\n" + "=" * 80)
    print(f"Hi3DGen Verification Complete. Live Success: {live_success}")
    print("=" * 80)


if __name__ == "__main__":
    main()

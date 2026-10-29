"""Omni-3D Synthesis Engine for Project #2.

Reusable, production-grade engine that transforms 2D reference images into
fully realized 3D models using Vision LLMs (LL3M methodology) and Blender 5.2 LTS,
exporting into GLB, OBJ, STL, and FBX formats.
"""

from __future__ import annotations

import ast
import base64
import datetime
import io
import json
import mimetypes
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Generator

PROJECT_DIR = Path(__file__).resolve().parent
ROOT_DIR = PROJECT_DIR.parent
DEFAULT_BLENDER = Path(r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")


def find_blender() -> Path:
    """Detect local Blender executable, prioritizing Blender 5.2 LTS."""
    if DEFAULT_BLENDER.is_file():
        return DEFAULT_BLENDER
    # Check PATH
    import shutil
    p = shutil.which("blender")
    if p:
        return Path(p)
    # Check default install locations on Windows
    program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Blender Foundation"
    if program_files.is_dir():
        for sub in sorted(program_files.iterdir(), reverse=True):
            candidate = sub / "blender.exe"
            if candidate.is_file():
                return candidate
    return DEFAULT_BLENDER


def encode_image(image_path: Path, max_dim: int = 448) -> tuple[str, str]:
    """Encode and thumbnail image to base64 for optimal vision token latency."""
    mime, _ = mimetypes.guess_type(str(image_path))
    if not mime:
        mime = "image/png"
    try:
        from PIL import Image
        img = Image.open(image_path)
        if max(img.size) > max_dim:
            img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            img.save(buf, format="PNG", optimize=True)
            mime = "image/png"
        else:
            img.convert("RGB").save(buf, format="JPEG", quality=88, optimize=True)
            mime = "image/jpeg"
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        return b64, mime
    except Exception:
        b64 = base64.b64encode(image_path.read_bytes()).decode("utf-8")
        return b64, mime


def is_valid_python_syntax(code: str) -> bool:
    """Check if code snippet is syntactically valid Python without crashing."""
    if not code or not code.strip():
        return False
    try:
        ast.parse(code)
        return True
    except (SyntaxError, ValueError):
        return False


def extract_blender_script(llm_output: str) -> str:
    """Robustly extract the primary, complete Blender Python script from LLM output.

    Handles:
    - Multiple code blocks (filters and picks the complete script containing 'import bpy' and exporters)
    - Unclosed code blocks (where LLM hit token budget or stream finished before closing ```)
    - Direct python scripts without markdown fences, anchored by line-level imports
    - Eliminates reasoning monologues, commentary, or text mistakenly matching substrings
    """
    if not llm_output or not llm_output.strip():
        return ""

    # 1. Find all closed markdown code blocks
    code_blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", llm_output, re.DOTALL)
    if code_blocks:
        bpy_blocks = [b.strip() for b in code_blocks if re.search(r'(?m)^[ \t]*import bpy\b', b) or "bpy." in b]
        if bpy_blocks:
            # Prefer blocks that are syntactically valid and contain import bpy
            full_scripts = [b for b in bpy_blocks if "import bpy" in b]
            if full_scripts:
                valid = [b for b in full_scripts if is_valid_python_syntax(b)]
                if valid:
                    return max(valid, key=len)
                return max(full_scripts, key=len)
            valid = [b for b in bpy_blocks if is_valid_python_syntax(b)]
            if valid:
                return max(valid, key=len)
            return max(bpy_blocks, key=len)
        return max(code_blocks, key=len).strip()

    # 2. Check for unclosed code block (e.g. ```python ... EOF)
    unclosed = re.search(r"```(?:python|py)?\s*\n(.*)$", llm_output, re.DOTALL)
    if unclosed:
        code = unclosed.group(1).strip()
        if re.search(r'(?m)^[ \t]*import bpy\b', code) or "bpy." in code:
            return code

    # 3. Fallback: line-anchored search for '^import bpy' or '^from ... import bpy'
    m_import = re.search(r'(?m)^[ \t]*(?:import bpy\b|from [^\n]+ import [^\n]*bpy)', llm_output)
    if m_import:
        candidate = llm_output[m_import.start():].strip()
        lines = candidate.splitlines()
        code_lines = []
        for line in lines:
            # Stop if markdown heading or conversational closing appears after code
            if len(code_lines) > 20 and re.match(r'^(?:#{1,3}\s|Explanation:|Summary:|Notes:|I hope |Let me know|This script )', line.strip()):
                break
            code_lines.append(line)
        cleaned = "\n".join(code_lines).strip()
        if is_valid_python_syntax(cleaned) or "bpy.ops" in cleaned:
            return cleaned

    return ""


# Verified High-Fidelity 3D Sculpting & PBR Helper Suite
HELPER_DEFINITIONS = {
    "hex_to_linear": '''def hex_to_linear(hex_str):
    hex_str = hex_str.lstrip('#')
    r, g, b = (int(hex_str[i:i+2], 16) / 255.0 for i in (0, 2, 4))
    def s(c): return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return (s(r), s(g), s(b), 1.0)
''',
    "init_clean_scene": '''def init_clean_scene():
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for _ in range(3):
        bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
''',
    "make_organic_pbr_material": '''def make_organic_pbr_material(name, base_hex, roughness=0.35, metallic=0.0, sss_weight=0.25, sss_radius=(1.0, 0.4, 0.2), rim_hex=None, rim_strength=1.5, rim_blend=0.3):
    if isinstance(sss_weight, str) and sss_weight.startswith('#'):
        rim_hex = sss_weight
        rim_strength = sss_radius if isinstance(sss_radius, (int, float)) else 1.5
        sss_weight = metallic if isinstance(metallic, (int, float)) else 0.25
        metallic = 0.0
    elif isinstance(metallic, str) and metallic.startswith('#'):
        rim_hex = metallic
        metallic = 0.0
    roughness = float(roughness) if isinstance(roughness, (int, float)) else 0.35
    metallic = float(metallic) if isinstance(metallic, (int, float)) else 0.0
    sss_weight = float(sss_weight) if isinstance(sss_weight, (int, float)) else 0.25
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    output = nodes.get("Material Output")
    bsdf.inputs["Base Color"].default_value = hex_to_linear(base_hex)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    for sub_k in ("Subsurface Weight", "Subsurface"):
        if sub_k in bsdf.inputs:
            bsdf.inputs[sub_k].default_value = sss_weight
            break
    if "Subsurface Radius" in bsdf.inputs and isinstance(sss_radius, (tuple, list)):
        bsdf.inputs["Subsurface Radius"].default_value = sss_radius
    if rim_hex and rim_strength > 0:
        lw = nodes.new("ShaderNodeLayerWeight")
        lw.inputs["Blend"].default_value = rim_blend
        emit = nodes.new("ShaderNodeEmission")
        emit.inputs["Color"].default_value = hex_to_linear(rim_hex)
        mult = nodes.new("ShaderNodeMath")
        mult.operation = 'MULTIPLY'
        mult.inputs[1].default_value = rim_strength
        links.new(lw.outputs["Facing"], mult.inputs[0])
        links.new(mult.outputs["Value"], emit.inputs["Strength"])
        add = nodes.new("ShaderNodeAddShader")
        links.new(bsdf.outputs["BSDF"], add.inputs[0])
        links.new(emit.outputs["Emission"], add.inputs[1])
        links.new(add.outputs["Shader"], output.inputs["Surface"])
    return mat
''',
    "create_swept_spline_mesh": '''def create_swept_spline_mesh(name, control_points, radii, bevel_depth=0.20, bevel_res=6):
    curve_data = bpy.data.curves.new(f"{name}_Curve", type='CURVE')
    curve_data.dimensions = '3D'
    curve_data.bevel_depth = bevel_depth
    curve_data.bevel_resolution = bevel_res
    curve_data.use_fill_caps = True
    spline = curve_data.splines.new('BEZIER')
    spline.bezier_points.add(len(control_points) - 1)
    for i, (pt, r) in enumerate(zip(control_points, radii)):
        bp = spline.bezier_points[i]
        bp.co = Vector(pt) if not isinstance(pt, Vector) else pt
        # Clamp minimum radius to prevent OpenVDB sub-voxel fragmentation (floating dust)
        bp.radius = max(0.18, float(r))
        bp.handle_left_type = 'AUTO'
        bp.handle_right_type = 'AUTO'
    obj = bpy.data.objects.new(name, curve_data)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.convert(target='MESH')
    return obj
''',
    "fuse_objects_voxel_remesh": '''def fuse_objects_voxel_remesh(objects, active_obj, voxel_size=0.030, smooth_factor=0.55, smooth_iters=2):
    voxel_size = max(0.02, min(0.1, voxel_size))
    bpy.ops.object.select_all(action='DESELECT')
    for o in objects:
        if o and hasattr(o, "name") and o.name in bpy.data.objects:
            o.select_set(True)
    active_obj.select_set(True)
    bpy.context.view_layer.objects.active = active_obj
    bpy.ops.object.join()
    active_obj.data.remesh_voxel_size = voxel_size
    bpy.ops.object.voxel_remesh()
    if smooth_factor > 0 and smooth_iters > 0:
        sm = active_obj.modifiers.new("RemeshSmooth", 'SMOOTH')
        sm.factor = smooth_factor
        sm.iterations = smooth_iters
        bpy.ops.object.modifier_apply(modifier=sm.name)
    bpy.ops.object.shade_smooth()
    return active_obj
''',
    "safe_remove_object": '''def safe_remove_object(obj, *args, **kwargs):
    try:
        if obj and hasattr(obj, 'name') and obj.name in bpy.data.objects:
            bpy.data.objects.remove(obj, do_unlink=True)
    except Exception:
        pass
''',
    "carve_boolean_recess": '''def carve_boolean_recess(target_obj, cutter_obj, solver='EXACT'):
    if not target_obj or not cutter_obj: return
    bpy.context.view_layer.objects.active = target_obj
    mod = target_obj.modifiers.new(f"Carve_{cutter_obj.name}", 'BOOLEAN')
    mod.operation = 'DIFFERENCE'
    mod.solver = solver
    mod.object = cutter_obj
    bpy.ops.object.modifier_apply(modifier=mod.name)
    safe_remove_object(cutter_obj)
''',
    "apply_procedural_relief": '''def apply_procedural_relief(target_obj, tex_type='CLOUDS', noise_scale=0.20, strength=0.015, mid_level=0.5):
    if not target_obj: return
    tex = bpy.data.textures.new(f"{target_obj.name}_ReliefTex", type=tex_type)
    tex.noise_scale = noise_scale
    if tex_type == 'VORONOI':
        tex.distance_metric = 'DISTANCE'
    elif tex_type == 'CLOUDS':
        tex.noise_depth = 2
    disp = target_obj.modifiers.new("MicroRelief", 'DISPLACE')
    disp.texture = tex
    disp.strength = strength
    disp.mid_level = mid_level
    bpy.context.view_layer.objects.active = target_obj
    bpy.ops.object.modifier_apply(modifier=disp.name)
''',
    "add_nested_eye": '''def add_nested_eye(name, loc, radius, iris_mat, pupil_mat=None, hi_mat=None, fwd=(0, -1, 0)):
    parts = []
    fwd_vec = Vector(fwd).normalized()
    up_vec = Vector((0, 0, 1))
    right_vec = fwd_vec.cross(up_vec).normalized()
    if right_vec.length < 0.1:
        right_vec = Vector((1, 0, 0))

    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=16, radius=radius, location=loc)
    iris = bpy.context.active_object
    iris.name = f"{name}_Iris"
    # Flatten depth-wise along character forward gaze axis (-Y)
    iris.scale = (1.0, 0.45, 1.0)
    bpy.ops.object.transform_apply(scale=True)
    bpy.ops.object.shade_smooth()
    if iris_mat: iris.data.materials.append(iris_mat)
    parts.append(iris)

    if pupil_mat:
        p_loc = Vector(loc) + fwd_vec * (radius * 0.15)
        bpy.ops.mesh.primitive_uv_sphere_add(segments=20, ring_count=12, radius=radius * 0.55, location=p_loc)
        pupil = bpy.context.active_object
        pupil.name = f"{name}_Pupil"
        pupil.scale = (1.0, 0.35, 1.0)
        bpy.ops.object.transform_apply(scale=True)
        bpy.ops.object.shade_smooth()
        pupil.data.materials.append(pupil_mat)
        parts.append(pupil)

    if hi_mat:
        h_loc = Vector(loc) + fwd_vec * (radius * 0.28) + right_vec * (radius * 0.25) + up_vec * (radius * 0.28)
        bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8, radius=radius * 0.22, location=h_loc)
        hi = bpy.context.active_object
        hi.name = f"{name}_Highlight"
        bpy.ops.object.shade_smooth()
        hi.data.materials.append(hi_mat)
        parts.append(hi)
    return parts
''',
    "export_scene_models": '''def export_scene_models(exports_dir, base_name="model"):
    exports_dir = Path(exports_dir)
    exports_dir.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action='DESELECT')
    for obj in [o for o in bpy.data.objects if o.type == 'MESH']:
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        for mod in list(obj.modifiers):
            try:
                bpy.ops.object.modifier_apply(modifier=mod.name)
            except Exception:
                obj.modifiers.remove(mod)
        bpy.ops.object.select_all(action='DESELECT')
    # Explicitly select all mesh objects before calling exporters to avoid selection-state dependencies
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.export_scene.gltf(filepath=str(exports_dir / f"{base_name}.glb"), export_format='GLB', export_apply=True)
    bpy.ops.wm.obj_export(filepath=str(exports_dir / f"{base_name}.obj"))
    bpy.ops.wm.stl_export(filepath=str(exports_dir / f"{base_name}.stl"))
    bpy.ops.export_scene.fbx(filepath=str(exports_dir / f"{base_name}.fbx"))
    print("MODEL_BUILD_OK")
''',
}


def sanitize_blender_script(script: str) -> str:
    """Pre-execution auto-fixer for known Blender API hallucinations and helper injections."""
    # 1. Fix parent_set with invalid KEEP_TRANSFORM enum
    script = re.sub(
        r"bpy\.ops\.object\.parent_set\(\s*type\s*=\s*['\"]OBJECT_KEEP_TRANSFORM['\"]\s*\)",
        "bpy.ops.object.parent_set(type='OBJECT', keep_transform=True)",
        script
    )
    script = re.sub(
        r"bpy\.ops\.object\.parent_set\(\s*type\s*=\s*['\"]KEEP_TRANSFORM['\"]\s*\)",
        "bpy.ops.object.parent_set(type='OBJECT', keep_transform=True)",
        script
    )

    # 2. Fix use_auto_smooth (removed in Blender 4.0+/5.0+)
    script = re.sub(r'[\w\.]+\.use_auto_smooth\s*=\s*\w+', '# use_auto_smooth deprecated in Blender 5.x', script)

    # 3. Fix legacy OBJ/STL exporter calls if any
    script = re.sub(
        r"bpy\.ops\.export_scene\.obj\(\s*filepath\s*=\s*([^,\)]+)[^\)]*\)",
        r"bpy.ops.wm.obj_export(filepath=\1)",
        script
    )
    script = re.sub(
        r"bpy\.ops\.export_mesh\.stl\(\s*filepath\s*=\s*([^,\)]+)[^\)]*\)",
        r"bpy.ops.wm.stl_export(filepath=\1)",
        script
    )

    # 4. Fix .to_track_quat(...).to_quaternion() hallucination (Vector.to_track_quat already returns Quaternion)
    script = re.sub(r"\.to_track_quat\(([^\)]+)\)\.to_quaternion\(\)", r".to_track_quat(\1)", script)

    # 5. Fix invalid ## placeholder syntax (e.g. primitive_##op##_)
    script = re.sub(r'bpy\.ops\.mesh\.primitive_##[^#\n]+##_[^\n]*', 'pass', script)

    # 6. Fix obsolete BLENDER_EEVEE_NEXT engine name (renamed to BLENDER_EEVEE in modern Blender)
    script = script.replace("'BLENDER_EEVEE_NEXT'", "'BLENDER_EEVEE'").replace('"BLENDER_EEVEE_NEXT"', '"BLENDER_EEVEE"')

    # 7. Safe guard materials.append when None is passed
    script = re.sub(r'([a-zA-Z0-9_\.]+)\.materials\.append\(([^\)]+)\)', r'if \2 is not None: \1.materials.append(\2)', script)

    # 8. Safe guard voxel remesh size (prevent OOM freezes if < 0.02)
    def clamp_voxel(m):
        val = float(m.group(1))
        if val < 0.02:
            return "remesh_voxel_size = 0.025"
        return m.group(0)
    script = re.sub(r"remesh_voxel_size\s*=\s*([0-9\.]+)", clamp_voxel, script)

    # Safe guard direct object removal calls against already deleted StructRNA
    script = re.sub(r"bpy\.data\.objects\.remove\(", "safe_remove_object(", script)

    # 9. Strip any stray markdown headers, English prose bullets, or em-dashes at the top
    clean_lines = []
    found_code = False
    for line in script.splitlines():
        if not found_code:
            stripped = line.strip()
            # If line is conversational English or markdown commentary, skip it
            if stripped.startswith(('Also ', 'Note: ', 'The error: ', 'Fix: ', 'Here is ', '# ---', '```')):
                continue
            if stripped.startswith(('import ', 'from ', 'def ', 'class ', '#', 'exports_dir', 'init_clean_scene')):
                found_code = True
        if found_code:
            clean_lines.append(line)
    if clean_lines:
        script = "\n".join(clean_lines)

    # 10. Strip any buggy/fragile LLM re-definitions of standard verified helpers so verified implementations take precedence
    for fn_name in HELPER_DEFINITIONS:
        pattern = r'def\s+' + fn_name + r'\s*\([^)]*\):(?:\n(?:[ \t]+.*|[ \t]*))*'
        script = re.sub(pattern, '', script)

    # Iteratively inject any used high-level helper functions and their dependencies
    changed = True
    injected_any = False
    while changed:
        changed = False
        for fn_name, fn_def in HELPER_DEFINITIONS.items():
            if fn_name in script and f"def {fn_name}" not in script:
                script = fn_def + "\n" + script
                changed = True
                injected_any = True

    if injected_any:
        script = "# Auto-Injected Verified SOTA 3D Sculpting & PBR Helpers\n" + script

    # 6. Ensure fundamental imports
    if "import bpy" not in script:
        script = "import bpy\nimport math\nfrom pathlib import Path\nfrom mathutils import Vector, Euler, Matrix\n" + script
    else:
        prefix_imports = []
        if "from pathlib import Path" not in script and "Path(" in script:
            prefix_imports.append("from pathlib import Path")
        if "from mathutils import" not in script and any(k in script for k in ("Vector(", "Euler(", "Matrix(")):
            prefix_imports.append("from mathutils import Vector, Euler, Matrix")
        if prefix_imports:
            script = "\n".join(prefix_imports) + "\n" + script

    return script


def inject_exports_dir(python_script: str, exports_dir: Path) -> str:
    """Safely inject or overwrite exports_dir in the generated script with posix path."""
    exports_posix = exports_dir.resolve().as_posix()
    target_statement = f'exports_dir = Path("{exports_posix}")'

    pattern = r'exports_dir\s*=\s*Path\(__file__\)\.resolve\(\)\.parent\s*/\s*["\']exports["\']'
    if re.search(pattern, python_script):
        python_script = re.sub(pattern, lambda _: target_statement, python_script, count=1)
    elif re.search(r'exports_dir\s*=\s*Path\([^\)]+\)', python_script):
        python_script = re.sub(r'exports_dir\s*=\s*Path\([^\)]+\)', lambda _: target_statement, python_script, count=1)
    else:
        python_script = f'from pathlib import Path\n{target_statement}\nexports_dir.mkdir(parents=True, exist_ok=True)\n' + python_script

    return python_script


def build_silhouette_inflation_script(
    image_path: Path,
    exports_dir: Path,
    formats: list[str],
    cushion_thickness: float = 0.38,
    grid_res: int = 86,
    user_guidance: str = "",
) -> str:
    """Generate high-speed Teddy silhouette inflation and exact UV texture projection script."""
    img_posix = image_path.resolve().as_posix()
    exp_posix = exports_dir.resolve().as_posix()
    formats_json = json.dumps(formats)

    return f'''"""Auto-Generated Teddy Silhouette Inflation & Exact UV Projection Script."""
import time
import json
from pathlib import Path
import bpy
import bmesh
import numpy as np

def init_clean_scene():
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for _ in range(3):
        bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)

def filter_islands(mask, min_size=35):
    h, w = mask.shape
    visited = np.zeros((h, w), dtype=bool)
    cleaned = np.zeros((h, w), dtype=bool)
    for y in range(h):
        for x in range(w):
            if mask[y, x] and not visited[y, x]:
                island = []
                queue = [(x, y)]
                visited[y, x] = True
                while queue:
                    cx, cy = queue.pop(0)
                    island.append((cx, cy))
                    for dx, dy in ((-1,0), (1,0), (0,-1), (0,1)):
                        nx, ny = cx + dx, cy + dy
                        if 0 <= nx < w and 0 <= ny < h and mask[ny, nx] and not visited[ny, nx]:
                            visited[ny, nx] = True
                            queue.append((nx, ny))
                if len(island) >= min_size:
                    for ix, iy in island:
                        cleaned[iy, ix] = True
    return cleaned

def fast_chamfer_edt(mask):
    h, w = mask.shape
    INF = float(h + w)
    dist = np.where(mask, INF, 0.0).astype(np.float32)
    for y in range(h):
        for x in range(w):
            if mask[y, x]:
                val = dist[y, x]
                if y > 0: val = min(val, dist[y - 1, x] + 1.0)
                if x > 0: val = min(val, dist[y, x - 1] + 1.0)
                if y > 0 and x > 0: val = min(val, dist[y - 1, x - 1] + 1.414)
                if y > 0 and x < w - 1: val = min(val, dist[y - 1, x + 1] + 1.414)
                dist[y, x] = val
    for y in range(h - 1, -1, -1):
        for x in range(w - 1, -1, -1):
            if mask[y, x]:
                val = dist[y, x]
                if y < h - 1: val = min(val, dist[y + 1, x] + 1.0)
                if x < w - 1: val = min(val, dist[y, x + 1] + 1.0)
                if y < h - 1 and x < w - 1: val = min(val, dist[y + 1, x + 1] + 1.414)
                if y < h - 1 and x > 0: val = min(val, dist[y + 1, x - 1] + 1.414)
                dist[y, x] = val
    return dist

def main():
    t0 = time.time()
    init_clean_scene()
    
    img_path = "{img_posix}"
    exports_dir = Path("{exp_posix}")
    exports_dir.mkdir(parents=True, exist_ok=True)
    formats = {formats_json}
    
    img = bpy.data.images.load(img_path)
    w_orig, h_orig = img.size
    pixels = np.array(img.pixels[:], dtype=np.float32).reshape((h_orig, w_orig, 4))
    
    grid_res = {grid_res}
    step_y = max(1, h_orig // grid_res)
    step_x = max(1, w_orig // grid_res)
    sub = pixels[::step_y, ::step_x, :]
    h, w, _ = sub.shape
    
    alpha = sub[:, :, 3]
    rgb = sub[:, :, :3]
    if np.any(alpha < 0.85):
        raw_mask = alpha > 0.15
    else:
        corners = np.vstack([rgb[:4, :4, :].reshape(-1, 3),
                             rgb[-4:, :4, :].reshape(-1, 3),
                             rgb[:4, -4:, :].reshape(-1, 3),
                             rgb[-4:, -4:, :].reshape(-1, 3)])
        bg = np.median(corners, axis=0)
        diff = np.linalg.norm(rgb - bg, axis=-1)
        raw_mask = diff > 0.15
        
    mask = filter_islands(raw_mask, min_size=35)
    if np.sum(mask) < 20:
        mask = raw_mask
    if np.sum(mask) < 20:
        mask = np.ones((h, w), dtype=bool)
        
    dist = fast_chamfer_edt(mask)
    max_d = max(1.0, float(dist.max()))
    norm_dist = np.clip(dist / max_d, 0.0, 1.0)
    cushion = {cushion_thickness}
    z_map = cushion * np.sin(norm_dist * (np.pi / 2.0))
    
    is_border = np.zeros_like(mask, dtype=bool)
    for y in range(h):
        for x in range(w):
            if mask[y, x]:
                if y == 0 or y == h - 1 or x == 0 or x == w - 1:
                    is_border[y, x] = True
                elif not (mask[y-1, x] and mask[y+1, x] and mask[y, x-1] and mask[y, x+1]):
                    is_border[y, x] = True
    z_map[is_border] = 0.0
    
    bm = bmesh.new()
    uv_layer = bm.loops.layers.uv.new("UVMap")
    aspect = w / h
    scale_x = aspect * 2.0
    scale_z = 2.0
    
    v_front, v_back = {{}}, {{}}
    for y in range(h):
        for x in range(w):
            if mask[y, x]:
                vx = (x / (w - 1) - 0.5) * scale_x
                vz = (y / (h - 1) - 0.5) * scale_z
                elev = float(z_map[y, x])
                if is_border[y, x]:
                    v_seam = bm.verts.new((vx, 0.0, vz))
                    v_front[(x, y)] = v_seam
                    v_back[(x, y)] = v_seam
                else:
                    v_front[(x, y)] = bm.verts.new((vx, -elev, vz))
                    v_back[(x, y)] = bm.verts.new((vx, +elev * 0.85, vz))
                    
    bm.verts.ensure_lookup_table()
    for y in range(h - 1):
        for x in range(w - 1):
            corners = [(x, y), (x + 1, y), (x + 1, y + 1), (x, y + 1)]
            if all(c in v_front for c in corners):
                verts_f = [v_front[c] for c in corners]
                if len(set(verts_f)) >= 3:
                    try:
                        ff = bm.faces.new(verts_f)
                        for loop in ff.loops:
                            u = (loop.vert.co.x / scale_x) + 0.5
                            v = (loop.vert.co.z / scale_z) + 0.5
                            loop[uv_layer].uv = (min(1.0, max(0.0, u)), min(1.0, max(0.0, v)))
                    except ValueError:
                        pass
                verts_b = [v_back[c] for c in reversed(corners)]
                if len(set(verts_b)) >= 3:
                    try:
                        fb = bm.faces.new(verts_b)
                        for loop in fb.loops:
                            u = 1.0 - ((loop.vert.co.x / scale_x) + 0.5)
                            v = (loop.vert.co.z / scale_z) + 0.5
                            loop[uv_layer].uv = (min(1.0, max(0.0, u)), min(1.0, max(0.0, v)))
                    except ValueError:
                        pass
                        
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=0.005)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    
    mesh = bpy.data.meshes.new("TeddyMesh")
    bm.to_mesh(mesh)
    bm.free()
    
    obj = bpy.data.objects.new("TeddyAsset", mesh)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    
    sm = obj.modifiers.new("Smooth", "SMOOTH")
    sm.factor = 0.5
    sm.iterations = 2
    bpy.ops.object.modifier_apply(modifier="Smooth")
    
    sub_mod = obj.modifiers.new("Subsurf", "SUBSURF")
    sub_mod.levels = 1
    bpy.ops.object.modifier_apply(modifier="Subsurf")
    bpy.ops.object.shade_smooth()
    
    mat = bpy.data.materials.new("FaithfulImagePBR")
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    tex_node = nodes.new("ShaderNodeTexImage")
    tex_node.image = img
    links.new(tex_node.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.35
    for sub_k in ("Subsurface Weight", "Subsurface"):
        if sub_k in bsdf.inputs:
            bsdf.inputs[sub_k].default_value = 0.20
            break
    obj.data.materials.append(mat)
    
    bpy.ops.object.select_all(action='SELECT')
    if "glb" in formats:
        bpy.ops.export_scene.gltf(filepath=str(exports_dir / "model.glb"), export_format='GLB', export_apply=True)
    if "obj" in formats:
        bpy.ops.wm.obj_export(filepath=str(exports_dir / "model.obj"))
    if "stl" in formats:
        bpy.ops.wm.stl_export(filepath=str(exports_dir / "model.stl"))
    if "fbx" in formats:
        bpy.ops.export_scene.fbx(filepath=str(exports_dir / "model.fbx"))
        
    print(f"SILHOUETTE_INFLATION_OK: Completed in {{time.time() - t0:.2f}}s")
    print("MODEL_BUILD_OK")

if __name__ == "__main__":
    main()
'''


def build_contour_relief_script(
    image_path: Path,
    exports_dir: Path,
    formats: list[str],
    relief_depth: float = 0.16,
    base_thickness: float = 0.08,
    grid_res: int = 86,
    user_guidance: str = "",
) -> str:
    """Generate high-resolution 2.5D contour relief and antique metallic PBR script."""
    img_posix = image_path.resolve().as_posix()
    exp_posix = exports_dir.resolve().as_posix()
    formats_json = json.dumps(formats)

    return f'''"""Auto-Generated SOTA 2.5D Contour Relief & Metallic PBR Script."""
import time
import json
from pathlib import Path
import bpy
import bmesh
import numpy as np

def init_clean_scene():
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for _ in range(3):
        bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)

def filter_islands(mask, min_size=35):
    h, w = mask.shape
    visited = np.zeros((h, w), dtype=bool)
    cleaned = np.zeros((h, w), dtype=bool)
    for y in range(h):
        for x in range(w):
            if mask[y, x] and not visited[y, x]:
                island = []
                queue = [(x, y)]
                visited[y, x] = True
                while queue:
                    cx, cy = queue.pop(0)
                    island.append((cx, cy))
                    for dx, dy in ((-1,0), (1,0), (0,-1), (0,1)):
                        nx, ny = cx + dx, cy + dy
                        if 0 <= nx < w and 0 <= ny < h and mask[ny, nx] and not visited[ny, nx]:
                            visited[ny, nx] = True
                            queue.append((nx, ny))
                if len(island) >= min_size:
                    for ix, iy in island:
                        cleaned[iy, ix] = True
    return cleaned

def main():
    t0 = time.time()
    init_clean_scene()
    
    img_path = "{img_posix}"
    exports_dir = Path("{exp_posix}")
    exports_dir.mkdir(parents=True, exist_ok=True)
    formats = {formats_json}
    
    img = bpy.data.images.load(img_path)
    w_orig, h_orig = img.size
    pixels = np.array(img.pixels[:], dtype=np.float32).reshape((h_orig, w_orig, 4))
    
    grid_res = {grid_res}
    step_y = max(1, h_orig // grid_res)
    step_x = max(1, w_orig // grid_res)
    sub = pixels[::step_y, ::step_x, :]
    h, w, _ = sub.shape
    
    alpha = sub[:, :, 3]
    rgb = sub[:, :, :3]
    gray = 0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]
    
    if np.any(alpha < 0.85):
        raw_mask = alpha > 0.15
    else:
        corners = np.vstack([rgb[:4, :4, :].reshape(-1, 3),
                             rgb[-4:, :4, :].reshape(-1, 3),
                             rgb[:4, -4:, :].reshape(-1, 3),
                             rgb[-4:, -4:, :].reshape(-1, 3)])
        bg = np.median(corners, axis=0)
        diff = np.linalg.norm(rgb - bg, axis=-1)
        raw_mask = diff > 0.15
        
    mask = filter_islands(raw_mask, min_size=35)
    if np.sum(mask) < 20:
        mask = raw_mask
    if np.sum(mask) < 20:
        mask = np.ones((h, w), dtype=bool)
        
    aspect = w / h
    scale_x = aspect * 2.0
    scale_z = 2.0
    relief_d = {relief_depth}
    base_t = {base_thickness}
    
    bm = bmesh.new()
    uv_layer = bm.loops.layers.uv.new("UVMap")
    
    v_top = {{}}
    v_bot = {{}}
    for y in range(h):
        for x in range(w):
            if mask[y, x]:
                vx = (x / (w - 1) - 0.5) * scale_x
                vz = (y / (h - 1) - 0.5) * scale_z
                z_rel = float(gray[y, x]) * relief_d
                v_top[(x, y)] = bm.verts.new((vx, -(base_t + z_rel), vz))
                v_bot[(x, y)] = bm.verts.new((vx, 0.0, vz))
                
    bm.verts.ensure_lookup_table()
    for y in range(h - 1):
        for x in range(w - 1):
            corners = [(x, y), (x + 1, y), (x + 1, y + 1), (x, y + 1)]
            if all(c in v_top for c in corners):
                ft = bm.faces.new([v_top[c] for c in corners])
                for loop in ft.loops:
                    u = (loop.vert.co.x / scale_x) + 0.5
                    v = (loop.vert.co.z / scale_z) + 0.5
                    loop[uv_layer].uv = (min(1.0, max(0.0, u)), min(1.0, max(0.0, v)))
                    
                fb = bm.faces.new([v_bot[c] for c in reversed(corners)])
                for loop in fb.loops:
                    u = 1.0 - ((loop.vert.co.x / scale_x) + 0.5)
                    v = (loop.vert.co.z / scale_z) + 0.5
                    loop[uv_layer].uv = (min(1.0, max(0.0, u)), min(1.0, max(0.0, v)))
                    
    top_verts = set(v_top.values())
    bot_map = {{v_top[k]: v_bot[k] for k in v_top}}
    boundary_edges = [e for e in bm.edges if e.verts[0] in top_verts and e.verts[1] in top_verts and len(e.link_faces) == 1]
    for edge in boundary_edges:
        v1, v2 = edge.verts
        f = edge.link_faces[0]
        v_idx = list(f.verts).index(v1)
        if f.verts[(v_idx + 1) % len(f.verts)] == v2:
            bm.faces.new([v2, v1, bot_map[v1], bot_map[v2]])
        else:
            bm.faces.new([v1, v2, bot_map[v2], bot_map[v1]])
            
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=0.005)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    
    mesh = bpy.data.meshes.new("ReliefMesh")
    bm.to_mesh(mesh)
    bm.free()
    
    obj = bpy.data.objects.new("ReliefAsset", mesh)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    
    bev = obj.modifiers.new("Bevel", "BEVEL")
    bev.width = 0.015
    bev.segments = 2
    bpy.ops.object.modifier_apply(modifier="Bevel")
    bpy.ops.object.shade_smooth()
    
    mat = bpy.data.materials.new("ReliefPBR")
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    tex_node = mat.node_tree.nodes.new("ShaderNodeTexImage")
    tex_node.image = img
    mat.node_tree.links.new(tex_node.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Metallic"].default_value = 0.70
    bsdf.inputs["Roughness"].default_value = 0.28
    obj.data.materials.append(mat)
    
    bpy.ops.object.select_all(action='SELECT')
    if "glb" in formats:
        bpy.ops.export_scene.gltf(filepath=str(exports_dir / "model.glb"), export_format='GLB', export_apply=True)
    if "obj" in formats:
        bpy.ops.wm.obj_export(filepath=str(exports_dir / "model.obj"))
    if "stl" in formats:
        bpy.ops.wm.stl_export(filepath=str(exports_dir / "model.stl"))
    if "fbx" in formats:
        bpy.ops.export_scene.fbx(filepath=str(exports_dir / "model.fbx"))
        
    print(f"CONTOUR_RELIEF_OK: Completed in {{time.time() - t0:.2f}}s")
    print("MODEL_BUILD_OK")

if __name__ == "__main__":
    main()
'''


class Omni3DEngine:
    """Core synthesis and orchestration engine for Image-to-3D generation."""

    def __init__(self, ollama_url: str = "http://localhost:11434"):
        self.ollama_url = ollama_url.rstrip("/")
        self.blender_exe = find_blender()

    def get_available_models(self) -> list[str]:
        """Fetch models installed in Ollama."""
        try:
            req = urllib.request.Request(f"{self.ollama_url}/api/tags")
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return [m.get("name") for m in data.get("models", [])]
        except Exception:
            return ["glm-5.3-flash:cloud", "kimi-k2.7-code:cloud", "gemma4:latest"]

    def analyze_image_guidance(self, image_path: Path, model: str = "glm-5.3-flash:cloud") -> str:
        """Auto-generate stylistic and anatomical 3D modeling guidance from reference image."""
        prompt = (
            "Analyze this reference image for a 3D technical artist and Blender modeler. "
            "Write a concise, 2-3 sentence stylistic and anatomical 3D modeling guidance note describing: "
            "1. Subject shape, silhouette, and proportions (e.g. chibi cartoon, hard-surface, realistic). "
            "2. Key anatomical and functional parts to model. "
            "3. PBR materials and colors (e.g. metallic, matte, glass transmission, emission). "
            "Keep it direct and actionable for procedural 3D modeling."
        )
        stream = self.stream_ollama_chat(prompt=prompt, image_path=image_path, model=model, timeout=120)
        try:
            while True:
                next(stream)
        except StopIteration as stop:
            return stop.value.strip()

    def build_ll3m_prompt(
        self,
        user_guidance: str = "",
        export_formats: list[str] | None = None,
        quality_preset: str = "sota_sculpt",
    ) -> str:
        """Construct the LL3M prompt enforcing clean Blender 5.2 procedural modeling and SOTA organic sculpting."""
        if not export_formats:
            export_formats = ["glb", "obj", "stl", "fbx"]

        formats_str = ", ".join(f.upper() for f in export_formats)

        if quality_preset == "sota_sculpt":
            geometric_architecture = f"""2. SOTA 5-STAGE COMPUTATIONAL SCULPTING (ORGANIC WATERTIGHT MESH):
   Do NOT generate disconnected balls or simple stacked cones! Follow this production pipeline:

   STAGE 1: FLUID SKELETAL SWEEPS & ANATOMICAL MASSES:
   - For flowing/swept features (flames, tails, hair locks, horns, tentacles, limbs):
     Use `create_swept_spline_mesh(name, control_points, radii, bevel_depth=0.20)`.
     The `radii` list controls tapering per point (e.g. [1.8, 1.4, 0.7, 0.05] for a tapered flame/tail).
   - For torso, skull, and head volumes: add scaled UV spheres or cylinders overlapping naturally.

   STAGE 2: OPENVDB VOXEL REMESH FUSION:
   - Fuse primary organic body masses and swept bases into a single continuous skin:
     `body = fuse_objects_voxel_remesh([part1, part2, ...], active_obj=body, voxel_size=0.030, smooth_factor=0.55, smooth_iters=2)`
   - This melts away all intersection seams and produces a seamless, watertight, organic manifold mesh!

   STAGE 3: SUBTRACTIVE BOOLEAN CARVING (ANATOMICAL RECESSES):
   - Carve eye orbital sockets, mouth cavities, and visor recesses into the remeshed body:
     `carve_boolean_recess(target_obj=body, cutter_obj=socket_cutter, solver='EXACT')`
   - Nest eyes recessed INSIDE the carved sockets using `add_nested_eye(name, loc, radius, iris_mat, pupil_mat, hi_mat)` or detailed geometry. Never stick eyes flat on top of the surface!

   STAGE 4: PROCEDURAL MICRO-DETAIL SURFACE RELIEF:
   - Apply subtle organic skin, cloth, or surface relief to eliminate flat plastic surfaces:
     `apply_procedural_relief(target_obj=body, tex_type='CLOUDS', noise_scale=0.20, strength=0.015)`

   STAGE 5: HIGH-FIDELITY PBR SHADING & MULTI-FORMAT EXPORTS:
   - Note on Materials: Objects joined into `body` via `fuse_objects_voxel_remesh` become ONE single unified body mesh datablock. Assign the primary body material directly: `body.data.materials.append(body_mat)`.
   - Any elements requiring distinct materials (nested eyes, pupils, highlights, floating embers, visors) must be created or parented AFTER voxel remeshing so their materials remain distinct.
   - Create multi-layer PBR materials:
     `mat = make_organic_pbr_material(name, base_hex="#FF6B1A", roughness=0.35, sss_weight=0.3, rim_hex="#FFAA33", rim_strength=2.0)`
   - Assign materials to parts, then call:
     `export_scene_models(exports_dir, base_name="model")`
   - Finish with: `print("MODEL_BUILD_OK")`"""
        else:
            geometric_architecture = f"""2. GEOMETRIC ARCHITECTURE (Factory-Based Decomposition):
   - Decompose into distinct functional parts parented or grouped cleanly.
   - Use small parameterized factory functions: add_sphere(), add_cube(), add_cylinder(), add_torus(), tube_between().
   - Apply scale (bpy.ops.object.transform_apply(scale=True)) on meshes before applying bevel modifiers.
   - Add Bevel modifiers with 3+ segments on hard edges for specular highlights.
   - For auto-smooth in Blender 4.0+/5.0+: use bmesh sharp-edge calculation or shade_smooth, avoiding obsolete use_auto_smooth.
   - For parenting: assign child.parent = root directly, or call bpy.ops.object.parent_set(type='OBJECT', keep_transform=True). Never use invalid 'OBJECT_KEEP_TRANSFORM'.

3. PBR MATERIALS (Principled BSDF):
   - Convert hex/sRGB colors to scene-linear before assigning to Base Color.
   - Set Roughness, Metallic, and Transmission appropriately.
   - For version-resilient BSDF inputs: use alias fallback ("Transmission Weight" / "Transmission", "Subsurface Weight" / "Subsurface").

4. MULTI-FORMAT EXPORT PROTOCOL:
   Resolve exports directory relative to script:
   exports_dir = Path(__file__).resolve().parent / "exports"
   exports_dir.mkdir(parents=True, exist_ok=True)
   Apply all modifiers before export so all formats share identical geometry.
   Execute required exporters:
   - GLB: bpy.ops.export_scene.gltf(filepath=str(exports_dir / "model.glb"), export_format="GLB", export_apply=True)
   - OBJ: bpy.ops.wm.obj_export(filepath=str(exports_dir / "model.obj"))
   - STL: bpy.ops.wm.stl_export(filepath=str(exports_dir / "model.stl"))
   - FBX: bpy.ops.export_scene.fbx(filepath=str(exports_dir / "model.fbx"))"""

        prompt = f"""You are an elite 3D technical artist, spatial geometrician, and Blender Python (bpy) specialist following the LL3M (Large Language 3D Modelers) methodology.

TASK:
Analyze the reference image and synthesize a complete, standalone, production-ready Blender Python script that procedurally builds this 3D model and exports it into target formats: {formats_str}.

ADDITIONAL USER GUIDANCE:
{user_guidance or "Faithfully reproduce the primary subject with accurate shapes, PBR colors, and smooth beveled geometry."}

ENGINEERING SPECIFICATION & BEST PRACTICES:
1. SCENE HYGIENE:
   - Call `init_clean_scene()` or purge existing objects recursively.
   - Ensure all coordinates are Z-up, character/asset centered at origin.

{geometric_architecture}

FINAL REQUIREMENTS (CRITICAL):
- Output EXACTLY ONE single Python code block enclosed in ```python ... ```.
- NOTE: The verified helper functions (`init_clean_scene`, `hex_to_linear`, `make_organic_pbr_material`, `create_swept_spline_mesh`, `fuse_objects_voxel_remesh`, `carve_boolean_recess`, `apply_procedural_relief`, `add_nested_eye`, `export_scene_models`) are ALREADY PRE-DEFINED and automatically provided in the environment. Do NOT write code defining them! Simply invoke them directly.
- Keep the script concise and direct: focus on anatomical coordinates, tapering radii, socket placements, and PBR color choices.
- Do NOT output any preliminary snippets, multiple code blocks, or markdown explanations.
- The script must end with export and `print("MODEL_BUILD_OK")`."""
        return prompt

    def stream_ollama_chat(
        self,
        prompt: str,
        image_path: Path | None = None,
        model: str = "glm-5.3-flash:cloud",
        timeout: int = 600,
    ) -> Generator[dict, None, str]:
        """Stream chat tokens from Ollama /api/chat yielding progress events."""
        url = f"{self.ollama_url}/api/chat"
        messages = [
            {
                "role": "system",
                "content": (
                    "You are an elite 3D technical artist, spatial geometrician, and Blender Python programmer.\n"
                    "CRITICAL: Keep internal reasoning extremely brief (under 80 words). "
                    "Immediately write and output the complete, self-contained, runnable Blender Python script wrapped in a single ```python ... ``` block. "
                    "Do NOT output markdown essays, monologues, or separate snippets."
                ),
            }
        ]

        if image_path and image_path.is_file():
            b64, _ = encode_image(image_path, max_dim=384)
            messages.append({"role": "user", "content": prompt, "images": [b64]})
        else:
            messages.append({"role": "user", "content": prompt})

        payload = json.dumps({
            "model": model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": 0.2,
                "num_ctx": 16384,
                "num_predict": 8192,
            },
        }).encode("utf-8")

        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        accumulated_content = []
        accumulated_thinking = []
        last_yield = time.time()

        with urllib.request.urlopen(req, timeout=timeout) as resp:
            for line in resp:
                s = line.decode("utf-8", errors="replace").strip()
                if not s:
                    continue
                try:
                    chunk = json.loads(s)
                    msg = chunk.get("message") or {}
                    c = msg.get("content") or ""
                    th = msg.get("thinking") or ""
                    if c:
                        accumulated_content.append(c)
                    if th:
                        accumulated_thinking.append(th)

                    now = time.time()
                    if now - last_yield > 0.5:
                        last_yield = now
                        yield {
                            "type": "token_chunk",
                            "thinking_chars": sum(len(x) for x in accumulated_thinking),
                            "content_chars": sum(len(x) for x in accumulated_content),
                            "latest_delta": c or (th[:40] if th else ""),
                        }

                    if chunk.get("done"):
                        break
                except json.JSONDecodeError:
                    pass

        content = "".join(accumulated_content)
        # Only fallback to thinking if it actually contains python code
        if not content.strip() and accumulated_thinking:
            joined_th = "".join(accumulated_thinking)
            if "import bpy" in joined_th:
                content = joined_th
        return content

    def execute_blender_script(self, script_path: Path) -> dict:
        """Run synthesized modeling script headlessly via Blender 5.2."""
        if not self.blender_exe.is_file():
            raise FileNotFoundError(f"Blender executable not found at: {self.blender_exe}")

        cmd = [str(self.blender_exe), "-b", "-P", str(script_path)]
        t0 = time.time()
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
        elapsed = round(time.time() - t0, 2)

        has_traceback = ("Traceback (most recent call last):" in res.stdout or "Error: Python:" in res.stdout)
        has_build_ok = ("MODEL_BUILD_OK" in res.stdout or "SPACEMAN_BUILD_OK" in res.stdout)
        is_success = (res.returncode == 0 and not has_traceback) or has_build_ok
        return {
            "success": is_success,
            "returncode": res.returncode,
            "output": res.stdout,
            "elapsed_sec": elapsed,
        }

    def generate_asset(
        self,
        image_path: Path,
        job_dir: Path,
        model: str = "glm-5.3-flash:cloud",
        guidance: str = "",
        formats: list[str] | None = None,
        quality_preset: str = "sota_sculpt",
        progress_cb: Callable[[dict], None] | None = None,
    ) -> dict:
        """Complete end-to-end Image-to-3D pipeline execution."""
        if not formats:
            formats = ["glb", "obj", "stl", "fbx"]

        job_dir.mkdir(parents=True, exist_ok=True)
        exports_dir = job_dir / "exports"
        exports_dir.mkdir(parents=True, exist_ok=True)

        print(f"[DEBUG omni_engine] generate_asset called with quality_preset: {quality_preset}")

        def report(stage: int, stage_name: str, message: str, meta: dict | None = None):
            if progress_cb:
                data = {"stage": stage, "stage_name": stage_name, "message": message, "timestamp": time.time()}
                if meta:
                    data.update(meta)
                progress_cb(data)

        # Stage 1 & 2: Route by Mesh Architecture Preset / Provider Engine
        actual_provider = quality_preset
        if quality_preset in ("tripo3d", "meshy", "trellis_hf", "modly_local", "triposr_local"):
            import providers
            report(1, "Perception", f"Dispatching image ({image_path.name}) to {quality_preset.upper()} engine...")
            script_file = job_dir / f"{quality_preset}_job.json"
            script_file.write_text(json.dumps({"provider": quality_preset, "image": str(image_path), "formats": formats}), encoding="utf-8")

            t_prov = time.time()
            try:
                if quality_preset == "tripo3d":
                    providers.generate_tripo3d_asset(image_path, exports_dir, formats, progress_cb=progress_cb)
                    actual_provider = "Tripo3D Cloud Neural Engine"
                elif quality_preset == "meshy":
                    providers.generate_meshy_asset(image_path, exports_dir, formats, progress_cb=progress_cb)
                    actual_provider = "Meshy.ai PBR Cloud Engine"
                elif quality_preset == "trellis_hf":
                    providers.generate_trellis_hf_asset(image_path, exports_dir, formats, progress_cb=progress_cb)
                    actual_provider = "Microsoft TRELLIS (Hugging Face ZeroGPU)"
                elif quality_preset == "modly_local":
                    providers.generate_modly_asset(image_path, exports_dir, formats, progress_cb=progress_cb)
                    actual_provider = "Modly Local AI Engine (GTX)"
                elif quality_preset == "triposr_local":
                    providers.generate_triposr_local_asset(image_path, exports_dir, formats, progress_cb=progress_cb)
                    actual_provider = "Local Offline TripoSR (GTX)"

                build_result = {
                    "success": True,
                    "output": f"{quality_preset.upper()} neural model generated successfully.",
                    "elapsed_sec": round(time.time() - t_prov, 2),
                }
            except Exception as prov_err:
                err_text = str(prov_err)
                report(3, "Provider Error", f"⚠️ {quality_preset.upper()} FAILED: {err_text}")
                report(3, "Self-Healing", "Notice: Activating Local Watertight Teddy Silhouette & UV Engine as safety preview...")
                fallback_script = build_silhouette_inflation_script(
                    image_path=image_path,
                    exports_dir=exports_dir,
                    formats=formats,
                    user_guidance=guidance,
                )
                fallback_file = job_dir / "generate_model_fallback.py"
                fallback_file.write_text(fallback_script, encoding="utf-8")
                build_result = self.execute_blender_script(fallback_file)
                (job_dir / "blender_build_fallback.log").write_text(build_result["output"], encoding="utf-8")
                actual_provider = f"Local Fallback ({quality_preset.upper()} Error: {err_text})"
        elif quality_preset == "silhouette_inflation":
            actual_provider = "SOTA Teddy Silhouette Inflation"
            report(1, "Perception", f"Extracting 2D silhouette contours from {image_path.name} (Teddy EDT Architecture)...")
            time.sleep(0.3)
            report(2, "Synthesis", "Synthesizing harmonic EDT distance transform mesh & frontal UV projection...")
            python_script = build_silhouette_inflation_script(
                image_path=image_path,
                exports_dir=exports_dir,
                formats=formats,
                user_guidance=guidance,
            )
            script_file = job_dir / "generate_model.py"
            script_file.write_text(python_script, encoding="utf-8")
            report(2, "Synthesis", "Watertight Teddy inflation script generated.")
        elif quality_preset == "contour_relief":
            report(1, "Perception", f"Analyzing image luminance and heightmap contours from {image_path.name}...")
            time.sleep(0.3)
            report(2, "Synthesis", "Synthesizing 2.5D displacement relief and antique metallic PBR...")
            python_script = build_contour_relief_script(
                image_path=image_path,
                exports_dir=exports_dir,
                formats=formats,
                user_guidance=guidance,
            )
            script_file = job_dir / "generate_model.py"
            script_file.write_text(python_script, encoding="utf-8")
            report(2, "Synthesis", "2.5D Contour relief script generated.")
        else:
            # Stage 1: Spatial Perception
            preset_name = "SOTA Organic Sculpt" if quality_preset == "sota_sculpt" else "Fast Procedural"
            report(1, "Perception", f"Analyzing reference image ({image_path.name}) with {model} [{preset_name}]...")
            prompt = self.build_ll3m_prompt(user_guidance=guidance, export_formats=formats, quality_preset=quality_preset)

            # Stage 2: Procedural Code Synthesis
            report(2, "Synthesis", f"Synthesizing Blender Python modeling code via {model}...")
            stream = self.stream_ollama_chat(prompt=prompt, image_path=image_path, model=model)
            try:
                while True:
                    chunk = next(stream)
                    co = chunk.get("content_chars", 0)
                    th = chunk.get("thinking_chars", 0)
                    if co > 0:
                        msg = f"Synthesizing Blender Python code ({co:,} chars)..."
                    elif th > 0:
                        msg = f"Reasoning 3D geometry & anatomy ({th:,} chars)..."
                    else:
                        msg = "Model initializing..."
                    report(2, "Synthesis", msg, chunk)
            except StopIteration as stop:
                synthesized_code = stop.value

            # Persist full raw LLM response for auditability & debugging
            (job_dir / "raw_llm_response.txt").write_text(synthesized_code, encoding="utf-8")

            # Robustly extract the full Blender Python script (handles multiple blocks & unclosed blocks)
            python_script = extract_blender_script(synthesized_code)

            # If the first attempt produced no code (e.g. reasoning hit token limit), automatically retry once with direct code prompt
            if not python_script or "import bpy" not in python_script:
                report(2, "Synthesis", "Reasoning completed without code. Retrying direct code synthesis...")
                retry_prompt = prompt + "\n\nCRITICAL INSTRUCTION: Output ONLY the complete runnable Python script starting with ```python\nimport bpy. Do not include chain-of-thought or markdown essays."
                stream = self.stream_ollama_chat(prompt=retry_prompt, image_path=image_path, model=model)
                try:
                    while True:
                        chunk = next(stream)
                        co = chunk.get("content_chars", 0)
                        if co > 0:
                            report(2, "Synthesis", f"Synthesizing Blender Python code ({co:,} chars)...", chunk)
                except StopIteration as stop:
                    synthesized_code = stop.value
                (job_dir / "raw_llm_response_retry.txt").write_text(synthesized_code, encoding="utf-8")
                python_script = extract_blender_script(synthesized_code)

            if not python_script or "import bpy" not in python_script:
                report(2, "Self-Healing", "LLM reasoning budget exceeded without code. Activating Watertight Teddy Silhouette Inflation & Exact UV Engine...")
                python_script = build_silhouette_inflation_script(
                    image_path=image_path,
                    exports_dir=exports_dir,
                    formats=formats,
                    user_guidance=guidance,
                )
                script_file = job_dir / "generate_model.py"
                script_file.write_text(python_script, encoding="utf-8")
                report(2, "Synthesis", "Watertight Teddy inflation script generated.")
            else:
                # Sanitize known Blender API hallucinations & inject target exports_dir
                python_script = sanitize_blender_script(python_script)
                python_script = inject_exports_dir(python_script, exports_dir)

                script_file = job_dir / "generate_model.py"
                script_file.write_text(python_script, encoding="utf-8")
                report(2, "Synthesis", "Procedural code synthesis complete.")

        # Stage 3: Headless Blender Compilation (only for procedural/script presets)
        if quality_preset not in ("tripo3d", "meshy", "trellis_hf", "modly_local", "triposr_local"):
            report(3, "Blender Compile", "Executing script headlessly in Blender 5.2 LTS...")
            build_result = self.execute_blender_script(script_file)
            (job_dir / "blender_build.log").write_text(build_result["output"], encoding="utf-8")

            # Self-Healing Retry Loop (Autonomous Harnessing)
            if not build_result["success"]:
                err_lines = [l for l in build_result["output"].splitlines() if "Error" in l or "Traceback" in l or "File " in l]
                summary = "\n".join(err_lines[-5:]) if err_lines else build_result["output"][-400:]
                report(3, "Self-Healing", f"Blender reported error:\n{summary}\nAutonomously repairing script...")

                repair_prompt = f"""The following Blender Python script produced an execution error in Blender 5.2 LTS:

ERROR:
{summary}

ORIGINAL SCRIPT:
```python
{python_script}
```

TASK:
Fix the error in the script. Ensure all syntax, operators, and imports are 100% valid for Blender 5.2 LTS.
CRITICAL: Do NOT output any reasoning, commentary, or text before or after the code. Output ONLY the complete runnable Python script starting with ```python\nimport bpy and ending with ```."""

                stream = self.stream_ollama_chat(prompt=repair_prompt, image_path=None, model=model)
                try:
                    while True:
                        next(stream)
                except StopIteration as stop:
                    repaired_code = stop.value

                (job_dir / "raw_llm_response_repair.txt").write_text(repaired_code, encoding="utf-8")
                repaired_script = extract_blender_script(repaired_code)
                if repaired_script and "import bpy" in repaired_script:
                    repaired_script = sanitize_blender_script(repaired_script)
                    repaired_script = inject_exports_dir(repaired_script, exports_dir)
                    script_file.write_text(repaired_script, encoding="utf-8")

                    report(3, "Blender Compile", "Re-executing repaired script in Blender 5.2 LTS...")
                    build_result = self.execute_blender_script(script_file)
                    (job_dir / "blender_build.log").write_text(build_result["output"], encoding="utf-8")

            # Safety Fallback Net: If custom LLM code failed or failed to export .glb,
            # autonomously fallback to the verified, deterministic Teddy Silhouette Inflation & Exact UV engine!
            has_glb = bool(list(exports_dir.glob("*.glb")))
            if not build_result["success"] or not has_glb:
                report(3, "Self-Healing", "Procedural assembly encountered topological/syntax limits. Activating Watertight Teddy Silhouette Inflation & Exact UV fallback...")
                fallback_script = build_silhouette_inflation_script(
                    image_path=image_path,
                    exports_dir=exports_dir,
                    formats=formats,
                    user_guidance=guidance,
                )
                fallback_file = job_dir / "generate_model_fallback.py"
                fallback_file.write_text(fallback_script, encoding="utf-8")
                build_result = self.execute_blender_script(fallback_file)
                (job_dir / "blender_build_fallback.log").write_text(build_result["output"], encoding="utf-8")

        # Stage 4: Deliverables Verification
        report(4, "Deliverables", "Verifying export files and metadata...")
        deliverables = {}
        for ext in formats:
            candidate = list(exports_dir.glob(f"*.{ext}"))
            if candidate:
                f = candidate[0]
                deliverables[ext] = {
                    "filename": f.name,
                    "path": str(f),
                    "size_bytes": f.stat().st_size,
                    "size_display": f"{round(f.stat().st_size / 1024, 1)} KB",
                }

        # Crucial gate: If no files were exported, the generation was NOT successful
        if not deliverables or ("glb" in formats and "glb" not in deliverables):
            err_msg = "Blender execution finished but failed to create export files (no .glb found in exports/)."
            report(4, "Failed", err_msg, {"log": build_result["output"][-1000:]})
            raise RuntimeError(err_msg)

        preview_img = exports_dir / "preview.png"
        preview_url = f"/files/jobs/{job_dir.name}/exports/{preview_img.name}" if preview_img.is_file() else None

        report(5, "Complete", f"Successfully generated 3D model with {len(deliverables)} formats. Engine: {actual_provider}", {
            "deliverables": deliverables,
            "preview_url": preview_url,
            "elapsed_sec": build_result["elapsed_sec"],
            "provider_used": actual_provider,
        })

        return {
            "job_id": job_dir.name,
            "script_file": str(script_file),
            "deliverables": deliverables,
            "preview_url": preview_url,
            "build_log": build_result["output"],
        }

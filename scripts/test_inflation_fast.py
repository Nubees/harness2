import sys
import time
from pathlib import Path
import bpy
import numpy as np
import bmesh

def clean_scene():
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for _ in range(3):
        bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)

def fast_chamfer_edt(mask):
    """Vectorized 2D Chamfer distance transform in pure numpy (0 external dependencies)."""
    h, w = mask.shape
    INF = float(h + w)
    dist = np.where(mask, INF, 0.0).astype(np.float32)
    
    # Forward pass: top-to-bottom, left-to-right
    for y in range(h):
        for x in range(w):
            if mask[y, x]:
                val = dist[y, x]
                if y > 0: val = min(val, dist[y - 1, x] + 1.0)
                if x > 0: val = min(val, dist[y, x - 1] + 1.0)
                if y > 0 and x > 0: val = min(val, dist[y - 1, x - 1] + 1.414)
                if y > 0 and x < w - 1: val = min(val, dist[y - 1, x + 1] + 1.414)
                dist[y, x] = val
                
    # Backward pass: bottom-to-top, right-to-left
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

def test_inflate(image_path: str, max_depth: float = 0.35, grid_res: int = 80):
    t0 = time.time()
    clean_scene()
    image_path = str(Path(image_path).resolve())
    img = bpy.data.images.load(image_path)
    w_orig, h_orig = img.size
    print(f"Loaded image {w_orig}x{h_orig} from {image_path}")
    
    # Extract RGBA pixels
    pixels = np.array(img.pixels[:], dtype=np.float32).reshape((h_orig, w_orig, 4))
    
    step_y = max(1, h_orig // grid_res)
    step_x = max(1, w_orig // grid_res)
    sub = pixels[::step_y, ::step_x, :]
    h, w, _ = sub.shape
    print(f"Subsampled to {w}x{h} in {time.time() - t0:.2f}s")
    
    alpha = sub[:, :, 3]
    rgb = sub[:, :, :3]
    if np.any(alpha < 0.85):
        mask = alpha > 0.15
    else:
        # Auto-detect background from 4 corners
        corners = np.vstack([rgb[:4, :4, :].reshape(-1, 3),
                             rgb[-4:, :4, :].reshape(-1, 3),
                             rgb[:4, -4:, :].reshape(-1, 3),
                             rgb[-4:, -4:, :].reshape(-1, 3)])
        bg = np.median(corners, axis=0)
        diff = np.linalg.norm(rgb - bg, axis=-1)
        mask = diff > 0.15
        
    print(f"Mask active cells: {np.sum(mask)} / {mask.size}")
    if np.sum(mask) < 20:
        mask = np.ones((h, w), dtype=bool)
        
    t_edt = time.time()
    dist = fast_chamfer_edt(mask)
    print(f"EDT completed in {time.time() - t_edt:.2f}s, max_dist = {dist.max():.2f}")
    
    max_d = max(1.0, float(dist.max()))
    norm_dist = np.clip(dist / max_d, 0.0, 1.0)
    # Smooth sine inflation curve
    z_map = max_depth * np.sin(norm_dist * (np.pi / 2.0))
    
    # Mark border pixels (pixels where any neighbor is outside mask)
    is_border = np.zeros_like(mask, dtype=bool)
    for y in range(h):
        for x in range(w):
            if mask[y, x]:
                if y == 0 or y == h - 1 or x == 0 or x == w - 1:
                    is_border[y, x] = True
                elif not (mask[y-1, x] and mask[y+1, x] and mask[y, x-1] and mask[y, x+1]):
                    is_border[y, x] = True
                    
    # Force border elevation to exactly zero
    z_map[is_border] = 0.0
    
    # Build BMesh
    bm = bmesh.new()
    uv_layer = bm.loops.layers.uv.new("UVMap")
    
    aspect = w / h
    scale_x = aspect * 2.0
    scale_z = 2.0
    
    v_front = {}
    v_back = {}
    
    for y in range(h):
        for x in range(w):
            if mask[y, x]:
                vx = (x / (w - 1) - 0.5) * scale_x
                vz = (y / (h - 1) - 0.5) * scale_z
                elev = float(z_map[y, x])
                
                if is_border[y, x]:
                    # Single welded seam vertex at Z = 0
                    v_seam = bm.verts.new((vx, 0.0, vz))
                    v_front[(x, y)] = v_seam
                    v_back[(x, y)] = v_seam
                else:
                    v_front[(x, y)] = bm.verts.new((vx, -elev, vz))
                    v_back[(x, y)] = bm.verts.new((vx, +elev * 0.85, vz))
                    
    bm.verts.ensure_lookup_table()
    
    # Add quad faces for front and back
    face_count = 0
    for y in range(h - 1):
        for x in range(w - 1):
            corners = [(x, y), (x + 1, y), (x + 1, y + 1), (x, y + 1)]
            if all(c in v_front for c in corners):
                # Front face
                verts_f = [v_front[c] for c in corners]
                # Avoid degenerate faces if all 4 are the same border vertex
                if len(set(verts_f)) >= 3:
                    try:
                        ff = bm.faces.new(verts_f)
                        for loop in ff.loops:
                            u = (loop.vert.co.x / scale_x) + 0.5
                            v = (loop.vert.co.z / scale_z) + 0.5
                            loop[uv_layer].uv = (min(1.0, max(0.0, u)), min(1.0, max(0.0, v)))
                        face_count += 1
                    except ValueError:
                        pass
                        
                # Back face (reversed winding)
                verts_b = [v_back[c] for c in reversed(corners)]
                if len(set(verts_b)) >= 3:
                    try:
                        fb = bm.faces.new(verts_b)
                        for loop in fb.loops:
                            # Mirrored U
                            u = 1.0 - ((loop.vert.co.x / scale_x) + 0.5)
                            v = (loop.vert.co.z / scale_z) + 0.5
                            loop[uv_layer].uv = (min(1.0, max(0.0, u)), min(1.0, max(0.0, v)))
                        face_count += 1
                    except ValueError:
                        pass

    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=0.005)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    
    mesh = bpy.data.meshes.new("InflatedMesh")
    bm.to_mesh(mesh)
    bm.free()
    
    obj = bpy.data.objects.new("InflatedAsset", mesh)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    
    print(f"Generated mesh with {len(mesh.vertices)} verts, {len(mesh.polygons)} faces in {time.time() - t0:.2f}s")
    
    # Smooth modifier
    sm = obj.modifiers.new("Smooth", "SMOOTH")
    sm.factor = 0.5
    sm.iterations = 2
    bpy.ops.object.modifier_apply(modifier="Smooth")
    
    # Subsurf modifier
    sub_mod = obj.modifiers.new("Subsurf", "SUBSURF")
    sub_mod.levels = 1
    bpy.ops.object.modifier_apply(modifier="Subsurf")
    bpy.ops.object.shade_smooth()
    
    # PBR Material with original texture
    mat = bpy.data.materials.new("FaithfulImagePBR")
    mat.use_nodes = True
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
    
    exports_dir = Path("test_inflation_output")
    exports_dir.mkdir(parents=True, exist_ok=True)
    
    bpy.ops.object.select_all(action='SELECT')
    t_exp = time.time()
    bpy.ops.export_scene.gltf(filepath=str(exports_dir / "inflated.glb"), export_format='GLB', export_apply=True)
    bpy.ops.wm.obj_export(filepath=str(exports_dir / "inflated.obj"))
    bpy.ops.wm.stl_export(filepath=str(exports_dir / "inflated.stl"))
    bpy.ops.export_scene.fbx(filepath=str(exports_dir / "inflated.fbx"))
    
    print(f"Exported all 4 formats in {time.time() - t_exp:.2f}s! Total time: {time.time() - t0:.2f}s")

if __name__ == "__main__":
    test_img = "Project_no2_Image_to_3d_Model/spaceman.png"
    if len(sys.argv) > 1 and sys.argv[-1].endswith(('.png', '.jpg', '.webp')):
        test_img = sys.argv[-1]
    test_inflate(test_img, max_depth=0.35, grid_res=80)

import bpy
import numpy as np
import bmesh
from pathlib import Path
import time

def clean_scene():
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for _ in range(3):
        bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)

def filter_islands(mask, min_size=40):
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

def run_clean_test(image_path: str):
    t0 = time.time()
    clean_scene()
    img = bpy.data.images.load(str(Path(image_path).resolve()))
    w_orig, h_orig = img.size
    pixels = np.array(img.pixels[:], dtype=np.float32).reshape((h_orig, w_orig, 4))
    
    grid_res = 86
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
        
    mask = filter_islands(raw_mask, min_size=40)
    print(f"Raw mask active: {np.sum(raw_mask)}, after island filter: {np.sum(mask)}")
    
    dist = fast_chamfer_edt(mask)
    max_d = max(1.0, float(dist.max()))
    norm_dist = np.clip(dist / max_d, 0.0, 1.0)
    z_map = 0.35 * np.sin(norm_dist * (np.pi / 2.0))
    
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
    
    v_front, v_back = {}, {}
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
    
    mesh = bpy.data.meshes.new("InflatedMesh")
    bm.to_mesh(mesh)
    bm.free()
    
    obj = bpy.data.objects.new("InflatedAsset", mesh)
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
    
    out_dir = Path("Project_no2_Image_to_3d_Model/exports")
    glb_path = out_dir / "clean_spaceman.glb"
    bpy.ops.export_scene.gltf(filepath=str(glb_path), export_format='GLB', export_apply=True)
    print(f"SUCCESS: Exported {glb_path} ({glb_path.stat().st_size:,} bytes) in {time.time() - t0:.2f}s!")

if __name__ == "__main__":
    run_clean_test("Project_no2_Image_to_3d_Model/spaceman.png")

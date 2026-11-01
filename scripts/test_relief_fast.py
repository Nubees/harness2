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

def generate_contour_relief(image_path: str, relief_depth: float = 0.18, base_thickness: float = 0.10, grid_res: int = 100, is_medallion: bool = False):
    t0 = time.time()
    clean_scene()
    image_path = str(Path(image_path).resolve())
    img = bpy.data.images.load(image_path)
    w_orig, h_orig = img.size
    
    pixels = np.array(img.pixels[:], dtype=np.float32).reshape((h_orig, w_orig, 4))
    step_y = max(1, h_orig // grid_res)
    step_x = max(1, w_orig // grid_res)
    sub = pixels[::step_y, ::step_x, :]
    h, w, _ = sub.shape
    
    alpha = sub[:, :, 3]
    rgb = sub[:, :, :3]
    
    # Grayscale luminance heightmap
    gray = 0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]
    
    if np.any(alpha < 0.85):
        mask = alpha > 0.15
    else:
        corners = np.vstack([rgb[:4, :4, :].reshape(-1, 3),
                             rgb[-4:, :4, :].reshape(-1, 3),
                             rgb[:4, -4:, :].reshape(-1, 3),
                             rgb[-4:, -4:, :].reshape(-1, 3)])
        bg = np.median(corners, axis=0)
        diff = np.linalg.norm(rgb - bg, axis=-1)
        mask = diff > 0.12

    if np.sum(mask) < 20:
        mask = np.ones((h, w), dtype=bool)
        
    aspect = w / h
    scale_x = aspect * 2.0
    scale_z = 2.0
    
    bm = bmesh.new()
    uv_layer = bm.loops.layers.uv.new("UVMap")
    
    v_top = {}
    v_bot = {}
    
    for y in range(h):
        for x in range(w):
            if mask[y, x]:
                vx = (x / (w - 1) - 0.5) * scale_x
                vz = (y / (h - 1) - 0.5) * scale_z
                # Top elevation with relief details
                z_rel = float(gray[y, x]) * relief_depth
                
                v_top[(x, y)] = bm.verts.new((vx, -(base_thickness + z_rel), vz))
                v_bot[(x, y)] = bm.verts.new((vx, 0.0, vz))
                
    bm.verts.ensure_lookup_table()
    
    # Top and bottom faces
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
                    
    # Perimeter side walls
    top_verts = set(v_top.values())
    bot_map = {v_top[k]: v_bot[k] for k in v_top}
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
    
    # Bevel and smooth
    bev = obj.modifiers.new("Bevel", "BEVEL")
    bev.width = 0.015
    bev.segments = 2
    bpy.ops.object.modifier_apply(modifier="Bevel")
    bpy.ops.object.shade_smooth()
    
    # Metallic Bronze / Antique Gold PBR material with image texture
    mat = bpy.data.materials.new("ReliefPBR")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    
    tex_node = mat.node_tree.nodes.new("ShaderNodeTexImage")
    tex_node.image = img
    mat.node_tree.links.new(tex_node.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Metallic"].default_value = 0.70
    bsdf.inputs["Roughness"].default_value = 0.28
    
    obj.data.materials.append(mat)
    
    exports_dir = Path("test_relief_output")
    exports_dir.mkdir(parents=True, exist_ok=True)
    
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.export_scene.gltf(filepath=str(exports_dir / "relief.glb"), export_format='GLB', export_apply=True)
    bpy.ops.wm.obj_export(filepath=str(exports_dir / "relief.obj"))
    bpy.ops.wm.stl_export(filepath=str(exports_dir / "relief.stl"))
    bpy.ops.export_scene.fbx(filepath=str(exports_dir / "relief.fbx"))
    
    print(f"Relief generation and export completed in {time.time() - t0:.2f}s!")

if __name__ == "__main__":
    test_img = "Project_no2_Image_to_3d_Model/spaceman.png"
    if len(sys.argv) > 1 and sys.argv[-1].endswith(('.png', '.jpg', '.webp')):
        test_img = sys.argv[-1]
    generate_contour_relief(test_img, relief_depth=0.15, base_thickness=0.08, grid_res=80)

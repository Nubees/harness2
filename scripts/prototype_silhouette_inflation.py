import sys
import time
from pathlib import Path
import bpy
import numpy as np
import bmesh
from mathutils import Vector

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

def inflate_image_silhouette(image_path: str, max_depth: float = 0.40, grid_res: int = 120):
    """Inflates a 2D image silhouette into an organic watertight 3D manifold with exact texture mapping."""
    t0 = time.time()
    clean_scene()
    image_path = str(Path(image_path).resolve())
    img = bpy.data.images.load(image_path)
    w_orig, h_orig = img.size
    
    # Extract RGBA pixels to numpy array
    pixels = np.array(img.pixels[:], dtype=np.float32).reshape((h_orig, w_orig, 4))
    
    # Subsample to grid_res
    step_y = max(1, h_orig // grid_res)
    step_x = max(1, w_orig // grid_res)
    sub_pixels = pixels[::step_y, ::step_x, :]
    h, w, _ = sub_pixels.shape
    
    # Foreground mask
    alpha = sub_pixels[:, :, 3]
    rgb = sub_pixels[:, :, :3]
    if np.any(alpha < 0.9):
        mask = alpha > 0.15
    else:
        # Detect background color from corners
        bg = (sub_pixels[0, 0, :3] + sub_pixels[0, -1, :3] + sub_pixels[-1, 0, :3] + sub_pixels[-1, -1, :3]) / 4.0
        diff = np.linalg.norm(rgb - bg, axis=-1)
        mask = diff > 0.12
        
    print(f"Foreground pixels: {np.sum(mask):,} / {mask.size:,}")
    if np.sum(mask) < 20:
        mask = np.ones((h, w), dtype=bool)
        
    # Distance transform
    dist = fast_chamfer_edt(mask)
    max_d = np.max(dist)
    if max_d <= 0:
        max_d = 1.0
        
    # Harmonic circular-arc elevation Z = max_depth * sin((pi/2) * (d / max_d))
    norm_dist = np.clip(dist / max_d, 0.0, 1.0)
    height_map = max_depth * np.sin(norm_dist * (np.pi / 2.0))
    
    # Build BMesh
    bm = bmesh.new()
    uv_layer = bm.loops.layers.uv.new("UVMap")
    
    # Normalized dimensions in Blender (Z is up, Y is depth, X is horizontal)
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
                z_elev = float(height_map[y, x])
                
                # Front vertex (+Y depth toward camera is -Y in standard Blender coordinates)
                # Let's align so -Y is front
                vf = bm.verts.new((vx, -z_elev, vz))
                v_front[(x, y)] = vf
                
                # Back vertex (+Y depth)
                vb = bm.verts.new((vx, +z_elev * 0.9, vz))
                v_back[(x, y)] = vb
                
    bm.verts.ensure_lookup_table()
    
    # Create front and back quad faces
    for y in range(h - 1):
        for x in range(w - 1):
            corners = [(x, y), (x + 1, y), (x + 1, y + 1), (x, y + 1)]
            if all(c in v_front for c in corners):
                # Front face
                f_front = bm.faces.new([v_front[c] for c in corners])
                for loop in f_front.loops:
                    px = loop.vert.co.x
                    pz = loop.vert.co.z
                    u = (px / scale_x) + 0.5
                    v = (pz / scale_z) + 0.5
                    loop[uv_layer].uv = (min(1.0, max(0.0, u)), min(1.0, max(0.0, v)))
                    
                # Back face (reversed winding for correct outward normals)
                f_back = bm.faces.new([v_back[c] for c in reversed(corners)])
                for loop in f_back.loops:
                    px = loop.vert.co.x
                    pz = loop.vert.co.z
                    # Mirrored U for natural back texture
                    u = 1.0 - ((px / scale_x) + 0.5)
                    v = (pz / scale_z) + 0.5
                    loop[uv_layer].uv = (min(1.0, max(0.0, u)), min(1.0, max(0.0, v)))
                    
    # Weld boundary vertices where elevation is near zero
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=0.02)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    
    mesh = bpy.data.meshes.new("InflatedMesh")
    bm.to_mesh(mesh)
    bm.free()
    
    obj = bpy.data.objects.new("InflatedAsset", mesh)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    
    print(f"Raw inflated mesh: {len(mesh.vertices):,} vertices, {len(mesh.polygons):,} faces.")
    
    # OpenVDB Voxel Remesh to seal and unify topology
    obj.data.remesh_voxel_size = 0.025
    bpy.ops.object.voxel_remesh()
    
    # Smooth modifier
    sm = obj.modifiers.new("Smooth", "SMOOTH")
    sm.factor = 0.60
    sm.iterations = 3
    bpy.ops.object.modifier_apply(modifier="Smooth")
    
    # Subsurf modifier
    sub = obj.modifiers.new("Subsurf", "SUBSURF")
    sub.levels = 1
    bpy.ops.object.modifier_apply(modifier="Subsurf")
    bpy.ops.object.shade_smooth()
    
    print(f"Remeshed manifold: {len(obj.data.vertices):,} vertices, {len(obj.data.polygons):,} faces.")
    
    # Re-project frontal UV layer after remeshing
    uv_layer = obj.data.uv_layers.new(name="ImageUV")
    obj.data.uv_layers.active = uv_layer
    
    for poly in obj.data.polygons:
        for loop_idx in poly.loop_indices:
            v_idx = obj.data.loops[loop_idx].vertex_index
            vx, vy, vz = obj.data.vertices[v_idx].co
            # If front hemisphere (vy <= 0)
            if vy <= 0:
                u = (vx / scale_x) + 0.5
            else:
                u = 1.0 - ((vx / scale_x) + 0.5)
            v = (vz / scale_z) + 0.5
            uv_layer.data[loop_idx].uv = (min(1.0, max(0.0, u)), min(1.0, max(0.0, v)))
            
    # Faithful PBR Material with original texture
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
    
    # Export all formats
    exports_dir = Path("test_inflation_output")
    exports_dir.mkdir(parents=True, exist_ok=True)
    
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.export_scene.gltf(filepath=str(exports_dir / "inflated.glb"), export_format='GLB', export_apply=True)
    bpy.ops.wm.obj_export(filepath=str(exports_dir / "inflated.obj"))
    bpy.ops.wm.stl_export(filepath=str(exports_dir / "inflated.stl"))
    bpy.ops.export_scene.fbx(filepath=str(exports_dir / "inflated.fbx"))
    
    elapsed = round(time.time() - t0, 2)
    print(f"SUCCESS: Silhouette inflation complete in {elapsed}s! All 4 formats exported.")

if __name__ == "__main__":
    test_img = r"Project_no2_Image_to_3d_Model/spaceman.png"
    if len(sys.argv) > 1 and sys.argv[-1].endswith(('.png', '.jpg', '.webp')):
        test_img = sys.argv[-1]
    inflate_image_silhouette(test_img, max_depth=0.45, grid_res=96)

import bpy
import math
from pathlib import Path
from mathutils import Vector, Euler, Matrix

# Clear scene
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()
for block in bpy.data.meshes: bpy.data.meshes.remove(block)
for block in bpy.data.materials: bpy.data.materials.remove(block)

exports_dir = Path("test_advanced_output")
exports_dir.mkdir(parents=True, exist_ok=True)

print("--- Testing Advanced Organic 3D Geometry in Blender 5.2 LTS ---")

# 1. Base Organic Head/Body: slightly squashed sphere
bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=24, radius=1.0, location=(0, 0, 1.0))
body = bpy.context.active_object
body.name = "BodyBase"
body.scale = (1.05, 0.95, 0.92)
bpy.ops.object.transform_apply(scale=True)

# 2. Add Cheeks to flesh out organic silhouette
for side, x in [("L", -0.55), ("R", 0.55)]:
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=16, radius=0.38, location=(x, -0.45, 0.85))
    chk = bpy.context.active_object
    chk.name = f"Cheek_{side}"
    chk.scale = (1.1, 0.9, 0.9)
    bpy.ops.object.transform_apply(scale=True)

# 3. Add Swept Plume Base on Crown (tilted back)
bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=16, radius=0.65, location=(0, 0.45, 1.55))
plume_base = bpy.context.active_object
plume_base.name = "PlumeBase"
plume_base.scale = (0.85, 1.3, 1.1)
bpy.ops.object.transform_apply(scale=True)

# 4. Join Body, Cheeks, and PlumeBase into ONE object
bpy.ops.object.select_all(action='DESELECT')
body.select_set(True)
for obj_name in ["Cheek_L", "Cheek_R", "PlumeBase"]:
    bpy.data.objects[obj_name].select_set(True)
bpy.context.view_layer.objects.active = body
bpy.ops.object.join()
print("Joined organic components into single mesh object.")

# 5. OpenVDB Voxel Remeshing: FUSES all intersecting meshes into a SEAMLESS continuous skin!
body.data.remesh_voxel_size = 0.035
bpy.ops.object.voxel_remesh()
print("Voxel remeshing complete! All seams melted into continuous organic topology.")

# 6. Apply Smooth Modifier
mod_smooth = body.modifiers.new(name="OrganicSmooth", type='SMOOTH')
mod_smooth.factor = 0.75
mod_smooth.iterations = 4
bpy.ops.object.modifier_apply(modifier="OrganicSmooth")

# 7. Apply Subdivision Surface for glass-smooth curvature
mod_sub = body.modifiers.new(name="Subsurf", type='SUBSURF')
mod_sub.levels = 1
mod_sub.render_levels = 1
bpy.ops.object.modifier_apply(modifier="Subsurf")
bpy.ops.object.shade_smooth()
print(f"Body mesh generated: {len(body.data.vertices):,} vertices, {len(body.data.polygons):,} faces.")

# 8. Eye Sockets Carving via Boolean Difference (creates natural recessed sockets!)
for side, x in [("L", -0.32), ("R", 0.32)]:
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=16, radius=0.28, location=(x, -0.85, 1.05))
    cutter = bpy.context.active_object
    cutter.scale = (1.0, 0.8, 1.25)
    bpy.ops.object.transform_apply(scale=True)
    
    # Boolean cutter
    mod_bool = body.modifiers.new(name=f"EyeCut_{side}", type='BOOLEAN')
    mod_bool.operation = 'DIFFERENCE'
    mod_bool.object = cutter
    bpy.context.view_layer.objects.active = body
    bpy.ops.object.modifier_apply(modifier=f"EyeCut_{side}")
    
    # Remove cutter mesh
    bpy.data.objects.remove(cutter, do_unlink=True)

# 9. Inset Glossy Eyes inside the carved sockets
eye_mat = bpy.data.materials.new(name="EyeScleraMat")
eye_mat.use_nodes = True
nodes = eye_mat.node_tree.nodes
bsdf = nodes.get("Principled BSDF")
bsdf.inputs["Base Color"].default_value = (1.0, 0.95, 0.75, 1.0) # warm cream
bsdf.inputs["Roughness"].default_value = 0.15 # glossy

for side, x in [("L", -0.32), ("R", 0.32)]:
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=16, radius=0.25, location=(x, -0.82, 1.05))
    eye = bpy.context.active_object
    eye.name = f"Eye_{side}"
    eye.scale = (0.9, 0.6, 1.15)
    bpy.ops.object.transform_apply(scale=True)
    eye.data.materials.append(eye_mat)
    bpy.ops.object.shade_smooth()

# 10. Dynamic Swept Flames using Bézier Spline Curves with Taper Bevel
print("Constructing dynamic swept flame spline lofts...")
curve_data = bpy.data.curves.new(name="FlamePlumeCurve", type='CURVE')
curve_data.dimensions = '3D'
curve_data.bevel_depth = 0.16
curve_data.bevel_resolution = 6

spline = curve_data.splines.new('BEZIER')
spline.bezier_points.add(3) # 4 points total
pts = [
    Vector((0.0, 0.2, 1.6)),    # root at crown
    Vector((-0.3, 0.6, 2.1)),   # mid-rise swept back & left
    Vector((-0.8, 1.1, 2.4)),   # arched sweep
    Vector((-1.4, 1.5, 2.2)),   # curling tip
]
radii = [1.8, 1.4, 0.8, 0.05] # thick root tapering to sharp tip!

for i, pt in enumerate(spline.bezier_points):
    pt.co = pts[i]
    pt.radius = radii[i]
    pt.handle_left_type = 'AUTO'
    pt.handle_right_type = 'AUTO'

curve_obj = bpy.data.objects.new("FlamePlume", curve_data)
bpy.context.collection.objects.link(curve_obj)

# Convert flame curve to mesh so it can be exported to standard GLB/OBJ
bpy.context.view_layer.objects.active = curve_obj
curve_obj.select_set(True)
bpy.ops.object.convert(target='MESH')
mod_flame_smooth = curve_obj.modifiers.new(name="FlameSubsurf", type='SUBSURF')
mod_flame_smooth.levels = 1
bpy.ops.object.modifier_apply(modifier="FlameSubsurf")
bpy.ops.object.shade_smooth()

# 11. Emissive Flame Gradient Material
flame_mat = bpy.data.materials.new(name="FlameGlowMat")
flame_mat.use_nodes = True
f_bsdf = flame_mat.node_tree.nodes.get("Principled BSDF")
f_bsdf.inputs["Base Color"].default_value = (1.0, 0.35, 0.05, 1.0) # vivid orange
f_bsdf.inputs["Roughness"].default_value = 0.3
f_bsdf.inputs["Emission Color"].default_value = (1.0, 0.45, 0.08, 1.0)
f_bsdf.inputs["Emission Strength"].default_value = 6.0
curve_obj.data.materials.append(flame_mat)

# 12. Body PBR Material with Subsurface Scatter and Velvet Rim Sheen
body_mat = bpy.data.materials.new(name="BodyFlameMat")
body_mat.use_nodes = True
b_nodes = body_mat.node_tree.nodes
b_bsdf = b_nodes.get("Principled BSDF")
b_bsdf.inputs["Base Color"].default_value = (1.0, 0.42, 0.05, 1.0)
b_bsdf.inputs["Roughness"].default_value = 0.35
# Subsurface for organic glow
for sub_key in ("Subsurface Weight", "Subsurface"):
    if sub_key in b_bsdf.inputs:
        b_bsdf.inputs[sub_key].default_value = 0.25
        break
# Emission for self-illumination
b_bsdf.inputs["Emission Color"].default_value = (1.0, 0.25, 0.02, 1.0)
b_bsdf.inputs["Emission Strength"].default_value = 1.2
body.data.materials.append(body_mat)

# 13. Multi-Format Exports
glb_out = exports_dir / "sculpted_character.glb"
obj_out = exports_dir / "sculpted_character.obj"
stl_out = exports_dir / "sculpted_character.stl"
fbx_out = exports_dir / "sculpted_character.fbx"

bpy.ops.export_scene.gltf(filepath=str(glb_out), export_format="GLB", export_apply=True)
bpy.ops.wm.obj_export(filepath=str(obj_out))
bpy.ops.wm.stl_export(filepath=str(stl_out))
bpy.ops.export_scene.fbx(filepath=str(fbx_out))

print("Exports successfully completed:")
print(f" - GLB: {glb_out.name} ({round(glb_out.stat().st_size / 1024, 1)} KB)")
print(f" - OBJ: {obj_out.name} ({round(obj_out.stat().st_size / 1024, 1)} KB)")
print(f" - STL: {stl_out.name} ({round(stl_out.stat().st_size / 1024, 1)} KB)")
print(f" - FBX: {fbx_out.name} ({round(fbx_out.stat().st_size / 1024, 1)} KB)")
print("MODEL_BUILD_OK")

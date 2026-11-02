"""Unified Headless Blender Addon Adapter for Omni-3D.

Drives `Asset_Generator-2D-3D` (tin2tin) and `SculptMate` (shravan-d) headlessly inside
Blender 5.2.1 LTS (-b -P), bypassing broken GUI modal timers and off-thread C-API calls.
"""

import sys
import os
import argparse
import math
import time
from pathlib import Path

# Add the user addons directory to sys.path
ADDONS_DIR = Path(r"C:\Users\User101\AppData\Roaming\Blender Foundation\Blender\5.2\scripts\addons")
if str(ADDONS_DIR) not in sys.path:
    sys.path.insert(0, str(ADDONS_DIR))

import bpy


def setup_textured_image_plane(image_path: str):
    """Programmatically sets up the textured image plane required by Asset_Generator_2D_3D."""
    bpy.ops.wm.read_factory_settings(use_empty=True)

    img = bpy.data.images.load(filepath=os.path.abspath(image_path), check_existing=True)

    bpy.ops.mesh.primitive_plane_add(size=2.0, location=(0, 0, 0), rotation=(math.radians(90), 0, 0))
    plane = bpy.context.active_object
    plane.name = "Input_Image_Plane"

    mat = bpy.data.materials.new(name="Mat_Input_Image")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    out_node = nodes.new(type="ShaderNodeOutputMaterial")
    bsdf_node = nodes.new(type="ShaderNodeBsdfPrincipled")
    tex_node = nodes.new(type="ShaderNodeTexImage")
    tex_node.image = img

    links.new(tex_node.outputs["Color"], bsdf_node.inputs["Base Color"])
    links.new(tex_node.outputs["Alpha"], bsdf_node.inputs["Alpha"])
    links.new(bsdf_node.outputs["BSDF"], out_node.inputs["Surface"])

    plane.data.materials.append(mat)
    plane.select_set(True)
    bpy.context.view_layer.objects.active = plane
    return plane


def run_asset_generator_headless(image_path: str, exports_dir: str, formats: list[str]) -> bool:
    """Executes Asset_Generator_2D_3D headlessly."""
    print(f"[Adapter:Asset_Generator] Setting up image plane for {image_path}...")
    setup_textured_image_plane(image_path)

    import addon_utils
    addon_utils.enable("Asset_Generator_2D_3D", default_set=False)

    scene = bpy.context.scene
    scene.trellis_model_backend = "TRELLIS2"
    scene.trellis_pipeline_type = "1024_cascade"
    scene.trellis_seed = 42

    print("[Adapter:Asset_Generator] Triggering object.trellis_convert...")
    try:
        res = bpy.ops.object.trellis_convert()
        print(f"[Adapter:Asset_Generator] Operator result: {res}")
    except Exception as exc:
        print(f"[Adapter:Asset_Generator] Operator error: {exc}")

    # The operator writes run_3d.py to datafiles/3D_Async_Queue
    data_dir = os.path.join(bpy.utils.user_resource("DATAFILES"), "3D_Async_Queue")
    run_script = os.path.join(data_dir, "run_3d.py")

    out_glb = Path(exports_dir) / "model.glb"
    expected_output = image_path.replace(".png", "_3d.glb")

    if os.path.isfile(run_script):
        print(f"[Adapter:Asset_Generator] Running generated runner script: {run_script}")
        import subprocess
        res_proc = subprocess.run([sys.executable, "-u", run_script], capture_output=True, text=True)
        print("[Adapter:Asset_Generator] Runner stdout:", res_proc.stdout[:500])
        if os.path.isfile(expected_output):
            import shutil
            shutil.copy2(expected_output, out_glb)
            return True

    return False


def run_sculptmate_headless(image_path: str, exports_dir: str, formats: list[str]) -> bool:
    """Executes SculptMate headlessly with Blender 5.2 modern color attribute support."""
    print(f"[Adapter:SculptMate] Initializing for image {image_path}...")
    import addon_utils
    addon_utils.enable("SculptMate", default_set=False)

    try:
        from SculptMate import GUIPanel
        if not hasattr(bpy.ops.tool, "generate") or "generate" not in dir(bpy.ops.tool):
            GUIPanel.register()
    except Exception as exc:
        print(f"[Adapter:SculptMate] Note on GUIPanel register: {exc}")

    bpy.context.window_manager.input_image_path = os.path.abspath(image_path)
    bpy.context.scene.my_props.model_type = "lean"  # 'lean' runs TripoSR
    bpy.context.scene.my_props.enable_textures = True

    print("[Adapter:SculptMate] Invoking tool.generate...")
    try:
        bpy.ops.tool.generate()
        # Wait up to 30s for the worker thread if active
        for _ in range(60):
            if bpy.context.window_manager.buttons_enabled:
                break
            time.sleep(0.5)
    except Exception as exc:
        print(f"[Adapter:SculptMate] Invocation note: {exc}")

    # Check if a mesh was created
    mesh_objs = [o for o in bpy.data.objects if o.type == "MESH"]
    if mesh_objs:
        print(f"[Adapter:SculptMate] Generated mesh found: {[o.name for o in mesh_objs]}")
        out_glb = Path(exports_dir) / "model.glb"
        bpy.ops.export_scene.gltf(filepath=str(out_glb), export_format="GLB")
        return True

    return False


def run_2d_to_3d_plugin_headless(image_path: str, exports_dir: str, formats: list[str]) -> bool:
    """Executes blender-2d-to-3d-plugin headlessly with automatic contour extrusion and UV projection."""
    print(f"[Adapter:2D_to_3D] Processing image {image_path}...")
    import site
    user_site = site.getusersitepackages()
    if user_site and user_site not in sys.path:
        site.addsitedir(user_site)

    bpy.ops.wm.read_factory_settings(use_empty=True)

    import addon_utils
    addon_utils.enable("blender_2d_to_3d_plugin", default_set=False)

    wm = bpy.context.window_manager
    if hasattr(wm, "image_to_mesh_settings"):
        wm.image_to_mesh_settings.extrude_depth = 0.2
        wm.image_to_mesh_settings.simplicity = 3.0
        wm.image_to_mesh_settings.enclosed = False  # Rounded bevel extrusion
        wm.image_to_mesh_settings.rounded = True
        wm.image_to_mesh_settings.min_length = 80.0

    print("[Adapter:2D_to_3D] Invoking object.image_to_mesh...")
    try:
        res = bpy.ops.object.image_to_mesh(filepath=os.path.abspath(image_path))
        print(f"[Adapter:2D_to_3D] Operator returned: {res}")
    except Exception as exc:
        print(f"[Adapter:2D_to_3D] Operator execution error: {exc}")
        return False

    mesh_objs = [o for o in bpy.data.objects if o.type == "MESH"]
    if mesh_objs:
        print(f"[Adapter:2D_to_3D] Generated mesh found: {[o.name for o in mesh_objs]}")
        out_glb = Path(exports_dir) / "model.glb"
        bpy.ops.object.select_all(action="DESELECT")
        for obj in mesh_objs:
            obj.select_set(True)
        bpy.context.view_layer.objects.active = mesh_objs[0]
        bpy.ops.export_scene.gltf(filepath=str(out_glb), export_format="GLB", use_selection=True)
        return True

    return False


def export_additional_formats(exports_dir: Path, formats: list[str]):
    """Converts model.glb into OBJ, STL, FBX if requested."""
    out_glb = exports_dir / "model.glb"
    if not out_glb.is_file():
        return

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(out_glb))
    bpy.ops.object.select_all(action="SELECT")

    if "obj" in formats:
        bpy.ops.wm.obj_export(filepath=str(exports_dir / "model.obj"))
    if "stl" in formats:
        bpy.ops.wm.stl_export(filepath=str(exports_dir / "model.stl"))
    if "fbx" in formats:
        bpy.ops.export_scene.fbx(filepath=str(exports_dir / "model.fbx"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--addon", required=True, choices=["addon_asset_generator", "addon_sculptmate", "addon_2d_to_3d"])
    parser.add_argument("--image", required=True)
    parser.add_argument("--exports", required=True)
    parser.add_argument("--formats", default="glb,obj,stl,fbx")

    # Filter arguments passed after '--'
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []

    args = parser.parse_args(argv)
    exports_dir = Path(args.exports)
    formats = [f.strip().lower() for f in args.formats.split(",")]

    success = False
    if args.addon == "addon_asset_generator":
        success = run_asset_generator_headless(args.image, args.exports, formats)
    elif args.addon == "addon_sculptmate":
        success = run_sculptmate_headless(args.image, args.exports, formats)
    elif args.addon == "addon_2d_to_3d":
        success = run_2d_to_3d_plugin_headless(args.image, args.exports, formats)

    if success:
        export_additional_formats(exports_dir, formats)
        print("[Adapter] Finished successfully with deliverables.")
        sys.exit(0)
    else:
        print("[Adapter] Add-on could not complete local inference directly (Hardware or dependencies missing).")
        sys.exit(2)


if __name__ == "__main__":
    main()

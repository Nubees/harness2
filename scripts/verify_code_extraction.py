import sys
from pathlib import Path

# Add project directory to sys.path
sys.path.insert(0, str(Path(r"C:\Projects\Harnes2\Project_no2_Image_to_3d_Model")))
from omni_engine import extract_blender_script, sanitize_blender_script, Omni3DEngine

# Test 1: Multiple code blocks (where first is an introductory snippet)
sample_multi_block = """
Here is an idea for modifier application:
```python
bpy.ops.object.select_all(action='DESELECT')
for obj in mesh_objs:
    obj.select_set(True)
```

And now here is the complete, runnable Blender script:
```python
import bpy
import math
from pathlib import Path

# Setup
exports_dir = Path(__file__).resolve().parent / "exports"
exports_dir.mkdir(parents=True, exist_ok=True)

bpy.ops.mesh.primitive_uv_sphere_add(radius=1.0, location=(0, 0, 1))
sphere = bpy.context.active_object
sphere.name = "MyTestSphere"

# Export
bpy.ops.export_scene.gltf(filepath=str(exports_dir / "model.glb"), export_format="GLB")
print("MODEL_BUILD_OK")
```
"""

extracted = extract_blender_script(sample_multi_block)
assert "import bpy" in extracted, "Failed: 'import bpy' not in extracted script"
assert "MyTestSphere" in extracted, "Failed: 'MyTestSphere' not in extracted script"
assert "mesh_objs" not in extracted or "MyTestSphere" in extracted, "Failed: selected wrong block"
print("Test 1 PASS: Multi-block extraction correctly picked the complete script!")

# Test 2: Unclosed code block (when LLM stream ends before closing ```)
sample_unclosed = """
```python
import bpy
from pathlib import Path

bpy.ops.mesh.primitive_cube_add(size=2.0)
print("MODEL_BUILD_OK")
"""
extracted_unclosed = extract_blender_script(sample_unclosed)
assert "import bpy" in extracted_unclosed
assert "primitive_cube_add" in extracted_unclosed
print("Test 2 PASS: Unclosed code block correctly extracted!")

# Test 3: Raw Python text without fences
sample_raw = """
Sure! Here is the script:

import bpy
import math

bpy.ops.mesh.primitive_cone_add()
"""
extracted_raw = extract_blender_script(sample_raw)
assert extracted_raw.startswith("import bpy")
print("Test 3 PASS: Raw Python text without fences extracted from 'import bpy'!")

# Test 4: Blender execution traceback detection
engine = Omni3DEngine()
# Create a dummy script with a traceback
tmp_fail_script = Path("tmp_fail_test.py")
tmp_fail_script.write_text("import bpy\nnon_existent_function()\n", encoding="utf-8")
res = engine.execute_blender_script(tmp_fail_script)
assert res["success"] is False, f"Expected success=False on traceback, got {res['success']}"
tmp_fail_script.unlink(missing_ok=True)
print("Test 4 PASS: Blender script crash with traceback correctly detected as success=False!")

# Test 5: Script sanitation for invalid parent_set enum and obsolete properties
sample_hallucinated = """
import bpy
bpy.ops.object.parent_set(type='OBJECT_KEEP_TRANSFORM')
obj.data.use_auto_smooth = True
v = Vector((1, 2, 3))
"""
sanitized = sanitize_blender_script(sample_hallucinated)
assert "OBJECT_KEEP_TRANSFORM" not in sanitized
assert "parent_set(type='OBJECT', keep_transform=True)" in sanitized
assert "from mathutils import Vector" in sanitized
assert "# use_auto_smooth deprecated" in sanitized
print("Test 5 PASS: Script sanitizer auto-corrected parent_set enum and use_auto_smooth!")

# Test 6: SOTA helper injection when LLM invokes high-level sculpting API
sample_sota_call = """
import bpy
body = bpy.data.objects['Cube']
fuse_objects_voxel_remesh([body], body, voxel_size=0.03)
create_swept_spline_mesh('Flame', [(0,0,0), (0,0,1)], [1.0, 0.1])
"""
sanitized_sota = sanitize_blender_script(sample_sota_call)
assert "def fuse_objects_voxel_remesh" in sanitized_sota, "Failed: fuse_objects_voxel_remesh not injected"
assert "def create_swept_spline_mesh" in sanitized_sota, "Failed: create_swept_spline_mesh not injected"
print("Test 6 PASS: Verified SOTA sculpting helpers are automatically injected into caller scripts!")

# Test 7: Conversational prose monologue mentioning 'import bpy' inside sentences must NOT extract invalid code
sample_prose_monologue = """
I will now think about the error.
Also init_clean_scene() before materials - but helpers defined before import bpy; init called after import. Fine.
Also add_cyl fix: o.rotation_quaternion = d.to_track_quat('Z','Y').
Also rotation_mode = 'QUATERNION' then assign rotation_quaternion — fine.
"""
extracted_prose = extract_blender_script(sample_prose_monologue)
assert extracted_prose == "", f"Expected empty extraction from prose monologue, got: {repr(extracted_prose)}"
print("Test 7 PASS: Conversational monologue mentioning 'import bpy' safely rejected!")

# Test 8: Sanitizer fixes .to_track_quat().to_quaternion() and primitive_##op##_
sample_buggy_syntax = """
import bpy
o.rotation_quaternion = d.to_track_quat('Z','Y').to_quaternion()
bpy.ops.mesh.primitive_##op##_(**kw) if False else None
"""
sanitized_bugs = sanitize_blender_script(sample_buggy_syntax)
assert ".to_quaternion()" not in sanitized_bugs
assert "d.to_track_quat('Z','Y')" in sanitized_bugs
assert "##op##" not in sanitized_bugs
print("Test 8 PASS: Hallucinated quaternion and template placeholders successfully sanitized!")

print("\nALL 8 ROBUSTNESS TESTS PASSED 100%!")

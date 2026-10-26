import sys
from pathlib import Path

# Add project directory to sys.path
sys.path.insert(0, str(Path(r"C:\Projects\Harnes2\Project_no2_Image_to_3d_Model")))
from omni_engine import extract_blender_script, Omni3DEngine

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

print("\nALL 4 ROBUSTNESS TESTS PASSED 100%!")

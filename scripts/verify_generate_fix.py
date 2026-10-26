import re
from pathlib import Path
import sys

# 1. Test regex escape fix with actual Windows paths
job_dir = Path(r"C:\Projects\Harnes2\Project_no2_Image_to_3d_Model\runs\job_test")
exports_dir = job_dir / "exports"

synthesized_code = """
import bpy
from pathlib import Path

# Setup directories
exports_dir = Path(__file__).resolve().parent / "exports"
exports_dir.mkdir(parents=True, exist_ok=True)

print("Starting generation...")
"""

exports_posix = exports_dir.resolve().as_posix()
target_statement = f'exports_dir = Path("{exports_posix}")'

pattern = r'exports_dir\s*=\s*Path\(__file__\)\.resolve\(\)\.parent\s*/\s*["\']exports["\']'

try:
    if re.search(pattern, synthesized_code):
        result_code = re.sub(pattern, lambda _: target_statement, synthesized_code, count=1)
    else:
        result_code = synthesized_code
    print("Test 1 PASS: Regex replacement succeeded without bad escape error!")
    assert exports_posix in result_code
    print("Posix path present in generated script:", exports_posix)
except Exception as e:
    print(f"Test 1 FAIL: {e}")
    sys.exit(1)

# 2. Test fallback pattern with other formats
alt_code = """
import bpy
from pathlib import Path
exports_dir = Path("exports")
"""
alt_pat = r'exports_dir\s*=\s*Path\([^\)]+\)'
try:
    alt_result = re.sub(alt_pat, lambda _: target_statement, alt_code, count=1)
    print("Test 2 PASS: Fallback pattern replaced successfully!")
    assert exports_posix in alt_result
except Exception as e:
    print(f"Test 2 FAIL: {e}")
    sys.exit(1)

print("\nAll regex & path tests passed 100%!")

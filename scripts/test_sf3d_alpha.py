"""Test SF3D with transparent PNG (has_alpha=True) and Token Rotation / Public Pool."""

import json
import time
from pathlib import Path
from PIL import Image, ImageDraw
from gradio_client import Client, handle_file

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXPORTS_DIR = PROJECT_ROOT / "Project_no2_Image_to_3d_Model" / "exports" / "sf3d_test"
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

# Create a transparent PNG
trans_img_path = EXPORTS_DIR / "test_transparent_circle.png"
img = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)
draw.ellipse((64, 64, 448, 448), fill=(220, 50, 50, 255), outline=(255, 255, 255, 255), width=8)
img.save(trans_img_path)
print(f"Created transparent test image: {trans_img_path}")

def check_alpha(path: Path) -> bool:
    with Image.open(path) as im:
        if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
            extrema = im.convert("RGBA").getchannel("A").getextrema()
            return extrema[0] < 255
        return False

print(f"Has alpha: {check_alpha(trans_img_path)}")

# Test with token=None (Public pool test)
print("\nTesting Public Community Pool (token=None) with transparent image...")
t0 = time.time()
client = Client("stabilityai/stable-fast-3d", token=None, httpx_kwargs={"timeout": 120.0})
print(f"Connected in {time.time() - t0:.2f}s")

# Step 1: /requires_bg_remove
t1 = time.time()
res1 = client.predict(
    image=handle_file(str(trans_img_path)),
    fr=0.85,
    api_name="/requires_bg_remove",
)
print(f"Step 1 (/requires_bg_remove) on transparent image took {time.time() - t1:.2f}s")
print(f"Result: {res1}")

# Step 2: Since has_alpha is True, skip 'Remove Background' and call 'Run' directly!
client._skip_components = False
t2 = time.time()
print("Calling 'Run' directly (skipping 'Remove Background')...")
res_run = client.predict(
    "Run",
    handle_file(str(trans_img_path)),
    None,
    0.85,
    "None",
    -1,
    1024,
    fn_index=5,
)
print(f"Step 2 mesh generation took {time.time() - t2:.2f}s")
raw_glb = res_run[4]
glb_path = raw_glb["value"] if isinstance(raw_glb, dict) and "value" in raw_glb else raw_glb
print(f"Generated GLB: {glb_path} (exists: {Path(glb_path).is_file()})")

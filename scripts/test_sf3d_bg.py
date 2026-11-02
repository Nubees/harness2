import json
import time
from pathlib import Path
from gradio_client import Client, handle_file

keys_file = Path("Project_no2_Image_to_3d_Model/keys.json")
token = None
if keys_file.exists():
    d = json.loads(keys_file.read_text())
    token = d.get("hf_token") or (d.get("hf_tokens") and d["hf_tokens"][0])

client = Client("stabilityai/stable-fast-3d", token=token)
img_path = Path("Project_no2_Image_to_3d_Model/spaceman.png")

print(f"Testing requires_bg_remove on opaque image: {img_path}")
res = client.predict(
    image=handle_file(str(img_path)),
    fr=0.85,
    api_name="/requires_bg_remove",
)
print("Result of /requires_bg_remove:")
print(f"Type: {type(res)}, value: {res}")

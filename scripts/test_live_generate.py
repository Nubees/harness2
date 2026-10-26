import json
import time
import urllib.request

url = "http://localhost:8766/api/generate"
payload = json.dumps({
    "image": "uploads/upload_20261026_221356.png",
    "model": "glm-5.3-flash:cloud",
    "quality_preset": "sota_sculpt",
    "prompt": "Create high-fidelity stylized 3D character with fluid Bézier flames, smooth organic body, and carved facial features.",
    "formats": ["glb", "obj", "stl", "fbx"]
}).encode("utf-8")

req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req) as resp:
    res = json.loads(resp.read().decode("utf-8"))
    job_id = res["job_id"]
    print(f"Job queued: {job_id}")

events_url = f"http://localhost:8766/api/jobs/{job_id}/events"
print(f"Streaming events from {events_url}...")

req_ev = urllib.request.Request(events_url)
with urllib.request.urlopen(req_ev, timeout=600) as stream:
    for line in stream:
        s = line.decode("utf-8", errors="replace").strip()
        if not s or s.startswith(":"):
            continue
        if s.startswith("data:"):
            data_str = s[5:].strip()
            try:
                evt = json.loads(data_str)
                stage = evt.get("stage")
                stage_name = evt.get("stage_name")
                msg = evt.get("message", "")
                print(f"[{stage_name or 'STAGE ' + str(stage)}] {msg}")

                if stage_name in ("Complete", "Failed") or stage == 5:
                    if stage_name == "Complete":
                        print("\nGENERATION SUCCESSFUL!")
                        print("Deliverables:", json.dumps(evt.get("deliverables", {}), indent=2))
                    else:
                        print("\nGENERATION FAILED:", msg)
                    break
            except Exception as e:
                pass

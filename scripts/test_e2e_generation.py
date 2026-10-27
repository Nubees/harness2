import json
import time
import urllib.request

def test_generation(preset="silhouette_inflation"):
    print(f"\n--- Testing E2E Generation for Preset: {preset} ---")
    url = "http://localhost:8766/api/generate"
    payload = {
        "image": "spaceman.png",
        "model": "glm-5.3-flash:cloud",
        "prompt": "Test generation",
        "formats": ["glb", "obj", "stl", "fbx"],
        "quality_preset": preset
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    
    with urllib.request.urlopen(req) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        job_id = res["job_id"]
        print(f"Queued Job ID: {job_id}")
        
    events_url = f"http://localhost:8766/api/jobs/{job_id}/events"
    events_req = urllib.request.Request(events_url)
    
    with urllib.request.urlopen(events_req, timeout=120) as resp:
        for line in resp:
            line_str = line.decode("utf-8", errors="replace").strip()
            if line_str.startswith("data: "):
                data = json.loads(line_str[6:])
                stage = data.get("stage")
                stage_name = data.get("stage_name", "")
                msg = data.get("message", "")
                print(f"[{stage_name} | Stage {stage}] {msg}")
                if stage == 5 or stage_name in ("Complete", "Failed"):
                    if stage_name == "Complete":
                        print("SUCCESS! Deliverables:", json.dumps(data.get("deliverables"), indent=2))
                    else:
                        print("FAILURE:", data)
                    break

if __name__ == "__main__":
    test_generation("silhouette_inflation")
    test_generation("contour_relief")

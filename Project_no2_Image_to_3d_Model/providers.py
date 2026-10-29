"""Neural 3D Provider Integrations and Quota Management for Omni-3D.

Supports:
- Tripo3D (Cloud AI Neural Mesh Generator)
- Meshy.ai (Cloud AI PBR Multi-Texture & Neural Mesh)
- Microsoft TRELLIS (Hugging Face ZeroGPU SOTA NeRF/Gaussian Splatting)
- Local Offline TripoSR (Zero-Cost Local Neural Weights for GTX Video Card)
"""

from __future__ import annotations

import base64
import datetime
import io
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

PROJECT_DIR = Path(__file__).resolve().parent
KEYS_FILE = PROJECT_DIR / "keys.json"
DEFAULT_BLENDER = Path(r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")


def get_blender_exe() -> Path:
    if DEFAULT_BLENDER.is_file():
        return DEFAULT_BLENDER
    import shutil
    p = shutil.which("blender")
    return Path(p) if p else DEFAULT_BLENDER


def load_keys() -> dict[str, str]:
    """Load API keys from keys.json or fallback to environment variables."""
    keys = {
        "tripo3d_key": os.environ.get("TRIPO3D_API_KEY", ""),
        "meshy_key": os.environ.get("MESHY_API_KEY", ""),
        "hf_token": os.environ.get("HF_TOKEN", ""),
    }
    if KEYS_FILE.is_file():
        try:
            data = json.loads(KEYS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for k in keys:
                    if data.get(k):
                        keys[k] = data[k].strip()
        except Exception:
            pass
    return keys


def save_keys(keys_data: dict[str, str]) -> dict[str, str]:
    """Persist API keys to keys.json."""
    current = load_keys()
    for k in ("tripo3d_key", "meshy_key", "hf_token"):
        if k in keys_data:
            current[k] = str(keys_data[k]).strip()
    KEYS_FILE.write_text(json.dumps(current, indent=2), encoding="utf-8")
    return current


def get_time_until_utc_midnight() -> tuple[int, str]:
    """Calculate remaining seconds and formatted string until 00:00 UTC daily reset."""
    now = datetime.datetime.now(datetime.timezone.utc)
    midnight = (now + datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    remaining = int((midnight - now).total_seconds())
    hours = remaining // 3600
    mins = (remaining % 3600) // 60
    return remaining, f"{hours}h {mins}m"


def get_time_until_month_reset() -> tuple[int, str]:
    """Calculate remaining seconds and formatted string until 1st of next month."""
    now = datetime.datetime.now(datetime.timezone.utc)
    if now.month == 12:
        next_month = now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        next_month = now.replace(month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
    remaining = int((next_month - now).total_seconds())
    days = remaining // 86400
    hours = (remaining % 86400) // 3600
    return remaining, f"{days}d {hours}h"


def check_cuda_status() -> dict:
    """Check if CUDA GPU (e.g. GTX/RTX) is available locally."""
    try:
        import torch
        available = torch.cuda.is_available()
        gpu_name = torch.cuda.get_device_name(0) if available else "None"
        return {"has_cuda": available, "device_name": gpu_name}
    except Exception:
        return {"has_cuda": False, "device_name": "Standby (Ready for GTX Transfer)"}


def get_providers_status() -> dict:
    """Return live status, red/green light indicators, and reset timers for all providers."""
    keys = load_keys()
    tripo_key = keys.get("tripo3d_key", "")
    meshy_key = keys.get("meshy_key", "")
    hf_token = keys.get("hf_token", "")

    sec_daily, str_daily = get_time_until_utc_midnight()
    sec_monthly, str_monthly = get_time_until_month_reset()
    cuda_info = check_cuda_status()

    # 1. Tripo3D Status
    tripo_status = {
        "id": "tripo3d",
        "name": "Tripo3D",
        "has_key": bool(tripo_key),
        "status": "ready" if tripo_key else "needs_key",
        "light": "green" if tripo_key else "red",
        "timer_text": str_daily if not tripo_key else f"Active ({str_daily} reset)",
        "reset_seconds": sec_daily,
        "desc": "300–600 welcome credits + daily free refill at 00:00 UTC",
        "signup_url": "https://platform.tripo3d.ai",
    }

    # 2. Meshy Status
    meshy_status = {
        "id": "meshy",
        "name": "Meshy.ai",
        "has_key": bool(meshy_key),
        "status": "ready" if meshy_key else "needs_key",
        "light": "green" if meshy_key else "red",
        "timer_text": f"Active ({str_monthly} reset)" if meshy_key else "Paid Plan Req.",
        "reset_seconds": sec_monthly if meshy_key else 0,
        "desc": "Meshy restricts API keys to paid Pro plans ($20+/mo). Free credits on meshy.ai are web-app only.",
        "signup_url": "https://www.meshy.ai/pricing",
    }

    # 3. Hugging Face (TRELLIS) Status
    hf_status = {
        "id": "trellis_hf",
        "name": "Hugging Face (TRELLIS)",
        "has_key": bool(hf_token),
        "status": "ready",
        "light": "green",  # HuggingFace ZeroGPU is free even without key, but key gives higher priority
        "timer_text": "ZeroGPU Ready" if hf_token else "Community Pool",
        "reset_seconds": 0,
        "desc": "Microsoft TRELLIS on shared ZeroGPU A100 clusters (Free daily quotas)",
        "signup_url": "https://huggingface.co/settings/tokens",
    }

    # 4. Local Offline TripoSR Status (Ready for GTX Transfer)
    local_status = {
        "id": "triposr_local",
        "name": "Local Offline (GTX)",
        "has_key": True,
        "status": "ready",
        "light": "green",  # Always green!
        "timer_text": "Always Active" if not cuda_info["has_cuda"] else f"GTX Online ({cuda_info['device_name']})",
        "reset_seconds": 0,
        "has_cuda": cuda_info["has_cuda"],
        "device_name": cuda_info["device_name"],
        "desc": "100% offline and unlimited. Automatically leverages NVIDIA GTX hardware once project is copied to your GPU PC.",
    }

    return {
        "providers": {
            "tripo3d": tripo_status,
            "meshy": meshy_status,
            "trellis_hf": hf_status,
            "triposr_local": local_status,
        },
        "keys_configured": {
            "tripo3d": bool(tripo_key),
            "meshy": bool(meshy_key),
            "hf_token": bool(hf_token),
        },
    }


def convert_glb_to_formats(glb_path: Path, exports_dir: Path, formats: list[str]) -> list[str]:
    """Execute headless Blender 5.2 LTS to convert a generated GLB into OBJ, STL, and FBX."""
    blender_exe = get_blender_exe()
    if not blender_exe.is_file() or not glb_path.is_file():
        return []

    script_content = f'''
import bpy
from pathlib import Path

bpy.ops.wm.read_factory_settings(use_empty=True)

glb_path = r"{glb_path}"
exports_dir = Path(r"{exports_dir}")

bpy.ops.import_scene.gltf(filepath=glb_path)
bpy.ops.object.select_all(action='SELECT')

formats = {formats}
if "obj" in formats:
    bpy.ops.wm.obj_export(filepath=str(exports_dir / "model.obj"))
if "stl" in formats:
    bpy.ops.wm.stl_export(filepath=str(exports_dir / "model.stl"))
if "fbx" in formats:
    bpy.ops.export_scene.fbx(filepath=str(exports_dir / "model.fbx"))

print("CONVERT_EXPORT_OK")
'''
    temp_script = exports_dir.parent / "convert_formats.py"
    temp_script.write_text(script_content, encoding="utf-8")

    try:
        subprocess.run(
            [str(blender_exe), "-b", "-P", str(temp_script)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=120,
            text=True,
            errors="replace",
        )
    except Exception as exc:
        print(f"[Conversion warning] Blender conversion failed: {exc}")

    created = []
    for fmt in formats:
        fpath = exports_dir / f"model.{fmt}"
        if fpath.is_file():
            created.append(fmt)
    return created


# ==============================================================================
# 1. TRIPO3D CLOUD GENERATOR
# ==============================================================================
def generate_tripo3d_asset(
    image_path: Path,
    exports_dir: Path,
    formats: list[str],
    progress_cb: Callable[[dict], None] | None = None,
) -> dict:
    """Generate 3D model using Tripo3D REST API."""
    keys = load_keys()
    api_key = keys.get("tripo3d_key", "")
    if not api_key:
        raise ValueError(
            "Tripo3D API Key is not configured! Please click the '🔑 Keys' button or Tripo3D pill in the top bar to enter your free key (get 300–600 free credits at platform.tripo3d.ai)."
        )

    def report(msg: str):
        if progress_cb:
            progress_cb({"stage": 2, "stage_name": "Tripo3D Cloud", "message": msg})

    report("Encoding reference image for Tripo3D Cloud GPU cluster...")
    img_bytes = image_path.read_bytes()
    b64_data = base64.b64encode(img_bytes).decode("utf-8")
    ext = image_path.suffix.lstrip(".").lower() or "png"
    if ext == "jpg":
        ext = "jpeg"

    # Step 1: Create image-to-model task
    create_url = "https://api.tripo3d.ai/v2/openapi/task"
    payload = {
        "type": "image_to_model",
        "file": {
            "type": ext,
            "data": b64_data,
        },
    }
    req = urllib.request.Request(
        create_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Omni-3D-Studio/2.0",
        },
        method="POST",
    )

    try:
        report("Dispatching image-to-3d synthesis job to Tripo3D neural workers...")
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        err_body = err.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Tripo3D API error ({err.code}): {err_body}")

    if data.get("code") != 0 or "data" not in data or "task_id" not in data["data"]:
        raise RuntimeError(f"Tripo3D dispatch error: {data.get('message', 'Unknown response')}")

    task_id = data["data"]["task_id"]
    report(f"Job queued on Tripo3D cluster (Task ID: {task_id[:12]}...). Synthesizing neural geometry...")

    # Step 2: Poll task status
    poll_url = f"https://api.tripo3d.ai/v2/openapi/task/{task_id}"
    poll_headers = {
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "Omni-3D-Studio/2.0",
    }

    t0 = time.time()
    glb_url = None
    while time.time() - t0 < 300:  # 5 minutes timeout
        time.sleep(3.0)
        poll_req = urllib.request.Request(poll_url, headers=poll_headers, method="GET")
        with urllib.request.urlopen(poll_req, timeout=20) as resp:
            task_resp = json.loads(resp.read().decode("utf-8"))

        task_data = task_resp.get("data", {})
        status = task_data.get("status", "").lower()
        progress = task_data.get("progress", 0)

        report(f"Tripo3D Neural Synthesis in progress: {progress}% ({status})...")

        if status == "success":
            output = task_data.get("output", {})
            glb_url = output.get("pbr_model") or output.get("model")
            break
        elif status in ("failed", "cancelled"):
            raise RuntimeError(f"Tripo3D task {status}: {task_data.get('error', 'Generation aborted')}")

    if not glb_url:
        raise TimeoutError("Tripo3D generation timed out waiting for neural mesh.")

    # Step 3: Download finished GLB
    report("Downloading high-detail neural GLB model from Tripo3D...")
    glb_dest = exports_dir / "model.glb"
    dl_req = urllib.request.Request(glb_url, headers={"User-Agent": "Omni-3D-Studio/2.0"})
    with urllib.request.urlopen(dl_req, timeout=60) as resp:
        glb_dest.write_bytes(resp.read())

    # Step 4: Export to OBJ, STL, FBX via Blender
    if any(f in formats for f in ("obj", "stl", "fbx")):
        report("Converting neural GLB to OBJ, STL, and FBX deliverables via Blender 5.2 LTS...")
        convert_glb_to_formats(glb_dest, exports_dir, formats)

    return {"success": True, "deliverables": {fmt: exports_dir / f"model.{fmt}" for fmt in formats if (exports_dir / f"model.{fmt}").is_file()}}


# ==============================================================================
# 2. MESHY CLOUD GENERATOR
# ==============================================================================
def generate_meshy_asset(
    image_path: Path,
    exports_dir: Path,
    formats: list[str],
    progress_cb: Callable[[dict], None] | None = None,
) -> dict:
    """Generate 3D model using Meshy.ai REST API."""
    keys = load_keys()
    api_key = keys.get("meshy_key", "")
    if not api_key:
        raise ValueError(
            "Meshy.ai API Key is not configured. Note: Meshy does not provide API keys on free accounts (their 100-200 credits are web-only and API keys require a paid Pro subscription). For free cloud generation, use Tripo3D (platform.tripo3d.ai) or Hugging Face TRELLIS."
        )

    def report(msg: str):
        if progress_cb:
            progress_cb({"stage": 2, "stage_name": "Meshy Cloud", "message": msg})

    report("Encoding reference image as data URI for Meshy.ai...")
    img_bytes = image_path.read_bytes()
    b64_data = base64.b64encode(img_bytes).decode("utf-8")
    ext = image_path.suffix.lstrip(".").lower() or "png"
    if ext == "jpg":
        ext = "jpeg"
    data_uri = f"data:image/{ext};base64,{b64_data}"

    # Step 1: Create image-to-3d task
    create_url = "https://api.meshy.ai/openapi/v2/image-to-3d"
    payload = {
        "image_url": data_uri,
        "enable_pbr": True,
        "surface_mode": "organic",
    }
    req = urllib.request.Request(
        create_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Omni-3D-Studio/2.0",
        },
        method="POST",
    )

    try:
        report("Submitting job to Meshy.ai cloud GPU pipeline...")
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        err_body = err.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Meshy.ai API error ({err.code}): {err_body}")

    task_id = data.get("result")
    if not task_id:
        raise RuntimeError(f"Meshy.ai dispatch error: {data.get('message', 'No task ID returned')}")

    report(f"Job queued on Meshy.ai (Task ID: {task_id[:12]}...). Neural reconstruction running...")

    # Step 2: Poll task status
    poll_url = f"https://api.meshy.ai/openapi/v2/image-to-3d/{task_id}"
    poll_headers = {
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "Omni-3D-Studio/2.0",
    }

    t0 = time.time()
    glb_url = None
    while time.time() - t0 < 360:  # 6 minutes timeout
        time.sleep(4.0)
        poll_req = urllib.request.Request(poll_url, headers=poll_headers, method="GET")
        with urllib.request.urlopen(poll_req, timeout=20) as resp:
            task_resp = json.loads(resp.read().decode("utf-8"))

        status = task_resp.get("status", "").upper()
        progress = task_resp.get("progress", 0)

        report(f"Meshy.ai Synthesis in progress: {progress}% ({status})...")

        if status == "SUCCEEDED":
            model_urls = task_resp.get("model_urls", {})
            glb_url = model_urls.get("glb")
            break
        elif status in ("FAILED", "EXPIRED"):
            raise RuntimeError(f"Meshy task {status}: {task_resp.get('task_error', {}).get('message', 'Failed')}")

    if not glb_url:
        raise TimeoutError("Meshy generation timed out waiting for neural mesh.")

    # Step 3: Download finished GLB
    report("Downloading finished PBR neural mesh from Meshy.ai...")
    glb_dest = exports_dir / "model.glb"
    dl_req = urllib.request.Request(glb_url, headers={"User-Agent": "Omni-3D-Studio/2.0"})
    with urllib.request.urlopen(dl_req, timeout=60) as resp:
        glb_dest.write_bytes(resp.read())

    # Step 4: Export to OBJ, STL, FBX via Blender
    if any(f in formats for f in ("obj", "stl", "fbx")):
        report("Converting Meshy GLB to OBJ, STL, and FBX deliverables via Blender 5.2 LTS...")
        convert_glb_to_formats(glb_dest, exports_dir, formats)

    return {"success": True, "deliverables": {fmt: exports_dir / f"model.{fmt}" for fmt in formats if (exports_dir / f"model.{fmt}").is_file()}}


# ==============================================================================
# 3. HUGGING FACE / TRELLIS ZERO-GPU GENERATOR
# ==============================================================================
def generate_trellis_hf_asset(
    image_path: Path,
    exports_dir: Path,
    formats: list[str],
    progress_cb: Callable[[dict], None] | None = None,
) -> dict:
    """Generate 3D model using Microsoft TRELLIS on Hugging Face Spaces."""
    keys = load_keys()
    hf_token = keys.get("hf_token", "")

    def report(msg: str):
        if progress_cb:
            progress_cb({"stage": 2, "stage_name": "TRELLIS (HF)", "message": msg})

    report("Connecting to Microsoft TRELLIS space on Hugging Face ZeroGPU cluster...")

    # We call the public Gradio client API on Hugging Face space: JeffreyXiang/TRELLIS
    space_api_url = "https://jeffreyxiang-trellis.hf.space"

    headers = {"User-Agent": "Omni-3D-Studio/2.0"}
    if hf_token:
        headers["Authorization"] = f"Bearer {hf_token}"

    report("Uploading reference image to TRELLIS space...")
    img_bytes = image_path.read_bytes()
    b64_data = base64.b64encode(img_bytes).decode("utf-8")
    ext = image_path.suffix.lstrip(".").lower() or "png"
    data_uri = f"data:image/{ext};base64,{b64_data}"

    # Call gradio prediction endpoint
    call_url = f"{space_api_url}/call/image_to_3d"
    call_payload = {
        "data": [
            {"path": data_uri},  # image
            0,                     # seed
            7.5,                   # SS guidance strength
            7.5,                   # SLAT guidance strength
        ]
    }

    try:
        req = urllib.request.Request(
            call_url,
            data=json.dumps(call_payload).encode("utf-8"),
            headers={"Content-Type": "application/json", **headers},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            init_res = json.loads(resp.read().decode("utf-8"))
            event_id = init_res.get("event_id")
    except Exception as exc:
        raise RuntimeError(
            f"Failed to connect to Hugging Face TRELLIS space: {exc}. "
            "Tip: Enter a free Hugging Face User Access Token (huggingface.co/settings/tokens) in the top bar to get priority ZeroGPU access."
        )

    if not event_id:
        raise RuntimeError("No event ID returned from TRELLIS ZeroGPU queue.")

    report(f"Queued on Hugging Face ZeroGPU (Event: {event_id[:8]}...). Awaiting GPU slice...")

    # Stream SSE status from Gradio
    status_url = f"{space_api_url}/call/image_to_3d/{event_id}"
    glb_url = None
    t0 = time.time()

    status_req = urllib.request.Request(status_url, headers=headers, method="GET")
    with urllib.request.urlopen(status_req, timeout=300) as resp:
        for line in resp:
            text = line.decode("utf-8", errors="replace").strip()
            if text.startswith("event: heartbeat"):
                report("TRELLIS neural diffusion running on ZeroGPU...")
            elif text.startswith("data:"):
                try:
                    payload = json.loads(text[5:].strip())
                    if isinstance(payload, list) and len(payload) > 0:
                        # Output contains file info
                        first = payload[0]
                        if isinstance(first, dict) and "url" in first:
                            glb_url = first["url"]
                            break
                        elif isinstance(first, str) and first.endswith(".glb"):
                            glb_url = first if first.startswith("http") else f"{space_api_url}/file={first}"
                            break
                except Exception:
                    pass
            if time.time() - t0 > 300:
                break

    if not glb_url:
        raise TimeoutError("Hugging Face TRELLIS run timed out or GPU pool busy. Please retry in a few moments.")

    report("Downloading SOTA neural mesh from TRELLIS...")
    glb_dest = exports_dir / "model.glb"
    with urllib.request.urlopen(urllib.request.Request(glb_url, headers=headers), timeout=60) as resp:
        glb_dest.write_bytes(resp.read())

    # Export formats
    if any(f in formats for f in ("obj", "stl", "fbx")):
        report("Converting TRELLIS GLB to OBJ, STL, and FBX deliverables via Blender 5.2 LTS...")
        convert_glb_to_formats(glb_dest, exports_dir, formats)

    return {"success": True, "deliverables": {fmt: exports_dir / f"model.{fmt}" for fmt in formats if (exports_dir / f"model.{fmt}").is_file()}}


# ==============================================================================
# 4. LOCAL OFFLINE TRIPOSR (GTX / LOCAL NEURAL ENGINE)
# ==============================================================================
def generate_triposr_local_asset(
    image_path: Path,
    exports_dir: Path,
    formats: list[str],
    progress_cb: Callable[[dict], None] | None = None,
) -> dict:
    """Run local offline TripoSR neural reconstruction.
    
    Checks for local CUDA GPU. If running on current machine without GTX card yet,
    gracefully diagnoses GPU readiness for project transfer and executes high-resolution
    watertight Teddy Silhouette/OpenVDB engine as seamless offline fallback!
    """
    def report(msg: str):
        if progress_cb:
            progress_cb({"stage": 2, "stage_name": "Local Neural Engine", "message": msg})

    cuda_info = check_cuda_status()
    if cuda_info["has_cuda"]:
        report(f"NVIDIA GPU detected ({cuda_info['device_name']})! Running local offline TripoSR neural weights...")
        # If user transferred to their GTX PC, try invoking local TripoSR
        try:
            import torch
            from tsr.system import TSR
            report("Initializing local TSR neural pipeline on CUDA...")
            model = TSR.from_pretrained("stabilityai/TripoSR", config_name="config.yaml", weight_name="model.ckpt")
            model.to("cuda")
            report("Synthesizing neural 3D mesh locally on GTX...")
            from PIL import Image
            img = Image.open(image_path)
            with torch.no_grad():
                scene_codes = model([img], device="cuda")
            mesh = model.extract_mesh(scene_codes, resolution=256)[0]
            glb_dest = exports_dir / "model.glb"
            mesh.export(str(glb_dest))
            report("Local TripoSR neural inference complete!")
            if any(f in formats for f in ("obj", "stl", "fbx")):
                convert_glb_to_formats(glb_dest, exports_dir, formats)
            return {"success": True, "deliverables": {fmt: exports_dir / f"model.{fmt}" for fmt in formats if (exports_dir / f"model.{fmt}").is_file()}}
        except Exception as exc:
            report(f"Local TripoSR library not yet installed ({exc}). Activating High-Res Watertight Sculpt Engine...")
    else:
        report(
            "Local Engine Diagnosis: GTX GPU not detected on this machine. Ready for PC transfer! "
            "Activating Local SOTA Watertight Silhouette & UV Engine (Runs 100% offline on any CPU)..."
        )

    # Seamless fallback: Build watertight Teddy Silhouette Inflation mesh locally
    from omni_engine import build_silhouette_inflation_script, find_blender
    blender_exe = find_blender()
    script = build_silhouette_inflation_script(
        image_path=image_path,
        exports_dir=exports_dir,
        formats=formats,
        user_guidance="Local offline watertight neural reconstruction",
    )
    script_path = exports_dir.parent / "local_offline_build.py"
    script_path.write_text(script, encoding="utf-8")
    report("Compiling watertight 3D geometry headlessly in Blender 5.2 LTS...")
    subprocess.run(
        [str(blender_exe), "-b", "-P", str(script_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=120,
        text=True,
    )

    return {"success": True, "deliverables": {fmt: exports_dir / f"model.{fmt}" for fmt in formats if (exports_dir / f"model.{fmt}").is_file()}}

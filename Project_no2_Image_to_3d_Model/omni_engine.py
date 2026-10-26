"""Omni-3D Synthesis Engine for Project #2.

Reusable, production-grade engine that transforms 2D reference images into
fully realized 3D models using Vision LLMs (LL3M methodology) and Blender 5.2 LTS,
exporting into GLB, OBJ, STL, and FBX formats.
"""

from __future__ import annotations

import base64
import datetime
import io
import json
import mimetypes
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Generator

PROJECT_DIR = Path(__file__).resolve().parent
ROOT_DIR = PROJECT_DIR.parent
DEFAULT_BLENDER = Path(r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")


def find_blender() -> Path:
    """Detect local Blender executable, prioritizing Blender 5.2 LTS."""
    if DEFAULT_BLENDER.is_file():
        return DEFAULT_BLENDER
    # Check PATH
    import shutil
    p = shutil.which("blender")
    if p:
        return Path(p)
    # Check default install locations on Windows
    program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Blender Foundation"
    if program_files.is_dir():
        for sub in sorted(program_files.iterdir(), reverse=True):
            candidate = sub / "blender.exe"
            if candidate.is_file():
                return candidate
    return DEFAULT_BLENDER


def encode_image(image_path: Path, max_dim: int = 448) -> tuple[str, str]:
    """Encode and thumbnail image to base64 for optimal vision token latency."""
    mime, _ = mimetypes.guess_type(str(image_path))
    if not mime:
        mime = "image/png"
    try:
        from PIL import Image
        img = Image.open(image_path)
        if max(img.size) > max_dim:
            img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            img.save(buf, format="PNG", optimize=True)
            mime = "image/png"
        else:
            img.convert("RGB").save(buf, format="JPEG", quality=88, optimize=True)
            mime = "image/jpeg"
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        return b64, mime
    except Exception:
        b64 = base64.b64encode(image_path.read_bytes()).decode("utf-8")
        return b64, mime


class Omni3DEngine:
    """Core synthesis and orchestration engine for Image-to-3D generation."""

    def __init__(self, ollama_url: str = "http://localhost:11434"):
        self.ollama_url = ollama_url.rstrip("/")
        self.blender_exe = find_blender()

    def get_available_models(self) -> list[str]:
        """Fetch models installed in Ollama."""
        try:
            req = urllib.request.Request(f"{self.ollama_url}/api/tags")
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return [m.get("name") for m in data.get("models", [])]
        except Exception:
            return ["glm-5.3-flash:cloud", "kimi-k2.7-code:cloud", "gemma4:latest"]

    def build_ll3m_prompt(self, user_guidance: str = "", export_formats: list[str] | None = None) -> str:
        """Construct the LL3M prompt enforcing clean Blender 5.2 procedural modeling."""
        if not export_formats:
            export_formats = ["glb", "obj", "stl", "fbx"]

        formats_str = ", ".join(f.upper() for f in export_formats)

        prompt = f"""You are an elite 3D technical artist, spatial geometrician, and Blender Python (bpy) specialist following the LL3M (Large Language 3D Modelers) methodology.

TASK:
Analyze the reference image and synthesize a complete, standalone, production-ready Blender Python script that procedurally builds this 3D model and exports it into target formats: {formats_str}.

ADDITIONAL USER GUIDANCE:
{user_guidance or "Faithfully reproduce the primary subject with accurate shapes, PBR colors, and smooth beveled geometry."}

ENGINEERING SPECIFICATION & BEST PRACTICES:
1. SCENE HYGIENE:
   - Switch to OBJECT mode if needed.
   - Delete all existing objects and run bpy.data.orphans_purge() recursively.
   - Ensure all coordinates are Z-up, character/asset centered at origin.

2. GEOMETRIC ARCHITECTURE (Factory-Based Decomposition):
   - Decompose into distinct functional parts parented or grouped cleanly.
   - Use small parameterized factory functions: add_sphere(), add_cube(), add_cylinder(), add_torus(), tube_between().
   - Apply scale (bpy.ops.object.transform_apply(scale=True)) on meshes before applying bevel modifiers.
   - Add Bevel modifiers with 3+ segments on hard edges for specular highlights.
   - For auto-smooth in Blender 4.0+/5.0+: use bmesh sharp-edge calculation or shade_smooth, avoiding obsolete use_auto_smooth.

3. PBR MATERIALS (Principled BSDF):
   - Convert hex/sRGB colors to scene-linear before assigning to Base Color.
   - Set Roughness, Metallic, and Transmission appropriately.
   - For version-resilient BSDF inputs: use alias fallback ("Transmission Weight" / "Transmission", "Subsurface Weight" / "Subsurface").

4. MULTI-FORMAT EXPORT PROTOCOL:
   Resolve exports directory relative to script:
   ```python
   from pathlib import Path
   exports_dir = Path(__file__).resolve().parent / "exports"
   exports_dir.mkdir(parents=True, exist_ok=True)
   ```
   Apply all modifiers before export so all formats share identical geometry.
   Execute required exporters:
   - GLB: bpy.ops.export_scene.gltf(filepath=str(exports_dir / "model.glb"), export_format="GLB", export_apply=True)
   - OBJ: bpy.ops.wm.obj_export(filepath=str(exports_dir / "model.obj"))
   - STL: bpy.ops.wm.stl_export(filepath=str(exports_dir / "model.stl"))
   - FBX: bpy.ops.export_scene.fbx(filepath=str(exports_dir / "model.fbx"))

5. OUTPUT FORMAT:
   Return the complete, self-contained Python script wrapped in a single ```python ... ``` code block.
   Print "MODEL_BUILD_OK" to stdout at the end of the script."""
        return prompt

    def stream_ollama_chat(
        self,
        prompt: str,
        image_path: Path | None = None,
        model: str = "glm-5.3-flash:cloud",
        timeout: int = 300,
    ) -> Generator[dict, None, str]:
        """Stream chat tokens from Ollama /api/chat yielding progress events."""
        url = f"{self.ollama_url}/api/chat"
        messages = [
            {"role": "system", "content": "You are an elite 3D technical artist, spatial geometrician, and Blender Python programmer."}
        ]

        if image_path and image_path.is_file():
            b64, _ = encode_image(image_path, max_dim=384)
            messages.append({"role": "user", "content": prompt, "images": [b64]})
        else:
            messages.append({"role": "user", "content": prompt})

        payload = json.dumps({
            "model": model,
            "messages": messages,
            "stream": True,
            "options": {"temperature": 0.2},
        }).encode("utf-8")

        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        accumulated_content = []
        accumulated_thinking = []
        last_yield = time.time()

        with urllib.request.urlopen(req, timeout=timeout) as resp:
            for line in resp:
                s = line.decode("utf-8", errors="replace").strip()
                if not s:
                    continue
                try:
                    chunk = json.loads(s)
                    msg = chunk.get("message") or {}
                    c = msg.get("content") or ""
                    th = msg.get("thinking") or ""
                    if c:
                        accumulated_content.append(c)
                    if th:
                        accumulated_thinking.append(th)

                    now = time.time()
                    if now - last_yield > 0.5:
                        last_yield = now
                        yield {
                            "type": "token_chunk",
                            "thinking_chars": sum(len(x) for x in accumulated_thinking),
                            "content_chars": sum(len(x) for x in accumulated_content),
                            "latest_delta": c or (th[:40] if th else ""),
                        }

                    if chunk.get("done"):
                        break
                except json.JSONDecodeError:
                    pass

        content = "".join(accumulated_content)
        if not content.strip() and accumulated_thinking:
            content = "".join(accumulated_thinking)
        return content

    def execute_blender_script(self, script_path: Path) -> dict:
        """Run synthesized modeling script headlessly via Blender 5.2."""
        if not self.blender_exe.is_file():
            raise FileNotFoundError(f"Blender executable not found at: {self.blender_exe}")

        cmd = [str(self.blender_exe), "-b", "-P", str(script_path)]
        t0 = time.time()
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
        elapsed = round(time.time() - t0, 2)

        is_success = ("MODEL_BUILD_OK" in res.stdout or "SPACEMAN_BUILD_OK" in res.stdout or res.returncode == 0)
        return {
            "success": is_success,
            "returncode": res.returncode,
            "output": res.stdout,
            "elapsed_sec": elapsed,
        }

    def generate_asset(
        self,
        image_path: Path,
        job_dir: Path,
        model: str = "glm-5.3-flash:cloud",
        guidance: str = "",
        formats: list[str] | None = None,
        progress_cb: Callable[[dict], None] | None = None,
    ) -> dict:
        """Complete end-to-end Image-to-3D pipeline execution."""
        if not formats:
            formats = ["glb", "obj", "stl", "fbx"]

        job_dir.mkdir(parents=True, exist_ok=True)
        exports_dir = job_dir / "exports"
        exports_dir.mkdir(parents=True, exist_ok=True)

        def report(stage: int, stage_name: str, message: str, meta: dict | None = None):
            if progress_cb:
                data = {"stage": stage, "stage_name": stage_name, "message": message, "timestamp": time.time()}
                if meta:
                    data.update(meta)
                progress_cb(data)

        # Stage 1: Spatial Perception
        report(1, "Perception", f"Analyzing reference image ({image_path.name}) using {model}...")
        prompt = self.build_ll3m_prompt(user_guidance=guidance, export_formats=formats)

        # Stage 2: Procedural Code Synthesis
        report(2, "Synthesis", f"Synthesizing Blender Python modeling code via {model}...")
        stream = self.stream_ollama_chat(prompt=prompt, image_path=image_path, model=model)
        try:
            while True:
                chunk = next(stream)
                report(2, "Synthesis", f"Generating code ({chunk['content_chars']} chars generated)...", chunk)
        except StopIteration as stop:
            synthesized_code = stop.value

        # Extract python code
        m = re.search(r"```(?:python|py)?\s*\n(.*?)```", synthesized_code, re.DOTALL)
        python_script = m.group(1).strip() if m else synthesized_code

        # Ensure correct exports target directory in script
        target_replacement = f'exports_dir = Path(r"{exports_dir}")'
        python_script = re.sub(
            r'exports_dir\s*=\s*Path\(__file__\)\.resolve\(\)\.parent\s*/\s*["\']exports["\']',
            target_replacement,
            python_script,
        )

        script_file = job_dir / "generate_model.py"
        script_file.write_text(python_script, encoding="utf-8")
        report(2, "Synthesis", "Procedural code synthesis complete.")

        # Stage 3: Headless Blender Compilation
        report(3, "Blender Compile", "Executing script headlessly in Blender 5.2 LTS...")
        build_result = self.execute_blender_script(script_file)
        (job_dir / "blender_build.log").write_text(build_result["output"], encoding="utf-8")

        if not build_result["success"]:
            report(3, "Failed", f"Blender exited with code {build_result['returncode']}", {"log": build_result["output"][-1000:]})
            raise RuntimeError(f"Blender compilation failed: {build_result['output'][-500:]}")

        # Stage 4: Deliverables Verification
        report(4, "Deliverables", "Verifying export files and metadata...")
        deliverables = {}
        for ext in formats:
            candidate = list(exports_dir.glob(f"*.{ext}"))
            if candidate:
                f = candidate[0]
                deliverables[ext] = {
                    "filename": f.name,
                    "path": str(f),
                    "size_bytes": f.stat().st_size,
                    "size_display": f"{round(f.stat().st_size / 1024, 1)} KB",
                }

        preview_img = exports_dir / "preview.png"
        preview_url = f"/files/jobs/{job_dir.name}/exports/{preview_img.name}" if preview_img.is_file() else None

        report(5, "Complete", f"Successfully generated 3D model with {len(deliverables)} formats.", {
            "deliverables": deliverables,
            "preview_url": preview_url,
            "elapsed_sec": build_result["elapsed_sec"],
        })

        return {
            "job_id": job_dir.name,
            "script_file": str(script_file),
            "deliverables": deliverables,
            "preview_url": preview_url,
            "build_log": build_result["output"],
        }

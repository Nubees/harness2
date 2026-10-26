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


def extract_blender_script(llm_output: str) -> str:
    """Robustly extract the primary, complete Blender Python script from LLM output.

    Handles:
    - Multiple code blocks (filters and picks the complete script containing 'import bpy' and exporters)
    - Unclosed code blocks (where LLM hit token budget or stream finished before closing ```)
    - Direct python scripts without markdown fences
    """
    if not llm_output or not llm_output.strip():
        return ""

    # 1. Find all closed markdown code blocks
    code_blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", llm_output, re.DOTALL)
    if code_blocks:
        # Prefer blocks containing import bpy or bpy.
        bpy_blocks = [b.strip() for b in code_blocks if "import bpy" in b or "bpy." in b]
        if bpy_blocks:
            full_scripts = [b for b in bpy_blocks if "import bpy" in b]
            if full_scripts:
                # Return the longest complete script
                return max(full_scripts, key=len)
            return max(bpy_blocks, key=len)
        return max(code_blocks, key=len).strip()

    # 2. Check for unclosed code block (e.g. ```python ... EOF)
    unclosed = re.search(r"```(?:python|py)?\s*\n(.*)$", llm_output, re.DOTALL)
    if unclosed:
        code = unclosed.group(1).strip()
        if "bpy" in code or len(code) > 80:
            return code

    # 3. Fallback: search for 'import bpy'
    if "import bpy" in llm_output:
        idx = llm_output.find("import bpy")
        return llm_output[idx:].strip()

    return llm_output.strip()


def sanitize_blender_script(script: str) -> str:
    """Pre-execution auto-fixer for known Blender API hallucinations."""
    # 1. Fix parent_set with invalid KEEP_TRANSFORM enum
    script = re.sub(
        r"bpy\.ops\.object\.parent_set\(\s*type\s*=\s*['\"]OBJECT_KEEP_TRANSFORM['\"]\s*\)",
        "bpy.ops.object.parent_set(type='OBJECT', keep_transform=True)",
        script
    )
    script = re.sub(
        r"bpy\.ops\.object\.parent_set\(\s*type\s*=\s*['\"]KEEP_TRANSFORM['\"]\s*\)",
        "bpy.ops.object.parent_set(type='OBJECT', keep_transform=True)",
        script
    )

    # 2. Fix use_auto_smooth (removed in Blender 4.0+/5.0+)
    script = re.sub(r'[\w\.]+\.use_auto_smooth\s*=\s*\w+', '# use_auto_smooth deprecated in Blender 5.x', script)

    # 3. Fix legacy OBJ/STL exporter calls if any
    script = re.sub(
        r"bpy\.ops\.export_scene\.obj\(\s*filepath\s*=\s*([^,\)]+)[^\)]*\)",
        r"bpy.ops.wm.obj_export(filepath=\1)",
        script
    )
    script = re.sub(
        r"bpy\.ops\.export_mesh\.stl\(\s*filepath\s*=\s*([^,\)]+)[^\)]*\)",
        r"bpy.ops.wm.stl_export(filepath=\1)",
        script
    )

    # 4. Ensure fundamental imports
    if "import bpy" not in script:
        script = "import bpy\nimport math\nfrom pathlib import Path\nfrom mathutils import Vector, Euler, Matrix\n" + script
    elif "from mathutils import" not in script and any(k in script for k in ("Vector(", "Euler(", "Matrix(")):
        script = "from mathutils import Vector, Euler, Matrix\n" + script

    return script


def inject_exports_dir(python_script: str, exports_dir: Path) -> str:
    """Safely inject or overwrite exports_dir in the generated script with posix path."""
    exports_posix = exports_dir.resolve().as_posix()
    target_statement = f'exports_dir = Path("{exports_posix}")'

    pattern = r'exports_dir\s*=\s*Path\(__file__\)\.resolve\(\)\.parent\s*/\s*["\']exports["\']'
    if re.search(pattern, python_script):
        python_script = re.sub(pattern, lambda _: target_statement, python_script, count=1)
    elif re.search(r'exports_dir\s*=\s*Path\([^\)]+\)', python_script):
        python_script = re.sub(r'exports_dir\s*=\s*Path\([^\)]+\)', lambda _: target_statement, python_script, count=1)
    else:
        python_script = f'from pathlib import Path\n{target_statement}\nexports_dir.mkdir(parents=True, exist_ok=True)\n' + python_script

    return python_script


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

    def analyze_image_guidance(self, image_path: Path, model: str = "glm-5.3-flash:cloud") -> str:
        """Auto-generate stylistic and anatomical 3D modeling guidance from reference image."""
        prompt = (
            "Analyze this reference image for a 3D technical artist and Blender modeler. "
            "Write a concise, 2-3 sentence stylistic and anatomical 3D modeling guidance note describing: "
            "1. Subject shape, silhouette, and proportions (e.g. chibi cartoon, hard-surface, realistic). "
            "2. Key anatomical and functional parts to model. "
            "3. PBR materials and colors (e.g. metallic, matte, glass transmission, emission). "
            "Keep it direct and actionable for procedural 3D modeling."
        )
        stream = self.stream_ollama_chat(prompt=prompt, image_path=image_path, model=model, timeout=120)
        try:
            while True:
                next(stream)
        except StopIteration as stop:
            return stop.value.strip()

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
   - For parenting: assign child.parent = root directly, or call bpy.ops.object.parent_set(type='OBJECT', keep_transform=True). Never use invalid 'OBJECT_KEEP_TRANSFORM'.

3. PBR MATERIALS (Principled BSDF):
   - Convert hex/sRGB colors to scene-linear before assigning to Base Color.
   - Set Roughness, Metallic, and Transmission appropriately.
   - For version-resilient BSDF inputs: use alias fallback ("Transmission Weight" / "Transmission", "Subsurface Weight" / "Subsurface").

4. MULTI-FORMAT EXPORT PROTOCOL:
   Resolve exports directory relative to script:
   exports_dir = Path(__file__).resolve().parent / "exports"
   exports_dir.mkdir(parents=True, exist_ok=True)
   Apply all modifiers before export so all formats share identical geometry.
   Execute required exporters:
   - GLB: bpy.ops.export_scene.gltf(filepath=str(exports_dir / "model.glb"), export_format="GLB", export_apply=True)
   - OBJ: bpy.ops.wm.obj_export(filepath=str(exports_dir / "model.obj"))
   - STL: bpy.ops.wm.stl_export(filepath=str(exports_dir / "model.stl"))
   - FBX: bpy.ops.export_scene.fbx(filepath=str(exports_dir / "model.fbx"))

5. STRICT OUTPUT FORMAT (CRITICAL):
   - Output EXACTLY ONE single Python code block enclosed in ```python ... ```.
   - Do NOT output any preliminary snippets, multiple code blocks, or markdown explanations.
   - The script must be completely self-contained from `import bpy` to export and `print("MODEL_BUILD_OK")`."""
        return prompt

    def stream_ollama_chat(
        self,
        prompt: str,
        image_path: Path | None = None,
        model: str = "glm-5.3-flash:cloud",
        timeout: int = 600,
    ) -> Generator[dict, None, str]:
        """Stream chat tokens from Ollama /api/chat yielding progress events."""
        url = f"{self.ollama_url}/api/chat"
        messages = [
            {
                "role": "system",
                "content": (
                    "You are an elite 3D technical artist, spatial geometrician, and Blender Python programmer.\n"
                    "CRITICAL: Keep internal reasoning extremely brief (under 80 words). "
                    "Immediately write and output the complete, self-contained, runnable Blender Python script wrapped in a single ```python ... ``` block. "
                    "Do NOT output markdown essays, monologues, or separate snippets."
                ),
            }
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
            "options": {
                "temperature": 0.2,
                "num_ctx": 16384,
                "num_predict": 8192,
            },
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
        # Only fallback to thinking if it actually contains python code
        if not content.strip() and accumulated_thinking:
            joined_th = "".join(accumulated_thinking)
            if "import bpy" in joined_th:
                content = joined_th
        return content

    def execute_blender_script(self, script_path: Path) -> dict:
        """Run synthesized modeling script headlessly via Blender 5.2."""
        if not self.blender_exe.is_file():
            raise FileNotFoundError(f"Blender executable not found at: {self.blender_exe}")

        cmd = [str(self.blender_exe), "-b", "-P", str(script_path)]
        t0 = time.time()
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
        elapsed = round(time.time() - t0, 2)

        has_traceback = ("Traceback (most recent call last):" in res.stdout or "Error: Python:" in res.stdout)
        has_build_ok = ("MODEL_BUILD_OK" in res.stdout or "SPACEMAN_BUILD_OK" in res.stdout)
        is_success = (res.returncode == 0 and not has_traceback) or has_build_ok
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
                co = chunk.get("content_chars", 0)
                th = chunk.get("thinking_chars", 0)
                if co > 0:
                    msg = f"Synthesizing Blender Python code ({co:,} chars)..."
                elif th > 0:
                    msg = f"Reasoning 3D geometry & anatomy ({th:,} chars)..."
                else:
                    msg = "Model initializing..."
                report(2, "Synthesis", msg, chunk)
        except StopIteration as stop:
            synthesized_code = stop.value

        # Persist full raw LLM response for auditability & debugging
        (job_dir / "raw_llm_response.txt").write_text(synthesized_code, encoding="utf-8")

        # Robustly extract the full Blender Python script (handles multiple blocks & unclosed blocks)
        python_script = extract_blender_script(synthesized_code)

        # If the first attempt produced no code (e.g. reasoning hit token limit), automatically retry once with direct code prompt
        if not python_script or "import bpy" not in python_script:
            report(2, "Synthesis", "Reasoning completed without code. Retrying direct code synthesis...")
            retry_prompt = prompt + "\n\nCRITICAL INSTRUCTION: Output ONLY the complete runnable Python script starting with ```python\nimport bpy. Do not include chain-of-thought or markdown essays."
            stream = self.stream_ollama_chat(prompt=retry_prompt, image_path=image_path, model=model)
            try:
                while True:
                    chunk = next(stream)
                    co = chunk.get("content_chars", 0)
                    if co > 0:
                        report(2, "Synthesis", f"Synthesizing Blender Python code ({co:,} chars)...", chunk)
            except StopIteration as stop:
                synthesized_code = stop.value
            (job_dir / "raw_llm_response_retry.txt").write_text(synthesized_code, encoding="utf-8")
            python_script = extract_blender_script(synthesized_code)

        if not python_script or "import bpy" not in python_script:
            report(2, "Failed", "LLM did not return a valid Blender Python modeling script.")
            raise RuntimeError("No valid Blender Python script found in LLM response.")

        # Sanitize known Blender API hallucinations & inject target exports_dir
        python_script = sanitize_blender_script(python_script)
        python_script = inject_exports_dir(python_script, exports_dir)

        script_file = job_dir / "generate_model.py"
        script_file.write_text(python_script, encoding="utf-8")
        report(2, "Synthesis", "Procedural code synthesis complete.")

        # Stage 3: Headless Blender Compilation
        report(3, "Blender Compile", "Executing script headlessly in Blender 5.2 LTS...")
        build_result = self.execute_blender_script(script_file)
        (job_dir / "blender_build.log").write_text(build_result["output"], encoding="utf-8")

        # Self-Healing Retry Loop (Autonomous Harnessing)
        if not build_result["success"]:
            err_lines = [l for l in build_result["output"].splitlines() if "Error" in l or "Traceback" in l or "File " in l]
            summary = "\n".join(err_lines[-5:]) if err_lines else build_result["output"][-400:]
            report(3, "Self-Healing", f"Blender reported error:\n{summary}\nAutonomously repairing script...")

            repair_prompt = f"""The following Blender Python script produced an execution error in Blender 5.2 LTS:

ERROR:
{summary}

ORIGINAL SCRIPT:
```python
{python_script}
```

TASK:
Fix the error in the script. Ensure all syntax, operators, and imports are 100% valid for Blender 5.2 LTS.
Output ONLY the complete corrected script wrapped in a single ```python ... ``` code block without preamble or explanation."""

            stream = self.stream_ollama_chat(prompt=repair_prompt, image_path=None, model=model)
            try:
                while True:
                    next(stream)
            except StopIteration as stop:
                repaired_code = stop.value

            (job_dir / "raw_llm_response_repair.txt").write_text(repaired_code, encoding="utf-8")
            repaired_script = extract_blender_script(repaired_code)
            if repaired_script and "import bpy" in repaired_script:
                repaired_script = sanitize_blender_script(repaired_script)
                repaired_script = inject_exports_dir(repaired_script, exports_dir)
                script_file.write_text(repaired_script, encoding="utf-8")

                report(3, "Blender Compile", "Re-executing repaired script in Blender 5.2 LTS...")
                build_result = self.execute_blender_script(script_file)
                (job_dir / "blender_build.log").write_text(build_result["output"], encoding="utf-8")

        if not build_result["success"]:
            err_lines = [l for l in build_result["output"].splitlines() if "Error" in l or "Traceback" in l or "File " in l]
            summary = "\n".join(err_lines[-5:]) if err_lines else build_result["output"][-400:]
            report(3, "Failed", f"Blender compilation failed:\n{summary}", {"log": build_result["output"][-1000:]})
            raise RuntimeError(f"Blender script execution failed:\n{summary}")

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

        # Crucial gate: If no files were exported, the generation was NOT successful
        if not deliverables or ("glb" in formats and "glb" not in deliverables):
            err_msg = "Blender execution finished but failed to create export files (no .glb found in exports/)."
            report(4, "Failed", err_msg, {"log": build_result["output"][-1000:]})
            raise RuntimeError(err_msg)

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

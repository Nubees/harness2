"""Custom Task Dispatcher for Harness².

Takes a user task/problem, executes an autonomous Propose-Probe-Compose cycle
powered by Ollama, outputs the refined solution, and triggers the Knowledge Bridge
to sync learned lessons to GEMINI.md (Antigravity) and CLAUDE.md (Claude Code).
"""

from __future__ import annotations

import argparse
import atexit
import base64
import datetime
import json
import mimetypes
import os
import re
import signal
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
BASE_HARNESS_DIR = ROOT / "third_party" / "jb_runner" / "harness_baseline_oc"
RUNS_ROOT = ROOT / "runs" / "custom"
TELEMETRY_FILE = ROOT / "runs" / "telemetry_status.json"
MAX_FILE_CONTEXT_CHARS = 40_000

_ACTIVE_TASK: dict | None = None


def _cleanup_telemetry():
    global _ACTIVE_TASK
    if _ACTIVE_TASK and _ACTIVE_TASK.get("status") == "RUNNING":
        update_telemetry(
            status="CANCELLED",
            task_id=_ACTIVE_TASK.get("task_id", ""),
            objective=_ACTIVE_TASK.get("objective", ""),
            model=_ACTIVE_TASK.get("model", ""),
            stage=_ACTIVE_TASK.get("stage", 0),
            stage_name="Cancelled",
            details="Process terminated unexpectedly",
            start_time=_ACTIVE_TASK.get("start_time"),
        )


atexit.register(_cleanup_telemetry)


def update_telemetry(
    status: str,
    task_id: str = "",
    objective: str = "",
    model: str = "",
    stage: int = 0,
    stage_name: str = "",
    details: str = "",
    start_time: float | None = None,
) -> None:
    global _ACTIVE_TASK
    _ACTIVE_TASK = {
        "status": status,
        "task_id": task_id,
        "objective": objective,
        "model": model,
        "stage": stage,
        "stage_name": stage_name,
        "start_time": start_time,
    }
    try:
        now = time.time()
        elapsed = round(now - start_time, 1) if start_time else 0
        data = {
            "night_shift": {
                "status": status,
                "task_id": task_id,
                "objective": objective,
                "model": model,
                "stage": stage,
                "stage_name": stage_name,
                "details": details,
                "pid": os.getpid(),
                "start_time": start_time,
                "elapsed_sec": elapsed,
                "updated_at": datetime.datetime.now().isoformat(),
            }
        }
        TELEMETRY_FILE.parent.mkdir(parents=True, exist_ok=True)
        temp_p = TELEMETRY_FILE.with_suffix(".tmp")
        temp_p.write_text(json.dumps(data, indent=2), encoding="utf-8")
        temp_p.replace(TELEMETRY_FILE)
    except Exception:
        pass


def encode_image_b64(image_path: Path, max_dim: int = 512) -> tuple[str, str]:
    mime, _ = mimetypes.guess_type(str(image_path))
    if not mime:
        mime = "image/png"
    try:
        from PIL import Image
        import io
        img = Image.open(image_path)
        if max(img.size) > max_dim:
            img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            img.save(buf, format="PNG", optimize=True)
            mime = "image/png"
        else:
            img.convert("RGB").save(buf, format="JPEG", quality=85, optimize=True)
            mime = "image/jpeg"
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        return b64, mime
    except Exception:
        b64 = base64.b64encode(image_path.read_bytes()).decode("utf-8")
        return b64, mime


def call_ollama_chat(
    prompt: str,
    system: str = "",
    model: str = "kimi-k2.7-code:cloud",
    base_url: str = "http://localhost:11434/v1",
    retries: int = 3,
    timeout: int = 180,
    image_path: Path | str | None = None,
) -> str:
    url = base_url.rstrip("/") + "/chat/completions"
    messages = []
    if system:
        messages.append({"role": "system", "content": system})

    if image_path and Path(image_path).is_file():
        img_p = Path(image_path)
        b64, mime = encode_image_b64(img_p)
        user_content = [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
        ]
        messages.append({"role": "user", "content": user_content})
    else:
        messages.append({"role": "user", "content": prompt})

    payload_dict = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "stream": True,
    }
    payload = json.dumps(payload_dict).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                content_type = resp.headers.get("Content-Type", "")
                if "event-stream" in content_type or True:  # streaming mode
                    accumulated = []
                    for line in resp:
                        s = line.decode("utf-8", errors="replace").strip()
                        if not s or s == "data: [DONE]":
                            continue
                        if s.startswith("data: "):
                            raw_json = s[6:]
                            try:
                                chunk = json.loads(raw_json)
                                choices = chunk.get("choices") or []
                                if choices:
                                    delta = choices[0].get("delta") or {}
                                    c = delta.get("content") or ""
                                    if c:
                                        accumulated.append(c)
                            except json.JSONDecodeError:
                                pass
                        elif s.startswith("{"):
                            try:
                                body = json.loads(s)
                                choices = body.get("choices") or []
                                if choices:
                                    return (choices[0].get("message") or {}).get("content") or ""
                            except json.JSONDecodeError:
                                pass
                    return "".join(accumulated)
                else:
                    body = json.loads(resp.read().decode("utf-8"))
                    choices = body.get("choices") or []
                    if choices:
                        return (choices[0].get("message") or {}).get("content") or ""
                    return ""
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode("utf-8", errors="replace")
            print(f"  [ERROR] Ollama HTTP {e.code} (attempt {attempt}/{retries}): {err_msg[:200]}")
            if e.code in (404, 400, 410):
                raise RuntimeError(f"Ollama model error ({e.code}): {err_msg[:200]}")
            if attempt == retries:
                raise
        except (urllib.error.URLError, TimeoutError) as e:
            print(f"  [WARNING] Ollama connection failure (attempt {attempt}/{retries}): {e}")
            if attempt == retries:
                raise RuntimeError(f"Could not connect to Ollama at {base_url}. Ensure Ollama is running.")
        time.sleep(2 * attempt)
    return ""


def dispatch_custom_task(
    task_description: str,
    target_file: Path | None = None,
    image_path: Path | None = None,
    output_file: Path | None = None,
    model: str = "kimi-k2.7-code:cloud",
    k: int = 1,
    base_url: str = "http://localhost:11434/v1",
) -> dict:
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_slug = re.sub(r"[^a-zA-Z0-9_]+", "_", task_description[:30]).strip("_").lower()
    task_id = f"task_{safe_slug}_{timestamp}"
    task_dir = RUNS_ROOT / task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 65)
    print(f"  [NIGHT SHIFT] HARNESS² AUTONOMOUS TASK RUNNER")
    print("=" * 65)
    print(f"Task ID:    {task_id}")
    print(f"Model:      {model}")
    print(f"Objective:  {task_description}")
    if image_path:
        print(f"Image Ref:  {image_path}")
    print(f"Directory:  {task_dir}")
    print("=" * 65 + "\n")

    # Read target file context if provided, with safe bounding
    context_text = ""
    if target_file and target_file.is_file():
        file_body = target_file.read_text(encoding="utf-8", errors="replace")
        if len(file_body) > MAX_FILE_CONTEXT_CHARS:
            file_body = file_body[:MAX_FILE_CONTEXT_CHARS] + "\n... [truncated for context limit]"
        context_text = f"\n\n# Context File: {target_file.name}\n```\n{file_body}\n```"

    # Step 1: Base Rollout
    t_start = time.time()
    current_stage = 1
    update_telemetry("RUNNING", task_id, task_description, model, stage=1, stage_name="Propose", details="Running Base Rollout...", start_time=t_start)
    print("[1/4] Running Initial Base Rollout...")
    base_prompt = f"Solve the following task:\n{task_description}{context_text}\n\nProvide the complete working solution and explanation."
    t0 = time.time()
    try:
        base_solution = call_ollama_chat(
            base_prompt,
            system="You are an expert autonomous software engineer and 3D graphics specialist.",
            model=model,
            base_url=base_url,
            image_path=image_path,
        )
        if not base_solution.strip():
            raise RuntimeError("Base rollout returned empty response from model.")
        (task_dir / "base_solution.md").write_text(base_solution, encoding="utf-8")
        print(f"  -> Base solution generated in {time.time()-t0:.1f}s")

        # Step 2: Propose Improvements & Probe (supports K budgets)
        current_stage = 2
        update_telemetry("RUNNING", task_id, task_description, model, stage=2, stage_name="Probe", details=f"Probing {k} candidate critiques...", start_time=t_start)
        print(f"\n[2/4] Proposing Harness Refinements (Exploring {k} candidates)...")
        candidate_critiques = []
        solution_preview = base_solution if len(base_solution) <= 25000 else (base_solution[:25000] + "\n... [truncated for prompt length]")
        for i in range(1, k + 1):
            focus = "General robustness, performance, visual accuracy, and clean architecture" if i == 1 else f"Domain-specific edge cases, rendering artifacts, and styling fidelity (Pass {i})"
            propose_prompt = f"""Review the initial solution for the task below:
TASK:
{task_description}

INITIAL SOLUTION:
{solution_preview}

Focus area: {focus}
Identify potential flaws, edge cases, visual discrepancies, missing error-handling, or performance bugs.
Propose a refined, bulletproof approach that addresses these gaps."""
            critique = call_ollama_chat(
                propose_prompt,
                system="You are a senior principal code reviewer, graphics engineer, and harness architect.",
                model=model,
                base_url=base_url,
            )
            (task_dir / f"candidate_critique_{i}.md").write_text(critique, encoding="utf-8")
            candidate_critiques.append(critique)
            print(f"  -> Candidate {i}/{k} analyzed.")

        all_critiques = "\n\n---\n\n".join(candidate_critiques)

        # Step 3: Compose Winning Solution
        current_stage = 3
        update_telemetry("RUNNING", task_id, task_description, model, stage=3, stage_name="Compose", details="Composing Winning Solution...", start_time=t_start)
        print("\n[3/4] Composing Final Optimized Deliverable...")
        compose_prompt = f"""Using the initial solution and the architectural critiques below, synthesize the definitive, optimal final solution for the task:

TASK:
{task_description}

INITIAL BASE SOLUTION:
{solution_preview}

CRITIQUES & PROPOSED REFINEMENTS:
{all_critiques}

Output the complete, self-contained, production-ready solution."""

        final_solution = call_ollama_chat(
            compose_prompt,
            system="You are an elite code synthesizer and 3D graphics specialist.",
            model=model,
            base_url=base_url,
            image_path=image_path,
        )
        final_path = task_dir / "deliverable.md"
        final_path.write_text(final_solution, encoding="utf-8")
        print(f"  -> Final deliverable saved to {final_path.name}")

        if output_file:
            m = re.search(r"```(?:html|javascript|js|typescript|ts|python|py)?\s*\n(.*?)```", final_solution, re.DOTALL)
            extracted_code = m.group(1).strip() if m else final_solution
            out_p = Path(output_file)
            out_p.parent.mkdir(parents=True, exist_ok=True)
            out_p.write_text(extracted_code, encoding="utf-8")
            print(f"  -> Extracted code saved to {out_p}")

        # Step 4: Reflect & Extract Lesson for Knowledge Base
        current_stage = 4
        update_telemetry("RUNNING", task_id, task_description, model, stage=4, stage_name="Reflect", details="Extracting lessons & syncing knowledge...", start_time=t_start)
        print("\n[4/4] Reflecting and Extracting Lesson for Assistant Sync...")
        reflect_prompt = f"""Analyze the contrast between the base solution and the composed solution for this task:
TASK: {task_description}

Extract a concise, high-value lesson for future AI assistants tackling similar problems.
Format your reply strictly as:
<experience>
cue: <Specific situation or task trigger where this applies>
lesson: <Direct, actionable rule or guideline to follow>
evidence: <Why this refinement improved the final result>
confidence: high
</experience>"""

        reflection_text = call_ollama_chat(reflect_prompt, system="You are an experience reflector.", model=model, base_url=base_url)
        (task_dir / "reflection.md").write_text(reflection_text, encoding="utf-8")

        # Write summary.json for knowledge bridge
        summary_data = {
            "task_id": task_id,
            "objective": task_description,
            "model": model,
            "timestamp": timestamp,
            "modes": {
                "parallel": {
                    "stages": [
                        {
                            "label": "critique_compose",
                            "notes": reflection_text,
                        }
                    ]
                }
            },
        }
        (task_dir / "summary.json").write_text(json.dumps(summary_data, indent=2), encoding="utf-8")

        # Step 5: Automatically Trigger Knowledge Sync
        print("\n[Sync] Triggering Knowledge Bridge to update GEMINI.md and CLAUDE.md...")
        try:
            from . import sync_knowledge
        except (ImportError, ValueError):
            import sync_knowledge

        synced_count = sync_knowledge.sync_all(RUNS_ROOT)

        update_telemetry("COMPLETED", task_id, task_description, model, stage=4, stage_name="Complete", details=f"Complete! Deliverable at {final_path.name}", start_time=t_start)
    except Exception as e:
        update_telemetry("FAILED", task_id, task_description, model, stage=current_stage, stage_name="Failed", details=str(e), start_time=t_start)
        raise
    print("\n" + "=" * 65)
    print(f"  TASK COMPLETE!")
    print(f"  Deliverable: {final_path}")
    print(f"  Learned lessons synced: {synced_count}")
    print("=" * 65 + "\n")

    return {
        "task_id": task_id,
        "deliverable_path": str(final_path),
        "deliverable_content": final_solution,
        "reflection": reflection_text,
    }


def main():
    parser = argparse.ArgumentParser(description="Dispatch a custom task into the Harness² autonomous recursive loop.")
    parser.add_argument("--task", type=str, required=True, help="Task description or objective")
    parser.add_argument("--file", type=Path, default=None, help="Optional target file context")
    parser.add_argument("--image", type=Path, default=None, help="Optional image file for multimodal vision tasks")
    parser.add_argument("--output", type=Path, default=None, help="Optional path to save extracted code output")
    parser.add_argument("--model", type=str, default=os.environ.get("OLLAMA_MODEL", "kimi-k2.7-code:cloud"), help="Ollama model")
    parser.add_argument("--k", type=int, default=1, help="Recursion scale budget")
    args = parser.parse_args()

    dispatch_custom_task(
        task_description=args.task,
        target_file=args.file,
        image_path=args.image,
        output_file=args.output,
        model=args.model,
        k=args.k,
    )


if __name__ == "__main__":
    main()

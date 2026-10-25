"""Custom Task Dispatcher for Harness².

Takes a user task/problem, executes an autonomous Propose-Probe-Compose cycle
powered by Ollama, outputs the refined solution, and triggers the Knowledge Bridge
to sync learned lessons to GEMINI.md (Antigravity) and CLAUDE.md (Claude Code).
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
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
MAX_FILE_CONTEXT_CHARS = 40_000


def call_ollama_chat(
    prompt: str,
    system: str = "",
    model: str = "kimi-k2.7-code:cloud",
    base_url: str = "http://localhost:11434/v1",
    retries: int = 3,
    timeout: int = 180,
) -> str:
    url = base_url.rstrip("/") + "/chat/completions"
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = json.dumps({"model": model, "messages": messages, "temperature": 0.2}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
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
    print("[1/4] Running Initial Base Rollout...")
    base_prompt = f"Solve the following task:\n{task_description}{context_text}\n\nProvide the complete working solution and explanation."
    t0 = time.time()
    base_solution = call_ollama_chat(base_prompt, system="You are an expert autonomous software engineer.", model=model, base_url=base_url)
    if not base_solution.strip():
        raise RuntimeError("Base rollout returned empty response from model.")
    (task_dir / "base_solution.md").write_text(base_solution, encoding="utf-8")
    print(f"  -> Base solution generated in {time.time()-t0:.1f}s")

    # Step 2: Propose Improvements & Probe (supports K budgets)
    print(f"\n[2/4] Proposing Harness Refinements (Exploring {k} candidates)...")
    candidate_critiques = []
    for i in range(1, k + 1):
        focus = "General robustness, performance, and clean architecture" if i == 1 else f"Domain-specific edge cases, boundary conditions, and failure resilience (Pass {i})"
        propose_prompt = f"""Review the initial solution for the task below:
TASK:
{task_description}

INITIAL SOLUTION:
{base_solution[:2000]}

Focus area: {focus}
Identify potential flaws, edge cases, missing error-handling, or performance bugs.
Propose a refined, bulletproof approach that addresses these gaps."""
        critique = call_ollama_chat(propose_prompt, system="You are a senior principal code reviewer and harness architect.", model=model, base_url=base_url)
        (task_dir / f"candidate_critique_{i}.md").write_text(critique, encoding="utf-8")
        candidate_critiques.append(critique)
        print(f"  -> Candidate {i}/{k} analyzed.")

    all_critiques = "\n\n---\n\n".join(candidate_critiques)

    # Step 3: Compose Winning Solution
    print("\n[3/4] Composing Final Optimized Deliverable...")
    compose_prompt = f"""Using the initial solution and the architectural critique below, synthesize the definitive, optimal final solution for the task:

TASK:
{task_description}

CRITIQUES & PROPOSED REFINEMENTS:
{all_critiques}

Output the final, polished, production-ready solution."""

    final_solution = call_ollama_chat(compose_prompt, system="You are an elite code synthesizer.", model=model, base_url=base_url)
    final_path = task_dir / "deliverable.md"
    final_path.write_text(final_solution, encoding="utf-8")
    print(f"  -> Final deliverable saved to {final_path.name}")

    # Step 4: Reflect & Extract Lesson for Knowledge Base
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
    parser.add_argument("--model", type=str, default=os.environ.get("OLLAMA_MODEL", "kimi-k2.7-code:cloud"), help="Ollama model")
    parser.add_argument("--k", type=int, default=1, help="Recursion scale budget")
    args = parser.parse_args()

    dispatch_custom_task(args.task, args.file, args.model, args.k)


if __name__ == "__main__":
    main()

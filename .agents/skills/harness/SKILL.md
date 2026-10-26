---
name: harness
description: Dispatches complex, multi-step, or tough tasks to the Harness² autonomous recursive engine (Night Shift) using Ollama, and automatically synchronizes learned lessons into GEMINI.md and CLAUDE.md.
---

# Harness² Autonomous Task Dispatcher

Use this skill when the user asks to solve a complex coding task, optimize a script, or run a problem through the Harness² autonomous engine. Also proactively suggest this skill when encountering intricate algorithmic challenges, parsing errors, or tasks with complex edge cases.

## Workflow

### 1. Model Confirmation
Before dispatching the task, list the available Ollama models (such as `glm-5.3-flash:cloud`, `deepseek-v4.1-flash:cloud`, `minimax-m3.1-flash:cloud`, `kimi-k2.7-code:cloud`, `qwen3-coder:480b-cloud`, `qwen3.8:27b-mtp-q4_K_M`, or local weights) and ask the user which model to assign:
> "Which Ollama model should we assign for this task?
> - `glm-5.3-flash:cloud` (High-speed flash cloud model)
> - `deepseek-v4.1-flash:cloud` (Fast reasoning & code flash model)
> - `minimax-m3.1-flash:cloud` (Long-context flash model)
> - `kimi-k2.7-code:cloud` (Default high-speed coding cloud model)
> - `qwen3-coder:480b-cloud` (Massive repository coding model)
> - `qwen3.8:27b-mtp-q4_K_M` (High-throughput MTP model)
> - Local on-device model (e.g. `gemma4:latest`, `qwen3.5:4b`)"

### 2. Dispatch Task
Run the task dispatcher in the background using `run_command`:
```cmd
.venv\Scripts\python scripts/dispatch_task.py --task "<task_description>" --model <selected_model>
```
*Live Telemetry:* You and the user can track real-time recursion progress (Propose -> Probe -> Compose -> Reflect) live at `http://localhost:8765/dashboard` (served by `scripts/telemetry_server.py` or `start_dashboard.bat`).

### 3. Automatic Learning & Assistant Sync
The dispatcher executes the recursive Propose–Probe–Compose cycle:
1. Base solution rollout.
2. Candidate critiques & refinements.
3. Final composition saved to `runs/custom/<task_id>/deliverable.md`.
4. Reflection lesson extracted and automatically appended to:
   - `GEMINI.md` (for Antigravity)
   - `CLAUDE.md` (for Claude Code CLI)
   - `scripts/` (for reusable utility tools)

### 4. Report Results to User
Inform the user when the background run completes, present the deliverable path, and highlight the new lesson added to `GEMINI.md` and `CLAUDE.md`.

# Project Memory: Harness² (Google Research)

## Project Summary
- **Repo:** `google-research/harness2` (arXiv:2610.14224).
- **Domain:** Recursive agent harnessing for fixed-weight foundation models.
- **Key Concepts:**
  - Task-level recursion (Propose-Probe-Compose cycle across $K$ budgets; parallel or sequential).
  - Harnessing-level recursion (persistent lesson accumulation in improvement library).
  - 8 editable components: system prompts, guardrails, memory, tool guidance, subagents, skills, scripts, plugins.
  - Substrates: OpenCode (`oc`) and Codex (`cx`).
  - Benchmarks: JobBench (`jb`), LAB (`lab`), WorkBuddy-Bench (`wb`).

## Dual-Shift Architecture (Antigravity & Claude Code Integration)
- **Day Shift (Overseeing Chat AI):** Antigravity acts as the conversational architect and project manager, identifying tough/complex tasks.
- **Night Shift (Autonomous Engine):** Harness² runs in the background powered by **Ollama** (zero Google Cloud / Vertex AI costs), exploring candidate harnesses, probing executions, and synthesizing solutions.
- **Dual Knowledge Bridge (`scripts/sync_knowledge.py`):** Automatically synchronizes reflection lessons and newly discovered rules into:
  - `GEMINI.md` (read by Antigravity).
  - `CLAUDE.md` (read by Claude Code CLI).
- **Custom Task Dispatcher (`scripts/dispatch_task.py`):** Runs autonomous recursive optimization on custom user tasks without benchmark dependencies.
- **Antigravity Skill (`.agents/skills/harness/SKILL.md`):** Allows Antigravity to suggest or dispatch tasks directly from chat with model selection.

## Environment & Setup (Windows)
- **Runtime:** Python 3.12 managed via `uv` in `.venv`.
- **Install command:** `uv pip install -e ".[render]"`
- **Cross-Platform Patches Applied:**
  - `harness2/core/schedule.py`: Added safe import fallback for Unix-specific `fcntl` file locks.
  - `harness2/core/tree.py`: Normalized `p.relative_to(...)` to `.as_posix()` to prevent Windows backslash path mismatches on the editable component surface.
- **Multi-Agent Verification:**
  - Unit tests: `python -m unittest tests/test_workflow.py` (5/5 passing).
  - Deterministic demo: `harness2-demo --output runs/demo --k 2` (2/2 tasks completed, 0 failed).
  - Critic Audit: Resolved Ollama retry/timeout handling, date-drift duplication in sync, and non-interactive input parsing.

## Startup & Tool Scripts
- `start.bat`: General launcher (auto `.venv` provisioning, tests, checks, demo, activated shell).
- `start_ollama.bat`: Full-featured launcher with interactive CLI chat (`scripts/harness_chat.py`), model detection, and task execution.
- `start_google.bat`: Configured for Google Cloud Vertex AI (ADC credentials, project detection, Gemini 2.5 Flash).
- `scripts/select_ollama_model.ps1`: Dynamic Ollama scanner categorizing local weights and cloud models (`glm-5.3-flash:cloud`, `deepseek-v4.1-flash:cloud`, `minimax-m3.1-flash:cloud`, `qwen3.8:27b-mtp-q4_K_M`, `qwen3-coder:480b-cloud`, `deepseek-v3.1:671b-cloud`, `kimi-k2.7-code:cloud`, `gpt-oss:120b-cloud`).
- `scripts/harness_chat.py`: Interactive CLI chat with active harness rules and system prompt.

## Autonomous Lessons (Harness² Knowledge Base)

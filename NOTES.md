# Harness²: Project Notes & Dual-Assistant Architecture

## 1. Project Purpose & Architecture
**Harness²** (Google Research, [arXiv:2610.14224](https://arxiv.org/abs/2610.14224)) is an autonomous framework for **recursive agent harnessing in an open world**. Rather than updating foundation model weights, it optimizes the surrounding scaffold:

- **8 Editable Components:** `systemprompt.md`, `guardrails.md`, `LongTermMEMORY.md`, `tool_descriptions/tool_guidance.md`, `sub_agents/`, `skills/`, `scripts/`, `plugin/`.
- **Task-Level Recursion:** Propose–Probe–Compose cycles ($K$ budgets; parallel or sequential). Proposes harness edits, probes them on the active task, and composes refinements from behavioral contrasts without ground-truth feedback.
- **Harnessing-Level Recursion:** Accumulates adopted harnesses and lessons in a persistent improvement library across subsequent tasks.
- **Substrates:** OpenCode (`oc`) and Codex (`cx`).
- **Original Academic Benchmarks:** JobBench (`jb`), LAB (`lab`), WorkBuddy-Bench (`wb`).

---

## 2. New Architectural Direction: Antigravity + Claude Code Bridge

We are extending Harness² beyond static benchmarks into a **live autonomous improvement engine** for daily development:

```
  +-------------------------------------------------------------+
  |              ANTIGRAVITY (Overseeing Chat AI)               |
  |  - Conversational Architect & Project Manager               |
  |  - Identifies tough/complex assignments                     |
  |  - Prompts user for preferred Ollama model                  |
  +-------------------------------------------------------------+
                                |
                                v
  +-------------------------------------------------------------+
  |          HARNESS² TASK RUNNER (Night Shift Engine)          |
  |  - Zero Google Vertex AI / Zero Cloud API billing           |
  |  - Runs on selected Ollama Model (local / cloud endpoints)  |
  |  - Executes Propose -> Probe -> Compose recursive cycle     |
  |  - Extracts reusable rules, lessons, and helper scripts     |
  +-------------------------------------------------------------+
                                |
                                v
  +-------------------------------------------------------------+
  |                   DUAL KNOWLEDGE BRIDGE                     |
  |  - Syncs to GEMINI.md  ==> Antigravity inherits new lessons |
  |  - Syncs to CLAUDE.md  ==> Claude Code CLI inherits lessons |
  |  - Saves helper tools  ==> scripts/*.py                     |
  +-------------------------------------------------------------+
```

### Core Tenets of This Direction
1. **No Google Cloud Vertex AI:** Removed all requirements for GCP/Vertex AI accounts. Night Shift runs exclusively via Ollama (supporting local weights and connected Ollama cloud models).
2. **Antigravity as Overseer:** Antigravity monitors conversations, identifies complex tasks, asks the user which Ollama model to assign, and triggers the recursive engine in the background.
3. **Dual Learning Sync:** When Harness² solves an assignment, the extracted lessons are automatically written to both:
   - `GEMINI.md` (read by Antigravity).
   - `CLAUDE.md` (read by Claude Code CLI).
   - Reusable scripts in `scripts/`.
4. **Dual Verification Subagents:**
   - **Verifier Subagent:** Validates code execution, checks output correctness, and ensures zero runtime exceptions.
   - **Critic Subagent:** Challenges the design, probes for loopholes or edge-cases, and optimizes implementation efficiency.

---

## 3. Work Completed & Platform Patches Applied
1. **Repository Setup:** Cloned `google-research/harness2` into `c:\Projects\Harnes2`.
2. **Environment:** Created Python 3.12 `.venv` via `uv` and installed editable dependencies with `uv pip install -e ".[render]"`.
3. **Cross-Platform Patches (Windows Compatibility):**
   - [`harness2/core/schedule.py`](harness2/core/schedule.py): Added safe import and fallback for Unix-specific `fcntl` file locks.
   - [`harness2/core/tree.py`](harness2/core/tree.py): Applied `.as_posix()` to relative paths to normalize Windows backslashes with POSIX component trees.
4. **Validation:**
   - Unit tests: `python -m unittest tests/test_workflow.py` (5/5 passing).
   - Deterministic demo: `harness2-demo --output runs/demo --k 2` (2/2 tasks completed, 0 failed).
5. **Launchers & UI:**
   - [`start.bat`](start.bat): Master launcher with auto `.venv` setup and syntax-hardened menus.
   - [`start_ollama.bat`](start_ollama.bat): Model-detection launcher featuring live chat ([`scripts/harness_chat.py`](scripts/harness_chat.py)) and model selection.
   - [`scripts/select_ollama_model.ps1`](scripts/select_ollama_model.ps1): Dynamic model scanner categorizing local weights, active cloud models, and downloadable library models.

---

## 4. Development Status for Custom Task Engine
- [x] Update Ollama model list in `scripts/select_ollama_model.ps1` with the latest cloud and high-performance models (`glm-5.3-flash:cloud`, `deepseek-v4.1-flash:cloud`, `minimax-m3.1-flash:cloud`, `qwen3.8:27b-mtp-q4_K_M`, `qwen3-coder:480b-cloud`, `deepseek-v3.1:671b-cloud`, `gpt-oss:120b-cloud`, `kimi-k2.7-code:cloud`).
- [x] Create `scripts/dispatch_task.py`: The standalone task runner that accepts a custom user problem, executes the recursive Propose–Probe–Compose cycle via Ollama, and produces deliverable files.
- [x] Create `scripts/sync_knowledge.py`: The bridge that extracts reflection lessons from `runs/` and updates `GEMINI.md` and `CLAUDE.md`.
- [x] Create `.agents/skills/harness/SKILL.md`: The Antigravity skill enabling seamless task handoff directly from chat.
- [x] Engage Verifier and Critic subagents to audit, test, and challenge scripts with fault-tolerant prefix stripping and tag handling.

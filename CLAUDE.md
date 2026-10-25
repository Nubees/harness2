# Claude Code Instructions: Harness² Project

## Project Overview
- **Domain:** Recursive Agent Harnessing (Harness²).
- **Architecture:** Dual-Shift System (Antigravity/Claude Code as Day Shift, Harness² as Night Shift).
- **Runtime:** Python 3.12 managed via `uv` in `.venv`.
- **Model Engine:** Ollama local and cloud-backed models (`http://localhost:11434/v1`).

## Key Commands
- Run workflow unit tests: `.venv\Scripts\python -m unittest tests/test_workflow.py`
- Dispatch autonomous task: `.venv\Scripts\python scripts/dispatch_task.py --task "<description>"`
- Sync lessons from runs: `.venv\Scripts\python scripts/sync_knowledge.py`
- Launch Ollama menu: `start_ollama.bat`
- Launch Master launcher: `start.bat`

## Autonomous Lessons (Harness² Knowledge Base)

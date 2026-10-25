"""Knowledge Bridge: Syncs Harness² reflections & lessons into GEMINI.md and CLAUDE.md.

Extracts:
1. Cue & Lesson rules from Harness² task summaries/reflections.
2. Appends them to GEMINI.md (for Antigravity) and CLAUDE.md (for Claude Code CLI).
3. Bulletproof against date-drift duplication, formatting variations, and missing tags.
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
GEMINI_MD = ROOT / "GEMINI.md"
CLAUDE_MD = ROOT / "CLAUDE.md"

SECTION_HEADER = "## Autonomous Lessons (Harness² Knowledge Base)"


def extract_lessons_from_summary(summary_path: Path) -> list[dict]:
    lessons = []
    try:
        data = json.loads(summary_path.read_text(encoding="utf-8"))
    except Exception:
        return lessons

    # Extract stable date from summary timestamp (e.g. YYYYMMDD_HHMMSS) or file mtime
    raw_ts = data.get("timestamp", "")
    if len(raw_ts) >= 8 and raw_ts[:8].isdigit():
        lesson_date = f"{raw_ts[:4]}-{raw_ts[4:6]}-{raw_ts[6:8]}"
    else:
        try:
            mtime = datetime.datetime.fromtimestamp(summary_path.stat().st_mtime)
            lesson_date = mtime.date().isoformat()
        except Exception:
            lesson_date = datetime.date.today().isoformat()

    modes = data.get("modes") or {}
    for mode, mode_data in modes.items():
        stages = mode_data.get("stages") or []
        for stage in stages:
            notes = stage.get("notes") or ""
            # Permissive regex for tags, markdown wrappers, or raw text
            exp_match = re.search(r"<experience>(.*?)(?:</experience>|$)", notes, re.DOTALL | re.IGNORECASE)
            content = exp_match.group(1).strip() if exp_match else notes

            cue_m = re.search(r"(?:^|\n)\s*(?:\*\*)?cue(?:\*\*)?:\s*(.+?)(?=\n\s*(?:\*\*)?(?:lesson|evidence|confidence)(?:\*\*)?:|$)", content, re.IGNORECASE | re.DOTALL)
            lesson_m = re.search(r"(?:^|\n)\s*(?:\*\*)?lesson(?:\*\*)?:\s*(.+?)(?=\n\s*(?:\*\*)?(?:cue|evidence|confidence)(?:\*\*)?:|$)", content, re.IGNORECASE | re.DOTALL)
            evidence_m = re.search(r"(?:^|\n)\s*(?:\*\*)?evidence(?:\*\*)?:\s*(.+?)(?=\n\s*(?:\*\*)?(?:cue|lesson|confidence)(?:\*\*)?:|$)", content, re.IGNORECASE | re.DOTALL)

            if lesson_m:
                lessons.append({
                    "task_id": data.get("task_id", summary_path.parent.name),
                    "mode": mode,
                    "cue": re.sub(r"\s+", " ", cue_m.group(1).strip()) if cue_m else "",
                    "lesson": re.sub(r"\s+", " ", lesson_m.group(1).strip()),
                    "evidence": re.sub(r"\s+", " ", evidence_m.group(1).strip()) if evidence_m else "",
                    "date": lesson_date,
                })
    return lessons


def format_lesson_markdown(lesson: dict) -> str:
    lines = [f"- **[{lesson['date']}] ({lesson['task_id']}):** {lesson['lesson']}"]
    if lesson.get("cue"):
        lines.append(f"  - *When to apply:* {lesson['cue']}")
    if lesson.get("evidence"):
        lines.append(f"  - *Evidence:* {lesson['evidence']}")
    return "\n".join(lines)


def update_target_file(target_path: Path, lesson_items: list[dict]) -> bool:
    if not lesson_items:
        return False

    target_path.parent.mkdir(parents=True, exist_ok=True)
    existing_text = target_path.read_text(encoding="utf-8") if target_path.is_file() else f"# {target_path.stem} Instructions\n\n"

    # Robust deduplication against existing text by unique (task_id) key
    new_entries = []
    seen_keys = set(re.findall(r"\((task_[a-zA-Z0-9_]+)\)", existing_text))

    for item in lesson_items:
        tid = item["task_id"]
        if tid not in seen_keys:
            seen_keys.add(tid)
            new_entries.append(format_lesson_markdown(item))

    if not new_entries:
        return False

    append_str = "\n".join(new_entries) + "\n"
    if SECTION_HEADER in existing_text:
        updated = existing_text.rstrip() + "\n" + append_str
    else:
        updated = existing_text.rstrip() + f"\n\n{SECTION_HEADER}\n" + append_str

    target_path.write_text(updated, encoding="utf-8")
    return True


def sync_all(runs_dir: Path = ROOT / "runs") -> int:
    all_lessons = []
    if runs_dir.is_dir():
        for summary_file in runs_dir.rglob("summary.json"):
            for l in extract_lessons_from_summary(summary_file):
                all_lessons.append(l)

    updated_gemini = update_target_file(GEMINI_MD, all_lessons)
    updated_claude = update_target_file(CLAUDE_MD, all_lessons)

    print(f"Knowledge Bridge: Found {len(all_lessons)} total lesson(s).")
    if updated_gemini:
        print(f" -> Synchronized new entries into {GEMINI_MD.name}")
    if updated_claude:
        print(f" -> Synchronized new entries into {CLAUDE_MD.name}")

    return len(all_lessons)


def main():
    parser = argparse.ArgumentParser(description="Sync Harness² learned lessons into GEMINI.md and CLAUDE.md")
    parser.add_argument("--runs-dir", type=Path, default=ROOT / "runs", help="Root runs directory")
    args = parser.parse_args()

    count = sync_all(args.runs_dir)
    print(f"Done. Processed {count} lesson(s).")


if __name__ == "__main__":
    main()

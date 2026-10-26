"""Live Telemetry Server for Harness² Dual-Shift Dashboard.

Provides a lightweight, zero-dependency HTTP and SSE (Server-Sent Events) server
that streams live Day Shift and Night Shift states, recursion progress, Ollama
connectivity, and synchronized knowledge lessons to shift_dashboard.html.
"""

from __future__ import annotations

import argparse
import datetime
import http.server
import json
import os
import re
import socketserver
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS_ROOT = ROOT / "runs" / "custom"
TELEMETRY_FILE = ROOT / "runs" / "telemetry_status.json"
GEMINI_MD = ROOT / "GEMINI.md"
CLAUDE_MD = ROOT / "CLAUDE.md"
DASHBOARD_HTML = ROOT / "dashboard" / "index.html"


_CACHE = {
    "ollama": {"time": 0.0, "data": None},
    "knowledge": {"time": 0.0, "data": None},
}


def is_pid_alive(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        if sys.platform == "win32":
            import ctypes
            kernel32 = ctypes.windll.kernel32
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if h:
                kernel32.CloseHandle(h)
                return True
            return False
        else:
            os.kill(pid, 0)
            return True
    except Exception:
        return False


def get_ollama_status(base_url: str = "http://localhost:11434") -> dict:
    now = time.time()
    cached = _CACHE["ollama"]
    if cached["data"] and (now - cached["time"]) < 2.5:
        return cached["data"]

    try:
        req = urllib.request.Request(f"{base_url}/api/tags")
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = [m.get("name") for m in data.get("models", [])]
            res = {
                "connected": True,
                "url": base_url,
                "model_count": len(models),
                "models": models[:10],
            }
            cached["time"] = now
            cached["data"] = res
            return res
    except Exception as e:
        res = {
            "connected": False,
            "url": base_url,
            "error": str(e),
            "model_count": 0,
            "models": [],
        }
        cached["time"] = now
        cached["data"] = res
        return res


def get_knowledge_stats() -> dict:
    now = time.time()
    cached = _CACHE["knowledge"]
    if cached["data"] and (now - cached["time"]) < 2.5:
        return cached["data"]

    lessons = []
    if GEMINI_MD.is_file():
        content = GEMINI_MD.read_text(encoding="utf-8", errors="replace")
        matches = re.findall(r"- \*\*\[(\d{4}-\d{2}-\d{2})\] \(([^)]+)\):\*\* (.*?)(?=\n- \*\*|\n## |\Z)", content, re.DOTALL)
        for date_str, task_id, lesson_text in matches:
            lessons.append({
                "date": date_str,
                "task_id": task_id,
                "lesson": lesson_text.strip().replace("\n", " ")[:200],
            })
    res = {
        "count": len(lessons),
        "latest": lessons[-1] if lessons else None,
        "files_synced": ["GEMINI.md", "CLAUDE.md"],
    }
    cached["time"] = now
    cached["data"] = res
    return res


def get_telemetry_snapshot() -> dict:
    night_shift = {
        "status": "STANDBY",
        "task_id": None,
        "objective": None,
        "model": "None (Idle)",
        "stage": 0,
        "stage_name": "Idle",
        "details": "Awaiting task dispatch",
        "elapsed_sec": 0,
        "updated_at": None,
    }

    if TELEMETRY_FILE.is_file():
        try:
            raw = json.loads(TELEMETRY_FILE.read_text(encoding="utf-8", errors="replace"))
            ns = raw.get("night_shift", {})
            updated_at = ns.get("updated_at")
            pid = ns.get("pid")

            if ns.get("status") == "RUNNING":
                # Check PID liveness first
                if pid and not is_pid_alive(pid):
                    ns["status"] = "CRASHED"
                    ns["details"] = f"Worker process (PID {pid}) exited unexpectedly"
                elif updated_at:
                    try:
                        up_dt = datetime.datetime.fromisoformat(updated_at)
                        if (datetime.datetime.now() - up_dt).total_seconds() > 300:
                            ns["status"] = "STALE"
                            ns["details"] = "Task inactive for over 5 minutes"
                    except Exception:
                        pass

            night_shift.update(ns)
        except Exception:
            pass

    knowledge = get_knowledge_stats()
    ollama = get_ollama_status()

    day_shift = {
        "status": "ACTIVE",
        "platform": "Antigravity Chat",
        "role": "Conversational Architect & Project Overseer",
        "details": "Interactive pair programming with developer",
    }

    return {
        "day_shift": day_shift,
        "night_shift": night_shift,
        "knowledge_bridge": knowledge,
        "ollama": ollama,
        "server_time": datetime.datetime.now().isoformat(),
    }


class TelemetryHandler(http.server.BaseHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?")[0]

        if path == "/api/status":
            data = get_telemetry_snapshot()
            body = json.dumps(data, indent=2).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        elif path == "/api/events":
            # Server-Sent Events (SSE) live telemetry stream
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Connection", "keep-alive")
            self.end_headers()

            try:
                while True:
                    snapshot = get_telemetry_snapshot()
                    payload = f"data: {json.dumps(snapshot)}\n\n".encode("utf-8")
                    self.wfile.write(payload)
                    self.wfile.flush()
                    time.sleep(1.0)
            except (ConnectionResetError, BrokenPipeError):
                pass

        elif path in ("/", "/dashboard", "/dashboard/index.html"):
            # Serve shift_dashboard.html
            dash_path = ROOT / "dashboard" / "index.html"
            alt_path = Path(r"C:\Users\User101\.gemini\antigravity\brain\94c366a4-3998-4777-90c1-31fdc6170b73\shift_dashboard.html")
            target = dash_path if dash_path.is_file() else alt_path

            if target.is_file():
                body = target.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"Dashboard HTML not found.")
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")

    def log_message(self, format, *args):
        # Silence routine access logs to keep terminal quiet
        if "/api/" in (args[0] if args else ""):
            return
        super().log_message(format, *args)


class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def start_server(port: int = 8765):
    server = ThreadedHTTPServer(("0.0.0.0", port), TelemetryHandler)
    print("\n" + "=" * 65)
    print(f"  [HARNESS² TELEMETRY SERVER]")
    print(f"  Live Dashboard:  http://localhost:{port}/dashboard")
    print(f"  JSON API:        http://localhost:{port}/api/status")
    print(f"  SSE Stream:      http://localhost:{port}/api/events")
    print("=" * 65 + "\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping telemetry server...")
        server.server_close()


def main():
    parser = argparse.ArgumentParser(description="Harness² Live Telemetry Server")
    parser.add_argument("--port", type=int, default=8765, help="Port to listen on (default 8765)")
    args = parser.parse_args()
    start_server(args.port)


if __name__ == "__main__":
    main()

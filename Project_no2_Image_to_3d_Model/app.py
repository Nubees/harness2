"""Omni-3D Studio Application Server.

Lightweight, zero-dependency HTTP & SSE backend server providing the
interactive Image-to-3D Studio application for Project #2.
"""

from __future__ import annotations

import argparse
import datetime
import http.server
import json
import mimetypes
import os
import queue
import re
import socketserver
import sys
import threading
import time
import urllib.parse
import webbrowser
from pathlib import Path

# Local imports
PROJECT_DIR = Path(__file__).resolve().parent
STATIC_DIR = PROJECT_DIR / "static"
UPLOADS_DIR = PROJECT_DIR / "uploads"
JOBS_DIR = PROJECT_DIR / "jobs"
EXPORTS_DIR = PROJECT_DIR / "exports"

UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
JOBS_DIR.mkdir(parents=True, exist_ok=True)
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(PROJECT_DIR))
from omni_engine import Omni3DEngine, find_blender

ENGINE = Omni3DEngine()
JOBS: dict[str, dict] = {}


class StudioHTTPHandler(http.server.BaseHTTPRequestHandler):
    """Custom HTTP and SSE handler for Omni-3D Studio."""

    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self):
        url_parts = urllib.parse.urlparse(self.path)
        path = url_parts.path

        # 1. Studio Web App UI
        if path in ("/", "/index.html", "/studio"):
            studio_html = STATIC_DIR / "studio.html"
            if not studio_html.is_file():
                self.send_error(404, "studio.html not found")
                return
            content = studio_html.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(content)
            return

        # 2. API: List Available Models
        if path == "/api/models":
            models = ENGINE.get_available_models()
            payload = json.dumps({"models": models}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(payload)
            return

        # 3. API: Status & Diagnostics
        if path == "/api/status":
            blender_path = find_blender()
            status_data = {
                "server": "Omni-3D Studio",
                "blender": {
                    "installed": blender_path.is_file(),
                    "path": str(blender_path),
                },
                "ollama": {
                    "url": ENGINE.ollama_url,
                    "models": ENGINE.get_available_models(),
                },
                "active_jobs": len([j for j in JOBS.values() if j.get("status") == "RUNNING"]),
            }
            payload = json.dumps(status_data).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(payload)
            return

        # 4. SSE Stream for Live Job Events
        m = re.match(r"^/api/jobs/([^/]+)/events$", path)
        if m:
            job_id = m.group(1)
            job = JOBS.get(job_id)
            if not job:
                self.send_error(404, f"Job {job_id} not found")
                return

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self._send_cors_headers()
            self.end_headers()

            q: queue.Queue = job["queue"]
            while True:
                try:
                    event = q.get(timeout=25.0)
                    line = f"data: {json.dumps(event)}\n\n".encode("utf-8")
                    self.wfile.write(line)
                    self.wfile.flush()
                    if event.get("stage") == 5 or event.get("stage_name") in ("Complete", "Failed"):
                        break
                except queue.Empty:
                    # Ping / keep-alive
                    try:
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
                    except Exception:
                        break
                except Exception:
                    break
            return

        # 5. Static File Serving (/files/...)
        if path.startswith("/files/"):
            rel = path[7:]  # strip /files/
            file_path = PROJECT_DIR / rel
            if file_path.is_file():
                mime, _ = mimetypes.guess_type(str(file_path))
                if not mime:
                    if file_path.suffix.lower() == ".glb":
                        mime = "model/gltf-binary"
                    elif file_path.suffix.lower() == ".fbx":
                        mime = "application/octet-stream"
                    elif file_path.suffix.lower() == ".stl":
                        mime = "model/stl"
                    else:
                        mime = "application/octet-stream"

                size = file_path.stat().st_size
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(size))
                self.send_header("Accept-Ranges", "bytes")
                self._send_cors_headers()
                self.end_headers()
                with open(file_path, "rb") as f:
                    while chunk := f.read(64 * 1024):
                        self.wfile.write(chunk)
                return

        self.send_error(404, "Endpoint not found")

    def do_POST(self):
        url_parts = urllib.parse.urlparse(self.path)
        path = url_parts.path

        # 1. Image Upload
        if path == "/api/upload":
            content_type = self.headers.get("Content-Type", "")
            length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(length)

            # Extract image filename and bytes
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"upload_{timestamp}.png"
            dest_file = UPLOADS_DIR / filename

            if "multipart/form-data" in content_type:
                # Basic boundary parsing
                boundary = content_type.split("boundary=")[1].encode("utf-8")
                parts = raw_body.split(boundary)
                for part in parts:
                    if b"Content-Type: image/" in part or b"filename=" in part:
                        header_body = part.split(b"\r\n\r\n", 1)
                        if len(header_body) == 2:
                            data = header_body[1].rstrip(b"\r\n--")
                            dest_file.write_bytes(data)
                            break
            else:
                dest_file.write_bytes(raw_body)

            resp_data = {
                "filename": filename,
                "filepath": str(dest_file.relative_to(PROJECT_DIR)).replace("\\", "/"),
                "preview_url": f"/files/uploads/{filename}",
            }
            payload = json.dumps(resp_data).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(payload)
            return

        # 2. Auto-Analyze Image for Stylistic & Anatomy Guidance
        if path == "/api/analyze-image":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length).decode("utf-8"))

            image_ref = body.get("image", "")
            model = body.get("model", "glm-5.3-flash:cloud")

            img_path = PROJECT_DIR / image_ref
            if not img_path.is_file():
                img_path = Path(image_ref)
            if not img_path.is_file():
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({"error": f"Image file not found: {image_ref}"}).encode("utf-8"))
                return

            try:
                guidance = ENGINE.analyze_image_guidance(img_path, model=model)
                payload = json.dumps({"guidance": guidance}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(payload)
            except Exception as exc:
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(exc)}).encode("utf-8"))
            return

        # 2. Trigger Generation Pipeline
        if path == "/api/generate":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length).decode("utf-8"))

            image_ref = body.get("image", "spaceman.png")
            model = body.get("model", "glm-5.3-flash:cloud")
            prompt = body.get("prompt", "")
            formats = body.get("formats", ["glb", "obj", "stl", "fbx"])
            quality_preset = body.get("quality_preset", "sota_sculpt")

            # Resolve image file
            img_path = PROJECT_DIR / image_ref
            if not img_path.is_file():
                img_path = Path(image_ref)
            if not img_path.is_file():
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({"error": f"Image file not found: {image_ref}"}).encode("utf-8"))
                return

            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            job_id = f"job_{timestamp}"
            job_dir = JOBS_DIR / job_id
            job_queue = queue.Queue()

            JOBS[job_id] = {
                "job_id": job_id,
                "status": "RUNNING",
                "queue": job_queue,
                "start_time": time.time(),
            }

            def run_job():
                try:
                    def on_progress(evt):
                        job_queue.put(evt)

                    result = ENGINE.generate_asset(
                        image_path=img_path,
                        job_dir=job_dir,
                        model=model,
                        guidance=prompt,
                        formats=formats,
                        quality_preset=quality_preset,
                        progress_cb=on_progress,
                    )
                    JOBS[job_id]["status"] = "COMPLETE"
                    JOBS[job_id]["result"] = result
                except Exception as exc:
                    JOBS[job_id]["status"] = "FAILED"
                    job_queue.put({"stage": 5, "stage_name": "Failed", "message": str(exc)})

            t = threading.Thread(target=run_job, daemon=True)
            t.start()

            resp = {"job_id": job_id, "status": "QUEUED"}
            payload = json.dumps(resp).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(payload)
            return

        self.send_error(404, "Endpoint not found")

    def log_message(self, format, *args):
        # Mute standard noisy HTTP log requests
        pass


def run_studio_app(port: int = 8766, open_browser: bool = True):
    server_address = ("0.0.0.0", port)
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(server_address, StudioHTTPHandler) as httpd:
        url = f"http://localhost:{port}"
        print("\n" + "=" * 65)
        print(f"  [OMNI-3D STUDIO] Image-to-3D Application Running")
        print(f"  URL:         {url}")
        print(f"  Blender:     {find_blender()}")
        print(f"  Ollama:      {ENGINE.ollama_url}")
        print("=" * 65 + "\n")

        if open_browser:
            webbrowser.open(url)

        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down Omni-3D Studio...")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Start Omni-3D Studio Web Application.")
    parser.add_argument("--port", type=int, default=8766, help="HTTP port (default: 8766)")
    parser.add_argument("--no-browser", action="store_true", help="Do not open browser automatically")
    args = parser.parse_args()
    run_studio_app(port=args.port, open_browser=not args.no_browser)

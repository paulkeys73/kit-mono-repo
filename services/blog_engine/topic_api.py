#!/usr/bin/env python3
import argparse
import json
import subprocess
import threading
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent
POST_SCRIPT = BASE_DIR / "post.sh"
JOBS_LOCK = threading.Lock()
JOBS: dict[str, dict] = {}
PIPELINE_LOCK = threading.Lock()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def tail_text(text: str, max_lines: int = 40) -> str:
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    return "\n".join(lines[-max_lines:])


def run_post_for_topic(topic: str) -> dict:
    if not POST_SCRIPT.exists():
        return {
            "topic": topic,
            "exit_code": 1,
            "stdout_tail": "",
            "stderr_tail": f"Missing script: {POST_SCRIPT}",
        }

    with PIPELINE_LOCK:
        completed = subprocess.run(
            ["bash", str(POST_SCRIPT), topic],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            check=False,
        )
    return {
        "topic": topic,
        "exit_code": completed.returncode,
        "stdout_tail": tail_text(completed.stdout),
        "stderr_tail": tail_text(completed.stderr),
    }


def run_job(job_id: str) -> None:
    with JOBS_LOCK:
        job = JOBS[job_id]
        topics = list(job["topics"])
        job["status"] = "running"
        job["started_at"] = utc_now_iso()

    failed = False
    for topic in topics:
        result = run_post_for_topic(topic)
        with JOBS_LOCK:
            JOBS[job_id]["results"].append(result)
        if result["exit_code"] != 0:
            failed = True
            break

    with JOBS_LOCK:
        JOBS[job_id]["status"] = "failed" if failed else "completed"
        JOBS[job_id]["finished_at"] = utc_now_iso()


def extract_topics(payload: dict) -> list[str]:
    if "topics" in payload:
        raw_topics = payload["topics"]
        if not isinstance(raw_topics, list):
            raise ValueError("'topics' must be a list of strings")
        topics = [str(item).strip() for item in raw_topics if str(item).strip()]
    elif "topic" in payload:
        topic = str(payload["topic"]).strip()
        topics = [topic] if topic else []
    else:
        raise ValueError("Missing 'topic' or 'topics' in request body")

    if not topics:
        raise ValueError("No non-empty topics provided")
    return topics


class TopicRequestHandler(BaseHTTPRequestHandler):
    server_version = "TopicAPI/1.0"

    def log_message(self, fmt: str, *args) -> None:
        print(f"[{utc_now_iso()}] {self.address_string()} - {fmt % args}")

    def _send_json(self, status_code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/health":
            self._send_json(
                200,
                {
                    "status": "ok",
                    "time": utc_now_iso(),
                },
            )
            return

        if path.startswith("/jobs/"):
            job_id = path.split("/jobs/", 1)[1]
            with JOBS_LOCK:
                job = JOBS.get(job_id)
            if not job:
                self._send_json(404, {"error": "job not found", "job_id": job_id})
                return
            self._send_json(200, job)
            return

        self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/topics":
            self._send_json(404, {"error": "not found"})
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length) if content_length > 0 else b""
        if not raw_body:
            self._send_json(400, {"error": "empty request body"})
            return

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            self._send_json(400, {"error": f"invalid JSON: {exc.msg}"})
            return

        if not isinstance(payload, dict):
            self._send_json(400, {"error": "request body must be a JSON object"})
            return

        try:
            topics = extract_topics(payload)
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
            return

        job_id = uuid.uuid4().hex
        with JOBS_LOCK:
            JOBS[job_id] = {
                "id": job_id,
                "status": "queued",
                "topics": topics,
                "results": [],
                "created_at": utc_now_iso(),
                "started_at": None,
                "finished_at": None,
            }

        worker = threading.Thread(target=run_job, args=(job_id,), daemon=True)
        worker.start()

        self._send_json(
            202,
            {
                "message": "job queued",
                "job_id": job_id,
                "topics": topics,
                "status_url": f"/jobs/{job_id}",
            },
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Topic ingestion API for post.sh")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host")
    parser.add_argument("--port", type=int, default=8787, help="Bind port")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), TopicRequestHandler)
    print(f"Topic API listening on http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()

"""
run_live_demo.py — Lineage Engine Live Demo Orchestrator
=========================================================
Run this single file to start everything:
  1. Docker databases (Neo4j + Postgres)
  2. FastAPI backend (port 8000)
  3. Vite/React frontend (port 5173)
  4. Auto-opens the dashboard in your browser
  5. Streams the pipeline from `pipeline_plugin.py` to the engine live

Edit `pipeline_plugin.py` to switch to a different pipeline.

Usage:
    python run_live_demo.py
"""

import os
import sys
import time
import uuid
import subprocess
import threading
import webbrowser
from datetime import datetime, timezone

# Fix Windows Unicode encoding for emojis
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import httpx

# ── Import the active pipeline ────────────────────────────────────────────────
from pipeline_plugin import (
    PIPELINE_JOBS,
    PIPELINE_NAME,
    NAMESPACE,
    ORCHESTRATOR,
    EVENT_DELAY_SECONDS,
)

# ── Configuration ─────────────────────────────────────────────────────────────
API_BASE = "http://localhost:8000"
FRONTEND_URL = "http://localhost:5173"
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(ROOT_DIR, "frontend")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _stream_process(cmd, cwd, prefix):
    """Spawn a subprocess and stream its stdout to console with a tag prefix."""
    def _run():
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            cwd=cwd, text=True, shell=True,
        )
        for line in iter(proc.stdout.readline, ""):
            if line.strip():
                print(f"[{prefix}] {line.strip()}")
        proc.stdout.close()
        proc.wait()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t


def _build_ol_event(job: dict) -> dict:
    """
    Convert a pipeline_plugin job definition into an OpenLineage JSON event.
    This is the exact format that POST /lineage/events expects.
    """
    now = datetime.now(timezone.utc).isoformat()
    return {
        "eventType": "COMPLETE",
        "eventTime": now,
        "run": {"runId": str(uuid.uuid4())},
        "job": {
            "namespace": NAMESPACE,
            "name": job["job_name"],
        },
        "inputs": [
            {"namespace": ns, "name": name, "facets": {}}
            for ns, name in job["inputs"]
        ],
        "outputs": [
            {"namespace": ns, "name": name, "facets": {}}
            for ns, name in job["outputs"]
        ],
    }


def _wait_for_api(timeout_seconds=60):
    """Poll the API health endpoint until it responds or timeout."""
    print(f"[ORCHESTRATOR] Waiting for FastAPI (up to {timeout_seconds}s)...", flush=True)
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            r = httpx.get(f"{API_BASE}/health", timeout=2)
            if r.status_code == 200:
                print("[ORCHESTRATOR] ✅ FastAPI is ready.")
                return True
        except Exception:
            pass
        time.sleep(2)
    print("[ORCHESTRATOR] ❌ FastAPI did not start in time. Check for errors above.")
    return False


# ── Simulator ─────────────────────────────────────────────────────────────────

def simulate_live_pipeline():
    """
    Reads jobs from pipeline_plugin.py and POSTs them to the Lineage Engine
    one by one with a delay — simulating a live, running pipeline.
    """
    # Wait for API to be healthy before firing events
    if not _wait_for_api(timeout_seconds=60):
        return

    print(f"\n[SIMULATOR] >> Starting live simulation of '{PIPELINE_NAME}' pipeline")
    print(f"[SIMULATOR] {len(PIPELINE_JOBS)} jobs to emit | {EVENT_DELAY_SECONDS}s delay between each\n")

    for i, job in enumerate(PIPELINE_JOBS, start=1):
        payload = _build_ol_event(job)
        print(f"[SIMULATOR] [{i}/{len(PIPELINE_JOBS)}] Emitting: {job['job_name']:<25}", end=" ", flush=True)

        try:
            r = httpx.post(f"{API_BASE}/lineage/events", json=payload, timeout=10)
            if r.status_code == 200:
                print("✅")
            else:
                print(f"❌  ({r.status_code}: {r.text})")
        except Exception as e:
            print(f"❌  (API error: {e})")

        time.sleep(EVENT_DELAY_SECONDS)

    print(f"\n[SIMULATOR] ✅ All {len(PIPELINE_JOBS)} pipeline jobs submitted.")
    print(f"[SIMULATOR] Open the dashboard and search for: {NAMESPACE}/customers\n")


# ── Main Orchestrator ──────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 60)
    print("[>>]  Lineage Engine - Live Demo Orchestrator")
    print("=" * 60 + "\n")

    # 1. Databases
    print("--> [1/5] Starting databases (Docker)...")
    subprocess.run("docker compose up -d", cwd=ROOT_DIR, shell=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("           Docker compose started.\n")

    # 2. FastAPI backend
    print("--> [2/5] Starting FastAPI backend (port 8000)...")
    _stream_process(
        "uvicorn app.main:app --host 0.0.0.0 --port 8000",
        cwd=ROOT_DIR, prefix="API"
    )
    print()

    # 3. React frontend
    print("--> [3/5] Starting React dashboard (port 5173)...")
    _stream_process("npm run dev", cwd=FRONTEND_DIR, prefix="VITE")
    print()

    # 4. Open browser
    print("--> [4/5] Opening dashboard in 6 seconds...")
    time.sleep(6)
    webbrowser.open(FRONTEND_URL)
    print(f"           Browser opened → {FRONTEND_URL}\n")

    # 5. Start simulator in background
    print("--> [5/5] Starting pipeline simulator thread...")
    sim_thread = threading.Thread(target=simulate_live_pipeline, daemon=True)
    sim_thread.start()

    print("\n" + "=" * 60)
    print("[OK] ALL SYSTEMS UP")
    print(f"   Dashboard  -> {FRONTEND_URL}")
    print(f"   API Docs   -> {API_BASE}/docs")
    print(f"   Pipeline   -> {PIPELINE_NAME}")
    print("   Press Ctrl+C to stop.")
    print("=" * 60 + "\n")

    # Keep alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[SHUTDOWN] Orchestrator stopped.")
        sys.exit(0)


if __name__ == "__main__":
    main()

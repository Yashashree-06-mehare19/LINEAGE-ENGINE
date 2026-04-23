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
import socket
import subprocess
import threading
import webbrowser
import urllib.parse
from datetime import datetime, timezone
import atexit

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
    DEFAULT_SEARCH_URI,
    DEFAULT_SEARCH_DIRECTION,
)

# ── Configuration ─────────────────────────────────────────────────────────────
API_BASE = "http://localhost:8000"
FRONTEND_URL = "http://localhost:5173"
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(ROOT_DIR, "frontend")


# ── Helpers ──────────────────────────────────────────────────────────────────

PROCS = []

def cleanup():
    for proc in PROCS:
        try:
            if sys.platform == "win32":
                subprocess.call(['taskkill', '/F', '/T', '/PID', str(proc.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                proc.terminate()
        except Exception:
            pass

atexit.register(cleanup)

def _stream_process(cmd, cwd, prefix):
    """Spawn a subprocess and stream its stdout to console with a tag prefix."""
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        cwd=cwd, text=True, shell=True,
    )
    PROCS.append(proc)
    
    def _run():
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


def _wait_for_port(host: str, port: int, label: str, timeout_seconds=90):
    """Poll a TCP port until it accepts connections or timeout."""
    print(f"[ORCHESTRATOR] Waiting for {label} on {host}:{port} (up to {timeout_seconds}s)...", flush=True)
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=2):
                print(f"[ORCHESTRATOR] ✅ {label} is ready on port {port}.")
                return True
        except (ConnectionRefusedError, OSError):
            pass
        time.sleep(3)
    print(f"[ORCHESTRATOR] ❌ {label} did not start in time (port {port} still closed).")
    return False


def _wait_for_docker_healthy(container_name: str, timeout_seconds=180):
    """
    Poll `docker inspect` until the container's Health.Status is 'healthy'.
    This reuses Docker's own healthcheck (cypher-shell, pg_isready, etc.)
    instead of re-implementing them in Python. Far more reliable than TCP probes.
    """
    print(f"[ORCHESTRATOR] Waiting for {container_name} to be healthy (up to {timeout_seconds}s)...", flush=True)
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            result = subprocess.run(
                ["docker", "inspect", "--format", "{{.State.Health.Status}}", container_name],
                capture_output=True, text=True, timeout=5
            )
            status = result.stdout.strip()
            if status == "healthy":
                print(f"[ORCHESTRATOR] ✅ {container_name} is healthy.")
                return True
            elif status in ("starting", "unhealthy", ""):
                print(f"[ORCHESTRATOR] ⏳ {container_name}: {status or 'waiting'}...   ", end='\r', flush=True)
            else:
                # Container not found
                return False
        except Exception:
            pass
        time.sleep(3)
    print(f"\n[ORCHESTRATOR] ❌ {container_name} never became healthy.")
    return False


def _wait_for_api(timeout_seconds=120):
    """Poll the API health endpoint until it responds or timeout."""
    print(f"[ORCHESTRATOR] Waiting for FastAPI (up to {timeout_seconds}s)...", flush=True)
    deadline = time.time() + timeout_seconds
    last_status = None
    while time.time() < deadline:
        try:
            r = httpx.get(f"{API_BASE}/health", timeout=10)
            if r.status_code == 200:
                data = r.json()
                if data.get("status") == "healthy":
                    print("\n[ORCHESTRATOR] ✅ FastAPI and databases are fully ready.")
                    return True
                else:
                    # Still waiting for DBs
                    last_status = data.get("services", {})
                    summary = ", ".join([f"{k}: {'ok' if v == 'ok' else 'starting'}" for k, v in last_status.items()])
                    print(f"[ORCHESTRATOR] ⏳ DBs initializing... ({summary})    ", end='\r', flush=True)
        except Exception as e:
            last_status = f"Request failed: {type(e).__name__} - {e}"
            print(f"[ORCHESTRATOR] ⏳ Waiting for API to start...         ", end='\r', flush=True)
        time.sleep(2)
    print(f"\n[ORCHESTRATOR] ❌ FastAPI did not become healthy in time.")
    return False


# ── Simulator ─────────────────────────────────────────────────────────────────

def simulate_live_pipeline():
    """
    Reads jobs from pipeline_plugin.py and POSTs them to the Lineage Engine
    one by one with a delay — simulating a live, running pipeline.
    """
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
    print("           Docker compose started.")

    # Wait for Docker containers to be "healthy" per their own healthchecks.
    # Docker runs cypher-shell inside neo4j to confirm Bolt is truly ready.
    # This is far more reliable than a raw TCP port check.
    if not _wait_for_docker_healthy("lineage-engine-neo4j-1", timeout_seconds=180):
        # Fallback to container name without project prefix
        if not _wait_for_docker_healthy("lineage-engine_neo4j_1", timeout_seconds=10):
            print("[ABORT] Neo4j never became healthy. Run: docker compose logs neo4j")
            sys.exit(1)

    if not _wait_for_docker_healthy("lineage-engine-postgres-1", timeout_seconds=60):
        if not _wait_for_docker_healthy("lineage-engine_postgres_1", timeout_seconds=10):
            print("[ABORT] PostgreSQL never became healthy. Run: docker compose logs postgres")
            sys.exit(1)
    print()

    # 2. FastAPI backend
    print("--> [2/5] Starting FastAPI backend (port 8000)...")
    _stream_process(
        "uvicorn app.main:app --host 0.0.0.0 --port 8000",
        cwd=ROOT_DIR, prefix="API"
    )
    
    # Wait for FastAPI to be fully healthy before continuing
    if not _wait_for_api(timeout_seconds=120):
        print("[ABORT] FastAPI did not become healthy.")
        sys.exit(1)
    print()

    # 3. React frontend
    print("--> [3/5] Starting React dashboard (port 5173)...")
    _stream_process("npm run dev", cwd=FRONTEND_DIR, prefix="VITE")
    
    # Wait for frontend dev server
    if not _wait_for_port("localhost", 5173, "React Frontend", timeout_seconds=60):
        print("[ABORT] React frontend never came up.")
        sys.exit(1)
    print()

    # 4. Start simulator in background
    print("--> [4/5] Starting pipeline simulator thread...")
    sim_thread = threading.Thread(target=simulate_live_pipeline, daemon=True)
    sim_thread.start()
    
    # Give the simulator a 1-second head start to insert the first node before we open UI
    time.sleep(1)

    # 5. Open browser
    print("--> [5/5] Opening dashboard with active pipeline...")
    encoded_uri = urllib.parse.quote(DEFAULT_SEARCH_URI, safe='')
    full_frontend_url = f"{FRONTEND_URL}/?uri={encoded_uri}&depth=5&direction={DEFAULT_SEARCH_DIRECTION}"
    
    time.sleep(1)
    webbrowser.open(full_frontend_url)
    print(f"           Browser opened → {full_frontend_url}\n")

    print("\n" + "=" * 60)
    print("[OK] ALL SYSTEMS UP")
    print(f"   Dashboard  -> {full_frontend_url}")
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

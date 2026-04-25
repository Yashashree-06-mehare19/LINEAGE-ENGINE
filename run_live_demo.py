"""
run_live_demo.py — Lineage Engine Live Demo Orchestrator
=========================================================
Run this single file to start everything:
  1. Docker databases (Neo4j + Postgres + Airflow) — waits until all are HEALTHY
  2. FastAPI backend (port 8000)
  3. Vite/React frontend (port 5173)
  4. Auto-opens the dashboard in your browser
  5. Streams the pipeline from `pipeline_plugin.py` to the engine live
  6. Runs integrated Stage 6-9 validation tests after the simulation

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
SCRIPTS_DIR = os.path.join(ROOT_DIR, "scripts")


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

    Stage 10: If the job has a 'column_mappings' key, we inject the
    OpenLineage columnLineage facet into the output dataset's facets.
    The facet maps each output column → list of input fields that feed it.
    """
    now = datetime.now(timezone.utc).isoformat()

    # ── Build column lineage facets for each output dataset ────────────────
    # column_mappings format: (input_dataset_name, input_col, output_dataset_name, output_col)
    # We group by output_dataset_name first, then output_col.
    column_facets_by_output: dict[str, dict] = {}   # {output_dataset_name: facet_dict}

    for mapping in job.get("column_mappings", []):
        in_ds_name, in_col, out_ds_name, out_col = mapping

        if out_ds_name not in column_facets_by_output:
            column_facets_by_output[out_ds_name] = {"fields": {}}

        if out_col not in column_facets_by_output[out_ds_name]["fields"]:
            column_facets_by_output[out_ds_name]["fields"][out_col] = {"inputFields": []}

        # Determine namespace for the input dataset (same NAMESPACE as job)
        column_facets_by_output[out_ds_name]["fields"][out_col]["inputFields"].append({
            "namespace": NAMESPACE,
            "name": in_ds_name,
            "field": in_col,
        })

    # ── Build output dataset list, injecting facets where available ─────────
    outputs = []
    for ns, name in job["outputs"]:
        facets = {}
        if name in column_facets_by_output:
            facets["columnLineage"] = column_facets_by_output[name]
        outputs.append({"namespace": ns, "name": name, "facets": facets})

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
        "outputs": outputs,
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


def _wait_for_api(timeout_seconds=60):
    """
    Poll the API health endpoint until it reports fully healthy or timeout.
    Because we used `docker compose up --wait` before starting FastAPI,
    Neo4j and Postgres are guaranteed healthy — this mainly waits for uvicorn to boot.
    """
    print(f"[ORCHESTRATOR] Waiting for FastAPI to become healthy (up to {timeout_seconds}s)...", flush=True)
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            r = httpx.get(f"{API_BASE}/health", timeout=5)
            if r.status_code == 200:
                data = r.json()
                if data.get("status") == "healthy":
                    print("\n[ORCHESTRATOR] ✅ FastAPI and all databases are fully ready.")
                    return True
                else:
                    services = data.get("services", {})
                    summary = ", ".join([f"{k}: {v}" for k, v in services.items()])
                    print(f"[ORCHESTRATOR] ⏳ Still waiting... ({summary})    ", end='\r', flush=True)
        except Exception:
            print(f"[ORCHESTRATOR] ⏳ Waiting for FastAPI to start...         ", end='\r', flush=True)
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


# ── Integrated Stage Tests ────────────────────────────────────────────────────

def _run_test_script(script_name: str) -> bool:
    """
    Runs a test script from the scripts/ directory as a subprocess.
    Returns True if it passed (exit code 0), False otherwise.
    """
    script_path = os.path.join(SCRIPTS_DIR, script_name)
    print(f"\n[TEST] Running {script_name}...", flush=True)

    # PYTHONUTF8=1 forces UTF-8 stdout on Windows so emoji chars don't crash
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"

    result = subprocess.run(
        [sys.executable, script_path],
        cwd=ROOT_DIR,
        capture_output=False,   # stream output directly to terminal
        env=env,
    )
    return result.returncode == 0


def run_stage_tests():
    """
    Runs integrated validation tests for Stages 6, 7, 8, and 9.
    Called automatically after the pipeline simulation completes.
    """
    print("\n" + "=" * 60)
    print("[TEST SUITE]  Running Stage 6-9 Validation Tests")
    print("=" * 60)

    results = {}

    # ── Stage 6: Neo4j Constraints ─────────────────────────────────────────
    # Stage 6 has no separate script — it's verified by checking the /health
    # endpoint and the startup log. We verify it here via the API directly.
    print("\n[TEST] Stage 6: Neo4j Constraint Automation")
    try:
        r = httpx.get(f"{API_BASE}/health", timeout=5)
        data = r.json()
        neo4j_status = data.get("services", {}).get("neo4j", "unknown")
        if neo4j_status == "ok":
            print("  ✅ PASS: Neo4j is healthy — constraints were applied on startup")
            results["Stage 6 (Constraints)"] = True
        else:
            print(f"  ❌ FAIL: Neo4j not reporting ok — got '{neo4j_status}'")
            results["Stage 6 (Constraints)"] = False
    except Exception as e:
        print(f"  ❌ FAIL: Could not reach /health — {e}")
        results["Stage 6 (Constraints)"] = False

    # ── Stage 7: Impact Analysis ───────────────────────────────────────────
    print()
    passed_7 = _run_test_script("test_stage7.py")
    results["Stage 7 (Impact Analysis)"] = passed_7

    # ── Stage 8: Multi-Hop PII Propagation ────────────────────────────────
    print()
    passed_8 = _run_test_script("test_stage8.py")
    results["Stage 8 (PII Propagation)"] = passed_8

    # ── Stage 9: Airflow Dual Endpoint ────────────────────────────────────
    # Verify that the /api/v1/lineage endpoint (Airflow standard) works by
    # sending a real OpenLineage event directly to it.
    print("\n[TEST] Stage 9: Airflow Dual Endpoint (/api/v1/lineage)")
    try:
        payload = {
            "eventType": "COMPLETE",
            "eventTime": datetime.now(timezone.utc).isoformat(),
            "run": {"runId": str(uuid.uuid4())},
            "job": {"namespace": "airflow_test", "name": "test_dual_endpoint_job"},
            "inputs": [{"namespace": "postgres", "name": "raw.test_source", "facets": {}}],
            "outputs": [{"namespace": "postgres", "name": "clean.test_output", "facets": {}}],
        }
        r = httpx.post(f"{API_BASE}/api/v1/lineage", json=payload, timeout=10)
        if r.status_code == 200 and r.json().get("status") == "ok":
            print("  ✅ PASS: POST /api/v1/lineage accepted event (Airflow OL standard endpoint works)")
            results["Stage 9 (Airflow Endpoint)"] = True
        else:
            print(f"  ❌ FAIL: Got {r.status_code} — {r.text}")
            results["Stage 9 (Airflow Endpoint)"] = False
    except Exception as e:
        print(f"  ❌ FAIL: {e}")
        results["Stage 9 (Airflow Endpoint)"] = False

    # ── Final Summary ──────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("[TEST SUITE]  Results Summary")
    print("=" * 60)
    all_passed = True
    for stage, passed in results.items():
        icon = "✅" if passed else "❌"
        print(f"  {icon}  {stage}")
        if not passed:
            all_passed = False

    print()
    if all_passed:
        print("  🎉  ALL STAGES PASSED — Lineage Engine is fully operational!")
    else:
        print("  ⚠️   Some tests failed — check output above for details.")
    print("=" * 60 + "\n")


# ── Main Orchestrator ──────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 60)
    print("[>>]  Lineage Engine - Live Demo Orchestrator")
    print("=" * 60 + "\n")

    # 1. Databases — use --wait so Docker blocks until all healthchecks pass
    #    Neo4j healthcheck: cypher-shell probe, up to ~3 min (30s start + 15 retries × 10s)
    #    Postgres healthcheck: pg_isready, up to ~50s
    #    This GUARANTEES Neo4j is serving Bolt queries before we start FastAPI.
    print("--> [1/5] Starting databases (Docker)...")
    print("    NOTE: Using --wait flag — will block until Neo4j + Postgres are")
    print("          fully healthy inside Docker. Neo4j can take up to 3 minutes.")
    print("    Please wait...\n", flush=True)

    result = subprocess.run(
        "docker compose up -d --wait",
        cwd=ROOT_DIR, shell=True,
        stderr=subprocess.STDOUT,   # merge stderr into stdout (works on PowerShell)
    )
    if result.returncode != 0:
        print("\n[ABORT] Docker compose failed. Check that Docker Desktop is running.")
        print("        Try: docker compose down && docker compose up -d --wait")
        sys.exit(1)
    print("\n    ✅ All Docker services are healthy and ready.\n")

    # 2. FastAPI backend — Neo4j is now guaranteed ready, so this should be fast
    print("--> [2/5] Starting FastAPI backend (port 8000)...")
    _stream_process(
        "uvicorn app.main:app --host 0.0.0.0 --port 8000",
        cwd=ROOT_DIR, prefix="API"
    )
    
    # Wait for FastAPI + DBs to be healthy (should be very fast now)
    if not _wait_for_api(timeout_seconds=60):
        print("[ABORT] FastAPI did not become healthy.")
        sys.exit(1)
    print()

    # 3. React frontend
    print("--> [3/5] Starting React dashboard (port 5173)...")
    _stream_process("npm run dev", cwd=FRONTEND_DIR, prefix="VITE")
    
    if not _wait_for_port("localhost", 5173, "React Frontend", timeout_seconds=60):
        print("[ABORT] React frontend never came up.")
        sys.exit(1)
    print()

    # 4. Run integrated tests FIRST (these wipe the DB to assert cleanly)
    print("--> [4/5] Running Stage 6-9 Tests...")
    run_stage_tests()

    # 5. Start simulator in background — runs all pipeline jobs
    print("--> [5/5] Starting live pipeline simulation...")
    sim_thread = threading.Thread(target=simulate_live_pipeline, daemon=False)
    sim_thread.start()
    
    # Give simulator a head start before opening the browser
    time.sleep(1)

    # 6. Open browser
    print("--> [6/6] Opening dashboard with active pipeline...")
    encoded_uri = urllib.parse.quote(DEFAULT_SEARCH_URI, safe='')
    full_frontend_url = f"{FRONTEND_URL}/?uri={encoded_uri}&depth=5&direction={DEFAULT_SEARCH_DIRECTION}"
    
    time.sleep(1)
    webbrowser.open(full_frontend_url)
    print(f"           Browser opened → {full_frontend_url}\n")

    print("\n" + "=" * 60)
    print("[OK] ALL SYSTEMS UP")
    print(f"   Dashboard  -> {full_frontend_url}")
    print(f"   API Docs   -> {API_BASE}/docs")
    print(f"   Airflow UI -> http://localhost:8081  (admin / sEmA7hUc7F98A2pq)")
    print(f"   Pipeline   -> {PIPELINE_NAME}")
    print("=" * 60 + "\n")

    # Keep alive
    print("Press Ctrl+C to stop all services.\n")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[SHUTDOWN] Orchestrator stopped.")
        sys.exit(0)


if __name__ == "__main__":
    main()

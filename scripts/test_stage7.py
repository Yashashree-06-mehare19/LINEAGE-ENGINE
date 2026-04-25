"""
Integration tests for Stage 7 (Impact Analysis Endpoint).
Run with: python scripts/test_stage7.py
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import httpx
from urllib.parse import quote
from datetime import datetime, timezone
from app.models import LineageEvent, JobRef, RunRef, DatasetRef
from app.storage.graph_writer import write_event
from app.db_client import get_neo4j_driver, get_postgres_conn

BASE = "http://localhost:8000"
PASSED = []
FAILED = []


def check(name, cond, got=None):
    if cond:
        print(f"  ✅ PASS: {name}")
        PASSED.append(name)
    else:
        print(f"  ❌ FAIL: {name}" + (f" | got: {got}" if got else ""))
        FAILED.append(name)


def wipe_db():
    driver = get_neo4j_driver()
    with driver.session() as s:
        s.run("MATCH (n) DETACH DELETE n")
    
    conn = get_postgres_conn()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM run_log")
    conn.commit()
    conn.close()


def seed_graph():
    """
    Creates a multi-hop graph:
    raw.users ──> j1 ──> staging.users ──┐
                                         ├──> j3 ──> clean.purchases ──> j4 ──> reporting.dashboard
    raw.orders ─> j2 ──> staging.orders ─┘
    """
    now = datetime.now(timezone.utc)
    
    # Event 1
    write_event(LineageEvent(
        job=JobRef(name="j1", owner="dev", orchestrator="airflow"),
        run=RunRef(run_id="run-j1", status="COMPLETE", start_time=now, end_time=now),
        inputs=[DatasetRef(namespace="pg", name="raw.users", uri="pg://raw.users", tags=["pii"])],
        outputs=[DatasetRef(namespace="pg", name="staging.users", uri="pg://staging.users", tags=[])],
        event_time=now
    ))
    
    # Event 2
    write_event(LineageEvent(
        job=JobRef(name="j2", owner="dev", orchestrator="airflow"),
        run=RunRef(run_id="run-j2", status="COMPLETE", start_time=now, end_time=now),
        inputs=[DatasetRef(namespace="pg", name="raw.orders", uri="pg://raw.orders", tags=[])],
        outputs=[DatasetRef(namespace="pg", name="staging.orders", uri="pg://staging.orders", tags=[])],
        event_time=now
    ))
    
    # Event 3
    write_event(LineageEvent(
        job=JobRef(name="j3", owner="dev", orchestrator="airflow"),
        run=RunRef(run_id="run-j3", status="COMPLETE", start_time=now, end_time=now),
        inputs=[
            DatasetRef(namespace="pg", name="staging.users", uri="pg://staging.users", tags=[]),
            DatasetRef(namespace="pg", name="staging.orders", uri="pg://staging.orders", tags=[])
        ],
        outputs=[DatasetRef(namespace="pg", name="clean.purchases", uri="pg://clean.purchases", tags=[])],
        event_time=now
    ))
    
    # Event 4
    write_event(LineageEvent(
        job=JobRef(name="j4", owner="dev", orchestrator="airflow"),
        run=RunRef(run_id="run-j4", status="COMPLETE", start_time=now, end_time=now),
        inputs=[DatasetRef(namespace="pg", name="clean.purchases", uri="pg://clean.purchases", tags=[])],
        outputs=[DatasetRef(namespace="pg", name="reporting.dashboard", uri="pg://reporting.dashboard", tags=[])],
        event_time=now
    ))


print("Wiping DB...")
wipe_db()
print("Seeding test graph...")
seed_graph()
time.sleep(0.5)

print("\n" + "="*55)
print("TEST 1: Impact of changing raw.users")
print("="*55)
# raw.users impacts j1, staging.users, j3, clean.purchases, j4, reporting.dashboard
# That's 3 jobs (j1, j3, j4) and 3 datasets (staging.users, clean.purchases, reporting.dashboard)
r = httpx.get(f"{BASE}/lineage/impact/{quote('pg://raw.users', safe='')}")
check("HTTP 200", r.status_code == 200, r.status_code)
data = r.json()

check("Dataset URI matches", data.get("dataset_uri") == "pg://raw.users")
affected_jobs = data.get("affected_jobs", [])
affected_datasets = data.get("affected_datasets", [])
impact_score = data.get("impact_score")

check("Contains affected job j1", "j1" in affected_jobs)
check("Contains affected job j3", "j3" in affected_jobs)
check("Contains affected job j4", "j4" in affected_jobs)
check("Does NOT contain independent job j2", "j2" not in affected_jobs)

check("Contains dataset staging.users", "pg://staging.users" in affected_datasets)
check("Contains dataset clean.purchases", "pg://clean.purchases" in affected_datasets)
check("Contains dataset reporting.dashboard", "pg://reporting.dashboard" in affected_datasets)
check("Does NOT contain raw.orders", "pg://raw.orders" not in affected_datasets)
check("Does NOT contain staging.orders", "pg://staging.orders" not in affected_datasets)

check("Impact score is exactly 6", impact_score == 6, impact_score)


print("\n" + "="*55)
print("TEST 2: Impact of changing clean.purchases")
print("="*55)
# clean.purchases impacts j4 and reporting.dashboard (1 job, 1 dataset)
r = httpx.get(f"{BASE}/lineage/impact/{quote('pg://clean.purchases', safe='')}")
check("HTTP 200", r.status_code == 200, r.status_code)
data = r.json()

check("Impact score is exactly 2", data.get("impact_score") == 2, data.get("impact_score"))
check("Affected job is exactly j4", data.get("affected_jobs") == ["j4"])
check("Affected dataset is reporting.dashboard", data.get("affected_datasets") == ["pg://reporting.dashboard"])


print("\n" + "="*55)
print("TEST 3: Not Found")
print("="*55)
r = httpx.get(f"{BASE}/lineage/impact/{quote('pg://does.not.exist', safe='')}")
check("HTTP 404 for missing dataset", r.status_code == 404, r.status_code)


print("\n" + "="*55)
print(f"RESULTS: {len(PASSED)} passed  |  {len(FAILED)} failed")
sys.exit(0 if not FAILED else 1)

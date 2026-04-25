"""
Integration tests for Stage 8 (Multi-Hop PII Propagation).
Run with: python scripts/test_stage8.py
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import httpx
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
    Creates a 3-hop graph:
    raw.sensitive (pii) ──> j1 ──> staging.clean ──> j2 ──> final.dashboard
    """
    now = datetime.now(timezone.utc)
    
    # Event 1 (1-hop PII) -> graph_writer natively propagates PII to staging.clean
    write_event(LineageEvent(
        job=JobRef(name="j1", owner="dev", orchestrator="airflow"),
        run=RunRef(run_id="run-j1", status="COMPLETE", start_time=now, end_time=now),
        inputs=[DatasetRef(namespace="pg", name="raw.sensitive", uri="pg://raw.sensitive", tags=["pii"])],
        outputs=[DatasetRef(namespace="pg", name="staging.clean", uri="pg://staging.clean", tags=[])],
        event_time=now
    ))
    
    # Event 2 -> final.dashboard won't get PII because graph_writer only propagates 1 hop at write-time
    write_event(LineageEvent(
        job=JobRef(name="j2", owner="dev", orchestrator="airflow"),
        run=RunRef(run_id="run-j2", status="COMPLETE", start_time=now, end_time=now),
        inputs=[DatasetRef(namespace="pg", name="staging.clean", uri="pg://staging.clean", tags=[])],
        outputs=[DatasetRef(namespace="pg", name="final.dashboard", uri="pg://final.dashboard", tags=[])],
        event_time=now
    ))

print("Wiping DB...")
wipe_db()
print("Seeding test graph...")
seed_graph()
time.sleep(0.5)

print("\n" + "="*55)
print("TEST 1: Trigger Retroactive PII Propagation")
print("="*55)

r = httpx.post(f"{BASE}/lineage/admin/propagate-pii")
check("HTTP 200", r.status_code == 200, r.status_code)
data = r.json()
check("status is success", data.get("status") == "success")
check("Updated exactly 1 dataset (final.dashboard)", data.get("datasets_updated") == 1, data.get("datasets_updated"))

# Verify in database
driver = get_neo4j_driver()
with driver.session() as s:
    res = s.run("MATCH (d:Dataset {uri: 'pg://final.dashboard'}) RETURN d.tags AS tags").single()
    tags = res["tags"] if res else []
    check("final.dashboard inherited PII tag", "pii" in tags)

print("\n" + "="*55)
print(f"RESULTS: {len(PASSED)} passed  |  {len(FAILED)} failed")
sys.exit(0 if not FAILED else 1)

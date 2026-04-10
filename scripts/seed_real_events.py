"""
Stage 1 — Day 2: Seed realistic multi-hop pipeline events + test all 3 API endpoints.

Run from the lineage-engine root:
    python scripts/seed_real_events.py

This creates a 5-job e-commerce pipeline:
    s3://data-lake/landing/orders_2024.csv
      → ingest.load_raw_orders
        → postgres://prod:5432/raw.orders
          → transform.clean_orders
            → postgres://prod:5432/staging.orders ─┐
                                                    ├→ transform.enrich_orders
            → postgres://prod:5432/staging.customers─┘
              ← transform.clean_customers              → postgres://prod:5432/mart.orders_enriched
                                                         → reporting.build_dashboard
                                                           → postgres://prod:5432/reporting.order_summary
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx, uuid
from datetime import datetime, timezone, timedelta

BASE = "http://localhost:8000"


def ts(offset_minutes=0):
    t = datetime.now(timezone.utc) + timedelta(minutes=offset_minutes)
    return t.isoformat()


events = [
    {
        "eventType": "COMPLETE",
        "eventTime": ts(0),
        "run": {"runId": str(uuid.uuid4())},
        "job": {"namespace": "airflow", "name": "ingest.load_raw_orders"},
        "inputs": [
            {"namespace": "s3://data-lake", "name": "landing/orders_2024.csv", "facets": {}}
        ],
        "outputs": [
            {"namespace": "postgres://prod:5432", "name": "raw.orders", "facets": {}}
        ],
    },
    {
        "eventType": "COMPLETE",
        "eventTime": ts(2),
        "run": {"runId": str(uuid.uuid4())},
        "job": {"namespace": "airflow", "name": "ingest.load_raw_customers"},
        "inputs": [
            {"namespace": "s3://data-lake", "name": "landing/customers_2024.csv", "facets": {}}
        ],
        "outputs": [
            {"namespace": "postgres://prod:5432", "name": "raw.customers", "facets": {}}
        ],
    },
    {
        "eventType": "COMPLETE",
        "eventTime": ts(5),
        "run": {"runId": str(uuid.uuid4())},
        "job": {"namespace": "airflow", "name": "transform.clean_orders"},
        "inputs": [
            {"namespace": "postgres://prod:5432", "name": "raw.orders", "facets": {}}
        ],
        "outputs": [
            {"namespace": "postgres://prod:5432", "name": "staging.orders", "facets": {}}
        ],
    },
    {
        "eventType": "COMPLETE",
        "eventTime": ts(6),
        "run": {"runId": str(uuid.uuid4())},
        "job": {"namespace": "airflow", "name": "transform.clean_customers"},
        "inputs": [
            {"namespace": "postgres://prod:5432", "name": "raw.customers", "facets": {}}
        ],
        "outputs": [
            {"namespace": "postgres://prod:5432", "name": "staging.customers", "facets": {}}
        ],
    },
    {
        "eventType": "COMPLETE",
        "eventTime": ts(10),
        "run": {"runId": str(uuid.uuid4())},
        "job": {"namespace": "airflow", "name": "transform.enrich_orders"},
        "inputs": [
            {"namespace": "postgres://prod:5432", "name": "staging.orders", "facets": {}},
            {"namespace": "postgres://prod:5432", "name": "staging.customers", "facets": {}},
        ],
        "outputs": [
            {"namespace": "postgres://prod:5432", "name": "mart.orders_enriched", "facets": {}}
        ],
    },
    {
        "eventType": "COMPLETE",
        "eventTime": ts(15),
        "run": {"runId": str(uuid.uuid4())},
        "job": {"namespace": "airflow", "name": "reporting.build_dashboard"},
        "inputs": [
            {"namespace": "postgres://prod:5432", "name": "mart.orders_enriched", "facets": {}}
        ],
        "outputs": [
            {"namespace": "postgres://prod:5432", "name": "reporting.order_summary", "facets": {}}
        ],
    },
    # A FAIL event to test that path
    {
        "eventType": "FAIL",
        "eventTime": ts(20),
        "run": {"runId": str(uuid.uuid4())},
        "job": {"namespace": "airflow", "name": "transform.clean_orders"},
        "inputs": [
            {"namespace": "postgres://prod:5432", "name": "raw.orders", "facets": {}}
        ],
        "outputs": [],
    },
]


def seed_events():
    print("=" * 70)
    print("STEP 1 — Seeding 7 pipeline events")
    print("=" * 70)
    ok = 0
    fail = 0
    for e in events:
        r = httpx.post(f"{BASE}/lineage/events", json=e, timeout=10)
        label = "✅" if r.status_code == 200 else "❌"
        print(f"[{e['eventType']:8s}] {label} {e['job']['name']:45s} → {r.json()}")
        if r.status_code == 200:
            ok += 1
        else:
            fail += 1
    print(f"\nSeeded: {ok} ok, {fail} failed\n")
    return fail == 0


def test_upstream():
    print("=" * 70)
    print("STEP 2 — Test GET /lineage/upstream (reporting.order_summary, depth=5)")
    print("=" * 70)
    uri = "postgres://prod:5432/reporting.order_summary"
    r = httpx.get(f"{BASE}/lineage/upstream/{uri}", params={"depth": 5}, timeout=10)
    data = r.json()
    nodes = data.get("nodes", [])
    edges = data.get("edges", [])
    print(f"Status: {r.status_code}")
    print(f"Nodes returned: {len(nodes)}")
    for n in nodes:
        print(f"  [{n.get('label', 'Unknown'):7s}] {n.get('id', 'Unknown')}")
    print(f"Edges returned: {len(edges)}")
    passed = r.status_code == 200 and len(nodes) >= 5
    print(f"\n{'✅ PASS' if passed else '❌ FAIL'} — upstream query\n")
    return passed


def test_downstream():
    print("=" * 70)
    print("STEP 3 — Test GET /lineage/downstream (raw.orders, depth=5)")
    print("=" * 70)
    uri = "postgres://prod:5432/raw.orders"
    r = httpx.get(f"{BASE}/lineage/downstream/{uri}", params={"depth": 5}, timeout=10)
    data = r.json()
    nodes = data.get("nodes", [])
    edges = data.get("edges", [])
    print(f"Status: {r.status_code}")
    print(f"Nodes returned: {len(nodes)}")
    for n in nodes:
        print(f"  [{n.get('label', 'Unknown'):7s}] {n.get('id', 'Unknown')}")
    passed = r.status_code == 200 and len(nodes) >= 3
    print(f"\n{'✅ PASS' if passed else '❌ FAIL'} — downstream query\n")
    return passed


def test_runs():
    print("=" * 70)
    print("STEP 4 — Test GET /lineage/runs (transform.clean_orders)")
    print("=" * 70)
    r = httpx.get(f"{BASE}/lineage/runs/transform.clean_orders", timeout=10)
    data = r.json()
    runs_list = data.get("runs", [])
    print(f"Status: {r.status_code}")
    print(f"Runs returned: {len(runs_list)}")
    for run in runs_list:
        status_label = "✅" if run.get("status") == "COMPLETE" else "❌"
        print(f"  {status_label} [{run.get('status', '?'):8s}] run_id={run.get('run_id', '?')[:8]}... | started={run.get('start_time', '?')}")
    # Expect 2 runs: 1 COMPLETE + 1 FAIL
    passed = r.status_code == 200 and len(runs_list) >= 2
    print(f"\n{'✅ PASS' if passed else '❌ FAIL'} — runs query (expected ≥2)\n")
    return passed


def main():
    print("\n🚀 Stage 1 — Day 2: Real Events Seeding + API Verification\n")

    seeded = seed_events()
    if not seeded:
        print("❌ Seeding failed — aborting API tests")
        return

    up = test_upstream()
    down = test_downstream()
    runs = test_runs()

    print("=" * 70)
    passed = sum([up, down, runs])
    print(f"\n📊 FINAL: {passed}/3 tests passed")
    if passed == 3:
        print("🎉 Stage 1 Day 2 — COMPLETE! All API endpoints verified.\n")
    else:
        print("⚠️  Some tests failed — check the output above.\n")


if __name__ == "__main__":
    main()

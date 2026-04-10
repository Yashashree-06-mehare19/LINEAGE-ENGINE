"""
Stage 1 — Day 1: Feed jaffle_shop manifest.json to the lineage engine.

Run from the lineage-engine root:
    python scripts/ingest_dbt_manifest.py

Prerequisites:
    - FastAPI server running: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
    - jaffle_shop_duckdb cloned + dbt seed + dbt run completed at: c:/Rubiscape/jaffle_shop_duckdb
"""

import sys, os

# Make sure we can import from the project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from parsers.dbt_parser import parse_manifest   # Note: function is parse_manifest, not parse_dbt_manifest
from dataclasses import asdict
import json

MANIFEST_PATH = r"c:\Rubiscape\jaffle_shop_duckdb\target\manifest.json"
API_BASE = "http://localhost:8000"


def lineage_event_to_dict(event) -> dict:
    """Convert internal LineageEvent dataclass → OpenLineage-shaped JSON the API accepts."""
    from datetime import datetime

    def ts(dt):
        return dt.isoformat() if dt else None

    return {
        "eventType": event.run.status,   # "COMPLETE" or "FAIL"
        "eventTime": ts(event.event_time),
        "run": {
            "runId": event.run.run_id
        },
        "job": {
            "namespace": getattr(event.job, "namespace", "dbt"),
            "name": event.job.name,
        },
        "inputs": [
            {
                "namespace": ds.namespace,
                "name": ds.name,
                "facets": {}
            }
            for ds in event.inputs
        ],
        "outputs": [
            {
                "namespace": ds.namespace,
                "name": ds.name,
                "facets": {}
            }
            for ds in event.outputs
        ],
    }


def main():
    if not os.path.exists(MANIFEST_PATH):
        print(f"[ERROR] manifest.json not found at:\n  {MANIFEST_PATH}")
        print("Run `dbt seed && dbt run` inside jaffle_shop_duckdb first.")
        return

    print(f"Parsing manifest.json from:\n  {MANIFEST_PATH}\n")
    events = parse_manifest(MANIFEST_PATH)
    print(f"Found {len(events)} lineage events from dbt manifest\n")
    print("-" * 70)

    pass_count = 0
    fail_count = 0

    for event in events:
        payload = lineage_event_to_dict(event)
        try:
            r = httpx.post(f"{API_BASE}/lineage/events", json=payload, timeout=10)
            status_label = "✅" if r.status_code == 200 else "❌"
            print(f"{status_label} [{r.status_code}] {event.job.name:50s} → {r.json()}")
            if r.status_code == 200:
                pass_count += 1
            else:
                fail_count += 1
        except Exception as e:
            print(f"❌ [ERR] {event.job.name:50s} → {e}")
            fail_count += 1

    print("-" * 70)
    print(f"\nResult: {pass_count} ok, {fail_count} failed out of {len(events)} events")


if __name__ == "__main__":
    main()

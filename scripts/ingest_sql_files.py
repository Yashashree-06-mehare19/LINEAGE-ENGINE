"""
Stage 1 — Day 1: Feed jaffle_shop raw .sql files to the lineage engine via sql_parser.

Run from the lineage-engine root:
    python scripts/ingest_sql_files.py

Prerequisites:
    - FastAPI server running: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
    - jaffle_shop_duckdb cloned at: c:/Rubiscape/jaffle_shop_duckdb

Note: dbt SQL files use Jinja2 templating ({{ ref(...) }}, {{ source(...) }}).
      SQLGlot cannot parse Jinja templates, so some files will be PARSE ERROR.
      This is EXPECTED — dbt_parser.py handles dbt-syntax; sql_parser.py handles plain SQL.
      Staging models and simple SELECT queries will parse fine.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from parsers.sql_parser import parse_sql
from datetime import datetime, timezone
import uuid

SQL_DIR = r"c:\Rubiscape\jaffle_shop_duckdb\models"
API_BASE = "http://localhost:8000"
NAMESPACE = "duckdb://jaffle_shop"


def lineage_event_to_dict(event, job_name: str) -> dict:
    """Convert internal LineageEvent → OpenLineage JSON for the API."""
    def ts(dt):
        return dt.isoformat() if dt else None

    return {
        "eventType": "COMPLETE",
        "eventTime": ts(event.event_time),
        "run": {"runId": str(uuid.uuid4())},
        "job": {
            "namespace": "duckdb",
            "name": f"sql.{job_name}",
        },
        "inputs": [
            {"namespace": ds.namespace, "name": ds.name, "facets": {}}
            for ds in event.inputs
        ],
        "outputs": [
            {"namespace": ds.namespace, "name": ds.name, "facets": {}}
            for ds in event.outputs
        ],
    }


def main():
    if not os.path.exists(SQL_DIR):
        print(f"[ERROR] SQL directory not found:\n  {SQL_DIR}")
        return

    sql_files = []
    for root, dirs, files in os.walk(SQL_DIR):
        for filename in files:
            if filename.endswith(".sql"):
                sql_files.append(os.path.join(root, filename))

    print(f"Found {len(sql_files)} .sql files in jaffle_shop models\n")
    print("-" * 70)

    ok = 0
    skipped = 0
    parse_error = 0
    api_error = 0

    for filepath in sql_files:
        filename = os.path.basename(filepath)
        job_name = filename.replace(".sql", "")

        with open(filepath, "r", encoding="utf-8") as f:
            sql_text = f.read()

        # Check for Jinja templating — sql_parser can't handle these
        if "{{" in sql_text or "{%" in sql_text:
            print(f"⚠️  [SKIP-JINJA] {job_name:40s} → dbt Jinja syntax (use dbt_parser instead)")
            skipped += 1
            continue

        try:
            event = parse_sql(sql=sql_text, dialect="duckdb", job_name=job_name)
        except Exception as e:
            print(f"❌ [PARSE-ERR] {job_name:40s} → {e}")
            parse_error += 1
            continue

        if not event.inputs and not event.outputs:
            print(f"⚠️  [EMPTY]     {job_name:40s} → No tables extracted (pure CTE or subquery)")
            skipped += 1
            continue

        payload = lineage_event_to_dict(event, job_name)
        try:
            r = httpx.post(f"{API_BASE}/lineage/events", json=payload, timeout=10)
            status_label = "✅" if r.status_code == 200 else "❌"
            inputs_str = ", ".join(ds.name for ds in event.inputs) or "(none)"
            outputs_str = ", ".join(ds.name for ds in event.outputs) or "(none)"
            print(f"{status_label} [{r.status_code}] {job_name:40s} | in: {inputs_str} → out: {outputs_str}")
            if r.status_code == 200:
                ok += 1
            else:
                api_error += 1
        except Exception as e:
            print(f"❌ [API-ERR]   {job_name:40s} → {e}")
            api_error += 1

    print("-" * 70)
    print(f"\nResult: {ok} posted, {skipped} skipped (Jinja/empty), {parse_error} parse errors, {api_error} API errors")
    print(f"Total files: {len(sql_files)}")


if __name__ == "__main__":
    main()

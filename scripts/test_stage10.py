"""
Integration tests for Stage 10 (Column-Level Lineage).
Run with: python scripts/test_stage10.py

Graph seeded:
  raw_customers → stg_customers → customers
  raw_customers.id       → stg_customers.customer_id → customers.customer_id
  raw_customers.first_name → stg_customers.first_name
  raw_orders.order_date  → stg_orders.order_date
"""
import sys
import os
import time

# Fix Windows Unicode encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import httpx
from urllib.parse import quote
from datetime import datetime, timezone
from app.db_client import get_neo4j_driver, get_postgres_conn

BASE = "http://localhost:8000"
PASSED = []
FAILED = []


def check(name, cond, got=None):
    if cond:
        print(f"  ✅ PASS: {name}")
        PASSED.append(name)
    else:
        print(f"  ❌ FAIL: {name}" + (f" | got: {got}" if got is not None else ""))
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
    POST two OL events with columnLineage facets:
      Event 1: raw_customers → stg_customers  (3 column mappings)
      Event 2: stg_customers → customers       (2 column mappings, chaining through customer_id)
    This creates a 2-hop column chain:
      raw_customers/id → stg_customers/customer_id → customers/customer_id
    """
    NS = "duckdb://jaffle_shop"
    now = datetime.now(timezone.utc).isoformat()

    # Event 1: raw_customers → stg_customers
    ev1 = {
        "eventType": "COMPLETE",
        "eventTime": now,
        "run": {"runId": "col-test-run-1"},
        "job": {"namespace": NS, "name": "stg_customers_test"},
        "inputs":  [{"namespace": NS, "name": "raw_customers", "facets": {}}],
        "outputs": [{
            "namespace": NS,
            "name": "stg_customers",
            "facets": {
                "columnLineage": {
                    "fields": {
                        "customer_id": {
                            "inputFields": [{"namespace": NS, "name": "raw_customers", "field": "id"}]
                        },
                        "first_name": {
                            "inputFields": [{"namespace": NS, "name": "raw_customers", "field": "first_name"}]
                        },
                        "last_name": {
                            "inputFields": [{"namespace": NS, "name": "raw_customers", "field": "last_name"}]
                        },
                    }
                }
            }
        }],
    }

    # Event 2: stg_customers → customers
    ev2 = {
        "eventType": "COMPLETE",
        "eventTime": now,
        "run": {"runId": "col-test-run-2"},
        "job": {"namespace": NS, "name": "customers_test"},
        "inputs":  [{"namespace": NS, "name": "stg_customers", "facets": {}}],
        "outputs": [{
            "namespace": NS,
            "name": "customers",
            "facets": {
                "columnLineage": {
                    "fields": {
                        "customer_id": {
                            "inputFields": [{"namespace": NS, "name": "stg_customers", "field": "customer_id"}]
                        },
                        "full_name": {
                            "inputFields": [
                                {"namespace": NS, "name": "stg_customers", "field": "first_name"},
                                {"namespace": NS, "name": "stg_customers", "field": "last_name"},
                            ]
                        },
                    }
                }
            }
        }],
    }

    r1 = httpx.post(f"{BASE}/lineage/events", json=ev1, timeout=10)
    assert r1.status_code == 200, f"Seed event 1 failed: {r1.text}"
    r2 = httpx.post(f"{BASE}/lineage/events", json=ev2, timeout=10)
    assert r2.status_code == 200, f"Seed event 2 failed: {r2.text}"


# ── Setup ─────────────────────────────────────────────────────────────────────
print("Wiping DB...")
wipe_db()
print("Seeding test graph with column lineage facets...")
seed_graph()
time.sleep(0.5)

NS = "duckdb://jaffle_shop"


# ═════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 55)
print("TEST 1: GET /lineage/columns — list columns for stg_customers")
print("=" * 55)
# stg_customers should have 3 columns: customer_id, first_name, last_name

stg_uri = f"{NS}/stg_customers"
r = httpx.get(f"{BASE}/lineage/columns/{quote(stg_uri, safe='')}")
check("HTTP 200", r.status_code == 200, r.status_code)
data = r.json()
check("dataset_uri matches", data.get("dataset_uri") == stg_uri)
cols = {c["name"] for c in data.get("columns", [])}
check("column_count == 3", data.get("column_count") == 3, data.get("column_count"))
check("customer_id present", "customer_id" in cols)
check("first_name present",  "first_name" in cols)
check("last_name present",   "last_name" in cols)


# ═════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 55)
print("TEST 2: GET /lineage/columns — raw_customers has input columns")
print("=" * 55)
# raw_customers is an INPUT dataset — its columns (id, first_name, last_name)
# ARE written as Column nodes because they appear in TRANSFORMS edges.
raw_uri = f"{NS}/raw_customers"
r = httpx.get(f"{BASE}/lineage/columns/{quote(raw_uri, safe='')}")
check("HTTP 200", r.status_code == 200, r.status_code)
raw_cols = {c["name"] for c in r.json().get("columns", [])}
check("id column present", "id" in raw_cols, raw_cols)
check("first_name column present", "first_name" in raw_cols, raw_cols)
check("last_name column present", "last_name" in raw_cols, raw_cols)


# ═════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 55)
print("TEST 3: GET /lineage/columns — unknown dataset returns 404")
print("=" * 55)
r = httpx.get(f"{BASE}/lineage/columns/{quote('duckdb://jaffle_shop/does_not_exist', safe='')}")
check("HTTP 404", r.status_code == 404, r.status_code)


# ═════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 55)
print("TEST 4: GET /lineage/column-upstream — stg_customers/customer_id")
print("=" * 55)
# stg_customers/customer_id ← raw_customers/id  (1 hop)
col_uri = f"{NS}/stg_customers/customer_id"
r = httpx.get(f"{BASE}/lineage/column-upstream/{quote(col_uri, safe='')}")
check("HTTP 200", r.status_code == 200, r.status_code)
data = r.json()
upstream = [c["uri"] for c in data.get("upstream_columns", [])]
check("column_uri matches", data.get("column_uri") == col_uri)
check("raw_customers/id is upstream", f"{NS}/raw_customers/id" in upstream, upstream)


# ═════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 55)
print("TEST 5: GET /lineage/column-upstream — 2-hop: customers/customer_id")
print("=" * 55)
# customers/customer_id ← stg_customers/customer_id ← raw_customers/id  (2 hops)
col_uri = f"{NS}/customers/customer_id"
r = httpx.get(f"{BASE}/lineage/column-upstream/{quote(col_uri, safe='')}")
check("HTTP 200", r.status_code == 200, r.status_code)
upstream = [c["uri"] for c in r.json().get("upstream_columns", [])]
check("stg_customers/customer_id is upstream", f"{NS}/stg_customers/customer_id" in upstream, upstream)
check("raw_customers/id is 2-hop upstream",    f"{NS}/raw_customers/id" in upstream, upstream)


# ═════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 55)
print("TEST 6: GET /lineage/column-upstream — missing column returns 404")
print("=" * 55)
r = httpx.get(f"{BASE}/lineage/column-upstream/{quote(f'{NS}/stg_customers/nonexistent', safe='')}")
check("HTTP 404", r.status_code == 404, r.status_code)


# ═════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 55)
print("TEST 7: GET /lineage/column-impact — raw_customers/id")
print("=" * 55)
# raw_customers/id → stg_customers/customer_id → customers/customer_id  (2 hops)
col_uri = f"{NS}/raw_customers/id"
r = httpx.get(f"{BASE}/lineage/column-impact/{quote(col_uri, safe='')}")
check("HTTP 200", r.status_code == 200, r.status_code)
data = r.json()
impacted = [c["uri"] for c in data.get("impacted_columns", [])]
impact_score = data.get("impact_score", 0)
check("impact_score >= 2", impact_score >= 2, impact_score)
check("stg_customers/customer_id impacted", f"{NS}/stg_customers/customer_id" in impacted, impacted)
check("customers/customer_id impacted (2-hop)", f"{NS}/customers/customer_id" in impacted, impacted)


# ═════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 55)
print("TEST 8: GET /lineage/column-impact — leaf column has impact 0")
print("=" * 55)
# customers/customer_id is a leaf — nothing downstream
col_uri = f"{NS}/customers/customer_id"
r = httpx.get(f"{BASE}/lineage/column-impact/{quote(col_uri, safe='')}")
check("HTTP 200", r.status_code == 200, r.status_code)
check("impact_score == 0", r.json().get("impact_score") == 0, r.json().get("impact_score"))


# ═════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 55)
print("TEST 9: full_name has 2 input fields (first_name + last_name)")
print("=" * 55)
col_uri = f"{NS}/stg_customers/first_name"
r = httpx.get(f"{BASE}/lineage/column-impact/{quote(col_uri, safe='')}")
check("HTTP 200", r.status_code == 200, r.status_code)
impacted = [c["uri"] for c in r.json().get("impacted_columns", [])]
check("customers/full_name is downstream of first_name", f"{NS}/customers/full_name" in impacted, impacted)


# ═════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 55)
print(f"RESULTS: {len(PASSED)} passed  |  {len(FAILED)} failed")
sys.exit(0 if not FAILED else 1)

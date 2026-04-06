"""
Stage 3 Integration Tests — tests write_event() directly against real Neo4j + Postgres.

Run with:
    python scripts/test_stage3.py

Requires:
    docker compose up -d   (Neo4j + Postgres must be running)
    .env must be loaded (contains NEO4J_URI, POSTGRES_DSN)
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from datetime import datetime, timezone
from app.models import LineageEvent, JobRef, RunRef, DatasetRef
from app.storage.graph_writer import write_event
from app.db_client import get_neo4j_driver, get_postgres_conn

PASSED = []
FAILED = []


def check(name, condition, got=None):
    if condition:
        print(f"  PASS: {name}")
        PASSED.append(name)
    else:
        msg = f"  FAIL: {name}"
        if got is not None:
            msg += f"  |  got: {got}"
        print(msg)
        FAILED.append(name)


def neo4j_query(cypher, **params):
    driver = get_neo4j_driver()
    with driver.session() as s:
        return s.run(cypher, **params).data()


def postgres_query(sql, params=()):
    conn = get_postgres_conn()
    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    conn.close()
    return rows


# ─────────────────────────────────────────────────────────
# SETUP — wipe Neo4j between tests
# ─────────────────────────────────────────────────────────

def wipe_neo4j():
    driver = get_neo4j_driver()
    with driver.session() as s:
        s.run("MATCH (n) DETACH DELETE n")
    print("  [setup] Neo4j wiped")


def make_event(
    job_name="test.job",
    run_id="run-001",
    status="COMPLETE",
    inputs=None,
    outputs=None,
):
    now = datetime.now(timezone.utc)
    return LineageEvent(
        job=JobRef(name=job_name, owner="test-team", orchestrator="airflow"),
        run=RunRef(run_id=run_id, status=status, start_time=now, end_time=now),
        inputs=inputs or [DatasetRef(namespace="postgres", name="raw.orders", uri="postgres://raw.orders", tags=[])],
        outputs=outputs or [DatasetRef(namespace="postgres", name="clean.orders", uri="postgres://clean.orders", tags=[])],
        event_time=now,
    )


# ─────────────────────────────────────────────────────────
# TEST 1 — Job node created in Neo4j
# ─────────────────────────────────────────────────────────
print("\n" + "="*55)
print("TEST 1: Job node created in Neo4j")
print("="*55)
wipe_neo4j()

write_event(make_event(job_name="orders_pipeline.transform", run_id="run-t1"))
rows = neo4j_query("MATCH (j:Job {name: $n}) RETURN j", n="orders_pipeline.transform")
check("Job node exists", len(rows) == 1, rows)
check("Job.owner = test-team", rows[0]["j"]["owner"] == "test-team")
check("Job.orchestrator = airflow", rows[0]["j"]["orchestrator"] == "airflow")


# ─────────────────────────────────────────────────────────
# TEST 2 — Dataset nodes created
# ─────────────────────────────────────────────────────────
print("\n" + "="*55)
print("TEST 2: Dataset nodes created in Neo4j")
print("="*55)

rows = neo4j_query("MATCH (d:Dataset) RETURN d.uri AS uri ORDER BY d.uri")
uris = [r["uri"] for r in rows]
check("2 datasets exist", len(uris) == 2, uris)
check("raw.orders in graph", "postgres://raw.orders" in uris)
check("clean.orders in graph", "postgres://clean.orders" in uris)

raw = neo4j_query("MATCH (d:Dataset {uri: 'postgres://raw.orders'}) RETURN d")[0]["d"]
check("Dataset.namespace = postgres", raw["namespace"] == "postgres")
check("Dataset.name = raw.orders", raw["name"] == "raw.orders")


# ─────────────────────────────────────────────────────────
# TEST 3 — PRODUCES and CONSUMES edges
# ─────────────────────────────────────────────────────────
print("\n" + "="*55)
print("TEST 3: PRODUCES and CONSUMES edges created")
print("="*55)

produces = neo4j_query("MATCH ()-[r:PRODUCES]->() RETURN count(r) AS c")[0]["c"]
consumes = neo4j_query("MATCH ()-[r:CONSUMES]->() RETURN count(r) AS c")[0]["c"]
check("1 PRODUCES edge", produces == 1, produces)
check("1 CONSUMES edge", consumes == 1, consumes)

edge_check = neo4j_query(
    "MATCH (j:Job {name: $jn})-[:PRODUCES]->(d:Dataset {uri: $du}) RETURN j,d",
    jn="orders_pipeline.transform", du="postgres://clean.orders"
)
check("Job PRODUCES clean.orders", len(edge_check) == 1, edge_check)

edge_check2 = neo4j_query(
    "MATCH (d:Dataset {uri: $du})-[:CONSUMES]->(j:Job {name: $jn}) RETURN d,j",
    du="postgres://raw.orders", jn="orders_pipeline.transform"
)
check("raw.orders CONSUMES Job", len(edge_check2) == 1, edge_check2)


# ─────────────────────────────────────────────────────────
# TEST 4 — Run node and HAS_RUN edge
# ─────────────────────────────────────────────────────────
print("\n" + "="*55)
print("TEST 4: Run node and HAS_RUN edge")
print("="*55)

run_rows = neo4j_query("MATCH (r:Run {run_id: 'run-t1'}) RETURN r")
check("Run node exists", len(run_rows) == 1, run_rows)
check("Run.status = COMPLETE", run_rows[0]["r"]["status"] == "COMPLETE")

has_run = neo4j_query(
    "MATCH (j:Job)-[:HAS_RUN]->(r:Run {run_id: 'run-t1'}) RETURN j"
)
check("Job HAS_RUN edge exists", len(has_run) == 1, has_run)


# ─────────────────────────────────────────────────────────
# TEST 5 — PostgreSQL audit log written
# ─────────────────────────────────────────────────────────
print("\n" + "="*55)
print("TEST 5: PostgreSQL run_log audit entry")
print("="*55)

pg_rows = postgres_query("SELECT * FROM run_log WHERE run_id = %s", ("run-t1",))
check("1 row in run_log", len(pg_rows) == 1, pg_rows)
if pg_rows:
    row = pg_rows[0]
    check("job_name correct", row[1] == "orders_pipeline.transform", row[1])
    check("status = COMPLETE", row[2] == "COMPLETE", row[2])
    check("input_datasets recorded", "postgres://raw.orders" in (row[5] or []), row[5])
    check("output_datasets recorded", "postgres://clean.orders" in (row[6] or []), row[6])


# ─────────────────────────────────────────────────────────
# TEST 6 — Idempotency (write same event twice — no duplicate nodes)
# ─────────────────────────────────────────────────────────
print("\n" + "="*55)
print("TEST 6: Idempotency — write same event twice")
print("="*55)

wipe_neo4j()
e = make_event(job_name="idempotent.job", run_id="run-idem-001")
write_event(e)
write_event(e)  # second call with SAME run_id

job_count = neo4j_query("MATCH (j:Job) RETURN count(j) AS c")[0]["c"]
ds_count  = neo4j_query("MATCH (d:Dataset) RETURN count(d) AS c")[0]["c"]
run_count = neo4j_query("MATCH (r:Run) RETURN count(r) AS c")[0]["c"]
prod_count= neo4j_query("MATCH ()-[r:PRODUCES]->() RETURN count(r) AS c")[0]["c"]

check("Exactly 1 Job node", job_count == 1, job_count)
check("Exactly 2 Dataset nodes", ds_count == 2, ds_count)
check("Exactly 1 Run node", run_count == 1, run_count)
check("Exactly 1 PRODUCES edge", prod_count == 1, prod_count)

pg_count = postgres_query(
    "SELECT COUNT(*) FROM run_log WHERE run_id = %s", ("run-idem-001",)
)[0][0]
check("Exactly 1 row in run_log (no duplicate)", pg_count == 1, pg_count)


# ─────────────────────────────────────────────────────────
# TEST 7 — PII tag propagation
# ─────────────────────────────────────────────────────────
print("\n" + "="*55)
print("TEST 7: PII tag propagates from input to output")
print("="*55)

wipe_neo4j()
pii_event = LineageEvent(
    job=JobRef(name="pii.job", owner="team", orchestrator="airflow"),
    run=RunRef(run_id="run-pii-001", status="COMPLETE",
               start_time=datetime.now(timezone.utc),
               end_time=datetime.now(timezone.utc)),
    inputs=[DatasetRef(namespace="postgres", name="raw.customers",
                       uri="postgres://raw.customers", tags=["pii"])],
    outputs=[DatasetRef(namespace="postgres", name="clean.customers",
                        uri="postgres://clean.customers", tags=[])],
    event_time=datetime.now(timezone.utc),
)
write_event(pii_event)

output_tags = neo4j_query(
    "MATCH (d:Dataset {uri: 'postgres://clean.customers'}) RETURN d.tags AS tags"
)
tags = output_tags[0]["tags"] if output_tags else []
check("'pii' tag propagated to output", "pii" in tags, tags)

# No PII — no propagation
wipe_neo4j()
clean_event = LineageEvent(
    job=JobRef(name="clean.job", owner="team", orchestrator="airflow"),
    run=RunRef(run_id="run-nopii-001", status="COMPLETE",
               start_time=datetime.now(timezone.utc),
               end_time=datetime.now(timezone.utc)),
    inputs=[DatasetRef(namespace="postgres", name="meta.config",
                       uri="postgres://meta.config", tags=[])],
    outputs=[DatasetRef(namespace="postgres", name="reports.summary",
                        uri="postgres://reports.summary", tags=[])],
    event_time=datetime.now(timezone.utc),
)
write_event(clean_event)

output_tags2 = neo4j_query(
    "MATCH (d:Dataset {uri: 'postgres://reports.summary'}) RETURN d.tags AS tags"
)
tags2 = output_tags2[0]["tags"] if output_tags2 else []
check("No PII tag when input has no PII", "pii" not in tags2, tags2)


# ─────────────────────────────────────────────────────────
# TEST 8 — End-to-end via HTTP (Stage 2 + Stage 3 together)
# ─────────────────────────────────────────────────────────
print("\n" + "="*55)
print("TEST 8: Full end-to-end via POST /lineage/events")
print("="*55)

wipe_neo4j()
import httpx

r = httpx.post("http://localhost:8000/lineage/events", json={
    "eventType": "COMPLETE",
    "eventTime": "2024-01-15T14:32:00.000Z",
    "run": {
        "runId": "e2e-run-001",
        "facets": {
            "nominalTime": {
                "nominalStartTime": "2024-01-15T14:30:00.000Z",
                "nominalEndTime":   "2024-01-15T14:32:00.000Z"
            }
        }
    },
    "job": {
        "namespace": "local_dev",
        "name": "e2e_pipeline.step1",
        "facets": {"ownership": {"owners": [{"name": "data-team", "type": "team"}]}}
    },
    "inputs":  [{"namespace": "postgres", "name": "raw.sales", "facets": {}}],
    "outputs": [{"namespace": "postgres", "name": "clean.sales", "facets": {}}]
})

check("HTTP 200", r.status_code == 200, r.status_code)
check("status: ok", r.json().get("status") == "ok", r.json())

# Verify it actually landed in Neo4j
job_in_graph = neo4j_query("MATCH (j:Job {name: 'e2e_pipeline.step1'}) RETURN j")
check("Job written to Neo4j via HTTP", len(job_in_graph) == 1, job_in_graph)

ds_in_graph = neo4j_query("MATCH (d:Dataset) RETURN d.uri AS uri")
uris_e2e = [r["uri"] for r in ds_in_graph]
check("raw.sales in Neo4j", "postgres://raw.sales" in uris_e2e, uris_e2e)
check("clean.sales in Neo4j", "postgres://clean.sales" in uris_e2e, uris_e2e)

pg_e2e = postgres_query("SELECT run_id, status FROM run_log WHERE run_id = %s", ("e2e-run-001",))
check("Run in Postgres run_log", len(pg_e2e) == 1, pg_e2e)
check("correct owner echoed", r.json().get("job") == "e2e_pipeline.step1")


# ─────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────
print("\n" + "="*55)
print(f"RESULTS: {len(PASSED)} passed  |  {len(FAILED)} failed")
if FAILED:
    print("Failed tests:")
    for f in FAILED:
        print(f"  - {f}")
else:
    print("All Stage 3 tests passed!")
print("="*55)
sys.exit(0 if not FAILED else 1)

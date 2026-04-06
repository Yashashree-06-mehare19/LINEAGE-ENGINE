# Progress

## Stage 1 — Foundation & Infrastructure ✅ COMPLETE

### What Works
- Docker Compose: Neo4j 5.15.0 + PostgreSQL 15.6 running
- `app/models.py` — LineageEvent, JobRef, RunRef, DatasetRef dataclasses
- `app/db_client.py` — get_neo4j_driver() + get_postgres_conn()
- `app/main.py` — FastAPI app with /health endpoint
- Neo4j: 3 constraints (job_name_unique, dataset_uri_unique, run_id_unique) + 1 index (dataset_tags_index) — applied manually in browser
- PostgreSQL: run_log table auto-created via volume mount
- GET /health returns `{"status":"healthy","neo4j":"ok","postgres":"ok"}`

### Stage 1 Decisions Made
- FastAPI runs locally (not in Docker) — easier Windows dev, hot reload
- Python 3.13 used (not 3.11) — works fine with --prefer-binary
- psycopg2 (not psycopg2-binary) — binary fails on Windows
- .env uses localhost, not Docker service names

---

## Stage 2 — Ingestion Layer ✅ COMPLETE (integration testing pending)

### What Was Built
- `app/ingestion/pydantic_models.py` — OLRunEvent, OLDataset, OLJob, OLRun Pydantic v2 models
- `app/ingestion/converter.py` — ol_event_to_lineage_event()
- `app/ingestion/router.py` — POST /lineage/events (skips START events)
- `app/storage/graph_writer.py` — STUB (logs only, Stage 3 replaces this)
- `parsers/sql_parser.py` — SQLGlot parser, CTE-aware, Postgres + Snowflake dialects
- `parsers/dbt_parser.py` — manifest.json parser
- `app/main.py` — updated to mount ingestion router

### Verified Working
- Swagger UI shows POST /lineage/events under "ingestion" tag ✅
- GET /health still returns healthy ✅
- No import errors on startup ✅

### Integration Tests — ALL PASSING (exit code 0)
- COMPLETE event → 200 + {status: ok} ✅
- START event → 200 + {status: skipped} ✅
- FAIL event → 200 + {status: ok} ✅
- Missing field → 422 ✅
- Bad datetime → 422 ✅
- Empty inputs/outputs → 200 ok ✅
- Health still healthy after events ✅
- SQL: INSERT SELECT → correct inputs/outputs ✅
- SQL: CTE not treated as real table ✅
- SQL: CREATE TABLE AS Snowflake dialect ✅
- SQL: JOIN → both tables as inputs ✅
- dbt: 2 events from 2 deps, skip no-dep + test nodes ✅
- dbt: correct orchestrator, schema prefix, dep names ✅

Test script: `scripts/test_stage2.py`

---

## Stage 3 — Storage Layer ✅ COMPLETE

### What Was Built
- `app/storage/graph_writer.py` — real write_event() replacing the stub
  - `_write_graph(tx, event)` — all Neo4j writes in single transaction
  - `_upsert_job()`, `_upsert_dataset()` — MERGE-based, safe to re-run
  - `_create_produces_edge()`, `_create_consumes_edge()`, `_create_run()`, `_create_has_run_edge()`
  - `_write_postgres()` — inserts to run_log, ON CONFLICT DO NOTHING, failure not raised
  - `_propagate_pii_tags()` — 1-hop PII propagation at write time

### All 34 Integration Tests PASSED
- Job node created with correct properties
- Dataset nodes (namespace, name, uri)
- PRODUCES and CONSUMES edges with timestamps
- Run node + HAS_RUN edge
- PostgreSQL run_log all fields correct
- Idempotency: write same event twice = 1 node each, 1 run_log row
- PII propagation: pii input → output inherits pii tag
- No-PII: clean input → output stays clean
- Full end-to-end via HTTP: POST → Neo4j + Postgres verified

Test script: `scripts/test_stage3.py`

---

## Stage 4 — Query API ❌ NOT STARTED
- `app/api/router.py` — GET upstream/downstream/runs endpoints
- `app/api/cypher_queries.py` — Cypher strings

---

## Known Issues / Watchpoints
- Neo4j constraints were applied manually — not automated on container start yet
- run_log table uses TEXT for run_id (not UUID) — matches current write pattern
- Airflow service in docker-compose.yml is defined but not tested

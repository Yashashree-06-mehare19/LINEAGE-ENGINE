# Active Context

## Current Focus
Ready to begin Stage 4 — Query API (GET /lineage/upstream, /downstream, /runs endpoints).

## Last Completed
- Stage 3 fully implemented: real `write_event()` with Neo4j + Postgres writes
- 34/34 Stage 3 tests PASSED (exit code 0):
  - TEST 1: Job node created correctly in Neo4j
  - TEST 2: Dataset nodes (namespace, name, uri properties)
  - TEST 3: PRODUCES and CONSUMES edges with timestamps
  - TEST 4: Run node + HAS_RUN edge
  - TEST 5: PostgreSQL run_log audit entry (all 5 fields)
  - TEST 6: Idempotency — writing same event twice = exactly 1 of each node
  - TEST 7: PII tag propagation (pii input → output tagged; clean input → no tag)
  - TEST 8: Full end-to-end HTTP → Neo4j + Postgres verified
- Test script: `scripts/test_stage3.py`

## Immediate Next Steps
1. Build Stage 4 — Query API GET endpoints
2. `app/api/cypher_queries.py` — Cypher traversal strings
3. `app/api/pydantic_models.py` — LineageGraphResponse, RunsResponse
4. `app/api/router.py` — GET /lineage/upstream/{id}, /downstream/{id}, /runs/{job_id}
5. Mount api router in app/main.py
6. Test with seed data already in Neo4j

## Active Decisions
- `graph_writer.py` is a STUB — logs only. Stage 3 replaces this file entirely.
- The ingestion router skips `START` events by design (no output datasets yet)
- FastAPI runs locally on Windows, DBs run in Docker

## Server State
- uvicorn running at http://localhost:8000
- Docker containers: neo4j + postgres both healthy
- Command: `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`

## Important File Paths
```
c:\Rubiscape\lineage-engine\
├── app/
│   ├── main.py               ← mounts ingestion_router + /health
│   ├── models.py             ← LineageEvent dataclass (shared)
│   ├── db_client.py          ← DB connection wrappers
│   ├── ingestion/
│   │   ├── pydantic_models.py  ← OLRunEvent validation
│   │   ├── converter.py        ← OL → LineageEvent
│   │   └── router.py           ← POST /lineage/events
│   └── storage/
│       └── graph_writer.py     ← STUB (replace in Stage 3)
├── parsers/
│   ├── sql_parser.py           ← SQLGlot parser
│   └── dbt_parser.py           ← manifest.json parser
├── docs/
│   ├── lineage_engine_master_build_doc.md  ← source of truth
│   └── current.md              ← what was done each stage
└── memory-bank/                ← this folder
```

# Active Context

## Current Focus
Stage 2 (Week 2 Dashboard) has been completely built. A brand-new Vite+React workspace has been scaffolded under `/frontend/`, featuring dynamic DAG graphs mapping the REST node paths from `FastAPI`. 

## Last Completed
- Provisioned `React Flow` mapping with `dagre` LR traversals via Axios requests to `localhost:8000`.
- Built custom components styled natively using `TailwindCSS` with dark-mode Glassmorphism arrays (glowy nodes, interactive popovers).
- Implemented `SearchBar`, `LineageGraph`, `NodeSidePanel` and `RunsPanel`.
- Verified API CORS handshaking effectively returning datasets (jobs, lineage links, runs, output pipelines).

## Immediate Next Steps
- Review frontend visualization with user at `http://localhost:5173`.
- Address any further dynamic aesthetic changes!

## Active Decisions
- A lineage "hop" (Dataset to Dataset) counts as `depth=1` from the API user's perspective, but internally the pipeline traverses `2` edges (from Dataset->Job->Dataset), ensuring queries calculate traversing depth correctly!
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

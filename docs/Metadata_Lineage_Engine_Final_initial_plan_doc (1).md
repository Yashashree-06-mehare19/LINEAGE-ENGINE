# Metadata Lineage Engine — Onboarding Guide
> **Who this is for:** A brand-new teammate who has never seen this codebase. Read top to bottom. Everything you need is here.

---

## Table of Contents
1. [What Is This Project?](#1-what-is-this-project)
2. [Why Does It Exist? (The Problem)](#2-why-does-it-exist-the-problem)
3. [How It Solves The Problem](#3-how-it-solves-the-problem)
4. [System Architecture (Bird's Eye View)](#4-system-architecture-birds-eye-view)
5. [The Graph Data Model](#5-the-graph-data-model)
6. [Every File Explained](#6-every-file-explained)
7. [Data Flow — Request by Request](#7-data-flow--request-by-request)
8. [Dependency Graph (What Imports What)](#8-dependency-graph-what-imports-what)
9. [The Tech Stack](#9-the-tech-stack)
10. [How to Run It Locally](#10-how-to-run-it-locally)
11. [API Reference](#11-api-reference)
12. [Testing Strategy](#12-testing-strategy)
13. [The Build Stages (What Was Done When)](#13-the-build-stages-what-was-done-when)
14. [What Is Still To Build](#14-what-is-still-to-build)
15. [Key Design Decisions (The "Why" Behind The Code)](#15-key-design-decisions)
16. [Glossary](#16-glossary)

---

## 1. What Is This Project?

**One sentence:** A backend engine that automatically tracks how data flows through a company's pipelines and answers "where did this data come from?" in milliseconds.

**What it does concretely:**
- When Airflow runs a job that reads from `raw.orders` and writes to `clean.orders`, our system **records that relationship**
- When a developer asks "what is upstream of `clean.orders`?" — our system **traverses the graph** and returns every ancestor
- The full picture is stored as a **graph** (nodes = datasets/jobs, edges = data flow direction)

*(How to explain to a new teammate: "Think of it like Git blame, but for data. Instead of 'who changed this line?', we answer 'which job touched this table and what fed into it?'")*

---

## 2. Why Does It Exist? (The Problem)

Modern data teams have invisible pipelines. When data is wrong, finding the root cause takes days:

| Symptom | Without This System |
|---|---|
| Dashboard shows wrong revenue | Spend 2 days tracing SQL scripts manually |
| Schema change breaks 5 downstream jobs | Nobody knows which jobs depend on that table |
| GDPR request: "delete all data about user X" | Can't answer — don't know where it flows |
| ML model produces bad predictions | Can't trace which training data was used |

**With this system:** One API call returns the full ancestry. GDPR traceability is instant. Schema impact analysis is a query.

*(How to explain: "Airflow runs jobs, dbt transforms data, SQL scripts load tables — but none of them talk to each other about what they touched. We are that bridge.")*

---

## 3. How It Solves The Problem

Three ingestion paths feed lineage into the system:

```
PATH A — Runtime (Airflow → OpenLineage)
   Airflow task finishes → automatically POSTs an OpenLineage JSON event
   → POST /lineage/events → stored in Neo4j graph

PATH B — Static SQL Parser
   You have .sql files on disk → run our SQL parser (SQLGlot)
   → it reads FROM/JOIN/INSERT/CREATE → emits LineageEvent → stored

PATH C — Static dbt Parser
   dbt compiles → generates manifest.json → run our dbt parser
   → reads model dependencies → emits LineageEvents → stored
```

Once stored, query it:
```
GET /lineage/upstream/postgres://clean.orders
→ returns full JSON graph of every dataset + job that produced clean.orders
```

*(How to explain: "Three different worlds — Airflow runtime, hand-written SQL, and dbt models — all feed into one graph. Once it's in the graph, you query it the same way regardless of where it came from.")*

---

## 4. System Architecture (Birds Eye View)

```
LAYER 1: DATA PRODUCERS
   [Airflow DAG]   [.sql files]   [dbt manifest.json]
        |               |                  |
        v               v                  v
   POST /lineage/events (OpenLineage JSON format)

LAYER 2: FASTAPI BACKEND  (runs locally, port 8000)
   INGESTION LAYER  (app/ingestion/)
     1. Pydantic v2 validates the OpenLineage JSON
     2. Converter translates OL format -> internal format
     3. Router calls write_event()
           |
           v
   STORAGE LAYER  (app/storage/graph_writer.py)
     - Writes Job/Dataset/Run nodes to Neo4j (MERGE, idempotent)
     - Writes run record to PostgreSQL (audit log)
     - Propagates PII tags to output datasets
           |
           v
   QUERY API  (app/api/)
     GET /lineage/upstream/{id}   -> Cypher graph traversal
     GET /lineage/downstream/{id} -> Cypher graph traversal
     GET /lineage/runs/{job_id}   -> PostgreSQL SELECT
     GET /lineage/runs/global     -> All recent runs
     GET /lineage/datasets        -> All datasets in graph

LAYER 3: DATABASES  (in Docker)
   NEO4J (port 7474)            POSTGRESQL (port 5432)
   Graph storage                Audit log (run_log table)
   Job/Dataset/Run              run history, times,
   nodes + edges                input/output datasets

LAYER 4: REACT DASHBOARD  (frontend/, port 5173)
   - Search datasets by URI
   - See interactive graph (React Flow + Dagre layout)
   - Click a node -> see properties, PII tags, run history
   - Graph auto-refreshes every 4 seconds (live mode)
```

*(How to explain: "Backend is FastAPI Python. Storage is Neo4j graph + Postgres audit. Frontend is React. Everything in Docker except the FastAPI app itself which runs locally for easier development.")*

---

## 5. The Graph Data Model

This is what lives inside Neo4j. **Understand this and you understand everything.**

### Nodes

| Node Type | What It Represents | Key Property |
|---|---|---|
| `Dataset` | A table, file, or data asset | `uri` (unique key) e.g. `"postgres://clean.orders"` |
| `Job` | A transformation (Airflow task, SQL script, dbt model) | `name` (unique key) |
| `Run` | One execution of a Job at a point in time | `run_id` (unique key, UUID) |

### Edges

| Edge | Direction | Meaning |
|---|---|---|
| `CONSUMES` | `Dataset -> Job` | "This dataset was read by this job" |
| `PRODUCES` | `Job -> Dataset` | "This job wrote to this dataset" |
| `HAS_RUN` | `Job -> Run` | "This job has this execution record" |

### Visual Example

```
(raw.orders) --[:CONSUMES]--> (load_orders_job) --[:PRODUCES]--> (clean.orders)
                                      |
                                 [:HAS_RUN]
                                      |
                                      v
                               (Run: uuid, COMPLETE, 2024-01-01)
```

### URI Format
Every dataset gets a unique URI:
```
"{namespace}://{name}"
postgres://clean.orders
dbt://staging.stg_customers
sql_parser://raw.users
```

*(How to explain: "The URI is the passport of a dataset. If two different jobs reference the same table, they reference the same URI, so the graph knows it's the same node — no duplicates.")*

---

## 6. Every File Explained

### Root Level
```
lineage-engine/
├── run_live_demo.py      <- THE DEMO LAUNCHER. Run this to start everything at once.
├── pipeline_plugin.py    <- THE ONLY FILE you edit to point at a different pipeline.
├── docker-compose.yml    <- Spins up Neo4j + PostgreSQL containers.
├── requirements.txt      <- Python dependencies.
├── .env                  <- DB connection strings (not committed to git).
└── Dockerfile            <- (exists but app runs locally in dev, not in Docker)
```

### `app/` — The FastAPI Backend

```
app/
├── main.py               <- Entry point. Creates FastAPI app, registers routers, CORS, /health.
├── models.py             <- Internal data contracts (Python dataclasses, NOT Pydantic).
├── db_client.py          <- DB connection singletons. get_neo4j_driver() + get_postgres_conn().
│
├── ingestion/            <- Handles POST /lineage/events
│   ├── pydantic_models.py  <- Validates incoming OpenLineage JSON (OLRunEvent model)
│   ├── converter.py        <- Translates OL format -> internal LineageEvent format
│   └── router.py           <- FastAPI route: POST /lineage/events
│
├── storage/              <- Handles writing to databases
│   └── graph_writer.py     <- write_event() -> Neo4j + Postgres writes + PII propagation
│
└── api/                  <- Handles GET queries
    ├── pydantic_models.py  <- Response schemas (NodeModel, EdgeModel, LineageGraphResponse)
    ├── cypher_queries.py   <- Raw Cypher query strings extracted for clarity
    └── router.py           <- All GET /lineage/* endpoints
```

### `parsers/` — Static Ingestion Paths

```
parsers/
├── sql_parser.py    <- Parses SQL strings via SQLGlot. FROM/JOIN = inputs, INSERT/CREATE = outputs.
│                      CTE-aware. Multi-dialect (postgres, snowflake).
└── dbt_parser.py    <- Parses dbt manifest.json. One LineageEvent per (model, dependency) pair.
```

### `frontend/` — React Dashboard

```
frontend/
├── package.json          <- Node dependencies (React Flow, axios, dagre, Tailwind)
├── vite.config.js        <- Vite dev server config
└── src/
    ├── main.jsx          <- React root mount
    ├── App.jsx           <- Top-level app with routing
    ├── api/
    │   └── lineageApi.js   <- All axios HTTP calls to FastAPI backend
    ├── pages/
    │   ├── GraphView.jsx         <- Main graph visualization page (React Flow canvas)
    │   ├── DirectoryView.jsx     <- Browsable list of all datasets
    │   └── SystemRunsView.jsx    <- Global run history table
    ├── components/
    │   ├── CustomNodes.jsx       <- React Flow node renderers (Dataset=blue, Job=orange)
    │   ├── LineageGraph.jsx      <- React Flow canvas + Dagre auto-layout
    │   ├── NodeSidePanel.jsx     <- Slide-in panel: node properties + PII tags
    │   ├── RunsPanel.jsx         <- Job run history table in side panel
    │   ├── SearchBar.jsx         <- Dataset URI search + direction selector
    │   └── Sidebar.jsx           <- Left navigation sidebar
    └── utils/                    <- Layout helpers
```

### `scripts/` — Developer Tools

```
scripts/
├── test_stage2.py          <- Integration tests for Stage 2 (ingestion layer)
├── test_stage3.py          <- Integration tests for Stage 3 (34 tests)
├── test_stage4.py          <- Integration tests for Stage 4 (25 tests)
├── seed_real_events.py     <- Seeds realistic lineage data for manual testing
├── seed_dummy_data.py      <- Seeds simple dummy data
├── ingest_sql_files.py     <- Runs SQL parser on .sql files and POSTs to API
└── ingest_dbt_manifest.py  <- Runs dbt parser on manifest.json and POSTs to API
```

### `infra/` and `docs/`

```
infra/
└── postgres_init.sql       <- Creates run_log table on first Postgres container start

docs/
├── lineage_engine_master_build_doc.md  <- THE ORIGINAL SPEC. Source of truth.
├── current.md                          <- Running changelog of what was done per stage
├── stage2_learning_doc.md              <- Learning notes: ingestion layer
├── stage3_learning_doc.md              <- Learning notes: storage layer
├── system_learning_doc.md              <- Learning notes: overall system design
└── testing_qna.md                      <- Q&A on testing patterns used

memory-bank/
├── projectbrief.md    <- What we are building (the brief)
├── productContext.md  <- Why it exists (the problem it solves)
├── activeContext.md   <- Current session state, last completed, next steps
├── systemPatterns.md  <- Architecture rules, interface contracts, module responsibilities
├── techContext.md     <- Tech stack versions, how to start each session
└── progress.md        <- What works, what is left, stage-by-stage status
```

---

## 7. Data Flow — Request by Request

### Flow A: Airflow posts an event → data gets stored

```
1. Airflow finishes a task
2. OpenLineage plugin fires POST /lineage/events with JSON:
   {
     "eventType": "COMPLETE",
     "eventTime": "2024-01-01T10:00:00Z",
     "run":     { "runId": "abc-123" },
     "job":     { "namespace": "postgres", "name": "load_orders" },
     "inputs":  [{ "namespace": "postgres", "name": "raw.orders" }],
     "outputs": [{ "namespace": "postgres", "name": "clean.orders" }]
   }

3. app/ingestion/pydantic_models.py validates it (OLRunEvent schema)
   -> if validation fails, FastAPI auto-returns 422

4. app/ingestion/router.py checks: is eventType COMPLETE or FAIL?
   -> if START: return {"status": "skipped"}   (no output datasets yet)
   -> if COMPLETE or FAIL: proceed

5. app/ingestion/converter.py translates:
   OLRunEvent -> LineageEvent (internal dataclass)
   Renames: runId->run_id, builds DatasetRef.uri (namespace + "://" + name)

6. app/storage/graph_writer.write_event(lineage_event):
   a. Opens Neo4j session, calls _write_graph() in ONE transaction:
      - MERGE Job node "load_orders"
      - MERGE Dataset node "postgres://raw.orders"
      - MERGE Dataset node "postgres://clean.orders"
      - MERGE CONSUMES edge (raw.orders -> load_orders)
      - MERGE PRODUCES edge (load_orders -> clean.orders)
      - MERGE Run node (abc-123, COMPLETE)
      - MERGE HAS_RUN edge (load_orders -> abc-123)
   b. INSERT into PostgreSQL run_log table (audit record)
   c. PII check: if raw.orders has pii tag -> add pii tag to clean.orders

7. Return {"status": "ok", "job": "load_orders", "run_id": "abc-123"}
```

### Flow B: Developer queries upstream lineage

```
1. GET /lineage/upstream/postgres://clean.orders?depth=3

2. app/api/router.get_upstream():
   a. Check dataset exists in Neo4j
   b. Run Cypher traversal:
      MATCH path = (start:Dataset {uri: $uri})<-[:CONSUMES|PRODUCES*1..6]-(node)
      RETURN DISTINCT nodes(path), relationships(path)
      (depth=3 means max_edges=6, because one "hop" Dataset->Job->Dataset = 2 edges)

3. Build LineageGraphResponse:
   {
     "dataset_id": "postgres://clean.orders",
     "direction": "upstream",
     "depth": 3,
     "nodes": [ {...Job}, {...Dataset}, ... ],
     "edges": [ {...CONSUMES}, {...PRODUCES}, ... ],
     "node_count": 5,
     "edge_count": 4
   }
```

*(How to explain the depth×2 trick: "In the graph, going from Dataset A to Dataset B always crosses TWO edges: Dataset->Job->Dataset. So when a user says 'depth=3 hops', we tell Cypher 'traverse 6 edges'. This was a real bug we found and fixed.")*

---

## 8. Dependency Graph (What Imports What)

```
                     app/models.py
                    (LineageEvent, JobRef, RunRef, DatasetRef)
                          |
         +----------------+-----------------------+
         |                |                       |
         v                v                       v
app/ingestion/       app/storage/           parsers/
converter.py         graph_writer.py        sql_parser.py
         |                |                 dbt_parser.py
         |                |
         v                v
app/ingestion/       app/db_client.py
router.py            (get_neo4j_driver, get_postgres_conn)

app/main.py
  imports: ingestion/router.py
           api/router.py

app/api/router.py
  imports: api/pydantic_models.py
           api/cypher_queries.py
           db_client.py

frontend/src/api/lineageApi.js
  -> HTTP calls to FastAPI (not Python imports — only HTTP)
```

**Critical Rule:** `models.py` is imported by everything. It never imports anything from `app/`. This prevents circular imports and decouples the web layer from the data layer.

*(How to explain: "models.py is the backbone. If you import it in a weird direction, you will create circular imports. Data only flows one way: models -> ingestion/storage/api, never backwards.")*

---

## 9. The Tech Stack

| Layer | Technology | Why |
|---|---|---|
| Language | Python 3.13 | Modern, async-ready, vast data ecosystem |
| Web framework | FastAPI 0.115 | Auto-generates OpenAPI docs, Pydantic built-in |
| ASGI server | uvicorn 0.29 | Production-grade async server for FastAPI |
| Data validation | Pydantic v2 | At HTTP boundary ONLY. Internal = plain dataclasses |
| Graph database | Neo4j 5.15 | Native graph storage. Cypher traversals O(1) per hop |
| Neo4j driver | neo4j 5.19 | Official Python driver, bolt protocol |
| Relational DB | PostgreSQL 15.6 | Audit log, run history. Excellent for time-ordered SQL |
| Postgres driver | psycopg2 2.9.11 | NOT psycopg2-binary — binary fails on Windows |
| SQL parser | SQLGlot 23.12.2 | Multi-dialect SQL AST parser, CTE-aware |
| Container runtime | Docker Compose | Runs Neo4j + PostgreSQL only |
| Frontend framework | React + Vite | Vite for fast dev server with hot reload |
| Graph UI | React Flow | Interactive canvas for node/edge visualization |
| Graph layout | @dagrejs/dagre | Automatic Left-to-Right DAG layout |
| Frontend styling | Tailwind CSS | Utility-first CSS, glassmorphism dark theme |
| HTTP client (FE) | axios | API calls from React to FastAPI |
| Testing | pytest 8.2 | Standard Python test runner |
| Integration testing | testcontainers 4.4 | Spins up real DBs for tests |
| HTTP test client | httpx 0.27 | Tests FastAPI endpoints end-to-end |

---

## 10. How to Run It Locally

### Prerequisites
- Docker Desktop installed and running
- Python 3.11+ installed
- Node.js 18+ installed
- Clone the repo and `cd lineage-engine`

### Option 1: One-command demo (recommended for first run)
```powershell
python run_live_demo.py
```
This single script handles everything:
1. Starts Docker (Neo4j + PostgreSQL)
2. Starts FastAPI on port 8000
3. Starts React on port 5173
4. Opens the browser automatically
5. Simulates the "Jaffle Shop" pipeline live (events appear every 3 seconds)

### Option 2: Manual (for active development)
```powershell
# Terminal 1 — databases
docker compose up -d

# Terminal 2 — backend (with hot reload)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 3 — frontend
cd frontend
npm install   # first time only
npm run dev
```

### Environment Variables (`.env` file in project root)
```
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=lineage_password
POSTGRES_DSN=postgresql://lineage_user:lineage_password@localhost:5432/lineage_db
```

### URLs Once Running

| What | URL |
|---|---|
| React Dashboard | http://localhost:5173 |
| FastAPI Swagger Docs | http://localhost:8000/docs |
| Health Check | http://localhost:8000/health |
| Neo4j Browser UI | http://localhost:7474 (login: neo4j / lineage_password) |

### Windows-Specific Gotcha
```powershell
# ALWAYS use psycopg2, NOT psycopg2-binary on Windows
pip install -r requirements.txt --prefer-binary
```

---

## 11. API Reference

### POST `/lineage/events`
Ingest a lineage event. Called by Airflow, SQL parser scripts, and dbt scripts.

**Request body (OpenLineage format):**
```json
{
  "eventType": "COMPLETE",
  "eventTime": "2024-01-01T10:00:00Z",
  "run": { "runId": "uuid-here" },
  "job": { "namespace": "postgres", "name": "load_orders" },
  "inputs":  [{ "namespace": "postgres", "name": "raw.orders", "facets": {} }],
  "outputs": [{ "namespace": "postgres", "name": "clean.orders", "facets": {} }]
}
```
**Responses:**
- `200 {"status": "ok"}` — COMPLETE or FAIL event stored
- `200 {"status": "skipped"}` — START events intentionally ignored
- `422` — Validation error (missing fields, bad datetime format)
- `500` — Neo4j or Postgres write failed

---

### GET `/lineage/upstream/{dataset_uri}`
Get full ancestry of a dataset — everything that produced it.

**Example:** `GET /lineage/upstream/postgres://clean.orders?depth=5`

**Response:**
```json
{
  "dataset_id": "postgres://clean.orders",
  "direction": "upstream",
  "depth": 5,
  "nodes": [
    { "id": "4:abc", "label": "Dataset", "properties": { "uri": "...", "name": "..." } },
    { "id": "4:def", "label": "Job", "properties": { "name": "load_orders" } }
  ],
  "edges": [
    { "source_id": "4:abc", "target_id": "4:def", "type": "CONSUMES", "properties": {} }
  ],
  "node_count": 5,
  "edge_count": 4
}
```

---

### GET `/lineage/downstream/{dataset_uri}`
Get everything this dataset feeds into (same schema as upstream).

---

### GET `/lineage/runs/{job_name}`
Get execution history of a specific job from PostgreSQL.

---

### GET `/lineage/runs/global`
Get the most recent runs across ALL jobs. Used by the System Runs dashboard view.

---

### GET `/lineage/datasets`
List all datasets currently in the graph. Used by the Directory view.

---

### GET `/health`
Returns DB connectivity status.
```json
{ "status": "healthy", "services": { "neo4j": "ok", "postgres": "ok" } }
```

---

## 12. Testing Strategy

### Three layers of tests:

**Layer 1: Integration Tests (scripts/test_stage*.py)**
Run against real DBs. Use httpx.TestClient to call FastAPI. Write real data, query it, assert correctness, clean up.

```powershell
docker compose up -d   # must be running

python scripts/test_stage2.py   # 15 tests: ingestion layer
python scripts/test_stage3.py   # 34 tests: storage layer
python scripts/test_stage4.py   # 25 tests: query API
```

### What Is Tested

| Test | What It Verifies |
|---|---|
| COMPLETE event -> 200 ok | Full ingestion path works |
| START event -> 200 skipped | Business rule: ignore START events |
| Missing field -> 422 | Pydantic validation catches bad input |
| Same event posted twice -> 1 node | MERGE idempotency works |
| PII input -> PII on output | Tag propagation works |
| Upstream of `reporting.dashboard` returns 10 nodes | Graph traversal correct |
| `depth=1` returns exactly 3 nodes | Depth limiting works |
| SQL: CTE not listed as input | SQL parser CTE filtering works |
| dbt: extracts dep_name from node ID | dbt parser name parsing works |

*(How to explain: "We don't use mocks on the database layer. We test against a real Neo4j and real Postgres. This is called integration testing. It is slower but catches real bugs — like the depth*2 issue we found where the query was wrong.")*

---

## 13. The Build Stages (What Was Done When)

### Stage 1 — Foundation ✅ COMPLETE
- Docker Compose: Neo4j + PostgreSQL
- `app/models.py` — internal dataclasses
- `app/db_client.py` — connection helpers
- `app/main.py` — FastAPI skeleton + `/health`
- Neo4j constraints applied manually in browser (job_name_unique, dataset_uri_unique, run_id_unique)
- PostgreSQL `run_log` table created via Docker init SQL

### Stage 2 — Ingestion Layer ✅ COMPLETE
- `app/ingestion/pydantic_models.py` — validates OL events
- `app/ingestion/converter.py` — OL to LineageEvent translation
- `app/ingestion/router.py` — POST /lineage/events with START skip logic
- `app/storage/graph_writer.py` — **STUB** (logs only, no real DB write yet)
- `parsers/sql_parser.py` — SQLGlot multi-dialect SQL parser
- `parsers/dbt_parser.py` — manifest.json parser
- 15 integration tests all passing

### Stage 3 — Storage Layer ✅ COMPLETE (replaced the stub)
- `app/storage/graph_writer.py` — **REAL** (Neo4j MERGE + Postgres INSERT)
- PII tag propagation at write time (1-hop)
- 34 integration tests all passing

### Stage 4 — Query API ✅ COMPLETE
- `app/api/pydantic_models.py` — response schemas
- `app/api/cypher_queries.py` — Cypher strings
- `app/api/router.py` — upstream, downstream, runs, datasets, global runs
- Depth calculation bug found and fixed: user depth=N → max_edges=N*2
- Route ordering bug fixed: /runs/global must be before /runs/{job_id:path}
- 25 integration tests all passing

### Stage 5 — React Dashboard ✅ COMPLETE
- `frontend/` — Vite + React + Tailwind + React Flow + Dagre
- Live graph auto-polls every 4 seconds
- Dataset=blue nodes, Job=orange nodes
- PRODUCES=green edges, CONSUMES=orange edges with labels
- Side panels: node properties, PII badges, run history table
- `run_live_demo.py` + `pipeline_plugin.py` — one-command demo orchestrator

---

## 14. What Is Still To Build

| Item | Notes |
|---|---|
| Multi-hop retroactive PII propagation | Currently only 1-hop at write time |
| Airflow integration test | docker-compose.yml has Airflow service defined but untested |
| Neo4j constraint automation | Currently applied manually in Neo4j browser |
| Real Airflow DAG plugin | `airflow_dags/` folder exists, to be completed |
| Impact analysis endpoint | "Which jobs break if I change this schema?" |
| Column-level lineage | Currently table-level only |
| OpenLineage facet parsing | Column-level PII flags from Airflow facets |
| RAG Answer Generation module | AI module on top of lineage graph — Stage E in progress |

---

## 15. Key Design Decisions

*(These are the "why" answers for senior-level conversations)*

### Decision 1: Pydantic only at the HTTP boundary
`app/ingestion/pydantic_models.py` and `app/api/pydantic_models.py` use Pydantic. Everything else uses Python `@dataclass`.

**Why:** Pydantic v2 is powerful but heavy. Internal code doesn't need HTTP validation. If you replace FastAPI tomorrow, all internal logic stays unchanged.

### Decision 2: The Converter Pattern
`app/ingestion/converter.py` is the ONLY file that knows OpenLineage field names (`runId`, `nominalTime`, `eventType`). After conversion, no other file sees those names.

**Why:** OpenLineage is an external standard that changes. If OL schema changes, you fix ONE file — not 20.

### Decision 3: MERGE not CREATE for Neo4j
All Neo4j writes use `MERGE`. Never `CREATE`.

**Why:** Safe for retries. If Airflow re-sends an event (network failure), you get exactly 1 node — not duplicates. This is called idempotency.

### Decision 4: PostgreSQL is NOT the source of truth
If Postgres write fails, it is logged but NOT raised. Neo4j is the source of truth.

**Why:** PostgreSQL `run_log` is an audit trail for humans. The graph structure lives in Neo4j. These are separate concerns. Losing an audit row is recoverable. Blocking the ingestion pipeline on an audit failure is not acceptable.

### Decision 5: Depth × 2 in Cypher
When user says `depth=3`, Cypher traverses `max_edges=6`.

**Why:** To go from one Dataset to another Dataset, you must cross 2 edges: `Dataset->Job->Dataset`. One "hop" in user terms = 2 edges in graph terms. This was discovered as a real bug during Stage 4 testing.

### Decision 6: Stub-first development
Stage 2 built a fake `write_event()` that just logged. Stage 3 replaced the file. The interface never changed.

**Why:** Stages can work independently. Stage 2 tests the ingestion + conversion pipeline in isolation without needing DB infrastructure. The public interface signature `write_event(event: LineageEvent) -> None` was locked from Day 1.

### Decision 7: FastAPI runs locally, DBs in Docker
**Why:** Hot reload for Python works unreliably inside Docker on Windows. DBs need persistence volumes (Docker). FastAPI code changes constantly during dev, so it runs locally with `--reload`.

*(How to explain each decision: "Every one of these has a 'what goes wrong without it' story. If we used CREATE instead of MERGE, duplicate events from Airflow would fill the graph with duplicates. If the converter didn't exist, every file would depend on Airflow's naming conventions and one OL spec update would break everything.")*

---

## 16. Glossary

| Term | Meaning |
|---|---|
| **OpenLineage** | Open standard JSON format for lineage events. Airflow supports it natively. We receive events in this format. |
| **Lineage** | The record of how data flows from source to destination across transformations |
| **Upstream** | Everything that contributed to creating a dataset (ancestors, input side) |
| **Downstream** | Everything that consumes a dataset (descendants, output side) |
| **PII** | Personally Identifiable Information. Datasets tagged with `pii`. Our system auto-propagates this tag 1 hop at write time. |
| **MERGE** | Neo4j Cypher command: "Create this node IF it doesn't exist, otherwise match it". Prevents duplicates. |
| **Idempotency** | Calling the same operation multiple times produces the same result as calling it once. |
| **Cypher** | Neo4j's query language. Like SQL but for graphs. `MATCH (n:Dataset) RETURN n` |
| **bolt://** | Neo4j's binary driver protocol. Like `postgresql://` but for Neo4j. |
| **DAG** | Directed Acyclic Graph. A graph with direction and no cycles. Airflow pipelines and our lineage graph are both DAGs. |
| **dbt** | Data Build Tool. A SQL transformation framework. Its `manifest.json` contains the full dependency graph of all models. |
| **SQLGlot** | Python library that parses SQL into an AST tree. We use it to extract table names. |
| **React Flow** | React library for node-edge canvas rendering. Powers the interactive graph in the dashboard. |
| **Dagre** | Auto-layout algorithm for directed graphs. Arranges nodes left-to-right automatically. |
| **run_log** | PostgreSQL table. One row per job execution. Stores run_id, status, timestamps, input/output datasets. |
| **facets** | In OpenLineage, optional metadata bags (e.g. column schema, PII flags). We receive them but don't process most yet. |
| **stub** | A placeholder implementation that does nothing real (e.g. "just log it"). Used to unblock other stages during development. |

---

*Document maintained by: Aary Tadwalkar and AI Agent*
*Last updated: April 2026*
*Source of truth for build plan: `docs/lineage_engine_master_build_doc.md`*
*Memory bank (session state): `memory-bank/` directory*

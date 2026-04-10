# Lineage Engine — Full Execution Plan
## Real Data Testing + Dashboard Build

---

## WEEK 1 — Real Data, Existing Backend

---

### DAY 1 — jaffle_shop: dbt Pipeline Testing (Paths B + C)

#### Goal
Feed real SQL files and a real `manifest.json` into your existing parsers. Verify a proper multi-table lineage graph appears in Neo4j.

---

#### Step 1 — Install dbt with DuckDB

```bash
pip install dbt-core dbt-duckdb
```

DuckDB is an in-memory database — no server, no Docker needed. dbt will run SQL against it and produce real output tables.

---

#### Step 2 — Clone jaffle_shop

```bash
git clone https://github.com/dbt-labs/jaffle_shop_duckdb
cd jaffle_shop_duckdb
```

**What is jaffle_shop?**
A fake e-commerce company dataset: customers, orders, payments. It is the official dbt demo project used worldwide for exactly this kind of testing. It has a realistic multi-hop dependency graph across 6 tables.

**The pipeline it represents:**
```
raw_customers ──→ stg_customers ──→ customers (final)
raw_orders    ──→ stg_orders    ──→ orders    (final) ──→ order_payments
raw_payments  ──→ stg_payments  ──┘
```

---

#### Step 3 — Run the pipeline

```bash
dbt deps        # install dbt packages
dbt run         # executes all SQL models against DuckDB, creates real tables
```

**What happens during `dbt run`:**
- dbt reads all `.sql` files in `/models/`
- Executes them in dependency order (stg_ models first, then final models)
- Writes actual tables into a local DuckDB file (`jaffle_shop.duckdb`)
- Generates `target/manifest.json` — the full dependency graph

**What you should see:** No errors. 6 models created successfully.

---

#### Step 4 — Feed manifest.json to your dbt_parser.py

```python
# scripts/ingest_dbt_manifest.py
from parsers.dbt_parser import parse_dbt_manifest
import httpx

events = parse_dbt_manifest("../jaffle_shop_duckdb/target/manifest.json")

for event in events:
    r = httpx.post("http://localhost:8000/lineage/events", json=event.dict())
    print(f"{event.job.name:50s} → {r.status_code} {r.json()}")

print(f"\nTotal events ingested: {len(events)}")
```

**What to expect:**
- 6 events (one per dbt model, skipping test nodes and source-only nodes)
- Each event has inputs (upstream models) and outputs (the model itself)
- All should return `{status: ok}`

---

#### Step 5 — Feed the .sql files to your sql_parser.py

```python
# scripts/ingest_sql_files.py
import os, httpx, uuid
from parsers.sql_parser import parse_sql_lineage
from datetime import datetime, timezone

SQL_DIR = "../jaffle_shop_duckdb/models"

for root, dirs, files in os.walk(SQL_DIR):
    for filename in files:
        if not filename.endswith(".sql"):
            continue
        filepath = os.path.join(root, filename)
        with open(filepath, "r") as f:
            sql_text = f.read()

        job_name = filename.replace(".sql", "")
        try:
            event = parse_sql_lineage(
                sql=sql_text,
                job_name=job_name,
                namespace="duckdb://jaffle_shop"
            )
            r = httpx.post("http://localhost:8000/lineage/events", json=event.dict())
            print(f"{job_name:40s} → {r.status_code} {r.json()}")
        except Exception as e:
            print(f"{job_name:40s} → PARSE ERROR: {e}")
```

**What to expect:**
- Some models use dbt's `{{ ref() }}` syntax — your SQLGlot parser will skip or partially parse these (expected, not a bug — Path C handles dbt SQL, Path B handles raw SQL)
- Staging models with plain SQL JOINs and CTEs will parse correctly
- You will see inputs/outputs extracted from FROM and INSERT INTO clauses

---

#### Step 6 — Verify in Neo4j Browser

Open `http://localhost:7474` and run these queries:

```cypher
-- See everything
MATCH (n) RETURN n

-- See only the lineage flow (left to right)
MATCH path = (d1:Dataset)-[:CONSUMES|PRODUCES*]->(d2:Dataset)
RETURN path

-- Count what was created
MATCH (j:Job) RETURN count(j) AS jobs
MATCH (d:Dataset) RETURN count(d) AS datasets
MATCH (r:Run) RETURN count(r) AS runs

-- See a specific dataset's connections
MATCH (d:Dataset {name: "stg_orders"})-[r]-(n)
RETURN d, r, n
```

**What you should see in the graph:**
- Blue nodes = Datasets (raw_orders, stg_orders, orders, etc.)
- Orange nodes = Jobs (stg_orders transformer, orders transformer, etc.)
- Purple nodes = Runs (execution records)
- Arrows flowing left to right: raw → stg → final

**Neo4j Browser tips:**
- Click a node → properties panel appears on the right
- Drag nodes to rearrange layout
- Use the layout button (top right) to switch to hierarchical layout for cleaner flow

---

#### Key things to watch for / Possible Issues

| Issue | Why | Fix |
|---|---|---|
| dbt ref() syntax not parsed by sql_parser | Expected — dbt SQL uses templating not raw SQL | Use dbt_parser for dbt models, sql_parser for plain SQL only |
| 0 events from dbt_parser | manifest.json path wrong, or dbt compile not run | Run `dbt compile` explicitly, check the path |
| Duplicate dataset nodes | Same table referenced by both parsers | MERGE in Neo4j handles this — no duplicates, expected behavior |
| Parser throws on CTE | Your sql_parser handles CTEs — check the specific syntax | Log the SQL that failed, debug the SQLGlot call |

---

### DAY 2 — Seed Real OpenLineage Events + Test All API Endpoints

#### Goal
Simulate a realistic multi-hop Airflow pipeline by manually crafting and POSTing OpenLineage events. Test all 3 query endpoints against real seeded data. Verify run_log in Postgres.

---

#### Step 1 — Write seed_real_events.py

```python
# scripts/seed_real_events.py
import httpx, uuid
from datetime import datetime, timezone, timedelta

BASE = "http://localhost:8000"

def ts(offset_minutes=0):
    t = datetime.now(timezone.utc) + timedelta(minutes=offset_minutes)
    return t.isoformat()

# A realistic 5-job e-commerce pipeline
# s3://landing/orders.csv
#   → ingest.load_raw_orders
#     → postgres://prod/raw.orders
#       → transform.clean_orders
#         → postgres://prod/staging.orders ─┐
#                                           ├→ transform.enrich_orders
#         → postgres://prod/staging.customers ─┘
#           → transform.clean_customers       → postgres://prod/mart.orders_enriched
#                                               → reporting.build_dashboard
#                                                 → postgres://prod/reporting.order_summary

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
    # Simulate a FAIL event to test that path
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

print("Seeding events...\n")
for e in events:
    r = httpx.post(f"{BASE}/lineage/events", json=e)
    print(f"[{e['eventType']:8s}] {e['job']['name']:45s} → {r.status_code} {r.json()}")

print("\nDone.")
```

---

#### Step 2 — Test the upstream endpoint

```bash
# URL-encode the dataset URI: postgres://prod:5432/reporting.order_summary
# becomes: postgres%3A%2F%2Fprod%3A5432%2Freporting.order_summary

curl "http://localhost:8000/lineage/upstream/postgres%3A%2F%2Fprod%3A5432%2Freporting.order_summary?depth=5"
```

**What you should get back:**
```json
{
  "nodes": [
    {"id": "postgres://prod:5432/reporting.order_summary", "type": "Dataset"},
    {"id": "reporting.build_dashboard", "type": "Job"},
    {"id": "postgres://prod:5432/mart.orders_enriched", "type": "Dataset"},
    {"id": "transform.enrich_orders", "type": "Job"},
    {"id": "postgres://prod:5432/staging.orders", "type": "Dataset"},
    {"id": "postgres://prod:5432/staging.customers", "type": "Dataset"},
    ...
  ],
  "edges": [...]
}
```

**What to verify:**
- depth=1 returns only the immediate job and its inputs (3 nodes)
- depth=2 returns one more hop back (5 nodes)
- depth=5 returns the entire chain including S3 source files
- Multi-input job (enrich_orders) shows BOTH staging.orders AND staging.customers as upstream

---

#### Step 3 — Test the downstream endpoint

```bash
curl "http://localhost:8000/lineage/downstream/postgres%3A%2F%2Fprod%3A5432%2Fraw.orders?depth=5"
```

**What to verify:**
- raw.orders → clean_orders job → staging.orders → enrich_orders → mart → dashboard → summary
- Does NOT include raw.customers branch (different upstream path)

---

#### Step 4 — Test the runs endpoint

```bash
curl "http://localhost:8000/lineage/runs/transform.clean_orders"
```

**What to verify:**
- Returns 2 entries (one COMPLETE, one FAIL — both were seeded)
- Each entry has run_id, status, started_at, ended_at
- FAIL run has no ended_at (or null) — expected since FAIL events may not include end time

---

#### Step 5 — Verify Postgres run_log directly

```bash
docker exec -it <postgres_container_name> psql -U lineage_user -d lineage_db

# Inside psql:
SELECT * FROM run_log ORDER BY started_at DESC;
SELECT job_name, status, COUNT(*) FROM run_log GROUP BY job_name, status;
```

**What to verify:**
- 7 rows (6 COMPLETE + 1 FAIL)
- All fields populated correctly (run_id, job_name, status, timestamps)
- FAIL event is recorded (your system should store FAIL events, not skip them)

---

#### Key things to watch for / Possible Issues

| Issue | Why | Fix |
|---|---|---|
| 404 on upstream query | URI encoding wrong | Double-check `%3A` = `:` and `%2F` = `/` |
| depth=5 returns too few nodes | Hop calculation bug (known from Stage 4) | Internally depth is multiplied by 2 for Dataset→Job→Dataset — verify cypher query |
| FAIL event not in run_log | graph_writer not writing FAIL events | Check graph_writer.py — should write both COMPLETE and FAIL |
| Multi-input job not showing both parents | Cypher traversal issue | Run `MATCH (d:Dataset {name:"staging.orders"})-[r]-(n) RETURN d,r,n` in Neo4j to verify edges exist |

---

## WEEK 2 — Build the Dashboard

---

### DAY 1-2 — React App Scaffold + Graph Rendering

#### Goal
Create a React app that connects to your FastAPI backend and renders lineage graphs left-to-right using React Flow.

---

#### Tech stack decision

| Library | Purpose |
|---|---|
| React + Vite | Frontend framework (fast dev setup) |
| React Flow | Graph visualization (left-to-right DAG layout) |
| dagre | Auto-layout algorithm for React Flow (left-to-right positioning) |
| TailwindCSS | Styling |
| axios | HTTP calls to your FastAPI |

---

#### Project setup

```bash
# Inside your lineage-engine folder
npm create vite@latest frontend -- --template react
cd frontend
npm install
npm install reactflow dagre @dagrejs/dagre
npm install axios
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p
```

---

#### Folder structure for frontend

```
frontend/
├── src/
│   ├── App.jsx                 ← root, routing between screens
│   ├── api/
│   │   └── lineageApi.js       ← all axios calls to FastAPI
│   ├── components/
│   │   ├── SearchBar.jsx       ← dataset search input
│   │   ├── LineageGraph.jsx    ← React Flow graph component
│   │   ├── NodeSidePanel.jsx   ← properties panel (appears on node click)
│   │   ├── RunHistoryTable.jsx ← runs table for a selected job
│   │   └── Toolbar.jsx         ← upstream/downstream toggle, depth slider
│   ├── utils/
│   │   ├── graphLayout.js      ← dagre left-to-right layout function
│   │   └── nodeStyles.js       ← color definitions per node type
│   └── screens/
│       ├── ExplorerScreen.jsx  ← main lineage explorer
│       └── RunsScreen.jsx      ← run history screen
```

---

#### Core API wrapper (lineageApi.js)

```javascript
// src/api/lineageApi.js
import axios from 'axios';

const API = axios.create({ baseURL: 'http://localhost:8000' });

export const getUpstream = (datasetUri, depth) =>
    API.get(`/lineage/upstream/${encodeURIComponent(datasetUri)}`, { params: { depth } });

export const getDownstream = (datasetUri, depth) =>
    API.get(`/lineage/downstream/${encodeURIComponent(datasetUri)}`, { params: { depth } });

export const getRuns = (jobId) =>
    API.get(`/lineage/runs/${encodeURIComponent(jobId)}`);
```

---

#### Left-to-right layout using dagre (graphLayout.js)

```javascript
// src/utils/graphLayout.js
import dagre from '@dagrejs/dagre';

export function applyDagreLayout(nodes, edges) {
    const g = new dagre.graphlib.Graph();
    g.setGraph({ rankdir: 'LR', ranksep: 120, nodesep: 60 }); // LR = Left to Right
    g.setDefaultEdgeLabel(() => ({}));

    nodes.forEach(node => g.setNode(node.id, { width: 160, height: 50 }));
    edges.forEach(edge => g.setEdge(edge.source, edge.target));

    dagre.layout(g);

    return nodes.map(node => {
        const pos = g.node(node.id);
        return { ...node, position: { x: pos.x - 80, y: pos.y - 25 } };
    });
}
```

---

#### Node color coding (nodeStyles.js)

```javascript
// src/utils/nodeStyles.js
export const NODE_STYLES = {
    Dataset: {
        background: '#4A90D9',   // blue
        color: '#ffffff',
        border: '2px solid #2E6FA3',
        borderRadius: '8px',
        padding: '8px 14px',
        fontSize: '12px',
        fontWeight: '600',
    },
    Job: {
        background: '#E8832A',   // orange
        color: '#ffffff',
        border: '2px solid #B5621E',
        borderRadius: '8px',
        padding: '8px 14px',
        fontSize: '12px',
        fontWeight: '600',
    },
};
```

---

### DAY 3 — Search, Node Click Panel, Full Interactivity

#### SearchBar component — behaviour spec

```
User types a dataset name or URI
  ↓
As they type: show autocomplete suggestions (GET /lineage/search if you add it later,
              or just free text for now)
  ↓
User hits Enter or clicks Search
  ↓
Two buttons appear: [Upstream ↑]  [Downstream ↓]
  ↓
User clicks one
  ↓
API call fires → graph renders
```

**Fields:**
- Text input: placeholder "Enter dataset name or URI..."
- Search button (or Enter key)
- After search: direction toggle buttons (Upstream / Downstream)
- Depth slider: 1 to 6, default 3, label "Hops"

---

#### NodeSidePanel — what to show on click

When a **Dataset node** is clicked:
```
Panel title: "Dataset"
─────────────────────────────
Name:         raw.orders
URI:          postgres://prod:5432/raw.orders
Namespace:    postgres://prod:5432
Tags:         [pii]  (if present, shown as red badge)
─────────────────────────────
Actions:
  [→ Explore Upstream]       ← re-runs upstream query with this node as root
  [→ Explore Downstream]     ← re-runs downstream query with this node as root
```

When a **Job node** is clicked:
```
Panel title: "Job"
─────────────────────────────
Name:         transform.clean_orders
Namespace:    airflow
Owner:        dev
Orchestrator: airflow
Created at:   2024-01-15
─────────────────────────────
Actions:
  [→ View Run History]       ← navigates to RunsScreen for this job
```

**Panel behaviour:**
- Slides in from the right side of the graph
- Clicking blank canvas area closes it
- Clicking a different node updates it (does not close and reopen)

---

#### Graph interaction behaviour

| User action | What happens |
|---|---|
| Click node | Side panel opens with node properties |
| Click blank canvas | Side panel closes |
| Double-click Dataset node | Re-runs query with that dataset as root (drill down) |
| Hover edge | Edge highlights, tooltip shows relationship type (CONSUMES / PRODUCES) |
| Scroll | Zoom in/out |
| Drag canvas | Pan the view |
| Drag node | Node moves (React Flow default) |
| Click [Upstream] button in side panel | Re-queries with that node, direction flips |

---

### DAY 4 — Run History Screen

#### RunHistoryTable — full spec

**Trigger:** Click "View Run History" in the Job side panel.

**Layout:**
```
← Back to Explorer                    Job: transform.clean_orders
─────────────────────────────────────────────────────────────────
Run ID          Status    Started At            Duration    
─────────────────────────────────────────────────────────────────
abc-001         ✅ COMPLETE  2024-01-15 10:32:00   1m 45s
xyz-089         ❌ FAIL      2024-01-14 10:32:00   0m 12s
def-234         ✅ COMPLETE  2024-01-13 10:32:00   1m 50s
─────────────────────────────────────────────────────────────────
Showing 3 runs
```

**Status badge colours:**
- COMPLETE → green background, white text
- FAIL → red background, white text
- (future) RUNNING → yellow background, dark text

**Duration calculation:**
```javascript
// Computed from started_at and ended_at
const duration = (ended_at - started_at) in seconds
// Display as: "1m 45s" or "12s" or "N/A" if ended_at is null
```

**Sorting:** Default newest first. Click column header to sort.

**Back button:** Returns to Explorer screen with previous graph still rendered (do not re-fetch).

---

### DAY 5 — Polish + Local Deploy

#### Visual polish checklist

- Consistent fonts (use Inter or system-ui)
- Proper empty state: if no graph loaded yet, show a helpful prompt message in center of canvas
- Loading spinner while API calls are in-flight
- Error state: if API returns 404 (dataset not found), show clear message "Dataset not found — check the URI and try again"
- Responsive layout: sidebar + main canvas, sidebar collapses on small screens
- Page title + favicon (your system name)

---

#### Layout of the full dashboard

```
┌─────────────────────────────────────────────────────────────┐
│  HEADER: "Lineage Engine"          [Explorer] [Run History] │
├──────────────┬──────────────────────────────────────────────┤
│              │                                              │
│  LEFT        │   MAIN CANVAS                               │
│  SIDEBAR     │   (React Flow graph renders here)           │
│              │                                              │
│  Search box  │   Left-to-right flow:                       │
│              │   [s3 file] → [job] → [raw] → [job] → [stg] │
│  Direction:  │                                              │
│  ○ Upstream  │                                              │
│  ● Downstream│                                              │
│              │                                              │
│  Depth: ─●── │                                              │
│  (slider 1-6)│                                              │
│              │                                ┌──────────┐  │
│  Last search │                                │ SIDE     │  │
│  history     │                                │ PANEL    │  │
│  (clickable) │                                │ (on node │  │
│              │                                │  click)  │  │
│              │                                └──────────┘  │
└──────────────┴──────────────────────────────────────────────┘
```

---

#### Local deploy

```bash
cd frontend
npm run build          # creates dist/ folder
npm run preview        # serves the built app locally at http://localhost:4173
```

For development (with hot reload):
```bash
npm run dev            # runs at http://localhost:5173
```

**CORS — you will need this on your FastAPI:**
```python
# app/main.py — add this
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:4173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## WEEK 3 — Real Live Pipeline with Dagster (Optional)

---

### Goal
Move from simulated events to a real running pipeline that automatically POSTs OpenLineage events to your engine with zero manual intervention.

---

### Why Dagster over Airflow

| Factor | Airflow | Dagster |
|---|---|---|
| Windows setup | Complex, needs WSL | Works natively |
| OpenLineage support | Plugin install + config | Built-in |
| Learning curve | Steep | Gentler |
| Local UI | Basic | Rich, modern |
| For testing purposes | Overkill | Right-sized |

---

### Step 1 — Install Dagster

```bash
pip install dagster dagster-webserver dagster-openlineage
```

---

### Step 2 — Define a simple 3-job pipeline

```python
# dagster_pipeline/pipeline.py
from dagster import asset, define_asset_job, Definitions
import duckdb, pandas as pd

@asset
def raw_orders():
    """Simulates loading raw order data"""
    conn = duckdb.connect("pipeline.duckdb")
    conn.execute("""
        CREATE OR REPLACE TABLE raw_orders AS
        SELECT 1 AS order_id, 101 AS customer_id, 250.00 AS amount, 'valid' AS status
        UNION ALL
        SELECT 2, 102, 75.50, 'valid'
        UNION ALL
        SELECT 3, 103, 430.00, 'pending'
    """)
    return "raw_orders created"

@asset(deps=[raw_orders])
def staging_orders(raw_orders):
    """Cleans and validates orders"""
    conn = duckdb.connect("pipeline.duckdb")
    conn.execute("""
        CREATE OR REPLACE TABLE staging_orders AS
        SELECT order_id, customer_id, amount
        FROM raw_orders
        WHERE status = 'valid'
    """)
    return "staging_orders created"

@asset(deps=[staging_orders])
def order_summary(staging_orders):
    """Aggregates orders by customer"""
    conn = duckdb.connect("pipeline.duckdb")
    conn.execute("""
        CREATE OR REPLACE TABLE order_summary AS
        SELECT customer_id, COUNT(*) AS order_count, SUM(amount) AS total_spent
        FROM staging_orders
        GROUP BY customer_id
    """)
    return "order_summary created"

pipeline_job = define_asset_job("orders_pipeline", selection="*")

defs = Definitions(assets=[raw_orders, staging_orders, order_summary], jobs=[pipeline_job])
```

---

### Step 3 — Wire OpenLineage to your engine

```python
# dagster_pipeline/dagster.yaml  (workspace config)
# Set the OpenLineage endpoint to point at your engine
```

```bash
# Environment variable — Dagster picks this up automatically
export DAGSTER_OPENLINEAGE_TRANSPORT_URL=http://localhost:8000
export DAGSTER_OPENLINEAGE_NAMESPACE=dagster_local
```

---

### Step 4 — Run it and watch events arrive

```bash
# Terminal 1 — start Dagster UI
dagster dev -f dagster_pipeline/pipeline.py

# Open http://localhost:3000
# Click "Materialize All" to run the pipeline
```

**What happens:**
- Dagster runs raw_orders → staging_orders → order_summary in order
- After each asset materializes, Dagster fires an OpenLineage event automatically
- Your FastAPI receives 3 POST requests at `/lineage/events`
- Neo4j graph updates in real time
- Your dashboard (if running) can be refreshed to show the new lineage

---

### Verification after Dagster run

```bash
# Check your engine received the events
curl http://localhost:8000/lineage/downstream/dagster_local%2Fraw_orders?depth=3

# Check Neo4j
# Open http://localhost:7474
# MATCH (n) RETURN n
# Should show 3 new dataset nodes + 3 job nodes from the Dagster run
```

---

## Summary Checklist

### Week 1 — Done when:
- [ ] dbt run completes with 6 models in jaffle_shop
- [ ] manifest.json ingested, 6 events posted successfully
- [ ] SQL files parsed, events posted (partial success acceptable for dbt-syntax files)
- [ ] Neo4j browser shows multi-hop graph with correct node types and edge directions
- [ ] seed_real_events.py posts 7 events (6 COMPLETE + 1 FAIL), all succeed
- [ ] Upstream query for `reporting.order_summary` at depth=5 returns full chain
- [ ] Downstream query for `raw.orders` returns full affected chain
- [ ] Runs query for `transform.clean_orders` returns 2 entries (COMPLETE + FAIL)
- [ ] Postgres run_log has 7 rows with correct fields

### Week 2 — Done when:
- [ ] React app runs at localhost:5173 without errors
- [ ] Search + direction toggle + depth slider all functional
- [ ] Graph renders left-to-right with correct colours (blue=Dataset, orange=Job)
- [ ] Clicking a Dataset node opens side panel with correct properties
- [ ] Clicking a Job node opens side panel with "View Run History" button
- [ ] Run History screen shows table with correct columns and status badges
- [ ] Back button returns to Explorer with graph still visible
- [ ] Empty state, loading, and error states all handled
- [ ] CORS configured, frontend talks to backend successfully
- [ ] `npm run build` produces a working static build

### Week 3 — Done when:
- [ ] Dagster installed and UI running at localhost:3000
- [ ] Pipeline defined with 3 assets (raw → staging → summary)
- [ ] Pipeline runs successfully (all 3 assets materialize)
- [ ] Real OpenLineage events received by your engine automatically
- [ ] Lineage for Dagster pipeline visible in your dashboard

---

## Reference — API Endpoints

```
POST /lineage/events
  Body: OpenLineage JSON event
  Returns: {status: "ok"} or {status: "skipped"}

GET /lineage/upstream/{dataset_uri}?depth=N
  dataset_uri: URL-encoded full URI (e.g. postgres%3A%2F%2Fprod%3A5432%2Fraw.orders)
  depth: number of Dataset-to-Dataset hops (default 3, max 6 recommended)
  Returns: {nodes: [...], edges: [...]}

GET /lineage/downstream/{dataset_uri}?depth=N
  Same as upstream but traverses forward
  Returns: {nodes: [...], edges: [...]}

GET /lineage/runs/{job_name}
  job_name: exact job name string (URL-encoded if contains special chars)
  Returns: [{run_id, job_name, status, started_at, ended_at}, ...]
```

---

## Reference — Node + Edge Response Shape

```json
{
  "nodes": [
    {
      "id": "postgres://prod:5432/raw.orders",
      "type": "Dataset",
      "properties": {
        "name": "raw.orders",
        "namespace": "postgres://prod:5432",
        "uri": "postgres://prod:5432/raw.orders",
        "tags": []
      }
    },
    {
      "id": "transform.clean_orders",
      "type": "Job",
      "properties": {
        "name": "transform.clean_orders",
        "namespace": "airflow",
        "owner": "dev",
        "orchestrator": "airflow"
      }
    }
  ],
  "edges": [
    {
      "source": "postgres://prod:5432/raw.orders",
      "target": "transform.clean_orders",
      "type": "CONSUMES"
    },
    {
      "source": "transform.clean_orders",
      "target": "postgres://prod:5432/staging.orders",
      "type": "PRODUCES"
    }
  ]
}
```

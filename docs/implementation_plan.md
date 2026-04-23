# Lineage Engine — Implementation Plan (Staged)

> **Who this is for:** Aary Tadwalkar + AI Agent team.  
> **Based on:** Full code audit vs dev plan docs (April 2026).  
> **Goal:** Verify current state, then define what to build next in proper stages.

---

## Current State Audit

### What the Dev Plan Defined vs What Exists

| Stage | Plan Said | Reality | Status |
|---|---|---|---|
| Stage 1 — Foundation | Docker + FastAPI + DBs + `/health` | ✅ All present and tested | ✅ DONE |
| Stage 2 — Ingestion | POST endpoint, Pydantic validation, Converter, SQL/dbt parsers | ✅ All present, 15 tests pass | ✅ DONE |
| Stage 3 — Storage | Neo4j MERGE writes, Postgres audit log, PII propagation | ✅ All present, 34 tests pass | ✅ DONE |
| Stage 4 — Query API | upstream, downstream, runs, datasets | ✅ Endpoints exist, 25 tests pass | ✅ DONE |
| Stage 5 — Frontend | React + ReactFlow + Dagre dashboard | ✅ Built and running | ✅ DONE |

### 🔴 Known Broken Thing You Reported: Upstream / Downstream Not Working

**Root Cause (confirmed by code audit):**  
The frontend `NodeSidePanel.jsx` calls `onExplore(node.id, 'upstream')`.  
But `node.id` is a Neo4j **internal element ID** like `"4:abc-123:0"` — not the dataset URI.

The backend expects:  
```
GET /lineage/upstream/postgres://clean.orders   ← a URI string
```

What the frontend actually sends:  
```
GET /lineage/upstream/4:abc-123:0   ← a Neo4j element_id (WRONG)
```

This causes a 404 every time you click "Explore Upstream" or "Explore Downstream" from the side panel.

**Secondary Issue:**  
In `lineageApi.js`, the URI is URL-encoded:  
```js
`/lineage/upstream/${encodeURIComponent(datasetUri)}`
```
But FastAPI uses `{dataset_id:path}` path param — it receives the **encoded** string, not the decoded URI.  
The `:path` suffix catches slashes correctly, BUT `encodeURIComponent` converts `:` to `%3A` and `//` to `%2F%2F`, which FastAPI's path param does NOT auto-decode. So `postgres://clean.orders` becomes `postgres%3A%2F%2Fclean.orders` — a string Neo4j won't find.

---

## Stage-by-Stage Implementation Plan

---

## 🟥 Stage Fix-0 — Fix Upstream / Downstream (THE BLOCKER)
**Scope:** 2 files. No new features.  
**Time estimate:** 30 minutes.

### The Bug (summarized simply)
- Side panel sends Neo4j `element_id` → backend expects `uri` → 404 always
- Frontend double-encodes the URI → backend receives garbled URI → 404 always

### Fix A — `NodeSidePanel.jsx`

#### [MODIFY] [NodeSidePanel.jsx](file:///c:/Rubiscape/lineage-engine/frontend/src/components/NodeSidePanel.jsx)

Change line 78 and 85:
```diff
- onClick={() => onExplore(node.id, 'upstream')}
+ onClick={() => onExplore(data.uri, 'upstream')}

- onClick={() => onExplore(node.id, 'downstream')}
+ onClick={() => onExplore(data.uri, 'downstream')}
```

`data.uri` is the actual dataset URI like `postgres://clean.orders`, which is what the backend expects.

### Fix B — `lineageApi.js`

#### [MODIFY] [lineageApi.js](file:///c:/Rubiscape/lineage-engine/frontend/src/api/lineageApi.js)

Remove `encodeURIComponent` — the `:path` wildcard in FastAPI handles slashes natively.  
The URI must be sent RAW so the backend can look it up in Neo4j:
```diff
- const res = await API.get(`/lineage/upstream/${encodeURIComponent(datasetUri)}`, { params: { depth } });
+ const res = await API.get(`/lineage/upstream/${datasetUri}`, { params: { depth } });

- const res = await API.get(`/lineage/downstream/${encodeURIComponent(datasetUri)}`, { params: { depth } });
+ const res = await API.get(`/lineage/downstream/${datasetUri}`, { params: { depth } });
```

### Verification
1. Run `python run_live_demo.py`
2. After simulation, click any Dataset node → side panel opens
3. Click "Explore Upstream" → graph should reload with ancestry
4. Click "Explore Downstream" → graph should reload with descendants
5. Should NOT see 404 errors in browser console

---

## 🟧 Stage 6 — Neo4j Constraint Automation
**Scope:** Remove the "apply constraints manually in browser" step.  
**Time estimate:** 45 minutes.

### Problem
Right now, Neo4j constraints are applied by hand in the Neo4j browser at `localhost:7474` during first setup. If a new developer clones the repo and just runs `docker compose up`, the constraints won't exist and duplicate nodes can be created.

### Fix — Auto-Apply Constraints on Startup

#### [MODIFY] [db_client.py](file:///c:/Rubiscape/lineage-engine/app/db_client.py)
Add a `apply_neo4j_constraints()` function that runs on FastAPI startup.

#### [MODIFY] [main.py](file:///c:/Rubiscape/lineage-engine/app/main.py)
Add a `@app.on_event("startup")` handler that calls `apply_neo4j_constraints()`.

**Constraints to auto-apply:**
```cypher
CREATE CONSTRAINT job_name_unique IF NOT EXISTS FOR (j:Job) REQUIRE j.name IS UNIQUE
CREATE CONSTRAINT dataset_uri_unique IF NOT EXISTS FOR (d:Dataset) REQUIRE d.uri IS UNIQUE
CREATE CONSTRAINT run_id_unique IF NOT EXISTS FOR (r:Run) REQUIRE r.run_id IS UNIQUE
CREATE INDEX dataset_tags_index IF NOT EXISTS FOR (d:Dataset) ON (d.tags)
```

### Verification
- Start fresh Docker containers
- Run FastAPI — constraints should appear in Neo4j browser automatically
- No manual step needed

---

## 🟨 Stage 7 — Impact Analysis Endpoint
**Scope:** New GET endpoint: "Which jobs will break if I change this dataset's schema?"  
**Time estimate:** 2–3 hours.

### The Feature
One of the listed "still to build" items from the dev plan. This is the killer feature for schema change management.

**New Endpoint:**
```
GET /lineage/impact/{dataset_uri}
```

**What it returns:**
- All **downstream jobs** that directly consume this dataset
- All **downstream datasets** that depend on it (transitively)
- Impact severity score (how many things break if this changes)

### Files

#### [MODIFY] [router.py](file:///c:/Rubiscape/lineage-engine/app/api/router.py)
Add `get_impact()` endpoint using a Cypher traversal:
```cypher
MATCH path = (start:Dataset {uri: $uri})-[:CONSUMES]->(j:Job)-[:PRODUCES*1..N]->(affected)
RETURN DISTINCT nodes(path), relationships(path)
```

#### [MODIFY] [pydantic_models.py](file:///c:/Rubiscape/lineage-engine/app/api/pydantic_models.py)
Add `ImpactResponse` schema with `affected_jobs`, `affected_datasets`, `impact_score`.

#### [NEW] test_stage7.py
Integration tests: seed a graph, call `/impact/`, verify affected node list.

### Verification
- Run test_stage7.py → all pass
- Open Swagger UI at `/docs`, test the endpoint manually

---

## 🟩 Stage 8 — Multi-Hop Retroactive PII Propagation
**Scope:** Upgrade PII propagation from 1-hop to N-hop, running on demand.  
**Time estimate:** 3–4 hours.

### Current Limitation
`graph_writer._propagate_pii_tags()` only tags **direct outputs** (1-hop). If:
```
raw.users (pii) → load_job → staging.users → transform_job → clean.users
```
`staging.users` gets pii tag. `clean.users` does NOT — it's 2 hops away.

### Fix — Retroactive Graph Propagation

#### [MODIFY] [graph_writer.py](file:///c:/Rubiscape/lineage-engine/app/storage/graph_writer.py)
Add `propagate_pii_retroactive()` function using a Cypher MATCH that traverses any depth:
```cypher
MATCH (pii:Dataset)-[:CONSUMES|PRODUCES*1..20]->(downstream:Dataset)
WHERE 'pii' IN pii.tags AND NOT 'pii' IN downstream.tags
SET downstream.tags = downstream.tags + ['pii']
```

#### [NEW] POST `/lineage/admin/propagate-pii`
A maintenance endpoint to trigger retroactive propagation manually or on schedule.

#### [MODIFY] `test_stage3.py`
Add multi-hop PII test: seed 3-hop chain with PII at source, call propagate, verify all 3 hops tagged.

### Verification
- Seed 3-hop PII chain
- Call `/admin/propagate-pii`
- Verify every node in chain has pii tag

---

## 🟦 Stage 9 — Airflow Integration (Live Test)
**Scope:** Verify the Airflow DAG plugin works end-to-end with the running engine.  
**Time estimate:** 4–6 hours.

### Current State
`airflow_dags/` folder exists but is untested. `docker-compose.yml` has an Airflow service defined but never brought up.

### Plan

#### [MODIFY] [docker-compose.yml](file:///c:/Rubiscape/lineage-engine/docker-compose.yml)
Enable Airflow service (currently commented out or never started).

#### [MODIFY / COMPLETE] `airflow_dags/` folder
Write a real Airflow DAG that:
1. Reads from a dummy source table
2. Writes to a dummy output table
3. Has the OpenLineage Airflow provider installed and configured to POST to `http://localhost:8000/lineage/events`

#### New environment variable
Add `OPENLINEAGE_URL=http://localhost:8000` to `.env`.

### Verification
- Trigger the Airflow DAG manually
- Check Neo4j → new Job, Dataset, Run nodes should appear automatically
- No manual API calls needed

---

## 🟪 Stage 10 — Column-Level Lineage
**Scope:** Upgrade from table-level to column-level tracking.  
**Time estimate:** 1–2 days (complex).

### Current State
All lineage is at the **table** level (`postgres://clean.orders`). No column info tracked.

### Plan
This requires:
1. **OpenLineage facets parsing** — Airflow's OL events have a `columnLineage` facet with field-level info
2. **New `Column` node type** in Neo4j
3. **New edges**: `Column -[:COLUMN_OF]-> Dataset`, `Column -[:TRANSFORMS]-> Column`
4. **Frontend**: expand the node side panel to show column list when clicking a Dataset

> [!IMPORTANT]  
> This is the most complex stage. Do NOT start until Stages Fix-0 through 9 are complete.  
> Recommend a separate planning session for this stage alone.

---

## 🤖 Stage 11 — RAG Answer Generation Module
**Scope:** AI module that answers natural language questions about lineage.  
**Time estimate:** 3–5 days (research phase needed).

### Current State
`docs/Metadata_Lineage_Engine_Final_initial_plan_doc (1).md` mentions "RAG Answer Generation module — Stage E in progress" and references a separate deep dive. This was partially built in a different project context.

### Plan
- Build a LLM-based query interface: user types "Which jobs use customer data?" → system translates to Cypher → returns natural language answer
- This sits **on top of** the existing graph — it does not replace any query endpoints
- New module: `app/rag/` folder

> [!IMPORTANT]  
> Requires separate planning session. Depends on all graph data being correct and queryable first.

---

## Priority Order (Recommended Execution Sequence)

```
Fix-0  → Upstream/Downstream is BROKEN today (30 min, do this FIRST)
Stage 6 → Auto-constraints (makes dev setup clean for new teammates)
Stage 7 → Impact analysis (most useful new feature, builds on existing API)
Stage 8 → Multi-hop PII (correctness improvement, not visible to users)
Stage 9 → Airflow live integration (end-to-end real pipeline test)
Stage 10 → Column-level lineage (requires separate planning)
Stage 11 → RAG module (requires separate planning)
```

---

## Open Questions for Aary

> [!IMPORTANT]
> **Question 1:** After Fix-0 (upstream/downstream fix), do you want to also fix the Search Bar's `encodeURIComponent` for URIs typed manually? Currently, if someone types `postgres://clean.orders` in the search box and hits Enter, the same encoding bug may affect that flow too. The GraphView already calls `fetchGraph(uri, depth, direction)` → `getUpstream(uri)` → `encodeURIComponent`. Should I fix this in the same pass?

> [!IMPORTANT]
> **Question 2:** Stage 9 (Airflow) requires Docker resources. Do you want to enable the Airflow service in docker-compose.yml now? It will use significant RAM. Confirm before I touch the Docker config.

> [!IMPORTANT]
> **Question 3:** For Stage 7 (Impact Analysis), should the `/impact/` endpoint be added to the frontend UI too (a dedicated view), or just expose it as a backend API for now?

---

## Verification Plan

### Fix-0 (Upstream/Downstream)
1. `python run_live_demo.py` — let simulator finish
2. Search for `duckdb://jaffle_shop/customers` in the UI
3. Click Upstream → should show full ancestry graph
4. Click any Dataset node → side panel → "Explore Upstream" → graph should reload (NOT 404)
5. Browser console (F12) → no 404 errors

### Stage 6 (Constraints)
1. `docker compose down -v` (wipe volumes)
2. `docker compose up -d`
3. Run FastAPI → check Neo4j browser at `localhost:7474`
4. Run `SHOW CONSTRAINTS` in Neo4j browser → 3 constraints should exist automatically

### Stage 7 (Impact Analysis)
1. `python scripts/test_stage7.py` → all tests pass
2. Swagger UI → test `/lineage/impact/postgres://raw.orders` → returns affected jobs list

---

*Plan created: 2026-04-23*  
*Author: Antigravity (AI Agent)*

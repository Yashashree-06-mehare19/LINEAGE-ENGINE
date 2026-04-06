# Stage 3 — Storage Layer: How It Works

## 1. What Was the Problem

At the end of Stage 2, the system could **receive** lineage events (via HTTP, SQL parser, dbt parser) and convert them to `LineageEvent` objects. But `write_event()` was a **stub** — it did nothing except print to logs. Data went nowhere.

The problem Stage 3 solves:
> "How do we take a `LineageEvent` and turn it into actual nodes, edges, and records in two different databases?"

---

## 2. The Solution

Replace the stub `write_event()` with a real function that:

1. Opens a **Neo4j transaction** → writes all graph nodes and edges atomically
2. Inserts a row into **PostgreSQL** `run_log` → independent audit trail
3. Runs **PII tag propagation** → if an input was tagged PII, outputs inherit that tag

All of this happens inside a single `write_event()` call. Stage 2 doesn't need to change a single line.

---

## 3. The Full Data Flow (what happens when `write_event()` is called)

```
write_event(event: LineageEvent)
    │
    ├── 1. Neo4j Transaction (atomic — all or nothing)
    │       ├── MERGE Job node
    │       ├── for each input:
    │       │     ├── MERGE Dataset node
    │       │     └── MERGE Dataset -[:CONSUMES]-> Job edge
    │       ├── for each output:
    │       │     ├── MERGE Dataset node
    │       │     └── MERGE Job -[:PRODUCES]-> Dataset edge
    │       ├── MERGE Run node
    │       └── MERGE Job -[:HAS_RUN]-> Run edge
    │
    ├── 2. PostgreSQL INSERT into run_log
    │       └── ON CONFLICT DO NOTHING (safe for retries)
    │
    └── 3. PII tag propagation
            └── if any input.tags has 'pii' or 'sensitive':
                    SET output.tags = output.tags + ['pii']
```

---

## 4. How We Tackled It — File by File

### The One File: `app/storage/graph_writer.py`

This entire stage lives in one file. It replaces the stub completely.

---

### Concept A: Neo4j Transactions with `MERGE`

**Problem:** If Airflow runs the same DAG twice, we'd get duplicate `Job` nodes in the graph. We need writes to be **idempotent** — running them 10 times produces the same result as running them once.

**Solution:** Use `MERGE` instead of `CREATE` in Cypher:
```cypher
MERGE (j:Job {name: $name})
ON CREATE SET j.owner = $owner, j.orchestrator = $orchestrator
ON MATCH SET  j.owner = $owner, j.orchestrator = $orchestrator
```

- `MERGE`: "Find this node if it exists. If not, create it."
- `ON CREATE SET`: Properties set the first time only
- `ON MATCH SET`: Properties updated every time

The same pattern applies to `Dataset`, `Run`, and all edges. **Every single write is idempotent.**

---

### Concept B: Single Transaction via `execute_write()`

**Problem:** If the job node writes, but then the edge write crashes halfway through — we'd have orphaned nodes in the graph (a job with no edges).

**Solution:** Wrap all Neo4j writes in **one transaction**:
```python
with driver.session() as session:
    session.execute_write(_write_graph, event)
```

`execute_write()` passes a transaction object `tx` to our `_write_graph()` function. Every `tx.run()` inside `_write_graph()` is part of the **same transaction**. If anything fails, the whole thing rolls back — no partial writes.

---

### Concept C: Graph Schema — Direction Matters

The Neo4j graph has two types of edges:

```
(:Dataset {uri: "postgres://raw.orders"})
    -[:CONSUMES {timestamp}]->
(:Job {name: "transform_step"})
    -[:PRODUCES {timestamp}]->
(:Dataset {uri: "postgres://clean.orders"})
```

**Why this direction?**
- `CONSUMES`: "This dataset was consumed (read) by this job"
- `PRODUCES`: "This job produced (wrote) this dataset"

To trace **upstream** of `clean.orders`:
→ Walk backwards through PRODUCES edges
→ Find the job that produced it
→ Walk backwards through CONSUMES edges
→ Find what that job consumed

This is the traversal Stage 4 uses for `GET /lineage/upstream/{dataset_id}`.

---

### Concept D: PostgreSQL as Independent Audit Log

**Problem:** Neo4j is great for graph traversal, but getting "all historical runs of a job sorted by time" is much easier in a relational database.

**Solution:** Write a row to `run_log` after every successful Neo4j write:
```python
INSERT INTO run_log (run_id, job_name, status, start_time, end_time, input_datasets, output_datasets)
VALUES (%s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (run_id) DO NOTHING
```

**Critical design decision:** If the Postgres write fails, we **log the error but do NOT raise it**:
```python
except Exception as e:
    logger.error(f"Postgres write failed: {e}")
    # Do NOT re-raise
```

Why? Because Neo4j is the **source of truth** for lineage. A Postgres failure should not make Airflow think the lineage event was rejected. The graph is what matters.

---

### Concept E: PII Tag Propagation

**Problem:** If a job reads from a PII-tagged dataset and writes to a new one, the new dataset should automatically be marked as PII. Otherwise, downstream consumers might not know sensitive data is flowing through.

**Solution:** After writing to Neo4j, we check if any input had a PII tag:
```python
pii_tags = {"pii", "sensitive"}
input_has_pii = any(
    bool(pii_tags.intersection(set(d.tags)))
    for d in event.inputs
)
```

If yes, we update the output datasets in Neo4j:
```cypher
MATCH (d:Dataset {uri: $uri})
WHERE NOT 'pii' IN d.tags
SET d.tags = d.tags + ['pii']
```

**Scope:** This is **1-hop only** — direct outputs of the current event. If `raw_customers (pii)` → `staging_customers` → `clean_customers`, then:
- At first job write: `staging_customers` gets tagged pii ✅
- At second job write: `clean_customers` gets tagged pii ✅ (because now staging_customers has pii)

Multi-hop **retroactive** propagation (tagging existing historical datasets) is Phase 2.

---

## 5. The Test Results (what we verified)

All 34 tests passed — here's what each one validated:

| Test | What It Proved |
|---|---|
| **1** Job node created | Neo4j MERGE creates Job with correct properties |
| **2** Dataset nodes | Namespace, name, URI all stored correctly |
| **3** PRODUCES + CONSUMES edges | Correct direction, correct nodes connected |
| **4** Run node + HAS_RUN | Run captured with status, job linked |
| **5** PostgreSQL run_log | All 5 fields written correctly |
| **6** Idempotency | Write same event twice → 0 duplicates anywhere |
| **7** PII propagation | pii input → output tagged; clean input → no tag |
| **8** Full end-to-end | Airflow → HTTP → Neo4j + Postgres — all connected |

---

## 6. Key Patterns Used

| Pattern | Where Used | Why |
|---|---|---|
| **MERGE** (Cypher) | All Neo4j writes | Idempotency — safe to retry |
| **Single transaction** | `execute_write()` | Atomicity — no partial graph writes |
| **Swallow exception** | `_write_postgres()` | Postgres failure ≠ lineage failure |
| **Post-write hook** | `_propagate_pii_tags()` | PII tag logic runs after graph is committed |
| **Set intersection** | PII check | Pythonic way to check if any tag matches |

---

## 7. The Stub Pattern (Why Stage 2 Tests Still Pass)

The original stub:
```python
def write_event(event: LineageEvent) -> None:
    logger.info(f"[STUB] job={event.job.name}")
```

The real replacement has the **exact same signature**:
```python
def write_event(event: LineageEvent) -> None:
    # real Neo4j + Postgres writes
```

Stage 2's router imports `write_event` and calls it:
```python
from app.storage.graph_writer import write_event
write_event(lineage_event)
```

Stage 2 **never needed to change**. This is the power of programming to an interface — Stage 2 depends on a function contract, not an implementation. Swap the implementation file, and everything just works.

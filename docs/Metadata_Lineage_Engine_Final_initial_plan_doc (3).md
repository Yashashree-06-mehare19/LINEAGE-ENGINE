# Developer Q&A: Project Understanding
*This document contains the core "Whys," "Hows," and "Wheres" covering the reasoning behind the architectural choices of the Lineage Engine. It serves as your personal cheat sheet for defending technical decisions.*

---

## 1. WHY did we choose a Graph Database (Neo4j) instead of just using SQL?
**The Reason:** Data Lineage is inherently a graph. 
If dataset A feeds dataset B, which feeds dataset C, tracking this in a SQL database requires recursive CTEs (Common Table Expressions). Recursive SQL queries are notoriously slow and incredibly complex to maintain as your pipeline grows to thousands of nodes. Neo4j is built natively to track deep, variable-length relationship paths. In Neo4j, traversing from node A through 50 layers to node Z takes milliseconds. 
**Summary:** We chose Neo4j because it is optimized for "ancestry" and "impact" queries.

## 2. WHY do we use both PostgreSQL AND Neo4j?
**The Reason:** Separation of concerns. 
Neo4j is great at mapping relationships (Topology), but it is a poor choice for storing thousands of rows of historical audit logs. If an Airflow job runs 5,000 times a year, inserting 5,000 nodes into the Graph will clutter the visual data flow. We use PostgreSQL to strictly log the *history* (what time did it run, did it fail?), ensuring the Neo4j graph remains clean, fast, and only tracks the physical shape of the data.

## 3. WHY did we use FastAPI over Django/Flask?
**The Reason:** Performance and Developer Experience.
Lineage events happen constantly behind the scenes in large systems. FastAPI is extremely fast (built on ASGI). Furthermore, FastAPI relies heavily on `Pydantic` for instant Data Validation, and automatically creates the Swagger Documentation (`/docs`), meaning we did not have to write separate API docs for the users interacting with our API.

## 4. WHAT is the "Converter Pattern" and WHY do we use it?
**Where is it?** `app/ingestion/converter.py`
**The Reason:** We ingest data formatted to the "OpenLineage" JSON industry standard. However, if OpenLineage changes their standard next year, we do not want to rewrite our entire backend. 
The Converter acts as a translator. It takes OpenLineage language and turns it into our own internal dataclass (`LineageEvent` in `models.py`). This means the core engine, the databases, and the retrievers never actually see "OpenLineage" syntax—they only see our custom standard.

## 5. WHY do we use `MERGE` instead of `CREATE` in the Neo4j database?
**The Reason:** Idempotency (Safety against duplicate data). 
If an orchestrator creates a network hiccup and sends us the exact same dataset record twice, using `CREATE` would result in two identical clusters in the graph, corrupting the layout. Neo4j’s `MERGE` operation acts like an "Insert or Ignore" / "Upsert". It guarantees that a Dataset like `postgres://clean.orders` exists precisely *once* in the database, no matter how many times a system tells us it was created.

## 6. HOW does the system map out Lineage? (The Logic)
**The Reason:** The engine relies on tracking three specific Node Types and three Edge Types:
* **Node Types:** `Job` (the script), `Dataset` (the table), and `Run` (the execution instance).
* **Edge Types:**
  1. `CONSUMES` (A Dataset points to a Job)
  2. `PRODUCES` (A Job points to a Dataset)
  3. `HAS_RUN` (A Job points to a Run)
Whenever we ask "Where did this dataset come from?", we just traverse backwards up the `PRODUCES` and `CONSUMES` chains.

## 7. WHY write static SQL and dbt parsers instead of just relying on Airflow?
**The Reason:** Not all code runs in an advanced orchestrator. Many businesses have data pipelines consisting of random SQL scripts running on chron jobs or legacy systems. By hooking in `SQLGlot` and a custom dbt manifest parser, we allow the engine to map out legacy flows just by analyzing the `.sql` code itself, extracting the `SELECT FROM` (Consumers) and `INSERT INTO` (Producers) relationships dynamically.

## 8. WHY did we design the Frontend with React / ReactFlow?
**The Reason:** Rendering graphs is complex math. `ReactFlow` provides a highly optimized, interactive, drag-and-drop canvas out of the box, capable of rendering node networks easily. We combined this with a glassmorphism design (TailwindCSS) to ensure an ultra-modern aesthetic, because lineage graphs can quickly become visually overwhelming if not cleanly designed.

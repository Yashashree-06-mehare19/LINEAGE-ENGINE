# Learn by Building: End-to-End Pipeline Testing

Hello Aary! As we just ran all the integration tests for your Metadata Lineage Engine, here is a breakdown of the testing concepts we used.

## 1. What was the problem?
When building an engine with multiple components—a REST API (running on FastAPI), a graph database (Neo4j), and a relational log (PostgreSQL)—we face a critical question: **Does everything actually work together when we send real data?** 

Testing individual functions (unit testing) isn't enough because the most complex bugs happen at the boundaries where different systems interact (e.g., when the Pydantic models try to write to Neo4j). We needed a way to prove that the entire system end-to-end automatically translates a JSON lineage push into a queryable graph.

## 2. The Solution
We use **End-to-End (E2E) and Integration Testing**. The solution is to programmatically recreate real-world scenarios:
- Spin up all the actual services involved (FastAPI, Neo4j, Postgres).
- Wipe the databases so we always start with a clean slate.
- Send a series of realistic HTTP POST requests (simulating Apache Airflow or dbt).
- Directly query the databases and the GET REST endpoints to assert that the exact nodes, edges, and logs were created correctly.

## 3. How we tackled it & What we used
### Approach & Logic
We broke the testing into 3 focused stages representing the lifecycle of our data:
1. **Ingestion Testing (`test_stage2.py`)**: Tests the `POST /lineage/events` boundary. This exclusively ensures that badly formatted JSON is rejected (HTTP 422) and valid JSON is properly coerced into our internal Python DataClasses.
2. **Storage Testing (`test_stage3.py`)**: Tests the Cypher/SQL merging logic. It verifies that running the same event twice results in the same number of nodes (idempotency) and correctly propagates metadata parameters like "PII" tags through the Graph edges.
3. **API Integrity Testing (`test_stage4.py`)**: Tests the retrieval of graph data. It simulates a huge multi-hop pipeline (e.g., `raw -> staging -> clean -> reporting`), wipes the DB, seeds it, and then validates if the mathematical logic behind `GET /upstream/` actually matches the realistic dataset map.

### Technologies Stack
* **Python's `pytest` & standalone scripts**: Using standard Python to orchestrate the HTTP calls and checks.
* **`httpx` package**: An HTTP client (similar to `requests` but async-capable) to send the `.post()` and `.get()` HTTP requests against our localhost FastAPI app.
* **Neo4j / PostgreSQL Drivers**: Standard raw connect clients (`psycopg2` and `neo4j`) were used to directly dive into the databases and bypass our actual app in order to verify that the app legitimately created the underlying `run_log` entries and node metadata properties.
* **Docker / Docker Compose**: Allowed us to run identical versions of Neo4j/PostgreSQL locally, ensuring our tests run in a production-mirroring environment.

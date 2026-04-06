Stage 1 — Complete Summary

What Stage 1 is
The foundation every other stage builds on. No features, no endpoints (except health check) — just databases running, schemas defined, and shared Python code that everyone imports.

What we built
1. Folder structure
lineage-engine/
├── app/
│   ├── __init__.py
│   ├── main.py          ← FastAPI app + /health endpoint
│   ├── models.py        ← LineageEvent dataclass (internal data format)
│   ├── db_client.py     ← Neo4j + Postgres connection wrappers
│   ├── api/
│   ├── ingestion/
│   └── storage/
├── infra/
│   ├── neo4j_init.cypher    ← constraints + indexes (ran manually)
│   └── postgres_init.sql    ← run_log table (auto-ran on container start)
├── parsers/
├── tests/
├── scripts/
├── airflow_dags/
├── .env                 ← credentials and config
├── docker-compose.yml   ← runs Neo4j + PostgreSQL in Docker
├── Dockerfile           ← for containerising the API later
└── requirements.txt     ← all Python packages

Credentials — save these
ServiceUsernamePasswordWhere usedNeo4jneo4jlineage_password.env, Neo4j browser loginPostgreSQLlineage_userlineage_password.env connection stringPostgreSQL DB name——lineage_db

Connection strings (in .env)
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=lineage_password
POSTGRES_DSN=postgresql://lineage_user:lineage_password@localhost:5432/lineage_db

URLs — bookmark these
WhatURLFastAPI apphttp://localhost:8000Health checkhttp://localhost:8000/healthSwagger API docs (auto-generated)http://localhost:8000/docsNeo4j browserhttp://localhost:7474PostgreSQLaccessible on port 5432

Docker — commands used
powershell# Start both databases in background
docker compose up -d

# Check container status
docker compose ps

# Stop containers (when done for the day)
docker compose down

# Stop and wipe all data (nuclear option)
docker compose down -v
What Docker runs:
ContainerImagePortslineage-engine-neo4j-1neo4j:5.15.07474 (browser), 7687 (bolt)lineage-engine-postgres-1postgres:15.65432

Python — commands used
powershell# Install all dependencies
pip install -r requirements.txt --prefer-binary

# Start the FastAPI server (run this every session)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
Packages installed:
fastapi==0.115.0      ← web framework
uvicorn==0.29.0       ← runs FastAPI
pydantic>=2.9.0       ← data validation
neo4j==5.19.0         ← Neo4j Python driver
psycopg2==2.9.11      ← PostgreSQL Python driver
sqlglot==23.12.2      ← SQL parser (Stage 2)
pytest==8.2.0         ← testing (Stage 4)
testcontainers==4.4.0 ← integration tests (Stage 4)
httpx==0.27.0         ← test HTTP client (Stage 4)
python-dotenv==1.0.1  ← reads .env file

Neo4j schema — applied manually in browser
3 constraints (enforce uniqueness, prevent duplicates):
cypherCREATE CONSTRAINT job_name_unique IF NOT EXISTS
  FOR (j:Job) REQUIRE j.name IS UNIQUE;

CREATE CONSTRAINT dataset_uri_unique IF NOT EXISTS
  FOR (d:Dataset) REQUIRE d.uri IS UNIQUE;

CREATE CONSTRAINT run_id_unique IF NOT EXISTS
  FOR (r:Run) REQUIRE r.run_id IS UNIQUE;
1 index (makes PII tag queries fast):
cypherCREATE INDEX dataset_tags_index IF NOT EXISTS
  FOR (d:Dataset) ON (d.tags);
Verify with:
cypherSHOW CONSTRAINTS;
Result: 3 rows — dataset_uri_unique, job_name_unique, run_id_unique ✅

PostgreSQL schema — auto-applied on container start
Table created automatically when Docker started (via volume mount of postgres_init.sql):
sqlCREATE TABLE run_log (
    run_id          TEXT PRIMARY KEY,
    job_name        TEXT NOT NULL,
    status          TEXT NOT NULL,
    start_time      TIMESTAMPTZ,
    end_time        TIMESTAMPTZ,
    input_datasets  TEXT[],
    output_datasets TEXT[],
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

Key decisions made

FastAPI runs locally (not in Docker) on Windows — easier for development, hot reload works
Only databases run in Docker — Neo4j and PostgreSQL
Python 3.13 used (not 3.11 as planned) — works fine, just needed --prefer-binary for packages
psycopg2 not psycopg2-binary — binary version wouldn't compile on Windows, plain version worked


How to restart everything next session
powershell# Terminal 1 — start databases
cd C:\Rubiscape\lineage-engine
docker compose up -d

# Terminal 2 — start FastAPI
cd C:\Rubiscape\lineage-engine
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
Then verify: http://localhost:8000/health shows healthy.

Stage 1 checklist — all green ✅
✅ Docker Compose running (Neo4j + PostgreSQL both healthy)
✅ PostgreSQL run_log table created automatically
✅ Neo4j constraints applied (3 constraints, 1 index)
✅ shared models.py — LineageEvent, JobRef, RunRef, DatasetRef
✅ shared db_client.py — get_neo4j_driver(), get_postgres_conn()
✅ FastAPI running on port 8000
✅ GET /health returns {"status":"healthy","neo4j":"ok","postgres":"ok"}

Ready for Stage 2 — say go and we start building POST /lineage/events.go3:43 PMStage 2 — Ingestion Layer
We're building the front door of the pipeline. By the end of this stage, the system will accept lineage events from 3 sources, validate them, and hand them to Stage 3.
Stage 2 builds:
├── app/ingestion/pydantic_models.py  ← validates incoming JSON
├── app/ingestion/converter.py        ← converts OL format → LineageEvent
├── app/ingestion/router.py           ← POST /lineage/events endpoint
├── parsers/sql_parser.py             ← SQLGlot SQL file parser
└── parsers/dbt_parser.py             ← dbt manifest.json parser
We also need a stub for Stage 3's write_event() so Stage 2 can run independently right now.

Step 1 — Create the Stage 3 stub first
Create app/storage/graph_writer.py:
pythonfrom app.models import LineageEvent
import logging

logger = logging.getLogger(__name__)


def write_event(event: LineageEvent) -> None:
    """
    STUB — Stage 3 will replace this with real Neo4j + Postgres writes.
    For now just logs the event so Stage 2 can be tested independently.
    """
    logger.info(f"[STUB] write_event called")
    logger.info(f"[STUB] job={event.job.name} run={event.run.run_id}")
    logger.info(f"[STUB] inputs={[d.uri for d in event.inputs]}")
    logger.info(f"[STUB] outputs={[d.uri for d in event.outputs]}")

Step 2 — Create app/ingestion/pydantic_models.py
pythonfrom pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import datetime


class OLDataset(BaseModel):
    namespace: str
    name: str
    facets: dict[str, Any] = Field(default_factory=dict)


class OLRunFacets(BaseModel):
    nominalTime: Optional[dict[str, Any]] = None
    model_config = {"extra": "allow"}


class OLRun(BaseModel):
    runId: str
    facets: OLRunFacets = Field(default_factory=OLRunFacets)


class OLJobFacets(BaseModel):
    ownership: Optional[dict[str, Any]] = None
    model_config = {"extra": "allow"}


class OLJob(BaseModel):
    namespace: str
    name: str
    facets: OLJobFacets = Field(default_factory=OLJobFacets)


class OLRunEvent(BaseModel):
    """
    Validates the OpenLineage JSON that Airflow POSTs to /lineage/events.
    eventType must be COMPLETE or FAIL to be processed.
    """
    eventType: str
    eventTime: datetime
    run: OLRun
    job: OLJob
    inputs: list[OLDataset] = Field(default_factory=list)
    outputs: list[OLDataset] = Field(default_factory=list)
    producer: str = ""
    schemaURL: str = ""
    model_config = {"extra": "allow"}

Step 3 — Create app/ingestion/converter.py
pythonfrom app.ingestion.pydantic_models import OLRunEvent, OLDataset
from app.models import LineageEvent, JobRef, RunRef, DatasetRef
from datetime import datetime, timezone


def ol_dataset_to_ref(ds: OLDataset) -> DatasetRef:
    return DatasetRef(
        namespace=ds.namespace,
        name=ds.name,
        uri=f"{ds.namespace}://{ds.name}",
        tags=[],
    )


def ol_event_to_lineage_event(event: OLRunEvent) -> LineageEvent:
    """
    Converts a validated OpenLineage event into our internal LineageEvent.
    This is the only place that knows about OpenLineage field names.
    """
    owner = ""
    if event.job.facets.ownership:
        owners = event.job.facets.ownership.get("owners", [])
        if owners:
            owner = owners[0].get("name", "")

    start_time = None
    end_time = None
    if event.run.facets.nominalTime:
        nt = event.run.facets.nominalTime
        if nt.get("nominalStartTime"):
            start_time = datetime.fromisoformat(
                nt["nominalStartTime"].replace("Z", "+00:00")
            )
        if nt.get("nominalEndTime"):
            end_time = datetime.fromisoformat(
                nt["nominalEndTime"].replace("Z", "+00:00")
            )

    return LineageEvent(
        job=JobRef(
            name=event.job.name,
            owner=owner,
            orchestrator="airflow",
        ),
        run=RunRef(
            run_id=event.run.runId,
            status=event.eventType,
            start_time=start_time or event.eventTime,
            end_time=end_time,
        ),
        inputs=[ol_dataset_to_ref(ds) for ds in event.inputs],
        outputs=[ol_dataset_to_ref(ds) for ds in event.outputs],
        event_time=event.eventTime,
    )

Step 4 — Create app/ingestion/router.py
pythonfrom fastapi import APIRouter, HTTPException
from app.ingestion.pydantic_models import OLRunEvent
from app.ingestion.converter import ol_event_to_lineage_event
from app.storage.graph_writer import write_event
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/lineage", tags=["ingestion"])


@router.post("/events", status_code=200)
def ingest_event(event: OLRunEvent):
    """
    Receives an OpenLineage event from Airflow or any OL-compatible source.
    Skips START events — only processes COMPLETE and FAIL.
    """
    logger.info(
        f"Received event: job={event.job.name} "
        f"run={event.run.runId} type={event.eventType}"
    )

    if event.eventType not in ("COMPLETE", "FAIL"):
        return {
            "status": "skipped",
            "reason": f"eventType {event.eventType} not processed"
        }

    try:
        lineage_event = ol_event_to_lineage_event(event)
        write_event(lineage_event)
        return {
            "status": "ok",
            "job": event.job.name,
            "run_id": event.run.runId
        }
    except Exception as e:
        logger.error(f"Failed to write event: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Storage write failed: {str(e)}"
        )

Step 5 — Mount the router in app/main.py
Update app/main.py — replace the entire file with this:
pythonimport os
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from app.ingestion.router import router as ingestion_router

app = FastAPI(
    title="Metadata Lineage Engine",
    description="Captures and exposes data lineage across pipelines.",
    version="1.0.0",
)

app.include_router(ingestion_router)


@app.get("/health", tags=["system"])
def health_check():
    status = {"neo4j": "unknown", "postgres": "unknown"}

    try:
        from app.db_client import get_neo4j_driver
        driver = get_neo4j_driver()
        with driver.session() as session:
            session.run("RETURN 1")
        status["neo4j"] = "ok"
    except Exception as e:
        status["neo4j"] = f"error: {str(e)}"

    try:
        from app.db_client import get_postgres_conn
        conn = get_postgres_conn()
        conn.close()
        status["postgres"] = "ok"
    except Exception as e:
        status["postgres"] = f"error: {str(e)}"

    all_ok = all(v == "ok" for v in status.values())
    return {
        "status": "healthy" if all_ok else "degraded",
        "services": status
    }

Step 6 — Create parsers/sql_parser.py
pythonimport sqlglot
import sqlglot.expressions as exp
from app.models import LineageEvent, JobRef, RunRef, DatasetRef
from datetime import datetime, timezone
import uuid
import os


def _normalise_table_name(table_expr) -> str:
    parts = []
    if hasattr(table_expr, 'db') and table_expr.db:
        parts.append(table_expr.db.lower())
    parts.append(table_expr.name.lower())
    return ".".join(p for p in parts if p)


def parse_sql(sql: str, dialect: str = "postgres",
              job_name: str = "sql_script") -> LineageEvent:
    """
    Parses a SQL string and returns a LineageEvent.
    Extracts source tables (FROM, JOIN) and target tables (INSERT INTO, CREATE TABLE AS).
    CTEs are excluded — they are not real tables.
    """
    try:
        statements = sqlglot.parse(sql, dialect=dialect)
    except Exception as e:
        raise ValueError(f"SQLGlot could not parse SQL: {e}")

    source_tables: set[str] = set()
    target_tables: set[str] = set()
    cte_names: set[str] = set()

    for statement in statements:
        if statement is None:
            continue

        for cte in statement.find_all(exp.CTE):
            if cte.alias:
                cte_names.add(cte.alias.lower())

        for insert in statement.find_all(exp.Insert):
            if insert.this and isinstance(insert.this, exp.Table):
                target_tables.add(_normalise_table_name(insert.this))

        for create in statement.find_all(exp.Create):
            if create.this and isinstance(create.this, exp.Table):
                target_tables.add(_normalise_table_name(create.this))

        for table in statement.find_all(exp.Table):
            name = _normalise_table_name(table)
            if name and name not in cte_names and name not in target_tables:
                source_tables.add(name)

    source_tables -= target_tables
    ns = "sql_parser"

    return LineageEvent(
        job=JobRef(name=job_name, owner="", orchestrator="sql_script"),
        run=RunRef(
            run_id=str(uuid.uuid4()),
            status="COMPLETE",
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc),
        ),
        inputs=[
            DatasetRef(namespace=ns, name=t, uri=f"{ns}://{t}")
            for t in sorted(source_tables)
        ],
        outputs=[
            DatasetRef(namespace=ns, name=t, uri=f"{ns}://{t}")
            for t in sorted(target_tables)
        ],
        event_time=datetime.now(timezone.utc),
    )


def parse_sql_file(filepath: str, dialect: str = "postgres") -> LineageEvent:
    with open(filepath, "r") as f:
        sql = f.read()
    job_name = os.path.basename(filepath).replace(".sql", "")
    return parse_sql(sql, dialect=dialect, job_name=job_name)

Step 7 — Create parsers/dbt_parser.py
pythonimport json
from app.models import LineageEvent, JobRef, RunRef, DatasetRef
from datetime import datetime, timezone
import uuid


def parse_manifest(manifest_path: str) -> list[LineageEvent]:
    """
    Parses a dbt manifest.json and returns one LineageEvent
    per model dependency relationship.
    """
    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    nodes = manifest.get("nodes", {})
    events = []

    for node_id, node in nodes.items():
        if node.get("resource_type") != "model":
            continue

        model_name = node.get("name", node_id)
        schema = node.get("schema", "dbt")
        depends_on_nodes = node.get("depends_on", {}).get("nodes", [])

        if not depends_on_nodes:
            continue

        for dep_node_id in depends_on_nodes:
            dep_name = dep_node_id.split(".")[-1]

            event = LineageEvent(
                job=JobRef(
                    name=f"dbt.{model_name}",
                    owner="",
                    orchestrator="dbt",
                ),
                run=RunRef(
                    run_id=str(uuid.uuid4()),
                    status="COMPLETE",
                    start_time=datetime.now(timezone.utc),
                    end_time=datetime.now(timezone.utc),
                ),
                inputs=[DatasetRef(
                    namespace="dbt",
                    name=dep_name,
                    uri=f"dbt://{dep_name}",
                )],
                outputs=[DatasetRef(
                    namespace="dbt",
                    name=f"{schema}.{model_name}",
                    uri=f"dbt://{schema}.{model_name}",
                )],
                event_time=datetime.now(timezone.utc),
            )
            events.append(event)

    return events

Once all 7 files are created, your uvicorn server should auto-reload. Check the terminal where uvicorn is running — it should show no errors.
Then confirm with:
powershellcurl http://localhost:8000/docs
Or open http://localhost:8000/docs in browser — you should see the Swagger UI with POST /lineage/events listed.
Create all files and paste what you see in the uvicorn terminal + the /docs page.
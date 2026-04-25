# app/storage/graph_writer.py
from app.models import LineageEvent, DatasetRef, JobRef, RunRef
from app.db_client import get_neo4j_driver, get_postgres_conn
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────
# PUBLIC INTERFACE — P2 calls this, P3 (this file) implements it
# ─────────────────────────────────────────────────────────

def write_event(event: LineageEvent) -> None:
    """
    Writes a complete lineage event to Neo4j and PostgreSQL.

    Order of operations:
      1. All Neo4j writes in one transaction (atomic)
      2. PostgreSQL insert (independent audit log)
      3. PII tag propagation (post-write hook)

    Args:
        event: A validated LineageEvent from the ingestion layer.

    Raises:
        Exception: If Neo4j write fails.
        PostgreSQL failure is logged but NOT raised — graph is source of truth.
    """
    driver = get_neo4j_driver()

    with driver.session() as session:
        session.execute_write(_write_graph, event)

    _write_postgres(event)
    _propagate_pii_tags(event)

    logger.info(
        f"write_event complete: job={event.job.name} "
        f"run={event.run.run_id} "
        f"inputs={len(event.inputs)} outputs={len(event.outputs)}"
    )


# ─────────────────────────────────────────────────────────
# NEO4J WRITES — all inside one transaction
# ─────────────────────────────────────────────────────────

def _write_graph(tx, event: LineageEvent) -> None:
    """All Neo4j writes in a single transaction. Uses MERGE — safe to call multiple times."""
    _upsert_job(tx, event.job)

    for dataset in event.inputs:
        _upsert_dataset(tx, dataset)
        _create_consumes_edge(tx, dataset, event.job, event.event_time)

    for dataset in event.outputs:
        _upsert_dataset(tx, dataset)
        _create_produces_edge(tx, event.job, dataset, event.event_time)

    _create_run(tx, event.run)
    _create_has_run_edge(tx, event.job, event.run)


def _upsert_job(tx, job: JobRef) -> None:
    """MERGE job by name — update owner/orchestrator on re-run."""
    tx.run(
        """
        MERGE (j:Job {name: $name})
        ON CREATE SET
            j.owner        = $owner,
            j.orchestrator = $orchestrator,
            j.created_at   = $now
        ON MATCH SET
            j.owner        = $owner,
            j.orchestrator = $orchestrator
        """,
        name=job.name,
        owner=job.owner,
        orchestrator=job.orchestrator,
        now=datetime.now(timezone.utc).isoformat(),
    )


def _upsert_dataset(tx, dataset: DatasetRef) -> None:
    """MERGE dataset by uri — only sets properties on first creation."""
    tx.run(
        """
        MERGE (d:Dataset {uri: $uri})
        ON CREATE SET
            d.namespace  = $namespace,
            d.name       = $name,
            d.tags       = $tags,
            d.created_at = $now
        """,
        uri=dataset.uri,
        namespace=dataset.namespace,
        name=dataset.name,
        tags=dataset.tags,
        now=datetime.now(timezone.utc).isoformat(),
    )


def _create_produces_edge(tx, job: JobRef, dataset: DatasetRef, ts) -> None:
    """Job -[:PRODUCES]-> Dataset"""
    tx.run(
        """
        MATCH (j:Job {name: $job_name})
        MATCH (d:Dataset {uri: $dataset_uri})
        MERGE (j)-[r:PRODUCES]->(d)
        ON CREATE SET r.timestamp = $timestamp
        """,
        job_name=job.name,
        dataset_uri=dataset.uri,
        timestamp=ts.isoformat() if ts else datetime.now(timezone.utc).isoformat(),
    )


def _create_consumes_edge(tx, dataset: DatasetRef, job: JobRef, ts) -> None:
    """Dataset -[:CONSUMES]-> Job"""
    tx.run(
        """
        MATCH (d:Dataset {uri: $dataset_uri})
        MATCH (j:Job {name: $job_name})
        MERGE (d)-[r:CONSUMES]->(j)
        ON CREATE SET r.timestamp = $timestamp
        """,
        dataset_uri=dataset.uri,
        job_name=job.name,
        timestamp=ts.isoformat() if ts else datetime.now(timezone.utc).isoformat(),
    )


def _create_run(tx, run: RunRef) -> None:
    """MERGE run by run_id — create only, never overwrite existing run."""
    tx.run(
        """
        MERGE (r:Run {run_id: $run_id})
        ON CREATE SET
            r.status     = $status,
            r.start_time = $start_time,
            r.end_time   = $end_time
        """,
        run_id=run.run_id,
        status=run.status,
        start_time=run.start_time.isoformat() if run.start_time else None,
        end_time=run.end_time.isoformat() if run.end_time else None,
    )


def _create_has_run_edge(tx, job: JobRef, run: RunRef) -> None:
    """Job -[:HAS_RUN]-> Run"""
    tx.run(
        """
        MATCH (j:Job {name: $job_name})
        MATCH (r:Run {run_id: $run_id})
        MERGE (j)-[:HAS_RUN]->(r)
        """,
        job_name=job.name,
        run_id=run.run_id,
    )


# ─────────────────────────────────────────────────────────
# POSTGRESQL WRITE — independent audit log
# ─────────────────────────────────────────────────────────

def _write_postgres(event: LineageEvent) -> None:
    """
    Inserts a run record into run_log for audit trail.
    ON CONFLICT DO NOTHING — safe to call with same run_id twice.
    Failure is caught, logged, and NOT re-raised (graph is source of truth).
    """
    try:
        conn = get_postgres_conn()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO run_log
                        (run_id, job_name, status, start_time, end_time,
                         input_datasets, output_datasets)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (run_id) DO NOTHING
                    """,
                    (
                        event.run.run_id,
                        event.job.name,
                        event.run.status,
                        event.run.start_time,
                        event.run.end_time,
                        [d.uri for d in event.inputs],
                        [d.uri for d in event.outputs],
                    ),
                )
        conn.close()
        logger.info(f"Postgres run_log written: run_id={event.run.run_id}")
    except Exception as e:
        logger.error(f"Postgres write failed for run {event.run.run_id}: {e}")
        # Do NOT re-raise — graph is source of truth


# ─────────────────────────────────────────────────────────
# PII TAG PROPAGATION — post-write hook
# ─────────────────────────────────────────────────────────

def _propagate_pii_tags(event: LineageEvent) -> None:
    """
    1-hop PII propagation:
    If ANY input dataset has a 'pii' or 'sensitive' tag,
    ALL output datasets in this event inherit the 'pii' tag.

    This is write-time only. Multi-hop retroactive propagation is Phase 2 scope.
    """
    pii_tags = {"pii", "sensitive"}
    input_has_pii = any(
        bool(pii_tags.intersection(set(d.tags)))
        for d in event.inputs
    )

    if not input_has_pii:
        return

    driver = get_neo4j_driver()
    with driver.session() as session:
        for output in event.outputs:
            session.run(
                """
                MATCH (d:Dataset {uri: $uri})
                WHERE NOT 'pii' IN d.tags
                SET d.tags = d.tags + ['pii']
                """,
                uri=output.uri,
            )

    logger.info(
        f"PII tags propagated to {len(event.outputs)} output dataset(s) "
        f"from job {event.job.name}"
    )


def propagate_pii_retroactive() -> int:
    """
    Multi-hop retroactive PII propagation.
    Finds any downstream dataset from a PII dataset and ensures it also has the PII tag.
    Returns the number of datasets updated.
    """
    driver = get_neo4j_driver()
    with driver.session() as session:
        result = session.run(
            """
            MATCH (pii:Dataset)-[:CONSUMES|PRODUCES*1..20]->(downstream:Dataset)
            WHERE 'pii' IN pii.tags AND NOT 'pii' IN downstream.tags
            SET downstream.tags = downstream.tags + ['pii']
            RETURN count(DISTINCT downstream) as updated_count
            """
        )
        record = result.single()
        count = record["updated_count"] if record else 0
        logger.info(f"Retroactive PII propagation updated {count} datasets.")
        return count

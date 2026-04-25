from fastapi import APIRouter, HTTPException, Query
from app.api.pydantic_models import LineageGraphResponse, RunsResponse, NodeModel, EdgeModel, RunRecord, DatasetsResponse, GlobalRunsResponse, DatasetRecord, ImpactResponse
from app.db_client import get_neo4j_driver, get_postgres_conn
import logging
from app.storage.graph_writer import propagate_pii_retroactive

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/lineage", tags=["query"])


def _neo4j_node_to_model(node) -> NodeModel:
    label = list(node.labels)[0] if node.labels else "Unknown"
    return NodeModel(
        id=str(node.element_id),
        label=label,
        properties=dict(node),
    )


def _neo4j_rel_to_model(rel) -> EdgeModel:
    return EdgeModel(
        source_id=str(rel.start_node.element_id),
        target_id=str(rel.end_node.element_id),
        type=rel.type,
        properties=dict(rel),
    )


@router.get("/upstream/{dataset_id:path}", response_model=LineageGraphResponse)
def get_upstream(
    dataset_id: str,
    depth: int = Query(default=10, ge=1, le=20, description="Max traversal hops"),
):
    """
    Returns all datasets and jobs that are upstream of the given dataset.
    Walks CONSUMES edges backwards — finding everything that produced this data.

    dataset_id: The URI of the dataset, e.g. "postgres://clean.orders"
    depth: Maximum number of hops to traverse (default 10, max 20)
    """
    driver = get_neo4j_driver()

    with driver.session() as session:
        # First check if dataset exists
        exists = session.run(
            "MATCH (d:Dataset {uri: $uri}) RETURN d.uri LIMIT 1",
            uri=dataset_id
        ).single()
        if not exists:
            raise HTTPException(status_code=404, detail=f"Dataset not found: {dataset_id}")

        max_edges = depth * 2
        result = session.run(
            f"""
            MATCH path = (start:Dataset {{uri: $uri}})<-[:CONSUMES|PRODUCES*1..{max_edges}]-(node)
            WHERE node:Dataset OR node:Job
            RETURN DISTINCT nodes(path) AS ns, relationships(path) AS rs
            LIMIT 1000
            """,
            uri=dataset_id,
        )

        all_nodes: dict[str, NodeModel] = {}
        all_edges: list[EdgeModel] = []

        for record in result:
            for node in record["ns"]:
                node_model = _neo4j_node_to_model(node)
                all_nodes[node_model.id] = node_model
            for rel in record["rs"]:
                all_edges.append(_neo4j_rel_to_model(rel))

    return LineageGraphResponse(
        dataset_id=dataset_id,
        direction="upstream",
        depth=depth,
        nodes=list(all_nodes.values()),
        edges=all_edges,
        node_count=len(all_nodes),
        edge_count=len(all_edges),
    )


@router.get("/downstream/{dataset_id:path}", response_model=LineageGraphResponse)
def get_downstream(
    dataset_id: str,
    depth: int = Query(default=10, ge=1, le=20),
):
    """
    Returns all datasets and jobs downstream of the given dataset.
    Walks PRODUCES edges forward — finding everything this data feeds into.
    """
    driver = get_neo4j_driver()

    with driver.session() as session:
        exists = session.run(
            "MATCH (d:Dataset {uri: $uri}) RETURN d.uri LIMIT 1",
            uri=dataset_id
        ).single()
        if not exists:
            raise HTTPException(status_code=404, detail=f"Dataset not found: {dataset_id}")

        max_edges = depth * 2
        result = session.run(
            f"""
            MATCH path = (start:Dataset {{uri: $uri}})-[:CONSUMES|PRODUCES*1..{max_edges}]->(node)
            WHERE node:Dataset OR node:Job
            RETURN DISTINCT nodes(path) AS ns, relationships(path) AS rs
            LIMIT 1000
            """,
            uri=dataset_id,
        )

        all_nodes: dict[str, NodeModel] = {}
        all_edges: list[EdgeModel] = []

        for record in result:
            for node in record["ns"]:
                node_model = _neo4j_node_to_model(node)
                all_nodes[node_model.id] = node_model
            for rel in record["rs"]:
                all_edges.append(_neo4j_rel_to_model(rel))

    return LineageGraphResponse(
        dataset_id=dataset_id,
        direction="downstream",
        depth=depth,
        nodes=list(all_nodes.values()),
        edges=all_edges,
        node_count=len(all_nodes),
        edge_count=len(all_edges),
    )


@router.get("/impact/{dataset_id:path}", response_model=ImpactResponse)
def get_impact(dataset_id: str):
    """
    Returns an impact analysis of changing this dataset.
    Finds all downstream jobs and datasets that depend on it transitively.
    """
    driver = get_neo4j_driver()
    with driver.session() as session:
        exists = session.run(
            "MATCH (d:Dataset {uri: $uri}) RETURN d.uri LIMIT 1",
            uri=dataset_id
        ).single()
        if not exists:
            raise HTTPException(status_code=404, detail=f"Dataset not found: {dataset_id}")

        result = session.run(
            """
            MATCH path = (start:Dataset {uri: $uri})-[:CONSUMES|PRODUCES*1..20]->(node)
            WHERE node:Dataset OR node:Job
            RETURN DISTINCT node
            """,
            uri=dataset_id,
        )

        affected_jobs = []
        affected_datasets = []

        for record in result:
            node = record["node"]
            label = list(node.labels)[0] if node.labels else "Unknown"
            if label == "Job":
                affected_jobs.append(node["name"])
            elif label == "Dataset":
                affected_datasets.append(node["uri"])

        impact_score = len(affected_jobs) + len(affected_datasets)

    return ImpactResponse(
        dataset_uri=dataset_id,
        affected_jobs=affected_jobs,
        affected_datasets=affected_datasets,
        impact_score=impact_score
    )


# IMPORTANT: /runs/global MUST be defined BEFORE /runs/{job_id:path}
# otherwise FastAPI matches the string "global" as a job_id.
@router.get("/runs/global", response_model=list[dict])
def get_global_runs(limit: int = Query(default=100, ge=1, le=500)):
    """
    Returns the most recent pipeline runs across ALL jobs (global audit view).
    """
    try:
        conn = get_postgres_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT run_id, job_name, status, start_time, end_time,
                       input_datasets, output_datasets
                FROM run_log
                ORDER BY start_time DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()
        conn.close()
    except Exception as e:
        logger.error(f"Postgres global runs query failed: {e}")
        raise HTTPException(status_code=500, detail="Database query failed")

    return [
        {
            "run_id": str(row[0]),
            "job_name": row[1],
            "status": row[2],
            "start_time": row[3].isoformat() if row[3] else None,
            "end_time": row[4].isoformat() if row[4] else None,
            "input_datasets": row[5] or [],
            "output_datasets": row[6] or [],
        }
        for row in rows
    ]


@router.get("/runs/{job_id:path}", response_model=RunsResponse)
def get_runs(job_id: str, limit: int = Query(default=50, ge=1, le=500)):
    """
    Returns the run history of a specific job from PostgreSQL.
    Returns empty list (not 404) if the job has no recorded runs.
    """
    try:
        conn = get_postgres_conn()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT run_id, job_name, status, start_time, end_time,
                       input_datasets, output_datasets
                FROM run_log
                WHERE job_name = %s
                ORDER BY start_time DESC
                LIMIT %s
                """,
                (job_id, limit),
            )
            rows = cur.fetchall()
        conn.close()
    except Exception as e:
        logger.error(f"Postgres query failed for job {job_id}: {e}")
        raise HTTPException(status_code=500, detail="Database query failed")

    runs = [
        RunRecord(
            run_id=str(row[0]),
            job_name=row[1],
            status=row[2],
            start_time=row[3].isoformat() if row[3] else None,
            end_time=row[4].isoformat() if row[4] else None,
            input_datasets=row[5] or [],
            output_datasets=row[6] or [],
        )
        for row in rows
    ]
    return RunsResponse(job_id=job_id, run_count=len(runs), runs=runs)


@router.get("/datasets", response_model=list[dict])
def get_datasets():
    """
    Returns a list of all datasets available in the graph.
    """
    driver = get_neo4j_driver()
    with driver.session() as session:
        result = session.run(
            "MATCH (d:Dataset) RETURN d.uri AS uri, d.namespace AS namespace, d.name AS name LIMIT 1000"
        )
        return [{"uri": r["uri"], "namespace": r["namespace"], "name": r["name"]} for r in result]


@router.post("/admin/propagate-pii")
def trigger_pii_propagation():
    """
    Triggers retroactive multi-hop PII propagation.
    """
    try:
        updated_count = propagate_pii_retroactive()
        return {"status": "success", "datasets_updated": updated_count}
    except Exception as e:
        logger.error(f"PII propagation failed: {e}")
        raise HTTPException(status_code=500, detail="PII propagation failed")

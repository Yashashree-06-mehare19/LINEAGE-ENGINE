# app/api/column_router.py
"""
Stage 10: Column-Level Lineage Query Endpoints
===============================================
Three endpoints for drilling into column-to-column lineage:

  GET /lineage/columns/{dataset_uri}
      → All columns known for a dataset

  GET /lineage/column-upstream/{column_uri}
      → All upstream columns that feed INTO a column (trace backwards)

  GET /lineage/column-impact/{column_uri}
      → All downstream columns that depend on a column (impact analysis)

Column URI format:  {dataset_namespace}://{dataset_name}/{column_name}
Example:            postgres://raw_orders/cust_id
"""
from fastapi import APIRouter, HTTPException
from urllib.parse import unquote
from app.api.pydantic_models import (
    ColumnListResponse,
    ColumnModel,
    ColumnImpactResponse,
    ColumnUpstreamResponse,
    ColumnTraceEntry,
)
from app.db_client import get_neo4j_driver
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/lineage", tags=["column-lineage"])


@router.get("/columns/{dataset_uri:path}", response_model=ColumnListResponse)
def get_columns_for_dataset(dataset_uri: str):
    """
    Returns all columns that belong to the given dataset.
    The dataset must exist in the graph (be a known Dataset node).
    Returns an empty column list (not 404) if the dataset has no columns yet.
    404 if the dataset itself doesn't exist.
    """
    dataset_uri = unquote(dataset_uri)
    driver = get_neo4j_driver()

    with driver.session() as session:
        # Verify dataset exists
        ds_exists = session.run(
            "MATCH (d:Dataset {uri: $uri}) RETURN d.uri LIMIT 1",
            uri=dataset_uri,
        ).single()
        if not ds_exists:
            raise HTTPException(
                status_code=404,
                detail=f"Dataset not found: {dataset_uri}"
            )

        result = session.run(
            """
            MATCH (c:Column {dataset_uri: $dataset_uri})
            RETURN c.uri AS uri, c.name AS name, c.dataset_uri AS dataset_uri
            ORDER BY c.name
            """,
            dataset_uri=dataset_uri,
        )

        columns = [
            ColumnModel(uri=r["uri"], name=r["name"], dataset_uri=r["dataset_uri"])
            for r in result
        ]

    return ColumnListResponse(
        dataset_uri=dataset_uri,
        column_count=len(columns),
        columns=columns,
    )


@router.get("/column-upstream/{column_uri:path}", response_model=ColumnUpstreamResponse)
def get_column_upstream(column_uri: str):
    """
    Traces backwards through TRANSFORMS edges to find all upstream columns
    that feed into the given column (directly or transitively).

    Answers: "Where does the data in this column originally come from?"
    404 if the column doesn't exist.
    """
    column_uri = unquote(column_uri)
    driver = get_neo4j_driver()

    with driver.session() as session:
        col_exists = session.run(
            "MATCH (c:Column {uri: $uri}) RETURN c.uri LIMIT 1",
            uri=column_uri,
        ).single()
        if not col_exists:
            raise HTTPException(
                status_code=404,
                detail=f"Column not found: {column_uri}"
            )

        # Walk TRANSFORMS edges backwards (upstream)
        # r.via_job is on the TRANSFORMS edge
        result = session.run(
            """
            MATCH (start:Column {uri: $uri})<-[r:TRANSFORMS*1..10]-(upstream:Column)
            WITH DISTINCT upstream,
                 [rel IN r | rel.via_job][0] AS via_job
            RETURN upstream.uri       AS uri,
                   upstream.name      AS name,
                   upstream.dataset_uri AS dataset_uri,
                   via_job
            """,
            uri=column_uri,
        )

        upstream_cols = [
            ColumnTraceEntry(
                uri=row["uri"],
                name=row["name"],
                dataset_uri=row["dataset_uri"],
                via_job=row["via_job"] or "",
            )
            for row in result
        ]

    return ColumnUpstreamResponse(
        column_uri=column_uri,
        upstream_columns=upstream_cols,
    )


@router.get("/column-impact/{column_uri:path}", response_model=ColumnImpactResponse)
def get_column_impact(column_uri: str):
    """
    Traces forwards through TRANSFORMS edges to find all downstream columns
    that depend on the given column (directly or transitively).

    Answers: "If I rename/drop this column, what downstream columns break?"
    Impact score = total number of impacted columns.
    404 if the column doesn't exist.
    """
    column_uri = unquote(column_uri)
    driver = get_neo4j_driver()

    with driver.session() as session:
        col_exists = session.run(
            "MATCH (c:Column {uri: $uri}) RETURN c.uri LIMIT 1",
            uri=column_uri,
        ).single()
        if not col_exists:
            raise HTTPException(
                status_code=404,
                detail=f"Column not found: {column_uri}"
            )

        # Walk TRANSFORMS edges forwards (downstream impact)
        result = session.run(
            """
            MATCH (start:Column {uri: $uri})-[r:TRANSFORMS*1..10]->(downstream:Column)
            WITH DISTINCT downstream,
                 [rel IN r | rel.via_job][0] AS via_job
            RETURN downstream.uri       AS uri,
                   downstream.name      AS name,
                   downstream.dataset_uri AS dataset_uri,
                   via_job
            """,
            uri=column_uri,
        )

        impacted = [
            ColumnTraceEntry(
                uri=row["uri"],
                name=row["name"],
                dataset_uri=row["dataset_uri"],
                via_job=row["via_job"] or "",
            )
            for row in result
        ]

    return ColumnImpactResponse(
        column_uri=column_uri,
        impacted_columns=impacted,
        impact_score=len(impacted),
    )

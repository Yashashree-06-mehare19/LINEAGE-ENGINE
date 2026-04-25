from pydantic import BaseModel
from typing import Optional, Any


class NodeModel(BaseModel):
    """Represents a single node in the lineage graph."""
    id: str                     # Neo4j element ID
    label: str                  # "Job", "Dataset", or "Run"
    properties: dict[str, Any]  # All node properties


class EdgeModel(BaseModel):
    """Represents a directed relationship between two nodes."""
    source_id: str
    target_id: str
    type: str                   # "PRODUCES", "CONSUMES", "HAS_RUN"
    properties: dict[str, Any]


class LineageGraphResponse(BaseModel):
    """
    Response for upstream and downstream traversal endpoints.
    Returns the full subgraph as nodes + edges.
    """
    dataset_id: str
    direction: str              # "upstream" or "downstream"
    depth: int
    nodes: list[NodeModel]
    edges: list[EdgeModel]
    node_count: int
    edge_count: int


class RunRecord(BaseModel):
    run_id: str
    job_name: str
    status: str
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    input_datasets: list[str] = []
    output_datasets: list[str] = []


class RunsResponse(BaseModel):
    job_id: str
    run_count: int
    runs: list[RunRecord]

class DatasetRecord(BaseModel):
    uri: str
    namespace: str
    name: str

class DatasetsResponse(BaseModel):
    dataset_count: int
    datasets: list[DatasetRecord]

class GlobalRunsResponse(BaseModel):
    run_count: int
    runs: list[RunRecord]

class ImpactResponse(BaseModel):
    dataset_uri: str
    affected_jobs: list[str]
    affected_datasets: list[str]
    impact_score: int

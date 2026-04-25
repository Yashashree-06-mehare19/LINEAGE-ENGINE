from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class DatasetRef:
    namespace: str
    name: str
    uri: str
    tags: list[str] = field(default_factory=list)


@dataclass
class JobRef:
    name: str
    owner: str = ""
    orchestrator: str = "airflow"


@dataclass
class RunRef:
    run_id: str
    status: str
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


@dataclass
class ColumnTransform:
    """
    A single column-to-column mapping produced by a job.
    Stored as a TRANSFORMS edge between two Column nodes in Neo4j.

    URI format:  {dataset_namespace}://{dataset_name}/{column_name}
    Example:     postgres://raw_orders/cust_id  →  postgres://orders/customer_id
    """
    input_column_uri: str    # e.g. "postgres://raw_orders/cust_id"
    output_column_uri: str   # e.g. "postgres://orders/customer_id"
    input_column_name: str   # e.g. "cust_id"
    output_column_name: str  # e.g. "customer_id"
    input_dataset_uri: str   # parent dataset, e.g. "postgres://raw_orders"
    output_dataset_uri: str  # parent dataset, e.g. "postgres://orders"
    via_job_name: str
    run_id: str
    timestamp: str           # ISO8601 string


@dataclass
class LineageEvent:
    job: JobRef
    run: RunRef
    inputs: list[DatasetRef]
    outputs: list[DatasetRef]
    event_time: Optional[datetime] = None
    # Stage 10: column-level transforms extracted from the OL columnLineage facet.
    # Defaults to [] so all existing callers continue working with zero changes.
    column_transforms: list[ColumnTransform] = field(default_factory=list)
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
class LineageEvent:
    job: JobRef
    run: RunRef
    inputs: list[DatasetRef]
    outputs: list[DatasetRef]
    event_time: Optional[datetime] = None
from app.ingestion.pydantic_models import OLRunEvent, OLDataset
from app.models import LineageEvent, JobRef, RunRef, DatasetRef
from datetime import datetime, timezone


def ol_dataset_to_ref(ds: OLDataset) -> DatasetRef:
    # If namespace already contains "://" (e.g. "postgres://prod:5432"),
    # join with "/" to avoid double "://" in the URI.
    # Otherwise (e.g. namespace="airflow"), join with "://".
    sep = "/" if "://" in ds.namespace else "://"
    return DatasetRef(
        namespace=ds.namespace,
        name=ds.name,
        uri=f"{ds.namespace}{sep}{ds.name}",
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

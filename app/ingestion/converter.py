from app.ingestion.pydantic_models import OLRunEvent, OLDataset
from app.models import LineageEvent, JobRef, RunRef, DatasetRef, ColumnTransform
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


def _build_dataset_uri(namespace: str, name: str) -> str:
    """Build dataset URI using the same logic as ol_dataset_to_ref."""
    sep = "/" if "://" in namespace else "://"
    return f"{namespace}{sep}{name}"


def _extract_column_transforms(
    event: OLRunEvent,
    inputs: list[DatasetRef],
    outputs: list[DatasetRef],
) -> list[ColumnTransform]:
    """
    Stage 10: Parse the OpenLineage columnLineage facet from each output dataset.

    The facet structure is:
      output.facets["columnLineage"]["fields"] = {
          "output_col_name": {
              "inputFields": [
                  {"namespace": "...", "name": "dataset_name", "field": "input_col_name"}
              ]
          }
      }

    Column URI format: {dataset_namespace}://{dataset_name}/{column_name}
    Example:           postgres://raw_orders/cust_id
    """
    transforms: list[ColumnTransform] = []
    now_iso = datetime.now(timezone.utc).isoformat()

    for output_ds in event.outputs:
        if not output_ds.column_lineage:
            continue

        # Build the output dataset URI (same logic as ol_dataset_to_ref)
        output_dataset_uri = _build_dataset_uri(output_ds.namespace, output_ds.name)

        for output_col_name, field_def in output_ds.column_lineage.fields.items():
            # URI of the output column
            output_col_uri = f"{output_dataset_uri}/{output_col_name}"

            for input_field in field_def.inputFields:
                input_dataset_uri = _build_dataset_uri(input_field.namespace, input_field.name)
                input_col_uri = f"{input_dataset_uri}/{input_field.field}"

                transforms.append(ColumnTransform(
                    input_column_uri=input_col_uri,
                    output_column_uri=output_col_uri,
                    input_column_name=input_field.field,
                    output_column_name=output_col_name,
                    input_dataset_uri=input_dataset_uri,
                    output_dataset_uri=output_dataset_uri,
                    via_job_name=event.job.name,
                    run_id=event.run.runId,
                    timestamp=now_iso,
                ))

    return transforms


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

    inputs = [ol_dataset_to_ref(ds) for ds in event.inputs]
    outputs = [ol_dataset_to_ref(ds) for ds in event.outputs]

    # Stage 10: extract column-level transforms from the columnLineage facet
    column_transforms = _extract_column_transforms(event, inputs, outputs)

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
        inputs=inputs,
        outputs=outputs,
        event_time=event.eventTime,
        column_transforms=column_transforms,
    )

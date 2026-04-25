from pydantic import BaseModel, Field, model_validator
from typing import Optional, Any
from datetime import datetime


class OLDataset(BaseModel):
    namespace: str
    name: str
    facets: dict[str, Any] = Field(default_factory=dict)

    # Stage 10: parsed from facets["columnLineage"] if present
    column_lineage: Optional["OLColumnLineageFacet"] = None

    @model_validator(mode="after")
    def extract_column_lineage(self) -> "OLDataset":
        """
        The columnLineage facet arrives inside facets["columnLineage"].
        We parse it here into a typed model so converter.py can iterate it cleanly.
        """
        raw = self.facets.get("columnLineage")
        if raw and isinstance(raw, dict) and "fields" in raw:
            try:
                self.column_lineage = OLColumnLineageFacet(**raw)
            except Exception:
                # If facet is malformed, skip column lineage — don't crash ingestion
                self.column_lineage = None
        return self


class OLInputField(BaseModel):
    """One input column that feeds into an output column."""
    namespace: str
    name: str       # dataset name
    field: str      # column name within that dataset
    model_config = {"extra": "allow"}


class OLColumnLineageField(BaseModel):
    """All input fields that feed into one specific output column."""
    inputFields: list[OLInputField] = Field(default_factory=list)
    model_config = {"extra": "allow"}


class OLColumnLineageFacet(BaseModel):
    """
    The full columnLineage facet for one output dataset.
    fields maps output_column_name → {inputFields: [...]}

    OpenLineage spec example:
    {
      "fields": {
        "customer_id": {
          "inputFields": [
            { "namespace": "postgres", "name": "raw_orders", "field": "cust_id" }
          ]
        }
      }
    }
    """
    fields: dict[str, OLColumnLineageField] = Field(default_factory=dict)
    model_config = {"extra": "allow"}


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


# Rebuild so forward references resolve
OLDataset.model_rebuild()

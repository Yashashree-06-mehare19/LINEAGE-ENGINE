"""
pipeline_plugin.py — Pipeline Adapter for Lineage Engine
=========================================================
This is the ONLY file you need to change to point the lineage engine
at a different data pipeline. No SQL parsing, no file paths.

Just define:
  - PIPELINE_NAME: human-readable label
  - NAMESPACE: the database/platform namespace (becomes part of every URI)
  - PIPELINE_JOBS: the ordered list of jobs, each with inputs and outputs

How URIs are built:
  namespace="duckdb://jaffle_shop" + name="raw_orders"
  → URI in Neo4j: "duckdb://jaffle_shop/raw_orders"

Default: Jaffle Shop DuckDB pipeline (5 transformation jobs)

         raw_customers ──► stg_customers ──┐
                                            ├──► customers  (final mart)
         raw_orders ────► stg_orders ──────┤
                                            └──► orders     (final mart)
         raw_payments ──► stg_payments ────┘
"""

# ── Configuration ────────────────────────────────────────────────────────────

PIPELINE_NAME = "jaffle_shop"
NAMESPACE = "duckdb://jaffle_shop"          # Used as job namespace
ORCHESTRATOR = "dbt"                         # Label shown on job nodes
EVENT_DELAY_SECONDS = 3.0                    # Pause between events so you can watch the graph grow

# ── Pipeline Job Definitions ──────────────────────────────────────────────────
# Each job = one transformation step in the pipeline.
# inputs/outputs = list of (namespace, dataset_name) tuples.

PIPELINE_JOBS = [
    {
        "job_name": "stg_customers",
        "description": "Stage raw customer records",
        "inputs": [
            (NAMESPACE, "raw_customers"),
        ],
        "outputs": [
            (NAMESPACE, "stg_customers"),
        ],
    },
    {
        "job_name": "stg_orders",
        "description": "Stage raw order records",
        "inputs": [
            (NAMESPACE, "raw_orders"),
        ],
        "outputs": [
            (NAMESPACE, "stg_orders"),
        ],
    },
    {
        "job_name": "stg_payments",
        "description": "Stage raw payment records",
        "inputs": [
            (NAMESPACE, "raw_payments"),
        ],
        "outputs": [
            (NAMESPACE, "stg_payments"),
        ],
    },
    {
        "job_name": "customers",
        "description": "Build customer mart: combines customers, orders, payments",
        "inputs": [
            (NAMESPACE, "stg_customers"),
            (NAMESPACE, "stg_orders"),
            (NAMESPACE, "stg_payments"),
        ],
        "outputs": [
            (NAMESPACE, "customers"),
        ],
    },
    {
        "job_name": "orders",
        "description": "Build orders mart: enriches orders with payment info",
        "inputs": [
            (NAMESPACE, "stg_orders"),
            (NAMESPACE, "stg_payments"),
        ],
        "outputs": [
            (NAMESPACE, "orders"),
        ],
    },
]

# ── Default Search URI for the Dashboard ─────────────────────────────────────
# This is what the "Try Demo" button in the React dashboard will search for.
# We use the raw input and search downstream so the user can watch the graph grow live!
DEFAULT_SEARCH_URI = f"{NAMESPACE}/raw_customers"
DEFAULT_SEARCH_DIRECTION = "downstream"

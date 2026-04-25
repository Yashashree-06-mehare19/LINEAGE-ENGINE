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

Stage 10: column_mappings added to each job.
  Each entry is (input_dataset_name, input_col, output_dataset_name, output_col).
  These are injected as OpenLineage columnLineage facets when events are emitted.
"""

# ── Configuration ────────────────────────────────────────────────────────────

PIPELINE_NAME = "jaffle_shop"
NAMESPACE = "duckdb://jaffle_shop"          # Used as job namespace
ORCHESTRATOR = "dbt"                         # Label shown on job nodes
EVENT_DELAY_SECONDS = 3.0                    # Pause between events so you can watch the graph grow

# ── Pipeline Job Definitions ──────────────────────────────────────────────────
# Each job = one transformation step in the pipeline.
# inputs/outputs = list of (namespace, dataset_name) tuples.
# column_mappings = list of (input_dataset, input_col, output_dataset, output_col)

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
        "column_mappings": [
            ("raw_customers", "id",         "stg_customers", "customer_id"),
            ("raw_customers", "first_name", "stg_customers", "first_name"),
            ("raw_customers", "last_name",  "stg_customers", "last_name"),
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
        "column_mappings": [
            ("raw_orders", "id",         "stg_orders", "order_id"),
            ("raw_orders", "user_id",    "stg_orders", "customer_id"),
            ("raw_orders", "status",     "stg_orders", "status"),
            ("raw_orders", "order_date", "stg_orders", "order_date"),
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
        "column_mappings": [
            ("raw_payments", "id",             "stg_payments", "payment_id"),
            ("raw_payments", "order_id",       "stg_payments", "order_id"),
            ("raw_payments", "payment_method", "stg_payments", "payment_method"),
            ("raw_payments", "amount",         "stg_payments", "amount"),
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
        "column_mappings": [
            ("stg_customers", "customer_id",   "customers", "customer_id"),
            ("stg_customers", "first_name",    "customers", "first_name"),
            ("stg_customers", "last_name",     "customers", "last_name"),
            ("stg_orders",    "order_id",      "customers", "first_order"),
            ("stg_payments",  "amount",        "customers", "lifetime_value"),
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
        "column_mappings": [
            ("stg_orders",   "order_id",       "orders", "order_id"),
            ("stg_orders",   "customer_id",    "orders", "customer_id"),
            ("stg_orders",   "status",         "orders", "status"),
            ("stg_payments", "amount",         "orders", "amount"),
            ("stg_payments", "payment_method", "orders", "bank_transfer_amount"),
        ],
    },
]

# ── Default Search URI for the Dashboard ─────────────────────────────────────
# Searching UPSTREAM from the final "customers" mart reveals all 3 raw source
# branches (raw_customers, raw_orders, raw_payments) converging through their
# staging layers — this is the full Jaffle Shop fan-in graph.
DEFAULT_SEARCH_URI = f"{NAMESPACE}/customers"
DEFAULT_SEARCH_DIRECTION = "upstream"

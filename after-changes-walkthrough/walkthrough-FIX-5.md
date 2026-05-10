# Walkthrough — Stage 10: Column-Level Lineage

This walkthrough covers the implementation of column-level tracking in the Lineage Engine.

## Changes Made

### 1. Data Models Updated
- **File:** `app/models.py`
- Added `ColumnRef` dataclass to store column names, URIs, and upstream dependencies.
- Updated `DatasetRef` to include a `columns` list.

### 2. Ingestion Logic
- **File:** `app/ingestion/converter.py`
- Updated `ol_dataset_to_ref` to parse the OpenLineage `columnLineage` facet.
- It now automatically maps output columns to their input columns across different datasets.

### 3. Neo4j Storage Layer
- **File:** `app/storage/graph_writer.py`
- Implemented `_upsert_column` and `_create_derived_from_edge`.
- Every ingestion now creates `(Dataset)-[:HAS_COLUMN]->(Column)` and `(Column)-[:DERIVED_FROM]->(Column)` relationships.
- Unique constraints for columns are enforced using the format `{dataset_uri}::{column_name}`.

### 4. Query API
- **File:** `app/api/router.py`
- Added a new endpoint: `GET /lineage/datasets/{uri}/columns`.
- This returns the schema of a dataset and the column-level lineage (where each column came from).

### 5. Frontend Dashboard
- **File:** `frontend/src/components/NodeSidePanel.jsx`
- Added a "Columns" section that appears when a dataset node is selected.
- Displays all columns and their upstream "Derived From" sources with a clean hierarchical UI.

## How to Verify

1. **Start the Engine:**
   ```bash
   python run_live_demo.py
   ```

2. **Trigger Column Lineage Test:**
   Run the provided test script which sends a payload with complex column dependencies:
   ```bash
   python scripts/test_stage10.py
   ```

3. **Check the Dashboard:**
   - Open `http://localhost:5173`.
   - Find the `clean_users` dataset.
   - Click it to open the side panel.
   - You should see the columns `user_id` and `full_name` with their respective upstream sources mapped.

## Technical Notes
- **Column Identity:** Columns are globally unique because their URI includes the parent dataset URI.
- **Idempotency:** Using `MERGE` ensures that re-sending the same lineage event does not create duplicate columns or edges.
- **Visual Clarity:** The main graph remains at the table level to prevent clutter, while column details are tucked away in the side panel for drill-down analysis.

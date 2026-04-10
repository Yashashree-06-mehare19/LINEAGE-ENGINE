# Learning: Debugging The Pipeline Seeding Issues

Hi Aary, here is a quick breakdown of the issues we just solved during Stage 1 Day 2 of our Execution Plan!

## 1. What was the problem?
When we ran `python scripts/seed_real_events.py`, we encountered a few sequential errors:
1. **URI Double Slam (`postgres://prod:5432://raw.orders`)**: Our `/lineage/upstream` and downstream queries returned `404 Not Found`. While debugging, we realized that the database correctly ingested the nodes, but the `DatasetRef` URIs were improperly formatted with an extra `://`.
2. **KeyError: 'type' & List vs Dict**: When verifying the API output, the `seed_real_events.py` test script crashed with `KeyError: 'type'` while parsing nodes, and the `test_runs` function failed because it expected a `list` iteratively but received a `dict`.
3. **Database Connection Refused**: A sudden `WinError 10061` and connection refusal. `neo4j` stopped responding and exited entirely when we tried to re-run the ingest script.

## 2. Solution
Here is the step-by-step resolution to the three problems:

1. **Fixing URI Construction**: We modified the `ol_dataset_to_ref` method inside `app/ingestion/converter.py` to be smarter about separators.
2. **Fixing Response Parsing**: We updated `scripts/seed_real_events.py` to use `.get('label')` corresponding to our internal `NodeModel` schema, and securely unpacked `r.json().get('runs', [])`.
3. **Restarting Neo4j Effectively**: We cleared the stale lock files by taking the container setup fully down via `docker compose down` to remove the instance, before bringing it back up properly clean with `docker compose up -d`.

## 3. How we tackled it and what did we use?

- **Python Logic (URI Fix)**: We used basic string checking to avoid the double URI mapping bug. 
  ```python
  # Checked if "://" already existed in the namespace
  sep = "/" if "://" in ds.namespace else "://"
  ```
- **Pydantic Model Matching (Response Parsing)**: We cross-referenced `app/api/pydantic_models.py` schema for `LineageGraphResponse` and `RunsResponse` to match our script access keys (`node['label']` instead of `'type'` and grabbing the `'runs'` array out of the JSON dict). 
- **Docker Tooling (Neo4j Crash)**: A container crash happens often when Neo4j is abruptly stopped—leaving a lock file hanging. Running `docker compose down` deletes the container and the network namespace safely, forcing a fresh clean startup upon `docker compose up -d` without wiping the persistent mounted volumes where our data actually lives!

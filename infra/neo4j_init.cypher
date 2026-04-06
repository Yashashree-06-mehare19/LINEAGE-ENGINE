CREATE CONSTRAINT job_name_unique IF NOT EXISTS
  FOR (j:Job) REQUIRE j.name IS UNIQUE;

CREATE CONSTRAINT dataset_uri_unique IF NOT EXISTS
  FOR (d:Dataset) REQUIRE d.uri IS UNIQUE;

CREATE CONSTRAINT run_id_unique IF NOT EXISTS
  FOR (r:Run) REQUIRE r.run_id IS UNIQUE;

CREATE INDEX dataset_tags_index IF NOT EXISTS
  FOR (d:Dataset) ON (d.tags);
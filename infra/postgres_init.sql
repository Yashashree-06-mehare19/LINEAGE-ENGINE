CREATE TABLE IF NOT EXISTS run_log (
    run_id          TEXT PRIMARY KEY,
    job_name        TEXT NOT NULL,
    status          TEXT NOT NULL,
    start_time      TIMESTAMPTZ,
    end_time        TIMESTAMPTZ,
    input_datasets  TEXT[],
    output_datasets TEXT[],
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS run_log_job_name_idx ON run_log (job_name);
CREATE INDEX IF NOT EXISTS run_log_start_time_idx ON run_log (start_time DESC);
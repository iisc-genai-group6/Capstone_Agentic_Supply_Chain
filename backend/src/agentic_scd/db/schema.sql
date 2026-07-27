CREATE TABLE IF NOT EXISTS signals (
    signal_id TEXT PRIMARY KEY,
    dedup_hash TEXT UNIQUE,
    source TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_reliability REAL,
    fetched_at TEXT NOT NULL,
    event_time TEXT,
    title TEXT NOT NULL,
    raw_text TEXT NOT NULL DEFAULT '',
    url TEXT,
    location TEXT,
    severity_hint TEXT,
    schema_version INTEGER NOT NULL,
    raw_payload TEXT,
    status TEXT NOT NULL DEFAULT 'new',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_signals_status ON signals(status);
CREATE INDEX IF NOT EXISTS idx_signals_dedup_hash ON signals(dedup_hash);
CREATE TABLE IF NOT EXISTS seen_rejected (
    dedup_hash TEXT PRIMARY KEY,
    first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    scenario_name TEXT,
    route TEXT,
    max_severity REAL,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    action_index INTEGER NOT NULL,
    action_text TEXT NOT NULL,
    owner TEXT,
    approved_by TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (run_id, action_index)
);
CREATE INDEX IF NOT EXISTS idx_approvals_run_id ON approvals(run_id);

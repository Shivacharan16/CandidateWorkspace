-- ====================================================================
-- CDC Ingestion & Auditable History Pipeline Database Schema
-- Compatible with SQLite and PostgreSQL syntax conventions
-- ====================================================================

-- Enable Foreign Key constraints in SQLite
PRAGMA foreign_keys = ON;

-- --------------------------------------------------------------------
-- 1. Pipeline Runs (Operational Auditing & Observability)
-- --------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id TEXT PRIMARY KEY,
    batch_name TEXT NOT NULL,
    source_file TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    duration_ms REAL,
    status TEXT NOT NULL, -- RUNNING, SUCCESS, PARTIAL_SUCCESS, FAILED
    total_events INTEGER NOT NULL DEFAULT 0,
    inserted_count INTEGER NOT NULL DEFAULT 0,
    updated_count INTEGER NOT NULL DEFAULT 0,
    deleted_count INTEGER NOT NULL DEFAULT 0,
    duplicate_count INTEGER NOT NULL DEFAULT 0,
    quarantined_count INTEGER NOT NULL DEFAULT 0,
    out_of_order_count INTEGER NOT NULL DEFAULT 0,
    error_summary TEXT
);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_started_at ON pipeline_runs(started_at DESC);

-- --------------------------------------------------------------------
-- 2. Processed Events (Idempotency & Deduplication Log)
-- --------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS processed_events (
    event_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    event_timestamp TEXT NOT NULL,
    pipeline_run_id TEXT NOT NULL,
    fingerprint_hash TEXT NOT NULL,
    processed_at TEXT NOT NULL,
    FOREIGN KEY(pipeline_run_id) REFERENCES pipeline_runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_processed_events_entity ON processed_events(entity_type, entity_id);

-- --------------------------------------------------------------------
-- 3. Quarantine Records (Dead-Letter Queue / Rejected Events)
-- --------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS quarantine_records (
    quarantine_id INTEGER PRIMARY KEY AUTOINCREMENT,
    pipeline_run_id TEXT NOT NULL,
    event_id TEXT,
    entity_type TEXT,
    entity_id TEXT,
    error_code TEXT NOT NULL,
    error_message TEXT NOT NULL,
    raw_payload TEXT NOT NULL,
    quarantined_at TEXT NOT NULL,
    retry_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'NEW', -- NEW, RETRIED, RESOLVED, DISCARDED
    FOREIGN KEY(pipeline_run_id) REFERENCES pipeline_runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_quarantine_run ON quarantine_records(pipeline_run_id);
CREATE INDEX IF NOT EXISTS idx_quarantine_status ON quarantine_records(status);

-- --------------------------------------------------------------------
-- 4. Customer Dimension (Current State)
-- --------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dim_customers_current (
    customer_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    tier TEXT NOT NULL,
    credit_limit REAL NOT NULL,
    status TEXT NOT NULL,
    address_city TEXT,
    address_country TEXT,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    last_event_id TEXT NOT NULL,
    last_event_timestamp TEXT NOT NULL,
    last_sequence_number INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_customers_current_status ON dim_customers_current(status, is_deleted);

-- --------------------------------------------------------------------
-- 5. Customer Dimension History (Auditable History / SCD Type 2)
-- --------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dim_customers_history (
    history_id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id TEXT NOT NULL,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    tier TEXT NOT NULL,
    credit_limit REAL NOT NULL,
    status TEXT NOT NULL,
    address_city TEXT,
    address_country TEXT,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    operation TEXT NOT NULL, -- INSERT, UPDATE, DELETE
    event_id TEXT NOT NULL,
    event_timestamp TEXT NOT NULL,
    sequence_number INTEGER NOT NULL,
    valid_from TEXT NOT NULL,
    valid_to TEXT,           -- NULL indicates current effective version
    is_current INTEGER NOT NULL DEFAULT 1,
    is_out_of_order INTEGER NOT NULL DEFAULT 0,
    pipeline_run_id TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    FOREIGN KEY(pipeline_run_id) REFERENCES pipeline_runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_cust_hist_lookup ON dim_customers_history(customer_id, valid_from, valid_to);
CREATE INDEX IF NOT EXISTS idx_cust_hist_current ON dim_customers_history(customer_id, is_current);

-- --------------------------------------------------------------------
-- 6. Orders Fact (Current State)
-- --------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fct_orders_current (
    order_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    order_amount REAL NOT NULL,
    order_status TEXT NOT NULL,
    currency TEXT NOT NULL,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    last_event_id TEXT NOT NULL,
    last_event_timestamp TEXT NOT NULL,
    last_sequence_number INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(customer_id) REFERENCES dim_customers_current(customer_id)
);

CREATE INDEX IF NOT EXISTS idx_orders_current_customer ON fct_orders_current(customer_id);

-- --------------------------------------------------------------------
-- 7. Orders Fact History (Auditable History)
-- --------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fct_orders_history (
    history_id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    order_amount REAL NOT NULL,
    order_status TEXT NOT NULL,
    currency TEXT NOT NULL,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    operation TEXT NOT NULL,
    event_id TEXT NOT NULL,
    event_timestamp TEXT NOT NULL,
    sequence_number INTEGER NOT NULL,
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    is_current INTEGER NOT NULL DEFAULT 1,
    is_out_of_order INTEGER NOT NULL DEFAULT 0,
    pipeline_run_id TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    FOREIGN KEY(pipeline_run_id) REFERENCES pipeline_runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_orders_hist_lookup ON fct_orders_history(order_id, valid_from, valid_to);

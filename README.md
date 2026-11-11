# Change Data Capture (CDC) Ingestion & Auditable History Platform

A high-performance, production-grade Data Engineering solution for processing Change Data Capture (CDC) streams (`INSERT`, `UPDATE`, `DELETE`) into an authoritative current-state table while preserving an immutable, queryable Slowly Changing Dimension (SCD Type 2) history. 

Designed with robust **deduplication**, **out-of-order event sequencing**, **referential integrity enforcement**, an **explicit Dead-Letter Queue (DLQ / Quarantine)**, **idempotency guarantees**, and **automated reconciliation audits**.

---

## 1. Project Architecture (3-Tier Folder Layout)

```
c:\CandidateWorkspace\
├── frontend/                          # Operational Dashboard & UI
│   ├── index.html                     # Responsive single-page web console
│   ├── app.js                         # Dynamic state & API controller
│   ├── styles.css                     # Modern dark-theme operations UI
│   └── package.json                   # UI metadata & scripts
├── backend/                           # Core Pipeline & API Layer
│   ├── config.py                      # Configurable paths & environment variables
│   ├── main.py                        # Central CLI application entrypoint
│   ├── models/                        # Pydantic schemas (CDCEnvelope, Domain, Metrics)
│   ├── validation/                    # Schema, business-rule & referential integrity validators
│   ├── transformation/                # CDC Engine, Deduplication, SCD2, & Out-of-Order sequencer
│   ├── storage/                       # Database repository & ACID transaction manager
│   ├── ingestion/                     # Chunked batch pipeline runner & metrics logger
│   ├── generator/                     # Reproducible synthetic dataset generator (Seed: 42)
│   ├── reconciliation/                # Mathematical balance reconciler & invariant auditor
│   ├── api/                           # FastAPI REST routes & static UI server
│   └── tests/                         # Comprehensive pytest test suite (13 test scenarios)
├── database/                          # Storage & Schema Layer
│   ├── schema.sql                     # Full DDL for SQLite / PostgreSQL
│   ├── data_dictionary.md             # Detailed schema, grain, nullability & business rules
│   ├── reconciliation_queries.sql     # Verification & balance audit queries
│   ├── sample_queries.sql             # Consumer time-travel & analytical queries
│   └── cdc_pipeline.db                # Auto-generated SQLite database
├── sample_data/                       # Reproducible Datasets
│   ├── starter_sample.json            # Curated starter batch with deliberate edge cases
│   └── scalable_sample_*.json         # Configurable scalable datasets (up to 100k+)
├── scripts/                           # Standalone Utility Scripts
│   ├── run_pipeline.py                # Batch ingestion runner
│   ├── run_generator.py               # Data generator CLI
│   ├── run_reconciliation.py          # Standalone reconciliation audit
│   ├── run_benchmark.py               # Performance throughput benchmark
│   └── start_server.py                # Dashboard & API server runner
├── .vscode/                           # Native VS Code Automation
│   ├── settings.json                  # Python interpreter & pytest configuration
│   ├── launch.json                    # 5 one-click F5 Run/Debug configurations
│   └── tasks.json                     # VS Code build and test tasks
├── run_all.bat                        # One-click Windows end-to-end demo script
├── run_tests.bat                      # One-click automated test runner
├── start_dashboard.bat                # One-click server launcher with browser launch
├── requirements.txt                   # Python dependencies
└── README.md                          # Comprehensive solution documentation
```

---

## 2. Architecture & Data Flow Diagram

```
                 +---------------------------------------+
                 |  CDC Source Stream / Batch Files      |
                 |  (JSON / JSONL / API Payloads)        |
                 +-------------------+-------------------+
                                     |
                                     v
                       [ 1. Ingestion Layer ]
                   (Reads batch, assigns run_id,
                    computes SHA-256 fingerprint)
                                     |
                                     v
                  [ 2. Gatekeeper & Validator ]
             Does envelope / business rules / FK pass?
                  /                             \
            NO   /                               \  YES
                v                                 v
   +------------------------+      [ 3. Idempotency Check ]
   |  Quarantine / DLQ      |      Is event_id already processed?
   |  (quarantine_records)  |             /              \
   |  - Error code & reason |       YES  /                \  NO
   |  - Original raw JSON   |           v                  v
   |  - Traceable for retry |    [ Skip Record ]    [ 4. Sequencing Check ]
   +------------------------+    (duplicate_count)  Is sequence_number or TS
                                                    older than current state?
                                                          /           \
                                                 YES (Late)           NO (Newer)
                                                      /                     \
                                                     v                       v
                                        +---------------------+    +--------------------+
                                        |  Audit History Only |    |  Dual Mutation:    |
                                        |  - Appends to SCD2  |    |  1. Update Current |
                                        |  - is_out_of_order=1|    |  2. Expire Old Ver |
                                        |  - Current Unchanged|    |  3. Append New Ver |
                                        +---------------------+    +--------------------+
                                                     \                       /
                                                      \                     /
                                                       v                   v
                                               +-------------------------------+
                                               |  Target Storage Layer         |
                                               |  - dim_customers_current      |
                                               |  - dim_customers_history      |
                                               |  - fct_orders_current         |
                                               |  - processed_events (Ledger)  |
                                               |  - pipeline_runs (Metrics)    |
                                               +-------------------------------+
```

---

## 3. Quick Start & Execution Instructions

### Option A: One-Click Demo in VS Code
1. Open this workspace in **VS Code**: `File` &rarr; `Open Folder` &rarr; `C:\CandidateWorkspace`.
2. Press **`F5`** or go to `Run and Debug` tab. Select:
   - **`1. Run CDC Backend & Dashboard (FastAPI)`** &rarr; starts the server and serves the dashboard on `http://localhost:8000`.
   - **`2. Run All Automated Tests (pytest)`** &rarr; runs the 13 automated test scenarios.
   - **`3. Run Batch Ingestion (Starter Sample)`** &rarr; ingests sample events into the database.
   - **`4. Run Reconciliation Audit Report`** &rarr; prints mathematical verification report.
   - **`5. Run Performance Benchmark (10k Records)`** &rarr; tests throughput.

### Option B: Windows Command Prompt / Double-Click
- Run **`run_all.bat`**: Executes initialization, starter generation, ingestion, reconciliation, and automated tests sequentially.
- Run **`run_tests.bat`**: Executes the pytest test suite.
- Run **`start_dashboard.bat`**: Starts the FastAPI server and launches `http://localhost:8000` in your browser.

### Option C: Terminal CLI
```powershell
# 1. Initialize Database Schema
python backend/main.py --init-db

# 2. Generate Starter Sample Dataset (Seed: 42)
python backend/main.py --generate-starter

# 3. Ingest Batch File
python backend/main.py --run-batch sample_data/starter_sample.json

# 4. Verify Reconciliation & Invariant Checks
python backend/main.py --reconcile

# 5. Run Automated Pytest Suite
python -m pytest backend/tests -v

# 6. Start API & Dashboard Server
python backend/main.py --serve
```

---

## 4. Key Design Decisions & Business Rules

### 4.1. Entity Grain & Models
1. **Customer Dimension (`dim_customers_current` & `dim_customers_history`)**:
   - Grain: One row per customer in current state; one row per mutation version in history.
   - Natural Key: `customer_id` (e.g. `CUST-1001`).
   - Monotonic Sequencing: Every entity mutation carries a strictly increasing `sequence_number` and ISO-8601 `event_timestamp`.
2. **Orders Fact (`fct_orders_current` & `fct_orders_history`)**:
   - Grain: One row per order in current state; one row per lifecycle status change in history.
   - Natural Key: `order_id` (e.g. `ORD-5001`).
   - Referential Integrity: Requires a valid, active `customer_id` in `dim_customers_current`.
3. **Quarantine Dead-Letter Queue (`quarantine_records`)**:
   - Stores unprocessable records with `error_code`, `error_message`, `raw_payload`, and `status`. Supports post-correction retry/replay.
4. **Idempotency Ledger (`processed_events`)**:
   - Primary key on `event_id`. Ensures replay of identical events produces zero duplicate mutations.

### 4.2. Handling Out-of-Order / Late-Arriving Events
When an event arrives whose `sequence_number < current.last_sequence_number` (or identical sequence with earlier timestamp):
1. **Current State Protection**: The current-state table is **not overwritten**, preserving the latest known state.
2. **Audit Preservation**: The late-arriving event is appended to the SCD Type 2 history table with `is_out_of_order = 1`, `is_current = 0`, and `valid_to = current.last_event_timestamp`.
3. **Metric Tracking**: Increments `out_of_order_count` in the pipeline run metrics.

### 4.3. Idempotency & Batch Re-Runs
- Running the exact same batch multiple times (e.g. after network disconnect or worker restart):
  - Previously processed event IDs match the `processed_events` ledger.
  - The pipeline skips mutation, increments `duplicate_count`, and creates **0 duplicate rows** in current or history tables.

### 4.4. Referential Integrity & Quarantine Retry
- An order arriving for a non-existent customer (or soft-deleted customer) is quarantined with `REFERENTIAL_INTEGRITY_VIOLATION`.
- Once the parent customer is ingested, the pipeline operator can invoke `POST /api/quarantine/retry`. The engine replays the quarantined record, resolving it into active current-state tables.

---

## 5. Automated Reconciliation & Invariant Proof

The pipeline validates data correctness using mathematical balance equations and relational invariant assertions:

### Mathematical Balance Equation
$$\text{Total Source Input} = \text{Inserted} + \text{Updated} + \text{Deleted} + \text{Duplicates} + \text{Out-of-Order} + \text{Quarantined}$$

### Real Ingestion Execution Evidence (38 Starter Events)
```
======================================================================
DATA PIPELINE RECONCILIATION & QUALITY AUDIT REPORT
======================================================================
Audit Timestamp:               2026-11-11T06:37:22.291795+00:00
Pipeline Runs Evaluated:       1
Mathematical Balance Status:   PASSED (All runs reconciled)
----------------------------------------------------------------------
VOLUME RECONCILIATION SUMMARY:
  Total Source Input Events:   38
  Successful State Mutations:  29  (24 Inserts + 4 Updates + 1 Delete)
  Deduplicated Events (Skips): 1
  Quarantined (DLQ) Records:   7   (Deliberate negative edge cases)
  Out-of-Order History Events: 1   (Late-arriving version 2)
----------------------------------------------------------------------
DATA INTEGRITY INVARIANTS:
  Duplicate PKs Detected:      0 (Expected: 0)
  SCD2 Active Version Issues:  0 (Expected: 0)
  Referential Integrity Flaws: 0 (Expected: 0)
----------------------------------------------------------------------
TARGET CURRENT ENTITY POPULATIONS:
  Active Customers in Current: 9
  Active Orders in Current:    14
======================================================================
```

---

## 6. Automated Test Suite (13 Test Scenarios)

The automated test suite in `backend/tests/` covers all required positive and negative scenarios:

| Test File | Test Case | Scenario Verified | Status |
| :--- | :--- | :--- | :--- |
| `test_happy_path.py` | `test_customer_insert_update_delete_scd2` | Full SCD2 lifecycle: INSERT &rarr; UPDATE &rarr; DELETE | **PASSED** |
| `test_happy_path.py` | `test_order_insert_and_update` | Valid order placement and status update | **PASSED** |
| `test_duplicates_and_idempotency.py` | `test_duplicate_events_in_same_batch` | Duplicate event IDs in same batch skipped cleanly | **PASSED** |
| `test_duplicates_and_idempotency.py` | `test_idempotent_rerun_of_entire_batch` | Re-running exact batch causes 0 mutations & 100% duplicate skips | **PASSED** |
| `test_out_of_order.py` | `test_late_arriving_event` | Late version does not regress current state; preserved in history | **PASSED** |
| `test_validation_and_quarantine.py` | `test_empty_batch_handling` | Ingesting empty batch succeeds with 0 events | **PASSED** |
| `test_validation_and_quarantine.py` | `test_malformed_input_quarantined` | Unparseable JSON and invalid structures routed to DLQ | **PASSED** |
| `test_validation_and_quarantine.py` | `test_missing_required_fields` | Missing name, invalid email, negative credit routed to DLQ | **PASSED** |
| `test_validation_and_quarantine.py` | `test_partial_failure_isolation` | Valid events succeed while invalid events quarantine | **PASSED** |
| `test_referential_integrity.py` | `test_orphan_order_quarantined` | Order referencing nonexistent customer rejected | **PASSED** |
| `test_referential_integrity.py` | `test_quarantine_retry_flow` | Quarantined order resolves once customer arrives | **PASSED** |
| `test_reconciliation.py` | `test_automated_reconciliation_balance` | Balance equation and invariant checks validated | **PASSED** |
| `test_performance_benchmark.py` | `test_pipeline_throughput_benchmark` | 5,000+ records processed at high throughput | **PASSED** |

---

## 7. Performance Benchmarks & Optimization

### Measured Benchmark (10,000 Synthetic Events)
- **Environment**: Local Windows SQLite in WAL mode, chunked transactions (1,000 events/commit).
- **Wall-Clock Duration**: **1.016 seconds**
- **Throughput**: **9,843.8 events / second**

### Optimization Applied:
1. **SQLite Write-Ahead Logging (`PRAGMA journal_mode = WAL`)**: Decouples readers from writers, eliminating disk write synchronization bottlenecks.
2. **Chunked Transaction Batching**: Events are processed inside chunked `BEGIN IMMEDIATE` / `COMMIT` blocks of 1,000 events instead of individual commits, reducing filesystem sync overhead from 10,000 fsyncs to 10 fsyncs.
3. **Compound B-Tree Indices**: Added `(customer_id, valid_from, valid_to)` and `(entity_type, entity_id)` indices to make deduplication and SCD2 version lookups $O(\log N)$.

---

## 8. Trade-offs & Limitations

1. **Storage Choice (SQLite vs Distributed Warehouse)**:
   - *Choice*: SQLite was chosen for local self-contained execution without external services (PostgreSQL/DuckDB/Kafka).
   - *Limitation*: SQLite does not support distributed concurrent writes across multiple worker nodes.
   - *Next Step*: For horizontal scalability, swap `storage/db.py` to PostgreSQL / Snowflake with a Kafka / Debezium ingestion stream.
2. **Sequence Number vs Millisecond Timestamps**:
   - In high-throughput distributed systems, clock skew can cause two events to have identical timestamps. The solution includes an explicit monotonic `sequence_number` to guarantee deterministic ordering.
3. **Quarantine Lifecycle**:
   - Quarantined records can be retried in-place via API. For production at enterprise scale, a dedicated quarantine dead-letter topic with automated schema-drift detection is recommended.
"# CandidateWorkspace" 



one of the main point in this github i have not uploaded on file due to its database size is large and i.e is  "cdc_pipeline.db" to refer this file or project folder it is in link it will be avalable alter here

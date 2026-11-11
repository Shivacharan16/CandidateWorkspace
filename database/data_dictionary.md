# Data Dictionary & Entity Relationship Specification

## 1. Overview & Architecture Context
This data dictionary details the tables, schemas, constraints, and audit conventions for the Change Data Capture (CDC) ingestion pipeline. The system ingests CDC streams representing entity mutations (`INSERT`, `UPDATE`, `DELETE`), updates the authoritative current-state table (`*_current`), and appends to an immutable, auditable history table (`*_history`).

---

## 2. Entity Grain & Key Summary

| Table | Entity Grain | Primary Key | Foreign Keys | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| `dim_customers_current` | One row per customer | `customer_id` | None | Fast lookup of the latest active customer state |
| `dim_customers_history` | One row per state change version | `history_id` | `pipeline_run_id` | SCD Type 2 audit timeline and time-travel queries |
| `fct_orders_current` | One row per order | `order_id` | `customer_id` | Authoritative current state of sales orders |
| `fct_orders_history` | One row per order state change | `history_id` | `pipeline_run_id` | Full audit trail of order transitions |
| `quarantine_records` | One row per rejected event | `quarantine_id` | `pipeline_run_id` | Dead-letter queue (DLQ) storing unprocessable records |
| `processed_events` | One row per ingested event ID | `event_id` | `pipeline_run_id` | Idempotency log guaranteeing deduplication |
| `pipeline_runs` | One row per pipeline execution | `run_id` | None | Observability, metrics, duration, and status tracking |

---

## 3. Entity Definitions

### 3.1. `dim_customers_current`
Represents the latest state of an individual customer.

| Column | Type | Nullable | Default | Description & Business Rules |
| :--- | :--- | :--- | :--- | :--- |
| `customer_id` | `TEXT` | **NO** | PK | Unique deterministic customer identifier (e.g. `CUST-1001`). |
| `name` | `TEXT` | **NO** | - | Full customer legal name. Must not be empty. |
| `email` | `TEXT` | **NO** | - | Valid RFC 5322 email string. |
| `tier` | `TEXT` | **NO** | - | Enum: `STANDARD`, `SILVER`, `GOLD`, `PLATINUM`. |
| `credit_limit` | `REAL` | **NO** | - | Monetary limit; must be `>= 0.00`. |
| `status` | `TEXT` | **NO** | - | Customer account status: `ACTIVE`, `SUSPENDED`, `DELETED`. |
| `address_city` | `TEXT` | YES | NULL | Customer billing city. |
| `address_country` | `TEXT` | YES | NULL | ISO country code or full name. |
| `is_deleted` | `INTEGER` | **NO** | 0 | Soft delete flag (1 = soft deleted, 0 = active). |
| `last_event_id` | `TEXT` | **NO** | - | Unique ID of the latest event that updated this record. |
| `last_event_timestamp` | `TEXT` | **NO** | - | ISO-8601 timestamp of latest accepted change. |
| `last_sequence_number`| `INTEGER`| **NO** | - | Monotonic sequence number used to reject stale out-of-order mutations. |
| `created_at` | `TEXT` | **NO** | - | Ingestion timestamp of the initial `INSERT` event. |
| `updated_at` | `TEXT` | **NO** | - | Ingestion timestamp of the latest applied modification. |

---

### 3.2. `dim_customers_history`
Preserves an immutable Slowly Changing Dimension (SCD Type 2) history of every state mutation.

| Column | Type | Nullable | Description & Business Rules |
| :--- | :--- | :--- | :--- |
| `history_id` | `INTEGER` | **NO** (PK) | Auto-incrementing surrogate primary key. |
| `customer_id` | `TEXT` | **NO** | Natural business key of customer. |
| `name`, `email`, `tier`, `credit_limit`, `status`, `address_city`, `address_country`, `is_deleted` | - | - | Snapshot of attributes at the time of change. |
| `operation` | `TEXT` | **NO** | CDC Operation: `INSERT`, `UPDATE`, `DELETE`. |
| `event_id` | `TEXT` | **NO** | Event ID from source payload that produced this historical record. |
| `event_timestamp` | `TEXT` | **NO** | Time the event happened at source (ISO-8601). |
| `sequence_number` | `INTEGER` | **NO** | Monotonic ordering key. |
| `valid_from` | `TEXT` | **NO** | ISO-8601 effective start timestamp of this version. |
| `valid_to` | `TEXT` | YES | ISO-8601 expiration timestamp (NULL indicates active/latest version). |
| `is_current` | `INTEGER` | **NO** | Flag: 1 if this version is currently active, 0 otherwise. |
| `is_out_of_order` | `INTEGER` | **NO** | Flag: 1 if event arrived out-of-order (older than current state). |
| `pipeline_run_id` | `TEXT` | **NO** | Foreign key to `pipeline_runs(run_id)`. |
| `recorded_at` | `TEXT` | **NO** | Processing pipeline clock timestamp. |

---

### 3.3. `fct_orders_current` & `fct_orders_history`
Captures orders placed by customers. Demonstrates referential integrity rules.

- **Referential Integrity Rule**: An order cannot be ingested if its `customer_id` is missing or refers to a nonexistent customer in `dim_customers_current`. Any order event with an unresolvable customer reference is quarantined with `REFERENTIAL_INTEGRITY_VIOLATION`.
- **Order Status Values**: `PENDING`, `CONFIRMED`, `SHIPPED`, `CANCELLED`, `REFUNDED`.
- **Amount Constraint**: `order_amount > 0`.

---

### 3.4. `quarantine_records` (Dead-Letter Queue / DLQ)
Stores all malformed, unauthorized, schema-violating, or orphan events.

| Column | Type | Description |
| :--- | :--- | :--- |
| `quarantine_id` | `INTEGER` PK | Unique surrogate key. |
| `pipeline_run_id` | `TEXT` | Execution batch that encountered the reject. |
| `event_id` | `TEXT` | Extracted event ID (or NULL if JSON unparseable). |
| `entity_type` | `TEXT` | Entity class (`CUSTOMER` or `ORDER`). |
| `entity_id` | `TEXT` | Extracted entity identifier. |
| `error_code` | `TEXT` | Categorical classification: `INVALID_SCHEMA`, `MISSING_REQUIRED_FIELD`, `REFERENTIAL_INTEGRITY_VIOLATION`, `MALFORMED_JSON`, `BUSINESS_RULE_VIOLATION`. |
| `error_message` | `TEXT` | Human-readable root cause explanation. |
| `raw_payload` | `TEXT` | Complete raw JSON or string input for auditing and replay. |
| `quarantined_at` | `TEXT` | Timestamp when the record was rejected. |
| `retry_count` | `INTEGER` | Times this quarantine item has been re-evaluated. |
| `status` | `TEXT` | Quarantine lifecycle state: `NEW`, `RETRIED`, `RESOLVED`, `DISCARDED`. |

---

### 3.5. `processed_events` (Idempotency Ledger)
Maintains unique record of all processed event IDs and cryptographic hash of payloads.
- **Uniqueness**: `event_id` is unique primary key.
- **Re-run behavior**: If a batch containing an already-processed `event_id` is re-run, the pipeline detects the duplicate in the ledger and marks it as an idempotent skip, incrementing `duplicate_count` without modifying target state.

---

### 3.6. `pipeline_runs` (Observability & Metrics)
Tracks every execution batch end-to-end.
- Records exact counts: `total_events`, `inserted_count`, `updated_count`, `deleted_count`, `duplicate_count`, `quarantined_count`, `out_of_order_count`.
- Records operational duration: `started_at`, `completed_at`, `duration_ms`.
- Records status: `RUNNING`, `SUCCESS`, `PARTIAL_SUCCESS`, `FAILED`.

---

## 4. Referential Integrity & Validation Rules Matrix

| Rule ID | Check Type | Trigger Condition | Pipeline Action |
| :--- | :--- | :--- | :--- |
| **BR-01** | Schema Validation | Missing `event_id`, `entity_type`, `operation`, `event_timestamp` | Reject to `quarantine_records` (`INVALID_SCHEMA`) |
| **BR-02** | Payload Integrity | Customer missing `name` or `email`, or invalid email format | Reject to `quarantine_records` (`MISSING_REQUIRED_FIELD` / `INVALID_EMAIL`) |
| **BR-03** | Domain Constraint | Customer `credit_limit < 0` or Order `order_amount <= 0` | Reject to `quarantine_records` (`BUSINESS_RULE_VIOLATION`) |
| **BR-04** | Deduplication | `event_id` already present in `processed_events` | Skip cleanly, increment run `duplicate_count` |
| **BR-05** | Out-of-Order | Event timestamp/seq is older than current state record | Append to `history` (with `is_out_of_order = 1`), skip updating `current` table |
| **BR-06** | Referential Integrity | Order `customer_id` not found in `dim_customers_current` | Reject to `quarantine_records` (`REFERENTIAL_INTEGRITY_VIOLATION`) |
| **BR-07** | Deletion | Operation is `DELETE` | Mark `is_deleted = 1` in current table, expire previous history record, record `DELETE` in history |

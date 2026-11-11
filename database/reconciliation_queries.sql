-- ====================================================================
-- Reconciliation & Data Integrity Validation Queries
-- Used for automated verification and audit reporting
-- ====================================================================

-- --------------------------------------------------------------------
-- 1. Reconciliation Equation Check
-- Total Input = (Unique Ingested Events) + (Quarantined Records) + (Idempotent Duplicates)
-- --------------------------------------------------------------------
SELECT 
    pr.run_id,
    pr.batch_name,
    pr.total_events AS reported_total_input,
    pr.inserted_count + pr.updated_count + pr.deleted_count AS successful_mutations,
    pr.duplicate_count AS deduplicated_events,
    pr.quarantined_count AS rejected_quarantined,
    pr.out_of_order_count AS out_of_order_events,
    (pr.inserted_count + pr.updated_count + pr.deleted_count + pr.duplicate_count + pr.quarantined_count + pr.out_of_order_count) AS reconciled_sum,
    CASE 
        WHEN pr.total_events = (pr.inserted_count + pr.updated_count + pr.deleted_count + pr.duplicate_count + pr.quarantined_count + pr.out_of_order_count)
        THEN 'BALANCED'
        ELSE 'DISCREPANCY_DETECTED'
    END AS reconciliation_status
FROM pipeline_runs pr
ORDER BY pr.started_at DESC;

-- --------------------------------------------------------------------
-- 2. Customer Current-State Uniqueness & Null Integrity Check
-- Ensures no duplicate customer_id exists in current state table
-- --------------------------------------------------------------------
SELECT 
    customer_id, 
    COUNT(*) AS count_instances
FROM dim_customers_current
GROUP BY customer_id
HAVING COUNT(*) > 1;

-- --------------------------------------------------------------------
-- 3. Customer SCD Type 2 Active Record Invariant
-- Exactly one active record (is_current = 1, valid_to IS NULL) per entity
-- --------------------------------------------------------------------
SELECT 
    customer_id,
    SUM(CASE WHEN is_current = 1 THEN 1 ELSE 0 END) AS active_record_count,
    SUM(CASE WHEN valid_to IS NULL THEN 1 ELSE 0 END) AS open_valid_to_count
FROM dim_customers_history
GROUP BY customer_id
HAVING active_record_count > 1 OR open_valid_to_count > 1;

-- --------------------------------------------------------------------
-- 4. Current State vs History Alignment
-- Current state attributes must match the is_current = 1 history record
-- --------------------------------------------------------------------
SELECT 
    c.customer_id,
    c.tier AS current_tier,
    h.tier AS history_tier,
    c.status AS current_status,
    h.status AS history_status,
    c.last_event_timestamp,
    h.event_timestamp AS history_event_timestamp
FROM dim_customers_current c
JOIN dim_customers_history h 
    ON c.customer_id = h.customer_id 
   AND h.is_current = 1
WHERE c.tier != h.tier 
   OR c.status != h.status 
   OR c.last_event_timestamp != h.event_timestamp;

-- --------------------------------------------------------------------
-- 5. Referential Integrity Audit
-- Ensures every current order links to an existing customer
-- --------------------------------------------------------------------
SELECT 
    o.order_id,
    o.customer_id,
    o.order_amount,
    o.order_status
FROM fct_orders_current o
LEFT JOIN dim_customers_current c 
    ON o.customer_id = c.customer_id
WHERE c.customer_id IS NULL;

-- --------------------------------------------------------------------
-- 6. Quarantine Analysis by Error Code
-- Summarizes why events were rejected across all pipeline runs
-- --------------------------------------------------------------------
SELECT 
    error_code,
    COUNT(*) AS reject_count,
    MIN(quarantined_at) AS first_seen,
    MAX(quarantined_at) AS last_seen
FROM quarantine_records
GROUP BY error_code
ORDER BY reject_count DESC;

-- --------------------------------------------------------------------
-- 7. Out-of-Order Events Audit
-- Confirms that out-of-order events are preserved in history with flag
-- --------------------------------------------------------------------
SELECT 
    customer_id,
    history_id,
    operation,
    event_id,
    event_timestamp,
    sequence_number,
    recorded_at,
    is_out_of_order
FROM dim_customers_history
WHERE is_out_of_order = 1
ORDER BY customer_id, event_timestamp;

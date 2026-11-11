-- ====================================================================
-- Sample Analytical Queries for Data Consumers
-- Demonstrates Current State & Historical Time-Travel Analysis
-- ====================================================================

-- --------------------------------------------------------------------
-- 1. Current Active Customers by Tier with Total Credit Capacity
-- --------------------------------------------------------------------
SELECT 
    tier,
    COUNT(*) AS total_customers,
    ROUND(SUM(credit_limit), 2) AS total_credit_limit,
    ROUND(AVG(credit_limit), 2) AS avg_credit_limit
FROM dim_customers_current
WHERE is_deleted = 0 AND status = 'ACTIVE'
GROUP BY tier
ORDER BY total_credit_limit DESC;

-- --------------------------------------------------------------------
-- 2. Time-Travel Query: Customer State as of a Specific Timestamp
-- Replace '2026-03-01T12:00:00Z' with target point-in-time
-- --------------------------------------------------------------------
SELECT 
    customer_id,
    name,
    email,
    tier,
    credit_limit,
    status,
    valid_from,
    valid_to
FROM dim_customers_history
WHERE valid_from <= '2026-03-01T12:00:00Z'
  AND (valid_to IS NULL OR valid_to > '2026-03-01T12:00:00Z');

-- --------------------------------------------------------------------
-- 3. Customer Lifecycle / Audit Trail for a Specific Customer
-- --------------------------------------------------------------------
SELECT 
    sequence_number,
    operation,
    valid_from,
    valid_to,
    tier,
    credit_limit,
    status,
    is_current,
    is_out_of_order,
    event_timestamp,
    recorded_at
FROM dim_customers_history
WHERE customer_id = 'CUST-1001'
ORDER BY sequence_number ASC, event_timestamp ASC;

-- --------------------------------------------------------------------
-- 4. Order Revenue by Current Customer Tier
-- --------------------------------------------------------------------
SELECT 
    c.tier,
    COUNT(o.order_id) AS total_orders,
    ROUND(SUM(o.order_amount), 2) AS total_revenue,
    ROUND(AVG(o.order_amount), 2) AS avg_order_value
FROM fct_orders_current o
JOIN dim_customers_current c ON o.customer_id = c.customer_id
WHERE o.is_deleted = 0 AND c.is_deleted = 0
GROUP BY c.tier
ORDER BY total_revenue DESC;

-- --------------------------------------------------------------------
-- 5. Dead-Letter Queue (DLQ) Operational Review
-- Shows the 20 most recent quarantined events with error details
-- --------------------------------------------------------------------
SELECT 
    quarantine_id,
    pipeline_run_id,
    event_id,
    entity_type,
    entity_id,
    error_code,
    error_message,
    quarantined_at,
    status
FROM quarantine_records
ORDER BY quarantine_id DESC
LIMIT 20;

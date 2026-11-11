import json
from datetime import datetime, timezone
from backend.models.metrics import RunStatus
from backend.transformation.cdc_engine import CDCEngine, ProcessingResult

def test_order_referencing_nonexistent_customer_is_quarantined(temp_db):
    pipeline = temp_db["pipeline"]
    repo = temp_db["repo"]

    orphan_order = {
        "event_id": "evt_ord_orphan",
        "entity_type": "ORDER",
        "entity_id": "ORD-ORPHAN-1",
        "operation": "INSERT",
        "event_timestamp": "2026-03-01T10:00:00Z",
        "sequence_number": 1,
        "payload": {
            "order_id": "ORD-ORPHAN-1",
            "customer_id": "CUST-NONEXISTENT",
            "order_amount": 199.99,
            "order_status": "PENDING",
            "currency": "USD"
        }
    }

    metrics = pipeline.run([orphan_order], batch_name="orphan_order_batch")
    assert metrics.quarantined_count == 1
    assert metrics.inserted_count == 0

    quarantine = repo.list_quarantine(run_id=metrics.run_id)
    assert len(quarantine) == 1
    assert quarantine[0]["error_code"] == "REFERENTIAL_INTEGRITY_VIOLATION"

    # Ensure order does NOT exist in target tables
    assert repo.get_order_current("ORD-ORPHAN-1") is None


def test_quarantine_retry_flow(temp_db):
    """
    Simulates out-of-order parent/child event ingestion:
    1. Order arrives BEFORE its Customer -> Quarantined with REFERENTIAL_INTEGRITY_VIOLATION
    2. Customer arrives later -> Ingested successfully
    3. Retry Quarantined Order -> Resolves successfully and populates fct_orders_current!
    """
    pipeline = temp_db["pipeline"]
    repo = temp_db["repo"]
    engine = CDCEngine(repo)

    # 1. Order arrives first
    early_order = {
        "event_id": "evt_ord_early",
        "entity_type": "ORDER",
        "entity_id": "ORD-EARLY-1",
        "operation": "INSERT",
        "event_timestamp": "2026-03-01T10:00:00Z",
        "sequence_number": 1,
        "payload": {
            "order_id": "ORD-EARLY-1",
            "customer_id": "CUST-FUTURE-1",
            "order_amount": 349.50,
            "order_status": "CONFIRMED",
            "currency": "USD"
        }
    }
    m1 = pipeline.run([early_order], batch_name="early_order_run")
    assert m1.quarantined_count == 1
    assert repo.get_order_current("ORD-EARLY-1") is None

    # 2. Customer arrives
    late_cust = {
        "event_id": "evt_cust_future",
        "entity_type": "CUSTOMER",
        "entity_id": "CUST-FUTURE-1",
        "operation": "INSERT",
        "event_timestamp": "2026-03-01T10:30:00Z",
        "sequence_number": 1,
        "payload": {
            "customer_id": "CUST-FUTURE-1",
            "name": "Future Customer",
            "email": "future@example.com",
            "tier": "GOLD",
            "credit_limit": 10000.0,
            "status": "ACTIVE"
        }
    }
    m2 = pipeline.run([late_cust], batch_name="late_cust_run")
    assert m2.inserted_count == 1

    # 3. Retry the quarantined record
    quarantined_records = repo.list_quarantine(status="NEW")
    assert len(quarantined_records) == 1
    q_item = quarantined_records[0]

    raw_event = json.loads(q_item["raw_payload"])
    retry_metrics = pipeline.run([raw_event], batch_name="retry_batch_1")
    assert retry_metrics.inserted_count == 1

    repo.update_quarantine_status(q_item["quarantine_id"], status="RESOLVED", retry_count=1)

    # Verify order is now active in target table!
    curr_order = repo.get_order_current("ORD-EARLY-1")
    assert curr_order is not None
    assert curr_order["customer_id"] == "CUST-FUTURE-1"
    assert curr_order["order_amount"] == 349.50

from backend.models.metrics import RunStatus

def test_customer_insert_update_delete_scd2_lifecycle(temp_db):
    pipeline = temp_db["pipeline"]
    repo = temp_db["repo"]

    events = [
        # 1. Insert customer
        {
            "event_id": "evt_c1_v1",
            "entity_type": "CUSTOMER",
            "entity_id": "CUST-100",
            "operation": "INSERT",
            "event_timestamp": "2026-03-01T10:00:00Z",
            "sequence_number": 1,
            "payload": {
                "customer_id": "CUST-100",
                "name": "Sarah Connor",
                "email": "sarah@resistance.org",
                "tier": "STANDARD",
                "credit_limit": 5000.0,
                "status": "ACTIVE"
            }
        },
        # 2. Update customer tier & credit limit
        {
            "event_id": "evt_c1_v2",
            "entity_type": "CUSTOMER",
            "entity_id": "CUST-100",
            "operation": "UPDATE",
            "event_timestamp": "2026-03-01T11:00:00Z",
            "sequence_number": 2,
            "payload": {
                "name": "Sarah Connor",
                "email": "sarah@resistance.org",
                "tier": "PLATINUM",
                "credit_limit": 50000.0,
                "status": "ACTIVE"
            }
        },
        # 3. Soft Delete customer
        {
            "event_id": "evt_c1_v3",
            "entity_type": "CUSTOMER",
            "entity_id": "CUST-100",
            "operation": "DELETE",
            "event_timestamp": "2026-03-01T12:00:00Z",
            "sequence_number": 3,
            "payload": {}
        }
    ]

    metrics = pipeline.run(events, batch_name="happy_path_batch")
    assert metrics.status == RunStatus.SUCCESS
    assert metrics.total_events == 3
    assert metrics.inserted_count == 1
    assert metrics.updated_count == 1
    assert metrics.deleted_count == 1

    # Verify Current State Table
    current = repo.get_customer_current("CUST-100")
    assert current is not None
    assert current["is_deleted"] == 1
    assert current["status"] == "DELETED"
    assert current["last_sequence_number"] == 3
    assert current["last_event_id"] == "evt_c1_v3"

    # Verify SCD Type 2 History Table
    history = repo.get_customer_history("CUST-100")
    assert len(history) == 3

    # Version 1 (Initial Insert): expired by v2
    v1 = history[0]
    assert v1["sequence_number"] == 1
    assert v1["operation"] == "INSERT"
    assert v1["tier"] == "STANDARD"
    assert v1["valid_to"] == "2026-03-01T11:00:00Z"
    assert v1["is_current"] == 0

    # Version 2 (Update): expired by v3
    v2 = history[1]
    assert v2["sequence_number"] == 2
    assert v2["operation"] == "UPDATE"
    assert v2["tier"] == "PLATINUM"
    assert v2["valid_to"] == "2026-03-01T12:00:00Z"
    assert v2["is_current"] == 0

    # Version 3 (Delete): current effective state
    v3 = history[2]
    assert v3["sequence_number"] == 3
    assert v3["operation"] == "DELETE"
    assert v3["is_deleted"] == 1
    assert v3["valid_to"] is None
    assert v3["is_current"] == 1


def test_order_insert_and_update(temp_db):
    pipeline = temp_db["pipeline"]
    repo = temp_db["repo"]

    # First insert active customer
    cust_event = {
        "event_id": "evt_c2_v1",
        "entity_type": "CUSTOMER",
        "entity_id": "CUST-200",
        "operation": "INSERT",
        "event_timestamp": "2026-03-01T10:00:00Z",
        "sequence_number": 1,
        "payload": {
            "customer_id": "CUST-200",
            "name": "John Doe",
            "email": "john.doe@example.com",
            "tier": "GOLD",
            "credit_limit": 10000.0,
            "status": "ACTIVE"
        }
    }
    pipeline.run([cust_event], batch_name="cust_prep")

    # Now insert and update order
    order_events = [
        {
            "event_id": "evt_ord1_v1",
            "entity_type": "ORDER",
            "entity_id": "ORD-101",
            "operation": "INSERT",
            "event_timestamp": "2026-03-01T10:30:00Z",
            "sequence_number": 1,
            "payload": {
                "order_id": "ORD-101",
                "customer_id": "CUST-200",
                "order_amount": 250.75,
                "order_status": "PENDING",
                "currency": "USD"
            }
        },
        {
            "event_id": "evt_ord1_v2",
            "entity_type": "ORDER",
            "entity_id": "ORD-101",
            "operation": "UPDATE",
            "event_timestamp": "2026-03-01T11:00:00Z",
            "sequence_number": 2,
            "payload": {
                "order_id": "ORD-101",
                "customer_id": "CUST-200",
                "order_amount": 250.75,
                "order_status": "SHIPPED",
                "currency": "USD"
            }
        }
    ]

    metrics = pipeline.run(order_events, batch_name="order_batch")
    assert metrics.status == RunStatus.SUCCESS
    assert metrics.inserted_count == 1
    assert metrics.updated_count == 1

    current_order = repo.get_order_current("ORD-101")
    assert current_order["order_status"] == "SHIPPED"
    assert current_order["last_sequence_number"] == 2

    order_history = repo.get_order_history("ORD-101")
    assert len(order_history) == 2
    assert order_history[0]["order_status"] == "PENDING"
    assert order_history[0]["is_current"] == 0
    assert order_history[1]["order_status"] == "SHIPPED"
    assert order_history[1]["is_current"] == 1

from backend.models.metrics import RunStatus

def test_duplicate_events_in_same_batch(temp_db):
    pipeline = temp_db["pipeline"]
    repo = temp_db["repo"]

    event = {
        "event_id": "evt_dup_001",
        "entity_type": "CUSTOMER",
        "entity_id": "CUST-300",
        "operation": "INSERT",
        "event_timestamp": "2026-03-01T10:00:00Z",
        "sequence_number": 1,
        "payload": {
            "customer_id": "CUST-300",
            "name": "Bruce Wayne",
            "email": "bruce@wayne-enterprises.com",
            "tier": "PLATINUM",
            "credit_limit": 100000.0,
            "status": "ACTIVE"
        }
    }

    # Batch contains two identical copies with the same event_id
    metrics = pipeline.run([event, dict(event)], batch_name="duplicate_batch")

    assert metrics.status == RunStatus.SUCCESS
    assert metrics.total_events == 2
    assert metrics.inserted_count == 1
    assert metrics.duplicate_count == 1

    # Only 1 record in current state and 1 in history
    current = repo.get_customer_current("CUST-300")
    assert current is not None

    history = repo.get_customer_history("CUST-300")
    assert len(history) == 1


def test_idempotent_rerun_of_entire_batch(temp_db):
    pipeline = temp_db["pipeline"]
    repo = temp_db["repo"]

    batch = [
        {
            "event_id": f"evt_rerun_{i}",
            "entity_type": "CUSTOMER",
            "entity_id": f"CUST-40{i}",
            "operation": "INSERT",
            "event_timestamp": "2026-03-01T10:00:00Z",
            "sequence_number": 1,
            "payload": {
                "customer_id": f"CUST-40{i}",
                "name": f"User {i}",
                "email": f"user{i}@example.com",
                "tier": "STANDARD",
                "credit_limit": 1000.0 * i,
                "status": "ACTIVE"
            }
        }
        for i in range(1, 6)
    ]

    # Run 1: initial ingestion
    run1 = pipeline.run(batch, batch_name="initial_run")
    assert run1.status == RunStatus.SUCCESS
    assert run1.inserted_count == 5
    assert run1.duplicate_count == 0

    # Run 2: Exact re-run of the same batch (restart/retry scenario)
    run2 = pipeline.run(batch, batch_name="rerun_batch")
    assert run2.status == RunStatus.SUCCESS
    assert run2.total_events == 5
    assert run2.inserted_count == 0
    assert run2.duplicate_count == 5

    # Target table counts remain exactly 5
    customers = repo.list_current_customers(limit=50)
    assert len(customers) == 5

    # Each customer has exactly 1 history row
    for i in range(1, 6):
        hist = repo.get_customer_history(f"CUST-40{i}")
        assert len(hist) == 1

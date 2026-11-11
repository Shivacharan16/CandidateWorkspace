from backend.models.metrics import RunStatus

def test_empty_batch_handling(temp_db):
    pipeline = temp_db["pipeline"]
    metrics = pipeline.run([], batch_name="empty_batch")
    assert metrics.status == RunStatus.SUCCESS
    assert metrics.total_events == 0
    assert metrics.inserted_count == 0
    assert metrics.quarantined_count == 0


def test_malformed_input_quarantined(temp_db):
    pipeline = temp_db["pipeline"]
    repo = temp_db["repo"]

    bad_events = [
        "This is not a valid JSON dict",
        12345,
        {"some_random_key": "no event_id or entity_type"}
    ]

    metrics = pipeline.run(bad_events, batch_name="malformed_batch")
    assert metrics.status == RunStatus.PARTIAL_SUCCESS
    assert metrics.total_events == 3
    assert metrics.quarantined_count == 3

    quarantine = repo.list_quarantine(run_id=metrics.run_id)
    assert len(quarantine) == 3
    error_codes = {q["error_code"] for q in quarantine}
    assert "MALFORMED_INPUT" in error_codes or "INVALID_SCHEMA" in error_codes


def test_missing_required_fields_and_invalid_email(temp_db):
    pipeline = temp_db["pipeline"]
    repo = temp_db["repo"]

    events = [
        # Missing name
        {
            "event_id": "evt_err_noname",
            "entity_type": "CUSTOMER",
            "entity_id": "CUST-ERR-1",
            "operation": "INSERT",
            "event_timestamp": "2026-03-01T10:00:00Z",
            "sequence_number": 1,
            "payload": {
                "customer_id": "CUST-ERR-1",
                "email": "valid@email.com",
                "tier": "STANDARD",
                "credit_limit": 1000.0
            }
        },
        # Invalid email syntax
        {
            "event_id": "evt_err_badmail",
            "entity_type": "CUSTOMER",
            "entity_id": "CUST-ERR-2",
            "operation": "INSERT",
            "event_timestamp": "2026-03-01T10:05:00Z",
            "sequence_number": 1,
            "payload": {
                "customer_id": "CUST-ERR-2",
                "name": "Bad Mail",
                "email": "not_an_email_address",
                "tier": "STANDARD",
                "credit_limit": 1000.0
            }
        },
        # Domain constraint: negative credit limit
        {
            "event_id": "evt_err_negcredit",
            "entity_type": "CUSTOMER",
            "entity_id": "CUST-ERR-3",
            "operation": "INSERT",
            "event_timestamp": "2026-03-01T10:10:00Z",
            "sequence_number": 1,
            "payload": {
                "customer_id": "CUST-ERR-3",
                "name": "Negative Credit",
                "email": "neg@domain.com",
                "tier": "STANDARD",
                "credit_limit": -500.0
            }
        }
    ]

    metrics = pipeline.run(events, batch_name="validation_error_batch")
    assert metrics.quarantined_count == 3
    assert metrics.inserted_count == 0

    quarantine = repo.list_quarantine(run_id=metrics.run_id)
    assert len(quarantine) == 3
    assert all(q["status"] == "NEW" for q in quarantine)


def test_partial_failure_isolation(temp_db):
    """
    Valid records succeed and mutate target tables, while invalid records
    are quarantined without aborting or rolling back the valid transactions.
    """
    pipeline = temp_db["pipeline"]
    repo = temp_db["repo"]

    mixed_batch = [
        # Valid 1
        {
            "event_id": "evt_good_1",
            "entity_type": "CUSTOMER",
            "entity_id": "CUST-GOOD-1",
            "operation": "INSERT",
            "event_timestamp": "2026-03-01T10:00:00Z",
            "sequence_number": 1,
            "payload": {
                "customer_id": "CUST-GOOD-1",
                "name": "Good User One",
                "email": "good1@example.com",
                "tier": "STANDARD",
                "credit_limit": 5000.0
            }
        },
        # Bad 1 (quarantined)
        {
            "event_id": "evt_bad_1",
            "entity_type": "CUSTOMER",
            "entity_id": "CUST-BAD-1",
            "operation": "INSERT",
            "event_timestamp": "2026-03-01T10:05:00Z",
            "sequence_number": 1,
            "payload": {
                "customer_id": "CUST-BAD-1",
                "name": "Bad User",
                "email": "invalid_email",
                "credit_limit": -100.0
            }
        },
        # Valid 2
        {
            "event_id": "evt_good_2",
            "entity_type": "CUSTOMER",
            "entity_id": "CUST-GOOD-2",
            "operation": "INSERT",
            "event_timestamp": "2026-03-01T10:10:00Z",
            "sequence_number": 1,
            "payload": {
                "customer_id": "CUST-GOOD-2",
                "name": "Good User Two",
                "email": "good2@example.com",
                "tier": "GOLD",
                "credit_limit": 15000.0
            }
        }
    ]

    metrics = pipeline.run(mixed_batch, batch_name="mixed_batch")
    assert metrics.status == RunStatus.PARTIAL_SUCCESS
    assert metrics.total_events == 3
    assert metrics.inserted_count == 2
    assert metrics.quarantined_count == 1

    # Good records are present in current table
    assert repo.get_customer_current("CUST-GOOD-1") is not None
    assert repo.get_customer_current("CUST-GOOD-2") is not None
    assert repo.get_customer_current("CUST-BAD-1") is None

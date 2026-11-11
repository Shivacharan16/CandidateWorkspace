from backend.models.metrics import RunStatus

def test_late_arriving_event_does_not_regress_current_state(temp_db):
    """
    Scenario:
    1. Version 1 arrives: sequence 1, tier STANDARD
    2. Version 3 arrives FIRST: sequence 3, tier PLATINUM (e.g. network latency delay on v2)
    3. Version 2 arrives LATE: sequence 2, tier GOLD
    Expected:
    - Current state table retains version 3 (PLATINUM, seq 3)
    - Version 2 is recorded in history table with is_out_of_order = 1 and is_current = 0
    - Historical timeline is fully auditable
    """
    pipeline = temp_db["pipeline"]
    repo = temp_db["repo"]

    # 1. Version 1 arrives
    v1_event = {
        "event_id": "evt_ooo_v1",
        "entity_type": "CUSTOMER",
        "entity_id": "CUST-500",
        "operation": "INSERT",
        "event_timestamp": "2026-03-01T10:00:00Z",
        "sequence_number": 1,
        "payload": {
            "customer_id": "CUST-500",
            "name": "Clark Kent",
            "email": "clark@dailyplanet.com",
            "tier": "STANDARD",
            "credit_limit": 5000.0,
            "status": "ACTIVE"
        }
    }
    m1 = pipeline.run([v1_event], batch_name="batch_v1")
    assert m1.inserted_count == 1

    # 2. Version 3 arrives (out-of-order ahead of v2)
    v3_event = {
        "event_id": "evt_ooo_v3",
        "entity_type": "CUSTOMER",
        "entity_id": "CUST-500",
        "operation": "UPDATE",
        "event_timestamp": "2026-03-01T12:00:00Z",
        "sequence_number": 3,
        "payload": {
            "name": "Clark Kent",
            "email": "clark@dailyplanet.com",
            "tier": "PLATINUM",
            "credit_limit": 50000.0,
            "status": "ACTIVE"
        }
    }
    m3 = pipeline.run([v3_event], batch_name="batch_v3")
    assert m3.updated_count == 1

    # Verify state is at version 3
    curr_before = repo.get_customer_current("CUST-500")
    assert curr_before["tier"] == "PLATINUM"
    assert curr_before["last_sequence_number"] == 3

    # 3. Version 2 arrives LATE
    v2_late_event = {
        "event_id": "evt_ooo_v2_late",
        "entity_type": "CUSTOMER",
        "entity_id": "CUST-500",
        "operation": "UPDATE",
        "event_timestamp": "2026-03-01T11:00:00Z",
        "sequence_number": 2,
        "payload": {
            "name": "Clark Kent",
            "email": "clark@dailyplanet.com",
            "tier": "GOLD",
            "credit_limit": 20000.0,
            "status": "ACTIVE"
        }
    }
    m2 = pipeline.run([v2_late_event], batch_name="batch_v2_late")
    assert m2.out_of_order_count == 1
    assert m2.updated_count == 0  # Did not mutate current table!

    # Verify Current State was NOT regressed to GOLD
    curr_after = repo.get_customer_current("CUST-500")
    assert curr_after["tier"] == "PLATINUM"
    assert curr_after["last_sequence_number"] == 3
    assert curr_after["last_event_id"] == "evt_ooo_v3"

    # Verify History Table contains all 3 versions
    history = repo.get_customer_history("CUST-500")
    assert len(history) == 3

    # Find the late record
    late_hist = [h for h in history if h["event_id"] == "evt_ooo_v2_late"][0]
    assert late_hist["is_out_of_order"] == 1
    assert late_hist["is_current"] == 0
    assert late_hist["tier"] == "GOLD"
    assert late_hist["sequence_number"] == 2

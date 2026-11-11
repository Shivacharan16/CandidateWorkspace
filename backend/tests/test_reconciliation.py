from backend.generator.dataset_generator import DatasetGenerator
from backend.reconciliation.reconciler import DataReconciler

def test_automated_reconciliation_balance(temp_db):
    pipeline = temp_db["pipeline"]
    db_path = temp_db["db_path"]

    # Generate starter dataset (includes inserts, updates, deletes, duplicates, out-of-order, and errors)
    gen = DatasetGenerator(seed=42)
    sample_events = gen.generate_starter_sample()

    # Run ingestion
    metrics = pipeline.run(sample_events, batch_name="starter_reconciliation_test")

    # Run reconciliation audit
    reconciler = DataReconciler(db_path)
    report = reconciler.run_reconciliation()

    # Assertions
    assert report.all_runs_balanced is True
    assert len(report.unbalanced_run_ids) == 0
    assert report.duplicate_primary_keys_detected == 0
    assert report.scd2_multiple_active_violations == 0
    assert report.referential_integrity_violations == 0
    assert report.total_source_events == len(sample_events)
    assert report.total_quarantined_records > 0
    assert report.total_deduplicated_events > 0
    assert report.total_out_of_order_events > 0

    # Mathematical equation balance check
    expected_sum = (
        metrics.inserted_count +
        metrics.updated_count +
        metrics.deleted_count +
        metrics.duplicate_count +
        metrics.quarantined_count +
        metrics.out_of_order_count
    )
    assert metrics.total_events == expected_sum

    # Verify report formatting
    text_report = reconciler.format_text_report(report)
    assert "PASSED" in text_report
    assert "DATA PIPELINE RECONCILIATION" in text_report

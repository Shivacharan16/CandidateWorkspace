import time
from backend.generator.dataset_generator import DatasetGenerator
from backend.reconciliation.reconciler import DataReconciler

def test_pipeline_throughput_benchmark(temp_db):
    pipeline = temp_db["pipeline"]
    db_path = temp_db["db_path"]

    event_count = 5000
    gen = DatasetGenerator(seed=123)
    events = gen.generate_scalable_dataset(total_count=event_count)

    t0 = time.perf_counter()
    metrics = pipeline.run(events, batch_name="benchmark_5k_run")
    t1 = time.perf_counter()

    elapsed_sec = t1 - t0
    throughput = event_count / elapsed_sec

    print(f"\n[BENCHMARK] Ingested {event_count:,} events in {elapsed_sec:.3f} s -> {throughput:,.1f} events/sec")

    assert metrics.total_events == event_count
    # Verify reasonable performance (> 500 records/sec)
    assert throughput > 500.0

    # Ensure reconciliation still passes
    reconciler = DataReconciler(db_path)
    report = reconciler.run_reconciliation()
    assert report.all_runs_balanced is True

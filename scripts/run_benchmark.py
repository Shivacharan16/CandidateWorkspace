import sys
import time
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.generator.dataset_generator import DatasetGenerator
from backend.ingestion.reader import BatchIngestionPipeline
from backend.config import DATABASE_PATH
from backend.storage.db import init_db

def main():
    parser = argparse.ArgumentParser(description="Performance and throughput benchmark")
    parser.add_argument("--count", type=int, default=10000, help="Number of records to benchmark (default: 10,000)")
    args = parser.parse_args()

    count = args.count
    print("=" * 60)
    print(f"CDC PIPELINE INGESTION PERFORMANCE BENCHMARK")
    print(f"Target Record Count: {count:,}")
    print("=" * 60)

    # Use a benchmark-specific SQLite DB file
    bench_db = Path(__file__).resolve().parent.parent / "database" / "benchmark_run.db"
    if bench_db.exists():
        bench_db.unlink()
    init_db(bench_db)

    print(f"[*] Generating {count:,} synthetic CDC events (seed=42)...")
    t0_gen = time.perf_counter()
    gen = DatasetGenerator(seed=42)
    events = gen.generate_scalable_dataset(total_count=count)
    t1_gen = time.perf_counter()
    print(f"[+] Dataset generated in {t1_gen - t0_gen:.3f} s")

    print(f"[*] Ingesting {count:,} events with chunked commits (chunk_size=1,000)...")
    pipeline = BatchIngestionPipeline(bench_db)

    t0_pipe = time.perf_counter()
    metrics = pipeline.run(events, batch_name=f"benchmark_{count}")
    t1_pipe = time.perf_counter()

    elapsed = t1_pipe - t0_pipe
    throughput = count / elapsed

    print("=" * 60)
    print("BENCHMARK EXECUTION RESULTS:")
    print(f"  Total Ingested:       {metrics.total_events:,}")
    print(f"  Wall-Clock Duration:  {elapsed:.3f} seconds ({metrics.duration_ms:.1f} ms)")
    print(f"  Throughput:           {throughput:,.1f} events/second")
    print(f"  Inserted:             {metrics.inserted_count:,}")
    print(f"  Updated:              {metrics.updated_count:,}")
    print(f"  Duplicates Handled:   {metrics.duplicate_count:,}")
    print(f"  Out-of-Order Sequenced:{metrics.out_of_order_count:,}")
    print(f"  Quarantined:          {metrics.quarantined_count:,}")
    print(f"  Status:               {metrics.status.value}")
    print("=" * 60)

    # Clean up benchmark DB
    if bench_db.exists():
        bench_db.unlink()

if __name__ == "__main__":
    main()

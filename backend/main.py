import argparse
import sys
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn
from backend.config import API_HOST, API_PORT, DATABASE_PATH, SAMPLE_DATA_DIR
from backend.generator.dataset_generator import DatasetGenerator
from backend.ingestion.reader import BatchIngestionPipeline
from backend.reconciliation.reconciler import DataReconciler
from backend.storage.db import init_db

def main():
    parser = argparse.ArgumentParser(
        description="CDC Change Ingestion & Auditable History Pipeline CLI"
    )
    parser.add_argument("--init-db", action="store_true", help="Initialize or reset database tables")
    parser.add_argument("--generate-starter", action="store_true", help="Generate reproducible starter sample")
    parser.add_argument("--generate-scalable", type=int, metavar="N", help="Generate scalable dataset with N records (e.g. 100000)")
    parser.add_argument("--run-batch", type=str, metavar="FILE", help="Execute ingestion pipeline on JSON/JSONL file")
    parser.add_argument("--reconcile", action="store_true", help="Run automated reconciliation and print audit report")
    parser.add_argument("--serve", action="store_true", help="Start the FastAPI REST backend & Dashboard UI")
    parser.add_argument("--host", type=str, default=API_HOST, help="API server host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=API_PORT, help="API server port (default: 8000)")

    args = parser.parse_args()

    # If no flags passed, show help
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    if args.init_db:
        print(f"[*] Initializing database schema at: {DATABASE_PATH}")
        init_db(DATABASE_PATH)
        print("[+] Database initialized successfully.")

    if args.generate_starter:
        print("[*] Generating reproducible starter sample dataset...")
        gen = DatasetGenerator(seed=42)
        events = gen.generate_starter_sample()
        out_path = SAMPLE_DATA_DIR / "starter_sample.json"
        SAMPLE_DATA_DIR.mkdir(parents=True, exist_ok=True)
        import json
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(events, f, indent=2)
        print(f"[+] Generated {len(events)} events saved to: {out_path}")

    if args.generate_scalable:
        count = args.generate_scalable
        print(f"[*] Generating scalable dataset with {count:,} events (Seed: 42)...")
        gen = DatasetGenerator(seed=42)
        out_path = SAMPLE_DATA_DIR / f"scalable_sample_{count}.json"
        SAMPLE_DATA_DIR.mkdir(parents=True, exist_ok=True)
        gen.generate_scalable_dataset(total_count=count, output_file=out_path)
        print(f"[+] Successfully generated scalable dataset: {out_path}")

    if args.run_batch:
        file_path = Path(args.run_batch)
        print(f"[*] Running ingestion pipeline on: {file_path}...")
        pipeline = BatchIngestionPipeline(DATABASE_PATH)
        metrics = pipeline.run(file_path, batch_name=f"cli_run_{file_path.stem}", source_file=str(file_path))
        print(f"[+] Batch Completed in {metrics.duration_ms} ms!")
        print(f"    Status:         {metrics.status.value}")
        print(f"    Total Events:   {metrics.total_events}")
        print(f"    Inserted:       {metrics.inserted_count}")
        print(f"    Updated:        {metrics.updated_count}")
        print(f"    Deleted:        {metrics.deleted_count}")
        print(f"    Duplicates:     {metrics.duplicate_count}")
        print(f"    Out-of-Order:   {metrics.out_of_order_count}")
        print(f"    Quarantined:    {metrics.quarantined_count}")
        if metrics.error_summary:
            print(f"    Notes:          {metrics.error_summary}")

    if args.reconcile:
        print("[*] Executing automated data reconciliation and integrity audit...")
        reconciler = DataReconciler(DATABASE_PATH)
        report = reconciler.run_reconciliation()
        text_report = reconciler.format_text_report(report)
        print(text_report)

    if args.serve:
        print(f"[*] Starting CDC Pipeline Server on http://{args.host}:{args.port}")
        uvicorn.run("backend.api.routes:app", host=args.host, port=args.port, reload=False)

if __name__ == "__main__":
    main()

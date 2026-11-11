import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.ingestion.reader import BatchIngestionPipeline
from backend.config import DATABASE_PATH, SAMPLE_DATA_DIR
from backend.generator.dataset_generator import DatasetGenerator

def main():
    sample_file = SAMPLE_DATA_DIR / "starter_sample.json"
    if not sample_file.exists():
        print("[*] Generating starter sample...")
        gen = DatasetGenerator(seed=42)
        events = gen.generate_starter_sample()
        SAMPLE_DATA_DIR.mkdir(parents=True, exist_ok=True)
        import json
        with open(sample_file, "w", encoding="utf-8") as f:
            json.dump(events, f, indent=2)

    print(f"[*] Ingesting sample file: {sample_file}")
    pipeline = BatchIngestionPipeline(DATABASE_PATH)
    metrics = pipeline.run(sample_file, batch_name="starter_sample_ingest", source_file=str(sample_file))
    print(f"[+] Pipeline Run Finished in {metrics.duration_ms} ms!")
    print(f"    Status:         {metrics.status.value}")
    print(f"    Total Events:   {metrics.total_events}")
    print(f"    Inserted:       {metrics.inserted_count}")
    print(f"    Updated:        {metrics.updated_count}")
    print(f"    Deleted:        {metrics.deleted_count}")
    print(f"    Duplicates:     {metrics.duplicate_count}")
    print(f"    Out-of-Order:   {metrics.out_of_order_count}")
    print(f"    Quarantined:    {metrics.quarantined_count}")

if __name__ == "__main__":
    main()

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.generator.dataset_generator import DatasetGenerator
from backend.config import SAMPLE_DATA_DIR

def main():
    parser = argparse.ArgumentParser(description="Generate synthetic CDC event datasets")
    parser.add_argument("--count", type=int, default=1000, help="Number of records to generate")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    parser.add_argument("--starter", action="store_true", help="Generate the curated starter sample (~38 events)")
    args = parser.parse_args()

    SAMPLE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    gen = DatasetGenerator(seed=args.seed)

    if args.starter:
        events = gen.generate_starter_sample()
        out = SAMPLE_DATA_DIR / "starter_sample.json"
        import json
        with open(out, "w", encoding="utf-8") as f:
            json.dump(events, f, indent=2)
        print(f"[+] Saved {len(events)} starter events to: {out}")
    else:
        out = SAMPLE_DATA_DIR / f"scalable_sample_{args.count}.json"
        events = gen.generate_scalable_dataset(total_count=args.count, output_file=out)
        print(f"[+] Saved {len(events):,} scalable events to: {out}")

if __name__ == "__main__":
    main()

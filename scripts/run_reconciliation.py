import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.reconciliation.reconciler import DataReconciler
from backend.config import DATABASE_PATH

def main():
    print(f"[*] Running data reconciliation audit on: {DATABASE_PATH}")
    reconciler = DataReconciler(DATABASE_PATH)
    report = reconciler.run_reconciliation()
    print(reconciler.format_text_report(report))

if __name__ == "__main__":
    main()

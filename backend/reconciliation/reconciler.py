import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional
from backend.models.metrics import ReconciliationReport
from backend.storage.db import get_connection

class DataReconciler:
    """Performs rigorous end-to-end reconciliation, mathematical audits, and invariant checks."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path

    def run_reconciliation(self) -> ReconciliationReport:
        conn = get_connection(self.db_path)
        now_iso = datetime.now(timezone.utc).isoformat()

        try:
            # 1. Pipeline Run Balance Reconciliation
            cursor = conn.execute(
                """
                SELECT 
                    run_id,
                    batch_name,
                    total_events,
                    inserted_count,
                    updated_count,
                    deleted_count,
                    duplicate_count,
                    quarantined_count,
                    out_of_order_count,
                    (inserted_count + updated_count + deleted_count + duplicate_count + quarantined_count + out_of_order_count) AS sum_parts,
                    CASE 
                        WHEN total_events = (inserted_count + updated_count + deleted_count + duplicate_count + quarantined_count + out_of_order_count)
                        THEN 1 ELSE 0 
                    END AS is_balanced
                FROM pipeline_runs;
                """
            )
            run_rows = [dict(row) for row in cursor.fetchall()]

            all_balanced = True
            unbalanced_ids = []
            total_source = 0
            total_mutations = 0
            total_dups = 0
            total_quarantined = 0
            total_ooo = 0

            for r in run_rows:
                total_source += r["total_events"]
                total_mutations += (r["inserted_count"] + r["updated_count"] + r["deleted_count"])
                total_dups += r["duplicate_count"]
                total_quarantined += r["quarantined_count"]
                total_ooo += r["out_of_order_count"]

                if not r["is_balanced"]:
                    all_balanced = False
                    unbalanced_ids.append(r["run_id"])

            # 2. Check for Duplicate Primary Keys in Current State
            cursor = conn.execute(
                """
                SELECT customer_id, COUNT(*) as cnt 
                FROM dim_customers_current 
                GROUP BY customer_id HAVING cnt > 1;
                """
            )
            cust_dup_pk = len(cursor.fetchall())

            cursor = conn.execute(
                """
                SELECT order_id, COUNT(*) as cnt 
                FROM fct_orders_current 
                GROUP BY order_id HAVING cnt > 1;
                """
            )
            ord_dup_pk = len(cursor.fetchall())
            total_dup_pk = cust_dup_pk + ord_dup_pk

            # 3. Check SCD2 Active Version Invariant (Exactly 1 active version per customer)
            cursor = conn.execute(
                """
                SELECT customer_id, SUM(is_current) as active_count
                FROM dim_customers_history
                GROUP BY customer_id
                HAVING active_count > 1;
                """
            )
            scd2_violations = len(cursor.fetchall())

            # 4. Check Referential Integrity Violations in Target Tables
            cursor = conn.execute(
                """
                SELECT o.order_id
                FROM fct_orders_current o
                LEFT JOIN dim_customers_current c ON o.customer_id = c.customer_id
                WHERE c.customer_id IS NULL;
                """
            )
            ref_violations = len(cursor.fetchall())

            # 5. Current Entity Counts
            cursor = conn.execute("SELECT COUNT(*) FROM dim_customers_current WHERE is_deleted = 0;")
            curr_customers = cursor.fetchone()[0]

            cursor = conn.execute("SELECT COUNT(*) FROM fct_orders_current WHERE is_deleted = 0;")
            curr_orders = cursor.fetchone()[0]

            report = ReconciliationReport(
                generated_at=now_iso,
                runs_evaluated=len(run_rows),
                all_runs_balanced=all_balanced,
                unbalanced_run_ids=unbalanced_ids,
                total_source_events=total_source,
                total_successful_mutations=total_mutations,
                total_deduplicated_events=total_dups,
                total_quarantined_records=total_quarantined,
                total_out_of_order_events=total_ooo,
                current_customer_count=curr_customers,
                current_order_count=curr_orders,
                duplicate_primary_keys_detected=total_dup_pk,
                scd2_multiple_active_violations=scd2_violations,
                referential_integrity_violations=ref_violations,
                details=run_rows
            )
            return report

        finally:
            conn.close()

    def format_text_report(self, report: ReconciliationReport) -> str:
        """Generates a formatted markdown / plain text reconciliation report."""
        lines = [
            "=" * 70,
            "DATA PIPELINE RECONCILIATION & QUALITY AUDIT REPORT",
            "=" * 70,
            f"Audit Timestamp:               {report.generated_at}",
            f"Pipeline Runs Evaluated:       {report.runs_evaluated}",
            f"Mathematical Balance Status:   {'PASSED (All runs reconciled)' if report.all_runs_balanced else 'FAILED'}",
            "-" * 70,
            "VOLUME RECONCILIATION SUMMARY:",
            f"  Total Source Input Events:   {report.total_source_events:,}",
            f"  Successful State Mutations:  {report.total_successful_mutations:,}",
            f"  Deduplicated Events (Skips): {report.total_deduplicated_events:,}",
            f"  Quarantined (DLQ) Records:   {report.total_quarantined_records:,}",
            f"  Out-of-Order History Events: {report.total_out_of_order_events:,}",
            "-" * 70,
            "DATA INTEGRITY INVARIANTS:",
            f"  Duplicate PKs Detected:      {report.duplicate_primary_keys_detected} (Expected: 0)",
            f"  SCD2 Active Version Issues:  {report.scd2_multiple_active_violations} (Expected: 0)",
            f"  Referential Integrity Flaws: {report.referential_integrity_violations} (Expected: 0)",
            "-" * 70,
            "TARGET CURRENT ENTITY POPULATIONS:",
            f"  Active Customers in Current: {report.current_customer_count:,}",
            f"  Active Orders in Current:    {report.current_order_count:,}",
            "=" * 70,
        ]
        return "\n".join(lines)

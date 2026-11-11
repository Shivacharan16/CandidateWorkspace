import sqlite3
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from backend.models.metrics import PipelineRunMetrics, QuarantineItem

class CDCRepository:
    """Repository handling all database interactions with ACID safety."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    # ------------------------------------------------------------------
    # Pipeline Runs (Observability)
    # ------------------------------------------------------------------
    def create_pipeline_run(self, run: PipelineRunMetrics) -> None:
        self.conn.execute(
            """
            INSERT INTO pipeline_runs (
                run_id, batch_name, source_file, started_at, completed_at,
                duration_ms, status, total_events, inserted_count, updated_count,
                deleted_count, duplicate_count, quarantined_count, out_of_order_count,
                error_summary
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                run.run_id, run.batch_name, run.source_file, run.started_at,
                run.completed_at, run.duration_ms, run.status.value, run.total_events,
                run.inserted_count, run.updated_count, run.deleted_count,
                run.duplicate_count, run.quarantined_count, run.out_of_order_count,
                run.error_summary
            )
        )

    def update_pipeline_run(self, run: PipelineRunMetrics) -> None:
        self.conn.execute(
            """
            UPDATE pipeline_runs SET
                completed_at = ?,
                duration_ms = ?,
                status = ?,
                total_events = ?,
                inserted_count = ?,
                updated_count = ?,
                deleted_count = ?,
                duplicate_count = ?,
                quarantined_count = ?,
                out_of_order_count = ?,
                error_summary = ?
            WHERE run_id = ?;
            """,
            (
                run.completed_at, run.duration_ms, run.status.value,
                run.total_events, run.inserted_count, run.updated_count,
                run.deleted_count, run.duplicate_count, run.quarantined_count,
                run.out_of_order_count, run.error_summary, run.run_id
            )
        )

    def get_pipeline_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        cursor = self.conn.execute("SELECT * FROM pipeline_runs WHERE run_id = ?", (run_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def list_pipeline_runs(self, limit: int = 50) -> List[Dict[str, Any]]:
        cursor = self.conn.execute(
            "SELECT * FROM pipeline_runs ORDER BY started_at DESC LIMIT ?", (limit,)
        )
        return [dict(row) for row in cursor.fetchall()]

    # ------------------------------------------------------------------
    # Processed Events Ledger (Deduplication & Idempotency)
    # ------------------------------------------------------------------
    def is_event_processed(self, event_id: str) -> bool:
        cursor = self.conn.execute(
            "SELECT 1 FROM processed_events WHERE event_id = ?", (event_id,)
        )
        return cursor.fetchone() is not None

    def record_processed_event(
        self,
        event_id: str,
        entity_type: str,
        entity_id: str,
        operation: str,
        event_timestamp: str,
        pipeline_run_id: str,
        fingerprint_hash: str,
        processed_at: str
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO processed_events (
                event_id, entity_type, entity_id, operation, event_timestamp,
                pipeline_run_id, fingerprint_hash, processed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                event_id, entity_type, entity_id, operation, event_timestamp,
                pipeline_run_id, fingerprint_hash, processed_at
            )
        )

    # ------------------------------------------------------------------
    # Quarantine / Dead-Letter Queue
    # ------------------------------------------------------------------
    def insert_quarantine(self, item: QuarantineItem) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO quarantine_records (
                pipeline_run_id, event_id, entity_type, entity_id, error_code,
                error_message, raw_payload, quarantined_at, retry_count, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                item.pipeline_run_id, item.event_id, item.entity_type, item.entity_id,
                item.error_code, item.error_message, item.raw_payload,
                item.quarantined_at, item.retry_count, item.status
            )
        )
        return cursor.lastrowid

    def list_quarantine(
        self,
        run_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        query = "SELECT * FROM quarantine_records WHERE 1=1"
        params = []
        if run_id:
            query += " AND pipeline_run_id = ?"
            params.append(run_id)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY quarantine_id DESC LIMIT ?"
        params.append(limit)

        cursor = self.conn.execute(query, tuple(params))
        return [dict(row) for row in cursor.fetchall()]

    def get_quarantine_by_id(self, quarantine_id: int) -> Optional[Dict[str, Any]]:
        cursor = self.conn.execute(
            "SELECT * FROM quarantine_records WHERE quarantine_id = ?", (quarantine_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def update_quarantine_status(self, quarantine_id: int, status: str, retry_count: int) -> None:
        self.conn.execute(
            "UPDATE quarantine_records SET status = ?, retry_count = ? WHERE quarantine_id = ?",
            (status, retry_count, quarantine_id)
        )

    # ------------------------------------------------------------------
    # Customer Dimension (Current & SCD Type 2 History)
    # ------------------------------------------------------------------
    def get_customer_current(self, customer_id: str) -> Optional[Dict[str, Any]]:
        cursor = self.conn.execute(
            "SELECT * FROM dim_customers_current WHERE customer_id = ?", (customer_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def upsert_customer_current(self, data: Dict[str, Any]) -> None:
        self.conn.execute(
            """
            INSERT INTO dim_customers_current (
                customer_id, name, email, tier, credit_limit, status,
                address_city, address_country, is_deleted, last_event_id,
                last_event_timestamp, last_sequence_number, created_at, updated_at
            ) VALUES (
                :customer_id, :name, :email, :tier, :credit_limit, :status,
                :address_city, :address_country, :is_deleted, :last_event_id,
                :last_event_timestamp, :last_sequence_number, :created_at, :updated_at
            )
            ON CONFLICT(customer_id) DO UPDATE SET
                name = excluded.name,
                email = excluded.email,
                tier = excluded.tier,
                credit_limit = excluded.credit_limit,
                status = excluded.status,
                address_city = excluded.address_city,
                address_country = excluded.address_country,
                is_deleted = excluded.is_deleted,
                last_event_id = excluded.last_event_id,
                last_event_timestamp = excluded.last_event_timestamp,
                last_sequence_number = excluded.last_sequence_number,
                updated_at = excluded.updated_at;
            """,
            data
        )

    def close_previous_customer_history(self, customer_id: str, valid_to_ts: str) -> None:
        """Sets is_current = 0 and valid_to timestamp on previous current record."""
        self.conn.execute(
            """
            UPDATE dim_customers_history
            SET is_current = 0, valid_to = ?
            WHERE customer_id = ? AND is_current = 1;
            """,
            (valid_to_ts, customer_id)
        )

    def insert_customer_history(self, data: Dict[str, Any]) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO dim_customers_history (
                customer_id, name, email, tier, credit_limit, status,
                address_city, address_country, is_deleted, operation,
                event_id, event_timestamp, sequence_number, valid_from,
                valid_to, is_current, is_out_of_order, pipeline_run_id, recorded_at
            ) VALUES (
                :customer_id, :name, :email, :tier, :credit_limit, :status,
                :address_city, :address_country, :is_deleted, :operation,
                :event_id, :event_timestamp, :sequence_number, :valid_from,
                :valid_to, :is_current, :is_out_of_order, :pipeline_run_id, :recorded_at
            );
            """,
            data
        )
        return cursor.lastrowid

    def list_current_customers(self, limit: int = 100, search: Optional[str] = None) -> List[Dict[str, Any]]:
        query = "SELECT * FROM dim_customers_current"
        params = []
        if search:
            query += " WHERE customer_id LIKE ? OR name LIKE ? OR email LIKE ?"
            term = f"%{search}%"
            params.extend([term, term, term])
        query += " ORDER BY customer_id ASC LIMIT ?"
        params.append(limit)
        cursor = self.conn.execute(query, tuple(params))
        return [dict(row) for row in cursor.fetchall()]

    def get_customer_history(self, customer_id: str) -> List[Dict[str, Any]]:
        cursor = self.conn.execute(
            """
            SELECT * FROM dim_customers_history
            WHERE customer_id = ?
            ORDER BY sequence_number ASC, event_timestamp ASC;
            """,
            (customer_id,)
        )
        return [dict(row) for row in cursor.fetchall()]

    # ------------------------------------------------------------------
    # Orders Fact (Current & History)
    # ------------------------------------------------------------------
    def check_customer_exists_and_active(self, customer_id: str) -> bool:
        """Referential integrity check: returns True if customer exists in current table."""
        cursor = self.conn.execute(
            "SELECT 1 FROM dim_customers_current WHERE customer_id = ? AND is_deleted = 0",
            (customer_id,)
        )
        return cursor.fetchone() is not None

    def get_order_current(self, order_id: str) -> Optional[Dict[str, Any]]:
        cursor = self.conn.execute(
            "SELECT * FROM fct_orders_current WHERE order_id = ?", (order_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def upsert_order_current(self, data: Dict[str, Any]) -> None:
        self.conn.execute(
            """
            INSERT INTO fct_orders_current (
                order_id, customer_id, order_amount, order_status, currency,
                is_deleted, last_event_id, last_event_timestamp,
                last_sequence_number, created_at, updated_at
            ) VALUES (
                :order_id, :customer_id, :order_amount, :order_status, :currency,
                :is_deleted, :last_event_id, :last_event_timestamp,
                :last_sequence_number, :created_at, :updated_at
            )
            ON CONFLICT(order_id) DO UPDATE SET
                customer_id = excluded.customer_id,
                order_amount = excluded.order_amount,
                order_status = excluded.order_status,
                currency = excluded.currency,
                is_deleted = excluded.is_deleted,
                last_event_id = excluded.last_event_id,
                last_event_timestamp = excluded.last_event_timestamp,
                last_sequence_number = excluded.last_sequence_number,
                updated_at = excluded.updated_at;
            """,
            data
        )

    def close_previous_order_history(self, order_id: str, valid_to_ts: str) -> None:
        self.conn.execute(
            """
            UPDATE fct_orders_history
            SET is_current = 0, valid_to = ?
            WHERE order_id = ? AND is_current = 1;
            """,
            (valid_to_ts, order_id)
        )

    def insert_order_history(self, data: Dict[str, Any]) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO fct_orders_history (
                order_id, customer_id, order_amount, order_status, currency,
                is_deleted, operation, event_id, event_timestamp, sequence_number,
                valid_from, valid_to, is_current, is_out_of_order,
                pipeline_run_id, recorded_at
            ) VALUES (
                :order_id, :customer_id, :order_amount, :order_status, :currency,
                :is_deleted, :operation, :event_id, :event_timestamp, :sequence_number,
                :valid_from, :valid_to, :is_current, :is_out_of_order,
                :pipeline_run_id, :recorded_at
            );
            """,
            data
        )
        return cursor.lastrowid

    def list_current_orders(self, limit: int = 100) -> List[Dict[str, Any]]:
        cursor = self.conn.execute(
            "SELECT * FROM fct_orders_current ORDER BY order_id ASC LIMIT ?", (limit,)
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_order_history(self, order_id: str) -> List[Dict[str, Any]]:
        cursor = self.conn.execute(
            """
            SELECT * FROM fct_orders_history
            WHERE order_id = ?
            ORDER BY sequence_number ASC, event_timestamp ASC;
            """,
            (order_id,)
        )
        return [dict(row) for row in cursor.fetchall()]

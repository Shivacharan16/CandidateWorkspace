import json
import uuid
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Generator, Optional, Union
from backend.models.metrics import PipelineRunMetrics, RunStatus
from backend.storage.db import get_connection, transaction
from backend.storage.repository import CDCRepository
from backend.transformation.cdc_engine import CDCEngine, ProcessingResult

class BatchIngestionPipeline:
    """Ingestion controller handling batch parsing, transactions, metrics, and error safety."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path

    @staticmethod
    def load_events_from_source(source: Union[str, Path, List[Any]]) -> List[Any]:
        """
        Loads CDC events from a JSON file, JSON Lines file, or Python in-memory list.
        Safe against syntax errors and empty files.
        """
        if isinstance(source, list):
            return source

        source_path = Path(source)
        if not source_path.exists():
            raise FileNotFoundError(f"Source file not found: {source_path}")

        raw_text = source_path.read_text(encoding="utf-8").strip()
        if not raw_text:
            return []

        # Attempt standard JSON array
        try:
            parsed = json.loads(raw_text)
            if isinstance(parsed, list):
                return parsed
            elif isinstance(parsed, dict):
                return [parsed]
        except json.JSONDecodeError:
            pass

        # Attempt JSON Lines (jsonl)
        events = []
        for line_num, line in enumerate(raw_text.splitlines(), start=1):
            line_str = line.strip()
            if not line_str:
                continue
            try:
                events.append(json.loads(line_str))
            except json.JSONDecodeError as e:
                # Deliver as raw malformed record so it gets routed to quarantine
                events.append({
                    "raw_unparsed": line_str,
                    "parse_error": str(e),
                    "line_number": line_num
                })

        return events

    def run(
        self,
        events: Union[str, Path, List[Any]],
        batch_name: str = "batch_cdc_ingest",
        source_file: Optional[str] = None
    ) -> PipelineRunMetrics:
        """
        Executes the ingestion pipeline over the given events.
        Guarantees idempotency, atomic commits in chunks, and metric reporting.
        """
        start_wall = time.perf_counter()
        now_iso = datetime.now(timezone.utc).isoformat()
        run_id = f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

        metrics = PipelineRunMetrics(
            run_id=run_id,
            batch_name=batch_name,
            source_file=str(source_file) if source_file else None,
            started_at=now_iso,
            status=RunStatus.RUNNING,
            total_events=0
        )

        conn = get_connection(self.db_path)
        repo = CDCRepository(conn)
        engine = CDCEngine(repo)

        # Register initial run in DB
        with transaction(conn):
            repo.create_pipeline_run(metrics)

        try:
            event_list = self.load_events_from_source(events)
            metrics.total_events = len(event_list)

            # Process events in atomic transaction blocks of 1000
            chunk_size = 1000
            for i in range(0, max(len(event_list), 1), chunk_size):
                chunk = event_list[i : i + chunk_size]
                if not chunk:
                    break

                with transaction(conn):
                    for raw_event in chunk:
                        res, _ = engine.process_event(raw_event, run_id=run_id)

                        if res == ProcessingResult.INSERTED:
                            metrics.inserted_count += 1
                        elif res == ProcessingResult.UPDATED:
                            metrics.updated_count += 1
                        elif res == ProcessingResult.DELETED:
                            metrics.deleted_count += 1
                        elif res == ProcessingResult.DUPLICATE_SKIPPED:
                            metrics.duplicate_count += 1
                        elif res == ProcessingResult.OUT_OF_ORDER_PROCESSED:
                            metrics.out_of_order_count += 1
                        elif res == ProcessingResult.QUARANTINED:
                            metrics.quarantined_count += 1

            # Determine final status
            if metrics.quarantined_count > 0:
                metrics.status = RunStatus.PARTIAL_SUCCESS
                metrics.error_summary = f"{metrics.quarantined_count} events quarantined due to validation failures"
            else:
                metrics.status = RunStatus.SUCCESS

        except Exception as e:
            metrics.status = RunStatus.FAILED
            metrics.error_summary = f"Pipeline execution failed: {str(e)}"
            raise
        finally:
            end_wall = time.perf_counter()
            metrics.completed_at = datetime.now(timezone.utc).isoformat()
            metrics.duration_ms = round((end_wall - start_wall) * 1000, 2)

            with transaction(conn):
                repo.update_pipeline_run(metrics)
            conn.close()

        return metrics

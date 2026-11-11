import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Query, Body, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from backend.config import DATABASE_PATH, FRONTEND_DIR, SAMPLE_DATA_DIR
from backend.generator.dataset_generator import DatasetGenerator
from backend.ingestion.reader import BatchIngestionPipeline
from backend.models.metrics import PipelineRunMetrics, ReconciliationReport, RunStatus
from backend.reconciliation.reconciler import DataReconciler
from backend.storage.db import get_connection, transaction, init_db
from backend.storage.repository import CDCRepository
from backend.transformation.cdc_engine import CDCEngine, ProcessingResult

def create_app() -> FastAPI:
    app = FastAPI(
        title="CDC Ingestion & Auditable History Pipeline",
        description="Production Data Engineering CDC pipeline with SCD Type 2, DLQ Quarantine, and Idempotency",
        version="1.0.0"
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ------------------------------------------------------------------
    # Request Models
    # ------------------------------------------------------------------
    class IngestRequest(BaseModel):
        batch_name: str = "api_batch_run"
        source_file: Optional[str] = None
        events: Optional[List[Dict[str, Any]]] = None

    class GenerateRequest(BaseModel):
        total_count: int = 1000
        seed: int = 42
        auto_ingest: bool = False

    class RetryQuarantineRequest(BaseModel):
        quarantine_ids: Optional[List[int]] = None
        retry_all: bool = False

    # ------------------------------------------------------------------
    # Startup Event: Ensure DB schema initialized
    # ------------------------------------------------------------------
    @app.on_event("startup")
    def on_startup():
        init_db()

    # ------------------------------------------------------------------
    # Pipeline Ingestion Endpoints
    # ------------------------------------------------------------------
    @app.post("/api/pipeline/run", response_model=PipelineRunMetrics)
    def run_pipeline(req: IngestRequest):
        pipeline = BatchIngestionPipeline(DATABASE_PATH)
        if req.events is not None:
            return pipeline.run(req.events, batch_name=req.batch_name, source_file=req.source_file)
        elif req.source_file:
            path = Path(req.source_file)
            if not path.is_absolute():
                path = SAMPLE_DATA_DIR / req.source_file
            return pipeline.run(path, batch_name=req.batch_name, source_file=str(path))
        else:
            raise HTTPException(status_code=400, detail="Must provide either 'events' or 'source_file'")

    @app.get("/api/pipeline/runs")
    def list_pipeline_runs(limit: int = 50):
        conn = get_connection(DATABASE_PATH)
        try:
            repo = CDCRepository(conn)
            return repo.list_pipeline_runs(limit=limit)
        finally:
            conn.close()

    @app.get("/api/pipeline/runs/{run_id}")
    def get_pipeline_run(run_id: str):
        conn = get_connection(DATABASE_PATH)
        try:
            repo = CDCRepository(conn)
            run = repo.get_pipeline_run(run_id)
            if not run:
                raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
            return run
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Current State & History Exploration
    # ------------------------------------------------------------------
    @app.get("/api/customers/current")
    def list_customers(limit: int = 100, search: Optional[str] = None):
        conn = get_connection(DATABASE_PATH)
        try:
            repo = CDCRepository(conn)
            return repo.list_current_customers(limit=limit, search=search)
        finally:
            conn.close()

    @app.get("/api/customers/history/{customer_id}")
    def get_customer_history(customer_id: str):
        conn = get_connection(DATABASE_PATH)
        try:
            repo = CDCRepository(conn)
            return repo.get_customer_history(customer_id)
        finally:
            conn.close()

    @app.get("/api/orders/current")
    def list_orders(limit: int = 100):
        conn = get_connection(DATABASE_PATH)
        try:
            repo = CDCRepository(conn)
            return repo.list_current_orders(limit=limit)
        finally:
            conn.close()

    @app.get("/api/orders/history/{order_id}")
    def get_order_history(order_id: str):
        conn = get_connection(DATABASE_PATH)
        try:
            repo = CDCRepository(conn)
            return repo.get_order_history(order_id)
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Quarantine / Dead-Letter Queue Endpoints
    # ------------------------------------------------------------------
    @app.get("/api/quarantine")
    def list_quarantine(run_id: Optional[str] = None, status: Optional[str] = None, limit: int = 100):
        conn = get_connection(DATABASE_PATH)
        try:
            repo = CDCRepository(conn)
            return repo.list_quarantine(run_id=run_id, status=status, limit=limit)
        finally:
            conn.close()

    @app.post("/api/quarantine/retry")
    def retry_quarantine(req: RetryQuarantineRequest):
        """Retries unprocessable events after fixing data quality issues."""
        conn = get_connection(DATABASE_PATH)
        repo = CDCRepository(conn)
        engine = CDCEngine(repo)
        now_iso = datetime.now(timezone.utc).isoformat()
        retry_run_id = f"retry_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

        try:
            items_to_retry = []
            if req.retry_all:
                items_to_retry = repo.list_quarantine(status="NEW", limit=500)
            elif req.quarantine_ids:
                for qid in req.quarantine_ids:
                    item = repo.get_quarantine_by_id(qid)
                    if item:
                        items_to_retry.append(item)

            resolved_count = 0
            still_failing = 0

            with transaction(conn):
                repo.create_pipeline_run(PipelineRunMetrics(
                    run_id=retry_run_id,
                    batch_name="quarantine_retry_batch",
                    started_at=now_iso,
                    status=RunStatus.RUNNING,
                    total_events=len(items_to_retry)
                ))

                for q_row in items_to_retry:
                    try:
                        raw = json.loads(q_row["raw_payload"])
                    except Exception:
                        still_failing += 1
                        continue

                    # Re-evaluate event
                    res, _ = engine.process_event(raw, run_id=retry_run_id)
                    if res in (ProcessingResult.INSERTED, ProcessingResult.UPDATED, ProcessingResult.DELETED, ProcessingResult.DUPLICATE_SKIPPED, ProcessingResult.OUT_OF_ORDER_PROCESSED):
                        repo.update_quarantine_status(
                            q_row["quarantine_id"], status="RESOLVED", retry_count=q_row["retry_count"] + 1
                        )
                        resolved_count += 1
                    else:
                        repo.update_quarantine_status(
                            q_row["quarantine_id"], status="RETRIED", retry_count=q_row["retry_count"] + 1
                        )
                        still_failing += 1

                repo.update_pipeline_run(PipelineRunMetrics(
                    run_id=retry_run_id,
                    batch_name="quarantine_retry_batch",
                    started_at=now_iso,
                    completed_at=datetime.now(timezone.utc).isoformat(),
                    status=RunStatus.SUCCESS if still_failing == 0 else RunStatus.PARTIAL_SUCCESS,
                    total_events=len(items_to_retry),
                    inserted_count=resolved_count,
                    quarantined_count=still_failing
                ))

            return {
                "message": f"Retried {len(items_to_retry)} records",
                "resolved": resolved_count,
                "still_failing": still_failing
            }
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Data Generator Endpoints
    # ------------------------------------------------------------------
    @app.post("/api/generator/starter")
    def generate_starter(auto_ingest: bool = False):
        generator = DatasetGenerator(seed=42)
        events = generator.generate_starter_sample()
        out_path = SAMPLE_DATA_DIR / "starter_sample.json"
        SAMPLE_DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(events, f, indent=2)

        run_result = None
        if auto_ingest:
            pipeline = BatchIngestionPipeline(DATABASE_PATH)
            metrics = pipeline.run(events, batch_name="starter_sample_ingest", source_file=str(out_path))
            run_result = metrics.model_dump()

        return {
            "status": "SUCCESS",
            "file_path": str(out_path),
            "event_count": len(events),
            "pipeline_run": run_result
        }

    @app.post("/api/generator/scalable")
    def generate_scalable(req: GenerateRequest):
        generator = DatasetGenerator(seed=req.seed)
        out_path = SAMPLE_DATA_DIR / f"scalable_sample_{req.total_count}.json"
        SAMPLE_DATA_DIR.mkdir(parents=True, exist_ok=True)
        events = generator.generate_scalable_dataset(total_count=req.total_count, output_file=out_path)

        run_result = None
        if req.auto_ingest:
            pipeline = BatchIngestionPipeline(DATABASE_PATH)
            metrics = pipeline.run(events, batch_name=f"scalable_{req.total_count}_ingest", source_file=str(out_path))
            run_result = metrics.model_dump()

        return {
            "status": "SUCCESS",
            "file_path": str(out_path),
            "event_count": len(events),
            "pipeline_run": run_result
        }

    # ------------------------------------------------------------------
    # Reconciliation & Quality Endpoints
    # ------------------------------------------------------------------
    @app.get("/api/reconciliation/report", response_model=ReconciliationReport)
    def get_reconciliation_report():
        reconciler = DataReconciler(DATABASE_PATH)
        return reconciler.run_reconciliation()

    # ------------------------------------------------------------------
    # Analytics / Dashboard Summary
    # ------------------------------------------------------------------
    @app.get("/api/analytics/summary")
    def get_dashboard_summary():
        conn = get_connection(DATABASE_PATH)
        try:
            cursor = conn.execute("SELECT COUNT(*) FROM pipeline_runs;")
            runs_count = cursor.fetchone()[0]

            cursor = conn.execute("SELECT COUNT(*) FROM dim_customers_current WHERE is_deleted = 0;")
            cust_count = cursor.fetchone()[0]

            cursor = conn.execute("SELECT COUNT(*) FROM fct_orders_current WHERE is_deleted = 0;")
            order_count = cursor.fetchone()[0]

            cursor = conn.execute("SELECT COUNT(*) FROM dim_customers_history;")
            cust_history_count = cursor.fetchone()[0]

            cursor = conn.execute("SELECT COUNT(*) FROM quarantine_records;")
            quarantine_count = cursor.fetchone()[0]

            cursor = conn.execute("SELECT COUNT(*) FROM processed_events;")
            processed_count = cursor.fetchone()[0]

            # Reconcile status
            reconciler = DataReconciler(DATABASE_PATH)
            recon = reconciler.run_reconciliation()

            return {
                "total_runs": runs_count,
                "active_customers": cust_count,
                "active_orders": order_count,
                "audit_history_records": cust_history_count,
                "quarantined_records": quarantine_count,
                "total_processed_events": processed_count,
                "all_runs_balanced": recon.all_runs_balanced,
                "data_integrity_pass": (
                    recon.duplicate_primary_keys_detected == 0 and
                    recon.scd2_multiple_active_violations == 0 and
                    recon.referential_integrity_violations == 0
                )
            }
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Frontend Static Files Mount
    # ------------------------------------------------------------------
    if FRONTEND_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

        @app.get("/", response_class=FileResponse)
        def serve_index():
            index_path = FRONTEND_DIR / "index.html"
            if index_path.exists():
                return FileResponse(index_path)
            return HTMLResponse("<h1>Frontend loading...</h1>")

    return app

app = create_app()

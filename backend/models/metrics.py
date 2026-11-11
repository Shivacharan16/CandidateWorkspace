from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class RunStatus(str, Enum):
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    FAILED = "FAILED"


class PipelineRunMetrics(BaseModel):
    run_id: str
    batch_name: str
    source_file: Optional[str] = None
    started_at: str
    completed_at: Optional[str] = None
    duration_ms: Optional[float] = None
    status: RunStatus = RunStatus.RUNNING
    total_events: int = 0
    inserted_count: int = 0
    updated_count: int = 0
    deleted_count: int = 0
    duplicate_count: int = 0
    quarantined_count: int = 0
    out_of_order_count: int = 0
    error_summary: Optional[str] = None


class QuarantineItem(BaseModel):
    quarantine_id: Optional[int] = None
    pipeline_run_id: str
    event_id: Optional[str] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    error_code: str
    error_message: str
    raw_payload: str
    quarantined_at: str
    retry_count: int = 0
    status: str = "NEW"


class ReconciliationReport(BaseModel):
    generated_at: str
    runs_evaluated: int
    all_runs_balanced: bool
    unbalanced_run_ids: List[str] = []
    total_source_events: int
    total_successful_mutations: int
    total_deduplicated_events: int
    total_quarantined_records: int
    total_out_of_order_events: int
    current_customer_count: int
    current_order_count: int
    duplicate_primary_keys_detected: int = 0
    scd2_multiple_active_violations: int = 0
    referential_integrity_violations: int = 0
    details: List[Dict[str, Any]] = []

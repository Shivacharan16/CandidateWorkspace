import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, Tuple
from backend.models.cdc_event import CDCEventEnvelope, EntityType, OperationType
from backend.models.metrics import QuarantineItem
from backend.storage.repository import CDCRepository
from backend.validation.validator import EventValidator

class ProcessingResult(str, Enum):
    INSERTED = "INSERTED"
    UPDATED = "UPDATED"
    DELETED = "DELETED"
    DUPLICATE_SKIPPED = "DUPLICATE_SKIPPED"
    OUT_OF_ORDER_PROCESSED = "OUT_OF_ORDER_PROCESSED"
    QUARANTINED = "QUARANTINED"


class CDCEngine:
    """Core CDC transformation, deduplication, out-of-order sequencing, and SCD2 engine."""

    def __init__(self, repo: CDCRepository):
        self.repo = repo

    @staticmethod
    def compute_fingerprint(data: Any) -> str:
        """Deterministic SHA-256 fingerprint of payload."""
        normalized = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def process_event(
        self,
        raw_event: Any,
        run_id: str
    ) -> Tuple[ProcessingResult, Dict[str, Any]]:
        """
        Processes a single CDC event with full validation, idempotency, and audit trail.
        Returns: (result_enum, details_dict)
        """
        now_iso = datetime.now(timezone.utc).isoformat()

        # Step 1: Envelope Validation
        is_valid_env, envelope, err_code, err_msg = EventValidator.validate_envelope(raw_event)
        if not is_valid_env or envelope is None:
            raw_str = json.dumps(raw_event, default=str) if isinstance(raw_event, (dict, list)) else str(raw_event)
            event_id = raw_event.get("event_id") if isinstance(raw_event, dict) else None
            entity_type = raw_event.get("entity_type") if isinstance(raw_event, dict) else None
            entity_id = raw_event.get("entity_id") if isinstance(raw_event, dict) else None
            
            self.repo.insert_quarantine(QuarantineItem(
                pipeline_run_id=run_id,
                event_id=event_id,
                entity_type=str(entity_type) if entity_type else None,
                entity_id=str(entity_id) if entity_id else None,
                error_code=err_code or "INVALID_ENVELOPE",
                error_message=err_msg or "Failed envelope validation",
                raw_payload=raw_str,
                quarantined_at=now_iso,
                status="NEW"
            ))
            return ProcessingResult.QUARANTINED, {
                "error_code": err_code, "error_message": err_msg, "event_id": event_id
            }

        # Step 2: Idempotency & Deduplication Check
        if self.repo.is_event_processed(envelope.event_id):
            return ProcessingResult.DUPLICATE_SKIPPED, {
                "event_id": envelope.event_id,
                "message": f"Event {envelope.event_id} has already been processed"
            }

        # Step 3: Payload Validation & Business Rules
        is_valid_pay, payload, pay_err_code, pay_err_msg = EventValidator.validate_payload(envelope)
        if not is_valid_pay or payload is None:
            self.repo.insert_quarantine(QuarantineItem(
                pipeline_run_id=run_id,
                event_id=envelope.event_id,
                entity_type=envelope.entity_type.value,
                entity_id=envelope.entity_id,
                error_code=pay_err_code or "INVALID_PAYLOAD",
                error_message=pay_err_msg or "Payload failed business validation",
                raw_payload=json.dumps(raw_event, default=str),
                quarantined_at=now_iso,
                status="NEW"
            ))
            return ProcessingResult.QUARANTINED, {
                "error_code": pay_err_code,
                "error_message": pay_err_msg,
                "event_id": envelope.event_id
            }

        # Step 4: Referential Integrity Check
        is_valid_ref, ref_err_code, ref_err_msg = EventValidator.validate_referential_integrity(
            self.repo, envelope, payload
        )
        if not is_valid_ref:
            self.repo.insert_quarantine(QuarantineItem(
                pipeline_run_id=run_id,
                event_id=envelope.event_id,
                entity_type=envelope.entity_type.value,
                entity_id=envelope.entity_id,
                error_code=ref_err_code or "REFERENTIAL_INTEGRITY_VIOLATION",
                error_message=ref_err_msg or "Foreign key constraint violated",
                raw_payload=json.dumps(raw_event, default=str),
                quarantined_at=now_iso,
                status="NEW"
            ))
            return ProcessingResult.QUARANTINED, {
                "error_code": ref_err_code,
                "error_message": ref_err_msg,
                "event_id": envelope.event_id
            }

        # Step 5: Entity-Specific State Mutation & History Archival
        fingerprint = self.compute_fingerprint(raw_event)

        if envelope.entity_type == EntityType.CUSTOMER:
            result = self._process_customer(envelope, payload, run_id, now_iso)
        elif envelope.entity_type == EntityType.ORDER:
            result = self._process_order(envelope, payload, run_id, now_iso)
        else:
            raise ValueError(f"Unsupported entity type {envelope.entity_type}")

        # Step 6: Mark event as successfully processed in idempotency ledger
        self.repo.record_processed_event(
            event_id=envelope.event_id,
            entity_type=envelope.entity_type.value,
            entity_id=envelope.entity_id,
            operation=envelope.operation.value,
            event_timestamp=envelope.event_timestamp,
            pipeline_run_id=run_id,
            fingerprint_hash=fingerprint,
            processed_at=now_iso
        )

        return result, {
            "event_id": envelope.event_id,
            "entity_id": envelope.entity_id,
            "entity_type": envelope.entity_type.value,
            "operation": envelope.operation.value
        }

    # ------------------------------------------------------------------
    # Customer Mutation Logic
    # ------------------------------------------------------------------
    def _process_customer(
        self,
        envelope: CDCEventEnvelope,
        payload: Dict[str, Any],
        run_id: str,
        now_iso: str
    ) -> ProcessingResult:
        current = self.repo.get_customer_current(envelope.entity_id)

        # Check for Out-of-Order / Late-Arriving Event
        if current:
            is_stale_seq = envelope.sequence_number < current["last_sequence_number"]
            is_stale_ts = (
                envelope.sequence_number == current["last_sequence_number"] and
                envelope.event_timestamp < current["last_event_timestamp"]
            )
            if is_stale_seq or is_stale_ts:
                # Event is older than current state: archive in history, do not mutate current table
                self.repo.insert_customer_history({
                    "customer_id": envelope.entity_id,
                    "name": payload.get("name", current["name"]),
                    "email": payload.get("email", current["email"]),
                    "tier": payload.get("tier", current["tier"]),
                    "credit_limit": payload.get("credit_limit", current["credit_limit"]),
                    "status": payload.get("status", current["status"]),
                    "address_city": payload.get("address_city", current["address_city"]),
                    "address_country": payload.get("address_country", current["address_country"]),
                    "is_deleted": 1 if envelope.operation == OperationType.DELETE else 0,
                    "operation": envelope.operation.value,
                    "event_id": envelope.event_id,
                    "event_timestamp": envelope.event_timestamp,
                    "sequence_number": envelope.sequence_number,
                    "valid_from": envelope.event_timestamp,
                    "valid_to": current["last_event_timestamp"],
                    "is_current": 0,
                    "is_out_of_order": 1,
                    "pipeline_run_id": run_id,
                    "recorded_at": now_iso
                })
                return ProcessingResult.OUT_OF_ORDER_PROCESSED

        # Standard in-order mutation
        is_insert = current is None
        is_delete = envelope.operation == OperationType.DELETE

        # Build current-state record
        cust_record = {
            "customer_id": envelope.entity_id,
            "name": payload.get("name", current["name"] if current else "Unknown"),
            "email": payload.get("email", current["email"] if current else "unknown@domain.com"),
            "tier": payload.get("tier", current["tier"] if current else "STANDARD"),
            "credit_limit": payload.get("credit_limit", current["credit_limit"] if current else 0.0),
            "status": "DELETED" if is_delete else payload.get("status", current["status"] if current else "ACTIVE"),
            "address_city": payload.get("address_city", current["address_city"] if current else None),
            "address_country": payload.get("address_country", current["address_country"] if current else None),
            "is_deleted": 1 if is_delete else 0,
            "last_event_id": envelope.event_id,
            "last_event_timestamp": envelope.event_timestamp,
            "last_sequence_number": envelope.sequence_number,
            "created_at": current["created_at"] if current else now_iso,
            "updated_at": now_iso
        }
        self.repo.upsert_customer_current(cust_record)

        # Close previous active history version
        self.repo.close_previous_customer_history(envelope.entity_id, envelope.event_timestamp)

        # Insert new active history record
        self.repo.insert_customer_history({
            "customer_id": envelope.entity_id,
            "name": cust_record["name"],
            "email": cust_record["email"],
            "tier": cust_record["tier"],
            "credit_limit": cust_record["credit_limit"],
            "status": cust_record["status"],
            "address_city": cust_record["address_city"],
            "address_country": cust_record["address_country"],
            "is_deleted": cust_record["is_deleted"],
            "operation": envelope.operation.value,
            "event_id": envelope.event_id,
            "event_timestamp": envelope.event_timestamp,
            "sequence_number": envelope.sequence_number,
            "valid_from": envelope.event_timestamp,
            "valid_to": None,
            "is_current": 1,
            "is_out_of_order": 0,
            "pipeline_run_id": run_id,
            "recorded_at": now_iso
        })

        if is_delete:
            return ProcessingResult.DELETED
        return ProcessingResult.INSERTED if is_insert else ProcessingResult.UPDATED

    # ------------------------------------------------------------------
    # Order Mutation Logic
    # ------------------------------------------------------------------
    def _process_order(
        self,
        envelope: CDCEventEnvelope,
        payload: Dict[str, Any],
        run_id: str,
        now_iso: str
    ) -> ProcessingResult:
        current = self.repo.get_order_current(envelope.entity_id)

        # Check for Out-of-Order / Late-Arriving Event
        if current:
            is_stale_seq = envelope.sequence_number < current["last_sequence_number"]
            is_stale_ts = (
                envelope.sequence_number == current["last_sequence_number"] and
                envelope.event_timestamp < current["last_event_timestamp"]
            )
            if is_stale_seq or is_stale_ts:
                self.repo.insert_order_history({
                    "order_id": envelope.entity_id,
                    "customer_id": payload.get("customer_id", current["customer_id"]),
                    "order_amount": payload.get("order_amount", current["order_amount"]),
                    "order_status": payload.get("order_status", current["order_status"]),
                    "currency": payload.get("currency", current["currency"]),
                    "is_deleted": 1 if envelope.operation == OperationType.DELETE else 0,
                    "operation": envelope.operation.value,
                    "event_id": envelope.event_id,
                    "event_timestamp": envelope.event_timestamp,
                    "sequence_number": envelope.sequence_number,
                    "valid_from": envelope.event_timestamp,
                    "valid_to": current["last_event_timestamp"],
                    "is_current": 0,
                    "is_out_of_order": 1,
                    "pipeline_run_id": run_id,
                    "recorded_at": now_iso
                })
                return ProcessingResult.OUT_OF_ORDER_PROCESSED

        # Standard in-order mutation
        is_insert = current is None
        is_delete = envelope.operation == OperationType.DELETE

        order_record = {
            "order_id": envelope.entity_id,
            "customer_id": payload.get("customer_id", current["customer_id"] if current else "UNKNOWN"),
            "order_amount": payload.get("order_amount", current["order_amount"] if current else 0.0),
            "order_status": "CANCELLED" if is_delete else payload.get("order_status", current["order_status"] if current else "PENDING"),
            "currency": payload.get("currency", current["currency"] if current else "USD"),
            "is_deleted": 1 if is_delete else 0,
            "last_event_id": envelope.event_id,
            "last_event_timestamp": envelope.event_timestamp,
            "last_sequence_number": envelope.sequence_number,
            "created_at": current["created_at"] if current else now_iso,
            "updated_at": now_iso
        }
        self.repo.upsert_order_current(order_record)

        # Close previous active history version
        self.repo.close_previous_order_history(envelope.entity_id, envelope.event_timestamp)

        # Insert new active history record
        self.repo.insert_order_history({
            "order_id": order_record["order_id"],
            "customer_id": order_record["customer_id"],
            "order_amount": order_record["order_amount"],
            "order_status": order_record["order_status"],
            "currency": order_record["currency"],
            "is_deleted": order_record["is_deleted"],
            "operation": envelope.operation.value,
            "event_id": envelope.event_id,
            "event_timestamp": envelope.event_timestamp,
            "sequence_number": envelope.sequence_number,
            "valid_from": envelope.event_timestamp,
            "valid_to": None,
            "is_current": 1,
            "is_out_of_order": 0,
            "pipeline_run_id": run_id,
            "recorded_at": now_iso
        })

        if is_delete:
            return ProcessingResult.DELETED
        return ProcessingResult.INSERTED if is_insert else ProcessingResult.UPDATED

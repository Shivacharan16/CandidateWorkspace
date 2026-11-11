import json
from typing import Tuple, Optional, Any, Dict
from pydantic import ValidationError
from backend.models.cdc_event import CDCEventEnvelope, EntityType, OperationType
from backend.models.domain import CustomerPayload, OrderPayload, CustomerUpdatePayload, OrderUpdatePayload
from backend.storage.repository import CDCRepository

class EventValidator:
    """Validates raw CDC events, schema compliance, business rules, and referential integrity."""

    @staticmethod
    def validate_envelope(raw_event: Any) -> Tuple[bool, Optional[CDCEventEnvelope], Optional[str], Optional[str]]:
        """
        Validates envelope structure.
        Returns: (is_valid, envelope, error_code, error_message)
        """
        if not isinstance(raw_event, dict):
            return False, None, "MALFORMED_INPUT", f"Expected dictionary/JSON object, got {type(raw_event).__name__}"

        try:
            envelope = CDCEventEnvelope(**raw_event)
            return True, envelope, None, None
        except ValidationError as e:
            errors = []
            for err in e.errors():
                loc = " -> ".join(str(l) for l in err["loc"])
                errors.append(f"{loc}: {err['msg']}")
            return False, None, "INVALID_SCHEMA", "; ".join(errors)
        except Exception as ex:
            return False, None, "INVALID_SCHEMA", str(ex)

    @staticmethod
    def validate_payload(envelope: CDCEventEnvelope) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str], Optional[str]]:
        """
        Validates the entity payload against specific business rules.
        For DELETE operations, only entity_id is strictly required.
        For UPDATE operations, partial attribute deltas are permitted.
        """
        if envelope.operation == OperationType.DELETE:
            payload = dict(envelope.payload) if envelope.payload else {}
            if envelope.entity_type == EntityType.CUSTOMER:
                payload["customer_id"] = envelope.entity_id
            elif envelope.entity_type == EntityType.ORDER:
                payload["order_id"] = envelope.entity_id
            return True, payload, None, None

        payload_dict = dict(envelope.payload) if envelope.payload else {}
        is_update = envelope.operation == OperationType.UPDATE

        if envelope.entity_type == EntityType.CUSTOMER:
            if "customer_id" not in payload_dict:
                payload_dict["customer_id"] = envelope.entity_id
            
            try:
                if is_update:
                    validated = CustomerUpdatePayload(**payload_dict)
                    return True, {k: v for k, v in validated.model_dump().items() if v is not None}, None, None
                else:
                    validated = CustomerPayload(**payload_dict)
                    return True, validated.model_dump(), None, None
            except ValidationError as e:
                errors = []
                for err in e.errors():
                    field_name = " -> ".join(str(l) for l in err["loc"])
                    errors.append(f"{field_name}: {err['msg']}")
                return False, None, "BUSINESS_RULE_VIOLATION", "; ".join(errors)

        elif envelope.entity_type == EntityType.ORDER:
            if "order_id" not in payload_dict:
                payload_dict["order_id"] = envelope.entity_id

            try:
                if is_update:
                    validated = OrderUpdatePayload(**payload_dict)
                    return True, {k: v for k, v in validated.model_dump().items() if v is not None}, None, None
                else:
                    validated = OrderPayload(**payload_dict)
                    return True, validated.model_dump(), None, None
            except ValidationError as e:
                errors = []
                for err in e.errors():
                    field_name = " -> ".join(str(l) for l in err["loc"])
                    errors.append(f"{field_name}: {err['msg']}")
                return False, None, "BUSINESS_RULE_VIOLATION", "; ".join(errors)

        return False, None, "UNKNOWN_ENTITY_TYPE", f"Unsupported entity type: {envelope.entity_type}"

    @staticmethod
    def validate_referential_integrity(
        repo: CDCRepository, envelope: CDCEventEnvelope, payload: Dict[str, Any]
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Ensures foreign keys exist in parent tables before mutation is accepted.
        For ORDER: customer_id must exist and be active in dim_customers_current.
        """
        if envelope.entity_type == EntityType.ORDER:
            customer_id = payload.get("customer_id")
            if not customer_id and envelope.operation == OperationType.UPDATE:
                curr_ord = repo.get_order_current(envelope.entity_id)
                if curr_ord:
                    customer_id = curr_ord["customer_id"]

            if envelope.operation == OperationType.INSERT and not customer_id:
                return False, "MISSING_REQUIRED_FIELD", "Order requires customer_id"

            if customer_id and not repo.check_customer_exists_and_active(customer_id):
                return False, "REFERENTIAL_INTEGRITY_VIOLATION", (
                    f"Referenced customer_id '{customer_id}' does not exist or is deleted in dim_customers_current"
                )

        return True, None, None

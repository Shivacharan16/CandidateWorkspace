from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field, field_validator
from datetime import datetime

class OperationType(str, Enum):
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    
    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            val_upper = value.upper()
            if val_upper in ("I", "INSERT"):
                return cls.INSERT
            if val_upper in ("U", "UPDATE"):
                return cls.UPDATE
            if val_upper in ("D", "DELETE"):
                return cls.DELETE
        return super()._missing_(value)


class EntityType(str, Enum):
    CUSTOMER = "CUSTOMER"
    ORDER = "ORDER"

    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            val_upper = value.upper()
            if val_upper in ("CUSTOMER", "CUSTOMERS"):
                return cls.CUSTOMER
            if val_upper in ("ORDER", "ORDERS"):
                return cls.ORDER
        return super()._missing_(value)


class CDCEventEnvelope(BaseModel):
    event_id: str = Field(..., min_length=1, description="Deterministic or unique event identifier")
    entity_type: EntityType = Field(..., description="Target business entity type")
    entity_id: str = Field(..., min_length=1, description="Natural primary key of the entity")
    operation: OperationType = Field(..., description="Mutation operation (INSERT, UPDATE, DELETE)")
    event_timestamp: str = Field(..., description="ISO-8601 timestamp when the mutation occurred")
    sequence_number: int = Field(default=1, ge=1, description="Monotonically increasing sequence/version number")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Entity attributes")
    source_system: Optional[str] = Field(default="cdc-producer", description="Source pipeline or service name")

    @field_validator("event_timestamp")
    @classmethod
    def validate_timestamp_format(cls, v: str) -> str:
        try:
            # Normalize trailing 'Z' if present
            clean_ts = v.replace("Z", "+00:00") if v.endswith("Z") else v
            datetime.fromisoformat(clean_ts)
            return v
        except Exception:
            raise ValueError(f"Invalid ISO-8601 timestamp: '{v}'")

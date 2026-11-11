import re
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, field_validator

EMAIL_REGEX = re.compile(r"^[\w\.\+\-]+@[\w\-]+\.[a-zA-Z]{2,}$")

class CustomerTier(str, Enum):
    STANDARD = "STANDARD"
    SILVER = "SILVER"
    GOLD = "GOLD"
    PLATINUM = "PLATINUM"


class CustomerStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    DELETED = "DELETED"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    SHIPPED = "SHIPPED"
    CANCELLED = "CANCELLED"
    REFUNDED = "REFUNDED"


class CustomerPayload(BaseModel):
    customer_id: str = Field(..., min_length=1, description="Customer PK")
    name: str = Field(..., min_length=1, description="Customer Name")
    email: str = Field(..., min_length=3, description="Valid email address")
    tier: CustomerTier = Field(default=CustomerTier.STANDARD)
    credit_limit: float = Field(default=0.0, ge=0.0, description="Credit limit, non-negative")
    status: CustomerStatus = Field(default=CustomerStatus.ACTIVE)
    address_city: Optional[str] = Field(default=None)
    address_country: Optional[str] = Field(default=None)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if not EMAIL_REGEX.match(v):
            raise ValueError(f"Invalid email address: '{v}'")
        return v.lower().strip()

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("Customer name cannot be empty or whitespace only")
        return trimmed


class OrderPayload(BaseModel):
    order_id: str = Field(..., min_length=1, description="Order PK")
    customer_id: str = Field(..., min_length=1, description="Foreign Key to Customer")
    order_amount: float = Field(..., gt=0.0, description="Order amount, must be strictly greater than 0")
    order_status: OrderStatus = Field(default=OrderStatus.PENDING)
    currency: str = Field(default="USD", min_length=3, max_length=3, description="3-letter currency code")

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        if not v.isalpha() or len(v) != 3:
            raise ValueError("Currency must be a 3-letter alphabetic code (e.g. USD, EUR)")
        return v.upper()


class CustomerUpdatePayload(BaseModel):
    customer_id: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None
    tier: Optional[CustomerTier] = None
    credit_limit: Optional[float] = Field(default=None, ge=0.0)
    status: Optional[CustomerStatus] = None
    address_city: Optional[str] = None
    address_country: Optional[str] = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            if not EMAIL_REGEX.match(v):
                raise ValueError(f"Invalid email address: '{v}'")
            return v.lower().strip()
        return v

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            trimmed = v.strip()
            if not trimmed:
                raise ValueError("Customer name cannot be empty or whitespace only")
            return trimmed
        return v


class OrderUpdatePayload(BaseModel):
    order_id: Optional[str] = None
    customer_id: Optional[str] = None
    order_amount: Optional[float] = Field(default=None, gt=0.0)
    order_status: Optional[OrderStatus] = None
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3)

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            if not v.isalpha() or len(v) != 3:
                raise ValueError("Currency must be a 3-letter alphabetic code (e.g. USD, EUR)")
            return v.upper()
        return v


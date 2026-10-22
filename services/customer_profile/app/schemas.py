
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


NonNegativeInt = Annotated[int, Field(ge=0)]
NonNegativeFloat = Annotated[float, Field(ge=0)]


class CustomerCreate(BaseModel):
    tenant_id: uuid.UUID
    external_id: Annotated[
        str, Field(min_length=1, max_length=100)
    ]
    tenure_months: NonNegativeInt = 0
    subscription_plan: Annotated[
        str | None, Field(max_length=50)
    ] = None
    monthly_spend: NonNegativeFloat = 0
    usage_30d: NonNegativeFloat = 0
    support_tickets_90d: NonNegativeInt = 0
    last_active_at: datetime | None = None


class CustomerUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenure_months: NonNegativeInt | None = None
    subscription_plan: Annotated[
        str | None, Field(max_length=50)
    ] = None
    monthly_spend: NonNegativeFloat | None = None
    usage_30d: NonNegativeFloat | None = None
    support_tickets_90d: NonNegativeInt | None = None
    last_active_at: datetime | None = None


class CustomerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    external_id: str
    tenure_months: int
    subscription_plan: str | None
    monthly_spend: Decimal
    usage_30d: Decimal
    support_tickets_90d: int
    last_active_at: datetime | None
    created_at: datetime
    updated_at: datetime

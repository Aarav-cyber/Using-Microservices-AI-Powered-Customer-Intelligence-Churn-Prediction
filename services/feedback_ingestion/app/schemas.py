from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class FeedbackCreate(BaseModel):
    tenant_id: UUID
    customer_id: UUID
    message: str = Field(min_length=1, max_length=5000)
    channel: str = Field(default="web", min_length=1, max_length=50)


class FeedbackRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    customer_id: UUID
    message: str
    channel: str
    created_at: datetime
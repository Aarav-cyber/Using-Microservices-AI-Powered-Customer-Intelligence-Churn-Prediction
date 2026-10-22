
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Customer(Base):
    __tablename__ = "customers"

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "external_id",
            name="uq_customers_tenant_external_id",
        ),
        CheckConstraint(
            "tenure_months >= 0",
            name="ck_customers_tenure_nonnegative",
        ),
        CheckConstraint(
            "monthly_spend >= 0",
            name="ck_customers_spend_nonnegative",
        ),
        CheckConstraint(
            "usage_30d >= 0",
            name="ck_customers_usage_nonnegative",
        ),
        CheckConstraint(
            "support_tickets_90d >= 0",
            name="ck_customers_tickets_nonnegative",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        index=True,
    )

    external_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    tenure_months: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    subscription_plan: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    monthly_spend: Mapped[float] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=0,
    )

    usage_30d: Mapped[float] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=0,
    )

    support_tickets_90d: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    last_active_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

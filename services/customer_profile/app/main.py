
import uuid
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Customer
from app.schemas import CustomerCreate, CustomerRead, CustomerUpdate

app = FastAPI(
    title="Customer Profile Service",
    description="Customer data API for the Customer Intelligence platform.",
    version="1.0.0",
)


@app.get("/health")
def health():
    return {"status": "ok", "service": "customer-profile"}


@app.post(
    "/api/v1/customers",
    response_model=CustomerRead,
    status_code=status.HTTP_201_CREATED,
)
def create_customer(
    payload: CustomerCreate,
    db: Session = Depends(get_db),
):
    customer = Customer(**payload.model_dump())
    db.add(customer)

    try:
        db.commit()
        db.refresh(customer)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A customer with this external_id already exists "
                   "for this tenant, or a database constraint was violated.",
        ) from exc

    return customer


@app.get(
    "/api/v1/customers",
    response_model=list[CustomerRead],
)
def list_customers(
    tenant_id: uuid.UUID,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    statement = (
        select(Customer)
        .where(Customer.tenant_id == tenant_id)
        .order_by(Customer.created_at.desc(), Customer.id)
        .offset(skip)
        .limit(limit)
    )

    return db.scalars(statement).all()


@app.get(
    "/api/v1/customers/{customer_id}",
    response_model=CustomerRead,
)
def get_customer(
    customer_id: uuid.UUID,
    tenant_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    customer = db.scalar(
        select(Customer).where(
            Customer.id == customer_id,
            Customer.tenant_id == tenant_id,
        )
    )

    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    return customer


@app.patch(
    "/api/v1/customers/{customer_id}",
    response_model=CustomerRead,
)
def update_customer(
    customer_id: uuid.UUID,
    payload: CustomerUpdate,
    tenant_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    customer = db.scalar(
        select(Customer).where(
            Customer.id == customer_id,
            Customer.tenant_id == tenant_id,
        )
    )

    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    changes = payload.model_dump(exclude_unset=True)

    if not changes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide at least one field to update",
        )

    # Numeric database fields are not nullable.
    non_nullable_fields = {
        "tenure_months",
        "monthly_spend",
        "usage_30d",
        "support_tickets_90d",
    }

    if any(
        field in changes and changes[field] is None
        for field in non_nullable_fields
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Numeric customer fields cannot be null",
        )

    for field, value in changes.items():
        setattr(customer, field, value)

    customer.updated_at = datetime.now(timezone.utc)

    try:
        db.commit()
        db.refresh(customer)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Customer update violated a database constraint",
        ) from exc

    return customer


@app.delete(
    "/api/v1/customers/{customer_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_customer(
    customer_id: uuid.UUID,
    tenant_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    customer = db.scalar(
        select(Customer).where(
            Customer.id == customer_id,
            Customer.tenant_id == tenant_id,
        )
    )

    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    db.delete(customer)
    db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)

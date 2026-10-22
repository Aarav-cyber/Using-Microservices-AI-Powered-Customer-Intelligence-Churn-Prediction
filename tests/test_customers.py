
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    TestingSessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def tenant_id():
    return str(uuid.uuid4())


def customer_payload(tenant_id, external_id="customer-001"):
    return {
        "tenant_id": tenant_id,
        "external_id": external_id,
        "tenure_months": 12,
        "subscription_plan": "premium",
        "monthly_spend": 49.99,
        "usage_30d": 120.0,
        "support_tickets_90d": 2,
    }


def test_health(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_customer(client, tenant_id):
    response = client.post(
        "/api/v1/customers",
        json=customer_payload(tenant_id),
    )

    assert response.status_code == 201

    data = response.json()
    assert data["tenant_id"] == tenant_id
    assert data["external_id"] == "customer-001"
    assert data["tenure_months"] == 12
    assert data["subscription_plan"] == "premium"
    assert "id" in data
    assert "created_at" in data


def test_get_customer(client, tenant_id):
    created = client.post(
        "/api/v1/customers",
        json=customer_payload(tenant_id),
    ).json()

    response = client.get(
        f"/api/v1/customers/{created['id']}",
        params={"tenant_id": tenant_id},
    )

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_customer_isolation(client, tenant_id):
    created = client.post(
        "/api/v1/customers",
        json=customer_payload(tenant_id),
    ).json()

    another_tenant = str(uuid.uuid4())

    response = client.get(
        f"/api/v1/customers/{created['id']}",
        params={"tenant_id": another_tenant},
    )

    assert response.status_code == 404


def test_duplicate_external_id_returns_conflict(client, tenant_id):
    payload = customer_payload(tenant_id)

    first = client.post("/api/v1/customers", json=payload)
    second = client.post("/api/v1/customers", json=payload)

    assert first.status_code == 201
    assert second.status_code == 409


def test_negative_tenure_is_rejected(client, tenant_id):
    payload = customer_payload(tenant_id)
    payload["tenure_months"] = -1

    response = client.post(
        "/api/v1/customers",
        json=payload,
    )

    assert response.status_code == 422


def test_update_customer(client, tenant_id):
    created = client.post(
        "/api/v1/customers",
        json=customer_payload(tenant_id),
    ).json()

    response = client.patch(
        f"/api/v1/customers/{created['id']}",
        params={"tenant_id": tenant_id},
        json={
            "usage_30d": 75.0,
            "support_tickets_90d": 3,
        },
    )

    assert response.status_code == 200
    assert float(response.json()["usage_30d"]) == 75.0
    assert response.json()["support_tickets_90d"] == 3
    assert response.json()["tenure_months"] == 12


def test_list_customers_is_tenant_scoped(client, tenant_id):
    client.post(
        "/api/v1/customers",
        json=customer_payload(tenant_id, "customer-001"),
    )
    client.post(
        "/api/v1/customers",
        json=customer_payload(tenant_id, "customer-002"),
    )

    another_tenant = str(uuid.uuid4())
    client.post(
        "/api/v1/customers",
        json=customer_payload(another_tenant, "customer-003"),
    )

    response = client.get(
        "/api/v1/customers",
        params={"tenant_id": tenant_id, "limit": 1},
    )

    assert response.status_code == 200
    assert len(response.json()) == 1

    all_customers = client.get(
        "/api/v1/customers",
        params={"tenant_id": tenant_id, "limit": 100},
    )

    assert len(all_customers.json()) == 2

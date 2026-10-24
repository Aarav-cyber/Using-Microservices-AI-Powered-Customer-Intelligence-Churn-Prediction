import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import create_access_token
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


@pytest.fixture
def auth_headers(tenant_id):
    token = create_access_token(tenant_id=tenant_id)
    return {"Authorization": f"Bearer {token}"}


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


def test_auth_token_endpoint(client, tenant_id):
    response = client.post(
        "/api/v1/auth/token",
        json={"tenant_id": tenant_id, "user_id": "test_user"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["tenant_id"] == tenant_id


def test_missing_token_returns_unauthorized(client, tenant_id):
    response = client.post(
        "/api/v1/customers",
        json=customer_payload(tenant_id),
    )
    assert response.status_code == 401
    assert "Missing Bearer authentication token" in response.json()["detail"]


def test_invalid_token_returns_unauthorized(client, tenant_id):
    response = client.get(
        "/api/v1/customers",
        headers={"Authorization": "Bearer invalid.token.value"},
    )
    assert response.status_code == 401
    assert "Invalid authentication token" in response.json()["detail"]


def test_create_customer(client, tenant_id, auth_headers):
    response = client.post(
        "/api/v1/customers",
        json=customer_payload(tenant_id),
        headers=auth_headers,
    )

    assert response.status_code == 201

    data = response.json()
    assert data["tenant_id"] == tenant_id
    assert data["external_id"] == "customer-001"
    assert data["tenure_months"] == 12
    assert data["subscription_plan"] == "premium"
    assert "id" in data
    assert "created_at" in data


def test_cross_tenant_create_is_forbidden(client, tenant_id, auth_headers):
    another_tenant = str(uuid.uuid4())
    response = client.post(
        "/api/v1/customers",
        json=customer_payload(another_tenant),
        headers=auth_headers,
    )

    assert response.status_code == 403
    assert "Forbidden" in response.json()["detail"]


def test_get_customer(client, tenant_id, auth_headers):
    created = client.post(
        "/api/v1/customers",
        json=customer_payload(tenant_id),
        headers=auth_headers,
    ).json()

    response = client.get(
        f"/api/v1/customers/{created['id']}",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_cross_tenant_access_is_forbidden_or_not_found(client, tenant_id, auth_headers):
    created = client.post(
        "/api/v1/customers",
        json=customer_payload(tenant_id),
        headers=auth_headers,
    ).json()

    another_tenant = str(uuid.uuid4())
    another_token = create_access_token(tenant_id=another_tenant)
    another_headers = {"Authorization": f"Bearer {another_token}"}

    # Calling with another tenant's credentials to fetch Tenant A's customer returns 404
    response = client.get(
        f"/api/v1/customers/{created['id']}",
        headers=another_headers,
    )
    assert response.status_code == 404


def test_duplicate_external_id_returns_conflict(client, tenant_id, auth_headers):
    payload = customer_payload(tenant_id)

    first = client.post("/api/v1/customers", json=payload, headers=auth_headers)
    second = client.post("/api/v1/customers", json=payload, headers=auth_headers)

    assert first.status_code == 201
    assert second.status_code == 409


def test_negative_tenure_is_rejected(client, tenant_id, auth_headers):
    payload = customer_payload(tenant_id)
    payload["tenure_months"] = -1

    response = client.post(
        "/api/v1/customers",
        json=payload,
        headers=auth_headers,
    )

    assert response.status_code == 422


def test_update_customer(client, tenant_id, auth_headers):
    created = client.post(
        "/api/v1/customers",
        json=customer_payload(tenant_id),
        headers=auth_headers,
    ).json()

    response = client.patch(
        f"/api/v1/customers/{created['id']}",
        headers=auth_headers,
        json={
            "usage_30d": 75.0,
            "support_tickets_90d": 3,
        },
    )

    assert response.status_code == 200
    assert float(response.json()["usage_30d"]) == 75.0
    assert response.json()["support_tickets_90d"] == 3
    assert response.json()["tenure_months"] == 12


def test_list_customers_is_tenant_scoped(client, tenant_id, auth_headers):
    client.post(
        "/api/v1/customers",
        json=customer_payload(tenant_id, "customer-001"),
        headers=auth_headers,
    )
    client.post(
        "/api/v1/customers",
        json=customer_payload(tenant_id, "customer-002"),
        headers=auth_headers,
    )

    another_tenant = str(uuid.uuid4())
    another_token = create_access_token(tenant_id=another_tenant)
    another_headers = {"Authorization": f"Bearer {another_token}"}

    client.post(
        "/api/v1/customers",
        json=customer_payload(another_tenant, "customer-003"),
        headers=another_headers,
    )

    response = client.get(
        "/api/v1/customers",
        params={"limit": 1},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert len(response.json()) == 1

    all_customers = client.get(
        "/api/v1/customers",
        params={"limit": 100},
        headers=auth_headers,
    )

    assert len(all_customers.json()) == 2

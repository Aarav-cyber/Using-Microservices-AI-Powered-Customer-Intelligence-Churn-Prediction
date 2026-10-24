import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

JWT_SECRET_KEY = os.getenv(
    "JWT_SECRET_KEY"
)
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM")

security = HTTPBearer(auto_error=False)


@dataclass
class TenantContext:
    tenant_id: uuid.UUID
    user_id: str
    role: str = "user"


def create_access_token(
    tenant_id: uuid.UUID | str,
    user_id: str = "tenant_user",
    role: str = "user",
    expires_delta: timedelta | None = None,
) -> str:
    """Generate a signed HMAC-SHA256 JWT containing tenant identity."""
    if expires_delta is None:
        expires_delta = timedelta(hours=24)

    expire = datetime.now(timezone.utc) + expires_delta
    payload = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "role": role,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def get_current_tenant(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(security)],
) -> TenantContext:
    """FastAPI dependency to extract and verify tenant identity from Bearer token."""
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Bearer authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    raw_tenant_id = payload.get("tenant_id")
    if not raw_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is missing required tenant_id claim.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        tenant_uuid = uuid.UUID(str(raw_tenant_id))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid tenant_id format in token: {raw_tenant_id}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return TenantContext(
        tenant_id=tenant_uuid,
        user_id=str(payload.get("sub", "anonymous")),
        role=str(payload.get("role", "user")),
    )
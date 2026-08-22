"""API key authentication for Lead Hunter."""
from __future__ import annotations

import os
from typing import Optional

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_api_key() -> str:
    """Load the API key from environment or secrets."""
    key = os.environ.get("LEAD_HUNTER_API_KEY")
    if not key:
        key = os.environ.get("LH_API_KEY")
    return key or ""


async def verify_api_key(api_key: Optional[str] = Security(api_key_header)) -> str:
    """Verify the X-API-Key header against configured secret."""
    expected = get_api_key()
    if not expected:
        # No key configured: reject any provided key as invalid
        if api_key:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid API key",
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key not configured on server",
        )
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-API-Key header required",
        )
    if api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )
    return api_key

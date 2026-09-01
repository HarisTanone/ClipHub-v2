"""Shared Repliz API helpers used by all social platform modules."""
import base64
from typing import Optional

import httpx
from fastapi import HTTPException

from src.config import settings


def repliz_auth_header() -> dict[str, str]:
    """Build Basic Auth header for Repliz API."""
    access_key = (settings.REPLIZ_ACCESS_KEY or "").strip()
    secret_key = (settings.REPLIZ_SECRET_KEY or "").strip()
    if not access_key or not secret_key:
        raise HTTPException(status_code=503, detail="Repliz credentials not configured")
    creds = base64.b64encode(
        f"{access_key}:{secret_key}".encode()
    ).decode()
    return {"Authorization": f"Basic {creds}"}


async def repliz_get(path: str, params: Optional[dict] = None) -> dict:
    """GET request to Repliz API."""
    url = f"{settings.REPLIZ_BASE_URL}{path}"
    headers = repliz_auth_header()
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers=headers, params=params)
    if resp.status_code == 401:
        raise HTTPException(status_code=502, detail="Repliz auth failed - check credentials")
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


async def repliz_post(path: str, json_body: Optional[dict] = None) -> dict | None:
    """POST request to Repliz API."""
    url = f"{settings.REPLIZ_BASE_URL}{path}"
    headers = repliz_auth_header()
    headers["Content-Type"] = "application/json"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, headers=headers, json=json_body or {})
    if resp.status_code == 401:
        raise HTTPException(status_code=502, detail="Repliz auth failed - check credentials")
    if resp.status_code == 204:
        return None
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


async def repliz_put(path: str, json_body: Optional[dict] = None) -> dict | None:
    """PUT request to Repliz API."""
    url = f"{settings.REPLIZ_BASE_URL}{path}"
    headers = repliz_auth_header()
    headers["Content-Type"] = "application/json"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.put(url, headers=headers, json=json_body or {})
    if resp.status_code == 401:
        raise HTTPException(status_code=502, detail="Repliz auth failed - check credentials")
    if resp.status_code == 204:
        return None
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


async def repliz_delete(path: str, params: Optional[dict] = None) -> None:
    """DELETE request to Repliz API."""
    url = f"{settings.REPLIZ_BASE_URL}{path}"
    headers = repliz_auth_header()
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.delete(url, headers=headers, params=params)
    if resp.status_code == 401:
        raise HTTPException(status_code=502, detail="Repliz auth failed - check credentials")
    if resp.status_code not in (200, 204):
        raise HTTPException(status_code=resp.status_code, detail=resp.text)

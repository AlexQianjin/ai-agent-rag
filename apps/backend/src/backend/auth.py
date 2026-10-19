"""Verify a Better Auth session for FastAPI routes."""

from typing import Annotated

import httpx
from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel

from backend.config import get_settings


class AuthenticatedUser(BaseModel):
    id: str
    email: str
    name: str
    role: str | None = None


def get_current_user(request: Request) -> AuthenticatedUser:
    """Load the signed-in user from the auth service.

    The browser session cookie, or an Authorization header, is forwarded to
    Better Auth's get-session endpoint. Routes that depend on this function
    reject requests that do not carry a valid session.
    """
    settings = get_settings()
    headers: dict[str, str] = {}
    cookie = request.headers.get("cookie")
    authorization = request.headers.get("authorization")
    if cookie:
        headers["cookie"] = cookie
    if authorization:
        headers["authorization"] = authorization
    if not headers:
        raise HTTPException(status_code=401, detail="Authentication required")

    url = f"{settings.auth_url.rstrip('/')}/api/auth/get-session"
    try:
        response = httpx.get(url, headers=headers, timeout=5.0)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Auth service is unavailable") from exc

    if response.status_code != 200:
        raise HTTPException(status_code=401, detail="Authentication required")

    payload = response.json()
    user = payload.get("user") if isinstance(payload, dict) else None
    if not isinstance(user, dict) or not user.get("id"):
        raise HTTPException(status_code=401, detail="Authentication required")

    role = user.get("role")
    return AuthenticatedUser(
        id=str(user["id"]),
        email=str(user.get("email") or ""),
        name=str(user.get("name") or ""),
        role=str(role) if role else None,
    )


CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]

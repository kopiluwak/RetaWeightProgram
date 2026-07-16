"""Shared FastAPI dependencies: settings, email sender, current-user auth."""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings, get_settings
from .database import get_db
from .email_sender import EmailSender, build_email_sender
from .models import User
from .security import decode_access_token

_email_sender: EmailSender | None = None

# Declares the bearer scheme so Swagger renders the global "Authorize" button.
bearer_scheme = HTTPBearer(auto_error=False)


def get_email_sender(settings: Settings = Depends(get_settings)) -> EmailSender:
    """FastAPI dependency: lazily build and reuse a process-wide email sender."""
    global _email_sender
    if _email_sender is None:
        _email_sender = build_email_sender(settings)
    return _email_sender


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """FastAPI dependency: resolve the authenticated user from the bearer token.

    Raises 401 for a missing/invalid/expired token, an unknown user, or a
    token whose epoch no longer matches (i.e. a revoked session).
    """
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    token = creds.credentials
    try:
        payload = decode_access_token(token)
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")

    user = (await db.execute(select(User).where(User.id == payload["sub"]))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    # F4 instant revocation: token must match the user's current epoch.
    if payload.get("epoch") != user.token_epoch:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session revoked")
    return user

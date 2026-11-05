"""Shared FastAPI dependencies: settings, email sender, current-user auth, quota."""
from __future__ import annotations

import datetime as dt
import logging
from typing import Literal

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from . import billing
from .config import Settings, get_settings
from .database import get_db
from .email_sender import EmailSender, build_email_sender
from .models import Entitlement, User
from .security import decode_access_token

_log = logging.getLogger(__name__)

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


# ----------------------------------------------------------------------------
# Quota enforcement (StoreKit monetization — arithmetic in app/billing.py)
# ----------------------------------------------------------------------------
async def get_or_create_entitlement(db: AsyncSession, user_id: str) -> Entitlement:
    """This user's entitlement row, created empty (free tier) on first touch.

    Lazily created rather than written at signup so the feature needs no
    backfill: existing accounts get a row the first time they hit anything that
    cares. The INSERT is retried-by-SELECT on a unique-violation because two
    concurrent first requests would otherwise both try to create it.
    """
    row = (await db.execute(
        select(Entitlement).where(Entitlement.user_id == user_id)
    )).scalar_one_or_none()
    if row is not None:
        return row
    try:
        async with db.begin_nested():
            row = Entitlement(user_id=user_id, revenuecat_app_user_id=user_id)
            db.add(row)
        return row
    except IntegrityError:
        # Lost the race — the other request created it.
        return (await db.execute(
            select(Entitlement).where(Entitlement.user_id == user_id)
        )).scalar_one()


class QuotaGuard:
    """A reserved-but-unspent unit of quota, handed to the endpoint.

    The contract, and the reason this is not a plain decrement in the
    dependency: **entry reserves, success commits.** `require_quota` only
    *checks* that quota exists; the endpoint calls `await quota.commit()` after
    the expensive provider call returns. A Bedrock timeout, a 502, or any
    exception on the way there means `commit()` never runs and the user keeps
    their scan.

    `commit()` is:
      * idempotent — a second call is a no-op, so a retry loop can't spend twice;
      * a no-op for an unlimited (`pro`) reservation;
      * an atomic conditional UPDATE (`... WHERE remaining > 0`), so two
        requests that both passed the reservation check can still never drive a
        counter below zero.

    It commits its own transaction rather than riding on the endpoint's,
    because several metered endpoints (pantry scan, recipe adapt, surprise-me)
    never commit anything of their own — the debit would be discarded when the
    session closed.
    """

    def __init__(self, kind: str, db: AsyncSession, row: Entitlement,
                 reservation: billing.Reservation) -> None:
        self.kind = kind
        self._db = db
        self._row = row
        self._reservation = reservation

    @property
    def unlimited(self) -> bool:
        """True when an active subscription covers this kind."""
        return self._reservation.unlimited

    @property
    def committed(self) -> bool:
        """True once the unit has been spent."""
        return self._reservation.committed

    async def commit(self) -> None:
        """Spend the reserved unit. Call only after the provider call succeeded."""
        if self._reservation.committed or self._reservation.unlimited:
            self._reservation.committed = True
            return
        self._reservation.committed = True
        column = getattr(Entitlement, billing.COLUMN_FOR_KIND[self.kind])
        await self._db.execute(
            update(Entitlement)
            .where(Entitlement.user_id == self._row.user_id, column > 0)
            .values({column: column - 1,
                     Entitlement.updated_at: dt.datetime.now(dt.timezone.utc)})
            .execution_options(synchronize_session=False)
        )
        await self._db.commit()
        # The UPDATE bypassed the ORM (deliberately — it has to be atomic), so
        # refresh explicitly rather than relying on expiry: the session is
        # expire_on_commit=False, and a lazily-expired attribute would blow up
        # with MissingGreenlet if something read it later in the request.
        await self._db.refresh(self._row)


def require_quota(kind: Literal["equipment_scan", "meal_scan", "program_gen"]):
    """Dependency factory: gate an endpoint on remaining quota.

    Returns 402 with a machine-readable body the app keys its paywall off::

        {"error": "quota_exhausted", "kind": "equipment_scan",
         "paywall": "steel_equipment_pack_5"}

    402 (not 403) on purpose: it is specifically "payment required", so the
    client can intercept the status code centrally and route to the paywall
    without inspecting every response body.

    The body is that object exactly — not wrapped in FastAPI's usual
    ``{"detail": ...}`` envelope — because the app parses it directly. That is
    what the `billing.QuotaExhausted` handler registered in `main.py` is for;
    raising `HTTPException` here would nest it one level deeper.

    The dependency RESERVES; it does not decrement. See `QuotaGuard`.
    """
    if kind not in billing.COLUMN_FOR_KIND:
        raise ValueError(f"unknown quota kind: {kind}")

    async def _dependency(
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> QuotaGuard:
        row = await get_or_create_entitlement(db, user.id)
        if not get_settings().billing_enforce:
            # Enforcement off: an unlimited reservation, so commit() is a no-op
            # and nothing is ever debited or refused.
            return QuotaGuard(kind, db, row, billing.Reservation(kind=kind, unlimited=True))
        state = billing.EntitlementState.from_row(row)
        # Raises billing.QuotaExhausted -> 402 with the paywall body.
        reservation = billing.reserve(state, kind)
        return QuotaGuard(kind, db, row, reservation)

    return _dependency

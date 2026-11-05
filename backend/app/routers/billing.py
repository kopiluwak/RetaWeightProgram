"""Billing router: entitlement status, post-purchase reconcile, RevenueCat webhook.

  GET  /billing/status              what this user has, what's left, show paywall?
  POST /billing/sync                reconcile against RevenueCat right now
  POST /billing/revenuecat/webhook  RevenueCat -> us (idempotent on event id)

All of the arithmetic lives in `app/billing.py` (pure, unit-tested). This file
is the I/O around it: read the row, ask the store, fold the event in, write the
row back.

Why both a webhook AND a sync endpoint: the webhook is the reliable path but
lags several seconds, which is an eternity while the user stares at a spinner
after paying. So the app calls `/billing/sync` immediately after a purchase and
the webhook arrives whenever it arrives. Both write through the SAME
append-only ledger keyed by a UNIQUE event id (RevenueCat's for the webhook, a
deterministic derived one for sync — `billing.sync_event_id`), so the two
racing over one purchase can never credit it twice.
"""
from __future__ import annotations

import datetime as dt
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .. import billing
from ..config import Settings, get_settings
from ..database import get_db
from ..deps import get_current_user, get_or_create_entitlement
from ..models import Entitlement, PurchaseEvent, User

router = APIRouter(prefix="/billing", tags=["billing"])

_log = logging.getLogger(__name__)


def _now() -> dt.datetime:
    """Timezone-aware UTC now."""
    return dt.datetime.now(dt.timezone.utc)


# ----------------------------------------------------------------------------
# Response shapes
# ----------------------------------------------------------------------------
class BillingStatusOut(BaseModel):
    """Everything the app needs to render entitlement state and the paywall.

    The client displays this; it never decides it. `-1` on a quota means
    unlimited (an active `pro` subscription).
    """

    tier: str                                   # free | starter | pro
    equipment_scans_remaining: int              # -1 = unlimited
    meal_scans_remaining: int
    program_gens_remaining: int
    trial_ends_at: str | None                   # ISO8601, starter window deadline
    trial_seconds_left: int
    pro_expires_at: str | None
    paywall_required: bool                      # can't do the next equipment scan
    app_user_id: str                            # RevenueCat App User ID (= users.id)
    products: dict[str, str]                    # role -> App Store product id
    provider: str                               # stub | revenuecat


def _status_out(user: User, state: billing.EntitlementState,
                provider_name: str, now: dt.datetime | None = None) -> BillingStatusOut:
    """Project an entitlement state into the wire shape."""
    at = now or _now()
    quotas = billing.quota_snapshot(state, at)
    return BillingStatusOut(
        tier=billing.resolve_tier(state, at),
        equipment_scans_remaining=quotas["equipment_scan"],
        meal_scans_remaining=quotas["meal_scan"],
        program_gens_remaining=quotas["program_gen"],
        trial_ends_at=state.trial_ends_at.isoformat() if billing.starter_window_open(state, at) else None,
        trial_seconds_left=billing.trial_seconds_left(state, at),
        pro_expires_at=state.pro_expires_at.isoformat() if billing.pro_active(state, at) and state.pro_expires_at else None,
        paywall_required=billing.paywall_required(state, at),
        app_user_id=user.id,
        products={
            "starter": billing.PRODUCT_STARTER_UNLOCK,
            "pro": billing.PRODUCT_PRO_MONTHLY,
            "equipment_pack": billing.PRODUCT_EQUIPMENT_PACK,
            "program_pack": billing.PRODUCT_PROGRAM_PACK,
        },
        provider=provider_name,
    )


# ----------------------------------------------------------------------------
# Persistence helpers
# ----------------------------------------------------------------------------
def _write_state(row: Entitlement, state: billing.EntitlementState) -> None:
    """Copy a computed state back onto the ORM row (no commit)."""
    for column, value in state.to_row_values().items():
        setattr(row, column, value)


async def _claim_event(db: AsyncSession, *, event_id: str, user_id: str,
                       product_id: str, event_type: str, payload: dict) -> bool:
    """Insert the ledger row, or report that this event was already handled.

    The UNIQUE index on `event_id` is what actually enforces idempotency, so
    the claim is an INSERT rather than a SELECT-then-INSERT: two concurrent
    deliveries of the same event (the classic webhook + sync race) cannot both
    see "not there yet" and both credit. The loser gets an IntegrityError.

    Wrapped in a SAVEPOINT because on Postgres a failed statement poisons the
    whole transaction — without it, a duplicate would take the rest of the
    request down with it.
    """
    try:
        async with db.begin_nested():
            db.add(PurchaseEvent(
                event_id=event_id, user_id=user_id, product_id=product_id[:64],
                event_type=(event_type or "UNKNOWN")[:32], raw_payload=payload,
            ))
    except IntegrityError:
        return False
    return True


async def _starter_already_granted(db: AsyncSession, user_id: str) -> bool:
    """Has this user ever been credited the non-consumable starter unlock?

    A restore, a reinstall or a second device re-delivers the same purchase,
    and a non-consumable must only ever grant once.
    """
    found = (await db.execute(
        select(PurchaseEvent.id).where(
            PurchaseEvent.user_id == user_id,
            PurchaseEvent.product_id == billing.PRODUCT_STARTER_UNLOCK,
        ).limit(1)
    )).first()
    return found is not None


# ----------------------------------------------------------------------------
# Endpoints
# ----------------------------------------------------------------------------
@router.get("/status", response_model=BillingStatusOut)
async def billing_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Current tier, remaining quotas, trial expiry, and whether to show the paywall.

    Read-only apart from lazily creating the row, and cheap enough for the app
    to call after every purchase and on every screen that shows a quota badge.
    """
    row = await get_or_create_entitlement(db, user.id)
    state = billing.EntitlementState.from_row(row)
    # Reflect a lapsed starter window in the stored row too, so the counters a
    # human reads in the DB match what the API reports.
    expired = billing.expire_window(state)
    if expired != state:
        _write_state(row, expired)
        await db.commit()
        state = expired
    return _status_out(user, state, settings.billing_provider)


@router.post("/sync", response_model=BillingStatusOut)
async def billing_sync(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Reconcile this user against RevenueCat right now.

    Called by the app immediately after a purchase completes, because webhooks
    lag several seconds and the user is waiting. Also the repair path: if a
    webhook was ever missed, this recomputes from the store's own view —
    including revoking `pro` when the store says it is gone.
    """
    row = await get_or_create_entitlement(db, user.id)
    state = billing.EntitlementState.from_row(row)
    now = _now()

    if settings.billing_provider == "revenuecat" and not settings.revenuecat_secret_key:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Billing is not configured (REVENUECAT_SECRET_KEY missing)")
    provider = billing.build_billing_provider(settings)

    try:
        snapshot = await provider.fetch_subscriber(user.id)
    except Exception as exc:  # network / RevenueCat outage
        _log.error("billing sync failed for one user: %s", exc)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            "Couldn't reach the store — your purchase is safe, try again")

    row.revenuecat_app_user_id = snapshot.app_user_id[:64]

    # Subscription state is absolute, not incremental, so it is safe (and
    # correct) to just assert it on every sync.
    if snapshot.has_pro:
        state = billing.grant_pro(state, snapshot.pro_expires_at, now)
    elif billing.pro_active(state, now):
        # The store says no active subscription but we still think there is one
        # — a missed EXPIRATION. Trust the store.
        _log.info("billing sync: revoking stale pro entitlement")
        state = billing.revoke_pro(state, now)

    # The non-consumable starter unlock: credited exactly once, ever.
    if snapshot.has_starter and not await _starter_already_granted(db, user.id):
        claimed = await _claim_event(
            db, event_id=billing.sync_event_id(user.id, billing.PRODUCT_STARTER_UNLOCK),
            user_id=user.id, product_id=billing.PRODUCT_STARTER_UNLOCK,
            event_type="SYNC_GRANT", payload={"source": snapshot.source},
        )
        if claimed:
            state = billing.grant_starter(state, now)

    # Consumables: one ledger row per RevenueCat transaction id, so a pack is
    # credited once whether it arrives here or by webhook first.
    for product_id, transaction_id in snapshot.purchases():
        if product_id not in (billing.PRODUCT_EQUIPMENT_PACK, billing.PRODUCT_PROGRAM_PACK):
            continue
        claimed = await _claim_event(
            db, event_id=billing.sync_event_id(user.id, product_id, transaction_id),
            user_id=user.id, product_id=product_id, event_type="SYNC_GRANT",
            payload={"source": snapshot.source, "transaction_id": transaction_id},
        )
        if claimed:
            state = billing.credit_pack(state, product_id, now)

    _write_state(row, state)
    await db.commit()
    return _status_out(user, state, settings.billing_provider, now)


@router.post("/revenuecat/webhook", include_in_schema=False)
async def revenuecat_webhook(
    request: Request,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """RevenueCat -> us. Idempotent on the event id; always 200 on a replay.

    Deliberately forgiving about *content* and strict about *authentication*:

      * a bad or missing shared secret is a 401 (fail closed — an unset
        `REVENUECAT_WEBHOOK_SECRET` rejects everything rather than accepting
        anything);
      * an event we can't attribute, can't parse, or don't handle answers 200,
        because a non-2xx makes RevenueCat retry forever and no amount of
        retrying will make an unparseable body parse.

    Note there is no `get_current_user` here: RevenueCat has no session. The
    shared secret IS the authentication, which is why it is checked first and
    with `secrets.compare_digest`.
    """
    if not billing.verify_shared_secret(authorization, settings.revenuecat_webhook_secret):
        _log.warning("revenuecat webhook rejected: bad or missing shared secret")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid webhook credentials")

    payload = await request.json()
    event = billing.parse_webhook_event(payload)
    if event is None:
        _log.warning("revenuecat webhook: unusable body (no event id or app_user_id)")
        return {"status": "ignored"}

    # The App User ID is our users.id (BillingContext configures it that way).
    user = (await db.execute(select(User).where(User.id == event.app_user_id))).scalar_one_or_none()
    if user is None:
        # Also try the recorded mapping, in case an anonymous RevenueCat id was
        # aliased to the real one after login.
        user = (await db.execute(
            select(User).join(Entitlement, Entitlement.user_id == User.id)
            .where(Entitlement.revenuecat_app_user_id == event.app_user_id)
        )).scalar_one_or_none()
    if user is None:
        _log.warning("revenuecat webhook %s for unknown app_user_id", event.event_type)
        return {"status": "unknown_user"}

    row = await get_or_create_entitlement(db, user.id)
    state = billing.EntitlementState.from_row(row)

    # Whether the starter was already credited must be read BEFORE the claim
    # inserts this event's own ledger row.
    already = await _starter_already_granted(db, user.id)

    if not await _claim_event(db, event_id=event.event_id, user_id=user.id,
                              product_id=event.product_id, event_type=event.event_type,
                              payload=payload):
        # Replay. 200 so RevenueCat stops retrying; nothing credited.
        _log.info("revenuecat webhook replay ignored (event already applied)")
        return {"status": "duplicate"}

    new_state = billing.apply_event(
        state, event.event_type, event.product_id,
        expires_at=event.expires_at, now=_now(), starter_already_granted=already,
    )
    _write_state(row, new_state)
    row.revenuecat_app_user_id = event.app_user_id[:64]
    await db.commit()
    _log.info("revenuecat webhook applied: %s %s", event.event_type, event.product_id or "-")
    return {"status": "ok"}

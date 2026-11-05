"""Monetization logic: quota arithmetic, trial windows, entitlement resolution.

Pure module, in the same spirit as `gamification.py` and `couch.py`: no FastAPI
imports and no DB session, so every rule below is unit-testable without a
server (`tests/test_billing.py`). The router owns persistence and HTTP; this
file owns *what the numbers should be*.

Commercial model implemented here
---------------------------------
``steel_starter_unlock``   NON-CONSUMABLE, $14.99 — 5 equipment scans + 7
                           meal-prep scans, usable within 7 days of purchase,
                           whichever limit is hit first; plus 10 program
                           generations that do NOT expire with that window
                           (added 2026-11-05 — before that a buyer could scan
                           but hit a second paywall at their first program).
``steel_pro_monthly``      AUTO-RENEWING — unlimited meal-prep scanning, recipe
                           generation and program regeneration.
``steel_equipment_pack_5`` CONSUMABLE — +5 equipment scans.
``steel_program_pack_3``   CONSUMABLE — +3 program generations.

RevenueCat entitlement identifiers: ``starter`` and ``pro``.

Three rules are worth stating once, because everything else follows from them:

1. **The starter window forfeits its own leftovers, and nothing else's.**
   ``trial_ends_at`` is the deadline of the current starter grant. Once it
   passes, starter scans are gone (that is what "within 7 days" means), but a
   consumable pack bought afterwards must not be eaten by the stale deadline —
   so `credit_pack` expires the window *first*, then adds the pack.
2. **Pro is unlimited for meal scans and program generations only.** Equipment
   scanning stays metered even for a subscriber, which is why
   ``steel_equipment_pack_5`` is still a sensible thing to sell them.
3. **Nothing is consumed until the expensive call succeeded.** The dependency
   reserves (a read-only check), the endpoint commits after the provider
   returns. A Bedrock timeout costs the user nothing. `Reservation` below is
   the pure half of that; `deps.require_quota` is the DB half.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, replace
from typing import Any, Literal, Protocol

_log = logging.getLogger(__name__)

# --- Product / entitlement identifiers (must match App Store Connect) --------
PRODUCT_STARTER_UNLOCK = "steel_starter_unlock"
PRODUCT_PRO_MONTHLY = "steel_pro_monthly"
PRODUCT_EQUIPMENT_PACK = "steel_equipment_pack_5"
PRODUCT_PROGRAM_PACK = "steel_program_pack_3"

ENTITLEMENT_STARTER = "starter"
ENTITLEMENT_PRO = "pro"

TIER_FREE = "free"
TIER_STARTER = "starter"
TIER_PRO = "pro"

# --- Grant sizes -------------------------------------------------------------
STARTER_EQUIPMENT_SCANS = 5
STARTER_MEAL_SCANS = 7
STARTER_WINDOW_DAYS = 7
STARTER_PROGRAM_GENS = 10   # not forfeited when the window lapses
EQUIPMENT_PACK_SCANS = 5
PROGRAM_PACK_GENS = 3

QuotaKind = Literal["equipment_scan", "meal_scan", "program_gen"]

#: Quota kind -> the Entitlement column that counts it. The router does the
#: actual UPDATE; keeping the mapping here means one place defines the link.
COLUMN_FOR_KIND: dict[str, str] = {
    "equipment_scan": "equipment_scans_remaining",
    "meal_scan": "meal_scans_remaining",
    "program_gen": "program_gens_remaining",
}

#: What an active `pro` subscription makes unlimited. Equipment scanning is
#: deliberately absent (see module docstring, rule 2).
PRO_UNLIMITED_KINDS = frozenset({"meal_scan", "program_gen"})

#: Which product the paywall should push when a given quota runs out. This is
#: the value the app keys its paywall off, so it travels in the 402 body.
PAYWALL_PRODUCT_FOR_KIND: dict[str, str] = {
    "equipment_scan": PRODUCT_EQUIPMENT_PACK,
    "meal_scan": PRODUCT_PRO_MONTHLY,
    "program_gen": PRODUCT_PROGRAM_PACK,
}

#: Sentinel for "no limit" — distinct from a large number so callers can't
#: accidentally decrement it into a limit.
UNLIMITED = -1

#: Webhook event types we act on. Anything else is stored and ignored (see
#: `apply_event`), which is what keeps a new RevenueCat event type from 500ing.
HANDLED_EVENT_TYPES = (
    "INITIAL_PURCHASE",
    "RENEWAL",
    "NON_RENEWING_PURCHASE",
    "CANCELLATION",
    "EXPIRATION",
    "PRODUCT_CHANGE",
    "BILLING_ISSUE",
    "REFUND",
)


def _now() -> dt.datetime:
    """Timezone-aware UTC now."""
    return dt.datetime.now(dt.timezone.utc)


def _aware(value: dt.datetime | None) -> dt.datetime | None:
    """Coerce a possibly-naive DB timestamp to UTC-aware.

    Same guard as deletion.py: rows written before a column was tz-aware come
    back naive, and comparing those to an aware now() raises TypeError — which
    here would mean a paying user getting a 402.
    """
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)


# ----------------------------------------------------------------------------
# Entitlement state
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class EntitlementState:
    """Immutable snapshot of one user's entitlements.

    Mirrors the `Entitlement` row field-for-field so the router can round-trip
    it (`from_row` / `to_row_values`) without this module importing the ORM.
    """

    tier: str = TIER_FREE
    pro_expires_at: dt.datetime | None = None
    equipment_scans_remaining: int = 0
    meal_scans_remaining: int = 0
    program_gens_remaining: int = 0
    trial_ends_at: dt.datetime | None = None

    @classmethod
    def from_row(cls, row: Any) -> "EntitlementState":
        """Build a snapshot from an `Entitlement` ORM row (or any duck-type)."""
        if row is None:
            return cls()
        return cls(
            tier=row.tier or TIER_FREE,
            pro_expires_at=_aware(row.pro_expires_at),
            equipment_scans_remaining=int(row.equipment_scans_remaining or 0),
            meal_scans_remaining=int(row.meal_scans_remaining or 0),
            program_gens_remaining=int(row.program_gens_remaining or 0),
            trial_ends_at=_aware(row.trial_ends_at),
        )

    def to_row_values(self) -> dict[str, Any]:
        """Column name -> value, for writing back onto an `Entitlement` row."""
        return {
            "tier": self.tier,
            "pro_expires_at": self.pro_expires_at,
            "equipment_scans_remaining": self.equipment_scans_remaining,
            "meal_scans_remaining": self.meal_scans_remaining,
            "program_gens_remaining": self.program_gens_remaining,
            "trial_ends_at": self.trial_ends_at,
        }


# ----------------------------------------------------------------------------
# Window + tier resolution
# ----------------------------------------------------------------------------
def pro_active(state: EntitlementState, now: dt.datetime | None = None) -> bool:
    """True while a `pro` subscription is still valid.

    A missing expiry means "active until we hear otherwise" — RevenueCat sends
    EXPIRATION when it actually lapses, and refusing service because a webhook
    omitted a date would be the wrong way to fail.
    """
    if state.tier != TIER_PRO:
        return False
    expires = _aware(state.pro_expires_at)
    return expires is None or (now or _now()) < expires


def starter_window_open(state: EntitlementState, now: dt.datetime | None = None) -> bool:
    """True while the current starter grant is still inside its 7-day window."""
    ends = _aware(state.trial_ends_at)
    return ends is not None and (now or _now()) <= ends


def trial_seconds_left(state: EntitlementState, now: dt.datetime | None = None) -> int:
    """Whole seconds left in the starter window (0 when closed/absent)."""
    ends = _aware(state.trial_ends_at)
    if ends is None:
        return 0
    return max(0, int((ends - (now or _now())).total_seconds()))


def expire_window(state: EntitlementState, now: dt.datetime | None = None) -> EntitlementState:
    """Forfeit a lapsed starter grant. Idempotent; a no-op while it's open.

    Zeroes the scan counters the starter granted and clears the deadline, so a
    later consumable pack lands on a clean slate instead of inheriting an
    already-expired window. Program generations are left alone on purpose:
    the starter's 10 builds are not window-limited.
    """
    if state.trial_ends_at is None or starter_window_open(state, now):
        return state
    return replace(
        state,
        equipment_scans_remaining=0,
        meal_scans_remaining=0,
        trial_ends_at=None,
        tier=TIER_PRO if state.tier == TIER_PRO else TIER_FREE,
    )


def resolve_tier(state: EntitlementState, now: dt.datetime | None = None) -> str:
    """The tier to *report* — computed, never trusted from the stored string.

    Pro outranks starter; starter only counts while its window is open. A row
    left saying "pro" after an EXPIRATION we missed still reports free.
    """
    if pro_active(state, now):
        return TIER_PRO
    if starter_window_open(state, now):
        return TIER_STARTER
    return TIER_FREE


def remaining(state: EntitlementState, kind: str, now: dt.datetime | None = None) -> int:
    """Quota left for `kind`: a count, or `UNLIMITED` for an active subscriber."""
    if kind not in COLUMN_FOR_KIND:
        raise ValueError(f"unknown quota kind: {kind}")
    if pro_active(state, now) and kind in PRO_UNLIMITED_KINDS:
        return UNLIMITED
    current = expire_window(state, now)
    return int(getattr(current, COLUMN_FOR_KIND[kind]))


def has_quota(state: EntitlementState, kind: str, now: dt.datetime | None = None) -> bool:
    """True when one more `kind` call is allowed right now."""
    left = remaining(state, kind, now)
    return left == UNLIMITED or left > 0


def debit(state: EntitlementState, kind: str, now: dt.datetime | None = None) -> EntitlementState:
    """Consume one unit of `kind`. Unlimited kinds and empty counters no-op.

    Never goes negative: a counter at 0 stays at 0 rather than wrapping into a
    debt the next purchase would silently pay off.
    """
    if pro_active(state, now) and kind in PRO_UNLIMITED_KINDS:
        return state
    current = expire_window(state, now)
    column = COLUMN_FOR_KIND[kind]
    left = int(getattr(current, column))
    if left <= 0:
        return current
    return replace(current, **{column: left - 1})


def quota_snapshot(state: EntitlementState, now: dt.datetime | None = None) -> dict[str, int]:
    """All three quotas at once, for `GET /billing/status`."""
    return {kind: remaining(state, kind, now) for kind in COLUMN_FOR_KIND}


def paywall_required(state: EntitlementState, now: dt.datetime | None = None) -> bool:
    """True when the user cannot do the gated first thing (an equipment scan).

    The gate is at FIRST SCAN, not signup: onboarding and the generated program
    come first, so this is deliberately narrow.
    """
    return not has_quota(state, "equipment_scan", now)


def paywall_product(kind: str) -> str:
    """Product id the app should present when `kind` is exhausted."""
    return PAYWALL_PRODUCT_FOR_KIND.get(kind, PRODUCT_STARTER_UNLOCK)


def quota_error_body(kind: str) -> dict[str, str]:
    """The machine-readable 402 body the app keys its paywall off."""
    return {"error": "quota_exhausted", "kind": kind, "paywall": paywall_product(kind)}


# ----------------------------------------------------------------------------
# Grants
# ----------------------------------------------------------------------------
def grant_starter(state: EntitlementState, now: dt.datetime | None = None) -> EntitlementState:
    """Apply a `steel_starter_unlock` purchase: 5 + 7 scans in a 7-day window,
    plus 10 program generations that outlive the window.

    Non-consumable, so a re-delivered purchase (a restore, a second device)
    must NOT re-grant. `starter_already_granted` is how the router decides;
    reaching here means it is a genuinely new grant.
    """
    at = now or _now()
    base = expire_window(state, at)
    return replace(
        base,
        tier=TIER_PRO if pro_active(base, at) else TIER_STARTER,
        equipment_scans_remaining=base.equipment_scans_remaining + STARTER_EQUIPMENT_SCANS,
        meal_scans_remaining=base.meal_scans_remaining + STARTER_MEAL_SCANS,
        program_gens_remaining=base.program_gens_remaining + STARTER_PROGRAM_GENS,
        trial_ends_at=at + dt.timedelta(days=STARTER_WINDOW_DAYS),
    )


def credit_pack(state: EntitlementState, product_id: str,
                now: dt.datetime | None = None) -> EntitlementState:
    """Apply a consumable pack. Stacks on top of anything, including `pro`.

    Expires a lapsed starter window first (rule 1) so the pack the user just
    paid for is never zeroed by an old deadline.
    """
    base = expire_window(state, now)
    if product_id == PRODUCT_EQUIPMENT_PACK:
        return replace(base,
                       equipment_scans_remaining=base.equipment_scans_remaining + EQUIPMENT_PACK_SCANS)
    if product_id == PRODUCT_PROGRAM_PACK:
        return replace(base,
                       program_gens_remaining=base.program_gens_remaining + PROGRAM_PACK_GENS)
    return base


def grant_pro(state: EntitlementState, expires_at: dt.datetime | None,
              now: dt.datetime | None = None) -> EntitlementState:
    """Start or renew `pro`. Leaves consumable counters untouched."""
    base = expire_window(state, now)
    return replace(base, tier=TIER_PRO, pro_expires_at=_aware(expires_at))


def revoke_pro(state: EntitlementState, now: dt.datetime | None = None) -> EntitlementState:
    """End `pro` immediately (EXPIRATION / REFUND).

    Falls back to starter if that window is somehow still open, else free.
    CANCELLATION is NOT this: a cancelled subscription is paid up to the end of
    its period, so it keeps serving until EXPIRATION arrives.
    """
    at = now or _now()
    base = replace(state, tier=TIER_FREE, pro_expires_at=None)
    base = expire_window(base, at)
    if starter_window_open(base, at):
        return replace(base, tier=TIER_STARTER)
    return base


def refund(state: EntitlementState, product_id: str,
           now: dt.datetime | None = None) -> EntitlementState:
    """Claw back what a refunded product granted.

    Consumables are zeroed rather than decremented by the pack size: the user
    has been given their money back, and a partially-spent pack should not
    leave a usable remainder. Counters never go negative.
    """
    at = now or _now()
    if product_id == PRODUCT_PRO_MONTHLY:
        return revoke_pro(state, at)
    if product_id == PRODUCT_STARTER_UNLOCK:
        return replace(state, equipment_scans_remaining=0, meal_scans_remaining=0,
                       program_gens_remaining=max(
                           0, state.program_gens_remaining - STARTER_PROGRAM_GENS),
                       trial_ends_at=None,
                       tier=TIER_PRO if pro_active(state, at) else TIER_FREE)
    if product_id == PRODUCT_EQUIPMENT_PACK:
        return replace(state, equipment_scans_remaining=0)
    if product_id == PRODUCT_PROGRAM_PACK:
        return replace(state, program_gens_remaining=0)
    return state


def apply_event(state: EntitlementState, event_type: str, product_id: str,
                expires_at: dt.datetime | None = None,
                now: dt.datetime | None = None,
                starter_already_granted: bool = False) -> EntitlementState:
    """Fold one purchase event into an entitlement state. Pure.

    Deliberately total: an unrecognised event type or product returns the state
    unchanged rather than raising, because a webhook that 500s gets retried
    forever and RevenueCat ships new event types without asking us.

    `starter_already_granted` is the router's answer to "have we credited this
    non-consumable before?" (a ledger lookup). Consumables intentionally ignore
    it — buying a second pack SHOULD credit again; replay protection for those
    is the UNIQUE event id, not the product.
    """
    at = now or _now()

    if event_type in ("INITIAL_PURCHASE", "RENEWAL", "NON_RENEWING_PURCHASE", "PRODUCT_CHANGE"):
        if product_id == PRODUCT_PRO_MONTHLY:
            return grant_pro(state, expires_at, at)
        if product_id == PRODUCT_STARTER_UNLOCK:
            return state if starter_already_granted else grant_starter(state, at)
        if product_id in (PRODUCT_EQUIPMENT_PACK, PRODUCT_PROGRAM_PACK):
            return credit_pack(state, product_id, at)
        return state

    if event_type == "EXPIRATION":
        if product_id == PRODUCT_PRO_MONTHLY or product_id == "":
            return revoke_pro(state, at)
        return expire_window(state, at)

    if event_type == "REFUND":
        return refund(state, product_id, at)

    # CANCELLATION = auto-renew switched off, still paid until the period ends.
    # BILLING_ISSUE = a retry window, not a lapse. Both keep access; the
    # EXPIRATION that may follow is what actually revokes it.
    if event_type in ("CANCELLATION", "BILLING_ISSUE"):
        return state

    _log.info("billing: ignoring unhandled event type %r", event_type)
    return state


# ----------------------------------------------------------------------------
# Webhook / sync plumbing (pure — the router only does I/O around this)
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class WebhookEvent:
    """One normalised RevenueCat webhook event."""

    event_id: str
    event_type: str
    app_user_id: str
    product_id: str = ""
    expires_at: dt.datetime | None = None
    entitlement_ids: tuple[str, ...] = ()


def parse_webhook_event(payload: dict) -> WebhookEvent | None:
    """Pull the fields we act on out of a webhook body.

    Returns None when the body has no event id or no app user id — without
    either we can neither deduplicate nor attribute it, and acting on it would
    be worse than dropping it (the router answers 200 so RevenueCat stops
    retrying a body we will never be able to use).
    """
    event = (payload or {}).get("event") or {}
    if not isinstance(event, dict):
        return None
    event_id = str(event.get("id") or "").strip()
    app_user_id = str(
        event.get("app_user_id") or event.get("original_app_user_id") or ""
    ).strip()
    if not event_id or not app_user_id:
        return None
    ents = event.get("entitlement_ids") or []
    if not isinstance(ents, list):
        ents = []
    return WebhookEvent(
        event_id=event_id[:128],
        event_type=str(event.get("type") or "").strip().upper()[:32],
        app_user_id=app_user_id,
        product_id=str(event.get("product_id") or "").strip()[:64],
        expires_at=parse_iso8601(event.get("expiration_at_ms")),
        entitlement_ids=tuple(str(e) for e in ents),
    )


def sync_event_id(app_user_id: str, product_id: str, transaction_id: str = "") -> str:
    """Deterministic ledger id for a purchase seen via `POST /billing/sync`.

    The app calls sync immediately after buying because webhooks lag several
    seconds, so the same purchase arrives twice by two routes. Deriving the id
    from the purchase itself (not from a random uuid) makes the two collide on
    the UNIQUE index, so whichever lands second is a no-op instead of a second
    credit. Consumables carry RevenueCat's per-transaction id; the
    non-consumable starter unlock has no transaction id and needs none — it is
    granted once per user by definition.
    """
    tail = transaction_id or "single"
    return f"sync:{app_user_id}:{product_id}:{tail}"[:128]


def verify_shared_secret(header_value: str | None, expected: str) -> bool:
    """Constant-time check of the webhook's Authorization header.

    Fails closed on an unset expected secret: an empty configured value must
    never mean "accept anything", or a task deployed without the env var would
    happily credit entitlements for anyone who found the URL.
    """
    if not expected:
        return False
    if not header_value:
        return False
    import secrets  # local import keeps the module's top-level surface small

    # Accept the raw secret or a "Bearer <secret>" form — RevenueCat sends
    # whatever string you type into the dashboard field.
    candidate = header_value.strip()
    if candidate.lower().startswith("bearer "):
        candidate = candidate[7:].strip()
    return secrets.compare_digest(candidate, expected)


# ----------------------------------------------------------------------------
# Reserve / commit
# ----------------------------------------------------------------------------
@dataclass
class Reservation:
    """A checked-but-not-yet-spent unit of quota.

    Created at dependency time (a read: "is there quota?"), spent by the
    endpoint only after the provider call returns. If Bedrock times out, the
    endpoint raises before `commit()` and the user keeps their scan.

    `committed` makes it idempotent, so an endpoint that commits inside a loop
    or a retry can't spend twice. The DB-backed subclass lives in deps.py.
    """

    kind: str
    unlimited: bool = False
    committed: bool = False

    def spend(self, state: EntitlementState,
              now: dt.datetime | None = None) -> EntitlementState:
        """Pure half of commit: return the debited state, once."""
        if self.committed or self.unlimited:
            self.committed = True
            return state
        self.committed = True
        return debit(state, self.kind, now)


def reserve(state: EntitlementState, kind: str,
            now: dt.datetime | None = None) -> Reservation:
    """Check quota and hand back a Reservation. Raises `QuotaExhausted` if dry."""
    left = remaining(state, kind, now)
    if left == UNLIMITED:
        return Reservation(kind=kind, unlimited=True)
    if left <= 0:
        raise QuotaExhausted(kind)
    return Reservation(kind=kind)


class QuotaExhausted(Exception):
    """No quota left for `kind`. deps.py turns this into the 402."""

    def __init__(self, kind: str) -> None:
        super().__init__(f"quota exhausted: {kind}")
        self.kind = kind
        self.body = quota_error_body(kind)


# ----------------------------------------------------------------------------
# Providers (stub | revenuecat) — mirrors recognition/neutron_parse
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class SubscriberSnapshot:
    """What the store thinks a subscriber owns, normalised across providers.

    `non_subscription_ids` carries RevenueCat's per-purchase transaction ids for
    consumables — they are what makes reconcile idempotent against the webhook.
    """

    app_user_id: str
    pro_expires_at: dt.datetime | None = None
    has_pro: bool = False
    has_starter: bool = False
    #: product_id -> [transaction id, ...] for one-off (consumable) purchases
    non_subscription_ids: dict[str, list[str]] | None = None
    source: str = "stub"

    def purchases(self) -> list[tuple[str, str]]:
        """[(product_id, transaction_id)] for every one-off purchase."""
        return [(pid, tid)
                for pid, ids in (self.non_subscription_ids or {}).items()
                for tid in ids]


class BillingProvider(Protocol):
    """Anything that can tell us what a subscriber owns."""

    name: str

    async def fetch_subscriber(self, app_user_id: str) -> SubscriberSnapshot:
        """Return the store's current view of this App User ID."""
        ...


def parse_iso8601(value: Any) -> dt.datetime | None:
    """Parse RevenueCat's timestamps ("2026-08-19T12:00:00Z" or epoch ms)."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return dt.datetime.fromtimestamp(float(value) / 1000.0, tz=dt.timezone.utc)
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    return _aware(parsed)


def parse_subscriber(payload: dict, app_user_id: str,
                     now: dt.datetime | None = None,
                     source: str = "revenuecat") -> SubscriberSnapshot:
    """Pure parser for `GET /v1/subscribers/{id}` (unit-testable, no network).

    Entitlements are read from the `entitlements` map — the identifiers
    (`starter`, `pro`) are the contract, not the product ids, so renaming a
    product in App Store Connect can't silently drop someone's access.
    """
    at = now or _now()
    sub = (payload or {}).get("subscriber", {}) or {}
    ents = sub.get("entitlements", {}) or {}

    def _active(key: str) -> tuple[bool, dt.datetime | None]:
        row = ents.get(key)
        if not isinstance(row, dict):
            return False, None
        expires = parse_iso8601(row.get("expires_date"))
        # A null expiry on a non-consumable entitlement means "forever".
        return (expires is None or expires > at), expires

    has_pro, pro_expires = _active(ENTITLEMENT_PRO)
    has_starter, _ = _active(ENTITLEMENT_STARTER)

    non_subs: dict[str, list[str]] = {}
    for product_id, rows in (sub.get("non_subscriptions", {}) or {}).items():
        ids = [str(r.get("id")) for r in (rows or []) if isinstance(r, dict) and r.get("id")]
        if ids:
            non_subs[str(product_id)] = ids

    return SubscriberSnapshot(
        app_user_id=app_user_id, pro_expires_at=pro_expires, has_pro=has_pro,
        has_starter=has_starter, non_subscription_ids=non_subs, source=source,
    )


class StubBillingProvider:
    """Deterministic offline provider, selected by `BILLING_PROVIDER=stub`.

    Same purpose as the stub recognizer and stub recipe engine: the whole
    purchase -> quota -> paywall flow must be walkable with no RevenueCat
    account and no network. It reports the starter entitlement as owned, so
    `POST /billing/sync` in a dev environment behaves like a completed
    $14.99 purchase ("simulated purchase" in the manual test walkthrough).

    It reports NO consumables — those are simulated by posting a webhook, which
    is also the path worth exercising, since that is where double-crediting
    would show up.
    """

    name = "stub"

    async def fetch_subscriber(self, app_user_id: str) -> SubscriberSnapshot:
        return SubscriberSnapshot(app_user_id=app_user_id, has_starter=True,
                                  has_pro=False, non_subscription_ids={}, source="stub")


class RevenueCatProvider:
    """Production provider: RevenueCat REST v1.

    Uses `urllib` on a worker thread rather than adding an async HTTP client —
    this is one small GET on a path the user is already waiting on, and the
    backend has no HTTP-client dependency today. (`boto3` is imported lazily in
    the Bedrock engines for the same "don't pay for the path you're not on"
    reason.)
    """

    name = "revenuecat"
    BASE_URL = "https://api.revenuecat.com/v1"
    TIMEOUT_SECONDS = 10

    def __init__(self, settings: Any) -> None:
        self._secret = settings.revenuecat_secret_key
        if not self._secret:
            raise ValueError("REVENUECAT_SECRET_KEY is not set")

    def _get(self, app_user_id: str) -> dict:
        """Blocking GET (run in a thread by fetch_subscriber)."""
        url = f"{self.BASE_URL}/subscribers/{urllib.parse.quote(app_user_id, safe='')}"
        req = urllib.request.Request(url, method="GET", headers={
            "Authorization": f"Bearer {self._secret}",
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=self.TIMEOUT_SECONDS) as resp:
            return json.loads(resp.read().decode("utf-8"))

    async def fetch_subscriber(self, app_user_id: str) -> SubscriberSnapshot:
        import asyncio  # local: keeps the module import-light for tests

        try:
            payload = await asyncio.to_thread(self._get, app_user_id)
        except urllib.error.HTTPError as exc:
            # 404 = RevenueCat has never seen this App User ID. That is the
            # normal state for a user who has not bought anything, not an error.
            if exc.code == 404:
                return SubscriberSnapshot(app_user_id=app_user_id, source=self.name)
            raise
        return parse_subscriber(payload, app_user_id, source=self.name)


def build_billing_provider(settings: Any) -> BillingProvider:
    """Factory: RevenueCat or the dev stub, per `settings.billing_provider`."""
    if settings.billing_provider == "revenuecat":
        return RevenueCatProvider(settings)
    return StubBillingProvider()

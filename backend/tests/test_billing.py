"""Unit tests for monetization logic (app/billing.py).

Run: python3 -m tests.test_billing

Pure functions only — no DB, no FastAPI, no network — matching
tests/test_couch.py and friends.

The five properties that must never silently regress, because each one is
either money we didn't earn or money we took twice:

  * a replayed webhook event id never double-credits;
  * a failed provider call never consumes a scan;
  * the starter window ends by DATE and by COUNT, whichever comes first;
  * a lapsed subscription actually revokes `pro`;
  * a consumable pack stacks on top of an active subscription.
"""
from __future__ import annotations

import datetime as dt

from app import billing as b

T0 = dt.datetime(2026, 8, 19, 12, 0, tzinfo=dt.timezone.utc)


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def _free() -> b.EntitlementState:
    return b.EntitlementState()


# --- The starter grant -------------------------------------------------------
def test_starter_grant_sizes_and_window():
    s = b.grant_starter(_free(), now=T0)
    _assert(s.equipment_scans_remaining == 5, f"equipment: {s.equipment_scans_remaining}")
    _assert(s.meal_scans_remaining == 7, f"meal: {s.meal_scans_remaining}")
    _assert(s.trial_ends_at == T0 + dt.timedelta(days=7), f"window: {s.trial_ends_at}")
    _assert(b.resolve_tier(s, T0) == "starter", f"tier: {b.resolve_tier(s, T0)}")



def test_starter_includes_ten_program_builds():
    """A $14.99 buyer must be able to build their first program without a
    second paywall (2026-11-05)."""
    s = b.grant_starter(_free(), now=T0)
    _assert(s.program_gens_remaining == 10, f"program gens: {s.program_gens_remaining}")
    _assert(b.has_quota(s, "program_gen", T0), "first program build refused")
    for _ in range(10):
        s = b.debit(s, "program_gen", T0)
    _assert(not b.has_quota(s, "program_gen", T0), "11th build allowed")


def test_starter_program_builds_survive_the_window():
    """Scans are forfeited at day 7; program builds are not."""
    s = b.grant_starter(_free(), now=T0)
    s = b.debit(s, "program_gen", T0)
    day8 = T0 + dt.timedelta(days=8)
    _assert(b.remaining(s, "equipment_scan", day8) == 0, "scans outlived the window")
    _assert(b.remaining(s, "program_gen", day8) == 9, f"builds: {b.remaining(s, 'program_gen', day8)}")
    after = b.apply_event(s, "EXPIRATION", b.PRODUCT_STARTER_UNLOCK, now=day8)
    _assert(after.program_gens_remaining == 9, "EXPIRATION ate program builds")


def test_starter_refund_claws_back_only_its_own_builds():
    """Refunding the starter removes its 10 builds but not a separately
    bought program pack's 3."""
    s = b.grant_starter(_free(), now=T0)
    s = b.credit_pack(s, b.PRODUCT_PROGRAM_PACK, T0)
    _assert(s.program_gens_remaining == 13, f"stacked: {s.program_gens_remaining}")
    s = b.refund(s, b.PRODUCT_STARTER_UNLOCK, T0)
    _assert(s.program_gens_remaining == 3, f"after refund: {s.program_gens_remaining}")
    s2 = b.refund(b.grant_starter(_free(), now=T0), b.PRODUCT_STARTER_UNLOCK, T0)
    _assert(s2.program_gens_remaining == 0, "refund left starter builds")

def test_trial_expires_by_count():
    """Five equipment scans, then the sixth is refused — inside the window."""
    s = b.grant_starter(_free(), now=T0)
    for i in range(5):
        _assert(b.has_quota(s, "equipment_scan", T0), f"scan {i + 1} refused early")
        s = b.debit(s, "equipment_scan", T0)
    _assert(s.equipment_scans_remaining == 0, f"left: {s.equipment_scans_remaining}")
    _assert(not b.has_quota(s, "equipment_scan", T0), "6th scan allowed")
    # ...while the meal quota from the same purchase is untouched.
    _assert(b.remaining(s, "meal_scan", T0) == 7, "meal scans wrongly consumed")


def test_trial_expires_by_date_even_with_scans_left():
    """Unused scans are forfeited when the 7 days run out."""
    s = b.grant_starter(_free(), now=T0)
    day6 = T0 + dt.timedelta(days=6)
    _assert(b.has_quota(s, "equipment_scan", day6), "refused inside the window")

    day8 = T0 + dt.timedelta(days=8)
    _assert(b.remaining(s, "equipment_scan", day8) == 0, "starter scans survived expiry")
    _assert(b.remaining(s, "meal_scan", day8) == 0, "starter meal scans survived expiry")
    _assert(b.resolve_tier(s, day8) == "free", f"tier after expiry: {b.resolve_tier(s, day8)}")
    _assert(b.paywall_required(s, day8), "paywall not required after expiry")


def test_expiry_boundary_is_inclusive():
    """Exactly at the deadline still counts as inside the window."""
    s = b.grant_starter(_free(), now=T0)
    edge = s.trial_ends_at
    _assert(b.has_quota(s, "equipment_scan", edge), "refused exactly at the deadline")
    _assert(not b.has_quota(s, "equipment_scan", edge + dt.timedelta(seconds=1)),
            "allowed one second past the deadline")


def test_starter_is_non_consumable_and_never_regrants():
    """A restore on a second device must not hand out five more scans."""
    s = b.grant_starter(_free(), now=T0)
    s = b.debit(s, "equipment_scan", T0)
    again = b.apply_event(s, "INITIAL_PURCHASE", b.PRODUCT_STARTER_UNLOCK,
                          now=T0, starter_already_granted=True)
    _assert(again.equipment_scans_remaining == 4,
            f"re-granted a non-consumable: {again.equipment_scans_remaining}")


# --- Consumables -------------------------------------------------------------
def test_equipment_pack_restores_quota_after_exhaustion():
    s = b.grant_starter(_free(), now=T0)
    for _ in range(5):
        s = b.debit(s, "equipment_scan", T0)
    _assert(not b.has_quota(s, "equipment_scan", T0), "fixture wrong")
    s = b.apply_event(s, "NON_RENEWING_PURCHASE", b.PRODUCT_EQUIPMENT_PACK, now=T0)
    _assert(b.remaining(s, "equipment_scan", T0) == 5, f"left: {s.equipment_scans_remaining}")


def test_pack_bought_after_the_window_is_not_eaten_by_the_stale_deadline():
    """The bug this rule exists to prevent: buying a pack on day 8 and having
    the expired starter window zero it on the next read."""
    s = b.grant_starter(_free(), now=T0)
    day8 = T0 + dt.timedelta(days=8)
    s = b.apply_event(s, "NON_RENEWING_PURCHASE", b.PRODUCT_EQUIPMENT_PACK, now=day8)
    _assert(b.remaining(s, "equipment_scan", day8) == 5,
            f"pack lost to a stale window: {b.remaining(s, 'equipment_scan', day8)}")
    day30 = T0 + dt.timedelta(days=30)
    _assert(b.remaining(s, "equipment_scan", day30) == 5, "pack expired — packs never expire")


def test_consumable_stacks_on_top_of_an_active_subscription():
    """Pro makes meal scans unlimited but NOT equipment scans, so a subscriber
    can still buy — and must still receive — an equipment pack."""
    s = b.grant_pro(_free(), expires_at=T0 + dt.timedelta(days=30), now=T0)
    _assert(b.remaining(s, "meal_scan", T0) == b.UNLIMITED, "pro meal scans not unlimited")
    _assert(b.remaining(s, "program_gen", T0) == b.UNLIMITED, "pro program gens not unlimited")
    _assert(b.remaining(s, "equipment_scan", T0) == 0, "pro wrongly unlimited on equipment")

    s = b.apply_event(s, "NON_RENEWING_PURCHASE", b.PRODUCT_EQUIPMENT_PACK, now=T0)
    s = b.apply_event(s, "NON_RENEWING_PURCHASE", b.PRODUCT_PROGRAM_PACK, now=T0)
    _assert(b.remaining(s, "equipment_scan", T0) == 5, "pack lost under an active sub")
    _assert(s.program_gens_remaining == 3, f"program pack lost: {s.program_gens_remaining}")
    _assert(b.resolve_tier(s, T0) == "pro", "buying a pack downgraded the tier")

    # And the stacked pack survives the subscription lapsing.
    lapsed = b.apply_event(s, "EXPIRATION", b.PRODUCT_PRO_MONTHLY, now=T0)
    _assert(lapsed.equipment_scans_remaining == 5, "pack lost when pro lapsed")
    _assert(lapsed.program_gens_remaining == 3, "program pack lost when pro lapsed")


def test_unlimited_kinds_are_never_debited():
    s = b.grant_pro(_free(), expires_at=None, now=T0)
    for _ in range(50):
        s = b.debit(s, "meal_scan", T0)
    _assert(b.remaining(s, "meal_scan", T0) == b.UNLIMITED, "unlimited quota was consumed")


def test_counters_never_go_negative():
    s = b.debit(_free(), "equipment_scan", T0)
    _assert(s.equipment_scans_remaining == 0, f"went negative: {s.equipment_scans_remaining}")


# --- Subscription lifecycle --------------------------------------------------
def test_subscription_lapse_revokes_pro():
    s = b.grant_pro(_free(), expires_at=T0 + dt.timedelta(days=30), now=T0)
    after = T0 + dt.timedelta(days=31)
    _assert(not b.pro_active(s, after), "expired subscription still active")
    _assert(b.resolve_tier(s, after) == "free", f"tier: {b.resolve_tier(s, after)}")
    _assert(b.remaining(s, "meal_scan", after) == 0, "unlimited survived expiry")

    revoked = b.apply_event(s, "EXPIRATION", b.PRODUCT_PRO_MONTHLY, now=after)
    _assert(revoked.tier == "free" and revoked.pro_expires_at is None,
            f"EXPIRATION left {revoked.tier}/{revoked.pro_expires_at}")


def test_cancellation_keeps_access_until_expiration():
    """Auto-renew off is not the same as paid-through-date reached."""
    s = b.grant_pro(_free(), expires_at=T0 + dt.timedelta(days=30), now=T0)
    s = b.apply_event(s, "CANCELLATION", b.PRODUCT_PRO_MONTHLY, now=T0)
    _assert(b.pro_active(s, T0), "cancellation cut access off early")


def test_billing_issue_keeps_access():
    s = b.grant_pro(_free(), expires_at=T0 + dt.timedelta(days=30), now=T0)
    s = b.apply_event(s, "BILLING_ISSUE", b.PRODUCT_PRO_MONTHLY, now=T0)
    _assert(b.pro_active(s, T0), "billing issue cut access off during the retry window")


def test_renewal_extends_the_expiry():
    s = b.grant_pro(_free(), expires_at=T0 + dt.timedelta(days=30), now=T0)
    later = T0 + dt.timedelta(days=60)
    s = b.apply_event(s, "RENEWAL", b.PRODUCT_PRO_MONTHLY, expires_at=later, now=T0)
    _assert(s.pro_expires_at == later, f"renewal did not extend: {s.pro_expires_at}")


def test_refund_claws_back():
    s = b.grant_pro(_free(), expires_at=T0 + dt.timedelta(days=30), now=T0)
    s = b.apply_event(s, "NON_RENEWING_PURCHASE", b.PRODUCT_EQUIPMENT_PACK, now=T0)
    refunded = b.apply_event(s, "REFUND", b.PRODUCT_EQUIPMENT_PACK, now=T0)
    _assert(refunded.equipment_scans_remaining == 0, "refunded pack still usable")
    _assert(b.pro_active(refunded, T0), "refunding a pack revoked the subscription")

    sub_refund = b.apply_event(s, "REFUND", b.PRODUCT_PRO_MONTHLY, now=T0)
    _assert(not b.pro_active(sub_refund, T0), "refunded subscription still active")


def test_unknown_event_type_is_inert():
    """A new RevenueCat event type must not raise — a 500 gets retried forever."""
    s = b.grant_starter(_free(), now=T0)
    same = b.apply_event(s, "SOMETHING_NEW_IN_2027", b.PRODUCT_PRO_MONTHLY, now=T0)
    _assert(same == s, "unknown event type mutated state")


# --- Webhook idempotency -----------------------------------------------------
class _FakeLedger:
    """Stand-in for the `purchase_events` UNIQUE index: first writer wins."""

    def __init__(self):
        self.seen: set[str] = set()

    def claim(self, event_id: str) -> bool:
        if event_id in self.seen:
            return False
        self.seen.add(event_id)
        return True


def _process(ledger: _FakeLedger, state: b.EntitlementState, payload: dict,
             now: dt.datetime) -> b.EntitlementState:
    """Mirror of the router's webhook handler, minus the DB and HTTP."""
    event = b.parse_webhook_event(payload)
    if event is None:
        return state
    if not ledger.claim(event.event_id):
        return state  # replay: 200, no credit
    return b.apply_event(state, event.event_type, event.product_id,
                         expires_at=event.expires_at, now=now)


def _payload(event_id: str, event_type: str, product_id: str, **extra) -> dict:
    return {"event": {"id": event_id, "type": event_type, "app_user_id": "u-1",
                      "product_id": product_id, **extra}}


def test_replayed_event_id_never_double_credits():
    ledger, s = _FakeLedger(), _free()
    body = _payload("evt-1", "NON_RENEWING_PURCHASE", b.PRODUCT_EQUIPMENT_PACK)
    s = _process(ledger, s, body, T0)
    _assert(s.equipment_scans_remaining == 5, f"first delivery: {s.equipment_scans_remaining}")
    for _ in range(4):  # RevenueCat retries
        s = _process(ledger, s, body, T0)
    _assert(s.equipment_scans_remaining == 5,
            f"replay double-credited: {s.equipment_scans_remaining}")


def test_distinct_event_ids_do_credit_twice():
    """The flip side: buying two packs is two events and must credit twice."""
    ledger, s = _FakeLedger(), _free()
    s = _process(ledger, s, _payload("evt-1", "NON_RENEWING_PURCHASE", b.PRODUCT_EQUIPMENT_PACK), T0)
    s = _process(ledger, s, _payload("evt-2", "NON_RENEWING_PURCHASE", b.PRODUCT_EQUIPMENT_PACK), T0)
    _assert(s.equipment_scans_remaining == 10, f"left: {s.equipment_scans_remaining}")


def test_sync_and_webhook_collide_on_the_same_purchase():
    """The reconcile call races the webhook by design; the derived id is what
    makes the loser a no-op instead of a second credit."""
    a = b.sync_event_id("u-1", b.PRODUCT_EQUIPMENT_PACK, "txn-99")
    again = b.sync_event_id("u-1", b.PRODUCT_EQUIPMENT_PACK, "txn-99")
    other = b.sync_event_id("u-1", b.PRODUCT_EQUIPMENT_PACK, "txn-100")
    _assert(a == again, "sync id is not deterministic")
    _assert(a != other, "different transactions collided")
    _assert(len(a) <= 128, "sync id exceeds the event_id column")


def test_webhook_without_id_or_user_is_dropped():
    _assert(b.parse_webhook_event({"event": {"type": "RENEWAL"}}) is None, "no id accepted")
    _assert(b.parse_webhook_event({"event": {"id": "x", "type": "RENEWAL"}}) is None,
            "no app_user_id accepted")
    _assert(b.parse_webhook_event({}) is None, "empty body accepted")


def test_webhook_expiry_parses_epoch_millis():
    ms = int((T0 + dt.timedelta(days=30)).timestamp() * 1000)
    event = b.parse_webhook_event(
        _payload("evt-3", "RENEWAL", b.PRODUCT_PRO_MONTHLY, expiration_at_ms=ms))
    _assert(event is not None and event.expires_at == T0 + dt.timedelta(days=30),
            f"bad expiry parse: {event.expires_at if event else None}")


# --- Shared-secret verification ----------------------------------------------
def test_webhook_secret_verification():
    _assert(b.verify_shared_secret("s3cret", "s3cret"), "correct secret rejected")
    _assert(b.verify_shared_secret("Bearer s3cret", "s3cret"), "bearer form rejected")
    _assert(not b.verify_shared_secret("wrong", "s3cret"), "wrong secret accepted")
    _assert(not b.verify_shared_secret(None, "s3cret"), "missing header accepted")
    # Fail closed: an unconfigured secret must not mean "allow everyone".
    _assert(not b.verify_shared_secret("anything", ""), "unconfigured secret accepted a call")
    _assert(not b.verify_shared_secret("", ""), "empty/empty accepted")


# --- Reserve / commit --------------------------------------------------------
def test_quota_not_consumed_when_the_provider_fails():
    """The whole point of reserving instead of decrementing: a Bedrock timeout
    must cost the user nothing."""
    s = b.grant_starter(_free(), now=T0)
    before = s.equipment_scans_remaining

    res = b.reserve(s, "equipment_scan", T0)
    try:
        raise RuntimeError("bedrock exploded")  # the provider call
    except RuntimeError:
        pass  # endpoint raises before commit; no spend()
    _assert(s.equipment_scans_remaining == before,
            f"consumed on failure: {s.equipment_scans_remaining}")
    _assert(not res.committed, "reservation committed itself")


def test_quota_consumed_only_after_success():
    s = b.grant_starter(_free(), now=T0)
    res = b.reserve(s, "equipment_scan", T0)
    s = res.spend(s, T0)  # provider returned
    _assert(s.equipment_scans_remaining == 4, f"left: {s.equipment_scans_remaining}")


def test_commit_is_idempotent():
    """An endpoint that commits twice (retry, loop) must still spend one."""
    s = b.grant_starter(_free(), now=T0)
    res = b.reserve(s, "equipment_scan", T0)
    s = res.spend(s, T0)
    s = res.spend(s, T0)
    _assert(s.equipment_scans_remaining == 4, f"double-spent: {s.equipment_scans_remaining}")


def test_reserve_raises_when_dry_with_the_paywall_body():
    try:
        b.reserve(_free(), "equipment_scan", T0)
    except b.QuotaExhausted as exc:
        _assert(exc.body == {"error": "quota_exhausted", "kind": "equipment_scan",
                             "paywall": b.PRODUCT_EQUIPMENT_PACK}, f"body: {exc.body}")
    else:
        raise AssertionError("reserve did not raise on an empty quota")


def test_paywall_product_per_kind():
    _assert(b.paywall_product("meal_scan") == b.PRODUCT_PRO_MONTHLY, "meal -> wrong product")
    _assert(b.paywall_product("program_gen") == b.PRODUCT_PROGRAM_PACK, "program -> wrong product")
    _assert(b.paywall_product("equipment_scan") == b.PRODUCT_EQUIPMENT_PACK, "equip -> wrong product")


def test_reserve_on_unlimited_does_not_touch_counters():
    s = b.grant_pro(_free(), expires_at=None, now=T0)
    res = b.reserve(s, "meal_scan", T0)
    _assert(res.unlimited, "pro reservation not marked unlimited")
    _assert(res.spend(s, T0) == s, "unlimited spend mutated state")


# --- Subscriber payload parsing ----------------------------------------------
def test_parse_subscriber_reads_entitlements_and_consumables():
    payload = {"subscriber": {
        "entitlements": {
            "pro": {"expires_date": "2026-09-19T12:00:00Z", "product_identifier": b.PRODUCT_PRO_MONTHLY},
            "starter": {"expires_date": None, "product_identifier": b.PRODUCT_STARTER_UNLOCK},
        },
        "non_subscriptions": {
            b.PRODUCT_EQUIPMENT_PACK: [{"id": "txn-1"}, {"id": "txn-2"}],
            b.PRODUCT_PROGRAM_PACK: [{"id": "txn-3"}],
        },
    }}
    snap = b.parse_subscriber(payload, "u-1", now=T0)
    _assert(snap.has_pro and snap.has_starter, f"entitlements missed: {snap}")
    _assert(snap.pro_expires_at == dt.datetime(2026, 9, 19, 12, 0, tzinfo=dt.timezone.utc),
            f"expiry: {snap.pro_expires_at}")
    _assert(sorted(snap.purchases()) == [
        (b.PRODUCT_EQUIPMENT_PACK, "txn-1"), (b.PRODUCT_EQUIPMENT_PACK, "txn-2"),
        (b.PRODUCT_PROGRAM_PACK, "txn-3")], f"purchases: {snap.purchases()}")


def test_parse_subscriber_treats_a_past_expiry_as_inactive():
    payload = {"subscriber": {"entitlements": {
        "pro": {"expires_date": "2026-08-01T00:00:00Z"}}}}
    snap = b.parse_subscriber(payload, "u-1", now=T0)
    _assert(not snap.has_pro, "expired entitlement reported active")


def test_parse_subscriber_survives_an_empty_body():
    snap = b.parse_subscriber({}, "u-1", now=T0)
    _assert(not snap.has_pro and not snap.has_starter and snap.purchases() == [],
            f"empty body mishandled: {snap}")


def test_state_round_trips_through_row_values():
    """`to_row_values` writes back onto the ORM row, so its keys must match."""
    s = b.grant_starter(_free(), now=T0)
    values = s.to_row_values()
    for column in b.COLUMN_FOR_KIND.values():
        _assert(column in values, f"missing column in row values: {column}")

    class _Row:
        pass

    row = _Row()
    for k, v in values.items():
        setattr(row, k, v)
    _assert(b.EntitlementState.from_row(row) == s, "round trip lost data")


def test_naive_timestamps_do_not_explode():
    """SQLite/legacy rows come back naive; comparing them would raise and 402
    a paying user."""
    naive = b.EntitlementState(tier="pro", pro_expires_at=dt.datetime(2027, 1, 1),
                               trial_ends_at=dt.datetime(2027, 1, 1))
    _assert(b.pro_active(naive, T0), "naive expiry mishandled")
    _assert(b.starter_window_open(naive, T0), "naive trial end mishandled")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"  FAIL  {t.__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    raise SystemExit(1 if failed else 0)

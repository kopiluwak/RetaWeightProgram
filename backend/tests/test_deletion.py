"""Unit tests for account deletion (app/deletion.py).

Run: python3 -m tests.test_deletion

Covers the two things that must not silently regress:
  * the grace-window arithmetic (a user purged early is a data-loss incident;
    a user purged late is a GDPR Art. 12(3) problem), and
  * the anonymising fold, which is the only reason any training data survives
    deletion at all. If merging ever stops working, retained rows become
    per-person records and the retention stops being lawful.

Pure functions only — no DB, matching tests/test_couch.py and friends.
"""
from __future__ import annotations

import datetime as dt

from app.deletion import GRACE_PERIOD_DAYS, is_due, scheduled_purge_at, tally_sets


class FakeSet:
    """Stand-in for models.SetLog with only the fields the fold reads."""

    def __init__(self, exercise_name, weight, reps, rir=2):
        self.exercise_name = exercise_name
        self.weight = weight
        self.reps = reps
        self.rir = rir


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


# --- Grace window ------------------------------------------------------------
def test_grace_period_is_30_days():
    """30 days sits inside the GDPR Art. 12(3) one-month deadline."""
    _assert(GRACE_PERIOD_DAYS == 30, f"expected 30-day grace, got {GRACE_PERIOD_DAYS}")


def test_scheduled_purge_is_request_plus_grace():
    requested = dt.datetime(2026, 8, 18, 12, 0, tzinfo=dt.timezone.utc)
    got = scheduled_purge_at(requested)
    _assert(got == dt.datetime(2026, 9, 17, 12, 0, tzinfo=dt.timezone.utc), f"got {got}")


def test_not_due_before_window_closes():
    requested = dt.datetime(2026, 8, 18, tzinfo=dt.timezone.utc)
    one_second_early = scheduled_purge_at(requested) - dt.timedelta(seconds=1)
    _assert(not is_due(requested, now=one_second_early), "purged a second too early")


def test_due_exactly_at_window_close():
    requested = dt.datetime(2026, 8, 18, tzinfo=dt.timezone.utc)
    _assert(is_due(requested, now=scheduled_purge_at(requested)), "not due at the boundary")


def test_never_due_when_not_requested():
    _assert(not is_due(None), "an active account must never be purged")


def test_naive_timestamp_does_not_explode():
    """Rows written before the column was tz-aware come back naive; comparing
    those to an aware now() would raise TypeError and stall the whole sweep."""
    naive = dt.datetime(2026, 1, 1, 0, 0)
    _assert(is_due(naive, now=dt.datetime(2026, 6, 1, tzinfo=dt.timezone.utc)),
            "naive timestamp mishandled")


# --- The anonymising fold ----------------------------------------------------
def test_identical_sets_merge_into_one_bin():
    """The core anonymity property: 40 identical sets become one bin of 40."""
    rows = [FakeSet("Bench Press", 135.0, 8, 2) for _ in range(40)]
    tally = tally_sets(rows, "intermediate", 4)
    _assert(len(tally) == 1, f"expected 1 bin, got {len(tally)}")
    _assert(list(tally.values()) == [40], f"expected count 40, got {list(tally.values())}")


def test_one_users_history_cannot_be_regrouped():
    """A realistic history must collapse to far fewer bins than sets — if bins
    ever approach the set count, the table is per-person data again."""
    rows = []
    for _ in range(12):                       # 12 sessions
        for reps in (8, 8, 7):                # 3 sets each
            rows.append(FakeSet("Squat", 185.0, reps, 2))
    tally = tally_sets(rows, "conservative", 3)
    _assert(len(rows) == 36, "fixture wrong")
    _assert(len(tally) == 2, f"expected 2 bins (8 reps, 7 reps), got {len(tally)}")
    _assert(sum(tally.values()) == 36, "lost sets in the fold")


def test_bodyweight_null_weight_becomes_zero_not_null():
    """A NULL dimension would never collide in the unique constraint, so every
    bodyweight set would get its own row — exactly the leak we're removing."""
    rows = [FakeSet("Pull-up", None, 6, 1) for _ in range(5)]
    tally = tally_sets(rows, "beginner", 3)
    _assert(len(tally) == 1, f"bodyweight sets failed to merge: {len(tally)} bins")
    key = next(iter(tally))
    _assert(key[1] == 0.0, f"expected weight 0.0, got {key[1]!r}")
    _assert(all(v is not None for v in key), f"NULL leaked into a dimension: {key}")


def test_weight_rounded_so_bins_actually_merge():
    """Float equality in a unique index is fragile; rounding makes it deterministic."""
    rows = [FakeSet("Curl", 22.51, 10, 2), FakeSet("Curl", 22.49, 10, 2)]
    tally = tally_sets(rows, "intermediate", 4)
    _assert(len(tally) == 1, f"near-equal weights failed to merge: {tally}")


def test_distinct_dimensions_stay_distinct():
    """Merging must not be so aggressive that the data loses its meaning."""
    rows = [
        FakeSet("Bench Press", 135.0, 8, 2),
        FakeSet("Bench Press", 145.0, 8, 2),   # different weight
        FakeSet("Bench Press", 135.0, 6, 2),   # different reps
        FakeSet("Bench Press", 135.0, 8, 0),   # different RIR
        FakeSet("Overhead Press", 135.0, 8, 2),  # different exercise
    ]
    tally = tally_sets(rows, "intermediate", 4)
    _assert(len(tally) == 5, f"expected 5 distinct bins, got {len(tally)}")


def test_experience_and_days_carried_and_never_null():
    rows = [FakeSet("Row", 95.0, 10, 2)]
    key = next(iter(tally_sets(rows, "beginner", 5)))
    _assert(key[4] == "beginner" and key[5] == 5, f"habits not carried: {key}")

    # A user with no habits row must still fold cleanly rather than write NULLs.
    key = next(iter(tally_sets(rows, "", 0)))
    _assert(key[4] == "unknown" and key[5] == 0, f"missing habits mishandled: {key}")


def test_empty_history_folds_to_nothing():
    _assert(tally_sets([], "intermediate", 4) == {}, "empty history should yield no bins")


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

"""Unit tests for app/couch.py (pure functions, no DB).

Run from backend/:  python3 -m tests.test_couch
"""
from __future__ import annotations

import datetime as dt

from app.couch import (
    LADDER_MAX,
    build_message,
    couch_days,
    couch_view,
    decision_due,
    nudge_level,
    program_full,
    week_number,
)

NOW = dt.datetime(2026, 7, 23, 12, 0, tzinfo=dt.timezone.utc)


def _ex(name: str, compound: bool, sets: int = 3) -> dict:
    return {"name": name, "pattern": "p", "primary": ["m"], "sets": sets,
            "reps": "5-8", "rir": "2-3", "compound": compound, "rest_seconds": 120}


def _program(days: int = 4, per_day: int = 5) -> dict:
    """A synthetic engine-shaped program: `days` days, each with 1 compound then
    `per_day-1` accessories (so compounds-first ordering is testable)."""
    prog_days = []
    for d in range(days):
        exs = [_ex(f"D{d}-compound", True, 4)]
        exs += [_ex(f"D{d}-acc{i}", False, 3) for i in range(per_day - 1)]
        prog_days.append({"name": f"Day {d+1}", "exercises": exs, "gaps": [], "est_minutes": 40})
    return {"days": prog_days}


# --- clock / target math ---
def test_week_number() -> None:
    start = NOW
    assert week_number(start, start) == 1
    assert week_number(start, start + dt.timedelta(days=6, hours=23)) == 1
    assert week_number(start, start + dt.timedelta(days=7)) == 2
    assert week_number(start, start + dt.timedelta(days=21)) == 4
    # naive datetime is coerced, not crashed
    assert week_number(start.replace(tzinfo=None), start + dt.timedelta(days=7)) == 2


def test_program_full_caps_at_ladder_max() -> None:
    assert program_full(_program(days=4, per_day=5)) == 5
    assert program_full(_program(days=3, per_day=9)) == LADDER_MAX  # capped at 6
    assert program_full({"days": []}) == 0


def test_nudge_level() -> None:
    assert nudge_level(0) == 0
    assert nudge_level(1) == 1
    assert nudge_level(2) == 2
    assert nudge_level(5) == 2


def test_decision_due_rules() -> None:
    # behind target, not snoozed, not graduated -> due
    assert decision_due(unlocked=1, target=2, week=2, snoozed_week=0, graduated=False)
    # caught up -> not due
    assert not decision_due(unlocked=2, target=2, week=2, snoozed_week=0, graduated=False)
    # snoozed this week -> suppressed
    assert not decision_due(unlocked=1, target=2, week=2, snoozed_week=2, graduated=False)
    # next week after a snooze -> returns
    assert decision_due(unlocked=1, target=3, week=3, snoozed_week=2, graduated=False)
    # graduated -> never due
    assert not decision_due(unlocked=6, target=6, week=9, snoozed_week=0, graduated=True)


# --- per-day reveal ---
def test_week1_one_exercise_per_day_and_time_budget() -> None:
    prog = _program(days=4, per_day=5)
    days = couch_days(prog, unlocked=1)
    assert len(days) == 4                         # keeps the 4-day schedule
    for d in days:
        assert len(d["exercises"]) == 1           # one exercise per day
        assert d["exercises"][0]["compound"] is True   # foundational compound first
        assert d["exercises"][0]["sets"] == 2     # newest move eased to 2 sets
        assert 8 <= d["est_minutes"] <= 15        # 8-15 min Week-1 session


def test_reveal_follows_authored_order() -> None:
    # Reveal follows the engine's slot order (primary compound first, then the
    # paired muscle) — NOT a compounds-first re-sort. A push day authored as
    # chest(compound) -> triceps(accessory) -> shoulders(compound) must reveal
    # chest+triceps at 2 exercises (the push pairing), not chest+shoulders.
    push = {"name": "Push", "exercises": [_ex("bench", True), _ex("triceps", False), _ex("ohp", True)]}
    revealed = couch_days({"days": [push]}, unlocked=2)[0]["exercises"]
    assert [e["name"] for e in revealed] == ["bench", "triceps"]


def test_newest_capped_older_keep_engine_sets() -> None:
    prog = _program(days=1, per_day=5)  # compound(4 sets) + 4 accessories(3 sets)
    exs = couch_days(prog, unlocked=3)[0]["exercises"]
    assert len(exs) == 3
    assert exs[0]["sets"] == 4   # oldest compound keeps engine sets
    assert exs[1]["sets"] == 3   # older accessory keeps engine sets
    assert exs[2]["sets"] == 2   # newest accessory capped to 2


def test_reveal_never_exceeds_day_length() -> None:
    prog = _program(days=2, per_day=3)
    exs = couch_days(prog, unlocked=6)[0]["exercises"]
    assert len(exs) == 3  # only 3 exist


# --- assembled view ---
def test_view_week1_message_and_headline() -> None:
    v = couch_view(program=_program(), unlocked=1, started_at=NOW, snoozed_week=0,
                   consecutive_skips=0, graduated=False, now=NOW)
    assert v["week"] == 1 and v["unlocked"] == 1 and v["full"] == 5
    assert v["decision_due"] is False           # only 1 day in, target==1
    assert "per day" in v["headline"]
    assert "Week 1" in v["message"]


def test_view_offers_add_next_week() -> None:
    v = couch_view(program=_program(), unlocked=1, started_at=NOW, snoozed_week=0,
                   consecutive_skips=0, graduated=False, now=NOW + dt.timedelta(days=7))
    assert v["week"] == 2 and v["decision_due"] is True
    assert "Level up" in v["message"] or "level up" in v["message"]


def test_view_nudge_after_skip() -> None:
    v = couch_view(program=_program(), unlocked=1, started_at=NOW, snoozed_week=0,
                   consecutive_skips=1, graduated=False, now=NOW + dt.timedelta(days=7))
    assert v["nudge_level"] == 1
    assert "lock in the habit" in v["message"]


def test_view_catch_up_only_plus_one() -> None:
    # 4 calendar weeks in but still at 1 exercise: target is 4, but the user is only
    # ever offered to move to 2 next (unlocked+1), never a jump.
    v = couch_view(program=_program(), unlocked=1, started_at=NOW, snoozed_week=0,
                   consecutive_skips=0, graduated=False, now=NOW + dt.timedelta(days=28))
    assert v["week"] == 5 and v["decision_due"] is True
    assert v["unlocked"] == 1  # view doesn't auto-advance; the add endpoint does +1


def test_view_graduation_clamps() -> None:
    v = couch_view(program=_program(days=3, per_day=5), unlocked=5, started_at=NOW,
                   snoozed_week=0, consecutive_skips=0, graduated=False,
                   now=NOW + dt.timedelta(days=60))
    assert v["graduated"] is True
    assert v["decision_due"] is False
    assert "milestone" in v["message"]
    # unlocked above a shorter program's full is clamped down
    v2 = couch_view(program=_program(days=2, per_day=3), unlocked=6, started_at=NOW,
                    snoozed_week=0, consecutive_skips=0, graduated=False, now=NOW)
    assert v2["unlocked"] == 3 and v2["full"] == 3 and v2["graduated"] is True


def test_just_added_and_skipped_copy() -> None:
    added = build_message(unlocked=2, full=5, week=2, graduated=False, decision=False,
                          nudge=0, new_name="Goblet Squat", just_added=True)
    assert "2 exercises a day" in added
    skipped = build_message(unlocked=1, full=5, week=2, graduated=False, decision=False,
                            nudge=1, new_name="x", just_skipped=True)
    assert "consistency first" in skipped


def test_user_added_exercise_always_shown_and_not_in_ramp() -> None:
    # Week-1 beginner (unlocked=1) with a user-added movement on Day 1.
    prog = _program(days=2, per_day=3)
    added = {**_ex("Preacher Curl", False, 3), "added_by_user": True}
    prog["days"][0]["exercises"].append(added)

    # Ramp length ignores the added exercise (still 3, not 4).
    assert program_full(prog) == 3

    days = couch_days(prog, 1)
    names0 = [e["name"] for e in days[0]["exercises"]]
    # Day 1 shows its 1 unlocked ramp move PLUS the always-on added move.
    assert names0 == ["D0-compound", "Preacher Curl"]
    # Day 2 (no added move) still shows exactly its 1 unlocked move.
    assert [e["name"] for e in days[1]["exercises"]] == ["D1-compound"]

    # Coach copy's "newest" name is a ramp move, never the user-added one.
    v = couch_view(program=prog, unlocked=1, started_at=NOW, snoozed_week=0,
                   consecutive_skips=0, graduated=False, now=NOW + dt.timedelta(days=7))
    assert v["added_today"] is None
    assert "Preacher Curl" not in (v["message"] or "")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"{name} OK")
    print("ALL_TESTS_PASSED")

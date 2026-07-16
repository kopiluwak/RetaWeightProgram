"""Unit tests for app/gamification.py (pure functions, no DB).

Run from backend/:  python3 -m tests.test_gamification
"""
from __future__ import annotations

import datetime as dt

from app.gamification import (
    best_workout_streak,
    consecutive_full_weeks,
    consecutive_protein_weeks,
    current_workout_streak,
    evaluate_workout_badges,
    full_weeks,
    level_for_xp,
    protein_weeks,
    sessions_in_week,
    total_xp,
    week_motivation,
    week_start,
    weeks_overview,
)

MON = dt.date(2026, 7, 6)   # a Monday
TODAY = dt.date(2026, 7, 9)  # that Thursday


def days(*offsets: int) -> dict[dt.date, int]:
    """{MON+offset: 1 session} helper."""
    return {MON + dt.timedelta(days=o): 1 for o in offsets}


def test_streaks() -> None:
    # Mon-Wed trained, today Thu untrained -> streak alive at 3.
    assert current_workout_streak(days(0, 1, 2), TODAY) == 3
    # Gap two days back -> broken.
    assert current_workout_streak(days(0, 1), TODAY) == 0
    # Today trained counts immediately.
    assert current_workout_streak(days(1, 2, 3), TODAY) == 3
    assert best_workout_streak(days(0, 1, 2, 4, 5, 6, 7)) == 4
    assert best_workout_streak({}) == 0


def test_weeks() -> None:
    assert week_start(TODAY) == MON
    assert sessions_in_week(days(0, 2, 4), MON) == 3
    # Two sessions on one day count once (frequency, not volume).
    two_a_day = {MON: 2, MON + dt.timedelta(days=1): 1}
    assert sessions_in_week(two_a_day, MON) == 2
    # Full weeks against a 3-day target.
    hist = days(0, 2, 4, -7, -5, -3, -14)  # this week full, last week full, week before 1 day
    assert full_weeks(hist, 3) == [MON - dt.timedelta(days=7), MON]
    assert consecutive_full_weeks(hist, 3, TODAY) == 2
    ov = weeks_overview(hist, 3, TODAY, n_weeks=3)
    assert [w["pct"] for w in ov] == [33, 100, 100]
    assert ov[-1]["week_start"] == MON.isoformat()


def test_protein_weeks() -> None:
    target = 100.0
    grams = {MON + dt.timedelta(days=i): 95.0 for i in range(5)}         # 5 hits this week
    grams.update({MON - dt.timedelta(days=7) + dt.timedelta(days=i): 95.0 for i in range(5)})
    assert protein_weeks(grams, target) == [MON - dt.timedelta(days=7), MON]
    assert consecutive_protein_weeks(grams, target, TODAY) == 2
    assert protein_weeks(grams, 0) == []


def test_xp_and_levels() -> None:
    assert total_xp(total_sessions=0, protein_hit_days=0, n_full_weeks=0, n_protein_weeks=0) == 0
    assert total_xp(total_sessions=2, protein_hit_days=3, n_full_weeks=1, n_protein_weeks=1) \
        == 2 * 50 + 3 * 25 + 150 + 75
    lvl, title, into, span = level_for_xp(0)
    assert (lvl, title, into, span) == (1, "Rookie", 0, 200)
    lvl, _, into, span = level_for_xp(199)
    assert (lvl, into, span) == (1, 199, 200)
    lvl, title, into, span = level_for_xp(200)   # cum for L2 = 100*2*1 = 200
    assert (lvl, into, span) == (2, 0, 400)
    lvl, _, _, _ = level_for_xp(100 * 10 * 9)    # exactly level 10
    assert lvl == 10
    assert level_for_xp(10 ** 6)[1] == "Legend"  # title clamps


def test_badges() -> None:
    target = 100.0
    hist = days(0, 1, 2, -7, -5, -3)  # 3-day current streak + full prior week (3-day target)
    grams = {MON + dt.timedelta(days=i): 95.0 for i in range(5)}
    new = evaluate_workout_badges(
        day_sessions=hist, days_per_week=3, day_grams=grams, protein_target=target,
        today=TODAY, level=2, already=set(),
    )
    assert "first_session" in new
    assert "streak_3" in new
    assert "weekly_warrior" in new
    assert "perfect_week" in new           # this week is full AND has 5 protein hits
    assert "streak_7" not in new
    assert "sessions_10" not in new
    # already-earned keys are never re-awarded
    again = evaluate_workout_badges(
        day_sessions=hist, days_per_week=3, day_grams=grams, protein_target=target,
        today=TODAY, level=2, already=set(new),
    )
    assert again == []


def test_motivation() -> None:
    assert "Set up" in week_motivation(0, 0)
    assert week_motivation(3, 3)
    assert week_motivation(2, 3)
    assert week_motivation(0, 3)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"{name} OK")
    print("ALL_TESTS_PASSED")

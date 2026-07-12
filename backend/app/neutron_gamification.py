"""Neutron gamification: streaks, level, muscle-preservation score, badges.

Pure functions over (day -> grams) aggregates so everything is unit-testable
and there is exactly one source of truth: ProteinLog rows. Only badge AWARDS
are persisted (NutritionBadge) so they survive broken streaks.

Design choices:
- A day "hits" when logged protein >= 90% of target (GLP-1 appetites are
  volatile; a hard 100% cliff punishes a 3-gram miss and kills motivation).
- Level = total hit-days, banded. Slow, monotonic, can't regress.
- Muscle-preservation score (0-100) = mean of per-day attainment over the
  trailing 28 days, attainment capped at 1.0/day so binge days can't buy back
  skipped days — consistency is the whole point of the metric.
"""
from __future__ import annotations

import datetime as dt

HIT_RATIO = 0.90

LEVELS = [
    (0, "Rookie"),
    (5, "Contender"),
    (15, "Builder"),
    (30, "Protector"),
    (60, "Guardian"),
    (100, "Sentinel"),
    (180, "Muscle Machine"),
    (365, "Legend"),
]

# key -> (name, description). Trigger logic lives in evaluate_badges below.
BADGES: dict[str, tuple[str, str]] = {
    "first_log": ("First Rep", "Logged your first protein entry."),
    "thirty_g_club": ("30 g Club", "Logged a single meal with 30 g+ of protein."),
    "first_hit": ("Target Down", "Hit your daily protein target for the first time."),
    "muscle_guardian": ("Muscle Guardian", "Hit your protein target 7 days in a row."),
    "iron_month": ("Iron Month", "Hit your protein target 30 days in a row."),
    "pantry_alchemist": ("Pantry Alchemist", "Generated recipes from your first kitchen scan."),
    "alpha_gal_champion": ("Alpha-Gal Champion", "Hit your target 7 days running — all without red meat."),
    "plant_powered": ("Plant Powered", "Hit your target 7 days running on a vegan or vegetarian pattern."),
    "surprise_seeker": ("Surprise Seeker", "Generated your first full-day Surprise Me plan."),
    "weight_watcher": ("Trend Tracker", "Logged bodyweight 4 weeks in a row."),
}

MOTIVATION_HIT = [
    "Target hit — your muscles thank you!",
    "That's the muscle-preservation game, played perfectly.",
    "Full marks today. Strength is built on days like this.",
]
MOTIVATION_CLOSE = [
    "So close — one Greek yogurt gets you there.",
    "A protein shake away from a perfect day.",
    "Almost there. Small appetite, smart choices.",
]
MOTIVATION_LOW = [
    "Every gram counts on GLP-1 — a small high-protein snack moves the bar.",
    "Muscle is expensive to build and cheap to keep. Feed it a little.",
    "No pressure — just aim for the next 10 grams.",
]


def day_hit(grams: float, target: float) -> bool:
    return target > 0 and grams >= HIT_RATIO * target


def current_streak(day_grams: dict[dt.date, float], target: float, today: dt.date) -> int:
    """Consecutive hit-days ending today or yesterday (today still in progress
    doesn't break the streak until it's actually over)."""
    if target <= 0:
        return 0
    start = today if day_hit(day_grams.get(today, 0.0), target) else today - dt.timedelta(days=1)
    streak = 0
    d = start
    while day_hit(day_grams.get(d, 0.0), target):
        streak += 1
        d -= dt.timedelta(days=1)
    return streak


def best_streak(day_grams: dict[dt.date, float], target: float) -> int:
    if target <= 0 or not day_grams:
        return 0
    days = sorted(day_grams)
    best = run = 0
    prev: dt.date | None = None
    for d in days:
        if not day_hit(day_grams[d], target):
            run = 0
            prev = None
            continue
        run = run + 1 if prev is not None and (d - prev).days == 1 else 1
        prev = d
        best = max(best, run)
    return best


def weekly_streak(day_grams: dict[dt.date, float], target: float, today: dt.date,
                  min_hits_per_week: int = 5) -> int:
    """Consecutive calendar weeks (Mon-Sun) with >= min_hits_per_week hit-days.
    The current in-progress week counts if it already qualifies, else is skipped."""
    if target <= 0:
        return 0

    def week_start(d: dt.date) -> dt.date:
        return d - dt.timedelta(days=d.weekday())

    def hits_in_week(ws: dt.date) -> int:
        return sum(
            1 for i in range(7)
            if day_hit(day_grams.get(ws + dt.timedelta(days=i), 0.0), target)
        )

    ws = week_start(today)
    streak = 0
    if hits_in_week(ws) >= min_hits_per_week:
        streak += 1
    ws -= dt.timedelta(days=7)
    while hits_in_week(ws) >= min_hits_per_week:
        streak += 1
        ws -= dt.timedelta(days=7)
    return streak


def total_hit_days(day_grams: dict[dt.date, float], target: float) -> int:
    return sum(1 for g in day_grams.values() if day_hit(g, target))


def level_for(hit_days: int) -> tuple[int, str, int | None]:
    """-> (level number 1-based, title, hit-days needed for next level or None)."""
    level, title = 1, LEVELS[0][1]
    nxt: int | None = None
    for i, (threshold, name) in enumerate(LEVELS):
        if hit_days >= threshold:
            level, title = i + 1, name
            nxt = LEVELS[i + 1][0] if i + 1 < len(LEVELS) else None
    return level, title, nxt


def muscle_score(day_grams: dict[dt.date, float], target: float, today: dt.date) -> int:
    """0-100 over the trailing 28 days; per-day attainment capped at 1."""
    if target <= 0:
        return 0
    total = 0.0
    for i in range(28):
        d = today - dt.timedelta(days=i)
        total += min(1.0, day_grams.get(d, 0.0) / target)
    return round(100 * total / 28)


def motivation(today_grams: float, target: float) -> str:
    if target <= 0:
        return "Set your weight to get a protein target — 1 g per kg keeps muscle on board."
    ratio = today_grams / target
    pool = MOTIVATION_HIT if ratio >= HIT_RATIO else MOTIVATION_CLOSE if ratio >= 0.65 else MOTIVATION_LOW
    return pool[int(today_grams) % len(pool)]


def evaluate_badges(
    *,
    day_grams: dict[dt.date, float],
    target: float,
    today: dt.date,
    has_any_log: bool,
    max_single_log_g: float,
    restrictions: list[str],
    diet_pattern: str,
    weight_log_weeks: int,
    already: set[str],
) -> list[str]:
    """Return badge keys newly earned (not in `already`). Event-driven badges
    (pantry_alchemist, surprise_seeker) are awarded at their endpoints instead."""
    earned: list[str] = []

    def add(key: str, cond: bool) -> None:
        if cond and key not in already:
            earned.append(key)

    streak = current_streak(day_grams, target, today)
    add("first_log", has_any_log)
    add("thirty_g_club", max_single_log_g >= 30)
    add("first_hit", total_hit_days(day_grams, target) >= 1)
    add("muscle_guardian", streak >= 7)
    add("iron_month", streak >= 30)
    add("alpha_gal_champion", streak >= 7 and "no_red_meat" in restrictions)
    add("plant_powered", streak >= 7 and diet_pattern in ("vegan", "vegetarian"))
    add("weight_watcher", weight_log_weeks >= 4)
    return earned

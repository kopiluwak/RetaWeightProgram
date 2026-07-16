"""Cross-app gamification: XP, workout streaks, weekly challenge, achievements.

Same design philosophy as neutron_gamification: pure functions over small
aggregates (day -> completed-session count, day -> protein grams) so all the
math is unit-testable and derived entirely from history. XP is recomputed from
the logs on every read, so it can never drift out of sync with what the user
actually did. Only achievement AWARDS are persisted (WorkoutBadge) so they
survive later broken streaks.

XP model (deterministic, monotonic — history only grows):
- 50 XP  per completed workout session
- 25 XP  per protein hit-day (>= 90% of target, mirrors neutron_gamification)
- 150 XP bonus per full program week (completed sessions >= days/week target)
- 75 XP  bonus per protein week (5+ hit-days in a Mon-Sun week)

Level curve is gently quadratic: level N -> N+1 costs 200*N XP, so early
levels land fast (dopamine) and later ones signal real consistency.
"""
from __future__ import annotations

import datetime as dt

from .neutron_gamification import HIT_RATIO, day_hit

XP_PER_WORKOUT = 50
XP_PER_PROTEIN_DAY = 25
XP_PER_FULL_WEEK = 150
XP_PER_PROTEIN_WEEK = 75
PROTEIN_WEEK_MIN_HITS = 5

# Title per level, clamped at the top — levels keep climbing past "Legend".
LEVEL_TITLES = [
    "Rookie", "Gunner", "Contender", "Athlete", "Warrior",
    "Champion", "Elite", "Titan", "Immortal", "Legend",
]

# key -> (name, description). Trigger logic lives in evaluate_workout_badges.
WORKOUT_BADGES: dict[str, tuple[str, str]] = {
    "first_session": ("First Rep", "Completed your first workout session."),
    "weekly_warrior": ("Weekly Warrior", "Completed every session of your weekly program."),
    "perfect_week": ("Perfect Week", "Full training week AND 5 protein target days in the same week."),
    "consistency_beast": ("Consistency Beast", "Four full training weeks in a row."),
    "streak_3": ("On a Roll", "Trained 3 days in a row."),
    "streak_7": ("Unstoppable", "Trained 7 days in a row."),
    "sessions_10": ("Double Digits", "Logged 10 workouts."),
    "sessions_50": ("Iron Fifty", "Logged 50 workouts."),
    "protein_pro": ("Protein Pro", "Hit your protein target 7 days in a row."),
    "macro_machine": ("Macro Machine", "Four protein weeks (5+ target days) in a row."),
}

MOTIVATION_WEEK_DONE = [
    "Week complete. You're playing this game on legend difficulty.",
    "Every session banked. Muscle: preserved. Bragging rights: earned.",
]
MOTIVATION_WEEK_CLOSE = [
    "One session from a perfect week — the bar is loaded.",
    "So close. Your future self is already flexing.",
]
MOTIVATION_WEEK_OPEN = [
    "This week's challenge is wide open. First session sets the tone.",
    "Streaks are built one workout at a time. Today counts double (not really — 50 XP).",
]


def week_start(d: dt.date) -> dt.date:
    """Monday of the week containing d."""
    return d - dt.timedelta(days=d.weekday())


# ------------------------------------------------------------ workout streaks


def current_workout_streak(day_sessions: dict[dt.date, int], today: dt.date) -> int:
    """Consecutive training days ending today or yesterday (a rest-day today
    doesn't break the streak until it's actually over — same rule as protein)."""
    start = today if day_sessions.get(today, 0) > 0 else today - dt.timedelta(days=1)
    streak = 0
    d = start
    while day_sessions.get(d, 0) > 0:
        streak += 1
        d -= dt.timedelta(days=1)
    return streak


def best_workout_streak(day_sessions: dict[dt.date, int]) -> int:
    """Longest run of consecutive training days anywhere in history."""
    days = sorted(d for d, n in day_sessions.items() if n > 0)
    best = run = 0
    prev: dt.date | None = None
    for d in days:
        run = run + 1 if prev is not None and (d - prev).days == 1 else 1
        prev = d
        best = max(best, run)
    return best


# ------------------------------------------------------------ weekly challenge


def sessions_in_week(day_sessions: dict[dt.date, int], ws: dt.date) -> int:
    """Completed sessions inside one Mon-Sun week, capped at one per day so a
    double session can't fake a full week (frequency is the point)."""
    return sum(1 for i in range(7) if day_sessions.get(ws + dt.timedelta(days=i), 0) > 0)


def full_weeks(day_sessions: dict[dt.date, int], target: int) -> list[dt.date]:
    """Week-starts of every week that met the days/week target, sorted."""
    if target <= 0:
        return []
    weeks = {week_start(d) for d, n in day_sessions.items() if n > 0}
    return sorted(ws for ws in weeks if sessions_in_week(day_sessions, ws) >= target)


def consecutive_full_weeks(day_sessions: dict[dt.date, int], target: int,
                           today: dt.date) -> int:
    """Consecutive full weeks ending at the current or previous week (the
    in-progress week counts if it already qualifies, else is skipped)."""
    if target <= 0:
        return 0
    ws = week_start(today)
    streak = 0
    if sessions_in_week(day_sessions, ws) >= target:
        streak += 1
    ws -= dt.timedelta(days=7)
    while sessions_in_week(day_sessions, ws) >= target:
        streak += 1
        ws -= dt.timedelta(days=7)
    return streak


def weeks_overview(day_sessions: dict[dt.date, int], target: int,
                   today: dt.date, n_weeks: int = 12) -> list[dict]:
    """Trailing weekly progress, oldest first: [{week_start, completed, target,
    pct}]. Feeds the shaded weekly badges in the app."""
    out: list[dict] = []
    this_ws = week_start(today)
    for w in range(n_weeks - 1, -1, -1):
        ws = this_ws - dt.timedelta(days=7 * w)
        done = sessions_in_week(day_sessions, ws)
        pct = round(100 * min(1.0, done / target)) if target > 0 else 0
        out.append({"week_start": ws.isoformat(), "completed": done,
                    "target": target, "pct": pct})
    return out


# ------------------------------------------------------------ protein weeks


def protein_weeks(day_grams: dict[dt.date, float], target: float) -> list[dt.date]:
    """Week-starts of every week with >= PROTEIN_WEEK_MIN_HITS hit-days."""
    if target <= 0:
        return []
    weeks = {week_start(d) for d in day_grams}
    out = []
    for ws in weeks:
        hits = sum(1 for i in range(7)
                   if day_hit(day_grams.get(ws + dt.timedelta(days=i), 0.0), target))
        if hits >= PROTEIN_WEEK_MIN_HITS:
            out.append(ws)
    return sorted(out)


def consecutive_protein_weeks(day_grams: dict[dt.date, float], target: float,
                              today: dt.date) -> int:
    """Consecutive protein weeks ending at the current or previous week."""
    qualified = set(protein_weeks(day_grams, target))
    ws = week_start(today)
    streak = 0
    if ws in qualified:
        streak += 1
    ws -= dt.timedelta(days=7)
    while ws in qualified:
        streak += 1
        ws -= dt.timedelta(days=7)
    return streak


# ------------------------------------------------------------ XP and levels


def total_xp(*, total_sessions: int, protein_hit_days: int,
             n_full_weeks: int, n_protein_weeks: int) -> int:
    """Recompute lifetime XP from history aggregates (single source of truth)."""
    return (total_sessions * XP_PER_WORKOUT
            + protein_hit_days * XP_PER_PROTEIN_DAY
            + n_full_weeks * XP_PER_FULL_WEEK
            + n_protein_weeks * XP_PER_PROTEIN_WEEK)


def level_for_xp(xp: int) -> tuple[int, str, int, int]:
    """-> (level 1-based, title, xp into this level, xp span of this level).

    Cumulative XP to reach level L is 100*L*(L-1); level L spans 200*L XP.
    """
    level = 1
    while 100 * (level + 1) * level <= xp:
        level += 1
    into = xp - 100 * level * (level - 1)
    span = 200 * level
    title = LEVEL_TITLES[min(level - 1, len(LEVEL_TITLES) - 1)]
    return level, title, into, span


# ------------------------------------------------------------ achievements


def evaluate_workout_badges(
    *,
    day_sessions: dict[dt.date, int],
    days_per_week: int,
    day_grams: dict[dt.date, float],
    protein_target: float,
    today: dt.date,
    level: int,
    already: set[str],
) -> list[str]:
    """Return badge keys newly earned (not in `already`)."""
    earned: list[str] = []

    def add(key: str, cond: bool) -> None:
        if cond and key not in already:
            earned.append(key)

    total = sum(1 for n in day_sessions.values() if n > 0)
    streak = current_workout_streak(day_sessions, today)
    fw = full_weeks(day_sessions, days_per_week)
    pw = set(protein_weeks(day_grams, protein_target))
    perfect = any(ws in pw for ws in fw)

    # Protein daily streak (mirror of neutron's current_streak, kept local so
    # this module stays importable without a profile).
    p_streak = 0
    if protein_target > 0:
        d = today if day_hit(day_grams.get(today, 0.0), protein_target) else today - dt.timedelta(days=1)
        while day_hit(day_grams.get(d, 0.0), protein_target):
            p_streak += 1
            d -= dt.timedelta(days=1)

    add("first_session", total >= 1)
    add("weekly_warrior", len(fw) >= 1)
    add("perfect_week", perfect)
    add("consistency_beast", consecutive_full_weeks(day_sessions, days_per_week, today) >= 4)
    add("streak_3", streak >= 3)
    add("streak_7", streak >= 7)
    add("sessions_10", total >= 10)
    add("sessions_50", total >= 50)
    add("protein_pro", p_streak >= 7)
    add("macro_machine", consecutive_protein_weeks(day_grams, protein_target, today) >= 4)
    return earned


def week_motivation(completed: int, target: int) -> str:
    """Microcopy for the weekly challenge, stable within a day's state."""
    if target <= 0:
        return "Set up your training habits to start the weekly challenge."
    if completed >= target:
        return MOTIVATION_WEEK_DONE[completed % len(MOTIVATION_WEEK_DONE)]
    if completed >= target - 1:
        return MOTIVATION_WEEK_CLOSE[completed % len(MOTIVATION_WEEK_CLOSE)]
    return MOTIVATION_WEEK_OPEN[completed % len(MOTIVATION_WEEK_OPEN)]

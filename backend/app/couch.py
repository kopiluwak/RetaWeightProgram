"""Couch-to-Weights — beginner progressive-onboarding logic (see COUCH_TO_WEIGHTS_SPEC.md).

Pure and framework-free (stdlib only, no FastAPI/DB) so it is deterministic and
unit-testable. The router passes in plain values (the stored ramp state + the active
program's `plan_json`) and gets back the beginner view.

Model recap: the beginner keeps their normal 3/4/5-day split, but each *day* starts
with one exercise and reveals one more per calendar week. This module never touches
the medical prescription (reps/RIR/rest) — it only decides how many exercises of each
day to show, gently caps the sets of the newest movement, and produces the coaching
copy + level-up decision.
"""
from __future__ import annotations

import datetime as dt

# Per-set time cost (minutes) — mirrors engine.py so est_minutes stays consistent.
_COST_COMPOUND = 3.5
_COST_ACCESSORY = 2.5
_WARMUP_MIN = 8

LADDER_MAX = 6          # full complement caps at 6 exercises/day -> ~6-week ramp (D5)
_NEW_MOVE_SETS = 2      # a brand-new exercise starts at 2 working sets (8-15 min Week 1)
_WEEK_DAYS = 7


# ---------------------------------------------------------------------------
# Clock / target math
# ---------------------------------------------------------------------------
def _aware(t: dt.datetime) -> dt.datetime:
    """Coerce to timezone-aware UTC (DB may hand back naive datetimes)."""
    return t if t.tzinfo is not None else t.replace(tzinfo=dt.timezone.utc)


def week_number(started_at: dt.datetime, now: dt.datetime) -> int:
    """1-based calendar week since the ramp began. Week 1 is the first 7 days."""
    elapsed = (_aware(now) - _aware(started_at)).total_seconds()
    return 1 + int(max(0.0, elapsed) // (_WEEK_DAYS * 86400))


def program_full(program: dict) -> int:
    """Full daily routine size = min(LADDER_MAX, longest day in the program)."""
    days = program.get("days") or []
    longest = max((len(d.get("exercises") or []) for d in days), default=0)
    return min(LADDER_MAX, longest)


def nudge_level(consecutive_skips: int) -> int:
    """0 normally; 1 after one skip; 2 after two or more consecutive skips."""
    if consecutive_skips <= 0:
        return 0
    return 1 if consecutive_skips == 1 else 2


def decision_due(*, unlocked: int, target: int, week: int, snoozed_week: int, graduated: bool) -> bool:
    """A +1 is offered when the user is behind the calendar target and hasn't already
    snoozed this week. Keys off `target` (not a per-level clock) so a user who fell
    behind is offered +1 repeatedly until caught up — always one at a time (D6)."""
    return (not graduated) and unlocked < target and week > snoozed_week


# ---------------------------------------------------------------------------
# Per-day reveal
# ---------------------------------------------------------------------------
def _cost(compound: bool) -> float:
    return _COST_COMPOUND if compound else _COST_ACCESSORY


def _reveal_day(day: dict, unlocked: int) -> dict:
    """Return a copy of `day` showing only its first `unlocked` exercises.

    Exercises are revealed in the engine's authored order: the templates put each
    day's primary compound first, then the paired secondary muscle (triceps on a
    push day, biceps on a pull day), so a 1-exercise day is the primary lift and a
    2-exercise day is the intended push/pull pairing. The newest revealed move is
    capped to 2 sets. est_minutes is recomputed for the shortened day.
    """
    exercises = list(day.get("exercises") or [])
    take = min(max(0, unlocked), len(exercises))
    revealed: list[dict] = []
    for pos in range(take):
        ex = dict(exercises[pos])  # never mutate the stored plan_json
        # The newest movement on this day (last one revealed) eases in at 2 sets.
        if pos == take - 1 and take == unlocked:
            ex["sets"] = min(int(ex.get("sets", _NEW_MOVE_SETS)), _NEW_MOVE_SETS)
        revealed.append(ex)
    est = int(_WARMUP_MIN + sum(_cost(bool(e.get("compound"))) * int(e.get("sets", 0)) for e in revealed))
    return {
        "name": day.get("name", ""),
        "exercises": revealed,
        "gaps": list(day.get("gaps") or []),
        "est_minutes": est,
    }


def couch_days(program: dict, unlocked: int) -> list[dict]:
    """Every training day, each revealing its first `unlocked` exercises."""
    return [_reveal_day(d, unlocked) for d in (program.get("days") or [])]


def _newest_exercise_name(program: dict, unlocked: int) -> str | None:
    """Name of the freshest movement (Day 1's `unlocked`-th exercise), for copy."""
    days = program.get("days") or []
    if not days:
        return None
    day0 = couch_days(program, unlocked)[0]
    exs = day0.get("exercises") or []
    return exs[-1]["name"] if exs else None


# ---------------------------------------------------------------------------
# Coaching copy (single source of truth for app + any future chat surface)
# ---------------------------------------------------------------------------
def _plural(n: int) -> str:
    return "" if n == 1 else "s"


def build_message(*, unlocked: int, full: int, week: int, graduated: bool,
                  decision: bool, nudge: int, new_name: str | None,
                  just_added: bool = False, just_skipped: bool = False) -> str:
    """The warm coach line for the current state (COUCH spec §7)."""
    name = new_name or "your next move"
    if graduated:
        return (f"That's the full routine — {full} exercises a day. You built it one week "
                f"at a time from a single move. This is a real milestone. 🎉")
    if just_skipped:
        return (f"No problem — consistency first. We'll stay at {unlocked} exercise"
                f"{_plural(unlocked)} a day this week and lock in the habit.")
    if just_added:
        return (f"Nice — {name} is in. You're now at {unlocked} exercise{_plural(unlocked)} "
                f"a day. Small steps, real progress. 💪")
    if decision:
        if nudge >= 2:
            return (f"You've built a solid base at {unlocked} exercise{_plural(unlocked)} a day — "
                    f"that consistency is exactly what makes adding the next one easy. Let's give "
                    f"it a try this week; I think you're more ready than you feel. Add {name}?")
        if nudge == 1:
            return (f"Last week we stayed at {unlocked} so you could lock in the habit. This week's "
                    f"the perfect time to add the next one — it only takes a few extra minutes and "
                    f"your body is ready. Shall we level up?")
        return (f"You're rolling. Add exercise #{unlocked + 1} this week — {name}. It only adds a "
                f"few minutes and your body's ready. Level up?")
    if unlocked == 1:
        return ("Week 1 — just one move per training day. Nail it and you've already started. "
                "8–15 minutes, that's it. 💪")
    return (f"You're at {unlocked} exercise{_plural(unlocked)} a day and on track. Keep logging — "
            f"the next add unlocks next week.")


def couch_view(*, program: dict, unlocked: int, started_at: dt.datetime,
               snoozed_week: int, consecutive_skips: int, graduated: bool,
               now: dt.datetime, added_name: str | None = None,
               just_added: bool = False, just_skipped: bool = False) -> dict:
    """Assemble the full CouchViewOut payload from ramp state + active program.

    `unlocked` is clamped to `full` here so a shorter regenerated program can't leave
    the user above their ceiling. Returns a plain dict (router wraps in CouchViewOut).
    """
    full = program_full(program)
    unlocked = max(1, min(unlocked, full)) if full else max(1, unlocked)
    graduated = graduated or (full > 0 and unlocked >= full)
    week = week_number(started_at, now)
    target = min(week, full) if full else week
    due = decision_due(unlocked=unlocked, target=target, week=week,
                       snoozed_week=snoozed_week, graduated=graduated)
    nudge = nudge_level(consecutive_skips)
    new_name = _newest_exercise_name(program, min(unlocked + 1, full) if due else unlocked)
    message = build_message(
        unlocked=unlocked, full=full, week=week, graduated=graduated,
        decision=due, nudge=nudge, new_name=new_name,
        just_added=just_added, just_skipped=just_skipped,
    )
    return {
        "mode": True,
        "week": week,
        "unlocked": unlocked,
        "full": full,
        "graduated": graduated,
        "decision_due": due,
        "nudge_level": nudge,
        "headline": f"Week {week} · {unlocked} exercise{_plural(unlocked)} per day",
        "message": message,
        "added_today": added_name if just_added else None,
        "added_reason": (f"The next foundational movement in your routine — {added_name}."
                         if (just_added and added_name) else None),
        "days": couch_days(program, unlocked),
    }

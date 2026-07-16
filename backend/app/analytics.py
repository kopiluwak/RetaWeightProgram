"""Analytics math (Reporting & Analytics v1).

Pure data + helpers, stdlib only — same philosophy as exercises.py/progression.py:
everything here is testable without a framework. The router feeds it plain rows.

Locked spec (BUILD: analytics v1):
- e1RM = weight * (1 + (reps + rir)/30), only when reps + rir <= 12.
- PR event = session-best e1RM exceeding all prior session bests, requiring
  >= 3 prior sessions of that exercise (no "PR" spam in week one).
- Volume = sum(weight * reps); NULL-weight sets contribute 0 volume and are
  excluded from e1RM (they get rep trends instead).
- Plateau: >= 6 sessions total AND >= 3 sessions in last 6 weeks AND no e1RM PR
  in last 6 weeks AND e1RM slope over the window <= 0.
- Projection: linear regression on last-90d session-best e1RM; only shown when
  slope > 0, >= 5 points, and the +2.5% target lands within 12 weeks.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass

from .exercises import LIBRARY

# ---------------------------------------------------------------- constants

E1RM_MAX_EFFECTIVE_REPS = 12
PR_MIN_PRIOR_SESSIONS = 3
PLATEAU_MIN_SESSIONS = 6
PLATEAU_WINDOW_WEEKS = 6
PLATEAU_MIN_RECENT_SESSIONS = 3
PROJECTION_WINDOW_DAYS = 90
PROJECTION_MIN_POINTS = 5
PROJECTION_MAX_HORIZON_WEEKS = 12
PROJECTION_TARGET_FACTOR = 1.025  # "+1 increment" ≈ 2.5% over current PR

RANGES_DAYS: dict[str, int | None] = {"30d": 30, "90d": 90, "6m": 183, "1y": 365, "all": None}

# name (lowercased) -> Exercise, for muscle/pattern rollups (spec F5)
_CATALOG = {e.name.strip().lower(): e for e in LIBRARY}
OTHER_MUSCLE = "other"


def muscles_for(exercise_name: str) -> tuple[str, ...]:
    """Primary muscles for an exercise name; ("other",) if not in the library."""
    e = _CATALOG.get(exercise_name.strip().lower())
    return e.primary if e else (OTHER_MUSCLE,)


# ---------------------------------------------------------------- primitives

@dataclass(frozen=True)
class SetRow:
    """One logged set, flattened. `when` is the set's local timestamp
    (router applies the client's tz offset before handing rows over)."""
    exercise: str
    weight: float | None
    reps: int
    rir: int
    when: dt.datetime
    session_id: str


def e1rm(weight: float | None, reps: int, rir: int) -> float | None:
    """Estimated 1RM (Epley, RIR-adjusted); None if the set isn't eligible
    (unweighted, zero reps, or effective reps beyond the accuracy ceiling)."""
    if weight is None or weight <= 0 or reps <= 0:
        return None
    effective = reps + max(rir, 0)
    if effective > E1RM_MAX_EFFECTIVE_REPS:
        return None
    return round(weight * (1 + effective / 30.0), 1)


def set_volume(weight: float | None, reps: int) -> float:
    """Tonnage for one set; NULL-weight sets contribute 0 by spec."""
    return (weight or 0.0) * reps


def week_start(d: dt.date) -> dt.date:
    """The Monday that starts the week containing `d`."""
    return d - dt.timedelta(days=d.weekday())  # Monday


def linreg(points: list[tuple[float, float]]) -> tuple[float, float] | None:
    """Least squares (slope, intercept); None if degenerate."""
    n = len(points)
    if n < 2:
        return None
    sx = sum(p[0] for p in points)
    sy = sum(p[1] for p in points)
    sxx = sum(p[0] * p[0] for p in points)
    sxy = sum(p[0] * p[1] for p in points)
    denom = n * sxx - sx * sx
    if denom == 0:
        return None
    slope = (n * sxy - sx * sy) / denom
    return slope, (sy - slope * sx) / n


# ------------------------------------------------------------- per exercise

@dataclass(frozen=True)
class SessionBest:
    date: dt.date
    e1rm: float | None       # best e1RM-eligible set that session
    top_weight: float | None  # heaviest weight that session
    top_weight_reps: int      # reps at that weight
    best_reps: int            # most reps in a single set (for unloaded work)
    volume: float             # exercise volume that session


def session_bests(rows: list[SetRow]) -> list[SessionBest]:
    """Collapse an exercise's set rows into one point per session, ordered by date."""
    by_session: dict[str, list[SetRow]] = defaultdict(list)
    for r in rows:
        by_session[r.session_id].append(r)
    out: list[SessionBest] = []
    for sets in by_session.values():
        date = min(s.when for s in sets).date()
        e1s = [v for s in sets if (v := e1rm(s.weight, s.reps, s.rir)) is not None]
        weighted = [s for s in sets if s.weight is not None]
        top_w = max((s.weight for s in weighted), default=None)
        top_w_reps = max((s.reps for s in weighted if s.weight == top_w), default=0) if top_w else 0
        out.append(SessionBest(
            date=date,
            e1rm=max(e1s) if e1s else None,
            top_weight=top_w,
            top_weight_reps=top_w_reps,
            best_reps=max(s.reps for s in sets),
            volume=sum(set_volume(s.weight, s.reps) for s in sets),
        ))
    return sorted(out, key=lambda b: b.date)


@dataclass(frozen=True)
class PrEvent:
    date: dt.date
    kind: str          # "e1rm" | "weight"
    value: float
    previous: float


def pr_events(bests: list[SessionBest]) -> list[PrEvent]:
    """PRs in chronological order. A PR needs >= PR_MIN_PRIOR_SESSIONS prior
    sessions with a comparable value, so early sessions don't all 'PR'."""
    out: list[PrEvent] = []
    for kind, values in (
        ("e1rm", [(b.date, b.e1rm) for b in bests if b.e1rm is not None]),
        ("weight", [(b.date, b.top_weight) for b in bests if b.top_weight is not None]),
    ):
        running: float | None = None
        for i, (date, v) in enumerate(values):
            if running is not None and v > running and i >= PR_MIN_PRIOR_SESSIONS:
                out.append(PrEvent(date=date, kind=kind, value=v, previous=running))
            running = v if running is None else max(running, v)
    return sorted(out, key=lambda p: p.date)


def pct_change(series: list[tuple[dt.date, float]]) -> float | None:
    """Percent change from first to last point; None if undefined."""
    if len(series) < 2 or series[0][1] == 0:
        return None
    return round((series[-1][1] / series[0][1] - 1) * 100, 1)


def detect_plateau(bests: list[SessionBest], today: dt.date) -> bool:
    """Apply the locked plateau rule (see module docstring) to one exercise."""
    pts = [(b.date, b.e1rm) for b in bests if b.e1rm is not None]
    if len(pts) < PLATEAU_MIN_SESSIONS:
        return False
    cutoff = today - dt.timedelta(weeks=PLATEAU_WINDOW_WEEKS)
    recent = [(d, v) for d, v in pts if d >= cutoff]
    if len(recent) < PLATEAU_MIN_RECENT_SESSIONS:
        return False
    if any(p.date >= cutoff for p in pr_events(bests) if p.kind == "e1rm"):
        return False
    fit = linreg([(d.toordinal(), v) for d, v in recent])
    # <= 0 with an epsilon: on a perfectly flat series float noise can yield a
    # slope of ~1e-13, which must still count as "not progressing".
    return fit is not None and fit[0] <= 1e-9


@dataclass(frozen=True)
class Projection:
    target: float
    date: dt.date


def project_pr(bests: list[SessionBest], today: dt.date) -> Projection | None:
    """Forecast when the next ~+2.5% e1RM PR lands, or None if the trend
    doesn't qualify (too few points, non-positive slope, or beyond horizon)."""
    cutoff = today - dt.timedelta(days=PROJECTION_WINDOW_DAYS)
    pts = [(b.date, b.e1rm) for b in bests if b.e1rm is not None and b.date >= cutoff]
    if len(pts) < PROJECTION_MIN_POINTS:
        return None
    fit = linreg([(d.toordinal(), v) for d, v in pts])
    if fit is None or fit[0] <= 0:
        return None
    slope, intercept = fit
    current_pr = max(v for _, v in pts)
    target = round(current_pr * PROJECTION_TARGET_FACTOR, 1)
    cross = (target - intercept) / slope
    # Horizon-check the raw float BEFORE building a date: a near-zero slope
    # (flat lift + float noise) puts the crossing millions of days out, which
    # would overflow date.fromordinal.
    horizon = (today + dt.timedelta(weeks=PROJECTION_MAX_HORIZON_WEEKS)).toordinal()
    if not (today.toordinal() < cross <= horizon):
        return None
    return Projection(target=target, date=dt.date.fromordinal(int(round(cross))))


# ------------------------------------------------------------ whole-account

def bucket_weekly(rows: list[SetRow], value=lambda r: set_volume(r.weight, r.reps)) -> list[tuple[dt.date, float]]:
    """Sum `value(row)` per calendar week (keyed by Monday), sorted by week."""
    acc: dict[dt.date, float] = defaultdict(float)
    for r in rows:
        acc[week_start(r.when.date())] += value(r)
    return sorted(acc.items())


def workouts_per_week(session_dates: list[dt.date], weeks: int, today: dt.date) -> list[tuple[dt.date, int]]:
    """Count of distinct workout days per week for the trailing `weeks` weeks
    (inclusive of the current week), zero-filled."""
    this_week = week_start(today)
    counts: dict[dt.date, set[dt.date]] = defaultdict(set)
    for d in session_dates:
        counts[week_start(d)].add(d)
    return [
        (w, len(counts.get(w, set())))
        for w in (this_week - dt.timedelta(weeks=i) for i in range(weeks - 1, -1, -1))
    ]


def weekly_streak(session_dates: list[dt.date], target: int, today: dt.date) -> int:
    """Consecutive weeks meeting `target` distinct workout days, counting back
    from the current week. A current week that hasn't hit target yet doesn't
    break the streak (it's still in progress); it just doesn't add to it."""
    per_week: dict[dt.date, set[dt.date]] = defaultdict(set)
    for d in session_dates:
        per_week[week_start(d)].add(d)
    w = week_start(today)
    streak = 0
    if len(per_week.get(w, set())) >= target:
        streak += 1
    w -= dt.timedelta(weeks=1)
    while len(per_week.get(w, set())) >= target:
        streak += 1
        w -= dt.timedelta(weeks=1)
    return streak


def month_volume(rows: list[SetRow], year: int, month: int) -> float:
    """Total tonnage logged within one calendar month."""
    return sum(
        set_volume(r.weight, r.reps)
        for r in rows
        if r.when.year == year and r.when.month == month
    )


def muscle_volume_split(rows: list[SetRow]) -> dict[str, float]:
    """Volume attributed to primary muscles, split evenly across an exercise's
    primaries so the parts sum to total volume."""
    acc: dict[str, float] = defaultdict(float)
    for r in rows:
        v = set_volume(r.weight, r.reps)
        if v <= 0:
            continue
        primaries = muscles_for(r.exercise)
        share = v / len(primaries)
        for m in primaries:
            acc[m] += share
    return {m: round(v, 1) for m, v in sorted(acc.items(), key=lambda kv: -kv[1])}


def daily_set_counts(rows: list[SetRow]) -> dict[dt.date, int]:
    """Sets logged per calendar day (feeds the consistency heatmap)."""
    acc: dict[dt.date, int] = defaultdict(int)
    for r in rows:
        acc[r.when.date()] += 1
    return dict(acc)

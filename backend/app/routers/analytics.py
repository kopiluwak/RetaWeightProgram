"""Analytics router (Reporting & Analytics v1).

  GET /analytics/summary            everything the Progress dashboard needs, one payload
  GET /analytics/exercises          searchable exercise list for the trends picker
  GET /analytics/exercises/{name}   per-exercise trend series + PRs + insights
  GET /analytics/history            heatmap day-cells + filterable session list

All aggregation is server-side (spec F2). Clients pass `tz` = minutes east of
UTC (JS: -new Date().getTimezoneOffset()) so days/weeks/months bucket in the
user's local time. Only completed sessions count.
"""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..analytics import (
    RANGES_DAYS,
    Projection,
    SetRow,
    bucket_weekly,
    daily_set_counts,
    detect_plateau,
    month_volume,
    muscle_volume_split,
    muscles_for,
    pct_change,
    pr_events,
    project_pr,
    session_bests,
    weekly_streak,
    workouts_per_week,
)
from ..database import get_db
from ..deps import get_current_user
from ..models import SetLog, User, UserHabits, WorkoutSession

router = APIRouter(prefix="/analytics", tags=["analytics"])

# ------------------------------------------------------------------ schemas


class WeekCount(BaseModel):
    week_start: str
    count: int


class ConsistencyOut(BaseModel):
    target_per_week: int
    this_week: int
    streak_weeks: int
    weeks: list[WeekCount]  # trailing 12, oldest first


class VolumeOut(BaseModel):
    this_month: float
    last_month: float
    pct_change: float | None


class PrOut(BaseModel):
    exercise: str
    kind: str  # "e1rm" | "weight"
    value: float
    previous: float
    date: str


class ImprovedOut(BaseModel):
    exercise: str
    pct: float
    sessions: int


class MuscleShareOut(BaseModel):
    muscle: str
    volume: float
    share: float  # 0..1


class SummaryOut(BaseModel):
    consistency: ConsistencyOut
    volume: VolumeOut
    recent_prs: list[PrOut]
    most_improved: list[ImprovedOut]
    muscle_focus: list[MuscleShareOut]


class ExerciseListItem(BaseModel):
    name: str
    muscles: list[str]
    sessions: int
    last_performed: str


class Point(BaseModel):
    date: str
    value: float


class BestSetOut(BaseModel):
    date: str
    weight: float
    reps: int


class ExercisePrsOut(BaseModel):
    e1rm: Point | None
    weight: BestSetOut | None


class ProjectionOut(BaseModel):
    target: float
    date: str


class ExerciseDetailOut(BaseModel):
    exercise: str
    range: str
    unloaded: bool
    e1rm_series: list[Point]
    volume_weekly: list[Point]
    best_sets: list[BestSetOut]
    reps_series: list[Point]
    pct_change: float | None
    prs: ExercisePrsOut
    plateau: bool
    plateau_message: str | None
    projection: ProjectionOut | None


class DayCell(BaseModel):
    date: str
    sets: int
    volume: float


class HistorySessionOut(BaseModel):
    id: str
    date: str
    day_name: str
    set_count: int
    volume: float
    exercises: list[str]
    muscles: list[str]


class HistoryOut(BaseModel):
    days: list[DayCell]
    sessions: list[HistorySessionOut]


# ------------------------------------------------------------------ helpers


def _tz(minutes: int) -> dt.timedelta:
    return dt.timedelta(minutes=max(-840, min(840, minutes)))


async def _load_rows(db: AsyncSession, user_id: str, tz: dt.timedelta) -> list[SetRow]:
    """All logged sets from completed sessions, dated in the user's local time.
    Sets inherit the session's start time so a workout is one calendar day."""
    rows = (await db.execute(
        select(SetLog, WorkoutSession.started_at, WorkoutSession.id)
        .join(WorkoutSession, SetLog.session_id == WorkoutSession.id)
        .where(WorkoutSession.user_id == user_id, WorkoutSession.status == "completed")
        .order_by(WorkoutSession.started_at)
    )).all()
    return [
        SetRow(
            exercise=s.exercise_name, weight=s.weight, reps=s.reps, rir=s.rir,
            when=started.replace(tzinfo=None) + tz if started.tzinfo is None
            else started.astimezone(dt.timezone.utc).replace(tzinfo=None) + tz,
            session_id=sid,
        )
        for s, started, sid in rows
    ]


def _today(tz: dt.timedelta) -> dt.date:
    return (dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) + tz).date()


def _by_exercise(rows: list[SetRow]) -> dict[str, list[SetRow]]:
    out: dict[str, list[SetRow]] = {}
    for r in rows:
        out.setdefault(r.exercise, []).append(r)
    return out


def _cut(rows: list[SetRow], days: int | None, today: dt.date) -> list[SetRow]:
    if days is None:
        return rows
    cutoff = today - dt.timedelta(days=days)
    return [r for r in rows if r.when.date() >= cutoff]


def _proj_out(p: Projection | None) -> ProjectionOut | None:
    return ProjectionOut(target=p.target, date=p.date.isoformat()) if p else None


# ---------------------------------------------------------------- endpoints


@router.get("/summary", response_model=SummaryOut)
async def summary(
    tz: int = Query(0, description="minutes east of UTC"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    off = _tz(tz)
    today = _today(off)
    rows = await _load_rows(db, user.id, off)

    habits = (await db.execute(
        select(UserHabits).where(UserHabits.user_id == user.id)
    )).scalar_one_or_none()
    target = habits.days_per_week if habits else 3

    session_dates = sorted({r.when.date() for r in rows})
    weeks = workouts_per_week(session_dates, 12, today)

    # Volume: calendar month vs last, local time.
    first_of_month = today.replace(day=1)
    last_month_anchor = first_of_month - dt.timedelta(days=1)
    this_m = month_volume(rows, today.year, today.month)
    last_m = month_volume(rows, last_month_anchor.year, last_month_anchor.month)
    vol_pct = round((this_m / last_m - 1) * 100, 1) if last_m > 0 else None

    # PRs (e1RM only on the dashboard) in the last 30 days, newest first.
    pr_cutoff = today - dt.timedelta(days=30)
    prs: list[PrOut] = []
    improved: list[ImprovedOut] = []
    window_90 = today - dt.timedelta(days=90)
    for name, ex_rows in _by_exercise(rows).items():
        bests = session_bests(ex_rows)
        for p in pr_events(bests):
            if p.kind == "e1rm" and p.date >= pr_cutoff:
                prs.append(PrOut(exercise=name, kind=p.kind, value=p.value,
                                 previous=p.previous, date=p.date.isoformat()))
        recent = [(b.date, b.e1rm) for b in bests if b.e1rm is not None and b.date >= window_90]
        if len(recent) >= 4:
            pct = pct_change(recent)
            if pct is not None and pct > 0:
                improved.append(ImprovedOut(exercise=name, pct=pct, sessions=len(recent)))
    prs.sort(key=lambda p: p.date, reverse=True)
    improved.sort(key=lambda i: i.pct, reverse=True)

    # Muscle focus: last 30 days.
    split = muscle_volume_split(_cut(rows, 30, today))
    total = sum(split.values()) or 1.0
    focus = [MuscleShareOut(muscle=m, volume=v, share=round(v / total, 3)) for m, v in split.items()]

    return SummaryOut(
        consistency=ConsistencyOut(
            target_per_week=target,
            this_week=weeks[-1][1],
            streak_weeks=weekly_streak(session_dates, target, today),
            weeks=[WeekCount(week_start=w.isoformat(), count=c) for w, c in weeks],
        ),
        volume=VolumeOut(this_month=round(this_m, 1), last_month=round(last_m, 1), pct_change=vol_pct),
        recent_prs=prs[:5],
        most_improved=improved[:3],
        muscle_focus=focus,
    )


@router.get("/exercises", response_model=list[ExerciseListItem])
async def exercise_list(
    tz: int = Query(0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = await _load_rows(db, user.id, _tz(tz))
    out: list[ExerciseListItem] = []
    for name, ex_rows in _by_exercise(rows).items():
        dates = sorted({r.when.date() for r in ex_rows})
        out.append(ExerciseListItem(
            name=name, muscles=list(muscles_for(name)),
            sessions=len({r.session_id for r in ex_rows}),
            last_performed=dates[-1].isoformat(),
        ))
    out.sort(key=lambda e: e.last_performed, reverse=True)
    return out


@router.get("/exercises/{name}", response_model=ExerciseDetailOut)
async def exercise_detail(
    name: str,
    range: str = Query("90d"),
    tz: int = Query(0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if range not in RANGES_DAYS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"range must be one of {list(RANGES_DAYS)}")
    off = _tz(tz)
    today = _today(off)
    all_rows = [r for r in await _load_rows(db, user.id, off) if r.exercise == name]
    if not all_rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No logged sets for that exercise")

    rows = _cut(all_rows, RANGES_DAYS[range], today)
    bests_all = session_bests(all_rows)     # PRs/plateau/projection use full history
    bests = session_bests(rows)             # series respect the selected range

    e1_series = [(b.date, b.e1rm) for b in bests if b.e1rm is not None]
    reps_series = [(b.date, float(b.best_reps)) for b in bests]
    unloaded = not any(r.weight is not None for r in all_rows)

    # All-time PRs.
    e1_all = [(b.date, b.e1rm) for b in bests_all if b.e1rm is not None]
    pr_e1 = max(e1_all, key=lambda p: p[1]) if e1_all else None
    weighted = [b for b in bests_all if b.top_weight is not None]
    pr_w = max(weighted, key=lambda b: (b.top_weight, b.top_weight_reps)) if weighted else None

    plateau = detect_plateau(bests_all, today)
    return ExerciseDetailOut(
        exercise=name, range=range, unloaded=unloaded,
        e1rm_series=[Point(date=d.isoformat(), value=v) for d, v in e1_series],
        volume_weekly=[Point(date=d.isoformat(), value=round(v, 1)) for d, v in bucket_weekly(rows)],
        best_sets=[BestSetOut(date=b.date.isoformat(), weight=b.top_weight, reps=b.top_weight_reps)
                   for b in bests if b.top_weight is not None],
        reps_series=[Point(date=d.isoformat(), value=v) for d, v in reps_series] if unloaded else [],
        pct_change=pct_change(reps_series if unloaded else e1_series),
        prs=ExercisePrsOut(
            e1rm=Point(date=pr_e1[0].isoformat(), value=pr_e1[1]) if pr_e1 else None,
            weight=BestSetOut(date=pr_w.date.isoformat(), weight=pr_w.top_weight,
                              reps=pr_w.top_weight_reps) if pr_w else None,
        ),
        plateau=plateau,
        plateau_message=(
            f"{name} has been flat for about {6} weeks. That's normal in a deficit — "
            "a deload week or a different rep range often gets things moving again."
            if plateau else None
        ),
        projection=_proj_out(project_pr(bests_all, today)),
    )


@router.get("/history", response_model=HistoryOut)
async def history(
    range: str = Query("6m"),
    exercise: str | None = Query(None),
    muscle: str | None = Query(None),
    tz: int = Query(0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if range not in RANGES_DAYS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"range must be one of {list(RANGES_DAYS)}")
    off = _tz(tz)
    today = _today(off)
    rows = _cut(await _load_rows(db, user.id, off), RANGES_DAYS[range], today)

    day_volume: dict[dt.date, float] = {}
    for r in rows:
        day_volume[r.when.date()] = day_volume.get(r.when.date(), 0.0) + (r.weight or 0.0) * r.reps
    days = [
        DayCell(date=d.isoformat(), sets=n, volume=round(day_volume.get(d, 0.0), 1))
        for d, n in sorted(daily_set_counts(rows).items())
    ]

    # Session list (filters apply here, not to the heatmap).
    sessions: dict[str, list[SetRow]] = {}
    for r in rows:
        sessions.setdefault(r.session_id, []).append(r)
    meta = {
        s.id: s for s in (await db.execute(
            select(WorkoutSession).where(WorkoutSession.user_id == user.id,
                                         WorkoutSession.id.in_(list(sessions))))
        ).scalars().all()
    } if sessions else {}

    items: list[HistorySessionOut] = []
    for sid, srows in sessions.items():
        names = sorted({r.exercise for r in srows})
        muscles = sorted({m for n in names for m in muscles_for(n)})
        if exercise and not any(exercise.lower() in n.lower() for n in names):
            continue
        if muscle and muscle.lower() not in muscles:
            continue
        items.append(HistorySessionOut(
            id=sid,
            date=min(r.when for r in srows).date().isoformat(),
            day_name=meta[sid].day_name if sid in meta else "",
            set_count=len(srows),
            volume=round(sum((r.weight or 0.0) * r.reps for r in srows), 1),
            exercises=names, muscles=muscles,
        ))
    items.sort(key=lambda i: i.date, reverse=True)
    return HistoryOut(days=days, sessions=items)

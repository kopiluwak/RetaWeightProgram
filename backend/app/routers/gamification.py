"""Gamification router — one-call payload for the home-screen hero.

  GET /gamification/summary   XP + level, workout streaks, weekly challenge,
                              protein progress, weekly overview, achievements

Everything is recomputed from WorkoutSession + ProteinLog history on each
read (see app/gamification.py for the rationale); only achievement awards
are persisted. Newly earned achievements are awarded as a side effect of
reading the summary, so the app never needs a separate "check badges" call.
"""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..deps import get_current_user
from ..gamification import (
    WORKOUT_BADGES,
    XP_PER_FULL_WEEK,
    XP_PER_PROTEIN_DAY,
    XP_PER_PROTEIN_WEEK,
    XP_PER_WORKOUT,
    best_workout_streak,
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
from ..models import NutritionProfile, ProteinLog, User, UserHabits, WorkoutBadge, WorkoutSession
from ..neutron_gamification import current_streak as protein_streak
from ..neutron_gamification import best_streak as best_protein_streak
from ..neutron_gamification import day_hit, total_hit_days

router = APIRouter(prefix="/gamification", tags=["gamification"])


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _local_date(ts: dt.datetime, tz_minutes: int) -> dt.date:
    """Calendar date of a UTC timestamp in the client's local time."""
    return (ts + dt.timedelta(minutes=tz_minutes)).date()


# ------------------------------------------------------------------ schemas


class XpOut(BaseModel):
    total: int
    level: int
    level_title: str
    xp_into_level: int
    level_span: int          # XP width of the current level
    per_workout: int         # award sizes, so the UI can promise them upfront
    per_protein_day: int
    per_full_week: int
    per_protein_week: int


class WorkoutStatsOut(BaseModel):
    sessions_this_week: int
    target_per_week: int
    week_pct: int            # 0-100, capped
    current_streak: int
    longest_streak: int
    total_sessions: int


class ProteinStatsOut(BaseModel):
    target_g: float | None
    today_g: float
    today_pct: int | None    # 0-100+, uncapped so the bar can overfill
    week_hit_days: int
    week_avg_g: float
    daily_streak: int
    best_daily_streak: int


class WeekBadgeOut(BaseModel):
    week_start: str
    completed: int
    target: int
    pct: int


class AchievementOut(BaseModel):
    key: str
    name: str
    description: str
    earned: bool
    awarded_at: str | None


class GamificationSummaryOut(BaseModel):
    xp: XpOut
    workout: WorkoutStatsOut
    protein: ProteinStatsOut
    weeks: list[WeekBadgeOut]
    achievements: list[AchievementOut]
    newly_earned: list[str]
    message: str


# ------------------------------------------------------------------ helpers


async def _day_sessions(db: AsyncSession, user_id: str, tz: int) -> dict[dt.date, int]:
    """Completed workout sessions per local calendar day (all history)."""
    rows = (await db.execute(
        select(WorkoutSession.completed_at)
        .where(WorkoutSession.user_id == user_id, WorkoutSession.status == "completed")
    )).scalars().all()
    acc: dict[dt.date, int] = {}
    for ts in rows:
        if ts is None:
            continue
        d = _local_date(ts, tz)
        acc[d] = acc.get(d, 0) + 1
    return acc


async def _day_grams(db: AsyncSession, user_id: str, tz: int,
                     since_days: int = 400) -> dict[dt.date, float]:
    """Protein grams per local day (same aggregate the nutrition router uses)."""
    cutoff = _now() - dt.timedelta(days=since_days)
    rows = (await db.execute(
        select(ProteinLog.grams, ProteinLog.logged_at)
        .where(ProteinLog.user_id == user_id, ProteinLog.logged_at >= cutoff)
    )).all()
    acc: dict[dt.date, float] = {}
    for grams, ts in rows:
        d = _local_date(ts, tz)
        acc[d] = acc.get(d, 0.0) + grams
    return acc


# ------------------------------------------------------------------ endpoint


@router.get("/summary", response_model=GamificationSummaryOut)
async def summary(tz: int = Query(default=0, ge=-840, le=840),
                  user: User = Depends(get_current_user),
                  db: AsyncSession = Depends(get_db)):
    today = _local_date(_now(), tz)

    habits = (await db.execute(
        select(UserHabits).where(UserHabits.user_id == user.id)
    )).scalar_one_or_none()
    target_per_week = habits.days_per_week if habits else 3

    prof = (await db.execute(
        select(NutritionProfile).where(NutritionProfile.user_id == user.id)
    )).scalar_one_or_none()
    protein_target = (prof.protein_target_g if prof else None) or 0.0

    day_sessions = await _day_sessions(db, user.id, tz)
    day_grams = await _day_grams(db, user.id, tz)

    # --- XP / level ---
    total_sessions = sum(1 for n in day_sessions.values() if n > 0)
    hit_days = total_hit_days(day_grams, protein_target)
    n_full = len(full_weeks(day_sessions, target_per_week))
    n_protein = len(protein_weeks(day_grams, protein_target))
    xp = total_xp(total_sessions=total_sessions, protein_hit_days=hit_days,
                  n_full_weeks=n_full, n_protein_weeks=n_protein)
    level, title, into, span = level_for_xp(xp)

    # --- weekly challenge ---
    this_ws = week_start(today)
    done_this_week = sessions_in_week(day_sessions, this_ws)
    week_pct = round(100 * min(1.0, done_this_week / target_per_week)) if target_per_week else 0

    # --- protein (this week = Mon-Sun so it matches the workout challenge) ---
    today_g = round(day_grams.get(today, 0.0), 1)
    week_days_elapsed = (today - this_ws).days + 1
    week_grams = [day_grams.get(this_ws + dt.timedelta(days=i), 0.0)
                  for i in range(week_days_elapsed)]
    week_hits = sum(1 for g in week_grams if day_hit(g, protein_target))
    week_avg = round(sum(week_grams) / max(1, week_days_elapsed), 1)

    # --- achievements (award new ones as a side effect of reading) ---
    earned_rows = (await db.execute(
        select(WorkoutBadge).where(WorkoutBadge.user_id == user.id)
    )).scalars().all()
    earned = {b.badge_key: b.awarded_at for b in earned_rows}
    new_keys = evaluate_workout_badges(
        day_sessions=day_sessions, days_per_week=target_per_week,
        day_grams=day_grams, protein_target=protein_target,
        today=today, level=level, already=set(earned),
    )
    for k in new_keys:
        db.add(WorkoutBadge(user_id=user.id, badge_key=k))
    await db.commit()
    now = _now()
    achievements = [AchievementOut(
        key=k, name=n, description=desc,
        earned=k in earned or k in new_keys,
        awarded_at=(earned[k].isoformat() if k in earned
                    else now.isoformat() if k in new_keys else None),
    ) for k, (n, desc) in WORKOUT_BADGES.items()]

    return GamificationSummaryOut(
        xp=XpOut(total=xp, level=level, level_title=title, xp_into_level=into,
                 level_span=span, per_workout=XP_PER_WORKOUT,
                 per_protein_day=XP_PER_PROTEIN_DAY, per_full_week=XP_PER_FULL_WEEK,
                 per_protein_week=XP_PER_PROTEIN_WEEK),
        workout=WorkoutStatsOut(
            sessions_this_week=done_this_week, target_per_week=target_per_week,
            week_pct=week_pct,
            current_streak=current_workout_streak(day_sessions, today),
            longest_streak=best_workout_streak(day_sessions),
            total_sessions=total_sessions),
        protein=ProteinStatsOut(
            target_g=protein_target or None, today_g=today_g,
            today_pct=round(100 * today_g / protein_target) if protein_target else None,
            week_hit_days=week_hits, week_avg_g=week_avg,
            daily_streak=protein_streak(day_grams, protein_target, today),
            best_daily_streak=best_protein_streak(day_grams, protein_target)),
        weeks=[WeekBadgeOut(**w) for w in weeks_overview(day_sessions, target_per_week, today)],
        achievements=achievements,
        newly_earned=new_keys,
        message=week_motivation(done_this_week, target_per_week),
    )

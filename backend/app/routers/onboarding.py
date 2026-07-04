"""Onboarding / habits router (spec onboarding decision).

Captures the inputs the program engine needs in later increments:
  - days_per_week (3|4|5)  -> selects the primary split
  - session_minutes        -> per-session set budget (default 60)
  - experience             -> volume band + movement complexity (default conservative)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings, get_settings
from ..database import get_db
from ..deps import get_current_user
from ..models import User, UserHabits
from ..schemas import HabitsIn, HabitsOut, MeOut

router = APIRouter(tags=["onboarding"])


def _habits_out(h: UserHabits | None) -> HabitsOut | None:
    if h is None:
        return None
    return HabitsOut(
        days_per_week=h.days_per_week,
        session_minutes=h.session_minutes,
        experience=h.experience,
        onboarded=h.onboarded,
    )


@router.get("/me", response_model=MeOut)
async def me(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    habits = (await db.execute(
        select(UserHabits).where(UserHabits.user_id == user.id)
    )).scalar_one_or_none()
    return MeOut(
        id=user.id,
        email=user.email,
        email_verified=user.email_verified,
        training_mode=user.training_mode,
        habits=_habits_out(habits),
    )


@router.put("/habits", response_model=HabitsOut)
async def set_habits(
    body: HabitsIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    habits = (await db.execute(
        select(UserHabits).where(UserHabits.user_id == user.id)
    )).scalar_one_or_none()
    if habits is None:
        habits = UserHabits(user_id=user.id)
        db.add(habits)
    habits.days_per_week = body.days_per_week
    habits.session_minutes = body.session_minutes
    habits.experience = body.experience
    habits.onboarded = True
    await db.commit()
    return _habits_out(habits)


@router.get("/habits/defaults", response_model=HabitsOut)
async def habits_defaults(settings: Settings = Depends(get_settings)):
    """Pre-fill values for the onboarding screen before the user customizes."""
    return HabitsOut(
        days_per_week=3,
        session_minutes=settings.default_session_minutes,
        experience=settings.default_experience,
        onboarded=False,
    )

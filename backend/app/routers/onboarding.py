"""Onboarding / habits router (spec onboarding decision).

Captures the inputs the program engine needs in later increments:
  - days_per_week (3|4|5)  -> selects the primary split
  - session_minutes        -> per-session set budget (default 60)
  - experience             -> volume band + movement complexity (default conservative)
"""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import couch as couch_logic
from ..config import Settings, get_settings
from ..database import get_db
from ..deps import get_current_user
from ..models import Program, User, UserHabits
from ..schemas import CouchStateOut, HabitsIn, HabitsOut, MeOut

router = APIRouter(tags=["onboarding"])


async def _active_program(db: AsyncSession, user_id: str) -> Program | None:
    """The user's active generated program (Couch derives its view from this)."""
    return (await db.execute(
        select(Program)
        .where(Program.user_id == user_id, Program.status == "active")
        .order_by(Program.created_at.desc())
    )).scalars().first()


async def _couch_state(db: AsyncSession, h: UserHabits) -> CouchStateOut | None:
    """Compact Couch state for /me, or None when the user isn't a beginner.

    Needs the active program to compute `full`/`decision_due`; if none exists yet
    (beginner hasn't generated a program), returns a pre-program placeholder so the
    app still knows the mode is on.
    """
    if not h.couch_mode:
        return None
    started = h.couch_started_at or couch_logic.dt.datetime.now(dt.timezone.utc)
    program = await _active_program(db, h.user_id)
    if program is None:
        week = couch_logic.week_number(started, dt.datetime.now(dt.timezone.utc))
        return CouchStateOut(mode=True, week=week, unlocked=h.couch_unlocked, full=0,
                             graduated=h.couch_graduated, decision_due=False,
                             nudge_level=couch_logic.nudge_level(h.couch_consecutive_skips))
    v = couch_logic.couch_view(
        program=program.plan_json, unlocked=h.couch_unlocked, started_at=started,
        snoozed_week=h.couch_snoozed_week, consecutive_skips=h.couch_consecutive_skips,
        graduated=h.couch_graduated, now=dt.datetime.now(dt.timezone.utc),
    )
    return CouchStateOut(mode=True, week=v["week"], unlocked=v["unlocked"], full=v["full"],
                         graduated=v["graduated"], decision_due=v["decision_due"],
                         nudge_level=v["nudge_level"])


def _habits_out(h: UserHabits | None, couch: CouchStateOut | None = None) -> HabitsOut | None:
    """Map the ORM habits row to its response schema (None passes through)."""
    if h is None:
        return None
    return HabitsOut(
        days_per_week=h.days_per_week,
        session_minutes=h.session_minutes,
        experience=h.experience,
        onboarded=h.onboarded,
        couch=couch,
    )


@router.get("/me", response_model=MeOut)
async def me(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Current user's profile + habits (the app's post-login bootstrap call)."""
    habits = (await db.execute(
        select(UserHabits).where(UserHabits.user_id == user.id)
    )).scalar_one_or_none()
    couch = await _couch_state(db, habits) if habits else None
    return MeOut(
        id=user.id,
        email=user.email,
        email_verified=user.email_verified,
        training_mode=user.training_mode,
        habits=_habits_out(habits, couch),
    )


@router.put("/habits", response_model=HabitsOut)
async def set_habits(
    body: HabitsIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create or update the user's habits; marks onboarding complete."""
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

    # Couch-to-Weights: the beginner option enables the progressive ramp. Initialize
    # the ramp only on the first switch into beginner (don't reset an in-progress
    # ramp if they re-save onboarding). Switching away makes the mode dormant but
    # keeps the state, so returning to beginner resumes where they left off.
    now = dt.datetime.now(dt.timezone.utc)
    if body.experience == "beginner":
        if not habits.couch_mode and habits.couch_started_at is None:
            habits.couch_started_at = now
            habits.couch_unlocked = 1
            habits.couch_snoozed_week = 0
            habits.couch_consecutive_skips = 0
            habits.couch_graduated = False
        habits.couch_mode = True
    else:
        habits.couch_mode = False

    await db.commit()
    couch = await _couch_state(db, habits)
    return _habits_out(habits, couch)


@router.get("/habits/defaults", response_model=HabitsOut)
async def habits_defaults(settings: Settings = Depends(get_settings)):
    """Pre-fill values for the onboarding screen before the user customizes."""
    return HabitsOut(
        days_per_week=3,
        session_minutes=settings.default_session_minutes,
        experience=settings.default_experience,
        onboarded=False,
    )

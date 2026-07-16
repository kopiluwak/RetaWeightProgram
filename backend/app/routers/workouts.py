"""Workout logging router (spec S3 #4 readiness/RIR, #6 progression).

  POST /workouts/start              start a session for a program day (+ readiness)
  POST /workouts/{id}/log           append a logged set
  POST /workouts/{id}/finish        complete the session, return progression suggestions
  GET  /workouts/history            recent sessions (summary)
  GET  /workouts/{id}               a session with its sets
"""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database import get_db
from ..deps import get_current_user
from ..models import Program, SetLog, User, WorkoutSession
from ..progression import LoggedSet, suggest_for_session
from ..schemas import (
    LastSetOut,
    LogSetIn,
    ProgressionSuggestionOut,
    SetLogOut,
    StartWorkoutIn,
    WorkoutHistoryItem,
    WorkoutSessionOut,
)

router = APIRouter(prefix="/workouts", tags=["workouts"])


def _now() -> dt.datetime:
    """Timezone-aware UTC now."""
    return dt.datetime.now(dt.timezone.utc)


def _iso(d: dt.datetime | None) -> str | None:
    """ISO-8601 string or None (timestamps cross the wire as strings)."""
    return d.isoformat() if d else None


def _session_out(s: WorkoutSession, suggestions=None) -> WorkoutSessionOut:
    """Map a session (sets must be loaded) to its response schema; sets are
    ordered by exercise then set number for a stable UI display."""
    return WorkoutSessionOut(
        id=s.id, program_id=s.program_id, day_index=s.day_index, day_name=s.day_name,
        readiness=s.readiness, status=s.status,
        started_at=_iso(s.started_at), completed_at=_iso(s.completed_at),
        sets=[SetLogOut(id=x.id, exercise_name=x.exercise_name, set_number=x.set_number,
                        reps=x.reps, rir=x.rir, weight=x.weight)
              for x in sorted(s.sets, key=lambda x: (x.exercise_name, x.set_number))],
        suggestions=[ProgressionSuggestionOut(exercise_name=g.exercise_name, action=g.action, message=g.message)
                     for g in (suggestions or [])],
    )


async def _load_session(db: AsyncSession, session_id: str, user_id: str) -> WorkoutSession:
    """Fetch an owned session with sets eagerly loaded; 404 if absent."""
    s = (await db.execute(
        select(WorkoutSession)
        .where(WorkoutSession.id == session_id, WorkoutSession.user_id == user_id)
        .options(selectinload(WorkoutSession.sets))
    )).scalar_one_or_none()
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workout session not found")
    return s


@router.post("/start", response_model=WorkoutSessionOut)
async def start(
    body: StartWorkoutIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Open a session for one program day, capturing pre-workout readiness."""
    # Resolve the program (explicit id or the active one).
    if body.program_id:
        program = (await db.execute(
            select(Program).where(Program.id == body.program_id, Program.user_id == user.id)
        )).scalar_one_or_none()
    else:
        program = (await db.execute(
            select(Program).where(Program.user_id == user.id, Program.status == "active")
            .order_by(Program.created_at.desc())
        )).scalars().first()
    if program is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No program found — generate one first")

    days = program.plan_json.get("days", [])
    if body.day_index >= len(days):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"day_index out of range (0..{len(days)-1})")

    session = WorkoutSession(
        user_id=user.id, program_id=program.id, day_index=body.day_index,
        day_name=days[body.day_index].get("name", f"Day {body.day_index + 1}"),
        readiness=body.readiness,
    )
    db.add(session)
    await db.commit()
    return await _session_out_loaded(db, session.id, user.id)


async def _session_out_loaded(db, sid, uid):
    """Reload a session fresh from the DB and serialize it."""
    return _session_out(await _load_session(db, sid, uid))


@router.post("/{session_id}/log", response_model=WorkoutSessionOut)
async def log_set(
    session_id: str,
    body: LogSetIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Append one logged set to an in-progress session (409 if finished)."""
    session = await _load_session(db, session_id, user.id)
    if session.status != "in_progress":
        raise HTTPException(status.HTTP_409_CONFLICT, "Session already completed")
    db.add(SetLog(
        session_id=session.id, exercise_name=body.exercise_name, reps_range=body.reps_range,
        set_number=body.set_number, weight=body.weight, reps=body.reps, rir=body.rir,
    ))
    await db.commit()
    return await _session_out_loaded(db, session.id, user.id)


@router.post("/{session_id}/finish", response_model=WorkoutSessionOut)
async def finish(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Close the session and return next-time progression suggestions."""
    session = await _load_session(db, session_id, user.id)
    session.status = "completed"
    session.completed_at = _now()
    await db.commit()
    session = await _load_session(db, session_id, user.id)

    # Build progression suggestions from the logged sets (spec S3 #6).
    logged: dict[str, tuple[str, list[LoggedSet]]] = {}
    for s in session.sets:
        reps_range = s.reps_range or "5-8"
        logged.setdefault(s.exercise_name, (reps_range, []))[1].append(LoggedSet(reps=s.reps, rir=s.rir))
    suggestions = suggest_for_session(logged)
    return _session_out(session, suggestions)


@router.get("/history", response_model=list[WorkoutHistoryItem])
async def history(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """All sessions newest-first, summarized for the history list."""
    sessions = (await db.execute(
        select(WorkoutSession)
        .where(WorkoutSession.user_id == user.id)
        .order_by(WorkoutSession.started_at.desc())
        .options(selectinload(WorkoutSession.sets))
    )).scalars().all()
    return [
        WorkoutHistoryItem(id=s.id, day_name=s.day_name, status=s.status,
                           started_at=_iso(s.started_at), set_count=len(s.sets))
        for s in sessions
    ]


@router.get("/last-performance", response_model=dict[str, LastSetOut])
async def last_performance(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Most recent logged weight/reps/RIR per exercise, for pre-filling the logger.
    Defined before /{session_id} so the literal path isn't captured as an id."""
    rows = (await db.execute(
        select(SetLog)
        .join(WorkoutSession, SetLog.session_id == WorkoutSession.id)
        .where(WorkoutSession.user_id == user.id)
        .order_by(SetLog.logged_at.desc())
    )).scalars().all()
    out: dict[str, LastSetOut] = {}
    for s in rows:
        if s.exercise_name not in out:  # rows are newest-first, so first wins
            out[s.exercise_name] = LastSetOut(weight=s.weight, reps=s.reps, rir=s.rir)
    return out


@router.get("/{session_id}", response_model=WorkoutSessionOut)
async def get_session(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """One session with all of its logged sets."""
    return _session_out(await _load_session(db, session_id, user.id))

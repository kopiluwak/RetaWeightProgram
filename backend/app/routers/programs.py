"""Programs router (spec S2/S3/S4/S5).

  POST /programs/generate   build a program from current confirmed inventory + habits
  GET  /programs/current    latest active program (+ stale flag vs newest inventory)
  GET  /programs/{id}       fetch a specific program
"""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified

from .. import couch as couch_logic
from .. import custom_exercise as cx
from ..config import Settings, get_settings
from ..database import get_db
from ..deps import get_current_user
from ..engine import generate_program
from ..exercises import LIBRARY
from ..models import InventoryVersion, Program, User, UserHabits
from ..schemas import (
    AddExerciseIn,
    ClassifiedExerciseOut,
    ClassifyExerciseIn,
    CouchAdvanceIn,
    CouchViewOut,
    ExerciseLibraryItemOut,
    GenerateProgramIn,
    MessageOut,
    ProgramOut,
    RemoveExerciseIn,
)


# `beginner` is a Couch-to-Weights (UI/API) value the volume engine doesn't know;
# map it to the conservative band so no engine change is needed (COUCH spec §2).
def _engine_experience(experience: str) -> str:
    return "conservative" if experience == "beginner" else experience

router = APIRouter(prefix="/programs", tags=["programs"])


async def _latest_confirmed_inventory(db: AsyncSession, user_id: str) -> InventoryVersion | None:
    """Active inventory (latest confirmed version) with items eagerly loaded."""
    return (await db.execute(
        select(InventoryVersion)
        .where(InventoryVersion.user_id == user_id, InventoryVersion.status == "confirmed")
        .order_by(InventoryVersion.version_no.desc())
        .options(selectinload(InventoryVersion.items))
    )).scalars().first()


def _to_out(program: Program, latest_inventory_id: str | None) -> ProgramOut:
    """Map an ORM program row + its stored plan JSON to the response schema.
    `stale` flags that the inventory changed since this program was built (S5)."""
    plan = program.plan_json
    return ProgramOut(
        id=program.id,
        days_per_week=program.days_per_week,
        session_minutes=program.session_minutes,
        experience=program.experience,
        inventory_version_id=program.inventory_version_id,
        stale=(latest_inventory_id is not None and program.inventory_version_id != latest_inventory_id),
        created_at=program.created_at.isoformat(),
        days=plan["days"],
        weekly_volume=plan["weekly_volume"],
        notes=plan["notes"],
        gaps=plan["gaps"],
    )


@router.post("/generate", response_model=ProgramOut)
async def generate(
    body: GenerateProgramIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate and persist a new active program; prior actives are superseded.

    Requires a confirmed inventory and completed onboarding (400 otherwise).
    """
    habits = (await db.execute(
        select(UserHabits).where(UserHabits.user_id == user.id)
    )).scalar_one_or_none()
    if habits is None or not habits.onboarded:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Complete onboarding (training habits) first")

    # Equipment customization: persist any provided preference before applying it.
    if body.bodyweight_only is not None:
        habits.gen_bodyweight_only = body.bodyweight_only
    if body.equipment_types is not None:
        # An empty list means "no specific restriction" — store null (= all).
        habits.gen_equipment_types = body.equipment_types or None

    inventory = await _latest_confirmed_inventory(db, user.id)
    # A confirmed inventory is required unless the user opted into bodyweight-only.
    if not habits.gen_bodyweight_only and (inventory is None or not inventory.items):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "No confirmed equipment inventory yet — scan and confirm your equipment first")

    days = body.days_per_week or habits.days_per_week

    if habits.gen_bodyweight_only:
        selected = []  # no equipment -> engine picks only bodyweight movements
    elif habits.gen_equipment_types:
        allowed = set(habits.gen_equipment_types)
        selected = [it for it in inventory.items if it.type in allowed]
    else:
        selected = list(inventory.items)

    items = [{"type": it.type} for it in selected]
    plan = generate_program(
        items, days, habits.session_minutes, _engine_experience(habits.experience)
    ).to_dict()

    # Supersede prior active programs (one active program at a time).
    prior = (await db.execute(
        select(Program).where(Program.user_id == user.id, Program.status == "active")
    )).scalars().all()
    for p in prior:
        p.status = "superseded"

    inventory_id = inventory.id if inventory else None
    program = Program(
        user_id=user.id, inventory_version_id=inventory_id,
        days_per_week=days, session_minutes=habits.session_minutes,
        experience=habits.experience, plan_json=plan, status="active",
    )
    db.add(program)
    await db.commit()
    await db.refresh(program)
    return _to_out(program, inventory_id)


@router.get("/current", response_model=ProgramOut | None)
async def current(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The user's active program, or null if none has been generated."""
    program = (await db.execute(
        select(Program)
        .where(Program.user_id == user.id, Program.status == "active")
        .order_by(Program.created_at.desc())
    )).scalars().first()
    if program is None:
        return None
    latest_inv = await _latest_confirmed_inventory(db, user.id)
    return _to_out(program, latest_inv.id if latest_inv else None)


# ---------------------------------------------------------------------------
# Couch-to-Weights (beginner progressive onboarding). See COUCH_TO_WEIGHTS_SPEC.md.
#
# NOTE: the static `/couch*` routes MUST be declared before the dynamic
# `/{program_id}` route (defined at the bottom of this file). FastAPI matches in
# definition order, so a `/{program_id}` declared first would capture
# `GET /programs/couch` as program_id="couch" and 404 with "Program not found".
# ---------------------------------------------------------------------------
async def _couch_habits_and_program(db: AsyncSession, user_id: str) -> tuple[UserHabits, Program]:
    """Load the ramp state + active program, or raise the right 400."""
    habits = (await db.execute(
        select(UserHabits).where(UserHabits.user_id == user_id)
    )).scalar_one_or_none()
    if habits is None or not habits.couch_mode:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Couch-to-Weights isn't active for this user")
    program = (await db.execute(
        select(Program)
        .where(Program.user_id == user_id, Program.status == "active")
        .order_by(Program.created_at.desc())
    )).scalars().first()
    if program is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Generate a program first, then your beginner plan appears")
    return habits, program


def _started(habits: UserHabits) -> dt.datetime:
    return habits.couch_started_at or dt.datetime.now(dt.timezone.utc)


@router.get("/couch", response_model=CouchViewOut)
async def couch_view(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The beginner's current view: ramp state + each day's first `unlocked` moves.

    Persists graduation/clamping if a regenerated (shorter) program pushed the user
    to or past the full complement, so state stays consistent across reads.
    """
    habits, program = await _couch_habits_and_program(db, user.id)
    now = dt.datetime.now(dt.timezone.utc)
    v = couch_logic.couch_view(
        program=program.plan_json, unlocked=habits.couch_unlocked, started_at=_started(habits),
        snoozed_week=habits.couch_snoozed_week, consecutive_skips=habits.couch_consecutive_skips,
        graduated=habits.couch_graduated, now=now,
    )
    if v["unlocked"] != habits.couch_unlocked or v["graduated"] != habits.couch_graduated:
        habits.couch_unlocked = v["unlocked"]
        habits.couch_graduated = v["graduated"]
        await db.commit()
    return CouchViewOut(**v)


@router.post("/couch/advance", response_model=CouchViewOut)
async def couch_advance(
    body: CouchAdvanceIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Apply the user's level-up decision (add exactly one, or defer this week)."""
    habits, program = await _couch_habits_and_program(db, user.id)
    now = dt.datetime.now(dt.timezone.utc)
    state = couch_logic.couch_view(
        program=program.plan_json, unlocked=habits.couch_unlocked, started_at=_started(habits),
        snoozed_week=habits.couch_snoozed_week, consecutive_skips=habits.couch_consecutive_skips,
        graduated=habits.couch_graduated, now=now,
    )
    if not state["decision_due"]:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "No level-up is available right now — check back next week")

    full = state["full"]
    added_name = None
    if body.action == "add":
        habits.couch_unlocked = min(habits.couch_unlocked + 1, full) if full else habits.couch_unlocked + 1
        habits.couch_consecutive_skips = 0
        if full and habits.couch_unlocked >= full:
            habits.couch_graduated = True
        added_name = couch_logic._newest_exercise_name(program.plan_json, habits.couch_unlocked)
    else:  # skip
        habits.couch_consecutive_skips += 1
        habits.couch_snoozed_week = state["week"]
    await db.commit()

    v = couch_logic.couch_view(
        program=program.plan_json, unlocked=habits.couch_unlocked, started_at=_started(habits),
        snoozed_week=habits.couch_snoozed_week, consecutive_skips=habits.couch_consecutive_skips,
        graduated=habits.couch_graduated, now=now, added_name=added_name,
        just_added=(body.action == "add"), just_skipped=(body.action == "skip"),
    )
    return CouchViewOut(**v)


@router.post("/couch/restart", response_model=MessageOut)
async def couch_restart(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Restart the beginner ramp from Week 1 (one exercise per day).

    Sets experience to `beginner`, re-arms Couch mode, and resets the ramp clock.
    Workout history and the active program are left untouched — this only rewinds
    the reveal state, so nothing the user logged is lost.
    """
    habits = (await db.execute(
        select(UserHabits).where(UserHabits.user_id == user.id)
    )).scalar_one_or_none()
    if habits is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Complete onboarding first")
    habits.experience = "beginner"
    habits.couch_mode = True
    habits.couch_started_at = dt.datetime.now(dt.timezone.utc)
    habits.couch_unlocked = 1
    habits.couch_snoozed_week = 0
    habits.couch_consecutive_skips = 0
    habits.couch_graduated = False
    await db.commit()
    return MessageOut(message="Restarted at Week 1 — one exercise per day. Your history is safe.")


@router.post("/couch/graduate", response_model=MessageOut)
async def couch_graduate(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Skip the rest of the ramp and move straight to the full program."""
    habits = (await db.execute(
        select(UserHabits).where(UserHabits.user_id == user.id)
    )).scalar_one_or_none()
    if habits is None or not habits.couch_mode:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Couch-to-Weights isn't active for this user")
    habits.couch_graduated = True
    await db.commit()
    return MessageOut(message="Graduated to your full program. Nice work — you built up to it.")


# ---------------------------------------------------------------------------
# Add-your-own-exercise: pick a known movement OR suggest one you saw on social
# media. Both land on the correct muscle-group day of the active program.
#
# NOTE (same rule as the couch routes): these static `/exercise*` paths MUST be
# declared before the dynamic `/{program_id}` catch-all at the bottom.
# ---------------------------------------------------------------------------
async def _active_program(db: AsyncSession, user_id: str) -> Program:
    """The user's active program, or a 400 telling them to generate one first."""
    program = (await db.execute(
        select(Program)
        .where(Program.user_id == user_id, Program.status == "active")
        .order_by(Program.created_at.desc())
    )).scalars().first()
    if program is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Generate a program first, then you can add exercises to it")
    return program


@router.get("/exercise-library", response_model=list[ExerciseLibraryItemOut])
async def exercise_library(user: User = Depends(get_current_user)):
    """Every pickable known movement (pull-up, push-up, isolation curl, …) for
    the 'choose a specific exercise' picker. Static data — no program needed."""
    return [ExerciseLibraryItemOut(**c) for c in cx.library_choices()]


@router.post("/exercises/classify", response_model=ClassifiedExerciseOut)
async def classify_exercise(
    body: ClassifyExerciseIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Resolve free text (an exercise the user saw) into a muscle group + form
    cue, and say which day it would land on — WITHOUT adding it yet, so the user
    can confirm or override. Library match first, Bedrock only if that misses."""
    program = await _active_program(db, user.id)
    classified = await cx.classify_exercise(body.text, settings)
    idx = cx.best_day_index(program.plan_json.get("days", []), classified.primary)
    days = program.plan_json.get("days", [])
    day_name = days[idx].get("name", f"Day {idx + 1}") if days else ""
    return ClassifiedExerciseOut(
        name=classified.name, primary=classified.primary, compound=classified.compound,
        description=classified.description, confidence=classified.confidence,
        source=classified.source, suggested_day_index=idx, suggested_day_name=day_name,
    )


@router.post("/exercises/add", response_model=ProgramOut)
async def add_exercise(
    body: AddExerciseIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add an exercise to the active program on the right muscle-group day and
    persist it. Accepts either a `library_id` or custom `name` + `primary`."""
    program = await _active_program(db, user.id)

    if body.library_id:
        match = next((e for e in LIBRARY if e.id == body.library_id), None)
        if match is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown exercise")
        pe = cx.make_program_exercise(
            match.name, list(match.primary), match.compound, match.description, body.sets
        )
    else:
        if not body.name or not body.primary:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "Provide either a library_id or name + primary muscles")
        pe = cx.make_program_exercise(
            body.name, body.primary, body.compound, body.description, body.sets
        )

    idx, _ = cx.add_exercise_to_plan(program.plan_json, pe, body.day_index)
    flag_modified(program, "plan_json")  # JSON dict mutated in place — mark dirty
    await db.commit()
    await db.refresh(program)
    latest_inv = await _latest_confirmed_inventory(db, user.id)
    return _to_out(program, latest_inv.id if latest_inv else None)


@router.post("/exercises/remove", response_model=ProgramOut)
async def remove_exercise(
    body: RemoveExerciseIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a user-added exercise (by day + name). Only user-added movements
    can be removed — generated exercises are left in place."""
    program = await _active_program(db, user.id)
    removed = cx.remove_exercise_from_plan(program.plan_json, body.day_index, body.name)
    if not removed:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "No user-added exercise by that name on that day")
    flag_modified(program, "plan_json")
    await db.commit()
    await db.refresh(program)
    latest_inv = await _latest_confirmed_inventory(db, user.id)
    return _to_out(program, latest_inv.id if latest_inv else None)


# Dynamic catch-all LAST so it never shadows the static routes above.
@router.get("/{program_id}", response_model=ProgramOut)
async def get_program(
    program_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fetch one program by id (404 if not found or not owned by the caller)."""
    program = (await db.execute(
        select(Program).where(Program.id == program_id, Program.user_id == user.id)
    )).scalar_one_or_none()
    if program is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Program not found")
    latest_inv = await _latest_confirmed_inventory(db, user.id)
    return _to_out(program, latest_inv.id if latest_inv else None)

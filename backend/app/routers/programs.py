"""Programs router (spec S2/S3/S4/S5).

  POST /programs/generate   build a program from current confirmed inventory + habits
  GET  /programs/current    latest active program (+ stale flag vs newest inventory)
  GET  /programs/{id}       fetch a specific program
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database import get_db
from ..deps import get_current_user
from ..engine import generate_program
from ..models import InventoryVersion, Program, User, UserHabits
from ..schemas import GenerateProgramIn, ProgramOut

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
    inventory = await _latest_confirmed_inventory(db, user.id)
    if inventory is None or not inventory.items:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "No confirmed equipment inventory yet — scan and confirm your equipment first")

    habits = (await db.execute(
        select(UserHabits).where(UserHabits.user_id == user.id)
    )).scalar_one_or_none()
    if habits is None or not habits.onboarded:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Complete onboarding (training habits) first")

    days = body.days_per_week or habits.days_per_week

    items = [{"type": it.type} for it in inventory.items]
    plan = generate_program(items, days, habits.session_minutes, habits.experience).to_dict()

    # Supersede prior active programs (one active program at a time).
    prior = (await db.execute(
        select(Program).where(Program.user_id == user.id, Program.status == "active")
    )).scalars().all()
    for p in prior:
        p.status = "superseded"

    program = Program(
        user_id=user.id, inventory_version_id=inventory.id,
        days_per_week=days, session_minutes=habits.session_minutes,
        experience=habits.experience, plan_json=plan, status="active",
    )
    db.add(program)
    await db.commit()
    await db.refresh(program)
    return _to_out(program, inventory.id)


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

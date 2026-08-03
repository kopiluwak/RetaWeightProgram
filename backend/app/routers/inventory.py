"""Inventory router (spec R1/R3/R1a/S1/S5).

Flow:
  POST /inventory/capture          upload image(s) + consent -> DRAFT version (recognized, unconfirmed)
  PUT  /inventory/{id}/confirm     submit user-corrected items -> CONFIRMED canonical version
  GET  /inventory                  current confirmed inventory
  POST /inventory/edit             manual edit -> NEW confirmed version (never mutates old one)
"""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..config import Settings, get_settings
from ..database import get_db
from ..deps import get_current_user
from ..equipment import is_valid_type
from ..models import CaptureSession, EquipmentItem, InventoryVersion, User
from ..recognition import build_recognizer
from ..schemas import (
    ConfirmInventoryIn,
    EditInventoryIn,
    EquipmentItemIn,
    EquipmentItemOut,
    InventoryVersionOut,
)
from ..storage import build_image_storage

router = APIRouter(prefix="/inventory", tags=["inventory"])


def _now() -> dt.datetime:
    """Timezone-aware UTC now."""
    return dt.datetime.now(dt.timezone.utc)


def _version_out(v: InventoryVersion) -> InventoryVersionOut:
    """Map an ORM version (items must already be loaded) to its response schema."""
    return InventoryVersionOut(
        id=v.id, version_no=v.version_no, status=v.status, source=v.source,
        items=[
            EquipmentItemOut(
                id=i.id, type=i.type, quantity=i.quantity, load_min=i.load_min,
                load_max=i.load_max, load_increment=i.load_increment,
                attributes=i.attributes, confidence=i.confidence, confirmed=i.confirmed,
            )
            for i in v.items
        ],
    )


async def _load_version_out(db: AsyncSession, version_id: str) -> InventoryVersionOut:
    """Re-fetch a version with its items eagerly loaded (selectinload), so the
    response serializer never triggers a lazy load outside the async context."""
    version = (await db.execute(
        select(InventoryVersion)
        .where(InventoryVersion.id == version_id)
        .options(selectinload(InventoryVersion.items))
    )).scalar_one()
    return _version_out(version)


async def _next_version_no(db: AsyncSession, user_id: str) -> int:
    """Next 1-based version number for this user's inventory history."""
    existing = (await db.execute(
        select(InventoryVersion.version_no).where(InventoryVersion.user_id == user_id)
    )).scalars().all()
    return (max(existing) + 1) if existing else 1


def _validate_items(items: list[EquipmentItemIn]) -> None:
    """400 if any submitted item uses a type outside the closed taxonomy."""
    for it in items:
        if not is_valid_type(it.type):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown equipment type: {it.type}")


async def _current_confirmed_items(db: AsyncSession, user_id: str) -> list[EquipmentItem]:
    """Items of the user's active (latest confirmed) inventory, or [] if none."""
    version = (await db.execute(
        select(InventoryVersion)
        .where(InventoryVersion.user_id == user_id, InventoryVersion.status == "confirmed")
        .order_by(InventoryVersion.version_no.desc())
        .options(selectinload(InventoryVersion.items))
    )).scalars().first()
    return list(version.items) if version else []


async def _supersede_confirmed(db: AsyncSession, user_id: str) -> None:
    """Mark all currently-confirmed versions superseded (a new one takes over)."""
    prior = (await db.execute(
        select(InventoryVersion).where(
            InventoryVersion.user_id == user_id, InventoryVersion.status == "confirmed"
        )
    )).scalars().all()
    for p in prior:
        p.status = "superseded"


@router.post("/capture", response_model=InventoryVersionOut)
async def capture(
    images: list[UploadFile] = File(...),
    consent_to_train: bool = Form(False),
    mode: str = Form("replace"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Run recognition on uploaded photos and return a DRAFT inventory version.

    `mode="replace"` (default) drafts only the newly recognized items — a full
    rescan. `mode="add"` merges the recognized items INTO the current confirmed
    inventory: an item whose type already exists bumps that type's quantity,
    otherwise it's appended. Either way the draft goes to the same confirm screen,
    so nothing becomes canonical until the user confirms.

    Photos are persisted (and the flywheel record kept) only with explicit
    consent; otherwise they are processed in memory and discarded.
    """
    if not images:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "At least one image required")
    if mode not in ("replace", "add"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "mode must be 'replace' or 'add'")

    raw = [await img.read() for img in images]

    recognizer = build_recognizer(settings)
    result = await recognizer.recognize(raw)

    # Draft version (unconfirmed) from the recognition result.
    version = InventoryVersion(
        user_id=user.id, version_no=await _next_version_no(db, user.id),
        status="draft", source=("photo_add" if mode == "add" else "photo"),
    )
    db.add(version)
    await db.flush()

    # Build the draft item set. In "add" mode we seed from the current confirmed
    # inventory (kept, quantities preserved), then merge recognized items in.
    merged: dict[str, dict] = {}
    order: list[str] = []
    if mode == "add":
        for it in await _current_confirmed_items(db, user.id):
            merged[it.type] = dict(
                type=it.type, quantity=it.quantity, load_min=it.load_min,
                load_max=it.load_max, load_increment=it.load_increment,
                attributes=it.attributes, confidence=None,
            )
            order.append(it.type)
    for r in result.items:
        t = r.type.value
        if t in merged:
            merged[t]["quantity"] += r.quantity  # duplicate type -> bump quantity
            # Keep existing load info; adopt recognized load only where missing.
            for k in ("load_min", "load_max", "load_increment"):
                if merged[t][k] is None:
                    merged[t][k] = getattr(r, k)
        else:
            merged[t] = dict(
                type=t, quantity=r.quantity, load_min=r.load_min, load_max=r.load_max,
                load_increment=r.load_increment, attributes=r.attributes, confidence=r.confidence,
            )
            order.append(t)
    for t in order:
        db.add(EquipmentItem(version_id=version.id, confirmed=False, **merged[t]))

    # Flywheel + image persistence — ONLY if the user consented (F8 / R1a).
    image_keys: list[str] = []
    if consent_to_train:
        storage = build_image_storage(settings)
        for data in raw:
            image_keys.append(storage.put(user.id, data))
    db.add(CaptureSession(
        user_id=user.id, consent_to_train=consent_to_train, image_keys=image_keys,
        recognizer=result.recognizer, draft_json=result.model_dump(mode="json"),
        resulting_version_id=version.id,
    ))

    await db.commit()
    return await _load_version_out(db, version.id)


@router.put("/{version_id}/confirm", response_model=InventoryVersionOut)
async def confirm(
    version_id: str,
    body: ConfirmInventoryIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Turn a draft into the canonical confirmed inventory using the user's
    corrected item list; also stores the correction into the flywheel record."""
    _validate_items(body.items)
    version = (await db.execute(
        select(InventoryVersion)
        .where(InventoryVersion.id == version_id, InventoryVersion.user_id == user.id)
        .options(selectinload(InventoryVersion.items))
    )).scalar_one_or_none()
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Inventory version not found")
    if version.status != "draft":
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a draft version can be confirmed")

    # Replace draft items with the user-corrected list (R3).
    for old in list(version.items):
        await db.delete(old)
    for it in body.items:
        db.add(EquipmentItem(
            version_id=version.id, type=it.type, quantity=it.quantity,
            load_min=it.load_min, load_max=it.load_max, load_increment=it.load_increment,
            attributes=it.attributes, confidence=None, confirmed=True,
        ))

    await _supersede_confirmed(db, user.id)
    version.status = "confirmed"
    version.confirmed_at = _now()

    # Close the flywheel triple with the corrected result.
    cap = (await db.execute(
        select(CaptureSession).where(CaptureSession.resulting_version_id == version.id)
    )).scalar_one_or_none()
    if cap is not None:
        cap.corrected_json = {"items": [it.model_dump(mode="json") for it in body.items]}

    await db.commit()
    return await _load_version_out(db, version.id)


@router.get("", response_model=InventoryVersionOut | None)
async def current_inventory(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The user's active (latest confirmed) inventory, or null if none yet."""
    version = (await db.execute(
        select(InventoryVersion)
        .where(InventoryVersion.user_id == user.id, InventoryVersion.status == "confirmed")
        .order_by(InventoryVersion.version_no.desc())
        .options(selectinload(InventoryVersion.items))
    )).scalars().first()
    return _version_out(version) if version else None


@router.post("/edit", response_model=InventoryVersionOut)
async def edit_inventory(
    body: EditInventoryIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Manual edit: creates a NEW confirmed version (spec S5 — never mutate the
    active one in place). The frontend prompts 'equipment changed — regenerate?'
    against the program engine in Increment 3."""
    _validate_items(body.items)
    version = InventoryVersion(
        user_id=user.id, version_no=await _next_version_no(db, user.id),
        status="draft", source="manual_edit",
    )
    db.add(version)
    await db.flush()
    for it in body.items:
        db.add(EquipmentItem(
            version_id=version.id, type=it.type, quantity=it.quantity,
            load_min=it.load_min, load_max=it.load_max, load_increment=it.load_increment,
            attributes=it.attributes, confidence=None, confirmed=True,
        ))
    await _supersede_confirmed(db, user.id)
    version.status = "confirmed"
    version.confirmed_at = _now()
    await db.commit()
    return await _load_version_out(db, version.id)

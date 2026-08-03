"""SQLAlchemy ORM models.

Spec notes:
- F8 data minimization: no password, no medication. We store a `training_mode`
  flag on the user, never the drug name.
- F3: OTP codes are short-lived, single-use, attempt-limited.
- F4: refresh tokens live server-side (registry) so logout/delete revokes them;
  `token_epoch` on the user enables instant "log out everywhere".
"""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _uuid() -> str:
    """Default factory for string (UUID4) primary keys."""
    return str(uuid.uuid4())


def _now() -> dt.datetime:
    """Default factory for timezone-aware UTC timestamps."""
    return dt.datetime.now(dt.timezone.utc)


class User(Base):
    """An account, identified by email (passwordless — OTP login only)."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)  # optional, store-only (F6)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # F8: training context only — NEVER the medication name.
    training_mode: Mapped[str] = mapped_column(String(40), default="deficit_preservation", nullable=False)

    # F4: bump to invalidate every outstanding access token for this user.
    token_epoch: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    habits: Mapped["UserHabits | None"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    inventory_versions: Mapped[list["InventoryVersion"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class OtpCode(Base):
    """A pending login code (F3): hashed, short-lived, single-use, attempt-limited."""

    __tablename__ = "otp_codes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(320), index=True, nullable=False)
    code_hash: Mapped[str] = mapped_column(String(128), nullable=False)  # sha256 hex, never plaintext
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    consumed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class RefreshToken(Base):
    """Server-side refresh-token registry entry (F4). Tokens are stored hashed;
    rotation marks the old row `used`, so reuse of a used token signals theft
    and revokes the whole family."""

    __tablename__ = "refresh_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    # Rotation lineage: a refresh issued from another points back to its parent.
    family_id: Mapped[str] = mapped_column(String(36), default=_uuid, index=True, nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # rotated already → reuse = theft
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    user: Mapped[User] = relationship(back_populates="refresh_tokens")


class UserHabits(Base):
    """Training preferences captured at onboarding; drive program generation."""

    __tablename__ = "user_habits"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    days_per_week: Mapped[int] = mapped_column(Integer, default=3, nullable=False)   # 3 | 4 | 5
    session_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    experience: Mapped[str] = mapped_column(String(20), default="conservative", nullable=False)
    onboarded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )

    # --- Couch-to-Weights (beginner progressive onboarding; see COUCH_TO_WEIGHTS_SPEC.md) ---
    # Per-user, not per-program, so the ramp survives program regeneration.
    couch_mode: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    couch_started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Exercises revealed PER DAY right now (Week 1 -> 1).
    couch_unlocked: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # The `week` number in which the user last tapped "Not yet" (snoozes prompts that
    # week only). 0 = never.
    couch_snoozed_week: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    couch_consecutive_skips: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    couch_graduated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # --- Program-generation preferences (equipment customization) ---
    # bodyweight_only ignores all equipment; gen_equipment_types (null = use ALL
    # owned types) restricts generation to a chosen subset of equipment types.
    gen_bodyweight_only: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    gen_equipment_types: Mapped[list | None] = mapped_column(JSON, nullable=True)

    user: Mapped[User] = relationship(back_populates="habits")


# ----------------------------------------------------------------------------
# Increment 2: equipment inventory (spec S1 versioned, R2 taxonomy, R1a flywheel)
# ----------------------------------------------------------------------------
class InventoryVersion(Base):
    """A point-in-time inventory. Edits never mutate a confirmed version in place
    (spec S5) — they create a new version. The user's *active* inventory is the
    latest version with status='confirmed'."""

    __tablename__ = "inventory_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-based, per user
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False)  # draft | confirmed | superseded
    source: Mapped[str] = mapped_column(String(16), default="photo", nullable=False)  # photo | manual_edit
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    confirmed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="inventory_versions")
    items: Mapped[list["EquipmentItem"]] = relationship(
        back_populates="version", cascade="all, delete-orphan"
    )
    capture: Mapped["CaptureSession | None"] = relationship(
        back_populates="resulting_version", uselist=False
    )


class EquipmentItem(Base):
    """One piece of equipment within an inventory version. `attributes` (JSON)
    holds type-specific fields: plate denominations, dumbbell increments, etc."""

    __tablename__ = "equipment_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    version_id: Mapped[str] = mapped_column(ForeignKey("inventory_versions.id", ondelete="CASCADE"), index=True, nullable=False)
    type: Mapped[str] = mapped_column(String(40), nullable=False)  # EquipmentType value
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    load_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    load_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    load_increment: Mapped[float | None] = mapped_column(Float, nullable=True)
    attributes: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    # Recognition provenance (null for manually-added items).
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    version: Mapped[InventoryVersion] = relationship(back_populates="items")


class CaptureSession(Base):
    """Flywheel record (spec R1a): the (image, LLM draft, corrected result) triple.
    Consent-gated (F8). Stored only when the user consents to training use."""

    __tablename__ = "capture_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    consent_to_train: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    image_keys: Mapped[list] = mapped_column(JSON, default=list, nullable=False)  # storage keys (S3/local)
    recognizer: Mapped[str] = mapped_column(String(40), default="stub", nullable=False)
    draft_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)        # raw LLM draft
    corrected_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)            # filled at confirm
    resulting_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("inventory_versions.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    resulting_version: Mapped["InventoryVersion | None"] = relationship(back_populates="capture")


# ----------------------------------------------------------------------------
# Increment 3: generated programs (spec S2/S3/S4)
# ----------------------------------------------------------------------------
class Program(Base):
    """A generated program. Tied to the inventory_version it was built from, so
    we can flag staleness when the user edits equipment (spec S5)."""

    __tablename__ = "programs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    inventory_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("inventory_versions.id", ondelete="SET NULL"), nullable=True
    )
    days_per_week: Mapped[int] = mapped_column(Integer, nullable=False)
    session_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    experience: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)  # active | superseded
    plan_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


# ----------------------------------------------------------------------------
# Increment 4: workout logging (spec S3 #4 readiness/RIR, #6 progression)
# ----------------------------------------------------------------------------
class WorkoutSession(Base):
    """One logged training session against a program day, with pre-session
    readiness (1-5) used by the progression engine's autoregulation."""

    __tablename__ = "workout_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    program_id: Mapped[str | None] = mapped_column(ForeignKey("programs.id", ondelete="SET NULL"), nullable=True)
    day_index: Mapped[int] = mapped_column(Integer, nullable=False)
    day_name: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    readiness: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1-5 self-report; feeds autoregulation
    status: Mapped[str] = mapped_column(String(16), default="in_progress", nullable=False)  # in_progress | completed
    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    sets: Mapped[list["SetLog"]] = relationship(back_populates="session", cascade="all, delete-orphan")


class SetLog(Base):
    """A single logged working set (weight × reps @ RIR) within a session."""

    __tablename__ = "set_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(ForeignKey("workout_sessions.id", ondelete="CASCADE"), index=True, nullable=False)
    exercise_name: Mapped[str] = mapped_column(String(80), nullable=False)
    reps_range: Mapped[str] = mapped_column(String(12), default="", nullable=False)  # prescribed range, for progression
    set_number: Mapped[int] = mapped_column(Integer, nullable=False)
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    reps: Mapped[int] = mapped_column(Integer, nullable=False)
    rir: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    logged_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    session: Mapped[WorkoutSession] = relationship(back_populates="sets")


# ----------------------------------------------------------------------------
# Increment 5: Neutron nutrition module (protein tracking for GLP-1 users)
# ----------------------------------------------------------------------------
class NutritionProfile(Base):
    """Per-user protein profile. Target defaults to protein_multiplier ×
    current bodyweight (1.52 g/kg ≈ 0.69 g/lb; auto mode recalculates whenever
    a new weight is logged); the user may pin a custom target instead. Diet pattern + restrictions gate every recipe the
    model is ever asked to produce — they are hard constraints, not hints."""

    __tablename__ = "nutrition_profiles"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    current_weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    goal_weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    protein_target_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_mode: Mapped[str] = mapped_column(String(10), default="auto", nullable=False)  # auto | custom
    # Auto-mode multiplier in g protein per kg bodyweight. Default 1.52 g/kg
    # ≈ 0.69 g/lb; 1.0 = the original spec minimum, 2.2 ≈ the classic 1 g/lb.
    protein_multiplier: Mapped[float] = mapped_column(Float, default=1.52, nullable=False)
    diet_pattern: Mapped[str] = mapped_column(String(20), default="omnivore", nullable=False)
    # e.g. ["no_garlic","no_onion","no_red_meat","no_dairy","keto","low_carb","custom:shellfish"]
    restrictions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    onboarded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )


class WeightLog(Base):
    """Bodyweight history (deferred analytics input, shipped with Neutron)."""

    __tablename__ = "weight_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    weight_kg: Mapped[float] = mapped_column(Float, nullable=False)
    logged_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class PantryItem(Base):
    """One food item in the user's single active pantry. Flat (not versioned
    like equipment) — the pantry churns daily and edits replace in place.
    Scan results are NOT persisted until the user confirms the list, which is
    also why scan photos are never stored (privacy: process-and-discard)."""

    __tablename__ = "pantry_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    quantity: Mapped[str] = mapped_column(String(60), default="", nullable=False)  # freeform: "2 cans", "500 g"
    category: Mapped[str] = mapped_column(String(16), default="pantry", nullable=False)  # pantry | fridge | freezer | other
    protein_per_100g: Mapped[float | None] = mapped_column(Float, nullable=True)
    protein_density: Mapped[str] = mapped_column(String(10), default="low", nullable=False)  # high | medium | low
    source: Mapped[str] = mapped_column(String(10), default="manual", nullable=False)  # scan | manual
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class SavedRecipe(Base):
    """A recipe the user chose to keep. `payload` holds the full generated
    recipe JSON (ingredients, steps, macros) so it renders offline forever."""

    __tablename__ = "saved_recipes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    protein_g: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    calories: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    source: Mapped[str] = mapped_column(String(16), default="builder", nullable=False)  # pantry_scan | builder | surprise
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class ProteinLog(Base):
    """One protein intake entry. The tracker, streaks, badges and level are all
    derived from these rows server-side — nothing gamified is stored twice."""

    __tablename__ = "protein_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    grams: Mapped[float] = mapped_column(Float, nullable=False)
    calories: Mapped[float | None] = mapped_column(Float, nullable=True)
    label: Mapped[str] = mapped_column(String(160), default="", nullable=False)  # meal name
    source: Mapped[str] = mapped_column(String(16), default="quick_add", nullable=False)  # recipe | quick_add | booster | voice
    logged_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class NutritionParseCache(Base):
    """AI-last cache for the voice-log fallback. Keyed by the NORMALIZED food
    phrase and shared across ALL users (a phrase like 'grilled chicken breast'
    is not personal data) — each distinct phrase hits Bedrock at most once, ever."""

    __tablename__ = "nutrition_parse_cache"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    phrase_norm: Mapped[str] = mapped_column(String(200), unique=True, index=True, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)  # ParsedFood dict
    model_id: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class NutritionBadge(Base):
    """Awarded badges are permanent even if the qualifying streak later breaks."""

    __tablename__ = "nutrition_badges"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    badge_key: Mapped[str] = mapped_column(String(40), nullable=False)
    awarded_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


# ----------------------------------------------------------------------------
# Gamification (workout XP / streaks / achievements — see app/gamification.py)
# ----------------------------------------------------------------------------
class WorkoutBadge(Base):
    """Awarded workout achievements — permanent even if the streak later breaks
    (mirror of NutritionBadge; XP itself is recomputed from history, not stored)."""

    __tablename__ = "workout_badges"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    badge_key: Mapped[str] = mapped_column(String(40), nullable=False)
    awarded_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

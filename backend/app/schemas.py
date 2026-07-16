"""Pydantic request/response schemas for every API endpoint.

Grouped by feature area (auth, onboarding, inventory, programs, workout
logging). These define the wire contract with the mobile app; validation
constraints (ranges, patterns) are enforced here so routers stay thin.
Nutrition (Neutron) schemas live inline in routers/nutrition.py.
"""
from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


# --- Auth ---
class RequestOtpIn(BaseModel):
    email: EmailStr
    phone: str | None = Field(default=None, max_length=32)  # optional, store-only (F6)


class VerifyOtpIn(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class RefreshIn(BaseModel):
    refresh_token: str


class LogoutIn(BaseModel):
    refresh_token: str | None = None
    everywhere: bool = False


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # access token lifetime, seconds


class MessageOut(BaseModel):
    message: str


# --- Onboarding / habits ---
class HabitsIn(BaseModel):
    days_per_week: int = Field(ge=3, le=5)
    session_minutes: int = Field(ge=20, le=120)
    experience: str = Field(pattern=r"^(conservative|intermediate|advanced)$")


class HabitsOut(BaseModel):
    days_per_week: int
    session_minutes: int
    experience: str
    onboarded: bool


class MeOut(BaseModel):
    id: str
    email: EmailStr
    email_verified: bool
    training_mode: str
    habits: HabitsOut | None = None


# --- Inventory (Increment 2) ---
class EquipmentItemIn(BaseModel):
    type: str
    quantity: int = Field(default=1, ge=1)
    load_min: float | None = None
    load_max: float | None = None
    load_increment: float | None = None
    attributes: dict = Field(default_factory=dict)


class EquipmentItemOut(EquipmentItemIn):
    id: str
    confidence: float | None = None
    confirmed: bool


class InventoryVersionOut(BaseModel):
    id: str
    version_no: int
    status: str
    source: str
    items: list[EquipmentItemOut]


class ConfirmInventoryIn(BaseModel):
    """User-corrected item list submitted from the confirmation screen (R3)."""
    items: list[EquipmentItemIn]


class EditInventoryIn(BaseModel):
    """Manual edit -> creates a new confirmed version (spec S5)."""
    items: list[EquipmentItemIn]


class CaptureMetaIn(BaseModel):
    consent_to_train: bool = False  # F8: only store images if the user opts in


# --- Programs (Increment 3) ---
class GenerateProgramIn(BaseModel):
    # If omitted, the user's onboarding days_per_week is used.
    days_per_week: int | None = Field(default=None, ge=3, le=5)


class ProgramExerciseOut(BaseModel):
    name: str
    pattern: str
    primary: list[str]
    sets: int
    reps: str
    rir: str
    compound: bool
    substituted_from: str | None = None
    description: str = ""
    video_url: str = ""


class ProgramDayOut(BaseModel):
    name: str
    exercises: list[ProgramExerciseOut]
    gaps: list[str]
    est_minutes: int


class ProgramOut(BaseModel):
    id: str
    days_per_week: int
    session_minutes: int
    experience: str
    inventory_version_id: str | None
    stale: bool  # true if a newer confirmed inventory exists than this was built from
    created_at: str
    days: list[ProgramDayOut]
    weekly_volume: dict[str, int]
    notes: list[str]
    gaps: list[str]


# --- Workout logging (Increment 4) ---
class StartWorkoutIn(BaseModel):
    program_id: str | None = None  # defaults to the active program
    day_index: int = Field(ge=0)
    readiness: int | None = Field(default=None, ge=1, le=5)


class LogSetIn(BaseModel):
    exercise_name: str
    set_number: int = Field(ge=1)
    reps: int = Field(ge=0)
    rir: int = Field(default=2, ge=0, le=10)
    weight: float | None = None
    reps_range: str = ""  # prescribed range, passed through for progression


class SetLogOut(BaseModel):
    id: str
    exercise_name: str
    set_number: int
    reps: int
    rir: int
    weight: float | None


class ProgressionSuggestionOut(BaseModel):
    exercise_name: str
    action: str
    message: str


class WorkoutSessionOut(BaseModel):
    id: str
    program_id: str | None
    day_index: int
    day_name: str
    readiness: int | None
    status: str
    started_at: str
    completed_at: str | None
    sets: list[SetLogOut]
    suggestions: list[ProgressionSuggestionOut] = []


class WorkoutHistoryItem(BaseModel):
    id: str
    day_name: str
    status: str
    started_at: str
    set_count: int


class LastSetOut(BaseModel):
    weight: float | None
    reps: int
    rir: int

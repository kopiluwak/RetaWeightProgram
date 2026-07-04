"""Canonical equipment taxonomy (spec R2).

This is the closed vocabulary the recognizer must emit and the inventory is
validated against. Keeping it canonical (not free-text) is what lets the
deterministic program engine in Increment 3 reason about available equipment.
"""
from __future__ import annotations

import enum


class EquipmentType(str, enum.Enum):
    BARBELL = "barbell"
    PLATES = "plates"                 # weight plates (denominations in attributes)
    FIXED_DUMBBELLS = "fixed_dumbbells"
    ADJUSTABLE_DUMBBELLS = "adjustable_dumbbells"
    KETTLEBELL = "kettlebell"
    BENCH_FLAT = "bench_flat"
    BENCH_ADJUSTABLE = "bench_adjustable"
    SQUAT_STAND = "squat_stand"
    POWER_RACK = "power_rack"
    PULL_UP_BAR = "pull_up_bar"
    CABLE_MACHINE = "cable_machine"
    SELECTORIZED_MACHINE = "selectorized_machine"   # generic pin-stack machine
    SMITH_MACHINE = "smith_machine"
    RESISTANCE_BANDS = "resistance_bands"
    BODYWEIGHT_ONLY = "bodyweight_only"
    # Cardio machines: stored so a future cardio module knows they exist, but
    # excluded from resistance programming (they map to no lifting patterns).
    TREADMILL = "treadmill"
    ROWING_MACHINE = "rowing_machine"
    STATIONARY_BIKE = "stationary_bike"
    ELLIPTICAL = "elliptical"
    CARDIO_OTHER = "cardio_other"
    OTHER = "other"


# Cardio equipment — known and stored, but not used by the strength engine.
CARDIO_TYPES: set[str] = {
    "treadmill", "rowing_machine", "stationary_bike", "elliptical", "cardio_other",
}


# Movement patterns each equipment type can support — used by the Increment-3
# engine to map a confirmed inventory to exercise selection. Defined here so the
# taxonomy and its training implications live in one place.
PATTERN_SUPPORT: dict[EquipmentType, set[str]] = {
    EquipmentType.BARBELL: {"squat", "hinge", "horizontal_press", "vertical_press", "horizontal_pull"},
    EquipmentType.PLATES: set(),  # modifier: enables loading for barbell/machines
    EquipmentType.FIXED_DUMBBELLS: {"squat", "hinge", "horizontal_press", "vertical_press", "horizontal_pull", "lunge"},
    EquipmentType.ADJUSTABLE_DUMBBELLS: {"squat", "hinge", "horizontal_press", "vertical_press", "horizontal_pull", "lunge"},
    EquipmentType.KETTLEBELL: {"hinge", "squat", "vertical_press", "carry", "lunge"},
    EquipmentType.BENCH_FLAT: {"horizontal_press"},
    EquipmentType.BENCH_ADJUSTABLE: {"horizontal_press", "incline_press"},
    EquipmentType.SQUAT_STAND: {"squat"},
    EquipmentType.POWER_RACK: {"squat", "vertical_pull"},
    EquipmentType.PULL_UP_BAR: {"vertical_pull"},
    EquipmentType.CABLE_MACHINE: {"horizontal_pull", "vertical_pull", "horizontal_press"},
    EquipmentType.SELECTORIZED_MACHINE: {"horizontal_press", "horizontal_pull", "squat", "hinge"},
    EquipmentType.SMITH_MACHINE: {"squat", "horizontal_press", "vertical_press"},
    EquipmentType.RESISTANCE_BANDS: {"horizontal_pull", "vertical_pull", "horizontal_press"},
    EquipmentType.BODYWEIGHT_ONLY: {"vertical_pull", "horizontal_press", "squat", "lunge"},
    EquipmentType.TREADMILL: set(),
    EquipmentType.ROWING_MACHINE: set(),
    EquipmentType.STATIONARY_BIKE: set(),
    EquipmentType.ELLIPTICAL: set(),
    EquipmentType.CARDIO_OTHER: set(),
    EquipmentType.OTHER: set(),
}


def is_valid_type(value: str) -> bool:
    return value in EquipmentType._value2member_map_

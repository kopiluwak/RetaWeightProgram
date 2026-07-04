"""Deterministic program generator (spec S2 rules-dominant, S3 constants, S4 splits).

Dependency-light on purpose (stdlib + exercises + equipment only) so it can be
unit-tested without FastAPI/DB. Given a confirmed inventory and the user's habits
it produces a reproducible 3/4/5-day program. No randomness: same inputs ->
same program, which is what makes it testable and medically defensible.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from urllib.parse import quote

from . import exercises as ex
from .exercises import Exercise
from .equipment import CARDIO_TYPES


def video_search_url(name: str) -> str:
    """A YouTube form-search link for the exercise. We use a search rather than a
    hardcoded video id so links never go dead; specific vetted videos can be
    curated later without changing the engine."""
    return "https://www.youtube.com/results?search_query=" + quote(f"how to {name} proper form")

# Per-set time cost (minutes), incl. rest. Compounds rest longer.
_COST_COMPOUND = 3.5
_COST_ACCESSORY = 2.5
_WARMUP_MIN = 8
_MIN_SETS = 2

# Volume scaling by experience (spec S3 #3: lower for beginners / deeper deficit).
_EXPERIENCE_FACTOR = {"conservative": 0.8, "intermediate": 1.0, "advanced": 1.15}

# Rep range + reps-in-reserve (spec S3 #1 intensity priority, #4 RIR autoregulation).
_COMPOUND_PRESCRIPTION = ("5-8", "2-3")
_ACCESSORY_PRESCRIPTION = ("8-12", "1-2")

# Suggested rest between sets (seconds): compounds need more recovery.
_COMPOUND_REST = 150
_ACCESSORY_REST = 75

# Slot = (pattern, base_sets_at_intermediate, is_compound)
_THREE_DAY = [
    ("Full Body A — Squat focus", [(ex.SQUAT, 3, True), (ex.H_PRESS, 3, True), (ex.H_PULL, 3, True), (ex.V_PRESS, 2, True), (ex.CORE_P, 2, False)]),
    ("Full Body B — Hinge focus", [(ex.HINGE, 3, True), (ex.V_PULL, 3, True), (ex.INCLINE_PRESS, 3, True), (ex.CURL, 2, False), (ex.TRI, 2, False)]),
    ("Full Body C — Mixed", [(ex.SQUAT, 2, True), (ex.LUNGE, 2, True), (ex.H_PULL, 3, True), (ex.V_PRESS, 2, True), (ex.CALF, 2, False)]),
]
_FOUR_DAY = [
    ("Upper A", [(ex.H_PRESS, 3, True), (ex.H_PULL, 3, True), (ex.V_PRESS, 3, True), (ex.V_PULL, 3, True), (ex.CURL, 2, False), (ex.TRI, 2, False)]),
    ("Lower A", [(ex.SQUAT, 4, True), (ex.HINGE, 3, True), (ex.LUNGE, 3, True), (ex.CALF, 3, False), (ex.CORE_P, 2, False)]),
    ("Upper B", [(ex.INCLINE_PRESS, 3, True), (ex.V_PULL, 3, True), (ex.H_PULL, 3, True), (ex.LATERAL, 3, False), (ex.TRI, 2, False), (ex.CURL, 2, False)]),
    ("Lower B", [(ex.HINGE, 4, True), (ex.SQUAT, 3, True), (ex.LUNGE, 3, True), (ex.CALF, 3, False), (ex.CORE_P, 2, False)]),
]
_FIVE_DAY = [
    ("Upper", [(ex.H_PRESS, 3, True), (ex.H_PULL, 3, True), (ex.V_PRESS, 3, True), (ex.V_PULL, 3, True), (ex.CURL, 2, False), (ex.TRI, 2, False)]),
    ("Lower", [(ex.SQUAT, 4, True), (ex.HINGE, 3, True), (ex.LUNGE, 3, True), (ex.CALF, 3, False), (ex.CORE_P, 2, False)]),
    ("Push", [(ex.INCLINE_PRESS, 4, True), (ex.V_PRESS, 3, True), (ex.LATERAL, 3, False), (ex.TRI, 3, False)]),
    ("Pull", [(ex.V_PULL, 4, True), (ex.H_PULL, 4, True), (ex.CURL, 3, False), (ex.CORE_P, 2, False)]),
    ("Legs", [(ex.HINGE, 4, True), (ex.SQUAT, 4, True), (ex.LUNGE, 3, True), (ex.CALF, 3, False)]),
]
_TEMPLATES = {3: _THREE_DAY, 4: _FOUR_DAY, 5: _FIVE_DAY}

_COACHING_NOTES = [
    "Train each working set 1-3 reps shy of failure (RIR). On low-energy days—common on a GLP-1—stop a rep earlier rather than skipping the session.",
    "Add reps within the range first; once you hit the top, add load (double progression). Maintaining strength in a deficit is success, not failure.",
    "Take a lighter deload week every 4-6 weeks, or sooner if joints/fatigue demand it—recovery is reduced when underfed.",
    "This only works if protein and sleep are adequate. (Specific targets come with the nutrition module.)",
]


@dataclass
class ProgramExercise:
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
    rest_seconds: int = 90


@dataclass
class ProgramDay:
    name: str
    exercises: list[ProgramExercise] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    est_minutes: int = 0


@dataclass
class Program:
    days_per_week: int
    session_minutes: int
    experience: str
    days: list[ProgramDay] = field(default_factory=list)
    weekly_volume: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def owned_types(inventory_items: list[dict]) -> set[str]:
    return {it["type"] for it in inventory_items}


def session_set_capacity_minutes(session_minutes: int) -> int:
    return max(0, session_minutes - _WARMUP_MIN)


def _cost(compound: bool) -> float:
    return _COST_COMPOUND if compound else _COST_ACCESSORY


def _pick(pattern: str, owned: set[str], usage: dict[str, int]) -> tuple[Exercise | None, str | None]:
    """Best available exercise for a pattern; fall back to a muscle-equivalent
    pattern if the requested one can't be equipped. Returns (exercise, substituted_from)."""
    def best(pat: str) -> Exercise | None:
        cands = [e for e in ex.LIBRARY if e.pattern == pat and e.available(owned)]
        if not cands:
            return None
        # Prefer least-used (variety across the week), then highest priority, then id.
        cands.sort(key=lambda e: (usage[e.id], -e.priority, e.id))
        return cands[0]

    chosen = best(pattern)
    if chosen:
        return chosen, None
    for fb in ex.SUBSTITUTION_FALLBACKS.get(pattern, []):
        alt = best(fb)
        if alt:
            return alt, pattern
    return None, None


def _scale_sets(base: int, factor: float) -> int:
    return max(_MIN_SETS, round(base * factor))


def _trim_to_budget(entries: list[ProgramExercise], usable_minutes: int) -> None:
    """Reduce sets until the day fits the time budget (spec S3 #9: fit-and-warn).
    Trim accessories first, then compounds, never below _MIN_SETS."""
    def total() -> float:
        return sum(_cost(e.compound) * e.sets for e in entries)

    while total() > usable_minutes:
        # candidate to trim: accessory with most sets first, else compound
        trimmable = [e for e in entries if not e.compound and e.sets > _MIN_SETS]
        if not trimmable:
            trimmable = [e for e in entries if e.compound and e.sets > _MIN_SETS]
        if not trimmable:
            break  # everything at the floor; day is as short as it goes
        trimmable.sort(key=lambda e: (-e.sets, e.name))
        trimmable[0].sets -= 1


def generate_program(
    inventory_items: list[dict],
    days_per_week: int,
    session_minutes: int,
    experience: str,
) -> Program:
    if days_per_week not in _TEMPLATES:
        raise ValueError("days_per_week must be 3, 4, or 5")

    owned = owned_types(inventory_items)
    factor = _EXPERIENCE_FACTOR.get(experience, 1.0)
    usable = session_set_capacity_minutes(session_minutes)
    usage: dict[str, int] = defaultdict(int)

    program = Program(days_per_week=days_per_week, session_minutes=session_minutes, experience=experience)
    weekly_volume: dict[str, int] = defaultdict(int)

    for day_name, slots in _TEMPLATES[days_per_week]:
        day = ProgramDay(name=day_name)
        for pattern, base, compound in slots:
            exercise, sub_from = _pick(pattern, owned, usage)
            if exercise is None:
                day.gaps.append(f"No equipment for {pattern.replace('_', ' ')} — slot skipped")
                continue
            usage[exercise.id] += 1
            sets = _scale_sets(base, factor)
            # Consolidation: if a substitution lands on an exercise already in this
            # day, merge the sets instead of listing the same lift twice.
            existing = next((e for e in day.exercises if e.name == exercise.name), None)
            if existing is not None:
                existing.sets += sets
                continue
            reps, rir = _COMPOUND_PRESCRIPTION if compound else _ACCESSORY_PRESCRIPTION
            rest = _COMPOUND_REST if exercise.compound else _ACCESSORY_REST
            day.exercises.append(ProgramExercise(
                name=exercise.name, pattern=exercise.pattern, primary=list(exercise.primary),
                sets=sets, reps=reps, rir=rir, compound=exercise.compound,
                substituted_from=sub_from, description=exercise.description,
                video_url=video_search_url(exercise.name), rest_seconds=rest,
            ))
        _trim_to_budget(day.exercises, usable)
        day.est_minutes = int(_WARMUP_MIN + sum(_cost(e.compound) * e.sets for e in day.exercises))
        for e in day.exercises:
            for m in e.primary:
                weekly_volume[m] += e.sets
        program.days.append(day)
        program.gaps.extend(day.gaps)

    program.weekly_volume = dict(sorted(weekly_volume.items(), key=lambda kv: kv[0]))
    program.notes = list(_COACHING_NOTES)
    cardio_present = sorted(owned & CARDIO_TYPES)
    if cardio_present:
        pretty = ", ".join(c.replace("_", " ") for c in cardio_present)
        program.notes.append(
            f"Cardio equipment noted ({pretty}). It's saved to your inventory but not "
            f"part of this resistance plan — a cardio module is planned."
        )
    if program.gaps:
        program.notes.append(
            "Some movement patterns couldn't be equipped from your current inventory "
            "(see gaps). Add equipment and regenerate to fill them."
        )
    return program

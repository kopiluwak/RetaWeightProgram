"""Add-your-own-exercise support (user-suggested & library picks).

Two entry points, both landing an exercise on the correct muscle-group day of a
generated program:

  1. "Choose a specific exercise" — pick a known movement from the exercise
     library (pull-up, push-up, isolation curl, …). No model call.
  2. "I saw it on social media" — free text the user describes; we first try a
     fuzzy match against the library, and only if that misses do we ask Bedrock
     to classify it (muscle group + compound + a short form cue). AI-last.

Everything here is pure/stdlib except the lazily-imported Bedrock client, so the
day-matching and stub classifier are unit-testable without FastAPI/DB/AWS. The
classifier mirrors neutron_parse.py exactly (forced tool call, temperature 0,
maxTokens floor 4096, stub engine selected by settings.vision_provider).
"""
from __future__ import annotations

import asyncio
import logging
import re
import unicodedata

from pydantic import BaseModel, Field

from . import exercises as ex
from .engine import (
    ProgramExercise,
    _ACCESSORY_PRESCRIPTION,
    _ACCESSORY_REST,
    _COMPOUND_PRESCRIPTION,
    _COMPOUND_REST,
    video_search_url,
)

_log = logging.getLogger(__name__)

# The muscle vocabulary the classifier is allowed to return (matches exercises.py).
MUSCLES = (
    ex.CHEST, ex.BACK, ex.QUADS, ex.HAMSTRINGS, ex.GLUTES, ex.SHOULDERS,
    ex.BICEPS, ex.TRICEPS, ex.CALVES, ex.CORE,
)

# Keyword hints tying a muscle to the DAY NAMES the engine authors. Used as a
# fallback signal when a day has no existing exercise sharing the muscle (e.g. a
# brand-new/empty beginner day). Lower-cased substring match against day.name.
_MUSCLE_DAY_KEYWORDS: dict[str, tuple[str, ...]] = {
    ex.CHEST: ("push", "chest"),
    ex.TRICEPS: ("push", "arms", "triceps"),
    ex.SHOULDERS: ("shoulder", "push"),
    ex.BACK: ("pull", "back"),
    ex.BICEPS: ("pull", "arms", "biceps"),
    ex.QUADS: ("legs", "quad"),
    ex.HAMSTRINGS: ("legs", "hamstring"),
    ex.GLUTES: ("legs", "glute"),
    ex.CALVES: ("legs", "calf", "calv"),
    ex.CORE: ("pull", "legs", "core", "abs"),
}


def normalize(raw: str) -> str:
    """Lowercase, ascii-fold, strip punctuation, collapse whitespace."""
    s = unicodedata.normalize("NFKD", raw or "").encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9 ]+", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


# ---------------------------------------------------------------------------
# 1. Library search (known exercises)
# ---------------------------------------------------------------------------
def library_choices() -> list[dict]:
    """Every pickable library movement, de-duplicated by name, for the
    'choose a specific exercise' list. Sorted by primary muscle then name."""
    seen: set[str] = set()
    out: list[dict] = []
    for e in ex.LIBRARY:
        if e.name in seen:
            continue
        seen.add(e.name)
        out.append({
            "id": e.id, "name": e.name, "pattern": e.pattern,
            "primary": list(e.primary), "compound": e.compound,
        })
    out.sort(key=lambda d: (d["primary"][0] if d["primary"] else "", d["name"]))
    return out


def find_library_exercise(text: str) -> ex.Exercise | None:
    """Best-effort match of free text to a known library exercise.

    Exact normalized name, then substring either direction, then token overlap.
    Returns None when nothing is confidently close (caller falls back to AI).
    """
    q = normalize(text)
    if not q:
        return None
    by_name = {normalize(e.name): e for e in ex.LIBRARY}
    if q in by_name:
        return by_name[q]
    # Substring both directions (e.g. "pullups" vs "pull up").
    q_nospace = q.replace(" ", "")
    for norm, e in by_name.items():
        n_nospace = norm.replace(" ", "")
        if q_nospace and (q_nospace in n_nospace or n_nospace in q_nospace):
            return e
    # Token overlap: require at least 2 shared meaningful tokens, or 1 if the
    # query is a single distinctive word.
    q_tokens = {t for t in q.split() if len(t) > 2}
    best, best_score = None, 0
    for norm, e in by_name.items():
        n_tokens = {t for t in norm.split() if len(t) > 2}
        score = len(q_tokens & n_tokens)
        if score > best_score:
            best, best_score = e, score
    if best is not None and best_score >= 2:
        return best
    return None


def exercise_to_classified(e: ex.Exercise) -> "ClassifiedExercise":
    """Adapt a library Exercise into the classifier's output shape."""
    return ClassifiedExercise(
        name=e.name, primary=list(e.primary), compound=e.compound,
        description=e.description, confidence=1.0, source="library",
    )


# ---------------------------------------------------------------------------
# 2. Day matching — place an exercise on the right muscle-group day
# ---------------------------------------------------------------------------
def best_day_index(days: list[dict], primary: list[str]) -> int:
    """Index of the training day this exercise best belongs to.

    Scores each day by (a) how many of its existing exercises already train one
    of `primary` (strong signal — the day's real content) and (b) whether the
    day NAME keywords match the muscle (fallback for empty/near-empty days).
    Ties go to the earliest day. Always returns a valid index (0 if no signal).
    """
    if not days:
        return 0
    prim = set(primary)
    best_i, best_score = 0, -1
    for i, day in enumerate(days):
        content = 0
        for entry in day.get("exercises", []):
            if prim & set(entry.get("primary", [])):
                content += 1
        name = (day.get("name") or "").lower()
        name_hit = 0
        for m in prim:
            if any(kw in name for kw in _MUSCLE_DAY_KEYWORDS.get(m, ())):
                name_hit = 1
                break
        score = content * 3 + name_hit
        if score > best_score:
            best_i, best_score = i, score
    return best_i


def make_program_exercise(
    name: str, primary: list[str], compound: bool, description: str,
    sets: int | None = None,
) -> ProgramExercise:
    """Build a ProgramExercise (prescription defaults mirror the engine's)."""
    reps, rir = _COMPOUND_PRESCRIPTION if compound else _ACCESSORY_PRESCRIPTION
    rest = _COMPOUND_REST if compound else _ACCESSORY_REST
    default_sets = 3 if compound else 2
    return ProgramExercise(
        name=name.strip()[:80] or "Custom exercise",
        pattern="custom",
        primary=[m for m in primary if m in MUSCLES] or [ex.CHEST],
        sets=max(1, min(6, sets if sets is not None else default_sets)),
        reps=reps, rir=rir, compound=compound,
        substituted_from=None, description=description.strip(),
        video_url=video_search_url(name), rest_seconds=rest,
        added_by_user=True,
    )


def add_exercise_to_plan(
    plan: dict, exercise: ProgramExercise, day_index: int | None = None,
) -> tuple[int, str]:
    """Insert `exercise` into the plan's day (auto-matched unless day_index given),
    mutating plan in place (days/weekly_volume). Returns (day_index, day_name)."""
    from dataclasses import asdict

    days = plan.get("days", [])
    if not days:
        raise ValueError("program has no days")
    idx = day_index if day_index is not None else best_day_index(days, exercise.primary)
    idx = max(0, min(idx, len(days) - 1))
    day = days[idx]
    day.setdefault("exercises", []).append(asdict(exercise))
    # Keep the day time estimate and weekly volume roughly consistent.
    day["est_minutes"] = int(day.get("est_minutes", 0) + (3.5 if exercise.compound else 2.5) * exercise.sets)
    vol = plan.setdefault("weekly_volume", {})
    for m in exercise.primary:
        vol[m] = vol.get(m, 0) + exercise.sets
    plan["weekly_volume"] = dict(sorted(vol.items()))
    return idx, day.get("name", f"Day {idx + 1}")


def remove_exercise_from_plan(plan: dict, day_index: int, name: str) -> bool:
    """Remove the first user-added exercise named `name` from the given day.
    Only user-added exercises can be removed. Returns True if one was removed."""
    days = plan.get("days", [])
    if day_index < 0 or day_index >= len(days):
        return False
    day = days[day_index]
    entries = day.get("exercises", [])
    for i, entry in enumerate(entries):
        if entry.get("added_by_user") and entry.get("name") == name:
            removed = entries.pop(i)
            sets = int(removed.get("sets", 0))
            day["est_minutes"] = max(
                0, int(day.get("est_minutes", 0) - (3.5 if removed.get("compound") else 2.5) * sets)
            )
            vol = plan.get("weekly_volume", {})
            for m in removed.get("primary", []):
                if m in vol:
                    vol[m] = max(0, vol[m] - sets)
            return True
    return False


# ---------------------------------------------------------------------------
# 3. AI classifier (free-text -> muscle group + compound + form cue), AI-last
# ---------------------------------------------------------------------------
class ClassifiedExercise(BaseModel):
    """A classified exercise ready to be added to a program day."""

    name: str = Field(min_length=1, max_length=80)
    primary: list[str] = Field(min_length=1)
    compound: bool = False
    description: str = Field(default="", max_length=400)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    source: str = "ai"  # library | ai | stub


SUBMIT_EXERCISE_TOOL = {
    "toolSpec": {
        "name": "submit_exercise",
        "description": "Classify one resistance-training exercise for a workout program.",
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Short canonical exercise name, title case."},
                    "primary": {
                        "type": "array",
                        "items": {"type": "string", "enum": list(MUSCLES)},
                        "description": "1-2 primary muscles worked, most important first.",
                    },
                    "compound": {"type": "boolean", "description": "True if it trains multiple joints/major muscles."},
                    "description": {"type": "string", "description": "One or two sentences of concise form cues."},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["name", "primary", "compound", "description"],
            }
        },
    }
}


def build_classify_prompt(text: str) -> str:
    return (
        "You classify a single resistance-training exercise for a weight-lifting "
        "app. The user describes a movement they saw (possibly informally or "
        "with slang). Identify a short canonical name, the 1-2 PRIMARY muscles "
        f"it trains (choose only from: {', '.join(MUSCLES)}), whether it is a "
        "compound (multi-joint) movement, and one or two sentences of concise, "
        "safe form cues. If the description is not a real exercise, still return "
        "your best guess with low confidence. Call submit_exercise once.\n\n"
        f"Exercise the user described: {text.strip()}"
    )


def parse_classify_output(response: dict, source: str) -> ClassifiedExercise | None:
    """Pure parser for the forced tool-use response (unit-testable)."""
    content = response.get("output", {}).get("message", {}).get("content", [])
    tool_input = None
    for block in content:
        if "toolUse" in block and block["toolUse"].get("name") == "submit_exercise":
            tool_input = block["toolUse"].get("input", {})
            break
    if not tool_input:
        return None
    name = str(tool_input.get("name", "")).strip()
    if not name:
        return None
    primary = [m for m in tool_input.get("primary", []) if m in MUSCLES][:2]
    if not primary:
        primary = [ex.CHEST]
    try:
        conf = min(1.0, max(0.0, float(tool_input.get("confidence", 0.5))))
    except (TypeError, ValueError):
        conf = 0.5
    return ClassifiedExercise(
        name=name[:80], primary=primary, compound=bool(tool_input.get("compound", False)),
        description=str(tool_input.get("description", "")).strip()[:400],
        confidence=conf, source=source,
    )


class DevStubClassifier:
    """Deterministic keyword heuristic so the add-exercise flow is fully testable
    without AWS. Mirrors neutron_parse's DevStubFoodParser style."""

    name = "stub"

    # (keyword, primary muscles, compound)
    _RULES: tuple[tuple[str, tuple[str, ...], bool], ...] = (
        ("curl", (ex.BICEPS,), False),
        ("row", (ex.BACK, ex.BICEPS), True),
        ("pull up", (ex.BACK, ex.BICEPS), True),
        ("pullup", (ex.BACK, ex.BICEPS), True),
        ("pulldown", (ex.BACK, ex.BICEPS), True),
        ("chin", (ex.BACK, ex.BICEPS), True),
        ("lat", (ex.BACK,), False),
        ("push up", (ex.CHEST, ex.TRICEPS), True),
        ("pushup", (ex.CHEST, ex.TRICEPS), True),
        ("bench", (ex.CHEST, ex.TRICEPS), True),
        ("chest", (ex.CHEST,), False),
        ("fly", (ex.CHEST,), False),
        ("pushdown", (ex.TRICEPS,), False),
        ("tricep", (ex.TRICEPS,), False),
        ("dip", (ex.TRICEPS,), False),
        ("overhead press", (ex.SHOULDERS, ex.TRICEPS), True),
        ("shoulder press", (ex.SHOULDERS, ex.TRICEPS), True),
        ("lateral", (ex.SHOULDERS,), False),
        ("delt", (ex.SHOULDERS,), False),
        ("shrug", (ex.SHOULDERS,), False),
        ("squat", (ex.QUADS, ex.GLUTES), True),
        ("lunge", (ex.QUADS, ex.GLUTES), True),
        ("leg press", (ex.QUADS, ex.GLUTES), True),
        ("leg extension", (ex.QUADS,), False),
        ("deadlift", (ex.HAMSTRINGS, ex.GLUTES), True),
        ("rdl", (ex.HAMSTRINGS, ex.GLUTES), True),
        ("hinge", (ex.HAMSTRINGS, ex.GLUTES), True),
        ("hamstring", (ex.HAMSTRINGS,), False),
        ("glute", (ex.GLUTES,), False),
        ("hip thrust", (ex.GLUTES, ex.HAMSTRINGS), True),
        ("calf", (ex.CALVES,), False),
        ("plank", (ex.CORE,), False),
        ("crunch", (ex.CORE,), False),
        ("sit up", (ex.CORE,), False),
        ("leg raise", (ex.CORE,), False),
        ("ab", (ex.CORE,), False),
        ("press", (ex.CHEST, ex.TRICEPS), True),
        ("raise", (ex.SHOULDERS,), False),
    )

    async def classify(self, text: str) -> ClassifiedExercise:
        low = normalize(text)
        primary: tuple[str, ...] = (ex.CHEST,)
        compound = False
        for kw, muscles, comp in self._RULES:
            if kw in low:
                primary, compound = muscles, comp
                break
        name = " ".join(w.capitalize() for w in low.split()[:5]) or "Custom Exercise"
        return ClassifiedExercise(
            name=name[:80], primary=list(primary), compound=compound,
            description="", confidence=0.4, source=self.name,
        )


class BedrockClassifier:
    """Production classifier: text-only Bedrock Converse with a forced tool call."""

    def __init__(self, settings):
        import boto3  # lazy: stub path needs no AWS deps
        self._model_id = settings.bedrock_model_id
        self._max_tokens = max(settings.bedrock_max_tokens, 4096)
        self.name = f"bedrock:{settings.bedrock_model_id}"
        self._client = boto3.client("bedrock-runtime", region_name=settings.aws_region)

    def _invoke(self, prompt: str) -> dict:
        return self._client.converse(
            modelId=self._model_id,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": self._max_tokens, "temperature": 0.0},
            toolConfig={
                "tools": [SUBMIT_EXERCISE_TOOL],
                "toolChoice": {"tool": {"name": "submit_exercise"}},
            },
        )

    async def classify(self, text: str) -> ClassifiedExercise:
        response = await asyncio.to_thread(self._invoke, build_classify_prompt(text))
        result = parse_classify_output(response, self.name)
        if result is None:
            _log.warning("exercise classify returned nothing: stopReason=%s",
                         response.get("stopReason"))
            # Never hard-fail the user's add; degrade to a stub guess.
            return await DevStubClassifier().classify(text)
        return result


def build_classifier(settings):
    """Factory: Bedrock classifier or dev stub, per settings.vision_provider."""
    if settings.vision_provider == "bedrock":
        return BedrockClassifier(settings)
    return DevStubClassifier()


async def classify_exercise(text: str, settings) -> ClassifiedExercise:
    """AI-last resolution: library match first, else classifier (Bedrock/stub)."""
    lib = find_library_exercise(text)
    if lib is not None:
        return exercise_to_classified(lib)
    return await build_classifier(settings).classify(text)

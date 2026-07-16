"""Double-progression suggestion engine (spec S3 #6).

Deterministic and framework-free so it's unit-testable. Given an exercise's
prescribed rep range and the sets actually logged for it in a session, it
recommends what to do next time:

  - increase_load : every working set hit the TOP of the range with effort to
    spare (RIR not at/below the hard floor) -> add load next time.
  - hold          : reps landed inside the range, or top reached but the last
    set was a grind (RIR 0) -> keep load, accumulate reps/quality.
  - reduce_load   : sets fell BELOW the bottom of the range -> load is too heavy
    for the prescribed reps; back off.

Rationale (deficit context, S3): we only push load when the lifter clearly
earned it, because recovery is compromised when underfed; grinding sets (RIR 0)
never trigger a load bump.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class LoggedSet:
    reps: int
    rir: int  # reps in reserve the lifter reported (0 = to failure)


@dataclass
class ProgressionSuggestion:
    exercise_name: str
    action: str        # increase_load | hold | reduce_load
    message: str


def _range_bounds(reps_range: str) -> tuple[int, int]:
    """Parse a "lo-hi" rep range string into (lo, hi) ints."""
    lo, _, hi = reps_range.partition("-")
    return int(lo), int(hi)


def suggest_for_exercise(exercise_name: str, reps_range: str, sets: list[LoggedSet]) -> ProgressionSuggestion:
    """Apply the double-progression rules (see module docstring) to one exercise."""
    if not sets:
        return ProgressionSuggestion(exercise_name, "hold", "No sets logged — keep the same load and log next time.")

    low, high = _range_bounds(reps_range)
    min_reps = min(s.reps for s in sets)
    all_at_top = all(s.reps >= high for s in sets)
    any_grind = any(s.rir <= 0 for s in sets)

    if min_reps < low:
        return ProgressionSuggestion(
            exercise_name, "reduce_load",
            f"Reps dropped below {low}. Reduce the load ~5-10% so you can stay in the {reps_range} range.",
        )
    if all_at_top and not any_grind:
        return ProgressionSuggestion(
            exercise_name, "increase_load",
            f"All sets hit {high}+ reps with reps in reserve. Add load next session (small jump) and rebuild reps.",
        )
    return ProgressionSuggestion(
        exercise_name, "hold",
        f"Stay at this load and add reps toward {high} across all sets before increasing.",
    )


def suggest_for_session(logged: dict[str, tuple[str, list[LoggedSet]]]) -> list[ProgressionSuggestion]:
    """logged: {exercise_name: (reps_range, [LoggedSet, ...])}. Deterministic order."""
    return [
        suggest_for_exercise(name, reps_range, sets)
        for name, (reps_range, sets) in sorted(logged.items())
    ]

"""Unit tests for the add-your-own-exercise logic (pure, no FastAPI/DB/AWS).

Run: python3 -m tests.test_custom_exercise
Covers: day-matching, library search, stub classifier, plan add/remove, and
the forced-tool response parser.
"""
from __future__ import annotations

import asyncio
from dataclasses import asdict

from app import custom_exercise as cx
from app import exercises as ex
from app.engine import generate_program


def _sample_program(days_per_week: int = 3) -> dict:
    """A real generated plan to match exercises against (full gym inventory)."""
    inv = [{"type": t} for t in (
        "barbell", "plates", "power_rack", "bench_adjustable",
        "adjustable_dumbbells", "cable_machine", "pull_up_bar",
    )]
    return generate_program(inv, days_per_week, 60, "intermediate").to_dict()


def test_find_library_exercise_variants():
    assert cx.find_library_exercise("pull ups").id == "pullup"
    assert cx.find_library_exercise("pullups").id == "pullup"
    assert cx.find_library_exercise("Push-up").id == "pushup"
    assert cx.find_library_exercise("dumbbell curl").id == "db_curl"
    # Nonsense returns None so the caller falls back to AI.
    assert cx.find_library_exercise("zxqw flarp") is None


def test_best_day_index_matches_muscle_day():
    plan = _sample_program(3)
    days = plan["days"]
    names = [d["name"].lower() for d in days]
    push_i = next(i for i, n in enumerate(names) if "push" in n)
    pull_i = next(i for i, n in enumerate(names) if "pull" in n)
    legs_i = next(i for i, n in enumerate(names) if "legs" in n)
    # Biceps -> Pull, chest -> Push, quads -> Legs.
    assert cx.best_day_index(days, [ex.BICEPS]) == pull_i
    assert cx.best_day_index(days, [ex.CHEST]) == push_i
    assert cx.best_day_index(days, [ex.QUADS]) == legs_i
    assert cx.best_day_index(days, [ex.HAMSTRINGS]) == legs_i


def test_best_day_index_empty_days_by_name():
    # No exercises present -> falls back to day-name keyword match.
    days = [
        {"name": "Push — Chest, Shoulders & Triceps", "exercises": []},
        {"name": "Pull — Back & Biceps", "exercises": []},
        {"name": "Legs — Quads, Hamstrings & Calves", "exercises": []},
    ]
    assert cx.best_day_index(days, [ex.TRICEPS]) == 0
    assert cx.best_day_index(days, [ex.BACK]) == 1
    assert cx.best_day_index(days, [ex.CALVES]) == 2
    # Never raises / always valid index even with unknown muscle.
    assert cx.best_day_index([], [ex.CHEST]) == 0


def test_add_exercise_lands_on_right_day_and_persists_flag():
    plan = _sample_program(3)
    pull_i = next(i for i, d in enumerate(plan["days"]) if "pull" in d["name"].lower())
    before = len(plan["days"][pull_i]["exercises"])
    vol_before = plan["weekly_volume"].get(ex.BICEPS, 0)

    pe = cx.make_program_exercise("Preacher Curl", [ex.BICEPS], False, "cue", sets=3)
    idx, name = cx.add_exercise_to_plan(plan, pe)

    assert idx == pull_i
    added = plan["days"][pull_i]["exercises"]
    assert len(added) == before + 1
    assert added[-1]["name"] == "Preacher Curl"
    assert added[-1]["added_by_user"] is True
    assert plan["weekly_volume"][ex.BICEPS] == vol_before + 3


def test_add_exercise_day_override():
    plan = _sample_program(3)
    pe = cx.make_program_exercise("Face Pull", [ex.SHOULDERS], False, "", sets=2)
    idx, _ = cx.add_exercise_to_plan(plan, pe, day_index=0)
    assert idx == 0
    assert plan["days"][0]["exercises"][-1]["name"] == "Face Pull"


def test_remove_only_user_added():
    plan = _sample_program(3)
    # Cannot remove a generated exercise.
    day0 = plan["days"][0]
    generated_name = day0["exercises"][0]["name"]
    assert cx.remove_exercise_from_plan(plan, 0, generated_name) is False

    pe = cx.make_program_exercise("Cable Crossover", [ex.CHEST], False, "", sets=2)
    idx, _ = cx.add_exercise_to_plan(plan, pe, day_index=0)
    assert cx.remove_exercise_from_plan(plan, idx, "Cable Crossover") is True
    # Gone now.
    assert cx.remove_exercise_from_plan(plan, idx, "Cable Crossover") is False


def test_stub_classifier_keywords():
    stub = cx.DevStubClassifier()
    r = asyncio.run(stub.classify("some crazy tiktok bicep curl thing"))
    assert ex.BICEPS in r.primary and r.compound is False
    r2 = asyncio.run(stub.classify("bulgarian split squat"))
    assert ex.QUADS in r2.primary and r2.compound is True
    r3 = asyncio.run(stub.classify("weird cable tricep pushdown"))
    assert ex.TRICEPS in r3.primary


def test_classify_exercise_library_first():
    class _S:  # settings stub; library hit must not touch the model
        vision_provider = "stub"
    r = asyncio.run(cx.classify_exercise("pull up", _S()))
    assert r.source == "library" and ex.BACK in r.primary


def test_parse_classify_output():
    response = {"output": {"message": {"content": [
        {"toolUse": {"name": "submit_exercise", "input": {
            "name": "Nordic Curl", "primary": ["hamstrings", "bogus"],
            "compound": True, "description": "Lower slowly.", "confidence": 0.9,
        }}}
    ]}}}
    r = cx.parse_classify_output(response, "bedrock:test")
    assert r is not None
    assert r.name == "Nordic Curl"
    assert r.primary == [ex.HAMSTRINGS]  # bogus muscle filtered out
    assert r.compound is True
    # No tool block -> None.
    assert cx.parse_classify_output({"output": {"message": {"content": []}}}, "x") is None


def test_classified_payload_round_trips_for_cache():
    # The classify cache stores model_dump() and rebuilds with ClassifiedExercise(
    # **payload) — this must survive the trip so cache reads work.
    orig = cx.ClassifiedExercise(
        name="Cable Pushdown", primary=[ex.TRICEPS], compound=False,
        description="Elbows pinned.", confidence=0.8, source="bedrock:test",
    )
    payload = orig.model_dump()
    rebuilt = cx.ClassifiedExercise(**{**payload, "source": "cache"})
    assert rebuilt.name == orig.name
    assert rebuilt.primary == orig.primary
    assert rebuilt.source == "cache"


def _run() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed")


if __name__ == "__main__":
    _run()

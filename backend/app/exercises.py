"""Exercise library (Increment 3).

Pure data + helpers, stdlib only, so the engine that consumes it stays testable
without any framework. Each exercise declares the equipment it needs as an
AND-of-ORs requirement over EquipmentType values: every group must be satisfied
by at least one owned type. An empty requirement = bodyweight, always available.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# --- Muscle vocabulary ---
CHEST = "chest"
BACK = "back"
QUADS = "quads"
HAMSTRINGS = "hamstrings"
GLUTES = "glutes"
SHOULDERS = "shoulders"
BICEPS = "biceps"
TRICEPS = "triceps"
CALVES = "calves"
CORE = "core"

# Priority tier for volume allocation (spec S3 #2): large movers earn 2x
# frequency when the time budget allows; the rest default to 1x.
PRIORITY_MUSCLES = {BACK, QUADS, CHEST, HAMSTRINGS, GLUTES}

# Movement patterns (engine slots reference these).
SQUAT = "squat"
HINGE = "hinge"
LUNGE = "lunge"
H_PRESS = "horizontal_press"
INCLINE_PRESS = "incline_press"
V_PRESS = "vertical_press"
H_PULL = "horizontal_pull"
V_PULL = "vertical_pull"
LATERAL = "lateral_raise"
CURL = "biceps_curl"
TRI = "triceps_ext"
CALF = "calf"
CORE_P = "core"

# Equipment shorthands (EquipmentType .value strings).
_DB = {"fixed_dumbbells", "adjustable_dumbbells"}
_BENCH = {"bench_flat", "bench_adjustable"}
_RACK = {"power_rack", "squat_stand", "smith_machine"}
_BAR_LOAD = [{"barbell"}, {"plates"}]
_PULLUP = {"pull_up_bar", "power_rack"}
_CABLE = {"cable_machine", "selectorized_machine"}


@dataclass(frozen=True)
class Exercise:
    id: str
    name: str
    pattern: str
    primary: tuple[str, ...]
    compound: bool
    requirements: tuple[frozenset[str], ...] = ()  # AND of ORs; empty = bodyweight
    priority: int = 1  # higher wins when several exercises fit one slot
    description: str = ""  # short form cue shown in the program

    def available(self, owned: set[str]) -> bool:
        """True if every requirement group is satisfied by some owned type."""
        return all(bool(group & owned) for group in self.requirements)


def _req(*groups: set[str]) -> tuple[frozenset[str], ...]:
    """Build an AND-of-ORs requirement tuple from equipment-type groups."""
    return tuple(frozenset(g) for g in groups)


# id, name, pattern, primary muscles, compound, requirements, priority, description
LIBRARY: list[Exercise] = [
    # --- Squat ---
    Exercise("bb_back_squat", "Barbell Back Squat", SQUAT, (QUADS, GLUTES), True, _req(*_BAR_LOAD, _RACK), 10,
             "Bar on upper back, brace, sit down between hips to at least parallel, drive up through mid-foot."),
    Exercise("smith_squat", "Smith Machine Squat", SQUAT, (QUADS, GLUTES), True, _req({"smith_machine"}), 7,
             "Feet slightly forward of the bar, descend to parallel, push through heels. The fixed path eases balance."),
    Exercise("goblet_squat", "Goblet Squat", SQUAT, (QUADS, GLUTES), True, _req(_DB | {"kettlebell"}), 6,
             "Hold one dumbbell/kettlebell at your chest, squat down keeping torso tall and elbows inside knees."),
    Exercise("bw_squat", "Bodyweight Squat", SQUAT, (QUADS, GLUTES), True, _req(), 2,
             "Feet shoulder-width, sit back and down to parallel, knees tracking over toes, stand tall."),
    # --- Hinge ---
    Exercise("bb_rdl", "Barbell Romanian Deadlift", HINGE, (HAMSTRINGS, GLUTES), True, _req(*_BAR_LOAD), 10,
             "Soft knees, push hips back, lower the bar along your legs until you feel a hamstring stretch, drive hips forward."),
    Exercise("db_rdl", "Dumbbell Romanian Deadlift", HINGE, (HAMSTRINGS, GLUTES), True, _req(_DB), 7,
             "Dumbbells in front of thighs, hinge at the hips with a flat back, feel the hamstrings, then stand tall."),
    Exercise("kb_swing", "Kettlebell Swing", HINGE, (HAMSTRINGS, GLUTES), True, _req({"kettlebell"}), 6,
             "Hike the bell back, snap the hips forward explosively to float it to chest height; it's a hinge, not a squat."),
    Exercise("bw_hip_hinge", "Single-Leg Hip Hinge", HINGE, (HAMSTRINGS, GLUTES), True, _req(), 2,
             "Balance on one leg, hinge forward reaching the floor while the free leg extends back, return under control."),
    # --- Lunge / unilateral ---
    Exercise("db_lunge", "Dumbbell Walking Lunge", LUNGE, (QUADS, GLUTES), True, _req(_DB), 7,
             "Dumbbells at sides, step forward and drop the back knee toward the floor, push through the front heel to advance."),
    Exercise("bw_split_squat", "Split Squat", LUNGE, (QUADS, GLUTES), True, _req(), 3,
             "Staggered stance, lower straight down until the back knee nears the floor, drive up. Finish all reps, then switch."),
    # --- Horizontal press ---
    Exercise("bb_bench", "Barbell Bench Press", H_PRESS, (CHEST, TRICEPS), True, _req(*_BAR_LOAD, _BENCH), 10,
             "Shoulder blades pinned, lower the bar to mid-chest with a slight tuck of the elbows, press up and slightly back."),
    Exercise("db_bench", "Dumbbell Bench Press", H_PRESS, (CHEST, TRICEPS), True, _req(_DB, _BENCH), 8,
             "Lie back with dumbbells at chest level, press up until they nearly touch, lower under control for a deep stretch."),
    Exercise("machine_press", "Machine Chest Press", H_PRESS, (CHEST, TRICEPS), True, _req(_CABLE), 6,
             "Set the seat so handles align with mid-chest, press out without locking hard, control the return."),
    Exercise("pushup", "Push-up", H_PRESS, (CHEST, TRICEPS), True, _req(), 3,
             "Hands just outside shoulders, body in a straight line, lower chest to the floor, press up. Elevate hands to scale."),
    # --- Incline press ---
    Exercise("db_incline", "Dumbbell Incline Press", INCLINE_PRESS, (CHEST, SHOULDERS), True, _req(_DB, {"bench_adjustable"}), 8,
             "Bench at ~30°, press dumbbells from upper chest to overhead, emphasizing the upper-chest stretch at the bottom."),
    Exercise("bb_incline", "Barbell Incline Press", INCLINE_PRESS, (CHEST, SHOULDERS), True, _req(*_BAR_LOAD, {"bench_adjustable"}), 9,
             "Bench at ~30°, lower the bar to the upper chest, press up and slightly back over the shoulders."),
    Exercise("decline_pushup", "Feet-Elevated Push-up", INCLINE_PRESS, (CHEST, SHOULDERS), True, _req(), 3,
             "Feet on a bench/box, hands on the floor; the elevation shifts emphasis to the upper chest and shoulders."),
    # --- Vertical press ---
    Exercise("bb_ohp", "Barbell Overhead Press", V_PRESS, (SHOULDERS, TRICEPS), True, _req(*_BAR_LOAD), 9,
             "Bar at collarbone, brace glutes and core, press overhead, move the head 'through' the window at lockout."),
    Exercise("db_shoulder_press", "Dumbbell Shoulder Press", V_PRESS, (SHOULDERS, TRICEPS), True, _req(_DB), 8,
             "Dumbbells at shoulder height, press overhead without flaring the ribs, lower under control to ear level."),
    Exercise("pike_pushup", "Pike Push-up", V_PRESS, (SHOULDERS, TRICEPS), True, _req(), 3,
             "Hips high in an inverted-V, lower the crown of your head toward the floor, press back up. A bodyweight overhead press."),
    # --- Horizontal pull ---
    Exercise("bb_row", "Barbell Row", H_PULL, (BACK, BICEPS), True, _req(*_BAR_LOAD), 9,
             "Hinge to ~45°, flat back, pull the bar to your lower ribs driving the elbows back, squeeze, lower under control."),
    Exercise("db_row", "Dumbbell Row", H_PULL, (BACK, BICEPS), True, _req(_DB), 8,
             "One hand and knee on a bench, row the dumbbell to your hip keeping the torso still, squeeze the lat at the top."),
    Exercise("cable_row", "Cable/Machine Row", H_PULL, (BACK, BICEPS), True, _req(_CABLE), 7,
             "Tall chest, pull the handle to your stomach driving elbows back, control the return without rounding."),
    Exercise("band_row", "Band Row", H_PULL, (BACK, BICEPS), True, _req({"resistance_bands"}), 4,
             "Anchor the band at chest height, pull the handles to your ribs squeezing the shoulder blades together."),
    Exercise("inverted_row", "Inverted Row", H_PULL, (BACK, BICEPS), True, _req(_PULLUP), 5,
             "Hang under a fixed bar, body straight, pull your chest to the bar. Lower your feet to make it harder."),
    # --- Vertical pull ---
    Exercise("pullup", "Pull-up", V_PULL, (BACK, BICEPS), True, _req(_PULLUP), 9,
             "Hang from the bar, pull your chest toward it leading with the elbows, control the descent. Band-assist if needed."),
    Exercise("lat_pulldown", "Lat Pulldown", V_PULL, (BACK, BICEPS), True, _req(_CABLE), 8,
             "Slight lean back, pull the bar to your upper chest driving elbows down and back, control the return."),
    Exercise("band_pulldown", "Band Lat Pulldown", V_PULL, (BACK, BICEPS), True, _req({"resistance_bands"}), 4,
             "Anchor a band overhead, pull the handles down to your chest squeezing the lats, resist on the way up."),
    # --- Shoulders isolation ---
    Exercise("db_lateral", "Dumbbell Lateral Raise", LATERAL, (SHOULDERS,), False, _req(_DB), 7,
             "Slight elbow bend, raise the dumbbells out to the sides to shoulder height, lead with the elbows, lower slowly."),
    Exercise("band_lateral", "Band Lateral Raise", LATERAL, (SHOULDERS,), False, _req({"resistance_bands"}), 4,
             "Stand on the band, raise the handles out to the sides to shoulder height, control the return."),
    # --- Biceps ---
    Exercise("db_curl", "Dumbbell Curl", CURL, (BICEPS,), False, _req(_DB), 7,
             "Elbows pinned at your sides, curl without swinging, squeeze at the top, lower fully for a complete stretch."),
    Exercise("bb_curl", "Barbell Curl", CURL, (BICEPS,), False, _req(*_BAR_LOAD), 7,
             "Shoulder-width grip, curl the bar with elbows fixed, no body swing, lower under control."),
    Exercise("band_curl", "Band Curl", CURL, (BICEPS,), False, _req({"resistance_bands"}), 4,
             "Stand on the band, curl the handles keeping elbows pinned, squeeze and resist the negative."),
    # --- Triceps ---
    Exercise("db_tri_ext", "Dumbbell Triceps Extension", TRI, (TRICEPS,), False, _req(_DB), 7,
             "Overhead (or lying), lower the dumbbell behind the head by bending only the elbows, extend to lock out."),
    Exercise("cable_pushdown", "Cable Pushdown", TRI, (TRICEPS,), False, _req(_CABLE), 7,
             "Elbows pinned to your sides, push the handle down to full extension, control the return to ~90°."),
    Exercise("bench_dip", "Bench Dip", TRI, (TRICEPS,), False, _req(), 3,
             "Hands on a bench behind you, lower your hips by bending the elbows to ~90°, press back up."),
    # --- Calves ---
    Exercise("db_calf", "Dumbbell Calf Raise", CALF, (CALVES,), False, _req(_DB), 6,
             "Hold a dumbbell, rise onto the balls of your feet for a full contraction, lower slowly for a deep stretch."),
    Exercise("bw_calf", "Bodyweight Calf Raise", CALF, (CALVES,), False, _req(), 3,
             "Rise onto your toes, pause at the top, lower under control. Use a step for more stretch; single-leg to progress."),
    # --- Core ---
    Exercise("hanging_leg_raise", "Hanging Leg Raise", CORE_P, (CORE,), False, _req(_PULLUP), 6,
             "Hang from the bar, raise your legs (bent to scale) by curling the pelvis up, lower slowly without swinging."),
    Exercise("plank", "Plank", CORE_P, (CORE,), False, _req(), 3,
             "Forearms down, body in a straight line, brace the abs and squeeze glutes; hold for time instead of reps."),
]

# Patterns sharing a muscle target — used for rule-based substitution when a
# slot's pattern can't be filled from the owned equipment.
SUBSTITUTION_FALLBACKS: dict[str, list[str]] = {
    V_PULL: [H_PULL],
    H_PULL: [V_PULL],
    INCLINE_PRESS: [H_PRESS, V_PRESS],
    H_PRESS: [INCLINE_PRESS],
    V_PRESS: [INCLINE_PRESS],
    LATERAL: [V_PRESS],
    LUNGE: [SQUAT],
    SQUAT: [LUNGE],
}

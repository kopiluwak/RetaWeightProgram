# Couch-to-Weights — Beginner Progressive Onboarding (SPEC)

Status: **APPROVED — backend implemented 2026-07-23.** Last updated 2026-07-23.
Read `PROJECT_STATE.md` + `OPERATIONS_RUNBOOK.md` first. This spec follows the
same structure as `NEUTRON_SPEC.md`: locked decisions up front, then data model,
API, engine integration, mobile, copy, testing, deploy.

---

## 0. One-paragraph summary

A "Couch-to-2K"–style easing-in mode for absolute beginners. The beginner still
picks their **3/4/5-day schedule**, but instead of getting a full split on day one,
each training **day** starts with **one exercise** (8–15 min sessions) and **gains
one more exercise each week**. So a beginner on a 4-day schedule does 4 different
single-exercise sessions in Week 1; in Week 2 each of those days keeps its exercise
and adds a new one (2 per day); and so on until each day reaches the full routine.
It is flexible (the user can defer an add) with **light, warm accountability** (a
gentle nudge the week after any skip, escalating slightly on a second consecutive
skip). The mode is **derived from the normal program** — the existing deterministic
engine still generates the full N-day plan; Couch mode is a *reveal window* that
shows only the first `unlocked` exercises **of each day**. Nothing about the program
engine's medical logic changes.

---

## 1. Locked decisions (from the requirements interview, 2026-07-23)

| # | Decision | Choice |
|---|----------|--------|
| D1 | Deliverable this session | **Spec doc only** (this file). No code yet. |
| D2 | Relationship to program engine | **Drip from the full program, per day.** The engine (`engine.py`) still generates the complete N-day plan; Couch mode reveals only the first `unlocked` exercises **of each day**. The beginner keeps their chosen 3/4/5-day schedule. No new generator. |
| D3 | Week advancement | **Calendar (7 days).** `week = 1 + floor((now − start)/7)`. Each new week raises the target by one exercise per day. A skip snoozes the prompt for the rest of that week only. |
| D4 | Trigger | **Onboarding experience field.** Selecting the beginner option auto-enables Couch mode. No separate global toggle in v1. |
| D5 | Ramp length / "full" | **6-week ramp.** Full complement per day = `min(6, that day's exercise count)`. First revealed exercise per day is its foundational compound. |
| D6 | Catch-up on missed weeks | **Always +1, never a jump.** If a user falls behind the calendar, the Add-it card keeps reappearing so they catch up one tap at a time; we never auto-add +2. |
| D7 | Add mechanism | **Explicit "Add it / Not yet" card** each week — no silent auto-advance. |

### 1a. Design principles carried from the coach-mode rules

- **Week 1 = ONE exercise per training day**, the single most important foundational
  movement for the user's equipment/goals (squat variation, a push, or a hinge).
  Sessions 8–15 min.
- **Every subsequent week: add exactly one exercise**, unless the user defers.
- **Goal:** keep adding one per week until the user hits the full daily routine.
- **Flexibility:** the user can always "keep the same number this week."
- **Light accountability:** warm/positive on a skip; mild positive pressure the
  week after a skip; slightly stronger (still supportive) on two skips in a row.
- **Every surface must state:** current week, exercise count this week, today's full
  workout (sets/reps/rest), and whether a new exercise was just added and why.
- Language stays encouraging, simple, jargon-free. Celebrate every small win.

---

## 2. The one reconciliation problem, and the fix

Today `experience` is a 3-value field — schema pattern
`^(conservative|intermediate|advanced)$` (`schemas.py` `HabitsIn`), engine bands
`_EXPERIENCE_FACTOR = {"conservative":0.8, "intermediate":1.0, "advanced":1.15}`
(`engine.py`), and the onboarding UI labels the conservative option **"New /
returning"** (`OnboardingScreen.tsx` `EXPERIENCE`). "Returning" lifters are *not*
absolute beginners and should not be dripped down to one exercise.

**Fix (recommended):** split the conservative chip into two onboarding options
without touching the engine's volume math:

- `beginner` → label **"New to lifting — ease me in"** → enables Couch mode.
- `conservative` → relabel to **"Returning / cautious"** → normal full program.

`beginner` is a **new experience value at the API/UI layer only**. The engine never
sees it: the programs router maps `beginner → conservative` before calling
`generate_program`, so `beginner` inherits the 0.8 volume band and no engine change
is needed. This keeps the experience field as the single trigger (D4) while not
mislabeling returning lifters as beginners.

> Alternative considered and rejected for v1: a standalone `couch_mode` boolean
> toggle independent of experience. Cleaner separation, but the interview picked the
> experience field as the trigger, so we keep one control. The boolean still exists
> internally (see `couch_mode` below) — we just derive it from the experience choice
> rather than exposing a second switch. Easy to expose later if wanted.

---

## 3. Data model

All new state lives on the existing **`UserHabits`** row (one per user) — Couch mode
is per-user, not per-program, and must survive program regeneration.

New columns on `user_habits` (`models.py` `UserHabits`):

| Column | Type | Default | Meaning |
|--------|------|---------|---------|
| `couch_mode` | bool | `false` | Master flag. Set true when `experience == "beginner"` at onboarding. |
| `couch_started_at` | datetime(tz) \| null | null | When Week 1 began. Anchors the calendar week counter. |
| `couch_unlocked` | int | `1` | Exercises revealed **per day** right now (Week 1 → 1). |
| `couch_snoozed_week` | int | `0` | The `week` number in which the user last tapped "Not yet". Suppresses further prompts that same week only (D3). `0` = never. |
| `couch_consecutive_skips` | int | `0` | Deferred adds in a row. Drives nudge escalation. Reset to 0 on any add. |
| `couch_graduated` | bool | `false` | True once `couch_unlocked` reaches `full`. Mode goes dormant; user is on the full plan. |

`experience` stays `String(20)` and simply gains `beginner` as an allowed value
(schema pattern widened — see §4).

### 3a. Derived values (never stored — computed on read)

- **`full`** — `min(6, max exercise count across the program's days)` (D5). The
  per-day reveal is capped to each day's own length.
- **`week`** — `1 + floor((now − couch_started_at) / 7 days)`. The calendar target;
  shown as "You're in Week 3".
- **`target`** — `min(week, full)`: how many exercises per day the user *should* be
  at by now. Drives catch-up (D6).
- **`decision_due`** — a +1 is offered when `couch_unlocked < target` **and**
  `week > couch_snoozed_week` **and** not `couch_graduated`. Because it keys off
  `target` (not a per-level clock), a user who fell behind is offered +1 repeatedly
  until caught up — always one at a time (D6).
- **`nudge_level`** — `0` normally; `1` the week after one skip; `2` after two or
  more consecutive skips. Selects the accountability copy (§7).

---

## 4. Schema / validation changes

`schemas.py`:

- `HabitsIn.experience` pattern → `^(beginner|conservative|intermediate|advanced)$`.
- `HabitsOut` gains a nested **`couch`** object (nullable): `mode`, `week`,
  `unlocked`, `full`, `graduated`, `decision_due`, `nudge_level`. `null` when the
  user is not a beginner. This flows through `MeOut.habits` so the app's post-login
  `/me` bootstrap already knows the Couch state — no extra call on launch.

New response schema **`CouchViewOut`** (returned by the Couch endpoints, §6):

```
CouchViewOut
  mode: bool
  week: int                 # display week number
  unlocked: int             # exercises per day this week
  full: int                 # full daily routine size (min(6, max day length))
  graduated: bool
  decision_due: bool        # a +1 is offered right now
  nudge_level: int          # 0|1|2 -> copy selection
  headline: str             # e.g. "Week 3 · 3 exercises per day"
  message: str              # the warm coach line for this state (§7)
  added_today: str | null   # name of the exercise just added (newest, day 1), else null
  added_reason: str | null  # short "why this one" line, else null
  days: list[ProgramDayOut] # every training day, each showing its first `unlocked`
                            # exercises (beginner-tuned sets, recomputed est_minutes)
```

Reusing `ProgramDayOut`/`ProgramExerciseOut` means `CouchProgramScreen` can render
days exactly like `ProgramScreen` (Day 1/2/… tabs), just with fewer exercises.

`CouchAdvanceIn`: `{ action: "add" | "skip" }`.

---

## 5. Engine integration — per-day reveal (drip-from-full-program)

No change to `generate_program`. We add a **pure, unit-testable** helper module
`backend/app/couch.py` (stdlib only — no FastAPI/DB) that turns an already-generated
`Program` dict + the stored Couch state into the beginner view.

**`couch_full(program: dict) -> int`** — `min(LADDER_MAX, max(len(day["exercises"])
for day in program["days"]))`, `LADDER_MAX = 6` (D5). This is the finish line.

**`couch_days(program: dict, unlocked: int) -> list[dict]`** — for each program day,
reveal its **first `unlocked` exercises**, so a 4-day beginner sees 4 days each with
`unlocked` moves:

1. Reveal exercises in the **engine's authored slot order** (not a compounds-first
   re-sort). The Push/Pull/Legs templates put each day's primary compound first and
   the paired secondary muscle second (triceps on push, biceps on pull), so a
   1-exercise day is the primary lift and a 2-exercise day is the intended pairing.
   Every day targets a distinct primary muscle, so Week 1 hits a different muscle
   group each training day (no repeated chest/leg days).
2. Take the first `min(unlocked, len(day))` of that authored list.
3. **Beginner set-cap:** the **newest** exercise on a day (index `unlocked-1`) is
   capped to **2 working sets** while it's brand-new; older exercises keep the
   engine's prescribed sets. This eases each new movement in and keeps Week-1
   sessions in the 8–15 min window (1 compound × 2 sets × 3.5 min + 8 min warm-up ≈
   15 min).
4. Reps/RIR/rest are passed through untouched from the engine — we never reinvent the
   medical logic.
5. Recompute `est_minutes` for the truncated day with the engine's own cost model
   (`_WARMUP_MIN` + Σ `_cost(compound)·sets`).

**`couch_state(habits, program, now) -> dict`** — pure clock/target math from §3a:
returns `full`, `week`, `target`, `decision_due`, `nudge_level`, plus the `headline`
and `message` copy (§7). No DB access — the router passes plain values in.

Because the view is derived on read, regenerating the program (new equipment, a
different day count) automatically re-derives it; `couch_unlocked` is clamped to the
new `full` on read if the new program's days are shorter.

---

## 6. API surface

All under `https://api.glpsteel.com`, all auth'd. Added to the existing
`routers/programs.py` (prefix `/programs`) since the Couch view is a program view.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/programs/couch` | Current Couch view for the user (`CouchViewOut`). 400 if not in Couch mode or no active program yet. Computes `decision_due`/`week`/`nudge_level` on the fly. |
| POST | `/programs/couch/advance` | Body `CouchAdvanceIn`. Applies the user's level-up decision. |

**`POST /programs/couch/advance` semantics**

- `action:"add"` (only valid when `decision_due`, else 409): `couch_unlocked += 1`;
  `couch_consecutive_skips = 0`. If `couch_unlocked >= full` →
  `couch_graduated = true` and the response celebrates reaching the full routine.
  Response sets `added_today`/`added_reason`. Because `decision_due` keys off
  `target`, a user who was behind will immediately see the card again for the next
  +1 — catch-up one tap at a time (D6), never a silent +2.
- `action:"skip"`: `couch_consecutive_skips += 1`; `couch_snoozed_week = week`
  (suppresses the prompt for the rest of *this* calendar week only; it returns next
  week). `couch_unlocked` unchanged. Response uses the warm "consistency first" copy.

Onboarding (`routers/onboarding.py`, `PUT /habits`): when the incoming
`experience == "beginner"` **and** the user is not already in Couch mode, initialize
`couch_mode=true`, `couch_started_at=now`, `couch_unlocked=1`,
`couch_level_since=now`, `couch_consecutive_skips=0`, `couch_graduated=false`. If a
user switches *away* from beginner later, set `couch_mode=false` (state retained but
dormant). `_habits_out` is extended to include the derived `couch` object.

> Note: `POST /programs/generate` is still required once (Couch needs an active
> program to derive the ladder from). The app should auto-generate right after a
> beginner finishes onboarding + inventory, then route to the Couch screen instead
> of the full ProgramScreen.

---

## 7. Accountability copy (backend-owned, single source of truth)

Copy strings live in `couch.py` so the app and any future chat surface stay
identical. Selected by state:

- **Week 1 (unlocked==1):** "Week 1 — just one move today: {name}. Nail this and
  you've already started. 8–15 minutes, that's it. 💪"
- **Normal level-up available (nudge_level 0):** "You're rolling. Add exercise #{n}
  this week — {name}. It only adds a few minutes and your body's ready. Level up?"
- **After a skip, warm confirm:** "No problem — consistency first. We'll stay at
  {unlocked} this week and lock in the habit."
- **Week after one skip (nudge_level 1):** "Last week we stayed at {unlocked} so you
  could lock in the habit. This week's the perfect time to add the next one — it
  only takes a few extra minutes and your body is ready. Shall we level up?"
- **Two skips in a row (nudge_level 2):** "You've built a solid base at {unlocked}
  exercises — that consistency is exactly what makes adding the next one easy. Let's
  give it a try this week; I think you're more ready than you feel. Add {name}?"
- **Graduation (unlocked==full):** "That's the full routine — {full} exercises. You
  built it one week at a time from a single move. This is a real milestone. 🎉"

Every Couch response also carries `headline` = `"Week {week} · {unlocked} exercise{s}
per day"` so the "which week / how many" requirement is always on screen.

---

## 8. Mobile

Reuse the existing `ui/` kit (Button, Card, Badge, Chip, ProgressBar, SetDots,
Stepper, ScreenBackground) and `theme.ts` — no inline hex, no new dependencies.

- **`OnboardingScreen.tsx`** — `EXPERIENCE` array: add `{key:"beginner", label:"New
  to lifting — ease me in"}` as the first chip; relabel `conservative` to
  `"Returning / cautious"`. A one-line helper under the chips when `beginner` is
  selected: "We'll start you with one exercise and add one each week."
- **New `CouchProgramScreen.tsx`** — the beginner's home for the program tab:
  - Header: `headline` ("Week 3 · 3 exercises today") + a `ProgressBar` of
    `unlocked / full` (visible finish line).
  - `added_today` banner (Badge "New this week") with `added_reason` when present.
  - Today's workout: the `today[]` exercises rendered like ProgramScreen's rows
    (name, sets×reps, rest, form-cue/video link), plus "Log this workout" → existing
    workout logger (`onStartWorkout`) unchanged.
  - **Decision card** shown only when `decision_due`: the `message` copy + two
    buttons — primary **"Add it"** (`success`) and secondary **"Not yet"**. Calls
    `POST /programs/couch/advance`. On add, a small celebration (reuse the +XP/
    achievement banner pattern from WorkoutScreen's done phase).
  - Graduation state: celebratory card + a "Go to full program" button that routes
    to the normal `ProgramScreen`.
- **Routing:** if `me.habits.couch.mode && !graduated`, the Program tab renders
  `CouchProgramScreen`; otherwise `ProgramScreen` as today. HomeScreen's program
  quick-action points to the same.
- **`api.ts`:** extend `Habits` type with the nested `couch` object; add
  `CouchApi.get()` → `GET /programs/couch` and `CouchApi.advance(action)` →
  `POST /programs/couch/advance`. `Program`/`ProgramApi` unchanged.

No native deps → JS-only change on the mobile side: `npx expo start` on the existing
dev build is enough to test (per runbook §B).

---

## 9. Testing

- **`tests/test_couch.py`** (pure, node-free, no DB — same pattern as
  `test_gamification.py`): `couch_ladder` ordering/dedup/cap, `couch_today` set
  capping + 8–15 min Week-1 time budget, `couch_decision` clock math (before 7 days:
  not due; at/after: due; skip resets clock; graduation clamps). Deterministic:
  same program → same ladder.
- Backend `python3 -m py_compile app/*.py app/routers/*.py`.
- `npx tsc --noEmit` in `mobile/`.
- **Simulator (runbook §B):** onboard as `beginner`, confirm Week-1 shows exactly
  one exercise 8–15 min; fast-forward the clock (temporary test override of
  `couch_level_since`) to verify the decision card, add, skip, nudge escalation, and
  graduation; check **both light and dark mode**.

---

## 10. Deploy notes

- **DB:** the six new columns are added to the **existing** `user_habits` table.
  `create_all` never adds columns to existing tables, so append idempotent ALTERs to
  `_COLUMN_BOOTSTRAP` in `database.py` (same mechanism used for
  `protein_multiplier`), e.g.:
  ```
  ALTER TABLE user_habits ADD COLUMN couch_mode BOOLEAN NOT NULL DEFAULT false
  ALTER TABLE user_habits ADD COLUMN couch_started_at TIMESTAMPTZ
  ALTER TABLE user_habits ADD COLUMN couch_unlocked INTEGER NOT NULL DEFAULT 1
  ALTER TABLE user_habits ADD COLUMN couch_level_since TIMESTAMPTZ
  ALTER TABLE user_habits ADD COLUMN couch_consecutive_skips INTEGER NOT NULL DEFAULT 0
  ALTER TABLE user_habits ADD COLUMN couch_graduated BOOLEAN NOT NULL DEFAULT false
  ```
  No manual DB step; boot applies them.
- **Backend deploy:** standard runbook §A (edit on drive → py_compile →
  **rsync to `~/wp-backend-build`** → docker build `--provenance=false --sbom=false`
  → push → force new deployment → **re-point `api.glpsteel.com` to the healthy
  target group** → `curl /health`).
- **Mobile:** JS-only; bump `ios.buildNumber` only when you cut a TestFlight build
  (runbook §C). Simulator pass first (§B).
- **Backward compatibility:** existing users have `couch_mode=false` (column default)
  → they see the unchanged full program. Only new `beginner` selections opt in.

---

## 11. Resolved (review answers, 2026-07-23)

1. **Ladder cap `LADDER_MAX = 6`** — confirmed; 6-week ramp. (D5)
2. **Beginner keeps the 3/4/5-day schedule** — each *day* ramps from 1 exercise,
   adding one per week; not a single repeated routine. (D2) This is the whole reason
   §5 became a per-day reveal.
3. **Explicit "Add it / Not yet" card** each week — confirmed, no silent
   auto-advance. (D7)
4. **Always +1** — confirmed; if a user falls behind, the card keeps reappearing to
   catch up one tap at a time, never a +2 jump. (D6)
5. **Relabel `conservative` → "Returning / cautious"** and add the `beginner` chip —
   confirmed fine to change. (§2)

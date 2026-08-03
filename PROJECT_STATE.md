# WeightProgram — Project State (handoff)

One-page onboarding for a new thread. Read this + `OPERATIONS_RUNBOOK.md` before working.
Last updated: 2026-07-04.

## What it is
A mobile app that photographs a user's weights/equipment, uses a vision LLM to
build an editable inventory, and generates 3/4/5-day resistance programs tuned for
GLP-1–class weight-loss (muscle preservation in a deficit), plus workout logging
with progression feedback. React Native (Expo) app + FastAPI backend on AWS.

## Repo layout (folder: WeightProgram/)
- `backend/` — FastAPI + SQLAlchemy(async) + asyncpg. App code in `backend/app/`.
- `mobile/` — Expo React Native (SDK 54, RN 0.81, React 19). Screens in `mobile/src/screens/`.
- `BUILD_SPEC.md` — locked design decisions + rationale (the "why").
- `DEPLOYMENT.md`, `OPERATIONS_RUNBOOK.md` — infra + deploy procedure + gotchas.
- `README.md` — architecture + local run.

## Architecture (all AWS us-east-1, account 453371324700)
- Backend runs on **ECS Express** service `weightprogram-api-1257` (Fargate), fronted by
  ALB `ecs-express-gateway-alb-a6344ce9`, live at **https://api.glpsteel.com**.
- **RDS Postgres 18** (`weightprogram-db`, database `postgres`, user `wpadmin`).
- **Bedrock** (Claude Sonnet 4.6, `us.anthropic.claude-sonnet-4-6`) for equipment recognition.
- **SES** (`no-reply@glpsteel.com`, domain verified, production) for OTP login emails.
- **S3** `weightprogram-captures` for consented capture images.
- Image: ECR `weightprogram-api`. Route 53 hosts `glpsteel.com`.

## What's built and working (verified in production on-device)
- **Auth:** passwordless email OTP; JWT access + rotating refresh (secure enclave on device).
- **Onboarding:** days/week, session length, experience.
- **Capture → recognition → confirm:** photos re-encoded to JPEG, sent to Bedrock (capped to
  4 images), user confirms an editable, versioned inventory. Cardio equipment recognized/stored
  but excluded from lifting programs.
- **Program engine:** deterministic 3/4/5-day generation (intensity-priority, RIR, frequency-as-
  output under a session time budget, double progression, deficit/deload notes). Exercise
  descriptions + YouTube how-to links + per-exercise rest targets.
- **Workout logging:** readiness check, set logging (pre-filled from last session), rest timer with
  audible beep + haptic, double-progression suggestions, history.
- **TestFlight:** Build 3 live to internal testers; Build 2 external group in Beta App Review.
  Reviewer login bypass: `reviewer@glpsteel.com` / code `027858` (env vars REVIEW_EMAIL/REVIEW_CODE).
- **UI system (2026-07-04):** Full visual rework, no new dependencies. `mobile/src/theme.ts`
  (light/dark palettes, spacing, radius, typography via `useTheme()`) + `mobile/src/ui/` kit
  (Button, Card, Badge, Chip, ProgressBar, SetDots, Stepper, ScreenBackground). Every screen
  now uses these — reuse them for any new screen instead of inline hex colors. `WorkoutScreen`
  specifically: "NOW LOGGING" banner + per-exercise `SetDots`/`Badge` show which set the user
  is on at a glance; `Stepper` (tap +/- with press-and-hold, or type directly) replaces plain
  text fields for weight/reps/RIR; rest timer got an animated progress bar. Not yet in a shipped
  TestFlight build — bump `ios.buildNumber` and run the EAS build steps in the runbook to ship it.

- **Analytics module (2026-07-06, not yet deployed/shipped):** server-side `/analytics/*`
  (summary, exercises, exercises/{name}, history) computed in `backend/app/analytics.py`
  (RIR-adjusted Epley e1RM capped at 12 effective reps; PRs need ≥3 prior sessions; 4-condition
  plateau gate; 90d linear-regression PR projection gated to a 12-week horizon). App side:
  `ProgressScreen` (5 reorderable cards, order in SecureStore), `ExerciseTrendsScreen`
  (range selector 30d–All), `HistoryScreen` (26-week heatmap + filterable log), PR share-card
  image via view-shot. Charts hand-rolled in `mobile/src/ui/charts/` on react-native-svg.
  **Three new native deps** (`react-native-svg@15.12.1`, `react-native-view-shot@4.0.3`,
  `react-native-safe-area-context@~5.6.0` — the last replaces RN core's deprecated
  SafeAreaView in `ScreenBackground`; `SafeAreaProvider` now wraps the app root) —
  run `npm install` in `mobile/` before the next build; all are Expo SDK 54-pinned versions.

- **Neutron nutrition module (2026-07-07; CONFIRMED LIVE in prod 2026-07-13 —
  `/nutrition/marketplace` returns 401, so an earlier note here claiming "not
  yet deployed" was stale):** see `NEUTRON_SPEC.md`.
  Protein profile (1 g/kg auto target + bodyweight logging), "Scan My Kitchen"
  (pantry/fridge photos → Bedrock forced-tool food list → user-confirmed pantry; photos
  never stored), recipe generation + vegan/vegetarian adapt + Surprise-Me day plan
  (Bedrock text Converse, hard dietary constraints incl. Alpha-Gal), protein logging with
  streaks/badges/levels/muscle-score (`neutron_gamification.py`, unit-tested), curated
  Protein Boosters marketplace (placeholder affiliate links + disclosure). Backend:
  `neutron_vision.py`, `neutron_recipes.py`, `neutron_gamification.py`,
  `routers/nutrition.py`, 6 new tables in `models.py` (auto-created on boot). Mobile: 6 new
  screens (NutritionHome/Setup, KitchenScan, Recipes, ProteinTracker, ProteinBoosters),
  `NutritionApi` in `api.ts`, Home "SOON" teaser card replaced with the live entrance.
  No new mobile dependencies. `tsc --noEmit` clean.

- **Neutron Voice Log (2026-07-12, not yet deployed/shipped):** dictate a meal →
  approximate daily protein total. Cache-first/AI-last: on-device speech
  recognition (`expo-speech-recognition`, on-device mode when supported) →
  on-device parse (`mobile/src/nutrition/`: quantity grammar + ~350-food
  curated DB with fuzzy matching + Naive Bayes category classifier + sqlite
  alias cache of corrections/AI answers + offline log queue) → editable review
  cards → existing `POST /nutrition/log` (`source: "voice"`). AI only for
  unresolved phrases via new `POST /nutrition/parse` (`neutron_parse.py`,
  forced-tool Bedrock, stubbed under `VISION_PROVIDER=stub`) backed by the
  shared `nutrition_parse_cache` table (auto-created on boot) — each phrase
  hits the model at most once. **Two new native deps** (`expo-speech-recognition
  ^3.1.3`, `expo-sqlite ~16.0.8`) + app.json plugin entries → next mobile build
  needs `npm install` AND a full `npx expo run:ios`. `tsc --noEmit` clean;
  parser/matcher unit-tested under node; backend py_compile + stub-parse tested.
  Details in `NEUTRON_SPEC.md` §N8.

- **Gamification module (2026-07-13, not yet deployed/shipped):** XP/levels,
  workout streaks, weekly challenge, achievements, and shaded weekly badges.
  Backend: `gamification.py` (pure functions, unit-tested in
  `tests/test_gamification.py` — run `python3 -m tests.test_gamification`),
  `routers/gamification.py` (`GET /gamification/summary?tz=` — recomputes XP
  from WorkoutSession+ProteinLog history on every read; reading it also awards
  new achievements into the new `workout_badges` table, auto-created on boot).
  Nutrition profile gained a configurable auto-target multiplier
  (`protein_multiplier` g/kg, default 1.52 ≈ 0.69 g/lb; presets 1.0 (GLP-1
  minimum) / 1.52 / 2.2≈1 g/lb in NutritionSetupScreen). **Deploy note:**
  `protein_multiplier` is a new COLUMN on `nutrition_profiles`; `create_all`
  never adds columns to existing tables, so `init_models` now also runs a
  `_COLUMN_BOOTSTRAP` list in `database.py` (idempotent ALTERs on boot) — no
  manual DB step. Add future pre-Alembic column additions to that list. Mobile: new `ui/` components
  (GamificationHeader, WeeklyChallengeCard, ProteinProgress, ProgressRing,
  WeeklyBadge — all react-native-svg, no new deps), Home redesigned around the
  hero + quick actions, WeeklyChallengeCard in ProgramScreen, shaded weekly
  badges in ProgressScreen's Consistency card, "Today" protein hero in
  ProteinTrackerScreen, +XP / achievement-unlocked banner on WorkoutScreen's
  done phase. `GamificationApi` in `api.ts`. JS-only (no native changes) —
  `npx expo start` on the existing dev build is enough to test. `tsc --noEmit`
  clean; backend py_compile + unit tests pass.

- **Couch-to-Weights beginner mode (2026-07-23, backend live + confirmed working,
  mobile built `tsc` clean but NOT yet in a shipped TestFlight build):** progressive
  onboarding — a beginner keeps their 3/4/5-day split but each day starts at ONE
  exercise and reveals one more per calendar week (6-week ramp, `LADDER_MAX=6`), with
  an explicit "Add it / Not yet" card, warm skip/nudge accountability, and +1-only
  catch-up. Spec: `COUCH_TO_WEIGHTS_SPEC.md`.
  Backend: pure module `couch.py` (per-day reveal, clock/target math, coach copy;
  unit-tested in `tests/test_couch.py` — `python3 -m tests.test_couch`), two
  endpoints on the programs router (`GET /programs/couch`, `POST /programs/couch/advance`),
  onboarding inits ramp state when `experience=="beginner"` and `/me`'s habits gain a
  `couch` object. New `beginner` experience value maps to the engine's `conservative`
  band (no engine change). Six new `user_habits` columns (`couch_*`) via
  `_COLUMN_BOOTSTRAP` idempotent ALTERs — no manual DB step.
  Mobile (JS-only, no new deps): `OnboardingScreen` experience chips split
  (`beginner` "New to lifting — ease me in" + relabeled `conservative`
  "Returning / cautious"); new `CouchProgramScreen` (headline + `unlocked/full`
  progress bar, coach message, Add-it/Not-yet decision card, added-this-week
  celebration, graduation handoff, day tabs of revealed exercises — hands the
  workout logger the real program id with only revealed days); `CouchApi` +
  `CouchState`/`CouchView` types in `api.ts`; `App.tsx` routes beginners to the
  Couch screen until `couch.graduated`. Next: simulator pass (runbook §B, both
  themes) then bump `ios.buildNumber` for TestFlight.

- **Program/inventory UX additions (2026-07-23, backend + mobile built `tsc`
  clean, NOT yet shipped):** four features layered on the above.
  (1) **Persistent Home nav** — `src/NavContext.tsx` provides `goHome`; wrapped
  around the authenticated app in `App.tsx`; `ScreenBackground` renders a top-right
  "⌂ Home" pill on every in-app screen (Home opts out via `showHome={false}`).
  (2) **Manage program** — new `POST /programs/couch/restart` (rewind ramp to
  Week 1, sets `experience=beginner`, re-arms Couch; workout logs untouched) and
  `POST /programs/couch/graduate` (jump to full program). Surfaced as a "Manage
  program" card on both `ProgramScreen` and `CouchProgramScreen` (Regenerate,
  Customize equipment, Add equipment, Restart/Graduate). ProgramScreen's
  `onModeChanged` makes the shell re-read `/me` and switch to the beginner view
  after a restart.
  (3) **Equipment customization** — `POST /programs/generate` now accepts
  `bodyweight_only` + `equipment_types`, persisted on two new `user_habits`
  columns (`gen_bodyweight_only`, `gen_equipment_types` JSONB) via
  `_COLUMN_BOOTSTRAP`. Bodyweight-only no longer requires a confirmed inventory
  (program `inventory_version_id` nullable in that case). New
  `CustomizationScreen` (per-type toggles + bodyweight switch). `ProgramApi.generate`
  now takes an opts object `{daysPerWeek, bodyweightOnly, equipmentTypes}`.
  (4) **Incremental scan-to-add** — `POST /inventory/capture` gains `mode`
  (`replace` default | `add`); `add` merges recognized items into the current
  confirmed inventory (duplicate type bumps quantity) and routes through the same
  confirm screen. `CaptureScreen` takes a `mode` prop; reachable from the Manage
  card. JS-only mobile, no new deps.

- **Program engine → Push/Pull/Legs split (2026-07-23, backend built, NOT deployed):**
  `engine.py` templates rebuilt so every training day targets a distinct primary
  muscle (fixes the beginner reveal showing 2 leg / 2 chest days). 3-day = Push /
  Pull / Legs; 4-day adds Shoulders & Arms; 5-day = Push / Pull / Legs / Shoulders /
  Arms. Slot order is significant: primary compound first, paired muscle second
  (triceps on push, biceps on pull), so beginner Week-1 = one distinct primary per
  day and Week-2 = chest+triceps / back+biceps / legs. `couch.py` reveal now follows
  the engine's authored slot order (removed the compounds-first re-sort) so the
  pairing is preserved; `tests/test_couch.py` updated (`test_reveal_follows_authored_order`).

- **Add-your-own-exercise (2026-07-27, backend + mobile built `tsc`/tests clean,
  NOT yet deployed/shipped):** two ways to add a movement to the active program,
  each landing on the correct muscle-group day and immediately loggable (the
  workout logger reads `plan_json.days[i].exercises`, so no logger change needed).
  (1) **Pick a specific one** — choose a known movement (pull-up, push-up,
  isolation curl, …) from the library. (2) **Saw it on social media** — free text;
  resolved AI-last (fuzzy library match first, Bedrock classifier only on a miss)
  into muscle group + compound flag + a short form cue, with a suggested day the
  user can override. Backend: pure module `custom_exercise.py` (library search,
  `best_day_index` muscle→day matching by existing-day content + day-name keywords,
  plan add/remove helpers, forced-tool Bedrock classifier + deterministic stub via
  `settings.vision_provider`, mirrors `neutron_parse.py`; unit-tested in
  `tests/test_custom_exercise.py` — `python3 -m tests.test_custom_exercise`).
  New `ProgramExercise.added_by_user` bool (default False, so pre-existing stored
  programs still parse). Four static routes added to the programs router BEFORE the
  `/{program_id}` catch-all: `GET /programs/exercise-library`,
  `POST /programs/exercises/{classify,add,remove}` (mutations use
  `flag_modified(program, "plan_json")` since the JSON dict is edited in place).
  Mobile (JS-only, no new deps): new `AddExerciseScreen` (library picker with
  search/muscle filter + social-suggest text→classify→confirm-day flow),
  "Add an exercise" button on ProgramScreen's Manage card, an "added" badge +
  Remove control on user-added exercise cards, `App.tsx` route `addExercise`,
  `ProgramApi.{exerciseLibrary,classifyExercise,addExercise,removeExercise}` in
  `api.ts`. Couch/beginner screen intentionally not wired (they graduate into the
  full ProgramScreen). Next: simulator pass (runbook §B, both themes).

## API surface (all under https://api.glpsteel.com)
`/auth/*` (request-otp, verify-otp, refresh, logout) · `/me` · `/habits*` ·
`/inventory` (capture, {id}/confirm, edit) · `/programs` (generate, current, {id}) ·
`/workouts` (start, {id}/log, {id}/finish, history, last-performance) ·
`/analytics` (summary, exercises, exercises/{name}, history) ·
`/nutrition` (profile, weight, pantry/scan, pantry, recipes/{generate,adapt,surprise,saved},
parse, log, summary, marketplace) · `/gamification/summary` ·
`/programs/couch` (GET, advance, restart, graduate) ·
`/programs/exercise-library` · `/programs/exercises` (classify, add, remove) ·
`/health` · `/privacy` · `/support`

## Known pending items (open)
1. Backend still has diagnostic `_log.warning` lines in `recognition.py` — remove before launch.
2. DB uses `rds.force_ssl=0` (plaintext in-VPC) — re-enable TLS via SSL context in `database.py`.
3. Reviewer bypass is a live backdoor — remove/rotate before public launch.
4. `api.glpsteel.com` needs a stable route so the blue/green re-point step goes away
   (add it to Express's managed host rule, or a dedicated ALB).
5. DB schema via `init_models` create_all on boot — move to Alembic before real users.
6. App: `WorkoutScreen` keyboard-avoidance fix ready (not yet in a shipped build).

## Deploy reality (see OPERATIONS_RUNBOOK.md for full detail)
- Build backend from `~/wp-backend-build` (internal disk), NOT the exFAT project drive.
  **Re-run rsync after every edit** or you rebuild old code.
- `docker build --provenance=false --sbom=false` (Fargate can't pull buildx attestation indexes).
- Every deploy: force new deployment → **re-point `api.glpsteel.com` listener rule to the healthy
  target group** (blue/green flips it) → verify `/health`. Health-check path must stay `/health`.
- App builds: `npx eas-cli build --platform ios --profile production` then `submit`; bump
  `ios.buildNumber` each time.

## How to start the next thread
Say: "Read PROJECT_STATE.md and OPERATIONS_RUNBOOK.md in the WeightProgram folder. Today I want to
work on <reporting / look-and-feel / feature X>." Then define the feature; for structured features
the project's interview-driven spec workflow applies, for pure visual polish iterate directly.

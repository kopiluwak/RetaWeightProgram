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

- **Neutron nutrition module (2026-07-07, not yet deployed/shipped):** see `NEUTRON_SPEC.md`.
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

## API surface (all under https://api.glpsteel.com)
`/auth/*` (request-otp, verify-otp, refresh, logout) · `/me` · `/habits*` ·
`/inventory` (capture, {id}/confirm, edit) · `/programs` (generate, current, {id}) ·
`/workouts` (start, {id}/log, {id}/finish, history, last-performance) ·
`/analytics` (summary, exercises, exercises/{name}, history) ·
`/nutrition` (profile, weight, pantry/scan, pantry, recipes/{generate,adapt,surprise,saved},
log, summary, marketplace) · `/health` · `/privacy` · `/support`

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

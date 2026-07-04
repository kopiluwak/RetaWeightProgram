# WeightProgram — Project State (handoff)

One-page onboarding for a new thread. Read this + `OPERATIONS_RUNBOOK.md` before working.
Last updated: 2026-07-02.

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

## API surface (all under https://api.glpsteel.com)
`/auth/*` (request-otp, verify-otp, refresh, logout) · `/me` · `/habits*` ·
`/inventory` (capture, {id}/confirm, edit) · `/programs` (generate, current, {id}) ·
`/workouts` (start, {id}/log, {id}/finish, history, last-performance) · `/health` · `/privacy` · `/support`

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

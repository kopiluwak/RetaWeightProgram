# WeightProgram

Photograph your weights/equipment → get a resistance program tuned for GLP-1–class
weight-loss (muscle preservation in a deficit). React Native client + FastAPI backend.

See `BUILD_SPEC.md` for the locked design decisions and roadmap.

## Status — Increment 1 (auth + onboarding) ✅
Passwordless email registration (6-digit OTP via AWS SES), JWT + rotating refresh
tokens with instant revocation, and the first-login habits/onboarding step that
feeds the program engine in later increments.

## Status — Increment 2 (equipment capture + recognition) ✅
Camera/photo capture → vision-LLM recognition (AWS Bedrock + Claude) → a
**mandatory confirmation screen** → editable, versioned inventory. Consent-gated
flywheel logging stores the (image, draft, corrected) triple only when the user
opts in. Runs against a deterministic **stub recognizer** (`VISION_PROVIDER=stub`)
so the whole flow is testable without AWS; flip to `bedrock` for real recognition.

## Status — Increment 3 (program engine) ✅
A **deterministic, rules-dominant** engine turns a confirmed inventory + habits
(days/week, session length, experience) into 3/4/5-day programs. Encodes the
locked training logic: intensity-priority (5-8 rep compounds), RIR autoregulation,
frequency-as-output under a session time budget, double progression, and deficit/
deload coaching notes. Same inputs → same program (testable, defensible). Picks
only exercises your equipment supports, substitutes muscle-equivalents when a
pattern can't be equipped, and honestly flags gaps it can't fill.

## Status — Increment 4 (workout logging) ✅
Log a session against a program day with a readiness check, record sets
(reps/weight/RIR), a rest timer driven by per-exercise `rest_seconds` (compounds
150s, accessories 75s), and on finish get **double-progression suggestions**
(increase / hold / reduce load) computed deterministically from what you logged —
load only increases when every set hit the top of the range with reps to spare,
never on a grinding set. Plus session history.

### Workouts API (Increment 4)
| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/workouts/start` | bearer | Start a session for a program day (+ readiness 1-5) |
| POST | `/workouts/{id}/log` | bearer | Log a set (exercise, set #, reps, RIR, weight) |
| POST | `/workouts/{id}/finish` | bearer | Complete + return progression suggestions |
| GET | `/workouts/history` | bearer | Recent sessions (summary) |
| GET | `/workouts/{id}` | bearer | A session with its sets |

### Programs API (Increment 3)
| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/programs/generate` | bearer | Build from current inventory + habits (optional `days_per_week` override) |
| GET | `/programs/current` | bearer | Active program (+ `stale` flag if inventory changed) |
| GET | `/programs/{id}` | bearer | A specific program |

### Inventory API (Increment 2)
| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/inventory/capture` | bearer | Upload image(s) + consent → draft inventory (recognized) |
| PUT | `/inventory/{id}/confirm` | bearer | Submit corrected items → confirmed canonical version |
| GET | `/inventory` | bearer | Current confirmed inventory |
| POST | `/inventory/edit` | bearer | Manual edit → new confirmed version (never mutates old) |

Set `VISION_PROVIDER=bedrock` and a valid `BEDROCK_MODEL_ID` to use real
recognition; the IAM role then also needs `bedrock:InvokeModel` and (if storing
images) `s3:PutObject`/`s3:DeleteObject` on your bucket.

## Layout
```
backend/   FastAPI + Postgres + SES
mobile/    Expo React Native app
```

## Run the backend
Requires Python 3.11+ and a Postgres database.

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then edit values

# create the database (once)
createdb weightprogram

uvicorn app.main:app --reload --port 8000
```

Tables are auto-created on startup for this increment (swap to Alembic before
production). Open http://localhost:8000/docs for the interactive API.

### Email in dev vs production
- `EMAIL_DEV_MODE=true` (default): OTP codes are **printed to the server log**
  instead of emailed — so you can test without SES. Look for `[DEV EMAIL] OTP for ...`.
- `EMAIL_DEV_MODE=false`: sends via SES. Two things to know:
  1. Verify your `SES_FROM_EMAIL` (or its domain) in the SES console first.
  2. **New SES accounts are in the sandbox**: you can only send to *verified*
     recipient addresses and are capped at 200/day. Request production access in
     the SES console to email arbitrary users. No code change needed when approved.
- AWS credentials are read from the standard chain (env, `~/.aws/credentials`, or
  the IAM role when deployed). Attach `iam-ses-policy.json` to that role. Never
  hardcode keys.

## Run the mobile app
Requires Node 18+ and the Expo tooling.

```bash
cd mobile
npm install
# set API_BASE_URL in src/config.ts to your backend (use your LAN IP for a
# physical device; localhost works for the iOS simulator)
npm start
```

## API (Increment 1)
| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/auth/request-otp` | – | Create-or-find user, email a code |
| POST | `/auth/verify-otp` | – | Verify code, return access + refresh tokens |
| POST | `/auth/refresh` | – | Rotate refresh token, return a new pair |
| POST | `/auth/logout` | – | Revoke this token, or `everywhere` |
| GET | `/me` | bearer | Current user + habits (+ `deletion_requested_at` / `deletion_scheduled_for` while a deletion is pending) |
| POST | `/me/deletion` | bearer | Request account deletion — starts the 30-day grace window, revokes every session |
| DELETE | `/me/deletion` | bearer | Cancel a pending deletion, keep the account |
| GET | `/habits/defaults` | – | Pre-fill values for onboarding |
| PUT | `/habits` | bearer | Save days/week, session length, experience |
| GET | `/health` | – | Liveness |

## Security & privacy notes (spec F4 / F8)
- No passwords stored — login is passwordless OTP.
- **No medication stored.** Only a non-identifying `training_mode` flag.
- Access tokens are short-lived JWTs carrying a per-user `token_epoch`; bumping the
  epoch (logout-everywhere / account disable) invalidates all outstanding tokens.
- Refresh tokens are stored only as SHA-256 hashes, rotated on use, with reuse
  detection that revokes the whole token family.
- Mobile keeps tokens in the OS secure enclave (`expo-secure-store`), never in
  AsyncStorage.
- **In-app account deletion** (App Store 5.1.1(v)) lives in `backend/app/deletion.py`:
  `POST /me/deletion` stamps `users.deletion_requested_at` and revokes every session,
  the account stays recoverable for `GRACE_PERIOD_DAYS` (30, sized to GDPR Art. 12(3)),
  and a 6-hourly in-process sweep then deletes consented S3 images, folds the user's
  sets into the anonymous `exercise_stat_bins` histogram and hard-deletes the `users`
  row (every user-owned table cascades on `user_id`). Retention is counters, not
  stripped rows — see the `ExerciseStatBin` docstring. Unit tests:
  `cd backend && python3 -m tests.test_deletion`. **Built, pending backend deploy.**

# WeightProgram — Project State (handoff)

One-page onboarding for a new thread. Read this + `OPERATIONS_RUNBOOK.md` before working.
Last updated: 2026-08-19.

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
  Reviewer login bypass: `reviewer@glpsteel.com`; the code lives ONLY in the ECS task-def env var
  `REVIEW_CODE` and is rotated per submission — never written down here. See runbook §D7.
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
  Protein profile (auto target from bodyweight — originally 1 g/kg, now a
  configurable multiplier defaulting to 1.52 g/kg; see the 2026-07-13 entry —
  plus bodyweight logging), "Scan My Kitchen"
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
  `api.ts`. Next: simulator pass (runbook §B, both themes).
  **Beginner-mode wiring (2026-08-05 follow-up):** the "Add an exercise" choice
  was ALSO added to CouchProgramScreen's Manage card (a beginner in Couch mode
  never sees the full ProgramScreen, so the earlier "full screen only" wiring hid
  the feature for beginners). `couch.py` now treats `added_by_user` exercises as
  outside the ramp: they are ALWAYS revealed regardless of `unlocked`, and are
  excluded from `program_full`'s longest-day count so adding one never bumps the
  weekly target. `_newest_exercise_name` reads ramp-only exercises so coach copy
  is unaffected. New `tests/test_couch.py::test_user_added_exercise_always_shown_
  and_not_in_ramp`; existing couch/custom_exercise tests still pass.
  **Classifier caching + filter fix (2026-08-06 follow-up):** (a) the muscle
  filter in the library picker now keys off the MAIN mover (`primary[0]`) so
  e.g. "biceps" shows only curls, not back+biceps rows (JS-only, AddExerciseScreen).
  Note: `glutes` is no longer a filter chip — the library has no glute-PRIMARY
  movement (glutes are only ever secondary on squats/RDLs); add a hip-thrust/glute-
  bridge to `exercises.py` if a glutes filter is wanted. (b) The AI classifier is
  now CACHED: new shared `exercise_classify_cache` table (mirrors
  `nutrition_parse_cache`, auto-created on boot) keyed by normalized phrase, so a
  given phrase hits Bedrock at most once ever across all users; only real Bedrock
  answers are written (the dev stub is never cached, so flipping to Bedrock can't
  be shadowed by a stale stub). Library matches never touch the model. Cache hits
  come back with `source:"cache"`. The static library list is also cached
  client-side (module-level promise in `api.ts`) so the picker fetches it once per
  session. New round-trip test in `tests/test_custom_exercise.py`.

- **Usability overhaul + onboarding name (2026-08-05, simulator pass done both
  themes; mobile `tsc --noEmit` clean + backend `py_compile` clean; mobile NOT yet
  in a shipped TestFlight build, backend NOT yet deployed):** a read-only UX review
  turned into a batch of fixes. All mobile changes are JS-only (no new deps) EXCEPT
  the name field, which is the only backend change this round.
  - **Bottom tab bar** replaces the hub-and-spoke nav: new `mobile/src/ui/TabBar.tsx`
    (+ `HomeGlyph` in `Glyphs.tsx`), rendered by `App.tsx` on the four top-level
    screens only (Home/Program/Progress/Nutrition); focused flows (capture, workout,
    sub-screens) hide it. Those four screens now pass `showHome={false}` (tab bar
    supersedes the old Home pill + "Back to home" buttons).
  - **Standardized back control:** `ScreenBackground` gained `onBack`/`backLabel`,
    rendered as a top-left header ROW (not an absolute overlay, so it never covers a
    title). Adopted across every sub-screen (Capture, ConfirmInventory — which had no
    back at all before, Customization, AddExercise, ExerciseTrends, History, and the
    nutrition sub-screens Recipes/ProteinTracker/ProteinBoosters/VoiceLog); their
    ad-hoc bottom "Back"/"Cancel" buttons and inline top-left text links were removed.
  - **Confirmations (`Alert`)** on destructive/expensive actions: ProgramScreen
    regenerate / split-change / restart-as-beginner; CouchProgramScreen regenerate /
    graduate / restart; Home sign-out; ConfirmInventory item remove; a new
    "Cancel workout" during logging (WorkoutScreen) that warns before discarding sets.
  - **Split vs. day tabs:** the 3/4/5-day chips moved out of the main ProgramScreen
    flow into the "Manage program" card (behind the regenerate confirm) so they can't
    be mistaken for the Day tabs.
  - **Auth/onboarding:** OTP field is autofillable (`textContentType="oneTimeCode"` +
    `autoComplete`), auto-submits at 6 digits, resend has a 30s cooldown + "code sent"
    feedback; Email/OTP/Onboarding wrapped in `KeyboardAvoidingView`.
  - **Copy/jargon:** new `mobile/src/labels.ts` (`prettyExperience` — Program subtitle
    no longer shows the raw `conservative`/`beginner` enum; `RIR_HINT` gloss on the
    logger). New `mobile/src/errors.ts` `friendlyError()` (network/5xx → actionable
    copy) adopted across the screens touched.
  - **Equipment type editing:** the one-at-a-time `‹ ›` cycler in ConfirmInventory is
    now a tap-to-open modal picker.
  - **Accessibility:** `theme.ts` `textTertiary` darkened (light) / lightened (dark)
    for WCAG AA on captions; text-link controls bumped to 44px min targets.
  - **Onboarding name (only backend change):** optional first-name field on
    `OnboardingScreen` → greeting personalization (`HomeScreen` uses `me.name`, falls
    back to the email-derived guess). Backend: new **nullable `users.name` column**
    added by `_COLUMN_BOOTSTRAP` on boot (no manual DB step), plus `HabitsIn.name`,
    `MeOut.name`, and `/me` + `PUT /habits` wiring (`routers/onboarding.py`). Mobile:
    `Me.name` + `HabitsInput` in `api.ts`. **Safe to ship the app before the backend
    deploy** — schemas don't forbid extra fields, so the current prod API ignores the
    `name` the app sends and `/me` omits it, so the greeting cleanly falls back.
  - Next: bump `ios.buildNumber` → TestFlight (runbook §C); deploy backend (runbook §A)
    so the name actually persists.

- **App Store hardening (2026-08-17/18, backend + mobile built clean, NOT yet
  deployed/shipped):** first two blockers from `APPSTORE_READINESS.md` closed.
  - **Reviewer bypass hardened (S1/HB-2).** `config.py` gained
    `Settings.review_bypass_state()`: the bypass now needs `REVIEW_EMAIL` +
    `REVIEW_CODE` (≥24 chars) + `REVIEW_BYPASS_UNTIL` (hard ISO expiry) and is
    inert past that date even if the vars remain set. `routers/auth.py` uses
    `secrets.compare_digest`, throttles 5 misses / 15 min, and logs every
    accept/miss; `main.py` announces the armed/inert state at boot. **The old
    6-digit code fails the length guard, so the backdoor is closed by this
    deploy alone** — rotating `REVIEW_CODE` on ECS is still required before
    review. Plaintext code scrubbed from this file and the runbook (still in git
    history — see `APPSTORE_READINESS.md` §2a).
  - **Account deletion (HB-1, guideline 5.1.1(v)).** New `app/deletion.py`:
    `POST /me/deletion` starts a **30-day grace window** (aligned to GDPR Art.
    12(3), not to any Apple maximum — Apple publishes none) and revokes every
    session; `DELETE /me/deletion` cancels; `/me` now carries
    `deletion_requested_at` + `deletion_scheduled_for`. A 6-hourly in-process
    sweep purges due accounts: deletes consented S3 images, folds the user's
    sets into the new anonymous `exercise_stat_bins` histogram, then one
    `DELETE FROM users` — all 13 user-owned tables already declare
    `ondelete="CASCADE"`, verified against the emitted DDL, and `set_logs`
    cascades via `workout_sessions`. `otp_codes` keys off email, not a FK, so it
    is deleted explicitly. **Retention is a counter, not stripped rows** — see
    the `ExerciseStatBin` docstring for why preserved rows would still be
    per-person data. Two new `EmailSender` methods send the scheduled and
    completed notices. Schema: nullable `users.deletion_requested_at` via
    `_COLUMN_BOOTSTRAP` + one new table (both automatic on boot).
    Mobile (JS-only, no new deps): `AccountApi` in `api.ts`, two-step confirm on
    a new Home menu item, new `PendingDeletionScreen` gating the whole app while
    deletion is pending (checked in `App.tsx` before the onboarding gate),
    `clearSession` added to `AuthContext`. Privacy + support pages in `main.py`
    rewritten for the deletion flow. Tests: `python3 -m tests.test_deletion`
    (13 pass). `tsc --noEmit` clean; backend `py_compile` clean; existing couch/
    gamification/custom_exercise suites still pass.
  - **Permission purpose strings (HB-4, guideline 5.1.1(i)).** The camera and
    photo-library strings claimed equipment use only, but `KitchenScanScreen`
    uses the same two permissions for kitchen/fridge photos. Both rewritten in
    `ios/WeightProgram/Info.plist` to name both uses and state that kitchen
    photos are never stored (verified against `routers/nutrition.py` —
    `scan_pantry` persists nothing), and mirrored into `app.json`'s
    `expo-image-picker` block so a future `prebuild` can't revert them
    (runbook gotcha #12). **Native change — needs a new app build to reach the
    binary.**
  - **Protein Boosters hidden for 1.0 (HB-3, guideline 2.1).** All ten
    `_MARKETPLACE` URLs are still `example.com` placeholders, and the screen
    told the user so ("Affiliate partnerships aren't live yet") — two taps from
    the Nutrition tab, which is a straight App Completeness rejection. The
    entrance NavRow in `NutritionHomeScreen.tsx` is commented out with
    re-enable instructions; the App.tsx route, `ProteinBoostersScreen` and
    `GET /nutrition/marketplace` are all untouched, so switching it back on is
    one JS-only edit. Also moved the FTC affiliate disclosure ABOVE the product
    list (it rendered below all ten cards, which fails the clear-and-conspicuous
    proximity/placement test). Affiliate-program options for the 1.1 re-enable —
    including the trap that **Amazon Associates terminates the agreement if a
    tagged link ships from an unapproved app** — are written up in
    `APPSTORE_READINESS.md` §2b.
  - **Medical disclaimers (HB-5, guideline 1.4.1).** The app frames itself
    around prescription GLP-1 use, derives a numeric protein target from
    bodyweight, prescribes training loads to beginners, and generates meals
    under allergy constraints `neutron_recipes.py` itself calls "a life-safety
    allergy" — and carried NO disclaimer anywhere (the only two in the repo
    were on the marketing site). Added persistent, non-dismissible notices at
    the three points where the app actually instructs: `OnboardingScreen`
    (training), `NutritionSetupScreen` (protein target + GLP-1 framing), and
    the generated-recipe view in `RecipesScreen` (AI content + allergens,
    placed ABOVE the "I made this"/"Save" actions so it's read before the food
    is eaten). Matching Health & safety sections added to `/privacy` and
    `/support` in `main.py`. Also softened two clinical-sounding claims: the
    uncited "research supports 1 g/kg as the bare minimum" and the preset
    labelled "GLP-1 minimum" — the app can't substantiate a medical threshold.
    All wording owner-approved. JS-only on mobile; `main.py` change ships with
    the next backend deploy.
  - **Website fabricated social proof removed (HB-6, guideline 2.3).** Deleted
    the social-proof bar (invented "4.9 App Store rating" for an unreleased app
    + three "As seen in" outlets that never covered us) and the entire
    transformations section (three fabricated testimonials with invented named
    people, invented weight-loss/lift numbers, and quotes naming tirzepatide and
    semaglutide). Deleted rather than commented out — HTML comments ship to the
    browser, so commented-out fake reviews are still visible in view-source.
    Recoverable from git history; the conditions for restoring them are written
    into `website/WEBSITE_BRIEF.md`. Neither section had an `id` and no nav link
    targeted them, so removal was clean (512 → 473 lines, HTML still
    well-formed). Then closed the second half: the four dead `href="#"` store
    buttons are gone — the two App Store buttons became non-clickable "Coming
    soon to the App Store" badges (`<span>`, not `<a>`, since an App Store URL
    404s until the app is actually released), and both Google Play buttons were
    REMOVED because Android isn't shipping for 1.0 (promising a download on an
    unshipped platform is the same 2.3 accuracy problem as the fake rating).
    Site now has zero dead links and zero unverifiable claims (512 → 457 lines,
    all internal anchors resolve). **Launch-day step:** convert the badges back
    to real links — exact markup in `website/WEBSITE_BRIEF.md` §"Switching the
    store buttons on". Website deploys via runbook §F (S3 + CloudFront
    invalidation), not the backend deploy.
  - **Privacy policy full data inventory (HB-7, guidelines 5.1.1/5.1.2).** The
    old policy listed 5 items and predated the entire nutrition module. Rewrote
    `_PRIVACY_HTML` in `main.py` to disclose everything the code actually
    handles: account fields (incl. the optional phone on `EmailEntryScreen`),
    workout logs + the 1–5 readiness rating, body-weight history, protein
    settings, dietary restrictions/allergies (flagged as sensitive), food and
    protein logs, pantry items and saved recipes, equipment photos (opt-in
    storage) vs kitchen photos (never stored — different retention, now stated
    as such), on-device voice transcription vs the text phrases that DO leave
    the device, and typed exercise descriptions. New sections: how AI processing
    works (Bedrock in our own account; the shared phrase cache holds no account
    link), what we never collect (medication, location, contacts, health app,
    ad identifiers), data-subject rights, US processing, and policy changes.
    **Audit correction:** an earlier draft of `APPSTORE_READINESS.md` claimed no
    screen collects a phone number — `EmailEntryScreen.tsx:55-59` does. The
    privacy nutrition label in §1.6 was wrong as a result and is now fixed;
    declare Contact Info → Phone as collected.
  - **All 7 hard blockers from the audit are now closed in code.** What's left
    before submission is operational, not code — see `APPSTORE_READINESS.md`.

## API surface (all under https://api.glpsteel.com)
`/auth/*` (request-otp, verify-otp, refresh, logout) · `/me` ·
`/me/deletion` (POST request, DELETE cancel) · `/habits*` ·
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
7. ~~`TUTORIAL.md` (§3.4, FAQ) and `website/index.html` still tell users to email support to
   delete their account.~~ **Done 2026-08-19.** `TUTORIAL.md` now documents "Home → menu →
   Delete account" (new §4.7 + FAQ) marked **(next build)**, and keeps the email route as the
   path that works on the *shipped* build (`ios.buildNumber` still 2). `website/index.html`
   carries no account-deletion copy at all, so nothing to change there. **Drop the
   "(next build)" tags from `TUTORIAL.md` once the deletion backend is deployed and the app
   build ships.**
8. `TUTORIAL.md` header now warns that the tab bar, beginner mode, program customization,
   in-app safety notices and account deletion are not in the build on users' devices. That
   warning must be removed with the same release as item 7.
9. `README.md` documents Increments 1–4 plus account deletion, but has no section for
   Neutron (Increment 5), Couch-to-Weights, gamification or the analytics API. Pre-existing
   gap, not introduced by the 2026-08-19 pass — `PROJECT_STATE.md` §"API surface" is the
   accurate list in the meantime.

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

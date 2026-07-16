# Neutron — Nutrition Module Spec (Increment 5)

Protein tracking, kitchen scanning, and recipe generation for GLP-1 users who
must hit **>= 1 g protein / kg bodyweight / day** to preserve muscle in a
deficit. Built 2026-07-07. Companion to `BUILD_SPEC.md`; deploy per
`OPERATIONS_RUNBOOK.md` (new tables are created by `init_models` on boot).

## N1. Feature spec & user flows

**Entry.** Home screen "Nutrition" card (replaces the SOON teaser). First tap
fetches `/nutrition/profile`; if not onboarded the user lands on setup
(current weight kg, optional goal weight, diet pattern, restrictions). Target
defaults to auto = 1 g/kg and recalculates on every weight log; a custom
target pins it (`target_mode: custom`).

**Neutron home.** Progress ring (today g / target g, color shifts
accent→teal→green as it fills), motivational message, streak + level badges,
quick-log (Stepper + one tap), collapsible weight check-in, and four doors:
Scan My Kitchen, Recipes & Meal Builder, Protein Tracker, Protein Boosters.

**Scan My Kitchen flow.**
1. Up to 4 photos (camera or library), HEIC→JPEG re-encode at 1600 px (same
   as equipment capture — Bedrock returns nothing on oversized payloads).
2. `POST /nutrition/pantry/scan` (multipart) → vision model returns a draft
   food list. **Photos are never persisted** — process-and-discard.
3. Review screen: edit names/quantities, re-bucket pantry/fridge/freezer,
   remove, add missed items. High-protein and low-confidence items are badged.
4. "Save & Generate High-Protein Recipes" (replaces pantry via
   `PUT /nutrition/pantry`, jumps to Recipes with auto-generate) or "Just save
   my pantry".

**Recipes & Meal Builder.** Filters: High-Protein (>=30 g/serving, default
on; off lowers the floor to 15 g), "Use my kitchen first", diet override chips
(vegan/vegetarian/pescatarian). Profile restrictions are ALWAYS applied and
shown read-only ("Always applied: …"). Generate → 3-5 recipe cards (protein,
kcal, total minutes, difficulty, % of daily target, tags). Detail view: macro
badges, "% of your daily protein" callout, pantry-tagged ingredients, numbered
steps, **Make it Vegan / Vegetarian** (regenerates that one recipe via
`/nutrition/recipes/adapt`, protein within 20% of original), "I made this —
log N g" (one-tap ProteinLog), Save recipe. **Surprise Me** →
`/nutrition/recipes/surprise` returns a full day (3 meals + snacks, each
~25-40 g so no single meal overwhelms a GLP-1 appetite) summing to >= target.

**Tracker.** Weekly bars (7 days vs target line), 4-week trend (avg g/day per
calendar week; current week averaged over elapsed days only), daily/weekly
streak + best streak, level card with progress to next level, muscle score,
badge cabinet (earned + locked), recent entries.

**Boosters.** Curated marketplace, category chips, protein/serving + price +
"Best for GLP-1 users" tags, placeholder affiliate links (tapping one shows an
honest "partnerships not live yet" alert), commission disclosure footer.

## N2. Data model (in `backend/app/models.py`)

| Table | Key fields | Notes |
|---|---|---|
| `nutrition_profiles` | user_id PK, current/goal weight kg, protein_target_g, target_mode auto\|custom, diet_pattern, restrictions JSON, onboarded | restrictions are hard constraints |
| `weight_logs` | weight_kg, logged_at | closes the deferred bodyweight-analytics gap |
| `pantry_items` | name, quantity (freeform), category, protein_per_100g, protein_density, source scan\|manual, confidence | flat, replace-in-place (unlike versioned equipment — pantries churn daily) |
| `saved_recipes` | title, protein_g, calories, payload JSON, source | payload = full recipe, renders offline |
| `protein_logs` | grams, calories, label, source recipe\|quick_add\|booster, logged_at | single source of truth for all gamification |
| `nutrition_badges` | badge_key, awarded_at | awards are permanent |
| `nutrition_parse_cache` | phrase_norm (unique), payload JSON, model_id | voice-log AI cache, shared across users (no user_id) |

## N3. API surface (`backend/app/routers/nutrition.py`)

`GET/PUT /nutrition/profile` · `POST/GET /nutrition/weight` ·
`POST /nutrition/pantry/scan` (multipart) · `GET/PUT /nutrition/pantry` ·
`POST /nutrition/recipes/{generate,adapt,surprise}` ·
`GET/POST/DELETE /nutrition/recipes/saved` ·
`POST/GET/DELETE /nutrition/log` · `GET /nutrition/summary` ·
`GET /nutrition/marketplace` · `POST /nutrition/parse` (voice-log AI
fallback; log source `voice` added).
Day bucketing uses `tz` minutes east of UTC, identical to `/analytics`.

## N4. Vision prompt (pantry scan, `neutron_vision.py`)

Bedrock Converse, temperature 0, **forced tool call** `submit_pantry` (same
pattern as `submit_inventory`). Prompt (abridged): *"You are cataloguing food
from photos of a home pantry, fridge, or freezer for a nutrition app whose
users must hit a daily protein target. Identify every distinct food you can
actually see… short generic name… rough quantity estimate… approximate
protein_per_100g (null if unsure)… protein_density bucket high >=15 g/100g /
medium 5-15 / low <5. Set LOW confidence for anything partially hidden or
ambiguous — do not guess items you cannot see. Ignore non-food objects."*
Parser clamps confidence, coerces bad enums, drops nameless rows. Stub scanner
(`vision_provider=stub`) returns a deterministic 7-item kitchen for dev.

## N5. Recipe prompt (`neutron_recipes.py`)

Temperature 0.7, forced tool `submit_recipes` / `submit_day_plan`. Persona:
*"You are the recipe engine of a fitness app for people on GLP-1 medications
(reduced appetite, calorie deficit) who must hit a daily protein minimum to
preserve muscle. Small appetites mean every bite has to count: favor
protein-dense recipes with modest volume, simple prep… macros must be
realistic — computed from actual ingredient quantities, per serving."* Then:
pantry list (mark `from_pantry=true`), diet-pattern rule, and each restriction
as a HARD constraint — `no_red_meat` is spelled out as Alpha-Gal life-safety
(no mammalian meat/by-products/gelatin/lard), customs render as "HARD
allergy/exclusion: no X". Veganize prompt requires protein within 20% of the
original. Day-plan prompt requires >= target total with 25-40 g meals.

## N6. Gamification (`neutron_gamification.py`, pure functions, unit-tested)

- **Hit day** = >= 90% of target (soft cliff — a 3 g miss shouldn't kill a
  streak for an appetite-suppressed user).
- **Daily streak**: consecutive hit days (today-in-progress doesn't break it).
  **Weekly streak**: consecutive Mon-Sun weeks with >= 5 hit days.
- **Level** = lifetime hit days, banded: Rookie 0 → Contender 5 → Builder 15
  → Protector 30 → Guardian 60 → Sentinel 100 → Muscle Machine 180 → Legend 365.
- **Muscle score** (0-100): mean per-day attainment over trailing 28 days,
  capped at 1.0/day so binges can't buy back skipped days.
- **Badges** (permanent): First Rep (first log) · 30 g Club (single log >= 30 g)
  · Target Down (first hit) · Muscle Guardian (7-day streak) · Iron Month
  (30-day streak) · Pantry Alchemist (first recipes from a scanned pantry —
  event-awarded at the generate endpoint) · Alpha-Gal Champion (7-day streak
  with no_red_meat active) · Plant Powered (7-day streak on vegan/vegetarian)
  · Surprise Seeker (first day plan — event-awarded) · Trend Tracker (weight
  logged 4 weeks running). New awards are returned by `/nutrition/log` and
  `/nutrition/recipes/generate` so the client can celebrate in the moment.

## N7. Privacy & positioning

Scan photos: encrypted in transit, recognition-only, never stored (stated on
both the scan screen and Neutron home). No medication data — consistent with
the app-wide F8 rule. Copy is supportive and science-anchored ("1 g/kg to
preserve lean mass"), never shaming; motivational lines rotate by ratio bands.

## N8. Voice Log (added 2026-07-12) — cache-first, AI-last protein logging

**Flow.** Neutron home "Voice Log" door → `VoiceLogScreen`. Tap-to-speak
(`expo-speech-recognition`; iOS SFSpeechRecognizer with
`requiresOnDeviceRecognition` when the device supports it — audio never
leaves the phone), live transcript, or a typed fallback input. The
transcript is parsed entirely on device, shown as editable item cards
(name, portion, protein Stepper, remove), then each confirmed item is
logged via the existing `POST /nutrition/log` with `source: "voice"` — so
streaks/badges/levels/summary all work unchanged.

**On-device pipeline** (`mobile/src/nutrition/`, pure TS, node-unit-tested):
1. `parser.ts` — quantity/unit grammar (numbers, number-words, g/kg/oz/lb/
   cups/tbsp/scoops/slices/counts), connector segmentation ("and", "with",
   commas), filler stripping, protected compounds ("mac and cheese").
2. Resolution tiers, in order: **alias cache** (user corrections + past AI
   answers, `voiceStore.ts`, expo-sqlite) → **exact** name/alias hit →
   **fuzzy** (char-bigram Dice + token containment, threshold 0.62) against
   `foods.ts` (~350 curated foods + ~700 aliases, approx protein/100 g +
   default servings) → **Naive Bayes category classifier** (`matcher.ts`,
   trained from the bundled data at first use, no ML runtime) for a usable
   offline estimate of unknown foods → only then **AI**.
3. AI tier: `POST /nutrition/parse` (batched unresolved phrases). Server
   checks `nutrition_parse_cache` (normalized phrase → estimate, shared
   across users) and calls Bedrock (forced tool `submit_food_items`, temp 0,
   maxTokens ≥4096, `neutron_parse.py`, stub via `VISION_PROVIDER=stub`)
   only on a miss; the device writes the answer to its alias cache — a
   phrase hits the model at most once, ever, for anyone.

**Corrections.** Any edit on the review card persists to the alias cache as
`source: correction` (beats AI rows, never overwritten by them) keyed by the
normalized phrase — `normalize()` in `matcher.ts` MUST stay in sync with
`normalize_phrase()` in `neutron_parse.py`.

**Offline.** Everything above except the AI tier works with no network;
low-confidence items get an "approx — tap to fix" badge. Failed log POSTs go
to the sqlite `log_queue` and flush next time the screen opens.

## N9. Ship checklist

1. Backend: rsync to `~/wp-backend-build`, docker build
   `--provenance=false --sbom=false`, deploy, re-point the ALB listener rule,
   verify `/health` and `GET /nutrition/marketplace`.
2. Tables auto-create on boot (`init_models`). Alembic still pending (known item #5).
3. Mobile: Voice Log adds TWO new NATIVE deps (`expo-speech-recognition`,
   `expo-sqlite`) + an `app.json` config plugin (mic + speech-recognition
   permission strings) — `npm install`, then a FULL dev build
   (`npx expo run:ios`, not `expo start`) before the simulator pass.
   Bump `ios.buildNumber`, EAS build + submit.
4. Verify Bedrock model access covers text-only Converse (same model id).
5. Before public launch: swap marketplace placeholder URLs for real affiliate
   links and re-check the disclosure copy.

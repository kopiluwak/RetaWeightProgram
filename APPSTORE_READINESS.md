# App Store Readiness Audit — Phase 1 (read-only)

Audit date: **2026-08-12**. Scope: **Apple App Store public submission only**. Android / Google Play
explicitly out of scope this session.

Method: every claim below is traced to a `file:line` in the repo as it exists on disk today. Where a
fact lives outside the repo (App Store Connect state, ECS env vars, RDS parameter group, uploaded
screenshots) it is marked `[unverified — confirm in App Store Connect]` or
`[unverified — confirm in AWS console]` rather than asserted.

Apple guideline numbers cited here were verified against Apple's published guidance
(see Sources at the bottom). Where a guideline is commonly invoked but does **not** actually apply to
this app, that is stated plainly rather than padded into the risk list.

**Nothing has been changed.** This document is the Phase 1 deliverable only.

---

## 0. Headline

| | count |
|---|---|
| HARD BLOCKERS — originally found | **7** |
| HARD BLOCKERS — **fixed in code** (HB-1 account deletion, HB-2 reviewer backdoor) | **2** |
| HARD BLOCKERS — **remaining** (HB-3, HB-4, HB-5, HB-6, HB-7) | **5** |
| SHOULD-FIX (technical debt / release hygiene, not a rejection cause) | **11** |
| Verified-clean areas (no action) | 4 |

**Progress log**
- 2026-08-17 — HB-2 reviewer backdoor hardened (time-boxed, length-checked, throttled, logged).
- 2026-08-18 — HB-1 in-app account deletion shipped (30-day grace, anonymising fold, purge sweep).
  Privacy and support pages rewritten for the deletion flow; the rest of HB-7 is still open.

The single most surprising result: **`ios/WeightProgram/Info.plist` is currently correct.** All five
permission strings the code actually needs are present. The ITMS-90683 class of failure is closed —
but see HB-4, because the camera/photo purpose strings describe only half of what those permissions
are used for, and see SF-9, because that file is **not under version control**.

The two things most likely to get this rejected are **no in-app account deletion** (HB-1) and the
**Protein Boosters screen shipping with dead placeholder links** (HB-3).

---

## 1. Gap table

### 1.1 Security

| # | Item | Current state (verified) | What must change |
|---|---|---|---|
| S1 | **Reviewer login backdoor** — ✅ **FIXED IN CODE 2026-08-17** | *Was:* `config.py` declared only `review_email` / `review_code`; `routers/auth.py` short-circuited `/auth/request-otp` and accepted a **fixed, non-expiring, non-rate-limited 6-digit** code on `/auth/verify-otp`, issuing a full token pair. The bypass skipped every control the real path has — no `OtpCode` row, no expiry check, no attempt counter, no hourly rate limit. The 6-digit code was also committed in plaintext in two markdown files in a GitHub-pushed repo. | *Now:* gated by `Settings.review_bypass_state()` (`config.py`) — hard ISO expiry, ≥24-char code required, constant-time compare, 5-miss/15-min throttle, WARNING log on every accept/miss and on boot. Plaintext code removed from `PROJECT_STATE.md` and `OPERATIONS_RUNBOOK.md`. **Remaining manual steps: rotate `REVIEW_CODE`, set `REVIEW_BYPASS_UNTIL` on the ECS task def, and decide on the git-history rewrite.** See HB-2. |
| S2 | **DB TLS disabled** | `backend/app/database.py:12` — `create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)`. No `connect_args`, no `ssl=` context. `OPERATIONS_RUNBOOK.md:180-181` records that the RDS parameter group was set to `rds.force_ssl=0` specifically so asyncpg could connect without TLS. `[unverified — confirm in AWS console]` that the parameter is still 0. | Postgres traffic between ECS and RDS is plaintext (in-VPC, but plaintext). Add an `ssl.SSLContext` with the RDS CA bundle to `create_async_engine`, then revert `rds.force_ssl` to 1. |
| S3 | **JWT secret has a shipping default** | `backend/app/config.py:30` — `jwt_secret: str = "CHANGE-ME-IN-ENV"`. There is no startup guard: `backend/app/main.py:22-26` `lifespan` only calls `init_models()`. If `JWT_SECRET` is ever absent from the task definition, every access token is signed with a string published in this repo and forgeable by anyone. | Add a fail-fast check in `lifespan` (or a validator on `Settings`) that refuses to boot in `environment == "production"` with the default secret. `[unverified — confirm in AWS console]` that `JWT_SECRET` is actually set on the ECS task def. |
| S4 | **Diagnostic `_log.warning` lines** | Four sites, not one: `backend/app/recognition.py:236-239`, `backend/app/neutron_vision.py:206`, `backend/app/neutron_parse.py:204`, `backend/app/custom_exercise.py:393`. | **Assessment: these are not a security or privacy defect.** Each logs only a count and the Bedrock `stopReason` — no user content, no PII, no secrets. `PROJECT_STATE.md:279` and `OPERATIONS_RUNBOOK.md:265` call for removing the `recognition.py` one; `OPERATIONS_RUNBOOK.md:196-199` simultaneously instructs operators to *use* these lines to diagnose empty scans. Recommendation: **keep them and downgrade to `_log.info`**, and correct the runbook — deleting them removes the only signal for the single most common production failure mode. Flagged as SHOULD-FIX (SF-3), not a blocker. |
| S5 | **Dead file shipped in the image** | `backend/app/recognition.py.bak` (10,277 bytes, dated 2026-07-02) sits alongside the live module and is copied into the Docker image by the build in `OPERATIONS_RUNBOOK.md:32-37`. Not imported anywhere. | Delete. **Requires your approval per the stop conditions — not deleted.** |
| S6 | **Secrets hygiene** | `backend/.env` exists on disk but is correctly untracked (`.gitignore:2-3`; `git ls-files backend/.env` → empty). Its contents are the same key set as `backend/.env.example`. No AWS keys are hardcoded (`backend/.env.example` comment: credentials come from the IAM role). `backend/app/storage.py:35` and `recognition.py:212` build boto3 clients with no explicit credentials — correct. | No action. **Verified clean.** |

### 1.2 `ios/WeightProgram/Info.plist` — permission strings

Every permission-triggering API in the app was enumerated (full sweep of `mobile/src/**`,
`mobile/App.tsx`, `mobile/package.json`, `mobile/ios/Podfile.lock`), then diffed against the plist.

| Permission | Required by (file:line) | Plist key | Present? | Verdict |
|---|---|---|---|---|
| Camera | `mobile/src/screens/CaptureScreen.tsx:31,36` (`requestCameraPermissionsAsync`, `launchCameraAsync`); `mobile/src/screens/KitchenScanScreen.tsx:46,51` | `NSCameraUsageDescription` | ✅ `Info.plist:49-50` | Present, **but wording is incomplete → HB-4** |
| Photo library (read) | `mobile/src/screens/CaptureScreen.tsx:41`; `mobile/src/screens/KitchenScanScreen.tsx:55` (`launchImageLibraryAsync`) | `NSPhotoLibraryUsageDescription` | ✅ `Info.plist:55-56` | Present, **wording incomplete → HB-4** |
| Microphone | `mobile/src/screens/VoiceLogScreen.tsx:90` (`ExpoSpeechRecognitionModule.requestPermissionsAsync`); also linked unconditionally by the ExpoAudio pod (`mobile/ios/Podfile.lock:34,1895`), used for playback at `mobile/src/screens/WorkoutScreen.tsx:60,63` | `NSMicrophoneUsageDescription` | ✅ `Info.plist:53-54` | Correct |
| Speech recognition | `mobile/src/screens/VoiceLogScreen.tsx:15-17,62,90,98-104` | `NSSpeechRecognitionUsageDescription` | ✅ `Info.plist:57-58` | Correct — this is the string whose absence caused the ITMS-90683 rejection of Build 11 (`OPERATIONS_RUNBOOK.md:250-254`). Closed. |
| Face ID | Nothing in JS. Injected by the `expo-secure-store` config plugin because ExpoSecureStore links `LocalAuthentication`. `mobile/src/tokenStore.ts:4,11-26` never passes `requireAuthentication`. | `NSFaceIDUsageDescription` | ✅ `Info.plist:51-52` | Keep (the framework is linked). String is unedited boilerplate — `Allow $(PRODUCT_NAME) to access your Face ID biometric data.` → SF-8 |
| Photo library (**add**) | **Nothing.** `mobile/src/ui/PrShareCard.tsx:35` writes via `captureRef(..., { result: "tmpfile" })` and hands the URI to RN's `Share.share` (`PrShareCard.tsx:37-43`). No `MediaLibrary`, no `CameraRoll` — `expo-media-library` is not a dependency. | `NSPhotoLibraryAddUsageDescription` | ❌ absent | **Correctly absent.** Saving from the system share sheet is the share extension's permission, not ours. |
| Haptics | `mobile/src/screens/WorkoutScreen.tsx:19,74`; `NutritionHomeScreen.tsx:6,88`; `RecipesScreen.tsx:7,58`; `mobile/src/ui/Stepper.tsx:3,46`; `mobile/src/ui/OverflowMenu.tsx:3,37,84` | *(none — iOS requires no usage string for haptics)* | n/a | No action |
| Location / Contacts / Calendar / HealthKit / Motion / Bluetooth / Tracking (ATT) / Notifications | **Zero references anywhere.** No `expo-location`, `expo-notifications`, `expo-sensors`, `expo-tracking-transparency`, HealthKit entitlement, or corresponding pods. | — | ❌ absent | **Correctly absent.** No ATT prompt required; nutrition label "Tracking = No" is defensible. |

**Result: no missing `NS*UsageDescription`.** The ITMS-90683 risk class is closed. Two follow-ons:
HB-4 (purpose-string accuracy) and SF-9 (the file is untracked in git).

Config-plugin note confirmed: `mobile/app.json` plugins (`expo-image-picker` at the plugins array,
`expo-speech-recognition` likewise) currently agree **verbatim** with the plist, so nothing has
drifted — but per `OPERATIONS_RUNBOOK.md:247-258` those entries do not reach the binary. The plist is
the source of truth.

### 1.3 App Store Connect metadata

All items in this section are `[unverified — confirm in App Store Connect]` as to their *current*
uploaded state; the "code state" column reflects what the repo can supply.

| Item | Code state | Gap |
|---|---|---|
| **Privacy policy URL** | Served at `https://api.glpsteel.com/privacy` — `backend/app/main.py:81-84`, HTML at `main.py:46-65`. | Content is **materially incomplete** — see §1.4. Also: hosting the legal policy on the API host means a backend outage takes the App Store's required privacy URL down with it. Consider serving it from the CloudFront site (`OPERATIONS_RUNBOOK.md:281-299`) instead. |
| **Support URL** | Served at `https://api.glpsteel.com/support` — `backend/app/main.py:87-90`, HTML at `main.py:67-78`. | Same hosting concern. `main.py:77` tells users to email for deletion — that text must change once HB-1 lands. |
| **Marketing URL** | `https://glpsteel.com` — `website/index.html`. | **Contains fabricated social proof and dead links → HB-6.** |
| **Privacy nutrition labels** | Not derivable from code; must be answered by hand. | Full mapping supplied in §1.6. Note the label must cover bodyweight, food logs and voice-derived food text — none of which the current privacy policy mentions. |
| **Age rating** | Not in repo. | The GLP-1 framing (`mobile/src/screens/NutritionSetupScreen.tsx:24,123`) means the "Medical or Treatment Information" question should be answered honestly rather than left at None. Draft answers go in Phase 3. |
| **Account deletion** | **No endpoint, no UI.** → HB-1. | |
| **App name / bundle identity** | `mobile/app.json` → `name: "WeightProgram"`, `slug: "weightprogram"`, `bundleIdentifier: "com.weightprogram.app"`. `Info.plist:9-10` `CFBundleDisplayName = WeightProgram`. Marketing brand is **GLP Steel** (`website/index.html:13,15`). | Product decision required: ship as "WeightProgram" (matches binary, mismatches all marketing) or rename the App Store listing to "GLP Steel". The bundle ID cannot change. → SF-10 |
| **Version string** | `Info.plist:21-22` `CFBundleShortVersionString = 0.1.0`; `mobile/app.json` `version: "0.1.0"`. | Legal, but a public 1.0 launch labelled 0.1.0 reads as beta. Recommend 1.0.0. → SF-6 |
| **Build number** | `Info.plist:34-35` `CFBundleVersion = 2`; `mobile/app.json` `ios.buildNumber = "2"`. | **These are both ignored for production builds.** `mobile/eas.json:4` sets `appVersionSource: "remote"` and `eas.json:15` sets `autoIncrement: true`, so EAS manages the build number server-side. The runbook instruction "bump `ios.buildNumber` in app.json first" (`OPERATIONS_RUNBOOK.md:122,140`) is a no-op under this config. → SF-7 |
| **Encryption declaration** | `Info.plist:36-37` `ITSAppUsesNonExemptEncryption = false`. | Correct — the app uses only HTTPS/OS crypto. Avoids the per-build compliance prompt. **Verified clean.** |

### 1.4 Privacy policy vs. what the app actually collects

Current policy text: `backend/app/main.py:46-65`. Data the code actually handles:

| Data actually collected | Evidence | In the policy? |
|---|---|---|
| Email address | `backend/app/models.py:31-34` (`users`), `routers/auth.py:82-88` | ✅ `main.py:53` |
| Generated user ID | `models.py:31-34` | ✅ `main.py:57` |
| Equipment photos (opt-in storage to S3) | `routers/inventory.py:107,171-178`; `backend/app/storage.py:37-46` | ✅ `main.py:55` |
| Equipment inventory / programs / workout logs | `models.py:139-268` | ✅ `main.py:56` |
| **Readiness / energy self-rating** | `mobile/src/screens/WorkoutScreen.tsx:26,49,95,100,178`; `routers/workouts.py:72` | ❌ **missing** |
| **Bodyweight + weight history** | `models.py:297-306` (`weight_logs`); `routers/nutrition.py:424-451` | ❌ **missing** |
| **Food / protein logs** | `models.py:344-357` (`protein_logs`); `routers/nutrition.py:691-751` | ❌ **missing** |
| **Dietary restrictions and allergies** | `mobile/src/screens/NutritionSetupScreen.tsx:30,173`; `backend/app/neutron_recipes.py:173-180` | ❌ **missing** — and these are health-adjacent (Alpha-Gal is a medical allergy) |
| **Kitchen / pantry photos** (processed, never stored) | `routers/nutrition.py:454-462`; module promise at `routers/nutrition.py:7,459` | ❌ **missing** — already flagged at `OPERATIONS_RUNBOOK.md:273-274` |
| **Voice-derived meal text sent to Bedrock** | `mobile/src/screens/VoiceLogScreen.tsx:98-104` → `routers/nutrition.py:638`; cached server-side in `models.py:359-371` (`nutrition_parse_cache`) | ❌ **missing** — audio stays on device, but the *transcript phrases* leave it and are cached |
| **Free-text exercise descriptions sent to Bedrock** | `routers/programs.py:321`; cached in `models.py:373-386` (`exercise_classify_cache`) | ❌ **missing** |
| **Optional display name** | `backend/app/database.py:46`; `routers/onboarding.py:112-117` | ❌ **missing** |
| Phone number | `models.py` `User.phone`; `routers/auth.py:84,87-88` accepts it | ⚠️ policy claims it at `main.py:54`, but **no screen collects it** — the field is dead in the UI. Harmless, but the policy over-discloses. |
| Affiliate commission relationship | `routers/nutrition.py:857-859` (`_DISCLOSURE`) | ❌ **missing from the policy** (it is disclosed in-app at `ProteinBoostersScreen.tsx:100`) |

Also stale: `main.py:50` says "Last updated: July 1, 2026" — predates the entire nutrition module.
And `main.py:62` promises "You may request deletion of your account and data at any time", which is
only true via email today (HB-1).

### 1.5 Apple guideline risk specific to this app

**HB-1 · Guideline 5.1.1(v) — Account deletion. HARD BLOCKER.**
The app creates accounts (`routers/auth.py:82-86` find-or-create on first OTP request). Apple requires
that an app supporting account creation let the user **initiate deletion from inside the app**, and
states that offering only a support-email flow is insufficient. Verified absent on both sides:
- Backend: the complete endpoint inventory across `backend/app/routers/*.py` contains no user-deletion
  route. The only `DELETE` verbs are `routers/nutrition.py:619` (saved recipe) and
  `routers/nutrition.py:737` (a single food-log entry).
- Mobile: `mobile/src/screens/HomeScreen.tsx:111-121` offers **Sign out** only; `mobile/src/AuthContext.tsx:34-35`
  calls `AuthApi.logout()` (`mobile/src/api.ts:78-81`), which revokes tokens and nothing else.
- The support page (`main.py:77`) says "Email support@glpsteel.com from your account email" — that is
  exactly the pattern Apple calls out as not sufficient on its own.

*Fix shape (Phase 2):* `DELETE /me` behind `get_current_user` that cascades the user's rows and
deletes their consented S3 objects via the existing `ImageStorage.delete` hook (already written for
this purpose — `backend/app/storage.py:24-26,48-52`), plus a confirmed destructive action in the Home
overflow menu next to Sign out.

**HB-3 · Guideline 2.1 (App Completeness) / 2.3.1 — the Protein Boosters marketplace ships non-functional. HARD BLOCKER.**
All ten catalog entries point at `https://example.com/affiliate-placeholder/...`
(`routers/nutrition.py:817,821,825,829,833,837,841,845,849,853`). The app detects this and shows an
alert reading *"Affiliate partnerships aren't live yet — this link is a placeholder"*
(`mobile/src/screens/ProteinBoostersScreen.tsx:46-52`), with buttons literally labelled
"View product (placeholder link)" (`ProteinBoostersScreen.tsx:94`). A reviewer who opens the Nutrition
tab will reach this in two taps. Shipping a screen that announces its own incompleteness is a
straightforward 2.1 rejection. Already on the internal list at `OPERATIONS_RUNBOOK.md:270-272`.
*Options:* (a) swap in real affiliate URLs before submission, or (b) hide the Protein Boosters
entrance for 1.0 and reintroduce it when partnerships are live. (b) is lower-risk.

**Guideline 3.1.5(a) — physical goods. NOT a blocker; the current design is compliant.**
Apple's rule is that apps enabling purchase of *physical goods consumed outside the app* must use
payment methods **other than** in-app purchase. Protein powders, bars and yogurt are physical goods;
the app takes no payment at all and merely opens an external URL
(`mobile/src/screens/ProteinBoostersScreen.tsx:53` → `Linking.openURL`). **No IAP entitlement is
required and none should be added.** The only exposure here is HB-3 (dead links) and SF-11 (stale
prices), not the payment rule. This directly answers the brief's question: linking out to physical
goods is compliant.

**HB-5 · Guideline 1.4.1 (Safety — Physical Harm) — health positioning with no in-app disclaimer. HARD BLOCKER.**
Apple's published position: medical apps "may be reviewed with greater scrutiny", and "apps should
remind users to check with a doctor in addition to using the app and before making medical decisions."
This app:
- is explicitly framed around users taking prescription GLP-1 medication —
  `mobile/src/screens/NutritionSetupScreen.tsx:123` ("On GLP-1 medication, appetite drops, but your
  muscles' protein needs don't"), and a preset labelled "GLP-1 minimum" at `NutritionSetupScreen.tsx:24`;
- prescribes a **numeric protein intake target computed from the user's bodyweight**
  (`NutritionSetupScreen.tsx:20`, default 1.52 g/kg);
- generates meals via an LLM under **hard allergy constraints including Alpha-Gal syndrome**, which the
  prompt itself calls "a life-safety allergy, not a preference" (`backend/app/neutron_recipes.py:158`,
  constraint rendering at `neutron_recipes.py:173-180`, surfaced at
  `mobile/src/screens/NutritionSetupScreen.tsx:30`);
- prescribes training loads and progression to beginners (`backend/app/engine.py`, `progression.py`).

A grep for disclaimer language across `mobile/src`, `backend/app` and the website returns **only two
hits, both on the marketing site** (`website/index.html:426` and `website/index.html:494`). **There is
no medical disclaimer anywhere inside the app or in the privacy policy.** An app that tells a
medicated user how much protein to eat, and generates food for a life-threatening allergy, with zero
"talk to your clinician" copy, is the exact shape Apple scrutinises under 1.4.1.
*Fix shape (Phase 2):* a persistent disclaimer on the nutrition setup screen and on generated recipe
output, plus a line in the privacy policy. **Note the stop condition — I will not touch any
weight-loss or GLP-1 marketing claim without your explicit sign-off on the wording.**

**HB-4 · Guideline 5.1.1(i) — purpose strings do not cover all uses. HARD BLOCKER (cheap to fix).**
`Info.plist:50` says the camera is used "to photograph your equipment" and `Info.plist:56` says photos
are accessed "to identify equipment". Both permissions are **also** used to photograph the user's
kitchen and food (`mobile/src/screens/KitchenScanScreen.tsx:51,55`), which those images are then sent
to a cloud model to analyse. Apple requires the purpose string to explain how the app uses the data;
a string that names only one of two materially different uses — one of which is food/household
imagery — is a reviewable inaccuracy. Fix by rewording both strings in
`ios/WeightProgram/Info.plist` **and** mirroring the change into `mobile/app.json` (which is the
source of truth only if `ios/` is ever regenerated — `OPERATIONS_RUNBOOK.md:255-258`).

**HB-6 · Guideline 2.3 (Accurate Metadata) — the marketing URL contains fabricated social proof. HARD BLOCKER.**
`website/index.html:167` renders **"4.9 App Store rating"** for an app that has never been publicly
released. `website/index.html:110` and `:447` are "Download on the App Store" buttons pointing at
`href="#"`. `OPERATIONS_RUNBOOK.md:275-277` already lists fake ratings, placeholder testimonials and a
press bar as unresolved. If `glpsteel.com` is submitted as the Marketing URL, a reviewer following it
sees an invented App Store rating. Beyond Apple, an unsubstantiated rating claim is an advertising-law
exposure independent of the App Store. *Note: `website/` is outside the Phase 2 edit scope you set, so
this one is documented as a manual step rather than fixed in code.*

**Guideline 1.2 (User-Generated Content) — does NOT apply. Assessed and dismissed.**
1.2 governs content users create and **share with each other**, and requires filtering, reporting and
blocking. This app has no social surface: no profiles, no feeds, no comments, no user-to-user
visibility. The two free-text inputs — the "saw it on social media" exercise box
(`routers/programs.py:321`) and voice meal dictation (`routers/nutrition.py:638`) — are private to the
author and never rendered to another user. The one sharing affordance, the PR card
(`mobile/src/ui/PrShareCard.tsx:37-43`), hands an image to the OS share sheet and leaves our system.
**No content-moderation feature is required for review.**

**Guideline 4.7 — does NOT apply.** 4.7 covers mini apps, mini games, streaming games, chatbots,
plug-ins and emulators embedded in a host app. This app embeds none of those; the AI work is
server-side, single-purpose and structured (forced tool calls at `recognition.py:225-228`,
`neutron_recipes.py`, `custom_exercise.py`). The remaining AI exposure is accuracy of generated
*food* under allergy constraints, which is HB-5's 1.4.1 problem, not 4.7. I am not aware of a
guideline number that would make AI recipe output a separate violation here, and am not going to
invent one.

**Guideline 5.1.2 (Data Use and Sharing) / ATT — no gap.** No tracking SDKs, no ad identifiers, no
`expo-tracking-transparency`, no third-party analytics in `mobile/package.json`. "Used for tracking:
No" is truthful across every data type.

### 1.6 Privacy nutrition label — proposed answers

Derived from code, ready to paste in Phase 3. All types are **linked to identity** because every row
carries a `user_id` foreign key.

| Data type | Collected | Linked to identity | Tracking | Purpose | Evidence |
|---|---|---|---|---|---|
| Email address | Yes | Yes | No | App Functionality (auth) | `models.py:31-34` |
| Name (optional) | Yes | Yes | No | App Functionality (personalisation) | `database.py:46`; `onboarding.py:112-117` |
| User ID | Yes | Yes | No | App Functionality | `models.py:31-34` |
| Health & Fitness — Fitness | Yes | Yes | No | App Functionality | `models.py:230-268` (workouts, sets) |
| Health & Fitness — Health (bodyweight) | Yes | Yes | No | App Functionality | `models.py:297-306` |
| Health & Fitness — Health (diet/allergies) | Yes | Yes | No | App Functionality | `models.py:270-296`, `344-357` |
| Photos | Yes *(conditional)* | Yes | No | App Functionality **+ Product Personalisation/Improvement when the user opts in** | `inventory.py:107,171-178`; opt-in flag `consent_to_train` |
| Audio Data | **No** | — | — | Speech is recognised **on-device** (`VoiceLogScreen.tsx:62,98-104`); no audio leaves the device | |
| Other User Content (meal text sent for parsing) | Yes | Yes | No | App Functionality | `nutrition.py:638`; `models.py:359-371` |
| Contact Info — Phone | **No** (declare No) | — | — | Field exists in the model but no screen collects it | `models.py` `User.phone` |
| Usage Data / Diagnostics / Identifiers / Location / Contacts | No | — | — | No SDKs present | `mobile/package.json` |

`[unverified — confirm in App Store Connect]` whether a label set is already saved from the TestFlight
submission; if so it predates the nutrition module and must be re-answered.

---

## 2. HARD BLOCKERS — Apple will reject, or the app is unshippable as-is

| ID | Blocker | Guideline | Where | Fixable in Phase 2 scope? |
|---|---|---|---|---|
| ~~**HB-1**~~ | ~~No in-app account deletion~~ **✅ FIXED 2026-08-18** | **5.1.1(v)** | `app/deletion.py`; `POST`/`DELETE /me/deletion` in `routers/onboarding.py`; Home menu item + `PendingDeletionScreen.tsx`; `App.tsx` gate | ✅ done. 30-day grace, anonymising fold, purge sweep. Tests: `python3 -m tests.test_deletion` |
| ~~**HB-2**~~ | ~~Live reviewer backdoor with a non-expiring fixed code, credential committed to a GitHub-pushed repo~~ **✅ CODE FIX LANDED 2026-08-17** | Not a guideline — a security defect that must not reach production | `config.py` `review_bypass_state()`; `auth.py` request-otp + verify-otp guards; `main.py` boot log | ✅ done in code. **Three manual steps remain — see §2a.** |
| **HB-3** | Protein Boosters ships with 10 dead `example.com` links and in-app copy admitting the feature isn't live | **2.1** App Completeness | `nutrition.py:817-853`; `ProteinBoostersScreen.tsx:46-52,94` | ✅ yes (hide the entrance) — **needs your call: hide vs. supply real URLs** |
| **HB-4** | Camera and photo-library purpose strings describe equipment only; both are also used for kitchen/food photos | **5.1.1(i)** | `Info.plist:49-50,55-56` vs `KitchenScanScreen.tsx:51,55` | ✅ yes |
| **HB-5** | GLP-1 / bodyweight-derived protein targets and allergy-constrained AI meals with **no medical disclaimer anywhere in the app** | **1.4.1** | `NutritionSetupScreen.tsx:24,123`; `neutron_recipes.py:158,173-180`; disclaimer exists only at `website/index.html:426,494` | ⚠️ yes, **but blocked on your approval of the wording** (stop condition) |
| **HB-6** | Marketing URL shows a fabricated "4.9 App Store rating" and dead store links | **2.3** Accurate Metadata | `website/index.html:167,110,447` | ❌ **out of the Phase 2 edit scope you set** — documented as a manual step |
| **HB-7** | Privacy policy omits bodyweight, food logs, dietary/allergy data, kitchen photos, voice-derived text and the affiliate relationship | **5.1.1** / **5.1.2** and App Store Connect accuracy | `main.py:46-65` vs §1.4 table | ✅ yes (`main.py` is in scope) |

### 2a. HB-2 — manual steps still outstanding

The code fix is deployed-ready but not self-completing. Three things only you can do:

1. **Rotate the credential on ECS.** Generate `openssl rand -hex 16` (32 chars), set it as
   `REVIEW_CODE` on the `weightprogram-api-1257` task definition, and set `REVIEW_BYPASS_UNTIL` to
   an ISO date ~6 weeks out. Until you do, the bypass is simply **inert** — the old 6-digit code
   fails the length guard, so the backdoor is already closed by this deploy even if you do nothing.
2. **Decide on the git-history rewrite.** The old code survives in two commits
   (`d3db78e`, `98a779a`). Rotating `REVIEW_CODE` makes the historical value worthless, which is
   normally sufficient. If you also want it gone from history:
   ```bash
   # DESTRUCTIVE — rewrites every commit hash; requires a force-push and
   # breaks any existing clone. Run only if the rotation above is done first.
   # Write the old code into a scratch file OUTSIDE the repo so this procedure
   # doesn't re-commit the very value it's removing:
   printf '%s==>REDACTED\n' "<old-6-digit-code>" > /tmp/scrub.txt
   git filter-repo --replace-text /tmp/scrub.txt
   git push --force origin main
   rm /tmp/scrub.txt
   ```
   I have **not** run this. `git filter-repo` is not installed by default (`brew install git-filter-repo`).
3. **Clear all three vars after approval.** Non-fatal if forgotten — the expiry date closes the
   window on its own, which was the point of the design.

---

## 3. SHOULD-FIX — technical debt and release hygiene

| ID | Item | Where | Note |
|---|---|---|---|
| **SF-1** | Re-enable DB TLS | `database.py:12`; `OPERATIONS_RUNBOOK.md:180-181` | Code change is small; the `rds.force_ssl` revert is a manual AWS step. Already on `OPERATIONS_RUNBOOK.md:263`. |
| **SF-2** | Move schema management to Alembic | `database.py:31-63` (`_COLUMN_BOOTSTRAP` + `create_all` on boot), `main.py:22-26` | `_COLUMN_BOOTSTRAP` swallows every exception at `database.py:62-63`, so a genuinely failing migration is silent. Pre-existing item, `OPERATIONS_RUNBOOK.md:268`. |
| **SF-3** | Diagnostic log lines | `recognition.py:236`, `neutron_vision.py:206`, `neutron_parse.py:204`, `custom_exercise.py:393` | **Recommend downgrading to `_log.info` rather than deleting** — see S4. The runbook currently both requires their removal (`:265`) and depends on them (`:196-199`); that contradiction should be resolved. |
| **SF-4** | Give `api.glpsteel.com` a stable route | `OPERATIONS_RUNBOOK.md:43-46,175-177,266` | Removes the manual blue/green re-point, which is the most failure-prone step in the deploy. |
| **SF-5** | Fail-fast on the default JWT secret in production | `config.py:30`; `main.py:22-26` | Cheap guard against a silently mis-provisioned task definition. |
| **SF-6** | Version string `0.1.0` → `1.0.0` for a public launch | `Info.plist:21-22`; `mobile/app.json` | Cosmetic but visible on the product page. |
| **SF-7** | Runbook build-number instruction is a no-op | `eas.json:4,15` vs `OPERATIONS_RUNBOOK.md:122,140` | `appVersionSource: "remote"` + `autoIncrement: true` means EAS owns the build number; editing `app.json` does nothing for the production profile. Correct the runbook (or switch to `"local"`). |
| **SF-8** | `NSFaceIDUsageDescription` is unedited boilerplate | `Info.plist:51-52` | Reads `$(PRODUCT_NAME)` while the other four strings are hand-written. Not a rejection cause; inconsistent. |
| **SF-9** | **`mobile/ios/` is git-ignored and completely untracked** | `.gitignore` (`mobile/ios/`); `git ls-files mobile/ios` → **0 files** | The hand-edited `Info.plist` carrying all five permission strings exists **only** on the exFAT drive, with no version history and no backup. Given `OPERATIONS_RUNBOOK.md:247-258` (plugins don't apply; hand edits are the only mechanism) and the prior ITMS-90683 rejection, losing this file re-opens that failure. Recommend tracking `ios/` or at minimum `ios/WeightProgram/Info.plist`. |
| **SF-10** | App name vs. brand mismatch | `app.json` `name: "WeightProgram"` vs `website/index.html:13` "GLP Steel" | Product decision needed before the listing is created. |
| **SF-11** | Hardcoded marketplace prices will go stale | `nutrition.py:816,820,824,828,832,836,840,844,848,852` | Ten USD prices baked into the binary's API response. Re-verify before launch (`OPERATIONS_RUNBOOK.md:272`) or drop the price field. |

### Also noticed (not on the launch path, recorded for completeness)

- **`UIUserInterfaceStyle` is pinned to `Light`** at `Info.plist:83-84` (and `app.json` `userInterfaceStyle: "light"`), while the app ships a complete dark palette in `mobile/src/theme.ts` and the runbook asks for simulator passes "in BOTH light and dark mode" (`OPERATIONS_RUNBOOK.md:107-108`). As configured, **the dark theme can never render on a device.** Either intentional (then the dark-mode test instruction is moot) or a bug. Not a review blocker.
- `recognition.py.bak` is dead weight in the deployed image (S5). Deletion needs your approval.
- Pre-existing open app items from `OPERATIONS_RUNBOOK.md:269`: clear/cap photos in `CaptureScreen`, keyboard avoidance in `WorkoutScreen` (`PROJECT_STATE.md:285` says the fix is ready but unshipped).

---

## 4. What is verified clean (no action needed)

1. **Info.plist permission coverage** — every permission the code exercises has a string; nothing
   orphaned; `NSPhotoLibraryAddUsageDescription` correctly absent. (§1.2)
2. **No tracking, no ads, no third-party analytics** — ATT prompt not required, "Tracking: No" is
   truthful. (`mobile/package.json`)
3. **Secrets hygiene in the repo** — `backend/.env` untracked, no hardcoded AWS keys, boto3 uses the
   IAM role. (S6)
4. **Auth token design** — hashed OTPs and refresh tokens, rotation with reuse detection
   (`auth.py:184-193`), epoch-based instant revocation (`deps.py:50-52`), tokens in the iOS secure
   enclave (`mobile/src/tokenStore.ts`). The *only* weakness in this subsystem is the reviewer bypass
   (HB-2), which sidesteps all of it.

---

## 5. Recommended Phase 2 order

1. HB-1 account deletion (largest, and every other privacy item references it)
2. HB-7 privacy policy rewrite (depends on HB-1's wording)
3. HB-4 Info.plist purpose strings (5 minutes)
4. HB-2 backdoor removal + doc scrub (code only; **you rotate the ECS env vars**)
5. HB-3 Protein Boosters — **needs your decision: hide the entrance, or supply real affiliate URLs**
6. HB-5 medical disclaimer — **needs your approval of the exact wording**
7. SF-1, SF-3, SF-5 while the backend is already open
8. HB-6 website — manual, outside the edit scope you set

---

## 6. Decisions I need from you before Phase 2

1. **HB-3:** hide the Protein Boosters entrance for 1.0, or do you have real affiliate URLs to drop in?
2. **HB-5:** approve disclaimer wording (I'll draft it for review; per your stop condition I won't
   alter any GLP-1 / weight-loss claim unilaterally).
3. **S5:** may I delete `backend/app/recognition.py.bak`?
4. **SF-3:** downgrade the four `_log.warning` lines to `_log.info` (my recommendation) or delete them
   as the runbook currently says?
5. **SF-10:** listing name — "WeightProgram" or "GLP Steel"?
6. **SF-9:** should `mobile/ios/` (or just `Info.plist`) be added to git? That edits `.gitignore`,
   which is outside the scope lock, so I'm asking rather than assuming.

---

## Sources

- [App Review Guidelines — Apple Developer](https://developer.apple.com/app-store/review/guidelines/)
- [Offering account deletion in your app — Apple Developer Support](https://developer.apple.com/support/offering-account-deletion-in-your-app/)
- [Account deletion within apps required starting January 31 — Apple Developer News](https://developer.apple.com/news/?id=mdkbobfo)
- [Account deletion requirement starts June 30 — Apple Developer News](https://developer.apple.com/news/?id=12m75xbj)

# WeightProgram — Consolidated Build Specification

**Status:** Phase 3 — Specification Lock (awaiting confirmation to execute)
**Date:** 2026-06-13
**Stack:** React Native (mobile client) + Python / FastAPI (backend)
**Product:** Photograph available weights/equipment → recognize → editable inventory → generate 3/4/5-day resistance programs tuned for a GLP-1–class user in a sustained caloric deficit. Email-only registration with OTP verification.

---

## 1. Locked Decisions

### Foundation
- **F1 — Backend framework:** FastAPI (async, Pydantic-typed schemas). *Confidence: high.*
- **F2 — Database:** PostgreSQL (relational core: users ↔ inventory ↔ programs; JSONB for flexible equipment/program blobs). *Confidence: high.*
- **F3 — Verification:** 6-digit OTP, 10-min expiry, single-use, rate-limited. Doubles as passwordless login (no passwords stored). *Confidence: high.*
- **F4 — Session:** Short-lived JWT access token (~15 min) + long-lived rotating refresh token (~30–60 days). Refresh token stored in OS secure enclave (iOS Keychain / Android Keystore via expo-secure-store or react-native-keychain). Refresh rotation with reuse detection. Server-side refresh-token registry to support logout-everywhere and account deletion. **No clinician/enterprise tier; not architected for one.** *Confidence: high.*
- **F6 — Phone number:** Optional, store-only. No SMS verification in v1. *Confidence: high.*
- **F8 — Compliance posture:** Consumer-health-data baseline + aggressive data minimization. **No HIPAA.** Specifically:
  - **Do not store medication.** Store only `training_mode` (e.g., `deficit_preservation`). The molecule (retatrutide/other) is never persisted per-user. May be asked for product analytics but not stored as structured per-user health data.
  - Explicit consent at point of image capture and any health-adjacent question.
  - Encryption in transit and at rest.
  - Working account + data deletion endpoint.
  - Honor Global Privacy Control (GPC) signals.
  - Health-adjacent data and user photos are **never** shared or sold for advertising.
  - *Confidence: high.* (Grounded in WA My Health My Data Act + CA consumer-health-data law, both in effect 2026, both reaching consumer apps that track weight/prescriptions; MHMDA carries a private right of action.)

### Recognition
- **R1 — Method:** Multimodal vision LLM emitting structured JSON → **mandatory** human-in-the-loop confirmation → confirmed inventory is canonical. No vision system reliably reads plate denominations/dumbbell dials from casual photos, so the draft is always user-confirmed. *Confidence: high.*
- **R1a — Data flywheel:** Log every (image, LLM draft, user-corrected inventory) triple from day one. Image-level labels only (not bounding boxes). Capture-now, train-later. Consent-gated (ties to F8). The correction delta is the highest-value training signal. Do NOT add localization capture to v1 (would add friction to the one screen that must stay frictionless). *Confidence: high.*

### Structure
- **S2 — Generation engine:** Hybrid, **rules-dominant**. Deterministic engine owns exercise selection, set/rep/volume prescription, split logic, and all deficit/recovery constraints (testable, reproducible, auditable, cheap). LLM confined to (a) coaching language / exercise cues and (b) "best substitute" suggestion only when the rule engine hits an equipment gap it can't fill. *Confidence: high.*
- **S3 — GLP-1 / deficit training logic (engine constants):**
  1. **Intensity priority over volume** — working sets mostly **5–10 reps**; when recovery degrades, cut sets, never load. *High.*
  2. **Frequency is an OUTPUT, not a hardcoded rule.** The engine distributes each muscle's weekly volume across the user's chosen days subject to the per-session time budget (#9). A **priority tier** governs allocation: large/primary movers (back, quads, chest, hams, glutes) get 2×/week *when the budget allows*; smaller/accessory muscles (arms, calves, side/rear delts) default to 1× and ride the compounds. *High* (2× benefit is real but modest at equated volume, strongest for big muscles).
  3. **Weekly volume ~8–14 hard sets per muscle group**, biased low as deficit deepens and lower still for near-beginners. *Moderate-high.*
  4. **Autoregulation by RIR (reps in reserve), target 1–3 RIR.** Primary adaptation for this population's fluctuating energy/appetite. *High.*
  5. **Compound multi-joint movements as the spine of each session**; accessories after. *High.*
  6. **Double progression** (add reps, then load); strength *maintenance* counts as success. *High.*
  7. **Deload every 4–6 weeks**, triggerable early by logged readiness/fatigue. *Moderate.*
  8. **Protein/recovery flag, not prescription** — surfaced as a coaching note; numbers wait for the nutrition module. *High.*
  9. **Session time budget — first-class hard constraint.** Captured at onboarding (days/week + session length), **default 60 min**, user-overridable. Engine converts duration to a per-session working-set budget via `time ≈ sets × (set_duration + rest)` (~15–20 sets in 60 min with compounds at 2–3 min rest; density techniques — antagonist supersets, shorter accessory rest — raise the ceiling). The engine **fits to the stated duration with a small tolerance and warns if priority volume can't fit**, rather than silently truncating. *High* on the constraint; *moderate* on the sets-per-minute coefficients (tunable).
  - **Cardio/conditioning:** OUT of v1 (deferred to a later version).

### Deferred decisions resolved from context (for completeness; lower stakes)
- **R2 — Equipment taxonomy (LLM output schema):** Classes covering the home/garage long tail — barbell + plates (by denomination & quantity), fixed dumbbells, adjustable dumbbells, kettlebells, bench (none/flat/adjustable), rack (none/squat stand/power rack), pull-up bar, cable/selectorized machines, resistance bands, bodyweight-only. Each item carries: type enum, quantity, load range, load increment, attachments. *Confidence: high.*
- **S1 — Inventory data model:** Per-user inventory = set of equipment entries (type enum + attributes JSONB + quantity + min/max load + increment). **Versioned** (version id, confirmed_at, source image ref) so program regeneration is traceable. Full CRUD for edits. *Confidence: high.*
- **R3 — Correction UX:** Post-recognition, show a pre-filled editable list; per-item confirm / edit / delete / add; show recognition confidence; user must confirm to proceed. *Confidence: high.*
- **R4 — Capture:** Allow a multi-photo session (pan the gym), synthesized into one inventory draft. *Confidence: moderate.*
- **S4 — Split templates (derived from chosen days + session budget):** The user's onboarding day-count selects the primary program; all three remain generatable.
  - **3-day = rotating-emphasis full-body** — every session hits major movement patterns; the 2nd weekly dose rotates across muscles. Net ~2× for priority movers, ~1× for the rest. This is where the time budget bites hardest.
  - **4-day = upper/lower ×2** — naturally 2× for most muscles; time budget just trims sets per session.
  - **5-day = upper/lower/push/pull/legs** — more days makes the budget *easier*; priority muscles hit 2× comfortably.
  - Each template instantiated against available equipment; rule-based substitution first, LLM fallback for gaps. *Confidence: high on 3/4-day, moderate on 5-day structure.*
- **S5 — Regeneration semantics:** An inventory edit creates a **new program version**; the active program is **not** silently mutated. User is prompted "equipment changed — regenerate?" History preserved. *Confidence: high.*
- **Onboarding (first login, after auth):** Capture training **habits** — days/week, **session length (default 60 min)**, and **training experience (default conservative / low-intermediate)**. These feed the engine directly. Non-health fields. *Confidence: high.* (Resolves former open item R-2.)
- **U — Screen map:** Auth (email → OTP), Onboarding/habits, Home, Capture, Inventory review/edit, Program list (3/4/5-day), Program-day detail, Workout logging (captures RIR + readiness). *Confidence: high.*

---

## 2. Rationale Chain (why the spine holds together)
Vision-LLM recognition is a *draft*, never trusted → mandatory confirmation makes recognition errors survivable AND produces the labeled flywheel data → confirmed inventory feeds a *deterministic* engine so program output is reproducible, testable, and defensible for users training hard while underfed → the engine's constants encode deficit-specific principles (intensity-priority, RIR autoregulation, ≥2× frequency) that are the product's actual moat → data minimization (training_mode flag, not medication) keeps most records out of "consumer health data" classification, sharply cutting legal exposure under MHMDA/CA → passwordless OTP + secure-enclave refresh tokens give daily-use friction-free auth without storing passwords, with server-side revocation for deletion compliance.

---

## 3. Execution Sequence (phased; starts with registration, as requested)
- **Increment 1 — Auth/Registration + Onboarding** *(start here)*: FastAPI app skeleton, Postgres schema (users, otp_codes, refresh_tokens, user_habits), email OTP issue/verify, JWT + rotating refresh, RN auth screens (email entry → OTP entry), and the first-login **onboarding/habits** screen (days/week, session length default 60 min, experience default conservative) → authenticated home. Email provider wired in (see risk R-1).
- **Increment 2 — Inventory capture**: RN camera + multi-photo capture, image upload (consented), vision-LLM recognition → JSON, correction/confirmation UX, inventory CRUD + versioning, flywheel logging.
- **Increment 3 — Program generation**: deterministic rule engine, S3 constants, S4 split templates, equipment-constrained exercise selection + LLM substitution fallback, program list + day-detail display.
- **Increment 4 — Logging & regeneration**: workout logging (RIR/readiness), autoregulation feedback, regenerate-on-inventory-edit flow, deload triggers.
- **Cross-cutting (all increments)**: F8 compliance baseline (consent, deletion endpoint, encryption, GPC), secure token storage, audit/logging hygiene.

---

## 4. Risk Register
| ID | Item | Status / Confidence | Mitigation |
|----|------|--------------------|------------|
| **R-1** | **Email delivery provider (F5) — OPEN.** Required before Increment 1 can send OTPs. | OPEN. Recommend **Resend** (DX) or **AWS SES** (cost at scale). | Confirm vendor at execution start; abstract behind an interface so it's swappable. |
| ~~R-2~~ | ~~Typical user's training experience — UNKNOWN.~~ **RESOLVED:** captured at onboarding; default conservative (low-intermediate) until set. | RESOLVED. | — |
| R-3 | Vision LLM mis-reads plate weights/quantities → bad drafts → correction friction. | Moderate residual. | Mandatory confirmation (R1) absorbs it; monitor correction rates via flywheel. |
| R-4 | Vision LLM per-signup cost & latency. | Moderate. | One recognition per capture session; cache; revisit if volume spikes. |
| R-5 | Deload cadence (S3 #7). | Moderate. | Make cadence a tunable; trigger early on logged fatigue. |
| R-6 | 5-day split structure (S4). | Moderate. | Validate against equipment-constrained instantiation; adjust template if gaps recur. |
| R-7 | Multi-photo synthesis (R4). | Moderate. | Start with up to N images merged into one draft; fall back to single photo if synthesis is unreliable. |
| — | Nutrition module, cardio, clinician/enterprise tier. | DEFERRED (explicitly out of v1). | Not built; not architecturally precluded except clinician tier (intentionally excluded). |

---

## 5. Outstanding before execution
1. **R-1:** pick email provider (Resend vs SES). *(Only remaining blocker; recommend Resend, swappable behind an interface.)*

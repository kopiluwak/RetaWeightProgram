# WeightProgram — User Tutorial

*Version: TestFlight Beta (2026) · Applies to iOS*

---

## 1. Introduction

**WeightProgram** turns whatever equipment you have — a garage rack, a hotel gym, a full commercial floor — into a personalized resistance-training program. Photograph your equipment, and the app's AI builds an inventory, then generates a 3-, 4-, or 5-day program designed specifically for people losing weight (including GLP-1 medication users) who want to **preserve muscle in a calorie deficit**.

Beyond training, the **Neutron** nutrition module helps you hit your daily protein target: scan your kitchen, generate recipes from what you actually have, and log protein by voice.

**What you'll learn in this tutorial:**

- How to sign in and complete onboarding
- How to find help inside the app
- How to scan equipment, generate a program, and log workouts
- How to track progress, PRs, and trends
- How to use Neutron for protein tracking, kitchen scans, recipes, and voice logging
- How streaks, XP, and achievements work

> **Note:** No password is ever created or stored. WeightProgram uses one-time email codes for all sign-ins.

---

## 2. Getting Started

### 2.1 Install the app

1. **Accept your TestFlight invitation** (sent to your email) and install Apple's **TestFlight** app from the App Store if you don't have it.
2. In TestFlight, tap **Install** next to WeightProgram.
   - *You should see:* the WeightProgram icon appear on your home screen.
3. **Open WeightProgram.**

[Screenshot placeholder: TestFlight listing showing WeightProgram with the Install button]

### 2.2 Sign in with your email

WeightProgram uses passwordless login — a 6-digit code emailed to you.

1. On the welcome screen, **enter your email address** and tap **Continue**.
   - *You should see:* a code-entry screen.
2. **Check your inbox** for an email from `no-reply@glpsteel.com` containing a 6-digit code.
   - *Tip:* Check spam/junk if it doesn't arrive within a minute.
3. **Enter the code.**
   - *Expected outcome:* you're signed in. The app keeps you signed in securely on this device — you won't need a code every time.

[Screenshot placeholder: Email entry screen with the Continue button]
[Screenshot placeholder: OTP code entry screen]

### 2.3 First-launch onboarding

On first sign-in, the app asks about your training habits on the **"Your training habits"** screen:

1. **Days per week** — tap a chip (3, 4, or 5). Choose what you'll realistically do, not your ideal.
2. **Session length (minutes)** — tap the time you can commit per session. Programs are built to fit this budget.
3. **Experience** — tap **New / returning**, **Intermediate**, or **Advanced**.
4. Tap **Continue**.
   - *Expected outcome:* you land on the **Home** screen.

> **Pro tip:** You can change these settings anytime — the screen itself says so. Your next generated program will use the new answers.

[Screenshot placeholder: Onboarding screen with Days per week, Session length, and Experience chips]

---

## 3. Accessing In-App Instructions & Help

WeightProgram's help is built into the flow of the app rather than gathered in a separate menu. Here is every help resource available and how to reach it.

### 3.1 Contextual help and on-screen guidance

Every major screen includes instructional text right where you need it:

- **Capture screen:** the subtitle explains exactly what to photograph — *"Photograph your weights, rack, bench, machines — pan around for multiple shots."*
- **Workout readiness check:** explains why you're being asked — *"How's your energy today? This tunes how hard to push."*
- **Voice Log:** shows example phrasings and displays a **"Heard"** transcript so you can verify what was captured.
- **Steppers and inputs:** weight/reps/RIR fields show your last session's numbers pre-filled, so you always know your starting point.

*What to do:* just read the grey subtitle text under each screen title before acting — it's the app's built-in instruction layer.

[Screenshot placeholder: Capture screen showing the instructional subtitle text]

### 3.2 Exercise instructions (how-to help for every movement)

Every exercise in your program includes built-in guidance:

1. Open your program from **Home → your program card**.
2. Tap any exercise.
   - *You should see:* a **plain-language description** of how to perform it, a **YouTube "how-to" link** for video demonstration, and the **rest target** for that exercise.
3. Tap the YouTube link to watch proper form before your first attempt.
   - *Expected outcome:* the video opens; return to the app when done.

[Screenshot placeholder: Exercise detail showing description, YouTube link, and rest target]

### 3.3 Onboarding / guided setup

The guided setup runs automatically on first launch (Section 2.3). The Nutrition module has its own guided setup the first time you open **Neutron** from Home — it walks you through bodyweight entry and protein-target selection before unlocking the tracker.

### 3.4 Support page and email (in-app chat alternative)

WeightProgram doesn't have in-app chat; support is handled by email with a fast, human response:

1. Visit the support page at **https://api.glpsteel.com/support**, or
2. Email **support@glpsteel.com** directly from your account email.
   - *Use this for:* login problems, account deletion requests, bug reports, and feature questions.

> **Note:** Account deletion is also handled here — email support from your account email address and your data will be removed.

### 3.5 Help center, FAQ, and tooltips — current status

The app does not yet ship a dedicated in-app help center, searchable knowledge base, FAQ screen, or tap-target tooltips. This tutorial serves as the knowledge base in the meantime, and the **Recommendations for In-App Integration** section at the end proposes how to bring these into the app.

### 3.6 TestFlight feedback (beta builds)

While in beta, you have one extra help channel:

1. Take a screenshot inside the app.
2. Tap the screenshot preview → **Share Beta Feedback**.
   - *Expected outcome:* your note and screenshot go straight to the developer.

---

## 4. Core Features

### 4.1 Scan your equipment

This is the foundation — your program is built from what you actually have.

1. From **Home**, tap the equipment card (it reads **"No equipment yet"** until your first scan).
2. On the **Scan your equipment** screen, tap the capture button and **photograph your weights, rack, bench, and machines**. Pan around and take multiple shots (you can also select photos from your library).
   - *Note:* the AI analyzes up to **4 photos** per scan — make each one count. Wide, well-lit shots work best.
3. Review the consent text about image handling, then submit.
   - *You should see:* a brief processing state while the AI identifies your equipment.
4. On the **Confirm Inventory** screen, review the detected list.
   - **Edit anything the AI got wrong** — adjust weights, remove misidentified items, add missing ones.
5. Tap **Confirm**.
   - *Expected outcome:* your inventory is saved and versioned. You can rescan or edit anytime.

> **Note:** Cardio equipment (treadmills, bikes) is recognized and stored but intentionally excluded from lifting programs.

[Screenshot placeholder: Capture screen with photo thumbnails and consent checkbox]
[Screenshot placeholder: Confirm Inventory screen with an editable equipment list]

### 4.2 Generate your program

1. From **Home**, tap **Generate program** (available once your inventory is confirmed).
   - *You should see:* a program built for your days/week, session length, and experience level.
2. Open the **Program** screen to review each training day: exercises, sets, target reps, **RIR (Reps In Reserve)** targets, and rest times.
   - *RIR explained:* "2 RIR" means stop the set when you could still do 2 more reps. This keeps training productive without burning you out in a deficit.
3. Read the **deficit and deload notes** included with your program — they explain how the plan protects muscle while you lose weight.

> **Pro tip:** Programs are deterministic, not random — the same inputs produce the same sensible plan. If your schedule changes, update days/week and regenerate.

[Screenshot placeholder: Program screen showing a training day with exercises, sets, reps, and RIR]

### 4.3 Log a workout

1. From the **Program** screen, start today's session.
2. **Readiness check:** rate your energy (1–5) on the *"How's your energy today?"* screen.
   - *Expected outcome:* the session tunes how hard to push based on your answer.
3. The **Workout** screen shows a **NOW LOGGING** banner and **set dots** under each exercise so you always know which set you're on.
4. For each set, adjust **weight / reps / RIR** with the **steppers** (tap **+/−**, press-and-hold to move fast, or tap the number to type).
   - *Note:* values are **pre-filled from your last session** — most sets need no editing.
5. Log the set.
   - *You should see:* the **rest timer** start with an animated progress bar; it finishes with an **audible beep and haptic buzz**, so you can pocket your phone between sets.
6. Watch for **progression suggestions** — when you hit the top of a rep range, the app tells you to add weight next time (double progression).
7. Finish the session.
   - *Expected outcome:* a done screen with a summary — and an **+XP banner** (plus any achievement unlocks) for completing it.

> **Warning:** Log sets as you do them rather than backfilling at the end — pre-fill and progression suggestions depend on accurate set-by-set data.

[Screenshot placeholder: Workout screen with NOW LOGGING banner, set dots, and steppers]
[Screenshot placeholder: Rest timer with animated progress bar]

### 4.4 Track your progress

1. From **Home**, tap **Trends, PRs and history** to open the **Progress** screen.
   - *You should see:* five cards (estimated 1RM trends, PRs, consistency with shaded weekly badges, and more). **Press and drag to reorder** cards — your order is saved.
2. Tap into **Exercise Trends** for any lift and use the **range selector** (30d → All) to see strength over time.
3. Open **History** for a **26-week training heatmap** and a filterable session log.
4. When you set a PR, tap the **share card** to generate an image you can post or send.

> **Note:** PR detection requires at least 3 prior sessions of an exercise — the app won't call your first attempt a "record."

[Screenshot placeholder: Progress screen with reorderable analytics cards]
[Screenshot placeholder: History screen with the 26-week heatmap]

### 4.5 Neutron — protein and nutrition

Muscle preservation in a deficit is half training, half protein. Neutron handles the second half.

#### Set up your protein profile

1. From **Home**, tap the **Neutron** card.
2. First time in, complete **Nutrition Setup**: enter your **bodyweight** and pick a protein target preset:
   - **1.0 g/kg** — GLP-1 minimum
   - **1.52 g/kg** (default, ≈ 0.69 g/lb)
   - **2.2 g/kg** (≈ 1 g/lb)
   - *Expected outcome:* a daily protein target in grams, auto-calculated from your weight.
3. Log your bodyweight here whenever it changes — your target updates automatically.

[Screenshot placeholder: Nutrition Setup screen with bodyweight entry and multiplier presets]

#### Scan your kitchen

1. From **Nutrition Home**, tap **Scan My Kitchen**.
2. Photograph your **pantry and fridge** shelves.
   - *You should see:* an AI-generated food list to review and confirm.
   - *Privacy note:* kitchen photos are analyzed and **never stored**.
3. Confirm the list.
   - *Expected outcome:* a saved pantry the recipe engine can cook from.

#### Generate recipes

1. From **Nutrition Home**, open **Recipes**.
2. Tap **Generate** for high-protein recipes built from your confirmed pantry, **Adapt** for vegan/vegetarian versions, or **Surprise Me** for a full day plan.
   - *Note:* hard dietary constraints (including Alpha-Gal) are respected — set them in your profile.
3. Save recipes you like for later.

[Screenshot placeholder: Recipes screen with Generate, Adapt, and Surprise Me options]

#### Log protein — including by voice

1. From **Nutrition Home** or the **Protein Tracker**, log what you ate.
   - *You should see:* the **"Today" protein hero** update toward your daily target.
2. **Voice Log:** tap the mic and say your meal naturally — *"two eggs and a cup of greek yogurt."*
   - *You should see:* a **"Heard"** transcript, then **editable review cards** with estimated protein per item.
3. Correct anything that's off, then confirm.
   - *Expected outcome:* protein added to today's total. The app remembers your corrections and gets more accurate over time.
   - *Note:* voice parsing works mostly on-device and queues logs when you're offline.

[Screenshot placeholder: Voice Log screen with mic button, transcript, and review cards]

#### Protein Boosters

The curated **Protein Boosters** marketplace lists high-protein products with affiliate disclosure. Browse it from Nutrition Home — purchases happen outside the app.

### 4.6 Streaks, XP, and achievements

Gamification is woven through the app — no setup needed:

- **Home** shows your **level, XP, and workout streak** in the hero header, plus a **weekly challenge**.
- Finishing workouts and hitting protein targets earn **XP**; the **Workout done screen** shows the +XP banner and any **achievements unlocked**.
- The **Progress** screen's Consistency card shows **shaded weekly badges** — darker means a stronger week.

[Screenshot placeholder: Home screen with gamification header, streak, and weekly challenge card]

---

## 5. Tips & Best Practices

- **Scan in good light, from a step back.** Wide shots that show whole racks and dumbbell runs recognize better than close-ups of a single plate.
- **Always review the confirm screen.** The AI is good but not perfect — a wrong dumbbell range flows into every program until fixed.
- **Be honest on the readiness check.** Under-recovered days with an honest low score produce better long-term progress than pretending you're fresh.
- **Trust the RIR targets.** In a calorie deficit, grinding every set to failure works against muscle retention. Leaving reps in reserve is the point, not a compromise.
- **Follow the progression prompts.** When the app says add weight, add the smallest increment you have. Small consistent jumps beat occasional big ones.
- **Front-load protein.** Hitting your target is much easier if breakfast and lunch carry 30–40 g each — use Voice Log right after eating so nothing is forgotten.
- **Rescan when your setup changes.** New adjustable dumbbells or a gym change deserve a fresh scan and a regenerated program.
- **Protect your streak with the minimum, not the maximum.** On a rough week, doing your shortest programmed day keeps the streak and the habit alive.

---

## 6. Troubleshooting Common Issues

**The login code never arrives.**
Check spam/junk for `no-reply@glpsteel.com`. Confirm you typed the email correctly and request a new code. Still stuck? Email support@glpsteel.com from another address.

**Equipment scan returns nothing or misses obvious items.**
Usually a photo problem: too dark, too close, or too many photos (only 4 are analyzed per scan). Retake with fewer, wider, brighter shots. You can also add missing items manually on the Confirm Inventory screen.

**The scan misidentified my equipment.**
Expected occasionally — that's why the confirm step exists. Edit or delete the wrong entries before confirming; your inventory is versioned, so nothing is lost.

**Pre-filled weights/reps look wrong.**
Pre-fill comes from your last logged session of that exercise. If you skipped logging or backfilled inaccurately, adjust with the stepper — the next session will pre-fill from today's correct data.

**The rest timer didn't beep.**
Check that your phone isn't in Silent mode and that WeightProgram has notification/sound permission in iOS Settings. The haptic buzz fires regardless.

**Voice Log heard me wrong.**
Check the "Heard" transcript first — if the transcript is right but the food is wrong, edit the review card; the app caches your correction and won't repeat the mistake. If the transcript itself is wrong, speak in shorter phrases and reduce background noise.

**Voice Log while offline.**
Logs queue on-device and sync when you're back online — no action needed.

**A PR I clearly set isn't showing.**
PRs require at least 3 prior logged sessions of that exercise, so early sessions establish a baseline first. Keep logging; it will register.

**The app seems out of sync or stuck.**
Force-quit and reopen — the app re-authenticates automatically. If it persists, check your connection; workout logging needs the network.

> **Warning:** Never delete and reinstall the app as a first troubleshooting step for sync issues — contact support first so nothing on the device is lost unnecessarily.

---

## 7. Frequently Asked Questions (FAQ)

**Do I need a password?**
No. Sign-in is always via a 6-digit code emailed to you. There is no password to forget or leak.

**Is this app only for people on GLP-1 medications?**
No — but it's tuned for anyone training in a calorie deficit. The programming (moderate volume, RIR-based intensity, deload guidance) prioritizes keeping muscle while losing weight.

**What is RIR?**
Reps In Reserve — how many reps you *could* still do when you stop a set. "2 RIR" = stop 2 reps before failure. It's a simpler, safer way to prescribe effort than percentages.

**Can I train at a commercial gym and at home?**
Yes. Rescan whenever you change locations, or maintain your inventory to reflect what you use most. Each program is generated from your current confirmed inventory.

**Why isn't my treadmill in my program?**
Cardio equipment is recognized and stored but deliberately excluded from lifting programs. Cardio programming is on the roadmap.

**Where do the protein targets come from?**
Your bodyweight × your chosen multiplier: 1.0 g/kg (GLP-1 minimum), 1.52 g/kg (default), or 2.2 g/kg (≈ 1 g/lb). Update your bodyweight and the target recalculates.

**Are my kitchen photos stored?**
No. Kitchen scan photos are analyzed to build your food list and never stored. Equipment photos are stored only if you consent on the capture screen.

**How is my estimated 1RM calculated?**
From your logged sets using an RIR-adjusted Epley formula, capped at 12 effective reps — so high-rep sets don't produce inflated numbers.

**How do I delete my account?**
Email **support@glpsteel.com** from your account email, or see https://api.glpsteel.com/privacy. Your data will be removed.

**Does the app work offline?**
Voice protein logs queue offline and sync later. Workout logging and program generation need a connection.

---

## Recommendations for In-App Integration

How this tutorial's content could live inside the app:

1. **First-run guided tour.** Convert Sections 2.3 and 4.1–4.3 into a 4-step overlay tour (Home → Scan → Program → first log) with skippable coach marks. The existing onboarding screen is the natural trigger point; store a `tour_completed` flag alongside the existing SecureStore preferences.

2. **"?" help sheet per screen.** Add a small help icon in each screen header that opens a bottom sheet with that screen's slice of this tutorial (Capture tips on CaptureScreen, RIR explainer on WorkoutScreen, transcript tips on VoiceLogScreen). Content can ship as static markdown in the bundle — no backend work.

3. **In-app FAQ screen.** Section 7 maps directly to a simple `FAQScreen` (accordion list, ~1 screen of code with the existing Card/Chip UI kit). Link it from Home and from error states (e.g., the OTP screen's "didn't get a code?" could deep-link to the login FAQ entry).

4. **Hosted help center.** Serve this tutorial at `api.glpsteel.com/help` next to the existing `/support` and `/privacy` pages (same static-HTML pattern already in `main.py`), and link it from the app and the App Store listing. One canonical source, updatable without an app release.

5. **Contextual first-use tooltips.** One-time tooltips on the three least discoverable interactions: press-and-hold on steppers, drag-to-reorder on Progress cards, and the PR share card. Dismiss-once, stored locally.

6. **Empty-state education.** The "No equipment yet" card already teaches; extend the pattern — an empty Progress screen could preview what appears after 3 sessions (tying into the PR baseline rule), and an empty pantry could show a sample scan result.

7. **Troubleshooting-aware errors.** Map common failures to Section 6 text at the point of error: scan returning zero items → photo tips inline; OTP timeout → spam-folder hint. Cheapest support deflection available.

8. **Support form instead of bare mailto.** A minimal in-app "Contact support" form (posting to the existing `/support` infrastructure or generating a pre-filled email) that auto-attaches app version and build number would cut back-and-forth on bug reports.

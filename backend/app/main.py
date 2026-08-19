"""FastAPI application entrypoint.

Wires all feature routers onto one app, runs the DB bootstrap on startup,
and serves the static privacy/support pages required for App Store review.
"""
from __future__ import annotations
from fastapi.responses import HTMLResponse

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import deletion
from .config import get_settings
from .database import init_models
from .routers import analytics, auth, gamification, inventory, nutrition, onboarding, programs, workouts

logging.basicConfig(level=logging.INFO)
settings = get_settings()
_log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Convenience bootstrap; production should use Alembic migrations instead.
    await init_models()
    # Make the reviewer-bypass state visible in the boot log. A bypass still
    # armed after App Review is the riskiest thing this service can be running,
    # so it announces itself on every start rather than sitting silent.
    armed, reason = settings.review_bypass_state()
    if armed:
        _log.warning(
            "REVIEWER LOGIN BYPASS IS ARMED for %s (%s) — clear the REVIEW_* env vars "
            "once App Review is complete.", settings.review_email, reason,
        )
    else:
        _log.info("reviewer login bypass inactive (%s)", reason)

    # Account-deletion purge sweep (5.1.1(v)). Runs in-process on a timer rather
    # than as external infrastructure; see app/deletion.py for why that is safe
    # with several ECS tasks running. Cancelled cleanly on shutdown so a
    # deploy doesn't leave the sweep mid-transaction.
    purge_task = asyncio.create_task(deletion.purge_loop())
    _log.info("account purge sweep started (grace period %d days)", deletion.GRACE_PERIOD_DAYS)
    try:
        yield
    finally:
        purge_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await purge_task


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(auth.router)
app.include_router(onboarding.router)
app.include_router(inventory.router)
app.include_router(programs.router)
app.include_router(workouts.router)
app.include_router(analytics.router)
app.include_router(nutrition.router)
app.include_router(gamification.router)


@app.get("/health", tags=["meta"])
async def health():
    """Liveness probe used by the deploy pipeline and load balancer."""
    return {"status": "ok", "environment": settings.environment}


_PRIVACY_HTML = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>WeightProgram — Privacy Policy</title>
<style>body{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;max-width:760px;margin:40px auto;padding:0 20px;line-height:1.6;color:#1a1a1a}h1{font-size:28px}h2{font-size:20px;margin-top:32px}.muted{color:#666;font-size:14px}</style></head><body>
<h1>WeightProgram Privacy Policy</h1><p class="muted">Last updated: August 18, 2026</p>
<p>WeightProgram ("we," "us") builds resistance-training programs from photos of the equipment you own, and helps you track your workouts and protein intake. This policy explains exactly what we collect, why, who else sees it, and how to get rid of it. We designed the app to collect as little as possible — but this page lists everything, not just the flattering parts.</p>

<h2>Information we collect</h2>
<p><strong>Account</strong></p><ul>
<li><strong>Email address</strong> — to create your account and send one-time login codes. Login is passwordless; we never store a password.</li>
<li><strong>Phone number</strong> — optional, only if you type one on the sign-in screen. We do not use it to contact you.</li>
<li><strong>First name</strong> — optional, only to personalise the greeting.</li>
<li><strong>Account identifier</strong> — a random user ID we generate for you.</li></ul>

<p><strong>Training</strong></p><ul>
<li><strong>Equipment inventory</strong> — the equipment you confirm you own, and the programs generated from it.</li>
<li><strong>Workout logs</strong> — each set you record: exercise, weight, reps and how many reps you had left in reserve.</li>
<li><strong>Readiness check-ins</strong> — the 1–5 energy rating you give before a session, used to adjust how hard the app pushes you.</li>
<li><strong>Progress milestones</strong> — streaks, XP, levels and badges, calculated from the above.</li></ul>

<p><strong>Body and nutrition</strong> — collected only if you use the nutrition features:</p><ul>
<li><strong>Body weight</strong> — your current weight, optional goal weight, and the history of weights you log over time.</li>
<li><strong>Protein settings</strong> — your daily protein target and how it was calculated.</li>
<li><strong>Dietary preferences and allergies</strong> — for example vegetarian, keto, or "no red meat (Alpha-Gal)". We treat these as sensitive and use them only to constrain the recipes we generate.</li>
<li><strong>Food and protein logs</strong> — what you logged, the estimated protein and calories, and when.</li>
<li><strong>Pantry list</strong> — the food items you confirm you have at home, and any recipes you save.</li></ul>

<p><strong>Photos and voice</strong></p><ul>
<li><strong>Equipment photos</strong> — sent for automated recognition. <strong>Stored only if you opt in</strong> to help improve recognition; otherwise they are used to produce your inventory and then discarded.</li>
<li><strong>Kitchen and fridge photos</strong> — sent for food recognition and then <strong>discarded immediately</strong>. We never store them, whatever you have chosen for equipment photos. Only the food list you confirm is saved.</li>
<li><strong>Voice meal logging</strong> — your speech is transcribed <strong>on your device</strong>; the audio never reaches us. If a phrase can't be matched on-device, that short text phrase (for example "two eggs and a slice of toast") is sent to our AI provider to estimate its protein content.</li>
<li><strong>Exercise descriptions you type</strong> — if you describe a movement in your own words, that text is sent to our AI provider to classify it.</li></ul>

<h2>What we never collect</h2><ul>
<li><strong>Medication information.</strong> The app is designed for people on GLP-1-class medication, but we never ask which drug you take, or whether you take one at all, and there is nowhere in the app to tell us.</li>
<li>Location, contacts, calendar, health-app data, or motion and fitness sensors. The app requests none of these permissions.</li>
<li>Advertising identifiers. There are no third-party analytics, advertising or tracking SDKs in the app.</li></ul>

<h2>How AI processing works</h2>
<p>Equipment recognition, food recognition, recipe generation and food-phrase estimates run on Amazon Bedrock, inside our own AWS account. Your content is not used to train anyone else's models.</p>
<p>To avoid re-analysing the same thing repeatedly, we keep a shared dictionary of food phrases and exercise names that have already been looked up — for example "grilled chicken breast" and its protein content. These entries are stored with <strong>no account link</strong>, are shared across all users, and are not personal to anyone.</p>

<h2>How we use it</h2><p>Solely to operate the app: to sign you in, recognise your equipment and food, generate and adjust your programs and recipes, track your workouts and protein, and show your progress. With your explicit consent, stored equipment photos also help improve recognition accuracy.</p>

<h2>What we do NOT do</h2><ul><li>We do <strong>not</strong> sell your data.</li><li>We do <strong>not</strong> share your data or photos for advertising.</li><li>We do <strong>not</strong> track you across other apps or websites.</li><li>We do <strong>not</strong> show ads.</li></ul>

<h2>Service providers</h2><p>We use Amazon Web Services to host the app, store data, send login emails, and run the AI recognition described above — all within our own controlled AWS environment in the United States. We do not share your personal data with any other third party. If you are outside the United States, your data is processed there.</p>

<h2>Security</h2><p>Data is encrypted in transit and at rest. Login tokens are stored in your device's secure storage (Keychain on iOS). Sessions can be revoked instantly, and signing out on one device does not leave others authorised.</p>

<h2>Your rights and choices</h2><ul>
<li><strong>Photo storage is opt-in.</strong> Recognition works either way; declining costs you nothing.</li>
<li><strong>Nutrition features are optional.</strong> If you don't use them, we hold no body weight, food or dietary data for you at all.</li>
<li><strong>Delete everything, in the app, at any time</strong> — see below. No email required.</li>
<li>You can request a copy or correction of your data, or ask a question about any of the above, at <a href="mailto:privacy@glpsteel.com">privacy@glpsteel.com</a>.</li></ul>
<h2>Deleting your account</h2>
<p>Open the menu on the Home screen and choose <strong>Delete account</strong>. You do not need to email us.</p>
<p>When you confirm, you are signed out everywhere immediately and your account enters a <strong>30-day grace period</strong>. Nothing is deleted during that time: if you change your mind, sign back in and choose &ldquo;Keep my account&rdquo;. We email you when deletion is scheduled and again once it is complete.</p>
<p>After 30 days we permanently delete your email address, any name you gave us, your equipment inventory and generated programs, your workout and set history, your bodyweight log, your food and protein logs, your dietary preferences and allergy settings, and any equipment photos you chose to share.</p>
<p><strong>What we keep:</strong> anonymous, aggregated training statistics — counts of how many times a given exercise was logged at a given weight, rep count and effort level. These are stored as shared totals with no user identifier, no account link and no dates, so they cannot be traced back to you or to any individual. We keep them to improve the training programs the app generates for everyone.</p>
<p>The shared food-phrase and exercise-name dictionary described above is not deleted, because those entries carry no link to your account and are not personal to you.</p>
<h2>Changes to this policy</h2><p>If we change what we collect or how we use it, we will update this page and change the date at the top. Material changes will also be surfaced in the app.</p>
<h2>Health &amp; safety</h2>
<p>WeightProgram provides general fitness and nutrition information. <strong>It is not medical advice, and it is not a substitute for care from a qualified professional.</strong></p>
<ul>
<li>Protein targets are calculated from your body weight alone. They do not account for kidney, liver or other health conditions. Talk to your doctor or a dietitian about what is right for you — especially if you take GLP-1 or other prescription medication.</li>
<li>Training programs are generated automatically from the equipment and preferences you enter. Check with your doctor before starting a new training program, and stop if something hurts.</li>
<li>Recipes and food estimates are AI-generated and can be wrong. <strong>Always check ingredients yourself before cooking or eating.</strong> If you have a food allergy, do not rely on this app alone to keep an allergen out of your meal.</li>
</ul>
<h2>Children</h2><p>WeightProgram is not directed to children under 13.</p>
<h2>Contact</h2><p>Questions: <a href="mailto:privacy@glpsteel.com">privacy@glpsteel.com</a>. You can delete your account in the app without contacting us.</p>
</body></html>"""

_SUPPORT_HTML = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>WeightProgram — Support</title>
<style>body{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;max-width:640px;margin:40px auto;padding:0 20px;line-height:1.6;color:#1a1a1a}h1{font-size:28px}</style></head><body>
<h1>WeightProgram Support</h1><p>Need help? Email <a href="mailto:support@glpsteel.com">support@glpsteel.com</a>.</p>
<h2>How the app works</h2><ul>
<li><strong>Sign in:</strong> enter your email; we send a 6-digit code — no password.</li>
<li><strong>Scan equipment:</strong> photograph your weights; confirm what we detect.</li>
<li><strong>Programs:</strong> 3/4/5-day programs from your equipment and habits.</li>
<li><strong>Logging:</strong> record sets/reps/effort; the app suggests when to add load.</li></ul>
<h2>Health &amp; safety</h2>
<p>WeightProgram provides general fitness and nutrition information — <strong>not medical advice</strong>. Protein targets come from your body weight alone and don't account for health conditions; talk to your doctor or dietitian, especially if you take GLP-1 or other prescription medication. Check with your doctor before starting a new training program. Recipes are AI-generated and can be wrong, so always check ingredients yourself before cooking or eating — if you have a food allergy, don't rely on this app alone to keep an allergen out of your meal.</p>
<h2>Delete your account</h2>
<p>In the app: <strong>Home &rarr; menu (&#8942;) &rarr; Delete account</strong>. Confirm twice and you're done — no email needed.</p>
<p>You're signed out everywhere straight away, and your data is permanently deleted after a 30-day grace period. Changed your mind? Sign back in before then and choose &ldquo;Keep my account&rdquo;. We'll email you when deletion is scheduled and again when it's finished.</p>
<p>Trouble signing in to delete it? Email <a href="mailto:support@glpsteel.com">support@glpsteel.com</a> from your account email.</p>
</body></html>"""


@app.get("/privacy", response_class=HTMLResponse, include_in_schema=False)
async def privacy():
    """Public privacy policy page (linked from the App Store listing)."""
    return _PRIVACY_HTML


@app.get("/support", response_class=HTMLResponse, include_in_schema=False)
async def support():
    """Public support/contact page (linked from the App Store listing)."""
    return _SUPPORT_HTML

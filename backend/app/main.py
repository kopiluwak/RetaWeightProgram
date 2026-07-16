"""FastAPI application entrypoint.

Wires all feature routers onto one app, runs the DB bootstrap on startup,
and serves the static privacy/support pages required for App Store review.
"""
from __future__ import annotations
from fastapi.responses import HTMLResponse

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import get_settings
from .database import init_models
from .routers import analytics, auth, gamification, inventory, nutrition, onboarding, programs, workouts

logging.basicConfig(level=logging.INFO)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Convenience bootstrap; production should use Alembic migrations instead.
    await init_models()
    yield


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
<h1>WeightProgram Privacy Policy</h1><p class="muted">Last updated: July 1, 2026</p>
<p>WeightProgram ("we," "us") builds resistance-training programs from photos of your equipment and helps you track your workouts. This policy explains what we collect, why, and your choices. We designed the app to collect as little as possible.</p>
<h2>Information we collect</h2><ul>
<li><strong>Email address</strong> — to create your account and send one-time login codes. Login is passwordless; we do not store passwords.</li>
<li><strong>Phone number (optional)</strong> — only if you choose to add it.</li>
<li><strong>Equipment photos</strong> — sent for automated recognition. Stored only if you opt in to help improve recognition; otherwise used to produce your inventory and not retained.</li>
<li><strong>Training data</strong> — your equipment inventory, generated programs, and logged workouts. We store a general training context only. <strong>We do not collect or store any medication information.</strong></li>
<li><strong>Account identifier</strong> — a user ID we generate for you.</li></ul>
<h2>How we use it</h2><p>Solely to operate the app: authenticate you, recognize equipment, generate and adjust programs, and track workouts. With your consent, stored photos help improve recognition.</p>
<h2>What we do NOT do</h2><ul><li>We do <strong>not</strong> sell your data.</li><li>We do <strong>not</strong> share your data or photos for advertising.</li><li>We do <strong>not</strong> track you across other apps or websites.</li></ul>
<h2>Service providers</h2><p>We use Amazon Web Services to host the app, store data, send login emails, and perform equipment recognition, within our controlled environment.</p>
<h2>Security</h2><p>Data is encrypted in transit and at rest. Login tokens are stored in your device's secure storage.</p>
<h2>Your choices</h2><ul><li>Photo storage is opt-in; recognition works either way.</li><li>You may request deletion of your account and data at any time.</li></ul>
<h2>Children</h2><p>WeightProgram is not directed to children under 13.</p>
<h2>Contact</h2><p>Questions or deletion requests: <a href="mailto:privacy@glpsteel.com">privacy@glpsteel.com</a>.</p>
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
<h2>Delete your account</h2><p>Email <a href="mailto:support@glpsteel.com">support@glpsteel.com</a> from your account email.</p>
</body></html>"""


@app.get("/privacy", response_class=HTMLResponse, include_in_schema=False)
async def privacy():
    """Public privacy policy page (linked from the App Store listing)."""
    return _PRIVACY_HTML


@app.get("/support", response_class=HTMLResponse, include_in_schema=False)
async def support():
    """Public support/contact page (linked from the App Store listing)."""
    return _SUPPORT_HTML

"""Auth router: passwordless OTP registration + login, token refresh, logout.

Flow (spec F3/F4):
  POST /auth/request-otp  -> create user if new, email a 6-digit code
  POST /auth/verify-otp   -> validate code, mark verified, issue token pair
  POST /auth/refresh      -> rotate refresh token, issue new pair (reuse = revoke family)
  POST /auth/logout       -> revoke this refresh token, or everywhere (epoch bump)
"""
from __future__ import annotations

import datetime as dt
import logging
import secrets as _secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings, get_settings
from ..database import get_db
from ..deps import get_email_sender
from ..email_sender import EmailSender
from ..models import OtpCode, RefreshToken, User
from ..schemas import LogoutIn, MessageOut, RefreshIn, RequestOtpIn, TokenPair, VerifyOtpIn
from ..security import (
    generate_otp_code,
    generate_refresh_token,
    mint_access_token,
    refresh_expiry,
    sha256_hex,
)

router = APIRouter(prefix="/auth", tags=["auth"])

_log = logging.getLogger(__name__)


def _now() -> dt.datetime:
    """Timezone-aware UTC now."""
    return dt.datetime.now(dt.timezone.utc)


# --- Reviewer-bypass throttle -------------------------------------------------
# The bypass skips the OtpCode table entirely, so it also skips that table's
# attempt counter and hourly rate limit. `review_code` is now required to be
# long and random (config.Settings.MIN_REVIEW_CODE_LENGTH), which already makes
# brute force impractical — this throttle exists so a scripted attempt is slow
# and loud as well. In-process on purpose: it only has to outlast a burst, and
# every attempt is logged regardless of which task handled it.
_REVIEW_FAILURES: list[dt.datetime] = []
_REVIEW_MAX_FAILURES = 5
_REVIEW_LOCKOUT = dt.timedelta(minutes=15)


def _review_locked_out() -> bool:
    """True when too many wrong review codes were presented recently."""
    cutoff = _now() - _REVIEW_LOCKOUT
    _REVIEW_FAILURES[:] = [t for t in _REVIEW_FAILURES if t >= cutoff]
    return len(_REVIEW_FAILURES) >= _REVIEW_MAX_FAILURES


async def _issue_token_pair(db: AsyncSession, user: User, settings: Settings,
                            family_id: str | None = None) -> TokenPair:
    """Mint an access JWT + new refresh token (hashed at rest) and commit.

    Passing `family_id` keeps a rotated refresh token in the same family so
    reuse detection can revoke the whole lineage.
    """
    raw_refresh = generate_refresh_token()
    rt = RefreshToken(
        user_id=user.id,
        token_hash=sha256_hex(raw_refresh),
        expires_at=refresh_expiry(),
    )
    if family_id:
        rt.family_id = family_id
    db.add(rt)
    access, expires_in = mint_access_token(user.id, user.token_epoch)
    await db.commit()
    return TokenPair(access_token=access, refresh_token=raw_refresh, expires_in=expires_in)


@router.post("/request-otp", response_model=MessageOut)
async def request_otp(
    body: RequestOtpIn,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    email_sender: EmailSender = Depends(get_email_sender),
):
    """Start login: create the user if new, then email a one-time code.

    Always returns the same neutral message so the endpoint can't be used to
    probe which emails have accounts.
    """
    email = body.email.lower()
    # Reviewer bypass (App Store review only): ensure the account exists and skip
    # the real OTP + email send. An unconfigured or EXPIRED bypass is not an
    # error — it falls through to the normal OTP path below, so the review
    # account keeps working as an ordinary account once the window closes.
    armed, reason = settings.review_bypass_state()
    if armed and email == settings.review_email.lower():
        _log.warning("reviewer bypass: OTP request short-circuited (%s)", reason)
        user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if user is None:
            db.add(User(email=email))
            await db.commit()
        return MessageOut(message="If that email is valid, a verification code has been sent.")

    # Find-or-create the user (email-only signup).
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is None:
        user = User(email=email, phone=body.phone)
        db.add(user)
        await db.flush()
    elif body.phone and not user.phone:
        user.phone = body.phone  # optional add-on (F6)

    # --- Rate limiting (F3) ---
    window_start = _now() - dt.timedelta(hours=1)
    recent = (await db.execute(
        select(OtpCode).where(OtpCode.email == email, OtpCode.created_at >= window_start)
    )).scalars().all()
    if len(recent) >= settings.otp_requests_per_hour:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many code requests; try later")
    if recent:
        newest = max(r.created_at for r in recent)
        if newest.tzinfo is None:
            newest = newest.replace(tzinfo=dt.timezone.utc)
        if (_now() - newest).total_seconds() < settings.otp_request_cooldown_seconds:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Please wait before requesting another code")

    code = generate_otp_code()
    db.add(OtpCode(
        email=email,
        code_hash=sha256_hex(code),
        expires_at=_now() + dt.timedelta(minutes=settings.otp_ttl_minutes),
    ))
    await db.commit()

    email_sender.send_otp(email, code)
    return MessageOut(message="If that email is valid, a verification code has been sent.")


@router.post("/verify-otp", response_model=TokenPair)
async def verify_otp(
    body: VerifyOtpIn,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Complete login: validate the code and issue an access/refresh pair."""
    email = body.email.lower()
    # Reviewer bypass (App Store review only): accept the rotating review code for
    # the review account. Guarded four ways — the bypass must be armed (set, long
    # enough, and inside its expiry window), repeated misses lock the path out,
    # the comparison is constant-time, and both hit and miss are logged. A miss
    # falls through to the normal OTP path below, which rejects it.
    armed, reason = settings.review_bypass_state()
    if armed and email == settings.review_email.lower():
        if _review_locked_out():
            _log.warning("reviewer bypass: locked out after %d failures", _REVIEW_MAX_FAILURES)
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                                "Too many attempts; try again later")
        if _secrets.compare_digest(body.code, settings.review_code):
            _REVIEW_FAILURES.clear()
            _log.warning("reviewer bypass: login ACCEPTED for %s (%s)", email, reason)
            user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
            if user is None:
                user = User(email=email)
                db.add(user)
                await db.flush()
            user.email_verified = True
            return await _issue_token_pair(db, user, settings)
        _REVIEW_FAILURES.append(_now())
        _log.warning("reviewer bypass: WRONG CODE presented for %s", email)
    otp = (await db.execute(
        select(OtpCode)
        .where(OtpCode.email == email, OtpCode.consumed.is_(False))
        .order_by(OtpCode.created_at.desc())
    )).scalars().first()

    if otp is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No active code; request a new one")

    expires_at = otp.expires_at if otp.expires_at.tzinfo else otp.expires_at.replace(tzinfo=dt.timezone.utc)
    if expires_at < _now():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Code expired; request a new one")
    if otp.attempts >= settings.otp_max_attempts:
        otp.consumed = True
        await db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Too many attempts; request a new code")

    if otp.code_hash != sha256_hex(body.code):
        otp.attempts += 1
        await db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Incorrect code")

    # Success: burn the code, mark verified.
    otp.consumed = True
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown email")
    user.email_verified = True
    return await _issue_token_pair(db, user, settings)


@router.post("/refresh", response_model=TokenPair)
async def refresh(
    body: RefreshIn,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Rotate a refresh token: retire the old one, return a fresh pair.

    Presenting an already-rotated token is treated as theft and revokes the
    entire token family.
    """
    token_hash = sha256_hex(body.refresh_token)
    rt = (await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )).scalar_one_or_none()

    if rt is None or rt.revoked:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")

    # Reuse detection: a token already rotated being presented again => theft.
    # Revoke the whole family.
    if rt.used:
        fam = (await db.execute(
            select(RefreshToken).where(RefreshToken.family_id == rt.family_id)
        )).scalars().all()
        for t in fam:
            t.revoked = True
        await db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token reuse detected; session revoked")

    expires_at = rt.expires_at if rt.expires_at.tzinfo else rt.expires_at.replace(tzinfo=dt.timezone.utc)
    if expires_at < _now():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token expired")

    # Mark rotated (used) but NOT revoked: a later replay of this token must hit
    # the `rt.used` reuse-detection branch above, not the `rt.revoked` reject.
    rt.used = True
    user = (await db.execute(select(User).where(User.id == rt.user_id))).scalar_one()
    return await _issue_token_pair(db, user, settings, family_id=rt.family_id)


@router.post("/logout", response_model=MessageOut)
async def logout(
    body: LogoutIn,
    db: AsyncSession = Depends(get_db),
):
    """Revoke this device's refresh token, or every session if `everywhere`."""
    if body.everywhere:
        # Need the user; resolve via the supplied refresh token.
        if not body.refresh_token:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "refresh_token required for logout-everywhere")
        rt = (await db.execute(
            select(RefreshToken).where(RefreshToken.token_hash == sha256_hex(body.refresh_token))
        )).scalar_one_or_none()
        if rt is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")
        user = (await db.execute(select(User).where(User.id == rt.user_id))).scalar_one()
        user.token_epoch += 1  # instantly invalidates all access tokens (F4)
        fam = (await db.execute(
            select(RefreshToken).where(RefreshToken.user_id == user.id)
        )).scalars().all()
        for t in fam:
            t.revoked = True
        await db.commit()
        return MessageOut(message="Logged out on all devices.")

    if body.refresh_token:
        rt = (await db.execute(
            select(RefreshToken).where(RefreshToken.token_hash == sha256_hex(body.refresh_token))
        )).scalar_one_or_none()
        if rt:
            rt.revoked = True
            await db.commit()
    return MessageOut(message="Logged out.")

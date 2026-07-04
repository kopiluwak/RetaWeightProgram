"""Auth router: passwordless OTP registration + login, token refresh, logout.

Flow (spec F3/F4):
  POST /auth/request-otp  -> create user if new, email a 6-digit code
  POST /auth/verify-otp   -> validate code, mark verified, issue token pair
  POST /auth/refresh      -> rotate refresh token, issue new pair (reuse = revoke family)
  POST /auth/logout       -> revoke this refresh token, or everywhere (epoch bump)
"""
from __future__ import annotations

import datetime as dt

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


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


async def _issue_token_pair(db: AsyncSession, user: User, settings: Settings,
                            family_id: str | None = None) -> TokenPair:
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
    email = body.email.lower()
# Reviewer bypass: ensure the account exists, skip the real OTP + email send.
    if settings.review_email and email == settings.review_email.lower():
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
    email = body.email.lower()
 # Reviewer bypass: accept the fixed code for the review email only.
    if (settings.review_email and email == settings.review_email.lower()
            and settings.review_code and body.code == settings.review_code):
        user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if user is None:
            user = User(email=email)
            db.add(user)
            await db.flush()
        user.email_verified = True
        return await _issue_token_pair(db, user, settings)
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

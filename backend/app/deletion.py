"""Account deletion: grace window, anonymising fold, and the purge job.

App Store Review Guideline 5.1.1(v) requires that an app which supports account
creation lets the user *initiate* deletion from inside the app. A support-email
flow is explicitly not sufficient on its own.

Shape of the flow:

  1. User confirms deletion in the app -> ``request_deletion`` stamps
     ``User.deletion_requested_at`` and revokes every session immediately
     (refresh tokens revoked + ``token_epoch`` bumped, so outstanding access
     tokens die at the next request). The rows are still there.
  2. For GRACE_PERIOD_DAYS the account is recoverable: signing back in lands on
     the restore screen, and ``cancel_deletion`` clears the timestamp.
  3. After the window, ``purge_user`` runs: consented capture images are deleted
     from S3, the user's logged sets are folded into the anonymous histogram, and
     the ``users`` row is deleted. Every user-owned table declares
     ``ondelete="CASCADE"`` on ``user_id``, so that single delete removes habits,
     inventories, programs, workouts, sets, nutrition, weights, pantry, recipes,
     protein logs and both badge tables. ``SetLog`` cascades transitively via
     ``workout_sessions``.

Why 30 days: Apple does not publish a maximum grace period — it only requires
that the delay is disclosed to the user and complies with local law. The binding
constraint is GDPR Article 12(3), which gives a controller one month to action an
erasure request. 30 days sits inside that.

What survives, and why it is not personal data: only ``ExerciseStatBin`` counts.
See that model's docstring — the fold increments shared counters rather than
copying rows, so no per-person structure remains to re-identify. Bodyweight,
food and protein logs, dietary restrictions and allergies (GDPR Art. 9 special
category), equipment photos and every identifier are hard-deleted.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging

from sqlalchemy import delete as sa_delete
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .database import SessionLocal
from .email_sender import build_email_sender
from .models import CaptureSession, ExerciseStatBin, RefreshToken, SetLog, User, UserHabits, WorkoutSession
from .storage import build_image_storage

_log = logging.getLogger(__name__)

#: Days between the user confirming deletion and the data actually going.
GRACE_PERIOD_DAYS = 30

#: How often the background job looks for accounts that are due.
PURGE_INTERVAL_SECONDS = 6 * 60 * 60


def _now() -> dt.datetime:
    """Timezone-aware UTC now."""
    return dt.datetime.now(dt.timezone.utc)


def _aware(value: dt.datetime) -> dt.datetime:
    """Coerce a possibly-naive DB timestamp to UTC-aware.

    Rows written before the column was timezone-aware (and SQLite in tests) can
    come back naive; comparing those to an aware ``now()`` raises TypeError.
    """
    return value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)


def scheduled_purge_at(requested_at: dt.datetime) -> dt.datetime:
    """When the account becomes eligible for purge."""
    return _aware(requested_at) + dt.timedelta(days=GRACE_PERIOD_DAYS)


def is_due(requested_at: dt.datetime | None, now: dt.datetime | None = None) -> bool:
    """True when the grace window has fully elapsed."""
    if requested_at is None:
        return False
    return (now or _now()) >= scheduled_purge_at(requested_at)


# ----------------------------------------------------------------------------
# Request / cancel
# ----------------------------------------------------------------------------
async def request_deletion(db: AsyncSession, user: User) -> dt.datetime:
    """Start the grace window and kill every live session. Returns the purge date.

    Idempotent: asking twice does not extend or reset the window, so a user can't
    accidentally keep pushing their own deletion date into the future by tapping
    the button again.
    """
    if user.deletion_requested_at is None:
        user.deletion_requested_at = _now()

    # Revoke everywhere. The account stays reachable via a fresh OTP login (that
    # is how the user cancels), but existing devices are signed out at once.
    tokens = (await db.execute(
        select(RefreshToken).where(RefreshToken.user_id == user.id)
    )).scalars().all()
    for t in tokens:
        t.revoked = True
    user.token_epoch += 1

    await db.commit()
    scheduled = scheduled_purge_at(user.deletion_requested_at)

    # Notify. A failed send must not fail the request — the deletion is already
    # committed, and refusing here would leave the user unable to retry.
    try:
        build_email_sender(get_settings()).send_deletion_scheduled(
            user.email, scheduled.date().isoformat()
        )
    except Exception as exc:  # pragma: no cover - network path
        _log.error("deletion-scheduled email failed: %s", exc)

    _log.info("account deletion requested; purge scheduled for %s", scheduled.date().isoformat())
    return scheduled


async def cancel_deletion(db: AsyncSession, user: User) -> None:
    """Clear a pending deletion. No-op if none is pending."""
    if user.deletion_requested_at is None:
        return
    user.deletion_requested_at = None
    await db.commit()
    _log.info("account deletion cancelled")


# ----------------------------------------------------------------------------
# The anonymising fold
# ----------------------------------------------------------------------------
def tally_sets(rows, experience: str, days_per_week: int) -> dict[tuple, int]:
    """Collapse set rows into ``{dimension_tuple: count}``. Pure — no DB.

    This is the step that actually does the anonymising, so it is kept separate
    and unit-tested. Two properties matter:

      * Identical sets MERGE into one bin with a count. That is what destroys the
        per-person grouping — after the merge there is no way to tell whether a
        bin's 40 observations came from one person or forty.
      * Every dimension is non-null. ``SetLog.weight`` is nullable (bodyweight
        movements); it maps to 0.0, because a NULL would never match in the
        unique constraint and would silently produce one row per set.
    """
    tally: dict[tuple, int] = {}
    for s in rows:
        key = (
            s.exercise_name,
            round(float(s.weight or 0.0), 1),  # NULL weight (bodyweight) -> 0.0
            int(s.reps),
            int(s.rir if s.rir is not None else 2),
            experience or "unknown",
            int(days_per_week or 0),
        )
        tally[key] = tally.get(key, 0) + 1
    return tally


async def fold_sets_into_stats(db: AsyncSession, user_id: str) -> int:
    """Fold one user's logged sets into the global histogram. Returns sets folded.

    This is the only retention path. It must run BEFORE the user row is deleted,
    because the sets cascade away with it.
    """
    habits = (await db.execute(
        select(UserHabits).where(UserHabits.user_id == user_id)
    )).scalar_one_or_none()
    experience = (habits.experience if habits else "unknown") or "unknown"
    days_per_week = (habits.days_per_week if habits else 0) or 0

    rows = (await db.execute(
        select(SetLog)
        .join(WorkoutSession, SetLog.session_id == WorkoutSession.id)
        .where(WorkoutSession.user_id == user_id)
    )).scalars().all()

    # Tally in memory first so one user contributes a single increment per bin
    # rather than one round-trip per set.
    tally = tally_sets(rows, experience, days_per_week)

    for (name, weight, reps, rir, exp, dpw), count in tally.items():
        existing = (await db.execute(
            select(ExerciseStatBin).where(
                ExerciseStatBin.exercise_name == name,
                ExerciseStatBin.weight_lb == weight,
                ExerciseStatBin.reps == reps,
                ExerciseStatBin.rir == rir,
                ExerciseStatBin.experience == exp,
                ExerciseStatBin.days_per_week == dpw,
            )
        )).scalar_one_or_none()
        if existing is None:
            db.add(ExerciseStatBin(
                exercise_name=name, weight_lb=weight, reps=reps, rir=rir,
                experience=exp, days_per_week=dpw, observations=count,
            ))
        else:
            existing.observations += count

    return len(rows)


# ----------------------------------------------------------------------------
# Purge
# ----------------------------------------------------------------------------
async def _delete_stored_images(db: AsyncSession, user_id: str) -> int:
    """Delete this user's consented capture images from S3/disk. Returns count.

    Best-effort per key: one dead object must not strand the whole purge, or a
    user could become permanently undeletable.
    """
    settings = get_settings()
    storage = build_image_storage(settings)
    sessions = (await db.execute(
        select(CaptureSession).where(CaptureSession.user_id == user_id)
    )).scalars().all()

    deleted = 0
    for cs in sessions:
        for key in (cs.image_keys or []):
            try:
                storage.delete(key)
                deleted += 1
            except Exception as exc:  # pragma: no cover - network path
                _log.error("purge: failed to delete image %s: %s", key, exc)
    return deleted


async def purge_user(db: AsyncSession, user: User) -> dict:
    """Hard-delete one account. Assumes the grace window has already elapsed.

    Order matters: images and the stats fold both need rows that the final
    delete destroys.
    """
    user_id = user.id
    images = await _delete_stored_images(db, user_id)
    sets = await fold_sets_into_stats(db, user_id)

    # Raw delete rather than db.delete(user): the ORM cascade would eagerly load
    # every collection, while the DB-level ON DELETE CASCADE on each user_id FK
    # does the same work in one statement.
    await db.execute(sa_delete(User).where(User.id == user_id))

    # OTP codes key off the email, not a user_id FK, so no cascade reaches them.
    await db.execute(
        text("DELETE FROM otp_codes WHERE email = :email"), {"email": user.email}
    )

    await db.commit()

    # Confirm completion, as Apple asks. Sent AFTER the commit so we never
    # promise a deletion that then rolled back. This is the last use of the
    # address before it is gone from our records.
    try:
        build_email_sender(get_settings()).send_deletion_complete(user.email)
    except Exception as exc:  # pragma: no cover - network path
        _log.error("deletion-complete email failed: %s", exc)

    _log.info("purged account: %d images deleted, %d sets folded into stats", images, sets)
    return {"images_deleted": images, "sets_folded": sets}


async def purge_due_accounts() -> int:
    """Purge every account whose grace window has elapsed. Returns how many."""
    cutoff = _now() - dt.timedelta(days=GRACE_PERIOD_DAYS)
    purged = 0
    async with SessionLocal() as db:
        due = (await db.execute(
            select(User).where(
                User.deletion_requested_at.is_not(None),
                User.deletion_requested_at <= cutoff,
            )
        )).scalars().all()
        for user in due:
            email = user.email
            try:
                await purge_user(db, user)
                purged += 1
            except Exception as exc:  # pragma: no cover
                await db.rollback()
                _log.exception("purge failed for one account (%s): %s", email, exc)
    if purged:
        _log.info("purge sweep complete: %d account(s) removed", purged)
    return purged


async def purge_loop() -> None:
    """Background sweep, started from main.py's lifespan.

    Several ECS tasks each run their own copy. That is safe: the sweep selects
    then deletes, so a loser simply finds nothing to do, and a failure on one
    account rolls back only that account.
    """
    while True:
        try:
            await purge_due_accounts()
        except asyncio.CancelledError:
            raise
        except Exception:  # pragma: no cover - never let the loop die
            _log.exception("purge sweep raised; continuing")
        await asyncio.sleep(PURGE_INTERVAL_SECONDS)

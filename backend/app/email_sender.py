"""Email delivery, abstracted behind an interface (spec: swappable provider).

Default implementation is AWS SES. A dev sink prints to stdout so the app runs
locally without SES configured. Swapping providers = one new subclass.
"""
from __future__ import annotations

import abc
import logging

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from .config import Settings

logger = logging.getLogger("weightprogram.email")


class EmailSender(abc.ABC):
    """Provider-agnostic interface: OTP plus the two account-deletion notices."""

    @abc.abstractmethod
    def send_otp(self, to_email: str, code: str) -> None: ...

    @abc.abstractmethod
    def send_deletion_scheduled(self, to_email: str, purge_date: str) -> None:
        """Confirm a deletion request and state when it completes.

        Apple asks that the user be told how long deletion will take; this is
        also the safety net if someone else triggers it on their account.
        """

    @abc.abstractmethod
    def send_deletion_complete(self, to_email: str) -> None:
        """Confirm the purge actually happened (Apple asks for this)."""


class SesEmailSender(EmailSender):
    """Production sender backed by AWS SES."""

    def __init__(self, settings: Settings):
        self._from = settings.ses_from_email
        self._config_set = settings.ses_configuration_set
        self._client = boto3.client("ses", region_name=settings.aws_region)

    def _send(self, to_email: str, subject: str, body_text: str, body_html: str) -> None:
        """Single SES call site shared by every message type."""
        kwargs = {
            "Source": self._from,
            "Destination": {"ToAddresses": [to_email]},
            "Message": {
                "Subject": {"Data": subject},
                "Body": {"Text": {"Data": body_text}, "Html": {"Data": body_html}},
            },
        }
        if self._config_set:
            kwargs["ConfigurationSetName"] = self._config_set
        try:
            self._client.send_email(**kwargs)
        except (BotoCoreError, ClientError) as exc:  # pragma: no cover - network path
            logger.error("SES send failed for %s: %s", to_email, exc)
            raise

    def send_otp(self, to_email: str, code: str) -> None:
        self._send(
            to_email,
            "Your WeightProgram verification code",
            (
                f"Your verification code is {code}\n\n"
                "It expires in 10 minutes. If you didn't request this, ignore this email."
            ),
            (
                f"<p>Your verification code is</p>"
                f"<p style='font-size:28px;font-weight:700;letter-spacing:4px'>{code}</p>"
                f"<p>It expires in 10 minutes. If you didn't request this, you can ignore this email.</p>"
            ),
        )

    def send_deletion_scheduled(self, to_email: str, purge_date: str) -> None:
        self._send(
            to_email,
            "Your WeightProgram account is scheduled for deletion",
            (
                "You asked us to delete your WeightProgram account.\n\n"
                f"Your account and personal data will be permanently deleted on {purge_date}.\n"
                "You've been signed out on all devices.\n\n"
                "Changed your mind? Sign in again before that date and choose "
                "'Keep my account'. After that date it can't be undone.\n\n"
                "If you did NOT request this, sign in now and cancel it."
            ),
            (
                "<p>You asked us to delete your WeightProgram account.</p>"
                f"<p>Your account and personal data will be permanently deleted on "
                f"<strong>{purge_date}</strong>. You've been signed out on all devices.</p>"
                "<p>Changed your mind? Sign in again before that date and choose "
                "&ldquo;Keep my account&rdquo;. After that date it can&rsquo;t be undone.</p>"
                "<p>If you did <strong>not</strong> request this, sign in now and cancel it.</p>"
            ),
        )

    def send_deletion_complete(self, to_email: str) -> None:
        self._send(
            to_email,
            "Your WeightProgram account has been deleted",
            (
                "Your WeightProgram account and personal data have been permanently deleted.\n\n"
                "This includes your email address, workout history, bodyweight and food logs, "
                "dietary preferences, and any equipment photos you chose to share.\n\n"
                "We keep only anonymous, aggregated training statistics that can't be linked "
                "back to you or to any individual.\n\n"
                "Thanks for training with us."
            ),
            (
                "<p>Your WeightProgram account and personal data have been permanently deleted.</p>"
                "<p>This includes your email address, workout history, bodyweight and food logs, "
                "dietary preferences, and any equipment photos you chose to share.</p>"
                "<p>We keep only anonymous, aggregated training statistics that can&rsquo;t be "
                "linked back to you or to any individual.</p>"
                "<p>Thanks for training with us.</p>"
            ),
        )


class DevEmailSender(EmailSender):
    """Logs instead of sending. Used when EMAIL_DEV_MODE=true."""

    def send_otp(self, to_email: str, code: str) -> None:
        logger.warning("[DEV EMAIL] OTP for %s = %s", to_email, code)

    def send_deletion_scheduled(self, to_email: str, purge_date: str) -> None:
        logger.warning("[DEV EMAIL] deletion scheduled for %s on %s", to_email, purge_date)

    def send_deletion_complete(self, to_email: str) -> None:
        logger.warning("[DEV EMAIL] deletion complete for %s", to_email)


def build_email_sender(settings: Settings) -> EmailSender:
    """Factory: dev sink or real SES sender, per EMAIL_DEV_MODE."""
    if settings.email_dev_mode:
        return DevEmailSender()
    return SesEmailSender(settings)

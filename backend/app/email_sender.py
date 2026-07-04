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
    @abc.abstractmethod
    def send_otp(self, to_email: str, code: str) -> None: ...


class SesEmailSender(EmailSender):
    def __init__(self, settings: Settings):
        self._from = settings.ses_from_email
        self._config_set = settings.ses_configuration_set
        self._client = boto3.client("ses", region_name=settings.aws_region)

    def send_otp(self, to_email: str, code: str) -> None:
        subject = "Your WeightProgram verification code"
        body_text = (
            f"Your verification code is {code}\n\n"
            "It expires in 10 minutes. If you didn't request this, ignore this email."
        )
        body_html = (
            f"<p>Your verification code is</p>"
            f"<p style='font-size:28px;font-weight:700;letter-spacing:4px'>{code}</p>"
            f"<p>It expires in 10 minutes. If you didn't request this, you can ignore this email.</p>"
        )
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


class DevEmailSender(EmailSender):
    """Logs the code instead of sending. Used when EMAIL_DEV_MODE=true."""

    def send_otp(self, to_email: str, code: str) -> None:
        logger.warning("[DEV EMAIL] OTP for %s = %s", to_email, code)


def build_email_sender(settings: Settings) -> EmailSender:
    if settings.email_dev_mode:
        return DevEmailSender()
    return SesEmailSender(settings)

"""Application configuration, loaded from environment variables.

All secrets and environment-specific values live here. Nothing else in the
codebase reads os.environ directly.
"""
import datetime as dt
from functools import lru_cache
from typing import ClassVar

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings.

    Values are read from environment variables (or a local ``.env`` file),
    falling back to the development defaults below. Field names map to
    UPPER_CASE env vars (e.g. ``database_url`` <- ``DATABASE_URL``).
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Core ---
    app_name: str = "WeightProgram API"
    environment: str = "development"  # development | production

    # --- Database (Postgres) ---
    # Example: postgresql+asyncpg://user:pass@localhost:5432/weightprogram
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/weightprogram"

    # --- JWT / sessions (spec F4) ---
    jwt_secret: str = "CHANGE-ME-IN-ENV"  # HMAC secret for access tokens
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 45

    # --- OTP (spec F3) ---
    otp_ttl_minutes: int = 10
    otp_max_attempts: int = 5          # verify attempts before a code is burned
    otp_request_cooldown_seconds: int = 30   # min gap between code requests per email
    otp_requests_per_hour: int = 5     # rate limit per email

    # --- AWS SES (spec F5 / email) ---
    aws_region: str = "us-east-1"
    ses_from_email: str = "no-reply@example.com"  # MUST be a verified SES identity
    ses_configuration_set: str | None = None
    # If true, OTP codes are logged to stdout instead of emailed (local dev without SES).
    email_dev_mode: bool = True

    # --- Image storage (spec F8 / R1a) ---
    image_storage_backend: str = "local"  # local | s3
    s3_bucket: str = "weightprogram-captures"
    local_image_dir: str = "./_local_images"

    # --- Vision recognition (spec R1 / R1b: Bedrock + Claude) ---
    vision_provider: str = "stub"  # stub | bedrock
    # Set to a Claude multimodal model id or inference-profile ARN available in
    # YOUR Bedrock account/region (check the Bedrock console — ids differ per
    # region and account). Example shape: "anthropic.claude-3-5-sonnet-20241022-v2:0".
    bedrock_model_id: str = "anthropic.claude-3-5-sonnet-20241022-v2:0"
    bedrock_max_tokens: int = 1024

    # --- Defaults for onboarding habits (spec onboarding decision) ---
    default_session_minutes: int = 60
    default_experience: str = "conservative"  # conservative | intermediate | advanced
    # --- App Store review: time-boxed reviewer bypass ---
    # An App Review tester cannot receive our OTP email, so ONE account may log
    # in with a fixed code. This is a real backdoor, so it is deliberately hard
    # to leave switched on by accident:
    #   * review_bypass_until is a HARD expiry. Past that date the code path is
    #     inert even if the other two vars are still on the task definition.
    #   * review_code must be at least MIN_REVIEW_CODE_LENGTH characters. The
    #     old 6-digit code was a 10^6 keyspace on an unthrottled endpoint.
    #   * every use, and every miss, is logged at WARNING.
    # Generate a fresh code per submission (`openssl rand -hex 16`), set it as an
    # ECS task-def env var, and NEVER commit it. See OPERATIONS_RUNBOOK.md §D7.
    review_email: str = ""
    review_code: str = ""
    review_bypass_until: str = ""  # ISO date "YYYY-MM-DD" (UTC, inclusive)

    MIN_REVIEW_CODE_LENGTH: ClassVar[int] = 24

    def review_bypass_state(self, today: dt.date | None = None) -> tuple[bool, str]:
        """Return ``(armed, reason)`` for the reviewer bypass.

        Armed only when every guard passes. The reason string is safe to log —
        it never contains the code itself. Callers MUST treat a False as
        "fall through to the normal OTP path", not as an error.
        """
        if not (self.review_email and self.review_code and self.review_bypass_until):
            return False, "not configured"
        if len(self.review_code) < self.MIN_REVIEW_CODE_LENGTH:
            return False, (
                f"REVIEW_CODE is shorter than {self.MIN_REVIEW_CODE_LENGTH} chars — refusing to arm"
            )
        try:
            until = dt.date.fromisoformat(self.review_bypass_until)
        except ValueError:
            return False, "REVIEW_BYPASS_UNTIL is not an ISO date (YYYY-MM-DD)"
        now = today or dt.datetime.now(dt.timezone.utc).date()
        if now > until:
            return False, f"expired {until.isoformat()}"
        return True, f"armed until {until.isoformat()}"


@lru_cache
def get_settings() -> Settings:
    """Return the singleton Settings instance (cached after first load)."""
    return Settings()

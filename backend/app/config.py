"""Application configuration, loaded from environment variables.

All secrets and environment-specific values live here. Nothing else in the
codebase reads os.environ directly.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
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
# App Store reviewer bypass — when both are set, this email + code logs in
    # without a real OTP send. Leave blank in normal operation.
    review_email: str = ""
    review_code: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()

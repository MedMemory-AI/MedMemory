import secrets
from datetime import datetime, timedelta, timezone


def generate_otp_code() -> str:
    """Produces a cryptographically random 6-digit numeric one-time password."""
    return f"{secrets.randbelow(1_000_000):06d}"


def otp_expiry(minutes: int) -> datetime:
    """Returns the UTC timestamp after which a generated OTP must be rejected."""
    return datetime.now(timezone.utc) + timedelta(minutes=minutes)

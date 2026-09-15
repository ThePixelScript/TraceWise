"""Token generation and validation for authentication."""

from __future__ import annotations

import hashlib
import time

# Default token expiration in seconds (1 hour)
DEFAULT_EXPIRY_SECONDS = 3600


def generate_token(user_id: str, expiry_seconds: int = DEFAULT_EXPIRY_SECONDS) -> str:
    """Generate a deterministic access token for the given user.

    The token encodes the user identifier and an expiration timestamp.
    Format: <user_id>:<expiry_timestamp>:<signature>
    """
    expiry_timestamp = int(time.time()) + expiry_seconds
    payload = f"{user_id}:{expiry_timestamp}"
    signature = hashlib.sha256(payload.encode()).hexdigest()[:16]
    return f"{payload}:{signature}"


def decode_token(token: str) -> dict:
    """Decode a token into its component parts.

    Returns a dictionary with user_id, expiry_timestamp, and signature.
    Raises ValueError if the token format is invalid.
    """
    parts = token.split(":")
    if len(parts) != 3:
        raise ValueError("Invalid token format.")
    return {
        "user_id": parts[0],
        "expiry_timestamp": int(parts[1]),
        "signature": parts[2],
    }


def is_token_expired(token: str) -> bool:
    """Check whether the given token has expired.

    Compares the token's embedded expiry timestamp against the current time.
    Returns True if the token is expired, False otherwise.
    """
    decoded = decode_token(token)
    return time.time() > decoded["expiry_timestamp"]

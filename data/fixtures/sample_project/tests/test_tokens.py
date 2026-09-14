"""Tests for token generation, decoding, and expiration."""

import time
from unittest.mock import patch

from src.auth.token import (
    DEFAULT_EXPIRY_SECONDS,
    decode_token,
    generate_token,
    is_token_expired,
)


def test_token_generation():
    """Verify that generate_token produces a well-formed token string."""
    token = generate_token(user_id="user-42")

    assert isinstance(token, str), "Token should be a string"
    parts = token.split(":")
    assert len(parts) == 3, "Token should have three colon-separated parts"
    assert parts[0] == "user-42", "First part should be the user ID"


def test_token_contains_expiry():
    """Verify that the token embeds a valid expiration timestamp."""
    before = int(time.time())
    token = generate_token(user_id="user-1", expiry_seconds=7200)
    decoded = decode_token(token)

    expected_min = before + 7200
    assert decoded["expiry_timestamp"] >= expected_min, (
        "Token expiry should be at least current time + expiry_seconds"
    )


def test_token_decode_roundtrip():
    """Verify that a generated token can be decoded back correctly."""
    token = generate_token(user_id="user-99", expiry_seconds=1800)
    decoded = decode_token(token)

    assert decoded["user_id"] == "user-99", "Decoded user_id should match"
    assert isinstance(decoded["expiry_timestamp"], int), (
        "Expiry timestamp should be an integer"
    )
    assert len(decoded["signature"]) == 16, "Signature should be 16 hex characters"


def test_invalid_token_format_raises():
    """Verify that a malformed token raises ValueError."""
    import pytest

    with pytest.raises(ValueError, match="Invalid token format"):
        decode_token("not-a-valid-token")


def test_expired_token():
    """Verify that a token with a past expiry is detected as expired."""
    # Generate a token that expired 10 seconds ago
    with patch("src.auth.token.time") as mock_time:
        mock_time.time.return_value = 1000000.0
        token = generate_token(user_id="user-1", expiry_seconds=60)

    # Now check expiration with current time well past the expiry
    with patch("src.auth.token.time") as mock_time:
        mock_time.time.return_value = 1000000.0 + 120
        assert is_token_expired(token) is True, "Token should be expired"


def test_valid_token_not_expired():
    """Verify that a freshly generated token is not expired."""
    token = generate_token(user_id="user-1", expiry_seconds=DEFAULT_EXPIRY_SECONDS)
    assert is_token_expired(token) is False, (
        "Freshly generated token should not be expired"
    )

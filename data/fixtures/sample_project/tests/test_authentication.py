"""Tests for user authentication and login flows."""

from src.auth.password import hash_password
from src.auth.service import AuthenticationService


def _build_user_store(email: str, password: str, user_id: str = "user-1") -> dict:
    """Helper to build a user store with one user."""
    return {
        email: {
            "user_id": user_id,
            "password_hash": hash_password(password),
            "display_name": "Test User",
        }
    }


def test_successful_login():
    """Verify that valid credentials produce a successful result with a token."""
    store = _build_user_store("alice@example.com", "correct-password")
    service = AuthenticationService(user_store=store)
    result = service.authenticate_user("alice@example.com", "correct-password")

    assert result.success is True, "Expected authentication to succeed"
    assert result.token is not None, "Expected a token to be returned"
    assert result.status_code == 200, "Expected HTTP 200 for successful login"


def test_invalid_password_returns_401():
    """Verify that a wrong password returns HTTP 401 Unauthorized."""
    store = _build_user_store("alice@example.com", "correct-password")
    service = AuthenticationService(user_store=store)
    result = service.authenticate_user("alice@example.com", "wrong-password")

    assert result.success is False, "Expected authentication to fail"
    assert result.status_code == 401, "Expected HTTP 401 for invalid credentials"
    assert result.error_message is not None, "Expected an error message"


def test_unknown_user_returns_401():
    """Verify that an unknown email returns HTTP 401."""
    store = _build_user_store("alice@example.com", "password123")
    service = AuthenticationService(user_store=store)
    result = service.authenticate_user("nobody@example.com", "password123")

    assert result.success is False, "Expected authentication to fail for unknown user"
    assert result.status_code == 401, "Expected HTTP 401 for unknown user"
    assert "not found" in result.error_message.lower(), (
        "Expected error message to mention user not found"
    )


def test_authentication_attempt_is_recorded():
    """Verify that every authentication attempt is logged in the audit log."""
    store = _build_user_store("alice@example.com", "password123")
    service = AuthenticationService(user_store=store)

    service.authenticate_user("alice@example.com", "password123")
    service.authenticate_user("alice@example.com", "wrong-password")

    log = service.get_auth_log()
    assert len(log) == 2, "Expected two authentication attempts in the log"
    assert log[0]["success"] is True, "First attempt should have succeeded"
    assert log[1]["success"] is False, "Second attempt should have failed"


def test_rate_limited_user_is_blocked():
    """Verify that a user is blocked after too many failed attempts."""
    from src.security.rate_limiter import RateLimiter

    store = _build_user_store("alice@example.com", "correct-password")
    limiter = RateLimiter(max_failures=3, lockout_seconds=600)
    service = AuthenticationService(user_store=store, rate_limiter=limiter)

    # Exhaust the allowed failures
    for _ in range(3):
        service.authenticate_user("alice@example.com", "wrong-password")

    # Next attempt should be blocked even with the correct password
    result = service.authenticate_user("alice@example.com", "correct-password")
    assert result.success is False, "Expected blocked user to be rejected"
    assert result.status_code == 401, "Expected HTTP 401 for rate-limited user"


def test_password_is_hashed_not_stored_plaintext():
    """Verify that password storage does not contain the plaintext password."""
    plaintext = "correct-password"
    store = _build_user_store("alice@example.com", plaintext)

    stored_hash = store["alice@example.com"]["password_hash"]

    assert stored_hash != plaintext
    assert ":" in stored_hash
    assert len(stored_hash.split(":")) == 2

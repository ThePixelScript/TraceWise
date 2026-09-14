"""Tests for authentication rate limiting."""

import time
from unittest.mock import patch

from src.security.rate_limiter import RateLimiter


def test_initial_state_not_blocked():
    """Verify that a new email is not blocked."""
    limiter = RateLimiter()
    assert limiter.is_blocked("user@example.com") is False


def test_below_threshold_not_blocked():
    """Verify that fewer failures than the threshold do not block."""
    limiter = RateLimiter(max_failures=5)
    for _ in range(4):
        limiter.record_failure("user@example.com")
    assert limiter.is_blocked("user@example.com") is False


def test_reaching_threshold_blocks():
    """Verify that reaching the failure threshold triggers a block."""
    limiter = RateLimiter(max_failures=3, lockout_seconds=600)
    for _ in range(3):
        limiter.record_failure("user@example.com")
    assert limiter.is_blocked("user@example.com") is True


def test_lockout_expires():
    """Verify that the lockout expires after the configured duration."""
    limiter = RateLimiter(max_failures=2, lockout_seconds=60)
    limiter.record_failure("user@example.com")
    limiter.record_failure("user@example.com")

    assert limiter.is_blocked("user@example.com") is True

    # Simulate time passing beyond the lockout duration
    with patch("src.security.rate_limiter.time") as mock_time:
        mock_time.time.return_value = time.time() + 120
        assert limiter.is_blocked("user@example.com") is False


def test_reset_clears_failures():
    """Verify that resetting clears the failure count."""
    limiter = RateLimiter(max_failures=3)
    for _ in range(2):
        limiter.record_failure("user@example.com")
    limiter.reset("user@example.com")

    assert limiter.get_failure_count("user@example.com") == 0
    assert limiter.is_blocked("user@example.com") is False


def test_failure_count_tracking():
    """Verify that the failure counter increments correctly."""
    limiter = RateLimiter()
    assert limiter.get_failure_count("user@example.com") == 0

    limiter.record_failure("user@example.com")
    assert limiter.get_failure_count("user@example.com") == 1

    limiter.record_failure("user@example.com")
    assert limiter.get_failure_count("user@example.com") == 2


def test_separate_emails_tracked_independently():
    """Verify that rate limiting tracks each email separately."""
    limiter = RateLimiter(max_failures=2, lockout_seconds=600)
    limiter.record_failure("alice@example.com")
    limiter.record_failure("alice@example.com")
    limiter.record_failure("bob@example.com")

    assert limiter.is_blocked("alice@example.com") is True
    assert limiter.is_blocked("bob@example.com") is False

"""Rate limiting for failed authentication attempts."""

from __future__ import annotations

import time

# Default maximum consecutive failures before lockout
DEFAULT_MAX_FAILURES = 5

# Default lockout duration in seconds (5 minutes)
DEFAULT_LOCKOUT_SECONDS = 300


class RateLimiter:
    """Enforces rate limiting on repeated failed authentication attempts.

    Tracks consecutive failures per email address and blocks further
    attempts after the configured threshold is reached. The lockout
    expires after a configurable duration.
    """

    def __init__(
        self,
        max_failures: int = DEFAULT_MAX_FAILURES,
        lockout_seconds: int = DEFAULT_LOCKOUT_SECONDS,
    ) -> None:
        self._max_failures = max_failures
        self._lockout_seconds = lockout_seconds
        # Maps email -> {"count": int, "locked_at": float | None}
        self._attempts: dict[str, dict] = {}

    def record_failure(self, email: str) -> None:
        """Record a failed authentication attempt for the given email.

        Increments the failure counter. If the counter reaches the
        maximum allowed failures, the account is locked.
        """
        entry = self._attempts.setdefault(email, {"count": 0, "locked_at": None})
        entry["count"] += 1
        if entry["count"] >= self._max_failures:
            entry["locked_at"] = time.time()

    def is_blocked(self, email: str) -> bool:
        """Check whether the given email is currently blocked.

        Returns True if the failure count has reached the threshold
        and the lockout period has not yet elapsed.
        """
        entry = self._attempts.get(email)
        if entry is None:
            return False
        if entry["locked_at"] is None:
            return False
        elapsed = time.time() - entry["locked_at"]
        if elapsed >= self._lockout_seconds:
            # Lockout has expired — reset
            self.reset(email)
            return False
        return True

    def reset(self, email: str) -> None:
        """Reset the failure counter for the given email.

        Called after a successful authentication to clear any
        accumulated failure state.
        """
        self._attempts.pop(email, None)

    def get_failure_count(self, email: str) -> int:
        """Return the current consecutive failure count for the email."""
        entry = self._attempts.get(email)
        if entry is None:
            return 0
        return entry["count"]

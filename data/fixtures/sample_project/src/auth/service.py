"""Authentication service for verifying user credentials."""

from __future__ import annotations

from src.auth.password import verify_password
from src.auth.token import generate_token
from src.security.rate_limiter import RateLimiter

# HTTP status code for unauthorized access
HTTP_401_UNAUTHORIZED = 401


class AuthenticationResult:
    """Represents the outcome of an authentication attempt."""

    def __init__(
        self,
        success: bool,
        token: str | None = None,
        status_code: int = 200,
        error_message: str | None = None,
    ) -> None:
        self.success = success
        self.token = token
        self.status_code = status_code
        self.error_message = error_message


class AuthenticationService:
    """Service that handles user authentication against stored credentials."""

    def __init__(
        self,
        user_store: dict[str, dict],
        rate_limiter: RateLimiter | None = None,
        token_expiry_seconds: int = 3600,
    ) -> None:
        self._user_store = user_store
        self._rate_limiter = rate_limiter
        self._token_expiry_seconds = token_expiry_seconds
        self._auth_log: list[dict] = []

    def authenticate_user(self, email: str, password: str) -> AuthenticationResult:
        """Authenticate a user by email and password.

        Verifies the provided credentials against the stored user data.
        Records every authentication attempt for auditing purposes.
        Returns an AuthenticationResult with a token on success,
        or HTTP 401 status on failure.
        """
        # Check rate limiting before attempting authentication
        if self._rate_limiter and self._rate_limiter.is_blocked(email):
            self._record_attempt(email, success=False)
            return AuthenticationResult(
                success=False,
                status_code=HTTP_401_UNAUTHORIZED,
                error_message="Too many failed attempts. Account temporarily locked.",
            )

        # Look up user by email
        user = self._user_store.get(email)
        if user is None:
            self._record_attempt(email, success=False)
            if self._rate_limiter:
                self._rate_limiter.record_failure(email)
            return AuthenticationResult(
                success=False,
                status_code=HTTP_401_UNAUTHORIZED,
                error_message="User not found.",
            )

        # Verify password against stored hash
        stored_hash = user["password_hash"]
        if not verify_password(password, stored_hash):
            self._record_attempt(email, success=False)
            if self._rate_limiter:
                self._rate_limiter.record_failure(email)
            return AuthenticationResult(
                success=False,
                status_code=HTTP_401_UNAUTHORIZED,
                error_message="Invalid credentials.",
            )

        # Authentication successful — generate token
        token = generate_token(
            user_id=user["user_id"],
            expiry_seconds=self._token_expiry_seconds,
        )
        self._record_attempt(email, success=True)
        if self._rate_limiter:
            self._rate_limiter.reset(email)
        return AuthenticationResult(success=True, token=token)

    def _record_attempt(self, email: str, *, success: bool) -> None:
        """Record an authentication attempt in the audit log.

        Stores the email, outcome, and a monotonic counter as timestamp
        placeholder for deterministic testing.
        """
        import time

        self._auth_log.append(
            {
                "email": email,
                "success": success,
                "timestamp": time.time(),
            }
        )

    def get_auth_log(self) -> list[dict]:
        """Return the full authentication attempt audit log."""
        return list(self._auth_log)

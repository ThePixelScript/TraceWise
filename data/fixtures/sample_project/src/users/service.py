"""User profile management service."""

from __future__ import annotations


class UserProfile:
    """Represents a user's profile information."""

    def __init__(self, user_id: str, email: str, display_name: str) -> None:
        self.user_id = user_id
        self.email = email
        self.display_name = display_name

    def to_dict(self) -> dict:
        """Convert the profile to a plain dictionary."""
        return {
            "user_id": self.user_id,
            "email": self.email,
            "display_name": self.display_name,
        }


class UserService:
    """Service for managing user profiles and user lookup."""

    def __init__(self, user_store: dict[str, dict]) -> None:
        self._user_store = user_store

    def get_user_profile(self, user_id: str) -> UserProfile | None:
        """Retrieve a user's profile by their unique identifier.

        Returns a UserProfile if the user exists, or None if the user
        is not found in the store.
        """
        for _email, user_data in self._user_store.items():
            if user_data.get("user_id") == user_id:
                return UserProfile(
                    user_id=user_data["user_id"],
                    email=_email,
                    display_name=user_data.get("display_name", ""),
                )
        return None

    def find_user_by_email(self, email: str) -> dict | None:
        """Look up a user record by email address.

        This method is used internally for user validation and
        credential retrieval. Returns the raw user dict or None.
        """
        return self._user_store.get(email)

    def list_user_ids(self) -> list[str]:
        """Return a list of all user identifiers in the store.

        Useful for administrative reporting. Note: this method shares
        vocabulary with authentication ('user', 'list') but does NOT
        perform any credential verification or login logic.
        """
        return [data["user_id"] for data in self._user_store.values()]

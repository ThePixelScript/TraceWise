"""Tests for user profile retrieval and user lookup."""

from src.users.service import UserProfile, UserService


def _sample_store() -> dict:
    """Build a sample user store with two users."""
    return {
        "alice@example.com": {
            "user_id": "user-1",
            "password_hash": "fakehash:fakedigest",
            "display_name": "Alice Smith",
        },
        "bob@example.com": {
            "user_id": "user-2",
            "password_hash": "fakehash:fakedigest",
            "display_name": "Bob Jones",
        },
    }


def test_get_existing_user_profile():
    """Verify that an existing user's profile is returned correctly."""
    service = UserService(user_store=_sample_store())
    profile = service.get_user_profile("user-1")

    assert profile is not None, "Expected a profile for user-1"
    assert profile.email == "alice@example.com", "Expected Alice's email"
    assert profile.display_name == "Alice Smith", "Expected Alice's display name"


def test_unknown_user_returns_none():
    """Verify that requesting a nonexistent user returns None."""
    service = UserService(user_store=_sample_store())
    profile = service.get_user_profile("user-999")

    assert profile is None, "Expected None for unknown user ID"


def test_find_user_by_email():
    """Verify that a user can be found by email address."""
    service = UserService(user_store=_sample_store())
    user = service.find_user_by_email("bob@example.com")

    assert user is not None, "Expected to find Bob by email"
    assert user["user_id"] == "user-2", "Expected Bob's user ID"


def test_find_unknown_email_returns_none():
    """Verify that an unknown email returns None."""
    service = UserService(user_store=_sample_store())
    user = service.find_user_by_email("nobody@example.com")

    assert user is None, "Expected None for unknown email"


def test_list_user_ids():
    """Verify that all user IDs in the store are listed."""
    service = UserService(user_store=_sample_store())
    ids = service.list_user_ids()

    assert len(ids) == 2, "Expected two user IDs"
    assert "user-1" in ids, "Expected user-1 in the list"
    assert "user-2" in ids, "Expected user-2 in the list"


def test_user_profile_to_dict():
    """Verify that UserProfile.to_dict returns a correct dictionary."""
    profile = UserProfile(
        user_id="user-1", email="test@example.com", display_name="Test"
    )
    data = profile.to_dict()

    assert data["user_id"] == "user-1"
    assert data["email"] == "test@example.com"
    assert data["display_name"] == "Test"

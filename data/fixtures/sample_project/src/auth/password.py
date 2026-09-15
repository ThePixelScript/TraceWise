"""Password hashing and verification utilities."""

import hashlib
import os

# Salt length in bytes for password hashing
SALT_LENGTH = 16


def hash_password(plaintext: str) -> str:
    """Hash a plaintext password using SHA-256 with a random salt.

    The password is never stored in plaintext. The returned string
    contains the hex-encoded salt and digest separated by a colon.
    Format: <salt_hex>:<digest_hex>
    """
    salt = os.urandom(SALT_LENGTH)
    digest = hashlib.sha256(salt + plaintext.encode()).hexdigest()
    return f"{salt.hex()}:{digest}"


def verify_password(plaintext: str, stored_hash: str) -> bool:
    """Verify a plaintext password against a stored hash.

    Extracts the salt from the stored hash, re-computes the digest,
    and compares it to the stored digest.
    """
    parts = stored_hash.split(":")
    if len(parts) != 2:
        return False
    salt_hex, stored_digest = parts
    salt = bytes.fromhex(salt_hex)
    computed_digest = hashlib.sha256(salt + plaintext.encode()).hexdigest()
    return computed_digest == stored_digest

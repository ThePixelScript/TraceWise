"""Text normalization utilities for preprocessing.

Provides deterministic, stateless normalization functions that convert
raw text into a canonical form suitable for tokenization and retrieval.
"""

import re
import unicodedata


def normalize_unicode(text: str) -> str:
    """Apply Unicode NFC normalization.

    Converts composed and decomposed forms into a single canonical
    representation so that visually identical strings compare as equal.
    """
    return unicodedata.normalize("NFC", text)


def normalize_case(text: str) -> str:
    """Convert text to lowercase."""
    return text.lower()


def normalize_whitespace(text: str) -> str:
    """Collapse repeated whitespace and strip leading/trailing space.

    Replaces any run of whitespace characters (spaces, tabs, newlines)
    with a single space.
    """
    return re.sub(r"\s+", " ", text).strip()


def normalize_text(text: str) -> str:
    """Apply the full normalization pipeline.

    Pipeline order:
        1. Unicode NFC normalization
        2. Lowercase conversion
        3. Whitespace normalization
    """
    result = normalize_unicode(text)
    result = normalize_case(result)
    result = normalize_whitespace(result)
    return result


__all__ = [
    "normalize_case",
    "normalize_text",
    "normalize_unicode",
    "normalize_whitespace",
]

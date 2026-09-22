"""Identifier splitting and lexical tokenization for preprocessing.

Provides deterministic token extraction from natural-language text and
source-code identifiers.  Supports camelCase, PascalCase, snake_case,
and kebab-case splitting with correct acronym handling.
"""

import re

# ---------------------------------------------------------------------------
# Identifier splitting
# ---------------------------------------------------------------------------

# Pattern for splitting compound identifiers:
#   1. Lowercase followed by uppercase  (camelCase boundary)
#   2. Uppercase followed by uppercase + lowercase  (acronym boundary)
#   3. Digit followed by uppercase letter  (alphanumeric boundary)
_CAMEL_SPLIT_RE = re.compile(
    r"""
    (?<=[a-z])(?=[A-Z])          # camelCase: aB → a | B
    | (?<=[A-Z])(?=[A-Z][a-z])   # acronym:  ABc → A | Bc  (HTTPResponse)
    | (?<=[0-9])(?=[A-Z])        # digit-to-upper: 256H → 256 | H
    """,
    re.VERBOSE,
)


def split_identifier(identifier: str) -> list[str]:
    """Split a compound identifier into its constituent terms.

    Supports:
        - camelCase:   ``authenticateUser`` → ``["authenticate", "user"]``
        - PascalCase:  ``AuthenticationService`` → ``["authentication", "service"]``
        - snake_case:  ``get_user_profile`` → ``["get", "user", "profile"]``
        - kebab-case:  ``test-case-id`` → ``["test", "case", "id"]``
        - Acronyms:    ``parseHTTPResponse`` → ``["parse", "http", "response"]``
        - Alphanumeric: ``SHA256Hasher`` → ``["sha256", "hasher"]``

    Dunder names are handled by stripping leading/trailing underscores
    before splitting::

        ``__init__`` → ``["init"]``

    Short meaningful tokens (``id``, ``ip``, ``db``, ``v2``) are preserved.
    """
    if not identifier:
        return []

    # Strip leading/trailing underscores (e.g. __init__ → init)
    stripped = identifier.strip("_")
    if not stripped:
        return []

    # Split on underscores and hyphens first
    parts = re.split(r"[_\-]+", stripped)

    tokens: list[str] = []
    for part in parts:
        if not part:
            continue
        # Apply camelCase / PascalCase / acronym splitting
        sub_parts = _CAMEL_SPLIT_RE.split(part)
        for sp in sub_parts:
            if sp:
                tokens.append(sp.lower())

    return tokens


# ---------------------------------------------------------------------------
# Lexical tokenization
# ---------------------------------------------------------------------------

# Matches contiguous runs of Unicode alphanumeric characters (including
# underscores and hyphens that sit between word characters, so compound
# identifiers stay together for subsequent splitting).
_WORD_RE = re.compile(r"[^\W_]+(?:[_\-][^\W_]+)*")


def tokenize(text: str) -> list[str]:
    """Extract tokens from text.

    Operates on the original (case-preserving) text so that camelCase
    and PascalCase boundaries are detected before lowercasing.

    Steps:
        1. Extract word-like runs (alphanumeric, underscored, hyphenated).
        2. Split each run via :func:`split_identifier`.
        3. Return all tokens lowercased, with standalone punctuation removed.

    Numbers are preserved.  Short meaningful tokens such as ``id``,
    ``ip``, ``db``, and ``v2`` are kept.
    """
    words = _WORD_RE.findall(text)
    tokens: list[str] = []
    for word in words:
        tokens.extend(split_identifier(word))
    return tokens


__all__ = [
    "split_identifier",
    "tokenize",
]

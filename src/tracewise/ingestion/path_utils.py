"""Filesystem and path normalization utilities for TraceWise ingestion."""

import re
from functools import lru_cache
from pathlib import Path


def normalize_posix_path(path: Path | str) -> str:
    """Normalize a filesystem path to a clean POSIX-style relative path string.

    Replaces Windows-style backslashes with forward slashes and strips
    redundant leading './' markers.
    """
    normalized = str(path).replace("\\", "/").strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


@lru_cache(maxsize=256)
def glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Compile a POSIX glob pattern into a compiled regular expression Pattern.

    Supports:
    - '*' matching characters within a single path segment.
    - '**' matching across multiple path segments (including zero segments).
    - '?' matching a single character within a path segment.
    """
    norm = normalize_posix_path(pattern).lstrip("/")

    p = norm
    if p.startswith("**/"):
        p = "\0START_GS\0" + p[3:]

    p = p.replace("/**/", "\0MID_GS\0")
    if p.endswith("/**"):
        p = p[:-3] + "\0END_GS\0"
    elif p == "**":
        return re.compile(r"^.*$")

    p = p.replace("**", "\0GS\0")
    p = p.replace("*", "\0STAR\0")
    p = p.replace("?", "\0Q\0")

    escaped = re.escape(p)
    escaped = escaped.replace(re.escape("\0START_GS\0"), r"(?:.+/)?")
    escaped = escaped.replace(re.escape("\0MID_GS\0"), r"/(?:.+/)?")
    escaped = escaped.replace(re.escape("\0END_GS\0"), r"(?:/.+)?")
    escaped = escaped.replace(re.escape("\0GS\0"), r".*")
    escaped = escaped.replace(re.escape("\0STAR\0"), r"[^/]*")
    escaped = escaped.replace(re.escape("\0Q\0"), r"[^/]")

    return re.compile(f"^{escaped}$")


def match_glob_pattern(path: str, pattern: str) -> bool:
    """Check if a POSIX relative path matches a glob pattern."""
    regex = glob_to_regex(pattern)
    return bool(regex.match(path))

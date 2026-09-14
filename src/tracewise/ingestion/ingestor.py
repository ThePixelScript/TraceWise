"""Deterministic filesystem artifact ingestor for TraceWise."""

import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from tracewise.ingestion.exceptions import (
    AmbiguousRuleError,
    IngestionEncodingError,
    IngestionFileError,
)
from tracewise.ingestion.path_utils import match_glob_pattern, normalize_posix_path
from tracewise.ingestion.rules import IngestionRule
from tracewise.models import Artifact


class ArtifactIngestor:
    """Discovers and ingests supported project files into validated Artifact models."""

    DEFAULT_EXCLUDED_DIRS: frozenset[str] = frozenset(
        {".git", ".venv", "__pycache__", "node_modules"}
    )
    SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({".txt", ".md", ".py"})
    EXTENSION_TO_LANGUAGE: dict[str, str] = {
        ".py": "python",
        ".md": "markdown",
        ".txt": "text",
    }

    def __init__(
        self,
        excluded_dirs: set[str] | frozenset[str] | None = None,
    ) -> None:
        """Initialize the ingestor with optional custom directory exclusion rules."""
        if excluded_dirs is not None:
            self.excluded_dirs = frozenset(excluded_dirs)
        else:
            self.excluded_dirs = self.DEFAULT_EXCLUDED_DIRS

    def ingest(
        self,
        root: Path | str,
        rules: Sequence[IngestionRule],
    ) -> list[Artifact]:
        """Ingest matching files from root into validated Artifact objects.

        Args:
            root: Base directory of the project to discover files in.
            rules: Ordered sequence of IngestionRule configurations.

        Returns:
            List of validated Artifact objects, sorted deterministically by ID.

        Raises:
            ValueError: If root does not exist, is not a directory, rules is empty,
                or rules contain invalid patterns.
            AmbiguousRuleError: If a discovered file matches multiple conflicting rules.
            IngestionFileError: If a file cannot be read due to I/O permissions
                or OS errors.
            IngestionEncodingError: If a file contains invalid UTF-8 bytes.
        """
        root_path = Path(root)
        if not root_path.exists():
            raise ValueError(f"Root path does not exist: {root_path}")
        if not root_path.is_dir():
            raise ValueError(f"Root path is not a directory: {root_path}")

        if not rules:
            raise ValueError("Rule collection cannot be empty.")

        # Validate and deduplicate identical rules
        unique_rules: list[IngestionRule] = []
        seen_rules: set[IngestionRule] = set()
        for rule in rules:
            if not isinstance(rule, IngestionRule):
                raise ValueError(f"Expected IngestionRule, got {type(rule).__name__}")
            if rule not in seen_rules:
                seen_rules.add(rule)
                unique_rules.append(rule)

        discovered_artifacts: list[Artifact] = []
        seen_paths: set[str] = set()

        for dirpath, dirnames, filenames in os.walk(root_path):
            # Prune excluded directories in-place to avoid descending into them
            dirnames[:] = [
                d
                for d in sorted(dirnames)
                if d not in self.excluded_dirs and not d.startswith(".git")
            ]

            for filename in sorted(filenames):
                file_full_path = Path(dirpath) / filename
                rel_path = file_full_path.relative_to(root_path)
                rel_posix = normalize_posix_path(rel_path)

                ext = file_full_path.suffix.lower()
                if ext not in self.SUPPORTED_EXTENSIONS:
                    continue

                matching_rules = [
                    rule
                    for rule in unique_rules
                    if match_glob_pattern(rel_posix, rule.pattern)
                ]

                if not matching_rules:
                    continue

                if len(matching_rules) > 1:
                    rule_details = ", ".join(
                        f"'{r.pattern}' ({r.artifact_type.value})"
                        for r in matching_rules
                    )
                    raise AmbiguousRuleError(
                        f"Ambiguous rule match for file '{rel_posix}': "
                        f"matched {len(matching_rules)} rules: {rule_details}"
                    )

                if rel_posix in seen_paths:
                    continue
                seen_paths.add(rel_posix)

                rule = matching_rules[0]

                try:
                    raw_bytes = file_full_path.read_bytes()
                except OSError as err:
                    raise IngestionFileError(
                        f"Failed to read file '{rel_posix}': {err}"
                    ) from err

                try:
                    raw_content = raw_bytes.decode("utf-8")
                except UnicodeDecodeError as err:
                    raise IngestionEncodingError(
                        f"File '{rel_posix}' is not valid UTF-8: {err}"
                    ) from err

                language = self.EXTENSION_TO_LANGUAGE.get(ext, "text")
                metadata: dict[str, Any] = {
                    "relative_path": rel_posix,
                    "extension": ext,
                    "language": language,
                }

                artifact = Artifact(
                    id=rel_posix,
                    artifact_type=rule.artifact_type,
                    file_path=rel_posix,
                    raw_content=raw_content,
                    content=raw_content,
                    metadata=metadata,
                )
                discovered_artifacts.append(artifact)

        discovered_artifacts.sort(key=lambda a: a.id)
        return discovered_artifacts

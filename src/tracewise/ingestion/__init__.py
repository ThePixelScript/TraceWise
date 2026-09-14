"""Artifact ingestion module for TraceWise."""

from tracewise.ingestion.exceptions import (
    AmbiguousRuleError,
    IngestionEncodingError,
    IngestionError,
    IngestionFileError,
)
from tracewise.ingestion.ingestor import ArtifactIngestor
from tracewise.ingestion.path_utils import normalize_posix_path
from tracewise.ingestion.rules import IngestionRule

__all__ = [
    "AmbiguousRuleError",
    "ArtifactIngestor",
    "IngestionEncodingError",
    "IngestionError",
    "IngestionFileError",
    "IngestionRule",
    "normalize_posix_path",
]

"""TraceWise: Automated requirements traceability and change impact analysis."""

from tracewise.ingestion import (
    AmbiguousRuleError,
    ArtifactIngestor,
    IngestionEncodingError,
    IngestionError,
    IngestionFileError,
    IngestionRule,
    normalize_posix_path,
)
from tracewise.models import (
    Artifact,
    ArtifactChunk,
    ArtifactType,
    TraceLink,
    TraceLinkStatus,
)

__version__ = "0.1.0"

__all__ = [
    "AmbiguousRuleError",
    "Artifact",
    "ArtifactChunk",
    "ArtifactIngestor",
    "ArtifactType",
    "IngestionEncodingError",
    "IngestionError",
    "IngestionFileError",
    "IngestionRule",
    "TraceLink",
    "TraceLinkStatus",
    "__version__",
    "normalize_posix_path",
]

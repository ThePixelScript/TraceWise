"""TraceWise: Automated requirements traceability and change impact analysis."""

from tracewise.ingestion import (
    AmbiguousRuleError,
    ArtifactIngestor,
    BaseChunker,
    ChunkingError,
    IngestionEncodingError,
    IngestionError,
    IngestionFileError,
    IngestionRule,
    PythonChunker,
    PythonParsingError,
    UnsupportedArtifactTypeError,
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
    "BaseChunker",
    "ChunkingError",
    "IngestionEncodingError",
    "IngestionError",
    "IngestionFileError",
    "IngestionRule",
    "PythonChunker",
    "PythonParsingError",
    "TraceLink",
    "TraceLinkStatus",
    "UnsupportedArtifactTypeError",
    "__version__",
    "normalize_posix_path",
]

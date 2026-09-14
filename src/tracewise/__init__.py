"""TraceWise: Automated requirements traceability and change impact analysis."""

from tracewise.models import (
    Artifact,
    ArtifactChunk,
    ArtifactType,
    TraceLink,
    TraceLinkStatus,
)

__version__ = "0.1.0"

__all__ = [
    "Artifact",
    "ArtifactChunk",
    "ArtifactType",
    "TraceLink",
    "TraceLinkStatus",
    "__version__",
]

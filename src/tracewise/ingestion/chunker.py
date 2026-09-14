"""Base interface for artifact chunkers."""

from abc import ABC, abstractmethod

from tracewise.models.artifact import Artifact
from tracewise.models.artifact_chunk import ArtifactChunk


class BaseChunker(ABC):
    """Abstract base class for language-specific artifact chunkers."""

    @abstractmethod
    def chunk(self, artifact: Artifact) -> list[ArtifactChunk]:
        """Extract structural chunks from an artifact.

        Args:
            artifact: The source artifact to chunk.

        Returns:
            List of extracted ArtifactChunk instances.
        """

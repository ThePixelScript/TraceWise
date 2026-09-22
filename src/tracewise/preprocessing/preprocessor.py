"""Preprocessing orchestrator for artifacts and artifact chunks.

Provides a stateless :class:`Preprocessor` that converts raw text from
:class:`~tracewise.models.Artifact` and
:class:`~tracewise.models.ArtifactChunk` instances into
:class:`~tracewise.preprocessing.models.ProcessedText` representations
suitable for downstream retrieval indexing.
"""

from typing import Any

from tracewise.models.artifact import Artifact
from tracewise.models.artifact_chunk import ArtifactChunk
from tracewise.preprocessing.models import ProcessedText
from tracewise.preprocessing.normalizer import normalize_text
from tracewise.preprocessing.tokenizer import tokenize


class Preprocessor:
    """Deterministic, stateless text preprocessor.

    Converts raw artifact or chunk text into a :class:`ProcessedText`
    containing the original text, a normalized form, and extracted tokens.

    The preprocessor never mutates its inputs.
    """

    def process_text(
        self,
        source_id: str,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> ProcessedText:
        """Preprocess arbitrary text.

        Args:
            source_id: Identifier for the source artifact or chunk.
            text: The raw text to preprocess.
            metadata: Optional metadata to attach to the result.

        Returns:
            A :class:`ProcessedText` with the original text preserved,
            the normalized form, and extracted tokens.
        """
        normalized = normalize_text(text)
        tokens = tokenize(text)

        return ProcessedText(
            source_id=source_id,
            original_text=text,
            normalized_text=normalized,
            tokens=tokens,
            metadata=metadata or {},
        )

    def process_artifact(self, artifact: Artifact) -> ProcessedText:
        """Preprocess an :class:`~tracewise.models.Artifact`.

        Uses ``artifact.id`` as the ``source_id`` and
        ``artifact.content`` as the input text.  The artifact is never
        mutated.
        """
        metadata = {
            **artifact.metadata,
            "artifact_type": artifact.artifact_type.value,
        }
        return self.process_text(
            source_id=artifact.id,
            text=artifact.content,
            metadata=metadata,
        )

    def process_chunk(self, chunk: ArtifactChunk) -> ProcessedText:
        """Preprocess an :class:`~tracewise.models.ArtifactChunk`.

        Uses ``chunk.id`` as the ``source_id`` and ``chunk.content``
        as the input text.  The chunk is never mutated.
        """
        metadata = {
            **chunk.metadata,
            "parent_id": chunk.parent_id,
            "name": chunk.name,
            "start_line": chunk.start_line,
            "end_line": chunk.end_line,
        }
        return self.process_text(
            source_id=chunk.id,
            text=chunk.content,
            metadata=metadata,
        )


__all__ = ["Preprocessor"]

"""Whole-file and class-level chunker for file-granularity artifacts."""

from __future__ import annotations

from pathlib import Path

from tracewise.ingestion.chunker import BaseChunker
from tracewise.ingestion.exceptions import UnsupportedArtifactTypeError
from tracewise.models.artifact import Artifact, ArtifactType
from tracewise.models.artifact_chunk import ArtifactChunk


class FileChunker(BaseChunker):
    """Extracts whole-file or class-level structural chunks from artifacts.

    Used for class-level or file-level benchmarks (e.g., iTrust, where gold-standard
    trace links connect requirements and Java compilation units/classes).
    """

    def __init__(self, use_stem_as_id: bool = True) -> None:
        """Initialize FileChunker.

        Args:
            use_stem_as_id: If True, uses the filename stem (e.g., 'AddPatientAction')
                as the chunk ID. If False, uses the full relative file path.
        """
        self.use_stem_as_id = use_stem_as_id

    def chunk(self, artifact: Artifact) -> list[ArtifactChunk]:
        """Extract a single file/class-level chunk from an artifact.

        Args:
            artifact: The Artifact to extract chunks from.

        Returns:
            List containing one ArtifactChunk representing the file/class,
            or an empty list if the artifact content is empty or whitespace-only.

        Raises:
            UnsupportedArtifactTypeError: If artifact is not a supported type.
        """
        if artifact.artifact_type not in (
            ArtifactType.SOURCE_CODE,
            ArtifactType.TEST_CASE,
        ):
            raise UnsupportedArtifactTypeError(
                f"Artifact '{artifact.id}' has unsupported type "
                f"'{artifact.artifact_type}'. "
                "FileChunker only supports SOURCE_CODE and TEST_CASE."
            )

        if not artifact.raw_content.strip():
            return []

        chunk_id = (
            Path(artifact.file_path).stem if self.use_stem_as_id else artifact.file_path
        )
        name = Path(artifact.file_path).stem
        source_lines = artifact.raw_content.splitlines(keepends=True)
        end_line = max(1, len(source_lines))

        return [
            ArtifactChunk(
                id=chunk_id,
                parent_id=artifact.id,
                name=name,
                raw_content=artifact.raw_content,
                content=artifact.content,
                start_line=1,
                end_line=end_line,
                metadata={
                    **artifact.metadata,
                    "granularity": "class" if self.use_stem_as_id else "file",
                },
            )
        ]


__all__ = ["FileChunker"]

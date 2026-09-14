"""Deterministic Python structural chunk extractor using AST."""

import ast

from tracewise.ingestion.chunker import BaseChunker
from tracewise.ingestion.exceptions import (
    PythonParsingError,
    UnsupportedArtifactTypeError,
)
from tracewise.models.artifact import Artifact, ArtifactType
from tracewise.models.artifact_chunk import ArtifactChunk


class PythonChunker(BaseChunker):
    """Extracts structural chunks from Python artifacts using AST."""

    def chunk(self, artifact: Artifact) -> list[ArtifactChunk]:
        """Extract structural chunks from a Python source artifact.

        Args:
            artifact: The Artifact to extract chunks from.

        Returns:
            List of extracted ArtifactChunk instances.

        Raises:
            UnsupportedArtifactTypeError: If artifact is not a Python source file.
            PythonParsingError: If AST parsing fails or line metadata is missing.
        """
        if artifact.artifact_type not in (
            ArtifactType.SOURCE_CODE,
            ArtifactType.TEST_CASE,
        ):
            raise UnsupportedArtifactTypeError(
                f"Artifact '{artifact.id}' has unsupported type "
                f"'{artifact.artifact_type}'. "
                "PythonChunker only supports SOURCE_CODE and TEST_CASE."
            )

        if not artifact.file_path.endswith(".py"):
            raise UnsupportedArtifactTypeError(
                f"Artifact '{artifact.id}' with path '{artifact.file_path}' "
                "is not a Python (.py) file."
            )

        # Empty or whitespace-only files yield zero chunks
        if not artifact.raw_content.strip():
            return []

        try:
            tree = ast.parse(artifact.raw_content, filename=artifact.file_path)
        except SyntaxError as exc:
            raise PythonParsingError(
                f"Syntax error in '{artifact.file_path}' at line {exc.lineno}: "
                f"{exc.msg}"
            ) from exc

        source_lines = artifact.raw_content.splitlines(keepends=True)

        def _extract_slice(start: int, end: int) -> str:
            return "".join(source_lines[start - 1 : end])

        def _get_start_line(
            node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
        ) -> int:
            if node.decorator_list:
                return min(d.lineno for d in node.decorator_list)
            return node.lineno

        def _get_end_line(
            node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
            start_line: int,
        ) -> int:
            end = node.end_lineno
            if end is None or end < start_line:
                raise PythonParsingError(
                    f"AST node '{node.name}' in '{artifact.file_path}' "
                    f"has invalid or missing end_lineno "
                    f"(start_line={start_line}, end_line={end})."
                )
            return end

        # Count base ID occurrences to detect duplicate definitions
        base_id_counts: dict[str, int] = {}
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                base_id = f"{artifact.file_path}#{node.name}"
                base_id_counts[base_id] = base_id_counts.get(base_id, 0) + 1
                if isinstance(node, ast.ClassDef):
                    for member in node.body:
                        if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            m_base = f"{artifact.file_path}#{node.name}.{member.name}"
                            base_id_counts[m_base] = base_id_counts.get(m_base, 0) + 1

        def _build_chunk_id(base_id: str, start_line: int) -> str:
            if base_id_counts[base_id] > 1:
                return f"{base_id}@L{start_line}"
            return base_id

        chunks: list[ArtifactChunk] = []

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                start_line = _get_start_line(node)
                end_line = _get_end_line(node, start_line)
                slice_text = _extract_slice(start_line, end_line)
                docstring = ast.get_docstring(node, clean=True) or ""
                is_async = isinstance(node, ast.AsyncFunctionDef)
                base_id = f"{artifact.file_path}#{node.name}"
                chunk_id = _build_chunk_id(base_id, start_line)

                chunks.append(
                    ArtifactChunk(
                        id=chunk_id,
                        parent_id=artifact.id,
                        name=node.name,
                        raw_content=slice_text,
                        content=slice_text,
                        start_line=start_line,
                        end_line=end_line,
                        metadata={
                            "chunk_type": "function",
                            "is_async": is_async,
                            "docstring": docstring,
                        },
                    )
                )

            elif isinstance(node, ast.ClassDef):
                start_line = _get_start_line(node)
                end_line = _get_end_line(node, start_line)
                slice_text = _extract_slice(start_line, end_line)
                docstring = ast.get_docstring(node, clean=True) or ""
                base_class_id = f"{artifact.file_path}#{node.name}"
                class_id = _build_chunk_id(base_class_id, start_line)

                class_chunk = ArtifactChunk(
                    id=class_id,
                    parent_id=artifact.id,
                    name=node.name,
                    raw_content=slice_text,
                    content=slice_text,
                    start_line=start_line,
                    end_line=end_line,
                    metadata={
                        "chunk_type": "class",
                        "docstring": docstring,
                    },
                )
                chunks.append(class_chunk)

                # Inspect direct body of the class for methods
                for member in node.body:
                    if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        m_start = _get_start_line(member)
                        m_end = _get_end_line(member, m_start)
                        m_slice = _extract_slice(m_start, m_end)
                        m_docstring = ast.get_docstring(member, clean=True) or ""
                        m_is_async = isinstance(member, ast.AsyncFunctionDef)
                        m_base_id = f"{artifact.file_path}#{node.name}.{member.name}"
                        method_id = _build_chunk_id(m_base_id, m_start)

                        chunks.append(
                            ArtifactChunk(
                                id=method_id,
                                parent_id=class_id,
                                name=member.name,
                                raw_content=m_slice,
                                content=m_slice,
                                start_line=m_start,
                                end_line=m_end,
                                metadata={
                                    "chunk_type": "method",
                                    "is_async": m_is_async,
                                    "docstring": m_docstring,
                                },
                            )
                        )

        return chunks

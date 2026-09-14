"""Exceptions for the TraceWise artifact ingestion and chunking pipeline."""


class IngestionError(Exception):
    """Base exception for all artifact ingestion failures."""


class IngestionFileError(IngestionError):
    """Raised when an artifact file cannot be accessed or read."""


class IngestionEncodingError(IngestionError):
    """Raised when an artifact file fails UTF-8 decoding."""


class AmbiguousRuleError(IngestionError):
    """Raised when a file matches multiple conflicting ingestion rules."""


class ChunkingError(Exception):
    """Base exception for all artifact chunking failures."""


class UnsupportedArtifactTypeError(ChunkingError):
    """Raised when an artifact type or file extension is not supported for chunking."""


class PythonParsingError(ChunkingError):
    """Raised when Python AST parsing fails or AST node line metadata is invalid."""

"""Exceptions for the TraceWise artifact ingestion pipeline."""


class IngestionError(Exception):
    """Base exception for all artifact ingestion failures."""


class IngestionFileError(IngestionError):
    """Raised when an artifact file cannot be accessed or read."""


class IngestionEncodingError(IngestionError):
    """Raised when an artifact file fails UTF-8 decoding."""


class AmbiguousRuleError(IngestionError):
    """Raised when a file matches multiple conflicting ingestion rules."""

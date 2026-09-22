"""Exceptions for the TraceWise retrieval pipeline."""


class RetrieverError(Exception):
    """Base exception for retrieval-layer errors."""


class NotIndexedError(RetrieverError):
    """Raised when retrieval is requested before indexing."""

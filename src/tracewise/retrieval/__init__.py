"""Retrieval layer contracts and models for TraceWise."""

from tracewise.retrieval.base import BaseRetriever
from tracewise.retrieval.exceptions import NotIndexedError, RetrieverError
from tracewise.retrieval.models import RetrievalCandidate
from tracewise.retrieval.tfidf import TfidfRetriever

__all__ = [
    "BaseRetriever",
    "NotIndexedError",
    "RetrievalCandidate",
    "RetrieverError",
    "TfidfRetriever",
]

"""Retrieval layer contracts and models for TraceWise."""

from tracewise.retrieval.base import BaseRetriever
from tracewise.retrieval.bm25 import BM25Retriever
from tracewise.retrieval.exceptions import NotIndexedError, RetrieverError
from tracewise.retrieval.models import RetrievalCandidate
from tracewise.retrieval.semantic import SemanticRetriever
from tracewise.retrieval.structural import StructuralRetriever
from tracewise.retrieval.tfidf import TfidfRetriever

__all__ = [
    "BM25Retriever",
    "BaseRetriever",
    "NotIndexedError",
    "RetrievalCandidate",
    "RetrieverError",
    "SemanticRetriever",
    "StructuralRetriever",
    "TfidfRetriever",
]

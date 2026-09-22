"""TF-IDF and Cosine similarity retrieval baseline for TraceWise."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence

import numpy as np

from tracewise.preprocessing.models import ProcessedText
from tracewise.retrieval.base import BaseRetriever
from tracewise.retrieval.exceptions import NotIndexedError
from tracewise.retrieval.models import RetrievalCandidate


class TfidfRetriever(BaseRetriever):
    """Lexical retrieval baseline using sublinear TF-IDF and Cosine similarity.

    Algorithm specification (Milestone 2B):
    - Sublinear TF: TF(t, d) = 1 + ln(count(t, d)) if count > 0 else 0
    - Document frequency: DF(t) = count of indexed target documents containing t
    - Smoothed IDF: IDF(t) = ln(1 + N / DF(t)) where N is total target documents
    - Term weight: weight(t, d) = TF(t, d) * IDF(t)
    - Cosine similarity: dot(q, d) / (||q||_2 * ||d||_2)
    - Threshold: if ||q||_2 <= 1e-12 or ||d||_2 <= 1e-12, score = 0.0
    - Pre-normalized float64 target matrix for vectorized dot product
    - Candidates sorted by (-score, target_id) with 1-based ranks
    """

    retriever_name: str = "tfidf_cosine"

    def __init__(self) -> None:
        self._is_indexed: bool = False
        self._target_ids: list[str] = []
        self._vocabulary: list[str] = []
        self._term_to_index: dict[str, int] = {}
        self._idf: np.ndarray = np.empty(0, dtype=np.float64)
        self._doc_matrix_norm: np.ndarray = np.empty((0, 0), dtype=np.float64)

    @property
    def is_indexed(self) -> bool:
        """Whether the retriever has an active index ready for querying."""
        return self._is_indexed

    def index(self, documents: Sequence[ProcessedText]) -> None:
        """Build or replace the retriever's target index with documents.

        Calling index again replaces the previous index completely. If indexing
        fails for any reason, the prior valid state remains unchanged.

        Args:
            documents: Sequence of preprocessed text documents to index.

        Raises:
            ValueError: If documents is empty or contains duplicate source_ids.
        """
        doc_list = list(documents)
        if not doc_list:
            raise ValueError("Cannot index an empty document sequence.")

        target_ids: list[str] = []
        seen_ids: set[str] = set()
        for doc in doc_list:
            sid = doc.source_id
            if sid in seen_ids:
                raise ValueError(f"Duplicate document source_id found: '{sid}'.")
            seen_ids.add(sid)
            target_ids.append(sid)

        num_docs = len(doc_list)

        # Build vocabulary from unique tokens across all documents in sorted order
        unique_tokens: set[str] = set()
        doc_token_counts: list[Counter[str]] = []
        for doc in doc_list:
            counts = Counter(doc.tokens)
            doc_token_counts.append(counts)
            unique_tokens.update(counts.keys())

        vocabulary = sorted(unique_tokens)
        term_to_index = {term: idx for idx, term in enumerate(vocabulary)}
        vocab_size = len(vocabulary)

        if vocab_size == 0:
            idf = np.zeros(0, dtype=np.float64)
            doc_matrix_norm = np.zeros((num_docs, 0), dtype=np.float64)
        else:
            # Document frequency: number of documents containing term at least once
            df = np.zeros(vocab_size, dtype=np.float64)
            for counts in doc_token_counts:
                for term in counts:
                    df[term_to_index[term]] += 1.0

            # IDF: ln(1.0 + N / DF(t))
            idf = np.log(1.0 + (num_docs / df))

            # Build document TF-IDF matrix
            doc_matrix = np.zeros((num_docs, vocab_size), dtype=np.float64)
            for doc_idx, counts in enumerate(doc_token_counts):
                for term, count in counts.items():
                    col_idx = term_to_index[term]
                    tf = 1.0 + math.log(count)
                    doc_matrix[doc_idx, col_idx] = tf * idf[col_idx]

            # Row pre-normalization by L2 norm
            row_norms = np.linalg.norm(doc_matrix, axis=1, keepdims=True)
            doc_matrix_norm = np.zeros_like(doc_matrix)
            valid_rows = (row_norms > 1e-12).squeeze(axis=1)
            doc_matrix_norm[valid_rows] = doc_matrix[valid_rows] / row_norms[valid_rows]

        # Atomic commit to object state only after all calculations succeed
        self._target_ids = target_ids
        self._vocabulary = vocabulary
        self._term_to_index = term_to_index
        self._idf = idf
        self._doc_matrix_norm = doc_matrix_norm
        self._is_indexed = True

    def retrieve(
        self,
        query: ProcessedText,
        top_k: int | None = None,
    ) -> list[RetrievalCandidate]:
        """Retrieve candidate matches for a query from the indexed corpus.

        Candidates are scored using Cosine similarity and sorted in descending
        order of relevance score, with ties broken by target_id ascending:
            key=lambda candidate: (-candidate.score, candidate.target_id)
        Ranks are 1-based and consecutive (1, 2, 3, ...).

        Args:
            query: Preprocessed query to search against indexed documents.
            top_k: Optional maximum number of candidates to return.
                If None, returns all candidates for the query.

        Returns:
            List of RetrievalCandidate objects ordered by descending score.

        Raises:
            NotIndexedError: If retrieve is called before index.
            ValueError: If top_k is less than or equal to 0.
        """
        if not self._is_indexed:
            raise NotIndexedError(
                f"Retriever '{self.retriever_name}' cannot retrieve before indexing."
            )

        if top_k is not None and top_k <= 0:
            raise ValueError(f"top_k must be strictly positive, got {top_k}.")

        num_docs = len(self._target_ids)
        vocab_size = len(self._vocabulary)

        if vocab_size == 0 or not query.tokens:
            scores = np.zeros(num_docs, dtype=np.float64)
        else:
            q_counts = Counter(query.tokens)
            q_vec = np.zeros(vocab_size, dtype=np.float64)
            for term, count in q_counts.items():
                if term in self._term_to_index:
                    col_idx = self._term_to_index[term]
                    tf = 1.0 + math.log(count)
                    q_vec[col_idx] = tf * self._idf[col_idx]

            q_norm = np.linalg.norm(q_vec)
            if q_norm <= 1e-12:
                scores = np.zeros(num_docs, dtype=np.float64)
            else:
                q_vec_norm = q_vec / q_norm
                scores = self._doc_matrix_norm.dot(q_vec_norm)

        # Pair each target with its score
        raw: list[tuple[str, float]] = []
        for idx, target_id in enumerate(self._target_ids):
            raw_score = float(scores[idx])
            # Clamp potential floating point inaccuracies to [0.0, 1.0]
            if raw_score < 0.0:
                raw_score = 0.0
            elif raw_score > 1.0:
                raw_score = 1.0
            raw.append((target_id, raw_score))

        # Shared contract ordering: (-score, target_id)
        raw.sort(key=lambda item: (-item[1], item[0]))

        if top_k is not None:
            raw = raw[:top_k]

        return [
            RetrievalCandidate(
                query_id=query.source_id,
                target_id=target_id,
                score=score,
                rank=rank,
                retriever_name=self.retriever_name,
            )
            for rank, (target_id, score) in enumerate(raw, start=1)
        ]

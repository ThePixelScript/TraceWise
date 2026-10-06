"""BM25 lexical retrieval baseline for TraceWise."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

import numpy as np

from tracewise.preprocessing.models import ProcessedText
from tracewise.retrieval.base import BaseRetriever
from tracewise.retrieval.exceptions import NotIndexedError
from tracewise.retrieval.models import RetrievalCandidate


class BM25Retriever(BaseRetriever):
    """Lexical retrieval baseline using standard Okapi BM25.

    Algorithm specification (Milestone 3B):
    - Term Frequency: TF(t, d) = raw frequency count of token t in document d.
    - Document length: |d| = total token count in document d.
    - Average document length: avgdl = (1 / N) * sum(|d|) across target corpus.
    - Length normalization: B(d) = 1 - b + b * (|d| / avgdl) (or 1.0 if avgdl == 0).
    - BM25 Term Weight:
        TF_BM25(t, d) = (TF(t, d) * (k1 + 1)) / (TF(t, d) + k1 * B(d))
    - Smoothed Non-Negative Inverse Document Frequency:
        IDF(t) = ln(1 + (N - DF(t) + 0.5) / (DF(t) + 0.5))
      where N is total target documents and DF(t) is count of documents containing t.
    - Query Scoring:
        Score(Q, d) = sum_{t in Q} TF_BM25(t, d) * IDF(t)
    - Default parameters: k1 = 1.5, b = 0.75 (standard un-tuned Okapi BM25 defaults).
    - Candidates sorted by (-score, target_id) with 1-based ranks.
    """

    retriever_name: str = "bm25"

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        """Initialize BM25 retriever with configurable parameters.

        Args:
            k1: Term frequency saturation parameter (must be >= 0.0).
            b: Document length normalization parameter (must be in [0.0, 1.0]).

        Raises:
            ValueError: If k1 < 0.0 or b is not in [0.0, 1.0].
        """
        if k1 < 0.0:
            raise ValueError(f"BM25 parameter k1 must be non-negative, got {k1}.")
        if not (0.0 <= b <= 1.0):
            raise ValueError(f"BM25 parameter b must be between 0.0 and 1.0, got {b}.")

        self.k1 = float(k1)
        self.b = float(b)
        self._is_indexed: bool = False
        self._target_ids: list[str] = []
        self._vocabulary: list[str] = []
        self._term_to_index: dict[str, int] = {}
        self._idf: np.ndarray = np.empty(0, dtype=np.float64)
        self._doc_lengths: np.ndarray = np.empty(0, dtype=np.float64)
        self._avg_doc_len: float = 0.0
        self._doc_matrix: np.ndarray = np.empty((0, 0), dtype=np.float64)

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
        doc_lengths_list: list[float] = []

        for doc in doc_list:
            counts = Counter(doc.tokens)
            doc_token_counts.append(counts)
            doc_lengths_list.append(float(len(doc.tokens)))
            unique_tokens.update(counts.keys())

        vocabulary = sorted(unique_tokens)
        term_to_index = {term: idx for idx, term in enumerate(vocabulary)}
        vocab_size = len(vocabulary)

        doc_lengths = np.array(doc_lengths_list, dtype=np.float64)
        avg_doc_len = float(np.mean(doc_lengths)) if num_docs > 0 else 0.0

        if vocab_size == 0:
            idf = np.zeros(0, dtype=np.float64)
            doc_matrix = np.zeros((num_docs, 0), dtype=np.float64)
        else:
            # Document frequency: count of documents containing term at least once
            df = np.zeros(vocab_size, dtype=np.float64)
            for counts in doc_token_counts:
                for term in counts:
                    df[term_to_index[term]] += 1.0

            # Smoothed non-negative BM25 IDF: ln(1 + (N - DF + 0.5) / (DF + 0.5))
            idf = np.log(1.0 + (num_docs - df + 0.5) / (df + 0.5))

            # Build precomputed document BM25 matrix:
            # doc_matrix[d, t] = TF_BM25(t, d) * idf[t]
            doc_matrix = np.zeros((num_docs, vocab_size), dtype=np.float64)
            for doc_idx, counts in enumerate(doc_token_counts):
                doc_len = doc_lengths[doc_idx]
                len_norm = (
                    1.0 - self.b + self.b * (doc_len / avg_doc_len)
                    if avg_doc_len > 0.0
                    else 1.0
                )
                for term, count in counts.items():
                    col_idx = term_to_index[term]
                    tf_bm25 = (count * (self.k1 + 1.0)) / (count + self.k1 * len_norm)
                    doc_matrix[doc_idx, col_idx] = tf_bm25 * idf[col_idx]

        # Atomic commit to object state only after all calculations succeed
        self._target_ids = target_ids
        self._vocabulary = vocabulary
        self._term_to_index = term_to_index
        self._idf = idf
        self._doc_lengths = doc_lengths
        self._avg_doc_len = avg_doc_len
        self._doc_matrix = doc_matrix
        self._is_indexed = True

    def retrieve(
        self,
        query: ProcessedText,
        top_k: int | None = None,
    ) -> list[RetrievalCandidate]:
        """Retrieve candidate matches for a query from the indexed corpus.

        Candidates are scored using BM25 and sorted in descending order
        of relevance score, with ties broken by target_id ascending:
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
                    q_vec[col_idx] = float(count)

            scores = self._doc_matrix.dot(q_vec)

        # Pair each target with its score
        raw: list[tuple[str, float]] = []
        for idx, target_id in enumerate(self._target_ids):
            raw_score = float(scores[idx])
            if raw_score < 0.0:
                raw_score = 0.0
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


__all__ = ["BM25Retriever"]

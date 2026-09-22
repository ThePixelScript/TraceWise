"""Tests for TraceWise retrieval contracts, models, and base lifecycle."""

from collections.abc import Sequence

import pytest
from pydantic import ValidationError

from tracewise.preprocessing.models import ProcessedText
from tracewise.retrieval.base import BaseRetriever
from tracewise.retrieval.exceptions import NotIndexedError, RetrieverError
from tracewise.retrieval.models import RetrievalCandidate


class MockRetriever(BaseRetriever):
    """Minimal concrete retriever used to test contract lifecycle and ordering."""

    def __init__(self, name: str = "mock_retriever") -> None:
        self._name = name
        self._indexed: bool = False
        self._documents: dict[str, ProcessedText] = {}
        self.preset_scores: dict[str, float] = {}

    @property
    def is_indexed(self) -> bool:
        return self._indexed

    def index(self, documents: Sequence[ProcessedText]) -> None:
        self._documents = {doc.source_id: doc for doc in documents}
        self._indexed = True

    def retrieve(
        self,
        query: ProcessedText,
        top_k: int | None = None,
    ) -> list[RetrievalCandidate]:
        if not self._indexed:
            raise NotIndexedError(
                f"Retriever '{self._name}' cannot retrieve before indexing."
            )

        if top_k is not None and top_k <= 0:
            raise ValueError(f"top_k must be strictly positive, got {top_k}.")

        raw: list[tuple[str, float]] = []
        for doc_id in self._documents:
            score = self.preset_scores.get(doc_id, 0.0)
            raw.append((doc_id, score))

        # Shared contract ordering: (-score, target_id)
        raw.sort(key=lambda item: (-item[1], item[0]))

        if top_k is not None:
            raw = raw[:top_k]

        return [
            RetrievalCandidate(
                query_id=query.source_id,
                target_id=doc_id,
                score=score,
                rank=idx,
                retriever_name=self._name,
            )
            for idx, (doc_id, score) in enumerate(raw, start=1)
        ]


class TestRetrievalCandidateValidation:
    def test_valid_construction(self):
        candidate = RetrievalCandidate(
            query_id="REQ-001",
            target_id="src/auth.py#login",
            score=0.95,
            rank=1,
            retriever_name="bm25",
            metadata={"lexical_overlap": 3},
        )
        assert candidate.query_id == "REQ-001"
        assert candidate.target_id == "src/auth.py#login"
        assert candidate.score == 0.95
        assert candidate.rank == 1
        assert candidate.retriever_name == "bm25"
        assert candidate.metadata == {"lexical_overlap": 3}

    def test_default_metadata_is_empty_dict(self):
        candidate = RetrievalCandidate(
            query_id="REQ-001",
            target_id="src/auth.py#login",
            score=1.0,
            rank=1,
            retriever_name="tfidf",
        )
        assert candidate.metadata == {}

    def test_empty_query_id_rejected(self):
        with pytest.raises(ValidationError, match="query_id"):
            RetrievalCandidate(
                query_id="",
                target_id="src/auth.py#login",
                score=1.0,
                rank=1,
                retriever_name="bm25",
            )
        with pytest.raises(ValidationError, match="query_id"):
            RetrievalCandidate(
                query_id="   ",
                target_id="src/auth.py#login",
                score=1.0,
                rank=1,
                retriever_name="bm25",
            )

    def test_empty_target_id_rejected(self):
        with pytest.raises(ValidationError, match="target_id"):
            RetrievalCandidate(
                query_id="REQ-001",
                target_id="",
                score=1.0,
                rank=1,
                retriever_name="bm25",
            )
        with pytest.raises(ValidationError, match="target_id"):
            RetrievalCandidate(
                query_id="REQ-001",
                target_id="   ",
                score=1.0,
                rank=1,
                retriever_name="bm25",
            )

    def test_empty_retriever_name_rejected(self):
        with pytest.raises(ValidationError, match="retriever_name"):
            RetrievalCandidate(
                query_id="REQ-001",
                target_id="src/auth.py#login",
                score=1.0,
                rank=1,
                retriever_name="",
            )
        with pytest.raises(ValidationError, match="retriever_name"):
            RetrievalCandidate(
                query_id="REQ-001",
                target_id="src/auth.py#login",
                score=1.0,
                rank=1,
                retriever_name="   ",
            )

    def test_whitespace_in_identifiers_is_stripped(self):
        candidate = RetrievalCandidate(
            query_id="  REQ-001  ",
            target_id="  src/auth.py#login  ",
            score=0.8,
            rank=1,
            retriever_name="  bm25  ",
        )
        assert candidate.query_id == "REQ-001"
        assert candidate.target_id == "src/auth.py#login"
        assert candidate.retriever_name == "bm25"

    def test_rank_one_accepted(self):
        candidate = RetrievalCandidate(
            query_id="REQ-001",
            target_id="src/auth.py#login",
            score=0.5,
            rank=1,
            retriever_name="bm25",
        )
        assert candidate.rank == 1

    def test_rank_zero_rejected(self):
        with pytest.raises(ValidationError, match="rank"):
            RetrievalCandidate(
                query_id="REQ-001",
                target_id="src/auth.py#login",
                score=0.5,
                rank=0,
                retriever_name="bm25",
            )

    def test_negative_rank_rejected(self):
        with pytest.raises(ValidationError, match="rank"):
            RetrievalCandidate(
                query_id="REQ-001",
                target_id="src/auth.py#login",
                score=0.5,
                rank=-1,
                retriever_name="bm25",
            )

    def test_finite_score_accepted(self):
        for val in (0.0, 100.5, -42.0, 1e-6, 1e12):
            c = RetrievalCandidate(
                query_id="REQ-001",
                target_id="src/auth.py#login",
                score=val,
                rank=1,
                retriever_name="bm25",
            )
            assert c.score == val

    def test_nan_score_rejected(self):
        with pytest.raises(ValidationError, match="score"):
            RetrievalCandidate(
                query_id="REQ-001",
                target_id="src/auth.py#login",
                score=float("nan"),
                rank=1,
                retriever_name="bm25",
            )

    def test_positive_infinity_score_rejected(self):
        with pytest.raises(ValidationError, match="score"):
            RetrievalCandidate(
                query_id="REQ-001",
                target_id="src/auth.py#login",
                score=float("inf"),
                rank=1,
                retriever_name="bm25",
            )

    def test_negative_infinity_score_rejected(self):
        with pytest.raises(ValidationError, match="score"):
            RetrievalCandidate(
                query_id="REQ-001",
                target_id="src/auth.py#login",
                score=float("-inf"),
                rank=1,
                retriever_name="bm25",
            )

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            RetrievalCandidate(
                query_id="REQ-001",
                target_id="src/auth.py#login",
                score=0.8,
                rank=1,
                retriever_name="bm25",
                unexpected_field="disallowed",
            )

    def test_mutation_after_creation_rejected(self):
        candidate = RetrievalCandidate(
            query_id="REQ-001",
            target_id="src/auth.py#login",
            score=0.8,
            rank=1,
            retriever_name="bm25",
        )
        with pytest.raises(ValidationError):
            candidate.score = 0.99  # type: ignore[misc]

    def test_serialization_roundtrip(self):
        candidate = RetrievalCandidate(
            query_id="REQ-001",
            target_id="src/auth.py#login",
            score=0.88,
            rank=2,
            retriever_name="bm25",
            metadata={"source": "header"},
        )
        serialized = candidate.model_dump_json()
        reconstructed = RetrievalCandidate.model_validate_json(serialized)
        assert reconstructed == candidate


class TestRetrieverExceptions:
    def test_not_indexed_error_inherits_from_retriever_error(self):
        assert issubclass(NotIndexedError, RetrieverError)


class TestRetrieverLifecycle:
    def test_new_retriever_is_not_indexed(self):
        retriever = MockRetriever()
        assert retriever.is_indexed is False

    def test_retrieve_before_index_raises_not_indexed_error(self):
        retriever = MockRetriever()
        query = ProcessedText(
            source_id="Q-1",
            original_text="search query",
            normalized_text="search query",
            tokens=["search", "query"],
        )
        with pytest.raises(NotIndexedError, match="cannot retrieve before indexing"):
            retriever.retrieve(query)

    def test_index_changes_indexed_state(self):
        retriever = MockRetriever()
        docs = [
            ProcessedText(
                source_id="D-1",
                original_text="doc one",
                normalized_text="doc one",
                tokens=["doc", "one"],
            ),
            ProcessedText(
                source_id="D-2",
                original_text="doc two",
                normalized_text="doc two",
                tokens=["doc", "two"],
            ),
        ]
        retriever.index(docs)
        assert retriever.is_indexed is True

    def test_reindexing_replaces_index_completely(self):
        retriever = MockRetriever()
        initial_docs = [
            ProcessedText(
                source_id="D-1",
                original_text="doc one",
                normalized_text="doc one",
                tokens=["doc", "one"],
            ),
            ProcessedText(
                source_id="D-2",
                original_text="doc two",
                normalized_text="doc two",
                tokens=["doc", "two"],
            ),
        ]
        retriever.index(initial_docs)
        assert len(retriever._documents) == 2
        assert "D-1" in retriever._documents

        new_docs = [
            ProcessedText(
                source_id="D-3",
                original_text="doc three",
                normalized_text="doc three",
                tokens=["doc", "three"],
            ),
        ]
        retriever.index(new_docs)
        assert len(retriever._documents) == 1
        assert "D-1" not in retriever._documents
        assert "D-3" in retriever._documents
        assert retriever.is_indexed is True

    def test_top_k_zero_raises_value_error(self):
        retriever = MockRetriever()
        retriever.index(
            [
                ProcessedText(
                    source_id="D-1",
                    original_text="doc one",
                    normalized_text="doc one",
                    tokens=["doc", "one"],
                )
            ]
        )
        query = ProcessedText(
            source_id="Q-1",
            original_text="query",
            normalized_text="query",
            tokens=["query"],
        )
        with pytest.raises(ValueError, match="strictly positive"):
            retriever.retrieve(query, top_k=0)

    def test_top_k_negative_raises_value_error(self):
        retriever = MockRetriever()
        retriever.index(
            [
                ProcessedText(
                    source_id="D-1",
                    original_text="doc one",
                    normalized_text="doc one",
                    tokens=["doc", "one"],
                )
            ]
        )
        query = ProcessedText(
            source_id="Q-1",
            original_text="query",
            normalized_text="query",
            tokens=["query"],
        )
        with pytest.raises(ValueError, match="strictly positive"):
            retriever.retrieve(query, top_k=-5)

    def test_top_k_none_returns_all_candidates(self):
        retriever = MockRetriever()
        docs = [
            ProcessedText(
                source_id=f"D-{i}",
                original_text=f"doc {i}",
                normalized_text=f"doc {i}",
                tokens=["doc", str(i)],
            )
            for i in range(5)
        ]
        retriever.index(docs)
        query = ProcessedText(
            source_id="Q-1",
            original_text="query",
            normalized_text="query",
            tokens=["query"],
        )

        candidates = retriever.retrieve(query, top_k=None)
        assert len(candidates) == 5

    def test_top_k_limits_returned_results(self):
        retriever = MockRetriever()
        docs = [
            ProcessedText(
                source_id=f"D-{i}",
                original_text=f"doc {i}",
                normalized_text=f"doc {i}",
                tokens=["doc", str(i)],
            )
            for i in range(10)
        ]
        retriever.index(docs)
        query = ProcessedText(
            source_id="Q-1",
            original_text="query",
            normalized_text="query",
            tokens=["query"],
        )

        candidates = retriever.retrieve(query, top_k=3)
        assert len(candidates) == 3


class TestRetrieverCandidateOrdering:
    def test_higher_score_comes_first(self):
        retriever = MockRetriever()
        retriever.preset_scores = {
            "target_low": 0.2,
            "target_high": 0.9,
            "target_mid": 0.5,
        }
        docs = [
            ProcessedText(
                source_id=k,
                original_text="text",
                normalized_text="text",
                tokens=["text"],
            )
            for k in retriever.preset_scores
        ]
        retriever.index(docs)

        query = ProcessedText(
            source_id="Q-1",
            original_text="query",
            normalized_text="query",
            tokens=["query"],
        )
        candidates = retriever.retrieve(query)

        assert [c.target_id for c in candidates] == [
            "target_high",
            "target_mid",
            "target_low",
        ]
        assert [c.score for c in candidates] == [0.9, 0.5, 0.2]

    def test_equal_scores_broken_by_target_id_ascending(self):
        retriever = MockRetriever()
        retriever.preset_scores = {
            "src/z_module.py#func": 0.75,
            "src/a_module.py#func": 0.75,
            "src/m_module.py#func": 0.75,
        }
        docs = [
            ProcessedText(
                source_id=k,
                original_text="text",
                normalized_text="text",
                tokens=["text"],
            )
            for k in retriever.preset_scores
        ]
        retriever.index(docs)

        query = ProcessedText(
            source_id="Q-1",
            original_text="query",
            normalized_text="query",
            tokens=["query"],
        )
        candidates = retriever.retrieve(query)

        assert [c.target_id for c in candidates] == [
            "src/a_module.py#func",
            "src/m_module.py#func",
            "src/z_module.py#func",
        ]

    def test_ranks_are_consecutive_one_based(self):
        retriever = MockRetriever()
        retriever.preset_scores = {
            "T-1": 0.8,
            "T-2": 0.6,
            "T-3": 0.4,
            "T-4": 0.2,
        }
        docs = [
            ProcessedText(
                source_id=k,
                original_text="text",
                normalized_text="text",
                tokens=["text"],
            )
            for k in retriever.preset_scores
        ]
        retriever.index(docs)

        query = ProcessedText(
            source_id="Q-1",
            original_text="query",
            normalized_text="query",
            tokens=["query"],
        )
        candidates = retriever.retrieve(query)

        ranks = [c.rank for c in candidates]
        assert ranks == [1, 2, 3, 4]

    def test_no_duplicate_target_ids_returned(self):
        retriever = MockRetriever()
        docs = [
            ProcessedText(
                source_id="T-1",
                original_text="doc 1",
                normalized_text="doc 1",
                tokens=["doc", "1"],
            ),
            ProcessedText(
                source_id="T-2",
                original_text="doc 2",
                normalized_text="doc 2",
                tokens=["doc", "2"],
            ),
            ProcessedText(
                source_id="T-3",
                original_text="doc 3",
                normalized_text="doc 3",
                tokens=["doc", "3"],
            ),
        ]
        retriever.index(docs)

        query = ProcessedText(
            source_id="Q-1",
            original_text="query",
            normalized_text="query",
            tokens=["query"],
        )
        candidates = retriever.retrieve(query)

        target_ids = [c.target_id for c in candidates]
        assert len(target_ids) == len(set(target_ids))

"""Tests for TraceWise retrieval contracts, models, and base lifecycle."""

from collections.abc import Sequence

import pytest
from pydantic import ValidationError

from tracewise.retrieval import (
    BaseRetriever,
    NotIndexedError,
    ProcessedText,
    RetrievalCandidate,
    RetrieverError,
)


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
        self._documents = {doc.id: doc for doc in documents}
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

        # Compute or lookup scores for indexed documents
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
                query_id=query.id,
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


class TestProcessedTextValidation:
    def test_valid_construction(self):
        pt = ProcessedText(
            id="REQ-001",
            content="authenticate user with email",
            tokens=["authenticate", "user", "email"],
            metadata={"length": 3},
        )
        assert pt.id == "REQ-001"
        assert pt.content == "authenticate user with email"
        assert pt.tokens == ["authenticate", "user", "email"]
        assert pt.metadata == {"length": 3}

    def test_empty_id_rejected(self):
        with pytest.raises(ValidationError, match="id"):
            ProcessedText(id="", content="text")
        with pytest.raises(ValidationError, match="id"):
            ProcessedText(id="   ", content="text")

    def test_mutation_rejected(self):
        pt = ProcessedText(id="DOC-1", content="hello")
        with pytest.raises(ValidationError):
            pt.content = "new"  # type: ignore[misc]

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            ProcessedText(id="DOC-1", content="hello", extra="forbidden")


class TestRetrieverLifecycle:
    def test_new_retriever_is_not_indexed(self):
        retriever = MockRetriever()
        assert retriever.is_indexed is False

    def test_retrieve_before_index_raises_not_indexed_error(self):
        retriever = MockRetriever()
        query = ProcessedText(id="Q-1", content="search query")
        with pytest.raises(NotIndexedError, match="cannot retrieve before indexing"):
            retriever.retrieve(query)

    def test_not_indexed_error_inherits_from_retriever_error(self):
        assert issubclass(NotIndexedError, RetrieverError)

    def test_index_changes_indexed_state(self):
        retriever = MockRetriever()
        docs = [
            ProcessedText(id="D-1", content="doc one"),
            ProcessedText(id="D-2", content="doc two"),
        ]
        retriever.index(docs)
        assert retriever.is_indexed is True

    def test_reindexing_replaces_index_completely(self):
        retriever = MockRetriever()
        initial_docs = [
            ProcessedText(id="D-1", content="doc one"),
            ProcessedText(id="D-2", content="doc two"),
        ]
        retriever.index(initial_docs)
        assert len(retriever._documents) == 2
        assert "D-1" in retriever._documents

        # Replace with a completely new corpus
        new_docs = [
            ProcessedText(id="D-3", content="doc three"),
        ]
        retriever.index(new_docs)
        assert len(retriever._documents) == 1
        assert "D-1" not in retriever._documents
        assert "D-3" in retriever._documents
        assert retriever.is_indexed is True

    def test_top_k_zero_raises_value_error(self):
        retriever = MockRetriever()
        retriever.index([ProcessedText(id="D-1", content="doc one")])
        query = ProcessedText(id="Q-1", content="query")
        with pytest.raises(ValueError, match="strictly positive"):
            retriever.retrieve(query, top_k=0)

    def test_top_k_negative_raises_value_error(self):
        retriever = MockRetriever()
        retriever.index([ProcessedText(id="D-1", content="doc one")])
        query = ProcessedText(id="Q-1", content="query")
        with pytest.raises(ValueError, match="strictly positive"):
            retriever.retrieve(query, top_k=-5)

    def test_top_k_none_returns_all_candidates(self):
        retriever = MockRetriever()
        docs = [ProcessedText(id=f"D-{i}", content=f"doc {i}") for i in range(5)]
        retriever.index(docs)
        query = ProcessedText(id="Q-1", content="query")

        candidates = retriever.retrieve(query, top_k=None)
        assert len(candidates) == 5

    def test_top_k_limits_returned_results(self):
        retriever = MockRetriever()
        docs = [ProcessedText(id=f"D-{i}", content=f"doc {i}") for i in range(10)]
        retriever.index(docs)
        query = ProcessedText(id="Q-1", content="query")

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
        docs = [ProcessedText(id=k, content="text") for k in retriever.preset_scores]
        retriever.index(docs)

        query = ProcessedText(id="Q-1", content="query")
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
        docs = [ProcessedText(id=k, content="text") for k in retriever.preset_scores]
        retriever.index(docs)

        query = ProcessedText(id="Q-1", content="query")
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
        docs = [ProcessedText(id=k, content="text") for k in retriever.preset_scores]
        retriever.index(docs)

        query = ProcessedText(id="Q-1", content="query")
        candidates = retriever.retrieve(query)

        ranks = [c.rank for c in candidates]
        assert ranks == [1, 2, 3, 4]

    def test_no_duplicate_target_ids_returned(self):
        retriever = MockRetriever()
        docs = [
            ProcessedText(id="T-1", content="doc 1"),
            ProcessedText(id="T-2", content="doc 2"),
            ProcessedText(id="T-3", content="doc 3"),
        ]
        retriever.index(docs)

        query = ProcessedText(id="Q-1", content="query")
        candidates = retriever.retrieve(query)

        target_ids = [c.target_id for c in candidates]
        assert len(target_ids) == len(set(target_ids))

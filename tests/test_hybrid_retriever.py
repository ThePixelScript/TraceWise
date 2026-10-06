"""Comprehensive unit tests for Milestone B4: Hybrid Retrieval Baseline.

Verifies:
- RRF score calculation
- Missing-rank handling
- Deterministic ranking and tie-breaking
- Duplicate target handling
- Empty rankings handling
- Integration with the BaseRetriever lifecycle and contracts
"""

from collections.abc import Sequence

import pytest

from tracewise.preprocessing.models import ProcessedText
from tracewise.retrieval.base import BaseRetriever
from tracewise.retrieval.exceptions import NotIndexedError
from tracewise.retrieval.hybrid import (
    HybridRetriever,
    compute_rrf_score,
    fuse_rrf_rankings,
)
from tracewise.retrieval.models import RetrievalCandidate


class DummyRetriever(BaseRetriever):
    """Deterministic mock retriever for unit testing fusion logic."""

    retriever_name: str = "dummy"

    def __init__(
        self, candidates_per_query: dict[str, list[RetrievalCandidate]] | None = None
    ) -> None:
        self._indexed: bool = False
        self._candidates = candidates_per_query or {}

    @property
    def is_indexed(self) -> bool:
        return self._indexed

    def index(self, documents: Sequence[ProcessedText]) -> None:
        self._indexed = True

    def retrieve(
        self,
        query: ProcessedText,
        top_k: int | None = None,
    ) -> list[RetrievalCandidate]:
        if not self._indexed:
            raise NotIndexedError(f"Retriever '{self.retriever_name}' is not indexed.")
        if top_k is not None and top_k <= 0:
            raise ValueError(f"top_k must be strictly positive, got {top_k}.")
        cands = self._candidates.get(query.source_id, [])
        if top_k is not None:
            return cands[:top_k]
        return list(cands)


def make_doc(source_id: str, text: str) -> ProcessedText:
    """Helper to construct minimal valid ProcessedText objects."""
    tokens = text.lower().split()
    return ProcessedText(
        source_id=source_id,
        original_text=text,
        normalized_text=text.lower(),
        tokens=tokens,
    )


# ==============================================================================
# 1. RRF Score Calculation Tests
# ==============================================================================


class TestRRFScoreCalculation:
    """Tests for compute_rrf_score function."""

    def test_single_ranking_calculation(self):
        # Rank 1 with k=60: 1 / (60 + 1) = 1 / 61
        assert pytest.approx(compute_rrf_score([1], k=60), rel=1e-6) == 1.0 / 61.0
        # Rank 10 with k=60: 1 / (60 + 10) = 1 / 70
        assert pytest.approx(compute_rrf_score([10], k=60), rel=1e-6) == 1.0 / 70.0

    def test_three_component_equal_contribution(self):
        # Target ranked #1, #2, #3 across three components
        expected = (1.0 / 61.0) + (1.0 / 62.0) + (1.0 / 63.0)
        assert pytest.approx(compute_rrf_score([1, 2, 3], k=60), rel=1e-6) == expected

    def test_custom_k_parameter(self):
        # Rank 1 with k=20: 1 / 21
        assert pytest.approx(compute_rrf_score([1], k=20), rel=1e-6) == 1.0 / 21.0
        assert pytest.approx(compute_rrf_score([1, 1], k=10), rel=1e-6) == 2.0 / 11.0

    def test_invalid_k_raises_value_error(self):
        with pytest.raises(
            ValueError, match="RRF constant k must be strictly positive"
        ):
            compute_rrf_score([1], k=0)
        with pytest.raises(
            ValueError, match="RRF constant k must be strictly positive"
        ):
            compute_rrf_score([1], k=-10)

    def test_invalid_rank_raises_value_error(self):
        with pytest.raises(ValueError, match="must be a positive 1-based integer"):
            compute_rrf_score([0], k=60)
        with pytest.raises(ValueError, match="must be a positive 1-based integer"):
            compute_rrf_score([-1], k=60)


# ==============================================================================
# 2. Missing-Rank Handling Tests
# ==============================================================================


class TestMissingRankHandling:
    """Verifies that missing ranks contribute 0.0 without errors."""

    def test_target_missing_from_some_components(self):
        # Target present in component 1 (rank 1), missing in 2 and 3
        score = compute_rrf_score([1, None, None], k=60)
        assert pytest.approx(score, rel=1e-6) == 1.0 / 61.0

        # Target present in components 1 and 3, missing in 2
        score = compute_rrf_score([2, None, 5], k=60)
        expected = (1.0 / 62.0) + (1.0 / 65.0)
        assert pytest.approx(score, rel=1e-6) == expected

    def test_target_missing_from_all_components(self):
        # Completely absent
        assert compute_rrf_score([None, None, None], k=60) == 0.0
        assert compute_rrf_score([], k=60) == 0.0

    def test_fuse_rankings_with_missing_targets(self):
        # Ranking 1 has docA, Ranking 2 has docB, Ranking 3 has docA and docB
        c1 = [
            RetrievalCandidate(
                query_id="q", target_id="docA", score=0.9, rank=1, retriever_name="r1"
            )
        ]
        c2 = [
            RetrievalCandidate(
                query_id="q", target_id="docB", score=0.8, rank=1, retriever_name="r2"
            )
        ]
        c3 = [
            RetrievalCandidate(
                query_id="q", target_id="docA", score=0.7, rank=1, retriever_name="r3"
            ),
            RetrievalCandidate(
                query_id="q", target_id="docB", score=0.6, rank=2, retriever_name="r3"
            ),
        ]

        fused = fuse_rrf_rankings([c1, c2, c3], k=60)
        # docA: rank 1 in r1, None in r2, rank 1 in r3 => 1/61 + 1/61 = 2/61 ~ 0.0327868
        # docB: None in r1, rank 1 in r2, rank 2 in r3 => 1/61 + 1/62 ~ 0.0325211
        assert fused[0][0] == "docA"
        assert fused[1][0] == "docB"
        assert pytest.approx(fused[0][1], rel=1e-6) == (1.0 / 61.0) + (1.0 / 61.0)
        assert pytest.approx(fused[1][1], rel=1e-6) == (1.0 / 61.0) + (1.0 / 62.0)


# ==============================================================================
# 3. Deterministic Ranking & Tie-Breaking Tests
# ==============================================================================


class TestDeterministicRankingAndTies:
    """Verifies deterministic sorting and tie-breaking by target_id."""

    def test_deterministic_tie_breaking_by_target_id(self):
        # Two documents with identical fused scores: docB and docA
        c1 = [
            RetrievalCandidate(
                query_id="q", target_id="docB", score=0.5, rank=1, retriever_name="r1"
            ),
            RetrievalCandidate(
                query_id="q", target_id="docA", score=0.5, rank=1, retriever_name="r1"
            ),
        ]
        fused = fuse_rrf_rankings([c1], k=60)
        # Same score (1/61) -> alphabetical tie-breaking: docA before docB
        assert fused[0][0] == "docA"
        assert fused[1][0] == "docB"

    def test_hybrid_retriever_assigns_consecutive_1_based_ranks(self):
        q = make_doc("Q1", "test query")
        c1 = [
            RetrievalCandidate(
                query_id="Q1", target_id="T2", score=0.9, rank=1, retriever_name="r1"
            ),
            RetrievalCandidate(
                query_id="Q1", target_id="T1", score=0.8, rank=2, retriever_name="r1"
            ),
            RetrievalCandidate(
                query_id="Q1", target_id="T3", score=0.7, rank=3, retriever_name="r1"
            ),
        ]
        r1 = DummyRetriever({"Q1": c1})
        r2 = DummyRetriever({"Q1": []})
        r3 = DummyRetriever({"Q1": []})
        r1.index([])
        r2.index([])
        r3.index([])

        hybrid = HybridRetriever(
            tfidf_retriever=r1, semantic_retriever=r2, structural_retriever=r3
        )
        hybrid._is_indexed = True
        results = hybrid.retrieve(q)

        assert len(results) == 3
        assert [c.rank for c in results] == [1, 2, 3]
        assert results[0].target_id == "T2"
        assert results[1].target_id == "T1"
        assert results[2].target_id == "T3"


# ==============================================================================
# 4. Duplicate Target Handling Tests
# ==============================================================================


class TestDuplicateTargetHandling:
    """Verifies that duplicate targets in a component ranking use best rank."""

    def test_duplicate_target_uses_best_rank(self):
        # Target docA appears twice in ranking r1: at rank 5 and rank 2
        c1 = [
            RetrievalCandidate(
                query_id="q", target_id="docA", score=0.4, rank=5, retriever_name="r1"
            ),
            RetrievalCandidate(
                query_id="q", target_id="docA", score=0.8, rank=2, retriever_name="r1"
            ),
        ]
        fused = fuse_rrf_rankings([c1], k=60)
        assert len(fused) == 1
        assert fused[0][0] == "docA"
        # Must use rank 2 (best rank), NOT rank 5 and NOT sum of both
        assert pytest.approx(fused[0][1], rel=1e-6) == 1.0 / (60.0 + 2.0)


# ==============================================================================
# 5. Empty Rankings Handling Tests
# ==============================================================================


class TestEmptyRankings:
    """Verifies graceful handling of empty ranking inputs."""

    def test_all_empty_rankings_with_corpus_targets(self):
        all_targets = ["docZ", "docA", "docM"]
        fused = fuse_rrf_rankings([], all_target_ids=all_targets, k=60)
        assert len(fused) == 3
        # All have score 0.0, sorted alphabetically by target_id
        assert [item[0] for item in fused] == ["docA", "docM", "docZ"]
        assert all(item[1] == 0.0 for item in fused)

    def test_completely_empty_returns_empty_list(self):
        fused = fuse_rrf_rankings([], all_target_ids=None, k=60)
        assert fused == []

    def test_one_empty_component_among_others(self):
        c1 = [
            RetrievalCandidate(
                query_id="q", target_id="docA", score=1.0, rank=1, retriever_name="r1"
            )
        ]
        fused = fuse_rrf_rankings([c1, []], k=60)
        assert len(fused) == 1
        assert fused[0][0] == "docA"
        assert pytest.approx(fused[0][1], rel=1e-6) == 1.0 / 61.0


# ==============================================================================
# 6. Integration & BaseRetriever Lifecycle Tests
# ==============================================================================


class TestHybridRetrieverIntegration:
    """Verifies HybridRetriever contracts, lifecycle, and end-to-end integration."""

    def test_unindexed_retrieval_raises_not_indexed_error(self):
        hybrid = HybridRetriever()
        q = make_doc("Q", "sample query")
        with pytest.raises(NotIndexedError, match="cannot retrieve before indexing"):
            hybrid.retrieve(q)

    def test_invalid_top_k_raises_value_error(self):
        docs = [make_doc("D1", "hello world")]
        hybrid = HybridRetriever()
        hybrid.index(docs)
        q = make_doc("Q", "hello")
        with pytest.raises(ValueError, match="top_k must be strictly positive"):
            hybrid.retrieve(q, top_k=0)
        with pytest.raises(ValueError, match="top_k must be strictly positive"):
            hybrid.retrieve(q, top_k=-5)

    def test_empty_documents_index_raises_value_error(self):
        hybrid = HybridRetriever()
        with pytest.raises(ValueError, match="Cannot index an empty document sequence"):
            hybrid.index([])

    def test_duplicate_source_id_index_raises_value_error(self):
        docs = [make_doc("D1", "hello"), make_doc("D1", "world")]
        hybrid = HybridRetriever()
        with pytest.raises(ValueError, match="Duplicate source_id"):
            hybrid.index(docs)

    def test_top_k_limits_output_correctly(self):
        docs = [
            make_doc("D1", "apple pie"),
            make_doc("D2", "banana bread"),
            make_doc("D3", "cherry tart"),
        ]
        hybrid = HybridRetriever()
        hybrid.index(docs)
        q = make_doc("Q", "apple banana")

        results = hybrid.retrieve(q, top_k=2)
        assert len(results) == 2
        assert results[0].rank == 1
        assert results[1].rank == 2

    def test_candidate_metadata_contains_rrf_telemetry(self):
        docs = [
            make_doc("D1", "user authentication login"),
            make_doc("D2", "payment processing checkout"),
        ]
        hybrid = HybridRetriever()
        hybrid.index(docs)
        q = make_doc("Q", "authentication user")

        results = hybrid.retrieve(q)
        assert len(results) == 2
        top_cand = results[0]
        assert top_cand.retriever_name == "hybrid"
        assert top_cand.metadata["rrf_k"] == 60
        assert "component_ranks" in top_cand.metadata
        comp_ranks = top_cand.metadata["component_ranks"]
        assert "tfidf" in comp_ranks
        assert "semantic" in comp_ranks
        assert "structural" in comp_ranks

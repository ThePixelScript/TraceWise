"""Tests for dense semantic retrieval baseline (Milestone 4A)."""

from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pytest

from tracewise.evaluation import BenchmarkRunner
from tracewise.preprocessing.models import ProcessedText
from tracewise.retrieval import NotIndexedError, SemanticRetriever


def make_doc(
    source_id: str,
    tokens: list[str],
    normalized_text: str | None = None,
) -> ProcessedText:
    """Helper to create minimal valid ProcessedText instances for tests."""
    norm = normalized_text if normalized_text is not None else " ".join(tokens)
    return ProcessedText(
        source_id=source_id,
        original_text=norm,
        normalized_text=norm,
        tokens=tokens,
    )


class DeterministicMockEmbedder:
    """Mock embedder providing deterministic dense embeddings offline without network.

    Maps words to fixed basis vectors in R^dim.
    """

    def __init__(
        self, vocab_map: dict[str, list[float]] | None = None, dim: int = 4
    ) -> None:
        self.dim = dim
        self.vocab_map = vocab_map or {
            "auth": [1.0, 0.0, 0.0, 0.0],
            "token": [0.0, 1.0, 0.0, 0.0],
            "database": [0.0, 0.0, 1.0, 0.0],
            "query": [0.0, 0.0, 0.0, 1.0],
            "login": [0.8, 0.6, 0.0, 0.0],
        }

    def __call__(self, texts: Sequence[str]) -> np.ndarray:
        out: list[list[float]] = []
        for text in texts:
            words = text.lower().split()
            vec = np.zeros(self.dim, dtype=np.float32)
            for w in words:
                if w in self.vocab_map:
                    raw = np.array(self.vocab_map[w], dtype=np.float32)
                    lim = min(self.dim, len(raw))
                    vec[:lim] += raw[:lim]
            out.append(vec.tolist())
        return np.asarray(out, dtype=np.float32)


class TestSemanticLifecycleAndValidation:
    def test_retrieve_before_index_raises_not_indexed_error(self):
        retriever = SemanticRetriever(embedder=DeterministicMockEmbedder())
        assert retriever.is_indexed is False
        query = make_doc("Q-1", ["auth", "token"])
        with pytest.raises(NotIndexedError, match="cannot retrieve before indexing"):
            retriever.retrieve(query)

    def test_empty_index_raises_value_error(self):
        retriever = SemanticRetriever(embedder=DeterministicMockEmbedder())
        with pytest.raises(ValueError, match="empty"):
            retriever.index([])
        assert retriever.is_indexed is False

    def test_duplicate_source_id_raises_value_error(self):
        retriever = SemanticRetriever(embedder=DeterministicMockEmbedder())
        docs = [
            make_doc("DOC-1", ["auth"]),
            make_doc("DOC-1", ["token"]),
        ]
        with pytest.raises(ValueError, match="Duplicate document source_id"):
            retriever.index(docs)
        assert retriever.is_indexed is False

    def test_successful_index_sets_is_indexed_true(self):
        retriever = SemanticRetriever(embedder=DeterministicMockEmbedder())
        docs = [
            make_doc("DOC-1", ["auth"]),
            make_doc("DOC-2", ["database"]),
        ]
        retriever.index(docs)
        assert retriever.is_indexed is True
        assert retriever._dim == 4

    def test_reindex_replaces_previous_corpus(self):
        retriever = SemanticRetriever(embedder=DeterministicMockEmbedder())
        retriever.index([make_doc("D-1", ["auth"]), make_doc("D-2", ["database"])])
        assert retriever._target_ids == ["D-1", "D-2"]

        retriever.index([make_doc("D-3", ["query"])])
        assert retriever._target_ids == ["D-3"]

    def test_top_k_zero_or_negative_raises_value_error(self):
        retriever = SemanticRetriever(embedder=DeterministicMockEmbedder())
        retriever.index([make_doc("D-1", ["auth"])])
        query = make_doc("Q-1", ["auth"])

        with pytest.raises(ValueError, match="strictly positive"):
            retriever.retrieve(query, top_k=0)

        with pytest.raises(ValueError, match="strictly positive"):
            retriever.retrieve(query, top_k=-1)

    def test_query_dimension_mismatch_raises_value_error(self):
        retriever = SemanticRetriever(embedder=DeterministicMockEmbedder(dim=4))
        retriever.index([make_doc("D-1", ["auth"])])

        mismatched_embedder = DeterministicMockEmbedder(dim=3)
        retriever._embedder_func = mismatched_embedder

        query = make_doc("Q-1", ["auth"])
        with pytest.raises(ValueError, match="dimension"):
            retriever.retrieve(query)


class TestSemanticCosineSimilarityCalculations:
    def test_orthogonal_vectors_yield_zero_score(self):
        # auth is [1, 0, 0, 0], database is [0, 0, 1, 0] -> dot product = 0.0
        retriever = SemanticRetriever(embedder=DeterministicMockEmbedder())
        retriever.index([make_doc("D-db", ["database"])])

        query = make_doc("Q-auth", ["auth"])
        candidates = retriever.retrieve(query)

        assert len(candidates) == 1
        assert candidates[0].target_id == "D-db"
        assert candidates[0].score == pytest.approx(0.0, abs=1e-6)

    def test_identical_vectors_yield_unit_score(self):
        # auth is [1, 0, 0, 0] -> normalized is [1, 0, 0, 0] -> dot = 1.0
        retriever = SemanticRetriever(embedder=DeterministicMockEmbedder())
        retriever.index([make_doc("D-auth", ["auth"])])

        query = make_doc("Q-auth", ["auth"])
        candidates = retriever.retrieve(query)

        assert len(candidates) == 1
        assert candidates[0].target_id == "D-auth"
        assert candidates[0].score == pytest.approx(1.0, abs=1e-6)

    def test_known_cosine_similarity(self):
        # auth: [1, 0, 0, 0] (unit length)
        # login: [0.8, 0.6, 0.0, 0.0] (norm = sqrt(0.64 + 0.36) = 1.0)
        # Cosine similarity between auth and login = 1.0 * 0.8 + 0.0 = 0.8
        retriever = SemanticRetriever(embedder=DeterministicMockEmbedder())
        retriever.index(
            [make_doc("D-login", ["login"]), make_doc("D-db", ["database"])]
        )

        query = make_doc("Q-auth", ["auth"])
        candidates = retriever.retrieve(query)

        assert len(candidates) == 2
        c_login = next(c for c in candidates if c.target_id == "D-login")
        c_db = next(c for c in candidates if c.target_id == "D-db")

        assert c_login.score == pytest.approx(0.8, abs=1e-5)
        assert c_db.score == pytest.approx(0.0, abs=1e-5)
        assert c_login.rank == 1
        assert c_db.rank == 2

    def test_negative_cosine_clamped_to_zero(self):
        # Embedder producing opposite vectors
        custom_embedder = DeterministicMockEmbedder(
            vocab_map={"pos": [1.0, 0.0], "neg": [-1.0, 0.0]}, dim=2
        )
        retriever = SemanticRetriever(embedder=custom_embedder)
        retriever.index([make_doc("D-neg", ["neg"])])

        query = make_doc("Q-pos", ["pos"])
        candidates = retriever.retrieve(query)

        assert len(candidates) == 1
        # Raw dot product is -1.0, must be clamped to 0.0
        assert candidates[0].score == 0.0

    def test_blank_or_zero_norm_query_gives_zero_scores(self):
        retriever = SemanticRetriever(embedder=DeterministicMockEmbedder())
        retriever.index([make_doc("D1", ["auth"]), make_doc("D2", ["database"])])

        empty_query = make_doc("Q-empty", [], normalized_text="")
        candidates = retriever.retrieve(empty_query)

        assert len(candidates) == 2
        for c in candidates:
            assert c.score == 0.0


class TestSemanticOrderingAndDeterminism:
    def test_ties_broken_by_target_id_ascending(self):
        retriever = SemanticRetriever(embedder=DeterministicMockEmbedder())
        retriever.index(
            [
                make_doc("z_target", ["database"]),
                make_doc("a_target", ["database"]),
                make_doc("m_target", ["database"]),
            ]
        )
        query = make_doc("Q", ["database"])
        candidates = retriever.retrieve(query)

        assert len(candidates) == 3
        assert candidates[0].score == candidates[1].score == candidates[2].score
        assert [c.target_id for c in candidates] == [
            "a_target",
            "m_target",
            "z_target",
        ]
        assert [c.rank for c in candidates] == [1, 2, 3]

    def test_top_k_limits_output(self):
        retriever = SemanticRetriever(embedder=DeterministicMockEmbedder())
        docs = [make_doc(f"D-{i}", ["auth"]) for i in range(10)]
        retriever.index(docs)

        query = make_doc("Q", ["auth"])
        candidates = retriever.retrieve(query, top_k=4)

        assert len(candidates) == 4
        assert [c.rank for c in candidates] == [1, 2, 3, 4]

    def test_atomic_failure_on_reindex(self):
        retriever = SemanticRetriever(embedder=DeterministicMockEmbedder())
        valid_docs = [make_doc("D1", ["auth"]), make_doc("D2", ["token"])]
        retriever.index(valid_docs)
        assert retriever.is_indexed is True

        # Malformed batch with duplicates
        invalid_docs = [make_doc("ERR", ["auth"]), make_doc("ERR", ["token"])]
        with pytest.raises(ValueError, match="Duplicate document source_id"):
            retriever.index(invalid_docs)

        # State should be completely unchanged
        assert retriever.is_indexed is True
        assert retriever._target_ids == ["D1", "D2"]


class TestSemanticBenchmarkRunnerIntegration:
    @pytest.fixture
    def sample_project_dir(self) -> Path:
        return (
            Path(__file__).resolve().parent.parent
            / "data"
            / "fixtures"
            / "sample_project"
        )

    def test_semantic_source_code_only_evaluation(self, sample_project_dir: Path):
        # Uses the real pretrained fastembed model
        retriever = SemanticRetriever(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )
        runner = BenchmarkRunner(project_root=sample_project_dir)
        result = runner.run(
            retriever=retriever,
            artifact_type_filter="source_code",
        )

        assert result.retriever_name == "semantic"
        assert result.num_queries == 10
        assert result.metadata["total_target_chunks"] == 26
        assert result.metadata["artifact_type_filter"] == "source_code"

        total_relevant = sum(q.num_relevant for q in result.query_results.values())
        assert total_relevant == 16

        for q_res in result.query_results.values():
            assert q_res.num_retrieved == 26

        # Exact official B2 source-code baseline metrics:
        assert result.mean_average_precision == pytest.approx(0.7350, abs=1e-3)
        assert result.mean_reciprocal_rank == pytest.approx(0.8500, abs=1e-3)

        assert result.mean_precision_at_k[1] == pytest.approx(0.7000, abs=1e-3)
        assert result.mean_precision_at_k[3] == pytest.approx(0.4333, abs=1e-3)
        assert result.mean_precision_at_k[5] == pytest.approx(0.2800, abs=1e-3)

        assert result.mean_recall_at_k[1] == pytest.approx(0.4500, abs=1e-3)
        assert result.mean_recall_at_k[3] == pytest.approx(0.8500, abs=1e-3)
        assert result.mean_recall_at_k[5] == pytest.approx(0.9000, abs=1e-3)

    def test_semantic_evaluation_determinism(self, sample_project_dir: Path):
        runner = BenchmarkRunner(project_root=sample_project_dir)
        res1 = runner.run(
            retriever=SemanticRetriever(
                model_name="sentence-transformers/all-MiniLM-L6-v2"
            ),
            artifact_type_filter="source_code",
        )
        res2 = runner.run(
            retriever=SemanticRetriever(
                model_name="sentence-transformers/all-MiniLM-L6-v2"
            ),
            artifact_type_filter="source_code",
        )

        assert res1.mean_average_precision == res2.mean_average_precision
        assert res1.mean_reciprocal_rank == res2.mean_reciprocal_rank
        assert res1.mean_precision_at_k == res2.mean_precision_at_k
        assert res1.mean_recall_at_k == res2.mean_recall_at_k

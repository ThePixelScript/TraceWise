"""Tests for BM25 lexical retrieval baseline (Milestone 3B)."""

import math
from pathlib import Path

import numpy as np
import pytest

from tracewise.evaluation import BenchmarkRunner
from tracewise.preprocessing.models import ProcessedText
from tracewise.retrieval import BM25Retriever, NotIndexedError


def make_doc(source_id: str, tokens: list[str]) -> ProcessedText:
    """Helper to create minimal valid ProcessedText instances for tests."""
    return ProcessedText(
        source_id=source_id,
        original_text=" ".join(tokens),
        normalized_text=" ".join(tokens),
        tokens=tokens,
    )


class TestBM25LifecycleAndValidation:
    def test_retrieve_before_index_raises_not_indexed_error(self):
        retriever = BM25Retriever()
        assert retriever.is_indexed is False
        query = make_doc("Q-1", ["auth", "token"])
        with pytest.raises(NotIndexedError, match="cannot retrieve before indexing"):
            retriever.retrieve(query)

    def test_empty_index_raises_value_error(self):
        retriever = BM25Retriever()
        with pytest.raises(ValueError, match="empty"):
            retriever.index([])
        assert retriever.is_indexed is False

    def test_duplicate_source_id_raises_value_error(self):
        retriever = BM25Retriever()
        docs = [
            make_doc("DOC-1", ["user", "login"]),
            make_doc("DOC-1", ["auth", "token"]),
        ]
        with pytest.raises(ValueError, match="Duplicate document source_id"):
            retriever.index(docs)
        assert retriever.is_indexed is False

    def test_successful_index_sets_is_indexed_true(self):
        retriever = BM25Retriever()
        docs = [
            make_doc("DOC-1", ["auth", "token"]),
            make_doc("DOC-2", ["database", "query"]),
        ]
        retriever.index(docs)
        assert retriever.is_indexed is True

    def test_reindex_replaces_previous_corpus(self):
        retriever = BM25Retriever()
        initial_docs = [
            make_doc("D-1", ["token", "one"]),
            make_doc("D-2", ["token", "two"]),
        ]
        retriever.index(initial_docs)
        assert retriever._target_ids == ["D-1", "D-2"]

        new_docs = [
            make_doc("D-3", ["fresh", "corpus"]),
        ]
        retriever.index(new_docs)
        assert retriever._target_ids == ["D-3"]
        assert "token" not in retriever._term_to_index
        assert "fresh" in retriever._term_to_index

    def test_top_k_zero_raises_value_error(self):
        retriever = BM25Retriever()
        retriever.index([make_doc("D-1", ["auth"])])
        query = make_doc("Q-1", ["auth"])
        with pytest.raises(ValueError, match="strictly positive"):
            retriever.retrieve(query, top_k=0)

    def test_top_k_negative_raises_value_error(self):
        retriever = BM25Retriever()
        retriever.index([make_doc("D-1", ["auth"])])
        query = make_doc("Q-1", ["auth"])
        with pytest.raises(ValueError, match="strictly positive"):
            retriever.retrieve(query, top_k=-3)

    def test_invalid_k1_raises_value_error(self):
        with pytest.raises(ValueError, match="k1 must be non-negative"):
            BM25Retriever(k1=-0.1)

    def test_invalid_b_raises_value_error(self):
        with pytest.raises(ValueError, match="b must be between 0.0 and 1.0"):
            BM25Retriever(b=-0.01)
        with pytest.raises(ValueError, match="b must be between 0.0 and 1.0"):
            BM25Retriever(b=1.01)

    def test_custom_valid_k1_and_b(self):
        retriever = BM25Retriever(k1=1.2, b=0.5)
        assert retriever.k1 == 1.2
        assert retriever.b == 0.5


class TestBM25HandCalculatedCorpus:
    """Exact hand-calculated 2-document corpus verified against analytical formulas."""

    def test_hand_calculated_corpus_df_idf_and_scores(self):
        # D1: tokens = ["auth", "token"] (|D1| = 2)
        # D2: tokens = ["auth", "service", "login"] (|D2| = 3)
        # N = 2, avgdl = (2 + 3) / 2 = 2.5
        d1 = make_doc("D1", ["auth", "token"])
        d2 = make_doc("D2", ["auth", "service", "login"])
        retriever = BM25Retriever(k1=1.5, b=0.75)
        retriever.index([d1, d2])

        # Vocabulary is sorted unique target tokens
        assert retriever._vocabulary == ["auth", "login", "service", "token"]
        assert retriever._doc_lengths.tolist() == [2.0, 3.0]
        assert retriever._avg_doc_len == 2.5

        auth_idx = retriever._term_to_index["auth"]
        token_idx = retriever._term_to_index["token"]
        service_idx = retriever._term_to_index["service"]
        login_idx = retriever._term_to_index["login"]

        # Hand-calculated smoothed non-negative IDFs:
        # IDF(t) = ln(1 + (N - DF(t) + 0.5) / (DF(t) + 0.5))
        # IDF(auth) = ln(1 + (2 - 2 + 0.5) / (2 + 0.5)) = ln(1 + 0.2) = ln(1.2)
        # IDF(token) = ln(1 + (2 - 1 + 0.5) / (1 + 0.5)) = ln(1 + 1.0) = ln(2.0)
        expected_idf_auth = math.log(1.2)
        expected_idf_token = math.log(2.0)
        expected_idf_service = math.log(2.0)
        expected_idf_login = math.log(2.0)

        assert retriever._idf[auth_idx] == pytest.approx(expected_idf_auth, abs=1e-12)
        assert retriever._idf[token_idx] == pytest.approx(expected_idf_token, abs=1e-12)
        assert retriever._idf[service_idx] == pytest.approx(
            expected_idf_service, abs=1e-12
        )
        assert retriever._idf[login_idx] == pytest.approx(expected_idf_login, abs=1e-12)

        # Hand-calculated BM25 scores for Query Q1: ["auth", "token"]
        # For D1 (L=2, L/avgdl = 0.8):
        #   len_norm = 1 - 0.75 + 0.75 * 0.8 = 0.85
        #   TF_BM25(auth, D1) = (1 * 2.5) / (1 + 1.5 * 0.85) = 2.5 / 2.275 = 100 / 91
        #   TF_BM25(token, D1) = 100 / 91
        #   Score(Q1, D1) = ln(1.2) * (100 / 91) + ln(2.0) * (100 / 91)
        #                 = ln(2.4) * (100 / 91) ≈ 0.962054
        # For D2 (L=3, L/avgdl = 1.2):
        #   len_norm = 1 - 0.75 + 0.75 * 1.2 = 1.15
        #   TF_BM25(auth, D2) = (1 * 2.5) / (1 + 1.5 * 1.15) = 2.5 / 2.725 = 100 / 109
        #   Score(Q1, D2) = ln(1.2) * (100 / 109) ≈ 0.167267
        q1 = make_doc("Q1", ["auth", "token"])
        candidates = retriever.retrieve(q1)

        assert len(candidates) == 2
        c_d1 = next(c for c in candidates if c.target_id == "D1")
        c_d2 = next(c for c in candidates if c.target_id == "D2")

        expected_score_d1 = math.log(2.4) * (100.0 / 91.0)
        expected_score_d2 = math.log(1.2) * (100.0 / 109.0)

        assert c_d1.score == pytest.approx(expected_score_d1, abs=1e-6)
        assert c_d2.score == pytest.approx(expected_score_d2, abs=1e-6)
        assert c_d1.rank == 1
        assert c_d2.rank == 2

    def test_sublinear_tf_with_repeated_tokens(self):
        # D1 has 1 occurrence of "term", D2 has 2 occurrences of "term"
        # Both documents have identical length
        d1 = make_doc("D1", ["term", "x"])
        d2 = make_doc("D2", ["term", "term"])
        retriever = BM25Retriever(k1=1.5, b=0.75)
        retriever.index([d1, d2])

        q = make_doc("Q", ["term"])
        candidates = retriever.retrieve(q)

        c_d1 = next(c for c in candidates if c.target_id == "D1")
        c_d2 = next(c for c in candidates if c.target_id == "D2")

        # In D1, count = 1: TF_BM25 = 2.5 / 2.5 = 1.0
        # In D2, count = 2:
        # TF_BM25 = (2 * 2.5) / (2 + 1.5 * 1.0) = 5.0 / 3.5 = 10/7 ≈ 1.42857
        # 1.42857 < 2 * 1.0 => sublinear saturation confirmed
        assert c_d2.score > c_d1.score
        assert c_d2.score < 2.0 * c_d1.score

    def test_length_normalization_penalty(self):
        # D_short has 1 matching token out of 2 total tokens
        # D_long has 1 matching token out of 10 total tokens
        d_short = make_doc("D_short", ["auth", "a"])
        d_long = make_doc(
            "D_long",
            ["auth", "b", "c", "d", "e", "f", "g", "h", "i", "j"],
        )
        retriever = BM25Retriever(k1=1.5, b=0.75)
        retriever.index([d_short, d_long])

        q = make_doc("Q", ["auth"])
        candidates = retriever.retrieve(q)

        c_short = next(c for c in candidates if c.target_id == "D_short")
        c_long = next(c for c in candidates if c.target_id == "D_long")

        # Shorter document has higher term density, so length normalization rewards it
        assert c_short.score > c_long.score

    def test_b_zero_disables_length_normalization(self):
        # With b = 0.0, document length is ignored
        d_short = make_doc("D_short", ["auth", "a"])
        d_long = make_doc(
            "D_long",
            ["auth", "b", "c", "d", "e", "f", "g", "h", "i", "j"],
        )
        retriever = BM25Retriever(k1=1.5, b=0.0)
        retriever.index([d_short, d_long])

        q = make_doc("Q", ["auth"])
        candidates = retriever.retrieve(q)

        c_short = next(c for c in candidates if c.target_id == "D_short")
        c_long = next(c for c in candidates if c.target_id == "D_long")

        # Without length normalization, identical term frequencies give identical scores
        assert c_short.score == pytest.approx(c_long.score, abs=1e-12)


class TestBM25EdgeCases:
    def test_empty_query_tokens_gives_zero_scores(self):
        retriever = BM25Retriever()
        retriever.index(
            [
                make_doc("D1", ["auth", "token"]),
                make_doc("D2", ["database", "connection"]),
            ]
        )
        query = make_doc("Q-empty", [])
        candidates = retriever.retrieve(query)
        assert len(candidates) == 2
        for c in candidates:
            assert c.score == 0.0

    def test_query_entirely_outside_vocabulary_gives_zero_scores(self):
        retriever = BM25Retriever()
        retriever.index(
            [
                make_doc("D1", ["auth", "token"]),
                make_doc("D2", ["database", "connection"]),
            ]
        )
        query = make_doc("Q-outside", ["quantum", "teleportation"])
        candidates = retriever.retrieve(query)
        assert len(candidates) == 2
        for c in candidates:
            assert c.score == 0.0

    def test_target_with_empty_tokens_scores_zero(self):
        retriever = BM25Retriever()
        retriever.index(
            [
                make_doc("D-empty", []),
                make_doc("D-has-tokens", ["auth", "service"]),
            ]
        )
        query = make_doc("Q1", ["auth"])
        candidates = retriever.retrieve(query)
        c_empty = next(c for c in candidates if c.target_id == "D-empty")
        c_has = next(c for c in candidates if c.target_id == "D-has-tokens")
        assert c_empty.score == 0.0
        assert c_has.score > 0.0

    def test_query_with_unseen_and_seen_tokens(self):
        retriever = BM25Retriever()
        retriever.index(
            [
                make_doc("D1", ["auth", "token"]),
                make_doc("D2", ["cache", "memory"]),
            ]
        )
        query = make_doc("Q1", ["auth", "unseen_token_xyz"])
        candidates = retriever.retrieve(query)
        c_d1 = next(c for c in candidates if c.target_id == "D1")
        assert c_d1.score > 0.0
        c_d2 = next(c for c in candidates if c.target_id == "D2")
        assert c_d2.score == 0.0

    def test_single_document_corpus(self):
        retriever = BM25Retriever()
        retriever.index([make_doc("SINGLE", ["auth", "user"])])
        query = make_doc("Q1", ["auth"])
        candidates = retriever.retrieve(query)
        assert len(candidates) == 1
        assert candidates[0].target_id == "SINGLE"
        assert candidates[0].score > 0.0
        assert candidates[0].rank == 1

    def test_all_documents_empty_tokens(self):
        retriever = BM25Retriever()
        retriever.index([make_doc("D1", []), make_doc("D2", [])])
        query = make_doc("Q1", ["auth"])
        candidates = retriever.retrieve(query)
        assert len(candidates) == 2
        for c in candidates:
            assert c.score == 0.0


class TestBM25OrderingAndRankInvariants:
    def test_equal_scores_broken_by_target_id_ascending(self):
        retriever = BM25Retriever()
        retriever.index(
            [
                make_doc("z_target", ["identical", "token"]),
                make_doc("a_target", ["identical", "token"]),
                make_doc("m_target", ["identical", "token"]),
            ]
        )
        query = make_doc("Q1", ["identical", "token"])
        candidates = retriever.retrieve(query)
        assert len(candidates) == 3
        assert candidates[0].score == candidates[1].score == candidates[2].score
        assert [c.target_id for c in candidates] == [
            "a_target",
            "m_target",
            "z_target",
        ]

    def test_ranks_are_consecutive_one_to_n(self):
        retriever = BM25Retriever()
        docs = [make_doc(f"DOC-{i}", ["term", f"specific_{i}"]) for i in range(5)]
        retriever.index(docs)
        query = make_doc("Q1", ["term"])
        candidates = retriever.retrieve(query, top_k=None)
        assert len(candidates) == 5
        assert [c.rank for c in candidates] == [1, 2, 3, 4, 5]

    def test_ranks_are_consecutive_one_to_k_for_top_k(self):
        retriever = BM25Retriever()
        docs = [make_doc(f"DOC-{i}", ["term", f"specific_{i}"]) for i in range(5)]
        retriever.index(docs)
        query = make_doc("Q1", ["term"])
        candidates = retriever.retrieve(query, top_k=3)
        assert len(candidates) == 3
        assert [c.rank for c in candidates] == [1, 2, 3]

    def test_top_k_limits_output_length(self):
        retriever = BM25Retriever()
        docs = [make_doc(f"DOC-{i}", ["term"]) for i in range(10)]
        retriever.index(docs)
        query = make_doc("Q1", ["term"])
        candidates = retriever.retrieve(query, top_k=4)
        assert len(candidates) == 4

    def test_top_k_none_returns_all_including_zero_scores(self):
        retriever = BM25Retriever()
        docs = [
            make_doc("MATCH", ["relevant", "term"]),
            make_doc("NON_MATCH_1", ["other", "stuff"]),
            make_doc("NON_MATCH_2", ["something", "else"]),
        ]
        retriever.index(docs)
        query = make_doc("Q1", ["relevant"])
        candidates = retriever.retrieve(query, top_k=None)
        assert len(candidates) == 3
        assert candidates[0].target_id == "MATCH"
        assert candidates[0].score > 0.0
        assert candidates[1].score == 0.0
        assert candidates[2].score == 0.0

    def test_no_duplicate_target_ids_in_output(self):
        retriever = BM25Retriever()
        docs = [make_doc(f"T-{i}", ["token", f"v_{i}"]) for i in range(7)]
        retriever.index(docs)
        query = make_doc("Q1", ["token"])
        candidates = retriever.retrieve(query)
        target_ids = [c.target_id for c in candidates]
        assert len(target_ids) == len(set(target_ids))


class TestBM25DeterminismAndAtomicFailure:
    def test_indexing_same_corpus_repeatedly_gives_identical_state(self):
        docs = [
            make_doc("D1", ["auth", "token", "service"]),
            make_doc("D2", ["database", "query", "service"]),
            make_doc("D3", ["frontend", "ui", "component"]),
        ]
        r1 = BM25Retriever()
        r1.index(docs)

        r2 = BM25Retriever()
        r2.index(docs)

        assert r1._vocabulary == r2._vocabulary
        assert r1._term_to_index == r2._term_to_index
        np.testing.assert_allclose(r1._idf, r2._idf)
        np.testing.assert_allclose(r1._doc_matrix, r2._doc_matrix)

        q = make_doc("Q", ["auth", "service"])
        c1 = r1.retrieve(q)
        c2 = r2.retrieve(q)
        assert [(c.target_id, c.score, c.rank) for c in c1] == [
            (c.target_id, c.score, c.rank) for c in c2
        ]

    def test_repeated_retrieve_calls_do_not_modify_index(self):
        docs = [
            make_doc("D1", ["auth", "token"]),
            make_doc("D2", ["service", "token"]),
        ]
        retriever = BM25Retriever()
        retriever.index(docs)

        matrix_before = retriever._doc_matrix.copy()
        idf_before = retriever._idf.copy()

        q = make_doc("Q", ["auth"])
        for _ in range(5):
            retriever.retrieve(q)

        np.testing.assert_array_equal(retriever._doc_matrix, matrix_before)
        np.testing.assert_array_equal(retriever._idf, idf_before)
        assert retriever.is_indexed is True

    def test_invalid_reindex_preserves_previous_valid_state(self):
        retriever = BM25Retriever()
        valid_docs = [
            make_doc("D1", ["auth", "token"]),
            make_doc("D2", ["service", "token"]),
        ]
        retriever.index(valid_docs)
        assert retriever.is_indexed is True
        assert len(retriever._target_ids) == 2

        q = make_doc("Q", ["auth"])
        initial_results = retriever.retrieve(q)

        duplicate_docs = [
            make_doc("ERR", ["one"]),
            make_doc("ERR", ["two"]),
        ]
        with pytest.raises(ValueError, match="Duplicate document source_id"):
            retriever.index(duplicate_docs)

        assert retriever.is_indexed is True
        assert retriever._target_ids == ["D1", "D2"]
        after_results = retriever.retrieve(q)
        assert [(c.target_id, c.score) for c in initial_results] == [
            (c.target_id, c.score) for c in after_results
        ]

    def test_empty_reindex_preserves_previous_valid_state(self):
        retriever = BM25Retriever()
        valid_docs = [make_doc("D1", ["auth"])]
        retriever.index(valid_docs)

        with pytest.raises(ValueError, match="empty"):
            retriever.index([])

        assert retriever.is_indexed is True
        assert retriever._target_ids == ["D1"]


class TestBM25BenchmarkRunnerIntegration:
    @pytest.fixture
    def sample_project_dir(self) -> Path:
        return (
            Path(__file__).resolve().parent.parent
            / "data"
            / "fixtures"
            / "sample_project"
        )

    def test_bm25_source_code_only_evaluation(self, sample_project_dir: Path):
        retriever = BM25Retriever(k1=1.5, b=0.75)
        runner = BenchmarkRunner(project_root=sample_project_dir)
        result = runner.run(
            retriever=retriever,
            artifact_type_filter="source_code",
        )

        assert result.retriever_name == "bm25"
        assert result.num_queries == 10
        assert result.metadata["total_target_chunks"] == 26
        assert result.metadata["artifact_type_filter"] == "source_code"

        # Verify only 16 source-code links evaluated across queries
        total_relevant = sum(q.num_relevant for q in result.query_results.values())
        assert total_relevant == 16

        # Verify all queries retrieved 26 source-code chunks
        for q_res in result.query_results.values():
            assert q_res.num_retrieved == 26

        # Exact official B1 source-code baseline metrics:
        assert result.mean_average_precision == pytest.approx(0.7030, abs=1e-3)
        assert result.mean_reciprocal_rank == pytest.approx(0.8033, abs=1e-3)

        assert result.mean_precision_at_k[1] == pytest.approx(0.7000, abs=1e-3)
        assert result.mean_precision_at_k[3] == pytest.approx(0.3333, abs=1e-3)
        assert result.mean_precision_at_k[5] == pytest.approx(0.2600, abs=1e-3)

        assert result.mean_recall_at_k[1] == pytest.approx(0.5000, abs=1e-3)
        assert result.mean_recall_at_k[3] == pytest.approx(0.7000, abs=1e-3)
        assert result.mean_recall_at_k[5] == pytest.approx(0.8500, abs=1e-3)

    def test_bm25_evaluation_determinism(self, sample_project_dir: Path):
        runner = BenchmarkRunner(project_root=sample_project_dir)
        res1 = runner.run(
            retriever=BM25Retriever(k1=1.5, b=0.75),
            artifact_type_filter="source_code",
        )
        res2 = runner.run(
            retriever=BM25Retriever(k1=1.5, b=0.75),
            artifact_type_filter="source_code",
        )

        assert res1.mean_average_precision == res2.mean_average_precision
        assert res1.mean_reciprocal_rank == res2.mean_reciprocal_rank
        assert res1.mean_precision_at_k == res2.mean_precision_at_k
        assert res1.mean_recall_at_k == res2.mean_recall_at_k

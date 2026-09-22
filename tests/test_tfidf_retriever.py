"""Tests for TF-IDF + Cosine retrieval baseline (Milestone 2B)."""

import math

import numpy as np
import pytest

from tracewise.preprocessing.models import ProcessedText
from tracewise.retrieval import NotIndexedError, RetrievalCandidate, TfidfRetriever


def make_doc(source_id: str, tokens: list[str]) -> ProcessedText:
    """Helper to create minimal valid ProcessedText instances for tests."""
    return ProcessedText(
        source_id=source_id,
        original_text=" ".join(tokens),
        normalized_text=" ".join(tokens),
        tokens=tokens,
    )


class TestTfidfLifecycleAndValidation:
    def test_retrieve_before_index_raises_not_indexed_error(self):
        retriever = TfidfRetriever()
        assert retriever.is_indexed is False
        query = make_doc("Q-1", ["auth", "token"])
        with pytest.raises(NotIndexedError, match="cannot retrieve before indexing"):
            retriever.retrieve(query)

    def test_empty_index_raises_value_error(self):
        retriever = TfidfRetriever()
        with pytest.raises(ValueError, match="empty"):
            retriever.index([])
        assert retriever.is_indexed is False

    def test_duplicate_source_id_raises_value_error(self):
        retriever = TfidfRetriever()
        docs = [
            make_doc("DOC-1", ["user", "login"]),
            make_doc("DOC-1", ["auth", "token"]),
        ]
        with pytest.raises(ValueError, match="Duplicate document source_id"):
            retriever.index(docs)
        assert retriever.is_indexed is False

    def test_successful_index_sets_is_indexed_true(self):
        retriever = TfidfRetriever()
        docs = [
            make_doc("DOC-1", ["auth", "token"]),
            make_doc("DOC-2", ["database", "query"]),
        ]
        retriever.index(docs)
        assert retriever.is_indexed is True

    def test_reindex_replaces_previous_corpus(self):
        retriever = TfidfRetriever()
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
        retriever = TfidfRetriever()
        retriever.index([make_doc("D-1", ["auth"])])
        query = make_doc("Q-1", ["auth"])
        with pytest.raises(ValueError, match="strictly positive"):
            retriever.retrieve(query, top_k=0)

    def test_top_k_negative_raises_value_error(self):
        retriever = TfidfRetriever()
        retriever.index([make_doc("D-1", ["auth"])])
        query = make_doc("Q-1", ["auth"])
        with pytest.raises(ValueError, match="strictly positive"):
            retriever.retrieve(query, top_k=-3)


class TestTfidfHandCalculatedCorpus:
    """Exact hand-calculated 2-document corpus specified in Milestone 2B."""

    def test_hand_calculated_corpus_df_idf_and_scores(self):
        # D1: tokens = ["auth", "token"]
        # D2: tokens = ["auth", "service", "login"]
        # N = 2
        d1 = make_doc("D1", ["auth", "token"])
        d2 = make_doc("D2", ["auth", "service", "login"])
        retriever = TfidfRetriever()
        retriever.index([d1, d2])

        # Vocabulary is sorted unique target tokens
        assert retriever._vocabulary == ["auth", "login", "service", "token"]

        # Verify Document Frequencies:
        # DF(auth) = 2, DF(token) = 1, DF(service) = 1, DF(login) = 1
        auth_idx = retriever._term_to_index["auth"]
        token_idx = retriever._term_to_index["token"]
        service_idx = retriever._term_to_index["service"]
        login_idx = retriever._term_to_index["login"]

        # Verify IDFs: IDF(t) = ln(1 + N / DF(t))
        # IDF(auth) = ln(1 + 2/2) = ln(2)
        # IDF(token) = ln(1 + 2/1) = ln(3)
        expected_idf_auth = math.log(2.0)
        expected_idf_token = math.log(3.0)
        expected_idf_service = math.log(3.0)
        expected_idf_login = math.log(3.0)

        assert retriever._idf[auth_idx] == pytest.approx(expected_idf_auth, abs=1e-12)
        assert retriever._idf[token_idx] == pytest.approx(expected_idf_token, abs=1e-12)
        assert retriever._idf[service_idx] == pytest.approx(
            expected_idf_service, abs=1e-12
        )
        assert retriever._idf[login_idx] == pytest.approx(expected_idf_login, abs=1e-12)

        # Query Q1: tokens = ["auth", "token"]
        q1 = make_doc("Q1", ["auth", "token"])
        candidates = retriever.retrieve(q1)

        assert len(candidates) == 2
        candidate_d1 = next(c for c in candidates if c.target_id == "D1")
        candidate_d2 = next(c for c in candidates if c.target_id == "D2")

        # For D1, Q1 and D1 have identical term weights: cosine must be exactly 1.0
        assert candidate_d1.score == pytest.approx(1.0, abs=1e-6)
        assert candidate_d1.rank == 1

        # For D2, exact vectorized cosine dot(q, d2) / (||q||_2 * ||d2||_2):
        # q weights:   auth: ln(2), token: ln(3)
        #              ||q||_2 = sqrt(ln(2)^2 + ln(3)^2)
        # d2 weights:  auth: ln(2), service: ln(3), login: ln(3)
        #              ||d2||_2 = sqrt(ln(2)^2 + 2 * ln(3)^2)
        # dot(q, d2) = ln(2) * ln(2) = ln(2)^2
        # cosine(q, d2) = ln(2)^2 / (||q||_2 * ||d2||_2)
        expected_cosine_d2 = (expected_idf_auth**2) / (
            math.sqrt(expected_idf_auth**2 + expected_idf_token**2)
            * math.sqrt(
                expected_idf_auth**2 + expected_idf_service**2 + expected_idf_login**2
            )
        )
        assert candidate_d2.score == pytest.approx(expected_cosine_d2, abs=1e-6)
        assert candidate_d2.rank == 2

    def test_single_term_document_cosine_matches_projected_ratio(self):
        # When target contains ONLY the single matching term "auth":
        # d_auth weights: auth: ln(2) => ||d_auth||_2 = ln(2)
        # q weights:      auth: ln(2), token: ln(3) => ||q||_2 = sqrt(ln(2)^2 + ln(3)^2)
        # dot(q, d_auth) = ln(2)^2
        # cosine = ln(2)^2 / (ln(2) * ||q||_2) = ln(2) / sqrt(ln(2)^2 + ln(3)^2)
        d1 = make_doc("D1", ["auth", "token"])
        d_auth = make_doc("D-auth", ["auth"])
        retriever = TfidfRetriever()
        retriever.index([d1, d_auth])

        q = make_doc("Q1", ["auth", "token"])
        candidates = retriever.retrieve(q)

        candidate_auth = next(c for c in candidates if c.target_id == "D-auth")
        expected_ratio = math.log(2.0) / math.sqrt(
            math.log(2.0) ** 2 + math.log(3.0) ** 2
        )
        assert candidate_auth.score == pytest.approx(expected_ratio, abs=1e-6)

    def test_sublinear_tf_with_repeated_tokens(self):
        # D1: "alpha" occurs twice (count=2), "beta" occurs once (count=1)
        # D2: "alpha" occurs once, "beta" occurs once
        # N = 2, DF(alpha) = 2, DF(beta) = 2 => IDF(alpha) = IDF(beta) = ln(2)
        #
        # For D1 with sublinear TF:
        #   TF(alpha, D1) = 1 + ln(2)
        #   TF(beta, D1)  = 1 + ln(1) = 1.0
        #   w(alpha, D1)  = (1 + ln(2)) * ln(2)
        #   w(beta, D1)   = 1.0 * ln(2)
        #   ||D1||_2      = ln(2) * sqrt((1 + ln(2))^2 + 1)
        #
        # Query Q: ["beta"] (w(beta, Q) = ln(2), ||Q||_2 = ln(2))
        # Exact Cosine(Q, D1) = w(beta, D1) / ||D1||_2 = 1 / sqrt((1 + ln(2))^2 + 1)
        #                     ≈ 0.508542
        # If raw TF were used (TF=count=2):
        #   ||D1||_2 would be ln(2) * sqrt(2^2 + 1) = ln(2) * sqrt(5)
        #   Raw TF Cosine would be 1 / sqrt(5) ≈ 0.447214
        d1 = make_doc("D1", ["alpha", "alpha", "beta"])
        d2 = make_doc("D2", ["alpha", "beta"])
        retriever = TfidfRetriever()
        retriever.index([d1, d2])

        q = make_doc("Q", ["beta"])
        candidates = retriever.retrieve(q)

        candidate_d1 = next(c for c in candidates if c.target_id == "D1")
        expected_sublinear_cosine = 1.0 / math.sqrt((1.0 + math.log(2.0)) ** 2 + 1.0)
        raw_tf_cosine = 1.0 / math.sqrt(2.0**2 + 1.0)

        # Confirm exact match to sublinear TF cosine and clear separation from raw TF
        assert candidate_d1.score == pytest.approx(expected_sublinear_cosine, abs=1e-6)
        assert abs(candidate_d1.score - raw_tf_cosine) > 0.05


class TestTfidfEdgeCases:
    def test_empty_query_tokens_gives_zero_scores(self):
        retriever = TfidfRetriever()
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
        retriever = TfidfRetriever()
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
        retriever = TfidfRetriever()
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
        retriever = TfidfRetriever()
        retriever.index(
            [
                make_doc("D1", ["auth", "token"]),
                make_doc("D2", ["cache", "memory"]),
            ]
        )
        # "unseen_token_xyz" should be ignored and not cause errors
        query = make_doc("Q1", ["auth", "unseen_token_xyz"])
        candidates = retriever.retrieve(query)
        c_d1 = next(c for c in candidates if c.target_id == "D1")
        assert c_d1.score > 0.0
        c_d2 = next(c for c in candidates if c.target_id == "D2")
        assert c_d2.score == 0.0

    def test_single_document_corpus(self):
        retriever = TfidfRetriever()
        retriever.index([make_doc("SINGLE", ["auth", "user"])])
        query = make_doc("Q1", ["auth"])
        candidates = retriever.retrieve(query)
        assert len(candidates) == 1
        assert candidates[0].target_id == "SINGLE"
        assert candidates[0].score > 0.0
        assert candidates[0].rank == 1

    def test_all_documents_empty_tokens(self):
        retriever = TfidfRetriever()
        retriever.index([make_doc("D1", []), make_doc("D2", [])])
        query = make_doc("Q1", ["auth"])
        candidates = retriever.retrieve(query)
        assert len(candidates) == 2
        for c in candidates:
            assert c.score == 0.0


class TestTfidfOrderingAndRankInvariants:
    def test_equal_scores_broken_by_target_id_ascending(self):
        retriever = TfidfRetriever()
        # All three documents have identical tokens, thus identical similarity
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
        # Scores are identical
        assert candidates[0].score == candidates[1].score == candidates[2].score
        # Tie-broken deterministically by target_id ascending
        assert [c.target_id for c in candidates] == [
            "a_target",
            "m_target",
            "z_target",
        ]

    def test_ranks_are_consecutive_one_to_n(self):
        retriever = TfidfRetriever()
        docs = [make_doc(f"DOC-{i}", ["term", f"specific_{i}"]) for i in range(5)]
        retriever.index(docs)
        query = make_doc("Q1", ["term"])
        candidates = retriever.retrieve(query, top_k=None)
        assert len(candidates) == 5
        assert [c.rank for c in candidates] == [1, 2, 3, 4, 5]

    def test_ranks_are_consecutive_one_to_k_for_top_k(self):
        retriever = TfidfRetriever()
        docs = [make_doc(f"DOC-{i}", ["term", f"specific_{i}"]) for i in range(5)]
        retriever.index(docs)
        query = make_doc("Q1", ["term"])
        candidates = retriever.retrieve(query, top_k=3)
        assert len(candidates) == 3
        assert [c.rank for c in candidates] == [1, 2, 3]

    def test_top_k_limits_output_length(self):
        retriever = TfidfRetriever()
        docs = [make_doc(f"DOC-{i}", ["term"]) for i in range(10)]
        retriever.index(docs)
        query = make_doc("Q1", ["term"])
        candidates = retriever.retrieve(query, top_k=4)
        assert len(candidates) == 4

    def test_top_k_none_returns_all_including_zero_scores(self):
        retriever = TfidfRetriever()
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
        retriever = TfidfRetriever()
        docs = [make_doc(f"T-{i}", ["token", f"v_{i}"]) for i in range(7)]
        retriever.index(docs)
        query = make_doc("Q1", ["token"])
        candidates = retriever.retrieve(query)
        target_ids = [c.target_id for c in candidates]
        assert len(target_ids) == len(set(target_ids))


class TestTfidfDeterminism:
    def test_indexing_same_corpus_repeatedly_gives_identical_state(self):
        docs = [
            make_doc("D1", ["auth", "token", "service"]),
            make_doc("D2", ["database", "query", "service"]),
            make_doc("D3", ["frontend", "ui", "component"]),
        ]
        r1 = TfidfRetriever()
        r1.index(docs)

        r2 = TfidfRetriever()
        r2.index(docs)

        assert r1._vocabulary == r2._vocabulary
        assert r1._term_to_index == r2._term_to_index
        np.testing.assert_allclose(r1._idf, r2._idf)
        np.testing.assert_allclose(r1._doc_matrix_norm, r2._doc_matrix_norm)

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
        retriever = TfidfRetriever()
        retriever.index(docs)

        matrix_before = retriever._doc_matrix_norm.copy()
        idf_before = retriever._idf.copy()

        q = make_doc("Q", ["auth"])
        for _ in range(5):
            retriever.retrieve(q)

        np.testing.assert_array_equal(retriever._doc_matrix_norm, matrix_before)
        np.testing.assert_array_equal(retriever._idf, idf_before)
        assert retriever.is_indexed is True


class TestTfidfAtomicFailure:
    def test_invalid_reindex_preserves_previous_valid_state(self):
        retriever = TfidfRetriever()
        valid_docs = [
            make_doc("D1", ["auth", "token"]),
            make_doc("D2", ["service", "token"]),
        ]
        retriever.index(valid_docs)
        assert retriever.is_indexed is True
        assert len(retriever._target_ids) == 2

        q = make_doc("Q", ["auth"])
        initial_results = retriever.retrieve(q)

        # Attempt to index invalid corpus with duplicate source_ids
        duplicate_docs = [
            make_doc("ERR", ["one"]),
            make_doc("ERR", ["two"]),
        ]
        with pytest.raises(ValueError, match="Duplicate document source_id"):
            retriever.index(duplicate_docs)

        # Index should still be active with original state
        assert retriever.is_indexed is True
        assert retriever._target_ids == ["D1", "D2"]
        after_results = retriever.retrieve(q)
        assert [(c.target_id, c.score) for c in initial_results] == [
            (c.target_id, c.score) for c in after_results
        ]

    def test_empty_reindex_preserves_previous_valid_state(self):
        retriever = TfidfRetriever()
        valid_docs = [make_doc("D1", ["auth"])]
        retriever.index(valid_docs)

        with pytest.raises(ValueError, match="empty"):
            retriever.index([])

        assert retriever.is_indexed is True
        assert retriever._target_ids == ["D1"]


class TestTfidfProcessedTextContractUsage:
    def test_retriever_uses_source_id_and_tokens_from_processed_text(self):
        doc = ProcessedText(
            source_id="src/module.py#func",
            original_text="def func(): return True",
            normalized_text="def func return true",
            tokens=["def", "func", "return", "true"],
            metadata={"file_type": "python"},
        )
        retriever = TfidfRetriever()
        retriever.index([doc])

        query = ProcessedText(
            source_id="REQ-42",
            original_text="Requirement: func must return true",
            normalized_text="requirement func must return true",
            tokens=["func", "return", "true"],
        )
        candidates = retriever.retrieve(query)
        assert len(candidates) == 1
        candidate = candidates[0]
        assert isinstance(candidate, RetrievalCandidate)
        assert candidate.query_id == "REQ-42"
        assert candidate.target_id == "src/module.py#func"
        assert candidate.retriever_name == "tfidf_cosine"
        assert candidate.score > 0.0
        assert candidate.rank == 1

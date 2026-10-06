"""Comprehensive unit and integration tests for evaluation metrics.

Covers IR metrics, edge cases, ground truth loading, and benchmark harness.
"""

from pathlib import Path

import pytest

from tracewise.evaluation import (
    BenchmarkRunner,
    EvaluationResult,
    QueryEvaluationResult,
    average_precision,
    evaluate_query,
    evaluate_retrieval,
    load_ground_truth,
    mean_average_precision,
    mean_reciprocal_rank,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
    run_sample_project_benchmark,
)
from tracewise.retrieval.models import RetrievalCandidate
from tracewise.retrieval.tfidf import TfidfRetriever


def make_candidate(
    target_id: str,
    rank: int,
    query_id: str = "Q1",
    score: float = 1.0,
    retriever_name: str = "test_retriever",
) -> RetrievalCandidate:
    """Helper to construct a valid RetrievalCandidate for evaluation tests."""
    return RetrievalCandidate(
        query_id=query_id,
        target_id=target_id,
        score=score,
        rank=rank,
        retriever_name=retriever_name,
    )


class TestPrecisionAtK:
    def test_hand_calculated_precision_at_k(self):
        # 6 candidates, 3 relevant targets: T1, T2, T3
        gold = {"T1", "T2", "T3"}
        candidates = [
            make_candidate("T1", 1),  # Hit 1
            make_candidate("X1", 2),
            make_candidate("T2", 3),  # Hit 2
            make_candidate("X2", 4),
            make_candidate("X3", 5),
            make_candidate("T3", 6),  # Hit 3
        ]

        assert precision_at_k(candidates, gold, k=1) == pytest.approx(1.0)
        assert precision_at_k(candidates, gold, k=2) == pytest.approx(0.5)
        assert precision_at_k(candidates, gold, k=3) == pytest.approx(2.0 / 3.0)
        assert precision_at_k(candidates, gold, k=4) == pytest.approx(0.5)
        assert precision_at_k(candidates, gold, k=5) == pytest.approx(0.4)
        assert precision_at_k(candidates, gold, k=6) == pytest.approx(0.5)

    def test_k_larger_than_candidate_list_divides_by_k(self):
        # 2 candidates, both relevant. k = 5.
        # Per standard TREC/IR convention: 2 / 5 = 0.4
        gold = {"T1", "T2"}
        candidates = [make_candidate("T1", 1), make_candidate("T2", 2)]
        assert precision_at_k(candidates, gold, k=5) == pytest.approx(0.4)

    def test_zero_candidates_returns_zero(self):
        assert precision_at_k([], {"T1"}, k=5) == 0.0

    def test_empty_relevant_targets_returns_zero(self):
        candidates = [make_candidate("T1", 1)]
        assert precision_at_k(candidates, set(), k=1) == 0.0

    def test_zero_hits_returns_zero(self):
        candidates = [make_candidate("X1", 1), make_candidate("X2", 2)]
        assert precision_at_k(candidates, {"T1"}, k=2) == 0.0

    def test_invalid_k_raises_value_error(self):
        candidates = [make_candidate("T1", 1)]
        with pytest.raises(ValueError, match="strictly positive"):
            precision_at_k(candidates, {"T1"}, k=0)
        with pytest.raises(ValueError, match="strictly positive"):
            precision_at_k(candidates, {"T1"}, k=-2)

    def test_duplicate_candidate_target_counted_at_most_once(self):
        # If candidate list contains duplicates of T1 in top-k
        candidates = [
            make_candidate("T1", 1),
            make_candidate("T1", 2),
            make_candidate("X1", 3),
        ]
        # Top-2 has two instances of T1, but only 1 distinct relevant target
        assert precision_at_k(candidates, {"T1"}, k=2) == pytest.approx(1.0 / 2.0)


class TestRecallAtK:
    def test_hand_calculated_recall_at_k(self):
        gold = {"T1", "T2", "T3"}
        candidates = [
            make_candidate("T1", 1),  # Hit 1
            make_candidate("X1", 2),
            make_candidate("T2", 3),  # Hit 2
            make_candidate("X2", 4),
            make_candidate("X3", 5),
            make_candidate("T3", 6),  # Hit 3
        ]

        assert recall_at_k(candidates, gold, k=1) == pytest.approx(1.0 / 3.0)
        assert recall_at_k(candidates, gold, k=2) == pytest.approx(1.0 / 3.0)
        assert recall_at_k(candidates, gold, k=3) == pytest.approx(2.0 / 3.0)
        assert recall_at_k(candidates, gold, k=5) == pytest.approx(2.0 / 3.0)
        assert recall_at_k(candidates, gold, k=6) == pytest.approx(1.0)
        assert recall_at_k(candidates, gold, k=10) == pytest.approx(1.0)

    def test_zero_candidates_returns_zero(self):
        assert recall_at_k([], {"T1"}, k=5) == 0.0

    def test_empty_relevant_targets_returns_zero(self):
        candidates = [make_candidate("T1", 1)]
        assert recall_at_k(candidates, set(), k=1) == 0.0

    def test_invalid_k_raises_value_error(self):
        candidates = [make_candidate("T1", 1)]
        with pytest.raises(ValueError, match="strictly positive"):
            recall_at_k(candidates, {"T1"}, k=0)

    def test_duplicate_candidate_target_does_not_inflate_recall(self):
        candidates = [
            make_candidate("T1", 1),
            make_candidate("T1", 2),
        ]
        gold = {"T1", "T2"}
        # Both top-2 items are T1; recall should be 1/2 = 0.5, not 2/2 = 1.0
        assert recall_at_k(candidates, gold, k=2) == pytest.approx(0.5)


class TestAveragePrecision:
    def test_hand_calculated_average_precision_full_ranking(self):
        # 3 relevant targets: T1, T2, T3
        # Hits at ranks 1, 3, 6 out of 6 candidates:
        # P(1) = 1/1 = 1.0
        # P(3) = 2/3
        # P(6) = 3/6 = 0.5
        # Sum = 1.0 + 2/3 + 0.5 = 13/6
        # AP = (13/6) / 3 = 13/18 ≈ 0.722222
        gold = {"T1", "T2", "T3"}
        candidates = [
            make_candidate("T1", 1),
            make_candidate("X1", 2),
            make_candidate("T2", 3),
            make_candidate("X2", 4),
            make_candidate("X3", 5),
            make_candidate("T3", 6),
        ]
        expected_ap = (1.0 + (2.0 / 3.0) + (3.0 / 6.0)) / 3.0
        assert average_precision(candidates, gold) == pytest.approx(
            expected_ap, abs=1e-10
        )

    def test_hand_calculated_average_precision_with_k_cutoff(self):
        # Using same setup as above, with cutoff k=3:
        # Only hits at rank 1 and 3 are counted.
        # P(1) = 1/1, P(3) = 2/3
        # Sum = 1 + 2/3 = 5/3
        # AP@3 = (5/3) / 3 = 5/9 ≈ 0.555556
        gold = {"T1", "T2", "T3"}
        candidates = [
            make_candidate("T1", 1),
            make_candidate("X1", 2),
            make_candidate("T2", 3),
            make_candidate("X2", 4),
            make_candidate("X3", 5),
            make_candidate("T3", 6),
        ]
        expected_ap_3 = (1.0 + (2.0 / 3.0)) / 3.0
        assert average_precision(candidates, gold, k=3) == pytest.approx(
            expected_ap_3, abs=1e-10
        )

    def test_perfect_ranking_gives_1_point_0(self):
        gold = {"T1", "T2"}
        candidates = [make_candidate("T1", 1), make_candidate("T2", 2)]
        assert average_precision(candidates, gold) == pytest.approx(1.0)

    def test_unretrieved_targets_penalize_ap(self):
        # 4 relevant targets, but only 1 retrieved at rank 1:
        # P(1) = 1/1, AP = 1.0 / 4 = 0.25
        gold = {"T1", "T2", "T3", "T4"}
        candidates = [make_candidate("T1", 1), make_candidate("X1", 2)]
        assert average_precision(candidates, gold) == pytest.approx(0.25)

    def test_zero_candidates_or_empty_gold_gives_zero(self):
        assert average_precision([], {"T1"}) == 0.0
        assert average_precision([make_candidate("T1", 1)], set()) == 0.0

    def test_no_hits_gives_zero(self):
        candidates = [make_candidate("X1", 1), make_candidate("X2", 2)]
        assert average_precision(candidates, {"T1"}) == 0.0

    def test_invalid_k_raises_value_error(self):
        with pytest.raises(ValueError, match="strictly positive"):
            average_precision([make_candidate("T1", 1)], {"T1"}, k=0)

    def test_duplicate_target_does_not_repeat_precision_reward(self):
        # T1 at rank 1, T1 repeated at rank 2
        gold = {"T1"}
        candidates = [make_candidate("T1", 1), make_candidate("T1", 2)]
        # Hit at rank 1 gives P(1) = 1.0. Rank 2 is duplicate, ignored.
        # AP = 1.0 / 1 = 1.0
        assert average_precision(candidates, gold) == pytest.approx(1.0)


class TestMeanAveragePrecision:
    def test_hand_calculated_map_across_queries(self):
        # Q1: gold={A}, retrieved=[A] -> AP = 1.0
        # Q2: gold={B, C}, retrieved=[X, B] -> AP = (1/2) / 2 = 0.25
        # Q3: gold={D}, retrieved=[X, Y] -> AP = 0.0
        # MAP = (1.0 + 0.25 + 0.0) / 3 = 1.25 / 3 ≈ 0.416667
        ground_truth = {
            "Q1": {"A"},
            "Q2": {"B", "C"},
            "Q3": {"D"},
        }
        query_candidates = {
            "Q1": [make_candidate("A", 1, query_id="Q1")],
            "Q2": [
                make_candidate("X", 1, query_id="Q2"),
                make_candidate("B", 2, query_id="Q2"),
            ],
            "Q3": [
                make_candidate("X", 1, query_id="Q3"),
                make_candidate("Y", 2, query_id="Q3"),
            ],
        }

        expected_map = (1.0 + 0.25 + 0.0) / 3.0
        assert mean_average_precision(query_candidates, ground_truth) == pytest.approx(
            expected_map, abs=1e-10
        )

    def test_query_missing_from_retriever_scores_zero_and_is_included(self):
        ground_truth = {
            "Q1": {"A"},
            "Q2": {"B"},
        }
        # Retriever only returned results for Q1
        query_candidates = {
            "Q1": [make_candidate("A", 1, query_id="Q1")],
        }
        # Q1 AP = 1.0, Q2 AP = 0.0 -> MAP = 0.5
        assert mean_average_precision(query_candidates, ground_truth) == pytest.approx(
            0.5
        )

    def test_queries_with_empty_gold_set_are_excluded_from_denominator(self):
        ground_truth = {
            "Q1": {"A"},
            "Q_EMPTY": set(),
        }
        query_candidates = {
            "Q1": [make_candidate("A", 1, query_id="Q1")],
        }
        # Only Q1 has relevant targets -> denominator is 1, MAP = 1.0
        assert mean_average_precision(query_candidates, ground_truth) == pytest.approx(
            1.0
        )

    def test_empty_ground_truth_returns_zero(self):
        assert mean_average_precision({}, {}) == 0.0


class TestReciprocalRank:
    def test_hand_calculated_reciprocal_rank(self):
        gold = {"T1"}
        c_rank_1 = [make_candidate("T1", 1)]
        c_rank_2 = [make_candidate("X", 1), make_candidate("T1", 2)]
        c_rank_3 = [
            make_candidate("X", 1),
            make_candidate("Y", 2),
            make_candidate("T1", 3),
        ]

        assert reciprocal_rank(c_rank_1, gold) == pytest.approx(1.0)
        assert reciprocal_rank(c_rank_2, gold) == pytest.approx(0.5)
        assert reciprocal_rank(c_rank_3, gold) == pytest.approx(1.0 / 3.0)

    def test_first_relevant_beyond_k_returns_zero(self):
        gold = {"T1"}
        candidates = [
            make_candidate("X", 1),
            make_candidate("Y", 2),
            make_candidate("T1", 3),
        ]
        assert reciprocal_rank(candidates, gold, k=2) == 0.0
        assert reciprocal_rank(candidates, gold, k=3) == pytest.approx(1.0 / 3.0)

    def test_zero_candidates_or_empty_gold_gives_zero(self):
        assert reciprocal_rank([], {"T1"}) == 0.0
        assert reciprocal_rank([make_candidate("T1", 1)], set()) == 0.0

    def test_no_hits_gives_zero(self):
        candidates = [make_candidate("X1", 1), make_candidate("X2", 2)]
        assert reciprocal_rank(candidates, {"T1"}) == 0.0

    def test_invalid_k_raises_value_error(self):
        with pytest.raises(ValueError, match="strictly positive"):
            reciprocal_rank([make_candidate("T1", 1)], {"T1"}, k=0)


class TestMeanReciprocalRank:
    def test_hand_calculated_mrr(self):
        ground_truth = {
            "Q1": {"A"},
            "Q2": {"B"},
            "Q3": {"C"},
        }
        query_candidates = {
            "Q1": [make_candidate("A", 1)],  # RR = 1.0
            "Q2": [make_candidate("X", 1), make_candidate("B", 2)],  # RR = 0.5
            "Q3": [make_candidate("X", 1)],  # RR = 0.0
        }
        expected_mrr = (1.0 + 0.5 + 0.0) / 3.0
        assert mean_reciprocal_rank(query_candidates, ground_truth) == pytest.approx(
            expected_mrr, abs=1e-10
        )

    def test_empty_ground_truth_returns_zero(self):
        assert mean_reciprocal_rank({}, {}) == 0.0


class TestEvaluationModels:
    def test_query_evaluation_result_valid_construction(self):
        res = QueryEvaluationResult(
            query_id="REQ-001",
            num_relevant=3,
            num_retrieved=10,
            precision_at_k={1: 1.0, 3: 0.6667},
            recall_at_k={1: 0.3333, 3: 0.6667},
            average_precision=0.75,
            reciprocal_rank=1.0,
        )
        assert res.query_id == "REQ-001"
        assert res.num_relevant == 3
        assert res.average_precision == 0.75

    def test_query_evaluation_result_rejects_empty_id_or_invalid_counts(self):
        with pytest.raises(ValueError, match="empty"):
            QueryEvaluationResult(
                query_id="   ",
                num_relevant=1,
                num_retrieved=1,
                precision_at_k={},
                recall_at_k={},
                average_precision=0.5,
                reciprocal_rank=0.5,
            )
        with pytest.raises(ValueError, match="negative"):
            QueryEvaluationResult(
                query_id="REQ-1",
                num_relevant=-1,
                num_retrieved=1,
                precision_at_k={},
                recall_at_k={},
                average_precision=0.5,
                reciprocal_rank=0.5,
            )

    def test_evaluation_result_model_immutability_and_dump(self):
        res = EvaluationResult(
            retriever_name="tfidf_cosine",
            dataset_name="sample_project",
            num_queries=1,
            mean_average_precision=0.8,
            mean_reciprocal_rank=1.0,
            mean_precision_at_k={1: 1.0},
            mean_recall_at_k={1: 0.5},
        )
        dumped = res.model_dump()
        assert dumped["retriever_name"] == "tfidf_cosine"
        assert dumped["mean_average_precision"] == 0.8

        with pytest.raises(ValueError):
            res.mean_average_precision = 0.5  # Frozen

    def test_evaluate_query_helper(self):
        cands = [make_candidate("T1", 1), make_candidate("X1", 2)]
        res = evaluate_query("Q1", cands, {"T1"}, k_values=(1, 2))
        assert res.query_id == "Q1"
        assert res.precision_at_k[1] == 1.0
        assert res.precision_at_k[2] == 0.5
        assert res.average_precision == 1.0
        assert res.reciprocal_rank == 1.0

    def test_evaluate_retrieval_helper(self):
        cands = {"Q1": [make_candidate("T1", 1)]}
        gt = {"Q1": {"T1"}}
        res = evaluate_retrieval("test_ret", cands, gt, dataset_name="toy")
        assert res.retriever_name == "test_ret"
        assert res.dataset_name == "toy"
        assert res.num_queries == 1
        assert res.mean_average_precision == 1.0


class TestGroundTruthLoader:
    @pytest.fixture
    def fixture_file(self) -> Path:
        return (
            Path(__file__).resolve().parent.parent
            / "data"
            / "fixtures"
            / "sample_project"
            / "trace_links.json"
        )

    def test_load_sample_project_ground_truth(self, fixture_file: Path):
        gt = load_ground_truth(fixture_file)
        assert len(gt) == 10
        assert set(gt.keys()) == {f"REQ-{i:03d}" for i in range(1, 11)}

        total_links = sum(len(targets) for targets in gt.values())
        assert total_links == 33

    def test_load_with_artifact_type_filter(self, fixture_file: Path):
        src_gt = load_ground_truth(fixture_file, artifact_type="source_code")
        assert len(src_gt) == 10
        src_total = sum(len(targets) for targets in src_gt.values())
        assert src_total == 16

        test_gt = load_ground_truth(fixture_file, artifact_type="test_case")
        assert len(test_gt) == 10
        test_total = sum(len(targets) for targets in test_gt.values())
        assert test_total == 17

        assert src_total + test_total == 33

    def test_load_with_unknown_filter_yields_empty_mapping(self, fixture_file: Path):
        gt = load_ground_truth(fixture_file, artifact_type="nonexistent")
        assert gt == {}

    def test_load_with_query_key_fn(self, fixture_file: Path):
        gt = load_ground_truth(
            fixture_file,
            query_key_fn=lambda q: f"requirements/{q}.md",
        )
        assert "requirements/REQ-001.md" in gt
        assert len(gt) == 10

    def test_load_missing_file_raises_file_not_found(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            load_ground_truth(tmp_path / "missing.json")

    def test_load_invalid_json_format(self, tmp_path: Path):
        bad_json = tmp_path / "bad.json"
        bad_json.write_text('{"not": "a list"}', encoding="utf-8")
        with pytest.raises(ValueError, match="Expected list"):
            load_ground_truth(bad_json)


class TestGranularityAndExactMatching:
    def test_class_chunk_does_not_match_method_ground_truth(self):
        # Ground truth specifies a method target:
        method_gold = {"src/auth/service.py#AuthenticationService.authenticate_user"}

        # Candidate returns the enclosing class:
        class_candidate = [
            make_candidate(
                "src/auth/service.py#AuthenticationService",
                1,
            )
        ]

        # Exact matching dictates precision and recall must be 0.0
        assert precision_at_k(class_candidate, method_gold, k=1) == 0.0
        assert recall_at_k(class_candidate, method_gold, k=1) == 0.0
        assert average_precision(class_candidate, method_gold) == 0.0

        # When candidate returns the exact method target:
        exact_candidate = [
            make_candidate(
                "src/auth/service.py#AuthenticationService.authenticate_user",
                1,
            )
        ]
        assert precision_at_k(exact_candidate, method_gold, k=1) == 1.0
        assert recall_at_k(exact_candidate, method_gold, k=1) == 1.0
        assert average_precision(exact_candidate, method_gold) == 1.0


class TestSampleProjectB0Evaluation:
    @pytest.fixture
    def sample_project_dir(self) -> Path:
        return (
            Path(__file__).resolve().parent.parent
            / "data"
            / "fixtures"
            / "sample_project"
        )

    def test_b0_sample_project_benchmark_execution(self, sample_project_dir: Path):
        retriever = TfidfRetriever()
        runner = BenchmarkRunner(project_root=sample_project_dir)
        result = runner.run(retriever=retriever, top_k=None)

        assert isinstance(result, EvaluationResult)
        assert result.retriever_name == "tfidf_cosine"
        assert result.dataset_name == "sample_project"
        assert result.num_queries == 10

        # Exact known B0 baseline metrics on sample_project fixture:
        # MAP ≈ 0.7148, MRR ≈ 0.8833
        assert result.mean_average_precision == pytest.approx(0.7148, abs=1e-3)
        assert result.mean_reciprocal_rank == pytest.approx(0.8833, abs=1e-3)

        assert result.mean_precision_at_k[1] == pytest.approx(0.8000, abs=1e-3)
        assert result.mean_precision_at_k[3] == pytest.approx(0.6000, abs=1e-3)
        assert result.mean_precision_at_k[5] == pytest.approx(0.4400, abs=1e-3)

        assert result.mean_recall_at_k[1] == pytest.approx(0.2833, abs=1e-3)
        assert result.mean_recall_at_k[3] == pytest.approx(0.6033, abs=1e-3)
        assert result.mean_recall_at_k[5] == pytest.approx(0.7367, abs=1e-3)

        # Every requirement has an individual query result entry
        assert len(result.query_results) == 10
        for i in range(1, 11):
            qid = f"REQ-{i:03d}"
            assert qid in result.query_results
            q_res = result.query_results[qid]
            assert q_res.num_relevant > 0
            assert q_res.num_retrieved == 53  # All 53 target chunks indexed

    def test_b0_sample_project_helper(self, sample_project_dir: Path):
        result = run_sample_project_benchmark(sample_project_dir=sample_project_dir)
        assert result.retriever_name == "tfidf_cosine"
        assert result.num_queries == 10
        assert result.mean_average_precision == pytest.approx(0.7148, abs=1e-3)

    def test_b0_evaluation_determinism(self, sample_project_dir: Path):
        runner1 = BenchmarkRunner(project_root=sample_project_dir)
        res1 = runner1.run(retriever=TfidfRetriever())

        runner2 = BenchmarkRunner(project_root=sample_project_dir)
        res2 = runner2.run(retriever=TfidfRetriever())

        assert res1.mean_average_precision == res2.mean_average_precision
        assert res1.mean_reciprocal_rank == res2.mean_reciprocal_rank
        assert res1.mean_precision_at_k == res2.mean_precision_at_k
        assert res1.mean_recall_at_k == res2.mean_recall_at_k

    def test_b0_source_code_only_evaluation(self, sample_project_dir: Path):
        runner = BenchmarkRunner(project_root=sample_project_dir)
        result = runner.run(
            retriever=TfidfRetriever(),
            artifact_type_filter="source_code",
        )
        assert result.num_queries == 10
        assert result.metadata["total_target_chunks"] == 26
        assert result.metadata["artifact_type_filter"] == "source_code"

        # Verify only 16 source-code ground-truth links are evaluated
        total_relevant = sum(q.num_relevant for q in result.query_results.values())
        assert total_relevant == 16

        # Verify all queries retrieved exactly 26 source-code chunks
        for q_res in result.query_results.values():
            assert q_res.num_retrieved == 26

        # Exact official B0 source-code baseline metrics:
        assert result.mean_average_precision == pytest.approx(0.7485, abs=1e-3)
        assert result.mean_reciprocal_rank == pytest.approx(0.8500, abs=1e-3)

        assert result.mean_precision_at_k[1] == pytest.approx(0.8000, abs=1e-3)
        assert result.mean_precision_at_k[3] == pytest.approx(0.3667, abs=1e-3)
        assert result.mean_precision_at_k[5] == pytest.approx(0.2400, abs=1e-3)

        assert result.mean_recall_at_k[1] == pytest.approx(0.5500, abs=1e-3)
        assert result.mean_recall_at_k[3] == pytest.approx(0.7500, abs=1e-3)
        assert result.mean_recall_at_k[5] == pytest.approx(0.8000, abs=1e-3)
